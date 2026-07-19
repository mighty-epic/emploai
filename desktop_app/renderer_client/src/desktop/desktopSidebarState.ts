import type { SessionSummary } from '@/lib/appApi';
import type {
  DesktopFleetIdentity,
  DesktopSidebarProjectState,
  DesktopSidebarSessionState,
  DesktopSidebarState,
} from '@/lib/desktopBridge';

export const DESKTOP_SIDEBAR_STATE_VERSION = 1;
export const DESKTOP_SIDEBAR_ACTIVITY_LIMIT = 8;
export const SIDEBAR_DRAFT_CHAT_ID = '__draft__';

export function projectDisplayName(projectPath: string, state?: DesktopSidebarProjectState | null) {
  const customName = String(state?.displayName || '').trim();
  return customName || projectPathBasename(projectPath);
}

export function normalizeWorkspacePath(value: string | null | undefined) {
  const trimmed = String(value || '').trim();
  if (!trimmed) {
    return '';
  }
  return trimmed.replace(/\//g, '\\').replace(/\\+$/, '');
}

export function sessionBelongsToFleetIdentity(session: SessionSummary, identity: DesktopFleetIdentity | null | undefined) {
  if (!identity?.identity_id) {
    return true;
  }
  const sessionIdentityId = String(session.fleet_identity_id || '').trim();
  const sessionIdentityRole = String(session.fleet_identity_role || '').trim().toLowerCase();
  const sessionWorkerId = String(session.fleet_worker_id || '').trim();
  const identityId = String(identity.identity_id || '').trim();
  const identityRole = String(identity.role || '').trim().toLowerCase();
  if (identityRole === 'worker') {
    if (sessionIdentityId) {
      return sessionIdentityId === identityId;
    }
    return Boolean(identity.worker_id && sessionWorkerId === identity.worker_id);
  }
  if (identityRole === 'manager') {
    if (sessionIdentityRole === 'worker' || sessionWorkerId) {
      return false;
    }
    if (sessionIdentityId === identityId || sessionIdentityRole === 'manager') {
      return true;
    }
    return !sessionIdentityId && !sessionIdentityRole;
  }
  return Boolean(sessionIdentityId && sessionIdentityId === identityId);
}

export function sessionIdForFleetIdentity(
  sessionList: SessionSummary[],
  identity: DesktopFleetIdentity | null | undefined,
  selectedSessionId?: string | null,
) {
  const cleanSelectedSessionId = String(selectedSessionId || '').trim();
  if (cleanSelectedSessionId) {
    const selectedSession = sessionList.find((item) => item.id === cleanSelectedSessionId);
    if (selectedSession && sessionBelongsToFleetIdentity(selectedSession, identity)) {
      return cleanSelectedSessionId;
    }
  }
  return sessionList.find((item) => sessionBelongsToFleetIdentity(item, identity))?.id || '';
}

export function fleetSessionCreateFields(identity: DesktopFleetIdentity | null | undefined) {
  if (!identity?.identity_id) {
    return {};
  }
  return {
    fleet_identity_id: identity.identity_id,
    fleet_identity_role: identity.role || null,
    fleet_worker_id: identity.worker_id || null,
  };
}

export function isWorkspacePathAllowed(projectPath: string, allowedRoot: string) {
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

export function shouldKeepSidebarProjectPath(
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

export function isAbsoluteWindowsPath(projectPath: string) {
  const normalized = normalizeWorkspacePath(projectPath);
  return /^[a-zA-Z]:\\/.test(normalized) || normalized.startsWith('\\\\');
}

export function projectPathBasename(projectPath: string) {
  const normalized = normalizeWorkspacePath(projectPath);
  if (!normalized) {
    return 'Project';
  }
  const parts = normalized.split('\\').filter(Boolean);
  return parts[parts.length - 1] || normalized;
}

export function projectPathHint(projectPath: string) {
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

export function createEmptySidebarState(): DesktopSidebarState {
  return {
    version: DESKTOP_SIDEBAR_STATE_VERSION,
    projectOrder: [],
    projects: {},
    sessionMeta: {},
    selectedProjectPath: null,
    lastSelectedProjectPath: null,
  };
}

export function coerceSidebarState(value: DesktopSidebarState | null | undefined): DesktopSidebarState {
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

export function ensureSidebarProjectEntry(state: DesktopSidebarState, projectPath: string): DesktopSidebarState {
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

export function ensureSidebarProjectEntries(state: DesktopSidebarState, projectPaths: string[]) {
  return projectPaths.reduce((next, projectPath) => ensureSidebarProjectEntry(next, projectPath), state);
}

export function workspaceSortOrder(order: string[], value: string) {
  const index = order.indexOf(value);
  return index >= 0 ? index : Number.MAX_SAFE_INTEGER;
}

export function sessionUiOrder(sessionMeta: Record<string, DesktopSidebarSessionState>, sessionId: string) {
  const value = sessionMeta[sessionId]?.order;
  return typeof value === 'number' ? value : Number.MAX_SAFE_INTEGER;
}

export function sessionSidebarSortTime(session: SessionSummary) {
  return String(session.created_at || session.updated_at || '');
}

export function sessionSidebarSortComparator(
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

export function existingSessionIdFrom(
  sessionList: SessionSummary[],
  ...candidateIds: Array<string | null | undefined>
) {
  for (const candidate of candidateIds) {
    const clean = String(candidate || '').trim();
    if (clean && sessionList.some((item) => item.id === clean)) {
      return clean;
    }
  }
  return null;
}
