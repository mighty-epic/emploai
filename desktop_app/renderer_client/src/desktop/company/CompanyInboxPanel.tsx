import { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  continueFleetWorkerQueue,
  reviewCompanyReport,
  reviewCompanyHandoff,
  routeCompanyObjectiveAssignment,
  type CompanyObjective,
  type CompanyReport,
} from '@/lib/appApi';
import { formatRelativeTime } from '@/lib/time';
import { userFacingError } from '../../../lib/diagnostics';


type Props = {
  apiBaseUrl: string;
  token: string;
  companyId: string;
  requests: any[];
  blockedTasks: any[];
  reports: CompanyReport[];
  routineReports: Array<Record<string, any>>;
  objectives: CompanyObjective[];
  handoffs: Array<Record<string, unknown>>;
  approvals: Array<Record<string, unknown>>;
  incompleteEmployees: Array<Record<string, unknown>>;
  staleKnowledge: Array<Record<string, unknown>>;
  reviewerIdentityId?: string | null;
  onChanged: () => Promise<void>;
};

export function CompanyInboxPanel({
  apiBaseUrl,
  token,
  companyId,
  requests,
  blockedTasks,
  reports,
  routineReports,
  objectives,
  handoffs,
  approvals,
  incompleteEmployees,
  staleKnowledge,
  reviewerIdentityId,
  onChanged,
}: Props) {
  const [view, setView] = useState<'attention' | 'reports'>('attention');
  const submittedReports = reports.filter(
    (report) => report.review_status === 'awaiting_review',
  );
  const companyReportIds = new Set(reports.map((report) => report.report_id));
  const additionalReports = routineReports.filter(
    (report) => !companyReportIds.has(String(report.report_id || '')),
  );
  const allReportCount = reports.length + additionalReports.length;
  const pendingHandoffs = handoffs.filter(
    (handoff) => String(handoff.status || 'pending') === 'pending',
  );
  const pendingApprovals = approvals.filter(
    (approval) => ['pending', 'awaiting_review', 'needs_decision'].includes(String(approval.status || 'pending')),
  );
  const attentionCount = requests.length
    + blockedTasks.length
    + submittedReports.length
    + pendingHandoffs.length
    + pendingApprovals.length
    + incompleteEmployees.length
    + staleKnowledge.length;
  const empty = attentionCount === 0;

  return (
    <View style={styles.content}>
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>COMPANY ATTENTION</Text>
          <Text style={styles.title}>Inbox</Text>
        </View>
        <View style={styles.tabs}>
          <InboxTab label={`Attention · ${attentionCount}`} selected={view === 'attention'} onPress={() => setView('attention')} />
          <InboxTab label={`All reports · ${allReportCount}`} selected={view === 'reports'} onPress={() => setView('reports')} />
        </View>
      </View>
      {view === 'attention' && empty ? (
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>Nothing needs your decision</Text>
          <Text style={styles.emptyBody}>
            Approvals, blockers, failed work, and submitted results will appear here.
          </Text>
        </View>
      ) : null}
      {view === 'attention' && !empty ? (
        <View style={styles.list}>
          {pendingApprovals.map((approval) => (
            <AttentionRow
              key={String(approval.approval_id || approval.id)}
              title={String(approval.title || approval.summary || approval.action || 'Approval required')}
              meta={String(approval.reason || approval.scope || 'Company approval')}
              status={String(approval.status || 'pending')}
            />
          ))}
          {requests.map((request) => (
            <AttentionRow
              key={request.request_id}
              title={request.message}
              meta={`${request.request_kind} · ${formatRelativeTime(request.updated_at || request.created_at)}`}
              status={request.status}
            />
          ))}
          {blockedTasks.map((task) => (
            <AttentionRow
              key={task.task_id}
              title={task.prompt}
              meta="Assignment needs recovery"
              status={task.status}
            />
          ))}
          {submittedReports.map((report) => (
            <ReportReviewRow
              key={report.report_id}
              apiBaseUrl={apiBaseUrl}
              token={token}
              companyId={companyId}
              report={report}
              objective={objectives.find(
                (item) => item.objective_id === report.objective_id,
              )}
              onChanged={onChanged}
            />
          ))}
          {pendingHandoffs.map((handoff) => (
            <HandoffReviewRow
              key={String(handoff.handoff_id)}
              apiBaseUrl={apiBaseUrl}
              token={token}
              companyId={companyId}
              handoff={handoff}
              reviewerIdentityId={reviewerIdentityId}
              onChanged={onChanged}
            />
          ))}
          {incompleteEmployees.map((employee) => (
            <AttentionRow
              key={String(employee.employee_id || employee.identity_id)}
              title={`${String(employee.display_name || 'Employee')} is not ready for ordinary work`}
              meta="Finish the identity's job contract and readiness review in Workforce."
              status={String(employee.job_contract_status || 'setup_incomplete')}
            />
          ))}
          {staleKnowledge.map((item) => (
            <AttentionRow
              key={String(item.knowledge_id || item.id)}
              title={`${String(item.title || 'Company knowledge')} needs review`}
              meta={`Review date passed: ${String(item.review_due_at || 'unknown')}`}
              status="stale"
            />
          ))}
        </View>
      ) : null}
      {view === 'reports' ? (
        allReportCount ? (
          <View style={styles.list}>
            {[...reports]
              .sort((left, right) => String(right.submitted_at || '').localeCompare(String(left.submitted_at || '')))
              .map((report) => (
                report.review_status === 'awaiting_review' ? (
                  <ReportReviewRow
                    key={report.report_id}
                    apiBaseUrl={apiBaseUrl}
                    token={token}
                    companyId={companyId}
                    report={report}
                    objective={objectives.find((item) => item.objective_id === report.objective_id)}
                    onChanged={onChanged}
                  />
                ) : (
                  <AttentionRow
                    key={report.report_id}
                    title={report.summary}
                    meta={`${report.execution_status.replace(/_/g, ' ')} · ${report.evidence.length} evidence · ${formatRelativeTime(report.submitted_at)}`}
                    status={report.review_status}
                  />
                )
              ))}
            {additionalReports.map((report) => (
              <AttentionRow
                key={String(report.report_id || report.id)}
                title={String(report.summary || report.output || report.prompt || 'Company activity report')}
                meta={`${String(report.identity_name || report.worker_name || 'Company activity')} · ${formatRelativeTime(String(report.updated_at || report.created_at || ''))}`}
                status={String(report.status || 'informational')}
              />
            ))}
          </View>
        ) : (
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>No Company reports yet</Text>
            <Text style={styles.emptyBody}>Every structured employee report will remain available here after review.</Text>
          </View>
        )
      ) : null}
    </View>
  );
}

function HandoffReviewRow({
  apiBaseUrl,
  token,
  companyId,
  handoff,
  reviewerIdentityId,
  onChanged,
}: {
  apiBaseUrl: string;
  token: string;
  companyId: string;
  handoff: Record<string, unknown>;
  reviewerIdentityId?: string | null;
  onChanged: () => Promise<void>;
}) {
  const [reworkOpen, setReworkOpen] = useState(false);
  const [rework, setRework] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const decide = async (decision: 'accepted' | 'rework_requested') => {
    if (decision === 'rework_requested' && !rework.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await reviewCompanyHandoff(
        apiBaseUrl,
        token,
        companyId,
        String(handoff.handoff_id || ''),
        {
          reviewer_identity_id: reviewerIdentityId,
          decision,
          rationale: decision === 'accepted'
            ? 'The recipient or owning manager accepted the handoff.'
            : 'The handoff does not yet satisfy its acceptance criteria.',
          rework_instructions: decision === 'rework_requested' ? rework.trim() : null,
        },
      );
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, 'The handoff decision could not be saved.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.reportRow}>
      <View style={styles.reportHeader}>
        <View style={styles.reportCopy}>
          <Text style={styles.rowTitle}>{String(handoff.deliverable || 'Handoff')}</Text>
          <Text style={styles.rowMeta}>{String(handoff.acceptance_criteria || 'Acceptance criteria required')}</Text>
        </View>
        <Text style={styles.awaiting}>HANDOFF</Text>
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {reworkOpen ? (
        <View style={styles.reworkEditor}>
          <TextInput
            accessibilityLabel="Handoff rework instructions"
            multiline
            style={styles.input}
            value={rework}
            placeholder="State what the sender must correct"
            placeholderTextColor="#637a8e"
            onChangeText={setRework}
          />
          <View style={styles.actions}>
            <Action label="Cancel" disabled={saving} onPress={() => setReworkOpen(false)} />
            <Action label={saving ? 'Saving…' : 'Request rework'} primary disabled={saving || !rework.trim()} onPress={() => void decide('rework_requested')} />
          </View>
        </View>
      ) : (
        <View style={styles.actions}>
          <Action label="Request rework" disabled={saving} onPress={() => setReworkOpen(true)} />
          <Action label={saving ? 'Accepting…' : 'Accept handoff'} primary disabled={saving} onPress={() => void decide('accepted')} />
        </View>
      )}
    </View>
  );
}

function InboxTab({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable style={[styles.tab, selected ? styles.tabSelected : null]} onPress={onPress}>
      <Text style={[styles.tabText, selected ? styles.tabTextSelected : null]}>{label}</Text>
    </Pressable>
  );
}

function ReportReviewRow({
  apiBaseUrl,
  token,
  companyId,
  report,
  objective,
  onChanged,
}: {
  apiBaseUrl: string;
  token: string;
  companyId: string;
  report: CompanyReport;
  objective?: CompanyObjective;
  onChanged: () => Promise<void>;
}) {
  const [reworkOpen, setReworkOpen] = useState(false);
  const [rework, setRework] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const review = async (decision: 'accepted' | 'rework_requested') => {
    if (decision === 'rework_requested' && !rework.trim()) return;
    setSaving(true);
    setError(null);
    let reviewSaved = false;
    try {
      await reviewCompanyReport(apiBaseUrl, token, companyId, {
        report_id: report.report_id,
        objective_id: report.objective_id,
        decision,
        rationale: decision === 'accepted'
          ? 'The assigning manager reviewed the submitted result and accepted it.'
          : 'The submitted result does not yet satisfy the objective.',
        rework_instructions: decision === 'rework_requested' ? rework.trim() : null,
      });
      reviewSaved = true;
      if (decision === 'rework_requested') {
        if (!objective || !report.assignee_identity_id) {
          throw new Error(
            'The review was saved, but its original assignment route is unavailable.',
          );
        }
        await routeCompanyObjectiveAssignment(
          apiBaseUrl,
          token,
          companyId,
          objective,
          report.assignee_identity_id,
          rework.trim(),
          {
            continuationTaskId: report.task_id || report.delegation_id || null,
            reworkForReportId: report.report_id,
          },
        );
      }
      if (decision === 'accepted' && report.worker_id) {
        try {
          await continueFleetWorkerQueue(
            apiBaseUrl,
            token,
            report.worker_id,
            report.report_id,
            {
              company_id: companyId,
              objective_id: report.objective_id,
              source: 'company_report_review',
            },
          );
        } catch (reason) {
          setError(userFacingError(
            reason,
            'The report was accepted, but the worker queue still needs manual continuation.',
          ));
        }
      }
      await onChanged();
    } catch (reason) {
      setError(userFacingError(
        reason,
        reviewSaved
          ? 'The review was saved, but the follow-up work could not be routed.'
          : 'The report review could not be saved.',
      ));
      if (reviewSaved) await onChanged();
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.reportRow}>
      <View style={styles.reportHeader}>
        <View style={styles.reportCopy}>
          <Text style={styles.rowTitle}>{report.summary}</Text>
          <Text style={styles.rowMeta}>
            {report.execution_status.replace(/_/g, ' ')}
            {' · '}
            {report.evidence.length} evidence
            {' · '}
            {report.blockers.length} blockers
          </Text>
        </View>
        <Text style={styles.awaiting}>AWAITING REVIEW</Text>
      </View>
      {report.next_suggested_action ? (
        <Text style={styles.suggestion}>{report.next_suggested_action}</Text>
      ) : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {reworkOpen ? (
        <View style={styles.reworkEditor}>
          <TextInput
            accessibilityLabel="Rework instructions"
            multiline
            autoFocus
            style={styles.input}
            value={rework}
            placeholder="State the bounded revision required"
            placeholderTextColor="#637a8e"
            onChangeText={setRework}
          />
          <View style={styles.actions}>
            <Action label="Cancel" disabled={saving} onPress={() => setReworkOpen(false)} />
            <Action
              label={saving ? 'Sending…' : 'Request rework'}
              primary
              disabled={saving || !rework.trim()}
              onPress={() => void review('rework_requested')}
            />
          </View>
        </View>
      ) : (
        <View style={styles.actions}>
          <Action label="Request rework" disabled={saving} onPress={() => setReworkOpen(true)} />
          <Action
            label={saving ? 'Accepting…' : 'Accept result'}
            primary
            disabled={saving}
            onPress={() => void review('accepted')}
          />
        </View>
      )}
    </View>
  );
}

function AttentionRow({
  title,
  meta,
  status,
}: {
  title: string;
  meta: string;
  status: string;
}) {
  return (
    <View style={styles.attentionRow}>
      <View style={styles.reportCopy}>
        <Text style={styles.rowTitle} numberOfLines={2}>{title}</Text>
        <Text style={styles.rowMeta}>{meta}</Text>
      </View>
      <Text style={styles.status}>{status.replace(/_/g, ' ')}</Text>
    </View>
  );
}

function Action({
  label,
  primary,
  disabled,
  onPress,
}: {
  label: string;
  primary?: boolean;
  disabled: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      disabled={disabled}
      style={[
        styles.action,
        primary ? styles.actionPrimary : null,
        disabled ? styles.disabled : null,
      ]}
      onPress={onPress}
    >
      <Text style={[styles.actionText, primary ? styles.actionTextPrimary : null]}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 20, paddingTop: 18, gap: 14 },
  header: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 },
  tabs: { flexDirection: 'row', gap: 3 },
  tab: { paddingHorizontal: 9, paddingVertical: 7, borderRadius: 7, backgroundColor: '#101e29' },
  tabSelected: { backgroundColor: '#17313b' },
  tabText: { color: '#74899c', fontSize: 8, fontWeight: '800' },
  tabTextSelected: { color: '#78ddea' },
  eyebrow: { color: '#5fd3e5', fontSize: 8, fontWeight: '800', letterSpacing: 1.05 },
  title: { color: '#edf5fb', fontSize: 17, fontWeight: '800' },
  list: { borderTopWidth: 1, borderTopColor: '#1b2a39' },
  attentionRow: {
    minHeight: 58,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#172635',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  reportRow: {
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#172635',
    gap: 8,
  },
  reportHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  reportCopy: { flex: 1, minWidth: 0 },
  rowTitle: { color: '#e6eef6', fontSize: 12, lineHeight: 16, fontWeight: '700' },
  rowMeta: { color: '#70869c', fontSize: 9, marginTop: 3, textTransform: 'capitalize' },
  awaiting: { color: '#efc35e', fontSize: 8, fontWeight: '900', letterSpacing: 0.5 },
  status: { color: '#efc35e', fontSize: 8, fontWeight: '900', textTransform: 'uppercase' },
  suggestion: { color: '#8298aa', fontSize: 10, lineHeight: 15 },
  actions: { flexDirection: 'row', justifyContent: 'flex-end', gap: 6 },
  action: {
    paddingHorizontal: 11,
    paddingVertical: 7,
    borderRadius: 7,
    backgroundColor: '#132430',
  },
  actionPrimary: { backgroundColor: '#70d7e5' },
  actionText: { color: '#80cdd8', fontSize: 9, fontWeight: '800' },
  actionTextPrimary: { color: '#07141b' },
  disabled: { opacity: 0.45 },
  reworkEditor: { gap: 7 },
  input: {
    minHeight: 70,
    borderRadius: 8,
    backgroundColor: '#101f2b',
    color: '#e2edf5',
    paddingHorizontal: 11,
    paddingVertical: 9,
    fontSize: 10,
    textAlignVertical: 'top',
    outlineStyle: 'none',
  } as any,
  error: { color: '#f0a0a6', fontSize: 9, lineHeight: 14 },
  empty: {
    minHeight: 72,
    paddingVertical: 13,
    paddingHorizontal: 14,
    borderRadius: 9,
    backgroundColor: '#0c1721',
  },
  emptyTitle: { color: '#d9e5ef', fontSize: 12, fontWeight: '800' },
  emptyBody: { color: '#758a9d', fontSize: 10, lineHeight: 15, marginTop: 4 },
});
