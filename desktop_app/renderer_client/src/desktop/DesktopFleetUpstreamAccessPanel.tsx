import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import {
  decideDesktopFleetPermissionRequest,
  setDesktopFleetConnectionPermissions,
  type DesktopFleetYggdrasilStatus,
} from '@/lib/desktopBridge';
import { userFacingError } from '../../lib/diagnostics';
import { DesktopFleetInfoButton } from './DesktopFleetInfoButton';
import { FLEET_TYPE as TYPE } from './desktopFleetUi';
import { DESKTOP_UI as UI } from './desktopUiTokens';

type PermissionKey = 'delegate_manager' | 'delegate_workers' | 'create_workers' | 'configure_manager_tools' | 'manage_runtime' | 'manage_updates';

const permissionRows: Array<[PermissionKey, string, string]> = [
  ['delegate_manager', 'Main identity', 'Allow the manager above to delegate to the main identity on this computer.'],
  ['delegate_workers', 'Existing agents', 'Expose and allow delegation to existing local agents.'],
  ['create_workers', 'Create agents', 'Allow the manager above to create a new local agent only when explicitly requested.'],
  ['configure_manager_tools', 'Configure manager tools', 'Allow the manager above to change this manager’s optional execution packs. Manager Core cannot be removed.'],
  ['manage_runtime', 'Start EmploAI', 'Allow the manager above to start this backend or desktop window while the persistent host remains connected.'],
  ['manage_updates', 'Update EmploAI', 'Allow the manager above to install a confirmed fast-forward update and restart this computer’s EmploAI app and backend.'],
];

export function DesktopFleetUpstreamAccessPanel({
  status,
  onChanged,
}: {
  status: DesktopFleetYggdrasilStatus | null;
  onChanged?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const permissions = status?.connection?.permissions || {
    delegate_manager: true,
    delegate_workers: true,
    create_workers: false,
    configure_manager_tools: false,
    manage_runtime: true,
    manage_updates: true,
  };
  const pendingRequest = status?.connection?.pendingRequest as Record<string, any> | null | undefined;

  const updatePermission = async (key: PermissionKey) => {
    setBusy(true);
    setError(null);
    try {
      await setDesktopFleetConnectionPermissions({ ...permissions, [key]: !permissions[key] });
      setMessage('Access updated. The manager above will receive the new capability directory automatically.');
      onChanged?.();
    } catch (updateError) {
      setError(userFacingError(updateError, 'Connection access could not be updated.'));
    } finally {
      setBusy(false);
    }
  };

  const decide = async (approve: boolean) => {
    const requestId = String(pendingRequest?.requestId || '');
    if (!requestId) return;
    setBusy(true);
    setError(null);
    try {
      await decideDesktopFleetPermissionRequest(requestId, approve);
      setMessage(approve ? 'Permission request approved.' : 'Permission request denied.');
      onChanged?.();
    } catch (decisionError) {
      setError(userFacingError(decisionError, 'The permission request could not be decided.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.panel}>
      <View style={styles.header}>
        <View style={styles.headerCopy}>
          <Text style={styles.eyebrow}>MANAGER ABOVE</Text>
          <Text style={styles.title}>Access to this computer</Text>
        </View>
        <View style={styles.headerActions}>
          <DesktopFleetInfoButton
            label="Access to this computer"
            text="This computer owns these permissions. Turning one off removes that destination or action from the manager-above interface."
          />
          <View style={styles.connectionBadge}>
            <Text style={styles.connectionBadgeText}>{status?.connection?.relayState === 'running' ? '● CONNECTED' : '○ RECONNECTING'}</Text>
          </View>
        </View>
      </View>

      <View style={styles.permissionGrid}>
        {permissionRows.map(([key, label, detail]) => {
          const enabled = Boolean(permissions[key]);
          return (
            <Pressable
              key={key}
              accessibilityRole="switch"
              accessibilityHint={detail}
              accessibilityState={{ checked: enabled, disabled: busy }}
              disabled={busy}
              onPress={() => void updatePermission(key)}
              style={[styles.permission, enabled ? styles.permissionEnabled : null]}
            >
              <View style={styles.permissionCopy}>
                <Text style={styles.permissionLabel}>{label}</Text>
              </View>
              <Text style={[styles.permissionValue, enabled ? styles.permissionValueEnabled : null]}>{enabled ? 'ALLOWED' : 'BLOCKED'}</Text>
            </Pressable>
          );
        })}
      </View>

      {pendingRequest ? (
        <View style={styles.pending} accessibilityLiveRegion="polite">
          <View style={styles.pendingCopy}>
            <Text style={styles.pendingTitle}>The manager above requested an access change</Text>
            <Text style={styles.pendingDetail}>{String(pendingRequest.reason || 'Review the requested permissions before deciding.')}</Text>
          </View>
          <View style={styles.actions}>
            <Pressable accessibilityRole="button" disabled={busy} onPress={() => void decide(false)} style={styles.denyButton}>
              <Text style={styles.denyButtonText}>Deny</Text>
            </Pressable>
            <Pressable accessibilityRole="button" disabled={busy} onPress={() => void decide(true)} style={styles.approveButton}>
              <Text style={styles.approveButtonText}>Approve</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      {error || message ? (
        <View style={[styles.notice, error ? styles.noticeError : null]} accessibilityLiveRegion="polite">
          <Text style={error ? styles.noticeErrorText : styles.noticeText}>{error || message}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { paddingVertical: 14, gap: 12, borderWidth: 0, borderRadius: 0, backgroundColor: 'transparent' },
  header: { position: 'relative', zIndex: 20, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 },
  headerCopy: { flex: 1, minWidth: 240 },
  headerActions: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  eyebrow: { color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: TYPE.eyebrow, fontWeight: '900', letterSpacing: 0.9 },
  title: { marginTop: 5, color: UI.color.text, fontSize: TYPE.panelTitle, fontWeight: '900' },
  connectionBadge: { paddingHorizontal: 8, paddingVertical: 5, borderWidth: 0, borderRadius: UI.radius.pill, backgroundColor: UI.color.successSoft },
  connectionBadgeText: { color: UI.color.success, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  permissionGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  permission: { flexGrow: 1, flexBasis: 230, minWidth: 210, minHeight: 62, padding: 12, borderWidth: 0, borderRadius: UI.radius.control, backgroundColor: UI.color.surfaceMuted, flexDirection: 'row', alignItems: 'center', gap: 10 },
  permissionEnabled: { backgroundColor: UI.color.accentSoft },
  permissionCopy: { flex: 1, gap: 3 },
  permissionLabel: { color: UI.color.text, fontSize: TYPE.control, fontWeight: '900' },
  permissionValue: { color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  permissionValueEnabled: { color: UI.color.success },
  pending: { padding: 10, borderWidth: 0, borderRadius: UI.radius.control, backgroundColor: UI.color.warningSoft, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 10 },
  pendingCopy: { flex: 1, minWidth: 220 },
  pendingTitle: { color: UI.color.warning, fontSize: TYPE.control, fontWeight: '900' },
  pendingDetail: { marginTop: 4, color: UI.color.textMuted, fontSize: TYPE.body, lineHeight: TYPE.bodyLine },
  actions: { flexDirection: 'row', gap: 6 },
  denyButton: { minHeight: 40, paddingHorizontal: 11, borderWidth: 0, borderRadius: UI.radius.control, backgroundColor: UI.color.dangerSoft, alignItems: 'center', justifyContent: 'center' },
  denyButtonText: { color: UI.color.danger, fontSize: TYPE.body, fontWeight: '900' },
  approveButton: { minHeight: 40, paddingHorizontal: 11, borderWidth: 0, borderRadius: UI.radius.control, backgroundColor: UI.color.successSoft, alignItems: 'center', justifyContent: 'center' },
  approveButtonText: { color: UI.color.success, fontSize: TYPE.body, fontWeight: '900' },
  notice: { padding: 9, borderWidth: 0, borderRadius: UI.radius.control, backgroundColor: UI.color.accentSoft },
  noticeError: { borderColor: UI.color.danger, backgroundColor: UI.color.dangerSoft },
  noticeText: { color: UI.color.textMuted, fontSize: TYPE.body },
  noticeErrorText: { color: UI.color.danger, fontSize: TYPE.body, fontWeight: '700' },
});
