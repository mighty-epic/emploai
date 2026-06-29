import type { FleetIdentity, SessionSummary } from '@/lib/appApi';

export const VOICE_SEGMENT_MS = 850;
export const SOCKET_RECONNECT_MS = 1600;
export const OUTBOUND_MESSAGE_TTL_MS = 60_000;
export const OUTBOUND_RETRY_MS = 2_000;
export const QUICK_TURN_OPTIONS = [50, 100, 200, 500];
export const CHAT_NO_ACTIVE_SESSION_STATUS = 'Open or select a chat before using agent controls.';
export const CHAT_CONTROL_GROUPS = [
  ['Chat', 'New chat, sidebar, search, attachments'],
  ['Run control', 'Pause, stop, steering, verbose run feed'],
  ['Agent', 'Model, variant, planner, skills, tools'],
  ['Workspace', 'Project folder, branch, file context, artifacts'],
  ['System', 'Account, pairing, automations, diagnostics'],
] as const;

export function sessionBelongsToFleetIdentity(session: SessionSummary, identity: FleetIdentity | null | undefined) {
  if (!identity?.identity_id) return true;
  const sessionIdentityId = String(session.fleet_identity_id || '').trim();
  const identityId = String(identity.identity_id || '').trim();
  const role = String(identity.role || '').trim().toLowerCase();
  if (sessionIdentityId) return sessionIdentityId === identityId;
  if (role === 'worker') return Boolean(identity.worker_id && session.fleet_worker_id === identity.worker_id);
  return role === 'manager';
}

export function fleetSessionCreateFields(identity: FleetIdentity | null | undefined) {
  if (!identity?.identity_id) return {};
  return {
    fleet_identity_id: identity.identity_id,
    fleet_identity_role: identity.role || null,
    fleet_worker_id: identity.worker_id || null,
  };
}

export function identityLabel(identity?: FleetIdentity | null) {
  if (!identity) return 'Manager';
  return identity.display_name || identity.identity_id || 'Identity';
}

export function normalizeWorkspacePath(value?: string | null) {
  return String(value || '').trim() || 'workspace://default';
}

export const TOOL_PACK_DEFINITIONS = [
  { id: 'interactive_desktop', label: 'Interactive Desktop', description: 'Vision, OCR, clicking, typing, windows, and browser-extension actions.' },
  { id: 'browser_isolated', label: 'Isolated Browser', description: 'Browser automation without using the live desktop.' },
  { id: 'workspace_write', label: 'Workspace Write', description: 'Editing files and running workspace commands.' },
  { id: 'workspace_read', label: 'Workspace Read', description: 'Reading files, searching code, tests, diffs, and safe shell reads.' },
  { id: 'web_research', label: 'Web Research', description: 'Search and fetch external documentation or websites.' },
  { id: 'scheduler', label: 'Automations', description: 'Recurring tasks, event feed, and scheduler inspection.' },
  { id: 'app_runtime', label: 'App Runtime', description: 'Session and runtime controls that are safe for this chat.' },
] as const;

export const DEFAULT_TOOL_PACK_IDS = TOOL_PACK_DEFINITIONS.map((pack) => pack.id);

export async function loadDocumentPickerModule() {
  return import('expo-document-picker');
}

export async function loadFileSystemModule() {
  return import('expo-file-system/legacy');
}

export async function loadImagePickerModule() {
  return import('expo-image-picker');
}

export type ScreenPreview = {
  uri: string;
  backend: string;
  width: number;
  height: number;
};

export type InterruptPolicy = 'none' | 'steer_now' | 'after_tool';

export type PendingOutboundMessage = {
  id: string;
  text: string;
  sessionId?: string;
  interruptPolicy: InterruptPolicy;
  expiresAt: number;
};

export function createClientId() {
  return `app-${Math.random().toString(36).slice(2, 10)}`;
}

export function normalizeRouteSessionId(value: string | string[] | undefined) {
  if (Array.isArray(value)) {
    return value[0];
  }
  return value;
}

export function normalizeRouteWorkspace(value: string | string[] | undefined) {
  const clean = String(normalizeRouteSessionId(value) || '').trim();
  if (!clean || clean === 'workspace://default') {
    return undefined;
  }
  return clean;
}
