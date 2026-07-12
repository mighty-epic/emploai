import { StyleSheet, Text, View } from 'react-native';

import type { DesktopFleetSnapshot } from '@/lib/desktopBridge';
import { remoteRuntimesFromFleetSnapshot } from './desktopRemoteRuntimes';
import { DESKTOP_UI as UI } from './desktopUiTokens';

export function DesktopFleetMachinesPanel({ snapshot }: { snapshot: DesktopFleetSnapshot | null | undefined }) {
  const machines = remoteRuntimesFromFleetSnapshot(snapshot);

  return (
    <View style={styles.section}>
      <View style={styles.headingRow}>
        <View>
          <Text style={styles.eyebrow}>FLEET TOPOLOGY</Text>
          <Text style={styles.title}>Computers in this Fleet</Text>
        </View>
        <Text style={styles.count}>{machines.length}</Text>
      </View>
      {machines.length ? (
        <View style={styles.grid}>
          {machines.map((machine) => {
            const online = machine.status === 'connected';
            const workers = machine.workers || [];
            return (
              <View key={machine.id} style={styles.machine}>
                <View style={styles.machineHeader}>
                  <View style={styles.machineIdentity}>
                    <Text style={styles.machineName} numberOfLines={1}>{machine.name}</Text>
                    <Text style={styles.machineMeta} numberOfLines={1}>{machine.hostLabel}</Text>
                  </View>
                  <View style={[styles.badge, online ? styles.badgeOnline : styles.badgeOffline]}>
                    <Text style={styles.badgeText}>{online ? '● CONNECTED' : '○ OFFLINE'}</Text>
                  </View>
                </View>
                <Text style={styles.counts}>{machine.detail}</Text>
                {workers.length ? (
                  <View style={styles.workerList}>
                    {workers.slice(0, 5).map((worker) => (
                      <View key={worker.id} style={styles.workerRow}>
                        <Text style={styles.workerName} numberOfLines={1}>{worker.name}</Text>
                        <Text style={styles.workerStatus}>{worker.activeTaskId ? 'task active' : worker.status}</Text>
                      </View>
                    ))}
                    {workers.length > 5 ? <Text style={styles.more}>+{workers.length - 5} more workers</Text> : null}
                  </View>
                ) : <Text style={styles.empty}>Manager desktop · no additional worker identities</Text>}
              </View>
            );
          })}
        </View>
      ) : (
        <View style={styles.emptyState} accessibilityLiveRegion="polite">
          <Text style={styles.emptyTitle}>No Fleet computers have reported in yet</Text>
          <Text style={styles.empty}>Prepare Yggdrasil above, then connect another desktop or create a local worker.</Text>
        </View>
      )}
      <Text style={styles.hint}>Use the worker cards below for tasks, reports, queue policy, stop/reset actions, and manual view-only previews.</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  section: { padding: 16, gap: 12, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.large, backgroundColor: UI.color.surface },
  headingRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  eyebrow: { color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  title: { marginTop: 4, color: UI.color.text, fontSize: 14, fontWeight: '800' },
  count: { minWidth: 28, color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: 16, fontWeight: '800', textAlign: 'right' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  machine: { flexGrow: 1, flexBasis: 260, minWidth: 240, maxWidth: 440, padding: 12, gap: 9, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.panel, backgroundColor: UI.color.surfaceMuted },
  machineHeader: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 },
  machineIdentity: { flex: 1, minWidth: 0 },
  machineName: { color: UI.color.text, fontSize: 12, fontWeight: '800' },
  machineMeta: { marginTop: 3, color: UI.color.textSubtle, fontSize: 9 },
  badge: { paddingHorizontal: 8, paddingVertical: 5, borderRadius: UI.radius.pill, borderWidth: 1 },
  badgeOnline: { borderColor: UI.color.accentBorder, backgroundColor: UI.color.successSoft },
  badgeOffline: { borderColor: UI.color.borderStrong, backgroundColor: UI.color.surface },
  badgeText: { color: UI.color.textMuted, fontFamily: UI.type.mono, fontSize: 8, fontWeight: '800' },
  counts: { color: UI.color.textMuted, fontSize: 10 },
  workerList: { borderTopWidth: 1, borderColor: UI.color.border },
  workerRow: { minHeight: 30, paddingVertical: 6, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, borderBottomWidth: 1, borderColor: UI.color.border },
  workerName: { flex: 1, color: UI.color.textMuted, fontSize: 10, fontWeight: '700' },
  workerStatus: { color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: 8 },
  more: { paddingTop: 7, color: UI.color.textSubtle, fontSize: 9 },
  emptyState: { padding: 13, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.panel, backgroundColor: UI.color.surfaceMuted },
  emptyTitle: { color: UI.color.textMuted, fontSize: 11, fontWeight: '800' },
  empty: { marginTop: 3, color: UI.color.textSubtle, fontSize: 9, lineHeight: 14 },
  hint: { color: UI.color.textSubtle, fontSize: 9, lineHeight: 14 },
});
