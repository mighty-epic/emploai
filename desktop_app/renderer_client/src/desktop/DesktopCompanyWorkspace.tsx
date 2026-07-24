import { useEffect, useState, type ReactNode } from 'react';
import { Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import {
  fetchCompanyContext,
  fetchCompanyOperatingModel,
  type CompanyContext,
  type CompanyDetail,
  type CompanyOperatingModel,
  type CompanyReport,
} from '@/lib/appApi';
import type {
  DesktopFleetIdentity,
  DesktopFleetSnapshot,
} from '@/lib/desktopBridge';
import type { LocalConfirm } from '@/lib/sharedConfirmations';
import { formatRelativeTime } from '@/lib/time';
import { userFacingError } from '../../lib/diagnostics';
import { CompanyCharterPanel } from './company/CompanyCharterPanel';
import { CompanyGovernancePanel } from './company/CompanyGovernancePanel';
import { CompanyInboxPanel } from './company/CompanyInboxPanel';
import { CompanyKnowledgePanel } from './company/CompanyKnowledgePanel';
import { CompanyPerformancePanel } from './company/CompanyPerformancePanel';
import { CompanyWorkforcePanel } from './company/CompanyWorkforcePanel';
import { CompanyWorkPanel } from './company/CompanyWorkPanel';
import { buildCompanyAssignmentTargets } from './company/companyAssignmentTargets';


type ManagerPage =
  | 'overview'
  | 'inbox'
  | 'company'
  | 'workforce'
  | 'work'
  | 'knowledge'
  | 'performance'
  | 'computers'
  | 'governance';
type WorkerPage = 'my_work' | 'requests' | 'computers';
type CompanyPage = ManagerPage | WorkerPage;

type Props = {
  apiBaseUrl: string;
  token: string;
  activeIdentity?: DesktopFleetIdentity | null;
  fleetSnapshot?: DesktopFleetSnapshot | null;
  computersContent: ReactNode;
  confirmAction: LocalConfirm;
};

const MANAGER_NAV: Array<{ id: ManagerPage; label: string }> = [
  { id: 'overview', label: 'Command Center' },
  { id: 'inbox', label: 'Inbox' },
  { id: 'company', label: 'Company' },
  { id: 'workforce', label: 'Workforce' },
  { id: 'work', label: 'Work' },
  { id: 'knowledge', label: 'Knowledge' },
  { id: 'performance', label: 'Performance' },
  { id: 'computers', label: 'Computers' },
  { id: 'governance', label: 'Governance' },
];
const MEMBER_MANAGER_NAV: Array<{ id: ManagerPage; label: string }> = [
  { id: 'overview', label: 'Branch Overview' },
  { id: 'inbox', label: 'Inbox' },
  { id: 'computers', label: 'Computers' },
];
const WORKER_NAV: Array<{ id: WorkerPage; label: string }> = [
  { id: 'my_work', label: 'My Work' },
  { id: 'requests', label: 'Requests' },
  { id: 'computers', label: 'This Computer' },
];

function stringValue(value: unknown, fallback = '') {
  const normalized = String(value ?? '').trim();
  return normalized || fallback;
}

function statusTone(status: string) {
  const normalized = status.toLowerCase();
  if (normalized.includes('block') || normalized.includes('fail')) return styles.toneDanger;
  if (normalized.includes('active') || normalized.includes('running')) return styles.toneActive;
  if (normalized.includes('complete') || normalized.includes('accepted')) return styles.toneSuccess;
  return styles.toneNeutral;
}

export function DesktopCompanyWorkspace({
  apiBaseUrl,
  token,
  activeIdentity,
  fleetSnapshot,
  computersContent,
  confirmAction,
}: Props) {
  const workerMode = activeIdentity?.role === 'worker';
  const [context, setContext] = useState<CompanyContext | null>(null);
  const [operatingModel, setOperatingModel] = useState<CompanyOperatingModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<CompanyPage>(workerMode ? 'my_work' : 'overview');

  useEffect(() => {
    let disposed = false;
    setLoading(true);
    setError(null);
    void fetchCompanyContext(apiBaseUrl, token)
      .then((next) => {
        if (disposed) return;
        setContext(next);
      })
      .catch((reason) => {
        if (disposed) return;
        setError(userFacingError(reason, 'Company data is unavailable.'));
      })
      .finally(() => {
        if (!disposed) setLoading(false);
      });
    return () => {
      disposed = true;
    };
  }, [apiBaseUrl, token]);

  const companyId = context?.active_company_id || 'unknown';
  const storageKey = `emploai.company.page.${companyId}.${workerMode ? 'worker' : 'manager'}`;

  useEffect(() => {
    if (!context?.active_company_id) {
      setOperatingModel(null);
      return;
    }
    let disposed = false;
    void fetchCompanyOperatingModel(apiBaseUrl, token, context.active_company_id)
      .then((next) => {
        if (!disposed) setOperatingModel(next);
      })
      .catch((reason) => {
        if (!disposed) setError(userFacingError(reason, 'The company operating model is unavailable.'));
      });
    return () => {
      disposed = true;
    };
  }, [apiBaseUrl, context?.active_company_id, token]);

  const refreshCompany = async () => {
    if (!context?.active_company_id) return;
    const [nextContext, nextOperatingModel] = await Promise.all([
      fetchCompanyContext(apiBaseUrl, token),
      fetchCompanyOperatingModel(apiBaseUrl, token, context.active_company_id),
    ]);
    setContext(nextContext);
    setOperatingModel(nextOperatingModel);
  };

  const selectPage = (next: CompanyPage) => {
    setPage(next);
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      window.localStorage.setItem(storageKey, next);
    }
  };

  const company = context?.active_company || null;
  const activeCompanySummary = context?.companies.find(
    (item) => item.company_id === context.active_company_id,
  );
  const rootOwned = activeCompanySummary?.ownership !== 'member';
  const manifest = company?.manifest || {};
  const companyName = stringValue(manifest.display_name, 'My Company');
  const tasks = Array.isArray(fleetSnapshot?.tasks) ? fleetSnapshot.tasks : [];
  const fleetReports = Array.isArray(fleetSnapshot?.reports) ? fleetSnapshot.reports : [];
  const companyReports: CompanyReport[] = operatingModel?.reports
    || (company?.reports as CompanyReport[] | undefined)
    || [];
  const requests = Array.isArray(fleetSnapshot?.upstream_requests) ? fleetSnapshot.upstream_requests : [];
  const identities = Array.isArray(fleetSnapshot?.identities) ? fleetSnapshot.identities : [];
  const assignmentTargets = buildCompanyAssignmentTargets({
    company,
    localComputerId: context?.local_computer_id || '',
    localComputerName: context?.local_computer_name || 'This computer',
    identities,
    fleetSnapshot,
  });
  const pendingRequests = requests.filter((item) => item.status === 'pending');
  const activeTasks = tasks.filter((item) => ['running', 'active', 'queued'].includes(item.status));
  const blockedTasks = tasks.filter((item) => item.status.includes('block') || item.status.includes('fail'));
  const nav = workerMode
    ? WORKER_NAV
    : rootOwned
      ? MANAGER_NAV
      : MEMBER_MANAGER_NAV;

  useEffect(() => {
    const fallback: CompanyPage = workerMode ? 'my_work' : 'overview';
    if (Platform.OS !== 'web' || typeof window === 'undefined') {
      setPage(fallback);
      return;
    }
    const saved = window.localStorage.getItem(storageKey) as CompanyPage | null;
    const allowed = nav.some((item) => item.id === saved);
    setPage(allowed && saved ? saved : fallback);
  }, [rootOwned, storageKey, workerMode]);

  const workerId = activeIdentity?.worker_id || '';
  const workerTasks = tasks.filter((item) => item.worker_id === workerId);
  const workerRequests = requests.filter(
    (item) => item.identity_id === activeIdentity?.identity_id || item.task_id && workerTasks.some((task) => task.task_id === item.task_id),
  );

  useEffect(() => {
    if (nav.some((item) => item.id === page)) return;
    selectPage(workerMode ? 'my_work' : 'overview');
  }, [page, rootOwned, workerMode]);

  return (
    <View style={styles.shell}>
      <View style={styles.header}>
        <View style={styles.headerCopy}>
          <Text style={styles.eyebrow}>{workerMode ? 'EMPLOYEE VIEW' : 'COMPANY OPERATING SYSTEM'}</Text>
          <Text style={styles.title}>{companyName}</Text>
          <Text style={styles.subtitle}>
            {workerMode
              ? `${activeIdentity?.display_name || 'Worker'} · own work and requests`
              : `${activeTasks.length} active · ${pendingRequests.length + blockedTasks.length} need attention`}
          </Text>
        </View>
        <View style={styles.contextBadge}>
          <View style={styles.contextDot} />
          <Text style={styles.contextBadgeText}>
            {activeCompanySummary?.ownership === 'member'
              ? 'WORKER MEMBERSHIP'
              : 'ROOT COMPANY'}
          </Text>
        </View>
      </View>

      <ScrollView
        horizontal
        accessibilityRole="tablist"
        showsHorizontalScrollIndicator={false}
        style={styles.navScroller}
        contentContainerStyle={styles.nav}
      >
        {nav.map((item) => {
          const selected = page === item.id;
          return (
            <Pressable
              key={item.id}
              accessibilityRole="tab"
              accessibilityState={{ selected }}
              style={({ hovered, pressed }: any) => [
                styles.navItem,
                hovered ? styles.navItemHovered : null,
                selected ? styles.navItemSelected : null,
                pressed ? styles.navItemPressed : null,
              ]}
              onPress={() => selectPage(item.id)}
            >
              <Text style={[styles.navText, selected ? styles.navTextSelected : null]}>
                {item.label}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>

      {error ? (
        <CompactNotice
          eyebrow="COMPANY CONTEXT"
          title="Company data needs attention"
          body={error}
          tone="danger"
        />
      ) : null}
      {loading && !company ? (
        <CompactNotice
          eyebrow="COMPANY CONTEXT"
          title="Opening company"
          body="Unlocking the local encrypted company partition."
        />
      ) : null}

      {page === 'computers' ? computersContent : null}
      {!workerMode && page === 'overview' ? (
        <ManagerOverview
          company={company}
          employeeCount={company?.employees.length || identities.length}
          activeTasks={activeTasks}
          attentionCount={pendingRequests.length + blockedTasks.length}
          reports={companyReports}
          rootOwned={rootOwned}
          onOpenInbox={() => selectPage('inbox')}
          onOpenWork={() => selectPage('work')}
          onOpenWorkforce={() => selectPage('workforce')}
          onOpenCompany={() => selectPage('company')}
        />
      ) : null}
      {!workerMode && page === 'inbox' ? (
        <CompanyInboxPanel
          apiBaseUrl={apiBaseUrl}
          token={token}
          companyId={companyId}
          requests={pendingRequests}
          blockedTasks={blockedTasks}
          reports={companyReports}
          routineReports={fleetReports as Array<Record<string, any>>}
          objectives={operatingModel?.objectives || company?.objectives || []}
          handoffs={operatingModel?.handoffs || company?.handoffs || []}
          approvals={operatingModel?.approvals || company?.approvals || []}
          incompleteEmployees={(company?.employees || []).filter((employee) => (
            !employee.protected
            && !['ready', 'limited_ready'].includes(String(employee.job_contract_status || ''))
          ))}
          staleKnowledge={(operatingModel?.knowledge || company?.knowledge || []).filter((item) => {
            const due = Date.parse(String(item.review_due_at || ''));
            return Number.isFinite(due) && due < Date.now() && String(item.status || 'active') === 'active';
          })}
          reviewerIdentityId={activeIdentity?.identity_id || null}
          onChanged={refreshCompany}
        />
      ) : null}
      {!workerMode && page === 'company' ? (
        <CompanyCharterPanel
          apiBaseUrl={apiBaseUrl}
          token={token}
          companyId={companyId}
          company={company}
          onChanged={refreshCompany}
        />
      ) : null}
      {!workerMode && page === 'workforce' ? (
        <CompanyWorkforcePanel
          apiBaseUrl={apiBaseUrl}
          token={token}
          companyId={companyId}
          company={company}
          operatingModel={operatingModel}
          identities={identities}
          confirmAction={confirmAction}
          onChanged={refreshCompany}
        />
      ) : null}
      {!workerMode && page === 'work' ? (
        <CompanyWorkPanel
          apiBaseUrl={apiBaseUrl}
          token={token}
          companyId={companyId}
          company={company}
          operatingModel={operatingModel}
          tasks={tasks}
          reports={companyReports}
          assignmentTargets={assignmentTargets}
          onChanged={refreshCompany}
        />
      ) : null}
      {!workerMode && page === 'knowledge' ? (
        <CompanyKnowledgePanel
          apiBaseUrl={apiBaseUrl}
          token={token}
          companyId={companyId}
          company={company}
          operatingModel={operatingModel}
          onChanged={refreshCompany}
        />
      ) : null}
      {!workerMode && page === 'performance' ? (
        <CompanyPerformancePanel
          apiBaseUrl={apiBaseUrl}
          token={token}
          companyId={companyId}
          company={company}
          operatingModel={operatingModel}
          onChanged={refreshCompany}
        />
      ) : null}
      {!workerMode && page === 'governance' ? (
        <CompanyGovernancePanel
          apiBaseUrl={apiBaseUrl}
          token={token}
          companyId={companyId}
          company={company}
          operatingModel={operatingModel}
          openRequestCount={pendingRequests.length}
          confirmAction={confirmAction}
          onChanged={refreshCompany}
        />
      ) : null}
      {workerMode && page === 'my_work' ? (
        <WorkerWorkView identity={activeIdentity} tasks={workerTasks} reports={fleetReports} />
      ) : null}
      {workerMode && page === 'requests' ? (
        <WorkerRequestsView requests={workerRequests} />
      ) : null}
    </View>
  );
}

function ManagerOverview({
  company,
  employeeCount,
  activeTasks,
  attentionCount,
  reports,
  rootOwned,
  onOpenInbox,
  onOpenWork,
  onOpenWorkforce,
  onOpenCompany,
}: {
  company: CompanyDetail | null;
  employeeCount: number;
  activeTasks: any[];
  attentionCount: number;
  reports: any[];
  rootOwned: boolean;
  onOpenInbox: () => void;
  onOpenWork: () => void;
  onOpenWorkforce: () => void;
  onOpenCompany: () => void;
}) {
  const onboardingStatus = stringValue(company?.manifest?.onboarding_status, 'not_started');
  return (
    <View style={styles.content}>
      <View style={styles.metricStrip}>
        <Metric label="Needs attention" value={attentionCount} accent onPress={onOpenInbox} />
        <Metric label="Active work" value={activeTasks.length} onPress={onOpenWork} />
        <Metric label="Employees" value={employeeCount} onPress={onOpenWorkforce} />
        <Metric label="Reports" value={reports.length} />
      </View>
      {!rootOwned ? (
        <View style={styles.memberNotice}>
          <View style={styles.onboardingCopy}>
            <Text style={styles.onboardingEyebrow}>MEMBER COMPUTER</Text>
            <Text style={styles.onboardingTitle}>Company authority stays with the root</Text>
            <Text style={styles.onboardingText}>
              This computer may operate its assigned branch and local resources. Switch to this computer’s own Company for local charter, workforce, and governance changes.
            </Text>
          </View>
        </View>
      ) : null}
      {rootOwned && onboardingStatus === 'not_started' ? (
        <Pressable accessibilityRole="button" style={styles.onboardingPrompt} onPress={onOpenCompany}>
          <View style={styles.onboardingCopy}>
            <Text style={styles.onboardingEyebrow}>OPTIONAL COMPANY SETUP</Text>
            <Text style={styles.onboardingTitle}>Give the CEO durable company direction</Text>
            <Text style={styles.onboardingText}>
              Add the purpose, offer, customers, constraints, and reserved decisions when you are ready.
            </Text>
          </View>
          <Text style={styles.onboardingAction}>Start →</Text>
        </Pressable>
      ) : null}
      <SectionHeader eyebrow="LIVE OPERATIONS" title="Current work" action="Open Work" onPress={onOpenWork} />
      {activeTasks.length ? (
        <View style={styles.list}>
          {activeTasks.slice(0, 6).map((task) => (
            <StatusRow
              key={task.task_id}
              title={task.prompt}
              meta={`Task ${task.task_id.slice(-6)} · ${formatRelativeTime(task.updated_at || task.created_at)}`}
              status={task.status}
            />
          ))}
        </View>
      ) : (
        <CompactEmpty title="No company work is active" body="Assign work from Chat or open Work to create an objective." />
      )}
    </View>
  );
}

function WorkerWorkView({ identity, tasks, reports }: { identity?: DesktopFleetIdentity | null; tasks: any[]; reports: any[] }) {
  return (
    <View style={styles.content}>
      <SectionHeader eyebrow="YOUR QUEUE" title={identity?.display_name || 'Worker'} />
      {tasks.length ? (
        <View style={styles.list}>
          {tasks.map((task) => (
            <StatusRow
              key={task.task_id}
              title={task.prompt}
              meta={reports.some((report) => report.task_id === task.task_id) ? 'Report submitted' : `Queue position ${task.queue_position || 0}`}
              status={task.status}
            />
          ))}
        </View>
      ) : (
        <CompactEmpty title="No work assigned" body="This identity is ready for direct chat or a manager assignment." />
      )}
    </View>
  );
}

function WorkerRequestsView({ requests }: { requests: any[] }) {
  return (
    <View style={styles.content}>
      <SectionHeader eyebrow="ASSISTANCE AND APPROVALS" title="Requests" />
      {requests.length ? (
        <View style={styles.list}>
          {requests.map((request) => (
            <StatusRow
              key={request.request_id}
              title={request.message}
              meta={request.request_kind}
              status={request.status}
            />
          ))}
        </View>
      ) : (
        <CompactEmpty title="No requests" body="Questions, permission needs, and blockers raised by this worker appear here." />
      )}
    </View>
  );
}

function Metric({ label, value, accent, onPress }: { label: string; value: number; accent?: boolean; onPress?: () => void }) {
  const content = (
    <>
      <Text style={[styles.metricValue, accent ? styles.metricValueAccent : null]}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </>
  );
  return onPress ? (
    <Pressable accessibilityRole="button" style={({ hovered }: any) => [styles.metric, hovered ? styles.metricHovered : null]} onPress={onPress}>
      {content}
    </Pressable>
  ) : <View style={styles.metric}>{content}</View>;
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.fact}>
      <Text style={styles.factLabel}>{label}</Text>
      <Text style={styles.factValue}>{value}</Text>
    </View>
  );
}

function SectionHeader({ eyebrow, title, action, onPress }: { eyebrow: string; title: string; action?: string; onPress?: () => void }) {
  return (
    <View style={styles.sectionHeader}>
      <View>
        <Text style={styles.sectionEyebrow}>{eyebrow}</Text>
        <Text style={styles.sectionTitle}>{title}</Text>
      </View>
      {action && onPress ? (
        <Pressable accessibilityRole="button" style={styles.textAction} onPress={onPress}>
          <Text style={styles.textActionLabel}>{action} →</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

function StatusRow({ title, meta, status }: { title: string; meta: string; status: string }) {
  return (
    <View style={styles.statusRow}>
      <View style={styles.rowCopy}>
        <Text style={styles.rowTitle} numberOfLines={2}>{title}</Text>
        <Text style={styles.rowMeta} numberOfLines={1}>{meta}</Text>
      </View>
      <Text style={[styles.statusText, statusTone(status)]}>{status.replace(/_/g, ' ')}</Text>
    </View>
  );
}

function CompactNotice({ eyebrow, title, body, tone }: { eyebrow: string; title: string; body: string; tone?: 'danger' }) {
  return (
    <View style={[styles.notice, tone === 'danger' ? styles.noticeDanger : null]}>
      <Text style={styles.noticeEyebrow}>{eyebrow}</Text>
      <Text style={styles.noticeTitle}>{title}</Text>
      <Text style={styles.noticeBody}>{body}</Text>
    </View>
  );
}

function CompactEmpty({ title, body }: { title: string; body: string }) {
  return (
    <View style={styles.empty}>
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.emptyBody}>{body}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  shell: {
    width: '100%',
    paddingBottom: 24,
  },
  header: {
    paddingHorizontal: 20,
    paddingTop: 17,
    paddingBottom: 14,
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 18,
  },
  headerCopy: {
    flex: 1,
  },
  eyebrow: {
    color: '#62d7e8',
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 1.3,
  },
  title: {
    color: '#f1f7fc',
    fontSize: 24,
    lineHeight: 29,
    fontWeight: '800',
    marginTop: 3,
  },
  subtitle: {
    color: '#8298ae',
    fontSize: 11,
    marginTop: 4,
  },
  contextBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 5,
    paddingHorizontal: 9,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: '#0d1c27',
  },
  contextDot: {
    width: 6,
    height: 6,
    borderRadius: 999,
    backgroundColor: '#5bd5a0',
  },
  contextBadgeText: {
    color: '#8da6ba',
    fontSize: 8,
    fontWeight: '800',
    letterSpacing: 0.8,
  },
  navScroller: {
    flexGrow: 0,
    flexShrink: 0,
  },
  nav: {
    minWidth: '100%',
    paddingHorizontal: 14,
    paddingBottom: 11,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 3,
    borderBottomWidth: 1,
    borderBottomColor: '#162535',
  },
  navItem: {
    alignSelf: 'flex-start',
    paddingHorizontal: 9,
    paddingVertical: 7,
    borderRadius: 7,
  },
  navItemHovered: {
    backgroundColor: '#101e2b',
  },
  navItemSelected: {
    backgroundColor: '#17303a',
  },
  navItemPressed: {
    opacity: 0.8,
  },
  navText: {
    color: '#8297aa',
    fontSize: 10,
    fontWeight: '700',
  },
  navTextSelected: {
    color: '#72dcea',
  },
  content: {
    paddingHorizontal: 20,
    paddingTop: 18,
    gap: 14,
  },
  metricStrip: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 1,
    backgroundColor: '#172635',
  },
  metric: {
    flexGrow: 1,
    minWidth: 130,
    paddingHorizontal: 15,
    paddingVertical: 13,
    backgroundColor: '#0b151f',
  },
  metricHovered: {
    backgroundColor: '#0f1d29',
  },
  metricValue: {
    color: '#eef5fb',
    fontSize: 20,
    lineHeight: 23,
    fontWeight: '800',
  },
  metricValueAccent: {
    color: '#71dce9',
  },
  metricLabel: {
    color: '#74899d',
    fontSize: 10,
    marginTop: 3,
  },
  onboardingPrompt: {
    minHeight: 92,
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderRadius: 10,
    backgroundColor: '#102630',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  memberNotice: {
    minHeight: 82,
    paddingHorizontal: 16,
    paddingVertical: 13,
    borderRadius: 10,
    backgroundColor: '#101e2a',
  },
  onboardingCopy: {
    flex: 1,
  },
  onboardingEyebrow: {
    color: '#68dce9',
    fontSize: 8,
    fontWeight: '800',
    letterSpacing: 1,
  },
  onboardingTitle: {
    color: '#eaf5fa',
    fontSize: 14,
    fontWeight: '800',
    marginTop: 4,
  },
  onboardingText: {
    color: '#8ba4b5',
    fontSize: 11,
    lineHeight: 16,
    marginTop: 4,
  },
  onboardingAction: {
    color: '#78ddea',
    fontSize: 12,
    fontWeight: '800',
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    gap: 12,
    marginTop: 3,
  },
  sectionEyebrow: {
    color: '#5fd3e5',
    fontSize: 8,
    fontWeight: '800',
    letterSpacing: 1.05,
  },
  sectionTitle: {
    color: '#edf5fb',
    fontSize: 17,
    fontWeight: '800',
    marginTop: 3,
  },
  textAction: {
    paddingVertical: 4,
  },
  textActionLabel: {
    color: '#69d7e5',
    fontSize: 10,
    fontWeight: '800',
  },
  list: {
    borderTopWidth: 1,
    borderTopColor: '#1b2a39',
  },
  statusRow: {
    minHeight: 58,
    paddingVertical: 10,
    paddingHorizontal: 2,
    borderBottomWidth: 1,
    borderBottomColor: '#172635',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  employeeRow: {
    minHeight: 62,
    paddingVertical: 9,
    paddingHorizontal: 2,
    borderBottomWidth: 1,
    borderBottomColor: '#172635',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 11,
  },
  avatar: {
    width: 34,
    height: 34,
    borderRadius: 9,
    backgroundColor: '#17313c',
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: {
    color: '#77dce8',
    fontSize: 13,
    fontWeight: '900',
  },
  rowCopy: {
    flex: 1,
    minWidth: 0,
  },
  rowTitle: {
    color: '#e6eef6',
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
  },
  rowMeta: {
    color: '#70869c',
    fontSize: 10,
    marginTop: 3,
  },
  statusText: {
    maxWidth: 118,
    fontSize: 8,
    fontWeight: '900',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
    textAlign: 'right',
  },
  toneDanger: {
    color: '#f0a0a6',
  },
  toneActive: {
    color: '#6ed8e7',
  },
  toneSuccess: {
    color: '#61d3a0',
  },
  toneNeutral: {
    color: '#8297aa',
  },
  notice: {
    marginHorizontal: 20,
    marginTop: 14,
    padding: 13,
    borderRadius: 9,
    backgroundColor: '#101e2a',
  },
  noticeDanger: {
    backgroundColor: '#2a171c',
  },
  noticeEyebrow: {
    color: '#65d5e4',
    fontSize: 8,
    fontWeight: '800',
    letterSpacing: 1,
  },
  noticeTitle: {
    color: '#ebf3fa',
    fontSize: 13,
    fontWeight: '800',
    marginTop: 4,
  },
  noticeBody: {
    color: '#879caf',
    fontSize: 11,
    lineHeight: 16,
    marginTop: 4,
  },
  empty: {
    minHeight: 72,
    paddingVertical: 13,
    paddingHorizontal: 14,
    borderRadius: 9,
    backgroundColor: '#0c1721',
  },
  emptyTitle: {
    color: '#d9e5ef',
    fontSize: 12,
    fontWeight: '800',
  },
  emptyBody: {
    color: '#758a9d',
    fontSize: 10,
    lineHeight: 15,
    marginTop: 4,
    maxWidth: 720,
  },
  definitionList: {
    borderTopWidth: 1,
    borderTopColor: '#1b2a39',
  },
  definitionRow: {
    minHeight: 56,
    borderBottomWidth: 1,
    borderBottomColor: '#172635',
    paddingVertical: 10,
    flexDirection: 'row',
    gap: 20,
  },
  definitionLabel: {
    width: 120,
    color: '#71879c',
    fontSize: 10,
    fontWeight: '700',
  },
  definitionValue: {
    flex: 1,
    color: '#dfeaf3',
    fontSize: 11,
    lineHeight: 16,
  },
  inlineFacts: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  fact: {
    minWidth: 150,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 8,
    backgroundColor: '#0d1923',
  },
  factLabel: {
    color: '#6f8498',
    fontSize: 8,
    fontWeight: '800',
    letterSpacing: 0.7,
    textTransform: 'uppercase',
  },
  factValue: {
    color: '#dae6ef',
    fontSize: 11,
    fontWeight: '700',
    marginTop: 4,
    textTransform: 'capitalize',
  },
  footnote: {
    color: '#708599',
    fontSize: 10,
    lineHeight: 15,
  },
});
