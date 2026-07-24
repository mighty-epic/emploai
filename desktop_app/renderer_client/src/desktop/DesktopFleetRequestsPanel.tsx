import { useMemo, useState } from 'react';
import ChevronDown from 'lucide-react-native/icons/chevron-down';
import ChevronUp from 'lucide-react-native/icons/chevron-up';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import type { DesktopFleetUpstreamRequest } from '@/lib/desktopBridge';
import { FLEET_TYPE as TYPE } from './desktopFleetUi';
import { DESKTOP_UI as UI } from './desktopUiTokens';
import { useFleetAutoDisclosure } from './useFleetAutoDisclosure';

type Decision = 'approved' | 'denied' | 'replied';

export function DesktopFleetRequestsPanel({
  desktopId,
  requests,
  busy,
  onDecision,
}: {
  desktopId: string;
  requests: DesktopFleetUpstreamRequest[];
  busy: boolean;
  onDecision: (requestId: string, decision: Decision, response?: string | null) => Promise<boolean>;
}) {
  const [replyDrafts, setReplyDrafts] = useState<Record<string, string>>({});
  const recent = requests.slice(0, 8);
  const pendingCount = recent.filter((request) => request.status === 'pending').length;
  const signature = useMemo(
    () => recent.map((request) => [
      request.request_id,
      request.status,
      request.response || '',
      request.updated_at || request.decided_at || request.created_at || '',
    ].join(':')).join('|'),
    [recent],
  );
  const { expanded, toggle } = useFleetAutoDisclosure({
    scopeKey: desktopId,
    activitySignature: signature,
    hasLiveActivity: pendingCount > 0,
  });
  const summary = pendingCount
    ? `${pendingCount} need${pendingCount === 1 ? 's' : ''} attention`
    : recent.length
      ? `${recent.length} recent · nothing pending`
      : 'Nothing needs attention';

  return (
    <View style={styles.section}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded }}
        accessibilityLabel={`Questions, approvals, and blockers. ${summary}`}
        onPress={toggle}
        style={styles.summary}
      >
        <View style={styles.summaryCopy}>
          <Text style={styles.title}>Requests</Text>
          <Text style={[styles.summaryText, pendingCount ? styles.summaryAttention : null]}>{summary}</Text>
        </View>
        <View style={styles.disclosure}>
          <Text style={styles.disclosureText}>{expanded ? 'Hide' : 'Show'}</Text>
          {expanded
            ? <ChevronUp size={16} color={UI.color.accentStrong} strokeWidth={2} />
            : <ChevronDown size={16} color={UI.color.accentStrong} strokeWidth={2} />}
        </View>
      </Pressable>

      {expanded ? (
        <View style={styles.requestList}>
          {recent.length ? recent.map((request) => {
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
                    <View style={styles.actions}>
                      <Pressable accessibilityRole="button" disabled={busy} onPress={() => void onDecision(request.request_id, 'approved', reply)} style={styles.approveButton}>
                        <Text style={styles.approveButtonText}>Approve</Text>
                      </Pressable>
                      <Pressable accessibilityRole="button" disabled={busy} onPress={() => void onDecision(request.request_id, 'denied', reply)} style={styles.denyButton}>
                        <Text style={styles.denyButtonText}>Deny</Text>
                      </Pressable>
                      <Pressable
                        accessibilityRole="button"
                        disabled={busy || !reply.trim()}
                        onPress={() => void onDecision(request.request_id, 'replied', reply)}
                        style={[styles.replyButton, !reply.trim() ? styles.disabled : null]}
                      >
                        <Text style={styles.replyButtonText}>Reply</Text>
                      </Pressable>
                    </View>
                  </>
                ) : null}
              </View>
            );
          }) : <Text style={styles.empty}>New requests from this computer will open this panel automatically.</Text>}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { width: '100%', overflow: 'hidden', borderRadius: UI.radius.control, backgroundColor: UI.color.surfaceMuted },
  summary: { minHeight: 62, paddingHorizontal: 12, paddingVertical: 9, flexDirection: 'row', alignItems: 'center', gap: 12 },
  summaryCopy: { flex: 1, minWidth: 0, gap: 4 },
  title: { color: UI.color.text, fontSize: TYPE.sectionTitle, fontWeight: '800' },
  summaryText: { color: UI.color.textSubtle, fontSize: TYPE.meta },
  summaryAttention: { color: UI.color.warning, fontWeight: '800' },
  disclosure: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  disclosureText: { color: UI.color.accentStrong, fontSize: TYPE.meta, fontWeight: '800' },
  requestList: { paddingHorizontal: 14, paddingBottom: 10 },
  requestCard: { paddingVertical: 11, gap: 6 },
  requestBlocked: { borderLeftWidth: 2, borderLeftColor: UI.color.danger, paddingLeft: 9 },
  requestHeader: { flexDirection: 'row', justifyContent: 'space-between', gap: 8 },
  requestKind: { color: UI.color.warning, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  requestStatus: { color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  requestIdentity: { color: UI.color.text, fontSize: TYPE.body, fontWeight: '900' },
  requestMessage: { color: UI.color.textMuted, fontSize: TYPE.body, lineHeight: TYPE.bodyLine },
  responseText: { color: UI.color.accentStrong, fontSize: TYPE.body },
  input: { minHeight: 39, paddingHorizontal: 11, borderWidth: 1, borderColor: UI.color.borderStrong, borderRadius: UI.radius.control, color: UI.color.text, backgroundColor: UI.color.surface },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  approveButton: { minHeight: 36, paddingHorizontal: 11, borderRadius: UI.radius.control, backgroundColor: UI.color.successSoft, alignItems: 'center', justifyContent: 'center' },
  approveButtonText: { color: UI.color.success, fontSize: TYPE.body, fontWeight: '900' },
  denyButton: { minHeight: 36, paddingHorizontal: 11, borderRadius: UI.radius.control, backgroundColor: UI.color.dangerSoft, alignItems: 'center', justifyContent: 'center' },
  denyButtonText: { color: UI.color.danger, fontSize: TYPE.body, fontWeight: '900' },
  replyButton: { minHeight: 36, paddingHorizontal: 11, borderRadius: UI.radius.control, backgroundColor: UI.color.accentSoft, alignItems: 'center', justifyContent: 'center' },
  replyButtonText: { color: UI.color.accentStrong, fontSize: TYPE.body, fontWeight: '900' },
  empty: { paddingVertical: 12, color: UI.color.textSubtle, fontSize: TYPE.body },
  disabled: { opacity: 0.4 },
});
