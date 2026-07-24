import ArrowLeft from 'lucide-react-native/icons/arrow-left';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import {
  requestDesktopFleetComputerPermissions,
  setDesktopFleetManagerToolPacksOnComputer,
  type DesktopFleetConnectionPermissions,
  type DesktopFleetRemoteTarget,
  type DesktopFleetSnapshot,
} from '@/lib/desktopBridge';
import { userFacingError } from '../../lib/diagnostics';
import { DesktopFleetConnectionAccess } from './DesktopFleetConnectionAccess';
import { DesktopFleetManagerTools } from './DesktopFleetManagerTools';
import { remoteRuntimesFromFleetSnapshot } from './desktopRemoteRuntimes';
import { DESKTOP_UI as UI } from './desktopUiTokens';

const BLOCKED_PERMISSIONS: DesktopFleetConnectionPermissions['permissions'] = {
  delegate_manager: false,
  delegate_workers: false,
  create_workers: false,
  configure_manager_tools: false,
  manage_runtime: false,
  manage_updates: false,
};

function permissionForDesktop(snapshot: DesktopFleetSnapshot, desktopId: string) {
  return snapshot.connection_permissions?.find((item) => item.desktop_id === desktopId) || null;
}

function childManager(permissionState: DesktopFleetConnectionPermissions | null): DesktopFleetRemoteTarget | null {
  return (permissionState?.capabilities?.targets || []).find((target) => target.target_kind === 'manager') || null;
}

export function DesktopFleetComputerSettingsPage({
  snapshot,
  desktopId,
  onBack,
  onChanged,
}: {
  snapshot: DesktopFleetSnapshot;
  desktopId: string;
  onBack: () => void;
  onChanged?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const machine = remoteRuntimesFromFleetSnapshot(snapshot).find((item) => item.id === desktopId) || null;
  const permissionState = permissionForDesktop(snapshot, desktopId);
  const permissions = permissionState?.permissions || BLOCKED_PERMISSIONS;
  const manager = childManager(permissionState);
  const localManager = (snapshot.identities || []).find((identity) => identity.role === 'manager') || null;

  const run = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      await action();
      setMessage(success);
      onChanged?.();
      return true;
    } catch (actionError) {
      setError(userFacingError(actionError, 'The computer setting could not be changed.'));
      return false;
    } finally {
      setBusy(false);
    }
  };

  if (!machine) {
    return (
      <View style={styles.page}>
        <Pressable accessibilityRole="button" onPress={onBack} style={styles.backButton}>
          <ArrowLeft size={16} color={UI.color.accentStrong} strokeWidth={2.2} />
          <Text style={styles.backText}>Fleet</Text>
        </Pressable>
        <Text style={styles.title}>Computer unavailable</Text>
        <Text style={styles.muted}>This computer is no longer in the direct-child list.</Text>
      </View>
    );
  }

  const online = machine.status === 'connected';
  const managerName = localManager?.display_name || 'This computer’s manager';

  return (
    <View style={styles.page}>
      <View style={styles.header}>
        <View style={styles.headerCopy}>
          <Pressable accessibilityRole="button" accessibilityLabel="Back to Fleet" onPress={onBack} style={styles.backButton}>
            <ArrowLeft size={16} color={UI.color.accentStrong} strokeWidth={2.2} />
            <Text style={styles.backText}>Fleet</Text>
          </Pressable>
          <Text style={styles.eyebrow}>COMPUTER SETTINGS</Text>
          <View style={styles.titleRow}>
            <Text style={styles.title}>{machine.name}</Text>
            <Text style={[styles.status, !online ? styles.statusOffline : null]}>{online ? '● ONLINE' : '○ OFFLINE'}</Text>
          </View>
          <Text style={styles.route}>{managerName} → {machine.name}</Text>
        </View>
      </View>

      <View style={styles.settingsGrid}>
        <View style={styles.settingColumn}>
          <Text style={styles.sectionEyebrow}>ACCESS</Text>
          <Text style={styles.sectionTitle}>From this computer</Text>
          <Text style={styles.sectionDetail}>Delegation and administration rights. Increased access must be approved on {machine.name}.</Text>
          <DesktopFleetConnectionAccess
            desktopId={machine.id}
            desktopName={machine.name}
            permissions={permissions}
            pendingRequest={permissionState?.pending_request || permissionState?.pendingRequest}
            online={online}
            protocolReady={permissionState?.source === 'paired_desktop'}
            busy={busy}
            onRequest={(nextPermissions) => run(
              () => requestDesktopFleetComputerPermissions(
                machine.id,
                nextPermissions,
                `Permission change requested from ${machine.name} settings`,
              ),
              `Permission request sent to ${machine.name}.`,
            )}
          />
        </View>

        <View style={styles.settingColumn}>
          <Text style={styles.sectionEyebrow}>MANAGER</Text>
          <Text style={styles.sectionTitle}>Tools on {machine.name}</Text>
          <Text style={styles.sectionDetail}>Optional tools run there directly. Disabled execution work continues to its default worker.</Text>
          <DesktopFleetManagerTools
            desktopId={machine.id}
            desktopName={machine.name}
            manager={manager}
            allowed={Boolean(permissions.configure_manager_tools)}
            online={online}
            busy={busy}
            onSave={(enabledToolPacks) => run(
              () => setDesktopFleetManagerToolPacksOnComputer(machine.id, enabledToolPacks),
              `Manager tools updated on ${machine.name}.`,
            )}
          />
        </View>
      </View>

      {message ? <Text style={styles.success}>{message}</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  page: { paddingVertical: 6, gap: 24 },
  header: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 },
  headerCopy: { flex: 1, minWidth: 0, gap: 7 },
  backButton: { minHeight: 34, alignSelf: 'flex-start', paddingRight: 10, flexDirection: 'row', alignItems: 'center', gap: 6 },
  backText: { color: UI.color.accentStrong, fontSize: 12, fontWeight: '800' },
  eyebrow: { color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  titleRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 10 },
  title: { color: UI.color.text, fontSize: 25, fontWeight: '900' },
  route: { color: UI.color.textMuted, fontFamily: UI.type.mono, fontSize: 10 },
  status: { color: UI.color.success, fontFamily: UI.type.mono, fontSize: 9, fontWeight: '900' },
  statusOffline: { color: UI.color.danger },
  settingsGrid: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-start', gap: 28 },
  settingColumn: { flexGrow: 1, flexBasis: 340, minWidth: 290, gap: 7 },
  sectionEyebrow: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: 9, fontWeight: '900', letterSpacing: 0.9 },
  sectionTitle: { color: UI.color.text, fontSize: 17, fontWeight: '900' },
  sectionDetail: { minHeight: 34, maxWidth: 520, color: UI.color.textMuted, fontSize: 12, lineHeight: 17 },
  muted: { color: UI.color.textMuted, fontSize: 13 },
  success: { color: UI.color.success, fontSize: 12, fontWeight: '700' },
  error: { color: UI.color.danger, fontSize: 12, fontWeight: '700' },
});
