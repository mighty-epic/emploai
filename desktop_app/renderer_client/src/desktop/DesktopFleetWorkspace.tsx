import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, useWindowDimensions, View } from 'react-native';

import {
  loadDesktopFleetYggdrasilStatus,
  type DesktopFleetSnapshot,
  type DesktopFleetYggdrasilStatus,
} from '@/lib/desktopBridge';
import { userFacingError } from '../../lib/diagnostics';
import { DESKTOP_UI as UI } from './desktopUiTokens';
import { DesktopFleetActivityPanel } from './DesktopFleetActivityPanel';
import { DesktopFleetChildConnectionPanel } from './DesktopFleetChildConnectionPanel';
import { DesktopFleetConnectionPanel } from './DesktopFleetConnectionPanel';
import { DesktopFleetInfoButton } from './DesktopFleetInfoButton';
import { DesktopFleetMachinesPanel } from './DesktopFleetMachinesPanel';
import { DesktopFleetParentPanel } from './DesktopFleetParentPanel';
import { DesktopFleetUpstreamAccessPanel } from './DesktopFleetUpstreamAccessPanel';
import { directFleetChildren, resolveDesktopFleetHierarchyRole } from './desktopFleetHierarchy';
import { FLEET_TYPE as TYPE } from './desktopFleetUi';

type IntermediaryLayout = 'side_by_side' | 'stacked';

const LAYOUT_STORAGE_KEY = 'emploai.fleet.intermediary-layout';

function roleCopy(role: ReturnType<typeof resolveDesktopFleetHierarchyRole>) {
  if (role === 'root_manager') return ['MANAGER COMPUTER', 'Computers managed from here', 'This computer delegates directly to the computers below and receives their reports and requests.'];
  if (role === 'leaf') return ['CONNECTED COMPUTER', 'Work and requests on this computer', 'This computer receives work from one manager above it and currently manages no computers below.'];
  if (role === 'intermediary') return ['INTERMEDIARY COMPUTER', 'Managing below, reporting above', 'This computer is both a worker in the chain above and a direct manager for the computers below it.'];
  return ['PRIVATE FLEET', 'Connect your computers', 'Create a private Yggdrasil hierarchy with no hosted account or cloud control plane.'];
}

export function DesktopFleetWorkspace({
  snapshot,
  snapshotError,
  snapshotRefreshing = false,
  onSnapshotRetry,
  onChanged,
  localComputerContent,
}: {
  snapshot: DesktopFleetSnapshot | null | undefined;
  snapshotError?: string | null;
  snapshotRefreshing?: boolean;
  onSnapshotRetry?: () => void;
  onChanged?: () => void;
  localComputerContent?: ReactNode;
}) {
  const { width } = useWindowDimensions();
  const [status, setStatus] = useState<DesktopFleetYggdrasilStatus | null | undefined>(undefined);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [connectOpen, setConnectOpen] = useState(false);
  const [preferredLayout, setPreferredLayout] = useState<IntermediaryLayout>('side_by_side');

  const refreshStatus = async (quiet = false) => {
    try {
      const next = await loadDesktopFleetYggdrasilStatus();
      setStatus(next);
      setStatusError(null);
    } catch (error) {
      if (!quiet) setStatusError(userFacingError(error, 'Fleet connection status could not be loaded.'));
      setStatus((current) => current === undefined ? null : current);
    }
  };

  useEffect(() => {
    try {
      const saved = globalThis.localStorage?.getItem(LAYOUT_STORAGE_KEY);
      if (saved === 'stacked' || saved === 'side_by_side') setPreferredLayout(saved);
    } catch {
      // A blocked storage API should not prevent Fleet from rendering.
    }
    void refreshStatus();
    const timer = globalThis.setInterval(() => void refreshStatus(true), 6000);
    return () => globalThis.clearInterval(timer);
  }, []);

  const role = resolveDesktopFleetHierarchyRole(status, snapshot);
  const children = useMemo(() => directFleetChildren(snapshot), [snapshot]);
  const compactIntermediary = width < 1180;
  const effectiveLayout: IntermediaryLayout = compactIntermediary ? 'stacked' : preferredLayout;
  const [eyebrow, title, detail] = roleCopy(role);

  const changed = () => {
    void refreshStatus(true);
    onChanged?.();
  };

  const changeLayout = (layout: IntermediaryLayout) => {
    setPreferredLayout(layout);
    try {
      globalThis.localStorage?.setItem(LAYOUT_STORAGE_KEY, layout);
    } catch {
      // Persisting the preference is optional; the in-memory choice still applies.
    }
  };

  if (!snapshot) {
    return (
      <View style={styles.topologyState} accessibilityLiveRegion="polite">
        <Text style={styles.topologyEyebrow}>FLEET TOPOLOGY</Text>
        <Text style={styles.topologyTitle}>
          {snapshotError ? 'Connected computers could not be read' : 'Reading connected computers…'}
        </Text>
        <Text style={snapshotError ? styles.topologyError : styles.topologyDetail}>
          {snapshotError || 'Checking this computer’s local Fleet records and private Yggdrasil connections.'}
        </Text>
        {snapshotError ? (
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: snapshotRefreshing }}
            disabled={snapshotRefreshing}
            onPress={onSnapshotRetry}
            style={[styles.retryButton, snapshotRefreshing ? styles.disabled : null]}
          >
            <Text style={styles.retryButtonText}>{snapshotRefreshing ? 'Reconnecting…' : 'Reconnect Fleet'}</Text>
          </Pressable>
        ) : null}
      </View>
    );
  }

  if (role === 'loading') {
    return (
      <View style={styles.loading} accessibilityLiveRegion="polite">
        <Text style={styles.loadingText}>Reading this computer’s Fleet role…</Text>
      </View>
    );
  }

  if (role === 'standalone') {
    return (
      <View style={styles.workspace}>
        <View style={styles.hero}>
          <View style={styles.heroHeader}>
            <View style={styles.heroCopy}>
              <Text style={styles.eyebrow}>{eyebrow}</Text>
              <Text style={styles.title}>{title}</Text>
            </View>
            <DesktopFleetInfoButton label={title} text={detail} />
          </View>
        </View>
        <DesktopFleetMachinesPanel
          snapshot={snapshot}
          onChanged={changed}
          onConnectRequested={() => setConnectOpen(true)}
          localComputerContent={localComputerContent}
          showConnectAction={false}
        />
        <DesktopFleetConnectionPanel onFleetChanged={changed} />
        {statusError ? <Text style={styles.errorText}>{statusError}</Text> : null}
      </View>
    );
  }

  return (
    <View style={styles.workspace}>
      <View style={styles.heroRow}>
        <View style={styles.heroCopy}>
          <Text style={styles.eyebrow}>{eyebrow}</Text>
          <Text style={styles.title}>{title}</Text>
          <View style={styles.pathRow}>
            {status?.connection?.configured ? <Text style={styles.pathChip}>↑ MANAGER ABOVE</Text> : <Text style={styles.pathChipMuted}>TOP OF CHAIN</Text>}
            <Text style={styles.pathCenter}>THIS COMPUTER</Text>
            {children.length ? <Text style={styles.pathChip}>↓ {children.length} DIRECTLY BELOW</Text> : <Text style={styles.pathChipMuted}>END OF CHAIN</Text>}
          </View>
        </View>
        <View style={styles.heroActions}>
          <DesktopFleetInfoButton label={title} text={detail} />
          {role === 'leaf' || role === 'intermediary' ? (
            <Pressable accessibilityRole="button" onPress={() => setConnectOpen((current) => !current)} style={styles.addButton}>
              <Text style={styles.addButtonText}>{connectOpen ? 'Close setup' : '+ Add computer below'}</Text>
            </Pressable>
          ) : null}
        </View>
      </View>

      {role === 'intermediary' ? (
        <View style={styles.layoutBar}>
          <View style={styles.layoutCopy}>
            <Text style={styles.layoutTitle}>Intermediary layout</Text>
          </View>
          <DesktopFleetInfoButton
            label="Intermediary layout"
            text={compactIntermediary ? 'The two sides are stacked automatically at this window width.' : 'Choose whether the manager-above and computers-below views sit side by side or stack vertically.'}
          />
          <View style={styles.layoutChoices}>
            {(['side_by_side', 'stacked'] as const).map((layout) => (
              <Pressable
                key={layout}
                accessibilityRole="radio"
                accessibilityState={{ checked: preferredLayout === layout, disabled: compactIntermediary && layout === 'side_by_side' }}
                disabled={compactIntermediary && layout === 'side_by_side'}
                onPress={() => changeLayout(layout)}
                style={[styles.layoutButton, preferredLayout === layout ? styles.layoutButtonSelected : null, compactIntermediary && layout === 'side_by_side' ? styles.disabled : null]}
              ><Text style={styles.layoutButtonText}>{layout === 'side_by_side' ? 'Side by side' : 'Stacked'}</Text></Pressable>
            ))}
          </View>
        </View>
      ) : null}

      {connectOpen ? <DesktopFleetChildConnectionPanel onClose={() => setConnectOpen(false)} onChanged={changed} /> : null}

      {role === 'root_manager' ? (
        <DesktopFleetMachinesPanel snapshot={snapshot} onChanged={changed} onConnectRequested={() => setConnectOpen(true)} localComputerContent={localComputerContent} />
      ) : null}

      {role === 'leaf' ? (
        <>
          <DesktopFleetParentPanel status={status || null} />
          <DesktopFleetActivityPanel snapshot={snapshot} />
          <DesktopFleetUpstreamAccessPanel status={status || null} onChanged={changed} />
        </>
      ) : null}

      {role === 'intermediary' ? (
        <>
          <View style={[styles.intermediary, effectiveLayout === 'side_by_side' ? styles.intermediarySide : styles.intermediaryStack]}>
            <View style={styles.intermediaryPane}>
              <View style={styles.paneLabel}><Text style={styles.paneLabelText}>↑ REPORTING TO THE MANAGER ABOVE</Text></View>
              <DesktopFleetParentPanel status={status || null} />
              <DesktopFleetActivityPanel snapshot={snapshot} compact />
            </View>
            <View style={styles.intermediaryPane}>
              <View style={styles.paneLabel}><Text style={styles.paneLabelText}>↓ MANAGING COMPUTERS BELOW</Text></View>
              <DesktopFleetMachinesPanel snapshot={snapshot} onChanged={changed} onConnectRequested={() => setConnectOpen(true)} localComputerContent={localComputerContent} compact />
            </View>
          </View>
          <DesktopFleetUpstreamAccessPanel status={status || null} onChanged={changed} />
        </>
      ) : null}

      {statusError ? <Text style={styles.errorText}>{statusError}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  workspace: { gap: 18 },
  topologyState: { minHeight: 180, paddingVertical: 22, gap: 9, borderWidth: 0, backgroundColor: 'transparent', alignItems: 'flex-start', justifyContent: 'center' },
  topologyEyebrow: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: TYPE.eyebrow, fontWeight: '900', letterSpacing: 1.2 },
  topologyTitle: { color: UI.color.text, fontSize: TYPE.heroTitle, fontWeight: '900' },
  topologyDetail: { maxWidth: 680, color: UI.color.textMuted, fontSize: TYPE.body, lineHeight: TYPE.bodyLine },
  topologyError: { maxWidth: 680, color: UI.color.danger, fontSize: TYPE.body, fontWeight: '700', lineHeight: TYPE.bodyLine },
  retryButton: { minHeight: 44, marginTop: 4, paddingHorizontal: 14, borderWidth: 0, borderRadius: UI.radius.control, backgroundColor: UI.color.accentSoft, alignItems: 'center', justifyContent: 'center' },
  retryButtonText: { color: UI.color.accentStrong, fontSize: TYPE.body, fontWeight: '900' },
  loading: { minHeight: 120, padding: 18, borderWidth: 0, backgroundColor: 'transparent', alignItems: 'center', justifyContent: 'center' },
  loadingText: { color: UI.color.textMuted, fontSize: TYPE.body },
  hero: { paddingVertical: 4, borderWidth: 0, backgroundColor: 'transparent' },
  heroHeader: { position: 'relative', zIndex: 20, flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 },
  heroRow: { position: 'relative', zIndex: 20, paddingVertical: 4, borderWidth: 0, backgroundColor: 'transparent', flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-start', justifyContent: 'space-between', gap: 14 },
  heroCopy: { flex: 1, minWidth: 280 },
  heroActions: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  eyebrow: { color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: TYPE.eyebrow, fontWeight: '600', letterSpacing: 0.7 },
  title: { marginTop: 6, color: UI.color.text, fontSize: TYPE.heroTitle, fontWeight: '700' },
  pathRow: { marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 7 },
  pathChip: { paddingHorizontal: 9, paddingVertical: 5, borderWidth: 0, borderRadius: UI.radius.pill, backgroundColor: UI.color.accentSoft, color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '700' },
  pathChipMuted: { paddingHorizontal: 9, paddingVertical: 5, borderWidth: 0, borderRadius: UI.radius.pill, backgroundColor: UI.color.surfaceMuted, color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '700' },
  pathCenter: { color: UI.color.text, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  addButton: { minHeight: 44, paddingHorizontal: 14, borderWidth: 0, borderRadius: UI.radius.control, backgroundColor: UI.color.accentSoft, alignItems: 'center', justifyContent: 'center' },
  addButtonText: { color: UI.color.accentStrong, fontSize: TYPE.body, fontWeight: '900' },
  layoutBar: { position: 'relative', zIndex: 20, padding: 10, borderWidth: 0, borderRadius: UI.radius.control, backgroundColor: UI.color.surfaceMuted, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  layoutCopy: { flex: 1, minWidth: 220 },
  layoutTitle: { color: UI.color.text, fontSize: TYPE.sectionTitle, fontWeight: '900' },
  layoutChoices: { flexDirection: 'row', gap: 6 },
  layoutButton: { minHeight: 40, paddingHorizontal: 11, borderWidth: 0, borderRadius: UI.radius.control, alignItems: 'center', justifyContent: 'center' },
  layoutButtonSelected: { backgroundColor: UI.color.accentSoft },
  layoutButtonText: { color: UI.color.textMuted, fontSize: TYPE.body, fontWeight: '800' },
  disabled: { opacity: 0.4 },
  intermediary: { gap: 10, alignItems: 'flex-start' },
  intermediarySide: { flexDirection: 'row' },
  intermediaryStack: { flexDirection: 'column' },
  intermediaryPane: { flex: 1, minWidth: 0, gap: 6 },
  paneLabel: { paddingHorizontal: 9, paddingVertical: 6, borderRadius: UI.radius.pill, alignSelf: 'flex-start', backgroundColor: UI.color.accentSoft },
  paneLabelText: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900', letterSpacing: 0.6 },
  errorText: { color: UI.color.danger, fontSize: TYPE.body, fontWeight: '700' },
});
