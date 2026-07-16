import { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  createDesktopFleetWorkerOnComputer,
  delegateDesktopFleetComputer,
  requestDesktopFleetComputerPermissions,
  type DesktopFleetConnectionPermissions,
  type DesktopFleetSnapshot,
} from '@/lib/desktopBridge';
import { userFacingError } from '../../lib/diagnostics';
import { remoteRuntimesFromFleetSnapshot } from './desktopRemoteRuntimes';
import { DESKTOP_UI as UI } from './desktopUiTokens';

type PermissionKey = 'delegate_manager' | 'delegate_workers' | 'create_workers';

const permissionRows: Array<[PermissionKey, string]> = [
  ['delegate_manager', 'Manager agent'],
  ['delegate_workers', 'Existing workers'],
  ['create_workers', 'Create workers'],
];

function permissionForDesktop(snapshot: DesktopFleetSnapshot | null | undefined, desktopId: string) {
  return snapshot?.connection_permissions?.find((item) => item.desktop_id === desktopId) || null;
}

export function DesktopFleetMachinesPanel({
  snapshot,
  onChanged,
}: {
  snapshot: DesktopFleetSnapshot | null | undefined;
  onChanged?: () => void;
}) {
  const machines = remoteRuntimesFromFleetSnapshot(snapshot);
  const managerDesktopId = String((snapshot?.manager as any)?.desktop_id || '');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [targetKinds, setTargetKinds] = useState<Record<string, 'manager' | 'worker'>>({});
  const [selectors, setSelectors] = useState<Record<string, string>>({});
  const [prompts, setPrompts] = useState<Record<string, string>>({});
  const [workerNames, setWorkerNames] = useState<Record<string, string>>({});
  const [permissionDrafts, setPermissionDrafts] = useState<Record<string, Record<PermissionKey, boolean>>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [messageById, setMessageById] = useState<Record<string, string>>({});
  const [errorById, setErrorById] = useState<Record<string, string>>({});

  const delegationsByDesktop = useMemo(() => {
    const grouped = new Map<string, NonNullable<DesktopFleetSnapshot['delegations']>>();
    for (const delegation of snapshot?.delegations || []) {
      const items = grouped.get(delegation.desktop_id) || [];
      items.push(delegation);
      grouped.set(delegation.desktop_id, items);
    }
    return grouped;
  }, [snapshot?.delegations]);

  const run = async (desktopId: string, action: () => Promise<unknown>, success: string) => {
    setBusyId(desktopId);
    setErrorById((current) => ({ ...current, [desktopId]: '' }));
    try {
      await action();
      setMessageById((current) => ({ ...current, [desktopId]: success }));
      onChanged?.();
    } catch (error) {
      setErrorById((current) => ({ ...current, [desktopId]: userFacingError(error, 'The paired computer could not complete that action.') }));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <View style={styles.section}>
      <View style={styles.headingRow}>
        <View>
          <Text style={styles.eyebrow}>FLEET TOPOLOGY</Text>
          <Text style={styles.title}>Computers in this Fleet</Text>
          <Text style={styles.headingDetail}>Connections carry task messages out and reports or permission requests back. Local identities and data stay local.</Text>
        </View>
        <Text style={styles.count}>{machines.length}</Text>
      </View>

      {machines.length ? (
        <View style={styles.grid}>
          {machines.map((machine) => {
            const online = machine.status === 'connected';
            const local = machine.id === managerDesktopId;
            const expanded = expandedId === machine.id;
            const permissionState = permissionForDesktop(snapshot, machine.id);
            const protocolReady = local || permissionState?.source === 'paired_desktop';
            const permissions = protocolReady && permissionState?.permissions ? permissionState.permissions : {
              delegate_manager: false,
              delegate_workers: false,
              create_workers: false,
            };
            const draft = permissionDrafts[machine.id] || permissions;
            const targetKind = targetKinds[machine.id] || 'manager';
            const recentDelegations = (delegationsByDesktop.get(machine.id) || []).slice(0, 3);
            const busy = busyId === machine.id;
            const delegationDisabled = busy || !online || !protocolReady
              || !String(prompts[machine.id] || '').trim()
              || (targetKind === 'worker' && !String(selectors[machine.id] || '').trim());
            const workerCreateDisabled = busy || !online || !protocolReady
              || !permissions.create_workers
              || !String(workerNames[machine.id] || '').trim();
            const permissionRequestDisabled = busy || !online || !protocolReady;

            return (
              <View key={machine.id} style={[styles.machine, expanded ? styles.machineExpanded : null]}>
                <View style={styles.machineHeader}>
                  <View style={styles.machineIdentity}>
                    <Text style={styles.machineName} numberOfLines={1}>{machine.name}</Text>
                    <Text style={styles.machineMeta} numberOfLines={1}>{local ? 'This manager computer' : machine.hostLabel}</Text>
                  </View>
                  <View style={[styles.badge, online ? styles.badgeOnline : styles.badgeOffline]}>
                    <Text style={styles.badgeText}>{online ? '● CONNECTED' : '○ OFFLINE'}</Text>
                  </View>
                </View>

                <Text style={styles.counts}>{local ? `${machine.workerCount} local worker ${machine.workerCount === 1 ? 'identity' : 'identities'}` : 'No remote identities are copied into this computer'}</Text>

                {local ? (
                  <Text style={styles.empty}>Create connection codes above. Every additional computer pairs directly back to this manager.</Text>
                ) : (
                  <>
                    <View style={styles.permissionStrip}>
                      {!protocolReady ? (
                        <View style={[styles.permissionBadge, styles.permissionBadgeWarning]}>
                          <Text style={styles.permissionBadgeText}>! UPDATE REQUIRED</Text>
                        </View>
                      ) : null}
                      {permissionRows.map(([key, label]) => (
                        <View key={key} style={[styles.permissionBadge, permissions[key] ? styles.permissionBadgeOn : null]}>
                          <Text style={styles.permissionBadgeText}>{permissions[key] ? '✓' : '—'} {label}</Text>
                        </View>
                      ))}
                    </View>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityState={{ expanded }}
                      onPress={() => setExpandedId(expanded ? null : machine.id)}
                      style={styles.openButton}
                    >
                      <Text style={styles.openButtonText}>{expanded ? 'Close controls' : protocolReady ? 'Delegate or change access' : 'Review connection update'}</Text>
                    </Pressable>
                  </>
                )}

                {expanded && !local ? (
                  <View style={styles.controls}>
                    {!protocolReady ? (
                      <View accessibilityLiveRegion="polite" style={[styles.notice, styles.noticeWarning]}>
                        <Text style={styles.noticeWarningText}>This computer is online but has not completed the current Fleet permission handshake. Update and restart EmploAI there; controls will unlock automatically without reconnecting Yggdrasil.</Text>
                      </View>
                    ) : null}
                    <View style={styles.controlSection}>
                      <Text style={styles.controlEyebrow}>SEND A DELEGATION</Text>
                      <Text style={styles.controlTitle}>Choose the agent on {machine.name}</Text>
                      <View style={styles.segmented}>
                        {(['manager', 'worker'] as const).map((kind) => {
                          const selected = targetKind === kind;
                          const allowed = permissions[kind === 'manager' ? 'delegate_manager' : 'delegate_workers'];
                          return (
                            <Pressable
                              key={kind}
                              accessibilityRole="button"
                              accessibilityState={{ disabled: !allowed, selected }}
                              disabled={!allowed}
                              onPress={() => setTargetKinds((current) => ({ ...current, [machine.id]: kind }))}
                              style={[styles.segment, selected ? styles.segmentSelected : null, !allowed ? styles.disabled : null]}
                            >
                              <Text style={[styles.segmentText, selected ? styles.segmentTextSelected : null]}>{kind === 'manager' ? 'Manager agent' : 'Existing worker'}</Text>
                            </Pressable>
                          );
                        })}
                      </View>
                      {targetKind === 'worker' ? (
                        <>
                          <Text style={styles.inputLabel}>Worker name on the other computer</Text>
                          <TextInput
                            accessibilityLabel="Worker name on the paired computer"
                            value={selectors[machine.id] || ''}
                            onChangeText={(value) => setSelectors((current) => ({ ...current, [machine.id]: value }))}
                            placeholder="Example: Research worker"
                            placeholderTextColor={UI.color.textSubtle}
                            style={styles.input}
                          />
                        </>
                      ) : null}
                      <Text style={styles.inputLabel}>Task message</Text>
                      <TextInput
                        accessibilityLabel={`Delegation message for ${machine.name}`}
                        multiline
                        value={prompts[machine.id] || ''}
                        onChangeText={(value) => setPrompts((current) => ({ ...current, [machine.id]: value }))}
                        placeholder="Describe the outcome, constraints, and what the report should include."
                        placeholderTextColor={UI.color.textSubtle}
                        style={[styles.input, styles.promptInput]}
                      />
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel={`Send delegation to ${machine.name}`}
                        accessibilityState={{ disabled: delegationDisabled }}
                        disabled={delegationDisabled}
                        onPress={() => void run(
                          machine.id,
                          () => delegateDesktopFleetComputer(machine.id, prompts[machine.id], targetKind, selectors[machine.id]),
                          `Delegation sent to ${machine.name}.`,
                        )}
                        style={[styles.primaryButton, delegationDisabled ? styles.disabled : null]}
                      >
                        <Text style={styles.primaryButtonText}>{busy ? 'Sending…' : 'Send delegation'}</Text>
                      </Pressable>
                    </View>

                    <View style={styles.controlSection}>
                      <Text style={styles.controlEyebrow}>REMOTE-LOCAL SETUP</Text>
                      <Text style={styles.controlTitle}>Create a worker on {machine.name}</Text>
                      <Text style={styles.empty}>The worker is created and stored there only. Enter that name when delegating; no identity is cloned here.</Text>
                      <TextInput
                        accessibilityLabel={`New worker name on ${machine.name}`}
                        value={workerNames[machine.id] || ''}
                        onChangeText={(value) => setWorkerNames((current) => ({ ...current, [machine.id]: value }))}
                        placeholder="New local worker name"
                        placeholderTextColor={UI.color.textSubtle}
                        style={styles.input}
                      />
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel={`Create worker on ${machine.name}`}
                        accessibilityState={{ disabled: workerCreateDisabled }}
                        disabled={workerCreateDisabled}
                        onPress={() => void run(
                          machine.id,
                          async () => {
                            const createdName = String(workerNames[machine.id] || '').trim();
                            await createDesktopFleetWorkerOnComputer(machine.id, createdName);
                            setTargetKinds((current) => ({ ...current, [machine.id]: 'worker' }));
                            setSelectors((current) => ({ ...current, [machine.id]: createdName }));
                            setWorkerNames((current) => ({ ...current, [machine.id]: '' }));
                          },
                          `Worker created on ${machine.name}. It is now selected as the delegation target.`,
                        )}
                        style={[styles.secondaryButton, workerCreateDisabled ? styles.disabled : null]}
                      >
                        <Text style={styles.secondaryButtonText}>{permissions.create_workers ? 'Create on paired computer' : 'Permission required'}</Text>
                      </Pressable>
                    </View>

                    <View style={[styles.controlSection, styles.permissionSection]}>
                      <Text style={styles.controlEyebrow}>CONNECTION PERMISSIONS</Text>
                      <Text style={styles.controlTitle}>Request a change</Text>
                      <Text style={styles.empty}>The other computer owns these permissions. Your changes remain pending until approved there.</Text>
                      <View style={styles.permissionDraftGrid}>
                        {permissionRows.map(([key, label]) => (
                          <Pressable
                            key={key}
                            accessibilityRole="switch"
                            accessibilityState={{ checked: Boolean(draft[key]) }}
                            onPress={() => setPermissionDrafts((current) => ({
                              ...current,
                              [machine.id]: { ...draft, [key]: !draft[key] },
                            }))}
                            style={[styles.permissionDraft, draft[key] ? styles.permissionDraftOn : null]}
                          >
                            <Text style={styles.permissionDraftText}>{draft[key] ? '✓' : '—'} {label}</Text>
                          </Pressable>
                        ))}
                      </View>
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel={`Request connection permission changes from ${machine.name}`}
                        accessibilityState={{ disabled: permissionRequestDisabled }}
                        disabled={permissionRequestDisabled}
                        onPress={() => void run(
                          machine.id,
                          () => requestDesktopFleetComputerPermissions(machine.id, draft, `Permission change requested from ${machine.name}`),
                          `Permission request sent to ${machine.name}.`,
                        )}
                        style={[styles.secondaryButton, permissionRequestDisabled ? styles.disabled : null]}
                      >
                        <Text style={styles.secondaryButtonText}>Send permission request</Text>
                      </Pressable>
                    </View>

                    {errorById[machine.id] || messageById[machine.id] ? (
                      <View accessibilityLiveRegion="polite" style={[styles.notice, errorById[machine.id] ? styles.noticeError : null]}>
                        <Text style={errorById[machine.id] ? styles.noticeErrorText : styles.noticeText}>{errorById[machine.id] || messageById[machine.id]}</Text>
                      </View>
                    ) : null}

                    {recentDelegations.length ? (
                      <View style={styles.reportList}>
                        <Text style={styles.controlEyebrow}>RECENT REPORTS</Text>
                        {recentDelegations.map((delegation) => (
                          <View key={delegation.delegation_id} style={styles.reportRow}>
                            <View style={styles.reportCopy}>
                              <Text style={styles.reportTarget}>{delegation.target_kind === 'worker' ? delegation.target_selector || 'Worker' : 'Manager agent'}</Text>
                              <Text style={styles.reportSummary} numberOfLines={3}>{String((delegation.report || {}).summary || delegation.prompt)}</Text>
                            </View>
                            <Text style={styles.reportStatus}>{delegation.status.toUpperCase()}</Text>
                          </View>
                        ))}
                      </View>
                    ) : null}
                  </View>
                ) : null}
              </View>
            );
          })}
        </View>
      ) : (
        <View style={styles.emptyState} accessibilityLiveRegion="polite">
          <Text style={styles.emptyTitle}>No connected computers yet</Text>
          <Text style={styles.empty}>Create a code above, paste it once on the other computer, and repeat once per additional computer.</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { padding: 16, gap: 12, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.large, backgroundColor: UI.color.surface },
  headingRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 },
  eyebrow: { color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  title: { marginTop: 4, color: UI.color.text, fontSize: 14, fontWeight: '800' },
  headingDetail: { marginTop: 4, maxWidth: 760, color: UI.color.textSubtle, fontSize: 9, lineHeight: 14 },
  count: { minWidth: 28, color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: 16, fontWeight: '800', textAlign: 'right' },
  grid: { gap: 10 },
  machine: { padding: 12, gap: 10, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.panel, backgroundColor: UI.color.surfaceMuted },
  machineExpanded: { borderColor: UI.color.accentBorder, backgroundColor: UI.color.surface },
  machineHeader: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 },
  machineIdentity: { flex: 1, minWidth: 0 },
  machineName: { color: UI.color.text, fontSize: 12, fontWeight: '800' },
  machineMeta: { marginTop: 3, color: UI.color.textSubtle, fontSize: 9 },
  badge: { paddingHorizontal: 8, paddingVertical: 5, borderRadius: UI.radius.pill, borderWidth: 1 },
  badgeOnline: { borderColor: UI.color.accentBorder, backgroundColor: UI.color.successSoft },
  badgeOffline: { borderColor: UI.color.borderStrong, backgroundColor: UI.color.surface },
  badgeText: { color: UI.color.textMuted, fontFamily: UI.type.mono, fontSize: 8, fontWeight: '800' },
  counts: { color: UI.color.textMuted, fontSize: 10 },
  emptyState: { padding: 13, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.panel, backgroundColor: UI.color.surfaceMuted },
  emptyTitle: { color: UI.color.textMuted, fontSize: 11, fontWeight: '800' },
  empty: { color: UI.color.textSubtle, fontSize: 9, lineHeight: 14 },
  permissionStrip: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  permissionBadge: { paddingHorizontal: 7, paddingVertical: 4, borderRadius: UI.radius.pill, borderWidth: 1, borderColor: UI.color.border, backgroundColor: UI.color.canvas },
  permissionBadgeOn: { borderColor: UI.color.accentBorder, backgroundColor: UI.color.accentSoft },
  permissionBadgeWarning: { borderColor: UI.color.warning, backgroundColor: UI.color.warningSoft },
  permissionBadgeText: { color: UI.color.textMuted, fontFamily: UI.type.mono, fontSize: 8, fontWeight: '700' },
  openButton: { minHeight: 44, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.control, alignItems: 'center', justifyContent: 'center' },
  openButtonText: { color: UI.color.textMuted, fontSize: 10, fontWeight: '800' },
  controls: { marginTop: 2, paddingTop: 12, borderTopWidth: 1, borderColor: UI.color.border, flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  controlSection: { flexGrow: 1, flexBasis: 290, minWidth: 270, padding: 12, gap: 8, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.control, backgroundColor: UI.color.canvas },
  permissionSection: { flexBasis: 320 },
  controlEyebrow: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: 8, fontWeight: '900', letterSpacing: 0.9 },
  controlTitle: { color: UI.color.text, fontSize: 11, fontWeight: '800' },
  segmented: { flexDirection: 'row', gap: 6 },
  segment: { flex: 1, minHeight: 44, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.control, alignItems: 'center', justifyContent: 'center' },
  segmentSelected: { borderColor: UI.color.accentBorder, backgroundColor: UI.color.accentSoft },
  segmentText: { color: UI.color.textSubtle, fontSize: 9, fontWeight: '800' },
  segmentTextSelected: { color: UI.color.accentStrong },
  inputLabel: { color: UI.color.textMuted, fontSize: 9, fontWeight: '700' },
  input: { minHeight: 42, paddingHorizontal: 11, paddingVertical: 9, borderWidth: 1, borderColor: UI.color.borderStrong, borderRadius: UI.radius.control, backgroundColor: UI.color.surface, color: UI.color.text, fontSize: 10 },
  promptInput: { minHeight: 82, textAlignVertical: 'top' },
  primaryButton: { minHeight: 42, borderRadius: UI.radius.control, backgroundColor: UI.color.accent, alignItems: 'center', justifyContent: 'center' },
  primaryButtonText: { color: UI.color.accentInk, fontSize: 10, fontWeight: '900' },
  secondaryButton: { minHeight: 42, paddingHorizontal: 12, borderRadius: UI.radius.control, borderWidth: 1, borderColor: UI.color.accentBorder, backgroundColor: UI.color.accentSoft, alignItems: 'center', justifyContent: 'center' },
  secondaryButtonText: { color: UI.color.accentStrong, fontSize: 10, fontWeight: '800' },
  disabled: { opacity: 0.4 },
  permissionDraftGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  permissionDraft: { flexGrow: 1, flexBasis: 125, minHeight: 44, paddingHorizontal: 8, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.control, justifyContent: 'center' },
  permissionDraftOn: { borderColor: UI.color.accentBorder, backgroundColor: UI.color.accentSoft },
  permissionDraftText: { color: UI.color.textMuted, fontSize: 8, fontWeight: '800' },
  notice: { flexBasis: '100%', padding: 10, borderWidth: 1, borderColor: UI.color.accentBorder, borderRadius: UI.radius.control, backgroundColor: UI.color.accentSoft },
  noticeError: { borderColor: UI.color.danger, backgroundColor: UI.color.dangerSoft },
  noticeWarning: { borderColor: UI.color.warning, backgroundColor: UI.color.warningSoft },
  noticeText: { color: UI.color.textMuted, fontSize: 9 },
  noticeErrorText: { color: UI.color.danger, fontSize: 9, fontWeight: '700' },
  noticeWarningText: { color: UI.color.warning, fontSize: 9, fontWeight: '700' },
  reportList: { flexBasis: '100%', gap: 6, paddingTop: 4 },
  reportRow: { padding: 9, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.control, flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  reportCopy: { flex: 1, gap: 3 },
  reportTarget: { color: UI.color.text, fontSize: 9, fontWeight: '800' },
  reportSummary: { color: UI.color.textSubtle, fontSize: 9, lineHeight: 14 },
  reportStatus: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: 8, fontWeight: '900' },
});
