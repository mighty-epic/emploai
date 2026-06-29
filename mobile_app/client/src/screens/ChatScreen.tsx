import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { TextInput } from 'react-native';

import { buildWsBaseUrl, loadAppConfig, type AppConfig, type AppConnectionMode } from '../../lib/appConfig';
import { reconcileRemoteAccountConfig } from '../../lib/accountSession';
import { requestJson } from '../../lib/appHttp';
import { describeError, logDiagnostic, shortStatusText, userFacingError } from '../../lib/diagnostics';
import { getUnreadCronCount } from '@/lib/cronInbox';
import { createApprovedConfirmation } from '@/lib/sharedConfirmations';
import { formatRelativeTime } from '@/lib/time';
import type { DrawerTab } from '@/components/AppDrawer';
import { useConfirmation } from '@/components/ConfirmationDialog';
import {
  mergeLiveMessage,
  mergeSessionMessagesWithLocalState,
  toChatMessage,
  type ChatMessage,
} from '@/screens/chatMessages';
import {
  formatLogLine,
  formatRealtimeToolEntry,
  formatTimelineLogEntry,
  isUserVisibleRuntimeMessage,
  isUserVisibleTimelineEvent,
  mergeTimelineEvents,
  mergeToolLogEntries,
  realtimeLogEventToTimelineEvent,
  realtimeToolEventToTimelineEvent,
  timelineEventsToLogLines,
  type ChatEvent,
} from '@/screens/chatTimeline';
import {
  type ArtifactDetail,
  type ArtifactSummary,
  type AgentOverview,
  type SkillSummary,
  type SkillValidation,
  type SubAgentStatus,
  activateSession,
  activateAgentSkill,
  appendAgentMemoryNote,
  clearAgentPendingFiles,
  configureAgent,
  controlAgentRun,
  createSession,
  deleteSession,
  fetchAgentOverview,
  fetchAgentConfig,
  fetchCronFeed,
  fetchFleetSnapshot,
  fetchJobs,
  fetchProfile,
  fetchAgentSkills,
  fetchSessionArtifactDetail,
  fetchSessionArtifacts,
  fetchSubAgents,
  fetchSessionDetail,
  fetchSidebarState,
  fetchSessions,
  fetchTelegramBotConfigs,
  forgetLastAgentMessage,
  resetAgentContext,
  searchAgentMemory,
  setFleetActiveIdentity,
  spawnSubAgent,
  updateAgentConfig,
  updateSessionSecurityPermissionMode,
  updateSessionToolPacks,
  validateAgentSkill,
  type ConfigEntry,
  type FleetIdentity,
  type FleetSnapshot,
  type MemorySearchResult,
  type ScheduledJob,
  type SessionDetail,
  type SessionMessage,
  type SessionSummary,
  type SessionTimelineEvent,
  type SidebarState,
  type TelegramBotConfig,
  updateSidebarState,
} from '@/lib/appApi';

import {
  CHAT_NO_ACTIVE_SESSION_STATUS,
  DEFAULT_TOOL_PACK_IDS,
  OUTBOUND_MESSAGE_TTL_MS,
  OUTBOUND_RETRY_MS,
  SOCKET_RECONNECT_MS,
  VOICE_SEGMENT_MS,
  createClientId,
  fleetSessionCreateFields,
  identityLabel,
  loadFileSystemModule,
  normalizeRouteSessionId,
  normalizeRouteWorkspace,
  normalizeWorkspacePath,
  sessionBelongsToFleetIdentity,
  type InterruptPolicy,
  type PendingOutboundMessage,
  type ScreenPreview,
} from './ChatScreen.helpers';
import { uploadChatAttachment, type ChatAttachmentKind } from './ChatScreenAttachments';
import { ChatScreenView } from './ChatScreenView';
import { handleChatRealtimeEvent } from './ChatScreenRealtime';

function appConfigSyncKey(config: AppConfig) {
  const tokenTail = (config.accountToken || config.accessToken || '').slice(-16);
  if (config.connectionMode === 'remote_cloud') {
    const accountKey = config.accountUserId || config.accountEmail || config.accountMobileId || tokenTail || 'signed-out';
    return ['remote', accountKey, config.accountMobileId || 'mobile', config.pairedDesktopId || 'unpaired'].join(':');
  }
  return [config.connectionMode, config.apiBaseUrl, tokenTail || 'no-token'].join(':');
}

export default function ChatScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ sessionId?: string | string[]; newSession?: string | string[]; workspace?: string | string[] }>();
  const requestedSessionId = normalizeRouteSessionId(params.sessionId);
  const requestedNewSession = normalizeRouteSessionId(params.newSession);
  const requestedWorkspace = normalizeRouteWorkspace(params.workspace);

  const [sessionId, setSessionId] = useState<string | undefined>();
  const [sessionName, setSessionName] = useState('New chat');
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [fleetSnapshot, setFleetSnapshot] = useState<FleetSnapshot | null>(null);
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [sidebarState, setSidebarState] = useState<SidebarState | null>(null);
  const [toolLogs, setToolLogs] = useState<string[]>([]);
  const [timelineEvents, setTimelineEvents] = useState<SessionTimelineEvent[]>([]);
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
  const [connectionMode, setConnectionMode] = useState<AppConnectionMode>('direct_backend');
  const [pairedDesktopId, setPairedDesktopId] = useState('');
  const [configLoaded, setConfigLoaded] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>('chats');
  const [cronUnreadCount, setCronUnreadCount] = useState(0);
  const [pairPromptOpen, setPairPromptOpen] = useState(false);
  const [workspacePanelOpen, setWorkspacePanelOpen] = useState(false);
  const [composerMenu, setComposerMenu] = useState<'model' | 'tools' | 'permissions' | null>(null);
  const [draftModel, setDraftModel] = useState('');
  const [draftVariant, setDraftVariant] = useState('');
  const [draftPlanner, setDraftPlanner] = useState('');
  const [draftEnabledToolPacks, setDraftEnabledToolPacks] = useState<string[] | null>(null);
  const [draftSecurityPermissionMode, setDraftSecurityPermissionMode] = useState<'low' | 'standard' | 'full_permissions' | ''>('');
  const [draftSessionWorkspace, setDraftSessionWorkspace] = useState<string | undefined>();
  const [telegramBots, setTelegramBots] = useState<TelegramBotConfig[]>([]);
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
  const [artifacts, setArtifacts] = useState<ArtifactSummary[]>([]);
  const [artifactDetail, setArtifactDetail] = useState<ArtifactDetail | null>(null);
  const [artifactStatus, setArtifactStatus] = useState('idle');
  const { confirm, confirmationDialog } = useConfirmation();

  const chatWsRef = useRef<WebSocket | null>(null);
  const voiceWsRef = useRef<WebSocket | null>(null);
  const screenWsRef = useRef<WebSocket | null>(null);
  const appClientIdRef = useRef(createClientId());
  const composerInputRef = useRef<TextInput | null>(null);
  const recordingRef = useRef<any | null>(null);
  const assistantSoundRef = useRef<any | null>(null);
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
  const securityPermissionMutationInFlightRef = useRef<string | null>(null);
  const blankChatRequestedRef = useRef(false);
  const accountSyncKeyRef = useRef('');

  const steeringArmed = steeringBetaEnabled && interruptPolicy !== 'none';
  const canStartVoice = !isVoiceBusy || steeringArmed;
  const mobileVoiceEnabled = false;
  const chatConnected = Boolean(apiBaseUrl && token && !(connectionMode === 'remote_cloud' && !pairedDesktopId));
  const chatBlocked = !configLoaded || !chatConnected;
  const setupMissing = configLoaded && !chatConnected;
  const hasActiveChatSession = Boolean(sessionId);
  const agentControlsDisabled = chatBlocked || !hasActiveChatSession;
  const subAgentSpawnDisabled = agentControlsDisabled || !subAgentPrompt.trim();
  const activeSessionSummary = sessions.find((item) => item.id === sessionId);
  const activeSecurityPermissionMode = String(
    activeSessionSummary?.security_permission_mode
    || draftSecurityPermissionMode
    || 'standard',
  );
  const activeSecurityPermissionLabel = activeSecurityPermissionMode === 'full_permissions'
    ? 'Full access'
    : activeSecurityPermissionMode === 'low'
      ? 'Ask for approval'
      : 'Approve for me';

  const showChatError = (error: unknown, fallback = 'Chat action did not finish.') => {
    setStatus(userFacingError(error, fallback));
  };

  const runtimeStatusText = (message: string, fallback = 'Run needs attention.') => (
    userFacingError(message, fallback)
  );

  const missingConnectionStatus = () => {
    if (!configLoaded) return 'Loading setup.';
    if (!apiBaseUrl) return connectionMode === 'remote_cloud' ? 'Service URL needed.' : 'Connect backend first.';
    if (!token) return connectionMode === 'remote_cloud' ? 'Sign in and pair this phone.' : 'Pair this phone first.';
    if (connectionMode === 'remote_cloud' && !pairedDesktopId) return 'pair this phone with a desktop first';
    return 'Setup needs attention.';
  };
  const requireChatConnection = (options?: { prompt?: boolean }) => {
    if (configLoaded && chatConnected) return true;
    setStatus(missingConnectionStatus());
    if (options?.prompt !== false && configLoaded) {
      setPairPromptOpen(true);
    }
    return false;
  };
  const ensureChatActiveSession = () => {
    if (!requireChatConnection()) return false;
    if (!sessionIdRef.current) {
      setStatus(CHAT_NO_ACTIVE_SESSION_STATUS);
      return false;
    }
    return true;
  };

  const isCurrentAccountRequest = (requestKey: string) => (
    requestKey === accountSyncKeyRef.current
  );

  const resetAccountScopedState = (label = 'syncing account') => {
    pendingMessagesRef.current = [];
    blankChatRequestedRef.current = false;
    sessionIdRef.current = undefined;
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
    [chatWsRef, voiceWsRef, screenWsRef].forEach((socketRef) => {
      if (socketRef.current) {
        try {
          socketRef.current.close();
        } catch {
          // no-op
        }
        socketRef.current = null;
      }
    });
    setSessionId(undefined);
    setSessionName('New chat');
    setInput('');
    setMessages([]);
    setSessions([]);
    setFleetSnapshot(null);
    setJobs([]);
    setSidebarState(null);
    setToolLogs([]);
    setTimelineEvents([]);
    setVoiceState('idle');
    setVoiceDraft('');
    setIsRecording(false);
    setIsVoiceBusy(false);
    setScreenPreview(null);
    setScreenStatus('idle');
    setScreenLiveState('off');
    setIsScreenLive(false);
    setPairPromptOpen(false);
    setWorkspacePanelOpen(false);
    setComposerMenu(null);
    setDraftModel('');
    setDraftVariant('');
    setDraftPlanner('');
    setDraftEnabledToolPacks(null);
    setDraftSecurityPermissionMode('');
    setDraftSessionWorkspace(undefined);
    setTelegramBots([]);
    setAgentOverview(null);
    setSkills([]);
    setSkillValidation(null);
    setMemoryResults([]);
    setConfigEntries([]);
    setSubAgents(null);
    setArtifacts([]);
    setArtifactDetail(null);
    setArtifactStatus('no artifacts');
    setStatus(label);
  };

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    let active = true;
    loadAppConfig()
      .then(async (loadedConfig) => {
        const { config } = await reconcileRemoteAccountConfig(loadedConfig);
        if (!active) return;
        const nextAccountSyncKey = appConfigSyncKey(config);
        if (accountSyncKeyRef.current && accountSyncKeyRef.current !== nextAccountSyncKey) {
          resetAccountScopedState('syncing signed-in account');
        }
        accountSyncKeyRef.current = nextAccountSyncKey;
        setApiBaseUrl(config.apiBaseUrl);
        setToken(config.accountToken || config.accessToken);
        setConnectionMode(config.connectionMode);
        setPairedDesktopId(config.pairedDesktopId);
        setConfigLoaded(true);
      })
      .catch(() => {
        if (!active) return;
        setStatus('Setup needs attention.');
        setConfigLoaded(true);
      });
    return () => {
      active = false;
    };
  }, []);

  const refreshArtifacts = async (targetSessionId?: string) => {
    const requestKey = accountSyncKeyRef.current;
    const activeSessionId = targetSessionId || sessionIdRef.current;
    if (!activeSessionId) {
      setArtifactStatus('no session');
      return;
    }
    if (!chatConnected) {
      setArtifactStatus(missingConnectionStatus());
      return;
    }
    setArtifactStatus('loading artifacts');
    try {
      const result = await fetchSessionArtifacts(apiBaseUrl, token, activeSessionId);
      if (!isCurrentAccountRequest(requestKey)) return;
      setArtifacts(Array.isArray(result) ? result : []);
      setArtifactStatus(result.length ? 'ready' : 'no artifacts');
    } catch (error) {
      if (!isCurrentAccountRequest(requestKey)) return;
      setArtifactStatus(userFacingError(error, 'Artifacts did not load.'));
    }
  };

  const openArtifact = async (artifact: ArtifactSummary) => {
    const activeSessionId = sessionIdRef.current;
    if (!activeSessionId) return;
    if (!requireChatConnection({ prompt: false })) return;
    setArtifactStatus('loading artifact');
    try {
      const detail = await fetchSessionArtifactDetail(apiBaseUrl, token, activeSessionId, artifact.artifact_id);
      setArtifactDetail(detail);
      setArtifactStatus('ready');
    } catch (error) {
      setArtifactStatus(userFacingError(error, 'Artifact did not open.'));
    }
  };

  const applySessionDetail = (detail: SessionDetail) => {
    const previousSessionId = sessionIdRef.current;
    const serverMessages = detail.messages.map((message) => toChatMessage(message));
    const timelineLogs = timelineEventsToLogLines(detail.timeline_events);
    sessionIdRef.current = detail.id;
    setSessionId(detail.id);
    setSessionName(detail.name);
    setTimelineEvents(Array.isArray(detail.timeline_events) ? detail.timeline_events.filter(isUserVisibleTimelineEvent) : []);
    setMessages((previous) => mergeSessionMessagesWithLocalState(
      serverMessages,
      previous,
      detail.id,
      !previousSessionId || previousSessionId === detail.id
    ));
    setToolLogs((previous) => mergeToolLogEntries(
      previousSessionId === detail.id ? [...previous, ...timelineLogs] : timelineLogs
    ));
    setArtifactDetail(null);
    if (detail.artifact_count > 0) {
      setArtifactStatus('loading artifacts');
      void refreshArtifacts(detail.id);
    } else {
      setArtifacts([]);
      setArtifactStatus('no artifacts');
    }
    setDraftModel('');
    setDraftVariant('');
    setDraftPlanner('');
    setDraftEnabledToolPacks(null);
    setDraftSecurityPermissionMode('');
    setComposerMenu(null);
  };

  const updateChatSecurityPermissionMode = async (permissionMode: 'low' | 'standard' | 'full_permissions') => {
    const activeSessionId = sessionIdRef.current;
    if (!requireChatConnection()) return;
    const currentMode = activeSessionId ? activeSecurityPermissionMode : (draftSecurityPermissionMode || 'standard');
    if (currentMode === permissionMode) {
      setComposerMenu(null);
      setStatus(permissionMode === 'full_permissions' ? 'Full access is already enabled for this chat session' : `Permission mode: ${permissionMode}`);
      return;
    }
    const mutationKey = activeSessionId ? `${activeSessionId}:${permissionMode}` : `draft:${permissionMode}`;
    if (securityPermissionMutationInFlightRef.current === mutationKey) {
      return;
    }
    securityPermissionMutationInFlightRef.current = mutationKey;
    try {
      if (!activeSessionId) {
        if (permissionMode === 'full_permissions') {
          const confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirm, {
            action_kind: 'session_full_permissions',
            title: 'Use Full access for this new chat?',
            message: 'The first message will create a chat with broader computer-control permission. Sensitive actions will still ask before execution.',
            risk_tier: 'access',
            origin_surface: 'mobile',
            payload: { draft_chat: true },
          }, {
            confirmLabel: 'Use Full access',
            tone: 'access',
            details: ['Full access applies only to the chat created from this draft.', 'The app still blocks hard safety risks.'],
          });
          if (!confirmationId) return;
        }
        setDraftSecurityPermissionMode(permissionMode);
        setComposerMenu(null);
        setStatus(permissionMode === 'full_permissions' ? 'Full access queued for the new chat' : `Draft permission: ${permissionMode}`);
        return;
      }
      let confirmationId: string | null = null;
      if (permissionMode === 'full_permissions') {
        confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirm, {
          action_kind: 'session_full_permissions',
          title: 'Enable Full access?',
          message: 'This gives this chat broader computer-control permission. Sensitive actions will still ask before execution.',
          risk_tier: 'access',
          origin_surface: 'mobile',
          origin_chat_id: activeSessionId,
          payload: { session_id: activeSessionId },
        }, {
          confirmLabel: 'Enable Full access',
          tone: 'access',
          details: ['Full access lasts only for this chat session.', 'The app will still block hard safety risks and ask before sensitive actions.'],
        });
        if (!confirmationId) return;
      }
      setStatus('updating permission mode');
      try {
        const detail = await updateSessionSecurityPermissionMode(apiBaseUrl, token, activeSessionId, {
          security_permission_mode: permissionMode,
        }, confirmationId);
        applySessionDetail(detail);
        await refreshSidebarData();
        setStatus(permissionMode === 'full_permissions' ? 'Full access enabled for this chat session' : `Permission mode: ${permissionMode}`);
      } catch (error) {
        showChatError(error, 'Permission was not updated.');
      }
    } finally {
      if (securityPermissionMutationInFlightRef.current === mutationKey) {
        securityPermissionMutationInFlightRef.current = null;
      }
    }
  };

  const clearVisibleSession = (label = 'New chat') => {
    sessionIdRef.current = undefined;
    setSessionId(undefined);
    setSessionName(label);
    setMessages([]);
    setTimelineEvents([]);
    setToolLogs([]);
    setAgentOverview(null);
    setVerboseMode(true);
    setArtifacts([]);
    setArtifactDetail(null);
    setArtifactStatus('no artifacts');
    setScreenPreview(null);
    setScreenStatus('idle');
    setStatus('ready');
  };

  const syncOverviewFromSessionDetail = (detail: SessionDetail) => {
    setAgentOverview((previous) => {
      if (!previous) {
        return previous;
      }
      return {
        ...previous,
        session_id: detail.id,
        current_model: detail.model,
        current_variant: detail.variant,
      };
    });
  };

  const applySessionSync = (payload?: Record<string, any>) => {
    const detail = payload?.session as SessionDetail | undefined;
    const syncedSessions = payload?.sessions as SessionSummary[] | undefined;
    const sharedState = payload?.shared_state as Record<string, any> | undefined;
    const activeSessionId = sessionIdRef.current;
    const activeSessionWasDeleted = Boolean(
      activeSessionId
      && Array.isArray(syncedSessions)
      && !syncedSessions.some((item) => item.id === activeSessionId)
    );
    if (Array.isArray(syncedSessions)) {
      setSessions(syncedSessions);
    }
    if (sharedState?.sidebar_state && typeof sharedState.sidebar_state === 'object') {
      setSidebarState(sharedState.sidebar_state as SidebarState);
    }
    if (activeSessionWasDeleted && (!detail?.id || detail.id === activeSessionId)) {
      clearVisibleSession('New chat');
      router.replace('/chat');
      setStatus('chat deleted');
      return;
    }
    if (activeSessionWasDeleted && detail?.id && detail.id !== activeSessionId) {
      applySessionDetail(detail);
      syncOverviewFromSessionDetail(detail);
      router.replace({ pathname: '/chat', params: { sessionId: detail.id } });
      setStatus('chat deleted, switched to current chat');
      void refreshAgentControls(detail.id);
      return;
    }
    if (detail?.id && (!sessionIdRef.current || detail.id === sessionIdRef.current)) {
      applySessionDetail(detail);
      syncOverviewFromSessionDetail(detail);
      void refreshAgentControls(detail.id);
    }
  };

  const refreshSidebarData = async () => {
    if (!chatConnected) return;
    const requestKey = accountSyncKeyRef.current;
    try {
      const [sessionsData, jobsData, cronFeed, nextSidebarState, botConfigs, fleetData] = await Promise.all([
        fetchSessions(apiBaseUrl, token),
        fetchJobs(apiBaseUrl, token),
        fetchCronFeed(apiBaseUrl, token).catch(() => []),
        fetchSidebarState(apiBaseUrl, token).catch(() => null),
        fetchTelegramBotConfigs(apiBaseUrl, token).catch(() => []),
        fetchFleetSnapshot(apiBaseUrl, token).catch(() => null),
      ]);
      if (!isCurrentAccountRequest(requestKey)) return;
      setSessions(Array.isArray(sessionsData) ? sessionsData : []);
      setJobs(Array.isArray(jobsData) ? jobsData : []);
      setTelegramBots(Array.isArray(botConfigs) ? botConfigs : []);
      if (fleetData) {
        setFleetSnapshot(fleetData);
      }
      if (nextSidebarState?.state) {
        setSidebarState(nextSidebarState.state);
      }
      const nextUnreadCount = await getUnreadCronCount(Array.isArray(cronFeed) ? cronFeed : []);
      if (!isCurrentAccountRequest(requestKey)) return;
      setCronUnreadCount(nextUnreadCount);
      const activeSummary = sessionsData.find((session) => session.id === sessionIdRef.current);
      if (activeSummary) {
        setSessionName(activeSummary.name);
      } else if (sessionIdRef.current) {
        clearVisibleSession('New chat');
        router.replace('/chat');
        setStatus('chat deleted');
      }
    } catch {
      // Sidebar data should not interrupt the active chat.
    }
  };

  const refreshAgentControls = async (targetSessionId?: string) => {
    if (!chatConnected) return;
    const requestKey = accountSyncKeyRef.current;
    try {
      const [overview, skillsResult, subAgentResult] = await Promise.all([
        fetchAgentOverview(apiBaseUrl, token, {
          sessionId: targetSessionId,
        }),
        fetchAgentSkills(apiBaseUrl, token, targetSessionId).catch(() => ({ items: [] })),
        fetchSubAgents(apiBaseUrl, token, targetSessionId).catch(() => null),
      ]);
      if (!isCurrentAccountRequest(requestKey)) return;
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
    if (!ensureChatActiveSession()) return;

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
      showChatError(error, 'Agent controls were not saved.');
    }
  };

  const runWorkspaceAction = async (
    label: string,
    action: () => Promise<string | void>,
    options?: { refreshControls?: boolean; successStatus?: string }
  ) => {
    if (!ensureChatActiveSession()) return;
    setStatus(label);
    try {
      const resultMessage = await action();
      if (options?.refreshControls !== false) {
        await refreshAgentControls(sessionIdRef.current);
      }
      setStatus(shortStatusText(resultMessage || options?.successStatus || 'ready'));
    } catch (error) {
      showChatError(error, 'Action did not finish.');
    }
  };

  const resetCurrentContext = async () => {
    if (!ensureChatActiveSession()) return;
    const ok = await confirm({
      title: 'Reset chat context?',
      message: 'This clears the active agent context for this chat. The visible history stays, but the runtime will start fresh.',
      confirmLabel: 'Reset',
      tone: 'danger',
    });
    if (!ok) return;
    await runWorkspaceAction('resetting context', async () => {
      await resetAgentContext(apiBaseUrl, token, sessionIdRef.current);
    });
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
    if (!requireChatConnection()) return;
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
    if (!requireChatConnection()) return;
    await runWorkspaceAction(`validating ${skillName}`, async () => {
      const result = await validateAgentSkill(apiBaseUrl, token, skillName, sessionIdRef.current);
      setSkillValidation(result);
    }, { refreshControls: false });
  };

  const spawnBackgroundTask = async () => {
    if (!ensureChatActiveSession()) return;
    const prompt = subAgentPrompt.trim();
    if (!prompt) {
      setStatus('Prompt required.');
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
    if (!requireChatConnection()) return;
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

  const persistSidebarState = async (nextState: SidebarState) => {
    setSidebarState(nextState);
    if (!chatConnected) return;
    try {
      const result = await updateSidebarState(apiBaseUrl, token, nextState);
      if (result.state) {
        setSidebarState(result.state);
      }
      setStatus('sidebar updated');
    } catch (error) {
      showChatError(error, 'Sidebar was not saved.');
      void refreshSidebarData();
    }
  };

  const selectSession = async (nextSessionId: string, options?: { updateRoute?: boolean; keepLogs?: boolean }) => {
    if (!requireChatConnection({ prompt: false })) return;

    blankChatRequestedRef.current = false;
    setDraftSessionWorkspace(undefined);
    setStatus('loading session');
    try {
      const detail = await activateSession(apiBaseUrl, token, nextSessionId);
      applySessionDetail(detail);
      if (!options?.keepLogs) {
        setToolLogs(timelineEventsToLogLines(detail.timeline_events));
      }
      if (options?.updateRoute !== false) {
        router.replace({ pathname: '/chat', params: { sessionId: detail.id } });
      }
      setStatus('connected');
      void refreshSidebarData();
      void refreshAgentControls(detail.id);
    } catch (error) {
      showChatError(error, 'Identity was not switched.');
    }
  };

  const deleteConversation = async (targetSessionId: string) => {
    if (!targetSessionId) {
      setStatus('Choose a chat first.');
      return;
    }
    if (!requireChatConnection({ prompt: false })) {
      setStatus(missingConnectionStatus());
      return;
    }
    setStatus('deleting chat');
    try {
      const result = await deleteSession(apiBaseUrl, token, targetSessionId);
      const deletedSessionId = result.deleted_session_id || targetSessionId;
      setSessions((previous) => previous.filter((item) => item.id !== deletedSessionId));
      if (sessionIdRef.current === deletedSessionId) {
        blankChatRequestedRef.current = true;
        setDraftSessionWorkspace(undefined);
        clearVisibleSession('New chat');
        router.replace('/chat');
      }
      await refreshSidebarData();
      setStatus('chat deleted');
    } catch (error) {
      showChatError(error, 'Chat did not open.');
    }
  };

  const activeFleetIdentity = (
    fleetSnapshot?.active_identity
    || fleetSnapshot?.identities?.find((identity) => identity.identity_id === fleetSnapshot.active_identity_id)
    || null
  );
  const activeFleetIdentityId = activeFleetIdentity?.identity_id || '';
  const visibleSessions = activeFleetIdentity
    ? sessions.filter((item) => sessionBelongsToFleetIdentity(item, activeFleetIdentity))
    : sessions;
  const activeFleetIdentitySelectedChatId = activeFleetIdentityId
    ? String(fleetSnapshot?.selected_chat_by_identity?.[activeFleetIdentityId] || '').trim()
    : '';
  const activeFleetIdentityTargetChatId = activeFleetIdentity
    ? activeFleetIdentitySelectedChatId || ''
    : '';
  const currentSessionSummary = sessions.find((item) => item.id === sessionId);
  const selectFleetIdentityFromChat = async (identity: FleetIdentity) => {
    if (!identity.identity_id) {
      return;
    }
    if (!requireChatConnection({ prompt: false })) return;
    setStatus(`switching to ${identityLabel(identity)}`);
    try {
      const selectedChatId = fleetSnapshot?.selected_chat_by_identity?.[identity.identity_id] || null;
      const result = await setFleetActiveIdentity(apiBaseUrl, token, identity.identity_id, selectedChatId, 'mobile');
      const nextSnapshot = await fetchFleetSnapshot(apiBaseUrl, token).catch(() => null);
      if (nextSnapshot) {
        setFleetSnapshot(nextSnapshot);
      }
      const nextSelectedChatId = String(
        selectedChatId
        || (result as Record<string, any> | null | undefined)?.selected_chat_id
        || nextSnapshot?.selected_chat_by_identity?.[identity.identity_id]
        || '',
      ).trim();
      if (nextSelectedChatId) {
        await selectSession(nextSelectedChatId, { updateRoute: true });
      } else {
        clearVisibleSession('New chat');
        router.replace('/chat');
        setStatus(`Active identity: ${identityLabel(identity)}`);
      }
    } catch (error) {
      showChatError(error, 'Identity was not switched.');
    }
  };

  useEffect(() => {
    if (!activeFleetIdentity) {
      return;
    }

    const currentSummary = sessionId ? sessions.find((item) => item.id === sessionId) || null : null;
    if (currentSummary && sessionBelongsToFleetIdentity(currentSummary, activeFleetIdentity)) {
      return;
    }

    if (activeFleetIdentityTargetChatId) {
      if (activeFleetIdentityTargetChatId !== sessionIdRef.current) {
        void selectSession(activeFleetIdentityTargetChatId, { updateRoute: true });
      }
      return;
    }

    if (sessionIdRef.current || messages.length || timelineEvents.length || agentOverview) {
      clearVisibleSession('New chat');
      router.replace('/chat');
      setStatus(`Active identity: ${identityLabel(activeFleetIdentity)}`);
    }
  }, [
    activeFleetIdentity,
    activeFleetIdentityTargetChatId,
    agentOverview,
    messages.length,
    router,
    sessionId,
    sessions,
    timelineEvents.length,
  ]);
  const currentEnabledToolPacks = currentSessionSummary?.enabled_tool_packs?.length
    ? currentSessionSummary.enabled_tool_packs
    : agentOverview?.enabled_tool_packs?.length
      ? agentOverview.enabled_tool_packs
      : DEFAULT_TOOL_PACK_IDS;
  const currentAvailableToolPacks = Array.isArray(currentSessionSummary?.available_tool_packs)
    ? currentSessionSummary.available_tool_packs
    : Array.isArray(agentOverview?.available_tool_packs)
      ? agentOverview.available_tool_packs
      : DEFAULT_TOOL_PACK_IDS;
  const lockReasons = (
    (currentSessionSummary?.lock_status?.disabled_pack_reasons as Record<string, unknown> | undefined)
    || (agentOverview?.lock_status?.disabled_pack_reasons as Record<string, unknown> | undefined)
    || {}
  );
  const effectiveEnabledToolPacks = draftEnabledToolPacks || currentEnabledToolPacks;
  const currentModelLabel = draftModel || agentOverview?.current_model || currentSessionSummary?.model || 'Model';
  const currentVariantLabel = draftVariant || agentOverview?.current_variant || '';

  const toggleChatToolPack = async (packId: string) => {
    if (!currentAvailableToolPacks.includes(packId)) {
      const hasLockReason = Boolean(lockReasons[packId]);
      setStatus(hasLockReason ? 'Tool is locked.' : 'Tool unavailable.');
      return;
    }
    const next = effectiveEnabledToolPacks.includes(packId)
      ? effectiveEnabledToolPacks.filter((item) => item !== packId)
      : [...effectiveEnabledToolPacks, packId];
    const activeSessionId = sessionIdRef.current;
    if (!activeSessionId) {
      setDraftEnabledToolPacks(next);
      setStatus(`Draft tools: ${next.length}`);
      return;
    }
    if (!requireChatConnection()) return;
    setStatus('updating tools');
    try {
      const detail = await updateSessionToolPacks(apiBaseUrl, token, activeSessionId, { enabled_tool_packs: next });
      applySessionDetail(detail);
      await refreshSidebarData();
      setStatus(`Tools: ${next.length}`);
    } catch (error) {
      showChatError(error, 'Tools were not updated.');
    }
  };

  const openBlankChat = (workspace?: string) => {
    blankChatRequestedRef.current = true;
    setDraftSessionWorkspace(normalizeRouteWorkspace(workspace));
    clearVisibleSession('New chat');
    setInput('');
    setVoiceDraft('');
    setComposerMenu(null);
    router.replace('/chat');
    setStatus('ready');
  };

  const ensureSessionForSend = async () => {
    if (sessionIdRef.current) return sessionIdRef.current;
    if (!requireChatConnection()) return null;

    setStatus('creating chat');
    try {
      const data = await createSession(apiBaseUrl, token, {
        workspace: draftSessionWorkspace || undefined,
        telegram_bot_config_id: telegramBots.find((bot) => bot.is_default)?.id || telegramBots[0]?.id || undefined,
        enabled_tool_packs: draftEnabledToolPacks || currentEnabledToolPacks,
        security_permission_mode: draftSecurityPermissionMode || undefined,
        ...fleetSessionCreateFields(activeFleetIdentity),
      });

      if (draftModel || draftVariant || draftPlanner) {
        await configureAgent(
          apiBaseUrl,
          token,
          {
            model: draftModel || undefined,
            variant: draftVariant || undefined,
            planner_model: draftPlanner || undefined,
          },
          data.session.id,
        );
      }

      const detail = await fetchSessionDetail(apiBaseUrl, token, data.session.id).catch(() => data.session);
      blankChatRequestedRef.current = false;
      setDraftSessionWorkspace(undefined);
      applySessionDetail(detail);
      setToolLogs(timelineEventsToLogLines(detail.timeline_events));
      router.replace({ pathname: '/chat', params: { sessionId: detail.id } });
      setStatus('session ready');
      void refreshSidebarData();
      void refreshAgentControls(detail.id);
      return detail.id;
    } catch (error) {
      showChatError(error, 'Chat was not created.');
      return null;
    }
  };

  useEffect(() => {
    if (!configLoaded) return;
    if (!chatConnected) {
      setStatus(missingConnectionStatus());
      return;
    }

    let cancelled = false;
    const requestKey = accountSyncKeyRef.current;

    (async () => {
      try {
        const [profile, sessionsData, jobsData, nextSidebarState, botConfigs, fleetData] = await Promise.all([
          fetchProfile(apiBaseUrl, token),
          fetchSessions(apiBaseUrl, token),
          fetchJobs(apiBaseUrl, token),
          fetchSidebarState(apiBaseUrl, token).catch(() => null),
          fetchTelegramBotConfigs(apiBaseUrl, token).catch(() => []),
          fetchFleetSnapshot(apiBaseUrl, token).catch(() => null),
        ]);

        if (cancelled || !isCurrentAccountRequest(requestKey)) return;
        setSessions(Array.isArray(sessionsData) ? sessionsData : []);
        setJobs(Array.isArray(jobsData) ? jobsData : []);
        setTelegramBots(Array.isArray(botConfigs) ? botConfigs : []);
        if (fleetData) {
          setFleetSnapshot(fleetData);
        }
        const loadedActiveFleetIdentity = (
          fleetData?.active_identity
          || fleetData?.identities?.find((identity) => identity.identity_id === fleetData.active_identity_id)
          || null
        );
        const loadedVisibleSessions = loadedActiveFleetIdentity
          ? sessionsData.filter((item) => sessionBelongsToFleetIdentity(item, loadedActiveFleetIdentity))
          : sessionsData;
        if (nextSidebarState?.state) {
          setSidebarState(nextSidebarState.state);
        }

        if (requestedNewSession === '1') {
          if (cancelled) return;
          blankChatRequestedRef.current = true;
          setDraftSessionWorkspace(requestedWorkspace);
          clearVisibleSession('New chat');
          setInput('');
          setVoiceDraft('');
          setComposerMenu(null);
          router.replace('/chat');
          return;
        }

        const selectedIdentityChatId = loadedActiveFleetIdentity
          ? String(fleetData?.selected_chat_by_identity?.[loadedActiveFleetIdentity.identity_id] || '').trim()
          : '';
        const suppressAutoSessionLoad = blankChatRequestedRef.current && !requestedSessionId;
        const profileCurrentSessionId = !suppressAutoSessionLoad
          && !loadedActiveFleetIdentity
          && profile.current_session_id
          && loadedVisibleSessions.some((item) => item.id === profile.current_session_id)
          ? profile.current_session_id
          : '';
        const nextSessionId = requestedSessionId
          || (!suppressAutoSessionLoad && selectedIdentityChatId && loadedVisibleSessions.some((item) => item.id === selectedIdentityChatId) ? selectedIdentityChatId : '')
          || profileCurrentSessionId
          || undefined;
        if (nextSessionId) {
          const detail = requestedSessionId && requestedSessionId !== profile.current_session_id
            ? await activateSession(apiBaseUrl, token, nextSessionId)
            : await fetchSessionDetail(apiBaseUrl, token, nextSessionId);
          if (cancelled || !isCurrentAccountRequest(requestKey)) return;
          applySessionDetail(detail);
          setStatus('connected');
          void refreshAgentControls(detail.id);
        } else {
          sessionIdRef.current = undefined;
          setSessionId(undefined);
          setSessionName('New chat');
          setMessages([]);
          setStatus('ready');
          void refreshAgentControls();
        }
      } catch (error) {
        if (cancelled) return;
        showChatError(error, 'Chat did not load.');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, chatConnected, configLoaded, connectionMode, pairedDesktopId, requestedNewSession, requestedSessionId, requestedWorkspace, router, token]);

  useEffect(() => {
    if (!configLoaded || !chatConnected) return;

    const intervalId = setInterval(() => {
      void refreshSidebarData();
    }, 10_000);

    return () => clearInterval(intervalId);
  }, [apiBaseUrl, chatConnected, configLoaded, connectionMode, pairedDesktopId, token]);

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
    setToolLogs((prev) => mergeToolLogEntries([entry, ...prev]));
  };

  const appendSystemMessage = (
    text: string,
    displayLabel = 'System',
    options?: { ephemeralLocal?: boolean; localSessionId?: string | null }
  ) => {
    if (!text) return;
    setMessages((prev) => mergeLiveMessage(prev, {
      role: 'system',
      content: text,
      displayLabel,
      timestamp: new Date().toISOString(),
      localSessionId: options?.localSessionId ?? sessionIdRef.current ?? null,
      ephemeralLocal: options?.ephemeralLocal,
    }));
  };

  const appendAssistantDelta = (delta: string) => {
    if (!delta) return;
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last?.role === 'assistant') {
        last.content += delta;
        last.ephemeralLocal = last.ephemeralLocal ?? true;
        last.localSessionId = last.localSessionId ?? sessionIdRef.current ?? null;
        last.timestamp = last.timestamp || new Date().toISOString();
        return [...next];
      }
      return [...next, {
        role: 'assistant',
        content: delta,
        displayLabel: 'Assistant',
        timestamp: new Date().toISOString(),
        localSessionId: sessionIdRef.current || null,
        ephemeralLocal: true,
      }];
    });
  };

  const applyAssistantFinal = (text: string) => {
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last?.role === 'assistant') {
        last.content = text || last.content;
        last.ephemeralLocal = last.ephemeralLocal ?? true;
        last.localSessionId = last.localSessionId ?? sessionIdRef.current ?? null;
        last.timestamp = last.timestamp || new Date().toISOString();
        return [...next];
      }
      return [...next, {
        role: 'assistant',
        content: text,
        displayLabel: 'Assistant',
        timestamp: new Date().toISOString(),
        localSessionId: sessionIdRef.current || null,
        ephemeralLocal: true,
      }];
    });
  };

  const appendUserMessage = (text: string, targetSessionId?: string | null) => {
    if (!text) return;
    setMessages((prev) => mergeLiveMessage(prev, {
      role: 'user',
      content: text,
      displayLabel: 'You',
      timestamp: new Date().toISOString(),
      localId: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      localSessionId: targetSessionId ?? sessionIdRef.current ?? null,
      pendingLocal: true,
    }));
  };

  const canSendOverChatSocket = () =>
    Boolean(chatWsRef.current && chatWsRef.current.readyState === WebSocket.OPEN);

  const closeFailedChatSocket = (ws: WebSocket) => {
    if (chatWsRef.current === ws) {
      chatWsRef.current = null;
    }
    try {
      ws.close();
    } catch {
      // no-op
    }
  };

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
      try {
        ws.send(JSON.stringify({
          text: next.text,
          session_id: next.sessionId,
          interrupt_policy: next.interruptPolicy,
        }));
      } catch (error) {
        pendingMessagesRef.current.unshift(next);
        logDiagnostic('chat.queue', 'queued chat send failed; retrying', describeError(error), 'warn');
        closeFailedChatSocket(ws);
        setStatus('chat reconnecting');
        break;
      }
    }

    if (pendingMessagesRef.current.length) {
      setStatus('waiting for backend startup');
      schedulePendingFlush();
      return;
    }

    appendLog('[queue] queued messages delivered');
    setStatus('connected');
  };

  const queuePendingMessage = (
    text: string,
    options?: { appendLocal?: boolean; sessionId?: string | null }
  ) => {
    const targetSessionId = options?.sessionId || sessionIdRef.current || null;
    const pending: PendingOutboundMessage = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      text,
      sessionId: targetSessionId || undefined,
      interruptPolicy,
      expiresAt: Date.now() + OUTBOUND_MESSAGE_TTL_MS,
    };

    pendingMessagesRef.current.push(pending);
    if (options?.appendLocal !== false) {
      appendUserMessage(text, targetSessionId);
    }
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
        const FileSystem = await loadFileSystemModule();
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

    await cleanupAssistantAudio();
    setVoiceState('idle');
    setStatus('assistant audio unavailable on mobile');
    setIsVoiceBusy(false);
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

  const handleRealtimeEvent = (data: ChatEvent, channel: 'chat' | 'voice' | 'screen') => handleChatRealtimeEvent({ router, params, requestedSessionId, requestedNewSession, requestedWorkspace, sessionId, setSessionId, sessionName, setSessionName, input, setInput, messages, setMessages, sessions, setSessions, fleetSnapshot, setFleetSnapshot, jobs, setJobs, sidebarState, setSidebarState, toolLogs, setToolLogs, timelineEvents, setTimelineEvents, status, setStatus, voiceState, setVoiceState, voiceDraft, setVoiceDraft, isRecording, setIsRecording, isVoiceBusy, setIsVoiceBusy, screenPreview, setScreenPreview, screenStatus, setScreenStatus, screenLiveState, setScreenLiveState, isScreenLive, setIsScreenLive, steeringBetaEnabled, setSteeringBetaEnabled, interruptPolicy, setInterruptPolicy, apiBaseUrl, setApiBaseUrl, token, setToken, connectionMode, setConnectionMode, pairedDesktopId, setPairedDesktopId, configLoaded, setConfigLoaded, drawerOpen, setDrawerOpen, drawerTab, setDrawerTab, cronUnreadCount, setCronUnreadCount, pairPromptOpen, setPairPromptOpen, workspacePanelOpen, setWorkspacePanelOpen, composerMenu, setComposerMenu, draftModel, setDraftModel, draftVariant, setDraftVariant, draftPlanner, setDraftPlanner, draftEnabledToolPacks, setDraftEnabledToolPacks, draftSecurityPermissionMode, setDraftSecurityPermissionMode, draftSessionWorkspace, setDraftSessionWorkspace, telegramBots, setTelegramBots, verboseMode, setVerboseMode, agentOverview, setAgentOverview, skills, setSkills, skillValidation, setSkillValidation, memoryQuery, setMemoryQuery, memoryNote, setMemoryNote, memoryResults, setMemoryResults, configKey, setConfigKey, configValue, setConfigValue, configEntries, setConfigEntries, workspaceDraft, setWorkspaceDraft, heartbeatDraft, setHeartbeatDraft, subAgentPrompt, setSubAgentPrompt, subAgents, setSubAgents, artifacts, setArtifacts, artifactDetail, setArtifactDetail, artifactStatus, setArtifactStatus, confirm, confirmationDialog, chatWsRef, voiceWsRef, screenWsRef, appClientIdRef, composerInputRef, recordingRef, assistantSoundRef, assistantAudioPathRef, pendingMessagesRef, outboundRetryRef, segmentTimeoutRef, chatReconnectRef, voiceReconnectRef, screenReconnectRef, segmentSequenceRef, voiceActiveRef, finishingSegmentRef, sessionIdRef, blankChatRequestedRef, steeringArmed, canStartVoice, mobileVoiceEnabled, chatConnected, chatBlocked, setupMissing, hasActiveChatSession, agentControlsDisabled, subAgentSpawnDisabled, activeSessionSummary, activeSecurityPermissionMode, activeSecurityPermissionLabel, showChatError, runtimeStatusText, missingConnectionStatus, requireChatConnection, ensureChatActiveSession, refreshArtifacts, openArtifact, applySessionDetail, updateChatSecurityPermissionMode, clearVisibleSession, syncOverviewFromSessionDetail, applySessionSync, refreshSidebarData, refreshAgentControls, applyQuickAgentConfig, runWorkspaceAction, resetCurrentContext, focusComposer, toggleSkill, runSkillValidation, spawnBackgroundTask, runTaskControl, persistSidebarState, selectSession, deleteConversation, activeFleetIdentity, activeFleetIdentityId, visibleSessions, activeFleetIdentitySelectedChatId, activeFleetIdentityTargetChatId, currentSessionSummary, selectFleetIdentityFromChat, currentEnabledToolPacks, currentAvailableToolPacks, lockReasons, effectiveEnabledToolPacks, currentModelLabel, currentVariantLabel, toggleChatToolPack, openBlankChat, ensureSessionForSend, appendLog, appendSystemMessage, appendAssistantDelta, applyAssistantFinal, appendUserMessage, canSendOverChatSocket, closeFailedChatSocket, schedulePendingFlush, expirePendingMessages, flushPendingMessages, queuePendingMessage, cleanupAssistantAudio, audioExtensionForMime, playAssistantAudio, clearReconnectTimers, applyScreenPayload }, data, channel);

  const uploadAttachment = async (kind: ChatAttachmentKind) => uploadChatAttachment(kind, {
    requireChatConnection,
    setStatus,
    ensureSessionForSend,
    apiBaseUrl,
    token,
    sessionIdRef,
    setSessionId,
    appendLog,
    refreshSidebarData,
    showChatError,
  });

  const refreshScreenshot = async () => {
    if (!configLoaded || !chatConnected) {
      setScreenStatus(missingConnectionStatus());
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
      setScreenStatus(userFacingError(error, 'Screen preview failed.'));
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
        const FileSystem = await loadFileSystemModule();
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
          const FileSystem = await loadFileSystemModule();
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

    setStatus('mobile voice is disabled in v1');
    setVoiceState('idle');
    setIsRecording(false);
    setIsVoiceBusy(false);
    voiceActiveRef.current = false;
  };

  const startVoiceCapture = async () => {
    if (!requireChatConnection()) return;
    if (!mobileVoiceEnabled) {
      setStatus('mobile voice is disabled in v1');
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
      showChatError(error, 'Voice did not start.');
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
  };

  useEffect(() => {
    if (!configLoaded) return;

    clearReconnectTimers();

    if (!chatConnected) {
      setStatus(missingConnectionStatus());
      return;
    }

    let disposed = false;
    const connectionAccountKey = accountSyncKeyRef.current;
    const socketStillCurrent = () => !disposed && accountSyncKeyRef.current === connectionAccountKey;

    const buildWsUrl = (path: string) => {
      const base = buildWsBaseUrl(apiBaseUrl);
      const params = new URLSearchParams({ token, client_id: appClientIdRef.current });
      if (sessionIdRef.current) params.set('session_id', sessionIdRef.current);
      return `${base}${path}?${params.toString()}`;
    };

    const connectChatSocket = () => {
      if (!socketStillCurrent()) return;
      const url = buildWsUrl(connectionMode === 'remote_cloud' ? '/ws/remote/mobile' : '/ws/app/chat');
      logDiagnostic('chat.ws', 'connecting', { url });
      const ws = new WebSocket(url);
      chatWsRef.current = ws;
      ws.onopen = () => {
        if (!socketStillCurrent()) return;
        logDiagnostic('chat.ws', 'connected', { url });
        if (pendingMessagesRef.current.length) {
          setStatus('connected · sending queued message');
          void flushPendingMessages();
        } else {
          setStatus('connected');
        }
      };
      ws.onclose = (event) => {
        const shouldReconnect = socketStillCurrent();
        logDiagnostic('chat.ws', 'closed', {
          code: event.code,
          reason: event.reason || '<empty>',
          wasClean: event.wasClean,
        }, event.wasClean ? 'info' : 'warn');
        if (chatWsRef.current === ws) chatWsRef.current = null;
        if (shouldReconnect) {
          setStatus('chat reconnecting');
          chatReconnectRef.current = setTimeout(connectChatSocket, SOCKET_RECONNECT_MS);
        }
      };
      ws.onerror = () => {
        if (!socketStillCurrent()) return;
        logDiagnostic('chat.ws', 'error', { readyState: ws.readyState }, 'error');
        setStatus('chat error');
        if (pendingMessagesRef.current.length) {
          schedulePendingFlush();
        }
      };
      ws.onmessage = (event) => {
        if (!socketStillCurrent()) return;
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
      if (!mobileVoiceEnabled) {
        setVoiceState('disabled');
        return;
      }
      if (!socketStillCurrent()) return;
      const url = buildWsUrl('/ws/app/voice');
      logDiagnostic('voice.ws', 'connecting', { url });
      const ws = new WebSocket(url);
      voiceWsRef.current = ws;
      ws.onopen = () => {
        if (!socketStillCurrent()) return;
        logDiagnostic('voice.ws', 'connected', { url });
        setVoiceState('ready');
      };
      ws.onclose = (event) => {
        const shouldReconnect = socketStillCurrent();
        logDiagnostic('voice.ws', 'closed', {
          code: event.code,
          reason: event.reason || '<empty>',
          wasClean: event.wasClean,
        }, event.wasClean ? 'info' : 'warn');
        if (voiceWsRef.current === ws) voiceWsRef.current = null;
        if (shouldReconnect) {
          setVoiceState('reconnecting');
          voiceReconnectRef.current = setTimeout(connectVoiceSocket, SOCKET_RECONNECT_MS);
        }
      };
      ws.onerror = () => {
        if (!socketStillCurrent()) return;
        logDiagnostic('voice.ws', 'error', { readyState: ws.readyState }, 'error');
        setVoiceState('error');
      };
      ws.onmessage = (event) => {
        if (!socketStillCurrent()) return;
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
  }, [apiBaseUrl, chatConnected, configLoaded, connectionMode, pairedDesktopId, token]);

  useEffect(() => {
    if (!configLoaded) return;

    if (!chatConnected || !isScreenLive) {
      if (!isScreenLive) {
        setScreenLiveState('off');
        setScreenStatus('idle');
      } else {
        setScreenLiveState('warning');
        setScreenStatus(missingConnectionStatus());
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
    const connectionAccountKey = accountSyncKeyRef.current;
    const socketStillCurrent = () => !disposed && accountSyncKeyRef.current === connectionAccountKey;
    setScreenLiveState('connecting');
    setScreenStatus('live connecting');

    const connectScreenSocket = () => {
      if (!socketStillCurrent()) return;
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
        if (!socketStillCurrent()) return;
        logDiagnostic('screen.ws', 'connected', { url });
        setScreenLiveState('connected');
        setScreenStatus('live connected');
      };
      ws.onclose = (event) => {
        const shouldReconnect = socketStillCurrent();
        logDiagnostic('screen.ws', 'closed', {
          code: event.code,
          reason: event.reason || '<empty>',
          wasClean: event.wasClean,
        }, event.wasClean ? 'info' : 'warn');
        if (screenWsRef.current === ws) {
          screenWsRef.current = null;
        }
        if (shouldReconnect) {
          setScreenLiveState('reconnecting');
          setScreenStatus('live reconnecting');
          screenReconnectRef.current = setTimeout(connectScreenSocket, SOCKET_RECONNECT_MS);
        }
      };
      ws.onerror = () => {
        if (!socketStillCurrent()) return;
        logDiagnostic('screen.ws', 'error', { readyState: ws.readyState }, 'error');
        setScreenLiveState('error');
        setScreenStatus('live error');
      };
      ws.onmessage = (event) => {
        if (!socketStillCurrent()) return;
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
  }, [apiBaseUrl, chatConnected, configLoaded, connectionMode, isScreenLive, pairedDesktopId, token]);

  const requireProviderApiKey = () => {
    if (!agentOverview) {
      return true;
    }
    const hasModelProvider = (agentOverview.model_groups || []).some((group: any) => (
      Array.isArray(group?.models) && group.models.length > 0
    ));
    if (hasModelProvider) {
      return true;
    }
    const message = 'You have not set an API key yet. Add an API key in Setup before sending a message.';
    setStatus(message);
    appendLog(`[setup] ${message}`);
    appendSystemMessage(message, 'Setup');
    return false;
  };

  const send = async () => {
    if (!requireChatConnection()) return;
    if (!requireProviderApiKey()) return;
    const trimmed = input.trim();
    if (!trimmed) return;
    const materializedSessionId = await ensureSessionForSend();
    if (!materializedSessionId) return;
    if (!canSendOverChatSocket()) {
      queuePendingMessage(trimmed, { sessionId: materializedSessionId });
      return;
    }
    const ws = chatWsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      queuePendingMessage(trimmed, { sessionId: materializedSessionId });
      return;
    }
    appendUserMessage(trimmed, materializedSessionId);
    logDiagnostic('chat.ws', 'sending chat message', {
      sessionId: materializedSessionId,
      interruptPolicy,
      textPreview: trimmed.slice(0, 140),
    });
    try {
      ws.send(JSON.stringify({
        text: trimmed,
        session_id: materializedSessionId,
        interrupt_policy: interruptPolicy,
      }));
    } catch (error) {
      logDiagnostic('chat.ws', 'chat send failed; queueing message', describeError(error), 'warn');
      closeFailedChatSocket(ws);
      queuePendingMessage(trimmed, { appendLocal: false, sessionId: materializedSessionId });
      return;
    }
    setInput('');
    setVoiceDraft('');
  };

  const toggleVerboseMode = async () => {
    if (!ensureChatActiveSession()) return;

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
      showChatError(error, 'Verbose feed was not updated.');
    }
  };

  const sessionUpdatedAt = sessions.find((item) => item.id === sessionId)?.updated_at;
  const subtitle = !configLoaded
    ? 'Loading chat setup...'
    : setupMissing
    ? (connectionMode === 'remote_cloud'
      ? 'Sign in and pair this phone with your desktop to open the shared chat space.'
      : (apiBaseUrl ? 'Tap the message field to finish pairing' : 'Tap the message field to connect this phone'))
    : (sessionId
      ? `Updated ${formatRelativeTime(sessionUpdatedAt)}`
      : draftSessionWorkspace
        ? `Ready in ${draftSessionWorkspace}`
        : 'Ready to chat');
  const pairingPromptTitle = connectionMode === 'remote_cloud'
    ? 'Connect this phone to your desktop'
    : (apiBaseUrl ? 'Finish pairing this phone' : 'Connect this phone');
  const pairingPromptText = connectionMode === 'remote_cloud'
    ? 'Sign in to the Kraitos control plane, then complete desktop pairing. After that, the phone stays synced through the VPS while the desktop remains the execution machine.'
    : (
      apiBaseUrl
        ? 'This phone already knows the backend URL, but it still needs a trusted-device token before chat opens up.'
        : 'Add the backend URL first, then complete trusted-device pairing. After that, chat stays as the main workspace.'
    );
  const workspaceStatus = [
    { label: 'Connection', value: shortStatusText(status) },
    { label: 'Session', value: sessionId ? sessionName : 'No session yet' },
    ...(draftSessionWorkspace && !sessionId ? [{ label: 'Workspace', value: draftSessionWorkspace }] : []),
  ];
  const fleetIdentities = fleetSnapshot?.identities || [];
  const sendDisabled = chatBlocked || !input.trim();

  return <ChatScreenView scope={{ router, params, requestedSessionId, requestedNewSession, requestedWorkspace, sessionId, setSessionId, sessionName, setSessionName, input, setInput, messages, setMessages, sessions, setSessions, fleetSnapshot, setFleetSnapshot, jobs, setJobs, sidebarState, setSidebarState, toolLogs, setToolLogs, timelineEvents, setTimelineEvents, status, setStatus, voiceState, setVoiceState, voiceDraft, setVoiceDraft, isRecording, setIsRecording, isVoiceBusy, setIsVoiceBusy, screenPreview, setScreenPreview, screenStatus, setScreenStatus, screenLiveState, setScreenLiveState, isScreenLive, setIsScreenLive, steeringBetaEnabled, setSteeringBetaEnabled, interruptPolicy, setInterruptPolicy, apiBaseUrl, setApiBaseUrl, token, setToken, connectionMode, setConnectionMode, pairedDesktopId, setPairedDesktopId, configLoaded, setConfigLoaded, drawerOpen, setDrawerOpen, drawerTab, setDrawerTab, cronUnreadCount, setCronUnreadCount, pairPromptOpen, setPairPromptOpen, workspacePanelOpen, setWorkspacePanelOpen, composerMenu, setComposerMenu, draftModel, setDraftModel, draftVariant, setDraftVariant, draftPlanner, setDraftPlanner, draftEnabledToolPacks, setDraftEnabledToolPacks, draftSecurityPermissionMode, setDraftSecurityPermissionMode, draftSessionWorkspace, setDraftSessionWorkspace, telegramBots, setTelegramBots, verboseMode, setVerboseMode, agentOverview, setAgentOverview, skills, setSkills, skillValidation, setSkillValidation, memoryQuery, setMemoryQuery, memoryNote, setMemoryNote, memoryResults, setMemoryResults, configKey, setConfigKey, configValue, setConfigValue, configEntries, setConfigEntries, workspaceDraft, setWorkspaceDraft, heartbeatDraft, setHeartbeatDraft, subAgentPrompt, setSubAgentPrompt, subAgents, setSubAgents, artifacts, setArtifacts, artifactDetail, setArtifactDetail, artifactStatus, setArtifactStatus, confirm, confirmationDialog, chatWsRef, voiceWsRef, screenWsRef, appClientIdRef, composerInputRef, recordingRef, assistantSoundRef, assistantAudioPathRef, pendingMessagesRef, outboundRetryRef, segmentTimeoutRef, chatReconnectRef, voiceReconnectRef, screenReconnectRef, segmentSequenceRef, voiceActiveRef, finishingSegmentRef, sessionIdRef, blankChatRequestedRef, steeringArmed, canStartVoice, mobileVoiceEnabled, chatConnected, chatBlocked, setupMissing, hasActiveChatSession, agentControlsDisabled, subAgentSpawnDisabled, activeSessionSummary, activeSecurityPermissionMode, activeSecurityPermissionLabel, showChatError, runtimeStatusText, missingConnectionStatus, requireChatConnection, ensureChatActiveSession, refreshArtifacts, openArtifact, applySessionDetail, updateChatSecurityPermissionMode, clearVisibleSession, syncOverviewFromSessionDetail, applySessionSync, refreshSidebarData, refreshAgentControls, applyQuickAgentConfig, runWorkspaceAction, resetCurrentContext, focusComposer, toggleSkill, runSkillValidation, spawnBackgroundTask, runTaskControl, persistSidebarState, selectSession, deleteConversation, activeFleetIdentity, activeFleetIdentityId, visibleSessions, activeFleetIdentitySelectedChatId, activeFleetIdentityTargetChatId, currentSessionSummary, selectFleetIdentityFromChat, currentEnabledToolPacks, currentAvailableToolPacks, lockReasons, effectiveEnabledToolPacks, currentModelLabel, currentVariantLabel, toggleChatToolPack, openBlankChat, ensureSessionForSend, appendLog, appendSystemMessage, appendAssistantDelta, applyAssistantFinal, appendUserMessage, canSendOverChatSocket, closeFailedChatSocket, schedulePendingFlush, expirePendingMessages, flushPendingMessages, queuePendingMessage, cleanupAssistantAudio, audioExtensionForMime, playAssistantAudio, clearReconnectTimers, applyScreenPayload, handleRealtimeEvent, uploadAttachment, refreshScreenshot, finishCurrentSegment, startSegmentRecording, startVoiceCapture, stopVoiceCapture, send, toggleVerboseMode, sessionUpdatedAt, subtitle, pairingPromptTitle, pairingPromptText, workspaceStatus, fleetIdentities, sendDisabled }} />;
}
