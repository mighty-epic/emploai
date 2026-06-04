import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  Animated,
  Easing,
  Image,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
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
import { describeError, logDiagnostic } from '../../lib/diagnostics';
import { DESKTOP_RECT_BUTTON_RADIUS } from './desktopUiTokens';
import {
  activateSession,
  appendSessionTimelineEvent,
  configureAgent,
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
  updateSessionHeadlessEligibility,
  updateSessionTelegramBotAssignment,
  updateSessionToolPacks,
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
  checkoutDesktopGitBranch,
  getDesktopGitRepoInfo,
  getDesktopPathStatus,
  loadDesktopBootstrap,
  loadDesktopSidebarState,
  pickDesktopFolder,
  saveDesktopSidebarState,
  type DesktopGitRepoState,
  type DesktopPathStatus,
  type DesktopVoicePackState,
  type DesktopRuntimeStatus,
  type DesktopSidebarProjectActivity,
  type DesktopSidebarProjectState,
  type DesktopSidebarSessionState,
  type DesktopSidebarState,
  type DesktopVoiceRuntimeStatus,
} from '@/lib/desktopBridge';
import {
  DESKTOP_COMMAND_PLACEHOLDER,
  DESKTOP_COMMAND_SUGGESTIONS,
  isDesktopSlashCommand,
  runDesktopSlashCommand,
} from '@/desktop/desktopCommands';
import { formatAbsoluteTime, formatRelativeTime } from '@/lib/time';

const VOICE_SEGMENT_MS = 850;
const VOICE_PROCESSOR_BUFFER_SIZE = 4096;
const VOICE_GATE_DBFS = -37.5;
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
const VOICE_ENGINE_NONE = 'none';
const VOICE_ENGINE_ENGLISH = 'english_local';
const VOICE_ENGINE_HEBREW = 'hebrew_local';
// Flip this back to true if always-on voice should submit immediately after gate close.
const ALWAYS_ON_VOICE_AUTO_SEND = false;

type InterruptPolicy = 'none' | 'steer_now' | 'after_tool';
type MessageSourceFormat = 'app_text' | 'app_voice_transcript';
type RealtimeChannel = 'chat' | 'voice';
type VoiceCaptureMode = 'push_to_talk' | 'always_on';
type StartupReadinessState = 'warming' | 'chat_ready' | 'fatal_error';
type ComposerInputOrigin = 'manual' | 'voice' | 'system';
type ActiveCommandPanel =
  | { kind: 'model' }
  | { kind: 'tools' }
  | { kind: 'draftProject' }
  | { kind: 'draftBranch' }
  | { kind: 'session'; sessionId: string }
  | { kind: 'verbose' }
  | { kind: 'command'; command: string; description: string }
  | null;

type DesktopMessage = {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string | null;
  displayLabel?: string | null;
  channel?: 'telegram' | 'app' | 'system' | null;
  sourceFormat?: string | null;
  messageKey?: string;
  pending?: boolean;
  localOnly?: boolean;
  localSessionId?: string | null;
};

type ActivityItem = {
  id: string;
  tone: 'neutral' | 'accent' | 'warn' | 'error';
  text: string;
  timestamp: number;
};

type TimelineEntry =
  | {
      id: string;
      kind: 'message';
      sourceMessageIndex: number;
      timestamp: string | null;
      sortValue: number;
      label: string;
      eyebrow: string;
      body: string;
      tone: 'neutral' | 'accent' | 'warn' | 'error';
    }
  | {
      id: string;
      kind: 'event';
      timestamp: string | null;
      sortValue: number;
      label: string;
      eyebrow: string;
      body: string;
      tone: 'neutral' | 'accent' | 'warn' | 'error';
    };

type TranscriptMessageEntry = {
  fullIndex: number;
  message: DesktopMessage;
};

type PendingSearchJump = {
  sessionId: string;
  messageIndex: number;
  attempt: number;
};

type RealtimeEvent = {
  type: string;
  session_id?: string;
  message?: string;
  payload?: Record<string, any>;
};

type QueuedMessage = {
  text: string;
  sourceFormat: MessageSourceFormat;
  interruptPolicy: InterruptPolicy;
  sessionId?: string;
};

type QueuedComposerMessage = {
  id: string;
  text: string;
  sourceFormat: MessageSourceFormat;
  sessionId: string;
  queuedAt: number;
};

type VoiceGateState = {
  pendingFrames: Float32Array[];
  pendingSampleCount: number;
  prerollFrames: Float32Array[];
  aboveFrames: number;
  belowFrames: number;
  recording: boolean;
  activeFrames: number;
  voicedFrames: number;
};

type Props = {
  apiBaseUrl: string;
  token: string;
  initialSessionId?: string | null;
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
  onOpenSetup?: () => void;
  setupOpen?: boolean;
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

type ToolPackDefinition = {
  id: string;
  label: string;
  description: string;
};

type MonoIconName =
  | 'menu'
  | 'settings'
  | 'compose'
  | 'search'
  | 'info'
  | 'voice'
  | 'history'
  | 'folder_closed'
  | 'folder_open'
  | 'branch'
  | 'chevron_down'
  | 'chevron_up'
  | 'check'
  | 'pin'
  | 'more'
  | 'plus';

const DESKTOP_SIDEBAR_STATE_VERSION = 1;
const DESKTOP_SIDEBAR_ACTIVITY_LIMIT = 8;
const SIDEBAR_DRAFT_CHAT_ID = '__draft__';
const COMPOSER_MIN_LINES = 1;
const COMPOSER_MAX_LINES = 8;
const COMPOSER_LINE_HEIGHT = 22;
const COMPOSER_MIN_HEIGHT = COMPOSER_MIN_LINES * COMPOSER_LINE_HEIGHT;
const COMPOSER_MAX_HEIGHT = COMPOSER_MAX_LINES * COMPOSER_LINE_HEIGHT;
const TOOL_PACK_DEFINITIONS: ToolPackDefinition[] = [
  {
    id: 'interactive_desktop',
    label: 'Interactive Desktop',
    description: 'Vision, OCR, clicking, typing, windows, and browser-extension actions.',
  },
  {
    id: 'browser_isolated',
    label: 'Isolated Browser',
    description: 'Selenium-style browser automation without using the live desktop.',
  },
  {
    id: 'workspace_write',
    label: 'Workspace Write',
    description: 'Editing files and running mutating workspace commands.',
  },
  {
    id: 'workspace_read',
    label: 'Workspace Read',
    description: 'Reading files, searching code, tests, diffs, and safe shell reads.',
  },
  {
    id: 'web_research',
    label: 'Web Research',
    description: 'Search and fetch external documentation or websites.',
  },
  {
    id: 'scheduler',
    label: 'Scheduler',
    description: 'Cron jobs, recurring tasks, run-now, and scheduler inspection.',
  },
  {
    id: 'app_runtime',
    label: 'App Runtime',
    description: 'Session and runtime controls that are safe for this chat.',
  },
];
const DEFAULT_TOOL_PACK_IDS = TOOL_PACK_DEFINITIONS.map((item) => item.id);
const MONO_ICON_GLYPHS: Record<MonoIconName, string> = {
  menu: '≡',
  settings: '⛭',
  compose: '✎',
  search: '⌕',
  info: '',
  voice: '◌',
  history: '◷',
  folder_closed: '',
  folder_open: '',
  branch: '⎇',
  chevron_down: '',
  chevron_up: '',
  check: '✓',
  pin: '⌖',
  more: '⋯',
  plus: '+',
};

function createClientId() {
  return `desktop-${Math.random().toString(36).slice(2, 10)}`;
}

function MonoIcon({
  name,
  style,
}: {
  name: MonoIconName;
  style?: any;
}) {
  const flattened = StyleSheet.flatten(style) || {};
  const color = typeof flattened.color === 'string' ? flattened.color : '#dfe8f5';
  const size = typeof flattened.fontSize === 'number' ? flattened.fontSize : 14;
  if (name === 'voice') {
    return (
      <View style={[flattened, { width: size + 2, height: size + 2, alignItems: 'center', justifyContent: 'center' }]}>
        <View style={{ width: size, height: size, position: 'relative' }}>
          <View
            style={{
              position: 'absolute',
              left: size * 0.31,
              top: size * 0.08,
              width: size * 0.38,
              height: size * 0.48,
              borderWidth: 1.5,
              borderColor: color,
              borderRadius: size * 0.2,
            }}
          />
          <View
            style={{
              position: 'absolute',
              left: size * 0.49,
              top: size * 0.56,
              width: 1.5,
              height: size * 0.16,
              backgroundColor: color,
            }}
          />
          <View
            style={{
              position: 'absolute',
              left: size * 0.24,
              top: size * 0.48,
              width: size * 0.52,
              height: size * 0.26,
              borderWidth: 1.5,
              borderTopWidth: 0,
              borderColor: color,
              borderBottomLeftRadius: size * 0.18,
              borderBottomRightRadius: size * 0.18,
            }}
          />
          <View
            style={{
              position: 'absolute',
              left: size * 0.34,
              top: size * 0.82,
              width: size * 0.32,
              height: 1.5,
              backgroundColor: color,
            }}
          />
        </View>
      </View>
    );
  }
  if (name === 'info') {
    return (
      <View style={[flattened, { width: size + 2, height: size + 2, alignItems: 'center', justifyContent: 'center' }]}>
        <View style={{ width: size, height: size, position: 'relative' }}>
          <View
            style={{
              position: 'absolute',
              left: size * 0.12,
              top: size * 0.12,
              width: size * 0.76,
              height: size * 0.76,
              borderWidth: 1.4,
              borderColor: color,
              borderRadius: size * 0.38,
            }}
          />
          <View
            style={{
              position: 'absolute',
              left: size * 0.45,
              top: size * 0.28,
              width: size * 0.1,
              height: size * 0.1,
              borderRadius: size * 0.05,
              backgroundColor: color,
            }}
          />
          <View
            style={{
              position: 'absolute',
              left: size * 0.46,
              top: size * 0.42,
              width: size * 0.08,
              height: size * 0.22,
              backgroundColor: color,
              borderRadius: 999,
            }}
          />
        </View>
      </View>
    );
  }
  if (name === 'folder_closed' || name === 'folder_open') {
    return (
      <View style={[flattened, { width: size + 2, height: size, alignItems: 'center', justifyContent: 'center' }]}>
        <View style={{ width: size, height: size, position: 'relative' }}>
          <View
            style={{
              position: 'absolute',
              left: size * 0.1,
              top: size * 0.16,
              width: size * 0.28,
              height: size * 0.12,
              borderWidth: 1.5,
              borderBottomWidth: 0,
              borderColor: color,
              borderTopLeftRadius: 2,
              borderTopRightRadius: 2,
            }}
          />
          <View
            style={{
              position: 'absolute',
              left: size * 0.08,
              top: name === 'folder_open' ? size * 0.34 : size * 0.28,
              width: size * 0.82,
              height: size * 0.44,
              borderWidth: 1.5,
              borderColor: color,
              borderRadius: 2,
            }}
          />
          {name === 'folder_open' ? (
            <View
              style={{
                position: 'absolute',
                left: size * 0.14,
                top: size * 0.26,
                width: size * 0.44,
                height: 1.5,
                backgroundColor: color,
                transform: [{ rotate: '-14deg' }],
              }}
            />
          ) : null}
        </View>
      </View>
    );
  }
  if (name === 'chevron_down' || name === 'chevron_up') {
    const isUp = name === 'chevron_up';
    return (
      <View style={[flattened, { width: size, height: size, alignItems: 'center', justifyContent: 'center' }]}>
        <View style={{ width: size, height: size * 0.7, position: 'relative' }}>
          <View
            style={{
              position: 'absolute',
              left: size * 0.19,
              top: size * 0.26,
              width: size * 0.36,
              height: 1.5,
              backgroundColor: color,
              borderRadius: 999,
              transform: [{ rotate: isUp ? '-42deg' : '42deg' }],
            }}
          />
          <View
            style={{
              position: 'absolute',
              right: size * 0.19,
              top: size * 0.26,
              width: size * 0.36,
              height: 1.5,
              backgroundColor: color,
              borderRadius: 999,
              transform: [{ rotate: isUp ? '42deg' : '-42deg' }],
            }}
          />
        </View>
      </View>
    );
  }
  return <Text style={[styles.monoIconBase, style]}>{MONO_ICON_GLYPHS[name]}</Text>;
}

function projectDisplayName(projectPath: string, state?: DesktopSidebarProjectState | null) {
  const customName = String(state?.displayName || '').trim();
  return customName || projectPathBasename(projectPath);
}

function normalizeWorkspacePath(value: string | null | undefined) {
  const trimmed = String(value || '').trim();
  if (!trimmed) {
    return '';
  }
  return trimmed.replace(/\//g, '\\').replace(/\\+$/, '');
}

function isWorkspacePathAllowed(projectPath: string, allowedRoot: string) {
  const normalizedProjectPath = normalizeWorkspacePath(projectPath);
  const normalizedAllowedRoot = normalizeWorkspacePath(allowedRoot);
  if (!normalizedProjectPath) {
    return false;
  }
  if (!normalizedAllowedRoot) {
    return true;
  }
  const candidate = normalizedProjectPath.toLowerCase();
  const root = normalizedAllowedRoot.toLowerCase();
  return candidate === root || candidate.startsWith(`${root}\\`);
}

function shouldKeepSidebarProjectPath(
  projectPath: string,
  options: {
    allowedRoot: string;
    sessionProjectPaths: Set<string>;
    draftProjectPath?: string | null;
  },
) {
  const { allowedRoot, sessionProjectPaths, draftProjectPath } = options;
  const normalized = normalizeWorkspacePath(projectPath);
  if (!normalized) {
    return false;
  }
  if (sessionProjectPaths.has(normalized)) {
    return true;
  }
  if (normalizeWorkspacePath(draftProjectPath) === normalized) {
    return true;
  }
  return isWorkspacePathAllowed(normalized, allowedRoot);
}

function isAbsoluteWindowsPath(projectPath: string) {
  const normalized = normalizeWorkspacePath(projectPath);
  return /^[a-zA-Z]:\\/.test(normalized) || normalized.startsWith('\\\\');
}

function projectPathBasename(projectPath: string) {
  const normalized = normalizeWorkspacePath(projectPath);
  if (!normalized) {
    return 'Project';
  }
  const parts = normalized.split('\\').filter(Boolean);
  return parts[parts.length - 1] || normalized;
}

function projectPathHint(projectPath: string) {
  const normalized = normalizeWorkspacePath(projectPath);
  if (!normalized) {
    return '';
  }
  const parts = normalized.split('\\').filter(Boolean);
  if (parts.length <= 1) {
    return normalized;
  }
  return parts.slice(0, -1).join('\\');
}

function composeVoiceDraftInput(baseInput: string, draftText: string) {
  const draft = String(draftText || '').trim();
  if (!draft) {
    return baseInput;
  }
  const baseWithoutTrailingWhitespace = baseInput.replace(/\s+$/, '');
  if (!baseWithoutTrailingWhitespace) {
    return draft;
  }
  return `${baseWithoutTrailingWhitespace} ${draft}`;
}

function appendVoiceTranscriptSegment(baseInput: string, segmentText: string) {
  const segment = String(segmentText || '').trim();
  const base = String(baseInput || '').trim();
  if (!segment) {
    return base;
  }
  if (!base) {
    return segment;
  }
  if (base === segment || base.endsWith(` ${segment}`)) {
    return base;
  }
  return `${base} ${segment}`;
}

const TIMELINE_BASE64_KEYS = new Set(['image_base64', 'base64', 'image_data', 'data', 'screenshot']);

function truncateTimelinePreview(value: unknown, limit = 220) {
  const text = String(value ?? '').trim();
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, Math.max(0, limit - 3))}...`;
}

function safeTimelineValuePreview(value: unknown, limit = 80) {
  if (Array.isArray(value)) {
    return truncateTimelinePreview(`Array[${value.length}]`, limit);
  }
  if (value && typeof value === 'object') {
    const keys = Object.keys(value as Record<string, unknown>).filter((key) => !TIMELINE_BASE64_KEYS.has(key));
    return truncateTimelinePreview(keys.slice(0, 4).join(', ') || 'object', limit);
  }
  return truncateTimelinePreview(value, limit);
}

function toolArgsPreview(toolArgs: Record<string, any>) {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(toolArgs || {}).slice(0, 4)) {
    const valueString = String(value ?? '');
    if (TIMELINE_BASE64_KEYS.has(key) && valueString.length > 100) {
      continue;
    }
    parts.push(`${key}: ${safeTimelineValuePreview(value, 80)}`);
  }
  return truncateTimelinePreview(parts.join(', '), 240);
}

function toolResultPreview(toolResult: unknown) {
  if (toolResult && typeof toolResult === 'object' && !Array.isArray(toolResult)) {
    const resultRecord = toolResult as Record<string, unknown>;
    if ('error' in resultRecord) {
      return {
        tone: 'error' as const,
        text: `Error: ${truncateTimelinePreview(resultRecord.error, 220)}`,
      };
    }
    const safeKeys = Object.keys(resultRecord).filter((key) => !TIMELINE_BASE64_KEYS.has(key));
    return {
      tone: 'accent' as const,
      text: truncateTimelinePreview(safeKeys.slice(0, 6).join(', ') || 'ok', 220),
    };
  }
  if (typeof toolResult === 'string') {
    const clean = truncateTimelinePreview(toolResult, 220);
    return {
      tone: clean.startsWith('Error') ? ('error' as const) : ('accent' as const),
      text: clean || 'ok',
    };
  }
  return {
    tone: 'accent' as const,
    text: safeTimelineValuePreview(toolResult, 220) || 'ok',
  };
}

function createLocalToolTimelineEvent(payload: Record<string, any>): SessionTimelineEvent | null {
  const toolName = String(payload.tool_name || '').trim();
  if (!toolName) {
    return null;
  }
  const argsPreview = toolArgsPreview((payload.tool_args || {}) as Record<string, any>);
  const resultPreview = toolResultPreview(payload.tool_result);
  const durationMs = Number(payload.duration_ms || 0);
  const callPreview = argsPreview ? `${toolName}(${argsPreview})` : `${toolName}()`;
  return {
    id: '',
    kind: 'tool',
    title: `Tool · ${toolName}`,
    content: `${callPreview}\n-> ${resultPreview.text} (${durationMs.toFixed(0)}ms)`,
    tone: resultPreview.tone,
    timestamp: typeof payload.timestamp === 'string' && payload.timestamp.trim()
      ? payload.timestamp.trim()
      : new Date().toISOString(),
    channel: 'app',
    source_format: 'app_text',
    metadata: payload,
  };
}

function timelineEventFallbackFingerprint(event: SessionTimelineEvent, includeTimestamp = true) {
  return [
    String(event.kind || 'note'),
    String(event.title || 'Event'),
    String(event.content || ''),
    includeTimestamp ? String(event.timestamp || '') : '',
    String(event.tone || 'neutral'),
  ].join('|');
}

function timelineEventMergeKey(event: SessionTimelineEvent) {
  const kind = String(event.kind || '').trim().toLowerCase();
  if (kind === 'tool') {
    return `fp:${timelineEventFallbackFingerprint(event, false)}`;
  }
  const id = String(event.id || '').trim();
  if (id) {
    return `id:${id}`;
  }
  return `fp:${timelineEventFallbackFingerprint(event, true)}`;
}

function normalizeTimelineEvents(events: SessionTimelineEvent[]) {
  const unique: SessionTimelineEvent[] = [];
  const seen = new Set<string>();
  for (const event of events) {
    const key = timelineEventMergeKey(event);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    unique.push(event);
  }
  return unique
    .map((event, index) => ({
      event,
      index,
      timestamp: timelineEventTimestampValue(event),
    }))
    .sort((left, right) => {
      if (left.timestamp != null && right.timestamp != null && left.timestamp !== right.timestamp) {
        return left.timestamp - right.timestamp;
      }
      if (left.timestamp != null && right.timestamp == null) {
        return -1;
      }
      if (left.timestamp == null && right.timestamp != null) {
        return 1;
      }
      return left.index - right.index;
    })
    .map((entry) => entry.event);
}

function mergeTimelineEventState(previous: SessionTimelineEvent[], incoming: SessionTimelineEvent[]) {
  const next = normalizeTimelineEvents(incoming);
  const seen = new Set(next.map((event) => timelineEventMergeKey(event)));
  for (const event of previous) {
    const kind = String(event.kind || '').trim().toLowerCase();
    if (kind !== 'tool' && kind !== 'command') {
      continue;
    }
    const key = timelineEventMergeKey(event);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    next.push(event);
  }
  return normalizeTimelineEvents(next);
}

function createEmptySidebarState(): DesktopSidebarState {
  return {
    version: DESKTOP_SIDEBAR_STATE_VERSION,
    projectOrder: [],
    projects: {},
    sessionMeta: {},
    selectedProjectPath: null,
    lastSelectedProjectPath: null,
  };
}

function coerceSidebarState(value: DesktopSidebarState | null | undefined): DesktopSidebarState {
  return {
    version: DESKTOP_SIDEBAR_STATE_VERSION,
    projectOrder: Array.isArray(value?.projectOrder)
      ? value.projectOrder.map((item) => normalizeWorkspacePath(item)).filter(Boolean)
      : [],
    projects: Object.fromEntries(
      Object.entries(value?.projects || {}).map(([projectPath, projectState]) => {
        const normalized = normalizeWorkspacePath(projectPath);
        const nextState = (projectState || {}) as DesktopSidebarProjectState;
        return [normalized, {
          pinned: Boolean(nextState.pinned),
          collapsed: Boolean(nextState.collapsed),
          displayName: typeof nextState.displayName === 'string' ? nextState.displayName : null,
          hidden: Boolean(nextState.hidden),
          recentActivity: Array.isArray(nextState.recentActivity) ? nextState.recentActivity.slice(0, DESKTOP_SIDEBAR_ACTIVITY_LIMIT) : [],
        }];
      }).filter(([projectPath]) => Boolean(projectPath))
    ),
    sessionMeta: Object.fromEntries(
      Object.entries(value?.sessionMeta || {}).map(([sessionId, sessionState]) => {
        const nextState = (sessionState || {}) as DesktopSidebarSessionState;
        return [sessionId, {
          pinned: Boolean(nextState.pinned),
          order: typeof nextState.order === 'number' ? nextState.order : null,
        }];
      })
    ),
    selectedProjectPath: normalizeWorkspacePath(value?.selectedProjectPath),
    lastSelectedProjectPath: normalizeWorkspacePath(value?.lastSelectedProjectPath),
  };
}

function ensureSidebarProjectEntry(state: DesktopSidebarState, projectPath: string): DesktopSidebarState {
  const normalized = normalizeWorkspacePath(projectPath);
  if (!normalized) {
    return state;
  }
  return {
    ...state,
    projectOrder: state.projectOrder.includes(normalized) ? state.projectOrder : [...state.projectOrder, normalized],
    projects: state.projects[normalized]
      ? state.projects
      : {
          ...state.projects,
          [normalized]: {
            pinned: false,
            collapsed: false,
            recentActivity: [],
          },
        },
  };
}

function ensureSidebarProjectEntries(state: DesktopSidebarState, projectPaths: string[]) {
  return projectPaths.reduce((next, projectPath) => ensureSidebarProjectEntry(next, projectPath), state);
}

function workspaceSortOrder(order: string[], value: string) {
  const index = order.indexOf(value);
  return index >= 0 ? index : Number.MAX_SAFE_INTEGER;
}

function sessionUiOrder(sessionMeta: Record<string, DesktopSidebarSessionState>, sessionId: string) {
  const value = sessionMeta[sessionId]?.order;
  return typeof value === 'number' ? value : Number.MAX_SAFE_INTEGER;
}

function sessionSidebarSortTime(session: SessionSummary) {
  return String(session.created_at || session.updated_at || '');
}

function sessionSidebarSortComparator(
  left: SessionSummary,
  right: SessionSummary,
  sessionMeta: Record<string, DesktopSidebarSessionState>,
) {
  const leftPinned = Boolean(sessionMeta[left.id]?.pinned);
  const rightPinned = Boolean(sessionMeta[right.id]?.pinned);
  if (leftPinned !== rightPinned) {
    return leftPinned ? -1 : 1;
  }
  const leftOrder = sessionUiOrder(sessionMeta, left.id);
  const rightOrder = sessionUiOrder(sessionMeta, right.id);
  if (leftOrder !== rightOrder) {
    return leftOrder - rightOrder;
  }
  const leftTime = sessionSidebarSortTime(left);
  const rightTime = sessionSidebarSortTime(right);
  if (leftTime !== rightTime) {
    return leftTime < rightTime ? 1 : -1;
  }
  return left.name.localeCompare(right.name);
}

function toDesktopMessage(message: SessionMessage): DesktopMessage {
  return {
    role: message.role || 'assistant',
    content: message.content || '',
    timestamp: message.timestamp,
    displayLabel: message.display_label,
    channel: message.channel,
    sourceFormat: message.source_format,
  };
}

function messageIdentitySeed(message: Pick<DesktopMessage, 'role' | 'content' | 'timestamp' | 'channel' | 'displayLabel' | 'sourceFormat'>) {
  return [
    message.role || 'assistant',
    message.timestamp || '',
    message.channel || '',
    message.sourceFormat || '',
    message.displayLabel || '',
    message.content || '',
  ].join('|');
}

function messageIdentitySeedFromSessionMessage(message: SessionMessage) {
  const raw = (message.raw || {}) as Record<string, unknown>;
  const explicitId = String(
    raw.message_id
      || raw.id
      || raw.telegram_message_id
      || raw.app_message_id
      || '',
  ).trim();
  if (explicitId) {
    return `message:${explicitId}`;
  }
  return messageIdentitySeed({
    role: message.role || 'assistant',
    content: message.content || '',
    timestamp: message.timestamp,
    channel: message.channel,
    displayLabel: message.display_label,
    sourceFormat: message.source_format,
  });
}

function toDesktopMessages(messages: SessionMessage[]): DesktopMessage[] {
  const occurrenceCounts = new Map<string, number>();
  return messages.map((message) => {
    const seed = messageIdentitySeedFromSessionMessage(message);
    const occurrence = (occurrenceCounts.get(seed) || 0) + 1;
    occurrenceCounts.set(seed, occurrence);
    return {
      ...toDesktopMessage(message),
      messageKey: `${seed}#${occurrence}`,
    };
  });
}

function toLiveDesktopMessage(message: SessionMessage, existingMessages: DesktopMessage[]) {
  const seed = messageIdentitySeedFromSessionMessage(message);
  const occurrence = existingMessages.reduce((count, current) => {
    const currentSeed = current.messageKey?.replace(/#\d+$/, '') || messageIdentitySeed(current);
    return currentSeed === seed ? count + 1 : count;
  }, 0) + 1;
  return {
    ...toDesktopMessage(message),
    messageKey: `${seed}#${occurrence}`,
  };
}

function labelForMessage(message: DesktopMessage) {
  if (message.displayLabel) return message.displayLabel;
  if (message.role === 'assistant') return 'Assistant';
  if (message.role === 'system') return 'System';
  return 'You';
}

function getCommandSuggestionQuery(value: string) {
  const trimmedStart = value.trimStart();
  if (!trimmedStart.startsWith('/')) {
    return null;
  }

  const commandText = trimmedStart.slice(1);
  if (commandText.includes('\n') || /\s/.test(commandText)) {
    return null;
  }

  return commandText.toLowerCase();
}

function parseComposerSlashCommand(value: string) {
  const trimmed = value.trim();
  if (!trimmed.startsWith('/')) {
    return null;
  }

  const body = trimmed.slice(1);
  const firstSpace = body.search(/\s/);
  const name = (firstSpace >= 0 ? body.slice(0, firstSpace) : body).trim().toLowerCase();
  const rawArgs = firstSpace >= 0 ? body.slice(firstSpace + 1).trim() : '';
  if (!name) {
    return null;
  }
  return { name, rawArgs };
}

function extractReferenceTitle(content: string, fallback: string) {
  const headingMatch = content.match(/(?:^|\n)#{1,3}\s+\**([^*\n]+?)\**(?=\n|$)/);
  if (headingMatch?.[1]) {
    return headingMatch[1].trim();
  }

  const firstUsefulLine = content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => line.length > 0 && !/^[-|`]/.test(line));

  if (!firstUsefulLine) {
    return fallback;
  }

  return firstUsefulLine.length > 72 ? `${firstUsefulLine.slice(0, 69)}...` : firstUsefulLine;
}

function summarizeReferenceContent(content: string) {
  const compact = content
    .replace(/\s+/g, ' ')
    .replace(/[#*_`>-]/g, ' ')
    .trim();

  if (!compact) {
    return 'Detailed reference note';
  }

  return compact.length > 132 ? `${compact.slice(0, 129)}...` : compact;
}

function isReferenceSidebarMessage(message: DesktopMessage, sessionName: string) {
  if (message.role !== 'assistant' || message.pending) {
    return false;
  }

  const content = String(message.content || '').trim();
  if (content.length < 900) {
    return false;
  }

  const sessionLooksLikeReference = /toolset overview|clarification/i.test(sessionName);
  const contentLooksLikeReference = /agent tools explained|tool categories|tool comparison|how to use these tools|toolset/i.test(content);
  const looksStructured = /(?:^|\n)(?:#{1,3}\s+|\d+\.\s+|- |\|)/.test(content) || content.includes('---');

  return looksStructured && (sessionLooksLikeReference || contentLooksLikeReference);
}

function summarizeToolPayload(payload: Record<string, any> | undefined) {
  if (!payload) return 'Tool activity';
  if (typeof payload.formatted === 'string' && payload.formatted.trim()) {
    return payload.formatted.trim();
  }

  const toolName = String(payload.tool_name || 'tool');
  const durationMs = Number(payload.duration_ms || 0);
  let preview = '';
  try {
    preview = JSON.stringify(payload.tool_result ?? {});
  } catch {
    preview = String(payload.tool_result ?? '');
  }
  if (preview.length > 180) {
    preview = `${preview.slice(0, 177)}...`;
  }
  return `${toolName} -> ${preview || 'ok'} (${Math.round(durationMs)}ms)`;
}

function summarizeRuntimeStatus(runtimeStatus?: DesktopRuntimeStatus | null) {
  if (!runtimeStatus) return 'Bootstrapping local runtime';
  const base = runtimeStatus.state || runtimeStatus.mode || 'unknown';
  if (runtimeStatus.degraded) {
    return `${base} · degraded`;
  }
  return base;
}

function taskBoardStatusLabel(status: string | null | undefined) {
  switch (status) {
    case 'completed':
      return 'Completed';
    case 'blocked':
      return 'Blocked';
    case 'interrupted':
      return 'Interrupted';
    case 'paused':
      return 'Paused';
    default:
      return 'Active';
  }
}

function taskBoardStepPrefix(status: string | null | undefined) {
  switch (status) {
    case 'done':
      return '[x]';
    case 'in_progress':
      return '[>]';
    case 'blocked':
      return '[!]';
    default:
      return '[ ]';
  }
}

function resolveTaskBoardState(
  nextBoard: TaskBoard | null | undefined,
  nextSessionId: string | null | undefined,
  currentSessionId: string | undefined,
) {
  if (nextBoard) {
    return nextBoard;
  }
  if (nextSessionId && currentSessionId && nextSessionId !== currentSessionId) {
    return null;
  }
  return null;
}

function normalizeCompletedTaskBoards(boards: TaskBoard[] | null | undefined) {
  return [...(boards || [])].sort((left, right) => {
    const leftTime = Date.parse(left.collapsed_completed_at || left.completed_at || left.updated_at || left.created_at || '') || 0;
    const rightTime = Date.parse(right.collapsed_completed_at || right.completed_at || right.updated_at || right.created_at || '') || 0;
    return rightTime - leftTime;
  });
}

function messageTimestampValue(message: DesktopMessage) {
  if (!message.timestamp) {
    return null;
  }
  const numeric = Date.parse(message.timestamp);
  return Number.isFinite(numeric) ? numeric : null;
}

function timelineEventTimestampValue(event: SessionTimelineEvent) {
  if (!event.timestamp) {
    return null;
  }
  const numeric = Date.parse(event.timestamp);
  return Number.isFinite(numeric) ? numeric : null;
}

function mergeTimelineEntries(messageRows: TranscriptMessageEntry[], timelineEvents: SessionTimelineEvent[]) {
  const messageEntries: TimelineEntry[] = messageRows
    .filter(({ message }) => !message.localOnly)
    .map(({ message, fullIndex }) => ({
      id: message.messageKey || `message-${message.timestamp || 'pending'}-${fullIndex}`,
      kind: 'message',
      sourceMessageIndex: fullIndex,
      timestamp: message.timestamp || null,
      sortValue: messageTimestampValue(message) ?? Number.MAX_SAFE_INTEGER - 1 + fullIndex,
      label: labelForMessage(message),
      eyebrow: message.role === 'assistant' ? 'Assistant' : message.role === 'system' ? 'System' : 'User',
      body: String(message.content || ''),
      tone: message.role === 'assistant' ? 'accent' : message.role === 'system' ? 'neutral' : 'neutral',
    }));

  const eventEntries: TimelineEntry[] = timelineEvents.map((event, index) => ({
    id: event.id || `event-${event.timestamp || 'pending'}-${index}`,
    kind: 'event',
    timestamp: event.timestamp || null,
    sortValue: timelineEventTimestampValue(event) ?? Number.MAX_SAFE_INTEGER + index,
    label: event.title || 'Event',
    eyebrow: event.kind ? event.kind.replace(/_/g, ' ') : 'Event',
    body: String(event.content || ''),
    tone: event.tone || 'neutral',
  }));

  return [...messageEntries, ...eventEntries].sort((left, right) => {
    if (left.sortValue !== right.sortValue) {
      return left.sortValue - right.sortValue;
    }
    if (left.kind !== right.kind) {
      return left.kind === 'message' ? -1 : 1;
    }
    return left.id.localeCompare(right.id);
  });
}

function createVoiceGateState(): VoiceGateState {
  return {
    pendingFrames: [],
    pendingSampleCount: 0,
    prerollFrames: [],
    aboveFrames: 0,
    belowFrames: 0,
    recording: false,
    activeFrames: 0,
    voicedFrames: 0,
  };
}

function bytesToBase64(bytes: Uint8Array) {
  let binary = '';
  for (let index = 0; index < bytes.length; index += 1) {
    binary += String.fromCharCode(bytes[index]);
  }
  return globalThis.btoa(binary);
}

function concatFloat32(chunks: Float32Array[], totalLength?: number) {
  const length = totalLength ?? chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const merged = new Float32Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged;
}

function encodePcm16Wav(samples: Float32Array, sampleRate: number) {
  const dataSize = samples.length * 2;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  let offset = 0;
  const writeString = (value: string) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset, value.charCodeAt(index));
      offset += 1;
    }
  };

  writeString('RIFF');
  view.setUint32(offset, 36 + dataSize, true);
  offset += 4;
  writeString('WAVE');
  writeString('fmt ');
  view.setUint32(offset, 16, true);
  offset += 4;
  view.setUint16(offset, 1, true);
  offset += 2;
  view.setUint16(offset, 1, true);
  offset += 2;
  view.setUint32(offset, sampleRate, true);
  offset += 4;
  view.setUint32(offset, sampleRate * 2, true);
  offset += 4;
  view.setUint16(offset, 2, true);
  offset += 2;
  view.setUint16(offset, 16, true);
  offset += 2;
  writeString('data');
  view.setUint32(offset, dataSize, true);
  offset += 4;

  for (let index = 0; index < samples.length; index += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[index]));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }

  return buffer;
}

function samplesDbfs(samples: Float32Array) {
  if (!samples.length) return -120;
  let sumSquares = 0;
  for (let index = 0; index < samples.length; index += 1) {
    sumSquares += samples[index] * samples[index];
  }
  if (sumSquares <= 0) return -120;
  const rms = Math.sqrt(sumSquares / samples.length);
  return 20 * Math.log10(Math.max(rms, 0.000001));
}

function formatStatusNumber(value: number | null | undefined) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return '-';
  }
  return Math.round(numeric).toLocaleString();
}

function clampUsagePercent(value: number | null | undefined) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 0;
  }
  return Math.max(0, Math.min(100, numeric));
}

function createAudioContext() {
  const AudioContextConstructor = globalThis.AudioContext || (globalThis as any).webkitAudioContext;
  if (!AudioContextConstructor) {
    throw new Error('Web Audio microphone capture is not available in this desktop renderer.');
  }
  return new AudioContextConstructor() as AudioContext;
}

function FoldSection({ title, summary, defaultOpen = false, children }: FoldSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <View style={styles.foldSection}>
      <Pressable style={styles.foldSectionHeader} onPress={() => setOpen((current) => !current)}>
        <View style={styles.foldSectionHeaderCopy}>
          <Text style={styles.foldSectionTitle}>{title}</Text>
          <Text style={styles.foldSectionSummary}>{summary}</Text>
        </View>
        <View style={styles.foldSectionToggle}>
          <Text style={styles.foldSectionToggleText}>{open ? 'Hide' : 'Show'}</Text>
        </View>
      </Pressable>
      {open ? <View style={styles.foldSectionBody}>{children}</View> : null}
    </View>
  );
}

export function DesktopConversationView({
  apiBaseUrl,
  token,
  initialSessionId,
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
  setupOpen = false,
}: Props) {
  const router = useRouter();
  const chatWsRef = useRef<WebSocket | null>(null);
  const voiceWsRef = useRef<WebSocket | null>(null);
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
  const voiceProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const voiceChunkSequenceRef = useRef(0);
  const voiceChunkChainRef = useRef(Promise.resolve());
  const voiceChunkSamplesRef = useRef<Float32Array[]>([]);
  const voiceChunkSampleCountRef = useRef(0);
  const voiceSampleRateRef = useRef(16000);
  const voicePressActiveRef = useRef(false);
  const voiceCaptureModeRef = useRef<VoiceCaptureMode>('push_to_talk');
  const alwaysOnEnabledRef = useRef(false);
  const voiceGateStateRef = useRef<VoiceGateState>(createVoiceGateState());
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
  const draftProjectTriggerRef = useRef<any>(null);
  const draftBranchTriggerRef = useRef<any>(null);
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

  const [sessionId, setSessionId] = useState<string | undefined>(initialSessionId || undefined);
  const [sessionName, setSessionName] = useState('Shared session');
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
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
  const [voiceState, setVoiceState] = useState('connecting');
  const [voiceDraft, setVoiceDraft] = useState('');
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [voiceRunning, setVoiceRunning] = useState(false);
  const [voiceRecording, setVoiceRecording] = useState(false);
  const [voiceMode, setVoiceMode] = useState<VoiceCaptureMode>('push_to_talk');
  const [voiceEngineChanging, setVoiceEngineChanging] = useState(false);
  const [liveVoiceStatus, setLiveVoiceStatus] = useState<DesktopVoiceRuntimeStatus | null>(voiceStatus || null);
  const [alwaysOnEnabled, setAlwaysOnEnabled] = useState(false);
  const [sidebarExpanded, setSidebarExpanded] = useState(false);
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
  const [dragState, setDragState] = useState<SidebarDragState>(null);
  const [hoveredProjectPath, setHoveredProjectPath] = useState<string | null>(null);
  const [openProjectMenuPath, setOpenProjectMenuPath] = useState<string | null>(null);
  const [hoveredSessionId, setHoveredSessionId] = useState<string | null>(null);
  const [openSessionMenuId, setOpenSessionMenuId] = useState<string | null>(null);
  const [sidebarChatTooltip, setSidebarChatTooltip] = useState<SidebarChatTooltipState | null>(null);
  const [pendingDraftBotProjectPath, setPendingDraftBotProjectPath] = useState<string | null>(null);
  const [pendingSessionSwitch, setPendingSessionSwitch] = useState<
    | { mode: 'session'; sessionId: string; jumpMessageIndex?: number | null }
    | { mode: 'draft_send'; projectPath: string; text: string; sourceFormat: MessageSourceFormat }
    | null
  >(null);
  const [pendingSearchJump, setPendingSearchJump] = useState<PendingSearchJump | null>(null);
  const [highlightedMessageIndex, setHighlightedMessageIndex] = useState<number | null>(null);
  const [showControls, setShowControls] = useState(false);
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
  const [hoveredToolPackInfoId, setHoveredToolPackInfoId] = useState<string | null>(null);
  const [pinnedToolPackInfoId, setPinnedToolPackInfoId] = useState<string | null>(null);
  const [toolPackInfoPopup, setToolPackInfoPopup] = useState<ToolPackInfoPopupState | null>(null);
  const [sessionSettingsMutationInFlight, setSessionSettingsMutationInFlight] = useState(false);
  const thinkingShineProgress = useRef(new Animated.Value(0)).current;
  const [voicePanelHidden, setVoicePanelHidden] = useState(false);
  const [dismissedCommandSuggestionInput, setDismissedCommandSuggestionInput] = useState<string | null>(null);
  const [keepRuntimeOnAppClose, setKeepRuntimeOnAppClose] = useState(false);
  const [savingCloseBehavior, setSavingCloseBehavior] = useState(false);
  const [contextUsageHovered, setContextUsageHovered] = useState(false);
  const selectedVoiceEngine = voicePackState?.defaultEngine || liveVoiceStatus?.selected_engine || voiceStatus?.selected_engine || VOICE_ENGINE_NONE;
  const allowedWorkspaceRoot = normalizeWorkspacePath(defaultWorkspace);
  const usingHebrewVoiceEngine = selectedVoiceEngine === VOICE_ENGINE_HEBREW;
  const activeVoiceSegmentMs = usingHebrewVoiceEngine ? HEBREW_VOICE_SEGMENT_MS : VOICE_SEGMENT_MS;
  const activeVoiceGateDbfs = usingHebrewVoiceEngine ? HEBREW_VOICE_GATE_DBFS : VOICE_GATE_DBFS;
  const activeVoiceGateReleaseMs = usingHebrewVoiceEngine ? HEBREW_VOICE_GATE_RELEASE_MS : VOICE_GATE_RELEASE_MS;

  const setProjectMenuRef = (projectPath: string) => (node: any) => {
    if (node) {
      projectMenuRefs.current[projectPath] = node;
      return;
    }
    delete projectMenuRefs.current[projectPath];
  };

  const setProjectMenuTriggerRef = (projectPath: string) => (node: any) => {
    if (node) {
      projectMenuTriggerRefs.current[projectPath] = node;
      return;
    }
    delete projectMenuTriggerRefs.current[projectPath];
  };

  const setSessionRowRef = (targetSessionId: string) => (node: any) => {
    if (node) {
      sessionRowRefs.current[targetSessionId] = node;
      return;
    }
    delete sessionRowRefs.current[targetSessionId];
  };

  const setSessionMenuRef = (targetSessionId: string) => (node: any) => {
    if (node) {
      sessionMenuRefs.current[targetSessionId] = node;
      return;
    }
    delete sessionMenuRefs.current[targetSessionId];
  };

  const setSessionMenuTriggerRef = (targetSessionId: string) => (node: any) => {
    if (node) {
      sessionMenuTriggerRefs.current[targetSessionId] = node;
      return;
    }
    delete sessionMenuTriggerRefs.current[targetSessionId];
  };

  const setToolPackInfoButtonRef = (packId: string) => (node: any) => {
    if (node) {
      toolPackInfoButtonRefs.current[packId] = node;
      return;
    }
    delete toolPackInfoButtonRefs.current[packId];
  };
  const activeVoiceGatePrerollMs = usingHebrewVoiceEngine ? HEBREW_VOICE_GATE_PREROLL_MS : VOICE_GATE_PREROLL_MS;
  const activeVoiceGateMaxMs = usingHebrewVoiceEngine ? HEBREW_VOICE_GATE_MAX_MS : VOICE_GATE_MAX_MS;

  const clearSidebarChatTooltipTimer = () => {
    if (sidebarChatTooltipTimerRef.current) {
      clearTimeout(sidebarChatTooltipTimerRef.current);
      sidebarChatTooltipTimerRef.current = null;
    }
  };

  const hideSidebarChatTooltip = (targetSessionId?: string | null) => {
    setSidebarChatTooltip((current) => {
      if (!current) {
        return null;
      }
      if (targetSessionId && current.sessionId !== targetSessionId) {
        return current;
      }
      return null;
    });
  };

  const clearToolPackInfoHideTimer = () => {
    if (toolPackInfoHideTimerRef.current) {
      clearTimeout(toolPackInfoHideTimerRef.current);
      toolPackInfoHideTimerRef.current = null;
    }
  };

  const hideToolPackInfoPopup = (targetPackId?: string | null) => {
    clearToolPackInfoHideTimer();
    setToolPackInfoPopup((current) => {
      if (!current) {
        return null;
      }
      if (targetPackId && current.packId !== targetPackId) {
        return current;
      }
      return null;
    });
    setHoveredToolPackInfoId((current) => (
      !targetPackId || current === targetPackId ? null : current
    ));
    setPinnedToolPackInfoId((current) => (
      !targetPackId || current === targetPackId ? null : current
    ));
  };

  const showToolPackInfoPopup = (packId: string, options?: { pinned?: boolean }) => {
    clearToolPackInfoHideTimer();
    if (options?.pinned) {
      setPinnedToolPackInfoId(packId);
    } else {
      setHoveredToolPackInfoId(packId);
    }
    if (Platform.OS !== 'web') {
      setToolPackInfoPopup({
        packId,
        top: 0,
        left: 0,
      });
      return;
    }
    const buttonNode = toolPackInfoButtonRefs.current[packId];
    const layerNode = floatingPanelRef.current;
    if (
      !buttonNode
      || !layerNode
      || typeof buttonNode.getBoundingClientRect !== 'function'
      || typeof layerNode.getBoundingClientRect !== 'function'
    ) {
      setToolPackInfoPopup({
        packId,
        top: 0,
        left: 0,
      });
      return;
    }
    const buttonRect = buttonNode.getBoundingClientRect();
    const layerRect = layerNode.getBoundingClientRect();
    const bubbleWidth = 292;
    const bubbleHeight = 136;
    const leftPreferred = buttonRect.left - layerRect.left - bubbleWidth - 12;
    const leftFallback = buttonRect.right - layerRect.left + 12;
    const nextLeft = leftPreferred >= 12
      ? leftPreferred
      : Math.max(12, Math.min(layerRect.width - bubbleWidth - 12, leftFallback));
    const unclampedTop = buttonRect.top - layerRect.top + buttonRect.height / 2 - bubbleHeight / 2;
    const nextTop = Math.max(12, Math.min(layerRect.height - bubbleHeight - 12, unclampedTop));
    setToolPackInfoPopup({
      packId,
      top: nextTop,
      left: nextLeft,
    });
  };

  const scheduleHideToolPackInfoPopup = (packId: string) => {
    clearToolPackInfoHideTimer();
    toolPackInfoHideTimerRef.current = setTimeout(() => {
      setHoveredToolPackInfoId((current) => (current === packId ? null : current));
      setToolPackInfoPopup((current) => {
        if (!current || current.packId !== packId || pinnedToolPackInfoId === packId) {
          return current;
        }
        return null;
      });
    }, 120);
  };

  const showSidebarChatTooltip = (targetSession: SessionSummary, projectPath: string) => {
    if (Platform.OS !== 'web') {
      return;
    }
    const rowNode = sessionRowRefs.current[targetSession.id];
    const shellNode = shellRef.current;
    if (
      !rowNode
      || !shellNode
      || typeof rowNode.getBoundingClientRect !== 'function'
      || typeof shellNode.getBoundingClientRect !== 'function'
    ) {
      return;
    }
    const rowRect = rowNode.getBoundingClientRect();
    const shellRect = shellNode.getBoundingClientRect();
    const tooltipWidth = 296;
    const tooltipHeight = 86;
    const nextLeft = Math.max(14, rowRect.left - shellRect.left - tooltipWidth - 16);
    const unclampedTop = rowRect.top - shellRect.top + rowRect.height / 2 - tooltipHeight / 2;
    const nextTop = Math.max(14, Math.min(shellRect.height - tooltipHeight - 14, unclampedTop));
    setSidebarChatTooltip({
      sessionId: targetSession.id,
      title: targetSession.name,
      projectPath,
      botLabel: telegramBotLabelForSession(targetSession),
      top: nextTop,
      left: nextLeft,
    });
  };

  const scheduleSidebarChatTooltip = (targetSession: SessionSummary, projectPath: string) => {
    if (Platform.OS !== 'web') {
      return;
    }
    clearSidebarChatTooltipTimer();
    sidebarChatTooltipTimerRef.current = setTimeout(() => {
      showSidebarChatTooltip(targetSession, projectPath);
    }, 2000);
  };

  useEffect(() => {
    setInterruptPolicy(normalizeInterruptPolicyValue(defaultInterruptPolicy));
  }, [defaultInterruptPolicy]);

  useEffect(() => (
    () => {
      clearSidebarChatTooltipTimer();
      clearToolPackInfoHideTimer();
    }
  ), []);

  useEffect(() => {
    if (sidebarExpanded) {
      return;
    }
    clearSidebarChatTooltipTimer();
    hideSidebarChatTooltip();
  }, [sidebarExpanded]);

  useEffect(() => {
    if (activeCommandPanel?.kind === 'tools') {
      return;
    }
    hideToolPackInfoPopup();
  }, [activeCommandPanel]);

  useEffect(() => {
    if (draftChat || (activeCommandPanel?.kind !== 'draftBranch' && activeCommandPanel?.kind !== 'draftProject')) {
      return;
    }
    setActiveCommandPanel(null);
  }, [draftChat, activeCommandPanel]);

  useEffect(() => {
    if (activeCommandPanel?.kind !== 'draftProject') {
      setDraftProjectSearch('');
    }
    if (activeCommandPanel?.kind !== 'draftBranch') {
      setDraftBranchSearch('');
    }
  }, [activeCommandPanel]);

  const lastMessage = messages.length > 0 ? messages[messages.length - 1] : null;
  const lastMessageSignature = lastMessage
    ? [
        lastMessage.role,
        lastMessage.channel || '',
        lastMessage.timestamp || '',
        lastMessage.content.slice(-120),
      ].join('|')
    : 'none';
  const transcriptSignature = [
    sessionId || 'none',
    String(messages.length),
    lastMessageSignature,
    assistantDraft,
  ].join('|');

  useEffect(() => {
    chatRunActiveRef.current = chatRunActive;
  }, [chatRunActive]);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    draftChatRef.current = draftChat;
  }, [draftChat]);

  useEffect(() => {
    if (!draftChat?.projectPath) {
      setDraftGitRepoState(null);
      setDraftGitRepoLoading(false);
      return;
    }
    let disposed = false;
    setDraftGitRepoLoading(true);
    void getDesktopGitRepoInfo(draftChat.projectPath).then((nextState) => {
      if (disposed) {
        return;
      }
      setDraftGitRepoState(nextState);
      setDraftGitRepoLoading(false);
      if (!nextState?.isGitRepo) {
        setDraftChat((current) => (
          current?.projectPath === draftChat.projectPath && current.selectedBranch
            ? {
                ...current,
                selectedBranch: null,
              }
            : current
        ));
        return;
      }
      const currentBranch = String(nextState.currentBranch || '').trim() || null;
      const branches = Array.isArray(nextState.branches) ? nextState.branches : [];
      setDraftChat((current) => {
        if (!current || current.projectPath !== draftChat.projectPath) {
          return current;
        }
        if (current.selectedBranch && branches.includes(current.selectedBranch)) {
          return current;
        }
        return {
          ...current,
          selectedBranch: currentBranch,
        };
      });
    }).catch(() => {
      if (!disposed) {
        setDraftGitRepoState(null);
        setDraftGitRepoLoading(false);
      }
    });
    return () => {
      disposed = true;
    };
  }, [draftChat?.projectPath]);

  useEffect(() => {
    if (configuredModelGroups.length) {
      setCachedModelGroups(configuredModelGroups);
    }
  }, [configuredModelGroups]);

  useEffect(() => {
    if (configuredPlannerModels.length) {
      setCachedPlannerModels(configuredPlannerModels);
    }
  }, [configuredPlannerModels]);

  useEffect(() => {
    if (overview?.model_groups?.length) {
      setCachedModelGroups(overview.model_groups);
    }
    if (overview?.available_planner_models?.length) {
      setCachedPlannerModels(overview.available_planner_models);
    }
  }, [overview]);

  useEffect(() => {
    let disposed = false;
    void loadDesktopSidebarState().then((stored) => {
      if (disposed) {
        return;
      }
      setSidebarState(coerceSidebarState(stored));
      setSidebarStateReady(true);
    }).catch(() => {
      if (!disposed) {
        setSidebarState(createEmptySidebarState());
        setSidebarStateReady(true);
      }
    });

    return () => {
      disposed = true;
    };
  }, []);

  useEffect(() => {
    if (!sidebarStateReady) {
      return;
    }
    void saveDesktopSidebarState(sidebarState).catch(() => {});
  }, [sidebarState, sidebarStateReady]);

  useEffect(() => {
    let disposed = false;
    const sessionProjectPaths = new Set(
      sessions
        .map((item) => normalizeWorkspacePath(item.workspace))
        .filter(Boolean),
    );
    const projectPaths = Array.from(new Set([
      ...sidebarState.projectOrder.map((item) => normalizeWorkspacePath(item)),
      ...Object.keys(sidebarState.projects).map((item) => normalizeWorkspacePath(item)),
      ...sessions.map((item) => normalizeWorkspacePath(item.workspace)),
      ...(draftChat ? [draftChat.projectPath] : []),
    ].filter(Boolean))).filter((projectPath) => shouldKeepSidebarProjectPath(projectPath, {
      allowedRoot: allowedWorkspaceRoot,
      sessionProjectPaths,
      draftProjectPath: draftChat?.projectPath,
    }));
    if (!projectPaths.length) {
      setProjectPathStatuses({});
      return () => {
        disposed = true;
      };
    }
    void Promise.all(projectPaths.map(async (projectPath) => [projectPath, await getDesktopPathStatus(projectPath)] as const))
      .then((entries) => {
        if (disposed) {
          return;
        }
        setProjectPathStatuses((current) => {
          const next: Record<string, DesktopPathStatus> = {};
          for (const [projectPath, status] of entries) {
            if (projectPath && status) {
              next[projectPath] = status;
            } else if (projectPath && current[projectPath]) {
              next[projectPath] = current[projectPath];
            }
          }
          return next;
        });
      })
      .catch(() => {
        if (!disposed) {
          setProjectPathStatuses((current) => current);
        }
      });

    return () => {
      disposed = true;
    };
  }, [allowedWorkspaceRoot, draftChat, sessions, sidebarState.projectOrder, sidebarState.projects]);

  useEffect(() => (
    () => {
      if (searchJumpTimerRef.current) {
        clearTimeout(searchJumpTimerRef.current);
        searchJumpTimerRef.current = null;
      }
      if (searchHighlightTimerRef.current) {
        clearTimeout(searchHighlightTimerRef.current);
        searchHighlightTimerRef.current = null;
      }
    }
  ), []);

  useEffect(() => {
    if (!sidebarSearchModalOpen) {
      return;
    }
    const timerId = setTimeout(() => {
      sidebarSearchInputRef.current?.focus();
    }, 20);
    return () => clearTimeout(timerId);
  }, [sidebarSearchModalOpen]);

  useEffect(() => {
    const normalizedQuery = sidebarSearch.trim();
    if (!sidebarSearchModalOpen || !normalizedQuery) {
      sidebarSearchRequestIdRef.current += 1;
      setSidebarSearchLoading(false);
      setSidebarSearchError(null);
      setSidebarSearchResults([]);
      return;
    }

    const requestId = ++sidebarSearchRequestIdRef.current;
    const timerId = setTimeout(() => {
      setSidebarSearchLoading(true);
      setSidebarSearchError(null);
      void searchSessions(apiBaseUrl, token, normalizedQuery, 40)
        .then((response) => {
          if (sidebarSearchRequestIdRef.current !== requestId) {
            return;
          }
          setSidebarSearchResults(response.results || []);
          setSidebarSearchLoading(false);
        })
        .catch((error) => {
          if (sidebarSearchRequestIdRef.current !== requestId) {
            return;
          }
          setSidebarSearchResults([]);
          setSidebarSearchLoading(false);
          setSidebarSearchError(describeError(error));
        });
    }, 220);

    return () => clearTimeout(timerId);
  }, [apiBaseUrl, sidebarSearch, sidebarSearchModalOpen, token]);

  const emitStartupState = (state: StartupReadinessState, detail?: string) => {
    if (!onStartupStateChange) {
      return;
    }
    if (startupTerminalStateRef.current && state !== 'warming') {
      return;
    }
    if (state === 'chat_ready' || state === 'fatal_error') {
      startupTerminalStateRef.current = state;
    }
    onStartupStateChange(state, detail);
  };

  const maybeResolveStartupReady = () => {
    if (startupTerminalStateRef.current) {
      return;
    }
    if (
      startupSidebarReadyRef.current
      && startupSessionStateReadyRef.current
      && startupChatSocketReadyRef.current
    ) {
      emitStartupState('chat_ready');
    }
  };

  useEffect(() => {
    voiceCaptureModeRef.current = voiceMode;
  }, [voiceMode]);

  useEffect(() => {
    alwaysOnEnabledRef.current = alwaysOnEnabled;
  }, [alwaysOnEnabled]);

  useEffect(() => {
    if (!pendingSearchJump || pendingSearchJump.sessionId !== sessionId) {
      return;
    }

    if (searchJumpTimerRef.current) {
      clearTimeout(searchJumpTimerRef.current);
      searchJumpTimerRef.current = null;
    }

    const targetInHistory = messages.some((message, index) => (
      index === pendingSearchJump.messageIndex && isReferenceSidebarMessage(message, sessionName)
    ));
    if (targetInHistory && !showReferenceRail) {
      setSidebarExpanded(true);
      setShowReferenceRail(true);
      return;
    }

    const targetY = targetInHistory
      ? historyMessageLayoutRef.current[pendingSearchJump.messageIndex]
      : transcriptMessageLayoutRef.current[pendingSearchJump.messageIndex];

    if (typeof targetY === 'number') {
      if (targetInHistory) {
        historyScrollRef.current?.scrollTo({
          y: Math.max(0, targetY - 20),
          animated: true,
        });
      } else {
        transcriptProgrammaticScrollUntilRef.current = Date.now() + 800;
        scrollRef.current?.scrollTo({
          y: Math.max(0, targetY - 24),
          animated: true,
        });
      }

      setHighlightedMessageIndex(pendingSearchJump.messageIndex);
      if (searchHighlightTimerRef.current) {
        clearTimeout(searchHighlightTimerRef.current);
      }
      searchHighlightTimerRef.current = setTimeout(() => {
        setHighlightedMessageIndex((current) => (
          current === pendingSearchJump.messageIndex ? null : current
        ));
      }, 3200);
      setPendingSearchJump(null);
      return;
    }

    if (pendingSearchJump.attempt >= 18) {
      setPendingSearchJump(null);
      return;
    }

    searchJumpTimerRef.current = setTimeout(() => {
      setPendingSearchJump((current) => {
        if (!current || current.sessionId !== pendingSearchJump.sessionId || current.messageIndex !== pendingSearchJump.messageIndex) {
          return current;
        }
        return {
          ...current,
          attempt: current.attempt + 1,
        };
      });
    }, 80);

    return () => {
      if (searchJumpTimerRef.current) {
        clearTimeout(searchJumpTimerRef.current);
        searchJumpTimerRef.current = null;
      }
    };
  }, [messages, pendingSearchJump, sessionId, sessionName, showReferenceRail]);

  useEffect(() => {
    if (!taskBoard) {
      taskBoardStateRef.current = { taskId: null, status: null };
      return;
    }

    const previous = taskBoardStateRef.current;
    const nextTaskId = taskBoard.task_id || null;
    const nextStatus = taskBoard.status || null;
    const isNewTask = previous.taskId !== nextTaskId;
    const becameCompleted = previous.status !== nextStatus && nextStatus === 'completed';

    if (isNewTask || becameCompleted || taskBoard.pending_reassessment_reason) {
      setTaskBoardCollapsed(false);
    }

    taskBoardStateRef.current = { taskId: nextTaskId, status: nextStatus };
  }, [taskBoard]);

  useEffect(() => {
    setExpandedCompletedTaskIds((previous) => {
      const allowedIds = new Set(completedTaskBoards.map((board) => board.task_id));
      const next: Record<string, boolean> = {};
      for (const [taskId, isExpanded] of Object.entries(previous)) {
        if (allowedIds.has(taskId)) {
          next[taskId] = isExpanded;
        }
      }
      return next;
    });
  }, [completedTaskBoards]);

  useEffect(() => {
    voiceRunningRef.current = voiceRunning;
  }, [voiceRunning]);

  useEffect(() => {
    voiceRecordingRef.current = voiceRecording;
  }, [voiceRecording]);

  const clearAssistantDeltaFlushTimer = () => {
    if (assistantDeltaFlushTimerRef.current) {
      clearTimeout(assistantDeltaFlushTimerRef.current);
      assistantDeltaFlushTimerRef.current = null;
    }
  };

  const flushAssistantDeltaBuffer = () => {
    clearAssistantDeltaFlushTimer();
    if (!assistantDeltaBufferRef.current) {
      return;
    }
    const delta = assistantDeltaBufferRef.current;
    assistantDeltaBufferRef.current = '';
    setAssistantDraft((previous) => previous + delta);
  };

  const clearTranscriptAutoScrollResumeTimer = () => {
    if (transcriptAutoScrollResumeTimerRef.current) {
      clearTimeout(transcriptAutoScrollResumeTimerRef.current);
      transcriptAutoScrollResumeTimerRef.current = null;
    }
  };

  const scrollTranscriptToEnd = (animated = true) => {
    transcriptProgrammaticScrollUntilRef.current = Date.now() + 300;
    scrollRef.current?.scrollToEnd({ animated });
  };

  const scheduleTranscriptAutoScrollResume = () => {
    clearTranscriptAutoScrollResumeTimer();
    transcriptAutoScrollResumeTimerRef.current = setTimeout(() => {
      transcriptAutoScrollSuspendedRef.current = false;
      transcriptAutoScrollResumeTimerRef.current = null;
      if (transcriptPendingAutoScrollRef.current) {
        transcriptPendingAutoScrollRef.current = false;
        scrollTranscriptToEnd(true);
      }
    }, TRANSCRIPT_AUTO_SCROLL_IDLE_MS);
  };

  const resetTranscriptAutoScrollState = () => {
    transcriptAutoScrollSuspendedRef.current = false;
    transcriptPendingAutoScrollRef.current = false;
    transcriptLastScrollOffsetYRef.current = 0;
    clearTranscriptAutoScrollResumeTimer();
  };

  useEffect(() => () => {
    clearTranscriptAutoScrollResumeTimer();
    clearAssistantDeltaFlushTimer();
  }, []);

  useEffect(() => {
    if (transcriptSignature === transcriptLastSignatureRef.current) {
      return;
    }

    transcriptLastSignatureRef.current = transcriptSignature;
    if (transcriptAutoScrollSuspendedRef.current) {
      transcriptPendingAutoScrollRef.current = true;
      return;
    }

    transcriptPendingAutoScrollRef.current = false;
    const timer = setTimeout(() => {
      scrollTranscriptToEnd(true);
    }, 0);
    return () => clearTimeout(timer);
  }, [transcriptSignature]);

  useEffect(() => {
    if ((voiceDraft || voiceError || voiceRecording) && !voicePanelHidden) {
      setShowVoicePanel(true);
    }
  }, [voiceDraft, voiceError, voiceRecording, voicePanelHidden]);

  const openVoicePanel = () => {
    setVoicePanelHidden(false);
    setSidebarExpanded(true);
    setShowVoicePanel(true);
  };

  const hideVoicePanel = () => {
    setVoicePanelHidden(true);
    setShowVoicePanel(false);
  };

  const pushActivity = (text: string, tone: ActivityItem['tone'] = 'neutral') => {
    const normalized = text.trim();
    if (!normalized) return;
    setActivity((previous) => [
      {
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        text: normalized,
        tone,
        timestamp: Date.now(),
      },
      ...previous,
    ].slice(0, MAX_ACTIVITY_ITEMS));
  };

  const updateSidebarState = (
    updater: (current: DesktopSidebarState) => DesktopSidebarState,
  ) => {
    setSidebarState((current) => coerceSidebarState(updater(coerceSidebarState(current))));
  };

  const selectProjectPath = (projectPath: string | null | undefined) => {
    const normalized = normalizeWorkspacePath(projectPath);
    updateSidebarState((current) => {
      if (!normalized) {
        return {
          ...current,
          selectedProjectPath: null,
        };
      }
      const ensured = ensureSidebarProjectEntry(current, normalized);
      return {
        ...ensured,
        selectedProjectPath: normalized,
        lastSelectedProjectPath: normalized,
      };
    });
  };

  const revealProjectInSidebar = (projectPath: string | null | undefined) => {
    const normalized = normalizeWorkspacePath(projectPath);
    if (!normalized) {
      return;
    }
    updateSidebarState((current) => {
      const ensured = ensureSidebarProjectEntry(current, normalized);
      const existing = ensured.projects[normalized] || {};
      return {
        ...ensured,
        selectedProjectPath: normalized,
        lastSelectedProjectPath: normalized,
        projects: {
          ...ensured.projects,
          [normalized]: {
            ...existing,
            collapsed: false,
            hidden: false,
          },
        },
      };
    });
    setSidebarExpanded(true);
  };

  const openSidebarSearchModal = () => {
    setSidebarSearchModalOpen(true);
  };

  const clearSidebarSearch = () => {
    sidebarSearchRequestIdRef.current += 1;
    setSidebarSearch('');
    setSidebarSearchLoading(false);
    setSidebarSearchError(null);
    setSidebarSearchResults([]);
  };

  const closeSidebarSearchModal = () => {
    setSidebarSearchModalOpen(false);
    clearSidebarSearch();
  };

  const discardDraftChat = (options?: { clearInput?: boolean }) => {
    draftChatRef.current = null;
    setDraftChat(null);
    if (options?.clearInput) {
      setComposerInputValue('');
    }
  };

  const pushProjectActivity = (sourceProjectPath: string, destinationProjectPath: string, movedSession: SessionSummary) => {
    const sourcePath = normalizeWorkspacePath(sourceProjectPath);
    const destinationPath = normalizeWorkspacePath(destinationProjectPath);
    if (!sourcePath || !destinationPath || sourcePath === destinationPath) {
      return;
    }

    const timestamp = new Date().toISOString();
    const sourceLabel = projectPathBasename(sourcePath);
    const destinationLabel = projectPathBasename(destinationPath);
    updateSidebarState((current) => {
      let next = ensureSidebarProjectEntries(current, [sourcePath, destinationPath]);
      const appendActivity = (projectPath: string, message: string, relatedProjectPath: string) => {
        const existing = next.projects[projectPath] || {};
        const recentActivity = [
          {
            id: `${movedSession.id}:${timestamp}:${projectPath}`,
            message,
            timestamp,
            sessionId: movedSession.id,
            relatedProjectPath,
          },
          ...(existing.recentActivity || []),
        ].slice(0, DESKTOP_SIDEBAR_ACTIVITY_LIMIT);
        next = {
          ...next,
          projects: {
            ...next.projects,
            [projectPath]: {
              ...existing,
              recentActivity,
            },
          },
        };
      };

      appendActivity(sourcePath, `${movedSession.name} moved to ${destinationLabel}`, destinationPath);
      appendActivity(destinationPath, `${movedSession.name} moved here from ${sourceLabel}`, sourcePath);
      return next;
    });
  };

  const reconcileSidebarProjects = (
    nextSessions: SessionSummary[],
    options?: {
      preferredSelectedProjectPath?: string | null;
      activeSessionWorkspace?: string | null;
    },
  ) => {
    const nextWorkspaceBySession: Record<string, string> = {};
    const projectPaths = new Set<string>();
    for (const item of nextSessions) {
      const workspace = normalizeWorkspacePath(item.workspace);
      if (!workspace) {
        continue;
      }
      nextWorkspaceBySession[item.id] = workspace;
      projectPaths.add(workspace);
      const previousWorkspace = currentWorkspaceBySessionRef.current[item.id];
      if (previousWorkspace && previousWorkspace !== workspace) {
        pushProjectActivity(previousWorkspace, workspace, item);
      }
    }
    currentWorkspaceBySessionRef.current = nextWorkspaceBySession;

    const preferredSelected = normalizeWorkspacePath(
      options?.preferredSelectedProjectPath
      || options?.activeSessionWorkspace
      || draftChatRef.current?.projectPath
      || '',
    );

    updateSidebarState((current) => {
      let next = ensureSidebarProjectEntries(current, Array.from(projectPaths));
      const fallbackSelection = normalizeWorkspacePath(
        preferredSelected
        || current.selectedProjectPath
        || current.lastSelectedProjectPath
        || Array.from(projectPaths)[0]
        || '',
      );
      next = {
        ...next,
        selectedProjectPath: fallbackSelection || null,
        lastSelectedProjectPath: fallbackSelection || current.lastSelectedProjectPath || null,
      };
      return next;
    });
  };

  const mergeLocalMessages = (
    syncedMessages: DesktopMessage[],
    previousMessages: DesktopMessage[],
    nextSessionId: string,
  ) => {
    const localMessages = previousMessages.filter((message) => (
      message.localOnly && message.localSessionId === nextSessionId
    ));
    return [...syncedMessages, ...localMessages]
      .map((message, index) => ({
        message,
        index,
        timestamp: messageTimestampValue(message),
      }))
      .sort((left, right) => {
        if (left.timestamp != null && right.timestamp != null && left.timestamp !== right.timestamp) {
          return left.timestamp - right.timestamp;
        }
        if (left.timestamp != null && right.timestamp == null) {
          return -1;
        }
        if (left.timestamp == null && right.timestamp != null) {
          return 1;
        }
        return left.index - right.index;
      })
      .map((entry) => entry.message);
  };

  const applySessionDetail = (detail: SessionDetail) => {
    const switchingSessions = detail.id !== sessionIdRef.current;
    const nextEnabledToolPacks = Array.isArray(detail.enabled_tool_packs) ? detail.enabled_tool_packs : [];
    const nextAvailableToolPacks = Array.isArray(detail.available_tool_packs) ? detail.available_tool_packs : [];
    const nextLockStatus = detail.lock_status || {};
    if (switchingSessions) {
      resetTranscriptAutoScrollState();
      setTaskBoardCollapsed(false);
      setExpandedCompletedTaskIds({});
      transcriptMessageLayoutRef.current = {};
      historyMessageLayoutRef.current = {};
      setArtifacts([]);
      setSelectedArtifactId(null);
      setSelectedArtifactDetail(null);
      setArtifactError(null);
    }
    setSessionId(detail.id);
    setSessionName(detail.name);
    setTaskBoard(resolveTaskBoardState(detail.task_board, detail.id, sessionIdRef.current));
    setCompletedTaskBoards(normalizeCompletedTaskBoards(detail.completed_task_boards));
    setTaskBoardArmedNextTurnState(Boolean(detail.task_board_armed_next_turn));
    setTimelineEvents((previous) => (
      switchingSessions
        ? normalizeTimelineEvents(detail.timeline_events || [])
        : mergeTimelineEventState(previous, detail.timeline_events || [])
    ));
    const syncedMessages = toDesktopMessages(detail.messages || []);
    setMessages((previous) => mergeLocalMessages(syncedMessages, previous, detail.id));
    setSessions((previous) => previous.map((item) => (
      item.id === detail.id
        ? {
            ...item,
            name: detail.name,
            updated_at: detail.updated_at,
            model: detail.model,
            workspace: detail.workspace,
            enabled_tool_packs: nextEnabledToolPacks,
            available_tool_packs: nextAvailableToolPacks,
            lock_status: nextLockStatus,
            telegram_bot_config_id: detail.telegram_bot_config_id ?? item.telegram_bot_config_id ?? null,
            headless_eligible: Boolean(detail.headless_eligible),
            artifact_count: Number(detail.artifact_count || 0),
            latest_artifact_at: detail.latest_artifact_at ?? item.latest_artifact_at ?? null,
            is_running: Boolean(detail.is_running),
            run_state: detail.run_state || item.run_state,
          }
        : item
    )));
    setOverview((previous) => {
      if (!previous || previous.session_id !== detail.id) {
        return previous;
      }
      return {
        ...previous,
        run_state: detail.run_state || previous.run_state,
        enabled_tool_packs: nextEnabledToolPacks,
        available_tool_packs: nextAvailableToolPacks,
        lock_status: nextLockStatus,
      };
    });
    discardDraftChat();
    selectProjectPath(detail.workspace);
  };

  const appendTimelineEvent = (event: SessionTimelineEvent) => {
    if (!event) {
      return;
    }
    setTimelineEvents((previous) => {
      const existingIndex = previous.findIndex((item) => timelineEventMergeKey(item) === timelineEventMergeKey(event));
      if (existingIndex < 0) {
        return normalizeTimelineEvents([...previous, event]);
      }
      const next = previous.slice();
      next[existingIndex] = event;
      return normalizeTimelineEvents(next);
    });
  };

  const handleTranscriptScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    const nativeEvent = event.nativeEvent;
    const nextOffsetY = Math.max(0, nativeEvent.contentOffset?.y ?? 0);
    const previousOffsetY = transcriptLastScrollOffsetYRef.current;
    transcriptLastScrollOffsetYRef.current = nextOffsetY;
    transcriptContentHeightRef.current = nativeEvent.contentSize?.height ?? transcriptContentHeightRef.current;
    transcriptViewportHeightRef.current = nativeEvent.layoutMeasurement?.height ?? transcriptViewportHeightRef.current;

    if (Date.now() < transcriptProgrammaticScrollUntilRef.current) {
      return;
    }

    const deltaY = nextOffsetY - previousOffsetY;
    if (Math.abs(deltaY) < TRANSCRIPT_SCROLL_MOVE_THRESHOLD) {
      return;
    }

    const distanceFromBottom = Math.max(
      0,
      transcriptContentHeightRef.current - (nextOffsetY + transcriptViewportHeightRef.current),
    );

    if (deltaY < -TRANSCRIPT_SCROLL_UP_THRESHOLD) {
      transcriptAutoScrollSuspendedRef.current = true;
      transcriptPendingAutoScrollRef.current = distanceFromBottom > 24;
      scheduleTranscriptAutoScrollResume();
      return;
    }

    if (transcriptAutoScrollSuspendedRef.current) {
      transcriptPendingAutoScrollRef.current = transcriptPendingAutoScrollRef.current || distanceFromBottom > 24;
      scheduleTranscriptAutoScrollResume();
    }
  };

  const applySessionSync = (payload: Record<string, any>) => {
    const detail = payload.session as SessionDetail | undefined;
    const syncedSessions = payload.sessions as SessionSummary[] | undefined;
    const syncedRuntime = payload.runtime as RuntimeOrchestratorStatus | undefined;
    if (Array.isArray(syncedSessions)) {
      reconcileSidebarProjects(syncedSessions, {
        preferredSelectedProjectPath: draftChatRef.current?.projectPath || undefined,
        activeSessionWorkspace: detail?.workspace,
      });
      setSessions(syncedSessions);
    }
    if (syncedRuntime) {
      setOrchestratorStatus(syncedRuntime);
    }
    if (detail?.id) {
      const modelChanged = Boolean(
        overview && (
          overview.current_model !== detail.model
          || overview.current_variant !== detail.variant
          || overview.context_usage?.model !== detail.model
        )
      );
      applySessionDetail(detail);
      setOverview((previous) => {
        if (!previous) {
          return previous;
        }
        return {
          ...previous,
          session_id: detail.id,
          current_model: detail.model,
          current_variant: detail.variant,
          planner_model: detail.planner_model ?? previous.planner_model ?? null,
          task_board_armed_next_turn: Boolean(detail.task_board_armed_next_turn),
          task_board: detail.task_board ?? null,
          completed_task_boards: normalizeCompletedTaskBoards(detail.completed_task_boards),
          context_usage: {
            ...previous.context_usage,
            model: detail.model,
          },
        };
      });
      if (modelChanged) {
        void refreshOverviewState(detail.id);
      }
    }
  };

  const refreshSidebarCollections = async (preferredSessionId?: string | null, quiet = true) => {
    if (sidebarCollectionsRefreshInFlightRef.current) {
      return;
    }
    sidebarCollectionsRefreshInFlightRef.current = true;
    try {
      const [profile, sessionList, jobList, botConfigList, runtimeSummary] = await Promise.all([
        fetchProfile(apiBaseUrl, token),
        fetchSessions(apiBaseUrl, token),
        fetchJobs(apiBaseUrl, token),
        fetchTelegramBotConfigs(apiBaseUrl, token).catch(() => []),
        fetchRuntimeOrchestratorStatus(apiBaseUrl, token).catch(() => null),
      ]);

      const currentSelectedSessionId = sessionIdRef.current || sessionId || null;
      const resolvedSessionId = draftChatRef.current
        ? null
        : preferredSessionId
          || profile.current_session_id
          || (currentSelectedSessionId && sessionList.some((item) => item.id === currentSelectedSessionId) ? currentSelectedSessionId : null)
          || sessionList[0]?.id
          || null;
      const activeSessionWorkspace = resolvedSessionId
        ? currentWorkspaceBySessionRef.current[resolvedSessionId]
          || sessions.find((item) => item.id === resolvedSessionId)?.workspace
        : undefined;

      reconcileSidebarProjects(sessionList, {
        preferredSelectedProjectPath: draftChatRef.current?.projectPath || undefined,
        activeSessionWorkspace,
      });
      setSessions(sessionList);
      setJobs(jobList);
      setTelegramBotConfigs(Array.isArray(botConfigList) ? botConfigList : []);
      setOrchestratorStatus(runtimeSummary);
      if (!quiet) {
        setStatus('ready');
        maybeResolveStartupReady();
      }
    } catch (error) {
      if (!quiet) {
        const message = describeError(error);
        setStatus(message);
        if (!startupTerminalStateRef.current) {
          emitStartupState('fatal_error', message);
        }
      }
    } finally {
      sidebarCollectionsRefreshInFlightRef.current = false;
    }
  };

  const refreshOverviewState = async (
    preferredSessionId?: string | null,
    options?: { includeCloseBehavior?: boolean; quiet?: boolean },
  ) => {
    if (overviewRefreshInFlightRef.current) {
      return;
    }
    const includeCloseBehavior = Boolean(options?.includeCloseBehavior);
    const quiet = Boolean(options?.quiet);
    const resolvedSessionId = draftChatRef.current
      ? null
      : preferredSessionId || sessionIdRef.current || null;
    if (!resolvedSessionId) {
      if (!quiet) {
        setOverview(null);
      }
      return;
    }

    overviewRefreshInFlightRef.current = true;
    try {
      const [nextOverview, closeBehaviorConfig] = await Promise.all([
        fetchAgentOverview(apiBaseUrl, token, {
          sessionId: resolvedSessionId || undefined,
        }),
        includeCloseBehavior
          ? fetchAgentConfig(
              apiBaseUrl,
              token,
              'channels.desktop.keep_runtime_on_app_close',
              resolvedSessionId || undefined,
            ).catch(() => ({ items: [] }))
          : Promise.resolve<{ items: Array<{ value?: unknown }> }>({ items: [] }),
      ]);
      setOverview(nextOverview);
      setRuntimeRunState(nextOverview?.run_state ?? 'idle');
      setTaskBoardArmedNextTurnState(Boolean(nextOverview?.task_board_armed_next_turn ?? false));
      setTaskBoard(resolveTaskBoardState(nextOverview?.task_board ?? null, resolvedSessionId, sessionIdRef.current));
      setCompletedTaskBoards(normalizeCompletedTaskBoards(nextOverview?.completed_task_boards ?? []));
      if (includeCloseBehavior) {
        setKeepRuntimeOnAppClose(Boolean(closeBehaviorConfig.items?.[0]?.value));
      }
    } catch (error) {
      if (!quiet) {
        const message = describeError(error);
        setStatus(message);
        if (!startupTerminalStateRef.current) {
          emitStartupState('fatal_error', message);
        }
      }
    } finally {
      overviewRefreshInFlightRef.current = false;
    }
  };

  const refreshSidebarState = async (preferredSessionId?: string | null, quiet = false) => {
    if (!quiet) {
      setStatus('loading shared session');
      emitStartupState('warming', 'Loading shared session');
    }

    try {
      let [profile, sessionList, jobList, botConfigList, runtimeSummary] = await Promise.all([
        fetchProfile(apiBaseUrl, token),
        fetchSessions(apiBaseUrl, token),
        fetchJobs(apiBaseUrl, token),
        fetchTelegramBotConfigs(apiBaseUrl, token).catch(() => []),
        fetchRuntimeOrchestratorStatus(apiBaseUrl, token).catch(() => null),
      ]);

      const currentSelectedSessionId = sessionIdRef.current || sessionId || null;
      let resolvedSessionId = preferredSessionId
        || profile.current_session_id
        || (currentSelectedSessionId && sessionList.some((item) => item.id === currentSelectedSessionId) ? currentSelectedSessionId : null)
        || sessionList[0]?.id
        || null;
      let detail: SessionDetail | null = null;
      if (draftChatRef.current) {
        resolvedSessionId = null;
      }

      if (!detail && resolvedSessionId) {
        detail = preferredSessionId && preferredSessionId !== profile.current_session_id
          ? await activateSessionWithRecovery(resolvedSessionId)
          : await fetchSessionDetail(apiBaseUrl, token, resolvedSessionId);
      }

      let nextOverview: AgentOverview | null = null;
      let closeBehaviorConfig: { items: Array<{ value?: unknown }> } = { items: [] };
      if (resolvedSessionId) {
        [nextOverview, closeBehaviorConfig] = await Promise.all([
          fetchAgentOverview(apiBaseUrl, token, {
            sessionId: resolvedSessionId || undefined,
          }),
          fetchAgentConfig(
            apiBaseUrl,
            token,
            'channels.desktop.keep_runtime_on_app_close',
            resolvedSessionId || undefined
          ).catch(() => ({ items: [] })),
        ]);
      }

      reconcileSidebarProjects(sessionList, {
        preferredSelectedProjectPath: draftChatRef.current?.projectPath || undefined,
        activeSessionWorkspace: detail?.workspace,
      });
      setSessions(sessionList);
      setJobs(jobList);
      setTelegramBotConfigs(Array.isArray(botConfigList) ? botConfigList : []);
      setOrchestratorStatus(runtimeSummary);
      setOverview(nextOverview);
      setRuntimeRunState(nextOverview?.run_state ?? 'idle');
      setTaskBoardArmedNextTurnState(Boolean(nextOverview?.task_board_armed_next_turn ?? detail?.task_board_armed_next_turn ?? false));
      setTaskBoard(resolveTaskBoardState(nextOverview?.task_board ?? detail?.task_board ?? null, resolvedSessionId, sessionIdRef.current));
      setCompletedTaskBoards(normalizeCompletedTaskBoards(nextOverview?.completed_task_boards ?? detail?.completed_task_boards ?? []));
      setKeepRuntimeOnAppClose(Boolean(closeBehaviorConfig.items?.[0]?.value));
      if (detail) {
        applySessionDetail(detail);
      } else if (draftChatRef.current) {
        setSessionId(undefined);
        setSessionName(draftChatRef.current.title);
        setMessages([]);
        setTimelineEvents([]);
        setTaskBoard(null);
        setCompletedTaskBoards([]);
        setTaskBoardArmedNextTurnState(false);
      } else if (preferredProjectPath) {
        resetConversationForDraft(preferredProjectPath);
        setDraftChat(buildDraftChatState(preferredProjectPath));
      } else {
        clearConversationSelection();
      }
      startupSidebarReadyRef.current = true;
      startupSessionStateReadyRef.current = true;
      setStatus('ready');
      maybeResolveStartupReady();
    } catch (error) {
      const message = describeError(error);
      setStatus(message);
      if (!startupTerminalStateRef.current) {
        emitStartupState('fatal_error', message);
      }
    }
  };

  const refreshVoiceRuntimeState = async () => {
    if (!apiBaseUrl || !token) {
      return null;
    }
    const next = await fetchVoiceRuntimeStatus(apiBaseUrl, token);
    setLiveVoiceStatus(next as DesktopVoiceRuntimeStatus);
    return next as DesktopVoiceRuntimeStatus;
  };

  const warmSelectedVoicePath = async (engineOverride?: string) => {
    const engine = engineOverride || selectedVoiceEngine;
    if (!apiBaseUrl || !token || engine !== VOICE_ENGINE_HEBREW) {
      return refreshVoiceRuntimeState();
    }
    lastVoiceWarmRequestEngineRef.current = engine;
    setVoiceState('warming');
    setStatus('warming Hebrew voice path');
    const warmed = await warmVoiceRuntime(apiBaseUrl, token);
    setLiveVoiceStatus(warmed as DesktopVoiceRuntimeStatus);
    if ((warmed?.selected_engine_state || '') === 'ready') {
      setVoiceState(alwaysOnEnabledRef.current ? 'always_on' : 'ready');
      setStatus('voice ready');
    } else if (warmed?.issues?.[0]) {
      setVoiceError(String(warmed.issues[0]));
      setVoiceState('error');
      setStatus(String(warmed.issues[0]));
    }
    return warmed as DesktopVoiceRuntimeStatus;
  };

  useEffect(() => {
    if (!apiBaseUrl || !token) return;
    void refreshSidebarState(initialSessionId, false);
  }, [apiBaseUrl, initialSessionId, token]);

  useEffect(() => {
    setLiveVoiceStatus(voiceStatus || null);
  }, [voiceStatus]);

  useEffect(() => {
    if (!apiBaseUrl || !token) {
      return;
    }
    if (selectedVoiceEngine !== VOICE_ENGINE_HEBREW) {
      lastVoiceWarmRequestEngineRef.current = null;
      return;
    }
    if ((liveVoiceStatus?.selected_engine_state || '') === 'ready') {
      lastVoiceWarmRequestEngineRef.current = selectedVoiceEngine;
      return;
    }
    if (lastVoiceWarmRequestEngineRef.current === selectedVoiceEngine || voiceEngineChanging) {
      return;
    }
    void warmSelectedVoicePath(selectedVoiceEngine);
  }, [apiBaseUrl, token, selectedVoiceEngine, liveVoiceStatus?.selected_engine_state, voiceEngineChanging]);

  useEffect(() => {
    if (!apiBaseUrl || !token || !sessionId) return;

    const intervalId = setInterval(() => {
      if (chatRunActiveRef.current) {
        return;
      }
      void refreshSidebarCollections(sessionId, true);
    }, SIDEBAR_REFRESH_MS);

    return () => clearInterval(intervalId);
  }, [apiBaseUrl, sessionId, token]);

  const flushPendingMessages = () => {
    const ws = chatWsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return;
    }

    while (pendingMessagesRef.current.length && ws.readyState === WebSocket.OPEN) {
      const next = pendingMessagesRef.current.shift();
      if (!next) break;
      ws.send(JSON.stringify({
        text: next.text,
        session_id: next.sessionId,
        interrupt_policy: next.interruptPolicy,
        source_format: next.sourceFormat,
      }));
    }
  };

  const queueMessage = (
    text: string,
    sourceFormat: MessageSourceFormat,
    explicitSessionId?: string,
    policyOverride?: InterruptPolicy,
  ) => {
    const activeSessionId = explicitSessionId || sessionIdRef.current;
    if (!activeSessionId) {
      setStatus('missing session');
      return;
    }

    setMessages((previous) => [
      ...previous,
      {
        role: 'user',
        content: text,
        timestamp: new Date().toISOString(),
        displayLabel: sourceFormat === 'app_voice_transcript' ? 'Voice' : 'You',
        channel: 'app',
        sourceFormat,
        messageKey: `pending:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
        pending: true,
      },
    ]);

    pendingMessagesRef.current.push({
      text,
      sourceFormat,
      interruptPolicy: policyOverride ?? interruptPolicy,
      sessionId: activeSessionId,
    });

    if (taskBoardArmedNextTurn && activeSessionId === sessionIdRef.current) {
      setTaskBoardArmedNextTurnState(false);
      setOverview((previous) => (
        previous
          ? {
              ...previous,
              task_board_armed_next_turn: false,
            }
          : previous
      ));
    }

    const ws = chatWsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      setChatRunActive(true);
      setRuntimeRunState('running');
      setLastAssistantOutputAt(null);
      flushPendingMessages();
      setStatus(sourceFormat === 'app_voice_transcript' ? 'sending voice transcript' : 'sending message');
    } else {
      setStatus('chat reconnecting · message queued');
    }
  };

  const queueComposerMessage = (text: string, sourceFormat: MessageSourceFormat, explicitSessionId?: string) => {
    const activeSessionId = explicitSessionId || sessionIdRef.current;
    if (!activeSessionId) {
      setStatus('missing session');
      return;
    }
    setQueuedComposerMessages((current) => [
      ...current,
      {
        id: `queued-${Date.now()}-${current.length}`,
        text,
        sourceFormat,
        sessionId: activeSessionId,
        queuedAt: Date.now(),
      },
    ]);
    setStatus('message queued for the current run');
  };

  const setComposerInputValue = (
    nextInput: string,
    options?: { syncVoiceBase?: boolean; origin?: ComposerInputOrigin },
  ) => {
    setInput(nextInput);
    lastComposerInputOriginRef.current = options?.origin ?? 'system';
    if (options?.syncVoiceBase === false) {
      return;
    }
    voiceComposerBaseInputRef.current = nextInput;
    if (!nextInput) {
      voiceComposerDraftRef.current = '';
    }
  };

  const handleComposerContentSizeChange = (
    event: NativeSyntheticEvent<TextInputContentSizeChangeEventData>,
  ) => {
    const nextHeight = event.nativeEvent.contentSize?.height;
    if (typeof nextHeight !== 'number' || Number.isNaN(nextHeight)) {
      return;
    }
    const clampedHeight = Math.max(COMPOSER_MIN_HEIGHT, Math.min(COMPOSER_MAX_HEIGHT, Math.ceil(nextHeight)));
    setComposerInputHeight((current) => (
      Math.abs(current - clampedHeight) < 1 ? current : clampedHeight
    ));
  };

  const handleComposerMeasureLayout = (event: LayoutChangeEvent) => {
    if (Platform.OS !== 'web') {
      return;
    }
    const nextHeight = event.nativeEvent.layout.height;
    if (typeof nextHeight !== 'number' || Number.isNaN(nextHeight)) {
      return;
    }
    const clampedHeight = Math.max(COMPOSER_MIN_HEIGHT, Math.min(COMPOSER_MAX_HEIGHT, Math.ceil(nextHeight)));
    setComposerInputHeight((current) => (
      Math.abs(current - clampedHeight) < 1 ? current : clampedHeight
    ));
  };

  const handleComposerInputChange = (nextInput: string) => {
    setComposerInputValue(nextInput, { syncVoiceBase: false, origin: 'manual' });
    if (!(voiceCaptureModeRef.current === 'always_on' && (voiceRecordingRef.current || voiceRunningRef.current))) {
      voiceComposerBaseInputRef.current = nextInput;
      voiceComposerDraftRef.current = '';
    }
  };

  useEffect(() => {
    if (!input) {
      setComposerInputHeight(COMPOSER_MIN_HEIGHT);
    }
  }, [input]);

  const appendLocalMessage = (
    content: string,
    role: DesktopMessage['role'],
    displayLabel: string,
    channel: DesktopMessage['channel'] = 'system',
  ) => {
    const normalized = content.trim();
    if (!normalized) {
      return;
    }
    const activeSessionId = sessionIdRef.current;
    setMessages((previous) => [
      ...previous,
      {
        role,
        content: normalized,
        timestamp: new Date().toISOString(),
        displayLabel,
        channel,
        sourceFormat: 'app_system',
        messageKey: `local:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
        localOnly: true,
        localSessionId: activeSessionId,
      },
    ]);
  };

  const appendLocalSystemMessage = (content: string, displayLabel = 'Command') => {
    appendLocalMessage(content, 'system', displayLabel, 'system');
  };

  const stopVoiceTracks = () => {
    const processor = voiceProcessorRef.current;
    voiceProcessorRef.current = null;
    if (processor) {
      processor.onaudioprocess = null;
      try {
        processor.disconnect();
      } catch {
        // no-op
      }
    }

    const source = voiceAudioSourceRef.current;
    voiceAudioSourceRef.current = null;
    if (source) {
      try {
        source.disconnect();
      } catch {
        // no-op
      }
    }

    const context = voiceAudioContextRef.current;
    voiceAudioContextRef.current = null;
    if (context && context.state !== 'closed') {
      void context.close().catch(() => undefined);
    }

    const stream = voiceStreamRef.current;
    voiceStreamRef.current = null;
    if (stream) {
      for (const track of stream.getTracks()) {
        track.stop();
      }
    }

    voiceGateStateRef.current = createVoiceGateState();
    deferredAlwaysOnFramesRef.current = [];
    deferredAlwaysOnSampleCountRef.current = 0;
  };

  const resetVoiceCaptureBuffers = (options?: { clearProgrammaticComposerInput?: boolean }) => {
    voiceChunkSequenceRef.current = 0;
    voiceChunkChainRef.current = Promise.resolve();
    voiceChunkSamplesRef.current = [];
    voiceChunkSampleCountRef.current = 0;
    voiceGateStateRef.current = createVoiceGateState();
    deferredAlwaysOnFramesRef.current = [];
    deferredAlwaysOnSampleCountRef.current = 0;
    drainingDeferredAlwaysOnFramesRef.current = false;
    voiceComposerBaseInputRef.current = '';
    voiceComposerDraftRef.current = '';
    const lastInputOrigin = lastComposerInputOriginRef.current;
    lastComposerInputOriginRef.current = 'system';
    setVoiceDraft('');
    setVoiceError(null);
    if (options?.clearProgrammaticComposerInput && lastInputOrigin !== 'manual') {
      setComposerInputValue('', { syncVoiceBase: false, origin: 'system' });
    }
  };

  const cleanupAssistantAudio = async () => {
    const audio = assistantAudioRef.current;
    assistantAudioRef.current = null;
    if (!audio) {
      return;
    }
    try {
      audio.pause();
    } catch {
      // no-op
    }
    audio.src = '';
  };

  const playAssistantAudio = async (audioBase64: string, mimeType: string) => {
    if (!audioBase64 || typeof globalThis.Audio === 'undefined') {
      return;
    }
    await cleanupAssistantAudio();
    const audio = new globalThis.Audio(`data:${mimeType || 'audio/mpeg'};base64,${audioBase64}`);
    assistantAudioRef.current = audio;
    try {
      await audio.play();
    } catch (error) {
      pushActivity(`Assistant audio failed: ${describeError(error)}`, 'warn');
      logDiagnostic('desktop.voice.audio', 'assistant audio playback failed', describeError(error), 'warn');
    }
  };

  const sendVoiceChunk = (samples: Float32Array, sampleRate: number) => {
    if (!samples.length) {
      return;
    }
    const wavBytes = new Uint8Array(encodePcm16Wav(samples, sampleRate));
    voiceChunkChainRef.current = voiceChunkChainRef.current
      .catch(() => undefined)
      .then(async () => {
        const ws = voiceWsRef.current;
        if (!ws || ws.readyState !== WebSocket.OPEN) {
          throw new Error('Voice socket unavailable');
        }
        voiceChunkSequenceRef.current += 1;
        ws.send(JSON.stringify({
          type: 'voice_chunk',
          session_id: sessionIdRef.current,
          sequence: voiceChunkSequenceRef.current,
          mime_type: 'audio/wav',
          audio_base64: bytesToBase64(wavBytes),
        }));
        logDiagnostic('desktop.voice.ws', 'sent voice chunk', {
          sequence: voiceChunkSequenceRef.current,
          samples: samples.length,
          sampleRate,
          sessionId: sessionIdRef.current || null,
        });
      })
      .catch((error) => {
        const message = describeError(error);
        setVoiceState('error');
        setVoiceError(message);
        setVoiceRunning(false);
        setVoiceRecording(false);
        pushActivity(`Voice chunk failed: ${message}`, 'error');
        logDiagnostic('desktop.voice.ws', 'voice chunk failed', message, 'error');
      });
  };

  const flushVoiceChunk = () => {
    const sampleCount = voiceChunkSampleCountRef.current;
    if (sampleCount <= 0) {
      return voiceChunkChainRef.current;
    }
    const samples = concatFloat32(voiceChunkSamplesRef.current, sampleCount);
    voiceChunkSamplesRef.current = [];
    voiceChunkSampleCountRef.current = 0;
    sendVoiceChunk(samples, voiceSampleRateRef.current);
    return voiceChunkChainRef.current;
  };

  const appendVoiceChunkSamples = (samples: Float32Array, force = false) => {
    if (!samples.length) return;
    voiceChunkSamplesRef.current.push(samples);
    voiceChunkSampleCountRef.current += samples.length;
    const chunkTarget = Math.max(1, Math.round(voiceSampleRateRef.current * activeVoiceSegmentMs / 1000));
    if (force || voiceChunkSampleCountRef.current >= chunkTarget) {
      void flushVoiceChunk();
    }
  };

  const beginVoiceSegment = (mode: VoiceCaptureMode) => {
    const ws = voiceWsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setStatus('voice socket unavailable');
      return false;
    }

    voiceCaptureModeRef.current = mode;
    voiceChunkSequenceRef.current = 0;
    voiceChunkChainRef.current = Promise.resolve();
    voiceChunkSamplesRef.current = [];
    voiceChunkSampleCountRef.current = 0;
    if (mode === 'always_on') {
      // Only seed always-on accumulation from a real manual composer draft.
      // Older programmatic voice text should not leak into a new segment.
      if (lastComposerInputOriginRef.current === 'manual') {
        voiceComposerBaseInputRef.current = input;
      } else if (!voiceComposerBaseInputRef.current) {
        voiceComposerBaseInputRef.current = '';
      }
      voiceComposerDraftRef.current = '';
    }
    setVoiceDraft('');
    setVoiceError(null);
    setAssistantDraft('');
    setThinking('');
    setVoiceState('listening');
    voiceRunningRef.current = true;
    voiceRecordingRef.current = true;
    setVoiceRunning(true);
    setVoiceRecording(true);
    setStatus(mode === 'always_on' ? 'always-on voice segment detected' : 'voice listening');
    ws.send(JSON.stringify({
      type: 'voice_start',
      session_id: sessionIdRef.current,
    }));
    logDiagnostic('desktop.voice.ws', 'sent voice_start', {
      mode,
      sampleRate: voiceSampleRateRef.current,
      sessionId: sessionIdRef.current || null,
    });
    return true;
  };

  const finishVoiceSegment = async (commit: boolean, mode: VoiceCaptureMode) => {
    await flushVoiceChunk().catch(() => undefined);
    await voiceChunkChainRef.current.catch(() => undefined);

    const ws = voiceWsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: commit ? 'voice_commit' : 'voice_cancel',
        session_id: sessionIdRef.current,
        interrupt_policy: commit ? interruptPolicy : 'none',
        auto_send: commit && mode === 'always_on' ? ALWAYS_ON_VOICE_AUTO_SEND : true,
      }));
      logDiagnostic('desktop.voice.ws', commit ? 'sent voice_commit' : 'sent voice_cancel', {
        mode,
        sessionId: sessionIdRef.current || null,
        interruptPolicy: commit ? interruptPolicy : 'none',
        autoSend: commit && mode === 'always_on' ? ALWAYS_ON_VOICE_AUTO_SEND : true,
      });
    }

    voiceRecordingRef.current = false;
    setVoiceRecording(false);
    if (commit) {
      voiceRunningRef.current = true;
      setVoiceRunning(true);
      setVoiceState('finalizing');
      setStatus(
        mode === 'always_on' && !ALWAYS_ON_VOICE_AUTO_SEND
          ? 'always-on transcript finalizing'
          : mode === 'always_on'
            ? 'always-on voice segment finalizing'
            : 'voice finalizing'
      );
    } else {
      if (mode === 'always_on') {
        voiceComposerDraftRef.current = '';
        setComposerInputValue(voiceComposerBaseInputRef.current, { syncVoiceBase: false, origin: 'voice' });
      }
      setVoiceDraft('');
      voiceRunningRef.current = false;
      setVoiceRunning(false);
      setVoiceState(mode === 'always_on' && alwaysOnEnabledRef.current ? 'always_on' : 'cancelled');
      setStatus(mode === 'always_on' && alwaysOnEnabledRef.current ? 'always-on voice listening' : 'voice cancelled');
    }
  };

  const takeGateFrame = (gate: VoiceGateState, frameSamples: number) => {
    if (gate.pendingSampleCount < frameSamples) {
      return null;
    }

    const frame = new Float32Array(frameSamples);
    let written = 0;
    while (written < frameSamples && gate.pendingFrames.length > 0) {
      const head = gate.pendingFrames[0];
      const needed = frameSamples - written;
      if (head.length <= needed) {
        frame.set(head, written);
        written += head.length;
        gate.pendingFrames.shift();
      } else {
        frame.set(head.subarray(0, needed), written);
        gate.pendingFrames[0] = head.subarray(needed);
        written += needed;
      }
    }
    gate.pendingSampleCount -= frameSamples;
    return frame;
  };

  const rememberDeferredAlwaysOnFrame = (frame: Float32Array) => {
    if (!alwaysOnEnabledRef.current || frame.length === 0) {
      return;
    }

    deferredAlwaysOnFramesRef.current.push(frame);
    deferredAlwaysOnSampleCountRef.current += frame.length;

    const maxSamples = Math.max(
      frame.length,
      Math.round(voiceSampleRateRef.current * VOICE_DEFERRED_FRAME_MAX_MS / 1000)
    );
    while (deferredAlwaysOnSampleCountRef.current > maxSamples && deferredAlwaysOnFramesRef.current.length > 1) {
      const dropped = deferredAlwaysOnFramesRef.current.shift();
      deferredAlwaysOnSampleCountRef.current -= dropped?.length || 0;
    }
  };

  const processAlwaysOnFrame = (frame: Float32Array) => {
    if (!alwaysOnEnabledRef.current) {
      return;
    }

    const gate = voiceGateStateRef.current;
    const frameDbfs = samplesDbfs(frame);
    const aboveThreshold = frameDbfs >= activeVoiceGateDbfs;
    const attackFrames = Math.max(1, Math.ceil(VOICE_GATE_ATTACK_MS / VOICE_GATE_FRAME_MS));
    const releaseFrames = Math.max(1, Math.ceil(activeVoiceGateReleaseMs / VOICE_GATE_FRAME_MS));
    const prerollFrames = Math.max(1, Math.ceil(activeVoiceGatePrerollMs / VOICE_GATE_FRAME_MS));
    const minFrames = Math.max(1, Math.ceil(VOICE_GATE_MIN_MS / VOICE_GATE_FRAME_MS));
    const maxFrames = Math.max(minFrames, Math.ceil(activeVoiceGateMaxMs / VOICE_GATE_FRAME_MS));

    if (!gate.recording) {
      if (voiceRunningRef.current || voiceRecordingRef.current) {
        rememberDeferredAlwaysOnFrame(frame);
        return;
      }
      gate.prerollFrames.push(frame);
      while (gate.prerollFrames.length > prerollFrames) {
        gate.prerollFrames.shift();
      }
      gate.aboveFrames = aboveThreshold ? gate.aboveFrames + 1 : 0;
      if (gate.aboveFrames < attackFrames) {
        return;
      }

      if (!beginVoiceSegment('always_on')) {
        voiceGateStateRef.current = createVoiceGateState();
        return;
      }

      gate.recording = true;
      gate.activeFrames = gate.prerollFrames.length;
      gate.voicedFrames = gate.aboveFrames;
      gate.belowFrames = 0;
      for (const preroll of gate.prerollFrames) {
        appendVoiceChunkSamples(preroll);
      }
      return;
    }

    appendVoiceChunkSamples(frame);
    gate.activeFrames += 1;
    if (aboveThreshold) {
      gate.voicedFrames += 1;
      gate.belowFrames = 0;
    } else {
      gate.belowFrames += 1;
    }

    const shouldClose = gate.belowFrames >= releaseFrames || gate.activeFrames >= maxFrames;
    if (!shouldClose) {
      return;
    }

    const shouldCommit = gate.voicedFrames >= minFrames;
    voiceGateStateRef.current = createVoiceGateState();
    void finishVoiceSegment(shouldCommit, 'always_on');
  };

  const drainDeferredAlwaysOnFrames = () => {
    if (
      !alwaysOnEnabledRef.current
      || voiceRunningRef.current
      || voiceRecordingRef.current
      || drainingDeferredAlwaysOnFramesRef.current
      || deferredAlwaysOnFramesRef.current.length === 0
    ) {
      return;
    }

    const frames = deferredAlwaysOnFramesRef.current.splice(0);
    deferredAlwaysOnSampleCountRef.current = 0;
    drainingDeferredAlwaysOnFramesRef.current = true;
    try {
      for (const frame of frames) {
        if (!alwaysOnEnabledRef.current) {
          break;
        }
        processAlwaysOnFrame(frame);
      }
    } finally {
      drainingDeferredAlwaysOnFramesRef.current = false;
    }
  };

  const processVoiceSamples = (samples: Float32Array) => {
    if (voiceCaptureModeRef.current === 'push_to_talk') {
      appendVoiceChunkSamples(samples);
      return;
    }

    const gate = voiceGateStateRef.current;
    gate.pendingFrames.push(samples);
    gate.pendingSampleCount += samples.length;
    const frameSamples = Math.max(1, Math.round(voiceSampleRateRef.current * VOICE_GATE_FRAME_MS / 1000));
    let frame = takeGateFrame(gate, frameSamples);
    while (frame) {
      processAlwaysOnFrame(frame);
      frame = takeGateFrame(gate, frameSamples);
    }
  };

  const handleRealtimeEvent = (event: RealtimeEvent, channel: RealtimeChannel) => {
    const payload = (event.payload || {}) as Record<string, any>;

    if (event.type === 'session_snapshot') {
      setSocketState('connected');
      if (typeof event.session_id === 'string' && event.session_id && event.session_id !== sessionIdRef.current) {
        setSessionId(event.session_id);
      }
      setChatRunActive(false);
      setLastAssistantOutputAt(null);
      setStatus('ready');
      return;
    }

    if (event.type === 'session_sync') {
      applySessionSync(payload);
      setStatus('ready');
      return;
    }

    if (event.type === 'user_message') {
      const message = payload.message as SessionMessage | undefined;
      if (message) {
        setMessages((previous) => [...previous, toLiveDesktopMessage(message, previous)]);
      }
      return;
    }

    if (event.type === 'assistant_delta') {
      setChatRunActive(true);
      setRuntimeRunState('running');
      setLastAssistantOutputAt(Date.now());
      assistantDeltaBufferRef.current += String(payload.delta || '');
      if (!assistantDeltaFlushTimerRef.current) {
        assistantDeltaFlushTimerRef.current = setTimeout(() => {
          flushAssistantDeltaBuffer();
        }, 40);
      }
      setOverview((previous) => (
        previous
          ? {
              ...previous,
              run_state: 'running',
            }
          : previous
      ));
      if (channel === 'voice') {
        setVoiceRunning(true);
      }
      return;
    }

    if (event.type === 'assistant_final') {
      const finalText = String(payload.text || '');
      const message = payload.message as SessionMessage | undefined;
      assistantDeltaBufferRef.current = '';
      clearAssistantDeltaFlushTimer();
      setAssistantDraft('');
      setThinking('');
      setLastAssistantOutputAt(Date.now());
      if (channel === 'voice') {
        voiceRunningRef.current = false;
        voiceRecordingRef.current = false;
        setVoiceRunning(false);
        setVoiceRecording(false);
      }
      if (message) {
        setMessages((previous) => [
          ...previous,
          toLiveDesktopMessage(message, previous),
        ]);
      } else if (finalText.trim()) {
        setMessages((previous) => [
          ...previous,
          {
            role: 'assistant',
            content: finalText,
            timestamp: new Date().toISOString(),
            displayLabel: 'Assistant',
            channel: 'app',
            sourceFormat: 'app_text',
            messageKey: `assistant:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
          },
        ]);
      }
      setChatRunActive(false);
      setRuntimeRunState('idle');
      setOverview((previous) => (
        previous
          ? {
              ...previous,
              run_state: 'idle',
            }
          : previous
      ));
      setStatus('ready');
      void refreshSidebarCollections(event.session_id || sessionIdRef.current, true);
      void refreshOverviewState(event.session_id || sessionIdRef.current, { quiet: true });
      return;
    }

    if (event.type === 'assistant_audio') {
      void playAssistantAudio(
        String(payload.audio_base64 || ''),
        String(payload.mime_type || 'audio/mpeg'),
      );
      return;
    }

    if (event.type === 'thinking') {
      setChatRunActive(true);
      setRuntimeRunState('running');
      setThinking(String(payload.formatted || payload.text || ''));
      setOverview((previous) => (
        previous
          ? {
              ...previous,
              run_state: 'running',
            }
          : previous
      ));
      return;
    }

    if (event.type === 'tool_event') {
      setChatRunActive(true);
      setRuntimeRunState('running');
      setOverview((previous) => (
        previous
          ? {
              ...previous,
              run_state: 'running',
            }
          : previous
      ));
      const toolTimelineEvent = createLocalToolTimelineEvent(payload);
      if (toolTimelineEvent) {
        appendTimelineEvent(toolTimelineEvent);
      }
      pushActivity(summarizeToolPayload(payload), 'accent');
      return;
    }

    if (event.type === 'artifact_created') {
      const created = Array.isArray(payload.artifacts) ? payload.artifacts as ArtifactSummary[] : [];
      if (created.length > 0) {
        setArtifacts((previous) => {
          const seen = new Set(previous.map((item) => item.artifact_id));
          const merged = [...created.filter((item) => !seen.has(item.artifact_id)), ...previous];
          return merged.sort((left, right) => String(right.created_at || '').localeCompare(String(left.created_at || '')));
        });
        if (!selectedArtifactId) {
          setSelectedArtifactId(created[0].artifact_id);
        }
      }
      return;
    }

    if (event.type === 'timeline_event') {
      const timelineEvent = (payload.event as SessionTimelineEvent | undefined) ?? null;
      if (timelineEvent) {
        appendTimelineEvent(timelineEvent);
      }
      return;
    }

    if (event.type === 'task_board') {
      const board = (payload.board as TaskBoard | null | undefined) ?? null;
      const completedBoards = normalizeCompletedTaskBoards(payload.completed_task_boards as TaskBoard[] | undefined);
      const summary = String(payload.summary || '').trim();
      const eventSessionId = event.session_id || sessionIdRef.current;
      setTaskBoard(resolveTaskBoardState(board, eventSessionId, sessionIdRef.current));
      setCompletedTaskBoards(completedBoards);
      if (board?.status === 'active') {
        setTaskBoardArmedNextTurnState(false);
      }
      setOverview((previous) => (
        previous
          ? {
              ...previous,
              task_board: resolveTaskBoardState(board, eventSessionId, sessionIdRef.current),
              completed_task_boards: completedBoards,
              task_board_armed_next_turn: board?.status === 'active'
                ? false
                : previous.task_board_armed_next_turn,
            }
          : previous
      ));
      if (summary) {
        const tone = board?.status === 'blocked' || board?.pending_reassessment_reason
          ? 'warn'
          : board?.status === 'completed'
            ? 'accent'
            : 'neutral';
        pushActivity(`Task board: ${summary}`, tone);
      }
      return;
    }

    if (event.type === 'current_session_changed') {
      const rawCurrentSessionId = payload.current_session_id;
      const currentSessionKnown = rawCurrentSessionId === null || rawCurrentSessionId === undefined
        ? null
        : String(rawCurrentSessionId || '').trim();
      const nextSessionId = currentSessionKnown !== null
        ? (currentSessionKnown || null)
        : event.session_id || sessionIdRef.current;
      void refreshSidebarCollections(nextSessionId, true);
      return;
    }

    if (event.type === 'log') {
      const message = String(payload.message || '');
      const tone = payload.level === 'error' ? 'error' : payload.level === 'warn' ? 'warn' : 'neutral';
      pushActivity(message, tone);
      return;
    }

    if (event.type === 'status') {
      const message = String(payload.message || event.message || '');
      const runState = payload.run_state === 'running'
        ? 'running'
        : payload.run_state === 'idle'
          ? 'idle'
          : message === 'running'
            ? 'running'
            : message === 'ready'
              ? 'idle'
              : null;
      if (runState) {
        setRuntimeRunState(runState);
        setChatRunActive(runState === 'running');
        if (runState === 'idle') {
          setAssistantDraft('');
          setThinking('');
          setLastAssistantOutputAt(null);
        }
        setOverview((previous) => (
          previous
            ? {
                ...previous,
                run_state: runState,
              }
            : previous
        ));
      }
      if (message) {
        if (message === 'ready') {
          setChatRunActive(false);
        }
        setStatus(message);
        pushActivity(message, 'neutral');
      }
      return;
    }

    if (event.type === 'warning') {
      const message = String(payload.message || event.message || 'warning');
      setStatus(message);
      setAssistantDraft('');
      if (channel === 'voice') {
        voiceRunningRef.current = false;
        voiceRecordingRef.current = false;
        setVoiceRunning(false);
        setVoiceRecording(false);
      }
      setChatRunActive(false);
      setRuntimeRunState('idle');
      setLastAssistantOutputAt(null);
      setOverview((previous) => (
        previous
          ? {
              ...previous,
              run_state: 'idle',
            }
          : previous
      ));
      void refreshSidebarCollections(event.session_id || sessionIdRef.current, true);
      pushActivity(message, 'warn');
      return;
    }

    if (event.type === 'error') {
      const message = String(payload.message || event.message || 'runtime error');
      setStatus(message);
      if (channel === 'voice') {
        setVoiceError(message);
        setVoiceState('error');
        voiceRunningRef.current = false;
        voiceRecordingRef.current = false;
        setVoiceRunning(false);
        setVoiceRecording(false);
      }
      setChatRunActive(false);
      setRuntimeRunState('idle');
      setLastAssistantOutputAt(null);
      setOverview((previous) => (
        previous
          ? {
              ...previous,
              run_state: 'idle',
            }
          : previous
      ));
      pushActivity(message, 'error');
      return;
    }

    if (channel === 'voice' && event.type === 'voice_state') {
      const rawState = String(payload.state || 'idle');
      const nextState = rawState === 'connected' ? 'ready' : rawState;
      setVoiceState(nextState);
      setVoiceError(null);
      const nextRunning = !['ready', 'idle', 'cancelled', 'error', 'unavailable', 'connected', 'always_on'].includes(nextState);
      voiceRunningRef.current = nextRunning;
      setVoiceRunning(nextRunning);
      if (nextState === 'idle' || nextState === 'cancelled') {
        voiceRecordingRef.current = false;
        setVoiceRecording(false);
        if (alwaysOnEnabledRef.current && nextState === 'idle') {
          setVoiceState('always_on');
          setTimeout(drainDeferredAlwaysOnFrames, 0);
        }
      }
      return;
    }

    if (channel === 'voice' && event.type === 'voice_partial') {
      const text = String(payload.text || '');
      setVoiceDraft(text);
      setVoiceState('listening');
      voiceRunningRef.current = true;
      setVoiceRunning(true);
      if (alwaysOnEnabledRef.current) {
        voiceComposerDraftRef.current = text;
        setComposerInputValue(
          composeVoiceDraftInput(voiceComposerBaseInputRef.current, text),
          { syncVoiceBase: false, origin: 'voice' }
        );
      }
      return;
    }

    if (channel === 'voice' && event.type === 'voice_transcript') {
      const text = String(payload.text || '').trim();
      if (!text) {
        return;
      }
      if (alwaysOnEnabledRef.current && !ALWAYS_ON_VOICE_AUTO_SEND) {
        const nextInput = appendVoiceTranscriptSegment(voiceComposerBaseInputRef.current, text);
        voiceComposerBaseInputRef.current = nextInput;
        voiceComposerDraftRef.current = '';
        setComposerInputValue(nextInput, { syncVoiceBase: false, origin: 'voice' });
      } else {
        setInput((current) => {
          const existing = current.trim();
          const nextInput = existing ? `${existing} ${text}` : text;
          voiceComposerBaseInputRef.current = nextInput;
          voiceComposerDraftRef.current = '';
          lastComposerInputOriginRef.current = 'voice';
          return nextInput;
        });
      }
      setVoiceDraft(text);
      voiceRecordingRef.current = false;
      voiceRunningRef.current = false;
      setVoiceRecording(false);
      setVoiceRunning(false);
      setVoiceState(alwaysOnEnabledRef.current ? 'always_on' : 'ready');
      setStatus('voice transcript ready to review');
      pushActivity(`Voice transcript ready: ${text}`, 'accent');
      return;
    }

    if (channel === 'voice' && event.type === 'voice_final') {
      const text = String(payload.text || '').trim();
      if (!text) {
        return;
      }
      setVoiceDraft(text);
      voiceRecordingRef.current = false;
      voiceRunningRef.current = true;
      setVoiceRecording(false);
      setVoiceRunning(true);
      setMessages((previous) => [
        ...previous,
        {
          role: 'user',
          content: text,
          timestamp: new Date().toISOString(),
          displayLabel: 'Voice',
          channel: 'app',
          sourceFormat: 'app_voice_transcript',
          messageKey: `voice:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
        },
      ]);
      pushActivity(`Voice transcript captured: ${text}`, 'accent');
    }
  };

  const executeSlashCommand = async (text: string) => {
    const commandLabel = text.trim().split(/\s+/, 1)[0] || '/command';
    setStatus(`${commandLabel} requested`);
    setAssistantDraft('');
    setThinking('');
    setVoiceDraft('');
    appendLocalMessage(text, 'user', 'Command', 'app');

    const result = await runDesktopSlashCommand(text, {
      apiBaseUrl,
      token,
      sessionId: sessionIdRef.current,
      overview,
      sessions,
      jobs,
      envFilePath,
    });

    const timelineSessionId = result.nextSessionId || sessionIdRef.current;
    let commandTimelineRecorded = false;
    if (timelineSessionId) {
      const timelineContent = result.output || `${commandLabel} completed.`;
      const response = await appendSessionTimelineEvent(apiBaseUrl, token, timelineSessionId, {
        kind: 'command',
        title: `Command · ${text.trim()}`,
        content: timelineContent,
        tone: 'accent',
        channel: 'app',
        source_format: 'app_system',
        metadata: {
          command: text.trim(),
          status: result.status || null,
        },
        source_client_id: appClientIdRef.current,
      }).catch(() => null);
      if (response?.event) {
        appendTimelineEvent(response.event);
        commandTimelineRecorded = true;
      }
    }

    if (result.refresh || result.nextSessionId) {
      await refreshSidebarState(result.nextSessionId || sessionIdRef.current, true);
    }

    if (result.output) {
      if (!commandTimelineRecorded) {
        appendLocalSystemMessage(result.output, 'Command Result');
      }
      const activityPreview = result.output.split('\n', 1)[0]?.trim();
      if (activityPreview) {
        pushActivity(activityPreview, 'accent');
      }
    } else if (result.handled && !commandTimelineRecorded) {
      appendLocalSystemMessage(`${commandLabel} completed.`, 'Command Result');
    }
    setStatus(result.status || 'ready');
  };

  const runSlashCommandFromComposer = async (text: string) => {
    try {
      await executeSlashCommand(text);
    } catch (error) {
      const message = describeError(error);
      setStatus(message);
      pushActivity(message, 'error');
      let commandTimelineRecorded = false;
      if (sessionIdRef.current) {
        const response = await appendSessionTimelineEvent(apiBaseUrl, token, sessionIdRef.current, {
          kind: 'command',
          title: `Command · ${text.trim()}`,
          content: message,
          tone: 'error',
          channel: 'app',
          source_format: 'app_system',
          metadata: {
            command: text.trim(),
            error: true,
          },
          source_client_id: appClientIdRef.current,
        }).catch(() => null);
        if (response?.event) {
          appendTimelineEvent(response.event);
          commandTimelineRecorded = true;
        }
      }
      if (!commandTimelineRecorded) {
        appendLocalSystemMessage(message, 'Command Error');
      }
    }
  };

  const runVerboseCommand = async (arg?: 'on' | 'off' | 'status') => {
    const commandText = arg ? `/verbose ${arg}` : '/verbose';
    setActiveCommandPanel(null);
    if (arg === 'on' || arg === 'off') {
      const nextVerboseMode = arg === 'on';
      setOverview((previous) => (
        previous
          ? {
              ...previous,
              verbose_mode: nextVerboseMode,
            }
          : previous
      ));
    }
    await runSlashCommandFromComposer(commandText);
  };

  const openCommandPanelForInput = (text: string) => {
    const command = parseComposerSlashCommand(text);
    if (!command || command.rawArgs) {
      return false;
    }

    if (command.name === 'model' || command.name === 'models') {
      setActiveCommandPanel({ kind: 'model' });
      setStatus('choose a model');
      return true;
    }

    if (command.name === 'planner') {
      setActiveCommandPanel({ kind: 'model' });
      setStatus('choose a planner model');
      return true;
    }

    if (command.name === 'session') {
      setSidebarExpanded(true);
      setStatus('choose a chat in the sidebar');
      return true;
    }

    if (command.name === 'verbose') {
      setActiveCommandPanel({ kind: 'verbose' });
      setStatus('choose verbose mode');
      return true;
    }

    if (command.name === 'compact') {
      return false;
    }

    const suggestion = DESKTOP_COMMAND_SUGGESTIONS.find((item) => item.name === command.name);
    setActiveCommandPanel({
      kind: 'command',
      command: `/${command.name}`,
      description: suggestion?.description || 'Run this command.',
    });
    setStatus(`review /${command.name}`);
    return true;
  };

  const chooseModel = async (model: string) => {
    if (!sessionIdRef.current && draftChatRef.current) {
      setDraftChat((current) => (
        current
          ? {
              ...current,
              model,
              variant: null,
            }
          : current
      ));
      setActiveCommandPanel(null);
      setStatus(`draft model ${model}`);
      return;
    }
    setStatus(`switching model to ${model}`);
    try {
      await configureAgent(apiBaseUrl, token, { model }, sessionIdRef.current);
      setActiveCommandPanel(null);
      appendLocalSystemMessage(`Model switched to ${model}.`, 'Command Result');
      pushActivity(`Model switched to ${model}`, 'accent');
      await refreshSidebarState(sessionIdRef.current, true);
      setStatus(`model ${model}`);
    } catch (error) {
      const message = describeError(error);
      setStatus(message);
      appendLocalSystemMessage(message, 'Command Error');
      pushActivity(message, 'error');
    }
  };

  const choosePlannerModel = async (plannerModel: string | null) => {
    if (!sessionIdRef.current && draftChatRef.current) {
      setDraftChat((current) => (
        current
          ? {
              ...current,
              plannerModel,
            }
          : current
      ));
      setActiveCommandPanel(null);
      setStatus(plannerModel ? `draft planner ${plannerModel}` : 'draft planner auto');
      return;
    }
    setStatus(plannerModel ? `switching planner to ${plannerModel}` : 'restoring automatic planner selection');
    try {
      await configureAgent(apiBaseUrl, token, { planner_model: plannerModel }, sessionIdRef.current);
      setActiveCommandPanel(null);
      appendLocalSystemMessage(
        plannerModel
          ? `Planner model pinned to ${plannerModel}.`
          : 'Planner model reset to automatic cheapest supported selection.',
        'Command Result',
      );
      pushActivity(
        plannerModel
          ? `Planner model pinned to ${plannerModel}`
          : 'Planner model reset to automatic selection',
        'accent',
      );
      await refreshSidebarState(sessionIdRef.current, true);
      setStatus(plannerModel ? `planner ${plannerModel}` : 'planner auto');
    } catch (error) {
      const message = describeError(error);
      setStatus(message);
      appendLocalSystemMessage(message, 'Command Error');
      pushActivity(message, 'error');
    }
  };

  const toggleCurrentSessionToolPack = async (packId: string) => {
    const activeSessionId = sessionIdRef.current;
    if (!activeSessionId && draftChatRef.current) {
      setDraftChat((current) => {
        if (!current) {
          return current;
        }
        const draftEnabled = current.enabledToolPacks ?? [...DEFAULT_TOOL_PACK_IDS];
        const nextEnabled = draftEnabled.includes(packId)
          ? draftEnabled.filter((item) => item !== packId)
          : [...draftEnabled, packId];
        return {
          ...current,
          enabledToolPacks: nextEnabled,
        };
      });
      setPinnedToolPackInfoId(null);
      setHoveredToolPackInfoId(null);
      setToolPackInfoPopup(null);
      setStatus(`${currentEnabledToolPacks.includes(packId) ? 'disabled' : 'enabled'} ${TOOL_PACK_DEFINITIONS.find((item) => item.id === packId)?.label || packId}`);
      return;
    }
    if (!activeSessionId) {
      setStatus('open a chat before changing tool packs');
      return;
    }
    const currentlyEnabled = currentEnabledToolPacks.includes(packId);
    if (!currentlyEnabled && currentDisabledPackReasons[packId]) {
      setStatus(currentDisabledPackReasons[packId]);
      return;
    }
    const nextEnabled = currentlyEnabled
      ? currentEnabledToolPacks.filter((item) => item !== packId)
      : [...currentEnabledToolPacks, packId];
    setToolPackMutationInFlight(packId);
    try {
      const detail = await updateSessionToolPacks(apiBaseUrl, token, activeSessionId, {
        enabled_tool_packs: nextEnabled,
      });
      applySessionDetail(detail);
      setPinnedToolPackInfoId(null);
      setHoveredToolPackInfoId(null);
      setToolPackInfoPopup(null);
      await refreshSidebarState(activeSessionId, true);
      setStatus(`${currentlyEnabled ? 'disabled' : 'enabled'} ${TOOL_PACK_DEFINITIONS.find((item) => item.id === packId)?.label || packId}`);
    } catch (error) {
      setStatus(describeError(error));
    } finally {
      setToolPackMutationInFlight(null);
    }
  };

  const updateChatTelegramBotAssignment = async (targetSessionId: string, telegramBotConfigId: string | null) => {
    setSessionSettingsMutationInFlight(true);
    try {
      const detail = await updateSessionTelegramBotAssignment(apiBaseUrl, token, targetSessionId, {
        telegram_bot_config_id: telegramBotConfigId,
      });
      if (detail.id === sessionIdRef.current) {
        applySessionDetail(detail);
      }
      await refreshSidebarState(sessionIdRef.current, true);
      const nextBot = telegramBotConfigs.find((item) => item.id === (telegramBotConfigId || defaultTelegramBotConfigId)) || null;
      setStatus(nextBot ? `chat assigned to ${nextBot.label}` : 'chat bot assignment cleared');
    } catch (error) {
      setStatus(describeError(error));
    } finally {
      setSessionSettingsMutationInFlight(false);
    }
  };

  const updateChatHeadlessEligibility = async (targetSessionId: string, headlessEligible: boolean) => {
    setSessionSettingsMutationInFlight(true);
    try {
      const detail = await updateSessionHeadlessEligibility(apiBaseUrl, token, targetSessionId, {
        headless_eligible: headlessEligible,
      });
      if (detail.id === sessionIdRef.current) {
        applySessionDetail(detail);
      }
      await refreshSidebarState(sessionIdRef.current, true);
      setStatus(headlessEligible ? 'chat can be used for sleep mode' : 'chat removed from sleep eligibility');
    } catch (error) {
      setStatus(describeError(error));
    } finally {
      setSessionSettingsMutationInFlight(false);
    }
  };

  const setSleepChatForBot = async (botConfigId: string, targetSessionId: string | null) => {
    setSessionSettingsMutationInFlight(true);
    try {
      const nextRuntime = await configureHeadlessRuntime(apiBaseUrl, token, {
        default_sleep_session_by_bot: {
          [botConfigId]: targetSessionId,
        },
      });
      setOrchestratorStatus(nextRuntime);
      setStatus(targetSessionId ? 'sleep chat updated' : 'sleep chat cleared');
    } catch (error) {
      setStatus(describeError(error));
    } finally {
      setSessionSettingsMutationInFlight(false);
    }
  };

  const sendQueuedComposerSlice = (items: QueuedComposerMessage[], actionPolicy: InterruptPolicy) => {
    if (!items.length) {
      return;
    }
    setQueuedComposerMessages((current) => current.filter((entry) => !items.some((item) => item.id === entry.id)));
    items.forEach((item) => {
      queueMessage(item.text, item.sourceFormat, item.sessionId, actionPolicy);
    });
    setStatus(actionPolicy === 'after_tool' ? 'queued steering for the next safe tool boundary' : 'steering current run');
  };

  const sendText = async () => {
    const trimmed = input.trim();
    if (!trimmed) return;

    if (isDesktopSlashCommand(trimmed)) {
      setComposerInputValue('');
      setAssistantDraft('');
      setThinking('');
      setLastAssistantOutputAt(null);
      if (openCommandPanelForInput(trimmed)) {
        return;
      }
      await runSlashCommandFromComposer(trimmed);
      return;
    }

    let targetSessionId = sessionIdRef.current || null;
    const pendingProjectPath = draftChatRef.current?.projectPath || selectedProjectPath || '';
    if (!targetSessionId || draftChatRef.current) {
      try {
        targetSessionId = await ensureSessionForOutgoingMessage();
      } catch (error) {
        if (isBusySessionSwitchError(error) && pendingProjectPath) {
          setPendingSessionSwitch({
            mode: 'draft_send',
            projectPath: pendingProjectPath,
            text: trimmed,
            sourceFormat: 'app_text',
          });
          setStatus('current task is still running · stop it to start this new chat');
          return;
        }
        setStatus(describeError(error));
        return;
      }
      if (!targetSessionId) {
        setStatus('choose a folder to start a new chat');
        return;
      }
    }

    setComposerInputValue('');
    setAssistantDraft('');
    setThinking('');
    setLastAssistantOutputAt(null);
    setVoiceDraft('');

    if (agentRunActive) {
      if (interruptPolicy === 'none') {
        queueComposerMessage(trimmed, 'app_text', targetSessionId);
      } else {
        queueMessage(trimmed, 'app_text', targetSessionId, interruptPolicy);
      }
      return;
    }

    queueMessage(trimmed, 'app_text', targetSessionId);
  };

  const selectCommandSuggestion = async (command: string) => {
    setComposerInputValue('');
    setAssistantDraft('');
    setThinking('');
    setLastAssistantOutputAt(null);
    setDismissedCommandSuggestionInput(null);
    if (openCommandPanelForInput(command)) {
      return;
    }
    await runSlashCommandFromComposer(command);
  };

  const handleComposerKeyPress = (event: any) => {
    const nativeEvent = event.nativeEvent || {};
    if (nativeEvent.key !== 'Enter' || nativeEvent.shiftKey) {
      return;
    }

    event.preventDefault?.();
    void sendText();
  };

  useEffect(() => {
    if (!apiBaseUrl || !token) return;
    if (!sessionId) {
      startupChatSocketReadyRef.current = true;
      setSocketState('idle');
      maybeResolveStartupReady();
      return;
    }

    let disposed = false;

    const connect = () => {
      if (disposed) return;
      const wsBase = buildWsBaseUrl(apiBaseUrl);
      if (!wsBase) {
        setSocketState('missing backend');
        return;
      }

      const params = new URLSearchParams({
        token,
        client_id: appClientIdRef.current,
      });
      if (sessionIdRef.current) {
        params.set('session_id', sessionIdRef.current);
      }

      setSocketState('connecting');
      emitStartupState('warming', 'Connecting chat');
      const ws = new WebSocket(`${wsBase}/ws/app/chat?${params.toString()}`);
      chatWsRef.current = ws;

      ws.onopen = () => {
        if (disposed) return;
        setSocketState('connected');
        startupChatSocketReadyRef.current = true;
        flushPendingMessages();
        maybeResolveStartupReady();
      };

      ws.onmessage = (messageEvent) => {
        if (disposed) return;
        try {
          handleRealtimeEvent(JSON.parse(String(messageEvent.data || '{}')) as RealtimeEvent, 'chat');
        } catch (error) {
          pushActivity(`Failed to parse websocket event: ${describeError(error)}`, 'warn');
        }
      };

      ws.onclose = () => {
        if (chatWsRef.current === ws) {
          chatWsRef.current = null;
        }
        if (!disposed) {
          startupChatSocketReadyRef.current = false;
          setSocketState('reconnecting');
          reconnectRef.current = setTimeout(connect, SOCKET_RECONNECT_MS);
        }
      };

      ws.onerror = () => {
        startupChatSocketReadyRef.current = false;
        setSocketState('error');
      };
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
        reconnectRef.current = null;
      }
      if (chatWsRef.current) {
        chatWsRef.current.close();
        chatWsRef.current = null;
      }
    };
  }, [apiBaseUrl, token]);

  useEffect(() => {
    if (!apiBaseUrl || !token) {
      setVoiceState('unavailable');
      setVoiceRunning(false);
      return;
    }
    if (!sessionId) {
      setVoiceState('idle');
      setVoiceRunning(false);
      return;
    }

    let disposed = false;
    const connect = () => {
      if (disposed) return;
      const wsBase = buildWsBaseUrl(apiBaseUrl);
      if (!wsBase) {
        setVoiceState('unavailable');
        return;
      }

      const params = new URLSearchParams({
        token,
        client_id: appClientIdRef.current,
      });
      if (sessionIdRef.current) {
        params.set('session_id', sessionIdRef.current);
      }

      setVoiceState('connecting');
      const ws = new WebSocket(`${wsBase}/ws/app/voice?${params.toString()}`);
      voiceWsRef.current = ws;

      ws.onopen = () => {
        if (disposed) return;
        setVoiceState('ready');
        setVoiceError(null);
        logDiagnostic('desktop.voice.ws', 'connected', { sessionId: sessionIdRef.current || null });
      };

      ws.onmessage = (messageEvent) => {
        if (disposed) return;
        try {
          handleRealtimeEvent(JSON.parse(String(messageEvent.data || '{}')) as RealtimeEvent, 'voice');
        } catch (error) {
          const message = describeError(error);
          pushActivity(`Voice websocket parse failed: ${message}`, 'warn');
          logDiagnostic('desktop.voice.ws', 'message parse failed', message, 'warn');
        }
      };

      ws.onclose = () => {
        if (voiceWsRef.current === ws) {
          voiceWsRef.current = null;
        }
        if (!disposed) {
          voicePressActiveRef.current = false;
          alwaysOnEnabledRef.current = false;
          setAlwaysOnEnabled(false);
          stopVoiceTracks();
          voiceRunningRef.current = false;
          voiceRecordingRef.current = false;
          setVoiceRunning(false);
          setVoiceRecording(false);
          setVoiceState('reconnecting');
          voiceReconnectRef.current = setTimeout(connect, SOCKET_RECONNECT_MS);
        }
      };

      ws.onerror = () => {
        voicePressActiveRef.current = false;
        alwaysOnEnabledRef.current = false;
        setAlwaysOnEnabled(false);
        stopVoiceTracks();
        voiceRunningRef.current = false;
        voiceRecordingRef.current = false;
        setVoiceRunning(false);
        setVoiceRecording(false);
        setVoiceState('error');
        setVoiceError('voice socket error');
      };
    };

    connect();

    return () => {
      disposed = true;
      if (voiceReconnectRef.current) {
        clearTimeout(voiceReconnectRef.current);
        voiceReconnectRef.current = null;
      }
      if (voiceWsRef.current) {
        voiceWsRef.current.close();
        voiceWsRef.current = null;
      }
      alwaysOnEnabledRef.current = false;
      setAlwaysOnEnabled(false);
      stopVoiceTracks();
      resetVoiceCaptureBuffers();
      voiceRunningRef.current = false;
      voiceRecordingRef.current = false;
      void cleanupAssistantAudio();
    };
  }, [apiBaseUrl, sessionId, selectedVoiceEngine, token]);

  const startVoiceCapture = async () => {
    if (!apiBaseUrl || !token) {
      voicePressActiveRef.current = false;
      setVoiceState('unavailable');
      setStatus('voice unavailable');
      return;
    }
    if (!sessionIdRef.current) {
      voicePressActiveRef.current = false;
      setStatus('start a chat first to enable voice');
      return;
    }
    if (selectedVoiceEngine === VOICE_ENGINE_NONE || liveVoiceStatus?.input_ok === false) {
      voicePressActiveRef.current = false;
      setStatus(liveVoiceStatus?.issues?.[0] || 'Select an English or Hebrew voice path first.');
      return;
    }
    if (voiceEngineChanging || selectedVoiceEngineState === 'warming') {
      voicePressActiveRef.current = false;
      setStatus('Hebrew voice path is still warming up');
      return;
    }
    if (!voiceWsRef.current || voiceWsRef.current.readyState !== WebSocket.OPEN) {
      voicePressActiveRef.current = false;
      setStatus('voice socket unavailable');
      return;
    }
    if (alwaysOnEnabledRef.current) {
      setStatus('always-on voice is already active');
      return;
    }
    if (voiceRecording) {
      return;
    }
    if (voiceRunning) {
      voicePressActiveRef.current = false;
      setStatus('voice still processing');
      return;
    }
    if (!globalThis.navigator?.mediaDevices?.getUserMedia) {
      voicePressActiveRef.current = false;
      setVoiceState('error');
      setVoiceError('Microphone capture is not available in this desktop renderer.');
      return;
    }

    try {
      voicePressActiveRef.current = true;
      voiceCaptureModeRef.current = 'push_to_talk';
      setVoiceMode('push_to_talk');
      await cleanupAssistantAudio();
      const stream = await globalThis.navigator.mediaDevices.getUserMedia({ audio: true });
      if (!voicePressActiveRef.current) {
        for (const track of stream.getTracks()) {
          track.stop();
        }
        return;
      }
      voiceStreamRef.current = stream;
      const context = createAudioContext();
      voiceAudioContextRef.current = context;
      if (context.state === 'suspended') {
        await context.resume();
      }
      voiceSampleRateRef.current = context.sampleRate;
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(VOICE_PROCESSOR_BUFFER_SIZE, 1, 1);
      voiceAudioSourceRef.current = source;
      voiceProcessorRef.current = processor;
      processor.onaudioprocess = (event) => {
        const input = event.inputBuffer.getChannelData(0);
        processVoiceSamples(new Float32Array(input));
      };
      source.connect(processor);
      processor.connect(context.destination);
      if (!beginVoiceSegment('push_to_talk')) {
        stopVoiceTracks();
      }
    } catch (error) {
      stopVoiceTracks();
      voicePressActiveRef.current = false;
      voiceRecordingRef.current = false;
      voiceRunningRef.current = false;
      setVoiceRecording(false);
      setVoiceRunning(false);
      setVoiceState('error');
      setVoiceError(describeError(error));
      setStatus(describeError(error));
      logDiagnostic('desktop.voice.ws', 'voice start failed', describeError(error), 'error');
    }
  };

  const stopVoiceCapture = async (commit: boolean) => {
    voicePressActiveRef.current = false;
    stopVoiceTracks();
    await finishVoiceSegment(commit, 'push_to_talk');
  };

  const startAlwaysOnVoice = async () => {
    if (!apiBaseUrl || !token) {
      setVoiceState('unavailable');
      setStatus('voice unavailable');
      return;
    }
    if (!sessionIdRef.current) {
      setStatus('start a chat first to enable voice');
      return;
    }
    if (selectedVoiceEngine === VOICE_ENGINE_NONE || liveVoiceStatus?.input_ok === false) {
      setStatus(liveVoiceStatus?.issues?.[0] || 'Select an English or Hebrew voice path first.');
      return;
    }
    if (voiceEngineChanging || selectedVoiceEngineState === 'warming') {
      setStatus('Hebrew voice path is still warming up');
      return;
    }
    if (!voiceWsRef.current || voiceWsRef.current.readyState !== WebSocket.OPEN) {
      setStatus('voice socket unavailable');
      return;
    }
    if (!globalThis.navigator?.mediaDevices?.getUserMedia) {
      setVoiceState('error');
      setVoiceError('Microphone capture is not available in this desktop renderer.');
      return;
    }
    if (alwaysOnEnabledRef.current) {
      return;
    }

    try {
      await cleanupAssistantAudio();
      voiceCaptureModeRef.current = 'always_on';
      alwaysOnEnabledRef.current = true;
      setVoiceMode('always_on');
      setAlwaysOnEnabled(true);
      setVoiceDraft('');
      setVoiceError(null);
      voiceRunningRef.current = false;
      voiceRecordingRef.current = false;
      setVoiceRunning(false);
      setVoiceRecording(false);
      setVoiceState('always_on');
      setStatus('always-on voice listening');
      voiceGateStateRef.current = createVoiceGateState();
      deferredAlwaysOnFramesRef.current = [];
      deferredAlwaysOnSampleCountRef.current = 0;
      const stream = await globalThis.navigator.mediaDevices.getUserMedia({ audio: true });
      if (!alwaysOnEnabledRef.current) {
        for (const track of stream.getTracks()) {
          track.stop();
        }
        return;
      }
      voiceStreamRef.current = stream;
      const context = createAudioContext();
      voiceAudioContextRef.current = context;
      if (context.state === 'suspended') {
        await context.resume();
      }
      voiceSampleRateRef.current = context.sampleRate;
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(VOICE_PROCESSOR_BUFFER_SIZE, 1, 1);
      voiceAudioSourceRef.current = source;
      voiceProcessorRef.current = processor;
      processor.onaudioprocess = (event) => {
        const input = event.inputBuffer.getChannelData(0);
        processVoiceSamples(new Float32Array(input));
      };
      source.connect(processor);
      processor.connect(context.destination);
      pushActivity('Always-on local Whisper voice mode enabled.', 'accent');
    } catch (error) {
      alwaysOnEnabledRef.current = false;
      setAlwaysOnEnabled(false);
      stopVoiceTracks();
      voiceRecordingRef.current = false;
      voiceRunningRef.current = false;
      setVoiceRecording(false);
      setVoiceRunning(false);
      setVoiceState('error');
      setVoiceError(describeError(error));
      setStatus(describeError(error));
      logDiagnostic('desktop.voice.ws', 'always-on voice start failed', describeError(error), 'error');
    }
  };

  const stopAlwaysOnVoice = async () => {
    alwaysOnEnabledRef.current = false;
    setAlwaysOnEnabled(false);
    const wasRecording = voiceGateStateRef.current.recording || voiceRecording;
    voiceGateStateRef.current = createVoiceGateState();
    deferredAlwaysOnFramesRef.current = [];
    deferredAlwaysOnSampleCountRef.current = 0;
    stopVoiceTracks();
    if (wasRecording) {
      await finishVoiceSegment(false, 'always_on');
    } else {
      voiceRecordingRef.current = false;
      voiceRunningRef.current = false;
      setVoiceRecording(false);
      setVoiceRunning(false);
      setVoiceState('ready');
      setStatus('always-on voice stopped');
    }
  };

  const cancelAlwaysOnSegment = async () => {
    voiceGateStateRef.current = createVoiceGateState();
    deferredAlwaysOnFramesRef.current = [];
    deferredAlwaysOnSampleCountRef.current = 0;
    await finishVoiceSegment(false, 'always_on');
  };

  const isBusySessionSwitchError = (error: unknown) => (
    describeError(error).toLowerCase().includes('finish or stop the current task')
  );

  const isRecoverableSessionActivationError = (error: unknown) => {
    const detail = describeError(error).toLowerCase();
    return (
      detail.includes('failed to fetch')
      || detail.includes('networkerror')
      || detail.includes('network request failed')
      || detail.includes('load failed')
    );
  };

  const activateSessionWithRecovery = async (targetSessionId: string) => {
    try {
      return await activateSession(apiBaseUrl, token, targetSessionId);
    } catch (error) {
      if (!isRecoverableSessionActivationError(error)) {
        throw error;
      }

      setStatus('reconnecting local runtime');
      await loadDesktopBootstrap({ force: true }).catch(() => null);
      await new Promise((resolve) => setTimeout(resolve, 700));
      return activateSession(apiBaseUrl, token, targetSessionId);
    }
  };

  const selectedProjectPathCandidate = normalizeWorkspacePath(
    draftChat?.projectPath
    || sidebarState.selectedProjectPath
    || sidebarState.lastSelectedProjectPath
    || sessions.find((item) => item.id === sessionIdRef.current)?.workspace
    || '',
  );
  const selectedProjectPath = isWorkspacePathAllowed(selectedProjectPathCandidate, allowedWorkspaceRoot)
    ? selectedProjectPathCandidate
    : '';
  const preferredProjectPath = selectedProjectPath || allowedWorkspaceRoot;
  const preferredFolderPickerPath = isWorkspacePathAllowed(preferredProjectPath, allowedWorkspaceRoot)
    ? preferredProjectPath
    : (allowedWorkspaceRoot || preferredProjectPath || null);
  const emptyConversationProjectPath = normalizeWorkspacePath(
    draftChat?.projectPath
    || selectedProjectPath
    || currentWorkspaceBySessionRef.current[sessionIdRef.current || '']
    || sessions.find((item) => item.id === sessionIdRef.current)?.workspace
    || '',
  );
  const emptyConversationProjectName = emptyConversationProjectPath
    ? projectPathBasename(emptyConversationProjectPath)
    : '';

  const buildDraftChatState = (
    projectPath: string,
    telegramBotConfigId?: string | null,
  ): SidebarDraftChat => {
    const currentSessionSummary = sessions.find((item) => item.id === sessionIdRef.current || item.id === sessionId) || null;
    const nextDraftModel = strOrNull(
      overview?.current_model
      || currentSessionSummary?.model
      || cachedModelGroups[0]?.models?.[0]
      || '',
    );
    const nextDraftVariant = strOrNull(overview?.current_variant || '');
    const nextDraftPlannerModel = strOrNull(
      overview?.planner_model
      || configuredPlannerModels[0]
      || cachedPlannerModels[0]
      || '',
    );
    const nextDraftEnabledToolPacks = Array.isArray(overview?.enabled_tool_packs) && overview.enabled_tool_packs.length > 0
      ? [...overview.enabled_tool_packs]
      : Array.isArray(currentSessionSummary?.enabled_tool_packs) && currentSessionSummary.enabled_tool_packs.length > 0
        ? [...currentSessionSummary.enabled_tool_packs]
        : [...DEFAULT_TOOL_PACK_IDS];
    return {
      id: SIDEBAR_DRAFT_CHAT_ID,
      projectPath,
      title: 'New chat',
      telegramBotConfigId: strOrNull(telegramBotConfigId) || defaultTelegramBotConfigId,
      model: nextDraftModel,
      variant: nextDraftVariant,
      plannerModel: nextDraftPlannerModel,
      enabledToolPacks: nextDraftEnabledToolPacks,
      selectedBranch: null,
    };
  };

  const resetConversationForDraft = (projectPath: string) => {
    setSessionId(undefined);
    setSessionName('New chat');
    setMessages([]);
    setTimelineEvents([]);
    setTaskBoardArmedNextTurnState(false);
    setRuntimeRunState('idle');
    setTaskBoard(null);
    setCompletedTaskBoards([]);
    setTaskBoardCollapsed(false);
    setExpandedCompletedTaskIds({});
    setAssistantDraft('');
    setThinking('');
    setShowReferenceRail(false);
    selectProjectPath(projectPath);
  };

  const clearConversationSelection = (projectPath?: string | null) => {
    setSessionId(undefined);
    setSessionName('New chat');
    setMessages([]);
    setTimelineEvents([]);
    setOverview(null);
    setTaskBoardArmedNextTurnState(false);
    setRuntimeRunState('idle');
    setTaskBoard(null);
    setCompletedTaskBoards([]);
    setTaskBoardCollapsed(false);
    setExpandedCompletedTaskIds({});
    setAssistantDraft('');
    setThinking('');
    setShowReferenceRail(false);
    if (projectPath) {
      selectProjectPath(projectPath);
    }
  };

  const resolveAllowedProjectPath = async (projectPath: string) => {
    const normalized = normalizeWorkspacePath(projectPath);
    if (!normalized) {
      return { requestedPath: '', targetPath: '', status: null as DesktopPathStatus | null };
    }

    const knownStatus = projectPathStatuses[normalized] || null;
    const status = knownStatus || await getDesktopPathStatus(normalized).catch(() => null);
    const resolvedStatusPath = normalizeWorkspacePath(status?.resolvedPath || '');
    const fallbackRootCandidate = (
      !isAbsoluteWindowsPath(normalized) && allowedWorkspaceRoot
        ? normalizeWorkspacePath(`${allowedWorkspaceRoot}\\${normalized.replace(/^\\+/, '')}`)
        : ''
    );
    const allowedCandidates = [
      resolvedStatusPath,
      normalized,
      fallbackRootCandidate,
    ].filter((candidate, index, values) => (
      Boolean(candidate)
      && values.indexOf(candidate) === index
      && isWorkspacePathAllowed(candidate, allowedWorkspaceRoot)
    ));

    let targetPath = allowedCandidates[0] || '';
    if (!targetPath && fallbackRootCandidate) {
      const fallbackStatus = await getDesktopPathStatus(fallbackRootCandidate).catch(() => null);
      if (fallbackStatus?.exists && fallbackStatus.isDirectory) {
        targetPath = normalizeWorkspacePath(fallbackStatus.resolvedPath || fallbackRootCandidate) || fallbackRootCandidate;
      }
    }

    return {
      requestedPath: normalized,
      targetPath,
      status,
    };
  };

  const promptForProjectFolder = async () => {
    const picked = await pickDesktopFolder(preferredFolderPickerPath || null);
    if (!picked) {
      return null;
    }
    const normalized = normalizeWorkspacePath(picked);
    if (!isWorkspacePathAllowed(normalized, allowedWorkspaceRoot)) {
      setStatus(
        allowedWorkspaceRoot
          ? `Choose a folder inside ${allowedWorkspaceRoot}`
          : 'Choose a valid workspace folder',
      );
      return null;
    }
    updateSidebarState((current) => {
      const ensured = ensureSidebarProjectEntry(current, normalized);
      return {
        ...ensured,
        selectedProjectPath: normalized,
        lastSelectedProjectPath: normalized,
        projects: {
          ...ensured.projects,
          [normalized]: {
            ...(ensured.projects[normalized] || {}),
            hidden: false,
          },
        },
      };
    });
    setSidebarExpanded(true);
    return normalized;
  };

  const resolveProjectPathForNewChat = async (projectPath: string) => {
    const { requestedPath, targetPath, status } = await resolveAllowedProjectPath(projectPath);
    if (!requestedPath) {
      return null;
    }
    if (!targetPath) {
      setStatus(`"${projectPathBasename(requestedPath)}" is outside the current workspace root · choose a replacement folder`);
      const replacement = await promptForProjectFolder();
      return replacement || null;
    }
    if (!status) {
      return targetPath;
    }
    if (status.exists && status.isDirectory) {
      return normalizeWorkspacePath(status.resolvedPath || targetPath) || targetPath;
    }

    setStatus(`"${projectPathBasename(targetPath)}" is no longer available · choose a replacement folder`);
    const replacement = await promptForProjectFolder();
    return replacement || null;
  };

  const openDraftChat = async (projectPath: string, telegramBotConfigId?: string | null) => {
    const resolvedProjectPath = await resolveProjectPathForNewChat(projectPath);
    if (!resolvedProjectPath) {
      return;
    }
    const resolvedBotConfigId = strOrNull(telegramBotConfigId) || defaultTelegramBotConfigId;
    if (!resolvedBotConfigId && telegramBotConfigs.length > 1) {
      setPendingDraftBotProjectPath(resolvedProjectPath);
      setSidebarExpanded(true);
      return;
    }
    discardDraftChat({ clearInput: true });
    const nextDraft = buildDraftChatState(resolvedProjectPath, resolvedBotConfigId);
    setSidebarExpanded(true);
    setPendingDraftBotProjectPath(null);
    resetConversationForDraft(resolvedProjectPath);
    setDraftChat(nextDraft);
    setStatus(`new chat in ${projectPathBasename(resolvedProjectPath)}`);
  };

  const confirmDraftBotSelection = async (telegramBotConfigId: string | null) => {
    const pendingProjectPath = pendingDraftBotProjectPath;
    setPendingDraftBotProjectPath(null);
    if (!pendingProjectPath) {
      return;
    }
    await openDraftChat(pendingProjectPath, telegramBotConfigId);
  };

  const chooseDraftProjectFolder = async () => {
    if (!draftChatRef.current) {
      return;
    }
    const pickedProject = await promptForProjectFolder();
    if (!pickedProject) {
      return;
    }
    resetConversationForDraft(pickedProject);
    setDraftChat((current) => (
      current
        ? {
            ...current,
            projectPath: pickedProject,
            selectedBranch: null,
          }
        : current
    ));
    setActiveCommandPanel((current) => (
      current?.kind === 'draftBranch' || current?.kind === 'draftProject'
        ? null
        : current
    ));
    setStatus(`draft folder ${projectPathBasename(pickedProject)}`);
  };

  const chooseDraftProject = (projectPath: string) => {
    const normalized = normalizeWorkspacePath(projectPath);
    const currentDraft = draftChatRef.current;
    if (!currentDraft || !normalized) {
      return;
    }
    if (normalizeWorkspacePath(currentDraft.projectPath) === normalized) {
      selectProjectPath(normalized);
      setActiveCommandPanel((current) => current?.kind === 'draftProject' ? null : current);
      return;
    }
    resetConversationForDraft(normalized);
    setDraftChat((current) => (
      current
        ? {
            ...current,
            projectPath: normalized,
            selectedBranch: null,
          }
        : current
    ));
    setDraftGitRepoState(null);
    setActiveCommandPanel((current) => (
      current?.kind === 'draftBranch' || current?.kind === 'draftProject'
        ? null
        : current
    ));
    setStatus(`draft folder ${projectPathBasename(normalized)}`);
  };

  const chooseDraftBranch = (branchName: string) => {
    if (!draftChatRef.current) {
      return;
    }
    setDraftChat((current) => (
      current
        ? {
            ...current,
            selectedBranch: branchName,
          }
        : current
    ));
    setActiveCommandPanel((current) => current?.kind === 'draftBranch' ? null : current);
    setStatus(`draft branch ${branchName}`);
  };

  const beginNewChat = async () => {
    let targetProject = preferredProjectPath;
    if (!targetProject) {
      targetProject = await promptForProjectFolder() || '';
    }
    if (!targetProject) {
      setStatus('choose a folder to start a new chat');
      return;
    }
    await openDraftChat(targetProject);
  };

  const materializeDraftSession = async (projectPath: string) => {
    const { requestedPath, targetPath, status } = await resolveAllowedProjectPath(projectPath);
    if (!requestedPath || !targetPath) {
      throw new Error(
        allowedWorkspaceRoot
          ? `Choose a folder inside ${allowedWorkspaceRoot}`
          : 'Choose a folder to start a new chat',
      );
    }
    const targetProjectPath = targetPath;
    const pathStatus = status || await getDesktopPathStatus(targetProjectPath).catch(() => null);
    if (pathStatus && (!pathStatus.exists || !pathStatus.isDirectory)) {
      throw new Error(`"${projectPathBasename(targetProjectPath)}" is no longer available. Choose another folder for the new chat.`);
    }
    setStatus('creating chat');
    const draftSnapshot = draftChatRef.current;
    const selectedDraftBranch = strOrNull(draftSnapshot?.selectedBranch);
    if (selectedDraftBranch) {
      setStatus(`switching to ${selectedDraftBranch}`);
      const switchedBranch = await checkoutDesktopGitBranch(targetProjectPath, selectedDraftBranch).catch(() => null);
      if (switchedBranch?.error) {
        throw new Error(String(switchedBranch.error));
      }
    }
    setStatus('creating chat');
    const created = await createSession(apiBaseUrl, token, {
      workspace: targetProjectPath,
      telegram_bot_config_id: draftSnapshot?.telegramBotConfigId || defaultTelegramBotConfigId,
      enabled_tool_packs: draftSnapshot?.enabledToolPacks ?? [...DEFAULT_TOOL_PACK_IDS],
    });
    const draftModel = strOrNull(draftSnapshot?.model);
    const draftVariant = strOrNull(draftSnapshot?.variant);
    const draftPlannerModel = draftSnapshot?.plannerModel === undefined
      ? undefined
      : draftSnapshot?.plannerModel;
    const nextConfigPayload: Record<string, unknown> = {};
    if (draftModel && draftModel !== created.session.model) {
      nextConfigPayload.model = draftModel;
    }
    if (draftVariant && draftVariant !== created.session.variant) {
      nextConfigPayload.variant = draftVariant;
    }
    if (draftPlannerModel !== undefined && draftPlannerModel !== created.session.planner_model) {
      nextConfigPayload.planner_model = draftPlannerModel;
    }
    if (Object.keys(nextConfigPayload).length > 0) {
      await configureAgent(apiBaseUrl, token, nextConfigPayload, created.session.id);
    }
    applySessionDetail(created.session);
    await Promise.all([
      refreshSidebarCollections(created.session.id, true),
      refreshOverviewState(created.session.id, { quiet: true }),
    ]);
    return created.session.id;
  };

  const ensureSessionForOutgoingMessage = async () => {
    if (sessionIdRef.current) {
      return sessionIdRef.current;
    }

    if (draftChatRef.current) {
      return materializeDraftSession(draftChatRef.current.projectPath);
    }

    let targetProject = preferredProjectPath;
    if (!targetProject) {
      targetProject = await promptForProjectFolder() || '';
    }
    if (!targetProject) {
      return null;
    }

    return materializeDraftSession(targetProject);
  };

  const openSession = async (
    nextSessionId: string,
    options?: { jumpMessageIndex?: number | null; projectPath?: string | null },
  ) => {
    if (!nextSessionId) {
      return;
    }
    if (nextSessionId === sessionIdRef.current && !draftChatRef.current) {
      if (typeof options?.jumpMessageIndex === 'number') {
        setPendingSearchJump({
          sessionId: nextSessionId,
          messageIndex: options.jumpMessageIndex,
          attempt: 0,
        });
      }
      if (options?.projectPath) {
        revealProjectInSidebar(options.projectPath);
      }
      return;
    }

    discardDraftChat({ clearInput: true });
    setOpenSessionMenuId(null);
    if (options?.projectPath) {
      revealProjectInSidebar(options.projectPath);
    }
    setStatus('switching shared session');
    setAssistantDraft('');
    setThinking('');
    try {
      const detail = await activateSessionWithRecovery(nextSessionId);
      applySessionDetail(detail);
      await Promise.all([
        refreshSidebarCollections(nextSessionId, true),
        refreshOverviewState(nextSessionId, { quiet: true }),
      ]);
      if (typeof options?.jumpMessageIndex === 'number') {
        setPendingSearchJump({
          sessionId: nextSessionId,
          messageIndex: options.jumpMessageIndex,
          attempt: 0,
        });
      }
    } catch (error) {
      if (isBusySessionSwitchError(error)) {
        setPendingSessionSwitch({
          mode: 'session',
          sessionId: nextSessionId,
          jumpMessageIndex: options?.jumpMessageIndex ?? null,
        });
        setStatus('current task is still running · stop it to switch chats');
        return;
      }
      setStatus(describeError(error));
    }
  };

  const confirmPendingSessionSwitch = async () => {
    if (!pendingSessionSwitch) {
      return;
    }

    const nextAction = pendingSessionSwitch;
    setPendingSessionSwitch(null);
    setStatus('stopping current run');
    try {
      await controlAgentRun(apiBaseUrl, token, 'stop', sessionIdRef.current);
      await refreshSidebarState(sessionIdRef.current, true);
      if (nextAction.mode === 'session') {
        await openSession(nextAction.sessionId, {
          jumpMessageIndex: nextAction.jumpMessageIndex ?? null,
        });
        return;
      }

      const nextSessionId = await materializeDraftSession(nextAction.projectPath);
      pendingMessagesRef.current.push({
        text: nextAction.text,
        sourceFormat: nextAction.sourceFormat,
        interruptPolicy,
        sessionId: nextSessionId,
      });
      setMessages((previous) => [
        ...previous,
        {
          role: 'user',
          content: nextAction.text,
          timestamp: new Date().toISOString(),
          displayLabel: nextAction.sourceFormat === 'app_voice_transcript' ? 'Voice' : 'You',
          channel: 'app',
          sourceFormat: nextAction.sourceFormat,
          messageKey: `pending:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
          pending: true,
        },
      ]);
      flushPendingMessages();
      setStatus(nextAction.sourceFormat === 'app_voice_transcript' ? 'sending voice transcript' : 'sending message');
    } catch (error) {
      setStatus(describeError(error));
    }
  };

  const dismissPendingSessionSwitch = () => {
    if (!pendingSessionSwitch) {
      return;
    }
    if (pendingSessionSwitch.mode === 'draft_send') {
      setComposerInputValue(pendingSessionSwitch.text);
      setStatus('kept the draft message unsent');
    } else {
      setStatus('chat switch cancelled');
    }
    setPendingSessionSwitch(null);
  };

  const toggleProjectPin = (projectPath: string) => {
    const normalized = normalizeWorkspacePath(projectPath);
    updateSidebarState((current) => {
      const ensured = ensureSidebarProjectEntry(current, normalized);
      const existing = ensured.projects[normalized] || {};
      return {
        ...ensured,
        projects: {
          ...ensured.projects,
          [normalized]: {
            ...existing,
            pinned: !existing.pinned,
          },
        },
      };
    });
  };

  const toggleSessionPin = (sessionEntry: SessionSummary) => {
    updateSidebarState((current) => {
      const existing = current.sessionMeta[sessionEntry.id] || {};
      return {
        ...current,
        sessionMeta: {
          ...current.sessionMeta,
          [sessionEntry.id]: {
            ...existing,
            pinned: !existing.pinned,
          },
        },
      };
    });
  };

  const toggleProjectCollapsed = (projectPath: string) => {
    const normalized = normalizeWorkspacePath(projectPath);
    updateSidebarState((current) => {
      const ensured = ensureSidebarProjectEntry(current, normalized);
      const existing = ensured.projects[normalized] || {};
      return {
        ...ensured,
        projects: {
          ...ensured.projects,
          [normalized]: {
            ...existing,
            collapsed: !existing.collapsed,
          },
        },
      };
    });
  };

  const renameProject = (projectPath: string) => {
    const normalized = normalizeWorkspacePath(projectPath);
    if (!normalized) {
      return;
    }
    const existingState = sidebarState.projects[normalized] || {};
    const currentName = projectDisplayName(normalized, existingState);
    const promptValue = globalThis.prompt?.('Rename folder in sidebar', currentName);
    if (typeof promptValue !== 'string') {
      return;
    }
    const nextName = promptValue.trim();
    updateSidebarState((current) => {
      const ensured = ensureSidebarProjectEntry(current, normalized);
      const existing = ensured.projects[normalized] || {};
      return {
        ...ensured,
        projects: {
          ...ensured.projects,
          [normalized]: {
            ...existing,
            displayName: nextName || null,
            hidden: false,
          },
        },
      };
    });
    setOpenProjectMenuPath(null);
  };

  const removeProjectFromSidebar = (projectPath: string) => {
    const normalized = normalizeWorkspacePath(projectPath);
    if (!normalized) {
      return;
    }
    const projectName = projectDisplayName(normalized, sidebarState.projects[normalized] || {});
    const confirmed = globalThis.confirm
      ? globalThis.confirm(`Remove "${projectName}" from the sidebar? This will not delete any files.`)
      : true;
    if (!confirmed) {
      return;
    }
    if (draftChatRef.current?.projectPath === normalized) {
      discardDraftChat({ clearInput: true });
    }
    updateSidebarState((current) => {
      const ensured = ensureSidebarProjectEntry(current, normalized);
      const existing = ensured.projects[normalized] || {};
      const fallbackProjectPath = [...ensured.projectOrder, ...Object.keys(ensured.projects)]
        .map((item) => normalizeWorkspacePath(item))
        .find((item) => item && item !== normalized && !ensured.projects[item]?.hidden) || null;
      return {
        ...ensured,
        selectedProjectPath: ensured.selectedProjectPath === normalized ? fallbackProjectPath : ensured.selectedProjectPath,
        lastSelectedProjectPath: ensured.lastSelectedProjectPath === normalized ? fallbackProjectPath : ensured.lastSelectedProjectPath,
        projects: {
          ...ensured.projects,
          [normalized]: {
            ...existing,
            hidden: true,
          },
        },
      };
    });
    setOpenProjectMenuPath(null);
  };

  const deleteSidebarSession = async (session: SessionSummary) => {
    if (!session?.id) {
      return;
    }
    const confirmed = globalThis.confirm
      ? globalThis.confirm(`Delete "${session.name}"? This will permanently remove the chat history for this conversation.`)
      : true;
    if (!confirmed) {
      return;
    }

    setOpenSessionMenuId(null);
    setStatus(`deleting ${session.name}`);

    try {
      const result = await deleteSession(apiBaseUrl, token, session.id);
      const nextCurrentSessionId = result.current_session_id || null;
      if (sessionIdRef.current === session.id && !nextCurrentSessionId) {
        clearConversationSelection(normalizeWorkspacePath(session.workspace) || selectedProjectPath);
      }
      await refreshSidebarState(nextCurrentSessionId, true);
      setStatus(nextCurrentSessionId ? 'ready' : 'chat deleted');
      pushActivity(`Deleted chat: ${session.name}`, 'accent');
    } catch (error) {
      const message = describeError(error);
      setStatus(message);
      pushActivity(`Delete chat failed: ${message}`, 'error');
    }
  };

  const moveProjectOrder = (draggedProjectPath: string, targetProjectPath: string) => {
    const dragged = normalizeWorkspacePath(draggedProjectPath);
    const target = normalizeWorkspacePath(targetProjectPath);
    if (!dragged || !target || dragged === target) {
      return;
    }
    updateSidebarState((current) => {
      const ensured = ensureSidebarProjectEntries(current, [dragged, target]);
      const order = [...ensured.projectOrder.filter((item) => item !== dragged)];
      const targetIndex = order.indexOf(target);
      if (targetIndex < 0) {
        order.push(dragged);
      } else {
        order.splice(targetIndex, 0, dragged);
      }
      return {
        ...ensured,
        projectOrder: order,
      };
    });
  };

  const moveSessionOrder = (projectPath: string, draggedSessionId: string, targetSessionId: string) => {
    if (!draggedSessionId || !targetSessionId || draggedSessionId === targetSessionId) {
      return;
    }
    const normalizedProjectPath = normalizeWorkspacePath(projectPath);
    const projectSessions = sessions
      .filter((item) => normalizeWorkspacePath(item.workspace) === normalizedProjectPath)
      .sort((left, right) => sessionSidebarSortComparator(left, right, sidebarState.sessionMeta));
    const order = projectSessions.map((item) => item.id).filter((sessionEntryId) => sessionEntryId !== draggedSessionId);
    const targetIndex = order.indexOf(targetSessionId);
    if (targetIndex < 0) {
      return;
    }
    order.splice(targetIndex, 0, draggedSessionId);
    updateSidebarState((current) => {
      const nextSessionMeta = { ...current.sessionMeta };
      order.forEach((sessionEntryId, index) => {
        nextSessionMeta[sessionEntryId] = {
          ...(nextSessionMeta[sessionEntryId] || {}),
          order: index,
        };
      });
      return {
        ...current,
        sessionMeta: nextSessionMeta,
      };
    });
  };

  const runControl = async (action: 'pause' | 'stop' | 'restart') => {
    setStatus(`${action} requested`);
    try {
      await controlAgentRun(apiBaseUrl, token, action, sessionIdRef.current);
      if (action === 'stop') {
        setChatRunActive(false);
        setRuntimeRunState('idle');
        setAssistantDraft('');
        setThinking('');
        setTaskBoard(null);
        setOverview((previous) => (
          previous
            ? {
                ...previous,
                run_state: 'idle',
                task_board: null,
              }
            : previous
        ));
      }
      pushActivity(`Run control: ${action}`, action === 'stop' ? 'warn' : 'accent');
      await refreshSidebarState(sessionIdRef.current, true);
    } catch (error) {
      setStatus(describeError(error));
    }
  };

  const toggleTaskBoardArmNextTurn = async () => {
    const activeSessionId = sessionIdRef.current;
    if (!activeSessionId) {
      setStatus('select a shared chat before arming long task mode');
      return;
    }

    const nextArmed = !taskBoardArmedNextTurn;
    setStatus(nextArmed ? 'arming long task mode for the next message' : 'disarming long task mode');
    try {
      const result = await setTaskBoardArmedNextTurn(apiBaseUrl, token, nextArmed, activeSessionId);
      const armed = Boolean(result.task_board_armed_next_turn);
      setTaskBoardArmedNextTurnState(armed);
      setOverview((previous) => (
        previous
          ? {
              ...previous,
              task_board_armed_next_turn: armed,
            }
          : previous
      ));
      setStatus(armed ? 'long task mode armed for the next message' : 'long task mode cleared');
      pushActivity(
        armed
          ? 'Long task mode armed. The next message will open a managed task board.'
          : 'Long task mode cleared. The next message will stay conversational unless it asks for real work.',
        armed ? 'accent' : 'neutral',
      );
    } catch (error) {
      const message = describeError(error);
      setStatus(message);
      pushActivity(`Long task mode update failed: ${message}`, 'error');
    }
  };

  const toggleKeepRuntimeOnAppClose = async () => {
    const nextValue = !keepRuntimeOnAppClose;
    setSavingCloseBehavior(true);
    setStatus(nextValue ? 'saving keep-alive on desktop close' : 'saving stop-on-close behavior');
    try {
      await updateAgentConfig(
        apiBaseUrl,
        token,
        {
          key: 'channels.desktop.keep_runtime_on_app_close',
          value: nextValue,
        },
        sessionIdRef.current
      );
      setKeepRuntimeOnAppClose(nextValue);
      pushActivity(
        nextValue
          ? 'Desktop close behavior updated: keep the local agent alive after the desktop app closes.'
          : 'Desktop close behavior updated: closing the desktop app will stop the local agent.',
        'accent'
      );
      setStatus(
        nextValue
          ? 'desktop close will keep the local agent alive'
          : 'desktop close will stop the local agent'
      );
    } catch (error) {
      setStatus(describeError(error));
    } finally {
      setSavingCloseBehavior(false);
    }
  };

  const dueJobs = jobs.filter((job) => job.due).length;
  const heartbeatLabel = overview?.heartbeat
    ? `${overview.heartbeat.interval_seconds}s${overview.heartbeat.running ? ' · running' : ''}`
    : 'unknown';
  const runtimeLabel = summarizeRuntimeStatus(runtimeStatus);
  const activeSession = sessions.find((item) => item.id === sessionId);
  const draftModelGroups = overview?.model_groups?.length ? overview.model_groups : cachedModelGroups;
  const draftPlannerModels = overview?.available_planner_models?.length ? overview.available_planner_models : cachedPlannerModels;
  const defaultTelegramBotConfigId = telegramBotConfigs.find((item) => item.is_default)?.id || telegramBotConfigs[0]?.id || null;
  const draftEnabledToolPacks = draftChat?.enabledToolPacks ?? [...DEFAULT_TOOL_PACK_IDS];
  const fallbackCatalogModel = draftModelGroups[0]?.models?.[0] || null;
  const currentEnabledToolPacks = draftChat
    ? draftEnabledToolPacks
    : Array.isArray(activeSession?.enabled_tool_packs) && activeSession.enabled_tool_packs.length > 0
      ? activeSession.enabled_tool_packs
      : Array.isArray(overview?.enabled_tool_packs) && overview.enabled_tool_packs.length > 0
        ? overview.enabled_tool_packs
        : [...DEFAULT_TOOL_PACK_IDS];
  const currentAvailableToolPacks = draftChat
    ? [...DEFAULT_TOOL_PACK_IDS]
    : Array.isArray(activeSession?.available_tool_packs) && activeSession.available_tool_packs.length > 0
      ? activeSession.available_tool_packs
      : Array.isArray(overview?.available_tool_packs) && overview.available_tool_packs.length > 0
        ? overview.available_tool_packs
        : [...DEFAULT_TOOL_PACK_IDS];
  const currentLockStatus = (draftChat ? {} : activeSession?.lock_status || overview?.lock_status || {}) as Record<string, any>;
  const currentDisabledPackReasons = (currentLockStatus.disabled_pack_reasons || {}) as Record<string, string>;
  const activeToolPackInfoId = toolPackInfoPopup?.packId || pinnedToolPackInfoId || hoveredToolPackInfoId;
  const activeToolPackInfo = activeToolPackInfoId
    ? TOOL_PACK_DEFINITIONS.find((item) => item.id === activeToolPackInfoId) || null
    : null;
  const activeToolPackInfoDisabledReason = activeToolPackInfoId
    ? currentDisabledPackReasons[activeToolPackInfoId] || null
    : null;
  const activeToolPackInfoAvailable = activeToolPackInfoId
    ? currentAvailableToolPacks.includes(activeToolPackInfoId)
    : false;
  const activeToolPackInfoEnabled = activeToolPackInfoId
    ? currentEnabledToolPacks.includes(activeToolPackInfoId)
    : false;
  const currentHeadlessBlockReason = typeof currentDisabledPackReasons.__headless__ === 'string'
    ? currentDisabledPackReasons.__headless__
    : null;
  const currentSessionTelegramBotConfigId = activeSession?.telegram_bot_config_id || defaultTelegramBotConfigId;
  const currentSessionTelegramBot = telegramBotConfigs.find((item) => item.id === currentSessionTelegramBotConfigId) || null;
  const telegramBotLabelForSession = (targetSession: SessionSummary | null | undefined) => {
    const targetBotId = targetSession?.telegram_bot_config_id || defaultTelegramBotConfigId;
    const bot = telegramBotConfigs.find((item) => item.id === targetBotId) || null;
    return bot?.label || 'No Telegram bot';
  };
  const currentSessionSleepBotConfigId = currentSessionTelegramBotConfigId || defaultTelegramBotConfigId;
  const currentSleepSessionIdForBot = currentSessionSleepBotConfigId
    ? orchestratorStatus?.default_sleep_session_by_bot?.[currentSessionSleepBotConfigId] || null
    : null;
  const currentSessionIsSleepChat = Boolean(sessionId && currentSleepSessionIdForBot === sessionId);
  const chatSettingsSessionId = activeCommandPanel?.kind === 'session' ? activeCommandPanel.sessionId : null;
  const chatSettingsSession = chatSettingsSessionId
    ? sessions.find((item) => item.id === chatSettingsSessionId) || (chatSettingsSessionId === sessionId ? activeSession || null : null)
    : null;
  const chatSettingsBotConfigId = chatSettingsSession?.telegram_bot_config_id || defaultTelegramBotConfigId;
  const chatSettingsSleepSessionId = chatSettingsBotConfigId
    ? orchestratorStatus?.default_sleep_session_by_bot?.[chatSettingsBotConfigId] || null
    : null;
  const pendingSwitchTargetLabel = pendingSessionSwitch?.mode === 'session'
    ? sessions.find((item) => item.id === pendingSessionSwitch.sessionId)?.name || 'selected chat'
    : pendingSessionSwitch
      ? `new chat in ${projectPathBasename(pendingSessionSwitch.projectPath)}`
      : null;
  const sessionProjectPaths = new Set(
    sessions
      .map((item) => normalizeWorkspacePath(item.workspace))
      .filter(Boolean),
  );
  const projectPaths = Array.from(new Set([
    ...sidebarState.projectOrder.map((item) => normalizeWorkspacePath(item)),
    ...Object.keys(sidebarState.projects).map((item) => normalizeWorkspacePath(item)),
    ...sessions.map((item) => normalizeWorkspacePath(item.workspace)),
    ...(draftChat ? [draftChat.projectPath] : []),
  ].filter(Boolean))).filter((projectPath) => shouldKeepSidebarProjectPath(projectPath, {
    allowedRoot: allowedWorkspaceRoot,
    sessionProjectPaths,
    draftProjectPath: draftChat?.projectPath,
  }));
  const projectGroups: SidebarProjectGroup[] = projectPaths
    .map((projectPath) => {
      const projectSessions = sessions
        .filter((item) => normalizeWorkspacePath(item.workspace) === projectPath)
        .sort((left, right) => sessionSidebarSortComparator(left, right, sidebarState.sessionMeta));
      const projectState = sidebarState.projects[projectPath] || {};
      const projectPathStatus = projectPathStatuses[projectPath];
      const folderAvailable = projectPathStatus ? Boolean(projectPathStatus.exists && projectPathStatus.isDirectory) : true;
      return {
        path: projectPath,
        label: projectDisplayName(projectPath, projectState),
        hint: folderAvailable ? projectPathHint(projectPath) : `Folder unavailable · ${projectPathHint(projectPath)}`,
        pinned: Boolean(projectState.pinned),
        collapsed: Boolean(projectState.collapsed),
        folderAvailable,
        activity: Array.isArray(projectState.recentActivity) ? projectState.recentActivity : [],
        sessions: projectSessions,
        matchesSearch: true,
      };
    })
    .filter((group) => !Boolean(sidebarState.projects[group.path]?.hidden))
    .sort((left, right) => {
      if (left.pinned !== right.pinned) {
        return left.pinned ? -1 : 1;
      }
      const leftOrder = workspaceSortOrder(sidebarState.projectOrder, left.path);
      const rightOrder = workspaceSortOrder(sidebarState.projectOrder, right.path);
      if (leftOrder !== rightOrder) {
        return leftOrder - rightOrder;
      }
      if (left.folderAvailable !== right.folderAvailable) {
        return left.folderAvailable ? -1 : 1;
      }
      return left.label.localeCompare(right.label);
    });
  const pinnedProjects = projectGroups.filter((group) => group.pinned);
  const pinnedChats = projectGroups.flatMap((group) => (
    group.sessions
      .filter((item) => Boolean(sidebarState.sessionMeta[item.id]?.pinned))
      .map((item) => ({ session: item, project: group }))
  ));
  const sidebarSearchQuery = sidebarSearch.trim();
  const sidebarSearchOpen = sidebarSearchModalOpen;
  const mergedSidebarSearchResults = sidebarSearchResults.filter((item) => item.kind !== 'project');
  const recentSearchSessions = sessions.slice(0, 8);
  const contextUsage = overview?.context_usage || null;
  const contextPercent = clampUsagePercent(contextUsage?.usage_percent);
  const contextPercentLabel = contextUsage
    ? `${contextPercent.toFixed(contextPercent >= 10 ? 0 : 1)}%`
    : 'loading';
  const contextTokenLabel = contextUsage
    ? `${formatStatusNumber(contextUsage.estimated_tokens)} / ${formatStatusNumber(contextUsage.max_tokens)}`
    : 'loading';
  const contextStateLabel = contextUsage
    ? [
        contextUsage.compaction_state === 'needs_compaction'
          ? 'Needs Compact'
          : contextUsage.compaction_state === 'compacted'
            ? 'Compacted'
            : 'OK',
        contextUsage.token_strategy ? contextUsage.token_strategy : null,
        typeof contextUsage.tool_schema_count === 'number' && contextUsage.tool_schema_count > 0
          ? `${formatStatusNumber(contextUsage.tool_schema_count)} tools`
          : null,
      ].filter(Boolean).join(' · ')
    : 'loading';
  const currentModelLabel = draftChat
    ? draftChat.model || fallbackCatalogModel || 'Choose model'
    : overview?.current_model || activeSession?.model || fallbackCatalogModel || 'Choose model';
  const currentVariantLabel = draftChat?.variant
    ? ` · ${draftChat.variant}`
    : overview?.current_variant
      ? ` · ${overview.current_variant}`
      : '';
  const currentPlannerLabel = draftChat
    ? draftChat.plannerModel || 'auto'
    : overview?.planner_model || 'auto';
  const draftFolderLabel = projectPathBasename(draftChat?.projectPath || '') || 'Choose folder';
  const draftBranchChoices = Array.isArray(draftGitRepoState?.branches) ? draftGitRepoState.branches : [];
  const normalizedDraftProjectSearch = draftProjectSearch.trim().toLowerCase();
  const normalizedDraftBranchSearch = draftBranchSearch.trim().toLowerCase();
  const filteredDraftProjects = projectGroups.filter((group) => (
    !normalizedDraftProjectSearch
    || group.label.toLowerCase().includes(normalizedDraftProjectSearch)
    || group.path.toLowerCase().includes(normalizedDraftProjectSearch)
    || group.hint.toLowerCase().includes(normalizedDraftProjectSearch)
  ));
  const filteredDraftBranchChoices = draftBranchChoices.filter((branchName) => (
    !normalizedDraftBranchSearch || branchName.toLowerCase().includes(normalizedDraftBranchSearch)
  ));
  const draftBranchLabel = draftGitRepoLoading
    ? 'Loading branch'
    : draftChat?.selectedBranch
      ? draftChat.selectedBranch
      : draftGitRepoState?.isGitRepo
        ? draftGitRepoState.currentBranch || 'Choose branch'
        : 'No git repo';
  const contextUsageRatio = Math.max(0, Math.min(1, contextPercent / 100));
  const contextBreakdownLabel = contextUsage
    ? [
        typeof contextUsage.system_prompt_tokens === 'number' && contextUsage.system_prompt_tokens > 0
          ? `sys ${formatStatusNumber(contextUsage.system_prompt_tokens)}`
          : null,
        typeof contextUsage.injected_context_tokens === 'number' && contextUsage.injected_context_tokens > 0
          ? `ctx ${formatStatusNumber(contextUsage.injected_context_tokens)}`
          : null,
        typeof contextUsage.tool_schema_tokens === 'number' && contextUsage.tool_schema_tokens > 0
          ? `tools ${formatStatusNumber(contextUsage.tool_schema_tokens)}`
          : null,
        typeof contextUsage.chat_history_tokens === 'number' && contextUsage.chat_history_tokens > 0
          ? `chat ${formatStatusNumber(contextUsage.chat_history_tokens)}`
          : null,
      ].filter(Boolean).join(' · ')
    : '';
  const contextUsageHoverLabel = contextUsage
    ? `Live prompt ${contextTokenLabel} · ${contextPercentLabel}${contextBreakdownLabel ? ` · ${contextBreakdownLabel}` : ''}`
    : 'Context loading';
  const activeTaskBoard = runtimeRunState === 'running' && taskBoard?.status === 'active' ? taskBoard : null;
  const taskBoardStatusText = taskBoardStatusLabel(activeTaskBoard?.status);
  const taskBoardUpdatedLabel = activeTaskBoard?.updated_at ? formatRelativeTime(activeTaskBoard.updated_at) : null;
  const taskBoardSummary = activeTaskBoard?.status === 'completed'
    ? activeTaskBoard?.completion_summary || activeTaskBoard?.progress_summary || activeTaskBoard?.latest_summary || null
    : activeTaskBoard?.progress_summary || activeTaskBoard?.latest_summary || null;
  const taskBoardTone = activeTaskBoard?.status === 'completed'
    ? 'complete'
    : activeTaskBoard?.status === 'blocked' || activeTaskBoard?.pending_reassessment_reason
      ? 'warn'
      : 'active';
  const hasCompletedTaskBoards = completedTaskBoards.length > 0;
  const voiceSummary = alwaysOnEnabled
    ? voiceRecording
      ? `${voiceState} · always-on segment`
      : voiceRunning
        ? `${voiceState} · processing`
        : 'always-on listening'
    : voiceRecording
      ? `${voiceState} · push-to-talk`
      : voiceRunning
        ? `${voiceState} · processing`
        : voiceState;
  const extendedVoiceStatus = liveVoiceStatus as (DesktopVoiceRuntimeStatus & {
    english_pack_manifest?: Record<string, unknown> | null;
    english_pack_manifest_verified?: boolean;
    hebrew_pack_manifest?: Record<string, unknown> | null;
    hebrew_pack_manifest_verified?: boolean;
  }) | null;
  const voicePacks = voicePackState?.packs ?? [];
  const englishVoicePack = voicePacks.find((pack) => pack.id === VOICE_ENGINE_ENGLISH) ?? null;
  const hebrewVoicePack = voicePacks.find((pack) => pack.id === VOICE_ENGINE_HEBREW) ?? null;
  const selectedVoicePack = voicePacks.find((pack) => pack.id === selectedVoiceEngine) ?? null;
  const selectedVoiceEngineState = String(extendedVoiceStatus?.selected_engine_state || '').trim().toLowerCase();
  const selectedVoiceManifest = selectedVoiceEngine === VOICE_ENGINE_ENGLISH
    ? (extendedVoiceStatus?.english_pack_manifest ?? null)
    : selectedVoiceEngine === VOICE_ENGINE_HEBREW
      ? (extendedVoiceStatus?.hebrew_pack_manifest ?? null)
      : null;
  const selectedVoiceManifestVerified = selectedVoiceEngine === VOICE_ENGINE_ENGLISH
    ? Boolean(extendedVoiceStatus?.english_pack_manifest_verified)
    : selectedVoiceEngine === VOICE_ENGINE_HEBREW
      ? Boolean(extendedVoiceStatus?.hebrew_pack_manifest_verified)
      : false;
  const selectedVoicePackProvenance = selectedVoiceManifestVerified
    ? String(
        selectedVoiceManifest?.['asset_name']
        || selectedVoiceManifest?.['pack_id']
        || selectedVoiceManifest?.['tuning_preset']
        || selectedVoiceManifest?.['repo_id']
        || 'verified pack',
      )
    : null;
  const selectedVoicePackModel = extendedVoiceStatus?.stt_model || selectedVoicePack?.path || null;
  const selectedVoicePackPath = selectedVoicePack?.path || null;
  const selectedVoicePackSummary = selectedVoiceEngine === VOICE_ENGINE_NONE
    ? 'Voice input is off. Open setup to re-enable a local path.'
    : selectedVoiceEngineState === 'warming'
      ? `Warming ${selectedVoicePack?.title || 'selected voice path'} so it is fully ready before capture starts.`
    : selectedVoicePack?.available
      ? `${selectedVoicePack.title} ready${selectedVoicePackModel ? ` · ${selectedVoicePackModel}` : ''}${selectedVoicePackProvenance ? ` · ${selectedVoicePackProvenance}` : ''}`
      : `${selectedVoicePack?.title || 'Selected voice path'} is not installed yet. Open setup to install it.`;
  const voicePackDiagnostics = selectedVoicePack?.available && selectedVoicePackPath
    ? `Installed pack path: ${selectedVoicePackPath}${selectedVoiceManifestVerified ? ' · verified pack' : ''}`
    : extendedVoiceStatus?.issues?.[0] || null;
  const activitySummary = activity.length ? `${activity.length} recent events` : 'No recent runtime events';
  const referenceEntries = messages.reduce<ReferenceEntry[]>((items, message, index) => {
    if (!isReferenceSidebarMessage(message, sessionName)) {
      return items;
    }

    const fallbackTitle = sessionName || `Reference ${items.length + 1}`;
    items.push({
      id: `${message.timestamp || 'reference'}-${index}`,
      index,
      title: extractReferenceTitle(message.content, fallbackTitle),
      summary: summarizeReferenceContent(message.content),
      message,
    });
    return items;
  }, []);
  const referenceIndexSet = new Set(referenceEntries.map((entry) => entry.index));
  const transcriptEntries = messages.reduce<Array<{ fullIndex: number; message: DesktopMessage }>>((items, message, index) => {
    if (!referenceIndexSet.has(index)) {
      items.push({ fullIndex: index, message });
    }
    return items;
  }, []);
  const transcriptTimelineEvents = timelineEvents.filter((event) => (
    event.kind === 'tool'
    || event.kind === 'command'
    || (event.kind === 'runtime' && (event.tone === 'warn' || event.tone === 'error'))
  ));
  const verboseModeOn = Boolean(overview?.verbose_mode);
  const timelineEntries = mergeTimelineEntries(
    messages.map((message, index) => ({ fullIndex: index, message })),
    timelineEvents,
  );
  const transcriptTimelineEntries = mergeTimelineEntries(transcriptEntries, transcriptTimelineEvents);
  const historySummary = timelineEntries.length === 1
    ? '1 timeline item'
    : `${timelineEntries.length} timeline items`;
  const referenceSummary = referenceEntries.length === 1
    ? referenceEntries[0].title
    : `${referenceEntries.length} saved reference notes`;
  const referenceRailKey = `${sessionId || 'none'}:${referenceEntries.length}`;
  const showVoiceBanner = Boolean(voiceDraft)
    || Boolean(voiceError)
    || alwaysOnEnabled
    || voiceRecording
    || voiceRunning
    || ['connecting', 'reconnecting', 'error', 'warming'].includes(voiceState)
    || selectedVoiceEngineState === 'warming';
  const voicePanelActive = !voicePanelHidden && (
    showVoicePanel
    || Boolean(voiceDraft)
    || Boolean(voiceError)
    || alwaysOnEnabled
    || voiceRecording
    || voiceRunning
  );
  const isCenteredDraftComposerStage = Boolean(
    draftChat
    && transcriptTimelineEntries.length === 0
    && referenceEntries.length === 0
    && !assistantDraft
    && !showVoiceBanner
    && !activeTaskBoard
    && !hasCompletedTaskBoards
  );
  const agentRunActive = runtimeRunState === 'running' || chatRunActive || Boolean(assistantDraft) || Boolean(thinking);
  const shouldShowThinkingIndicator = agentRunActive && (lastAssistantOutputAt === null || Date.now() - lastAssistantOutputAt > 1200);
  const thinkingShineTranslate = thinkingShineProgress.interpolate({
    inputRange: [0, 1],
    outputRange: [-64, 100],
  });
  const thinkingTextCounterTranslate = thinkingShineProgress.interpolate({
    inputRange: [0, 1],
    outputRange: [64, -100],
  });
  const hasComposerText = input.trim().length > 0;
  const currentSessionQueuedMessages = queuedComposerMessages.filter((item) => item.sessionId === sessionId);
  const queuedComposerMessagesDisplay = [...currentSessionQueuedMessages].reverse();
  const sendButtonMode = agentRunActive
    ? hasComposerText ? 'interrupt' : 'stop'
    : hasComposerText ? 'send' : 'idle';
  const sendButtonGlyph = sendButtonMode === 'stop'
    ? '■'
    : sendButtonMode === 'interrupt'
      ? '↪'
      : '↑';
  const voiceBannerText = voiceError
    ? voiceError
      : voiceDraft
      ? voiceDraft
      : selectedVoiceEngineState === 'warming' || voiceState === 'warming'
        ? 'Warming the Hebrew voice path so the local pass-3 model is fully ready before capture starts.'
      : alwaysOnEnabled && voiceRecording
        ? ALWAYS_ON_VOICE_AUTO_SEND
          ? 'Always-on voice detected speech. Local Whisper is drafting the transcript and will send when the gate closes.'
          : 'Always-on voice detected speech. Local Whisper is drafting the transcript and will place the final text in the message box.'
      : alwaysOnEnabled
        ? ALWAYS_ON_VOICE_AUTO_SEND
          ? 'Always-on voice is listening locally. Speech above the gate threshold will be transcribed and sent automatically.'
          : 'Always-on voice is listening locally. Speech above the gate threshold will become editable text before you send it.'
      : voiceRecording
        ? 'Push-to-talk is live. Keep holding to continue transcribing and release to send.'
        : voiceState === 'finalizing'
          ? 'Finishing the voice transcript and sending it through the shared session.'
          : voiceState === 'generating'
            ? 'Generating the assistant reply for the voice transcript.'
            : voiceState === 'synthesizing'
              ? 'Preparing assistant audio.'
              : voiceState === 'speaking'
                ? 'Playing assistant audio.'
      : voiceState === 'ready'
        ? 'Hold the push-to-talk button or switch to always-on local Whisper.'
        : `Voice ${voiceState}`;
  const handleVoiceEngineSelection = async (engine: typeof VOICE_ENGINE_ENGLISH | typeof VOICE_ENGINE_HEBREW) => {
    const targetPack = engine === VOICE_ENGINE_HEBREW ? hebrewVoicePack : englishVoicePack;
    if (voiceEngineChanging) {
      return;
    }
    if (voiceRecording || voiceRunning) {
      setVoiceError('Finish the current voice capture before switching paths.');
      pushActivity('Finish the current voice capture before switching paths.', 'warn');
      return;
    }
    if (!targetPack?.available) {
      const message = `${engine === VOICE_ENGINE_HEBREW ? 'Hebrew' : 'English'} voice pack is not ready yet. Open setup to install it.`;
      setVoiceError(message);
      pushActivity(message, 'warn');
      onOpenSetup?.();
      return;
    }
    if (selectedVoiceEngine === engine) {
      return;
    }

    setVoiceEngineChanging(true);
    setVoiceError(null);
    alwaysOnEnabledRef.current = false;
    setAlwaysOnEnabled(false);
    stopVoiceTracks();
    resetVoiceCaptureBuffers({ clearProgrammaticComposerInput: true });
    voiceRunningRef.current = false;
    voiceRecordingRef.current = false;
    setVoiceRunning(false);
    setVoiceRecording(false);
    lastVoiceWarmRequestEngineRef.current = null;
    if (engine === VOICE_ENGINE_HEBREW) {
      setVoiceState('warming');
      setStatus('warming Hebrew voice path');
    }
    try {
      const switched = await onSelectVoiceEngine?.(engine);
      if (switched === false) {
        setVoiceError(`Could not switch to the ${engine === VOICE_ENGINE_HEBREW ? 'Hebrew' : 'English'} voice path.`);
        setVoiceState('error');
      } else if (engine === VOICE_ENGINE_HEBREW) {
        await warmSelectedVoicePath(engine);
      } else {
        setVoiceState('ready');
        setStatus('voice ready');
        await refreshVoiceRuntimeState();
      }
    } catch (error) {
      const message = describeError(error);
      setVoiceError(message);
      setVoiceState('error');
      pushActivity(`Voice path switch failed: ${message}`, 'error');
    } finally {
      setVoiceEngineChanging(false);
    }
  };
  const historyAvailable = Boolean(timelineEntries.length || referenceEntries.length);
  const activeSessionArtifactCount = Number(
    sessions.find((item) => item.id === sessionId)?.artifact_count
    || sessions.find((item) => item.id === sessionIdRef.current)?.artifact_count
    || 0,
  );
  const selectedArtifactSummary = artifacts.find((item) => item.artifact_id === selectedArtifactId) || artifacts[0] || null;
  const commandSuggestionQuery = getCommandSuggestionQuery(input);
  const commandSuggestions = commandSuggestionQuery == null || dismissedCommandSuggestionInput === input
    ? []
    : DESKTOP_COMMAND_SUGGESTIONS.filter((suggestion) => (
      !commandSuggestionQuery
      || suggestion.name.startsWith(commandSuggestionQuery)
      || suggestion.name.includes(commandSuggestionQuery)
    )).slice(0, MAX_COMMAND_SUGGESTIONS);
  const floatingPanelKind = activeCommandPanel?.kind === 'model'
    ? 'model'
    : activeCommandPanel?.kind === 'tools'
      ? 'tools'
      : activeCommandPanel?.kind === 'draftProject'
        ? 'draftProject'
      : activeCommandPanel?.kind === 'draftBranch'
        ? 'draftBranch'
      : activeCommandPanel?.kind === 'session'
        ? 'session'
        : null;
  const floatingMenuKinds: Array<NonNullable<ActiveCommandPanel>['kind']> = ['model', 'tools', 'draftProject', 'draftBranch', 'session'];
  const hasDismissibleFloatingPanel = floatingPanelKind != null && floatingMenuKinds.includes(floatingPanelKind);
  const floatingPanelPrefersBelow = floatingPanelKind === 'draftProject' || floatingPanelKind === 'draftBranch';
  const shouldRenderGlobalFloatingPanel = floatingPanelKind != null && !floatingPanelPrefersBelow;
  const draftProjectCommandPanel = (
    <View
      ref={activeCommandPanel?.kind === 'draftProject' ? floatingPanelRef : null}
      style={[styles.commandPanel, styles.commandPanelFloating, styles.draftChoiceCommandPanel, styles.draftComposerInlineDropdown]}
    >
      <View style={styles.draftChoiceSearchShell}>
        <MonoIcon name="search" style={styles.draftChoiceSearchGlyph} />
        <TextInput
          style={styles.draftChoiceSearchInput}
          value={draftProjectSearch}
          onChangeText={setDraftProjectSearch}
          placeholder="Search folders"
          placeholderTextColor="#7d889d"
        />
      </View>
      <Text style={styles.draftChoiceSectionLabel}>Folders</Text>
      {filteredDraftProjects.length ? (
        <ScrollView style={styles.draftChoiceScroll} contentContainerStyle={styles.draftChoiceList}>
          {filteredDraftProjects.map((project) => {
            const selected = normalizeWorkspacePath(draftChat?.projectPath) === project.path;
            return (
              <Pressable
                key={`draft-project-${project.path}`}
                style={({ hovered }) => [
                  styles.draftChoiceRow,
                  hovered ? styles.draftChoiceRowHovered : null,
                  selected ? styles.draftChoiceRowSelected : null,
                ]}
                onPress={() => chooseDraftProject(project.path)}
              >
                <MonoIcon
                  name={selected ? 'folder_open' : 'folder_closed'}
                  style={[styles.draftChoiceRowIcon, selected ? styles.draftChoiceRowIconSelected : null]}
                />
                <Text
                  style={[styles.draftChoiceRowTitle, selected ? styles.draftChoiceRowTitleSelected : null]}
                  numberOfLines={1}
                >
                  {project.label}
                </Text>
                {selected ? <MonoIcon name="check" style={styles.draftChoiceRowCheck} /> : null}
              </Pressable>
            );
          })}
        </ScrollView>
      ) : (
        <View style={styles.commandPanelEmpty}>
          <Text style={styles.commandPanelEmptyTitle}>No folders found</Text>
          <Text style={styles.commandPanelEmptyText}>
            Try a different search or add another folder for draft chats.
          </Text>
        </View>
      )}
      <View style={styles.draftChoiceFooter}>
        <Pressable
          style={({ hovered }) => [
            styles.draftChoiceFooterAction,
            hovered ? styles.draftChoiceFooterActionHovered : null,
          ]}
          onPress={() => void chooseDraftProjectFolder()}
        >
          <MonoIcon name="plus" style={styles.draftChoiceFooterActionIcon} />
          <Text style={styles.draftChoiceFooterActionText}>Add folder…</Text>
        </Pressable>
      </View>
    </View>
  );
  const draftBranchCommandPanel = (
    <View
      ref={activeCommandPanel?.kind === 'draftBranch' ? floatingPanelRef : null}
      style={[styles.commandPanel, styles.commandPanelFloating, styles.draftChoiceCommandPanel, styles.draftComposerInlineDropdown]}
    >
      <View style={styles.draftChoiceSearchShell}>
        <MonoIcon name="search" style={styles.draftChoiceSearchGlyph} />
        <TextInput
          style={styles.draftChoiceSearchInput}
          value={draftBranchSearch}
          onChangeText={setDraftBranchSearch}
          placeholder="Search branches"
          placeholderTextColor="#7d889d"
        />
      </View>
      <Text style={styles.draftChoiceSectionLabel}>Branches</Text>
      {draftGitRepoLoading ? (
        <View style={styles.commandPanelEmpty}>
          <Text style={styles.commandPanelEmptyTitle}>Loading branches</Text>
          <Text style={styles.commandPanelEmptyText}>
            Checking the selected folder for Git branches.
          </Text>
        </View>
      ) : draftGitRepoState?.isGitRepo && filteredDraftBranchChoices.length ? (
        <ScrollView style={styles.draftChoiceScroll} contentContainerStyle={styles.draftChoiceList}>
          {filteredDraftBranchChoices.map((branchName) => {
            const selected = branchName === (draftChat?.selectedBranch || draftGitRepoState.currentBranch);
            return (
              <Pressable
                key={`draft-branch-${branchName}`}
                style={({ hovered }) => [
                  styles.draftChoiceRow,
                  hovered ? styles.draftChoiceRowHovered : null,
                  selected ? styles.draftChoiceRowSelected : null,
                ]}
                onPress={() => chooseDraftBranch(branchName)}
              >
                <MonoIcon
                  name="branch"
                  style={[styles.draftChoiceRowIcon, selected ? styles.draftChoiceRowIconSelected : null]}
                />
                <Text
                  style={[styles.draftChoiceRowTitle, selected ? styles.draftChoiceRowTitleSelected : null]}
                  numberOfLines={1}
                >
                  {branchName}
                </Text>
                {selected ? <MonoIcon name="check" style={styles.draftChoiceRowCheck} /> : null}
              </Pressable>
            );
          })}
        </ScrollView>
      ) : draftGitRepoState?.isGitRepo ? (
        <View style={styles.commandPanelEmpty}>
          <Text style={styles.commandPanelEmptyTitle}>No branches found</Text>
          <Text style={styles.commandPanelEmptyText}>
            This repository did not report any selectable local branches.
          </Text>
        </View>
      ) : (
        <View style={styles.commandPanelEmpty}>
          <Text style={styles.commandPanelEmptyTitle}>No Git repo here</Text>
          <Text style={styles.commandPanelEmptyText}>
            Choose a repository folder if you want this chat to start from a specific branch.
          </Text>
        </View>
      )}
    </View>
  );

  useEffect(() => {
    if (Platform.OS !== 'web') {
      return;
    }
    const hasDismissibleSurface = Boolean(
      openProjectMenuPath
      || openSessionMenuId
      || sidebarSearchModalOpen
      || hasDismissibleFloatingPanel
      || commandSuggestions.length,
    );
    if (!hasDismissibleSurface || typeof document === 'undefined') {
      return;
    }

    const containsTarget = (node: any, target: EventTarget | null) => {
      if (!node || !target || typeof node.contains !== 'function') {
        return false;
      }
      return node.contains(target);
    };

    const handlePointerAway = (event: MouseEvent) => {
      const target = event.target;
      const boundaries = [
        openProjectMenuPath ? projectMenuRefs.current[openProjectMenuPath] : null,
        openProjectMenuPath ? projectMenuTriggerRefs.current[openProjectMenuPath] : null,
        openSessionMenuId ? sessionMenuRefs.current[openSessionMenuId] : null,
        openSessionMenuId ? sessionMenuTriggerRefs.current[openSessionMenuId] : null,
        hasDismissibleFloatingPanel ? floatingPanelRef.current : null,
        activeCommandPanel?.kind === 'model' ? modelTriggerRef.current : null,
        activeCommandPanel?.kind === 'tools' ? toolsTriggerRef.current : null,
        activeCommandPanel?.kind === 'draftProject' ? draftProjectTriggerRef.current : null,
        activeCommandPanel?.kind === 'draftBranch' ? draftBranchTriggerRef.current : null,
        sidebarSearchModalOpen ? sidebarSearchModalRef.current : null,
        sidebarSearchModalOpen ? sidebarSearchLauncherRef.current : null,
        commandSuggestions.length ? commandSuggestionMenuRef.current : null,
        commandSuggestions.length ? composerTextRegionRef.current : null,
      ];

      if (boundaries.some((node) => containsTarget(node, target))) {
        return;
      }

      setOpenProjectMenuPath(null);
      setOpenSessionMenuId(null);
      if (sidebarSearchModalOpen) {
        setSidebarSearchModalOpen(false);
      }
      if (hasDismissibleFloatingPanel) {
        setActiveCommandPanel((current) => (
          current && floatingMenuKinds.includes(current.kind) ? null : current
        ));
      }
      if (commandSuggestions.length) {
        setDismissedCommandSuggestionInput(input);
      }
    };

    document.addEventListener('mousedown', handlePointerAway, true);
    return () => {
      document.removeEventListener('mousedown', handlePointerAway, true);
    };
  }, [
    activeCommandPanel,
    commandSuggestions.length,
    hasDismissibleFloatingPanel,
    input,
    openProjectMenuPath,
    openSessionMenuId,
    sidebarSearchModalOpen,
  ]);

  useEffect(() => {
    if (activeCommandPanel?.kind === 'tools') {
      return;
    }
    setHoveredToolPackInfoId(null);
    setPinnedToolPackInfoId(null);
  }, [activeCommandPanel]);

  useEffect(() => {
    thinkingShineProgress.stopAnimation();
    thinkingShineProgress.setValue(0);
    if (!shouldShowThinkingIndicator) {
      return;
    }
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(thinkingShineProgress, {
          toValue: 1,
          duration: 1320,
          easing: Easing.inOut(Easing.cubic),
          useNativeDriver: true,
        }),
        Animated.delay(120),
      ]),
    );
    animation.start();
    return () => {
      animation.stop();
      thinkingShineProgress.stopAnimation();
      thinkingShineProgress.setValue(0);
    };
  }, [shouldShowThinkingIndicator, thinkingShineProgress]);

  useEffect(() => {
    if (agentRunActive || !sessionId) {
      return;
    }
    const nextQueuedMessage = queuedComposerMessages.find((item) => item.sessionId === sessionId);
    if (!nextQueuedMessage) {
      return;
    }
    setQueuedComposerMessages((current) => current.filter((item) => item.id !== nextQueuedMessage.id));
    queueMessage(nextQueuedMessage.text, nextQueuedMessage.sourceFormat, nextQueuedMessage.sessionId, 'none');
  }, [agentRunActive, queuedComposerMessages, sessionId]);

  useEffect(() => {
    if (!referenceEntries.length) {
      referenceAutoOpenKeyRef.current = null;
      referenceDismissedKeyRef.current = null;
      setShowReferenceRail(false);
      return;
    }

    if (
      referenceAutoOpenKeyRef.current === referenceRailKey
      || referenceDismissedKeyRef.current === referenceRailKey
    ) {
      return;
    }

    referenceAutoOpenKeyRef.current = referenceRailKey;
    setSidebarExpanded(true);
    setShowReferenceRail(true);
  }, [referenceEntries.length, referenceRailKey]);

  const openReferenceRail = () => {
    referenceDismissedKeyRef.current = null;
    setSidebarExpanded(true);
    setShowReferenceRail(true);
  };

  const closeReferenceRail = () => {
    referenceDismissedKeyRef.current = referenceRailKey;
    setShowReferenceRail(false);
  };

  const refreshArtifacts = async (targetSessionId?: string | null) => {
    const effectiveSessionId = String(targetSessionId || sessionIdRef.current || '').trim();
    if (!effectiveSessionId) {
      setArtifacts([]);
      setSelectedArtifactId(null);
      setSelectedArtifactDetail(null);
      return;
    }
    setArtifactsLoading(true);
    setArtifactError(null);
    try {
      const nextArtifacts = await fetchSessionArtifacts(apiBaseUrl, token, effectiveSessionId);
      setArtifacts(Array.isArray(nextArtifacts) ? nextArtifacts : []);
      setSelectedArtifactId((current) => {
        if (current && nextArtifacts.some((item) => item.artifact_id === current)) {
          return current;
        }
        return nextArtifacts[0]?.artifact_id || null;
      });
    } catch (error) {
      setArtifactError(describeError(error));
    } finally {
      setArtifactsLoading(false);
    }
  };

  const openArtifactRail = () => {
    setSidebarExpanded(true);
    setShowArtifactRail(true);
    void refreshArtifacts(sessionIdRef.current);
  };

  const closeArtifactRail = () => {
    setShowArtifactRail(false);
  };

  const openArtifactPreview = async (artifactId: string) => {
    const effectiveSessionId = String(sessionIdRef.current || '').trim();
    if (!effectiveSessionId || !artifactId) {
      return;
    }
    setSelectedArtifactId(artifactId);
    setArtifactDetailLoading(true);
    setArtifactError(null);
    try {
      const detail = await fetchSessionArtifactDetail(apiBaseUrl, token, effectiveSessionId, artifactId);
      setSelectedArtifactDetail(detail);
    } catch (error) {
      setArtifactError(describeError(error));
    } finally {
      setArtifactDetailLoading(false);
    }
  };

  const openArtifactExternally = async (artifactId: string) => {
    const effectiveSessionId = String(sessionIdRef.current || '').trim();
    if (!effectiveSessionId || !artifactId || Platform.OS !== 'web') {
      return;
    }
    try {
      const payload = await fetchSessionArtifactBlob(apiBaseUrl, token, effectiveSessionId, artifactId);
      const objectUrl = window.URL.createObjectURL(payload.blob);
      window.open(objectUrl, '_blank', 'noopener,noreferrer');
      window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 60_000);
    } catch (error) {
      setArtifactError(describeError(error));
    }
  };

  const downloadArtifact = async (artifactId: string) => {
    const effectiveSessionId = String(sessionIdRef.current || '').trim();
    if (!effectiveSessionId || !artifactId || Platform.OS !== 'web') {
      return;
    }
    try {
      const payload = await fetchSessionArtifactBlob(apiBaseUrl, token, effectiveSessionId, artifactId);
      const objectUrl = window.URL.createObjectURL(payload.blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = payload.filename || `${artifactId}.bin`;
      anchor.rel = 'noopener noreferrer';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 60_000);
    } catch (error) {
      setArtifactError(describeError(error));
    }
  };

  const openSearchResult = async (target: SearchResultTarget) => {
    if (target.kind === 'project') {
      revealProjectInSidebar(target.projectPath);
      closeSidebarSearchModal();
      return;
    }

    closeSidebarSearchModal();
    await openSession(target.sessionId, {
      projectPath: target.projectPath,
      jumpMessageIndex: target.kind === 'message' ? target.messageIndex : null,
    });
  };

  const closeSidebar = () => {
    setSidebarExpanded(false);
  };

  useEffect(() => {
    if (!showArtifactRail) {
      return;
    }
    void refreshArtifacts(sessionId);
  }, [showArtifactRail, sessionId, lastAssistantOutputAt]);

  useEffect(() => {
    if (!showArtifactRail || !selectedArtifactId) {
      setSelectedArtifactDetail(null);
      return;
    }
    void openArtifactPreview(selectedArtifactId);
  }, [showArtifactRail, selectedArtifactId, sessionId]);

  const toggleSidebar = () => {
    if (sidebarExpanded) {
      closeSidebar();
      return;
    }
    setSidebarExpanded(true);
  };

  const projectDragProps = (projectPath: string) => {
    if (Platform.OS !== 'web') {
      return {};
    }
    return {
      draggable: true,
      onDragStart: () => setDragState({ kind: 'project', projectPath }),
      onDragOver: (event: any) => event.preventDefault(),
      onDrop: (event: any) => {
        event.preventDefault();
        if (dragState?.kind === 'project') {
          moveProjectOrder(dragState.projectPath, projectPath);
        }
        setDragState(null);
      },
      onDragEnd: () => setDragState(null),
    } as any;
  };

  const sessionDragProps = (projectPath: string, sessionEntryId: string) => {
    if (Platform.OS !== 'web') {
      return {};
    }
    return {
      draggable: true,
      onDragStart: () => setDragState({ kind: 'chat', projectPath, sessionId: sessionEntryId }),
      onDragOver: (event: any) => event.preventDefault(),
      onDrop: (event: any) => {
        event.preventDefault();
        if (dragState?.kind === 'chat' && dragState.projectPath === projectPath) {
          moveSessionOrder(projectPath, dragState.sessionId, sessionEntryId);
        }
        setDragState(null);
      },
      onDragEnd: () => setDragState(null),
    } as any;
  };

  return (
    <View ref={shellRef} style={styles.shell}>
      <View style={[styles.conversationColumn, isCenteredDraftComposerStage ? styles.conversationColumnDraftStage : null]}>
        <ScrollView
          ref={scrollRef}
          style={[
            styles.transcriptScroll,
            styles.centeredConversationBlock,
            isCenteredDraftComposerStage ? styles.transcriptScrollDraftStage : null,
          ]}
          contentContainerStyle={[
            styles.transcriptContent,
            isCenteredDraftComposerStage ? styles.transcriptContentDraftStage : null,
          ]}
          onScroll={handleTranscriptScroll}
          scrollEventThrottle={16}
        >
          {referenceEntries.length > 0 ? (
            <View style={styles.referenceMovedCard}>
              <View style={styles.referenceMovedCopy}>
                <Text style={styles.referenceMovedTitle}>Reference note moved to the history sidebar</Text>
                <Text style={styles.referenceMovedText}>
                  Long structured overview content and runtime history are tucked into the collapsible sidebar so the main chat stays readable.
                </Text>
              </View>
              <Pressable style={styles.referenceMovedButton} onPress={openReferenceRail}>
                <Text style={styles.referenceMovedButtonText}>{showReferenceRail ? 'History Open' : 'Open History'}</Text>
              </Pressable>
            </View>
          ) : null}

          {transcriptTimelineEntries.length === 0 && referenceEntries.length === 0 ? (
            <View style={[
              styles.emptyConversationCard,
              emptyConversationProjectName ? styles.emptyConversationDraftCard : null,
            ]}>
              {emptyConversationProjectName ? (
                <>
                  <Text style={styles.emptyDraftPrompt}>
                    What should we work on in {emptyConversationProjectName}?
                  </Text>
                  <View style={styles.emptyDraftFolderRow}>
                    <Text style={styles.emptyDraftFolderIcon}>⌂</Text>
                    <Text style={styles.emptyDraftFolderText}>{emptyConversationProjectName}</Text>
                  </View>
                  <Text style={[styles.emptyText, styles.emptyDraftSupportingText]}>
                    Start typing below or use voice. This new chat will stay in the folder shown here.
                  </Text>
                </>
              ) : (
                <>
                  <Text style={styles.emptyTitle}>No conversation turns yet</Text>
                  <Text style={styles.emptyText}>Start typing below or use voice. Live voice status appears above the composer.</Text>
                </>
              )}
            </View>
          ) : null}

          {transcriptTimelineEntries.map((entry, index) => {
            if (entry.kind === 'message') {
              const message = messages[entry.sourceMessageIndex];
              if (!message) {
                return null;
              }
              const fullIndex = entry.sourceMessageIndex;
              return (
                <View
                  key={message.messageKey || `${message.timestamp || 'ts'}-${fullIndex}-${index}`}
                  onLayout={(event) => {
                    transcriptMessageLayoutRef.current[fullIndex] = event.nativeEvent.layout.y;
                  }}
                  style={[
                    styles.messageBubble,
                    message.role === 'assistant'
                      ? styles.messageBubbleAssistant
                      : message.role === 'system'
                        ? styles.messageBubbleSystem
                        : styles.messageBubbleUser,
                    highlightedMessageIndex === fullIndex ? styles.searchJumpHighlight : null,
                    message.pending ? styles.messageBubblePending : null,
                  ]}
                >
                  <View style={styles.messageHeader}>
                    <Text style={styles.messageLabel}>{labelForMessage(message)}</Text>
                    <Text style={styles.messageTime}>
                      {message.timestamp ? formatAbsoluteTime(message.timestamp) : 'pending'}
                    </Text>
                  </View>
                  <Text style={styles.messageText}>{message.content}</Text>
                </View>
              );
            }

            const entryKind = entry.eyebrow.toLowerCase();
            const isToolEntry = entryKind === 'tool';
            const isCommandEntry = entryKind === 'command';
            const toolSections = isToolEntry ? entry.body.split(/\n(?:->|→)\s*/) : [];
            const commandText = isToolEntry
              ? (toolSections[0] || entry.body)
              : isCommandEntry
                ? entry.label.replace(/^command\s*·\s*/i, '').trim() || entry.label
                : entry.body;
            const resultText = isToolEntry
              ? (toolSections.length > 1 ? toolSections.slice(1).join('\n-> ') : '')
              : isCommandEntry
                ? entry.body
                : '';
            const eyebrowLabel = isToolEntry || isCommandEntry ? 'Command' : entry.label;
            return (
              <View
                key={`${entry.id}-${index}`}
                style={[
                  styles.timelineTranscriptCard,
                  entry.tone === 'accent'
                    ? styles.timelineTranscriptCardAccent
                    : entry.tone === 'warn'
                      ? styles.timelineTranscriptCardWarn
                      : entry.tone === 'error'
                        ? styles.timelineTranscriptCardError
                        : null,
                ]}
              >
                <View style={styles.timelineTranscriptHeader}>
                  <Text style={styles.timelineTranscriptEyebrow}>{eyebrowLabel}</Text>
                  <Text style={styles.timelineTranscriptTime}>
                    {entry.timestamp ? formatAbsoluteTime(entry.timestamp) : 'event'}
                  </Text>
                </View>
                <Text style={styles.timelineTranscriptBody}>{commandText}</Text>
                {resultText ? (
                  <View style={styles.timelineTranscriptResultBlock}>
                    <Text style={styles.timelineTranscriptResultEyebrow}>Command Result</Text>
                    <Text style={styles.timelineTranscriptResultText}>{resultText}</Text>
                  </View>
                ) : null}
              </View>
            );
          })}

          {assistantDraft ? (
            <View style={[styles.messageBubble, styles.messageBubbleAssistant, styles.messageBubbleDraft]}>
              <View style={styles.messageHeader}>
                <Text style={styles.messageLabel}>Assistant</Text>
                <Text style={styles.messageTime}>streaming</Text>
              </View>
              <Text style={styles.messageText}>{assistantDraft}</Text>
            </View>
          ) : null}

          {shouldShowThinkingIndicator ? (
            <View style={styles.syntheticThinkingRow}>
              <View style={styles.syntheticThinkingTextWrap}>
                <Text style={styles.syntheticThinkingText}>Thinking</Text>
                <Animated.View
                  pointerEvents="none"
                  style={[
                    styles.syntheticThinkingHighlightMask,
                    {
                      transform: [{ translateX: thinkingShineTranslate }],
                    },
                  ]}
                >
                  <Animated.Text
                    style={[
                      styles.syntheticThinkingText,
                      styles.syntheticThinkingTextHighlight,
                      { transform: [{ translateX: thinkingTextCounterTranslate }] },
                    ]}
                  >
                    Thinking
                  </Animated.Text>
                </Animated.View>
              </View>
            </View>
          ) : null}
        </ScrollView>

        {showVoiceBanner ? (
          <View style={[styles.centeredConversationBlock, styles.voiceBanner, voiceError ? styles.voiceBannerError : null]}>
            <Text style={styles.voiceBannerTitle}>Voice</Text>
            <Text style={styles.voiceBannerText}>{voiceBannerText}</Text>
          </View>
        ) : null}

        {activeTaskBoard ? (
          <View
            style={[
              styles.centeredConversationBlock,
              styles.taskBoardCard,
              taskBoardTone === 'complete'
                ? styles.taskBoardCardComplete
                : taskBoardTone === 'warn'
                  ? styles.taskBoardCardWarn
                  : null,
            ]}
          >
            <View style={styles.taskBoardHeader}>
              <View style={styles.taskBoardHeaderCopy}>
                <Text style={styles.taskBoardEyebrow}>Managed Task</Text>
                <Text style={styles.taskBoardGoal}>{activeTaskBoard.main_goal}</Text>
                <Text style={styles.taskBoardMeta}>
                  {taskBoardSummary || `${activeTaskBoard.completed_sub_goals}/${activeTaskBoard.total_sub_goals} sub-goals complete`}
                  {taskBoardUpdatedLabel ? ` · updated ${taskBoardUpdatedLabel}` : ''}
                </Text>
              </View>
              <View style={styles.taskBoardHeaderActions}>
                <Pressable
                  style={styles.taskBoardToggleButton}
                  onPress={() => setTaskBoardCollapsed((current) => !current)}
                >
                  <Text style={styles.taskBoardToggleButtonText}>{taskBoardCollapsed ? 'Expand' : 'Collapse'}</Text>
                </Pressable>
                <View
                  style={[
                    styles.taskBoardBadge,
                    taskBoardTone === 'complete'
                      ? styles.taskBoardBadgeComplete
                      : taskBoardTone === 'warn'
                        ? styles.taskBoardBadgeWarn
                        : null,
                  ]}
                >
                  <Text style={styles.taskBoardBadgeText}>{taskBoardStatusText}</Text>
                </View>
              </View>
            </View>

            {!taskBoardCollapsed ? (
              <>
                {activeTaskBoard.pending_reassessment_reason ? (
                  <View style={styles.taskBoardAlert}>
                    <Text style={styles.taskBoardAlertLabel}>Reassessing</Text>
                    <Text style={styles.taskBoardAlertText}>{activeTaskBoard.pending_reassessment_reason}</Text>
                  </View>
                ) : null}

                <View style={styles.taskBoardInfoRow}>
                  <View style={styles.taskBoardInfoChip}>
                    <Text style={styles.taskBoardInfoLabel}>Current Focus</Text>
                    <Text style={styles.taskBoardInfoValue}>
                      {activeTaskBoard.status === 'completed'
                        ? 'Task complete'
                        : activeTaskBoard.current_focus || 'Choose next sub-goal'}
                    </Text>
                  </View>
                  <View style={styles.taskBoardInfoChip}>
                    <Text style={styles.taskBoardInfoLabel}>Next Method</Text>
                    <Text style={styles.taskBoardInfoValue}>
                      {activeTaskBoard.status === 'completed'
                        ? activeTaskBoard.completion_summary || 'Task complete. No next method is needed.'
                        : activeTaskBoard.next_method || 'Not set yet'}
                    </Text>
                  </View>
                </View>

                <View style={styles.taskBoardSteps}>
                  {activeTaskBoard.sub_goals.map((subGoal) => (
                    <View key={subGoal.id} style={styles.taskBoardStepRow}>
                      <Text style={styles.taskBoardStepPrefix}>{taskBoardStepPrefix(subGoal.status)}</Text>
                      <View style={styles.taskBoardStepCopy}>
                        <Text style={styles.taskBoardStepTitle}>{subGoal.title}</Text>
                        {subGoal.completion_reason ? (
                          <Text style={styles.taskBoardStepMeta}>{subGoal.completion_reason}</Text>
                        ) : subGoal.completion_evidence ? (
                          <Text style={styles.taskBoardStepMeta}>{subGoal.completion_evidence}</Text>
                        ) : null}
                      </View>
                    </View>
                  ))}
                  <View style={styles.taskBoardStepRow}>
                    <Text style={styles.taskBoardStepPrefix}>{activeTaskBoard.verification_status === 'done' ? '[x]' : '[ ]'}</Text>
                    <View style={styles.taskBoardStepCopy}>
                      <Text style={styles.taskBoardStepTitle}>Verify the requested result and close the task</Text>
                      {activeTaskBoard.verification_summary ? (
                        <Text style={styles.taskBoardStepMeta}>{activeTaskBoard.verification_summary}</Text>
                      ) : (
                        <Text style={styles.taskBoardStepMeta}>
                          {activeTaskBoard.status === 'completed'
                            ? 'Waiting for verification summary.'
                            : 'This final check closes only after the requested result is verified.'}
                        </Text>
                      )}
                    </View>
                  </View>
                </View>
              </>
            ) : null}
          </View>
        ) : null}

        {hasCompletedTaskBoards ? (
          <View style={[styles.centeredConversationBlock, styles.completedTaskBoardsSection]}>
            <View style={styles.completedTaskBoardsHeader}>
              <View style={styles.completedTaskBoardsHeaderCopy}>
                <Text style={styles.completedTaskBoardsEyebrow}>Task History</Text>
                <Text style={styles.completedTaskBoardsTitle}>Managed Task History</Text>
              </View>
              <Text style={styles.completedTaskBoardsSummary}>{completedTaskBoards.length} kept</Text>
            </View>

            <View style={styles.completedTaskBoardsList}>
              {completedTaskBoards.map((board) => {
                const expanded = Boolean(expandedCompletedTaskIds[board.task_id]);
                const completedAtLabel = board.collapsed_completed_at || board.completed_at;
                const summaryText = board.collapsed_completion_summary || board.completion_summary || board.verification_summary || 'Completed';
                return (
                  <View key={`completed-task-${board.task_id}`} style={styles.completedTaskCard}>
                    <Pressable
                      style={styles.completedTaskCardHeader}
                      onPress={() => {
                        setExpandedCompletedTaskIds((previous) => ({
                          ...previous,
                          [board.task_id]: !expanded,
                        }));
                      }}
                    >
                      <View style={styles.completedTaskCardCopy}>
                        <Text style={styles.completedTaskCardTitle}>{board.collapsed_title || `[x] ${board.main_goal}`}</Text>
                        <Text style={styles.completedTaskCardMeta}>
                          {completedAtLabel ? `${formatRelativeTime(completedAtLabel)} · ` : ''}{taskBoardStatusLabel(board.status)} · {summaryText}
                        </Text>
                      </View>
                      <View style={styles.taskBoardHeaderActions}>
                        <View
                          style={[
                            styles.taskBoardBadge,
                            board.status === 'completed'
                              ? styles.taskBoardBadgeComplete
                              : board.status === 'blocked'
                                ? styles.taskBoardBadgeWarn
                                : null,
                          ]}
                        >
                          <Text style={styles.taskBoardBadgeText}>{taskBoardStatusLabel(board.status)}</Text>
                        </View>
                        <Text style={styles.completedTaskCardToggle}>{expanded ? 'Collapse' : 'Expand'}</Text>
                      </View>
                    </Pressable>

                    {expanded ? (
                      <View style={styles.completedTaskCardBody}>
                        <View style={styles.completedTaskCardSteps}>
                          {board.sub_goals.map((subGoal) => (
                            <View key={`${board.task_id}-${subGoal.id}`} style={styles.taskBoardStepRow}>
                              <Text style={styles.taskBoardStepPrefix}>{taskBoardStepPrefix(subGoal.status)}</Text>
                              <View style={styles.taskBoardStepCopy}>
                                <Text style={styles.taskBoardStepTitle}>{subGoal.title}</Text>
                                {subGoal.completion_reason ? (
                                  <Text style={styles.taskBoardStepMeta}>{subGoal.completion_reason}</Text>
                                ) : subGoal.completion_evidence ? (
                                  <Text style={styles.taskBoardStepMeta}>{subGoal.completion_evidence}</Text>
                                ) : null}
                              </View>
                            </View>
                          ))}
                        </View>
                        <View style={styles.completedTaskCardSummaryBox}>
                          <Text style={styles.completedTaskCardSummaryLabel}>Verification summary</Text>
                          <Text style={styles.completedTaskCardSummaryText}>{summaryText}</Text>
                        </View>
                      </View>
                    ) : null}
                  </View>
                );
              })}
            </View>
          </View>
        ) : null}

        <View style={[styles.composerDock, isCenteredDraftComposerStage ? styles.composerDockDraftStage : null]}>
        <View style={[styles.composerShell, isCenteredDraftComposerStage ? styles.composerShellDraftStage : null]}>
          {pendingSessionSwitch ? (
            <View style={styles.pendingSwitchCard}>
              <View style={styles.pendingSwitchCopy}>
                <Text style={styles.pendingSwitchEyebrow}>Switch Chat</Text>
                <Text style={styles.pendingSwitchTitle}>Current run is still active</Text>
                <Text style={styles.pendingSwitchText}>
                  Stop the current task to continue with {pendingSwitchTargetLabel || 'the selected chat'}.
                </Text>
              </View>
              <View style={styles.pendingSwitchActions}>
                <Pressable style={styles.pendingSwitchPrimaryAction} onPress={() => void confirmPendingSessionSwitch()}>
                  <Text style={styles.pendingSwitchPrimaryActionText}>Stop And Switch</Text>
                </Pressable>
                <Pressable style={styles.pendingSwitchSecondaryAction} onPress={dismissPendingSessionSwitch}>
                  <Text style={styles.pendingSwitchSecondaryActionText}>Cancel</Text>
                </Pressable>
              </View>
            </View>
          ) : null}

          {queuedComposerMessagesDisplay.length ? (
            <View style={styles.queuedComposerStack}>
              {queuedComposerMessagesDisplay.map((item) => {
                const originalIndex = currentSessionQueuedMessages.findIndex((entry) => entry.id === item.id);
                const steerLabel = currentSessionQueuedMessages.length > 1 && originalIndex === currentSessionQueuedMessages.length - 1
                  ? 'Steer All'
                  : 'Steer Now';
                return (
                  <View key={item.id} style={styles.queuedComposerRow}>
                    <Text style={styles.queuedComposerText} numberOfLines={1}>{item.text}</Text>
                    <Pressable
                      style={styles.queuedComposerAction}
                      onPress={() => {
                        const slice = currentSessionQueuedMessages.slice(0, originalIndex + 1);
                        sendQueuedComposerSlice(slice, 'steer_now');
                      }}
                    >
                      <Text style={styles.queuedComposerActionText}>{steerLabel}</Text>
                    </Pressable>
                  </View>
                );
              })}
            </View>
          ) : null}

          {activeCommandPanel?.kind === 'verbose' ? (
            <View style={styles.commandPanel}>
              <View style={styles.commandPanelHeader}>
                <View style={styles.commandPanelHeaderCopy}>
                  <Text style={styles.commandPanelEyebrow}>Verbose</Text>
                  <Text style={styles.commandPanelTitle}>Tool Logging</Text>
                  <Text style={styles.commandPanelText}>
                    Verbose mode is currently {overview?.verbose_mode ? 'ON' : 'OFF'}. Choose how tool activity should appear in the shared chat.
                  </Text>
                </View>
                <Pressable style={styles.commandPanelCloseButton} onPress={() => setActiveCommandPanel(null)}>
                  <Text style={styles.commandPanelCloseText}>Close</Text>
                </Pressable>
              </View>
              <View style={styles.commandPanelActionRow}>
                <Pressable
                  style={verboseModeOn ? styles.commandPanelPrimaryAction : styles.commandPanelSecondaryAction}
                  onPress={() => { void runVerboseCommand('on'); }}
                >
                  <Text style={verboseModeOn ? styles.commandPanelPrimaryActionText : styles.commandPanelSecondaryActionText}>
                    Turn Verbose On
                  </Text>
                </Pressable>
                <Pressable
                  style={!verboseModeOn ? styles.commandPanelPrimaryAction : styles.commandPanelSecondaryAction}
                  onPress={() => { void runVerboseCommand('off'); }}
                >
                  <Text style={!verboseModeOn ? styles.commandPanelPrimaryActionText : styles.commandPanelSecondaryActionText}>
                    Turn Verbose Off
                  </Text>
                </Pressable>
                <Pressable style={styles.commandPanelSecondaryAction} onPress={() => { void runVerboseCommand('status'); }}>
                  <Text style={styles.commandPanelSecondaryActionText}>Show Status</Text>
                </Pressable>
              </View>
            </View>
          ) : null}

          {activeCommandPanel?.kind === 'command' ? (
            <View style={styles.commandPanel}>
              <View style={styles.commandPanelHeader}>
                <View style={styles.commandPanelHeaderCopy}>
                  <Text style={styles.commandPanelEyebrow}>{activeCommandPanel.command}</Text>
                  <Text style={styles.commandPanelTitle}>Command Menu</Text>
                  <Text style={styles.commandPanelText}>{activeCommandPanel.description}</Text>
                </View>
                <Pressable style={styles.commandPanelCloseButton} onPress={() => setActiveCommandPanel(null)}>
                  <Text style={styles.commandPanelCloseText}>Close</Text>
                </Pressable>
              </View>
              <View style={styles.commandPanelActionRow}>
                <Pressable
                  style={styles.commandPanelPrimaryAction}
                  onPress={() => {
                    const commandToRun = activeCommandPanel.command;
                    setActiveCommandPanel(null);
                    void runSlashCommandFromComposer(commandToRun);
                  }}
                >
                  <Text style={styles.commandPanelPrimaryActionText}>Run {activeCommandPanel.command}</Text>
                </Pressable>
              </View>
            </View>
          ) : null}

          <View style={styles.composerUtilityAnchor}>
            {shouldRenderGlobalFloatingPanel ? (
              <View
                ref={floatingPanelRef}
                style={[
                  styles.commandPanelFloatingLayer,
                  floatingPanelPrefersBelow
                    ? styles.commandPanelFloatingBelowRight
                    : styles.commandPanelFloatingRight,
                ]}
              >
                {floatingPanelKind === 'model' ? (
                  <View style={[styles.commandPanel, styles.commandPanelSlim, styles.commandPanelFloating]}>
                    <View style={styles.commandPanelHeader}>
                    <View style={styles.commandPanelHeaderCopy}>
                      <Text style={styles.commandPanelEyebrow}>Model + Planner</Text>
                      <Text style={styles.commandPanelTitle}>Choose Runtime Models</Text>
                      <Text style={styles.commandPanelText}>
                        The main model handles the chat. Planner is currently set to {currentPlannerLabel} for task decomposition and reassessment.
                      </Text>
                    </View>
                      <Pressable style={styles.commandPanelCloseButton} onPress={() => setActiveCommandPanel(null)}>
                        <Text style={styles.commandPanelCloseText}>Close</Text>
                      </Pressable>
                    </View>
                    {draftModelGroups.length || draftPlannerModels.length ? (
                      <ScrollView style={styles.modelPickerScroll} contentContainerStyle={styles.modelPickerContent}>
                        {draftModelGroups.map((group) => (
                          <View key={group.provider} style={styles.modelProviderBlock}>
                            <Text style={styles.modelProviderTitle}>{group.provider}</Text>
                            <View style={styles.modelList}>
                              {group.models.map((model) => {
                                const selected = model === currentModelLabel;
                                return (
                                  <Pressable
                                    key={`${group.provider}-${model}`}
                                    style={({ hovered }) => [
                                      styles.modelListItem,
                                      hovered ? styles.modelListItemHovered : null,
                                      selected ? styles.modelListItemActive : null,
                                    ]}
                                    onPress={() => void chooseModel(model)}
                                  >
                                    <View style={styles.modelListItemCopy}>
                                      <Text style={[styles.modelListItemTitle, selected ? styles.modelListItemTitleActive : null]}>
                                        {model}
                                      </Text>
                                    </View>
                                    <Text style={[styles.modelListItemMeta, selected ? styles.modelListItemMetaActive : null]}>
                                      {selected ? 'Current' : 'Select'}
                                    </Text>
                                  </Pressable>
                                );
                              })}
                            </View>
                          </View>
                        ))}
                        <View style={styles.modelProviderBlock}>
                          <Text style={styles.modelProviderTitle}>Planner</Text>
                          <Text style={styles.modelProviderCaption}>
                            Automatic uses the cheapest supported planner for this session.
                          </Text>
                          <View style={styles.modelList}>
                            <Pressable
                              style={({ hovered }) => [
                                styles.modelListItem,
                                hovered ? styles.modelListItemHovered : null,
                                currentPlannerLabel === 'auto' ? styles.modelListItemActive : null,
                              ]}
                              onPress={() => void choosePlannerModel(null)}
                            >
                              <View style={styles.modelListItemCopy}>
                                <Text style={[styles.modelListItemTitle, currentPlannerLabel === 'auto' ? styles.modelListItemTitleActive : null]}>
                                  Automatic
                                </Text>
                              </View>
                              <Text style={[styles.modelListItemMeta, currentPlannerLabel === 'auto' ? styles.modelListItemMetaActive : null]}>
                                {currentPlannerLabel === 'auto' ? 'Current' : 'Select'}
                              </Text>
                            </Pressable>
                            {draftPlannerModels.map((model) => {
                              const selected = model === currentPlannerLabel;
                              return (
                                <Pressable
                                  key={`planner-inline-${model}`}
                                  style={({ hovered }) => [
                                    styles.modelListItem,
                                    hovered ? styles.modelListItemHovered : null,
                                    selected ? styles.modelListItemActive : null,
                                  ]}
                                  onPress={() => void choosePlannerModel(model)}
                                >
                                  <View style={styles.modelListItemCopy}>
                                    <Text style={[styles.modelListItemTitle, selected ? styles.modelListItemTitleActive : null]}>
                                      {model}
                                    </Text>
                                  </View>
                                  <Text style={[styles.modelListItemMeta, selected ? styles.modelListItemMetaActive : null]}>
                                    {selected ? 'Current' : 'Select'}
                                  </Text>
                                </Pressable>
                              );
                            })}
                          </View>
                        </View>
                      </ScrollView>
                    ) : (
                      <View style={styles.commandPanelEmpty}>
                        <Text style={styles.commandPanelEmptyTitle}>No configured model providers</Text>
                        <Text style={styles.commandPanelEmptyText}>
                          Add an API key in setup/settings, then reopen the model chooser.
                        </Text>
                      </View>
                    )}
                  </View>
                ) : null}
                {floatingPanelKind === 'tools' ? (
                  <View style={[styles.commandPanel, styles.commandPanelSlim, styles.commandPanelFloating, styles.toolPackCommandPanel]}>
                    <View style={styles.commandPanelHeader}>
                      <View style={styles.commandPanelHeaderCopy}>
                        <Text style={styles.commandPanelTitle}>Tool Packs</Text>
                        <Text style={styles.commandPanelText}>
                          Toggle the packs this chat can use. Conflicting packs stay dim until the current owner finishes.
                        </Text>
                        {currentHeadlessBlockReason ? (
                          <Text style={styles.commandPanelWarningText}>{currentHeadlessBlockReason}</Text>
                        ) : null}
                      </View>
                      <Pressable style={styles.commandPanelCloseButton} onPress={() => setActiveCommandPanel(null)}>
                        <Text style={styles.commandPanelCloseText}>Close</Text>
                      </Pressable>
                    </View>
                    <ScrollView style={styles.modelPickerScroll} contentContainerStyle={styles.modelPickerContent}>
                      <View style={styles.toolPackCompactList}>
                          {TOOL_PACK_DEFINITIONS.map((pack) => {
                            const enabled = currentEnabledToolPacks.includes(pack.id);
                            const available = currentAvailableToolPacks.includes(pack.id);
                            const disabledReason = currentDisabledPackReasons[pack.id] || null;
                            const blockedEnable = !enabled && Boolean(disabledReason);
                            const infoVisible = activeToolPackInfoId === pack.id;
                            return (
                              <View key={`tool-pack-${pack.id}`} style={styles.toolPackCompactGroup}>
                                <View
                                  style={[
                                    styles.toolPackCompactRow,
                                    enabled ? styles.toolPackCompactRowEnabled : null,
                                    !available ? styles.toolPackCompactRowUnavailable : null,
                                  ]}
                                >
                                  <Text
                                    style={[
                                      styles.toolPackCompactLabel,
                                      enabled ? styles.toolPackCompactLabelEnabled : null,
                                      !available ? styles.toolPackCompactLabelUnavailable : null,
                                    ]}
                                    numberOfLines={1}
                                  >
                                    {pack.label}
                                  </Text>
                                  <View style={styles.toolPackCompactActions}>
                                    <Pressable
                                      ref={setToolPackInfoButtonRef(pack.id)}
                                      onHoverIn={() => showToolPackInfoPopup(pack.id)}
                                      onHoverOut={() => scheduleHideToolPackInfoPopup(pack.id)}
                                      onPress={() => {
                                        if (pinnedToolPackInfoId === pack.id) {
                                          hideToolPackInfoPopup(pack.id);
                                          return;
                                        }
                                        showToolPackInfoPopup(pack.id, { pinned: true });
                                      }}
                                      style={({ hovered }) => [
                                        styles.toolPackInfoButton,
                                        hovered ? styles.toolPackInfoButtonHovered : null,
                                        infoVisible ? styles.toolPackInfoButtonActive : null,
                                      ]}
                                    >
                                      <MonoIcon
                                        name="info"
                                        style={[
                                          styles.toolPackInfoIcon,
                                          infoVisible ? styles.toolPackInfoIconActive : null,
                                        ]}
                                      />
                                    </Pressable>
                                    <Pressable
                                      style={[
                                        styles.toolPackSwitch,
                                        enabled ? styles.toolPackSwitchActive : null,
                                        toolPackMutationInFlight === pack.id ? styles.toolPackSwitchSaving : null,
                                        blockedEnable ? styles.toolPackSwitchDisabled : null,
                                      ]}
                                      onPress={() => void toggleCurrentSessionToolPack(pack.id)}
                                      disabled={toolPackMutationInFlight === pack.id}
                                    >
                                      <View
                                        style={[
                                          styles.toolPackSwitchKnob,
                                          enabled ? styles.toolPackSwitchKnobActive : null,
                                        ]}
                                      />
                                    </Pressable>
                                  </View>
                                </View>
                              </View>
                            );
                          })}
                      </View>
                    </ScrollView>
                  </View>
                ) : null}
                {floatingPanelKind === 'tools' && toolPackInfoPopup && activeToolPackInfo ? (
                  <Pressable
                    style={[
                      styles.toolPackInfoFloatingBubble,
                      {
                        top: toolPackInfoPopup.top,
                        left: toolPackInfoPopup.left,
                      },
                    ]}
                    onHoverIn={() => {
                      clearToolPackInfoHideTimer();
                      if (!pinnedToolPackInfoId) {
                        setHoveredToolPackInfoId(activeToolPackInfo.id);
                      }
                    }}
                    onHoverOut={() => {
                      if (pinnedToolPackInfoId === activeToolPackInfo.id) {
                        return;
                      }
                      scheduleHideToolPackInfoPopup(activeToolPackInfo.id);
                    }}
                  >
                    <Text style={styles.toolPackInfoTitle}>{activeToolPackInfo.label}</Text>
                    <Text style={styles.toolPackInfoText}>{activeToolPackInfo.description}</Text>
                    {activeToolPackInfoDisabledReason ? (
                      <Text style={styles.toolPackInfoWarning}>{activeToolPackInfoDisabledReason}</Text>
                    ) : !activeToolPackInfoAvailable && activeToolPackInfoEnabled ? (
                      <Text style={styles.toolPackInfoWarning}>
                        Enabled for this chat, but temporarily unavailable while another running chat owns it.
                      </Text>
                    ) : null}
                  </Pressable>
                ) : null}
                {floatingPanelKind === 'session' ? (
                  <View style={[styles.commandPanel, styles.commandPanelSlim, styles.commandPanelFloating]}>
                    <View style={styles.commandPanelHeader}>
                      <View style={styles.commandPanelHeaderCopy}>
                        <Text style={styles.commandPanelEyebrow}>Chat Settings</Text>
                        <Text style={styles.commandPanelTitle}>{chatSettingsSession?.name || 'Chat'}</Text>
                        <Text style={styles.commandPanelText}>
                          Assign this chat to a Telegram bot and choose whether it can be used as a sleep chat.
                        </Text>
                      </View>
                      <Pressable style={styles.commandPanelCloseButton} onPress={() => setActiveCommandPanel(null)}>
                        <Text style={styles.commandPanelCloseText}>Close</Text>
                      </Pressable>
                    </View>
                    {chatSettingsSession ? (
                      <ScrollView style={styles.modelPickerScroll} contentContainerStyle={styles.modelPickerContent}>
                        <View style={styles.modelProviderBlock}>
                          <Text style={styles.modelProviderTitle}>Telegram Bot</Text>
                          <Text style={styles.modelProviderCaption}>
                            App messages from this chat are mirrored only to the selected bot.
                          </Text>
                          <View style={styles.modelList}>
                            {telegramBotConfigs.length ? telegramBotConfigs.map((bot) => {
                              const selected = bot.id === chatSettingsBotConfigId;
                              return (
                                <Pressable
                                  key={`chat-bot-${bot.id}`}
                                  style={({ hovered }) => [
                                    styles.modelListItem,
                                    hovered ? styles.modelListItemHovered : null,
                                    selected ? styles.modelListItemActive : null,
                                  ]}
                                  disabled={sessionSettingsMutationInFlight}
                                  onPress={() => void updateChatTelegramBotAssignment(chatSettingsSession.id, bot.id)}
                                >
                                  <View style={styles.modelListItemCopy}>
                                    <Text style={[styles.modelListItemTitle, selected ? styles.modelListItemTitleActive : null]}>
                                      {bot.label}
                                    </Text>
                                    <Text style={styles.modelProviderCaption}>{bot.bot_token}{bot.is_default ? ' · default' : ''}</Text>
                                  </View>
                                  <Text style={[styles.modelListItemMeta, selected ? styles.modelListItemMetaActive : null]}>
                                    {selected ? 'Assigned' : 'Use'}
                                  </Text>
                                </Pressable>
                              );
                            }) : (
                              <View style={styles.commandPanelEmpty}>
                                <Text style={styles.commandPanelEmptyTitle}>No Telegram bots yet</Text>
                                <Text style={styles.commandPanelEmptyText}>
                                  Add more bot configs in setup/settings to route chats separately.
                                </Text>
                              </View>
                            )}
                          </View>
                        </View>

                        <View style={styles.modelProviderBlock}>
                          <Text style={styles.modelProviderTitle}>Sleep Mode</Text>
                          <Text style={styles.modelProviderCaption}>
                            Only designated sleep chats can keep running while the desktop UI is asleep.
                          </Text>
                          <View style={styles.modelList}>
                            <Pressable
                              style={({ hovered }) => [
                                styles.modelListItem,
                                hovered ? styles.modelListItemHovered : null,
                                chatSettingsSession.headless_eligible ? styles.modelListItemActive : null,
                              ]}
                              disabled={sessionSettingsMutationInFlight}
                              onPress={() => void updateChatHeadlessEligibility(chatSettingsSession.id, !chatSettingsSession.headless_eligible)}
                            >
                              <View style={styles.modelListItemCopy}>
                                <Text style={[styles.modelListItemTitle, chatSettingsSession.headless_eligible ? styles.modelListItemTitleActive : null]}>
                                  {chatSettingsSession.headless_eligible ? 'Sleep eligible' : 'Not sleep eligible'}
                                </Text>
                                <Text style={styles.modelProviderCaption}>
                                  {chatSettingsSession.headless_eligible
                                    ? 'This chat can be chosen as the sleep chat for its bot.'
                                    : 'Turn this on before assigning the chat as a sleep target.'}
                                </Text>
                              </View>
                              <Text style={[styles.modelListItemMeta, chatSettingsSession.headless_eligible ? styles.modelListItemMetaActive : null]}>
                                {chatSettingsSession.headless_eligible ? 'On' : 'Off'}
                              </Text>
                            </Pressable>
                            <Pressable
                              style={({ hovered }) => [
                                styles.modelListItem,
                                hovered ? styles.modelListItemHovered : null,
                                chatSettingsSleepSessionId === chatSettingsSession.id ? styles.modelListItemActive : null,
                                !chatSettingsSession.headless_eligible ? styles.modelListItemDisabled : null,
                              ]}
                              disabled={sessionSettingsMutationInFlight || !chatSettingsSession.headless_eligible || !chatSettingsBotConfigId}
                              onPress={() => {
                                if (!chatSettingsBotConfigId) {
                                  return;
                                }
                                const nextSessionId = chatSettingsSleepSessionId === chatSettingsSession.id ? null : chatSettingsSession.id;
                                void setSleepChatForBot(chatSettingsBotConfigId, nextSessionId);
                              }}
                            >
                              <View style={styles.modelListItemCopy}>
                                <Text style={[styles.modelListItemTitle, chatSettingsSleepSessionId === chatSettingsSession.id ? styles.modelListItemTitleActive : null]}>
                                  {chatSettingsSleepSessionId === chatSettingsSession.id ? 'Designated sleep chat' : 'Make this the sleep chat'}
                                </Text>
                                <Text style={styles.modelProviderCaption}>
                                  {chatSettingsSleepSessionId === chatSettingsSession.id
                                    ? 'Telegram and cron can keep using this chat while the UI is asleep.'
                                    : 'Assign this chat as the active sleep target for its Telegram bot.'}
                                </Text>
                              </View>
                              <Text style={[styles.modelListItemMeta, chatSettingsSleepSessionId === chatSettingsSession.id ? styles.modelListItemMetaActive : null]}>
                                {chatSettingsSleepSessionId === chatSettingsSession.id ? 'Assigned' : 'Choose'}
                              </Text>
                            </Pressable>
                          </View>
                        </View>
                      </ScrollView>
                    ) : (
                      <View style={styles.commandPanelEmpty}>
                        <Text style={styles.commandPanelEmptyTitle}>Chat not available</Text>
                        <Text style={styles.commandPanelEmptyText}>
                          Reopen the panel after the chat list refreshes.
                        </Text>
                      </View>
                    )}
                  </View>
                ) : null}

              </View>
            ) : null}
          </View>

          {commandSuggestions.length ? (
            <View ref={commandSuggestionMenuRef} style={styles.commandSuggestionMenu}>
              <View style={styles.commandSuggestionHeader}>
                <Text style={styles.commandSuggestionTitle}>Commands</Text>
                <Pressable
                  style={styles.commandSuggestionCloseButton}
                  onPress={() => setDismissedCommandSuggestionInput(input)}
                >
                  <Text style={styles.commandSuggestionCloseText}>Dismiss</Text>
                </Pressable>
              </View>
              <View style={styles.commandSuggestionList}>
                {commandSuggestions.map((suggestion) => (
                  <Pressable
                    key={suggestion.name}
                    style={styles.commandSuggestionItem}
                    onPress={() => void selectCommandSuggestion(suggestion.command)}
                  >
                    <Text style={styles.commandSuggestionCommand}>{suggestion.command}</Text>
                    <Text style={styles.commandSuggestionDescription} numberOfLines={1}>
                      {suggestion.description}
                    </Text>
                  </Pressable>
                ))}
              </View>
            </View>
          ) : null}

          <View ref={composerTextRegionRef} style={styles.composerTextRegion}>
            {Platform.OS === 'web' ? (
              <View pointerEvents="none" style={styles.composerInputMeasureShell}>
                <Text
                  style={styles.composerInputMeasureText}
                  onLayout={handleComposerMeasureLayout}
                >
                  {(input || ' ') + '\u200b'}
                </Text>
              </View>
            ) : null}
            <TextInput
              nativeID="desktop-composer-input"
              style={[styles.composerInput, { height: composerInputHeight }]}
              value={input}
              onChangeText={handleComposerInputChange}
              onContentSizeChange={handleComposerContentSizeChange}
              onKeyPress={handleComposerKeyPress}
              placeholder={DESKTOP_COMMAND_PLACEHOLDER}
              placeholderTextColor="#8f9ebb"
              multiline
              scrollEnabled={composerInputHeight >= COMPOSER_MAX_HEIGHT}
            />

            <View style={styles.composerFooterRow}>
              <View style={styles.composerFooterControls}>
                <Pressable
                  ref={modelTriggerRef}
                  style={({ hovered }) => [
                    styles.composerStatusPill,
                    styles.composerStatusPillWide,
                    hovered ? styles.statusSurfaceHovered : null,
                    activeCommandPanel?.kind === 'model' ? styles.composerStatusPillInteractiveActive : null,
                  ]}
                  onPress={() => setActiveCommandPanel((current) => current?.kind === 'model' ? null : { kind: 'model' })}
                >
                  <Text style={styles.composerStatusPillValue} numberOfLines={1}>
                    {currentModelLabel}{currentVariantLabel}
                  </Text>
                </Pressable>

                <Pressable
                  ref={toolsTriggerRef}
                  style={({ hovered }) => [
                    styles.composerStatusPill,
                    hovered ? styles.statusSurfaceHovered : null,
                    activeCommandPanel?.kind === 'tools' ? styles.composerStatusPillInteractiveActive : null,
                  ]}
                  onPress={() => setActiveCommandPanel((current) => current?.kind === 'tools' ? null : { kind: 'tools' })}
                >
                  <Text style={styles.composerStatusPillValue} numberOfLines={1}>
                    Tools · {currentEnabledToolPacks.length}
                  </Text>
                </Pressable>

                <Pressable
                  style={({ hovered }) => [
                    styles.composerStatusPill,
                    hovered ? styles.statusSurfaceHovered : null,
                    taskBoardArmedNextTurn ? styles.composerStatusPillInteractiveActive : null,
                  ]}
                  onPress={() => void toggleTaskBoardArmNextTurn()}
                >
                  <Text style={styles.composerStatusPillValue} numberOfLines={1}>
                    {taskBoardArmedNextTurn ? 'Long Task: Armed' : 'Long Task: Off'}
                  </Text>
                </Pressable>

                <Pressable
                  style={({ hovered }) => [
                    styles.contextMeterButton,
                    contextUsageHovered ? styles.contextMeterButtonExpanded : styles.contextMeterButtonCollapsed,
                    hovered ? styles.statusSurfaceHovered : null,
                  ]}
                  onHoverIn={() => setContextUsageHovered(true)}
                  onHoverOut={() => setContextUsageHovered(false)}
                >
                  <View style={styles.contextMeterOrb}>
                    <View
                      style={[
                        styles.contextMeterOrbFill,
                        contextUsage?.compaction_state === 'needs_compaction'
                          ? styles.contextMeterOrbFillWarn
                          : contextUsage?.compaction_state === 'compacted'
                            ? styles.contextMeterOrbFillCompact
                            : null,
                        { height: `${Math.max(contextUsageRatio * 100, contextUsageRatio > 0 ? 8 : 0)}%` },
                      ]}
                    />
                    <View style={styles.contextMeterOrbCore} />
                  </View>
                  {contextUsageHovered ? (
                    <View style={styles.contextMeterDetail}>
                      <Text style={styles.contextMeterDetailTitle}>Context</Text>
                      <Text style={styles.contextMeterDetailText} numberOfLines={1}>{contextUsageHoverLabel}</Text>
                      <Text style={styles.contextMeterDetailMeta} numberOfLines={1}>{contextStateLabel}</Text>
                    </View>
                  ) : null}
                </Pressable>
              </View>

              <View style={styles.composerFooterActions}>
                <Text style={styles.composerStatusInline} numberOfLines={1}>{status}</Text>
                <Pressable
                  style={[
                    styles.sendButton,
                    sendButtonMode === 'idle' ? styles.sendButtonIdle : null,
                    sendButtonMode === 'stop' ? styles.sendButtonStop : null,
                    sendButtonMode === 'interrupt' ? styles.sendButtonInterrupt : null,
                  ]}
                  onPress={() => {
                    if (sendButtonMode === 'stop') {
                      void runControl('stop');
                      return;
                    }
                    if (sendButtonMode === 'idle') {
                      return;
                    }
                    void sendText();
                  }}
                >
                  <Text style={[styles.sendButtonText, sendButtonMode === 'idle' ? styles.sendButtonTextIdle : null]}>
                    {sendButtonGlyph}
                  </Text>
                </Pressable>
              </View>
            </View>

            {draftChat ? (
              <View style={styles.draftComposerMetaTray}>
                <View style={styles.draftComposerMetaRow}>
                  <View style={styles.draftComposerMetaControl}>
                    <Pressable
                      ref={draftProjectTriggerRef}
                      style={({ hovered }) => [
                        styles.draftComposerMetaChip,
                        hovered ? styles.draftComposerMetaChipHovered : null,
                        activeCommandPanel?.kind === 'draftProject' ? styles.draftComposerMetaChipActive : null,
                      ]}
                      onPress={() => setActiveCommandPanel((current) => current?.kind === 'draftProject' ? null : { kind: 'draftProject' })}
                    >
                      <MonoIcon name="folder_closed" style={styles.draftComposerMetaIcon} />
                      <Text style={styles.draftComposerMetaLabel} numberOfLines={1}>{draftFolderLabel}</Text>
                      <MonoIcon
                        name={activeCommandPanel?.kind === 'draftProject' ? 'chevron_up' : 'chevron_down'}
                        style={styles.draftComposerMetaChevronIcon}
                      />
                    </Pressable>
                    {activeCommandPanel?.kind === 'draftProject' ? draftProjectCommandPanel : null}
                  </View>
                  <View style={styles.draftComposerMetaControl}>
                    <Pressable
                      ref={draftBranchTriggerRef}
                      style={({ hovered }) => [
                        styles.draftComposerMetaChip,
                        hovered ? styles.draftComposerMetaChipHovered : null,
                        activeCommandPanel?.kind === 'draftBranch' ? styles.draftComposerMetaChipActive : null,
                        !draftGitRepoState?.isGitRepo && !draftGitRepoLoading ? styles.draftComposerMetaChipDisabled : null,
                      ]}
                      disabled={!draftGitRepoState?.isGitRepo && !draftGitRepoLoading}
                      onPress={() => setActiveCommandPanel((current) => current?.kind === 'draftBranch' ? null : { kind: 'draftBranch' })}
                    >
                      <MonoIcon name="branch" style={styles.draftComposerMetaIcon} />
                      <Text style={styles.draftComposerMetaLabel} numberOfLines={1}>{draftBranchLabel}</Text>
                      <MonoIcon
                        name={activeCommandPanel?.kind === 'draftBranch' ? 'chevron_up' : 'chevron_down'}
                        style={styles.draftComposerMetaChevronIcon}
                      />
                    </Pressable>
                    {activeCommandPanel?.kind === 'draftBranch' ? draftBranchCommandPanel : null}
                  </View>
                </View>
              </View>
            ) : null}
          </View>
        </View>
        </View>
      </View>

      <View
        style={[
          styles.sidebarDock,
          sidebarExpanded ? styles.sidebarDockExpanded : styles.sidebarDockCollapsed,
        ]}
      >
        <View style={[styles.utilityRail, sidebarExpanded ? styles.utilityRailExpanded : null]}>
          <Pressable
            style={({ hovered }) => [
              styles.utilityRailButton,
              hovered ? styles.utilityRailButtonHovered : null,
              sidebarExpanded ? styles.utilityRailButtonActive : null,
            ]}
            onPress={toggleSidebar}
          >
            <MonoIcon name="menu" style={styles.utilityRailIcon} />
          </Pressable>
          <Pressable
            style={({ hovered }) => [
              styles.utilityRailButton,
              hovered ? styles.utilityRailButtonHovered : null,
              setupOpen ? styles.utilityRailButtonActive : null,
            ]}
            onPress={() => onOpenSetup?.()}
          >
            <MonoIcon name="settings" style={styles.utilityRailIcon} />
          </Pressable>
        </View>

        {sidebarExpanded ? (
          <ScrollView
            style={styles.sidebarContentScroll}
            contentContainerStyle={styles.sidebarContentStack}
            onScroll={() => {
              clearSidebarChatTooltipTimer();
              hideSidebarChatTooltip();
            }}
            scrollEventThrottle={16}
          >
            <View style={styles.sidebarNavStack}>
              <Pressable style={styles.sidebarListRow} onPress={() => void beginNewChat()}>
                <MonoIcon name="compose" style={styles.sidebarListRowIcon} />
                <View style={styles.sidebarListRowCopy}>
                  <Text style={styles.sidebarListRowTitle}>New chat</Text>
                  <Text style={styles.sidebarListRowText}>
                    {selectedProjectPath ? `Start in ${projectPathBasename(selectedProjectPath)}` : 'Choose a folder and start a chat'}
                  </Text>
                </View>
              </Pressable>

              <Pressable ref={sidebarSearchLauncherRef} style={styles.sidebarSearchShell} onPress={openSidebarSearchModal}>
                <MonoIcon name="search" style={styles.sidebarSearchGlyph} />
                <Text style={styles.sidebarSearchButtonText}>Search</Text>
              </Pressable>

              <View style={styles.sidebarComputerTabsRow}>
                <Pressable style={[styles.sidebarComputerTab, styles.sidebarComputerTabActive]}>
                  <Text style={[styles.sidebarComputerTabText, styles.sidebarComputerTabTextActive]}>This Computer</Text>
                </Pressable>
                <Pressable style={[styles.sidebarComputerTab, styles.sidebarComputerTabDisabled]} disabled>
                  <Text style={styles.sidebarComputerTabText}>Other Computers</Text>
                </Pressable>
              </View>

              <View style={styles.sidebarMenuList}>
                <Pressable
                  style={[styles.sidebarMenuRowMinimal, voicePanelActive ? styles.sidebarMenuRowMinimalActive : null]}
                  onPress={() => {
                    if (voicePanelActive) {
                      hideVoicePanel();
                    } else {
                      openVoicePanel();
                    }
                  }}
                >
                  <MonoIcon name="voice" style={styles.sidebarMenuRowGlyph} />
                  <Text style={styles.sidebarMenuRowLabelMinimal}>Voice</Text>
                  <Text style={styles.sidebarMenuRowValueMinimal}>{voiceSummary}</Text>
                </Pressable>

                <Pressable
                  style={[
                    styles.sidebarMenuRowMinimal,
                    showReferenceRail ? styles.sidebarMenuRowMinimalActive : null,
                    !historyAvailable ? styles.sidebarMenuRowMinimalDisabled : null,
                  ]}
                  disabled={!historyAvailable}
                  onPress={() => {
                    if (showReferenceRail) {
                      closeReferenceRail();
                    } else {
                      openReferenceRail();
                    }
                  }}
                >
                  <MonoIcon name="history" style={styles.sidebarMenuRowGlyph} />
                  <Text style={styles.sidebarMenuRowLabelMinimal}>History</Text>
                  <Text style={styles.sidebarMenuRowValueMinimal}>
                    {historyAvailable ? `${timelineEntries.length} items` : 'Empty'}
                  </Text>
                </Pressable>

                <Pressable
                  style={[
                    styles.sidebarMenuRowMinimal,
                    showArtifactRail ? styles.sidebarMenuRowMinimalActive : null,
                  ]}
                  onPress={() => {
                    if (showArtifactRail) {
                      closeArtifactRail();
                    } else {
                      openArtifactRail();
                    }
                  }}
                >
                  <MonoIcon name="history" style={styles.sidebarMenuRowGlyph} />
                  <Text style={styles.sidebarMenuRowLabelMinimal}>Artifacts</Text>
                  <Text style={styles.sidebarMenuRowValueMinimal}>
                    {activeSessionArtifactCount ? `${activeSessionArtifactCount} items` : 'Empty'}
                  </Text>
                </Pressable>

                <Pressable
                  style={[styles.sidebarMenuRowMinimal, showControls ? styles.sidebarMenuRowMinimalActive : null]}
                  onPress={() => setShowControls((current) => !current)}
                >
                  <MonoIcon name="settings" style={styles.sidebarMenuRowGlyph} />
                  <Text style={styles.sidebarMenuRowLabelMinimal}>Controls</Text>
                  <Text style={styles.sidebarMenuRowValueMinimal}>{showControls ? 'Open' : runtimeLabel}</Text>
                </Pressable>
              </View>
            </View>

            {pinnedProjects.length || pinnedChats.length ? (
              <View style={styles.sidebarPinnedSection}>
                <View style={styles.sidebarListSectionHeader}>
                  <Text style={styles.sidebarListSectionTitle}>Pinned</Text>
                </View>
                <View style={styles.sidebarSimpleList}>
                  {pinnedChats.map(({ session }) => (
                    <Pressable
                      key={`pinned-chat-${session.id}`}
                      style={[
                        styles.sidebarSimpleRow,
                        session.id === sessionId ? styles.sidebarSimpleRowActive : null,
                      ]}
                      onPress={() => void openSession(session.id)}
                    >
                      <View style={styles.sidebarSimpleRowCopy}>
                        <View style={styles.sidebarRunningRow}>
                          {session.is_running ? <View style={styles.sidebarRunningDot} /> : null}
                          <Text style={styles.sidebarSimpleRowTitle} numberOfLines={1}>{session.name}</Text>
                        </View>
                      </View>
                      <Text style={styles.sidebarSimpleRowMeta}>{session.is_running ? 'Running' : formatRelativeTime(session.updated_at)}</Text>
                    </Pressable>
                  ))}
                  {pinnedProjects.map((project) => (
                    <Pressable
                      key={`pinned-project-${project.path}`}
                      style={styles.sidebarSimpleRow}
                      onPress={() => {
                        selectProjectPath(project.path);
                        setSidebarExpanded(true);
                      }}
                    >
                      <View style={styles.sidebarSimpleRowCopy}>
                        <Text style={styles.sidebarSimpleRowTitle} numberOfLines={1}>{project.label}</Text>
                        <Text style={styles.sidebarSimpleRowSubtle} numberOfLines={1}>{project.hint || project.path}</Text>
                      </View>
                      <Text style={styles.sidebarSimpleRowMeta}>Folder</Text>
                    </Pressable>
                  ))}
                </View>
              </View>
            ) : null}

            <View style={styles.sidebarProjectsSection}>
              <View style={styles.sidebarListSectionHeader}>
                <Text style={styles.sidebarListSectionTitle}>Projects</Text>
                <Pressable onPress={() => void promptForProjectFolder()}>
                  <Text style={styles.sidebarSectionActionText}>Add Folder</Text>
                </Pressable>
              </View>
                {projectGroups.length === 0 ? (
                  <View style={styles.emptyCard}>
                    <Text style={styles.emptyTitle}>No folders yet</Text>
                    <Text style={styles.emptyText}>Add a folder or start a new chat to create the first project group in this sidebar.</Text>
                  </View>
                ) : (
                  <View style={styles.sidebarProjectList}>
                    {projectGroups.map((project) => {
                    const projectHasDraft = draftChat?.projectPath === project.path;
                    const projectActionsVisible = hoveredProjectPath === project.path || openProjectMenuPath === project.path;
                    return (
                      <View
                        key={`project-${project.path}`}
                        style={styles.projectCard}
                        {...(Platform.OS === 'web'
                          ? {
                              onMouseEnter: () => setHoveredProjectPath(project.path),
                              onMouseLeave: () => setHoveredProjectPath((current) => (
                                current === project.path ? null : current
                              )),
                            } as any
                          : {})}
                        {...projectDragProps(project.path)}
                      >
                        <View style={styles.projectHeaderRow}>
                          <Pressable
                            style={styles.projectHeaderMain}
                            onPress={() => {
                              setOpenProjectMenuPath(null);
                              setOpenSessionMenuId(null);
                              selectProjectPath(project.path);
                            }}
                          >
                            <Pressable
                              style={styles.projectFolderToggle}
                              onPress={() => toggleProjectCollapsed(project.path)}
                            >
                              <MonoIcon
                                name={project.collapsed ? 'folder_closed' : 'folder_open'}
                                style={styles.projectFolderToggleIcon}
                              />
                            </Pressable>
                            <Text style={styles.projectTitle} numberOfLines={1}>{project.label}</Text>
                          </Pressable>
                          {projectActionsVisible ? (
                            <View style={styles.projectHeaderActions}>
                              <Pressable
                                style={styles.projectHeaderActionButton}
                                onPress={() => {
                                  setOpenProjectMenuPath(null);
                                  void openDraftChat(project.path);
                                }}
                              >
                                <MonoIcon name="plus" style={styles.projectHeaderActionText} />
                              </Pressable>
                              <Pressable
                                ref={setProjectMenuTriggerRef(project.path)}
                                style={styles.projectHeaderActionButton}
                                onPress={() => setOpenProjectMenuPath((current) => (
                                  current === project.path ? null : project.path
                                ))}
                              >
                                <MonoIcon name="more" style={styles.projectHeaderActionText} />
                              </Pressable>
                            </View>
                          ) : null}
                        </View>

	                        {openProjectMenuPath === project.path ? (
	                          <View ref={setProjectMenuRef(project.path)} style={styles.projectMenu}>
	                            <Pressable
	                              style={styles.projectMenuItem}
	                              onPress={() => {
	                                toggleProjectPin(project.path);
	                                setOpenProjectMenuPath(null);
	                              }}
	                            >
	                              <Text style={styles.projectMenuItemText}>{project.pinned ? 'Unpin folder' : 'Pin folder'}</Text>
	                            </Pressable>
	                            <Pressable
	                              style={styles.projectMenuItem}
	                              onPress={() => renameProject(project.path)}
	                            >
	                              <Text style={styles.projectMenuItemText}>Rename folder</Text>
                            </Pressable>
	                            <Pressable
	                              style={styles.projectMenuItem}
	                              onPress={() => removeProjectFromSidebar(project.path)}
	                            >
	                              <Text style={[styles.projectMenuItemText, styles.projectMenuItemTextWarn]}>Remove folder</Text>
	                            </Pressable>
	                          </View>
	                        ) : null}

                        {!project.collapsed ? (
                          <View style={styles.projectContent}>
                            {project.sessions.map((item) => {
                              const selected = item.id === sessionId;
                              const sessionActionsVisible = hoveredSessionId === item.id || openSessionMenuId === item.id;
                              return (
                                <View
                                  key={item.id}
                                  {...(Platform.OS === 'web'
                                    ? {
                                        onMouseEnter: () => {
                                          setHoveredSessionId(item.id);
                                          scheduleSidebarChatTooltip(item, project.path);
                                        },
                                        onMouseLeave: () => {
                                          setHoveredSessionId((current) => (
                                            current === item.id ? null : current
                                          ));
                                          clearSidebarChatTooltipTimer();
                                          hideSidebarChatTooltip(item.id);
                                        },
                                      } as any
                                    : {})}
                                >
                                  <View
                                    ref={setSessionRowRef(item.id)}
                                    style={[styles.projectChatRow, selected ? styles.projectChatRowActive : null]}
                                    {...sessionDragProps(project.path, item.id)}
                                  >
                                    <Pressable
                                      style={styles.projectChatPrimary}
                                      onPress={() => {
                                        setOpenSessionMenuId(null);
                                        clearSidebarChatTooltipTimer();
                                        hideSidebarChatTooltip(item.id);
                                        void openSession(item.id);
                                      }}
                                    >
                                      <View style={styles.projectChatTitleRow}>
                                        <View style={styles.sidebarRunningRow}>
                                          {item.is_running ? <View style={styles.sidebarRunningDot} /> : null}
                                          <Text style={styles.projectChatTitle} numberOfLines={1}>{item.name}</Text>
                                        </View>
                                        <Text style={styles.projectChatAge}>{item.is_running ? 'Running' : formatRelativeTime(item.updated_at)}</Text>
                                      </View>
                                    </Pressable>
                                    {sessionActionsVisible ? (
                                      <View style={styles.projectChatActions}>
                                        <Pressable
                                          ref={setSessionMenuTriggerRef(item.id)}
                                          style={styles.projectChatActionButton}
                                          onPress={() => {
                                            clearSidebarChatTooltipTimer();
                                            hideSidebarChatTooltip(item.id);
                                            setOpenSessionMenuId((current) => (
                                              current === item.id ? null : item.id
                                            ));
                                          }}
                                        >
                                          <MonoIcon name="more" style={styles.projectChatActionText} />
                                        </Pressable>
                                      </View>
                                    ) : null}
                                  </View>
	                                  {openSessionMenuId === item.id ? (
	                                    <View ref={setSessionMenuRef(item.id)} style={styles.projectChatMenu}>
                                          <View style={styles.projectMenuLabelRow}>
                                            <Text style={styles.projectMenuLabelText}>Bot: {telegramBotLabelForSession(item)}</Text>
                                          </View>
	                                      <Pressable
	                                        style={styles.projectMenuItem}
	                                        onPress={() => {
	                                          toggleSessionPin(item);
	                                          setOpenSessionMenuId(null);
	                                        }}
	                                      >
	                                        <Text style={styles.projectMenuItemText}>
	                                          {sidebarState.sessionMeta[item.id]?.pinned ? 'Unpin chat' : 'Pin chat'}
	                                        </Text>
	                                      </Pressable>
                                        <Pressable
                                          style={styles.projectMenuItem}
                                          onPress={() => {
                                            setOpenSessionMenuId(null);
                                            setActiveCommandPanel({ kind: 'session', sessionId: item.id });
                                          }}
                                        >
                                          <Text style={styles.projectMenuItemText}>Chat settings</Text>
                                        </Pressable>
	                                      <Pressable
	                                        style={styles.projectMenuItem}
	                                        onPress={() => void deleteSidebarSession(item)}
	                                      >
                                        <Text style={[styles.projectMenuItemText, styles.projectMenuItemTextWarn]}>Delete chat</Text>
                                      </Pressable>
                                    </View>
                                  ) : null}
                                </View>
                              );
                            })}

                            {project.activity.map((activityItem) => (
                              <View key={activityItem.id} style={styles.projectActivityRow}>
                                <Text style={styles.projectActivityText}>{activityItem.message}</Text>
                                <Text style={styles.projectActivityMeta}>{formatRelativeTime(activityItem.timestamp)}</Text>
                              </View>
                            ))}

                            {project.sessions.length === 0 && !projectHasDraft && project.activity.length === 0 ? (
                              <View style={styles.projectEmptyState}>
                                <Text style={styles.projectEmptyText}>No chats in this folder yet.</Text>
                              </View>
                            ) : null}
                          </View>
                        ) : null}
                      </View>
                    );
                  })}
                  </View>
                )}
              </View>

            {voicePanelActive ? (
              <>
              <View style={styles.sidebarInsetDivider} />
              <View style={styles.voicePanel}>
                <View style={styles.voicePanelHeader}>
                  <View style={styles.voicePanelHeaderCopy}>
                    <Text style={styles.voiceLabel}>Mic / Voice State</Text>
                    <Text style={styles.voiceValue}>{voiceSummary}</Text>
                    <Text style={styles.voiceHint}>{selectedVoicePackSummary}</Text>
                    {voicePackDiagnostics ? (
                      <Text style={styles.voiceHint}>{voicePackDiagnostics}</Text>
                    ) : null}
                  </View>
                  <View style={styles.voicePanelHeaderActions}>
                    <Pressable style={styles.voicePanelHeaderAction} onPress={() => onOpenSetup?.()}>
                      <Text style={styles.voicePanelHeaderActionText}>Open Setup</Text>
                    </Pressable>
                    <Pressable style={styles.voicePanelHeaderAction} onPress={hideVoicePanel}>
                      <Text style={styles.voicePanelHeaderActionText}>Hide Voice</Text>
                    </Pressable>
                  </View>
                </View>

                <View style={styles.voiceLanguageRow}>
                  <Pressable
                    style={[
                      styles.voiceLanguageChip,
                      selectedVoiceEngine === VOICE_ENGINE_ENGLISH ? styles.voiceLanguageChipActive : null,
                      !englishVoicePack?.available || voiceEngineChanging ? styles.voiceModeChipDisabled : null,
                    ]}
                    onPress={() => {
                      void handleVoiceEngineSelection(VOICE_ENGINE_ENGLISH);
                    }}
                  >
                    <Text
                      style={[
                        styles.voiceLanguageChipText,
                        selectedVoiceEngine === VOICE_ENGINE_ENGLISH ? styles.voiceLanguageChipTextActive : null,
                      ]}
                    >
                      {voiceEngineChanging && selectedVoiceEngine !== VOICE_ENGINE_ENGLISH ? 'Switching…' : 'English Path'}
                    </Text>
                  </Pressable>
                  <Pressable
                    style={[
                      styles.voiceLanguageChip,
                      selectedVoiceEngine === VOICE_ENGINE_HEBREW ? styles.voiceLanguageChipActive : null,
                      !hebrewVoicePack?.available || voiceEngineChanging ? styles.voiceModeChipDisabled : null,
                    ]}
                    onPress={() => {
                      void handleVoiceEngineSelection(VOICE_ENGINE_HEBREW);
                    }}
                  >
                    <Text
                      style={[
                        styles.voiceLanguageChipText,
                        selectedVoiceEngine === VOICE_ENGINE_HEBREW ? styles.voiceLanguageChipTextActive : null,
                      ]}
                    >
                      {voiceEngineChanging && selectedVoiceEngine !== VOICE_ENGINE_HEBREW ? 'Switching…' : 'Hebrew Path'}
                    </Text>
                  </Pressable>
                </View>

                <View style={styles.voiceModeRow}>
                  <Pressable
                    style={[
                      styles.voiceModeChip,
                      voiceMode === 'push_to_talk' && !alwaysOnEnabled ? styles.voiceModeChipActive : null,
                      (voiceRunning || voiceRecording || alwaysOnEnabled) ? styles.voiceModeChipDisabled : null,
                    ]}
                    disabled={voiceRunning || voiceRecording || alwaysOnEnabled}
                    onPress={() => setVoiceMode('push_to_talk')}
                  >
                    <Text
                      style={[
                        styles.voiceModeChipText,
                        voiceMode === 'push_to_talk' && !alwaysOnEnabled ? styles.voiceModeChipTextActive : null,
                      ]}
                    >
                      Push To Talk
                    </Text>
                  </Pressable>
                  <Pressable
                    style={[
                      styles.voiceModeChip,
                      (voiceMode === 'always_on' || alwaysOnEnabled) ? styles.voiceModeChipActive : null,
                      (voiceRunning || voiceRecording) && !alwaysOnEnabled ? styles.voiceModeChipDisabled : null,
                    ]}
                    disabled={(voiceRunning || voiceRecording) && !alwaysOnEnabled}
                    onPress={() => setVoiceMode('always_on')}
                  >
                    <Text
                      style={[
                        styles.voiceModeChipText,
                        (voiceMode === 'always_on' || alwaysOnEnabled) ? styles.voiceModeChipTextActive : null,
                      ]}
                    >
                      Always On
                    </Text>
                  </Pressable>
                </View>

                <View style={styles.voiceRibbon}>
                  <View style={styles.voiceRibbonPrimary}>
                    <Text style={styles.voiceLabel}>
                      {voiceMode === 'always_on' || alwaysOnEnabled ? 'Always On' : 'Push To Talk'}
                    </Text>
                    <Text style={styles.voiceHint}>
                      {voiceMode === 'always_on' || alwaysOnEnabled
                        ? ALWAYS_ON_VOICE_AUTO_SEND
                          ? 'The mic stays open locally. Speech above the gate threshold is transcribed and sent when the segment ends.'
                          : 'The mic stays open locally. Speech above the gate threshold is transcribed into the message box for review.'
                        : 'Hold to record. Partial transcript appears below while you speak. Release to send the turn.'}
                    </Text>
                  </View>
                  <View style={styles.voiceRibbonActions}>
                    {voiceMode === 'always_on' || alwaysOnEnabled ? (
                      <>
                        <Pressable
                          style={[styles.ribbonButton, alwaysOnEnabled ? styles.ribbonButtonActive : null]}
                          disabled={voiceRunning && !alwaysOnEnabled}
                          onPress={() => {
                            if (alwaysOnEnabled) {
                              void stopAlwaysOnVoice();
                            } else {
                              void startAlwaysOnVoice();
                            }
                          }}
                        >
                          <Text style={styles.ribbonButtonText}>
                            {alwaysOnEnabled ? 'Stop Always On' : 'Start Always On'}
                          </Text>
                        </Pressable>
                        <Pressable
                          style={[
                            styles.ribbonButton,
                            styles.ribbonButtonMuted,
                            !voiceRecording ? styles.ribbonButtonDisabled : null,
                          ]}
                          disabled={!voiceRecording}
                          onPress={() => void cancelAlwaysOnSegment()}
                        >
                          <Text style={styles.ribbonButtonText}>Cancel Segment</Text>
                        </Pressable>
                      </>
                    ) : (
                      <>
                        <Pressable
                          style={[styles.ribbonButton, voiceRecording ? styles.ribbonButtonActive : null]}
                          disabled={voiceRunning}
                          onPressIn={() => {
                            if (!voiceRecording && !voiceRunning) {
                              void startVoiceCapture();
                            }
                          }}
                          onPressOut={() => {
                            if (voiceRecording || voicePressActiveRef.current) {
                              void stopVoiceCapture(true);
                            }
                          }}
                        >
                          <Text style={styles.ribbonButtonText}>{voiceRecording ? 'Release To Send' : 'Hold To Talk'}</Text>
                        </Pressable>
                        <Pressable
                          style={[styles.ribbonButton, styles.ribbonButtonMuted, !voiceRecording ? styles.ribbonButtonDisabled : null]}
                          disabled={!voiceRecording}
                          onPress={() => void stopVoiceCapture(false)}
                        >
                          <Text style={styles.ribbonButtonText}>Cancel</Text>
                        </Pressable>
                      </>
                    )}
                  </View>
                </View>

                {voiceDraft ? (
                  <View style={styles.transcriptDraft}>
                    <Text style={styles.transcriptLabel}>Live transcript draft</Text>
                    <Text style={styles.transcriptText}>{voiceDraft}</Text>
                  </View>
                ) : null}

                {voiceError ? (
                  <View style={styles.voiceErrorCard}>
                    <Text style={styles.voiceErrorTitle}>Voice diagnostics</Text>
                    <Text style={styles.voiceErrorText}>{voiceError}</Text>
                  </View>
                ) : null}
              </View>
              </>
            ) : null}

            {showReferenceRail && (timelineEntries.length > 0 || referenceEntries.length > 0) ? (
              <View style={styles.referencePanel}>
                <View style={styles.referencePanelHeader}>
                  <View style={styles.referencePanelHeaderCopy}>
                    <Text style={styles.referencePanelTitle}>History</Text>
                    <Text style={styles.referencePanelSummary}>
                      {referenceEntries.length ? `${historySummary} · ${referenceSummary}` : historySummary}
                    </Text>
                  </View>
                  <Pressable style={styles.referencePanelCloseButton} onPress={closeReferenceRail}>
                    <Text style={styles.referencePanelCloseText}>Close</Text>
                  </Pressable>
                </View>
                <ScrollView ref={historyScrollRef} contentContainerStyle={styles.referenceStack}>
                  {timelineEntries.map((entry) => (
                    <View
                      key={`timeline-${entry.id}`}
                      onLayout={(event) => {
                        if (entry.kind === 'message') {
                          historyMessageLayoutRef.current[entry.sourceMessageIndex] = event.nativeEvent.layout.y;
                        }
                      }}
                      style={[
                        styles.referenceCard,
                        entry.kind === 'message' && highlightedMessageIndex === entry.sourceMessageIndex
                          ? styles.searchJumpHighlight
                          : null,
                        entry.tone === 'accent'
                          ? styles.activityItemAccent
                          : entry.tone === 'warn'
                            ? styles.activityItemWarn
                            : entry.tone === 'error'
                              ? styles.activityItemError
                              : null,
                      ]}
                    >
                      <View style={styles.referenceCardHeader}>
                        <Text style={styles.referenceCardEyebrow}>{entry.eyebrow}</Text>
                        <Text style={styles.referenceCardTitle}>{entry.label}</Text>
                      </View>
                      <Text style={styles.referenceCardMeta}>
                        {entry.timestamp ? formatAbsoluteTime(entry.timestamp) : 'timeline event'}
                      </Text>
                      <Text style={styles.referenceCardBody}>{entry.body}</Text>
                    </View>
                  ))}
                </ScrollView>
              </View>
            ) : null}

            {showArtifactRail ? (
              <View style={styles.referencePanel}>
                <View style={styles.referencePanelHeader}>
                  <View style={styles.referencePanelHeaderCopy}>
                    <Text style={styles.referencePanelTitle}>Artifacts</Text>
                    <Text style={styles.referencePanelSummary}>
                      {activeSessionArtifactCount ? `${activeSessionArtifactCount} saved artifacts` : 'No saved artifacts yet'}
                    </Text>
                  </View>
                  <Pressable style={styles.referencePanelCloseButton} onPress={closeArtifactRail}>
                    <Text style={styles.referencePanelCloseText}>Close</Text>
                  </Pressable>
                </View>
                {artifactsLoading ? (
                  <View style={styles.emptyCard}>
                    <Text style={styles.emptyTitle}>Loading artifacts…</Text>
                    <Text style={styles.emptyText}>Pulling saved files, screenshots, and command outputs for this chat.</Text>
                  </View>
                ) : artifactError ? (
                  <View style={styles.emptyCard}>
                    <Text style={styles.emptyTitle}>Artifact view unavailable</Text>
                    <Text style={styles.emptyText}>{artifactError}</Text>
                  </View>
                ) : artifacts.length === 0 ? (
                  <View style={styles.emptyCard}>
                    <Text style={styles.emptyTitle}>No artifacts yet</Text>
                    <Text style={styles.emptyText}>Files, screenshots, OCR, browser captures, uploads, and command outputs for this chat will land here.</Text>
                  </View>
                ) : (
                  <View style={styles.artifactPanelStack}>
                    <ScrollView style={styles.artifactListScroll} contentContainerStyle={styles.artifactList}>
                      {artifacts.map((artifact) => {
                        const selected = artifact.artifact_id === (selectedArtifactId || selectedArtifactSummary?.artifact_id);
                        return (
                          <Pressable
                            key={artifact.artifact_id}
                            style={[styles.artifactRow, selected ? styles.artifactRowActive : null]}
                            onPress={() => {
                              setSelectedArtifactId(artifact.artifact_id);
                              void openArtifactPreview(artifact.artifact_id);
                            }}
                          >
                            <Text style={styles.artifactRowTitle} numberOfLines={1}>{artifact.title}</Text>
                            <Text style={styles.artifactRowMeta} numberOfLines={1}>
                              {artifact.artifact_kind} · {formatRelativeTime(artifact.created_at)}
                            </Text>
                            <Text style={styles.artifactRowPreview} numberOfLines={2}>
                              {artifact.preview_text || artifact.summary_text || 'Saved artifact'}
                            </Text>
                          </Pressable>
                        );
                      })}
                    </ScrollView>
                    <View style={styles.artifactPreviewCard}>
                      <View style={styles.artifactPreviewHeader}>
                        <View style={styles.artifactPreviewHeaderCopy}>
                          <Text style={styles.artifactPreviewTitle} numberOfLines={1}>
                            {selectedArtifactDetail?.title || selectedArtifactSummary?.title || 'Artifact preview'}
                          </Text>
                          <Text style={styles.artifactPreviewMeta} numberOfLines={1}>
                            {selectedArtifactDetail?.artifact_kind || selectedArtifactSummary?.artifact_kind || 'artifact'}
                            {selectedArtifactDetail?.payload_file_name ? ` · ${selectedArtifactDetail.payload_file_name}` : ''}
                          </Text>
                        </View>
                        <View style={styles.artifactPreviewActions}>
                          {selectedArtifactSummary ? (
                            <>
                              <Pressable style={styles.referencePanelCloseButton} onPress={() => void openArtifactExternally(selectedArtifactSummary.artifact_id)}>
                                <Text style={styles.referencePanelCloseText}>Open</Text>
                              </Pressable>
                              <Pressable style={styles.referencePanelCloseButton} onPress={() => void downloadArtifact(selectedArtifactSummary.artifact_id)}>
                                <Text style={styles.referencePanelCloseText}>Download</Text>
                              </Pressable>
                            </>
                          ) : null}
                        </View>
                      </View>
                      {artifactDetailLoading ? (
                        <Text style={styles.emptyText}>Loading preview…</Text>
                      ) : selectedArtifactDetail?.image_base64 ? (
                        <Image
                          source={{ uri: `data:${selectedArtifactDetail.mime_type};base64,${selectedArtifactDetail.image_base64}` }}
                          style={styles.artifactPreviewImage}
                          resizeMode="contain"
                        />
                      ) : (
                        <ScrollView style={styles.artifactPreviewScroll}>
                          <Text style={styles.artifactPreviewText}>
                            {selectedArtifactDetail?.inline_text
                              || selectedArtifactDetail?.preview_text
                              || selectedArtifactSummary?.preview_text
                              || 'No inline preview available.'}
                          </Text>
                        </ScrollView>
                      )}
                    </View>
                  </View>
                )}
              </View>
            ) : null}

            {showControls ? (
              <>
                <View style={styles.controlColumnHeader}>
                  <View style={styles.controlColumnHeaderCopy}>
                    <Text style={styles.eyebrow}>Controls</Text>
                    <Text style={styles.controlColumnTitle}>Session Controls</Text>
                    <Text style={styles.controlColumnText}>Run controls and deep links for this desktop session.</Text>
                  </View>
                  <Pressable style={styles.controlColumnCloseButton} onPress={() => setShowControls(false)}>
                    <Text style={styles.controlColumnCloseText}>Close</Text>
                  </Pressable>
                </View>
                <FoldSection
                  title="Runtime + Run Control"
                  summary={`${runtimeMode || 'desktop'} · heartbeat ${heartbeatLabel}`}
                  defaultOpen
                >
                  <Text style={styles.controlBody}>
                    Electron owns attach-or-launch. The renderer only talks to the local app API and shared session store.
                  </Text>
                  <View style={styles.controlMetricRow}>
                    <View style={styles.controlMetric}>
                      <Text style={styles.controlMetricLabel}>Mode</Text>
                      <Text style={styles.controlMetricValue}>{runtimeMode || 'desktop'}</Text>
                    </View>
                    <View style={styles.controlMetric}>
                      <Text style={styles.controlMetricLabel}>Heartbeat</Text>
                      <Text style={styles.controlMetricValue}>{heartbeatLabel}</Text>
                    </View>
                  </View>
                  <View style={styles.shutdownPreferenceCard}>
                    <View style={styles.shutdownPreferenceCopy}>
                      <Text style={styles.shutdownPreferenceTitle}>Desktop close behavior</Text>
                      <Text style={styles.shutdownPreferenceText}>
                        {keepRuntimeOnAppClose
                          ? 'Closing the desktop app will leave the local agent running so Telegram can stay live.'
                          : 'Closing the desktop app will stop the local agent by default so this machine fully shuts down.'}
                      </Text>
                    </View>
                    <Pressable
                      style={[
                        styles.actionButton,
                        keepRuntimeOnAppClose ? styles.actionButtonNeutral : styles.actionButtonWarn,
                        savingCloseBehavior ? styles.actionButtonDisabled : null,
                      ]}
                      onPress={() => void toggleKeepRuntimeOnAppClose()}
                      disabled={savingCloseBehavior}
                    >
                      <Text style={styles.actionButtonText}>
                        {savingCloseBehavior
                          ? 'Saving...'
                          : keepRuntimeOnAppClose
                            ? 'Keep Agent Alive: On'
                            : 'Keep Agent Alive: Off'}
                      </Text>
                    </Pressable>
                  </View>
                  <View style={styles.shutdownPreferenceCard}>
                    <View style={styles.shutdownPreferenceCopy}>
                      <Text style={styles.shutdownPreferenceTitle}>Long Task: next message</Text>
                      <Text style={styles.shutdownPreferenceText}>
                        {taskBoardArmedNextTurn
                          ? 'Armed. The next message in this shared chat, from desktop or Telegram, will start a managed task board.'
                          : 'Off. Casual messages stay conversational, and simple work requests will not open a managed task board unless you arm this first.'}
                      </Text>
                    </View>
                    <Pressable
                      style={[
                        styles.actionButton,
                        taskBoardArmedNextTurn ? styles.actionButtonNeutral : null,
                      ]}
                      onPress={() => void toggleTaskBoardArmNextTurn()}
                    >
                      <Text style={styles.actionButtonText}>
                        {taskBoardArmedNextTurn ? 'Long Task Armed' : 'Arm Next Message'}
                      </Text>
                    </Pressable>
                  </View>
                  <View style={styles.actionRow}>
                    <Pressable style={styles.actionButton} onPress={() => void runControl('pause')}>
                      <Text style={styles.actionButtonText}>Pause Run</Text>
                    </Pressable>
                    <Pressable style={styles.actionButton} onPress={() => void runControl('restart')}>
                      <Text style={styles.actionButtonText}>Restart Run</Text>
                    </Pressable>
                    <Pressable style={[styles.actionButton, styles.actionButtonWarn]} onPress={() => void runControl('stop')}>
                      <Text style={styles.actionButtonText}>Stop Run</Text>
                    </Pressable>
                  </View>
                </FoldSection>

                <FoldSection
                  title="Control Surfaces"
                  summary="Cron center, agent controls, memory, jobs"
                >
                  <Text style={styles.controlBody}>
                    Advanced controls stay available without putting phone-specific setup back into the desktop flow.
                  </Text>
                  <View style={styles.linkStack}>
                    <Pressable style={styles.deepLinkButton} onPress={() => router.push('/cron')}>
                      <Text style={styles.deepLinkButtonText}>Open Cron Center</Text>
                    </Pressable>
                    <Pressable style={styles.deepLinkButton} onPress={() => router.push('/agent')}>
                      <Text style={styles.deepLinkButtonText}>Open Agent Controls</Text>
                    </Pressable>
                  </View>
                  <View style={styles.scopeTagRow}>
                    {['memory', 'config', 'skills', 'subagents', 'heartbeat', 'jobs'].map((tag) => (
                      <View key={tag} style={styles.scopeTag}>
                        <Text style={styles.scopeTagText}>{tag}</Text>
                      </View>
                    ))}
                  </View>
                </FoldSection>

                <FoldSection
                  title="Telegram Help"
                  summary="Optional shared-session channel"
                >
                  <Text style={styles.controlBody}>
                    Desktop is the default surface, but Telegram can attach to the same shared sessions so you can switch channels mid-conversation.
                  </Text>
                  <View style={styles.telegramSteps}>
                    <Text style={styles.telegramStep}>1. Open Telegram and talk to BotFather.</Text>
                    <Text style={styles.telegramStep}>2. Create a bot and copy the bot token.</Text>
                    <Text style={styles.telegramStep}>3. Get your numeric Telegram user ID from userinfobot.</Text>
                    <Text style={styles.telegramStep}>4. Put those values into TELEGRAM_BOT_TOKEN and ALLOWED_USER_IDS.</Text>
                    {envFilePath ? (
                      <Text style={styles.telegramStep}>Env file: {envFilePath}</Text>
                    ) : null}
                    <Text style={styles.telegramStep}>
                      After restarting the agent runtime, Telegram, desktop, and mobile all read from the same shared session rail.
                    </Text>
                  </View>
                </FoldSection>

                <FoldSection
                  title="Session Summary"
                  summary={`${jobs.length} jobs${dueJobs ? ` · ${dueJobs} due` : ''}`}
                >
                  <View style={styles.summaryLine}>
                    <Text style={styles.summaryLabel}>Model</Text>
                    <Text style={styles.summaryValue}>{overview?.current_model || 'unknown'}</Text>
                  </View>
                  <View style={styles.summaryLine}>
                    <Text style={styles.summaryLabel}>Variant</Text>
                    <Text style={styles.summaryValue}>{overview?.current_variant || 'unknown'}</Text>
                  </View>
                  <View style={styles.summaryLine}>
                    <Text style={styles.summaryLabel}>Planner</Text>
                    <Text style={styles.summaryValue}>{overview?.planner_model || 'automatic'}</Text>
                  </View>
                  <View style={styles.summaryLine}>
                    <Text style={styles.summaryLabel}>Turns</Text>
                    <Text style={styles.summaryValue}>{overview ? String(overview.max_turns) : '-'}</Text>
                  </View>
                  <View style={styles.summaryLine}>
                    <Text style={styles.summaryLabel}>Cron jobs</Text>
                    <Text style={styles.summaryValue}>
                      {jobs.length} total{dueJobs ? ` · ${dueJobs} due` : ''}
                    </Text>
                  </View>
                  <View style={styles.summaryLine}>
                    <Text style={styles.summaryLabel}>Workspace</Text>
                    <Text style={styles.summaryValue} numberOfLines={2}>
                      {overview?.workspace || 'not loaded'}
                    </Text>
                  </View>
                </FoldSection>

                <FoldSection
                  title="Run / Tool Activity"
                  summary={activitySummary}
                >
                  {activity.length === 0 ? (
                    <Text style={styles.controlBody}>Tool calls, runtime notices, and voice diagnostics will accumulate here.</Text>
                  ) : (
                    <ScrollView style={styles.activityScroll} contentContainerStyle={styles.activityList}>
                      {activity.map((item) => (
                        <View
                          key={item.id}
                          style={[
                            styles.activityItem,
                            item.tone === 'accent'
                              ? styles.activityItemAccent
                              : item.tone === 'warn'
                                ? styles.activityItemWarn
                                : item.tone === 'error'
                                  ? styles.activityItemError
                                  : null,
                          ]}
                        >
                          <Text style={styles.activityTime}>{new Date(item.timestamp).toLocaleTimeString()}</Text>
                          <Text style={styles.activityText}>{item.text}</Text>
                        </View>
                      ))}
                    </ScrollView>
                  )}
                </FoldSection>
              </>
            ) : null}
          </ScrollView>
        ) : null}
      </View>

      {Platform.OS === 'web' && sidebarChatTooltip ? (
        <View pointerEvents="none" style={styles.sidebarChatTooltipLayer}>
          <View
            style={[
              styles.sidebarChatTooltipCard,
              {
                top: sidebarChatTooltip.top,
                left: sidebarChatTooltip.left,
              },
            ]}
          >
            <Text style={styles.sidebarChatTooltipTitle} numberOfLines={1}>
              {sidebarChatTooltip.title}
            </Text>
            <Text style={styles.sidebarChatTooltipMeta} numberOfLines={1}>
              {sidebarChatTooltip.projectPath}
            </Text>
            <Text style={styles.sidebarChatTooltipMetaSecondary} numberOfLines={1}>
              {sidebarChatTooltip.botLabel}
            </Text>
          </View>
        </View>
      ) : null}

      {sidebarSearchOpen ? (
        <Pressable style={styles.sidebarSearchModalOverlay} onPress={closeSidebarSearchModal}>
          <Pressable
            ref={sidebarSearchModalRef}
            style={styles.sidebarSearchModalCard}
            onPress={(event: any) => event?.stopPropagation?.()}
          >
            <View style={styles.sidebarSearchModalInputShell}>
              <MonoIcon name="search" style={styles.sidebarSearchModalInputGlyph} />
              <TextInput
                ref={sidebarSearchInputRef}
                style={styles.sidebarSearchModalInput}
                value={sidebarSearch}
                onChangeText={setSidebarSearch}
                placeholder="Search chats"
                placeholderTextColor="#8f8f8f"
              />
            </View>

            {!sidebarSearchQuery ? (
              <>
                <Text style={styles.sidebarSearchSectionLabel}>Recent chats</Text>
                <ScrollView style={styles.sidebarSearchResultsScroll} contentContainerStyle={styles.sidebarSearchResultsList}>
                  {recentSearchSessions.map((item) => (
                    <Pressable
                      key={`recent-chat-${item.id}`}
                      style={styles.sidebarSearchResultRow}
                      onPress={() => void openSearchResult({
                        kind: 'session',
                        sessionId: item.id,
                        projectPath: item.workspace || '',
                      })}
                    >
                      <View style={styles.sidebarSearchResultLine}>
                        <Text style={styles.sidebarSearchResultPrimary} numberOfLines={1}>{item.name}</Text>
                        <Text style={styles.sidebarSearchResultSecondary} numberOfLines={1}>
                          {projectPathBasename(item.workspace || '') || 'chat'}
                        </Text>
                      </View>
                    </Pressable>
                  ))}
                </ScrollView>
              </>
            ) : sidebarSearchLoading ? (
              <View style={styles.sidebarSearchEmptyState}>
                <Text style={styles.sidebarSearchEmptyTitle}>Searching…</Text>
                <Text style={styles.sidebarSearchEmptyText}>Scanning folders, chats, and saved message history.</Text>
              </View>
            ) : sidebarSearchError ? (
              <View style={styles.sidebarSearchEmptyState}>
                <Text style={styles.sidebarSearchEmptyTitle}>Search unavailable</Text>
                <Text style={styles.sidebarSearchEmptyText}>{sidebarSearchError}</Text>
              </View>
            ) : mergedSidebarSearchResults.length === 0 ? (
              <View style={styles.sidebarSearchEmptyState}>
                <Text style={styles.sidebarSearchEmptyTitle}>No matches</Text>
                <Text style={styles.sidebarSearchEmptyText}>Try a shorter phrase or one of the key words from the chat.</Text>
              </View>
            ) : (
              <ScrollView style={styles.sidebarSearchResultsScroll} contentContainerStyle={styles.sidebarSearchResultsList}>
                {mergedSidebarSearchResults.map((result, index) => {
                  const searchTarget: SearchResultTarget = result.kind === 'message'
                    ? {
                        kind: 'message',
                        sessionId: result.session_id || '',
                        projectPath: result.project_path,
                        messageIndex: Number(result.message_index ?? -1),
                      }
                    : {
                        kind: 'session',
                        sessionId: result.session_id || '',
                        projectPath: result.project_path,
                      };
                  const primaryText = result.kind === 'session'
                    ? result.session_name || 'Untitled chat'
                    : result.snippet || result.session_name || 'Message match';
                  const secondaryText = result.kind === 'session'
                    ? projectPathBasename(result.project_path) || 'chat'
                    : result.session_name || projectPathBasename(result.project_path) || 'chat';
                  return (
                    <Pressable
                      key={`${result.kind}-${result.session_id || 'session'}-${result.message_index ?? index}`}
                      style={styles.sidebarSearchResultRow}
                      onPress={() => void openSearchResult(searchTarget)}
                    >
                      <View style={styles.sidebarSearchResultLine}>
                        <Text style={styles.sidebarSearchResultPrimary} numberOfLines={1}>
                          {primaryText}
                        </Text>
                        <Text style={styles.sidebarSearchResultSecondary} numberOfLines={1}>
                          {secondaryText}
                        </Text>
                      </View>
                    </Pressable>
                  );
                })}
              </ScrollView>
            )}
          </Pressable>
        </Pressable>
      ) : null}

      {pendingDraftBotProjectPath ? (
        <Pressable style={styles.sidebarSearchModalOverlay} onPress={() => setPendingDraftBotProjectPath(null)}>
          <Pressable
            style={styles.sidebarSearchModalCard}
            onPress={(event: any) => event?.stopPropagation?.()}
          >
            <Text style={styles.sidebarSearchSectionLabel}>Choose a Telegram bot for the new chat</Text>
            <Text style={styles.sidebarSearchEmptyText}>
              Messages from this chat will mirror to the selected bot. You can reassign it later in chat settings.
            </Text>
            <ScrollView style={styles.sidebarSearchResultsScroll} contentContainerStyle={styles.sidebarSearchResultsList}>
              {telegramBotConfigs.map((bot) => (
                <Pressable
                  key={`draft-bot-${bot.id}`}
                  style={styles.sidebarSearchResultRow}
                  onPress={() => void confirmDraftBotSelection(bot.id)}
                >
                  <View style={styles.sidebarSearchResultLine}>
                    <Text style={styles.sidebarSearchResultPrimary} numberOfLines={1}>{bot.label}</Text>
                    <Text style={styles.sidebarSearchResultSecondary} numberOfLines={1}>
                      {bot.bot_token}{bot.is_default ? ' · default' : ''}
                    </Text>
                  </View>
                </Pressable>
              ))}
            </ScrollView>
            <View style={styles.commandPanelActionRow}>
              <Pressable
                style={styles.commandPanelSecondaryAction}
                onPress={() => setPendingDraftBotProjectPath(null)}
              >
                <Text style={styles.commandPanelSecondaryActionText}>Cancel</Text>
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  monoIconBase: {
    color: '#dfe8f5',
    fontSize: 14,
    fontWeight: '500',
    textAlign: 'center',
  },
  shell: {
    flex: 1,
    flexDirection: 'row',
    gap: 14,
    alignItems: 'stretch',
    position: 'relative',
  },
  sidebarDock: {
    flexShrink: 0,
    alignItems: 'stretch',
    backgroundColor: '#081122',
    borderRadius: 0,
    borderWidth: 1,
    borderColor: '#1d2946',
    overflow: 'hidden',
  },
  sidebarDockCollapsed: {
    width: 68,
  },
  sidebarDockExpanded: {
    width: 372,
    maxWidth: 420,
    flexDirection: 'row',
  },
  utilityRail: {
    width: '100%',
    paddingVertical: 14,
    paddingHorizontal: 8,
    gap: 10,
    alignItems: 'center',
  },
  utilityRailExpanded: {
    width: 70,
    flexShrink: 0,
    borderRightWidth: 1,
    borderRightColor: '#1d2946',
    alignItems: 'stretch',
    justifyContent: 'flex-start',
  },
  utilityRailButton: {
    width: 52,
    height: 52,
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: 'transparent',
    paddingVertical: 0,
    paddingHorizontal: 0,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
  },
  utilityRailButtonHovered: {
    backgroundColor: '#101b32',
    borderColor: '#31517d',
  },
  utilityRailButtonActive: {
    backgroundColor: 'transparent',
    borderColor: 'transparent',
  },
  utilityRailIcon: {
    color: '#f7fbff',
    fontSize: 19,
    fontWeight: '500',
  },
  utilityRailLabel: {
    color: '#9ab3d7',
    fontSize: 10,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  utilityRailLabelActive: {
    color: '#f7fbff',
  },
  utilityRailDivider: {
    width: '100%',
    height: 1,
    backgroundColor: '#1d2946',
    marginVertical: 2,
  },
  utilityRailTab: {
    width: '100%',
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#101b32',
    borderWidth: 1,
    borderColor: '#1d2946',
    paddingVertical: 10,
    paddingHorizontal: 8,
    alignItems: 'center',
    gap: 4,
  },
  utilityRailTabExpanded: {
    minHeight: 52,
    alignItems: 'flex-start',
    paddingHorizontal: 12,
  },
  utilityRailTabActive: {
    backgroundColor: '#172947',
    borderColor: '#62d2ff',
  },
  utilityRailTabDisabled: {
    opacity: 0.62,
  },
  utilityRailTabLabel: {
    color: '#d7e7ff',
    fontSize: 10,
    fontWeight: '800',
    textAlign: 'center',
  },
  utilityRailTabLabelExpanded: {
    width: '100%',
    fontSize: 12,
    textAlign: 'left',
  },
  utilityRailTabLabelActive: {
    color: '#f7fbff',
  },
  utilityRailTabMeta: {
    color: '#7f97bc',
    fontSize: 9,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    textAlign: 'center',
  },
  utilityRailTabMetaExpanded: {
    textAlign: 'left',
  },
  utilityRailTabMetaActive: {
    color: '#62d2ff',
  },
  sessionsRail: {
    width: 280,
    borderRadius: 28,
    backgroundColor: '#0d152a',
    borderWidth: 1,
    borderColor: '#1d2a47',
    padding: 18,
    gap: 14,
  },
  railHeader: {
    gap: 14,
  },
  railTitleBlock: {
    gap: 6,
  },
  railHeaderActions: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
  },
  eyebrow: {
    color: '#7ea3d8',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
  },
  railTitle: {
    color: '#f7fbff',
    fontSize: 26,
    fontWeight: '800',
  },
  railText: {
    color: '#98accd',
    fontSize: 13,
    lineHeight: 19,
  },
  primaryRailButton: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#d4ff65',
    paddingVertical: 12,
    paddingHorizontal: 14,
    alignItems: 'center',
  },
  primaryRailButtonText: {
    color: '#0b1325',
    fontWeight: '800',
  },
  secondaryRailButton: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#17253f',
    paddingVertical: 12,
    paddingHorizontal: 14,
    alignItems: 'center',
  },
  secondaryRailButtonText: {
    color: '#dbe7fb',
    fontWeight: '800',
  },
  railMetaRow: {
    flexDirection: 'row',
    gap: 10,
  },
  railMetaCard: {
    flex: 1,
    borderRadius: 16,
    backgroundColor: '#121f39',
    padding: 12,
    gap: 4,
  },
  metaLabel: {
    color: '#8397ba',
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  metaValue: {
    color: '#eef5ff',
    fontWeight: '700',
  },
  sidebarContentStack: {
    gap: 18,
    paddingHorizontal: 14,
    paddingVertical: 14,
    paddingBottom: 18,
  },
  sidebarNavStack: {
    gap: 12,
  },
  sidebarListRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  sidebarListRowIcon: {
    color: '#f4f8ff',
    fontSize: 16,
    width: 20,
    textAlign: 'center',
  },
  sidebarListRowCopy: {
    flex: 1,
    gap: 1,
  },
  sidebarListRowTitle: {
    color: '#f4f8ff',
    fontSize: 15,
    fontWeight: '700',
  },
  sidebarListRowText: {
    color: '#8f8f8f',
    fontSize: 11,
    lineHeight: 15,
  },
  sidebarListRowMeta: {
    color: '#8f8f8f',
    fontSize: 11,
    fontWeight: '700',
  },
  sidebarSearchShell: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#2a2a2a',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  sidebarSearchGlyph: {
    color: '#9a9a9a',
    fontSize: 13,
  },
  sidebarSearchButtonText: {
    color: '#dfe8f5',
    fontSize: 14,
    fontWeight: '500',
  },
  sidebarComputerTabsRow: {
    flexDirection: 'row',
    gap: 8,
  },
  sidebarComputerTab: {
    flex: 1,
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#242424',
    paddingHorizontal: 12,
    paddingVertical: 8,
    alignItems: 'center',
  },
  sidebarComputerTabActive: {
    backgroundColor: '#323232',
  },
  sidebarComputerTabDisabled: {
    opacity: 0.6,
  },
  sidebarComputerTabText: {
    color: '#a2a2a2',
    fontSize: 11,
    fontWeight: '700',
  },
  sidebarComputerTabTextActive: {
    color: '#f4f8ff',
  },
  sidebarMenuList: {
    gap: 4,
  },
  sidebarMenuRowMinimal: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    paddingHorizontal: 10,
    paddingVertical: 9,
  },
  sidebarMenuRowMinimalActive: {
    backgroundColor: '#2d2d2d',
  },
  sidebarMenuRowMinimalDisabled: {
    opacity: 0.55,
  },
  sidebarMenuRowGlyph: {
    color: '#9b9b9b',
    fontSize: 16,
    width: 22,
    textAlign: 'center',
  },
  sidebarMenuRowLabelMinimal: {
    flex: 1,
    color: '#efefef',
    fontSize: 14,
    fontWeight: '600',
  },
  sidebarMenuRowValueMinimal: {
    color: '#8f8f8f',
    fontSize: 11,
    fontWeight: '700',
  },
  sidebarListSectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  sidebarListSectionTitle: {
    color: '#7f7f7f',
    fontSize: 12,
    fontWeight: '700',
  },
  sidebarSectionActionText: {
    color: '#bdbdbd',
    fontSize: 11,
    fontWeight: '700',
  },
  sidebarSimpleList: {
    gap: 4,
  },
  sidebarSimpleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  sidebarSimpleRowActive: {
    backgroundColor: '#363636',
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
  },
  sidebarSimpleRowCopy: {
    flex: 1,
    gap: 2,
  },
  sidebarRunningRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    flex: 1,
  },
  sidebarRunningDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: '#d4ff65',
  },
  sidebarSimpleRowTitle: {
    color: '#efefef',
    fontSize: 14,
    fontWeight: '600',
  },
  sidebarSimpleRowSubtle: {
    color: '#777',
    fontSize: 11,
  },
  sidebarSimpleRowMeta: {
    color: '#8b8b8b',
    fontSize: 11,
    fontWeight: '700',
  },
  sidebarProjectList: {
    gap: 10,
  },
  sidebarChatsCard: {
    gap: 14,
  },
  sidebarChatsHeader: {
    borderBottomWidth: 1,
    borderBottomColor: '#1d2946',
    paddingBottom: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
  },
  sidebarChatsHeaderCopy: {
    flex: 1,
    gap: 4,
  },
  sidebarChatsTitle: {
    color: '#f7fbff',
    fontSize: 22,
    fontWeight: '900',
  },
  sidebarChatsText: {
    color: '#8fa5c7',
    fontSize: 12,
    lineHeight: 18,
  },
  sidebarChatsCloseButton: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#17253f',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  sidebarChatsCloseText: {
    color: '#dbe7fb',
    fontWeight: '900',
    fontSize: 12,
  },
  sidebarChatActionRow: {
    flexDirection: 'row',
    gap: 10,
  },
  secondaryRailButtonCompact: {
    minWidth: 112,
  },
  sidebarSearchCard: {
    borderRadius: 18,
    backgroundColor: '#121f39',
    borderWidth: 1,
    borderColor: '#203458',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  sidebarSearchInput: {
    color: '#edf5ff',
    fontSize: 14,
    paddingVertical: 0,
  },
  sidebarSearchModalOverlay: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    backgroundColor: 'rgba(4, 9, 18, 0.62)',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 36,
    paddingVertical: 32,
    zIndex: 80,
  },
  sidebarSearchModalCard: {
    width: '100%',
    maxWidth: 620,
    maxHeight: '72%',
    backgroundColor: '#262626',
    borderRadius: 22,
    paddingHorizontal: 12,
    paddingVertical: 12,
    gap: 8,
  },
  sidebarChatTooltipLayer: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    zIndex: 40,
  },
  sidebarChatTooltipCard: {
    position: 'absolute',
    width: 296,
    borderRadius: 18,
    backgroundColor: '#2c2c2c',
    paddingHorizontal: 14,
    paddingVertical: 11,
    gap: 4,
  },
  sidebarChatTooltipTitle: {
    color: '#f5f5f5',
    fontSize: 15,
    fontWeight: '700',
  },
  sidebarChatTooltipMeta: {
    color: '#c8c8c8',
    fontSize: 12,
    lineHeight: 16,
  },
  sidebarChatTooltipMetaSecondary: {
    color: '#979797',
    fontSize: 12,
    lineHeight: 16,
  },
  sidebarSearchModalInputShell: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: 16,
    backgroundColor: '#333333',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  sidebarSearchModalInputGlyph: {
    color: '#9a9a9a',
    fontSize: 13,
  },
  sidebarSearchModalInput: {
    flex: 1,
    color: '#f5f5f5',
    fontSize: 15,
    paddingVertical: 0,
  },
  sidebarSearchSectionLabel: {
    color: '#8e8e8e',
    fontSize: 12,
    fontWeight: '600',
    paddingHorizontal: 6,
  },
  sidebarSearchEmptyState: {
    paddingVertical: 18,
    paddingHorizontal: 6,
    gap: 6,
  },
  sidebarSearchEmptyTitle: {
    color: '#eef6ff',
    fontSize: 15,
    fontWeight: '700',
  },
  sidebarSearchEmptyText: {
    color: '#8ca4c8',
    fontSize: 13,
    lineHeight: 20,
  },
  sidebarSearchResultsScroll: {
    flexGrow: 0,
  },
  sidebarSearchResultsList: {
    gap: 4,
    paddingBottom: 6,
  },
  sidebarSearchResultRow: {
    backgroundColor: '#383838',
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  sidebarSearchResultLine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  sidebarSearchResultPrimary: {
    flex: 1,
    color: '#f5f5f5',
    fontSize: 14,
    fontWeight: '700',
  },
  sidebarSearchResultSecondary: {
    maxWidth: '34%',
    color: '#a4a4a4',
    fontSize: 12,
    fontWeight: '500',
  },
  sidebarPinnedSection: {
    gap: 10,
  },
  sidebarSectionTitle: {
    color: '#f7fbff',
    fontSize: 15,
    fontWeight: '900',
  },
  sidebarSectionMeta: {
    color: '#8aa2c8',
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  pinnedShortcutCard: {
    borderRadius: 18,
    backgroundColor: '#131f37',
    borderWidth: 1,
    borderColor: '#22365a',
    padding: 12,
    gap: 4,
  },
  pinnedShortcutLabel: {
    color: '#7ea3d8',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
    letterSpacing: 0.9,
  },
  pinnedShortcutTitle: {
    color: '#f4f8ff',
    fontSize: 14,
    fontWeight: '900',
  },
  pinnedShortcutMeta: {
    color: '#97adcf',
    fontSize: 12,
    lineHeight: 17,
  },
  sidebarProjectsSection: {
    gap: 12,
  },
  sidebarProjectsHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 10,
  },
  projectCard: {
    borderRadius: 0,
    backgroundColor: 'transparent',
    borderWidth: 0,
    borderColor: 'transparent',
    overflow: 'visible',
  },
  projectCardSelected: {
    backgroundColor: 'transparent',
  },
  projectHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    paddingVertical: 4,
  },
  projectHeaderMain: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  projectFolderToggle: {
    paddingVertical: 1,
    paddingRight: 2,
  },
  projectFolderToggleIcon: {
    color: '#d2dae6',
    fontSize: 18,
    fontWeight: '500',
  },
  projectTitle: {
    color: '#f5f5f5',
    fontSize: 14,
    fontWeight: '700',
  },
  projectMeta: {
    color: '#7f7f7f',
    fontSize: 11,
    lineHeight: 15,
  },
  projectHeaderActions: {
    flexDirection: 'row',
    gap: 6,
    justifyContent: 'flex-end',
  },
  projectHeaderActionButton: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: 'transparent',
    minWidth: 26,
    minHeight: 26,
    paddingHorizontal: 6,
    paddingVertical: 4,
    alignItems: 'center',
    justifyContent: 'center',
  },
  projectHeaderActionText: {
    color: '#8ea0bd',
    fontSize: 14,
    fontWeight: '500',
  },
  projectActionIconActive: {
    color: '#dfe8f5',
  },
  projectMenu: {
    alignSelf: 'flex-end',
    minWidth: 144,
    backgroundColor: '#2d2d2d',
    borderRadius: 12,
    paddingVertical: 4,
    marginBottom: 4,
  },
  projectMenuItem: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  projectMenuItemText: {
    color: '#f0f0f0',
    fontSize: 12,
    fontWeight: '600',
  },
  projectMenuItemTextWarn: {
    color: '#ffb8b8',
  },
  projectContent: {
    borderTopWidth: 0,
    borderTopColor: 'transparent',
    paddingLeft: 24,
    paddingRight: 0,
    paddingTop: 2,
    paddingBottom: 4,
    gap: 2,
  },
  projectChatRow: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: 'transparent',
    paddingLeft: 8,
    paddingRight: 4,
    paddingVertical: 5,
    flexDirection: 'row',
    gap: 8,
    alignItems: 'center',
  },
  projectChatRowDraft: {
    backgroundColor: 'transparent',
  },
  projectChatRowActive: {
    backgroundColor: '#162033',
    borderWidth: 1,
    borderColor: '#415b84',
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
  },
  searchJumpHighlight: {
    backgroundColor: '#213254',
  },
  projectChatCopy: {
    flex: 1,
    gap: 4,
  },
  projectChatPrimary: {
    flex: 1,
    gap: 2,
  },
  projectChatTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  projectChatTitle: {
    flex: 1,
    color: '#f0f0f0',
    fontSize: 13,
    fontWeight: '500',
  },
  projectChatAge: {
    color: '#8b8b8b',
    fontSize: 10,
    fontWeight: '700',
  },
  projectChatMeta: {
    color: '#7f7f7f',
    fontSize: 11,
    lineHeight: 15,
  },
  projectChatPreview: {
    color: '#8f8f8f',
    fontSize: 11,
    lineHeight: 15,
  },
  projectChatActions: {
    alignItems: 'flex-end',
    gap: 6,
  },
  projectChatMenu: {
    alignSelf: 'flex-end',
    minWidth: 136,
    backgroundColor: '#2d2d2d',
    borderRadius: 12,
    paddingVertical: 6,
    marginRight: 4,
    marginBottom: 4,
  },
  projectMenuLabelRow: {
    paddingHorizontal: 12,
    paddingTop: 4,
    paddingBottom: 8,
  },
  projectMenuLabelText: {
    color: '#9f9f9f',
    fontSize: 11,
    fontWeight: '700',
  },
  projectChatBadge: {
    borderRadius: 0,
    backgroundColor: '#3f3f3f',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  projectChatBadgeText: {
    color: '#f0f0f0',
    fontSize: 10,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.7,
  },
  projectChatActionButton: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: 'transparent',
    minWidth: 20,
    paddingHorizontal: 4,
    paddingVertical: 2,
    alignItems: 'center',
  },
  projectChatActionText: {
    color: '#7889a6',
    fontSize: 12,
    fontWeight: '500',
  },
  projectActivityRow: {
    borderRadius: 0,
    backgroundColor: 'transparent',
    paddingHorizontal: 8,
    paddingVertical: 6,
    gap: 3,
  },
  projectActivityText: {
    color: '#b8b8b8',
    fontSize: 11,
    lineHeight: 15,
  },
  projectActivityMeta: {
    color: '#777',
    fontSize: 10,
    textTransform: 'uppercase',
    letterSpacing: 0.7,
  },
  projectEmptyState: {
    borderRadius: 0,
    backgroundColor: 'transparent',
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  projectEmptyText: {
    color: '#8b8b8b',
    fontSize: 11,
    lineHeight: 15,
  },
  sidebarSecondaryToggleRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  sidebarSecondaryToggle: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#16243d',
    borderWidth: 1,
    borderColor: '#22385f',
    paddingHorizontal: 12,
    paddingVertical: 10,
    minWidth: 88,
    alignItems: 'center',
  },
  sidebarSecondaryToggleActive: {
    backgroundColor: '#1d3454',
    borderColor: '#62d2ff',
  },
  sidebarSecondaryToggleDisabled: {
    opacity: 0.55,
  },
  sidebarSecondaryToggleText: {
    color: '#edf5ff',
    fontSize: 12,
    fontWeight: '900',
  },
  sessionList: {
    flex: 1,
  },
  sessionListContent: {
    gap: 12,
    paddingBottom: 6,
  },
  sessionCard: {
    borderRadius: 18,
    backgroundColor: '#131f37',
    borderWidth: 1,
    borderColor: '#1c2946',
    padding: 14,
    gap: 6,
  },
  sessionCardActive: {
    backgroundColor: '#172947',
    borderColor: '#62d2ff',
  },
  sessionCardTitle: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '700',
  },
  sessionCardMeta: {
    color: '#8ea5cb',
    fontSize: 12,
  },
  sessionCardPreview: {
    color: '#dbe7fb',
    fontSize: 13,
    lineHeight: 18,
  },
  channelRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 2,
  },
  channelBadge: {
    borderRadius: 999,
    backgroundColor: '#213556',
    paddingHorizontal: 9,
    paddingVertical: 4,
  },
  channelBadgeText: {
    color: '#9fd7ff',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  conversationColumn: {
    flex: 1,
    gap: 14,
  },
  conversationColumnDraftStage: {
    justifyContent: 'center',
    gap: 18,
  },
  compactHeader: {
    borderRadius: 22,
    backgroundColor: '#0d172b',
    borderWidth: 1,
    borderColor: '#1f304f',
    paddingHorizontal: 18,
    paddingVertical: 14,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 14,
  },
  compactHeaderCopy: {
    flex: 1,
    gap: 4,
  },
  compactTitle: {
    color: '#f7fbff',
    fontSize: 18,
    fontWeight: '800',
  },
  compactSubtitle: {
    color: '#8ea8d2',
    fontSize: 12,
  },
  agentStatusBar: {
    borderRadius: 18,
    backgroundColor: '#081225',
    borderWidth: 1,
    borderColor: '#1d2b49',
    paddingHorizontal: 14,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flexWrap: 'wrap',
  },
  agentStatusItem: {
    minWidth: 138,
    borderRadius: 14,
    backgroundColor: '#101d35',
    paddingHorizontal: 12,
    paddingVertical: 9,
    gap: 3,
  },
  agentStatusMeter: {
    flex: 1,
    minWidth: 220,
    borderRadius: 14,
    backgroundColor: '#101d35',
    paddingHorizontal: 12,
    paddingVertical: 9,
    gap: 7,
  },
  agentStatusMeterHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 12,
  },
  agentStatusLabel: {
    color: '#7f96bc',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.9,
    textTransform: 'uppercase',
  },
  agentStatusValue: {
    color: '#f7fbff',
    fontSize: 13,
    fontWeight: '900',
  },
  contextStateBadge: {
    borderRadius: 0,
    paddingHorizontal: 10,
    paddingVertical: 4,
    alignSelf: 'flex-start',
  },
  contextStateBadgeNeutral: {
    backgroundColor: '#1c2b47',
  },
  contextStateBadgeWarn: {
    backgroundColor: '#5c3e00',
  },
  contextStateBadgeCompact: {
    backgroundColor: '#103824',
  },
  contextStateBadgeText: {
    color: '#f7fbff',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  contextMeterTrack: {
    height: 7,
    borderRadius: 999,
    backgroundColor: '#1c2b47',
    overflow: 'hidden',
  },
  contextMeterFill: {
    height: 7,
    borderRadius: 999,
    backgroundColor: '#62d2ff',
  },
  contextMeterFillWarn: {
    backgroundColor: '#ffbf3c',
  },
  contextMeterFillCompact: {
    backgroundColor: '#7be495',
  },
  contextMeterFootnote: {
    color: '#9bb0d4',
    fontSize: 10,
    fontWeight: '800',
    alignSelf: 'flex-end',
  },
  taskBoardCard: {
    borderRadius: 0,
    backgroundColor: '#0b1730',
    borderWidth: 1,
    borderColor: '#21406d',
    paddingHorizontal: 16,
    paddingVertical: 14,
    gap: 12,
  },
  taskBoardCardWarn: {
    borderColor: '#76511b',
    backgroundColor: '#1f1405',
  },
  taskBoardCardComplete: {
    borderColor: '#1f5f42',
    backgroundColor: '#0d2017',
  },
  taskBoardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
  },
  taskBoardHeaderCopy: {
    flex: 1,
    gap: 4,
  },
  taskBoardHeaderActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexWrap: 'wrap',
    justifyContent: 'flex-end',
  },
  taskBoardEyebrow: {
    color: '#8cb9ff',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  taskBoardGoal: {
    color: '#f7fbff',
    fontSize: 15,
    fontWeight: '900',
  },
  taskBoardMeta: {
    color: '#9eb7dd',
    fontSize: 12,
    lineHeight: 18,
  },
  taskBoardBadge: {
    borderRadius: 0,
    backgroundColor: '#17345e',
    paddingHorizontal: 11,
    paddingVertical: 6,
  },
  taskBoardBadgeWarn: {
    backgroundColor: '#825c1b',
  },
  taskBoardBadgeComplete: {
    backgroundColor: '#1c6a47',
  },
  taskBoardBadgeText: {
    color: '#f7fbff',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  taskBoardToggleButton: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#13233f',
    borderWidth: 1,
    borderColor: '#28446e',
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  taskBoardToggleButtonText: {
    color: '#dce8fb',
    fontSize: 11,
    fontWeight: '900',
  },
  taskBoardAlert: {
    borderRadius: 0,
    backgroundColor: 'rgba(255, 191, 60, 0.14)',
    borderWidth: 1,
    borderColor: 'rgba(255, 191, 60, 0.35)',
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 3,
  },
  taskBoardAlertLabel: {
    color: '#ffd37b',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  taskBoardAlertText: {
    color: '#fce7b4',
    fontSize: 12,
    lineHeight: 18,
  },
  taskBoardInfoRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  taskBoardInfoChip: {
    flex: 1,
    minWidth: 220,
    borderRadius: 0,
    backgroundColor: '#101f3b',
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 4,
  },
  taskBoardInfoLabel: {
    color: '#7d97c1',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.7,
    textTransform: 'uppercase',
  },
  taskBoardInfoValue: {
    color: '#f7fbff',
    fontSize: 12,
    lineHeight: 18,
    fontWeight: '700',
  },
  taskBoardSteps: {
    gap: 9,
  },
  taskBoardStepRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  taskBoardStepPrefix: {
    color: '#9fc7ff',
    fontSize: 12,
    fontWeight: '900',
    paddingTop: 1,
  },
  taskBoardStepCopy: {
    flex: 1,
    gap: 2,
  },
  taskBoardStepTitle: {
    color: '#f7fbff',
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 18,
  },
  taskBoardStepMeta: {
    color: '#9bb1d4',
    fontSize: 11,
    lineHeight: 17,
  },
  completedTaskBoardsSection: {
    gap: 12,
  },
  completedTaskBoardsHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  completedTaskBoardsHeaderCopy: {
    gap: 2,
  },
  completedTaskBoardsEyebrow: {
    color: '#7ca6ea',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  completedTaskBoardsTitle: {
    color: '#e6eefc',
    fontSize: 14,
    fontWeight: '800',
  },
  completedTaskBoardsSummary: {
    color: '#8fa8cf',
    fontSize: 12,
    fontWeight: '700',
  },
  completedTaskBoardsList: {
    gap: 10,
  },
  completedTaskCard: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#0d162b',
    borderWidth: 1,
    borderColor: '#1f3559',
    overflow: 'hidden',
  },
  completedTaskCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    paddingHorizontal: 14,
    paddingVertical: 13,
  },
  completedTaskCardCopy: {
    flex: 1,
    gap: 4,
  },
  completedTaskCardTitle: {
    color: '#f2f7ff',
    fontSize: 13,
    fontWeight: '800',
    lineHeight: 18,
  },
  completedTaskCardMeta: {
    color: '#92add8',
    fontSize: 11,
    lineHeight: 17,
  },
  completedTaskCardToggle: {
    color: '#a9c8ff',
    fontSize: 11,
    fontWeight: '900',
  },
  completedTaskCardBody: {
    borderTopWidth: 1,
    borderTopColor: '#173051',
    paddingHorizontal: 14,
    paddingVertical: 12,
    gap: 12,
  },
  completedTaskCardSteps: {
    gap: 9,
  },
  completedTaskCardSummaryBox: {
    borderRadius: 0,
    backgroundColor: '#101c35',
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 4,
  },
  completedTaskCardSummaryLabel: {
    color: '#8eaee1',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.7,
    textTransform: 'uppercase',
  },
  completedTaskCardSummaryText: {
    color: '#e5eefc',
    fontSize: 12,
    lineHeight: 18,
  },
  panelToggleButton: {
    borderRadius: 999,
    backgroundColor: '#193054',
    borderWidth: 1,
    borderColor: '#2b4b7c',
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  panelToggleButtonActive: {
    backgroundColor: '#d4ff65',
    borderColor: '#d4ff65',
  },
  panelToggleButtonText: {
    color: '#d8e7ff',
    fontWeight: '800',
    fontSize: 12,
  },
  panelToggleButtonTextActive: {
    color: '#0b1325',
  },
  sidebarMenu: {
    gap: 8,
  },
  sidebarMenuHeader: {
    paddingHorizontal: 4,
    paddingBottom: 8,
    gap: 5,
  },
  sidebarMenuTitle: {
    color: '#f7fbff',
    fontSize: 20,
    fontWeight: '900',
    lineHeight: 25,
  },
  sidebarMenuText: {
    color: '#8fa5c7',
    fontSize: 12,
    lineHeight: 17,
  },
  sidebarMenuRow: {
    minHeight: 54,
    borderRadius: 0,
    borderBottomWidth: 1,
    borderBottomColor: '#1d2946',
    paddingHorizontal: 4,
    paddingVertical: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  sidebarMenuRowActive: {
    borderBottomColor: '#d4ff65',
  },
  sidebarMenuRowDisabled: {
    opacity: 0.45,
  },
  sidebarMenuRowLabel: {
    color: '#f4f8ff',
    fontSize: 15,
    fontWeight: '800',
  },
  sidebarMenuRowValue: {
    color: '#87a3d4',
    fontSize: 12,
    fontWeight: '800',
    textAlign: 'right',
    textTransform: 'uppercase',
  },
  sidebarMenuCloseRow: {
    marginTop: 4,
    paddingHorizontal: 4,
    paddingVertical: 12,
  },
  sidebarMenuCloseText: {
    color: '#73e0ff',
    fontWeight: '900',
  },
  headerToggleRow: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
    justifyContent: 'flex-start',
  },
  headerToggleChip: {
    borderRadius: 999,
    backgroundColor: '#dbe5ff',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  headerToggleChipActive: {
    backgroundColor: '#0c1d38',
  },
  headerToggleChipText: {
    color: '#16345d',
    fontWeight: '800',
    fontSize: 12,
  },
  headerToggleChipTextActive: {
    color: '#f4f8ff',
  },
  statusCluster: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
    justifyContent: 'flex-start',
  },
  statusPill: {
    minWidth: 110,
    borderRadius: 18,
    backgroundColor: '#dbe5ff',
    paddingHorizontal: 14,
    paddingVertical: 12,
    gap: 3,
  },
  statusPillLabel: {
    color: '#5c6990',
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  statusPillValue: {
    color: '#10203f',
    fontWeight: '700',
  },
  voicePanel: {
    borderRadius: 24,
    backgroundColor: '#0f172b',
    borderWidth: 1,
    borderColor: '#223652',
    paddingHorizontal: 14,
    paddingVertical: 14,
    gap: 14,
  },
  sidebarInsetDivider: {
    height: 1,
    marginHorizontal: 12,
    backgroundColor: '#263448',
  },
  voicePanelHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 16,
  },
  voicePanelHeaderCopy: {
    flex: 1,
    gap: 5,
  },
  voicePanelHeaderActions: {
    gap: 8,
    alignSelf: 'flex-start',
  },
  voicePanelHeaderAction: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#183b49',
    paddingHorizontal: 12,
    paddingVertical: 9,
    alignSelf: 'flex-start',
  },
  voicePanelHeaderActionText: {
    color: '#f4fbff',
    fontWeight: '700',
  },
  voiceRibbon: {
    borderRadius: 18,
    backgroundColor: '#0f2a34',
    padding: 14,
    flexDirection: 'column',
    justifyContent: 'flex-start',
    gap: 12,
  },
  voiceRibbonPrimary: {
    flex: 1,
    gap: 5,
  },
  voiceRibbonActions: {
    flexDirection: 'column',
    alignItems: 'stretch',
    gap: 8,
  },
  voiceModeRow: {
    flexDirection: 'row',
    flexWrap: 'nowrap',
    gap: 10,
  },
  voiceLanguageRow: {
    flexDirection: 'row',
    gap: 10,
  },
  voiceLanguageChip: {
    flex: 1,
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#10252e',
    paddingHorizontal: 14,
    paddingVertical: 9,
    alignItems: 'center',
    justifyContent: 'center',
  },
  voiceLanguageChipActive: {
    backgroundColor: '#d4ff65',
  },
  voiceLanguageChipText: {
    color: '#c3ebf7',
    fontSize: 12,
    fontWeight: '800',
  },
  voiceLanguageChipTextActive: {
    color: '#10211d',
  },
  voiceModeChip: {
    flex: 1,
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    borderWidth: 1,
    borderColor: '#25566c',
    backgroundColor: '#0d2530',
    paddingHorizontal: 14,
    paddingVertical: 9,
    alignItems: 'center',
    justifyContent: 'center',
  },
  voiceModeChipActive: {
    backgroundColor: '#d4ff65',
    borderColor: '#d4ff65',
  },
  voiceModeChipDisabled: {
    opacity: 0.55,
  },
  voiceModeChipText: {
    color: '#c3ebf7',
    fontSize: 13,
    fontWeight: '800',
  },
  voiceModeChipTextActive: {
    color: '#10211d',
  },
  voiceLabel: {
    color: '#8fdaf6',
    fontSize: 12,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  voiceValue: {
    color: '#f3fdff',
    fontSize: 18,
    fontWeight: '800',
  },
  voiceHint: {
    color: '#b7dbe8',
    fontSize: 13,
    lineHeight: 18,
  },
  voiceCollapsedCard: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#102536',
    borderWidth: 1,
    borderColor: '#23465c',
    paddingHorizontal: 16,
    paddingVertical: 14,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 14,
  },
  voiceCollapsedCopy: {
    flex: 1,
    gap: 4,
  },
  voiceCollapsedTitle: {
    color: '#8fdaf6',
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  voiceCollapsedText: {
    color: '#f4fbff',
    fontWeight: '800',
  },
  voiceCollapsedAction: {
    color: '#c3ebf7',
    fontWeight: '700',
  },
  ribbonButton: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#1f5266',
    paddingHorizontal: 14,
    paddingVertical: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ribbonButtonActive: {
    backgroundColor: '#2f7d5d',
  },
  ribbonButtonMuted: {
    backgroundColor: '#29414b',
  },
  ribbonButtonDisabled: {
    opacity: 0.45,
  },
  ribbonButtonText: {
    color: '#f4fbff',
    fontWeight: '700',
    textAlign: 'center',
  },
  transcriptDraft: {
    borderRadius: 18,
    backgroundColor: '#1a233b',
    borderWidth: 0,
    borderColor: 'transparent',
    padding: 16,
    gap: 6,
  },
  transcriptLabel: {
    color: '#92abd8',
    fontSize: 12,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  transcriptText: {
    color: '#f2f6ff',
    fontSize: 15,
    lineHeight: 22,
  },
  voiceBanner: {
    borderRadius: 24,
    backgroundColor: '#0f2a34',
    borderWidth: 1,
    borderColor: '#24526a',
    paddingHorizontal: 16,
    paddingVertical: 14,
    gap: 6,
    marginBottom: 2,
  },
  voiceBannerError: {
    backgroundColor: '#35161d',
    borderColor: '#683441',
  },
  voiceBannerTitle: {
    color: '#8fdaf6',
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  voiceBannerText: {
    color: '#f4fbff',
    lineHeight: 20,
  },
  voiceErrorCard: {
    borderRadius: 18,
    backgroundColor: '#35161d',
    borderWidth: 0,
    borderColor: 'transparent',
    padding: 16,
    gap: 5,
  },
  voiceErrorTitle: {
    color: '#ffbdc6',
    fontWeight: '800',
  },
  voiceErrorText: {
    color: '#ffe8ec',
    lineHeight: 20,
  },
  centeredConversationBlock: {
    width: '100%',
    maxWidth: 980,
    alignSelf: 'center',
  },
  transcriptScroll: {
    flex: 1,
    borderRadius: 28,
    backgroundColor: '#0d1527',
    borderWidth: 0,
    borderColor: 'transparent',
  },
  transcriptScrollDraftStage: {
    flexGrow: 0,
    flexShrink: 0,
    flexBasis: 'auto',
    backgroundColor: 'transparent',
    borderRadius: 0,
  },
  transcriptContent: {
    padding: 18,
    gap: 12,
  },
  transcriptContentDraftStage: {
    paddingHorizontal: 0,
    paddingVertical: 0,
    gap: 0,
  },
  messageBubble: {
    borderRadius: 0,
    padding: 15,
    gap: 8,
  },
  messageBubbleUser: {
    alignSelf: 'flex-end',
    maxWidth: '78%',
    backgroundColor: '#d4ff65',
    borderRadius: 22,
  },
  messageBubbleAssistant: {
    alignSelf: 'stretch',
    backgroundColor: 'transparent',
    borderWidth: 0,
    paddingHorizontal: 0,
    paddingVertical: 0,
  },
  messageBubbleSystem: {
    alignSelf: 'stretch',
    backgroundColor: '#2a1d3e',
    borderWidth: 1,
    borderColor: '#4d356d',
  },
  messageBubblePending: {
    opacity: 0.76,
  },
  messageBubbleDraft: {
    borderStyle: 'dashed',
  },
  messageHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 16,
  },
  messageLabel: {
    color: '#7d94bf',
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  messageTime: {
    color: '#7d94bf',
    fontSize: 11,
  },
  messageText: {
    color: '#f4f8ff',
    fontSize: 15,
    lineHeight: 22,
  },
  composerDock: {
    width: '100%',
    alignItems: 'center',
    paddingHorizontal: 28,
    paddingTop: 2,
    paddingBottom: 6,
  },
  composerDockDraftStage: {
    paddingTop: 0,
    paddingBottom: 0,
  },
  composerShell: {
    position: 'relative',
    overflow: 'visible',
    width: '100%',
    maxWidth: 980,
    alignSelf: 'center',
    borderRadius: 30,
    backgroundColor: '#10182c',
    borderWidth: 0,
    borderColor: 'transparent',
    paddingHorizontal: 18,
    paddingTop: 14,
    paddingBottom: 12,
    gap: 10,
    shadowColor: '#02060f',
    shadowOpacity: 0.24,
    shadowRadius: 22,
    shadowOffset: { width: 0, height: 14 },
    elevation: 14,
  },
  composerShellDraftStage: {
    paddingBottom: 0,
    gap: 8,
  },
  composerUtilityAnchor: {
    position: 'relative',
    zIndex: 20,
  },
  composerTextRegion: {
    position: 'relative',
    minHeight: 0,
    justifyContent: 'flex-start',
    gap: 10,
    width: '100%',
  },
  composerInputMeasureShell: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: 0,
    opacity: 0,
    pointerEvents: 'none',
    zIndex: -1,
  },
  composerInputMeasureText: {
    width: '100%',
    minHeight: COMPOSER_MIN_HEIGHT,
    color: 'transparent',
    fontSize: 15,
    lineHeight: COMPOSER_LINE_HEIGHT,
    paddingHorizontal: 0,
    paddingVertical: 0,
    ...(Platform.OS === 'web'
      ? ({
          whiteSpace: 'pre-wrap',
          overflowWrap: 'anywhere',
        } as any)
      : null),
  },
  composerHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 12,
  },
  composerUtilityRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'stretch',
    gap: 12,
    flexWrap: 'wrap',
  },
  composerTitle: {
    color: '#ffffff',
    fontSize: 17,
    fontWeight: '800',
  },
  composerStatus: {
    color: '#98b0d9',
    fontSize: 13,
    flexShrink: 1,
    textAlign: 'right',
  },
  syntheticThinkingRow: {
    alignSelf: 'stretch',
    paddingVertical: 6,
  },
  syntheticThinkingTextWrap: {
    alignSelf: 'flex-start',
    overflow: 'hidden',
    position: 'relative',
    minWidth: 78,
    minHeight: 20,
    justifyContent: 'center',
  },
  syntheticThinkingHighlightMask: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: 68,
    overflow: 'hidden',
    justifyContent: 'center',
  },
  syntheticThinkingText: {
    color: '#98b0d9',
    fontSize: 13,
    lineHeight: 16,
    fontWeight: '900',
    letterSpacing: 0.2,
  },
  syntheticThinkingTextHighlight: {
    color: '#d4ff65',
    opacity: 0.92,
    textShadowColor: 'rgba(212, 255, 101, 0.34)',
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 12,
  },
  pendingSwitchCard: {
    borderRadius: 0,
    backgroundColor: '#17243d',
    borderWidth: 1,
    borderColor: '#45648d',
    padding: 14,
    gap: 12,
  },
  pendingSwitchCopy: {
    gap: 4,
  },
  pendingSwitchEyebrow: {
    color: '#8fdaf6',
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 0.9,
    textTransform: 'uppercase',
  },
  pendingSwitchTitle: {
    color: '#f7fbff',
    fontSize: 16,
    fontWeight: '900',
  },
  pendingSwitchText: {
    color: '#c2d3ee',
    fontSize: 13,
    lineHeight: 18,
  },
  pendingSwitchActions: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  pendingSwitchPrimaryAction: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#d4ff65',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  pendingSwitchPrimaryActionText: {
    color: '#0b1325',
    fontWeight: '900',
  },
  pendingSwitchSecondaryAction: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#1a2a47',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  pendingSwitchSecondaryActionText: {
    color: '#e6f0ff',
    fontWeight: '900',
  },
  queuedComposerStack: {
    gap: 8,
  },
  queuedComposerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: '#0c1427',
    borderWidth: 0,
    borderColor: 'transparent',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  queuedComposerText: {
    flex: 1,
    color: '#dce7ff',
    fontSize: 13,
  },
  queuedComposerAction: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#17253f',
  },
  queuedComposerActionText: {
    color: '#9fe8ff',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  commandPanel: {
    borderRadius: 14,
    backgroundColor: '#091225',
    borderWidth: 1,
    borderColor: '#2a3f68',
    padding: 12,
    gap: 12,
  },
  commandPanelSlim: {
    width: '100%',
    maxWidth: 560,
    alignSelf: 'flex-start',
  },
  commandPanelFloatingLayer: {
    position: 'absolute',
    bottom: '100%',
    marginBottom: 12,
    zIndex: 30,
  },
  commandPanelFloatingLeft: {
    left: 0,
  },
  commandPanelFloatingRight: {
    right: 0,
  },
  commandPanelFloatingBelowRight: {
    top: '100%',
    right: 0,
    bottom: 'auto',
    marginTop: 12,
    marginBottom: 0,
  },
  commandPanelFloating: {
    shadowColor: '#02060f',
    shadowOpacity: 0.42,
    shadowRadius: 22,
    shadowOffset: { width: 0, height: 16 },
    elevation: 18,
  },
  toolPackCommandPanel: {
    maxWidth: 460,
    gap: 10,
  },
  draftChoiceCommandPanel: {
    width: 348,
    maxWidth: 348,
    gap: 8,
  },
  draftChoiceSearchShell: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: 12,
    backgroundColor: '#2f2f2f',
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  draftChoiceSearchGlyph: {
    color: '#9b9b9b',
    fontSize: 13,
  },
  draftChoiceSearchInput: {
    flex: 1,
    color: '#f5f5f5',
    fontSize: 14,
    paddingVertical: 0,
  },
  draftChoiceSectionLabel: {
    color: '#8f8f8f',
    fontSize: 11,
    fontWeight: '700',
    paddingHorizontal: 4,
  },
  draftChoiceScroll: {
    maxHeight: 152,
  },
  draftChoiceList: {
    gap: 2,
  },
  draftChoiceRow: {
    minHeight: 32,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: 12,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: 'transparent',
  },
  draftChoiceRowHovered: {
    backgroundColor: '#3a3a3a',
  },
  draftChoiceRowSelected: {
    backgroundColor: '#474747',
  },
  draftChoiceRowIcon: {
    color: '#b4bccb',
    fontSize: 14,
  },
  draftChoiceRowIconSelected: {
    color: '#eef4ff',
  },
  draftChoiceRowTitle: {
    flex: 1,
    color: '#e8ebf2',
    fontSize: 13,
    fontWeight: '700',
  },
  draftChoiceRowTitleSelected: {
    color: '#ffffff',
  },
  draftChoiceRowCheck: {
    color: '#eef4ff',
    fontSize: 13,
  },
  draftChoiceFooter: {
    borderTopWidth: 1,
    borderTopColor: '#252525',
    paddingTop: 8,
  },
  draftChoiceFooterAction: {
    minHeight: 32,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: 12,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  draftChoiceFooterActionHovered: {
    backgroundColor: '#323232',
  },
  draftChoiceFooterActionIcon: {
    color: '#d9e5fb',
    fontSize: 14,
  },
  draftChoiceFooterActionText: {
    color: '#f4f8ff',
    fontSize: 13,
    fontWeight: '700',
  },
  commandPanelHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 10,
  },
  commandPanelHeaderCopy: {
    flex: 1,
    gap: 4,
  },
  commandPanelEyebrow: {
    color: '#d4ff65',
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  commandPanelTitle: {
    color: '#f7fbff',
    fontSize: 17,
    fontWeight: '900',
  },
  commandPanelText: {
    color: '#a9bcda',
    fontSize: 13,
    lineHeight: 18,
  },
  commandPanelWarningText: {
    color: '#d4ff65',
    fontSize: 12,
    lineHeight: 17,
  },
  commandPanelCloseButton: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#17253f',
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  commandPanelCloseText: {
    color: '#dbe7fb',
    fontWeight: '900',
    fontSize: 12,
  },
  modelPickerScroll: {
    maxHeight: 220,
  },
  modelPickerContent: {
    gap: 10,
  },
  modelProviderBlock: {
    gap: 6,
  },
  modelProviderTitle: {
    color: '#7aa4ff',
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  modelProviderCaption: {
    color: '#94a9cc',
    fontSize: 12,
    lineHeight: 17,
  },
  toolPackCompactList: {
    gap: 6,
  },
  toolPackCompactGroup: {
    gap: 6,
  },
  toolPackCompactRow: {
    minHeight: 38,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    backgroundColor: '#0f182d',
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  toolPackCompactRowEnabled: {
    backgroundColor: '#10182c',
  },
  toolPackCompactRowUnavailable: {
    opacity: 0.64,
  },
  toolPackCompactLabel: {
    flex: 1,
    color: '#d9e5fb',
    fontSize: 13,
    fontWeight: '800',
  },
  toolPackCompactLabelEnabled: {
    color: '#d4ff65',
  },
  toolPackCompactLabelUnavailable: {
    color: '#93a5c6',
  },
  toolPackCompactActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  toolPackInfoButton: {
    width: 24,
    height: 24,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'transparent',
  },
  toolPackInfoButtonHovered: {
    backgroundColor: '#13223e',
  },
  toolPackInfoButtonActive: {
    backgroundColor: '#162844',
  },
  toolPackInfoIcon: {
    color: '#7f97bd',
    fontSize: 13,
  },
  toolPackInfoIconActive: {
    color: '#d4ff65',
  },
  toolPackInfoBubble: {
    backgroundColor: '#111c33',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 4,
  },
  toolPackInfoFloatingBubble: {
    position: 'absolute',
    width: 292,
    backgroundColor: '#111c33',
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
    gap: 4,
    shadowColor: '#02060f',
    shadowOpacity: 0.36,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 10 },
    elevation: 18,
    zIndex: 40,
  },
  toolPackInfoTitle: {
    color: '#f4f8ff',
    fontSize: 12,
    fontWeight: '900',
  },
  toolPackInfoText: {
    color: '#9cb1d4',
    fontSize: 12,
    lineHeight: 17,
  },
  toolPackInfoWarning: {
    color: '#d4ff65',
    fontSize: 11,
    lineHeight: 16,
  },
  toolPackSwitch: {
    width: 42,
    height: 24,
    borderRadius: 999,
    backgroundColor: '#202b43',
    padding: 3,
    justifyContent: 'center',
  },
  toolPackSwitchActive: {
    backgroundColor: '#d4ff65',
  },
  toolPackSwitchSaving: {
    opacity: 0.72,
  },
  toolPackSwitchDisabled: {
    backgroundColor: '#1a2235',
  },
  toolPackSwitchKnob: {
    width: 18,
    height: 18,
    borderRadius: 999,
    backgroundColor: '#f4f8ff',
  },
  toolPackSwitchKnobActive: {
    alignSelf: 'flex-end',
    backgroundColor: '#0b1325',
  },
  modelList: {
    gap: 6,
  },
  modelListItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: 'transparent',
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  modelListItemHovered: {
    backgroundColor: '#13223e',
    borderColor: '#27466f',
  },
  modelListItemActive: {
    backgroundColor: '#d4ff65',
    borderColor: '#d4ff65',
  },
  toolPackListItemActive: {
    backgroundColor: '#101b32',
    borderColor: '#2f567e',
  },
  modelListItemDisabled: {
    opacity: 0.52,
  },
  modelListItemCopy: {
    flex: 1,
  },
  modelListItemTitle: {
    color: '#f4f8ff',
    fontWeight: '900',
    fontSize: 13,
  },
  modelListItemTitleActive: {
    color: '#0b1325',
  },
  toolPackListItemTitleActive: {
    color: '#d4ff65',
  },
  modelListItemMeta: {
    color: '#7aa4ff',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  modelListItemMetaActive: {
    color: '#193214',
  },
  toolPackListItemMetaActive: {
    color: '#d4ff65',
  },
  modelListItemMetaDisabled: {
    color: '#8b99b5',
  },
  toolPackListItemCaptionActive: {
    color: '#b7d88f',
  },
  timelineTranscriptCard: {
    alignSelf: 'stretch',
    borderRadius: 18,
    backgroundColor: '#101a30',
    borderWidth: 1,
    borderColor: '#203657',
    paddingHorizontal: 14,
    paddingVertical: 12,
    gap: 8,
  },
  timelineTranscriptCardAccent: {
    borderColor: '#2f567e',
    backgroundColor: '#10203b',
  },
  timelineTranscriptCardWarn: {
    borderColor: '#78561d',
    backgroundColor: '#231808',
  },
  timelineTranscriptCardError: {
    borderColor: '#78445a',
    backgroundColor: '#27131a',
  },
  timelineTranscriptHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  timelineTranscriptEyebrow: {
    color: '#9fc7ff',
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  timelineTranscriptTime: {
    color: '#7d94bf',
    fontSize: 11,
  },
  timelineTranscriptBody: {
    color: '#eef4ff',
    fontSize: 14,
    lineHeight: 21,
  },
  timelineTranscriptResultBlock: {
    gap: 4,
    borderTopWidth: 1,
    borderTopColor: '#203657',
    paddingTop: 8,
  },
  timelineTranscriptResultEyebrow: {
    color: '#8fe0ff',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  timelineTranscriptResultText: {
    color: '#d4e3ff',
    fontSize: 13,
    lineHeight: 19,
  },
  commandPanelEmpty: {
    borderRadius: 12,
    backgroundColor: '#101b32',
    padding: 12,
    gap: 4,
  },
  commandPanelEmptyTitle: {
    color: '#f7fbff',
    fontWeight: '900',
  },
  commandPanelEmptyText: {
    color: '#a9bcda',
    lineHeight: 18,
  },
  commandPanelActionRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  commandPanelPrimaryAction: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#d4ff65',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  commandPanelPrimaryActionActive: {
    backgroundColor: '#97f46f',
  },
  commandPanelPrimaryActionText: {
    color: '#0b1325',
    fontWeight: '900',
  },
  commandPanelSecondaryAction: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    borderWidth: 1,
    borderColor: '#355178',
    backgroundColor: 'rgba(16, 27, 50, 0.86)',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  commandPanelSecondaryActionText: {
    color: '#d9e7ff',
    fontWeight: '800',
  },
  interruptOptionList: {
    gap: 8,
  },
  interruptOptionCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#101b32',
    borderWidth: 1,
    borderColor: '#213655',
    paddingHorizontal: 12,
    paddingVertical: 11,
  },
  interruptOptionCardActive: {
    backgroundColor: '#172947',
    borderColor: '#62d2ff',
  },
  interruptOptionCopy: {
    flex: 1,
    gap: 3,
  },
  interruptOptionTitle: {
    color: '#f4f8ff',
    fontWeight: '900',
    fontSize: 13,
  },
  interruptOptionTitleActive: {
    color: '#f7fbff',
  },
  interruptOptionText: {
    color: '#a9bcda',
    fontSize: 12,
    lineHeight: 17,
  },
  interruptOptionMeta: {
    color: '#7aa4ff',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  interruptOptionMetaActive: {
    color: '#62d2ff',
  },
  sessionCommandScroll: {
    maxHeight: 320,
  },
  sessionCommandList: {
    gap: 8,
  },
  sessionCommandCard: {
    borderRadius: 0,
    backgroundColor: '#101b32',
    borderWidth: 1,
    borderColor: '#213659',
    padding: 12,
    gap: 5,
  },
  sessionCommandCardActive: {
    borderColor: '#d4ff65',
    backgroundColor: '#18273b',
  },
  sessionCommandHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
  },
  sessionCommandCopy: {
    flex: 1,
    gap: 3,
  },
  sessionCommandTitle: {
    color: '#f7fbff',
    fontSize: 15,
    fontWeight: '900',
  },
  sessionCommandMeta: {
    color: '#9fb4d7',
    fontSize: 11,
  },
  sessionCommandBadge: {
    borderRadius: 0,
    backgroundColor: '#d4ff65',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  sessionCommandBadgeText: {
    color: '#0b1325',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  sessionCommandPreview: {
    color: '#d7e4f8',
    fontSize: 13,
    lineHeight: 18,
  },
  interruptRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  composerStatusBar: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'stretch',
    gap: 8,
    flexWrap: 'wrap',
    flex: 1,
    minWidth: 250,
  },
  composerStatusPill: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: 'transparent',
    paddingHorizontal: 6,
    paddingVertical: 4,
    justifyContent: 'center',
  },
  composerStatusPillWide: {
    minWidth: 152,
    flexShrink: 1,
  },
  composerStatusPillInteractiveActive: {
    borderColor: 'transparent',
    backgroundColor: 'transparent',
  },
  composerStatusPillLabel: {
    color: '#7f96bc',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  composerStatusPillValue: {
    color: '#f7fbff',
    fontSize: 12,
    fontWeight: '800',
  },
  composerStatusPillMeta: {
    color: '#8da2c4',
    fontSize: 11,
  },
  composerStatusContextRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    flexWrap: 'wrap',
  },
  contextMeterButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    paddingHorizontal: 0,
    paddingVertical: 0,
    overflow: 'hidden',
  },
  contextMeterButtonCollapsed: {
    width: 18,
    minWidth: 18,
    height: 18,
  },
  contextMeterButtonExpanded: {
    minWidth: 176,
    paddingHorizontal: 6,
  },
  contextMeterHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  contextMeterState: {
    color: '#d9e7fb',
    fontSize: 11,
    fontWeight: '700',
  },
  contextMeterOrb: {
    position: 'relative',
    width: 18,
    height: 18,
    borderRadius: 999,
    backgroundColor: '#10213b',
    borderWidth: 1,
    borderColor: '#27466d',
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
  },
  contextMeterOrbFill: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: '#6fd6ff',
  },
  contextMeterOrbFillWarn: {
    backgroundColor: '#d4ff65',
  },
  contextMeterOrbFillCompact: {
    backgroundColor: '#82ffb3',
  },
  contextMeterOrbCore: {
    width: 6,
    height: 6,
    borderRadius: 999,
    backgroundColor: '#eaf4ff',
    opacity: 0.88,
  },
  contextMeterDetail: {
    minWidth: 138,
    gap: 1,
  },
  contextMeterDetailTitle: {
    color: '#dce7ff',
    fontSize: 11,
    fontWeight: '800',
  },
  contextMeterDetailText: {
    color: '#b2c5e4',
    fontSize: 11,
  },
  contextMeterDetailMeta: {
    color: '#7f96bc',
    fontSize: 10,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  composerFooterRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  composerFooterControls: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flex: 1,
    minWidth: 0,
  },
  composerFooterActions: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 10,
    flexShrink: 0,
  },
  draftComposerMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexWrap: 'wrap',
    marginTop: 0,
    overflow: 'visible',
  },
  draftComposerMetaTray: {
    marginTop: 4,
    marginHorizontal: -18,
    marginBottom: -12,
    paddingTop: 6,
    paddingBottom: 10,
    paddingHorizontal: 18,
    borderTopWidth: 1,
    borderTopColor: '#11192b',
    borderBottomLeftRadius: 30,
    borderBottomRightRadius: 30,
    backgroundColor: '#0a1020',
    overflow: 'visible',
  },
  draftComposerMetaControl: {
    position: 'relative',
    overflow: 'visible',
  },
  draftComposerMetaChip: {
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    minHeight: 30,
    paddingHorizontal: 12,
    paddingVertical: 5,
    backgroundColor: '#111823',
    borderRadius: 12,
  },
  draftComposerMetaChipHovered: {
    backgroundColor: '#1a2230',
  },
  draftComposerMetaChipActive: {
    backgroundColor: '#1c2535',
  },
  draftComposerMetaChipDisabled: {
    opacity: 0.6,
  },
  draftComposerMetaIcon: {
    color: '#b4bccb',
    fontSize: 14,
  },
  draftComposerMetaLabel: {
    maxWidth: 220,
    color: '#edf3ff',
    fontSize: 12,
    fontWeight: '800',
  },
  draftComposerMetaChevronIcon: {
    color: '#aebed8',
    fontSize: 13,
  },
  draftComposerInlineDropdown: {
    position: 'absolute',
    top: '100%',
    left: 0,
    marginTop: 8,
    zIndex: 40,
  },
  composerStatusInline: {
    color: '#8da2c4',
    fontSize: 12,
    maxWidth: 160,
    textAlign: 'right',
  },
  interruptChooserButton: {
    minWidth: 132,
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: 'transparent',
    paddingHorizontal: 12,
    paddingVertical: 9,
    gap: 4,
    alignSelf: 'flex-start',
  },
  interruptChooserButtonActive: {
    borderColor: 'transparent',
    backgroundColor: 'transparent',
  },
  statusSurfaceHovered: {
    backgroundColor: '#0a1427',
    borderColor: 'transparent',
  },
  interruptChooserEyebrow: {
    color: '#7f96bc',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  interruptChooserValue: {
    color: '#f7fbff',
    fontSize: 13,
    fontWeight: '800',
  },
  commandSuggestionMenu: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#091225',
    borderWidth: 1,
    borderColor: '#2a3f68',
    padding: 8,
    gap: 6,
  },
  commandSuggestionTitle: {
    color: '#7aa4ff',
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  commandSuggestionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  commandSuggestionCloseButton: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#17253f',
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  commandSuggestionCloseText: {
    color: '#dbe7fb',
    fontSize: 11,
    fontWeight: '800',
  },
  commandSuggestionList: {
    gap: 4,
  },
  commandSuggestionItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#101b32',
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  commandSuggestionCommand: {
    color: '#d4ff65',
    fontWeight: '900',
    minWidth: 110,
  },
  commandSuggestionDescription: {
    color: '#b9c8e6',
    flex: 1,
    fontSize: 13,
  },
  composerRow: {
    flexDirection: 'row',
    gap: 12,
    alignItems: 'flex-end',
  },
  composerInput: {
    width: '100%',
    minHeight: COMPOSER_MIN_HEIGHT,
    maxHeight: COMPOSER_MAX_HEIGHT,
    borderRadius: 0,
    backgroundColor: 'transparent',
    borderWidth: 0,
    borderColor: 'transparent',
    color: '#f6fbff',
    paddingHorizontal: 0,
    paddingVertical: 0,
    paddingTop: 0,
    paddingBottom: 0,
    textAlignVertical: 'top',
    fontSize: 15,
    lineHeight: COMPOSER_LINE_HEIGHT,
    overflow: 'hidden',
  },
  sendButton: {
    borderRadius: 999,
    backgroundColor: '#67d9ff',
    width: 42,
    minWidth: 42,
    height: 42,
    minHeight: 42,
    paddingHorizontal: 0,
    paddingVertical: 0,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#07101d',
    shadowOpacity: 0.22,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  sendButtonIdle: {
    backgroundColor: '#22334f',
  },
  sendButtonStop: {
    backgroundColor: '#8e5f67',
  },
  sendButtonInterrupt: {
    backgroundColor: '#8ee5ff',
  },
  sendButtonText: {
    color: '#082033',
    fontWeight: '800',
    fontSize: 20,
    lineHeight: 20,
  },
  sendButtonTextIdle: {
    color: '#6f89ad',
  },
  referenceMovedCard: {
    borderRadius: 0,
    backgroundColor: '#101c34',
    borderWidth: 1,
    borderColor: '#23365a',
    padding: 16,
    gap: 14,
  },
  referenceMovedCopy: {
    gap: 6,
  },
  referenceMovedTitle: {
    color: '#f7fbff',
    fontSize: 16,
    fontWeight: '800',
  },
  referenceMovedText: {
    color: '#a7bbdb',
    lineHeight: 20,
  },
  referenceMovedButton: {
    alignSelf: 'flex-start',
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#d9ff72',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  referenceMovedButtonText: {
    color: '#0a1831',
    fontWeight: '800',
  },
  sidebarContentScroll: {
    flex: 1,
  },
  controlColumnContent: {
    gap: 14,
    paddingHorizontal: 16,
    paddingVertical: 12,
    paddingBottom: 18,
  },
  sidebarSurfaceCard: {
    gap: 14,
  },
  sidebarSurfaceActionRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  controlColumnHeader: {
    borderBottomWidth: 1,
    borderBottomColor: '#1d2946',
    paddingBottom: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
  },
  controlColumnHeaderCopy: {
    flex: 1,
    gap: 4,
  },
  controlColumnTitle: {
    color: '#f7fbff',
    fontSize: 18,
    fontWeight: '900',
  },
  controlColumnText: {
    color: '#8fa5c7',
    fontSize: 12,
    lineHeight: 17,
  },
  controlColumnCloseButton: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#17253f',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  controlColumnCloseText: {
    color: '#dbe7fb',
    fontWeight: '900',
    fontSize: 12,
  },
  foldSection: {
    borderRadius: 0,
    backgroundColor: '#0f172e',
    borderWidth: 1,
    borderColor: '#1d2946',
    overflow: 'hidden',
  },
  foldSectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 12,
    paddingHorizontal: 18,
    paddingVertical: 16,
    alignItems: 'center',
  },
  foldSectionHeaderCopy: {
    flex: 1,
    gap: 4,
  },
  foldSectionTitle: {
    color: '#ffffff',
    fontSize: 17,
    fontWeight: '800',
  },
  foldSectionSummary: {
    color: '#a6b9d8',
    lineHeight: 19,
  },
  foldSectionToggle: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#17253f',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  foldSectionToggleText: {
    color: '#dbe7fb',
    fontWeight: '800',
    fontSize: 12,
  },
  foldSectionBody: {
    paddingHorizontal: 18,
    paddingBottom: 18,
    gap: 12,
  },
  referencePanel: {
    gap: 14,
  },
  referencePanelHeader: {
    borderBottomWidth: 1,
    borderBottomColor: '#1d2946',
    paddingBottom: 12,
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
  },
  referencePanelHeaderCopy: {
    flex: 1,
    gap: 4,
  },
  referencePanelTitle: {
    color: '#f7fbff',
    fontSize: 18,
    fontWeight: '900',
  },
  referencePanelSummary: {
    color: '#8fa5c7',
    fontSize: 12,
    lineHeight: 17,
  },
  referencePanelCloseButton: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#17253f',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  referencePanelCloseText: {
    color: '#dbe7fb',
    fontWeight: '900',
    fontSize: 12,
  },
  controlBody: {
    color: '#a6b9d8',
    lineHeight: 20,
  },
  referenceStack: {
    gap: 12,
  },
  referenceCard: {
    borderRadius: 0,
    backgroundColor: '#15203d',
    borderWidth: 1,
    borderColor: '#263a5f',
    padding: 14,
    gap: 10,
  },
  referenceCardHeader: {
    gap: 5,
  },
  referenceCardEyebrow: {
    color: '#7ea3d8',
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.9,
    textTransform: 'uppercase',
  },
  referenceCardTitle: {
    color: '#f5fbff',
    fontSize: 16,
    fontWeight: '800',
  },
  referenceCardSummary: {
    color: '#a9bcda',
    lineHeight: 19,
  },
  referenceCardMeta: {
    color: '#86a0c7',
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  referenceCardBody: {
    color: '#e9f2ff',
    fontSize: 13,
    lineHeight: 20,
  },
  artifactPanelStack: {
    gap: 12,
  },
  artifactListScroll: {
    maxHeight: 260,
  },
  artifactList: {
    gap: 8,
  },
  artifactRow: {
    borderRadius: 14,
    backgroundColor: '#121d35',
    borderWidth: 1,
    borderColor: '#223453',
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 4,
  },
  artifactRowActive: {
    borderColor: '#7aa4ff',
    backgroundColor: '#162440',
  },
  artifactRowTitle: {
    color: '#eef4ff',
    fontSize: 13,
    fontWeight: '800',
  },
  artifactRowMeta: {
    color: '#89a2c7',
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  artifactRowPreview: {
    color: '#c6d5ed',
    fontSize: 12,
    lineHeight: 18,
  },
  artifactPreviewCard: {
    borderRadius: 18,
    backgroundColor: '#0f182d',
    borderWidth: 1,
    borderColor: '#223453',
    padding: 14,
    gap: 12,
    minHeight: 220,
  },
  artifactPreviewHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 10,
  },
  artifactPreviewHeaderCopy: {
    flex: 1,
    gap: 4,
  },
  artifactPreviewTitle: {
    color: '#f7fbff',
    fontSize: 15,
    fontWeight: '900',
  },
  artifactPreviewMeta: {
    color: '#8fa5c7',
    fontSize: 11,
    lineHeight: 16,
  },
  artifactPreviewActions: {
    flexDirection: 'row',
    gap: 8,
  },
  artifactPreviewImage: {
    width: '100%',
    minHeight: 240,
    maxHeight: 420,
    borderRadius: 14,
    backgroundColor: '#081121',
  },
  artifactPreviewScroll: {
    maxHeight: 420,
  },
  artifactPreviewText: {
    color: '#dbe7fb',
    fontSize: 12,
    lineHeight: 19,
  },
  controlMetricRow: {
    flexDirection: 'row',
    gap: 10,
  },
  controlMetric: {
    flex: 1,
    borderRadius: 0,
    backgroundColor: '#15203d',
    padding: 12,
    gap: 4,
  },
  controlMetricLabel: {
    color: '#8ea2c8',
    fontSize: 11,
    textTransform: 'uppercase',
  },
  controlMetricValue: {
    color: '#ecf4ff',
    fontWeight: '700',
  },
  shutdownPreferenceCard: {
    borderRadius: 0,
    backgroundColor: '#15203d',
    borderWidth: 1,
    borderColor: '#243657',
    padding: 14,
    gap: 12,
  },
  shutdownPreferenceCopy: {
    gap: 5,
  },
  shutdownPreferenceTitle: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '800',
  },
  shutdownPreferenceText: {
    color: '#adc0df',
    fontSize: 13,
    lineHeight: 19,
  },
  actionRow: {
    flexDirection: 'row',
    gap: 10,
  },
  actionButton: {
    flex: 1,
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#1f3c62',
    paddingVertical: 11,
    alignItems: 'center',
  },
  actionButtonNeutral: {
    backgroundColor: '#23435e',
  },
  actionButtonWarn: {
    backgroundColor: '#603646',
  },
  actionButtonDisabled: {
    opacity: 0.6,
  },
  actionButtonText: {
    color: '#f6fbff',
    fontWeight: '800',
  },
  linkStack: {
    gap: 10,
  },
  deepLinkButton: {
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#f4f8ff',
    paddingVertical: 12,
    paddingHorizontal: 14,
  },
  deepLinkButtonText: {
    color: '#0c1a35',
    fontWeight: '800',
  },
  scopeTagRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  scopeTag: {
    borderRadius: 0,
    backgroundColor: '#1d2d4d',
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  scopeTagText: {
    color: '#a8d9ff',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  telegramSteps: {
    gap: 8,
  },
  telegramStep: {
    color: '#d6e4ff',
    lineHeight: 20,
  },
  summaryLine: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
  },
  summaryLabel: {
    color: '#93a7ca',
    fontSize: 12,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  summaryValue: {
    flex: 1,
    color: '#eef5ff',
    fontWeight: '700',
    textAlign: 'right',
  },
  activityScroll: {
    maxHeight: 260,
  },
  activityList: {
    gap: 10,
    paddingBottom: 6,
  },
  activityItem: {
    borderRadius: 0,
    backgroundColor: '#15203a',
    padding: 12,
    gap: 4,
  },
  activityItemAccent: {
    borderWidth: 1,
    borderColor: '#3dbce4',
  },
  activityItemWarn: {
    borderWidth: 1,
    borderColor: '#d59c47',
  },
  activityItemError: {
    borderWidth: 1,
    borderColor: '#d26779',
  },
  activityTime: {
    color: '#8ca2c8',
    fontSize: 11,
  },
  activityText: {
    color: '#edf5ff',
    lineHeight: 19,
  },
  emptyCard: {
    borderRadius: 0,
    backgroundColor: '#121c31',
    padding: 14,
    gap: 6,
  },
  emptyConversationCard: {
    borderRadius: 0,
    backgroundColor: '#131f37',
    padding: 16,
    gap: 6,
    alignItems: 'flex-start',
  },
  emptyConversationDraftCard: {
    minHeight: 180,
    justifyContent: 'center',
    alignItems: 'center',
    alignSelf: 'stretch',
    gap: 14,
    backgroundColor: 'transparent',
  },
  emptyDraftPrompt: {
    color: '#f7fbff',
    fontSize: 22,
    fontWeight: '700',
    textAlign: 'center',
  },
  emptyDraftFolderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: DESKTOP_RECT_BUTTON_RADIUS,
    backgroundColor: '#111b31',
    borderWidth: 1,
    borderColor: '#223659',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  emptyDraftFolderIcon: {
    color: '#8ea8d2',
    fontSize: 14,
    fontWeight: '700',
  },
  emptyDraftFolderText: {
    color: '#dce9ff',
    fontSize: 13,
    fontWeight: '700',
    letterSpacing: 0.2,
  },
  emptyDraftSupportingText: {
    textAlign: 'center',
  },
  emptyTitle: {
    color: '#f7fbff',
    fontWeight: '800',
  },
  emptyText: {
    color: '#a2b7d9',
    lineHeight: 20,
  },
});
