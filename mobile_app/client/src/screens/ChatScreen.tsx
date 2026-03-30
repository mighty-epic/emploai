import { Link, useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Image, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Audio } from 'expo-av';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import * as ImagePicker from 'expo-image-picker';

import { buildWsBaseUrl, loadAppConfig } from '../../lib/appConfig';
import { requestJson } from '../../lib/appHttp';
import { describeError, logDiagnostic } from '../../lib/diagnostics';
import { AppDrawer, type DrawerTab } from '@/components/AppDrawer';
import { CollapsibleSection } from '@/components/CollapsibleSection';
import {
  createSession,
  fetchJobs,
  fetchProfile,
  fetchSessionDetail,
  fetchSessions,
  type ScheduledJob,
  type SessionDetail,
  type SessionMessage,
  type SessionSummary,
} from '@/lib/appApi';
import { formatAbsoluteTime, formatRelativeTime } from '@/lib/time';

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
  timestamp?: string | null;
  displayLabel?: string | null;
  channel?: 'telegram' | 'app' | 'system' | null;
};

type ScreenPreview = {
  uri: string;
  backend: string;
  width: number;
  height: number;
};

type InterruptPolicy = 'none' | 'steer_now' | 'after_tool';

function normalizeRouteSessionId(value: string | string[] | undefined) {
  if (Array.isArray(value)) {
    return value[0];
  }
  return value;
}

function toChatMessage(message: SessionMessage): ChatMessage {
  return {
    role: message.role || 'assistant',
    content: message.content || '',
    timestamp: message.timestamp,
    displayLabel: message.display_label,
    channel: message.channel,
  };
}

function labelForMessage(message: ChatMessage) {
  if (message.displayLabel) return message.displayLabel;
  if (message.role === 'assistant') return 'Assistant';
  if (message.role === 'system') return 'System';
  return 'You';
}

export default function ChatScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ sessionId?: string | string[]; newSession?: string | string[] }>();
  const requestedSessionId = normalizeRouteSessionId(params.sessionId);
  const requestedNewSession = normalizeRouteSessionId(params.newSession);

  const [sessionId, setSessionId] = useState<string | undefined>();
  const [sessionName, setSessionName] = useState('New chat');
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
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
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>('chats');

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
  const setupMissing = !apiBaseUrl || !token;

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

  const applySessionDetail = (detail: SessionDetail) => {
    setSessionId(detail.id);
    setSessionName(detail.name);
    setMessages(detail.messages.map((message) => toChatMessage(message)));
  };

  const refreshSidebarData = async () => {
    if (!apiBaseUrl || !token) return;
    try {
      const [sessionsData, jobsData] = await Promise.all([
        fetchSessions(apiBaseUrl, token),
        fetchJobs(apiBaseUrl, token),
      ]);
      setSessions(Array.isArray(sessionsData) ? sessionsData : []);
      setJobs(Array.isArray(jobsData) ? jobsData : []);
      const activeSummary = sessionsData.find((session) => session.id === sessionIdRef.current);
      if (activeSummary) {
        setSessionName(activeSummary.name);
      }
    } catch {
      // Sidebar data should not interrupt the active chat.
    }
  };

  const selectSession = async (nextSessionId: string, options?: { updateRoute?: boolean; keepLogs?: boolean }) => {
    if (!apiBaseUrl || !token) {
      setStatus('missing backend');
      return;
    }

    setStatus('loading session');
    try {
      const detail = await fetchSessionDetail(apiBaseUrl, token, nextSessionId);
      applySessionDetail(detail);
      if (!options?.keepLogs) {
        setToolLogs([]);
      }
      if (options?.updateRoute !== false) {
        router.replace({ pathname: '/chat', params: { sessionId: detail.id } });
      }
      setStatus('connected');
      void refreshSidebarData();
    } catch (error) {
      setStatus(describeError(error));
    }
  };

  const createConversation = async () => {
    if (!apiBaseUrl || !token) {
      setStatus('missing backend');
      return;
    }

    setStatus('creating session');
    try {
      const data = await createSession(apiBaseUrl, token);
      applySessionDetail(data.session);
      setToolLogs([]);
      router.replace({ pathname: '/chat', params: { sessionId: data.session.id } });
      setStatus('session ready');
      void refreshSidebarData();
    } catch (error) {
      setStatus(describeError(error));
    }
  };

  useEffect(() => {
    if (!configLoaded) return;
    if (!apiBaseUrl || !token) return;

    let cancelled = false;

    (async () => {
      try {
        const [profile, sessionsData, jobsData] = await Promise.all([
          fetchProfile(apiBaseUrl, token),
          fetchSessions(apiBaseUrl, token),
          fetchJobs(apiBaseUrl, token),
        ]);

        if (cancelled) return;
        setSessions(Array.isArray(sessionsData) ? sessionsData : []);
        setJobs(Array.isArray(jobsData) ? jobsData : []);

        if (requestedNewSession === '1') {
          const created = await createSession(apiBaseUrl, token);
          if (cancelled) return;
          applySessionDetail(created.session);
          setStatus('session ready');
          void refreshSidebarData();
          router.replace({ pathname: '/chat', params: { sessionId: created.session.id } });
          return;
        }

        const nextSessionId = requestedSessionId || profile.current_session_id || sessionsData[0]?.id || undefined;
        if (nextSessionId) {
          const detail = await fetchSessionDetail(apiBaseUrl, token, nextSessionId);
          if (cancelled) return;
          applySessionDetail(detail);
          setStatus('connected');
        } else {
          setSessionId(undefined);
          setSessionName('New chat');
          setMessages([]);
          setStatus('ready');
        }
      } catch (error) {
        if (cancelled) return;
        setStatus(describeError(error));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, configLoaded, requestedNewSession, requestedSessionId, router, token]);

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
      return [...next, { role: 'assistant', content: delta, displayLabel: 'Assistant' }];
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
      return [...next, { role: 'assistant', content: text, displayLabel: 'Assistant' }];
    });
  };

  const appendUserMessage = (text: string) => {
    if (!text) return;
    setMessages((prev) => [...prev, { role: 'user', content: text, displayLabel: 'You' }]);
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
      void refreshSidebarData();
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
        void refreshSidebarData();
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
      if (data.session_id) {
        setSessionId(String(data.session_id));
      }
      appendLog(`Attached: ${data.filename}`);
      setStatus('attachment ready');
      void refreshSidebarData();
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

  const statusCards = [
    { label: 'Status', value: status },
    { label: 'Voice', value: voiceState },
    { label: 'Session', value: sessionId ? `${sessionName} (${sessionId})` : 'None' },
  ];

  return (
    <SafeAreaView style={styles.container}>
      <AppDrawer
        visible={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        initialTab={drawerTab}
        sessions={sessions}
        jobs={jobs}
        activeSessionId={sessionId}
        backendLabel={apiBaseUrl || 'Backend not configured'}
        onSelectSession={(nextSessionId) => {
          void selectSession(nextSessionId, { updateRoute: false });
        }}
        onCreateSession={() => {
          void createConversation();
        }}
      />

      <View style={styles.topBar}>
        <Pressable
          style={styles.topButton}
          onPress={() => {
            setDrawerTab('chats');
            setDrawerOpen(true);
          }}
        >
          <Text style={styles.topButtonText}>Menu</Text>
        </Pressable>
        <View style={styles.titleBlock}>
          <Text style={styles.title}>{sessionName}</Text>
          <Text style={styles.subtitle}>
            {sessionId ? `Updated ${formatRelativeTime(sessions.find((item) => item.id === sessionId)?.updated_at)}` : 'Ready for a new conversation'}
          </Text>
        </View>
        <Pressable style={styles.topButton} onPress={() => void refreshSidebarData()}>
          <Text style={styles.topButtonText}>Refresh</Text>
        </Pressable>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.statusRow}>
        {statusCards.map((card) => (
          <View key={card.label} style={styles.statusChip}>
            <Text style={styles.statusLabel}>{card.label}</Text>
            <Text style={styles.statusValue}>{card.value}</Text>
          </View>
        ))}
      </ScrollView>

      {setupMissing ? (
        <View style={styles.setupCard}>
          <Text style={styles.setupTitle}>Setup required</Text>
          <Text style={styles.setupText}>
            {apiBaseUrl
              ? 'This device still needs a saved token. Finish pairing before you start chatting.'
              : 'Add the backend URL first, then pair this device. After that this screen becomes your main workspace.'}
          </Text>
          <View style={styles.setupActions}>
            <Link href="/pair" style={styles.setupLink}>Open Pair</Link>
            <Link href="/settings" style={styles.setupLink}>Open Settings</Link>
            <Link href="/diagnostics" style={styles.setupLink}>Open Diagnostics</Link>
          </View>
        </View>
      ) : null}

      <ScrollView style={styles.messages} contentContainerStyle={styles.messagesContent}>
        {messages.length === 0 ? (
          <View style={styles.emptyState}>
            <Text style={styles.emptyTitle}>Chat-first workspace</Text>
            <Text style={styles.emptyText}>
              Open an existing session from the sidebar or start typing here. Cron jobs run in the background and now live in their own sidebar tab instead of crowding the conversation.
            </Text>
            <View style={styles.emptyActions}>
              <Pressable style={styles.primaryButton} onPress={() => void createConversation()}>
                <Text style={styles.primaryButtonText}>New chat</Text>
              </Pressable>
              <Pressable
                style={styles.secondaryButton}
                onPress={() => {
                  setDrawerTab('cron');
                  setDrawerOpen(true);
                }}
              >
                <Text style={styles.secondaryButtonText}>Open Cron</Text>
              </Pressable>
            </View>
          </View>
        ) : (
          messages.map((message, index) => (
            <View
              key={`${message.role}-${index}-${message.timestamp || ''}`}
              style={[
                styles.bubble,
                message.role === 'user'
                  ? styles.userBubble
                  : message.role === 'system'
                    ? styles.systemBubble
                    : styles.assistantBubble,
              ]}
            >
              <View style={styles.bubbleHeader}>
                <Text style={styles.bubbleRole}>{labelForMessage(message)}</Text>
                {message.timestamp ? (
                  <Text style={styles.bubbleTime}>{formatAbsoluteTime(message.timestamp)}</Text>
                ) : null}
              </View>
              <Text style={styles.bubbleText}>{message.content}</Text>
            </View>
          ))
        )}
      </ScrollView>

      {voiceDraft || isRecording || isVoiceBusy ? (
        <View style={styles.voiceBanner}>
          <Text style={styles.voiceBannerTitle}>Voice</Text>
          <Text style={styles.voiceBannerText}>
            {voiceDraft || (isRecording ? 'Listening... transcript will appear here.' : 'Finalizing voice input...')}
          </Text>
        </View>
      ) : null}

      <View style={styles.utilityStack}>
        <CollapsibleSection title="Remote view" meta={`${screenStatus} · ${screenLiveState}`}>
          <View style={styles.rowWrap}>
            <Pressable style={styles.secondaryButton} onPress={() => void refreshScreenshot()}>
              <Text style={styles.secondaryButtonText}>Refresh screen</Text>
            </Pressable>
            <Pressable
              style={[styles.secondaryButton, isScreenLive ? styles.liveButton : null]}
              onPress={() => setIsScreenLive((prev) => !prev)}
            >
              <Text style={styles.secondaryButtonText}>{isScreenLive ? 'Stop live' : 'Start live'}</Text>
            </Pressable>
          </View>
          {screenPreview ? (
            <>
              <Image source={{ uri: screenPreview.uri }} style={styles.screenPreview} resizeMode="cover" />
              <Text style={styles.helperText}>
                {screenPreview.backend} · {screenPreview.width}x{screenPreview.height}
              </Text>
            </>
          ) : (
            <Text style={styles.helperText}>No screenshot yet.</Text>
          )}
        </CollapsibleSection>

        <CollapsibleSection title="Composer tools" meta="Uploads, steering, and live controls">
          <View style={styles.rowWrap}>
            <Pressable style={styles.secondaryButton} onPress={() => void uploadAttachment('camera')}>
              <Text style={styles.secondaryButtonText}>Camera</Text>
            </Pressable>
            <Pressable style={styles.secondaryButton} onPress={() => void uploadAttachment('gallery')}>
              <Text style={styles.secondaryButtonText}>Gallery</Text>
            </Pressable>
            <Pressable style={styles.secondaryButton} onPress={() => void uploadAttachment('document')}>
              <Text style={styles.secondaryButtonText}>Document</Text>
            </Pressable>
          </View>
          {steeringBetaEnabled ? (
            <View style={styles.betaBlock}>
              <Text style={styles.helperText}>Beta steering</Text>
              <View style={styles.rowWrap}>
                <Pressable
                  style={[styles.secondaryButton, interruptPolicy === 'none' ? styles.activeSecondary : null]}
                  onPress={() => setInterruptPolicy('none')}
                >
                  <Text style={styles.secondaryButtonText}>Standard</Text>
                </Pressable>
                <Pressable
                  style={[styles.secondaryButton, interruptPolicy === 'steer_now' ? styles.activeSecondary : null]}
                  onPress={() => setInterruptPolicy('steer_now')}
                >
                  <Text style={styles.secondaryButtonText}>Steer now</Text>
                </Pressable>
                <Pressable
                  style={[styles.secondaryButton, interruptPolicy === 'after_tool' ? styles.activeSecondary : null]}
                  onPress={() => setInterruptPolicy('after_tool')}
                >
                  <Text style={styles.secondaryButtonText}>After tool</Text>
                </Pressable>
              </View>
            </View>
          ) : null}
        </CollapsibleSection>

        <CollapsibleSection title="Run feed" meta={toolLogs.length ? `${toolLogs.length} recent updates` : 'Quiet'}>
          {toolLogs.length === 0 ? (
            <Text style={styles.helperText}>No tool or status updates yet.</Text>
          ) : (
            toolLogs.slice(0, 8).map((entry, index) => (
              <Text key={`${entry}-${index}`} style={styles.logLine}>{entry}</Text>
            ))
          )}
        </CollapsibleSection>
      </View>

      <View style={styles.composerShell}>
        <View style={styles.voiceRow}>
          {isRecording ? (
            <>
              <Pressable style={styles.voiceStopButton} onPress={() => void stopVoiceCapture(true)}>
                <Text style={styles.voiceButtonText}>Stop and send</Text>
              </Pressable>
              <Pressable style={styles.voiceCancelButton} onPress={() => void stopVoiceCapture(false)}>
                <Text style={styles.voiceButtonText}>Cancel</Text>
              </Pressable>
            </>
          ) : (
            <Pressable
              style={[styles.voiceStartButton, !canStartVoice ? styles.disabledButton : null]}
              onPress={() => void startVoiceCapture()}
              disabled={!canStartVoice}
            >
              <Text style={styles.voiceButtonText}>
                {isVoiceBusy ? (steeringArmed ? 'Interrupt with voice' : 'Voice busy') : 'Start voice'}
              </Text>
            </Pressable>
          )}
          <Pressable
            style={styles.secondaryButton}
            onPress={() => {
              setDrawerTab('cron');
              setDrawerOpen(true);
            }}
          >
            <Text style={styles.secondaryButtonText}>Cron</Text>
          </Pressable>
        </View>

        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            value={input}
            onChangeText={setInput}
            placeholder="Message EmploAI"
            placeholderTextColor="#7f8aa3"
            multiline
          />
          <Pressable style={styles.sendButton} onPress={send}>
            <Text style={styles.sendButtonText}>Send</Text>
          </Pressable>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0b1020',
    paddingHorizontal: 16,
    paddingTop: 14,
    gap: 12,
  },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  topButton: {
    backgroundColor: '#182342',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  topButtonText: {
    color: '#dce8ff',
    fontWeight: '700',
    fontSize: 13,
  },
  titleBlock: {
    flex: 1,
    gap: 4,
  },
  title: {
    color: '#ffffff',
    fontSize: 24,
    fontWeight: '700',
  },
  subtitle: {
    color: '#8fa2c8',
    fontSize: 13,
  },
  statusRow: {
    gap: 8,
    paddingRight: 20,
  },
  statusChip: {
    backgroundColor: '#141c33',
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
    minWidth: 118,
    gap: 4,
  },
  statusLabel: {
    color: '#7f93bc',
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  statusValue: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: '600',
  },
  setupCard: {
    backgroundColor: '#16253f',
    borderRadius: 18,
    padding: 14,
    gap: 8,
  },
  setupTitle: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '700',
  },
  setupText: {
    color: '#d9e7ff',
    fontSize: 14,
    lineHeight: 20,
  },
  setupActions: {
    flexDirection: 'row',
    gap: 12,
    flexWrap: 'wrap',
  },
  setupLink: {
    color: '#7cc7ff',
    fontSize: 14,
    fontWeight: '700',
  },
  messages: {
    flex: 1,
  },
  messagesContent: {
    gap: 12,
    paddingBottom: 8,
  },
  emptyState: {
    backgroundColor: '#141c33',
    borderRadius: 22,
    padding: 18,
    gap: 10,
  },
  emptyTitle: {
    color: '#ffffff',
    fontSize: 18,
    fontWeight: '700',
  },
  emptyText: {
    color: '#d6e2fb',
    fontSize: 15,
    lineHeight: 22,
  },
  emptyActions: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
    paddingTop: 4,
  },
  bubble: {
    borderRadius: 18,
    padding: 14,
    gap: 8,
  },
  userBubble: {
    backgroundColor: '#21406b',
    alignSelf: 'flex-end',
    maxWidth: '88%',
  },
  assistantBubble: {
    backgroundColor: '#172038',
    alignSelf: 'flex-start',
    maxWidth: '94%',
  },
  systemBubble: {
    backgroundColor: '#1f2941',
    alignSelf: 'center',
    maxWidth: '96%',
  },
  bubbleHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 10,
  },
  bubbleRole: {
    color: '#8ecfff',
    fontWeight: '700',
    fontSize: 12,
  },
  bubbleTime: {
    color: '#8194b9',
    fontSize: 11,
  },
  bubbleText: {
    color: '#eef4ff',
    fontSize: 15,
    lineHeight: 22,
  },
  voiceBanner: {
    backgroundColor: '#16253f',
    borderRadius: 18,
    padding: 12,
    gap: 6,
  },
  voiceBannerTitle: {
    color: '#ffffff',
    fontWeight: '700',
  },
  voiceBannerText: {
    color: '#dce8ff',
    fontSize: 14,
  },
  utilityStack: {
    gap: 10,
  },
  rowWrap: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
  },
  helperText: {
    color: '#a9bbdf',
    fontSize: 13,
    lineHeight: 19,
  },
  screenPreview: {
    width: '100%',
    aspectRatio: 16 / 10,
    borderRadius: 14,
    backgroundColor: '#0f1730',
  },
  betaBlock: {
    gap: 8,
  },
  logLine: {
    color: '#d8e5fb',
    fontSize: 12,
    lineHeight: 18,
  },
  composerShell: {
    backgroundColor: '#10192e',
    borderRadius: 20,
    padding: 12,
    gap: 10,
    marginBottom: 8,
  },
  voiceRow: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
  },
  voiceStartButton: {
    backgroundColor: '#0f8f62',
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  voiceStopButton: {
    backgroundColor: '#b45309',
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  voiceCancelButton: {
    backgroundColor: '#6a2630',
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  voiceButtonText: {
    color: '#ffffff',
    fontWeight: '700',
    fontSize: 13,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 10,
  },
  input: {
    flex: 1,
    backgroundColor: '#141c33',
    color: '#ffffff',
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 12,
    minHeight: 50,
    maxHeight: 110,
  },
  sendButton: {
    backgroundColor: '#3b82f6',
    borderRadius: 16,
    paddingHorizontal: 18,
    paddingVertical: 14,
  },
  sendButtonText: {
    color: '#ffffff',
    fontWeight: '700',
  },
  primaryButton: {
    backgroundColor: '#3b82f6',
    borderRadius: 14,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  primaryButtonText: {
    color: '#ffffff',
    fontWeight: '700',
  },
  secondaryButton: {
    backgroundColor: '#223153',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  secondaryButtonText: {
    color: '#ffffff',
    fontWeight: '700',
    fontSize: 13,
  },
  activeSecondary: {
    backgroundColor: '#3b82f6',
  },
  liveButton: {
    backgroundColor: '#0f8f62',
  },
  disabledButton: {
    opacity: 0.55,
  },
});
