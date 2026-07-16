import type { DesktopFleetSnapshot } from '@/lib/desktopBridge';

function text(value: unknown) {
  return String(value || '').trim();
}

export function fleetLocalDesktopId(snapshot: DesktopFleetSnapshot | null | undefined) {
  return text(snapshot?.manager?.desktop_id);
}

export function fleetDirectChildDesktopIds(snapshot: DesktopFleetSnapshot | null | undefined) {
  if (!snapshot) return [];

  const localDesktopId = fleetLocalDesktopId(snapshot);
  const pairedIds = new Set(
    (snapshot.connection_permissions || [])
      .filter((permission) => text(permission.source).toLowerCase() === 'paired_desktop')
      .map((permission) => text(permission.desktop_id))
      .filter((desktopId) => desktopId && desktopId !== localDesktopId),
  );

  // Current pairings publish an explicit paired_desktop capability record. A
  // legacy snapshot may not have one, so retain the non-local desktop fallback
  // until all existing installations have refreshed their Fleet metadata.
  if (pairedIds.size) return Array.from(pairedIds);

  const legacyIds = new Set<string>();
  for (const desktop of snapshot.desktops || []) {
    const desktopId = text(desktop.desktop_id);
    if (desktopId && desktopId !== localDesktopId) legacyIds.add(desktopId);
  }
  for (const worker of snapshot.workers || []) {
    const desktopId = text(worker.machine_desktop_id);
    if (desktopId && desktopId !== localDesktopId) legacyIds.add(desktopId);
  }
  return Array.from(legacyIds);
}

export function fleetTopologyStatus(snapshot: DesktopFleetSnapshot) {
  const computerCount = fleetDirectChildDesktopIds(snapshot).length;
  const localDesktopId = fleetLocalDesktopId(snapshot);
  const localAgentCount = (snapshot.workers || []).filter(
    (worker) => !localDesktopId || text(worker.machine_desktop_id) === localDesktopId,
  ).length;
  const computerLabel = `${computerCount} computer${computerCount === 1 ? '' : 's'} below`;
  const agentLabel = `${localAgentCount} local agent${localAgentCount === 1 ? '' : 's'}`;
  return `${computerLabel} · ${agentLabel}`;
}

export function normalizeFleetSnapshotForDesktop(
  snapshot: DesktopFleetSnapshot | null | undefined,
): DesktopFleetSnapshot | null | undefined {
  if (!snapshot) return snapshot;

  // The snapshot manager is the authoritative local point of view. Account-era
  // auth state is deliberately not consulted: local-only Yggdrasil desktops do
  // not have a shared account identity, and a stale auth record can identify a
  // paired child as the current computer.
  const currentDesktopId = fleetLocalDesktopId(snapshot);
  if (!currentDesktopId) return snapshot;

  const managerFilter = (item: any) => (
    text(item?.role).toLowerCase() !== 'manager'
    || text(item?.desktop_id) === currentDesktopId
  );
  const identities = Array.isArray(snapshot.identities)
    ? snapshot.identities.filter(managerFilter)
    : [];
  const instances = Array.isArray(snapshot.instances)
    ? snapshot.instances.filter(managerFilter)
    : [];
  const currentManager = (
    instances.find((item: any) => text(item?.role).toLowerCase() === 'manager')
    || identities.find((item: any) => text(item?.role).toLowerCase() === 'manager')
    || snapshot.manager
    || null
  );
  const visibleIdentityIds = new Set(
    identities.map((item: any) => text(item?.identity_id)).filter(Boolean),
  );
  const selectedChatByIdentity = Object.fromEntries(
    Object.entries(snapshot.selected_chat_by_identity || {})
      .filter(([identityId]) => visibleIdentityIds.has(text(identityId))),
  );
  const activeIdentityVisible = snapshot.active_identity?.identity_id
    && visibleIdentityIds.has(text(snapshot.active_identity.identity_id));
  const activeIdentity = activeIdentityVisible
    ? snapshot.active_identity
    : identities.find((item: any) => (
        text(item?.identity_id) === text((currentManager as any)?.identity_id || (currentManager as any)?.instance_id)
      ))
      || currentManager
      || identities[0]
      || null;

  return {
    ...snapshot,
    identities,
    instances,
    manager: currentManager,
    active_identity: activeIdentity as any,
    active_identity_id: (activeIdentity as any)?.identity_id || (activeIdentity as any)?.instance_id || null,
    selected_chat_by_identity: selectedChatByIdentity,
  };
}
