import { useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from 'react';
import {
  Animated,
  Easing,
  Image,
  Platform,
  Pressable,
  ScrollView,

  Text,
  TextInput,
  View,
  type LayoutChangeEvent,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  type TextInputContentSizeChangeEventData,
} from 'react-native';
import { useRouter } from 'expo-router';

import { buildWsBaseUrl } from '../../lib/appConfig';
import { describeError, logDiagnostic, shortStatusText, userFacingError } from '../../lib/diagnostics';
import { useConfirmation } from '@/components/ConfirmationDialog';
import { createApprovedConfirmation } from '@/lib/sharedConfirmations';
import {
  openDesktopConversationContextMenu,
  type DesktopConversationContextMenuState,
  type DesktopConversationContextMenuTarget,
} from './DesktopConversationContextMenu';
import {
  desktopVoiceMachineReducer,
  initialDesktopVoiceMachineState,
} from './desktopJarvisState';
import {
  activateSession,
  appendSessionTimelineEvent,
  configureAgent,
  configureVoiceSttBackend,
  configureVoiceTtsBackend,
  controlAgentRun,
  createSession,
  deleteSession,
  fetchAgentConfig,
  fetchAgentOverview,
  fetchJobs,
  fetchProfile,
  fetchRuntimeOrchestratorStatus,
  fetchSessionArtifactBlob,
  fetchSessionArtifactDetail,
  fetchSessionArtifacts,
  fetchSessionDetail,
  fetchSessions,
  fetchTelegramBotConfigs,
  fetchVoiceRuntimeStatus,
  setTaskBoardArmedNextTurn,
  searchSessions,
  configureHeadlessRuntime,
  stopProcessWait,
  updateSessionHeadlessEligibility,
  updateSessionSecurityPermissionMode,
  updateSessionTelegramBotAssignment,
  updateSessionToolPacks,
  uploadAppAttachment,
  updateAgentConfig,
  warmVoiceRuntime,
  type AgentOverview,
  type ArtifactDetail,
  type ArtifactSummary,
  type ModelProviderGroup,
  type RuntimeOrchestratorStatus,
  type ScheduledJob,
  type SessionDetail,
  type SessionMessage,
  type SessionSearchResult,
  type SessionSummary,
  type SessionTimelineEvent,
  type TelegramBotConfig,
  type TaskBoard,
} from '@/lib/appApi';
import {
  assignDesktopFleetGroupTask,
  assignDesktopFleetTask,
  checkoutDesktopGitBranch,
  copyDesktopText,
  continueDesktopFleetWorkerQueue,
  createDesktopFolder,
  createDesktopFleetEnrollment,
  createDesktopFleetGroup,
  createDesktopFleetLocalWorker,
  deleteDesktopFleetGroup,
  deleteDesktopFleetWorker,
  getDesktopGitRepoInfo,
  getDesktopPathStatus,
  loadDesktopBootstrap,
  loadDesktopFleetSnapshot,
  loadDesktopSidebarState,
  pickDesktopFolder,
  renameDesktopFleetWorker,
  requestDesktopFleetWorkerPreview,
  resetDesktopFleetWorker,
  saveDesktopSidebarState,
  setDesktopFleetActiveIdentity,
  stopAllDesktopFleetWorkers,
  stopDesktopFleetWorker,
  type DesktopFleetEnrollment,
  type DesktopFleetIdentity,
  type DesktopFleetSnapshot,
  type DesktopFleetTask,
  type DesktopFleetWorker,
  type DesktopGitRepoState,
  type DesktopPathStatus,
  type DesktopVoicePackState,
  type DesktopRuntimeStatus,
  type DesktopSidebarProjectActivity,
  type DesktopSidebarState,
  type DesktopVoiceRuntimeStatus,
} from '@/lib/desktopBridge';
import {
  DESKTOP_COMMAND_PLACEHOLDER,
  DESKTOP_COMMAND_SUGGESTIONS,
  isDesktopSlashCommand,
  runDesktopSlashCommand,
} from '@/desktop/desktopCommands';
import {
  createLocalToolTimelineEvent,
  mergeTimelineEventState,
  normalizeTimelineEvents,
  timelineEventMergeKey,
} from '@/desktop/conversationTimeline';
import {
  extractReferenceTitle,
  isReferenceSidebarMessage,
  labelForMessage,
  summarizeReferenceContent,
  summarizeToolPayload,
  toDesktopMessages,
  toLiveDesktopMessage,
  type DesktopMessage,
} from '@/desktop/desktopMessages';
import {
  groupPlannerModelsByProvider,
  modelProviderKey,
  preferredModelFromGroups,
} from '@/desktop/modelProviders';
import {
  DESKTOP_SIDEBAR_ACTIVITY_LIMIT,
  SIDEBAR_DRAFT_CHAT_ID,
  coerceSidebarState,
  createEmptySidebarState,
  ensureSidebarProjectEntries,
  ensureSidebarProjectEntry,
  existingSessionIdFrom,
  fleetSessionCreateFields,
  isAbsoluteWindowsPath,
  isWorkspacePathAllowed,
  normalizeWorkspacePath,
  projectDisplayName,
  projectPathBasename,
  projectPathHint,
  sessionBelongsToFleetIdentity,
  sessionSidebarSortComparator,
  shouldKeepSidebarProjectPath,
  workspaceSortOrder,
} from '@/desktop/desktopSidebarState';
import {
  ALWAYS_ON_VOICE_AUTO_SEND,
  JARVIS_BARGE_IN_MIN_VOICED_MS,
  JARVIS_ENGLISH_VOICE_PATH_ERROR,
  JARVIS_WAKE_PHRASE,
  STT_BACKEND_GEMINI,
  STT_BACKEND_LOCAL_WHISPER,
  STT_BACKEND_OPENAI_REALTIME,
  TTS_BACKEND_KOKORO,
  TTS_BACKEND_KYUTAI,
  VOICE_ENGINE_ENGLISH,
  VOICE_ENGINE_HEBREW,
  VOICE_ENGINE_NONE,
  appendVoiceTranscriptSegment,
  composeVoiceDraftInput,
  isMeaningfulJarvisBargeInText,
  jarvisSttBackendLabel,
  jarvisTtsBackendLabel,
  normalizeJarvisSttBackend,
  normalizeJarvisTtsBackend,
  type JarvisSttBackend,
  type JarvisTtsBackend,
} from '@/desktop/desktopVoicePolicy';
import { getCommandSuggestionQuery, parseComposerSlashCommand } from '@/desktop/desktopComposer';
import { mergeTimelineEntries, messageTimestampValue } from '@/desktop/desktopTimelineEntries';
import {
  bytesToBase64,
  concatFloat32,
  createAudioContext,
  createVoiceGateState,
  encodePcm16Wav,
  samplesDbfs,
  takeGateFrame,
  type VoiceGateState,
} from '@/desktop/desktopVoiceAudio';
import {
  clearJarvisWakeProfile,
  createJarvisWakeMatchState,
  isJarvisWakeProfileReady,
  loadJarvisWakeProfile,
  saveJarvisWakeProfile,
  type JarvisWakeMatchState,
  type JarvisWakeProfile,
} from '@/desktop/desktopJarvisWakeProfile';
import {
  normalizeCompletedTaskBoards,
  resolveTaskBoardState,
  summarizeRuntimeStatus,
  taskBoardStatusLabel,
  taskBoardStepPrefix,
} from '@/desktop/desktopTaskBoard';
import { clampUsagePercent, finiteStatusNumber, formatStatusNumber } from '@/desktop/desktopStatusNumbers';
import {
  TOOL_PACK_DEFINITIONS,
  availableToolPackIdsFrom,
  defaultToolPackIds,
  enabledToolPackIdsFrom,
  formatToolPackLockReason as formatToolPackLockReasonText,
  toggleToolPackId,
  toolPackLabel,
} from '@/desktop/desktopToolPacks';
import { formatAbsoluteTime, formatRelativeTime } from '@/lib/time';
import { fleetTaskBatchStatusMessage, fleetTaskStatusMessage, isBlockedFleetTask } from '@/lib/fleetStatus';

const VOICE_SEGMENT_MS = 850;
const VOICE_GATE_DBFS = -35.5;
const VOICE_GATE_ATTACK_MS = 25;
const VOICE_GATE_MIN_MS = 50;
const VOICE_GATE_RELEASE_MS = 1500;
const VOICE_GATE_PREROLL_MS = 350;
const VOICE_GATE_FRAME_MS = 30;
const VOICE_GATE_MAX_MS = 30000;
const VOICE_DEFERRED_FRAME_MAX_MS = 15000;
const HEBREW_VOICE_SEGMENT_MS = 1200;
const HEBREW_VOICE_GATE_DBFS = -39.5;
const HEBREW_VOICE_GATE_RELEASE_MS = 900;
const HEBREW_VOICE_GATE_PREROLL_MS = 300;
const HEBREW_VOICE_GATE_MAX_MS = 3600;
const SOCKET_RECONNECT_MS = 1600;
const SIDEBAR_REFRESH_MS = 15000;
const MAX_ACTIVITY_ITEMS = 40;
const TRANSCRIPT_AUTO_SCROLL_IDLE_MS = 15000;
const TRANSCRIPT_SCROLL_UP_THRESHOLD = 6;
const TRANSCRIPT_SCROLL_MOVE_THRESHOLD = 2;
const MAX_COMMAND_SUGGESTIONS = 8;
// Flip this back to true if always-on voice should submit immediately after gate close.
const DESKTOP_NO_ACTIVE_SESSION_STATUS = 'Open or select a chat before using agent controls.';

type InterruptPolicy = 'none' | 'steer_now' | 'after_tool';
type MessageSourceFormat = 'app_text' | 'app_voice_transcript';
type ComposerRunMode = 'normal' | 'plan' | 'goal';
type PlanAction = 'approve' | 'dismiss' | 'answer_question' | 'exit';
type PlanAnswer = { question_id: string; option_id?: string | null; freeform_text?: string | null };
type ComposerModeOptions = {
  runMode?: ComposerRunMode | null;
  planAction?: PlanAction | null;
  planAnswer?: PlanAnswer | null;
};
type VoiceCaptureMode = 'push_to_talk' | 'always_on';
export type ConversationSurfaceMode = 'chat' | 'jarvis' | 'fleet';

export type DesktopConversationHeaderControls = {
  mode: ConversationSurfaceMode;
  identityStopActive: boolean;
  setMode: (mode: ConversationSurfaceMode) => void;
  stopIdentity: () => Promise<void>;
  newChat: () => Promise<void>;
  openProject: () => Promise<void>;
  toggleSidebar: () => void;
};
type StartupReadinessState = 'warming' | 'chat_ready' | 'fatal_error';
type ComposerInputOrigin = 'manual' | 'voice' | 'system';
type SecurityPermissionMode = 'low' | 'standard' | 'full_permissions';
type ActiveCommandPanel =
  | { kind: 'model' }
  | { kind: 'tools'; source?: 'main' | 'fleet' }
  | { kind: 'permissions'; sessionId?: string | null }
  | { kind: 'draftProject' }
  | { kind: 'draftBranch' }
  | { kind: 'draftTelegram' }
  | { kind: 'session'; sessionId: string }
  | { kind: 'verbose' }
  | { kind: 'command'; command: string; description: string }
  | null;

type ActivityItem = {
  id: string;
  tone: 'neutral' | 'accent' | 'warn' | 'error';
  text: string;
  timestamp: number;
};

type PendingSearchJump = {
  sessionId: string;
  messageIndex: number;
  attempt: number;
};

type QueuedMessage = {
  clientMessageId: string;
  text: string;
  sourceFormat: MessageSourceFormat;
  interruptPolicy: InterruptPolicy;
  sessionId?: string;
  deliveryState?: 'queued' | 'sent';
  modeOptions?: ComposerModeOptions;
};

type QueuedComposerMessage = {
  id: string;
  text: string;
  sourceFormat: MessageSourceFormat;
  sessionId: string;
  queuedAt: number;
  modeOptions?: ComposerModeOptions;
};

type Props = {
  apiBaseUrl: string;
  token: string;
  initialSessionId?: string | null;
  initialSurfaceMode?: ConversationSurfaceMode;
  runtimeMode?: string;
  runtimeStatus?: DesktopRuntimeStatus | null;
  envFilePath?: string;
  defaultWorkspace?: string | null;
  defaultInterruptPolicy?: string | null;
  configuredModelGroups?: ModelProviderGroup[];
  configuredPlannerModels?: string[];
  voicePackState?: DesktopVoicePackState | null;
  voiceStatus?: DesktopVoiceRuntimeStatus | null;
  onSelectVoiceEngine?: (engine: string) => Promise<boolean> | boolean;
  onStartupStateChange?: (state: StartupReadinessState, detail?: string) => void;
  onOpenSetup?: (target?: { tab?: 'general' | 'packs'; packId?: string | null }) => void;
  accountEmail?: string;
  updateAvailable?: boolean;
  remoteAuthBusy?: boolean;
  remoteAuthLoggingOut?: boolean;
  onLogoutRemoteAccount?: () => void;
  onInviteUnavailable?: () => void;
  setupOpen?: boolean;
  sidebarToggleSignal?: number;
  onHeaderControlsChange?: (controls: DesktopConversationHeaderControls | null) => void;
};

type FoldSectionProps = {
  title: string;
  summary: string;
  defaultOpen?: boolean;
  children: ReactNode;
};

function normalizeInterruptPolicyValue(value: string | null | undefined): InterruptPolicy {
  const normalized = String(value || '').trim().toLowerCase();
  return normalized === 'steer_now' || normalized === 'after_tool' ? normalized : 'none';
}

function strOrNull(value: string | null | undefined) {
  const normalized = String(value || '').trim();
  return normalized || null;
}

type ReferenceEntry = {
  id: string;
  index: number;
  title: string;
  summary: string;
  message: DesktopMessage;
};

type SidebarDraftChat = {
  id: '__draft__';
  projectPath: string;
  title: string;
  telegramBotConfigId?: string | null;
  model?: string | null;
  variant?: string | null;
  plannerModel?: string | null;
  enabledToolPacks?: string[];
  securityPermissionMode?: SecurityPermissionMode;
  selectedBranch?: string | null;
};

type SidebarChatTooltipState = {
  sessionId: string;
  title: string;
  projectPath: string;
  botLabel: string;
  top: number;
  left: number;
};

type ToolPackInfoPopupState = {
  packId: string;
  top: number;
  left: number;
};

type SidebarProjectGroup = {
  path: string;
  label: string;
  hint: string;
  pinned: boolean;
  collapsed: boolean;
  folderAvailable: boolean;
  activity: DesktopSidebarProjectActivity[];
  sessions: SessionSummary[];
  matchesSearch: boolean;
};

type SidebarDragState =
  | { kind: 'project'; projectPath: string }
  | { kind: 'chat'; projectPath: string; sessionId: string }
  | null;

type SearchResultTarget =
  | { kind: 'project'; projectPath: string }
  | { kind: 'session'; sessionId: string; projectPath: string }
  | { kind: 'message'; sessionId: string; projectPath: string; messageIndex: number };

import { COMPOSER_MAX_HEIGHT, COMPOSER_MIN_HEIGHT } from './DesktopConversationView.styleConstants';
import { FoldSection, MonoIcon, createClientId } from './DesktopConversationView.components';
import { handleDesktopConversationRealtimeEvent } from './DesktopConversationRealtime';
import { DesktopConversationRender } from './DesktopConversationRender';
import { useDesktopConversationController } from './DesktopConversationController';
import { styles } from './DesktopConversationView.styles';
import type { DesktopAudioCaptureHandle } from './desktopAudioCapture';

export function DesktopConversationView({
  apiBaseUrl,
  token,
  initialSessionId,
  initialSurfaceMode = 'chat',
  runtimeMode,
  runtimeStatus,
  envFilePath,
  defaultWorkspace,
  defaultInterruptPolicy,
  configuredModelGroups = [],
  configuredPlannerModels = [],
  voicePackState,
  voiceStatus,
  onSelectVoiceEngine,
  onStartupStateChange,
  onOpenSetup,
  accountEmail,
  updateAvailable,
  remoteAuthBusy,
  remoteAuthLoggingOut,
  onLogoutRemoteAccount,
  onInviteUnavailable,
  sidebarToggleSignal,
  onHeaderControlsChange,
}: Props) {
  const router = useRouter();
  const chatWsRef = useRef<WebSocket | null>(null);
  const voiceWsRef = useRef<WebSocket | null>(null);
  const controllerScopeRef = useRef<any>(null);
  const appClientIdRef = useRef(createClientId());
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const voiceReconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingMessagesRef = useRef<QueuedMessage[]>([]);
  const scrollRef = useRef<ScrollView | null>(null);
  const historyScrollRef = useRef<ScrollView | null>(null);
  const shellRef = useRef<any>(null);
  const sidebarSearchInputRef = useRef<TextInput | null>(null);
  const sessionIdRef = useRef<string | undefined>(undefined);
  const voiceStreamRef = useRef<MediaStream | null>(null);
  const voiceAudioContextRef = useRef<AudioContext | null>(null);
  const voiceAudioSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const voiceCaptureNodeRef = useRef<DesktopAudioCaptureHandle | null>(null);
  const voiceChunkSequenceRef = useRef(0);
  const voiceChunkChainRef = useRef(Promise.resolve());
  const voiceChunkSamplesRef = useRef<Float32Array[]>([]);
  const voiceChunkSampleCountRef = useRef(0);
  const externalSidebarToggleSignalRef = useRef(sidebarToggleSignal);
  const activeVoiceUtteranceIdRef = useRef<string | null>(null);
  const voiceSampleRateRef = useRef(16000);
  const voicePressActiveRef = useRef(false);
  const voiceCaptureModeRef = useRef<VoiceCaptureMode>('push_to_talk');
  const alwaysOnEnabledRef = useRef(false);
  const voiceStartInFlightRef = useRef(false);
  const voiceGateStateRef = useRef<VoiceGateState>(createVoiceGateState());
  const jarvisWakeMatchStateRef = useRef<JarvisWakeMatchState>(createJarvisWakeMatchState());
  const voiceRunningRef = useRef(false);
  const voiceRecordingRef = useRef(false);
  const voiceComposerBaseInputRef = useRef('');
  const voiceComposerDraftRef = useRef('');
  const lastComposerInputOriginRef = useRef<ComposerInputOrigin>('system');
  const deferredAlwaysOnFramesRef = useRef<Float32Array[]>([]);
  const deferredAlwaysOnSampleCountRef = useRef(0);
  const drainingDeferredAlwaysOnFramesRef = useRef(false);
  const lastVoiceWarmRequestEngineRef = useRef<string | null>(null);
  const assistantAudioRef = useRef<HTMLAudioElement | null>(null);
  const assistantAudioTextRef = useRef('');
  const activeVoiceBargeInCandidateRef = useRef(false);
  const activeVoiceBargeInReferenceTextRef = useRef('');
  const jarvisBargeInCandidateUtteranceIdsRef = useRef<Set<string>>(new Set());
  const transcriptAutoScrollSuspendedRef = useRef(false);
  const transcriptAutoScrollResumeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const transcriptPendingAutoScrollRef = useRef(false);
  const transcriptLastScrollOffsetYRef = useRef(0);
  const transcriptProgrammaticScrollUntilRef = useRef(0);
  const transcriptLastSignatureRef = useRef('');
  const transcriptContentHeightRef = useRef(0);
  const transcriptViewportHeightRef = useRef(0);
  const referenceAutoOpenKeyRef = useRef<string | null>(null);
  const referenceDismissedKeyRef = useRef<string | null>(null);
  const taskBoardStateRef = useRef<{ taskId: string | null; status: string | null }>({
    taskId: null,
    status: null,
  });
  const startupSidebarReadyRef = useRef(false);
  const startupSessionStateReadyRef = useRef(false);
  const startupChatSocketReadyRef = useRef(false);
  const startupTerminalStateRef = useRef<StartupReadinessState | null>(null);
  const draftChatRef = useRef<SidebarDraftChat | null>(null);
  const currentWorkspaceBySessionRef = useRef<Record<string, string>>({});
  const sidebarSearchRequestIdRef = useRef(0);
  const transcriptMessageLayoutRef = useRef<Record<number, number>>({});
  const historyMessageLayoutRef = useRef<Record<number, number>>({});
  const searchJumpTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchHighlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const floatingPanelRef = useRef<any>(null);
  const modelTriggerRef = useRef<any>(null);
  const toolsTriggerRef = useRef<any>(null);
  const permissionsTriggerRef = useRef<any>(null);
  const draftProjectTriggerRef = useRef<any>(null);
  const draftBranchTriggerRef = useRef<any>(null);
  const draftTelegramTriggerRef = useRef<any>(null);
  const sidebarSearchLauncherRef = useRef<any>(null);
  const sidebarSearchModalRef = useRef<any>(null);
  const commandSuggestionMenuRef = useRef<any>(null);
  const composerTextRegionRef = useRef<any>(null);
  const projectMenuRefs = useRef<Record<string, any>>({});
  const projectMenuTriggerRefs = useRef<Record<string, any>>({});
  const sessionRowRefs = useRef<Record<string, any>>({});
  const sessionMenuRefs = useRef<Record<string, any>>({});
  const sessionMenuTriggerRefs = useRef<Record<string, any>>({});
  const toolPackInfoButtonRefs = useRef<Record<string, any>>({});
  const sidebarChatTooltipTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toolPackInfoHideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sidebarCollectionsRefreshInFlightRef = useRef(false);
  const overviewRefreshInFlightRef = useRef(false);
  const chatRunActiveRef = useRef(false);
  const assistantDeltaBufferRef = useRef('');
  const assistantDeltaFlushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const conversationModeRef = useRef<ConversationSurfaceMode>(initialSurfaceMode);
  const jarvisWarmRequestedRef = useRef(false);
  const jarvisPushToTalkActiveRef = useRef(false);
  const jarvisSpaceHotkeyActiveRef = useRef(false);

  const [sessionId, setSessionId] = useState<string | undefined>(initialSessionId || undefined);
  const [sessionName, setSessionName] = useState('Shared session');
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionListLoading, setSessionListLoading] = useState(true);
  const [messages, setMessages] = useState<DesktopMessage[]>([]);
  const [timelineEvents, setTimelineEvents] = useState<SessionTimelineEvent[]>([]);
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [overview, setOverview] = useState<AgentOverview | null>(null);
  const [cachedModelGroups, setCachedModelGroups] = useState<ModelProviderGroup[]>(configuredModelGroups);
  const [cachedPlannerModels, setCachedPlannerModels] = useState<string[]>(configuredPlannerModels);
  const [orchestratorStatus, setOrchestratorStatus] = useState<RuntimeOrchestratorStatus | null>(null);
  const [telegramBotConfigs, setTelegramBotConfigs] = useState<TelegramBotConfig[]>([]);
  const [taskBoard, setTaskBoard] = useState<TaskBoard | null>(null);
  const [completedTaskBoards, setCompletedTaskBoards] = useState<TaskBoard[]>([]);
  const [taskBoardArmedNextTurn, setTaskBoardArmedNextTurnState] = useState(false);
  const [taskBoardCollapsed, setTaskBoardCollapsed] = useState(false);
  const [expandedCompletedTaskIds, setExpandedCompletedTaskIds] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState('loading shared session');
  const [socketState, setSocketState] = useState('connecting');
  const [conversationMode, setConversationMode] = useState<ConversationSurfaceMode>(initialSurfaceMode);
  useEffect(() => {
    setSessionListLoading(true);
  }, [apiBaseUrl, token]);
  useEffect(() => {
    if (sessions.length > 0 || status === 'ready') {
      setSessionListLoading(false);
    }
  }, [sessions.length, status]);
  useEffect(() => {
    if (initialSurfaceMode !== conversationModeRef.current) {
      setConversationMode(initialSurfaceMode);
      conversationModeRef.current = initialSurfaceMode;
    }
  }, [initialSurfaceMode]);
  const [input, setInput] = useState('');
  const [composerInputHeight, setComposerInputHeight] = useState(COMPOSER_MIN_HEIGHT);
  const [activeCommandPanel, setActiveCommandPanel] = useState<ActiveCommandPanel>(null);
  const [assistantDraft, setAssistantDraft] = useState('');
  const [thinking, setThinking] = useState('');
  const [lastAssistantOutputAt, setLastAssistantOutputAt] = useState<number | null>(null);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [interruptPolicy, setInterruptPolicy] = useState<InterruptPolicy>(() => normalizeInterruptPolicyValue(defaultInterruptPolicy));
  const [chatRunActive, setChatRunActive] = useState(false);
  const [runtimeRunState, setRuntimeRunState] = useState<'idle' | 'running'>('idle');
  const [queuedComposerMessages, setQueuedComposerMessages] = useState<QueuedComposerMessage[]>([]);
  const [voiceMachineState, dispatchVoiceMachine] = useReducer(
    desktopVoiceMachineReducer,
    initialDesktopVoiceMachineState,
  );
  const voiceState = voiceMachineState.voiceState;
  const jarvisState = voiceMachineState.jarvisPhase;
  const setVoiceState = (value: string) => dispatchVoiceMachine({ type: 'voice_state', value });
  const [voiceDraft, setVoiceDraft] = useState('');
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [voiceRunning, setVoiceRunning] = useState(false);
  const [voiceRecording, setVoiceRecording] = useState(false);
  const [voiceMode, setVoiceMode] = useState<VoiceCaptureMode>('push_to_talk');
  const [voiceEngineChanging, setVoiceEngineChanging] = useState(false);
  const [sttBackendChanging, setSttBackendChanging] = useState<JarvisSttBackend | null>(null);
  const [ttsBackendChanging, setTtsBackendChanging] = useState<JarvisTtsBackend | null>(null);
  const [liveVoiceStatus, setLiveVoiceStatus] = useState<DesktopVoiceRuntimeStatus | null>(null);
  const [alwaysOnEnabled, setAlwaysOnEnabled] = useState(false);
  const [jarvisWakeProfile, setJarvisWakeProfile] = useState<JarvisWakeProfile | null>(() => loadJarvisWakeProfile());
  const jarvisWakeProfileRef = useRef<JarvisWakeProfile | null>(jarvisWakeProfile);
  const [jarvisWakeEnrollmentOpen, setJarvisWakeEnrollmentOpen] = useState(false);
  const [sidebarExpanded, setSidebarExpanded] = useState(true);
  const [rightSidebarWidth, setRightSidebarWidth] = useState(328);
  const [fleetPanelOpen, setFleetPanelOpen] = useState(false);
  const [fleetSnapshot, setFleetSnapshot] = useState<DesktopFleetSnapshot | null>(null);
  const [fleetLoading, setFleetLoading] = useState(false);
  const [fleetStatus, setFleetStatus] = useState('Fleet idle');
  const [fleetError, setFleetError] = useState<string | null>(null);
  const [fleetWorkerNameDraft, setFleetWorkerNameDraft] = useState('');
  const [fleetEnrollment, setFleetEnrollment] = useState<DesktopFleetEnrollment | null>(null);
  const [fleetTaskDrafts, setFleetTaskDrafts] = useState<Record<string, string>>({});
  const [fleetRenameDrafts, setFleetRenameDrafts] = useState<Record<string, string>>({});
  const [fleetGroupNameDraft, setFleetGroupNameDraft] = useState('');
  const [fleetGroupTaskDrafts, setFleetGroupTaskDrafts] = useState<Record<string, string>>({});
  const [openFleetWorkerMenuId, setOpenFleetWorkerMenuId] = useState<string | null>(null);
  const [fleetChatPanelWidth, setFleetChatPanelWidth] = useState(340);
  const [fleetChatPanelCollapsed, setFleetChatPanelCollapsed] = useState(false);
  const [fleetDashboardCollapsed, setFleetDashboardCollapsed] = useState(false);
  const [sidebarSearch, setSidebarSearch] = useState('');
  const [sidebarSearchModalOpen, setSidebarSearchModalOpen] = useState(false);
  const [sidebarSearchLoading, setSidebarSearchLoading] = useState(false);
  const [sidebarSearchError, setSidebarSearchError] = useState<string | null>(null);
  const [sidebarSearchResults, setSidebarSearchResults] = useState<SessionSearchResult[]>([]);
  const [draftGitRepoState, setDraftGitRepoState] = useState<DesktopGitRepoState | null>(null);
  const [draftGitRepoLoading, setDraftGitRepoLoading] = useState(false);
  const [draftProjectSearch, setDraftProjectSearch] = useState('');
  const [draftBranchSearch, setDraftBranchSearch] = useState('');
  const [sidebarState, setSidebarState] = useState<DesktopSidebarState>(createEmptySidebarState());
  const [sidebarStateReady, setSidebarStateReady] = useState(false);
  const [projectPathStatuses, setProjectPathStatuses] = useState<Record<string, DesktopPathStatus>>({});
  const [draftChat, setDraftChat] = useState<SidebarDraftChat | null>(null);
  const [pendingDraftSecurityPermissionMode, setPendingDraftSecurityPermissionMode] = useState<SecurityPermissionMode | ''>('');
  const [dragState, setDragState] = useState<SidebarDragState>(null);
  const [hoveredProjectPath, setHoveredProjectPath] = useState<string | null>(null);
  const [openProjectMenuPath, setOpenProjectMenuPath] = useState<string | null>(null);
  const [hoveredSessionId, setHoveredSessionId] = useState<string | null>(null);
  const [openSessionMenuId, setOpenSessionMenuId] = useState<string | null>(null);
  const [sidebarChatTooltip, setSidebarChatTooltip] = useState<SidebarChatTooltipState | null>(null);
  const [contextMenu, setContextMenu] = useState<DesktopConversationContextMenuState>(null);
  const [pendingSessionSwitch, setPendingSessionSwitch] = useState<
    | { mode: 'session'; sessionId: string; jumpMessageIndex?: number | null }
    | { mode: 'draft_send'; projectPath: string; text: string; sourceFormat: MessageSourceFormat; modeOptions?: ComposerModeOptions }
    | null
  >(null);
  const [pendingSearchJump, setPendingSearchJump] = useState<PendingSearchJump | null>(null);
  const [highlightedMessageIndex, setHighlightedMessageIndex] = useState<number | null>(null);
  const [showVoicePanel, setShowVoicePanel] = useState(false);
  const [showReferenceRail, setShowReferenceRail] = useState(false);
  const [showArtifactRail, setShowArtifactRail] = useState(false);
  const [artifacts, setArtifacts] = useState<ArtifactSummary[]>([]);
  const [artifactsLoading, setArtifactsLoading] = useState(false);
  const [artifactError, setArtifactError] = useState<string | null>(null);
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);
  const [selectedArtifactDetail, setSelectedArtifactDetail] = useState<ArtifactDetail | null>(null);
  const [artifactDetailLoading, setArtifactDetailLoading] = useState(false);
  const [toolPackMutationInFlight, setToolPackMutationInFlight] = useState<string | null>(null);
  const [attachmentUploadInFlight, setAttachmentUploadInFlight] = useState(false);
  const [hoveredToolPackInfoId, setHoveredToolPackInfoId] = useState<string | null>(null);
  const [pinnedToolPackInfoId, setPinnedToolPackInfoId] = useState<string | null>(null);
  const [toolPackInfoPopup, setToolPackInfoPopup] = useState<ToolPackInfoPopupState | null>(null);
  const [activePermissionInfoId, setActivePermissionInfoId] = useState<SecurityPermissionMode | null>(null);
  const [expandedModelProviders, setExpandedModelProviders] = useState<Record<string, boolean>>({});
  const [expandedPlannerProviders, setExpandedPlannerProviders] = useState<Record<string, boolean>>({});
  const [sessionSettingsMutationInFlight, setSessionSettingsMutationInFlight] = useState(false);
  const { confirm: confirmAction, confirmationDialog } = useConfirmation();
  const folderChoiceResolveRef = useRef<((projectPath: string | null) => void) | null>(null);
  const [folderChoiceOpen, setFolderChoiceOpen] = useState(false);
  const [folderChoiceBusy, setFolderChoiceBusy] = useState<null | 'auto' | 'choose'>(null);
  const thinkingShineProgress = useRef(new Animated.Value(0)).current;
  const jarvisPulseProgress = useRef(new Animated.Value(0)).current;
  const [voicePanelHidden, setVoicePanelHidden] = useState(false);
  const [jarvisMuted, setJarvisMuted] = useState(false);
  useEffect(() => {
    dispatchVoiceMachine({ type: 'muted', value: conversationMode === 'jarvis' && jarvisMuted });
  }, [conversationMode, jarvisMuted]);
  const [jarvisStatusDrawerOpen, setJarvisStatusDrawerOpen] = useState(false);
  const [jarvisVoiceSettingsOpen, setJarvisVoiceSettingsOpen] = useState(false);
  const [jarvisHoldToTalkMode, setJarvisHoldToTalkMode] = useState(false);
  const [jarvisLatestTranscript, setJarvisLatestTranscript] = useState('');
  const [jarvisLatestSpokenText, setJarvisLatestSpokenText] = useState('');
  const [dismissedCommandSuggestionInput, setDismissedCommandSuggestionInput] = useState<string | null>(null);
  const [keepRuntimeOnAppClose, setKeepRuntimeOnAppClose] = useState(false);
  const [savingCloseBehavior, setSavingCloseBehavior] = useState(false);
  const [contextUsageHovered, setContextUsageHovered] = useState(false);
  const visibleVoiceStatus = conversationMode === 'jarvis' ? (liveVoiceStatus || voiceStatus || null) : null;
  const selectedVoiceEngine = voicePackState?.defaultEngine || visibleVoiceStatus?.selected_engine || VOICE_ENGINE_NONE;
  const currentJarvisSttBackend = normalizeJarvisSttBackend(visibleVoiceStatus?.stt_backend || null);
  const currentJarvisSttLabel = jarvisSttBackendLabel(currentJarvisSttBackend);
  const apiVoiceInputActive = currentJarvisSttBackend === STT_BACKEND_OPENAI_REALTIME || currentJarvisSttBackend === STT_BACKEND_GEMINI;
  const allowedWorkspaceRoot = normalizeWorkspacePath(defaultWorkspace);
  const usingHebrewVoiceEngine = selectedVoiceEngine === VOICE_ENGINE_HEBREW;
  const activeVoiceSegmentMs = usingHebrewVoiceEngine ? HEBREW_VOICE_SEGMENT_MS : VOICE_SEGMENT_MS;
  const configuredVoiceGateDbfs = finiteStatusNumber(visibleVoiceStatus?.voice_gate_dbfs);
  const configuredHebrewVoiceGateDbfs = finiteStatusNumber(
    visibleVoiceStatus?.hebrew_voice_gate_dbfs,
  );
  const activeVoiceGateDbfs = usingHebrewVoiceEngine
    ? configuredHebrewVoiceGateDbfs ?? HEBREW_VOICE_GATE_DBFS
    : configuredVoiceGateDbfs ?? VOICE_GATE_DBFS;
  const configuredJarvisBargeInGateDbfs = finiteStatusNumber(
    visibleVoiceStatus?.jarvis_barge_in_gate_dbfs,
  );
  const activeJarvisBargeInGateDbfs = configuredJarvisBargeInGateDbfs ?? activeVoiceGateDbfs;
  const activeVoiceGateReleaseMs = usingHebrewVoiceEngine ? HEBREW_VOICE_GATE_RELEASE_MS : VOICE_GATE_RELEASE_MS;
  const currentJarvisTtsBackend = normalizeJarvisTtsBackend(visibleVoiceStatus?.tts_backend || null);
  const currentJarvisTtsLabel = jarvisTtsBackendLabel(currentJarvisTtsBackend);
  const jarvisWakeProfileReady = isJarvisWakeProfileReady(jarvisWakeProfile);
  const currentJarvisWakePhrase = jarvisWakeProfile?.phrase || JARVIS_WAKE_PHRASE;
  const saveLocalJarvisWakeProfile = (profile: JarvisWakeProfile) => {
    saveJarvisWakeProfile(profile);
    jarvisWakeProfileRef.current = profile;
    setJarvisWakeProfile(profile);
    setJarvisWakeEnrollmentOpen(false);
    setStatus(`Wake phrase "${profile.phrase}" saved locally`);
  };
  const clearLocalJarvisWakeProfile = () => {
    clearJarvisWakeProfile();
    jarvisWakeProfileRef.current = null;
    setJarvisWakeProfile(null);
    setJarvisWakeEnrollmentOpen(true);
    setStatus('Jarvis wake phrase training cleared');
  };
  const closeContextMenu = () => setContextMenu(null);
  const openConversationContextMenu = (event: any, target: DesktopConversationContextMenuTarget) => {
    if (Platform.OS !== 'web') {
      return;
    }
    if (sidebarChatTooltipTimerRef.current) {
      clearTimeout(sidebarChatTooltipTimerRef.current);
      sidebarChatTooltipTimerRef.current = null;
    }
    setSidebarChatTooltip(null);
    setOpenProjectMenuPath(null);
    setOpenSessionMenuId(null);
    openDesktopConversationContextMenu(setContextMenu, event, target);
  };
  const openChatContextMenu = (event: any, session: SessionSummary, projectPath?: string | null) => {
    openConversationContextMenu(event, { kind: 'chat', session, projectPath });
  };
  const openProjectContextMenu = (event: any, project: any) => {
    openConversationContextMenu(event, { kind: 'project', project });
  };
  const openMessageContextMenu = (event: any, message: DesktopMessage) => {
    if (message.role === 'user') {
      openConversationContextMenu(event, { kind: 'userMessage', content: message.content });
    } else if (message.role === 'assistant') {
      openConversationContextMenu(event, { kind: 'assistantFinal', content: message.content });
    }
  };
  const openToolContextMenu = (event: any, content: string) => {
    openConversationContextMenu(event, { kind: 'toolCall', content });
  };

  const killLiveCommand = async (metadata: Record<string, any>) => {
    const processWaitId = String(metadata?.process_wait_id || '').trim();
    const commandId = String(metadata?.command_id || '').trim();
    const command = String(metadata?.command || commandId || 'command').trim();
    if (!processWaitId) {
      setStatus('No running process handle is available for that command.');
      return;
    }
    try {
      const confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirmAction, {
        action_kind: 'process_wait_stop',
        title: 'Stop this command?',
        message: 'EmploAI will stop only the exact process attached to this live command.',
        risk_tier: 'danger',
        origin_surface: 'desktop_chat',
        payload: { process_wait_id: processWaitId, command_id: commandId, command },
      }, {
        confirmLabel: 'Stop command',
        tone: 'danger',
      });
      if (!confirmationId) {
        return;
      }
      setStatus(`Stopping ${command.slice(0, 80)}`);
      await stopProcessWait(apiBaseUrl, token, processWaitId, 'Stopped from the live command card.', confirmationId);
      setStatus(`Stop requested for ${commandId || 'command'}`);
    } catch (error) {
      setStatus(userFacingError(error, 'Command was not stopped.'));
    }
  };

      const controllerScope = useDesktopConversationController({ ALWAYS_ON_VOICE_AUTO_SEND, Animated, COMPOSER_MAX_HEIGHT, COMPOSER_MIN_HEIGHT, DESKTOP_COMMAND_PLACEHOLDER, DESKTOP_COMMAND_SUGGESTIONS, DESKTOP_NO_ACTIVE_SESSION_STATUS, DESKTOP_SIDEBAR_ACTIVITY_LIMIT, DesktopConversationRender, Easing, FoldSection, HEBREW_VOICE_GATE_DBFS, HEBREW_VOICE_GATE_MAX_MS, HEBREW_VOICE_GATE_PREROLL_MS, HEBREW_VOICE_GATE_RELEASE_MS, HEBREW_VOICE_SEGMENT_MS, Image, JARVIS_BARGE_IN_MIN_VOICED_MS, JARVIS_ENGLISH_VOICE_PATH_ERROR, MAX_ACTIVITY_ITEMS, MAX_COMMAND_SUGGESTIONS, MonoIcon, Platform, Pressable, SIDEBAR_DRAFT_CHAT_ID, SIDEBAR_REFRESH_MS, SOCKET_RECONNECT_MS, STT_BACKEND_GEMINI, STT_BACKEND_LOCAL_WHISPER, STT_BACKEND_OPENAI_REALTIME, ScrollView, TOOL_PACK_DEFINITIONS, TRANSCRIPT_AUTO_SCROLL_IDLE_MS, TRANSCRIPT_SCROLL_MOVE_THRESHOLD, TRANSCRIPT_SCROLL_UP_THRESHOLD, TTS_BACKEND_KOKORO, TTS_BACKEND_KYUTAI, Text, TextInput, VOICE_DEFERRED_FRAME_MAX_MS, VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW, VOICE_ENGINE_NONE, VOICE_GATE_ATTACK_MS, VOICE_GATE_DBFS, VOICE_GATE_FRAME_MS, VOICE_GATE_MAX_MS, VOICE_GATE_MIN_MS, VOICE_GATE_PREROLL_MS, VOICE_GATE_RELEASE_MS, VOICE_SEGMENT_MS, View, accountEmail, activateSession, activeCommandPanel, activeJarvisBargeInGateDbfs, activePermissionInfoId, activeVoiceBargeInCandidateRef, activeVoiceBargeInReferenceTextRef, activeVoiceGateDbfs, activeVoiceGateReleaseMs, activeVoiceSegmentMs, activeVoiceUtteranceIdRef, activity, allowedWorkspaceRoot, alwaysOnEnabled, alwaysOnEnabledRef, apiBaseUrl, apiVoiceInputActive, appClientIdRef, appendSessionTimelineEvent, appendVoiceTranscriptSegment, artifactDetailLoading, artifactError, artifacts, artifactsLoading, assignDesktopFleetGroupTask, assignDesktopFleetTask, assistantAudioRef, assistantAudioTextRef, assistantDeltaBufferRef, assistantDeltaFlushTimerRef, assistantDraft, attachmentUploadInFlight, availableToolPackIdsFrom, buildWsBaseUrl, bytesToBase64, cachedModelGroups, cachedPlannerModels, chatRunActive, chatRunActiveRef, chatWsRef, checkoutDesktopGitBranch, clampUsagePercent, clearLocalJarvisWakeProfile, coerceSidebarState, commandSuggestionMenuRef, completedTaskBoards, composeVoiceDraftInput, composerInputHeight, composerTextRegionRef, concatFloat32, configureAgent, configureHeadlessRuntime, configureVoiceSttBackend, configureVoiceTtsBackend, configuredHebrewVoiceGateDbfs, configuredJarvisBargeInGateDbfs, configuredModelGroups, configuredPlannerModels, configuredVoiceGateDbfs, confirmAction, confirmationDialog, contextUsageHovered, continueDesktopFleetWorkerQueue, controlAgentRun, conversationMode, conversationModeRef, copyDesktopText, createApprovedConfirmation, createAudioContext, createClientId, createDesktopFleetEnrollment, createDesktopFleetGroup, createDesktopFleetLocalWorker, createDesktopFolder, createEmptySidebarState, createJarvisWakeMatchState, createLocalToolTimelineEvent, createSession, createVoiceGateState, currentJarvisSttBackend, currentJarvisSttLabel, currentJarvisTtsBackend, currentJarvisTtsLabel, currentJarvisWakePhrase, currentWorkspaceBySessionRef, defaultInterruptPolicy, defaultToolPackIds, defaultWorkspace, deferredAlwaysOnFramesRef, deferredAlwaysOnSampleCountRef, deleteDesktopFleetGroup, deleteDesktopFleetWorker, deleteSession, describeError, dismissedCommandSuggestionInput, draftBranchSearch, draftBranchTriggerRef, draftChat, draftChatRef, draftGitRepoLoading, draftGitRepoState, draftProjectSearch, draftProjectTriggerRef, draftTelegramTriggerRef, dragState, drainingDeferredAlwaysOnFramesRef, enabledToolPackIdsFrom, encodePcm16Wav, ensureSidebarProjectEntries, ensureSidebarProjectEntry, envFilePath, existingSessionIdFrom, expandedCompletedTaskIds, expandedModelProviders, expandedPlannerProviders, externalSidebarToggleSignalRef, extractReferenceTitle, fetchAgentConfig, fetchAgentOverview, fetchJobs, fetchProfile, fetchRuntimeOrchestratorStatus, fetchSessionArtifactBlob, fetchSessionArtifactDetail, fetchSessionArtifacts, fetchSessionDetail, fetchSessions, fetchTelegramBotConfigs, fetchVoiceRuntimeStatus, finiteStatusNumber, fleetChatPanelCollapsed, fleetChatPanelWidth, fleetDashboardCollapsed, fleetEnrollment, fleetError, fleetGroupNameDraft, fleetGroupTaskDrafts, fleetLoading, fleetPanelOpen, fleetRenameDrafts, fleetSessionCreateFields, fleetSnapshot, fleetStatus, fleetTaskBatchStatusMessage, fleetTaskDrafts, fleetTaskStatusMessage, fleetWorkerNameDraft, floatingPanelRef, folderChoiceBusy, folderChoiceOpen, folderChoiceResolveRef, formatAbsoluteTime, formatRelativeTime, formatStatusNumber, formatToolPackLockReasonText, getCommandSuggestionQuery, getDesktopGitRepoInfo, getDesktopPathStatus, groupPlannerModelsByProvider, handleDesktopConversationRealtimeEvent, highlightedMessageIndex, historyMessageLayoutRef, historyScrollRef, hoveredProjectPath, hoveredSessionId, hoveredToolPackInfoId, initialSessionId, initialSurfaceMode, input, interruptPolicy, isAbsoluteWindowsPath, isBlockedFleetTask, isDesktopSlashCommand, isMeaningfulJarvisBargeInText, isReferenceSidebarMessage, isWorkspacePathAllowed, jarvisBargeInCandidateUtteranceIdsRef, jarvisHoldToTalkMode, jarvisLatestSpokenText, jarvisLatestTranscript, jarvisMuted, jarvisPulseProgress, jarvisPushToTalkActiveRef, jarvisSpaceHotkeyActiveRef, jarvisStatusDrawerOpen, jarvisSttBackendLabel, jarvisTtsBackendLabel, jarvisVoiceSettingsOpen, jarvisWakeEnrollmentOpen, jarvisWakeMatchStateRef, jarvisWakeProfile, jarvisWakeProfileReady, jarvisWakeProfileRef, jarvisWarmRequestedRef, jobs, keepRuntimeOnAppClose, labelForMessage, lastAssistantOutputAt, lastComposerInputOriginRef, lastVoiceWarmRequestEngineRef, liveVoiceStatus, loadDesktopBootstrap, loadDesktopFleetSnapshot, loadDesktopSidebarState, logDiagnostic, mergeTimelineEntries, mergeTimelineEventState, messageTimestampValue, messages, modelProviderKey, modelTriggerRef, normalizeCompletedTaskBoards, normalizeInterruptPolicyValue, normalizeJarvisSttBackend, normalizeJarvisTtsBackend, normalizeTimelineEvents, normalizeWorkspacePath, onInviteUnavailable, onLogoutRemoteAccount, onOpenSetup, onSelectVoiceEngine, onStartupStateChange, openFleetWorkerMenuId, openProjectMenuPath, openSessionMenuId, orchestratorStatus, overview, overviewRefreshInFlightRef, parseComposerSlashCommand, pendingDraftSecurityPermissionMode, pendingMessagesRef, pendingSearchJump, pendingSessionSwitch, permissionsTriggerRef, pickDesktopFolder, pinnedToolPackInfoId, preferredModelFromGroups, projectDisplayName, projectMenuRefs, projectMenuTriggerRefs, projectPathBasename, projectPathHint, projectPathStatuses, queuedComposerMessages, reconnectRef, referenceAutoOpenKeyRef, referenceDismissedKeyRef, remoteAuthBusy, remoteAuthLoggingOut, renameDesktopFleetWorker, requestDesktopFleetWorkerPreview, resetDesktopFleetWorker, resolveTaskBoardState, rightSidebarWidth, router, runDesktopSlashCommand, runtimeMode, runtimeRunState, runtimeStatus, samplesDbfs, saveDesktopSidebarState, saveLocalJarvisWakeProfile, savingCloseBehavior, scrollRef, searchHighlightTimerRef, searchJumpTimerRef, searchSessions, selectedArtifactDetail, selectedArtifactId, selectedVoiceEngine, sessionBelongsToFleetIdentity, sessionId, sessionIdRef, sessionMenuRefs, sessionMenuTriggerRefs, sessionName, sessionRowRefs, sessionSettingsMutationInFlight, sessionSidebarSortComparator, sessions, setActiveCommandPanel, setActivePermissionInfoId, setActivity, setAlwaysOnEnabled, setArtifactDetailLoading, setArtifactError, setArtifacts, setArtifactsLoading, setAssistantDraft, setAttachmentUploadInFlight, setCachedModelGroups, setCachedPlannerModels, setChatRunActive, setCompletedTaskBoards, setComposerInputHeight, setContextUsageHovered, setConversationMode, setDesktopFleetActiveIdentity, setDismissedCommandSuggestionInput, setDraftBranchSearch, setDraftChat, setDraftGitRepoLoading, setDraftGitRepoState, setDraftProjectSearch, setDragState, setExpandedCompletedTaskIds, setExpandedModelProviders, setExpandedPlannerProviders, setFleetChatPanelCollapsed, setFleetChatPanelWidth, setFleetDashboardCollapsed, setFleetEnrollment, setFleetError, setFleetGroupNameDraft, setFleetGroupTaskDrafts, setFleetLoading, setFleetPanelOpen, setFleetRenameDrafts, setFleetSnapshot, setFleetStatus, setFleetTaskDrafts, setFleetWorkerNameDraft, setFolderChoiceBusy, setFolderChoiceOpen, setHighlightedMessageIndex, setHoveredProjectPath, setHoveredSessionId, setHoveredToolPackInfoId, setInput, setInterruptPolicy, setJarvisHoldToTalkMode, setJarvisLatestSpokenText, setJarvisLatestTranscript, setJarvisMuted, setJarvisStatusDrawerOpen, setJarvisVoiceSettingsOpen, setJarvisWakeEnrollmentOpen, setJobs, setKeepRuntimeOnAppClose, setLastAssistantOutputAt, setLiveVoiceStatus, setMessages, setOpenFleetWorkerMenuId, setOpenProjectMenuPath, setOpenSessionMenuId, setOrchestratorStatus, setOverview, setPendingDraftSecurityPermissionMode, setPendingSearchJump, setPendingSessionSwitch, setPinnedToolPackInfoId, setProjectPathStatuses, setQueuedComposerMessages, setRightSidebarWidth, setRuntimeRunState, setSavingCloseBehavior, setSelectedArtifactDetail, setSelectedArtifactId, setSessionId, setSessionName, setSessionSettingsMutationInFlight, setSessions, setShowArtifactRail, setShowReferenceRail, setShowVoicePanel, setSidebarChatTooltip, setSidebarExpanded, setSidebarSearch, setSidebarSearchError, setSidebarSearchLoading, setSidebarSearchModalOpen, setSidebarSearchResults, setSidebarState, setSidebarStateReady, setSocketState, setStatus, setSttBackendChanging, setTaskBoard, setTaskBoardArmedNextTurn, setTaskBoardArmedNextTurnState, setTaskBoardCollapsed, setTelegramBotConfigs, setThinking, setTimelineEvents, setToolPackInfoPopup, setToolPackMutationInFlight, setTtsBackendChanging, setVoiceDraft, setVoiceEngineChanging, setVoiceError, setVoiceMode, setVoicePanelHidden, setVoiceRecording, setVoiceRunning, setVoiceState, shellRef, shortStatusText, shouldKeepSidebarProjectPath, showArtifactRail, showReferenceRail, showVoicePanel, sidebarChatTooltip, sidebarChatTooltipTimerRef, sidebarCollectionsRefreshInFlightRef, sidebarExpanded, sidebarSearch, sidebarSearchError, sidebarSearchInputRef, sidebarSearchLauncherRef, sidebarSearchLoading, sidebarSearchModalOpen, sidebarSearchModalRef, sidebarSearchRequestIdRef, sidebarSearchResults, sidebarState, sidebarStateReady, sidebarToggleSignal, socketState, startupChatSocketReadyRef, startupSessionStateReadyRef, startupSidebarReadyRef, startupTerminalStateRef, status, stopAllDesktopFleetWorkers, stopDesktopFleetWorker, strOrNull, sttBackendChanging, styles, summarizeReferenceContent, summarizeRuntimeStatus, summarizeToolPayload, takeGateFrame, taskBoard, taskBoardArmedNextTurn, taskBoardCollapsed, taskBoardStateRef, taskBoardStatusLabel, taskBoardStepPrefix, telegramBotConfigs, thinking, thinkingShineProgress, timelineEventMergeKey, timelineEvents, toDesktopMessages, toLiveDesktopMessage, toggleToolPackId, token, toolPackInfoButtonRefs, toolPackInfoHideTimerRef, toolPackInfoPopup, toolPackLabel, toolPackMutationInFlight, toolsTriggerRef, transcriptAutoScrollResumeTimerRef, transcriptAutoScrollSuspendedRef, transcriptContentHeightRef, transcriptLastScrollOffsetYRef, transcriptLastSignatureRef, transcriptMessageLayoutRef, transcriptPendingAutoScrollRef, transcriptProgrammaticScrollUntilRef, transcriptViewportHeightRef, ttsBackendChanging, updateAgentConfig, updateAvailable, updateSessionHeadlessEligibility, updateSessionSecurityPermissionMode, updateSessionTelegramBotAssignment, updateSessionToolPacks, uploadAppAttachment, useConfirmation, useDesktopConversationController, useEffect, useRef, useRouter, useState, userFacingError, usingHebrewVoiceEngine, voiceAudioContextRef, voiceAudioSourceRef, voiceCaptureModeRef, voiceChunkChainRef, voiceChunkSampleCountRef, voiceChunkSamplesRef, voiceChunkSequenceRef, voiceComposerBaseInputRef, voiceComposerDraftRef, voiceDraft, voiceEngineChanging, voiceError, voiceGateStateRef, voiceMode, voicePackState, voicePanelHidden, voicePressActiveRef, voiceCaptureNodeRef, voiceReconnectRef, voiceRecording, voiceRecordingRef, voiceRunning, voiceRunningRef, voiceSampleRateRef, voiceStartInFlightRef, voiceState, voiceStatus, voiceStreamRef, voiceWsRef, warmVoiceRuntime, workspaceSortOrder });

  controllerScope.jarvisState = jarvisState;
  controllerScope.killLiveCommand = killLiveCommand;
  controllerScope.contextMenu = contextMenu;
  controllerScope.closeContextMenu = closeContextMenu;
  controllerScope.openChatContextMenu = openChatContextMenu;
  controllerScope.openProjectContextMenu = openProjectContextMenu;
  controllerScope.openMessageContextMenu = openMessageContextMenu;
  controllerScope.openToolContextMenu = openToolContextMenu;
  controllerScope.sessionListLoading = sessionListLoading;
  controllerScopeRef.current = controllerScope;

  const headerIdentityStopActive = Boolean(
    controllerScope.agentRunActive
    || controllerScope.chatRunActive
    || controllerScope.voiceRunning
    || controllerScope.runtimeRunState === 'running'
    || Number(controllerScope.overview?.active_visual_monitors || 0) > 0
    || controllerScope.hasActiveFleetTask
  );
  const headerControls = useMemo<DesktopConversationHeaderControls>(() => ({
    mode: controllerScope.conversationMode || 'chat',
    identityStopActive: headerIdentityStopActive,
    setMode: (mode: ConversationSurfaceMode) => {
      const activeScope = controllerScopeRef.current;
      activeScope?.setConversationMode?.(mode);
      if (mode === 'fleet') {
        void activeScope?.refreshFleetSnapshot?.({ quiet: true });
      }
    },
    stopIdentity: async () => {
      await controllerScopeRef.current?.stopCurrentIdentity?.();
    },
    newChat: async () => {
      await controllerScopeRef.current?.beginNewChat?.();
    },
    openProject: async () => {
      const activeScope = controllerScopeRef.current;
      const projectPath = await activeScope?.promptForProjectFolder?.();
      if (projectPath) await activeScope?.openDraftChat?.(projectPath);
    },
    toggleSidebar: () => {
      const activeScope = controllerScopeRef.current;
      activeScope?.setSidebarExpanded?.((current: boolean) => !current);
    },
  }), [controllerScope.conversationMode, headerIdentityStopActive]);

  useEffect(() => {
    onHeaderControlsChange?.(headerControls);
  }, [headerControls, onHeaderControlsChange]);

  useEffect(() => () => {
    onHeaderControlsChange?.(null);
  }, [onHeaderControlsChange]);

  return <DesktopConversationRender scope={controllerScope} />;
}
