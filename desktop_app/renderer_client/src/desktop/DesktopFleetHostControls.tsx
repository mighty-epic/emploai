import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import {
  getDesktopFleetComputerHostStatus,
  startDesktopFleetComputerDesktop,
  startDesktopFleetComputerRuntime,
  type DesktopFleetHostStatus,
} from '@/lib/desktopBridge';
import { userFacingError } from '../../lib/diagnostics';
import { DesktopFleetInfoButton } from './DesktopFleetInfoButton';
import { FLEET_TYPE as TYPE } from './desktopFleetUi';
import { DESKTOP_UI as UI } from './desktopUiTokens';

export function DesktopFleetHostControls({
  desktopId,
  desktopName,
  online,
  allowed,
  supported,
}: {
  desktopId: string;
  desktopName: string;
  online: boolean;
  allowed: boolean;
  supported: boolean;
}) {
  const [status, setStatus] = useState<DesktopFleetHostStatus | null>(null);
  const [busy, setBusy] = useState<'status' | 'runtime' | 'desktop' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = async () => {
    if (!online || !supported) return;
    setBusy('status');
    setError(null);
    try {
      setStatus(await getDesktopFleetComputerHostStatus(desktopId));
    } catch (statusError) {
      setError(userFacingError(statusError, `Could not read ${desktopName} host status.`));
    } finally {
      setBusy(null);
    }
  };

  useEffect(() => {
    setStatus(null);
    setError(null);
    void loadStatus();
  }, [desktopId, online, supported]);

  const run = async (
    action: 'runtime' | 'desktop',
    operation: () => Promise<DesktopFleetHostStatus | null>,
  ) => {
    setBusy(action);
    setError(null);
    try {
      const next = await operation();
      if (next) setStatus(next);
    } catch (actionError) {
      setError(userFacingError(actionError, `Could not start EmploAI on ${desktopName}.`));
    } finally {
      setBusy(null);
    }
  };

  const runtimeReady = Boolean(status?.runtime.ready);
  const desktopRunning = Boolean(status?.desktop.running);
  const disabled = Boolean(busy) || !online || !allowed || !supported;

  return (
    <View style={styles.section} accessibilityLiveRegion="polite">
      <View style={styles.headingRow}>
        <View style={styles.headingCopy}>
          <Text style={styles.eyebrow}>ALWAYS-ON HOST</Text>
          <Text style={styles.title}>Recover EmploAI on {desktopName}</Text>
        </View>
        <DesktopFleetInfoButton
          label="Persistent Fleet host"
          text="This small authenticated process stays connected over Yggdrasil when the EmploAI window and backend are closed. It can start them again, but it cannot provide mouse or keyboard control."
        />
      </View>

      {!supported ? (
        <Text style={styles.warning}>Update EmploAI on this computer to enable independent recovery controls.</Text>
      ) : (
        <View style={styles.statusRow}>
          <Text style={[styles.status, online ? styles.statusReady : styles.statusMuted]}>{online ? '● HOST CONNECTED' : '○ HOST OFFLINE'}</Text>
          <Text style={[styles.status, runtimeReady ? styles.statusReady : styles.statusMuted]}>{runtimeReady ? '● BACKEND READY' : '○ BACKEND STOPPED'}</Text>
          <Text style={[styles.status, desktopRunning ? styles.statusReady : styles.statusMuted]}>{desktopRunning ? '● APP OPEN' : '○ APP CLOSED'}</Text>
          {status?.app_version ? <Text style={styles.version}>v{status.app_version}</Text> : null}
        </View>
      )}

      <View style={styles.actions}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Refresh ${desktopName} host status`}
          disabled={Boolean(busy) || !online || !supported}
          onPress={() => void loadStatus()}
          style={[styles.secondaryButton, (Boolean(busy) || !online || !supported) ? styles.disabled : null]}
        ><Text style={styles.secondaryText}>{busy === 'status' ? 'Checking…' : 'Refresh status'}</Text></Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Start ${desktopName} backend`}
          disabled={disabled || runtimeReady}
          onPress={() => void run('runtime', () => startDesktopFleetComputerRuntime(desktopId))}
          style={[styles.secondaryButton, (disabled || runtimeReady) ? styles.disabled : null]}
        ><Text style={styles.secondaryText}>{busy === 'runtime' ? 'Starting backend…' : runtimeReady ? 'Backend ready' : 'Start backend'}</Text></Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Open EmploAI on ${desktopName}`}
          disabled={disabled || desktopRunning}
          onPress={() => void run('desktop', () => startDesktopFleetComputerDesktop(desktopId))}
          style={[styles.primaryButton, (disabled || desktopRunning) ? styles.disabled : null]}
        ><Text style={styles.primaryText}>{busy === 'desktop' ? 'Opening EmploAI…' : desktopRunning ? 'EmploAI is open' : 'Open EmploAI'}</Text></Pressable>
      </View>
      {!allowed && supported ? <Text style={styles.warning}>That computer has not allowed its manager to start EmploAI.</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    padding: 14,
    gap: 12,
    borderWidth: 1,
    borderColor: UI.color.accentBorder,
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.canvas,
  },
  headingRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 },
  headingCopy: { flex: 1, gap: 4 },
  eyebrow: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: TYPE.eyebrow, fontWeight: '900', letterSpacing: 0.8 },
  title: { color: UI.color.text, fontSize: TYPE.sectionTitle, fontWeight: '900' },
  statusRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 },
  status: { fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  statusReady: { color: UI.color.success },
  statusMuted: { color: UI.color.textSubtle },
  version: { marginLeft: 'auto', color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: TYPE.micro },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  primaryButton: { minHeight: 44, paddingHorizontal: 16, alignItems: 'center', justifyContent: 'center', borderRadius: UI.radius.control, backgroundColor: UI.color.accentStrong },
  primaryText: { color: UI.color.accentInk, fontSize: TYPE.body, fontWeight: '900' },
  secondaryButton: { minHeight: 44, paddingHorizontal: 14, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: UI.color.borderStrong, borderRadius: UI.radius.control, backgroundColor: UI.color.surface },
  secondaryText: { color: UI.color.text, fontSize: TYPE.body, fontWeight: '800' },
  disabled: { opacity: 0.42 },
  warning: { color: UI.color.warning, fontSize: TYPE.body, lineHeight: TYPE.bodyLine, fontWeight: '700' },
  error: { color: UI.color.danger, fontSize: TYPE.body, lineHeight: TYPE.bodyLine, fontWeight: '700' },
});
