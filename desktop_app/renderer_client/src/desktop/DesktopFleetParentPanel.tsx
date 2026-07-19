import { StyleSheet, Text, View } from 'react-native';

import type { DesktopFleetYggdrasilStatus } from '@/lib/desktopBridge';
import { DesktopFleetInfoButton } from './DesktopFleetInfoButton';
import { FLEET_TYPE as TYPE } from './desktopFleetUi';
import { DESKTOP_UI as UI } from './desktopUiTokens';

type ParentState = 'connected' | 'reconnecting' | 'offline';

function parentState(status: DesktopFleetYggdrasilStatus | null): ParentState {
  if (!status?.running) return 'offline';
  if (status.connection?.relayState === 'running') return 'connected';
  return 'reconnecting';
}

export function DesktopFleetParentPanel({ status }: { status: DesktopFleetYggdrasilStatus | null }) {
  const state = parentState(status);
  const stateLabel = state === 'connected' ? '● CONNECTED' : state === 'reconnecting' ? '◐ RECONNECTING' : '○ OFFLINE';
  const hostRegistered = Boolean(status?.connection?.hostRegistered);

  return (
    <View style={styles.section} accessibilityLiveRegion="polite">
      <View style={styles.headingRow}>
        <View style={styles.headingCopy}>
          <Text style={styles.eyebrow}>COMPUTER ABOVE</Text>
          <Text style={styles.title}>Your direct manager</Text>
        </View>
        <View style={styles.headingActions}>
          <DesktopFleetInfoButton
            label="Direct manager connection"
            text="This is the only computer directly above this one. It can send delegated work here, while reports and requests travel back through the same private Yggdrasil connection."
          />
          <Text style={styles.count}>1</Text>
        </View>
      </View>

      <View style={[styles.parentCard, state === 'connected' ? styles.parentCardConnected : null]}>
        <View style={styles.parentCopy}>
          <Text style={styles.parentName}>Manager computer</Text>
          <Text style={styles.parentMeta}>Direct parent · private Yggdrasil link</Text>
          <Text style={hostRegistered ? styles.hostReady : styles.hostWarning}>
            {hostRegistered ? '● Background host starts with Windows' : '◐ Background startup needs repair'}
          </Text>
        </View>
        <View style={[styles.statusBadge, state === 'connected' ? styles.statusConnected : state === 'reconnecting' ? styles.statusReconnecting : styles.statusOffline]}>
          <Text style={styles.statusText}>{stateLabel}</Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  section: { paddingVertical: 16, gap: 14, borderWidth: 0, borderRadius: 0, backgroundColor: 'transparent' },
  headingRow: { position: 'relative', zIndex: 20, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  headingCopy: { flex: 1, minWidth: 220 },
  headingActions: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  eyebrow: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: TYPE.eyebrow, fontWeight: '900', letterSpacing: 1.1 },
  title: { marginTop: 5, color: UI.color.text, fontSize: TYPE.sectionTitle, fontWeight: '900' },
  count: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: TYPE.sectionTitle, fontWeight: '900' },
  parentCard: { minHeight: 112, padding: 16, borderWidth: 0, borderRadius: UI.radius.large, backgroundColor: UI.color.surfaceMuted, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 14 },
  parentCardConnected: { backgroundColor: UI.color.accentSoft },
  parentCopy: { flex: 1, minWidth: 220, gap: 5 },
  parentName: { color: UI.color.text, fontSize: TYPE.sectionTitle, fontWeight: '900' },
  parentMeta: { color: UI.color.textMuted, fontSize: TYPE.body, lineHeight: TYPE.bodyLine },
  hostReady: { color: UI.color.success, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  hostWarning: { color: UI.color.warning, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  statusBadge: { minHeight: 32, paddingHorizontal: 11, borderWidth: 0, borderRadius: UI.radius.pill, alignItems: 'center', justifyContent: 'center' },
  statusConnected: { borderColor: UI.color.accentBorder, backgroundColor: UI.color.accentSoft },
  statusReconnecting: { borderColor: UI.color.warning, backgroundColor: UI.color.warningSoft },
  statusOffline: { borderColor: UI.color.borderStrong, backgroundColor: UI.color.surface },
  statusText: { color: UI.color.text, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900', letterSpacing: 0.5 },
});
