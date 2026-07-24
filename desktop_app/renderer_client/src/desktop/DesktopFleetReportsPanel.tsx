import { useState } from 'react';
import ChevronDown from 'lucide-react-native/icons/chevron-down';
import ChevronUp from 'lucide-react-native/icons/chevron-up';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { DesktopFleetDelegation } from '@/lib/desktopBridge';
import { fleetReportSummary } from './desktopFleetWorkerState';
import { DESKTOP_UI as UI } from './desktopUiTokens';

const DEFAULT_VISIBLE = 3;

export function DesktopFleetReportsPanel({ delegations }: { delegations: DesktopFleetDelegation[] }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? delegations : delegations.slice(0, DEFAULT_VISIBLE);
  const hiddenCount = Math.max(0, delegations.length - DEFAULT_VISIBLE);

  return (
    <View style={styles.section}>
      <View style={styles.header}>
        <Text style={styles.title}>Recent reports</Text>
        <Text style={styles.count}>{delegations.length}</Text>
      </View>
      {visible.length ? (
        <View style={styles.list}>
          {visible.map((delegation) => (
            <View key={delegation.delegation_id} style={styles.row}>
              <View style={styles.copy}>
                <Text style={styles.target}>{String((delegation.report || {}).target_label || delegation.target_selector || 'Main identity')}</Text>
                <Text style={styles.summary} numberOfLines={2}>
                  {fleetReportSummary({
                    summary: (delegation.report || {}).summary || delegation.prompt,
                    provider_failure: (delegation.report || {}).provider_failure,
                  })}
                </Text>
              </View>
              <Text style={styles.status}>{delegation.status.toUpperCase()}</Text>
            </View>
          ))}
        </View>
      ) : <Text style={styles.empty}>No reports yet.</Text>}
      {hiddenCount ? (
        <Pressable accessibilityRole="button" onPress={() => setExpanded((current) => !current)} style={styles.moreButton}>
          <Text style={styles.moreText}>{expanded ? 'Show less' : `Show ${hiddenCount} more`}</Text>
          {expanded
            ? <ChevronUp size={14} color={UI.color.accentStrong} strokeWidth={2} />
            : <ChevronDown size={14} color={UI.color.accentStrong} strokeWidth={2} />}
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { paddingTop: 6, gap: 8 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { color: UI.color.text, fontSize: 15, fontWeight: '900' },
  count: { color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: 10, fontWeight: '800' },
  list: { gap: 5 },
  row: { minHeight: 52, paddingHorizontal: 12, paddingVertical: 9, borderRadius: UI.radius.control, backgroundColor: UI.color.surfaceMuted, flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  copy: { flex: 1, minWidth: 0, gap: 2 },
  target: { color: UI.color.text, fontSize: 12, fontWeight: '800' },
  summary: { color: UI.color.textMuted, fontSize: 11, lineHeight: 16 },
  status: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: 9, fontWeight: '900' },
  empty: { color: UI.color.textSubtle, fontSize: 12 },
  moreButton: { minHeight: 34, alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 5 },
  moreText: { color: UI.color.accentStrong, fontSize: 11, fontWeight: '800' },
});
