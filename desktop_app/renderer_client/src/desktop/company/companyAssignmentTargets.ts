import type { CompanyDetail } from '@/lib/appApi';
import type {
  DesktopFleetIdentity,
  DesktopFleetRemoteTarget,
  DesktopFleetSnapshot,
} from '@/lib/desktopBridge';


export type CompanyAssignmentTarget = {
  identityId: string;
  displayName: string;
  role: string;
  status: string;
  computerId: string;
  computerName: string;
  scope: 'local' | 'child';
  isDefault: boolean;
};

function employeeCanAcceptWork(employee: CompanyDetail['employees'][number]): boolean {
  if (employee.status !== 'active') return false;
  const baseline = employee.protected && (
    employee.system_role === 'manager' || employee.is_default
  );
  return baseline || ['ready', 'limited_ready'].includes(employee.job_contract_status);
}

type BuildCompanyAssignmentTargetsArgs = {
  company: CompanyDetail | null;
  localComputerId: string;
  localComputerName: string;
  identities: DesktopFleetIdentity[];
  fleetSnapshot: DesktopFleetSnapshot | null | undefined;
};

function clean(value: unknown): string {
  return String(value ?? '').trim();
}

function targetFromRemote(
  target: DesktopFleetRemoteTarget,
  computerId: string,
  computerName: string,
): CompanyAssignmentTarget | null {
  const identityId = clean(target.identity_id);
  if (!identityId) return null;
  return {
    identityId,
    displayName: clean(target.display_name) || (target.role === 'manager' ? 'Manager' : 'Worker'),
    role: clean(target.role || target.target_kind) || 'worker',
    status: clean(target.status) || 'available',
    computerId,
    computerName,
    scope: 'child',
    isDefault: Boolean(target.is_default),
  };
}

/**
 * Company work may target local employees or identities explicitly published by
 * a direct child. Company membership is the allow-list; Fleet publication is
 * the live routability check. Connection permissions contain direct children
 * only, so this never flattens grandchildren into the root picker.
 */
export function buildCompanyAssignmentTargets({
  company,
  localComputerId,
  localComputerName,
  identities,
  fleetSnapshot,
}: BuildCompanyAssignmentTargetsArgs): CompanyAssignmentTarget[] {
  const activeEmployeeIds = new Set(
    (company?.employees || [])
      .filter(employeeCanAcceptWork)
      .map((employee) => clean(employee.identity_id))
      .filter(Boolean),
  );
  const byIdentity = new Map<string, CompanyAssignmentTarget>();

  for (const identity of identities) {
    const identityId = clean(identity.identity_id);
    if (!identityId || !activeEmployeeIds.has(identityId)) continue;
    byIdentity.set(identityId, {
      identityId,
      displayName: clean(identity.display_name) || (identity.role === 'manager' ? 'Manager' : 'Worker'),
      role: clean(identity.role) || 'worker',
      status: clean(identity.status) || 'available',
      computerId: localComputerId,
      computerName: localComputerName,
      scope: 'local',
      isDefault: Boolean(identity.is_default),
    });
  }

  const desktopNames = new Map(
    (fleetSnapshot?.desktops || []).map((desktop) => [
      clean(desktop.desktop_id),
      clean(desktop.display_name) || clean(desktop.desktop_id),
    ]),
  );
  for (const connection of fleetSnapshot?.connection_permissions || []) {
    if (connection.source !== 'paired_desktop') continue;
    const computerId = clean(connection.desktop_id);
    if (!computerId) continue;
    const computerName = desktopNames.get(computerId) || computerId;
    for (const target of connection.capabilities?.targets || []) {
      const candidate = targetFromRemote(target, computerId, computerName);
      if (!candidate || !activeEmployeeIds.has(candidate.identityId)) continue;
      byIdentity.set(candidate.identityId, candidate);
    }
  }

  return [...byIdentity.values()].sort((left, right) => {
    if (left.scope !== right.scope) return left.scope === 'local' ? -1 : 1;
    if (left.computerName !== right.computerName) {
      return left.computerName.localeCompare(right.computerName);
    }
    if (left.role !== right.role) return left.role === 'manager' ? -1 : 1;
    if (left.isDefault !== right.isDefault) return left.isDefault ? -1 : 1;
    return left.displayName.localeCompare(right.displayName);
  });
}
