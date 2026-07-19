import { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  decideDesktopFleetUpstreamRequest,
  type DesktopFleetUpstreamRequest,
  type DesktopFleetSnapshot,
} from '@/lib/desktopBridge';
import {
  redirectFleetComputerDelegation,
  redirectFleetTask,
  stopFleetComputerDelegation,
  stopFleetWorker,
  updateFleetTaskStatus,
} from '@/lib/appApi';
import { DESKTOP_UI as UI } from './desktopUiTokens';

type Props = {
  apiBaseUrl: string;
  token: string;
  managerSessionId?: string | null;
  snapshot?: DesktopFleetSnapshot | null;
  onChanged?: () => void | Promise<void>;
};

type Card = {
  id: string;
  kind: 'local' | 'child';
  state: string;
  prompt: string;
  route: Record<string, any>;
  metadata: Record<string, any>;
  workerId?: string | null;
  report?: Record<string, any> | null;
  createdAt?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
  requests: CardRequest[];
};

type CardRequest = DesktopFleetUpstreamRequest & {
  transport: 'local' | 'child';
};

const ACTIVE_STATES = new Set(['queued', 'running', 'paused', 'blocked', 'needs_review']);

function routeLabel(card: Card) {
  const computer = String(card.route.computer_name || (card.kind === 'local' ? 'This computer' : 'Child computer'));
  const identity = String(card.route.identity_name || (card.kind === 'local' ? 'Default worker' : 'Worker'));
  return card.kind === 'local' ? `Manager → ${computer} → ${identity}` : `Manager → ${computer} → ${identity}`;
}

function evidenceLabel(value: unknown) {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object') {
    const item = value as Record<string, any>;
    return String(item.title || item.label || item.path || item.url || item.message || item.detail || JSON.stringify(item));
  }
  return String(value ?? '');
}

function TaskCard({
  card,
  apiBaseUrl,
  token,
  onChanged,
}: {
  card: Card;
  apiBaseUrl: string;
  token: string;
  onChanged?: () => void | Promise<void>;
}) {
  const [redirect, setRedirect] = useState('');
  const [busy, setBusy] = useState<'stop' | 'redirect' | null>(null);
  const [error, setError] = useState('');
  const active = ACTIVE_STATES.has(card.state);
  const report = card.report || null;
  const evidence = [...(report?.evidence || []), ...(report?.artifacts || [])];
  const blockers = report?.blockers || [];

  const stop = async () => {
    if (!active || busy) return;
    setBusy('stop');
    setError('');
    try {
      if (card.kind === 'child') {
        await stopFleetComputerDelegation(apiBaseUrl, token, card.id, 'Stopped from the manager task card.');
      } else if (card.state === 'queued') {
        await updateFleetTaskStatus(apiBaseUrl, token, card.id, 'canceled', { source: 'desktop_task_card' });
      } else if (card.workerId) {
        await stopFleetWorker(apiBaseUrl, token, card.workerId, 'Stopped from the manager task card.', { task_id: card.id });
      }
      await onChanged?.();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'The task could not be stopped.');
    } finally {
      setBusy(null);
    }
  };

  const sendRedirect = async () => {
    const direction = redirect.trim();
    if (!active || !direction || busy) return;
    setBusy('redirect');
    setError('');
    try {
      if (card.kind === 'child') {
        await redirectFleetComputerDelegation(apiBaseUrl, token, card.id, direction);
      } else {
        await redirectFleetTask(apiBaseUrl, token, card.id, direction, { source: 'desktop_task_card' });
      }
      setRedirect('');
      await onChanged?.();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'The redirect could not be delivered.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <View style={styles.headerCopy}>
          <Text style={styles.eyebrow}>Delegated task</Text>
          <Text style={styles.route}>{routeLabel(card)}</Text>
        </View>
        <View style={[styles.stateBadge, active ? styles.stateBadgeActive : null]}>
          <Text style={[styles.stateText, active ? styles.stateTextActive : null]}>{card.state.replace(/_/g, ' ')}</Text>
        </View>
      </View>

      <Text style={styles.prompt}>{card.prompt}</Text>
      <View style={styles.milestoneRow}>
        <Text style={styles.milestone}>Created</Text>
        {card.state !== 'queued' ? <Text style={styles.milestone}>Accepted</Text> : null}
        {card.state === 'running' ? <Text style={[styles.milestone, styles.milestoneActive]}>Working</Text> : null}
        {!active ? <Text style={styles.milestone}>Reported</Text> : null}
      </View>

      {report?.summary ? (
        <View style={styles.reportBlock}>
          <Text style={styles.reportEyebrow}>Worker report</Text>
          <Text style={styles.reportSummary}>{String(report.summary)}</Text>
          <Text style={styles.reportMeta}>
            {String(report.confidence || 'unrated')} confidence · {evidence.length} evidence · {blockers.length} blockers
          </Text>
          {evidence.length ? (
            <View style={styles.detailList}>
              {evidence.slice(0, 5).map((item, index) => (
                <Text key={`evidence-${index}`} style={styles.detailText}>Evidence · {evidenceLabel(item)}</Text>
              ))}
            </View>
          ) : null}
          {blockers.length ? (
            <View style={styles.detailList}>
              {blockers.slice(0, 5).map((item: unknown, index: number) => (
                <Text key={`blocker-${index}`} style={styles.blockerText}>Blocker · {evidenceLabel(item)}</Text>
              ))}
            </View>
          ) : null}
          {report.next_suggested_action ? (
            <Text style={styles.nextAction}>Next · {String(report.next_suggested_action)}</Text>
          ) : null}
        </View>
      ) : null}

      {card.requests.length ? (
        <View style={styles.requestList}>
          {card.requests.map((request) => (
            <ManagerRequest
              key={request.request_id}
              card={card}
              request={request}
              apiBaseUrl={apiBaseUrl}
              token={token}
              onChanged={onChanged}
            />
          ))}
        </View>
      ) : null}

      {active ? (
        <View style={styles.controls}>
          <TextInput
            value={redirect}
            onChangeText={setRedirect}
            placeholder="Redirect this task…"
            placeholderTextColor="#73849c"
            style={styles.redirectInput}
            editable={!busy}
          />
          <Pressable
            style={[styles.redirectButton, (!redirect.trim() || busy) ? styles.buttonDisabled : null]}
            disabled={!redirect.trim() || Boolean(busy)}
            onPress={() => void sendRedirect()}
          >
            <Text style={styles.redirectButtonText}>{busy === 'redirect' ? 'Sending…' : 'Redirect'}</Text>
          </Pressable>
          <Pressable
            style={[styles.stopButton, busy ? styles.buttonDisabled : null]}
            disabled={Boolean(busy)}
            onPress={() => void stop()}
          >
            <Text style={styles.stopButtonText}>{busy === 'stop' ? 'Stopping…' : 'Stop'}</Text>
          </Pressable>
        </View>
      ) : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

function ManagerRequest({
  card,
  request,
  apiBaseUrl,
  token,
  onChanged,
}: {
  card: Card;
  request: CardRequest;
  apiBaseUrl: string;
  token: string;
  onChanged?: () => void | Promise<void>;
}) {
  const [response, setResponse] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pending = request.status === 'pending';

  const decide = async (decision: 'approved' | 'denied' | 'replied') => {
    if (!pending || busy) return;
    const reply = response.trim();
    if (decision === 'replied' && !reply) return;
    setBusy(true);
    setError('');
    try {
      if (request.transport === 'child') {
        await decideDesktopFleetUpstreamRequest(request.desktop_id, request.request_id, decision, reply || null);
      } else {
        const decidedAt = new Date().toISOString();
        const managerRequests = card.requests
          .filter((item) => item.transport === 'local')
          .map((item) => item.request_id === request.request_id
            ? { ...item, status: decision, response: reply || null, decided_at: decidedAt }
            : item)
          .map(({ transport: _transport, desktop_id: _desktopId, ...item }) => item);
        const direction = [
          `Manager ${decision} the ${request.request_kind} request.`,
          reply ? `Response: ${reply}` : '',
        ].filter(Boolean).join(' ');
        await updateFleetTaskStatus(apiBaseUrl, token, card.id, 'running', { manager_requests: managerRequests });
        await redirectFleetTask(apiBaseUrl, token, card.id, direction, { source: 'desktop_task_card_request' });
      }
      setResponse('');
      await onChanged?.();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'The manager response could not be delivered.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.requestBlock}>
      <View style={styles.requestHeader}>
        <Text style={styles.requestKind}>{request.request_kind.replace(/_/g, ' ')}</Text>
        <Text style={[styles.requestStatus, pending ? styles.requestStatusPending : null]}>{request.status}</Text>
      </View>
      <Text style={styles.requestMessage}>{request.message}</Text>
      {request.response ? <Text style={styles.requestResponse}>Manager · {request.response}</Text> : null}
      {pending ? (
        <View style={styles.requestControls}>
          <TextInput
            value={response}
            onChangeText={setResponse}
            placeholder="Manager response…"
            placeholderTextColor="#73849c"
            style={styles.requestInput}
            editable={!busy}
          />
          {request.request_kind === 'approval' ? (
            <>
              <Pressable style={[styles.approveButton, busy ? styles.buttonDisabled : null]} disabled={busy} onPress={() => void decide('approved')}>
                <Text style={styles.approveButtonText}>Approve</Text>
              </Pressable>
              <Pressable style={[styles.denyButton, busy ? styles.buttonDisabled : null]} disabled={busy} onPress={() => void decide('denied')}>
                <Text style={styles.denyButtonText}>Deny</Text>
              </Pressable>
            </>
          ) : (
            <Pressable style={[styles.redirectButton, (!response.trim() || busy) ? styles.buttonDisabled : null]} disabled={!response.trim() || busy} onPress={() => void decide('replied')}>
              <Text style={styles.redirectButtonText}>Reply</Text>
            </Pressable>
          )}
        </View>
      ) : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

export function DesktopManagerTaskCards({ apiBaseUrl, token, managerSessionId, snapshot, onChanged }: Props) {
  const cards = useMemo<Card[]>(() => {
    const sessionId = String(managerSessionId || '').trim();
    if (!sessionId || !snapshot) return [];
    const reportsByTask = new Map((snapshot.reports || []).map((report) => [report.task_id, report]));
    const upstreamRequests = snapshot.upstream_requests || [];
    const localCards: Card[] = (snapshot.tasks || [])
      .filter((task) => String((task.metadata || {}).origin_manager_session_id || '') === sessionId)
      .map((task: any) => ({
        id: task.task_id,
        kind: 'local',
        state: String(task.status || 'queued'),
        prompt: String(task.prompt || ''),
        route: (task.metadata || {}).route || {},
        metadata: task.metadata || {},
        workerId: task.worker_id,
        report: reportsByTask.get(task.task_id) as any,
        createdAt: task.created_at,
        startedAt: task.started_at,
        completedAt: task.completed_at,
        requests: (Array.isArray((task.metadata || {}).manager_requests) ? (task.metadata || {}).manager_requests : [])
          .map((request: any) => ({
            ...request,
            desktop_id: 'local',
            task_id: task.task_id,
            transport: 'local' as const,
          })),
      }));
    const childCards: Card[] = (snapshot.delegations || [])
      .filter((delegation) => String((delegation.metadata || {}).origin_manager_session_id || '') === sessionId)
      .map((delegation: any) => ({
        id: delegation.delegation_id,
        kind: 'child',
        state: String(delegation.status || 'queued'),
        prompt: String(delegation.prompt || ''),
        route: (delegation.metadata || {}).route || {
          computer_id: delegation.desktop_id,
          identity_name: delegation.target_selector || delegation.target_kind,
          identity_role: delegation.target_kind,
        },
        metadata: delegation.metadata || {},
        report: delegation.report || null,
        createdAt: delegation.created_at,
        startedAt: delegation.started_at,
        completedAt: delegation.completed_at,
        requests: upstreamRequests
          .filter((request) => String(request.task_id || '') === String(delegation.delegation_id || ''))
          .map((request) => ({ ...request, transport: 'child' as const })),
      }));
    return [...localCards, ...childCards].sort((a, b) => String(a.createdAt || '').localeCompare(String(b.createdAt || '')));
  }, [managerSessionId, snapshot]);

  if (!cards.length) return null;
  return (
    <View style={styles.list}>
      {cards.map((card) => (
        <TaskCard key={`${card.kind}-${card.id}`} card={card} apiBaseUrl={apiBaseUrl} token={token} onChanged={onChanged} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: 12, width: '100%' },
  card: { borderWidth: 0, borderRadius: 10, backgroundColor: UI.color.surfaceMuted, padding: 14, gap: 11 },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 },
  headerCopy: { flex: 1, minWidth: 0 },
  eyebrow: { color: '#60d4e5', fontSize: 10, fontWeight: '800', letterSpacing: 1.2, textTransform: 'uppercase' },
  route: { color: '#edf6fb', fontSize: 13, fontWeight: '800', marginTop: 3 },
  stateBadge: { borderWidth: 0, borderRadius: 999, paddingHorizontal: 9, paddingVertical: 4, backgroundColor: UI.color.surfaceRaised },
  stateBadgeActive: { backgroundColor: UI.color.accentSoft },
  stateText: { color: '#a9b5c5', fontSize: 10, fontWeight: '800', textTransform: 'uppercase' },
  stateTextActive: { color: '#93edf3' },
  prompt: { color: '#cbd5e2', fontSize: 13, lineHeight: 19 },
  milestoneRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  milestone: { color: '#8e9caf', fontSize: 10, fontWeight: '700', borderLeftWidth: 2, borderLeftColor: '#536277', paddingLeft: 6 },
  milestoneActive: { color: '#7ee8ef', borderLeftColor: '#49d2df' },
  reportBlock: { borderTopWidth: 1, borderTopColor: '#25384d', paddingTop: 10, gap: 6 },
  reportEyebrow: { color: '#8fa4bb', fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.9 },
  reportSummary: { color: '#e2e9f2', fontSize: 13, lineHeight: 19 },
  reportMeta: { color: '#7f91a7', fontSize: 10 },
  detailList: { gap: 3 },
  detailText: { color: '#aebdcd', fontSize: 11 },
  blockerText: { color: '#ffb1ab', fontSize: 11 },
  nextAction: { color: '#8fdce7', fontSize: 11 },
  requestList: { borderTopWidth: 1, borderTopColor: '#25384d', paddingTop: 10, gap: 8 },
  requestBlock: { borderWidth: 0, borderRadius: 9, backgroundColor: UI.color.warningSoft, padding: 10, gap: 7 },
  requestHeader: { flexDirection: 'row', justifyContent: 'space-between', gap: 10 },
  requestKind: { color: '#ffd88d', fontSize: 10, fontWeight: '900', textTransform: 'uppercase', letterSpacing: 0.8 },
  requestStatus: { color: '#96a4b6', fontSize: 10, fontWeight: '800', textTransform: 'uppercase' },
  requestStatusPending: { color: '#ffd88d' },
  requestMessage: { color: '#e7dfcf', fontSize: 12, lineHeight: 18 },
  requestResponse: { color: '#9fdde4', fontSize: 11, lineHeight: 16 },
  requestControls: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  requestInput: { flex: 1, minHeight: 34, borderWidth: 1, borderColor: '#4d4638', borderRadius: 7, backgroundColor: '#0e1117', color: '#edf4fb', paddingHorizontal: 9, paddingVertical: 6, fontSize: 11 },
  approveButton: { minHeight: 34, justifyContent: 'center', borderRadius: 7, backgroundColor: '#6bd6aa', paddingHorizontal: 10 },
  approveButtonText: { color: '#07140f', fontSize: 10, fontWeight: '900' },
  denyButton: { minHeight: 34, justifyContent: 'center', borderWidth: 0, borderRadius: 7, backgroundColor: UI.color.dangerSoft, paddingHorizontal: 10 },
  denyButtonText: { color: '#ffb5b0', fontSize: 10, fontWeight: '900' },
  controls: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  redirectInput: { flex: 1, minHeight: 36, borderWidth: 1, borderColor: '#33485f', borderRadius: 8, backgroundColor: '#09121d', color: '#edf4fb', paddingHorizontal: 10, paddingVertical: 7, fontSize: 12 },
  redirectButton: { minHeight: 36, justifyContent: 'center', borderRadius: 8, backgroundColor: '#54cfe0', paddingHorizontal: 12 },
  redirectButtonText: { color: '#041017', fontSize: 11, fontWeight: '900' },
  stopButton: { minHeight: 36, justifyContent: 'center', borderWidth: 0, borderRadius: 8, backgroundColor: UI.color.dangerSoft, paddingHorizontal: 12 },
  stopButtonText: { color: '#ffb5b0', fontSize: 11, fontWeight: '800' },
  buttonDisabled: { opacity: 0.45 },
  error: { color: '#ff9e99', fontSize: 11 },
});
