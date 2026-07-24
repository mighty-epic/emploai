import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import {
  refreshDesktopFleetManagerConnection,
  type DesktopFleetYggdrasilStatus,
} from '@/lib/desktopBridge';
import { userFacingError } from '../../lib/diagnostics';
import { DesktopFleetInfoButton } from './DesktopFleetInfoButton';
import { FLEET_TYPE as TYPE } from './desktopFleetUi';
import { DESKTOP_UI as UI } from './desktopUiTokens';

export function DesktopFleetManagerConnectionPanel({
  status,
  onRefreshed,
}: {
  status: DesktopFleetYggdrasilStatus | null | undefined;
  onRefreshed?: (status: DesktopFleetYggdrasilStatus) => void;
}) {
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const manager = status?.manager || null;
  const ready = Boolean(manager?.ready);

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const next = await refreshDesktopFleetManagerConnection();
      if (next) onRefreshed?.(next);
    } catch (refreshError) {
      setError(userFacingError(refreshError, 'This computer’s Fleet connection could not be repaired.'));
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <View style={styles.panel} accessibilityLiveRegion="polite">
      <View style={styles.header}>
        <View style={styles.copy}>
          <Text style={styles.eyebrow}>THIS COMPUTER</Text>
          <Text style={styles.title}>Fleet connection</Text>
          <Text style={styles.detail}>
            {manager?.detail || 'Checking whether paired computers can reach this manager…'}
          </Text>
        </View>
        <DesktopFleetInfoButton
          label="This computer’s Fleet connection"
          text="This is separate from pairing. Refresh checks Yggdrasil, restores the saved manager binding, verifies the restricted Windows Firewall rule, and starts the manager backend if needed. Repairing a broken binding can briefly restart the backend."
        />
      </View>

      <View style={styles.statusRow}>
        <Text style={[styles.badge, ready ? styles.badgeOnline : styles.badgeOffline]}>
          {ready ? '● ONLINE' : manager?.state === 'starting' ? '◌ STARTING' : '○ OFFLINE'}
        </Text>
        <Text style={[styles.signal, manager?.transport_ready ? styles.signalReady : null]}>Yggdrasil</Text>
        <Text style={[styles.signal, manager?.bind_ready ? styles.signalReady : null]}>Manager route</Text>
        <Text style={[styles.signal, manager?.runtime_ready ? styles.signalReady : null]}>Backend</Text>
        {manager?.address ? <Text style={styles.address}>{manager.address}</Text> : null}
      </View>

      {!manager?.persistent && ready ? (
        <Text style={styles.warning}>Refresh once to preserve this manager connection across future app starts.</Text>
      ) : null}
      <View style={styles.actionRow}>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: refreshing }}
          disabled={refreshing}
          onPress={() => void refresh()}
          style={[styles.button, refreshing ? styles.disabled : null]}
        >
          <Text style={styles.buttonText}>{refreshing ? 'Refreshing connection…' : ready ? 'Refresh connection' : 'Repair connection'}</Text>
        </Pressable>
        <Text style={styles.security}>🔒 Encrypted Yggdrasil transport · authenticated Fleet session</Text>
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { padding: 14, gap: 11, borderRadius: UI.radius.panel, backgroundColor: UI.color.surfaceMuted },
  header: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 },
  copy: { flex: 1, gap: 4 },
  eyebrow: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: TYPE.eyebrow, fontWeight: '900', letterSpacing: 0.8 },
  title: { color: UI.color.text, fontSize: TYPE.sectionTitle, fontWeight: '900' },
  detail: { maxWidth: 760, color: UI.color.textMuted, fontSize: TYPE.body, lineHeight: TYPE.bodyLine },
  statusRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 7 },
  badge: { paddingHorizontal: 9, paddingVertical: 5, borderRadius: UI.radius.pill, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  badgeOnline: { color: UI.color.success, backgroundColor: UI.color.successSoft },
  badgeOffline: { color: UI.color.danger, backgroundColor: UI.color.dangerSoft },
  signal: { paddingHorizontal: 8, paddingVertical: 5, borderRadius: UI.radius.pill, color: UI.color.textSubtle, backgroundColor: UI.color.surfaceRaised, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '800' },
  signalReady: { color: UI.color.success },
  address: { marginLeft: 'auto', color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: TYPE.micro },
  warning: { color: UI.color.warning, fontSize: TYPE.meta, fontWeight: '700' },
  actionRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 10 },
  button: { minHeight: 42, paddingHorizontal: 14, alignItems: 'center', justifyContent: 'center', borderRadius: UI.radius.control, backgroundColor: UI.color.accentSoft },
  buttonText: { color: UI.color.accentStrong, fontSize: TYPE.body, fontWeight: '900' },
  security: { color: UI.color.textMuted, fontSize: TYPE.meta, fontWeight: '700' },
  disabled: { opacity: 0.48 },
  error: { color: UI.color.danger, fontSize: TYPE.body, fontWeight: '700' },
});

