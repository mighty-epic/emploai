import type { DesktopFleetSnapshot, DesktopFleetYggdrasilStatus } from '@/lib/desktopBridge';
import { remoteRuntimesFromFleetSnapshot } from './desktopRemoteRuntimes';

export type DesktopFleetHierarchyRole = 'loading' | 'standalone' | 'root_manager' | 'leaf' | 'intermediary';

export function directFleetChildren(snapshot: DesktopFleetSnapshot | null | undefined) {
  return remoteRuntimesFromFleetSnapshot(snapshot);
}

export function resolveDesktopFleetHierarchyRole(
  status: DesktopFleetYggdrasilStatus | null | undefined,
  snapshot: DesktopFleetSnapshot | null | undefined,
): DesktopFleetHierarchyRole {
  if (status === undefined) return 'loading';
  const hasParent = Boolean(status?.connection?.configured);
  const hasChildren = directFleetChildren(snapshot).length > 0;
  if (hasParent && hasChildren) return 'intermediary';
  if (hasParent) return 'leaf';
  if (hasChildren) return 'root_manager';
  return 'standalone';
}
