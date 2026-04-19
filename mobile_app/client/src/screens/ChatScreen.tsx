import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Image, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Audio } from 'expo-av';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import * as ImagePicker from 'expo-image-picker';
import { SafeAreaView } from 'react-native-safe-area-context';

import { buildWsBaseUrl, loadAppConfig } from '../../lib/appConfig';
import { requestJson } from '../../lib/appHttp';
import { describeError, logDiagnostic } from '../../lib/diagnostics';
import { getUnreadCronCount } from '@/lib/cronInbox';
import { AppDrawer, type DrawerTab } from '@/components/AppDrawer';
import { CollapsibleSection } from '@/components/CollapsibleSection';
import {
  type AgentOverview,
  type SkillSummary,
  type SkillValidation,
  type SubAgentStatus,
  activateAgentSkill,
  appendAgentMemoryNote,
  clearAgentPendingFiles,
  configureAgent,
  controlAgentRun,
  createSession,
  fetchAgentOverview,
  fetchAgentConfig,
  fetchCronFeed,
  fetchJobs,
  fetchProfile,
  fetchAgentSkills,
  fetchSubAgents,
  fetchSessionDetail,
  fetchSessions,
  forgetLastAgentMessage,
  resetAgentContext,
  searchAgentMemory,
  spawnSubAgent,
  updateAgentConfig,
  validateAgentSkill,
  type ConfigEntry,
  type MemorySearchResult,
  type ScheduledJob,
  type SessionDetail,
  type SessionMessage,
  type SessionSummary,
} from '@/lib/appApi';
import { formatAbsoluteTime, formatRelativeTime } from '@/lib/time';

const VOICE_SEGMENT_MS = 850;
const SOCKET_RECONNECT_MS = 1600;
const OUTBOUND_MESSAGE_TTL_MS = 60_000;
const OUTBOUND_RETRY_MS = 2_000;
const QUICK_TURN_OPTIONS = [50, 100, 200, 500];
const HELP_COMMAND_GROUPS = [
  ['Basics', '/start /help /mode /task'],
  ['Run control', '/pause /stop /spawn /subagents'],
  ['Sessions and cron', '/session /schedule /jobs /job_remove'],
  ['Agent controls', '/model /models /variant /settings /workspace /headless /monitor /verbose /bridge /heartbeat'],
  ['Context and memory', '/history /context /files /forget /reset /memory /memory_update /config /analytics /security'],
  ['Setup', '/setup /restart'],
] as const;

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

type PendingOutboundMessage = {
  id: string;
  text: string;
  sessionId?: string;
  interruptPolicy: InterruptPolicy;
  expiresAt: number;
};

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

function formatConfigValue(value: unknown) {
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function formatRealtimeToolEntry(payload: Record<string, any> | undefined) {
  if (!payload) return '';
  if (typeof payload.formatted === 'string' && payload.formatted.trim()) {
    return payload.formatted.trim();
  }

  const toolName = String(payload.tool_name || 'tool');
  const durationMs = Number(payload.duration_ms || 0);
  let resultPreview = '';
  try {
    resultPreview = JSON.stringify(payload.tool_result ?? {});
  } catch {
    resultPreview = String(payload.tool_result ?? '');
  }
  if (resultPreview.length > 240) {
    resultPreview = `${resultPreview.slice(0, 237)}...`;
  }
  return `🔧 ${toolName} → ${resultPreview || 'ok'} (${Math.round(durationMs)}ms)`;
}

function formatLogLine(message: string, level?: string) {
  const normalized = message.trim();
  if (!normalized) return '';
  if (level === 'error') return `[error] ${normalized}`;
  if (level === 'warn') return `[warn] ${normalized}`;
  return normalized;
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
  const [cronUnreadCount, setCronUnreadCount] = useState(0);
  const [pairPromptOpen, setPairPromptOpen] = useState(false);
  const [workspacePanelOpen, setWorkspacePanelOpen] = useState(false);
  const [verboseMode, setVerboseMode] = useState(true);
  const [agentOverview, setAgentOverview] = useState<AgentOverview | null>(null);
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [skillValidation, setSkillValidation] = useState<SkillValidation | null>(null);
  const [memoryQuery, setMemoryQuery] = useState('');
  const [memoryNote, setMemoryNote] = useState('');
  const [memoryResults, setMemoryResults] = useState<MemorySearchResult[]>([]);
  const [configKey, setConfigKey] = useState('');
  const [configValue, setConfigValue] = useState('');
  const [configEntries, setConfigEntries] = useState<ConfigEntry[]>([]);
  const [workspaceDraft, setWorkspaceDraft] = useState('');
  const [heartbeatDraft, setHeartbeatDraft] = useState('1800');
  const [subAgentPrompt, setSubAgentPrompt] = useState('');
  const [subAgents, setSubAgents] = useState<SubAgentStatus | null>(null);

  const chatWsRef = useRef<WebSocket | null>(null);
  const voiceWsRef = useRef<WebSocket | null>(null);
  const screenWsRef = useRef<WebSocket | null>(null);
  const composerInputRef = useRef<TextInput | null>(null);
  const recordingRef = useRef<Audio.Recording | null>(null);
  const assistantSoundRef = useRef<Audio.Sound | null>(null);
  const assistantAudioPathRef = useRef<string | null>(null);
  const pendingMessagesRef = useRef<PendingOutboundMessage[]>([]);
  const outboundRetryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
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
      const [sessionsData, jobsData, cronFeed] = await Promise.all([
        fetchSessions(apiBaseUrl, token),
        fetchJobs(apiBaseUrl, token),
        fetchCronFeed(apiBaseUrl, token).catch(() => []),
      ]);
      setSessions(Array.isArray(sessionsData) ? sessionsData : []);
      setJobs(Array.isArray(jobsData) ? jobsData : []);
      setCronUnreadCount(await getUnreadCronCount(Array.isArray(cronFeed) ? cronFeed : []));
      const activeSummary = sessionsData.find((session) => session.id === sessionIdRef.current);
      if (activeSummary) {
        setSessionName(activeSummary.name);
      }
    } catch {
      // Sidebar data should not interrupt the active chat.
    }
  };

  const refreshAgentControls = async (targetSessionId?: string) => {
    if (!apiBaseUrl || !token) return;
    try {
      const [overview, skillsResult, subAgentResult] = await Promise.all([
        fetchAgentOverview(apiBaseUrl, token, {
          sessionId: targetSessionId,
        }),
        fetchAgentSkills(apiBaseUrl, token, targetSessionId).catch(() => ({ items: [] })),
        fetchSubAgents(apiBaseUrl, token, targetSessionId).catch(() => null),
      ]);
      setAgentOverview(overview);
      setVerboseMode(Boolean(overview.verbose_mode));
      setWorkspaceDraft(overview.workspace || '');
      setHeartbeatDraft(String(overview.heartbeat.interval_seconds || 1800));
      setConfigEntries(overview.config_preview || []);
      setSkills(Array.isArray(skillsResult.items) ? skillsResult.items : []);
      setSubAgents(subAgentResult);
    } catch {
      // Agent controls should not block chat rendering.
    }
  };

  const applyQuickAgentConfig = async (payload: Parameters<typeof configureAgent>[2]) => {
    if (!apiBaseUrl || !token) return;

    setStatus('updating agent controls');
    try {
      await configureAgent(
        apiBaseUrl,
        token,
        payload,
        sessionIdRef.current
      );
      await refreshAgentControls(sessionIdRef.current);
      await refreshSidebarData();
      setStatus('agent controls updated');
    } catch (error) {
      setStatus(describeError(error));
    }
  };

  const runWorkspaceAction = async (
    label: string,
    action: () => Promise<string | void>,
    options?: { refreshControls?: boolean; successStatus?: string }
  ) => {
    setStatus(label);
    try {
      const resultMessage = await action();
      if (options?.refreshControls !== false) {
        await refreshAgentControls(sessionIdRef.current);
      }
      setStatus(resultMessage || options?.successStatus || 'ready');
    } catch (error) {
      setStatus(describeError(error));
    }
  };

  const focusComposer = (draft?: string) => {
    if (typeof draft === 'string') {
      setInput(draft);
    }
    setWorkspacePanelOpen(false);
    setTimeout(() => {
      composerInputRef.current?.focus();
    }, 120);
  };

  const toggleSkill = async (skillName: string, active: boolean) => {
    if (!apiBaseUrl || !token) return;
    await runWorkspaceAction(active ? `activating ${skillName}` : `removing ${skillName}`, async () => {
      await activateAgentSkill(apiBaseUrl, token, { name: skillName, active }, sessionIdRef.current);
      const skillsResult = await fetchAgentSkills(apiBaseUrl, token, sessionIdRef.current);
      setSkills(skillsResult.items || []);
      if (!active && skillValidation?.name === skillName) {
        setSkillValidation(null);
      }
    }, { refreshControls: false });
  };

  const runSkillValidation = async (skillName: string) => {
    if (!apiBaseUrl || !token) return;
    await runWorkspaceAction(`validating ${skillName}`, async () => {
      const result = await validateAgentSkill(apiBaseUrl, token, skillName, sessionIdRef.current);
      setSkillValidation(result);
    }, { refreshControls: false });
  };

  const spawnBackgroundTask = async () => {
    if (!apiBaseUrl || !token) return;
    const prompt = subAgentPrompt.trim();
    if (!prompt) {
      setStatus('sub-agent prompt required');
      return;
    }

    await runWorkspaceAction('spawning sub-agent', async () => {
      await spawnSubAgent(apiBaseUrl, token, { prompt, headless: true, max_turns: 30 }, sessionIdRef.current);
      setSubAgentPrompt('');
      const result = await fetchSubAgents(apiBaseUrl, token, sessionIdRef.current);
      setSubAgents(result);
    }, { refreshControls: false });
  };

  const runTaskControl = async (action: 'pause' | 'stop' | 'restart') => {
    if (!apiBaseUrl || !token) return;
    await runWorkspaceAction(`${action} requested`, async () => {
      const response = await controlAgentRun(apiBaseUrl, token, action, sessionIdRef.current);
      if (response?.message) {
        appendLog(`[control] ${response.message}`);
        logDiagnostic('chat.control', `${action} acknowledged`, response);
      }
      if (action !== 'restart') {
        await refreshAgentControls(sessionIdRef.current);
      }
      return response?.message || `${action} requested`;
    });
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
      void refreshAgentControls(detail.id);
    } catch (error) {
      setStatus(describeError(error));
    }
  };

  const createConversation = async () => {
    if (!apiBaseUrl || !token) {
      setStatus(apiBaseUrl ? 'pair this phone first' : 'add backend first');
      setPairPromptOpen(true);
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
      void refreshAgentControls(data.session.id);
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
          void refreshAgentControls(detail.id);
        } else {
          setSessionId(undefined);
          setSessionName('New chat');
          setMessages([]);
          setStatus('ready');
          void refreshAgentControls();
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
    if (!configLoaded || !apiBaseUrl || !token) return;

    const intervalId = setInterval(() => {
      void refreshSidebarData();
    }, 10_000);

    return () => clearInterval(intervalId);
  }, [apiBaseUrl, configLoaded, token]);

  useEffect(() => {
    if (!configLoaded || !apiBaseUrl) return;

    let active = true;
    requestJson<{
      steering_beta_enabled?: boolean;
      startup_error?: string | null;
      dependency_status?: { issues?: string[] };
      last_runtime_error?: string | null;
    }>({
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
        if (data?.startup_error) {
          appendLog(`[backend] ${data.startup_error}`);
          appendSystemMessage(data.startup_error, 'Backend');
          setStatus('backend startup issue');
        } else if (Array.isArray(data?.dependency_status?.issues) && data.dependency_status.issues.length) {
          const summary = data.dependency_status.issues.join('\n');
          appendLog(`[backend] dependency warning: ${summary}`);
          appendSystemMessage(summary, 'Dependency warning');
        } else if (data?.last_runtime_error) {
          appendLog(`[backend] last runtime error: ${data.last_runtime_error}`);
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

  const appendSystemMessage = (text: string, displayLabel = 'System') => {
    if (!text) return;
    setMessages((prev) => [
      ...prev,
      {
        role: 'system',
        content: text,
        displayLabel,
        timestamp: new Date().toISOString(),
      },
    ]);
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

  const canSendOverChatSocket = () =>
    Boolean(chatWsRef.current && chatWsRef.current.readyState === WebSocket.OPEN);

  const schedulePendingFlush = () => {
    if (outboundRetryRef.current) {
      clearTimeout(outboundRetryRef.current);
    }
    outboundRetryRef.current = setTimeout(() => {
      void flushPendingMessages();
    }, OUTBOUND_RETRY_MS);
  };

  const expirePendingMessages = () => {
    const now = Date.now();
    const expired = pendingMessagesRef.current.filter((item) => item.expiresAt <= now);
    if (!expired.length) {
      return;
    }

    pendingMessagesRef.current = pendingMessagesRef.current.filter((item) => item.expiresAt > now);
    for (const item of expired) {
      appendSystemMessage(
        `A queued message expired before the backend became ready:\n\n${item.text}`,
        'Delivery failed'
      );
      appendLog(`[queue] expired unsent message after 60s: ${item.text.slice(0, 120)}`);
    }
    setStatus('queued message expired');
  };

  const flushPendingMessages = async () => {
    if (outboundRetryRef.current) {
      clearTimeout(outboundRetryRef.current);
      outboundRetryRef.current = null;
    }
    expirePendingMessages();
    if (!pendingMessagesRef.current.length) {
      return;
    }

    if (!canSendOverChatSocket()) {
      setStatus('waiting for backend startup');
      schedulePendingFlush();
      return;
    }

    while (pendingMessagesRef.current.length && canSendOverChatSocket()) {
      const next = pendingMessagesRef.current.shift();
      const ws = chatWsRef.current;
      if (!next) break;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        pendingMessagesRef.current.unshift(next);
        break;
      }

      logDiagnostic('chat.queue', 'flushing queued chat message', {
        sessionId: next.sessionId || null,
        interruptPolicy: next.interruptPolicy,
        textPreview: next.text.slice(0, 140),
      });
      ws.send(JSON.stringify({
        text: next.text,
        session_id: next.sessionId,
        interrupt_policy: next.interruptPolicy,
      }));
    }

    if (pendingMessagesRef.current.length) {
      setStatus('waiting for backend startup');
      schedulePendingFlush();
      return;
    }

    appendLog('[queue] queued messages delivered');
    setStatus('connected');
  };

  const queuePendingMessage = (text: string) => {
    const pending: PendingOutboundMessage = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      text,
      sessionId: sessionIdRef.current,
      interruptPolicy,
      expiresAt: Date.now() + OUTBOUND_MESSAGE_TTL_MS,
    };

    pendingMessagesRef.current.push(pending);
    appendUserMessage(text);
    appendLog('[queue] message queued for backend startup (up to 60s)');
    appendSystemMessage(
      'Your message was queued because the backend is still starting or reconnecting. It will be delivered automatically for up to 1 minute.',
      'Queued'
    );
    setInput('');
    setVoiceDraft('');
    setStatus('waiting for backend startup');
    schedulePendingFlush();
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
    if (outboundRetryRef.current) {
      clearTimeout(outboundRetryRef.current);
      outboundRetryRef.current = null;
    }
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

    if (data.type === 'thinking') {
      const formatted = String(data.payload?.formatted || data.payload?.text || '').trim();
      const raw = String(data.payload?.text || '').trim();
      if (formatted) {
        appendSystemMessage(formatted, 'Thinking');
      }
      if (raw) {
        appendLog(`[thinking] ${raw}`);
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
      const entry = formatRealtimeToolEntry(data.payload);
      appendLog(entry);
      logDiagnostic(
        `${channel}.tool`,
        'tool event',
        data.payload,
        data.payload?.level === 'error' ? 'error' : 'info'
      );
      return;
    }

    if (data.type === 'warning') {
      const message = String(data.payload?.message || data.message || 'warning');
      const detail = String(data.payload?.detail || '').trim();
      if (channel === 'screen') {
        setScreenStatus(message);
        setScreenLiveState('warning');
        appendLog(`[screen] ${message}`);
        if (detail) appendLog(`[screen] ${detail}`);
      } else {
        setStatus(message);
        if (channel === 'voice') {
          setIsVoiceBusy(false);
        }
        appendLog(`[warn] ${message}`);
        if (detail) appendLog(detail);
      }
      logDiagnostic(`${channel}.runtime`, 'warning event', data.payload || data, 'warn');
      return;
    }

    if (data.type === 'error') {
      const message = String(data.payload?.message || data.message || 'error');
      const detail = String(data.payload?.detail || '').trim();
      if (channel === 'screen') {
        setScreenStatus(message);
        setScreenLiveState('error');
        appendLog(`[screen] ${message}`);
        if (detail) appendLog(`[screen] ${detail}`);
      } else {
        setStatus(message);
        if (channel === 'voice') {
          setVoiceState('error');
          setIsVoiceBusy(false);
        }
        appendLog(`[error] ${message}`);
        if (detail) appendLog(detail);
        appendSystemMessage(detail ? `${message}\n\n${detail}` : message, 'Error');
      }
      logDiagnostic(`${channel}.runtime`, 'error event', data.payload || data, 'error');
      return;
    }

    if (data.type === 'status' || data.type === 'log') {
      const message = String(data.payload?.message || data.message || '');
      const level = typeof data.payload?.level === 'string' ? data.payload.level : undefined;
      if (message) appendLog(formatLogLine(message, level));
      if (data.type === 'status') {
        if (channel === 'screen') {
          setScreenStatus(message || screenStatus);
        } else {
          setStatus(message || status);
        }
      }
      if (message) {
        logDiagnostic(
          `${channel}.runtime`,
          `${data.type} event`,
          data.payload || data,
          level === 'error' ? 'error' : level === 'warn' ? 'warn' : 'info'
        );
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
    if (!configLoaded || !apiBaseUrl || !token) {
      setStatus(apiBaseUrl ? 'pair this phone first' : 'add backend first');
      setPairPromptOpen(true);
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
        if (pendingMessagesRef.current.length) {
          setStatus('connected · sending queued message');
          void flushPendingMessages();
        } else {
          setStatus('connected');
        }
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
        if (pendingMessagesRef.current.length) {
          schedulePendingFlush();
        }
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
    if (setupMissing) {
      setStatus(apiBaseUrl ? 'pair this phone first' : 'add backend first');
      setPairPromptOpen(true);
      return;
    }
    const trimmed = input.trim();
    if (!trimmed) return;
    if (!canSendOverChatSocket()) {
      queuePendingMessage(trimmed);
      return;
    }
    const ws = chatWsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      queuePendingMessage(trimmed);
      return;
    }
    appendUserMessage(trimmed);
    logDiagnostic('chat.ws', 'sending chat message', {
      sessionId: sessionIdRef.current || null,
      interruptPolicy,
      textPreview: trimmed.slice(0, 140),
    });
    ws.send(JSON.stringify({
      text: trimmed,
      session_id: sessionIdRef.current,
      interrupt_policy: interruptPolicy,
    }));
    setInput('');
    setVoiceDraft('');
  };

  const toggleVerboseMode = async () => {
    if (!apiBaseUrl || !token) return;

    const nextValue = !verboseMode;
    setStatus(nextValue ? 'enabling verbose feed' : 'disabling verbose feed');
    try {
      await configureAgent(
        apiBaseUrl,
        token,
        { verbose_mode: nextValue },
        sessionIdRef.current
      );
      setVerboseMode(nextValue);
      setStatus(nextValue ? 'verbose feed enabled' : 'verbose feed disabled');
      appendLog(nextValue ? 'Verbose run feed enabled.' : 'Verbose run feed disabled.');
    } catch (error) {
      setStatus(describeError(error));
    }
  };

  const sessionUpdatedAt = sessions.find((item) => item.id === sessionId)?.updated_at;
  const subtitle = setupMissing
    ? (apiBaseUrl ? 'Tap the message field to finish pairing' : 'Tap the message field to connect this phone')
    : (sessionId ? `Updated ${formatRelativeTime(sessionUpdatedAt)}` : 'Ready to chat');
  const pairingPromptTitle = apiBaseUrl ? 'Finish pairing this phone' : 'Connect this phone';
  const pairingPromptText = apiBaseUrl
    ? 'This phone already knows the backend URL, but it still needs a trusted-device token before chat opens up.'
    : 'Add the backend URL first, then complete trusted-device pairing. After that, chat stays as the main workspace.';
  const workspaceStatus = [
    { label: 'Connection', value: status },
    { label: 'Voice', value: voiceState },
    { label: 'Session', value: sessionId ? sessionName : 'No session yet' },
  ];

  return (
    <SafeAreaView edges={['top', 'left', 'right']} style={styles.container}>
      <AppDrawer
        visible={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        initialTab={drawerTab}
        sessions={sessions}
        jobs={jobs}
        cronUnreadCount={cronUnreadCount}
        activeSessionId={sessionId}
        backendLabel={apiBaseUrl || 'Backend not configured'}
        onSelectSession={(nextSessionId) => {
          void selectSession(nextSessionId, { updateRoute: false });
        }}
        onCreateSession={() => {
          void createConversation();
        }}
      />

      <Modal transparent visible={pairPromptOpen} animationType="fade" onRequestClose={() => setPairPromptOpen(false)}>
        <View style={styles.modalOverlay}>
          <Pressable style={styles.modalBackdrop} onPress={() => setPairPromptOpen(false)} />
          <View style={styles.promptCard}>
            <Text style={styles.promptTitle}>{pairingPromptTitle}</Text>
            <Text style={styles.promptText}>{pairingPromptText}</Text>
            <View style={styles.promptActions}>
              <Pressable
                style={styles.primaryButton}
                onPress={() => {
                  setPairPromptOpen(false);
                  router.push('/pair');
                }}
              >
                <Text style={styles.primaryButtonText}>Open Pair</Text>
              </Pressable>
              <Pressable
                style={styles.secondaryButton}
                onPress={() => {
                  setPairPromptOpen(false);
                  router.push('/settings');
                }}
              >
                <Text style={styles.secondaryButtonText}>Settings</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>

      <Modal transparent visible={workspacePanelOpen} animationType="slide" onRequestClose={() => setWorkspacePanelOpen(false)}>
        <View style={styles.sheetOverlay}>
          <Pressable style={styles.sheetBackdrop} onPress={() => setWorkspacePanelOpen(false)} />
          <SafeAreaView edges={['bottom']} style={styles.sheet}>
            <View style={styles.sheetHandle} />
            <View style={styles.sheetHeader}>
              <View style={styles.sheetHeading}>
                <Text style={styles.sheetTitle}>Workspace</Text>
                <Text style={styles.sheetSubtitle}>Every Telegram command now maps here as a chat-side control, panel, or shortcut</Text>
              </View>
              <Pressable onPress={() => setWorkspacePanelOpen(false)}>
                <Text style={styles.sheetClose}>Done</Text>
              </Pressable>
            </View>

            <ScrollView contentContainerStyle={styles.sheetContent}>
              <View style={styles.rowWrap}>
                <Pressable
                  style={styles.secondaryButton}
                  onPress={() => {
                    setWorkspacePanelOpen(false);
                    void createConversation();
                  }}
                >
                  <Text style={styles.secondaryButtonText}>New chat</Text>
                </Pressable>
                <Pressable
                  style={styles.secondaryButton}
                  onPress={() => {
                    setWorkspacePanelOpen(false);
                    setDrawerTab('chats');
                    setDrawerOpen(true);
                  }}
                >
                  <Text style={styles.secondaryButtonText}>Sessions (/session)</Text>
                </Pressable>
                <Pressable
                  style={styles.secondaryButton}
                  onPress={() => {
                    void refreshSidebarData();
                    setWorkspacePanelOpen(false);
                  }}
                >
                  <Text style={styles.secondaryButtonText}>Refresh lists</Text>
                </Pressable>
                <Pressable
                  style={styles.secondaryButton}
                  onPress={() => {
                    setWorkspacePanelOpen(false);
                    setDrawerTab('cron');
                    setDrawerOpen(true);
                  }}
                >
                  <Text style={styles.secondaryButtonText}>
                    {cronUnreadCount > 0 ? `Cron (${cronUnreadCount})` : 'Cron (/schedule /jobs)'}
                  </Text>
                </Pressable>
                <Pressable
                  style={[styles.secondaryButton, verboseMode ? styles.activeSecondary : null]}
                  onPress={() => void toggleVerboseMode()}
                >
                  <Text style={styles.secondaryButtonText}>{verboseMode ? 'Verbose on' : 'Verbose off'}</Text>
                </Pressable>
              </View>

              <CollapsibleSection
                title="Setup and help"
                meta="/start /help /mode /setup /restart"
                defaultExpanded={false}
              >
                <View style={styles.infoCard}>
                  <Text style={styles.infoCardLabel}>/start</Text>
                  <Text style={styles.infoCardText}>
                    EmploAI mobile channel connected. Current model: {agentOverview?.current_model || 'Unknown'} · variant: {agentOverview?.current_variant || 'Unknown'} · max turns: {agentOverview?.max_turns || '-'}
                  </Text>
                </View>
                <View style={styles.infoCard}>
                  <Text style={styles.infoCardLabel}>/mode</Text>
                  <Text style={styles.infoCardText}>Auto mode is always on. The app uses the unified agent directly.</Text>
                </View>
                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>/help command map</Text>
                  {HELP_COMMAND_GROUPS.map(([label, commands]) => (
                    <View key={label} style={styles.infoCard}>
                      <Text style={styles.infoCardLabel}>{label}</Text>
                      <Text style={styles.infoCardText}>{commands}</Text>
                    </View>
                  ))}
                </View>
                <View style={styles.rowWrap}>
                  <Pressable
                    style={styles.secondaryButton}
                    onPress={() => {
                      setWorkspacePanelOpen(false);
                      router.push(setupMissing ? '/pair' : '/settings');
                    }}
                  >
                    <Text style={styles.secondaryButtonText}>{setupMissing ? 'Open setup' : 'Open settings'}</Text>
                  </Pressable>
                  <Pressable
                    style={styles.secondaryButton}
                    onPress={() => void runTaskControl('restart')}
                  >
                    <Text style={styles.secondaryButtonText}>Restart backend</Text>
                  </Pressable>
                </View>
              </CollapsibleSection>

              <CollapsibleSection
                title="Task controls"
                meta="/task /pause /stop /spawn /subagents"
                defaultExpanded={false}
              >
                <Text style={styles.helperText}>
                  `/task` maps to the normal composer. Use a new message to steer the current run instead of relying on the removed legacy `/continue` path.
                </Text>
                <View style={styles.rowWrap}>
                  <Pressable style={styles.secondaryButton} onPress={() => focusComposer()}>
                    <Text style={styles.secondaryButtonText}>Open composer</Text>
                  </Pressable>
                  <Pressable style={styles.secondaryButton} onPress={() => void runTaskControl('pause')}>
                    <Text style={styles.secondaryButtonText}>Pause run</Text>
                  </Pressable>
                  <Pressable style={styles.secondaryButton} onPress={() => void runTaskControl('stop')}>
                    <Text style={styles.secondaryButtonText}>Stop run</Text>
                  </Pressable>
                </View>

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Spawn sub-agent</Text>
                  <TextInput
                    style={styles.textAreaInput}
                    value={subAgentPrompt}
                    onChangeText={setSubAgentPrompt}
                    placeholder="Describe the background task for /spawn"
                    placeholderTextColor="#7f8aa3"
                    multiline
                  />
                  <View style={styles.rowWrap}>
                    <Pressable style={styles.secondaryButton} onPress={() => void spawnBackgroundTask()}>
                      <Text style={styles.secondaryButtonText}>Spawn</Text>
                    </Pressable>
                    <Pressable
                      style={styles.secondaryButton}
                      onPress={() =>
                        void runWorkspaceAction(
                          'refreshing sub-agents',
                          async () => {
                            const result = await fetchSubAgents(apiBaseUrl, token, sessionIdRef.current);
                            setSubAgents(result);
                          },
                          { refreshControls: false }
                        )
                      }
                    >
                      <Text style={styles.secondaryButtonText}>Refresh list</Text>
                    </Pressable>
                  </View>
                </View>

                <View style={styles.infoCard}>
                  <Text style={styles.infoCardText}>
                    Sub-agents: {subAgents?.total_tasks || 0} total · {subAgents?.running || 0} running · {subAgents?.completed || 0} completed · {subAgents?.failed || 0} failed
                  </Text>
                </View>
                {(subAgents?.tasks || []).length ? (
                  subAgents!.tasks.map((task) => (
                    <View key={task.id} style={styles.infoCard}>
                      <Text style={styles.infoCardLabel}>{task.id} · {task.status}</Text>
                      <Text style={styles.infoCardText}>{task.prompt}</Text>
                      <Text style={styles.infoCardText}>
                        {task.completed_at
                          ? `Completed ${formatRelativeTime(task.completed_at)}`
                          : task.created_at
                            ? `Created ${formatRelativeTime(task.created_at)}`
                            : 'Waiting for timestamps'}
                      </Text>
                    </View>
                  ))
                ) : (
                  <Text style={styles.helperText}>No sub-agents yet.</Text>
                )}
              </CollapsibleSection>

              <CollapsibleSection
                title="Skills"
                meta="/skills /skill /skilltest"
                defaultExpanded={false}
              >
                <Text style={styles.helperText}>Activate one skill for the next messages or validate it from the phone without using Telegram.</Text>
                <View style={styles.rowWrap}>
                  <Pressable
                    style={styles.secondaryButton}
                    onPress={() =>
                      void runWorkspaceAction(
                        'refreshing skills',
                        async () => {
                          const result = await fetchAgentSkills(apiBaseUrl, token, sessionIdRef.current);
                          setSkills(result.items || []);
                        },
                        { refreshControls: false }
                      )
                    }
                  >
                    <Text style={styles.secondaryButtonText}>Refresh skills</Text>
                  </Pressable>
                </View>
                {skills.length ? (
                  skills.map((skill) => (
                    <View key={skill.name} style={styles.infoCard}>
                      <Text style={styles.infoCardLabel}>
                        {skill.name}
                        {skill.active ? ' · active' : ''}
                        {!skill.available ? ' · gated' : ''}
                      </Text>
                      <Text style={styles.infoCardText}>
                        {skill.description}
                        {skill.unavailable_reason ? `\n${skill.unavailable_reason}` : ''}
                      </Text>
                      <View style={styles.rowWrap}>
                        <Pressable
                          style={[styles.secondaryButton, skill.active ? styles.activeSecondary : null, !skill.available ? styles.disabledButton : null]}
                          disabled={!skill.available}
                          onPress={() => void toggleSkill(skill.name, !skill.active)}
                        >
                          <Text style={styles.secondaryButtonText}>{skill.active ? 'Deactivate' : 'Activate'}</Text>
                        </Pressable>
                        <Pressable
                          style={styles.secondaryButton}
                          onPress={() => void runSkillValidation(skill.name)}
                        >
                          <Text style={styles.secondaryButtonText}>Validate</Text>
                        </Pressable>
                      </View>
                    </View>
                  ))
                ) : (
                  <Text style={styles.helperText}>No skills available.</Text>
                )}
                {skillValidation ? (
                  <View style={styles.infoCard}>
                    <Text style={styles.infoCardLabel}>{skillValidation.name} · {skillValidation.valid ? 'valid' : 'invalid'}</Text>
                    <Text style={styles.infoCardText}>
                      Scripts: {skillValidation.scripts_count} · References: {skillValidation.references_count} · Assets: {skillValidation.assets_count}
                    </Text>
                    {skillValidation.errors.map((item) => (
                      <Text key={`error-${item}`} style={styles.infoCardText}>Error: {item}</Text>
                    ))}
                    {skillValidation.warnings.map((item) => (
                      <Text key={`warning-${item}`} style={styles.infoCardText}>Warning: {item}</Text>
                    ))}
                  </View>
                ) : null}
              </CollapsibleSection>

              <CollapsibleSection title="Status" meta="Moved off the main chat to keep the screen clean" defaultExpanded={false}>
                {workspaceStatus.map((item) => (
                  <View key={item.label} style={styles.statusRowCompact}>
                    <Text style={styles.statusRowLabel}>{item.label}</Text>
                    <Text style={styles.statusRowValue}>{item.value}</Text>
                  </View>
                ))}
              </CollapsibleSection>

              <CollapsibleSection
                title="Quick controls"
                meta={
                  agentOverview
                    ? `/model /models /variant /settings /verbose · ${agentOverview.current_model} · ${agentOverview.current_variant} · ${agentOverview.max_turns} turns`
                    : '/model /models /variant /settings /verbose'
                }
                defaultExpanded={false}
              >
                <Text style={styles.helperText}>Fast equivalents for the Telegram model and settings commands. Use Agent Controls for deeper inspection if needed.</Text>

                {agentOverview?.model_groups.map((group) => (
                  <View key={group.provider} style={styles.quickControlBlock}>
                    <Text style={styles.quickControlLabel}>{group.provider.toUpperCase()}</Text>
                    <View style={styles.rowWrap}>
                      {group.models.map((model) => (
                        <Pressable
                          key={model}
                          style={[styles.secondaryButton, model === agentOverview.current_model ? styles.activeSecondary : null]}
                          onPress={() => void applyQuickAgentConfig({ model })}
                        >
                          <Text style={styles.secondaryButtonText}>{model}</Text>
                        </Pressable>
                      ))}
                    </View>
                  </View>
                ))}

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Variant</Text>
                  <View style={styles.rowWrap}>
                    {(agentOverview?.available_variants || []).map((variant) => (
                      <Pressable
                        key={variant}
                        style={[styles.secondaryButton, variant === agentOverview?.current_variant ? styles.activeSecondary : null]}
                        onPress={() => void applyQuickAgentConfig({ variant })}
                      >
                        <Text style={styles.secondaryButtonText}>{variant}</Text>
                      </Pressable>
                    ))}
                  </View>
                </View>

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Max turns</Text>
                  <View style={styles.rowWrap}>
                    {QUICK_TURN_OPTIONS.map((turns) => (
                      <Pressable
                        key={turns}
                        style={[styles.secondaryButton, turns === agentOverview?.max_turns ? styles.activeSecondary : null]}
                        onPress={() => void applyQuickAgentConfig({ max_turns: turns })}
                      >
                        <Text style={styles.secondaryButtonText}>{turns}</Text>
                      </Pressable>
                    ))}
                  </View>
                </View>

                <View style={styles.rowWrap}>
                  <Pressable
                    style={[styles.secondaryButton, verboseMode ? styles.activeSecondary : null]}
                    onPress={() => void toggleVerboseMode()}
                  >
                    <Text style={styles.secondaryButtonText}>{verboseMode ? 'Verbose on' : 'Verbose off'}</Text>
                  </Pressable>
                  <Pressable
                    style={styles.secondaryButton}
                    onPress={() => {
                      setWorkspacePanelOpen(false);
                      router.push('/agent');
                    }}
                  >
                    <Text style={styles.secondaryButtonText}>More controls</Text>
                  </Pressable>
                </View>
              </CollapsibleSection>

              <CollapsibleSection
                title="Runtime controls"
                meta={
                  agentOverview
                    ? `/monitor /workspace /headless /heartbeat /bridge · ${agentOverview.bridge_enabled ? 'Real Chrome' : 'Selenium'} · ${agentOverview.headless_mode} · heartbeat ${agentOverview.heartbeat.enabled ? 'on' : 'off'}`
                    : '/monitor /workspace /headless /heartbeat /bridge'
                }
                defaultExpanded={false}
              >
                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Monitor</Text>
                  <View style={styles.rowWrap}>
                    <Pressable
                      style={[styles.secondaryButton, agentOverview?.auto_reply_enabled ? styles.activeSecondary : null]}
                      onPress={() => void applyQuickAgentConfig({ auto_reply_enabled: true })}
                    >
                      <Text style={styles.secondaryButtonText}>Monitor on</Text>
                    </Pressable>
                    <Pressable
                      style={[styles.secondaryButton, agentOverview && !agentOverview.auto_reply_enabled ? styles.activeSecondary : null]}
                      onPress={() => void applyQuickAgentConfig({ auto_reply_enabled: false })}
                    >
                      <Text style={styles.secondaryButtonText}>Monitor off</Text>
                    </Pressable>
                  </View>
                </View>

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Browser bridge</Text>
                  <View style={styles.rowWrap}>
                    <Pressable
                      style={[styles.secondaryButton, agentOverview?.bridge_enabled ? styles.activeSecondary : null]}
                      onPress={() => void applyQuickAgentConfig({ bridge_enabled: true })}
                    >
                      <Text style={styles.secondaryButtonText}>Real Chrome</Text>
                    </Pressable>
                    <Pressable
                      style={[styles.secondaryButton, agentOverview && !agentOverview.bridge_enabled ? styles.activeSecondary : null]}
                      onPress={() => void applyQuickAgentConfig({ bridge_enabled: false })}
                    >
                      <Text style={styles.secondaryButtonText}>Selenium</Text>
                    </Pressable>
                  </View>
                </View>

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Browser mode</Text>
                  <View style={styles.rowWrap}>
                    <Pressable
                      style={[styles.secondaryButton, agentOverview?.headless_mode === 'headless' ? styles.activeSecondary : null]}
                      onPress={() => void applyQuickAgentConfig({ headless_mode: 'headless' })}
                    >
                      <Text style={styles.secondaryButtonText}>Headless</Text>
                    </Pressable>
                    <Pressable
                      style={[styles.secondaryButton, agentOverview?.headless_mode === 'headed' ? styles.activeSecondary : null]}
                      onPress={() => void applyQuickAgentConfig({ headless_mode: 'headed' })}
                    >
                      <Text style={styles.secondaryButtonText}>Headed</Text>
                    </Pressable>
                  </View>
                </View>

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Heartbeat</Text>
                  <View style={styles.rowWrap}>
                    <Pressable
                      style={[styles.secondaryButton, agentOverview?.heartbeat.enabled ? styles.activeSecondary : null]}
                      onPress={() => void applyQuickAgentConfig({ heartbeat_enabled: true })}
                    >
                      <Text style={styles.secondaryButtonText}>Heartbeat on</Text>
                    </Pressable>
                    <Pressable
                      style={[styles.secondaryButton, agentOverview && !agentOverview.heartbeat.enabled ? styles.activeSecondary : null]}
                      onPress={() => void applyQuickAgentConfig({ heartbeat_enabled: false })}
                    >
                      <Text style={styles.secondaryButtonText}>Heartbeat off</Text>
                    </Pressable>
                  </View>
                  <View style={styles.rowWrap}>
                    <TextInput
                      style={styles.workspaceInputCompact}
                      value={heartbeatDraft}
                      onChangeText={setHeartbeatDraft}
                      placeholder="1800"
                      placeholderTextColor="#7f8aa3"
                      keyboardType="number-pad"
                    />
                    <Pressable
                      style={styles.secondaryButton}
                      onPress={() => void applyQuickAgentConfig({ heartbeat_interval_seconds: Number(heartbeatDraft) || 1800 })}
                    >
                      <Text style={styles.secondaryButtonText}>Set interval</Text>
                    </Pressable>
                  </View>
                  <Text style={styles.helperText}>
                    {agentOverview?.heartbeat.last_heartbeat
                      ? `Last heartbeat ${formatRelativeTime(agentOverview.heartbeat.last_heartbeat)}`
                      : 'No heartbeat recorded yet.'}
                  </Text>
                </View>

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Workspace</Text>
                  <View style={styles.rowWrap}>
                    <TextInput
                      style={styles.workspaceInput}
                      value={workspaceDraft}
                      onChangeText={setWorkspaceDraft}
                      placeholder="Workspace path"
                      placeholderTextColor="#7f8aa3"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                    <Pressable
                      style={styles.secondaryButton}
                      onPress={() => void applyQuickAgentConfig({ workspace: workspaceDraft })}
                    >
                      <Text style={styles.secondaryButtonText}>Apply</Text>
                    </Pressable>
                  </View>
                </View>
              </CollapsibleSection>

              <CollapsibleSection
                title="Context and files"
                meta={
                  agentOverview
                    ? `/history /context /files /forget /reset · ${agentOverview.context_usage.message_count} messages · ${agentOverview.pending_files.length} pending files`
                    : '/history /context /files /forget /reset'
                }
                defaultExpanded={false}
              >
                <View style={styles.infoCard}>
                  <Text style={styles.infoCardText}>
                    Context: {agentOverview?.context_usage.estimated_tokens || 0} / {agentOverview?.context_usage.max_tokens || 0} estimated tokens
                    {agentOverview ? ` (${agentOverview.context_usage.usage_percent}%)` : ''}
                  </Text>
                </View>

                {(agentOverview?.history || []).slice(0, 6).map((item, index) => (
                  <View key={`${item.timestamp || index}-${item.preview}`} style={styles.infoCard}>
                    <Text style={styles.infoCardLabel}>
                      {item.display_label || item.role}
                      {item.timestamp ? ` · ${formatRelativeTime(item.timestamp)}` : ''}
                    </Text>
                    <Text style={styles.infoCardText}>{item.preview}</Text>
                  </View>
                ))}

                {(agentOverview?.pending_files || []).slice(0, 6).map((item) => (
                  <View key={`${item.filename}-${item.uploaded_at || item.source_format || 'file'}`} style={styles.infoCard}>
                    <Text style={styles.infoCardLabel}>{item.filename}</Text>
                    <Text style={styles.infoCardText}>
                      {item.mime_type || 'unknown type'}
                      {item.size ? ` · ${item.size} bytes` : ''}
                      {item.uploaded_at ? ` · ${formatRelativeTime(item.uploaded_at)}` : ''}
                    </Text>
                  </View>
                ))}

                <View style={styles.rowWrap}>
                  <Pressable
                    style={styles.secondaryButton}
                    onPress={() =>
                      void runWorkspaceAction('clearing pending files', async () => {
                        await clearAgentPendingFiles(apiBaseUrl, token, sessionIdRef.current);
                      })
                    }
                  >
                    <Text style={styles.secondaryButtonText}>Clear files</Text>
                  </Pressable>
                  <Pressable
                    style={styles.secondaryButton}
                    onPress={() =>
                      void runWorkspaceAction('forgetting last message', async () => {
                        await forgetLastAgentMessage(apiBaseUrl, token, sessionIdRef.current);
                      })
                    }
                  >
                    <Text style={styles.secondaryButtonText}>Forget last</Text>
                  </Pressable>
                  <Pressable
                    style={styles.secondaryButton}
                    onPress={() =>
                      void runWorkspaceAction('resetting context', async () => {
                        await resetAgentContext(apiBaseUrl, token, sessionIdRef.current);
                      })
                    }
                  >
                    <Text style={styles.secondaryButtonText}>Reset context</Text>
                  </Pressable>
                </View>
              </CollapsibleSection>

              <CollapsibleSection
                title="Memory and config"
                meta="/memory /memory_update /config /analytics /security"
                defaultExpanded={false}
              >
                <View style={styles.infoCard}>
                  <Text style={styles.infoCardText}>
                    Memory file: {agentOverview?.memory_summary.memory_file_exists ? 'present' : 'missing'} · daily logs: {agentOverview?.memory_summary.daily_log_count || 0}
                  </Text>
                  <Text style={styles.infoCardText}>
                    Analytics: {agentOverview?.analytics.total_messages || 0} messages · {agentOverview?.analytics.total_commands || 0} commands · {agentOverview?.analytics.total_tokens || 0} tokens
                  </Text>
                  <Text style={styles.infoCardText}>
                    Security: {agentOverview?.security.allowed_users_count || 0} allowed users · {agentOverview?.security.max_requests_per_minute || 0}/min · {agentOverview?.security.security_events_24h || 0} events in 24h
                  </Text>
                </View>

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Search memory</Text>
                  <View style={styles.rowWrap}>
                    <TextInput
                      style={styles.workspaceInput}
                      value={memoryQuery}
                      onChangeText={setMemoryQuery}
                      placeholder="Search memory"
                      placeholderTextColor="#7f8aa3"
                    />
                    <Pressable
                      style={styles.secondaryButton}
                      onPress={() =>
                        void runWorkspaceAction(
                          'searching memory',
                          async () => {
                            const result = await searchAgentMemory(apiBaseUrl, token, memoryQuery, sessionIdRef.current);
                            setMemoryResults(result.results || []);
                          },
                          { refreshControls: false }
                        )
                      }
                    >
                      <Text style={styles.secondaryButtonText}>Search</Text>
                    </Pressable>
                  </View>
                  {memoryResults.map((result, index) => (
                    <View key={`${result.source}-${result.line || index}`} style={styles.infoCard}>
                      <Text style={styles.infoCardLabel}>
                        {result.source}
                        {result.line ? `:${result.line}` : ''}
                      </Text>
                      <Text style={styles.infoCardText}>{result.content}</Text>
                    </View>
                  ))}
                </View>

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Save memory note</Text>
                  <TextInput
                    style={styles.textAreaInput}
                    value={memoryNote}
                    onChangeText={setMemoryNote}
                    placeholder="Add a durable note or preference"
                    placeholderTextColor="#7f8aa3"
                    multiline
                  />
                  <Pressable
                    style={styles.secondaryButton}
                    onPress={() =>
                      void runWorkspaceAction('saving memory note', async () => {
                        await appendAgentMemoryNote(apiBaseUrl, token, memoryNote, sessionIdRef.current);
                        setMemoryNote('');
                      })
                    }
                  >
                    <Text style={styles.secondaryButtonText}>Save note</Text>
                  </Pressable>
                </View>

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Config</Text>
                  <View style={styles.rowWrap}>
                    <TextInput
                      style={styles.workspaceInputCompact}
                      value={configKey}
                      onChangeText={setConfigKey}
                      placeholder="config.key"
                      placeholderTextColor="#7f8aa3"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                    <TextInput
                      style={styles.workspaceInput}
                      value={configValue}
                      onChangeText={setConfigValue}
                      placeholder="value"
                      placeholderTextColor="#7f8aa3"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                  </View>
                  <View style={styles.rowWrap}>
                    <Pressable
                      style={styles.secondaryButton}
                      onPress={() =>
                        void runWorkspaceAction(
                          'loading config',
                          async () => {
                            const result = await fetchAgentConfig(apiBaseUrl, token, configKey || undefined, sessionIdRef.current);
                            setConfigEntries(result.items || []);
                          },
                          { refreshControls: false }
                        )
                      }
                    >
                      <Text style={styles.secondaryButtonText}>Load key</Text>
                    </Pressable>
                    <Pressable
                      style={styles.secondaryButton}
                      onPress={() =>
                        void runWorkspaceAction('saving config', async () => {
                          await updateAgentConfig(apiBaseUrl, token, { key: configKey, value: configValue }, sessionIdRef.current);
                          setConfigValue('');
                        })
                      }
                    >
                      <Text style={styles.secondaryButtonText}>Set value</Text>
                    </Pressable>
                  </View>
                  {(configEntries.length ? configEntries : agentOverview?.config_preview || []).slice(0, 10).map((entry) => (
                    <View key={entry.key} style={styles.infoCard}>
                      <Text style={styles.infoCardLabel}>{entry.key}</Text>
                      <Text style={styles.infoCardText}>{formatConfigValue(entry.value)}</Text>
                    </View>
                  ))}
                </View>
              </CollapsibleSection>

              <CollapsibleSection title="Remote view" meta={`${screenStatus} · ${screenLiveState}`} defaultExpanded={false}>
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

              <CollapsibleSection title="Composer tools" meta="Uploads and steering" defaultExpanded={false}>
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

              <CollapsibleSection
                title="Run feed"
                meta={`${verboseMode ? 'Verbose on' : 'Verbose off'} · ${toolLogs.length ? `${toolLogs.length} recent updates` : 'Quiet'}`}
                defaultExpanded={false}
              >
                {!verboseMode ? (
                  <Text style={styles.helperText}>Verbose feed is off. Turn it on to stream tool activity live.</Text>
                ) : toolLogs.length === 0 ? (
                  <Text style={styles.helperText}>No tool or status updates yet.</Text>
                ) : (
                  toolLogs.slice(0, 14).map((entry, index) => (
                    <Text key={`${entry}-${index}`} style={styles.logLine}>{entry}</Text>
                  ))
                )}
              </CollapsibleSection>
            </ScrollView>
          </SafeAreaView>
        </View>
      </Modal>

      <View style={styles.topBar}>
        <Pressable
          style={styles.topButton}
          onPress={() => {
            setDrawerTab('chats');
            setDrawerOpen(true);
          }}
        >
          <Text style={styles.topButtonText}>Sidebar</Text>
          {cronUnreadCount > 0 ? (
            <View style={styles.topButtonBadge}>
              <Text style={styles.topButtonBadgeText}>{cronUnreadCount > 9 ? '9+' : String(cronUnreadCount)}</Text>
            </View>
          ) : null}
        </Pressable>
        <View style={styles.titleBlock}>
          <Text style={styles.title}>{sessionName}</Text>
          <Text style={styles.subtitle}>{subtitle}</Text>
        </View>
        <Pressable style={styles.plusButton} onPress={() => setWorkspacePanelOpen(true)}>
          <Text style={styles.plusButtonText}>+</Text>
        </Pressable>
      </View>

      <ScrollView style={styles.messages} contentContainerStyle={styles.messagesContent}>
        {messages.length === 0 ? (
          <View style={styles.emptyState}>
            <Text style={styles.emptyHint}>
              {setupMissing ? 'Tap the message field to connect this phone.' : 'Your conversation will appear here.'}
            </Text>
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

      <View style={styles.composerShell}>
        <View style={styles.composerActionRow}>
          <Pressable style={styles.plusButtonSmall} onPress={() => setWorkspacePanelOpen(true)}>
            <Text style={styles.plusButtonSmallText}>+</Text>
          </Pressable>
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
        </View>

        <View style={styles.inputRow}>
          {setupMissing ? (
            <Pressable style={[styles.input, styles.lockedInput]} onPress={() => setPairPromptOpen(true)}>
              <Text style={styles.lockedInputText}>
                {apiBaseUrl ? 'Tap to finish pairing' : 'Tap to add backend and pair'}
              </Text>
            </Pressable>
          ) : (
            <TextInput
              ref={composerInputRef}
              style={styles.input}
              value={input}
              onChangeText={setInput}
              placeholder="Message EmploAI"
              placeholderTextColor="#7f8aa3"
              multiline
            />
          )}
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
    paddingTop: 8,
    gap: 12,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(5, 8, 18, 0.6)',
    justifyContent: 'center',
    paddingHorizontal: 22,
  },
  modalBackdrop: {
    ...StyleSheet.absoluteFillObject,
  },
  promptCard: {
    backgroundColor: '#111a31',
    borderRadius: 24,
    padding: 20,
    gap: 12,
  },
  promptTitle: {
    color: '#ffffff',
    fontSize: 20,
    fontWeight: '700',
  },
  promptText: {
    color: '#d7e3fb',
    fontSize: 15,
    lineHeight: 22,
  },
  promptActions: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
    paddingTop: 4,
  },
  sheetOverlay: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(5, 8, 18, 0.42)',
  },
  sheetBackdrop: {
    ...StyleSheet.absoluteFillObject,
  },
  sheet: {
    backgroundColor: '#0f1730',
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    paddingHorizontal: 16,
    paddingTop: 10,
    paddingBottom: 10,
    maxHeight: '82%',
    gap: 12,
  },
  sheetHandle: {
    alignSelf: 'center',
    width: 44,
    height: 5,
    borderRadius: 999,
    backgroundColor: '#41547f',
  },
  sheetHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
  },
  sheetHeading: {
    flex: 1,
    gap: 4,
  },
  sheetTitle: {
    color: '#ffffff',
    fontSize: 20,
    fontWeight: '700',
  },
  sheetSubtitle: {
    color: '#92a6cd',
    fontSize: 13,
    lineHeight: 19,
  },
  sheetClose: {
    color: '#7cc7ff',
    fontWeight: '700',
    fontSize: 14,
  },
  sheetContent: {
    gap: 12,
    paddingBottom: 10,
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
    position: 'relative',
  },
  topButtonText: {
    color: '#dce8ff',
    fontWeight: '700',
    fontSize: 13,
  },
  topButtonBadge: {
    position: 'absolute',
    top: -6,
    right: -6,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    paddingHorizontal: 5,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#f97316',
  },
  topButtonBadgeText: {
    color: '#ffffff',
    fontSize: 10,
    fontWeight: '800',
  },
  titleBlock: {
    flex: 1,
    gap: 4,
  },
  title: {
    color: '#ffffff',
    fontSize: 22,
    fontWeight: '700',
  },
  subtitle: {
    color: '#8fa2c8',
    fontSize: 13,
  },
  plusButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#182342',
    alignItems: 'center',
    justifyContent: 'center',
  },
  plusButtonText: {
    color: '#ffffff',
    fontWeight: '700',
    fontSize: 22,
  },
  messages: {
    flex: 1,
  },
  messagesContent: {
    gap: 12,
    paddingBottom: 12,
    flexGrow: 1,
  },
  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 30,
  },
  emptyHint: {
    color: '#6f82a8',
    fontSize: 15,
    textAlign: 'center',
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
  rowWrap: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
  },
  statusRowCompact: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 6,
  },
  statusRowLabel: {
    color: '#8fa2c8',
    fontSize: 13,
  },
  statusRowValue: {
    flex: 1,
    color: '#ffffff',
    fontSize: 13,
    fontWeight: '600',
    textAlign: 'right',
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
  quickControlBlock: {
    gap: 8,
  },
  quickControlLabel: {
    color: '#dce8ff',
    fontSize: 13,
    fontWeight: '700',
  },
  workspaceInput: {
    flex: 1,
    minWidth: 180,
    backgroundColor: '#0f1730',
    color: '#ffffff',
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  workspaceInputCompact: {
    minWidth: 110,
    backgroundColor: '#0f1730',
    color: '#ffffff',
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  textAreaInput: {
    minHeight: 92,
    backgroundColor: '#0f1730',
    color: '#ffffff',
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    textAlignVertical: 'top',
  },
  infoCard: {
    backgroundColor: '#101933',
    borderRadius: 14,
    padding: 12,
    gap: 4,
  },
  infoCardLabel: {
    color: '#dce8ff',
    fontSize: 12,
    fontWeight: '700',
  },
  infoCardText: {
    color: '#d8e5fb',
    fontSize: 12,
    lineHeight: 18,
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
  composerActionRow: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  plusButtonSmall: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: '#182342',
    alignItems: 'center',
    justifyContent: 'center',
  },
  plusButtonSmallText: {
    color: '#ffffff',
    fontSize: 20,
    fontWeight: '700',
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
  lockedInput: {
    justifyContent: 'center',
  },
  lockedInputText: {
    color: '#8ea2cb',
    fontSize: 15,
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
