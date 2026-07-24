import { useEffect, useMemo, useState } from 'react';
import ChevronDown from 'lucide-react-native/icons/chevron-down';
import ChevronUp from 'lucide-react-native/icons/chevron-up';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { DesktopFleetConnectionPermissions } from '@/lib/desktopBridge';
import { FLEET_TYPE as TYPE } from './desktopFleetUi';
import { DESKTOP_UI as UI } from './desktopUiTokens';

type ConnectionPermissions = DesktopFleetConnectionPermissions['permissions'];
type PermissionKey = keyof ConnectionPermissions;

const permissionRows: Array<[PermissionKey, string]> = [
  ['delegate_manager', 'Manager route'],
  ['delegate_workers', 'Existing workers'],
  ['create_workers', 'Create workers'],
  ['configure_manager_tools', 'Configure manager tools'],
  ['manage_runtime', 'Start EmploAI'],
  ['manage_updates', 'Update EmploAI'],
];

function copyPermissions(permissions: ConnectionPermissions): ConnectionPermissions {
  return { ...permissions };
}

export function DesktopFleetConnectionAccess({
  desktopId,
  desktopName,
  permissions,
  pendingRequest,
  online,
  protocolReady,
  busy,
  onRequest,
}: {
  desktopId: string;
  desktopName: string;
  permissions: ConnectionPermissions;
  pendingRequest?: Record<string, unknown> | null;
  online: boolean;
  protocolReady: boolean;
  busy: boolean;
  onRequest: (permissions: ConnectionPermissions) => Promise<boolean>;
}) {
  const permissionSignature = permissionRows.map(([key]) => permissions[key] ? '1' : '0').join('');
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState<ConnectionPermissions>(() => copyPermissions(permissions));

  useEffect(() => {
    setExpanded(false);
    setDraft(copyPermissions(permissions));
  }, [desktopId]);

  useEffect(() => {
    setDraft(copyPermissions(permissions));
  }, [permissionSignature]);

  const allowedCount = permissionRows.filter(([key]) => permissions[key]).length;
  const blockedLabels = permissionRows.filter(([key]) => !permissions[key]).map(([, label]) => label);
  const blockedSummary = blockedLabels.length === 1
    ? `${blockedLabels[0]} blocked`
    : blockedLabels.length > 1
      ? `${blockedLabels.length} permissions blocked`
      : 'All access allowed';
  const requestPending = Boolean(pendingRequest && String(pendingRequest.status || 'pending') === 'pending');
  const hasChanges = useMemo(
    () => permissionRows.some(([key]) => draft[key] !== permissions[key]),
    [draft, permissionSignature],
  );
  const submitDisabled = busy || !online || !protocolReady || requestPending || !hasChanges;

  const cancelChanges = () => {
    setDraft(copyPermissions(permissions));
    setExpanded(false);
  };

  const submitChanges = async () => {
    if (submitDisabled) return;
    const sent = await onRequest(copyPermissions(draft));
    if (!sent) return;
    setDraft(copyPermissions(permissions));
    setExpanded(false);
  };

  return (
    <View style={styles.container}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Connection access, ${allowedCount} of ${permissionRows.length} allowed, ${blockedSummary}`}
        accessibilityHint={expanded ? 'Collapse connection permissions' : 'Review or request different connection permissions'}
        accessibilityState={{ expanded }}
        onPress={() => setExpanded((current) => !current)}
        style={styles.summary}
      >
        <View style={styles.summaryCopy}>
          <Text style={styles.title}>Connection access</Text>
          <View style={styles.summaryMeta}>
            <Text style={styles.count}>{allowedCount} of {permissionRows.length} allowed</Text>
            <Text style={blockedLabels.length ? styles.blocked : styles.allowed}>{blockedSummary}</Text>
            {requestPending ? <Text style={styles.pending}>CHANGE PENDING</Text> : null}
          </View>
        </View>
        <View style={styles.disclosureAction}>
          <Text style={styles.disclosureLabel}>{expanded ? 'Close' : 'Change'}</Text>
          {expanded
            ? <ChevronUp size={16} color={UI.color.accentStrong} strokeWidth={2} />
            : <ChevronDown size={16} color={UI.color.accentStrong} strokeWidth={2} />}
        </View>
      </Pressable>

      {expanded ? (
        <View style={styles.editor}>
          <View style={styles.permissionList}>
            {permissionRows.map(([key, label]) => {
              const enabled = Boolean(draft[key]);
              return (
                <Pressable
                  key={key}
                  accessibilityRole="switch"
                  accessibilityLabel={label}
                  accessibilityState={{ checked: enabled, disabled: busy || requestPending }}
                  disabled={busy || requestPending}
                  onPress={() => setDraft((current) => ({ ...current, [key]: !current[key] }))}
                  style={styles.permissionRow}
                >
                  <Text style={styles.permissionLabel}>{label}</Text>
                  <View style={styles.permissionState}>
                    <View style={[styles.stateDot, enabled ? styles.stateDotAllowed : null]} />
                    <Text style={[styles.permissionValue, enabled ? styles.permissionValueAllowed : null]}>
                      {enabled ? 'ALLOWED' : 'BLOCKED'}
                    </Text>
                  </View>
                </Pressable>
              );
            })}
          </View>

          <View style={styles.footer}>
            <Text style={styles.approvalNote}>
              {requestPending
                ? `A change is waiting for approval on ${desktopName}.`
                : `Changes require approval on ${desktopName}.`}
            </Text>
            <View style={styles.actions}>
              <Pressable
                accessibilityRole="button"
                disabled={busy}
                onPress={cancelChanges}
                style={styles.cancelButton}
              >
                <Text style={styles.cancelButtonText}>Cancel</Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                accessibilityState={{ disabled: submitDisabled }}
                disabled={submitDisabled}
                onPress={() => void submitChanges()}
                style={[styles.sendButton, submitDisabled ? styles.disabled : null]}
              >
                <Text style={styles.sendButtonText}>{busy ? 'Sending…' : 'Send request'}</Text>
              </Pressable>
            </View>
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    overflow: 'hidden',
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surfaceMuted,
  },
  summary: {
    minHeight: 60,
    paddingHorizontal: 14,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  summaryCopy: { flex: 1, minWidth: 0, gap: 6 },
  title: { color: UI.color.text, fontSize: TYPE.control, fontWeight: '800' },
  summaryMeta: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 },
  count: { color: UI.color.textMuted, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '800' },
  blocked: { color: UI.color.warning, fontSize: TYPE.meta, fontWeight: '700' },
  allowed: { color: UI.color.success, fontSize: TYPE.meta, fontWeight: '700' },
  pending: {
    paddingHorizontal: 7,
    paddingVertical: 3,
    borderRadius: UI.radius.pill,
    backgroundColor: UI.color.warningSoft,
    color: UI.color.warning,
    fontFamily: UI.type.mono,
    fontSize: TYPE.micro,
    fontWeight: '900',
  },
  disclosureAction: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  disclosureLabel: { color: UI.color.accentStrong, fontSize: TYPE.body, fontWeight: '800' },
  editor: {
    paddingHorizontal: 14,
    paddingTop: 4,
    paddingBottom: 14,
  },
  permissionList: { paddingVertical: 3 },
  permissionRow: {
    minHeight: 43,
    paddingHorizontal: 2,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  permissionLabel: { flex: 1, color: UI.color.textMuted, fontSize: TYPE.body, fontWeight: '700' },
  permissionState: {
    minWidth: 78,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 6,
  },
  stateDot: { width: 6, height: 6, borderRadius: UI.radius.pill, backgroundColor: UI.color.textSubtle },
  stateDotAllowed: { backgroundColor: UI.color.success },
  permissionValue: { color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  permissionValueAllowed: { color: UI.color.success },
  footer: {
    paddingTop: 12,
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  approvalNote: { flexGrow: 1, flexShrink: 1, color: UI.color.textSubtle, fontSize: TYPE.meta },
  actions: { flexDirection: 'row', gap: 7 },
  cancelButton: {
    minHeight: 38,
    paddingHorizontal: 12,
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceRaised,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cancelButtonText: { color: UI.color.textMuted, fontSize: TYPE.body, fontWeight: '800' },
  sendButton: {
    minHeight: 38,
    paddingHorizontal: 12,
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accentSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendButtonText: { color: UI.color.accentStrong, fontSize: TYPE.body, fontWeight: '900' },
  disabled: { opacity: 0.4 },
});
