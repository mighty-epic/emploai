import type { TaskBoard } from '@/lib/appApi';
import type { DesktopRuntimeStatus } from '@/lib/desktopBridge';

export function summarizeRuntimeStatus(runtimeStatus?: DesktopRuntimeStatus | null) {
  if (!runtimeStatus) return 'Bootstrapping local runtime';
  const base = runtimeStatus.state || runtimeStatus.mode || 'unknown';
  if (runtimeStatus.degraded) {
    return `${base} \u00b7 degraded`;
  }
  return base;
}

export function taskBoardStatusLabel(status: string | null | undefined) {
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

export function taskBoardStepPrefix(status: string | null | undefined) {
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

export function resolveTaskBoardState(
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

export function normalizeCompletedTaskBoards(boards: TaskBoard[] | null | undefined) {
  return [...(boards || [])].sort((left, right) => {
    const leftTime = Date.parse(left.collapsed_completed_at || left.completed_at || left.updated_at || left.created_at || '') || 0;
    const rightTime = Date.parse(right.collapsed_completed_at || right.completed_at || right.updated_at || right.created_at || '') || 0;
    return rightTime - leftTime;
  });
}
