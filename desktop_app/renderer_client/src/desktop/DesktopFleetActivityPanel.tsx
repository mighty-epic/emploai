import { useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  loadDesktopFleetLocalActivity,
  requestDesktopFleetManager,
  type DesktopFleetIdentity,
  type DesktopFleetLocalActivity,
  type DesktopFleetSnapshot,
} from '@/lib/desktopBridge';
import { userFacingError } from '../../lib/diagnostics';
import { DESKTOP_UI as UI } from './desktopUiTokens';

type RequestKind = 'question' | 'approval' | 'blocked';

const requestKinds: Array<[RequestKind, string, string]> = [
  ['question', 'Question', 'Ask for context or a decision'],
  ['approval', 'Approval', 'Request permission to proceed'],
  ['blocked', 'Blocked', 'Escalate work that cannot continue'],
];

function identityKey(identity: DesktopFleetIdentity) {
  return String(identity.identity_id || identity.worker_id || identity.display_name || '');
}

function statusLabel(item: DesktopFleetLocalActivity) {
  if (item.activity_kind === 'delegation') {
    if (item.status === 'running') return 'IN PROGRESS';
    if (item.status === 'completed') return 'REPORT SENT';
  }
  if (item.status === 'sent') return 'WAITING';
  return item.status.replace(/_/g, ' ').toUpperCase();
}

export function DesktopFleetActivityPanel({
  snapshot,
  compact = false,
}: {
  snapshot: DesktopFleetSnapshot | null | undefined;
  compact?: boolean;
}) {
  const identities = snapshot?.identities || [];
  const [items, setItems] = useState<DesktopFleetLocalActivity[]>([]);
  const [selectedIdentityId, setSelectedIdentityId] = useState('');
  const [requestKind, setRequestKind] = useState<RequestKind>('question');
  const [requestMessage, setRequestMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const result = await loadDesktopFleetLocalActivity();
      setItems(Array.isArray(result?.items) ? result?.items || [] : []);
      setError(null);
    } catch (activityError) {
      if (!quiet) setError(userFacingError(activityError, 'Local Fleet activity could not be loaded.'));
    } finally {
      if (!quiet) setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    const timer = globalThis.setInterval(() => void refresh(true), 8000);
    return () => globalThis.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (selectedIdentityId && identities.some((identity) => identityKey(identity) === selectedIdentityId)) return;
    const manager = identities.find((identity) => identity.role === 'manager');
    const first = manager || identities[0];
    if (first) setSelectedIdentityId(identityKey(first));
  }, [identities.map(identityKey).join('|'), selectedIdentityId]);

  const selectedIdentity = identities.find((identity) => identityKey(identity) === selectedIdentityId) || identities[0] || null;
  const delegations = useMemo(() => items.filter((item) => item.activity_kind === 'delegation'), [items]);
  const requests = useMemo(() => items.filter((item) => item.activity_kind === 'request'), [items]);
  const activeCount = delegations.filter((item) => item.status === 'running' || item.status === 'queued').length;
  const waitingCount = requests.filter((item) => item.status === 'queued' || item.status === 'sent').length;

  const submitRequest = async () => {
    if (!requestMessage.trim() || !selectedIdentity) return;
    setSending(true);
    setError(null);
    setMessage(null);
    try {
      await requestDesktopFleetManager({
        requestKind,
        identityId: identityKey(selectedIdentity),
        identityLabel: selectedIdentity.display_name,
        message: requestMessage,
      });
      setRequestMessage('');
      setMessage('Request queued for the manager above. It will send automatically over the active Yggdrasil connection.');
      await refresh(true);
    } catch (requestError) {
      setError(userFacingError(requestError, 'The manager request could not be queued.'));
    } finally {
      setSending(false);
    }
  };

  return (
    <View style={[styles.panel, compact ? styles.panelCompact : null]}>
      <View style={styles.header}>
        <View style={styles.headerCopy}>
          <Text style={styles.eyebrow}>ACTIVITY FROM ABOVE</Text>
          <Text style={styles.title}>Work on this computer</Text>
          <Text style={styles.detail}>Incoming delegations run against identities stored here. Reports and requests cross the private connection; local conversations and files do not.</Text>
        </View>
        <Pressable accessibilityRole="button" accessibilityLabel="Refresh local Fleet activity" disabled={loading} onPress={() => void refresh()} style={styles.refreshButton}>
          <Text style={styles.refreshButtonText}>{loading ? 'Checking…' : 'Refresh'}</Text>
        </Pressable>
      </View>

      <View style={styles.summaryRow}>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryValue}>{activeCount}</Text>
          <Text style={styles.summaryLabel}>ACTIVE DELEGATIONS</Text>
        </View>
        <View style={styles.summaryCard}>
          <Text style={[styles.summaryValue, waitingCount ? styles.summaryAttention : null]}>{waitingCount}</Text>
          <Text style={styles.summaryLabel}>WAITING ON MANAGER</Text>
        </View>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryValue}>{identities.length}</Text>
          <Text style={styles.summaryLabel}>LOCAL IDENTITIES</Text>
        </View>
      </View>

      <View style={styles.columns}>
        <View style={styles.column}>
          <Text style={styles.sectionEyebrow}>INCOMING DELEGATIONS</Text>
          <Text style={styles.sectionTitle}>Assigned from the manager above</Text>
          {delegations.length ? delegations.slice(0, 12).map((item) => (
            <View key={item.activity_id} style={[styles.activityCard, item.status === 'failed' ? styles.activityError : null]}>
              <View style={styles.activityHeader}>
                <Text style={styles.activityIdentity}>{item.identity_label || 'Main identity'}</Text>
                <Text style={styles.activityStatus}>{statusLabel(item)}</Text>
              </View>
              <Text style={styles.activityMessage}>{item.message}</Text>
              {item.report && Object.keys(item.report).length ? (
                <Text style={styles.activityReport}>{String(item.report.summary || item.report.next_suggested_action || 'Report recorded.')}</Text>
              ) : null}
              <Text style={styles.activityTime}>{item.updated_at ? new Date(item.updated_at).toLocaleString() : 'Just now'}</Text>
            </View>
          )) : (
            <View style={styles.emptyState}>
              <Text style={styles.emptyTitle}>No delegations yet</Text>
              <Text style={styles.emptyText}>When the manager above sends work to an identity here, its progress and report will appear in this list.</Text>
            </View>
          )}
        </View>

        <View style={styles.column}>
          <Text style={styles.sectionEyebrow}>REQUEST THE MANAGER</Text>
          <Text style={styles.sectionTitle}>Escalate without exposing the local chat</Text>
          <Text style={styles.inputLabel}>From identity</Text>
          <View style={styles.identityList}>
            {identities.map((identity) => {
              const key = identityKey(identity);
              const selected = key === selectedIdentityId;
              return (
                <Pressable
                  key={key}
                  accessibilityRole="radio"
                  accessibilityState={{ checked: selected }}
                  onPress={() => setSelectedIdentityId(key)}
                  style={[styles.identityButton, selected ? styles.identityButtonSelected : null]}
                >
                  <Text style={[styles.identityName, selected ? styles.identityNameSelected : null]}>{identity.display_name}</Text>
                  <Text style={styles.identityRole}>{identity.role === 'manager' ? 'MAIN' : 'AGENT'}</Text>
                </Pressable>
              );
            })}
          </View>
          <Text style={styles.inputLabel}>Request type</Text>
          <View style={styles.kindList}>
            {requestKinds.map(([kind, label, hint]) => {
              const selected = requestKind === kind;
              return (
                <Pressable
                  key={kind}
                  accessibilityRole="radio"
                  accessibilityState={{ checked: selected }}
                  onPress={() => setRequestKind(kind)}
                  style={[styles.kindButton, selected ? styles.kindButtonSelected : null]}
                >
                  <Text style={[styles.kindName, selected ? styles.kindNameSelected : null]}>{label}</Text>
                  <Text style={styles.kindHint}>{hint}</Text>
                </Pressable>
              );
            })}
          </View>
          <Text style={styles.inputLabel}>Message to the manager above</Text>
          <TextInput
            accessibilityLabel="Request message to the manager above"
            multiline
            value={requestMessage}
            onChangeText={setRequestMessage}
            placeholder="State what is needed, why, and what remains blocked."
            placeholderTextColor={UI.color.textSubtle}
            style={[styles.input, styles.messageInput]}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: sending || !selectedIdentity || !requestMessage.trim() }}
            disabled={sending || !selectedIdentity || !requestMessage.trim()}
            onPress={() => void submitRequest()}
            style={[styles.primaryButton, (sending || !selectedIdentity || !requestMessage.trim()) ? styles.disabled : null]}
          ><Text style={styles.primaryButtonText}>{sending ? 'Queueing…' : `Send ${requestKind}`}</Text></Pressable>
        </View>
      </View>

      {requests.length ? (
        <View style={styles.requestHistory}>
          <Text style={styles.sectionEyebrow}>REQUEST HISTORY</Text>
          <View style={styles.requestGrid}>
            {requests.slice(0, 12).map((item) => (
              <View key={item.activity_id} style={[styles.requestCard, item.request_kind === 'blocked' ? styles.requestBlocked : null]}>
                <View style={styles.activityHeader}>
                  <Text style={styles.requestKind}>{String(item.request_kind || 'request').toUpperCase()}</Text>
                  <Text style={styles.activityStatus}>{statusLabel(item)}</Text>
                </View>
                <Text style={styles.activityIdentity}>{item.identity_label || 'Local identity'}</Text>
                <Text style={styles.activityMessage}>{item.message}</Text>
                {item.response ? <Text style={styles.response}>Manager: {item.response}</Text> : null}
              </View>
            ))}
          </View>
        </View>
      ) : null}

      {error || message ? (
        <View style={[styles.notice, error ? styles.noticeError : null]} accessibilityLiveRegion="polite">
          <Text style={error ? styles.noticeErrorText : styles.noticeText}>{error || message}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { padding: 18, gap: 14, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.large, backgroundColor: UI.color.surface },
  panelCompact: { padding: 14 },
  header: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 },
  headerCopy: { flex: 1, minWidth: 240 },
  eyebrow: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: 9, fontWeight: '900', letterSpacing: 1.1 },
  title: { marginTop: 5, color: UI.color.text, fontSize: 17, fontWeight: '900' },
  detail: { marginTop: 5, maxWidth: 720, color: UI.color.textMuted, fontSize: 10, lineHeight: 16 },
  refreshButton: { minHeight: 44, paddingHorizontal: 13, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.control, alignItems: 'center', justifyContent: 'center' },
  refreshButtonText: { color: UI.color.textMuted, fontSize: 9, fontWeight: '800' },
  summaryRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  summaryCard: { flexGrow: 1, flexBasis: 145, minWidth: 125, padding: 11, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.control, backgroundColor: UI.color.canvas },
  summaryValue: { color: UI.color.text, fontFamily: UI.type.mono, fontSize: 18, fontWeight: '900' },
  summaryAttention: { color: UI.color.warning },
  summaryLabel: { marginTop: 3, color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: 7, fontWeight: '900', letterSpacing: 0.6 },
  columns: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  column: { flexGrow: 1, flexBasis: 340, minWidth: 280, padding: 13, gap: 9, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.panel, backgroundColor: UI.color.canvas },
  sectionEyebrow: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: 8, fontWeight: '900', letterSpacing: 0.9 },
  sectionTitle: { color: UI.color.text, fontSize: 11, fontWeight: '800' },
  activityCard: { padding: 10, gap: 6, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.control, backgroundColor: UI.color.surface },
  activityError: { borderColor: UI.color.danger, backgroundColor: UI.color.dangerSoft },
  activityHeader: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 },
  activityIdentity: { flex: 1, color: UI.color.text, fontSize: 9, fontWeight: '800' },
  activityStatus: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: 7, fontWeight: '900' },
  activityMessage: { color: UI.color.textMuted, fontSize: 9, lineHeight: 14 },
  activityReport: { paddingTop: 6, borderTopWidth: 1, borderColor: UI.color.border, color: UI.color.textSubtle, fontSize: 9, lineHeight: 14 },
  activityTime: { color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: 7 },
  emptyState: { padding: 12, borderWidth: 1, borderStyle: 'dashed', borderColor: UI.color.border, borderRadius: UI.radius.control },
  emptyTitle: { color: UI.color.text, fontSize: 10, fontWeight: '800' },
  emptyText: { marginTop: 4, color: UI.color.textSubtle, fontSize: 9, lineHeight: 14 },
  inputLabel: { color: UI.color.textMuted, fontSize: 9, fontWeight: '800' },
  identityList: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  identityButton: { minHeight: 48, paddingHorizontal: 10, paddingVertical: 7, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.control, justifyContent: 'center' },
  identityButtonSelected: { borderColor: UI.color.accentBorder, backgroundColor: UI.color.accentSoft },
  identityName: { color: UI.color.textMuted, fontSize: 9, fontWeight: '800' },
  identityNameSelected: { color: UI.color.accentStrong },
  identityRole: { marginTop: 2, color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: 7, fontWeight: '900' },
  kindList: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  kindButton: { flexGrow: 1, flexBasis: 105, minHeight: 58, padding: 8, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.control },
  kindButtonSelected: { borderColor: UI.color.accentBorder, backgroundColor: UI.color.accentSoft },
  kindName: { color: UI.color.textMuted, fontSize: 9, fontWeight: '900' },
  kindNameSelected: { color: UI.color.accentStrong },
  kindHint: { marginTop: 3, color: UI.color.textSubtle, fontSize: 8, lineHeight: 12 },
  input: { minHeight: 44, paddingHorizontal: 11, paddingVertical: 9, borderWidth: 1, borderColor: UI.color.borderStrong, borderRadius: UI.radius.control, backgroundColor: UI.color.surface, color: UI.color.text, fontSize: 10 },
  messageInput: { minHeight: 88, textAlignVertical: 'top' },
  primaryButton: { minHeight: 44, paddingHorizontal: 12, borderRadius: UI.radius.control, backgroundColor: UI.color.accent, alignItems: 'center', justifyContent: 'center' },
  primaryButtonText: { color: UI.color.accentInk, fontSize: 10, fontWeight: '900' },
  disabled: { opacity: 0.4 },
  requestHistory: { gap: 9 },
  requestGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  requestCard: { flexGrow: 1, flexBasis: 245, minWidth: 220, maxWidth: 390, padding: 10, gap: 6, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.control, backgroundColor: UI.color.canvas },
  requestBlocked: { borderColor: UI.color.warning },
  requestKind: { color: UI.color.warning, fontFamily: UI.type.mono, fontSize: 8, fontWeight: '900' },
  response: { paddingTop: 6, borderTopWidth: 1, borderColor: UI.color.border, color: UI.color.accentStrong, fontSize: 9, lineHeight: 14 },
  notice: { padding: 10, borderWidth: 1, borderColor: UI.color.accentBorder, borderRadius: UI.radius.control, backgroundColor: UI.color.accentSoft },
  noticeError: { borderColor: UI.color.danger, backgroundColor: UI.color.dangerSoft },
  noticeText: { color: UI.color.textMuted, fontSize: 9 },
  noticeErrorText: { color: UI.color.danger, fontSize: 9, fontWeight: '700' },
});
