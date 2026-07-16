import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  createDesktopFleetWorkerOnComputer,
  decideDesktopFleetUpstreamRequest,
  delegateDesktopFleetComputer,
  requestDesktopFleetComputerPermissions,
  type DesktopFleetConnectionPermissions,
  type DesktopFleetRemoteTarget,
  type DesktopFleetSnapshot,
} from '@/lib/desktopBridge';
import { userFacingError } from '../../lib/diagnostics';
import { remoteRuntimesFromFleetSnapshot } from './desktopRemoteRuntimes';
import { DesktopFleetInfoButton } from './DesktopFleetInfoButton';
import { DesktopFleetComputerActivity } from './DesktopFleetComputerActivity';
import { DesktopFleetLivePreview } from './DesktopFleetLivePreview';
import { fleetReportSummary } from './desktopFleetWorkerState';
import { FLEET_TYPE as TYPE } from './desktopFleetUi';
import { DESKTOP_UI as UI } from './desktopUiTokens';

type PermissionKey = 'delegate_manager' | 'delegate_workers' | 'create_workers';

const permissionRows: Array<[PermissionKey, string]> = [
  ['delegate_manager', 'Main identity'],
  ['delegate_workers', 'Existing agents'],
  ['create_workers', 'Create agents'],
];

function permissionForDesktop(snapshot: DesktopFleetSnapshot | null | undefined, desktopId: string) {
  return snapshot?.connection_permissions?.find((item) => item.desktop_id === desktopId) || null;
}

function targetsForConnection(permissionState: DesktopFleetConnectionPermissions | null): DesktopFleetRemoteTarget[] {
  const targets = Array.isArray(permissionState?.capabilities?.targets)
    ? permissionState?.capabilities?.targets || []
    : [];
  return targets.filter((target) => {
    if (target.target_kind === 'manager') return Boolean(permissionState?.permissions.delegate_manager);
    if (target.target_kind === 'worker') return Boolean(permissionState?.permissions.delegate_workers);
    return false;
  });
}

export function DesktopFleetMachinesPanel({
  snapshot,
  onChanged,
  onConnectRequested,
  localComputerContent,
  showConnectAction = true,
  compact = false,
}: {
  snapshot: DesktopFleetSnapshot | null | undefined;
  onChanged?: () => void;
  onConnectRequested?: () => void;
  localComputerContent?: ReactNode;
  showConnectAction?: boolean;
  compact?: boolean;
}) {
  const managerDesktopId = String((snapshot?.manager as any)?.desktop_id || '');
  const machines = remoteRuntimesFromFleetSnapshot(snapshot);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [targetByDesktop, setTargetByDesktop] = useState<Record<string, string>>({});
  const [prompts, setPrompts] = useState<Record<string, string>>({});
  const [workerNames, setWorkerNames] = useState<Record<string, string>>({});
  const [permissionDrafts, setPermissionDrafts] = useState<Record<string, Record<PermissionKey, boolean>>>({});
  const [replyDrafts, setReplyDrafts] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedMachine = machines.find((machine) => machine.id === selectedId) || null;
  const selectedPermissionState = selectedMachine ? permissionForDesktop(snapshot, selectedMachine.id) : null;
  const selectedTargets = targetsForConnection(selectedPermissionState);

  useEffect(() => {
    if (!selectedMachine) return;
    const currentTarget = targetByDesktop[selectedMachine.id];
    if (selectedTargets.some((target) => target.identity_id === currentTarget || target.target_selector === currentTarget)) return;
    const managerTarget = selectedTargets.find((target) => target.target_kind === 'manager');
    const nextTarget = managerTarget || selectedTargets[0];
    if (nextTarget) {
      setTargetByDesktop((current) => ({
        ...current,
        [selectedMachine.id]: String(nextTarget.identity_id || nextTarget.target_selector || nextTarget.display_name),
      }));
    }
  }, [selectedMachine?.id, selectedTargets.map((target) => `${target.identity_id}:${target.target_selector}`).join('|')]);

  const delegationsByDesktop = useMemo(() => {
    const grouped = new Map<string, NonNullable<DesktopFleetSnapshot['delegations']>>();
    for (const delegation of snapshot?.delegations || []) {
      const items = grouped.get(delegation.desktop_id) || [];
      items.push(delegation);
      grouped.set(delegation.desktop_id, items);
    }
    return grouped;
  }, [snapshot?.delegations]);

  const requestsByDesktop = useMemo(() => {
    const grouped = new Map<string, NonNullable<DesktopFleetSnapshot['upstream_requests']>>();
    for (const request of snapshot?.upstream_requests || []) {
      const items = grouped.get(request.desktop_id) || [];
      items.push(request);
      grouped.set(request.desktop_id, items);
    }
    return grouped;
  }, [snapshot?.upstream_requests]);

  const run = async (busyKey: string, action: () => Promise<unknown>, success: string) => {
    setBusyId(busyKey);
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(success);
      onChanged?.();
    } catch (actionError) {
      setError(userFacingError(actionError, 'The connected computer could not complete that action.'));
    } finally {
      setBusyId(null);
    }
  };

  const resolveSelectedTarget = (desktopId: string, targets: DesktopFleetRemoteTarget[]) => {
    const selected = targetByDesktop[desktopId];
    return targets.find((target) => (
      target.identity_id === selected
      || target.target_selector === selected
      || target.display_name === selected
    )) || targets[0] || null;
  };

  return (
    <View style={[styles.section, compact ? styles.sectionCompact : null]}>
      <View style={styles.headingRow}>
        <View style={styles.headingCopy}>
          <Text style={styles.eyebrow}>FLEET COMPUTERS</Text>
          <Text style={styles.title}>Computers and their workers</Text>
        </View>
        <View style={styles.headingActions}>
          <DesktopFleetInfoButton
            label="Fleet computers"
            text="Computers in this Fleet are organized by their direct relationship. Workers live inside the computer where they run. No remote identities are copied; only explicitly exposed labels and activity appear here."
          />
          <Text style={styles.count}>{machines.length}</Text>
          {showConnectAction ? (
            <Pressable accessibilityRole="button" onPress={onConnectRequested} style={styles.connectButton}>
              <Text style={styles.connectButtonText}>+ Connect computer</Text>
            </Pressable>
          ) : null}
        </View>
      </View>

      <View style={styles.grid}>
        {machines.map((machine) => {
          const online = machine.status === 'connected';
          const isLocal = machine.id === managerDesktopId;
          const permissionState = permissionForDesktop(snapshot, machine.id);
          const capabilities = permissionState?.capabilities;
          const pendingRequests = (requestsByDesktop.get(machine.id) || []).filter((request) => request.status === 'pending').length;
          const recentDelegation = (delegationsByDesktop.get(machine.id) || [])[0];
          const isIntermediary = Number(capabilities?.child_count || 0) > 0;
          const visibleAgentCount = isLocal
            ? Number(machine.workerCount || 0)
            : Math.max(Number(machine.workerCount || 0), targetsForConnection(permissionState).length);
          return (
            <Pressable
              key={machine.id}
              accessibilityRole="button"
              accessibilityLabel={`Open ${machine.name}`}
              accessibilityState={{ selected: selectedId === machine.id }}
              onPress={() => setSelectedId((current) => current === machine.id ? null : machine.id)}
              style={[styles.machine, selectedId === machine.id ? styles.machineSelected : null]}
            >
              <View style={styles.machineHeader}>
                <View style={styles.machineIdentity}>
                  <Text style={styles.machineName} numberOfLines={1}>{machine.name}</Text>
                  <Text style={styles.machineMeta}>{isLocal ? 'This computer · local manager' : isIntermediary ? `Intermediary · ${capabilities?.child_count} below` : 'Connected computer'}</Text>
                </View>
                <View style={[styles.statusBadge, online ? styles.statusBadgeOnline : styles.statusBadgeOffline]}>
                  <Text style={styles.statusBadgeText}>{online ? '● ONLINE' : '○ OFFLINE'}</Text>
                </View>
              </View>
              <View style={styles.cardStats}>
                <View style={styles.stat}>
                  <Text style={styles.statValue}>{visibleAgentCount}</Text>
                  <Text style={styles.statLabel}>agents</Text>
                </View>
                <View style={styles.stat}>
                  <Text style={[styles.statValue, machine.activeCount ? styles.statAttention : null]}>{machine.activeCount}</Text>
                  <Text style={styles.statLabel}>active</Text>
                </View>
                <View style={styles.statWide}>
                  <Text style={styles.statLabel}>{machine.queuedCount ? 'QUEUE' : pendingRequests ? `${pendingRequests} REQUEST${pendingRequests === 1 ? '' : 'S'}` : 'LATEST'}</Text>
                  <Text style={styles.latestValue} numberOfLines={1}>{machine.queuedCount ? `${machine.queuedCount} queued` : recentDelegation?.status || machine.latestReport || 'No work yet'}</Text>
                </View>
              </View>
              <View style={[styles.openHintPill, selectedId === machine.id ? styles.openHintPillSelected : null]}>
                <Text style={[styles.openHint, selectedId === machine.id ? styles.openHintSelected : null]}>
                  {selectedId === machine.id ? 'DETAILS OPEN ↓' : 'OPEN WORKSPACE →'}
                </Text>
              </View>
            </Pressable>
          );
        })}
        {!machines.length ? (
          <Pressable accessibilityRole="button" onPress={onConnectRequested} style={[styles.machine, styles.emptyMachine]}>
            <Text style={styles.emptyGlyph}>＋</Text>
            <Text style={styles.emptyTitle}>Connect your first computer</Text>
            <Text style={styles.emptyText}>Create one private code here, then paste it once on the other computer.</Text>
          </Pressable>
        ) : null}
      </View>

      {selectedMachine ? (() => {
        const isLocal = selectedMachine.id === managerDesktopId;
        if (isLocal) {
          return (
            <View style={[styles.drawer, styles.localDrawer]} accessibilityLiveRegion="polite">
              <View style={styles.drawerHeader}>
                <View style={styles.headingCopy}>
                  <Text style={styles.drawerEyebrow}>THIS COMPUTER WORKSPACE</Text>
                  <Text style={styles.drawerTitle}>{selectedMachine.name}</Text>
                  <Text style={styles.drawerSubtitle}>Local workers, queues, reports, and screen preview all belong to this computer.</Text>
                </View>
                <View style={styles.drawerHeaderActions}>
                  <DesktopFleetInfoButton
                    label="This computer"
                    text="These workers run on this computer. Opening another computer switches the same workspace to that computer's exposed workers and activity."
                  />
                  <Pressable accessibilityRole="button" accessibilityLabel="Close this computer workspace" onPress={() => setSelectedId(null)} style={styles.closeButton}>
                    <Text style={styles.closeButtonText}>×</Text>
                  </Pressable>
                </View>
              </View>
              <DesktopFleetLivePreview
                desktopId={selectedMachine.id}
                desktopName={selectedMachine.name}
                online
              />
              {localComputerContent || (
                <View style={styles.localEmpty}>
                  <Text style={styles.emptyTitle}>No local worker controls available</Text>
                  <Text style={styles.emptyText}>Refresh Fleet to load the workers that run on this computer.</Text>
                </View>
              )}
            </View>
          );
        }
        const permissionState = selectedPermissionState;
        const permissions = permissionState?.permissions || { delegate_manager: false, delegate_workers: false, create_workers: false };
        const protocolReady = permissionState?.source === 'paired_desktop';
        const online = selectedMachine.status === 'connected';
        const targets = selectedTargets;
        const target = resolveSelectedTarget(selectedMachine.id, targets);
        const draft = permissionDrafts[selectedMachine.id] || { ...permissions };
        const requests = requestsByDesktop.get(selectedMachine.id) || [];
        const recentDelegations = (delegationsByDesktop.get(selectedMachine.id) || []).slice(0, 6);
        const busy = Boolean(busyId);
        return (
          <View style={styles.drawer} accessibilityLiveRegion="polite">
            <View style={styles.drawerHeader}>
              <View style={styles.headingCopy}>
                <Text style={styles.drawerEyebrow}>OPEN COMPUTER WORKSPACE</Text>
                <Text style={styles.drawerTitle}>{selectedMachine.name}</Text>
              </View>
              <View style={styles.drawerHeaderActions}>
                <DesktopFleetInfoButton
                  label={`${selectedMachine.name} privacy`}
                  text="Only capabilities this computer explicitly exposes appear here. Its conversations, files, providers, and settings remain private on that computer."
                />
                <Pressable accessibilityRole="button" accessibilityLabel="Close computer details" onPress={() => setSelectedId(null)} style={styles.closeButton}>
                  <Text style={styles.closeButtonText}>×</Text>
                </Pressable>
              </View>
            </View>

            {!protocolReady ? (
              <View style={styles.warning}>
                <Text style={styles.warningText}>UPDATE REQUIRED · This computer has not published its current capability directory yet. It may be connected with an older Fleet protocol. Update and restart EmploAI there; no re-pairing is needed.</Text>
              </View>
            ) : null}

            <View style={styles.drawerColumns}>
              <DesktopFleetComputerActivity
                snapshot={snapshot}
                desktopId={selectedMachine.id}
                targets={targets}
              />
              <DesktopFleetLivePreview
                desktopId={selectedMachine.id}
                desktopName={selectedMachine.name}
                online={online}
              />
            </View>

            <View style={styles.drawerColumns}>
              <View style={styles.controlSection}>
                <Text style={styles.controlEyebrow}>DELEGATE</Text>
                <Text style={styles.controlTitle}>Choose a destination identity</Text>
                {targets.length ? (
                  <View style={styles.targetList}>
                    {targets.map((item) => {
                      const key = String(item.identity_id || item.target_selector || item.display_name);
                      const selected = target === item;
                      return (
                        <Pressable
                          key={key}
                          accessibilityRole="radio"
                          accessibilityState={{ checked: selected }}
                          onPress={() => setTargetByDesktop((current) => ({ ...current, [selectedMachine.id]: key }))}
                          style={[styles.targetRow, selected ? styles.targetRowSelected : null]}
                        >
                          <View style={styles.targetCopy}>
                            <Text style={styles.targetName}>{item.display_name}</Text>
                            <Text style={styles.targetMeta}>{item.role === 'manager' ? 'Main identity' : 'Agent'} · {item.status || 'ready'}</Text>
                          </View>
                          <Text style={styles.targetCheck}>{selected ? '●' : '○'}</Text>
                        </Pressable>
                      );
                    })}
                  </View>
                ) : (
                  <Text style={styles.emptyText}>No target identities are currently allowed by this computer.</Text>
                )}
                <Text style={styles.inputLabel}>Task</Text>
                <TextInput
                  accessibilityLabel={`Delegation for ${selectedMachine.name}`}
                  multiline
                  value={prompts[selectedMachine.id] || ''}
                  onChangeText={(value) => setPrompts((current) => ({ ...current, [selectedMachine.id]: value }))}
                  placeholder="Describe the outcome, constraints, and what the report should include."
                  placeholderTextColor={UI.color.textSubtle}
                  style={[styles.input, styles.promptInput]}
                />
                <Pressable
                  accessibilityRole="button"
                  accessibilityState={{ disabled: busy || !online || !target || !(prompts[selectedMachine.id] || '').trim() }}
                  disabled={busy || !online || !target || !(prompts[selectedMachine.id] || '').trim()}
                  onPress={() => {
                    if (!target) return;
                    const prompt = prompts[selectedMachine.id] || '';
                    void run(
                      `delegate:${selectedMachine.id}`,
                      async () => {
                        await delegateDesktopFleetComputer(
                          selectedMachine.id,
                          prompt,
                          target.target_kind,
                          target.target_selector,
                        );
                        setPrompts((current) => current[selectedMachine.id] === prompt
                          ? { ...current, [selectedMachine.id]: '' }
                          : current);
                      },
                      `Delegation sent to ${target.display_name}.`,
                    );
                  }}
                  style={[styles.primaryButton, (busy || !online || !target || !(prompts[selectedMachine.id] || '').trim()) ? styles.disabled : null]}
                >
                  <Text style={styles.primaryButtonText}>{busyId === `delegate:${selectedMachine.id}` ? 'Sending…' : 'Send delegation'}</Text>
                </Pressable>
              </View>

              <View style={styles.controlSection}>
                <Text style={styles.controlEyebrow}>REQUESTS FROM BELOW</Text>
                <Text style={styles.controlTitle}>Questions, approvals, and blockers</Text>
                {requests.length ? requests.slice(0, 8).map((request) => {
                  const pending = request.status === 'pending';
                  const reply = replyDrafts[request.request_id] || '';
                  return (
                    <View key={request.request_id} style={[styles.requestCard, request.request_kind === 'blocked' ? styles.requestBlocked : null]}>
                      <View style={styles.requestHeader}>
                        <Text style={styles.requestKind}>{request.request_kind.toUpperCase()}</Text>
                        <Text style={styles.requestStatus}>{request.status.toUpperCase()}</Text>
                      </View>
                      <Text style={styles.requestIdentity}>{request.identity_label || 'Local agent'}</Text>
                      <Text style={styles.requestMessage}>{request.message}</Text>
                      {request.response ? <Text style={styles.responseText}>Response: {request.response}</Text> : null}
                      {pending ? (
                        <>
                          <TextInput
                            accessibilityLabel={`Reply to ${request.identity_label || 'agent request'}`}
                            value={reply}
                            onChangeText={(value) => setReplyDrafts((current) => ({ ...current, [request.request_id]: value }))}
                            placeholder="Optional response"
                            placeholderTextColor={UI.color.textSubtle}
                            style={styles.input}
                          />
                          <View style={styles.requestActions}>
                            <Pressable
                              accessibilityRole="button"
                              disabled={busy}
                              onPress={() => void run(
                                `request:${request.request_id}`,
                                () => decideDesktopFleetUpstreamRequest(selectedMachine.id, request.request_id, 'approved', reply),
                                'Request approved.',
                              )}
                              style={styles.approveButton}
                            ><Text style={styles.approveButtonText}>Approve</Text></Pressable>
                            <Pressable
                              accessibilityRole="button"
                              disabled={busy}
                              onPress={() => void run(
                                `request:${request.request_id}`,
                                () => decideDesktopFleetUpstreamRequest(selectedMachine.id, request.request_id, 'denied', reply),
                                'Request denied.',
                              )}
                              style={styles.denyButton}
                            ><Text style={styles.denyButtonText}>Deny</Text></Pressable>
                            <Pressable
                              accessibilityRole="button"
                              disabled={busy || !reply.trim()}
                              onPress={() => void run(
                                `request:${request.request_id}`,
                                () => decideDesktopFleetUpstreamRequest(selectedMachine.id, request.request_id, 'replied', reply),
                                'Reply sent.',
                              )}
                              style={[styles.replyButton, !reply.trim() ? styles.disabled : null]}
                            ><Text style={styles.replyButtonText}>Reply</Text></Pressable>
                          </View>
                        </>
                      ) : null}
                    </View>
                  );
                }) : <Text style={styles.emptyText}>No requests from this computer yet.</Text>}
              </View>
            </View>

            <View style={styles.drawerColumns}>
              {permissions.create_workers ? (
                <View style={styles.controlSection}>
                  <View style={styles.controlHeadingRow}>
                    <View style={styles.controlHeadingCopy}>
                      <Text style={styles.controlEyebrow}>OPTIONAL AGENT</Text>
                      <Text style={styles.controlTitle}>Create an identity on {selectedMachine.name}</Text>
                    </View>
                    <DesktopFleetInfoButton
                      label="Remote agent creation"
                      text="The worker is created and stored there only. It appears here after that computer publishes its next capability update."
                    />
                  </View>
                  <TextInput
                    accessibilityLabel={`New agent name on ${selectedMachine.name}`}
                    value={workerNames[selectedMachine.id] || ''}
                    onChangeText={(value) => setWorkerNames((current) => ({ ...current, [selectedMachine.id]: value }))}
                    placeholder="Agent name"
                    placeholderTextColor={UI.color.textSubtle}
                    style={styles.input}
                  />
                  <Pressable
                    accessibilityRole="button"
                    disabled={busy || !online || !(workerNames[selectedMachine.id] || '').trim()}
                    onPress={() => void run(
                      `create:${selectedMachine.id}`,
                      async () => {
                        await createDesktopFleetWorkerOnComputer(selectedMachine.id, workerNames[selectedMachine.id]);
                        setWorkerNames((current) => ({ ...current, [selectedMachine.id]: '' }));
                      },
                      'Agent created on the connected computer.',
                    )}
                    style={[styles.secondaryButton, (busy || !online || !(workerNames[selectedMachine.id] || '').trim()) ? styles.disabled : null]}
                  ><Text style={styles.secondaryButtonText}>Create on that computer</Text></Pressable>
                </View>
              ) : null}

              <View style={styles.controlSection}>
                <View style={styles.controlHeadingRow}>
                  <View style={styles.controlHeadingCopy}>
                    <Text style={styles.controlEyebrow}>CONNECTION ACCESS</Text>
                    <Text style={styles.controlTitle}>Request a permission change</Text>
                  </View>
                  <DesktopFleetInfoButton
                    label="Connection access"
                    text="The connected computer owns this decision. A change remains pending until someone approves it on that computer."
                  />
                </View>
                <View style={styles.permissionGrid}>
                  {permissionRows.map(([key, label]) => (
                    <Pressable
                      key={key}
                      accessibilityRole="switch"
                      accessibilityState={{ checked: Boolean(draft[key]) }}
                      onPress={() => setPermissionDrafts((current) => ({
                        ...current,
                        [selectedMachine.id]: { ...draft, [key]: !draft[key] },
                      }))}
                      style={[styles.permissionButton, draft[key] ? styles.permissionButtonOn : null]}
                    ><Text style={styles.permissionButtonText}>{draft[key] ? '✓' : '—'} {label}</Text></Pressable>
                  ))}
                </View>
                <Pressable
                  accessibilityRole="button"
                  disabled={busy || !online || !protocolReady}
                  onPress={() => void run(
                    `permissions:${selectedMachine.id}`,
                    () => requestDesktopFleetComputerPermissions(selectedMachine.id, draft, 'Permission change requested by the direct manager'),
                    'Permission request sent.',
                  )}
                  style={[styles.secondaryButton, (busy || !online || !protocolReady) ? styles.disabled : null]}
                ><Text style={styles.secondaryButtonText}>Send request</Text></Pressable>
              </View>

              <View style={styles.controlSection}>
                <Text style={styles.controlEyebrow}>RECENT REPORTS</Text>
                {recentDelegations.length ? recentDelegations.map((delegation) => (
                  <View key={delegation.delegation_id} style={styles.reportRow}>
                    <View style={styles.reportCopy}>
                      <Text style={styles.reportTarget}>{String((delegation.report || {}).target_label || delegation.target_selector || 'Main identity')}</Text>
                      <Text style={styles.reportSummary} numberOfLines={3}>{fleetReportSummary({ summary: (delegation.report || {}).summary || delegation.prompt, provider_failure: (delegation.report || {}).provider_failure })}</Text>
                    </View>
                    <Text style={styles.reportStatus}>{delegation.status.toUpperCase()}</Text>
                  </View>
                )) : <Text style={styles.emptyText}>No reports from this computer yet.</Text>}
              </View>
            </View>

            {error || message ? (
              <View style={[styles.notice, error ? styles.noticeError : null]} accessibilityLiveRegion="polite">
                <Text style={error ? styles.noticeErrorText : styles.noticeText}>{error || message}</Text>
              </View>
            ) : null}
          </View>
        );
      })() : null}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { padding: 18, gap: 14, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.large, backgroundColor: UI.color.surface },
  sectionCompact: { padding: 14 },
  headingRow: { position: 'relative', zIndex: 20, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-start', justifyContent: 'space-between', gap: 14 },
  headingCopy: { flex: 1, minWidth: 240 },
  headingActions: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  eyebrow: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: TYPE.eyebrow, fontWeight: '900', letterSpacing: 1.1 },
  title: { marginTop: 5, color: UI.color.text, fontSize: TYPE.panelTitle, fontWeight: '800' },
  count: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: TYPE.number, fontWeight: '900' },
  connectButton: { minHeight: 44, paddingHorizontal: 14, borderRadius: UI.radius.control, backgroundColor: UI.color.accent, alignItems: 'center', justifyContent: 'center' },
  connectButtonText: { color: UI.color.accentInk, fontSize: TYPE.body, fontWeight: '900' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  machine: { position: 'relative', flexGrow: 1, flexBasis: 270, minWidth: 250, maxWidth: 420, minHeight: 178, padding: 16, gap: 14, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.panel, backgroundColor: UI.color.surfaceMuted },
  machineSelected: { borderWidth: 2, borderColor: UI.color.accent, backgroundColor: UI.color.surfaceRaised, shadowColor: UI.color.accent, shadowOpacity: 0.16, shadowRadius: 18, shadowOffset: { width: 0, height: 8 }, elevation: 5 },
  machineHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  machineIdentity: { flex: 1, minWidth: 0 },
  machineName: { color: UI.color.text, fontSize: TYPE.sectionTitle, fontWeight: '900' },
  machineMeta: { marginTop: 4, color: UI.color.textMuted, fontSize: TYPE.meta },
  statusBadge: { paddingHorizontal: 7, paddingVertical: 5, borderRadius: UI.radius.pill, borderWidth: 1 },
  statusBadgeOnline: { borderColor: UI.color.accentBorder, backgroundColor: UI.color.successSoft },
  statusBadgeOffline: { borderColor: UI.color.borderStrong, backgroundColor: UI.color.canvas },
  statusBadgeText: { color: UI.color.textMuted, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  cardStats: { flexDirection: 'row', gap: 8 },
  stat: { minWidth: 50, paddingRight: 8, borderRightWidth: 1, borderColor: UI.color.border },
  statWide: { flex: 1, minWidth: 70 },
  statValue: { color: UI.color.text, fontFamily: UI.type.mono, fontSize: 17, fontWeight: '900' },
  statAttention: { color: UI.color.warning },
  statLabel: { marginTop: 3, color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '800', letterSpacing: 0.6 },
  latestValue: { marginTop: 4, color: UI.color.textMuted, fontSize: TYPE.meta, fontWeight: '700' },
  openHintPill: { alignSelf: 'flex-start', minHeight: 30, paddingHorizontal: 10, borderWidth: 1, borderColor: UI.color.borderStrong, borderRadius: UI.radius.pill, justifyContent: 'center', backgroundColor: UI.color.canvas },
  openHintPillSelected: { borderColor: UI.color.accent, backgroundColor: UI.color.accent },
  openHint: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900', letterSpacing: 0.4 },
  openHintSelected: { color: UI.color.accentInk },
  emptyMachine: { alignItems: 'center', justifyContent: 'center', borderStyle: 'dashed' },
  emptyGlyph: { color: UI.color.accentStrong, fontSize: 26, lineHeight: 28 },
  emptyTitle: { color: UI.color.text, fontSize: TYPE.sectionTitle, fontWeight: '800', textAlign: 'center' },
  emptyText: { color: UI.color.textSubtle, fontSize: TYPE.body, lineHeight: TYPE.bodyLine },
  drawer: { marginTop: 6, padding: 18, gap: 16, borderWidth: 2, borderColor: UI.color.accent, borderRadius: UI.radius.large, backgroundColor: UI.color.surfaceRaised, shadowColor: UI.color.shadow, shadowOpacity: 0.34, shadowRadius: 26, shadowOffset: { width: 0, height: 14 }, elevation: 8 },
  localDrawer: { backgroundColor: UI.color.canvas },
  localEmpty: { minHeight: 120, padding: 18, alignItems: 'center', justifyContent: 'center', gap: 6, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.panel },
  drawerHeader: { position: 'relative', zIndex: 20, flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  drawerHeaderActions: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  drawerEyebrow: { color: UI.color.accentInk, fontFamily: UI.type.mono, fontSize: TYPE.eyebrow, fontWeight: '900', letterSpacing: 1.1, alignSelf: 'flex-start', paddingHorizontal: 9, paddingVertical: 5, borderRadius: UI.radius.pill, backgroundColor: UI.color.accent },
  drawerTitle: { marginTop: 8, color: UI.color.text, fontSize: TYPE.heroTitle, fontWeight: '900' },
  drawerSubtitle: { marginTop: 6, maxWidth: 720, color: UI.color.textMuted, fontSize: TYPE.body, lineHeight: TYPE.bodyLine },
  closeButton: { width: 44, height: 44, borderRadius: UI.radius.control, borderWidth: 1, borderColor: UI.color.border, alignItems: 'center', justifyContent: 'center' },
  closeButtonText: { color: UI.color.textMuted, fontSize: 20 },
  warning: { padding: 10, borderWidth: 1, borderColor: UI.color.warning, borderRadius: UI.radius.control, backgroundColor: UI.color.warningSoft },
  warningText: { color: UI.color.warning, fontSize: TYPE.body, fontWeight: '700', lineHeight: TYPE.bodyLine },
  drawerColumns: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  controlSection: { flexGrow: 1, flexBasis: 310, minWidth: 280, padding: 15, gap: 11, borderWidth: 1, borderColor: UI.color.borderStrong, borderRadius: UI.radius.panel, backgroundColor: UI.color.surface },
  controlHeadingRow: { position: 'relative', zIndex: 20, flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 },
  controlHeadingCopy: { flex: 1, gap: 4 },
  controlEyebrow: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: TYPE.eyebrow, fontWeight: '900', letterSpacing: 0.9 },
  controlTitle: { color: UI.color.text, fontSize: TYPE.sectionTitle, fontWeight: '800' },
  targetList: { gap: 6 },
  targetRow: { minHeight: 52, paddingHorizontal: 10, paddingVertical: 8, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.control, flexDirection: 'row', alignItems: 'center', gap: 10 },
  targetRowSelected: { borderColor: UI.color.accentBorder, backgroundColor: UI.color.accentSoft },
  targetCopy: { flex: 1 },
  targetName: { color: UI.color.text, fontSize: TYPE.control, fontWeight: '800' },
  targetMeta: { marginTop: 3, color: UI.color.textSubtle, fontSize: TYPE.meta },
  targetCheck: { color: UI.color.accentStrong, fontSize: TYPE.control },
  inputLabel: { color: UI.color.textMuted, fontSize: TYPE.body, fontWeight: '700' },
  input: { minHeight: 48, paddingHorizontal: 12, paddingVertical: 10, borderWidth: 1, borderColor: UI.color.borderStrong, borderRadius: UI.radius.control, backgroundColor: UI.color.canvas, color: UI.color.text, fontSize: TYPE.control },
  promptInput: { minHeight: 112, textAlignVertical: 'top' },
  primaryButton: { minHeight: 44, paddingHorizontal: 12, borderRadius: UI.radius.control, backgroundColor: UI.color.accent, alignItems: 'center', justifyContent: 'center' },
  primaryButtonText: { color: UI.color.accentInk, fontSize: TYPE.body, fontWeight: '900' },
  secondaryButton: { minHeight: 44, paddingHorizontal: 12, borderRadius: UI.radius.control, borderWidth: 1, borderColor: UI.color.accentBorder, backgroundColor: UI.color.accentSoft, alignItems: 'center', justifyContent: 'center' },
  secondaryButtonText: { color: UI.color.accentStrong, fontSize: TYPE.body, fontWeight: '800' },
  disabled: { opacity: 0.4 },
  requestCard: { padding: 10, gap: 7, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.control, backgroundColor: UI.color.canvas },
  requestBlocked: { borderColor: UI.color.warning },
  requestHeader: { flexDirection: 'row', justifyContent: 'space-between', gap: 8 },
  requestKind: { color: UI.color.warning, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  requestStatus: { color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  requestIdentity: { color: UI.color.text, fontSize: TYPE.body, fontWeight: '800' },
  requestMessage: { color: UI.color.textMuted, fontSize: TYPE.body, lineHeight: TYPE.bodyLine },
  responseText: { color: UI.color.accentStrong, fontSize: TYPE.body, lineHeight: TYPE.bodyLine },
  requestActions: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  approveButton: { minHeight: 40, paddingHorizontal: 10, borderRadius: UI.radius.control, backgroundColor: UI.color.successSoft, borderWidth: 1, borderColor: UI.color.accentBorder, alignItems: 'center', justifyContent: 'center' },
  approveButtonText: { color: UI.color.success, fontSize: TYPE.body, fontWeight: '900' },
  denyButton: { minHeight: 40, paddingHorizontal: 10, borderRadius: UI.radius.control, backgroundColor: UI.color.dangerSoft, borderWidth: 1, borderColor: UI.color.danger, alignItems: 'center', justifyContent: 'center' },
  denyButtonText: { color: UI.color.danger, fontSize: TYPE.body, fontWeight: '900' },
  replyButton: { minHeight: 40, paddingHorizontal: 10, borderRadius: UI.radius.control, borderWidth: 1, borderColor: UI.color.borderStrong, alignItems: 'center', justifyContent: 'center' },
  replyButtonText: { color: UI.color.textMuted, fontSize: TYPE.body, fontWeight: '900' },
  permissionGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  permissionButton: { flexGrow: 1, flexBasis: 120, minHeight: 44, paddingHorizontal: 8, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.control, justifyContent: 'center' },
  permissionButtonOn: { borderColor: UI.color.accentBorder, backgroundColor: UI.color.accentSoft },
  permissionButtonText: { color: UI.color.textMuted, fontSize: TYPE.meta, fontWeight: '800' },
  reportRow: { padding: 9, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.control, flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  reportCopy: { flex: 1, gap: 3 },
  reportTarget: { color: UI.color.text, fontSize: TYPE.body, fontWeight: '800' },
  reportSummary: { color: UI.color.textSubtle, fontSize: TYPE.body, lineHeight: TYPE.bodyLine },
  reportStatus: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  notice: { padding: 10, borderWidth: 1, borderColor: UI.color.accentBorder, borderRadius: UI.radius.control, backgroundColor: UI.color.accentSoft },
  noticeError: { borderColor: UI.color.danger, backgroundColor: UI.color.dangerSoft },
  noticeText: { color: UI.color.textMuted, fontSize: TYPE.body },
  noticeErrorText: { color: UI.color.danger, fontSize: TYPE.body, fontWeight: '700' },
});
