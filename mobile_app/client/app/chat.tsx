import { Link } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Image, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Audio } from 'expo-av';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import * as ImagePicker from 'expo-image-picker';

import { buildWsBaseUrl, loadAppConfig } from '../lib/appConfig';
import { requestJson } from '../lib/appHttp';
import { describeError, logDiagnostic } from '../lib/diagnostics';

const VOICE_SEGMENT_MS = 850;
const SOCKET_RECONNECT_MS = 1600;

type ChatEvent = {
  type: string;
  session_id?: string;
  message?: string;
  payload?: Record<string, any>;
};

type ChatMessage = {
  role: 'user' | 'assistant' | 'system';
  content: string;
};

type ScreenPreview = {
  uri: string;
  backend: string;
  width: number;
  height: number;
};

type InterruptPolicy = 'none' | 'steer_now' | 'after_tool';

export default function ChatScreen() {
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [toolLogs, setToolLogs] = useState<string[]>([]);
  const [status, setStatus] = useState('disconnected');
  const [voiceState, setVoiceState] = useState('idle');
  const [voiceDraft, setVoiceDraft] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isVoiceBusy, setIsVoiceBusy] = useState(false);
  const [screenPreview, setScreenPreview] = useState<ScreenPreview | null>(null);
  const [screenStatus, setScreenStatus] = useState('idle');
  const [screenLiveState, setScreenLiveState] = useState('off');
  const [isScreenLive, setIsScreenLive] = useState(false);
  const [steeringBetaEnabled, setSteeringBetaEnabled] = useState(false);
  const [interruptPolicy, setInterruptPolicy] = useState<InterruptPolicy>('none');
  const [apiBaseUrl, setApiBaseUrl] = useState('');
  const [token, setToken] = useState('');
  const [configLoaded, setConfigLoaded] = useState(false);

  const chatWsRef = useRef<WebSocket | null>(null);
  const voiceWsRef = useRef<WebSocket | null>(null);
  const screenWsRef = useRef<WebSocket | null>(null);
  const recordingRef = useRef<Audio.Recording | null>(null);
  const assistantSoundRef = useRef<Audio.Sound | null>(null);
  const assistantAudioPathRef = useRef<string | null>(null);
  const segmentTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chatReconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const voiceReconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const screenReconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const segmentSequenceRef = useRef(0);
  const voiceActiveRef = useRef(false);
  const finishingSegmentRef = useRef<Promise<void> | null>(null);
  const sessionIdRef = useRef<string | undefined>(undefined);
  const steeringArmed = steeringBetaEnabled && interruptPolicy !== 'none';
  const canStartVoice = !isVoiceBusy || steeringArmed;

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    let active = true;
    loadAppConfig()
      .then((config) => {
        if (!active) return;
        setApiBaseUrl(config.apiBaseUrl);
        setToken(config.accessToken);
        setConfigLoaded(true);
      })
      .catch(() => {
        if (!active) return;
        setStatus('config error');
        setConfigLoaded(true);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!configLoaded || !apiBaseUrl) return;

    let active = true;
    requestJson<{ steering_beta_enabled?: boolean }>({
      scope: 'chat.health',
      url: `${apiBaseUrl}/api/app/health`,
    })
      .then((data) => {
        if (!active) return;
        const enabled = Boolean(data?.steering_beta_enabled);
        setSteeringBetaEnabled(enabled);
        if (!enabled) {
          setInterruptPolicy('none');
        }
      })
      .catch(() => {
        if (!active) return;
        setSteeringBetaEnabled(false);
        setInterruptPolicy('none');
      });

    return () => {
      active = false;
    };
  }, [apiBaseUrl, configLoaded]);

  const appendLog = (entry: string) => {
    if (!entry) return;
    setToolLogs((prev) => [entry, ...prev].slice(0, 40));
  };

  const appendAssistantDelta = (delta: string) => {
    if (!delta) return;
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last?.role === 'assistant') {
        last.content += delta;
        return [...next];
      }
      return [...next, { role: 'assistant', content: delta }];
    });
  };

  const applyAssistantFinal = (text: string) => {
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last?.role === 'assistant') {
        last.content = text || last.content;
        return [...next];
      }
      return [...next, { role: 'assistant', content: text }];
    });
  };

  const appendUserMessage = (text: string) => {
    if (!text) return;
    setMessages((prev) => [...prev, { role: 'user', content: text }]);
  };

  const cleanupAssistantAudio = async () => {
    const sound = assistantSoundRef.current;
    assistantSoundRef.current = null;
    if (sound) {
      try {
        sound.setOnPlaybackStatusUpdate(() => undefined);
        await sound.unloadAsync();
      } catch {
        // no-op
      }
    }

    const audioPath = assistantAudioPathRef.current;
    assistantAudioPathRef.current = null;
    if (audioPath) {
      try {
        await FileSystem.deleteAsync(audioPath, { idempotent: true });
      } catch {
        // no-op
      }
    }
  };

  const audioExtensionForMime = (mimeType: string) => {
    if (mimeType.includes('wav')) return 'wav';
    if (mimeType.includes('aac')) return 'aac';
    if (mimeType.includes('flac')) return 'flac';
    if (mimeType.includes('opus')) return 'opus';
    return 'mp3';
  };

  const playAssistantAudio = async (audioBase64: string, mimeType: string) => {
    if (!audioBase64) {
      setVoiceState('idle');
      setStatus('voice ready');
      setIsVoiceBusy(false);
      return;
    }

    const baseDir = FileSystem.cacheDirectory || FileSystem.documentDirectory;
    if (!baseDir) {
      setStatus('audio cache unavailable');
      setVoiceState('idle');
      setIsVoiceBusy(false);
      return;
    }

    try {
      await cleanupAssistantAudio();
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: false,
        playsInSilentModeIOS: true,
      });

      const ext = audioExtensionForMime(mimeType);
      const path = `${baseDir}assistant-${Date.now()}.${ext}`;
      await FileSystem.writeAsStringAsync(path, audioBase64, {
        encoding: FileSystem.EncodingType.Base64,
      });
      assistantAudioPathRef.current = path;

      const { sound } = await Audio.Sound.createAsync(
        { uri: path },
        { shouldPlay: true }
      );
      assistantSoundRef.current = sound;
      setVoiceState('speaking');
      setStatus('assistant speaking');

      sound.setOnPlaybackStatusUpdate((playbackStatus) => {
        if (!playbackStatus.isLoaded) {
          if (playbackStatus.error) {
            setStatus('assistant audio error');
            setVoiceState('idle');
            setIsVoiceBusy(false);
            void cleanupAssistantAudio();
          }
          return;
        }

        if (playbackStatus.didJustFinish) {
          setStatus('voice ready');
          setVoiceState('idle');
          setIsVoiceBusy(false);
          void cleanupAssistantAudio();
        }
      });
    } catch {
      setStatus('assistant audio error');
      setVoiceState('idle');
      setIsVoiceBusy(false);
      await cleanupAssistantAudio();
    }
  };

  const clearReconnectTimers = () => {
    if (chatReconnectRef.current) {
      clearTimeout(chatReconnectRef.current);
      chatReconnectRef.current = null;
    }
    if (voiceReconnectRef.current) {
      clearTimeout(voiceReconnectRef.current);
      voiceReconnectRef.current = null;
    }
    if (screenReconnectRef.current) {
      clearTimeout(screenReconnectRef.current);
      screenReconnectRef.current = null;
    }
  };

  const applyScreenPayload = (payload?: Record<string, any>) => {
    if (!payload?.image_base64 || !payload?.mime_type) return;
    setScreenPreview({
      uri: `data:${String(payload.mime_type)};base64,${String(payload.image_base64)}`,
      backend: String(payload.backend || 'unknown'),
      width: Number(payload.width || 0),
      height: Number(payload.height || 0),
    });
  };

  const handleRealtimeEvent = (data: ChatEvent, channel: 'chat' | 'voice' | 'screen') => {
    if (data.session_id) {
      setSessionId(data.session_id);
    }

    if (channel === 'screen') {
      if (data.type === 'screen_frame') {
        applyScreenPayload(data.payload);
        setScreenStatus('live');
        return;
      }

      if (data.type === 'screen_state') {
        const nextState = String(data.payload?.state || 'idle');
        setScreenLiveState(nextState);
        setScreenStatus(`live ${nextState}`);
        return;
      }
    }

    if (data.type === 'assistant_delta') {
      appendAssistantDelta(String(data.payload?.delta || ''));
      return;
    }

    if (data.type === 'assistant_final') {
      applyAssistantFinal(String(data.payload?.text || ''));
      if (channel !== 'voice') {
        setIsVoiceBusy(false);
      }
      return;
    }

    if (data.type === 'assistant_audio') {
      const audioBase64 = String(data.payload?.audio_base64 || '');
      const mimeType = String(data.payload?.mime_type || 'audio/mpeg');
      void playAssistantAudio(audioBase64, mimeType);
      return;
    }

    if (data.type === 'tool_event') {
      appendLog(JSON.stringify(data.payload || {}));
      return;
    }

    if (data.type === 'warning') {
      const message = String(data.payload?.message || data.message || 'warning');
      if (channel === 'screen') {
        setScreenStatus(message);
        setScreenLiveState('warning');
        appendLog(`[screen] ${message}`);
      } else {
        setStatus(message);
        if (channel === 'voice') {
          setIsVoiceBusy(false);
        }
        appendLog(message);
      }
      return;
    }

    if (data.type === 'error') {
      const message = String(data.payload?.message || data.message || 'error');
      if (channel === 'screen') {
        setScreenStatus(message);
        setScreenLiveState('error');
        appendLog(`[screen] ${message}`);
      } else {
        setStatus(message);
        if (channel === 'voice') {
          setVoiceState('error');
          setIsVoiceBusy(false);
        }
        appendLog(message);
      }
      return;
    }

    if (data.type === 'status' || data.type === 'log') {
      const message = String(data.payload?.message || data.message || '');
      if (message) appendLog(message);
      if (data.type === 'status') {
        if (channel === 'screen') {
          setScreenStatus(message || screenStatus);
        } else {
          setStatus(message || status);
        }
      }
      return;
    }

    if (channel === 'voice') {
      if (data.type === 'voice_state') {
        const nextState = String(data.payload?.state || 'idle');
        setVoiceState(nextState);
        if (nextState === 'idle' || nextState === 'cancelled') {
          setIsVoiceBusy(false);
        }
        if (nextState !== 'listening') {
          setStatus(`voice ${nextState}`);
        }
        return;
      }

      if (data.type === 'voice_partial') {
        setVoiceDraft(String(data.payload?.text || ''));
        return;
      }

      if (data.type === 'voice_final') {
        const transcript = String(data.payload?.text || '');
        setVoiceDraft(transcript);
        appendUserMessage(transcript);
        setVoiceState('processing');
        return;
      }
    }
  };

  const uploadAttachment = async (kind: 'camera' | 'gallery' | 'document') => {
    if (!apiBaseUrl) {
      setStatus('missing backend');
      return;
    }
    if (!token) {
      setStatus('missing token');
      return;
    }

    try {
      let asset: { uri: string; name: string; mimeType?: string | null } | null = null;

      if (kind === 'camera') {
        const permission = await ImagePicker.requestCameraPermissionsAsync();
        if (!permission.granted) {
          setStatus('camera denied');
          return;
        }
        const result = await ImagePicker.launchCameraAsync({
          mediaTypes: ImagePicker.MediaTypeOptions.Images,
          quality: 0.8,
        });
        if (result.canceled || !result.assets?.length) return;
        const picked = result.assets[0];
        asset = { uri: picked.uri, name: picked.fileName || `camera-${Date.now()}.jpg`, mimeType: picked.mimeType };
      } else if (kind === 'gallery') {
        const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
        if (!permission.granted) {
          setStatus('gallery denied');
          return;
        }
        const result = await ImagePicker.launchImageLibraryAsync({
          mediaTypes: ImagePicker.MediaTypeOptions.Images,
          quality: 0.8,
        });
        if (result.canceled || !result.assets?.length) return;
        const picked = result.assets[0];
        asset = { uri: picked.uri, name: picked.fileName || `gallery-${Date.now()}.jpg`, mimeType: picked.mimeType };
      } else {
        const result = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true, multiple: false });
        if (result.canceled || !result.assets?.length) return;
        const picked = result.assets[0];
        asset = { uri: picked.uri, name: picked.name, mimeType: picked.mimeType };
      }

      if (!asset) return;

      const form = new FormData();
      form.append('file', {
        uri: asset.uri,
        name: asset.name,
        type: asset.mimeType || 'application/octet-stream',
      } as any);
      if (sessionIdRef.current) form.append('session_id', sessionIdRef.current);

      const data = await requestJson<{ filename?: string; session_id?: string }>({
        scope: 'chat.upload',
        url: `${apiBaseUrl}/api/app/upload`,
        init: {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          body: form,
        },
      });
      if (data.session_id) setSessionId(String(data.session_id));
      appendLog(`Attached: ${data.filename}`);
      setStatus('attachment ready');
    } catch (error) {
      setStatus(describeError(error));
    }
  };

  const refreshScreenshot = async () => {
    if (!apiBaseUrl) {
      setScreenStatus('missing backend');
      return;
    }
    if (!token) {
      setScreenStatus('missing token');
      return;
    }

    setScreenStatus('capturing');
    try {
      const data = await requestJson<Record<string, any>>({
        scope: 'screen.capture',
        url: `${apiBaseUrl}/api/app/screenshot/current`,
        init: {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        },
      });
      applyScreenPayload(data);
      setScreenStatus('ready');
    } catch (error) {
      setScreenStatus(describeError(error));
    }
  };

  const finishCurrentSegment = async (continueRecording: boolean) => {
    if (finishingSegmentRef.current) {
      await finishingSegmentRef.current;
      if (continueRecording && voiceActiveRef.current && !recordingRef.current) {
        await startSegmentRecording();
      }
      return;
    }

    const finishTask = (async () => {
      if (segmentTimeoutRef.current) {
        clearTimeout(segmentTimeoutRef.current);
        segmentTimeoutRef.current = null;
      }

      const recording = recordingRef.current;
      recordingRef.current = null;
      if (!recording) return;

      try {
        await recording.stopAndUnloadAsync();
      } catch {
        return;
      }

      const uri = recording.getURI();
      if (!uri) return;

      try {
        const base64 = await FileSystem.readAsStringAsync(uri, {
          encoding: FileSystem.EncodingType.Base64,
        });
        segmentSequenceRef.current += 1;
        if (voiceWsRef.current && voiceWsRef.current.readyState === WebSocket.OPEN) {
          logDiagnostic('voice.ws', 'sending voice chunk', {
            sequence: segmentSequenceRef.current,
            sessionId: sessionIdRef.current || null,
          });
          voiceWsRef.current.send(JSON.stringify({
            type: 'voice_chunk',
            session_id: sessionIdRef.current,
            sequence: segmentSequenceRef.current,
            mime_type: 'audio/mp4',
            audio_base64: base64,
          }));
        } else {
          setStatus('voice socket unavailable');
          logDiagnostic('voice.ws', 'voice chunk dropped because socket was unavailable', {
            readyState: voiceWsRef.current?.readyState ?? null,
          }, 'warn');
        }
      } catch (error) {
        setStatus('voice upload error');
        logDiagnostic('voice.ws', 'voice chunk upload preparation failed', describeError(error), 'error');
      } finally {
        try {
          await FileSystem.deleteAsync(uri, { idempotent: true });
        } catch {
          // no-op
        }
      }
    })().finally(() => {
      finishingSegmentRef.current = null;
    });

    finishingSegmentRef.current = finishTask;
    await finishTask;

    if (continueRecording && voiceActiveRef.current) {
      await startSegmentRecording();
    }
  };

  const startSegmentRecording = async () => {
    if (!voiceActiveRef.current || recordingRef.current) return;

    try {
      const recording = new Audio.Recording();
      await recording.prepareToRecordAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      await recording.startAsync();
      recordingRef.current = recording;
      segmentTimeoutRef.current = setTimeout(() => {
        void finishCurrentSegment(true);
      }, VOICE_SEGMENT_MS);
    } catch {
      setStatus('recording error');
      setVoiceState('error');
      setIsRecording(false);
      setIsVoiceBusy(false);
      voiceActiveRef.current = false;
    }
  };

  const startVoiceCapture = async () => {
    if (!configLoaded || !apiBaseUrl) {
      setStatus('missing backend');
      return;
    }
    if (!token) {
      setStatus('missing token');
      return;
    }
    if (isVoiceBusy && !steeringArmed) {
      setStatus('voice still processing');
      return;
    }
    if (!voiceWsRef.current || voiceWsRef.current.readyState !== WebSocket.OPEN) {
      setStatus('voice socket unavailable');
      return;
    }

    try {
      if (isVoiceBusy && steeringArmed) {
        await cleanupAssistantAudio();
      }

      const permission = await Audio.requestPermissionsAsync();
      if (!permission.granted) {
        setStatus('microphone denied');
        return;
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      voiceActiveRef.current = true;
      segmentSequenceRef.current = 0;
      setVoiceDraft('');
      setVoiceState('listening');
      setStatus('voice listening');
      setIsRecording(true);
      setIsVoiceBusy(false);

      voiceWsRef.current.send(JSON.stringify({
        type: 'voice_start',
        session_id: sessionIdRef.current,
      }));
      logDiagnostic('voice.ws', 'sent voice_start', { sessionId: sessionIdRef.current || null });

      await startSegmentRecording();
    } catch (error) {
      setStatus(describeError(error) || 'voice start error');
      logDiagnostic('voice.ws', 'voice start failed', describeError(error), 'error');
      setVoiceState('error');
      setIsRecording(false);
      setIsVoiceBusy(false);
      voiceActiveRef.current = false;
    }
  };

  const stopVoiceCapture = async (commit: boolean) => {
    voiceActiveRef.current = false;
    setIsRecording(false);

    await finishCurrentSegment(false);

    if (voiceWsRef.current && voiceWsRef.current.readyState === WebSocket.OPEN) {
      logDiagnostic('voice.ws', commit ? 'sent voice_commit' : 'sent voice_cancel', {
        sessionId: sessionIdRef.current || null,
        interruptPolicy: commit ? interruptPolicy : 'none',
      });
      voiceWsRef.current.send(JSON.stringify({
        type: commit ? 'voice_commit' : 'voice_cancel',
        session_id: sessionIdRef.current,
        interrupt_policy: commit ? interruptPolicy : 'none',
      }));
    }

    if (commit) {
      setIsVoiceBusy(true);
      setVoiceState('finalizing');
      setStatus('voice finalizing');
    } else {
      setVoiceDraft('');
      setVoiceState('cancelled');
      setStatus('voice cancelled');
      setIsVoiceBusy(false);
    }

    try {
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: false,
        playsInSilentModeIOS: true,
      });
    } catch {
      // no-op
    }
  };

  useEffect(() => {
    if (!configLoaded) return;

    clearReconnectTimers();

    if (!apiBaseUrl) {
      setStatus('missing backend');
      return;
    }
    if (!token) {
      setStatus('missing token');
      return;
    }

    let disposed = false;

    const buildWsUrl = (path: string) => {
      const base = buildWsBaseUrl(apiBaseUrl);
      const params = new URLSearchParams({ token });
      if (sessionIdRef.current) params.set('session_id', sessionIdRef.current);
      return `${base}${path}?${params.toString()}`;
    };

    const connectChatSocket = () => {
      if (disposed) return;
      const url = buildWsUrl('/ws/app/chat');
      logDiagnostic('chat.ws', 'connecting', { url });
      const ws = new WebSocket(url);
      chatWsRef.current = ws;
      ws.onopen = () => {
        logDiagnostic('chat.ws', 'connected', { url });
        setStatus('connected');
      };
      ws.onclose = (event) => {
        logDiagnostic('chat.ws', 'closed', {
          code: event.code,
          reason: event.reason || '<empty>',
          wasClean: event.wasClean,
        }, event.wasClean ? 'info' : 'warn');
        if (chatWsRef.current === ws) chatWsRef.current = null;
        if (!disposed) {
          setStatus('chat reconnecting');
          chatReconnectRef.current = setTimeout(connectChatSocket, SOCKET_RECONNECT_MS);
        }
      };
      ws.onerror = () => {
        logDiagnostic('chat.ws', 'error', { readyState: ws.readyState }, 'error');
        setStatus('chat error');
      };
      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as ChatEvent;
          logDiagnostic('chat.ws', 'message', { type: payload.type || 'unknown' });
          handleRealtimeEvent(payload, 'chat');
        } catch (error) {
          logDiagnostic('chat.ws', 'message parse failed', describeError(error), 'error');
        }
      };
    };

    const connectVoiceSocket = () => {
      if (disposed) return;
      const url = buildWsUrl('/ws/app/voice');
      logDiagnostic('voice.ws', 'connecting', { url });
      const ws = new WebSocket(url);
      voiceWsRef.current = ws;
      ws.onopen = () => {
        logDiagnostic('voice.ws', 'connected', { url });
        setVoiceState('ready');
      };
      ws.onclose = (event) => {
        logDiagnostic('voice.ws', 'closed', {
          code: event.code,
          reason: event.reason || '<empty>',
          wasClean: event.wasClean,
        }, event.wasClean ? 'info' : 'warn');
        if (voiceWsRef.current === ws) voiceWsRef.current = null;
        if (!disposed) {
          setVoiceState('reconnecting');
          voiceReconnectRef.current = setTimeout(connectVoiceSocket, SOCKET_RECONNECT_MS);
        }
      };
      ws.onerror = () => {
        logDiagnostic('voice.ws', 'error', { readyState: ws.readyState }, 'error');
        setVoiceState('error');
      };
      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as ChatEvent;
          logDiagnostic('voice.ws', 'message', { type: payload.type || 'unknown' });
          handleRealtimeEvent(payload, 'voice');
        } catch (error) {
          logDiagnostic('voice.ws', 'message parse failed', describeError(error), 'error');
        }
      };
    };

    connectChatSocket();
    connectVoiceSocket();

    return () => {
      disposed = true;
      clearReconnectTimers();
      voiceActiveRef.current = false;
      if (segmentTimeoutRef.current) {
        clearTimeout(segmentTimeoutRef.current);
        segmentTimeoutRef.current = null;
      }
      if (recordingRef.current) {
        void recordingRef.current.stopAndUnloadAsync().catch(() => undefined);
        recordingRef.current = null;
      }
      void cleanupAssistantAudio();
      if (chatWsRef.current) {
        chatWsRef.current.close();
        chatWsRef.current = null;
      }
      if (voiceWsRef.current) {
        voiceWsRef.current.close();
        voiceWsRef.current = null;
      }
    };
  }, [apiBaseUrl, configLoaded, token]);

  useEffect(() => {
    if (!configLoaded) return;

    if (!apiBaseUrl || !token || !isScreenLive) {
      if (!isScreenLive) {
        setScreenLiveState('off');
        setScreenStatus('idle');
      }
      if (screenReconnectRef.current) {
        clearTimeout(screenReconnectRef.current);
        screenReconnectRef.current = null;
      }
      if (screenWsRef.current) {
        screenWsRef.current.close();
        screenWsRef.current = null;
      }
      return;
    }

    let disposed = false;
    setScreenLiveState('connecting');
    setScreenStatus('live connecting');

    const connectScreenSocket = () => {
      if (disposed) return;
      const base = buildWsBaseUrl(apiBaseUrl);
      const params = new URLSearchParams({
        token,
        fps: '1.2',
        max_width: '960',
        quality: '55',
      });
      const url = `${base}/ws/app/screen?${params.toString()}`;
      logDiagnostic('screen.ws', 'connecting', { url });
      const ws = new WebSocket(url);
      screenWsRef.current = ws;
      ws.onopen = () => {
        logDiagnostic('screen.ws', 'connected', { url });
        setScreenLiveState('connected');
        setScreenStatus('live connected');
      };
      ws.onclose = (event) => {
        logDiagnostic('screen.ws', 'closed', {
          code: event.code,
          reason: event.reason || '<empty>',
          wasClean: event.wasClean,
        }, event.wasClean ? 'info' : 'warn');
        if (screenWsRef.current === ws) {
          screenWsRef.current = null;
        }
        if (!disposed) {
          setScreenLiveState('reconnecting');
          setScreenStatus('live reconnecting');
          screenReconnectRef.current = setTimeout(connectScreenSocket, SOCKET_RECONNECT_MS);
        }
      };
      ws.onerror = () => {
        logDiagnostic('screen.ws', 'error', { readyState: ws.readyState }, 'error');
        setScreenLiveState('error');
        setScreenStatus('live error');
      };
      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as ChatEvent;
          logDiagnostic('screen.ws', 'message', { type: payload.type || 'unknown' });
          handleRealtimeEvent(payload, 'screen');
        } catch (error) {
          logDiagnostic('screen.ws', 'message parse failed', describeError(error), 'error');
        }
      };
    };

    connectScreenSocket();

    return () => {
      disposed = true;
      if (screenReconnectRef.current) {
        clearTimeout(screenReconnectRef.current);
        screenReconnectRef.current = null;
      }
      if (screenWsRef.current) {
        screenWsRef.current.close();
        screenWsRef.current = null;
      }
    };
  }, [apiBaseUrl, configLoaded, isScreenLive, token]);

  const send = () => {
    const trimmed = input.trim();
    if (!trimmed || !chatWsRef.current || chatWsRef.current.readyState !== WebSocket.OPEN) return;
    appendUserMessage(trimmed);
    logDiagnostic('chat.ws', 'sending chat message', {
      sessionId: sessionIdRef.current || null,
      interruptPolicy,
      textPreview: trimmed.slice(0, 140),
    });
    chatWsRef.current.send(JSON.stringify({
      text: trimmed,
      session_id: sessionIdRef.current,
      interrupt_policy: interruptPolicy,
    }));
    setInput('');
    setVoiceDraft('');
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>EmploAI Chat</Text>
        <Text style={styles.meta}>Status: {status}</Text>
        <Text style={styles.meta}>Voice: {voiceState}</Text>
        <Text style={styles.meta}>Backend: {apiBaseUrl || 'not set'}</Text>
        <Text style={styles.meta}>Session: {sessionId || 'none'}</Text>
        <Link href="/diagnostics" style={styles.diagnosticsLink}>Open Diagnostics</Link>
      </View>

      {(!apiBaseUrl || !token) ? (
        <View style={styles.setupCard}>
          <Text style={styles.setupTitle}>Setup required</Text>
          <Text style={styles.setupText}>
            {apiBaseUrl
              ? 'This device still needs an app token. Open Pair or Settings before starting a chat.'
              : 'Add the VPS backend URL first, then pair this device to get a token.'}
          </Text>
          <View style={styles.setupActions}>
            <Link href="/pair" style={styles.setupLink}>Open Pair</Link>
            <Link href="/settings" style={styles.setupLink}>Open Settings</Link>
            <Link href="/diagnostics" style={styles.setupLink}>Open Diagnostics</Link>
          </View>
        </View>
      ) : null}

      <View style={styles.screenCard}>
        <View style={styles.screenHeader}>
          <Text style={styles.screenTitle}>VPS screen</Text>
          <View style={styles.screenActions}>
            <Pressable style={styles.secondaryButton} onPress={() => void refreshScreenshot()}>
              <Text style={styles.buttonText}>Refresh</Text>
            </Pressable>
            <Pressable
              style={[styles.secondaryButton, isScreenLive ? styles.liveButton : null]}
              onPress={() => setIsScreenLive((prev) => !prev)}
            >
              <Text style={styles.buttonText}>{isScreenLive ? 'Live Off' : 'Live On'}</Text>
            </Pressable>
          </View>
        </View>
        <Text style={styles.meta}>Capture: {screenStatus}</Text>
        <Text style={styles.meta}>Live: {screenLiveState}</Text>
        {screenPreview ? (
          <>
            <Image source={{ uri: screenPreview.uri }} style={styles.screenPreview} resizeMode="cover" />
            <Text style={styles.meta}>
              {screenPreview.backend} | {screenPreview.width}x{screenPreview.height}
            </Text>
          </>
        ) : (
          <Text style={styles.screenEmpty}>No screenshot yet.</Text>
        )}
      </View>

      {(voiceDraft || isRecording || isVoiceBusy) ? (
        <View style={styles.voiceCard}>
          <Text style={styles.voiceTitle}>Voice draft</Text>
          <Text style={styles.voiceText}>
            {voiceDraft || (isRecording ? 'Listening... transcript will appear here.' : 'Finalizing voice input...')}
          </Text>
        </View>
      ) : null}

      <ScrollView style={styles.messages} contentContainerStyle={styles.messagesContent}>
        {messages.map((message, index) => (
          <View key={`${message.role}-${index}`} style={[styles.bubble, message.role === 'user' ? styles.userBubble : styles.assistantBubble]}>
            <Text style={styles.bubbleRole}>{message.role}</Text>
            <Text style={styles.bubbleText}>{message.content}</Text>
          </View>
        ))}
      </ScrollView>

      <View style={styles.logsCard}>
        <Text style={styles.logsTitle}>Tool / status feed</Text>
        {toolLogs.length === 0 ? (
          <Text style={styles.logsEmpty}>No events yet.</Text>
        ) : (
          toolLogs.slice(0, 6).map((entry, index) => (
            <Text key={`${entry}-${index}`} style={styles.logLine}>{entry}</Text>
          ))
        )}
      </View>

      <View style={styles.attachRow}>
        <Pressable style={styles.secondaryButton} onPress={() => void uploadAttachment('camera')}>
          <Text style={styles.buttonText}>Camera</Text>
        </Pressable>
        <Pressable style={styles.secondaryButton} onPress={() => void uploadAttachment('gallery')}>
          <Text style={styles.buttonText}>Gallery</Text>
        </Pressable>
        <Pressable style={styles.secondaryButton} onPress={() => void uploadAttachment('document')}>
          <Text style={styles.buttonText}>Document</Text>
        </Pressable>
      </View>

      {steeringBetaEnabled ? (
        <View style={styles.betaCard}>
          <Text style={styles.betaTitle}>Beta Steering</Text>
          <View style={styles.betaActions}>
            <Pressable
              style={[styles.betaButton, interruptPolicy === 'none' ? styles.betaButtonActive : null]}
              onPress={() => setInterruptPolicy('none')}
            >
              <Text style={styles.buttonText}>Standard</Text>
            </Pressable>
            <Pressable
              style={[styles.betaButton, interruptPolicy === 'steer_now' ? styles.betaButtonActive : null]}
              onPress={() => setInterruptPolicy('steer_now')}
            >
              <Text style={styles.buttonText}>Steer Now</Text>
            </Pressable>
            <Pressable
              style={[styles.betaButton, interruptPolicy === 'after_tool' ? styles.betaButtonActive : null]}
              onPress={() => setInterruptPolicy('after_tool')}
            >
              <Text style={styles.buttonText}>After Tool</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      <View style={styles.voiceActionsRow}>
        {isRecording ? (
          <>
            <Pressable style={styles.voiceStopButton} onPress={() => void stopVoiceCapture(true)}>
              <Text style={styles.buttonText}>Stop & Send</Text>
            </Pressable>
            <Pressable style={styles.voiceCancelButton} onPress={() => void stopVoiceCapture(false)}>
              <Text style={styles.buttonText}>Cancel</Text>
            </Pressable>
          </>
        ) : (
          <Pressable
            style={[styles.voiceStartButton, !canStartVoice ? styles.disabledButton : null]}
            onPress={() => void startVoiceCapture()}
            disabled={!canStartVoice}
          >
            <Text style={styles.buttonText}>
              {isVoiceBusy ? (steeringArmed ? 'Interrupt With Voice' : 'Voice Busy') : 'Start Voice'}
            </Text>
          </Pressable>
        )}
      </View>

      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="Send a message"
          placeholderTextColor="#7f8aa3"
        />
        <Pressable style={styles.button} onPress={send}>
          <Text style={styles.buttonText}>Send</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0b1020', padding: 16, gap: 12 },
  header: { gap: 4 },
  title: { color: '#fff', fontSize: 24, fontWeight: '700' },
  meta: { color: '#9aa9c7', fontSize: 13 },
  diagnosticsLink: { color: '#7cc7ff', fontSize: 14, fontWeight: '600' },
  setupCard: { backgroundColor: '#16253f', borderRadius: 16, padding: 12, gap: 8 },
  setupTitle: { color: '#fff', fontWeight: '700', fontSize: 15 },
  setupText: { color: '#d9e7ff', fontSize: 14, lineHeight: 20 },
  setupActions: { flexDirection: 'row', gap: 12, flexWrap: 'wrap' },
  setupLink: { color: '#7cc7ff', fontSize: 15, fontWeight: '600' },
  voiceCard: { backgroundColor: '#16253f', borderRadius: 16, padding: 12, gap: 8 },
  voiceTitle: { color: '#fff', fontWeight: '700', fontSize: 15 },
  voiceText: { color: '#d9e7ff', fontSize: 14 },
  screenCard: { backgroundColor: '#141c33', borderRadius: 16, padding: 12, gap: 8 },
  screenHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  screenActions: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  screenTitle: { color: '#fff', fontWeight: '700', fontSize: 15 },
  screenPreview: { width: '100%', aspectRatio: 16 / 10, borderRadius: 12, backgroundColor: '#0f1730' },
  screenEmpty: { color: '#9aa9c7', fontSize: 13 },
  messages: { flex: 1 },
  messagesContent: { gap: 10, paddingBottom: 10 },
  bubble: { borderRadius: 14, padding: 12, gap: 6 },
  userBubble: { backgroundColor: '#21406b', alignSelf: 'flex-end', maxWidth: '86%' },
  assistantBubble: { backgroundColor: '#172038', alignSelf: 'flex-start', maxWidth: '92%' },
  bubbleRole: { color: '#7cc7ff', fontWeight: '700', fontSize: 12 },
  bubbleText: { color: '#e8eefc', fontSize: 15 },
  logsCard: { backgroundColor: '#141c33', borderRadius: 16, padding: 12, gap: 8 },
  logsTitle: { color: '#fff', fontWeight: '700' },
  logsEmpty: { color: '#9aa9c7' },
  logLine: { color: '#c9d7f3', fontSize: 12 },
  attachRow: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  betaCard: { backgroundColor: '#16253f', borderRadius: 16, padding: 12, gap: 8 },
  betaTitle: { color: '#fff', fontWeight: '700', fontSize: 15 },
  betaActions: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  betaButton: { backgroundColor: '#223153', borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10 },
  betaButtonActive: { backgroundColor: '#3b82f6' },
  secondaryButton: { backgroundColor: '#223153', borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10 },
  liveButton: { backgroundColor: '#0f8f62' },
  voiceActionsRow: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  voiceStartButton: { backgroundColor: '#0f8f62', borderRadius: 12, paddingHorizontal: 18, paddingVertical: 12 },
  voiceStopButton: { backgroundColor: '#b45309', borderRadius: 12, paddingHorizontal: 18, paddingVertical: 12 },
  voiceCancelButton: { backgroundColor: '#6a2630', borderRadius: 12, paddingHorizontal: 18, paddingVertical: 12 },
  disabledButton: { opacity: 0.55 },
  inputRow: { flexDirection: 'row', gap: 10, alignItems: 'center' },
  input: { flex: 1, backgroundColor: '#141c33', color: '#fff', borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12 },
  button: { backgroundColor: '#3b82f6', borderRadius: 12, paddingHorizontal: 18, paddingVertical: 12 },
  buttonText: { color: '#fff', fontWeight: '700' },
});
