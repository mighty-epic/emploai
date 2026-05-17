import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
} from 'react-native';
import { useRouter } from 'expo-router';

import { buildWsBaseUrl } from '../../lib/appConfig';
import { describeError, logDiagnostic } from '../../lib/diagnostics';
import {
  activateSession,
  appendSessionTimelineEvent,
  configureAgent,
  controlAgentRun,
  createSession,
  fetchAgentConfig,
  fetchAgentOverview,
  fetchJobs,
  fetchProfile,
  fetchSessionDetail,
  fetchSessions,
  searchSessions,
  updateAgentConfig,
  type AgentOverview,
  type ScheduledJob,
  type SessionDetail,
  type SessionMessage,
  type SessionSearchResult,
  type SessionSummary,
  type SessionTimelineEvent,
  type TaskBoard,
} from '@/lib/appApi';
import {
  loadDesktopSidebarState,
  pickDesktopFolder,
  saveDesktopSidebarState,
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
const HEBREW_VOICE_GATE_DBFS = -44.0;
const HEBREW_VOICE_GATE_RELEASE_MS = 900;
const HEBREW_VOICE_GATE_PREROLL_MS = 300;
const HEBREW_VOICE_GATE_MAX_MS = 3600;
const SOCKET_RECONNECT_MS = 1600;
const SIDEBAR_REFRESH_MS = 5000;
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
type ActiveCommandPanel =
  | { kind: 'model' }
  | { kind: 'planner' }
  | { kind: 'session' }
  | { kind: 'command'; command: string; description: string }
  | null;

type DesktopMessage = {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string | null;
  displayLabel?: string | null;
  channel?: 'telegram' | 'app' | 'system' | null;
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
  defaultInterruptPolicy?: string | null;
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
};

type SidebarProjectGroup = {
  path: string;
  label: string;
  hint: string;
  pinned: boolean;
  collapsed: boolean;
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

type MonoIconName =
  | 'menu'
  | 'settings'
  | 'compose'
  | 'search'
  | 'voice'
  | 'history'
  | 'folder_closed'
  | 'folder_open'
  | 'pin'
  | 'more'
  | 'plus';

const DESKTOP_SIDEBAR_STATE_VERSION = 1;
const DESKTOP_SIDEBAR_ACTIVITY_LIMIT = 8;
const SIDEBAR_DRAFT_CHAT_ID = '__draft__';
const MONO_ICON_GLYPHS: Record<MonoIconName, string> = {
  menu: '≡',
  settings: '⛭',
  compose: '✎',
  search: '⌕',
  voice: '◌',
  history: '◷',
  folder_closed: '',
  folder_open: '',
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

function toDesktopMessage(message: SessionMessage): DesktopMessage {
  return {
    role: message.role || 'assistant',
    content: message.content || '',
    timestamp: message.timestamp,
    displayLabel: message.display_label,
    channel: message.channel,
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

function mergeTimelineEntries(messages: DesktopMessage[], timelineEvents: SessionTimelineEvent[]) {
  const messageEntries: TimelineEntry[] = messages
    .filter((message) => !message.localOnly)
    .map((message, index) => ({
    id: `message-${message.timestamp || 'pending'}-${index}`,
    kind: 'message',
    sourceMessageIndex: index,
    timestamp: message.timestamp || null,
    sortValue: messageTimestampValue(message) ?? Number.MAX_SAFE_INTEGER - 1 + index,
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
  defaultInterruptPolicy,
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
  const deferredAlwaysOnFramesRef = useRef<Float32Array[]>([]);
  const deferredAlwaysOnSampleCountRef = useRef(0);
  const drainingDeferredAlwaysOnFramesRef = useRef(false);
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
  const startupChatSocketReadyRef = useRef(false);
  const startupTerminalStateRef = useRef<StartupReadinessState | null>(null);
  const draftChatRef = useRef<SidebarDraftChat | null>(null);
  const currentWorkspaceBySessionRef = useRef<Record<string, string>>({});
  const sidebarSearchRequestIdRef = useRef(0);
  const transcriptMessageLayoutRef = useRef<Record<number, number>>({});
  const historyMessageLayoutRef = useRef<Record<number, number>>({});
  const searchJumpTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchHighlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [sessionId, setSessionId] = useState<string | undefined>(initialSessionId || undefined);
  const [sessionName, setSessionName] = useState('Shared session');
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [messages, setMessages] = useState<DesktopMessage[]>([]);
  const [timelineEvents, setTimelineEvents] = useState<SessionTimelineEvent[]>([]);
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [overview, setOverview] = useState<AgentOverview | null>(null);
  const [taskBoard, setTaskBoard] = useState<TaskBoard | null>(null);
  const [completedTaskBoards, setCompletedTaskBoards] = useState<TaskBoard[]>([]);
  const [taskBoardCollapsed, setTaskBoardCollapsed] = useState(false);
  const [expandedCompletedTaskIds, setExpandedCompletedTaskIds] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState('loading shared session');
  const [socketState, setSocketState] = useState('connecting');
  const [input, setInput] = useState('');
  const [activeCommandPanel, setActiveCommandPanel] = useState<ActiveCommandPanel>(null);
  const [assistantDraft, setAssistantDraft] = useState('');
  const [thinking, setThinking] = useState('');
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [interruptPolicy, setInterruptPolicy] = useState<InterruptPolicy>(() => normalizeInterruptPolicyValue(defaultInterruptPolicy));
  const [chatRunActive, setChatRunActive] = useState(false);
  const [queuedComposerMessages, setQueuedComposerMessages] = useState<QueuedComposerMessage[]>([]);
  const [voiceState, setVoiceState] = useState('connecting');
  const [voiceDraft, setVoiceDraft] = useState('');
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [voiceRunning, setVoiceRunning] = useState(false);
  const [voiceRecording, setVoiceRecording] = useState(false);
  const [voiceMode, setVoiceMode] = useState<VoiceCaptureMode>('push_to_talk');
  const [voiceEngineChanging, setVoiceEngineChanging] = useState(false);
  const [alwaysOnEnabled, setAlwaysOnEnabled] = useState(false);
  const [sidebarExpanded, setSidebarExpanded] = useState(false);
  const [sidebarSearch, setSidebarSearch] = useState('');
  const [sidebarSearchModalOpen, setSidebarSearchModalOpen] = useState(false);
  const [sidebarSearchLoading, setSidebarSearchLoading] = useState(false);
  const [sidebarSearchError, setSidebarSearchError] = useState<string | null>(null);
  const [sidebarSearchResults, setSidebarSearchResults] = useState<SessionSearchResult[]>([]);
  const [sidebarState, setSidebarState] = useState<DesktopSidebarState>(createEmptySidebarState());
  const [sidebarStateReady, setSidebarStateReady] = useState(false);
  const [draftChat, setDraftChat] = useState<SidebarDraftChat | null>(null);
  const [dragState, setDragState] = useState<SidebarDragState>(null);
  const [hoveredProjectPath, setHoveredProjectPath] = useState<string | null>(null);
  const [openProjectMenuPath, setOpenProjectMenuPath] = useState<string | null>(null);
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
  const [voicePanelHidden, setVoicePanelHidden] = useState(false);
  const [dismissedCommandSuggestionInput, setDismissedCommandSuggestionInput] = useState<string | null>(null);
  const [keepRuntimeOnAppClose, setKeepRuntimeOnAppClose] = useState(false);
  const [savingCloseBehavior, setSavingCloseBehavior] = useState(false);
  const [contextUsageHovered, setContextUsageHovered] = useState(false);
  const selectedVoiceEngine = voicePackState?.defaultEngine || voiceStatus?.selected_engine || VOICE_ENGINE_NONE;
  const usingHebrewVoiceEngine = selectedVoiceEngine === VOICE_ENGINE_HEBREW;
  const activeVoiceSegmentMs = usingHebrewVoiceEngine ? HEBREW_VOICE_SEGMENT_MS : VOICE_SEGMENT_MS;
  const activeVoiceGateDbfs = usingHebrewVoiceEngine ? HEBREW_VOICE_GATE_DBFS : VOICE_GATE_DBFS;
  const activeVoiceGateReleaseMs = usingHebrewVoiceEngine ? HEBREW_VOICE_GATE_RELEASE_MS : VOICE_GATE_RELEASE_MS;
  const activeVoiceGatePrerollMs = usingHebrewVoiceEngine ? HEBREW_VOICE_GATE_PREROLL_MS : VOICE_GATE_PREROLL_MS;
  const activeVoiceGateMaxMs = usingHebrewVoiceEngine ? HEBREW_VOICE_GATE_MAX_MS : VOICE_GATE_MAX_MS;

  useEffect(() => {
    setInterruptPolicy(normalizeInterruptPolicyValue(defaultInterruptPolicy));
  }, [defaultInterruptPolicy]);

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
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    draftChatRef.current = draftChat;
  }, [draftChat]);

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
    if (startupSidebarReadyRef.current && startupChatSocketReadyRef.current && sessionIdRef.current) {
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
    if (!(voiceCaptureModeRef.current === 'always_on' && voiceRecordingRef.current)) {
      voiceComposerBaseInputRef.current = input;
    }
  }, [input]);

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
      setInput('');
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
    if (detail.id !== sessionIdRef.current) {
      resetTranscriptAutoScrollState();
      setTaskBoardCollapsed(false);
      setExpandedCompletedTaskIds({});
      transcriptMessageLayoutRef.current = {};
      historyMessageLayoutRef.current = {};
    }
    setSessionId(detail.id);
    setSessionName(detail.name);
    setTaskBoard(resolveTaskBoardState(detail.task_board, detail.id, sessionIdRef.current));
    setCompletedTaskBoards(normalizeCompletedTaskBoards(detail.completed_task_boards));
    setTimelineEvents(detail.timeline_events || []);
    const syncedMessages = detail.messages.map((message) => toDesktopMessage(message));
    setMessages((previous) => mergeLocalMessages(syncedMessages, previous, detail.id));
    discardDraftChat();
    selectProjectPath(detail.workspace);
  };

  const appendTimelineEvent = (event: SessionTimelineEvent) => {
    if (!event?.id) {
      return;
    }
    setTimelineEvents((previous) => {
      const existingIndex = previous.findIndex((item) => item.id === event.id);
      if (existingIndex >= 0) {
        const next = previous.slice();
        next[existingIndex] = event;
        return next;
      }
      return [...previous, event];
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
    if (Array.isArray(syncedSessions)) {
      reconcileSidebarProjects(syncedSessions, {
        preferredSelectedProjectPath: draftChatRef.current?.projectPath || undefined,
        activeSessionWorkspace: detail?.workspace,
      });
      setSessions(syncedSessions);
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
          task_board: detail.task_board ?? null,
          completed_task_boards: normalizeCompletedTaskBoards(detail.completed_task_boards),
          context_usage: {
            ...previous.context_usage,
            model: detail.model,
          },
        };
      });
      if (modelChanged) {
        void refreshSidebarState(detail.id, true);
      }
    }
  };

  const refreshSidebarState = async (preferredSessionId?: string | null, quiet = false) => {
    if (!quiet) {
      setStatus('loading shared session');
      emitStartupState('warming', 'Loading shared session');
    }

    try {
      let [profile, sessionList, jobList] = await Promise.all([
        fetchProfile(apiBaseUrl, token),
        fetchSessions(apiBaseUrl, token),
        fetchJobs(apiBaseUrl, token),
      ]);

      let resolvedSessionId = preferredSessionId || profile.current_session_id || sessionList[0]?.id || null;
      let detail: SessionDetail | null = null;
      if (draftChatRef.current) {
        resolvedSessionId = null;
      }

      if (!detail && resolvedSessionId) {
        detail = preferredSessionId && preferredSessionId !== profile.current_session_id
          ? await activateSession(apiBaseUrl, token, resolvedSessionId)
          : await fetchSessionDetail(apiBaseUrl, token, resolvedSessionId);
      }

      let nextOverview: AgentOverview | null = null;
      let closeBehaviorConfig: { items: Array<{ value?: unknown }> } = { items: [] };
      if (resolvedSessionId) {
        nextOverview = await fetchAgentOverview(apiBaseUrl, token, {
          sessionId: resolvedSessionId || undefined,
        });
        closeBehaviorConfig = await fetchAgentConfig(
          apiBaseUrl,
          token,
          'channels.desktop.keep_runtime_on_app_close',
          resolvedSessionId || undefined
        ).catch(() => ({ items: [] }));
      }

      reconcileSidebarProjects(sessionList, {
        preferredSelectedProjectPath: draftChatRef.current?.projectPath || undefined,
        activeSessionWorkspace: detail?.workspace,
      });
      setSessions(sessionList);
      setJobs(jobList);
      setOverview(nextOverview);
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
      }
      startupSidebarReadyRef.current = true;
      startupChatSocketReadyRef.current = Boolean(resolvedSessionId) ? startupChatSocketReadyRef.current : true;
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

  useEffect(() => {
    if (!apiBaseUrl || !token) return;
    void refreshSidebarState(initialSessionId, false);
  }, [apiBaseUrl, initialSessionId, token]);

  useEffect(() => {
    if (!apiBaseUrl || !token || !sessionId) return;

    const intervalId = setInterval(() => {
      void refreshSidebarState(sessionId, true);
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
        pending: true,
      },
    ]);

    pendingMessagesRef.current.push({
      text,
      sourceFormat,
      interruptPolicy: policyOverride ?? interruptPolicy,
      sessionId: activeSessionId,
    });

    const ws = chatWsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      setChatRunActive(true);
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
      voiceComposerBaseInputRef.current = input;
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
        setInput(voiceComposerBaseInputRef.current);
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
        setMessages((previous) => [...previous, toDesktopMessage(message)]);
      }
      return;
    }

    if (event.type === 'assistant_delta') {
      setChatRunActive(true);
      setAssistantDraft((previous) => previous + String(payload.delta || ''));
      if (channel === 'voice') {
        setVoiceRunning(true);
      }
      return;
    }

    if (event.type === 'assistant_final') {
      const finalText = String(payload.text || '');
      const message = payload.message as SessionMessage | undefined;
      setAssistantDraft('');
      setThinking('');
      if (channel === 'voice') {
        voiceRunningRef.current = false;
        voiceRecordingRef.current = false;
        setVoiceRunning(false);
        setVoiceRecording(false);
      }
      if (message) {
        setMessages((previous) => [
          ...previous,
          toDesktopMessage(message),
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
          },
        ]);
      }
      setChatRunActive(false);
      setStatus('ready');
      void refreshSidebarState(event.session_id || sessionIdRef.current, true);
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
      setThinking(String(payload.formatted || payload.text || ''));
      return;
    }

    if (event.type === 'tool_event') {
      setChatRunActive(true);
      pushActivity(summarizeToolPayload(payload), 'accent');
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
      setOverview((previous) => (
        previous
          ? {
              ...previous,
              task_board: resolveTaskBoardState(board, eventSessionId, sessionIdRef.current),
              completed_task_boards: completedBoards,
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

    if (event.type === 'log') {
      const message = String(payload.message || '');
      const tone = payload.level === 'error' ? 'error' : payload.level === 'warn' ? 'warn' : 'neutral';
      pushActivity(message, tone);
      return;
    }

    if (event.type === 'status') {
      const message = String(payload.message || event.message || '');
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
      void refreshSidebarState(event.session_id || sessionIdRef.current, true);
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
        setInput(composeVoiceDraftInput(voiceComposerBaseInputRef.current, text));
      }
      return;
    }

    if (channel === 'voice' && event.type === 'voice_transcript') {
      const text = String(payload.text || '').trim();
      if (!text) {
        return;
      }
      if (alwaysOnEnabledRef.current && !ALWAYS_ON_VOICE_AUTO_SEND) {
        voiceComposerDraftRef.current = text;
        setInput(composeVoiceDraftInput(voiceComposerBaseInputRef.current, text));
      } else {
        setInput((current) => {
          const existing = current.trim();
          return existing ? `${existing} ${text}` : text;
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
      }
    }

    if (result.refresh || result.nextSessionId) {
      await refreshSidebarState(result.nextSessionId || sessionIdRef.current, true);
    }

    if (result.output) {
      appendLocalSystemMessage(result.output, 'Command Result');
      const activityPreview = result.output.split('\n', 1)[0]?.trim();
      if (activityPreview) {
        pushActivity(activityPreview, 'accent');
      }
    } else if (result.handled) {
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
      appendLocalSystemMessage(message, 'Command Error');
      pushActivity(message, 'error');
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
        }
      }
    }
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
    setInput('');
    setAssistantDraft('');
    setThinking('');

    if (isDesktopSlashCommand(trimmed)) {
      if (openCommandPanelForInput(trimmed)) {
        return;
      }
      await runSlashCommandFromComposer(trimmed);
      return;
    }

    setVoiceDraft('');
    if (draftChatRef.current) {
      try {
        const nextSessionId = await materializeDraftSession(draftChatRef.current.projectPath);
        queueMessage(trimmed, 'app_text', nextSessionId);
      } catch (error) {
        if (isBusySessionSwitchError(error)) {
          setPendingSessionSwitch({
            mode: 'draft_send',
            projectPath: draftChatRef.current.projectPath,
            text: trimmed,
            sourceFormat: 'app_text',
          });
          setStatus('current task is still running · stop it to start this new chat');
          return;
        }
        setStatus(describeError(error));
      }
      return;
    }

    if (agentRunActive) {
      if (interruptPolicy === 'none') {
        queueComposerMessage(trimmed, 'app_text');
      } else {
        queueMessage(trimmed, 'app_text', undefined, interruptPolicy);
      }
      return;
    }

    queueMessage(trimmed, 'app_text');
  };

  const selectCommandSuggestion = async (command: string) => {
    setInput('');
    setAssistantDraft('');
    setThinking('');
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
  }, [apiBaseUrl, selectedVoiceEngine, sessionId, token]);

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
      voiceRunningRef.current = false;
      voiceRecordingRef.current = false;
      void cleanupAssistantAudio();
    };
  }, [apiBaseUrl, sessionId, token]);

  const startVoiceCapture = async () => {
    if (!apiBaseUrl || !token) {
      voicePressActiveRef.current = false;
      setVoiceState('unavailable');
      setStatus('voice unavailable');
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

  const selectedProjectPath = normalizeWorkspacePath(
    draftChat?.projectPath
    || sidebarState.selectedProjectPath
    || sidebarState.lastSelectedProjectPath
    || sessions.find((item) => item.id === sessionIdRef.current)?.workspace
    || '',
  );

  const resetConversationForDraft = (projectPath: string) => {
    setSessionId(undefined);
    setSessionName('New chat');
    setMessages([]);
    setTimelineEvents([]);
    setTaskBoard(null);
    setCompletedTaskBoards([]);
    setTaskBoardCollapsed(false);
    setExpandedCompletedTaskIds({});
    setAssistantDraft('');
    setThinking('');
    setShowReferenceRail(false);
    selectProjectPath(projectPath);
  };

  const openDraftChat = (projectPath: string) => {
    const normalized = normalizeWorkspacePath(projectPath);
    if (!normalized) {
      return;
    }
    discardDraftChat({ clearInput: true });
    const nextDraft: SidebarDraftChat = {
      id: SIDEBAR_DRAFT_CHAT_ID,
      projectPath: normalized,
      title: 'New chat',
    };
    setSidebarExpanded(true);
    resetConversationForDraft(normalized);
    setDraftChat(nextDraft);
    setStatus(`new chat in ${projectPathBasename(normalized)}`);
  };

  const promptForProjectFolder = async () => {
    const picked = await pickDesktopFolder(selectedProjectPath || null);
    if (!picked) {
      return null;
    }
    const normalized = normalizeWorkspacePath(picked);
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

  const beginNewChat = async () => {
    let targetProject = selectedProjectPath;
    if (!targetProject) {
      targetProject = await promptForProjectFolder() || '';
    }
    if (!targetProject) {
      setStatus('choose a folder to start a new chat');
      return;
    }
    openDraftChat(targetProject);
  };

  const materializeDraftSession = async (projectPath: string) => {
    setStatus('creating chat');
    const created = await createSession(apiBaseUrl, token, { workspace: projectPath });
    applySessionDetail(created.session);
    await refreshSidebarState(created.session.id, true);
    return created.session.id;
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
    if (options?.projectPath) {
      revealProjectInSidebar(options.projectPath);
    }
    setStatus('switching shared session');
    setAssistantDraft('');
    setThinking('');
    try {
      const detail = await activateSession(apiBaseUrl, token, nextSessionId);
      applySessionDetail(detail);
      await refreshSidebarState(nextSessionId, true);
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
      setInput(pendingSessionSwitch.text);
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
      .sort((left, right) => {
        const leftPinned = Boolean(sidebarState.sessionMeta[left.id]?.pinned);
        const rightPinned = Boolean(sidebarState.sessionMeta[right.id]?.pinned);
        if (leftPinned !== rightPinned) {
          return leftPinned ? -1 : 1;
        }
        const leftOrder = sessionUiOrder(sidebarState.sessionMeta, left.id);
        const rightOrder = sessionUiOrder(sidebarState.sessionMeta, right.id);
        if (leftOrder !== rightOrder) {
          return leftOrder - rightOrder;
        }
        return left.updated_at < right.updated_at ? 1 : -1;
      });
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
      }
      pushActivity(`Run control: ${action}`, action === 'stop' ? 'warn' : 'accent');
      await refreshSidebarState(sessionIdRef.current, true);
    } catch (error) {
      setStatus(describeError(error));
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
  const pendingSwitchTargetLabel = pendingSessionSwitch?.mode === 'session'
    ? sessions.find((item) => item.id === pendingSessionSwitch.sessionId)?.name || 'selected chat'
    : pendingSessionSwitch
      ? `new chat in ${projectPathBasename(pendingSessionSwitch.projectPath)}`
      : null;
  const projectPaths = Array.from(new Set([
    ...sidebarState.projectOrder.map((item) => normalizeWorkspacePath(item)),
    ...Object.keys(sidebarState.projects).map((item) => normalizeWorkspacePath(item)),
    ...sessions.map((item) => normalizeWorkspacePath(item.workspace)),
    ...(draftChat ? [draftChat.projectPath] : []),
  ].filter(Boolean)));
  const projectGroups: SidebarProjectGroup[] = projectPaths
    .map((projectPath) => {
      const projectSessions = sessions
        .filter((item) => normalizeWorkspacePath(item.workspace) === projectPath)
        .sort((left, right) => {
          const leftPinned = Boolean(sidebarState.sessionMeta[left.id]?.pinned);
          const rightPinned = Boolean(sidebarState.sessionMeta[right.id]?.pinned);
          if (leftPinned !== rightPinned) {
            return leftPinned ? -1 : 1;
          }
          const leftOrder = sessionUiOrder(sidebarState.sessionMeta, left.id);
          const rightOrder = sessionUiOrder(sidebarState.sessionMeta, right.id);
          if (leftOrder !== rightOrder) {
            return leftOrder - rightOrder;
          }
          return left.updated_at < right.updated_at ? 1 : -1;
        });
      const projectState = sidebarState.projects[projectPath] || {};
      return {
        path: projectPath,
        label: projectDisplayName(projectPath, projectState),
        hint: projectPathHint(projectPath),
        pinned: Boolean(projectState.pinned),
        collapsed: Boolean(projectState.collapsed),
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
    ? contextUsage.compaction_state === 'needs_compaction'
      ? 'Needs Compact'
      : contextUsage.compaction_state === 'compacted'
        ? 'Compacted'
        : 'OK'
    : 'loading';
  const currentModelLabel = overview?.current_model || activeSession?.model || 'loading';
  const currentVariantLabel = overview?.current_variant ? ` · ${overview.current_variant}` : '';
  const currentPlannerLabel = overview?.planner_model || 'auto';
  const contextUsageRatio = Math.max(0, Math.min(1, contextPercent / 100));
  const contextUsageHoverLabel = contextUsage
    ? `${contextTokenLabel} · ${contextPercentLabel}`
    : 'Context loading';
  const taskBoardStatusText = taskBoardStatusLabel(taskBoard?.status);
  const taskBoardUpdatedLabel = taskBoard?.updated_at ? formatRelativeTime(taskBoard.updated_at) : null;
  const taskBoardSummary = taskBoard?.status === 'completed'
    ? taskBoard?.completion_summary || taskBoard?.progress_summary || taskBoard?.latest_summary || null
    : taskBoard?.progress_summary || taskBoard?.latest_summary || null;
  const taskBoardTone = taskBoard?.status === 'completed'
    ? 'complete'
    : taskBoard?.status === 'blocked' || taskBoard?.pending_reassessment_reason
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
  const voicePacks = voicePackState?.packs ?? [];
  const englishVoicePack = voicePacks.find((pack) => pack.id === VOICE_ENGINE_ENGLISH) ?? null;
  const hebrewVoicePack = voicePacks.find((pack) => pack.id === VOICE_ENGINE_HEBREW) ?? null;
  const selectedVoicePack = voicePacks.find((pack) => pack.id === selectedVoiceEngine) ?? null;
  const selectedVoicePackModel = voiceStatus?.stt_model || selectedVoicePack?.path || null;
  const selectedVoicePackPath = selectedVoicePack?.path || null;
  const selectedVoicePackSummary = selectedVoiceEngine === VOICE_ENGINE_NONE
    ? 'Voice input is off. Open setup to re-enable a local path.'
    : selectedVoicePack?.available
      ? `${selectedVoicePack.title} ready${selectedVoicePackModel ? ` · ${selectedVoicePackModel}` : ''}`
      : `${selectedVoicePack?.title || 'Selected voice path'} is not installed yet. Open setup to install it.`;
  const voicePackDiagnostics = selectedVoicePack?.available && selectedVoicePackPath
    ? `Installed pack path: ${selectedVoicePackPath}`
    : voiceStatus?.issues?.[0] || null;
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
  const timelineEntries = mergeTimelineEntries(messages, timelineEvents);
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
    || ['connecting', 'reconnecting', 'error'].includes(voiceState);
  const voicePanelActive = !voicePanelHidden && (
    showVoicePanel
    || Boolean(voiceDraft)
    || Boolean(voiceError)
    || alwaysOnEnabled
    || voiceRecording
    || voiceRunning
  );
  const agentRunActive = chatRunActive || Boolean(assistantDraft) || Boolean(thinking) || taskBoard?.status === 'active';
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
    try {
      const switched = await onSelectVoiceEngine?.(engine);
      if (switched === false) {
        setVoiceError(`Could not switch to the ${engine === VOICE_ENGINE_HEBREW ? 'Hebrew' : 'English'} voice path.`);
      }
    } catch (error) {
      const message = describeError(error);
      setVoiceError(message);
      pushActivity(`Voice path switch failed: ${message}`, 'error');
    } finally {
      setVoiceEngineChanging(false);
    }
  };
  const historyAvailable = Boolean(timelineEntries.length || referenceEntries.length);
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
    : null;

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
    <View style={styles.shell}>
      <View style={styles.conversationColumn}>
        <ScrollView
          ref={scrollRef}
          style={[styles.transcriptScroll, styles.centeredConversationBlock]}
          contentContainerStyle={styles.transcriptContent}
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

          {transcriptEntries.length === 0 && referenceEntries.length === 0 ? (
            <View style={styles.emptyConversationCard}>
              <Text style={styles.emptyTitle}>No conversation turns yet</Text>
              <Text style={styles.emptyText}>Start typing below or use voice. Live voice status appears above the composer.</Text>
            </View>
          ) : null}

          {transcriptEntries.map(({ fullIndex, message }, index) => (
              <View
                key={`${message.timestamp || 'ts'}-${fullIndex}-${index}`}
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
          ))}

          {assistantDraft ? (
            <View style={[styles.messageBubble, styles.messageBubbleAssistant, styles.messageBubbleDraft]}>
              <View style={styles.messageHeader}>
                <Text style={styles.messageLabel}>Assistant</Text>
                <Text style={styles.messageTime}>streaming</Text>
              </View>
              <Text style={styles.messageText}>{assistantDraft}</Text>
            </View>
          ) : null}
        </ScrollView>

        {showVoiceBanner ? (
          <View style={[styles.centeredConversationBlock, styles.voiceBanner, voiceError ? styles.voiceBannerError : null]}>
            <Text style={styles.voiceBannerTitle}>Voice</Text>
            <Text style={styles.voiceBannerText}>{voiceBannerText}</Text>
          </View>
        ) : null}

        {taskBoard ? (
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
                <Text style={styles.taskBoardGoal}>{taskBoard.main_goal}</Text>
                <Text style={styles.taskBoardMeta}>
                  {taskBoardSummary || `${taskBoard.completed_sub_goals}/${taskBoard.total_sub_goals} sub-goals complete`}
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
                {taskBoard.pending_reassessment_reason ? (
                  <View style={styles.taskBoardAlert}>
                    <Text style={styles.taskBoardAlertLabel}>Reassessing</Text>
                    <Text style={styles.taskBoardAlertText}>{taskBoard.pending_reassessment_reason}</Text>
                  </View>
                ) : null}

                <View style={styles.taskBoardInfoRow}>
                  <View style={styles.taskBoardInfoChip}>
                    <Text style={styles.taskBoardInfoLabel}>Current Focus</Text>
                    <Text style={styles.taskBoardInfoValue}>
                      {taskBoard.status === 'completed'
                        ? 'Task complete'
                        : taskBoard.current_focus || 'Choose next sub-goal'}
                    </Text>
                  </View>
                  <View style={styles.taskBoardInfoChip}>
                    <Text style={styles.taskBoardInfoLabel}>Next Method</Text>
                    <Text style={styles.taskBoardInfoValue}>
                      {taskBoard.status === 'completed'
                        ? taskBoard.completion_summary || 'Task complete. No next method is needed.'
                        : taskBoard.next_method || 'Not set yet'}
                    </Text>
                  </View>
                </View>

                <View style={styles.taskBoardSteps}>
                  {taskBoard.sub_goals.map((subGoal) => (
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
                    <Text style={styles.taskBoardStepPrefix}>{taskBoard.verification_status === 'done' ? '[x]' : '[ ]'}</Text>
                    <View style={styles.taskBoardStepCopy}>
                      <Text style={styles.taskBoardStepTitle}>Verify the requested result and close the task</Text>
                      {taskBoard.verification_summary ? (
                        <Text style={styles.taskBoardStepMeta}>{taskBoard.verification_summary}</Text>
                      ) : (
                        <Text style={styles.taskBoardStepMeta}>
                          {taskBoard.status === 'completed'
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
                <Text style={styles.completedTaskBoardsTitle}>Completed Managed Tasks</Text>
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
                          {completedAtLabel ? `${formatRelativeTime(completedAtLabel)} · ` : ''}{summaryText}
                        </Text>
                      </View>
                      <Text style={styles.completedTaskCardToggle}>{expanded ? 'Collapse' : 'Expand'}</Text>
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

        <View style={styles.composerDock}>
        <View style={styles.composerShell}>
          {thinking ? (
            <View style={styles.thinkingCard}>
              <Text style={styles.thinkingLabel}>Thinking</Text>
              <Text style={styles.thinkingText}>{thinking}</Text>
            </View>
          ) : null}

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
            {floatingPanelKind ? (
              <View
                style={[
                  styles.commandPanelFloatingLayer,
                  styles.commandPanelFloatingRight,
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
                    {overview?.model_groups?.length || overview?.available_planner_models?.length ? (
                      <ScrollView style={styles.modelPickerScroll} contentContainerStyle={styles.modelPickerContent}>
                        {overview.model_groups.map((group) => (
                          <View key={group.provider} style={styles.modelProviderBlock}>
                            <Text style={styles.modelProviderTitle}>{group.provider}</Text>
                            <View style={styles.modelList}>
                              {group.models.map((model) => {
                                const selected = model === overview.current_model;
                                return (
                                  <Pressable
                                    key={`${group.provider}-${model}`}
                                    style={[styles.modelListItem, selected ? styles.modelListItemActive : null]}
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
                              style={[styles.modelListItem, !overview?.planner_model ? styles.modelListItemActive : null]}
                              onPress={() => void choosePlannerModel(null)}
                            >
                              <View style={styles.modelListItemCopy}>
                                <Text style={[styles.modelListItemTitle, !overview?.planner_model ? styles.modelListItemTitleActive : null]}>
                                  Automatic
                                </Text>
                              </View>
                              <Text style={[styles.modelListItemMeta, !overview?.planner_model ? styles.modelListItemMetaActive : null]}>
                                {!overview?.planner_model ? 'Current' : 'Select'}
                              </Text>
                            </Pressable>
                            {overview?.available_planner_models?.map((model) => {
                              const selected = model === overview?.planner_model;
                              return (
                                <Pressable
                                  key={`planner-inline-${model}`}
                                  style={[styles.modelListItem, selected ? styles.modelListItemActive : null]}
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

              </View>
            ) : null}
          </View>

          {commandSuggestions.length ? (
            <View style={styles.commandSuggestionMenu}>
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

          <View style={styles.composerTextRegion}>
            <TextInput
              nativeID="desktop-composer-input"
              style={styles.composerInput}
              value={input}
              onChangeText={setInput}
              onKeyPress={handleComposerKeyPress}
              placeholder={DESKTOP_COMMAND_PLACEHOLDER}
              placeholderTextColor="#8f9ebb"
              multiline
            />

            <View style={styles.composerFooterRow}>
              <View style={styles.composerFooterControls}>
                <Pressable
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
                      <Text style={styles.contextMeterDetailText}>{contextUsageHoverLabel}</Text>
                      <Text style={styles.contextMeterDetailMeta}>{contextStateLabel}</Text>
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
          <ScrollView style={styles.sidebarContentScroll} contentContainerStyle={styles.sidebarContentStack}>
            <View style={styles.sidebarNavStack}>
              <Pressable style={styles.sidebarListRow} onPress={() => void beginNewChat()}>
                <MonoIcon name="compose" style={styles.sidebarListRowIcon} />
                <View style={styles.sidebarListRowCopy}>
                  <Text style={styles.sidebarListRowTitle}>New chat</Text>
                  <Text style={styles.sidebarListRowText}>
                    {selectedProjectPath ? `Start in ${projectPathBasename(selectedProjectPath)}` : 'Choose a folder and start a chat'}
                  </Text>
                </View>
                {draftChat ? <Text style={styles.sidebarListRowMeta}>Draft</Text> : null}
              </Pressable>

              <Pressable style={styles.sidebarSearchShell} onPress={openSidebarSearchModal}>
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
                        <Text style={styles.sidebarSimpleRowTitle} numberOfLines={1}>{session.name}</Text>
                      </View>
                      <Text style={styles.sidebarSimpleRowMeta}>{formatRelativeTime(session.updated_at)}</Text>
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
                                  openDraftChat(project.path);
                                }}
                              >
                                <MonoIcon name="plus" style={styles.projectHeaderActionText} />
                              </Pressable>
                              <Pressable
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
                          <View style={styles.projectMenu}>
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
                              <Text style={[styles.projectMenuItemText, styles.projectMenuItemTextWarn]}>Delete folder</Text>
                            </Pressable>
                          </View>
                        ) : null}

                        {!project.collapsed ? (
                          <View style={styles.projectContent}>
                            {projectHasDraft ? (
                              <View style={[styles.projectChatRow, styles.projectChatRowDraft]}>
                                <View style={styles.projectChatPrimary}>
                                  <View style={styles.projectChatTitleRow}>
                                    <Text style={styles.projectChatTitle}>New chat</Text>
                                    <Text style={styles.projectChatAge}>Draft</Text>
                                  </View>
                                </View>
                              </View>
                            ) : null}

                            {project.sessions.map((item) => {
                              const selected = item.id === sessionId;
                              return (
                                <View
                                  key={item.id}
                                  style={[styles.projectChatRow, selected ? styles.projectChatRowActive : null]}
                                  {...sessionDragProps(project.path, item.id)}
                                >
                                  <Pressable style={styles.projectChatPrimary} onPress={() => void openSession(item.id)}>
                                    <View style={styles.projectChatTitleRow}>
                                      <Text style={styles.projectChatTitle} numberOfLines={1}>{item.name}</Text>
                                      <Text style={styles.projectChatAge}>{formatRelativeTime(item.updated_at)}</Text>
                                    </View>
                                  </Pressable>
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

      {sidebarSearchOpen ? (
        <Pressable style={styles.sidebarSearchModalOverlay} onPress={closeSidebarSearchModal}>
          <Pressable
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
    borderRadius: 0,
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
    borderRadius: 16,
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
    borderRadius: 16,
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
    borderRadius: 16,
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
    borderRadius: 14,
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
    borderRadius: 16,
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
    borderRadius: 0,
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
    borderRadius: 0,
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
    borderRadius: 0,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  sidebarSimpleRowActive: {
    backgroundColor: '#363636',
  },
  sidebarSimpleRowCopy: {
    flex: 1,
    gap: 2,
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
    borderRadius: 999,
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
    paddingHorizontal: 14,
    paddingVertical: 14,
    gap: 10,
  },
  sidebarSearchModalInputShell: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: 16,
    backgroundColor: '#333333',
    paddingHorizontal: 14,
    paddingVertical: 12,
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
    gap: 6,
    paddingBottom: 8,
  },
  sidebarSearchResultRow: {
    backgroundColor: '#383838',
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 9,
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
    borderRadius: 12,
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
    paddingVertical: 6,
    marginBottom: 4,
  },
  projectMenuItem: {
    paddingHorizontal: 12,
    paddingVertical: 8,
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
    borderRadius: 0,
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
    borderRadius: 0,
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
    borderRadius: 14,
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
    borderRadius: 0,
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
    borderRadius: 0,
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
    borderRadius: 0,
    backgroundColor: 'transparent',
    borderWidth: 0,
    borderColor: 'transparent',
    paddingHorizontal: 10,
    paddingVertical: 4,
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
    borderRadius: 999,
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
    borderRadius: 999,
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
    borderRadius: 999,
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
    borderRadius: 0,
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
    borderRadius: 999,
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
    borderRadius: 0,
    backgroundColor: '#0f2a34',
    borderWidth: 1,
    borderColor: '#24526a',
    paddingHorizontal: 16,
    paddingVertical: 14,
    gap: 6,
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
  transcriptContent: {
    padding: 18,
    gap: 12,
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
    paddingTop: 8,
    paddingBottom: 6,
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
  composerUtilityAnchor: {
    position: 'relative',
    zIndex: 20,
  },
  composerTextRegion: {
    position: 'relative',
    minHeight: 84,
    justifyContent: 'flex-start',
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
  thinkingCard: {
    borderRadius: 18,
    backgroundColor: '#172440',
    padding: 14,
    gap: 5,
  },
  thinkingLabel: {
    color: '#97b4ff',
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  thinkingText: {
    color: '#dce7ff',
    lineHeight: 20,
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
    borderRadius: 0,
    backgroundColor: '#d4ff65',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  pendingSwitchPrimaryActionText: {
    color: '#0b1325',
    fontWeight: '900',
  },
  pendingSwitchSecondaryAction: {
    borderRadius: 0,
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
    borderRadius: 0,
    backgroundColor: '#091225',
    borderWidth: 1,
    borderColor: '#2a3f68',
    padding: 14,
    gap: 14,
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
  commandPanelFloating: {
    shadowColor: '#02060f',
    shadowOpacity: 0.42,
    shadowRadius: 22,
    shadowOffset: { width: 0, height: 16 },
    elevation: 18,
  },
  commandPanelHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
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
    fontSize: 18,
    fontWeight: '900',
  },
  commandPanelText: {
    color: '#a9bcda',
    fontSize: 13,
    lineHeight: 18,
  },
  commandPanelCloseButton: {
    borderRadius: 0,
    backgroundColor: '#17253f',
    paddingHorizontal: 12,
    paddingVertical: 8,
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
    gap: 12,
  },
  modelProviderBlock: {
    gap: 8,
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
  modelList: {
    gap: 8,
  },
  modelListItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    borderRadius: 0,
    backgroundColor: '#101b32',
    borderWidth: 1,
    borderColor: '#213655',
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  modelListItemActive: {
    backgroundColor: '#d4ff65',
    borderColor: '#d4ff65',
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
  commandPanelEmpty: {
    borderRadius: 0,
    backgroundColor: '#101b32',
    padding: 14,
    gap: 5,
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
    borderRadius: 0,
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
  interruptOptionList: {
    gap: 8,
  },
  interruptOptionCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    borderRadius: 0,
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
    gap: 10,
  },
  sessionCommandCard: {
    borderRadius: 0,
    backgroundColor: '#101b32',
    borderWidth: 1,
    borderColor: '#213659',
    padding: 14,
    gap: 6,
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
    paddingHorizontal: 10,
    paddingVertical: 5,
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
    borderRadius: 0,
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
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 2,
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    gap: 12,
  },
  composerFooterControls: {
    flexDirection: 'row',
    alignItems: 'flex-end',
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
  composerStatusInline: {
    color: '#8da2c4',
    fontSize: 12,
    maxWidth: 160,
    textAlign: 'right',
  },
  interruptChooserButton: {
    minWidth: 132,
    borderRadius: 0,
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
    borderRadius: 0,
    backgroundColor: '#091225',
    borderWidth: 1,
    borderColor: '#2a3f68',
    padding: 10,
    gap: 8,
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
    borderRadius: 0,
    backgroundColor: '#17253f',
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  commandSuggestionCloseText: {
    color: '#dbe7fb',
    fontSize: 11,
    fontWeight: '800',
  },
  commandSuggestionList: {
    gap: 6,
  },
  commandSuggestionItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: 0,
    backgroundColor: '#101b32',
    paddingHorizontal: 12,
    paddingVertical: 10,
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
    flex: 1,
    minHeight: 72,
    maxHeight: 220,
    borderRadius: 0,
    backgroundColor: 'transparent',
    borderWidth: 0,
    borderColor: 'transparent',
    color: '#f6fbff',
    paddingHorizontal: 0,
    paddingVertical: 0,
    paddingTop: 2,
    paddingBottom: 36,
    textAlignVertical: 'top',
    fontSize: 15,
    lineHeight: 22,
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
    borderRadius: 0,
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
    borderRadius: 0,
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
    borderRadius: 0,
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
    borderRadius: 0,
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
    borderRadius: 0,
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
    borderRadius: 0,
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
