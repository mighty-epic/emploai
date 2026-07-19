import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Pressable, Text, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { PageHeader } from '@/components/PageHeader';
import { useConfirmation } from '@/components/ConfirmationDialog';
import type { DesktopPressableState } from '@/lib/pressableState';
import { createApprovedConfirmation } from '@/lib/sharedConfirmations';
import {
  acknowledgeAutomationEvent,
  actOnJob,
  cancelAutomationEventRun,
  cancelProcessWait,
  createJob,
  fetchAutomationEventRuns,
  fetchCronFeed,
  fetchFleetSnapshot,
  fetchJobs,
  fetchPlannerContracts,
  fetchProcessWaits,
  fetchSessions,
  retryAutomationEventRun,
  setProcessWaitPersistent,
  stopProcessWait,
  updateJob,
  updatePlannerContractStatus,
  type AutomationEventRun,
  type CronFeedItem,
  type FleetSnapshot,
  type PlannerContract,
  type ProcessWait,
  type ScheduledJob,
  type SessionSummary,
} from '@/lib/appApi';
import { loadAppConfig } from '../../lib/appConfig';
import { shortStatusText, userFacingError } from '../../lib/diagnostics';
import { DesktopAutomationDetail } from './DesktopAutomationDetail';
import { DesktopAutomationEditor } from './DesktopAutomationEditor';
import { DesktopAutomationList } from './DesktopAutomationList';
import { automationStyles as styles } from './DesktopAutomations.styles';
import {
  automationPayloadFromDraft,
  cronFeedMatchesAutomation,
  draftFromAutomation,
  emptyAutomationDraft,
  eventRunMatchesAutomation,
  plannerContractMatchesAutomation,
  processWaitMatchesAutomation,
  type AutomationDetailTab,
  type AutomationEditorDraft,
  type AutomationListFilter,
} from './desktopAutomations';

type EditorState = {
  mode: 'create' | 'edit';
  draft: AutomationEditorDraft;
  jobId?: string;
  key: string;
};

const QUICK_TEMPLATES: Array<{ label: string; description: string; schedule: string; draft: AutomationEditorDraft }> = [
  {
    label: 'Morning Brief',
    description: 'Start the day with project progress, blockers, and the next useful action.',
    schedule: 'Daily · 08:00',
    draft: { ...emptyAutomationDraft(), name: 'Morning brief', prompt: 'Give me a concise morning brief with project progress, blockers, and the next useful action.', scheduleMode: 'daily', dailyTime: '08:00' },
  },
  {
    label: 'Weekly Review',
    description: 'Summarize the week and surface anything that needs a decision.',
    schedule: 'Every 7 Days',
    draft: { ...emptyAutomationDraft(), name: 'Weekly review', prompt: 'Review the past week of work. Summarize progress, blockers, decisions, and next actions.', intervalAmount: '7', intervalUnit: 'days' },
  },
  {
    label: 'Project Monitor',
    description: 'Check for stalled tasks or failed background work on a steady cadence.',
    schedule: 'Every 2 Hours',
    draft: { ...emptyAutomationDraft(), name: 'Project monitor', prompt: 'Check the active project for stalled tasks or failed background work and report only what needs attention.', intervalAmount: '2', intervalUnit: 'hours' },
  },
];

function validDetailTab(value: unknown): AutomationDetailTab {
  return value === 'activity' || value === 'advanced' ? value : 'overview';
}

function validListFilter(value: unknown): AutomationListFilter {
  return value === 'active' || value === 'paused' || value === 'attention' ? value : 'all';
}

function isLocalAuthorizationFailure(error: unknown) {
  const message = error instanceof Error ? error.message : String(error || '');
  return /\b(?:401|403)\b|unauthorized|forbidden|invalid token|token expired/i.test(message);
}

function headerButtonStyle(primary = false) {
  return ({ hovered, pressed }: DesktopPressableState) => [
    styles.button,
    primary ? styles.primaryButton : null,
    hovered ? styles.buttonHover : null,
    pressed ? styles.buttonPressed : null,
  ];
}

export default function DesktopAutomationsScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ automation?: string; view?: string; compose?: string; filter?: string; q?: string }>();
  const { width } = useWindowDimensions();
  const compactLayout = width < 1040;
  const stackedLayout = width < 760;
  const { confirm, confirmationDialog } = useConfirmation();
  const initialParamsAppliedRef = useRef(false);

  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [fleetSnapshot, setFleetSnapshot] = useState<FleetSnapshot | null>(null);
  const [feed, setFeed] = useState<CronFeedItem[]>([]);
  const [eventRuns, setEventRuns] = useState<AutomationEventRun[]>([]);
  const [processWaits, setProcessWaits] = useState<ProcessWait[]>([]);
  const [plannerContracts, setPlannerContracts] = useState<PlannerContract[]>([]);
  const [status, setStatus] = useState('Loading automations…');
  const [apiBaseUrl, setApiBaseUrl] = useState('');
  const [token, setToken] = useState('');
  const [configLoaded, setConfigLoaded] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(typeof params.automation === 'string' ? params.automation : null);
  const [detailTab, setDetailTab] = useState<AutomationDetailTab>(() => validDetailTab(params.view));
  const [query, setQuery] = useState(typeof params.q === 'string' ? params.q : '');
  const [filter, setFilter] = useState<AutomationListFilter>(() => validListFilter(params.filter));
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    let secondFrame = 0;
    const frame = window.requestAnimationFrame(() => {
      secondFrame = window.requestAnimationFrame(() => window.scrollTo({ top: 0, left: 0, behavior: 'auto' }));
    });
    return () => {
      window.cancelAnimationFrame(frame);
      if (secondFrame) window.cancelAnimationFrame(secondFrame);
    };
  }, [editor?.key]);

  const setRouteParams = (values: Record<string, string | undefined>) => {
    (router as any).setParams(values);
  };

  const showError = (error: unknown, fallback: string) => {
    const message = userFacingError(error, fallback);
    setStatus(message === 'Sign in again.' ? 'Local runtime connection expired. Refresh to reconnect.' : message);
  };

  useEffect(() => {
    loadAppConfig()
      .then((config) => {
        setApiBaseUrl(config.apiBaseUrl);
        setToken(config.accessToken);
        setConfigLoaded(true);
      })
      .catch((error) => {
        showError(error, 'The local runtime configuration needs attention.');
        setConfigLoaded(true);
      });
  }, []);

  const loadAutomations = async (quiet = false) => {
    if (!apiBaseUrl || !token) {
      if (!quiet) setStatus('Start the local runtime to load automations.');
      return;
    }
    if (!quiet) setStatus('Loading automations…');
    const requestWorkspace = (baseUrl: string, accessToken: string) => Promise.all([
      fetchSessions(baseUrl, accessToken),
      fetchJobs(baseUrl, accessToken),
      fetchCronFeed(baseUrl, accessToken),
      fetchAutomationEventRuns(baseUrl, accessToken),
      fetchProcessWaits(baseUrl, accessToken),
      fetchPlannerContracts(baseUrl, accessToken),
      fetchFleetSnapshot(baseUrl, accessToken).catch(() => null),
    ]);
    const applyWorkspace = ([sessionList, jobList, feedItems, runItems, processItems, plannerItems, fleetData]: Awaited<ReturnType<typeof requestWorkspace>>) => {
      const nextJobs = Array.isArray(jobList) ? jobList : [];
      setSessions(Array.isArray(sessionList) ? sessionList : []);
      setJobs(nextJobs);
      setFeed(Array.isArray(feedItems) ? feedItems : []);
      setEventRuns(Array.isArray(runItems) ? runItems : []);
      setProcessWaits(Array.isArray(processItems) ? processItems : []);
      setPlannerContracts(Array.isArray(plannerItems) ? plannerItems : []);
      setFleetSnapshot(fleetData);
      setSelectedJobId((current) => current && nextJobs.some((job) => job.id === current) ? current : nextJobs[0]?.id || null);
    };
    try {
      applyWorkspace(await requestWorkspace(apiBaseUrl, token));
      if (!quiet) setStatus('Ready');
    } catch (error) {
      if (isLocalAuthorizationFailure(error)) {
        try {
          const refreshed = await loadAppConfig();
          if (refreshed.apiBaseUrl && refreshed.accessToken) {
            applyWorkspace(await requestWorkspace(refreshed.apiBaseUrl, refreshed.accessToken));
            setApiBaseUrl(refreshed.apiBaseUrl);
            setToken(refreshed.accessToken);
            setStatus('Ready');
            return;
          }
        } catch (refreshError) {
          showError(refreshError, 'The local runtime connection could not be refreshed. Restart the runtime, then try again.');
          return;
        }
      }
      showError(error, 'Automations did not load. Check that the local runtime is online, then refresh.');
    }
  };

  useEffect(() => {
    if (configLoaded) void loadAutomations();
  }, [apiBaseUrl, configLoaded, token]);

  useEffect(() => {
    if (!configLoaded || !apiBaseUrl || !token) return;
    const intervalId = setInterval(() => void loadAutomations(true), 8000);
    return () => clearInterval(intervalId);
  }, [apiBaseUrl, configLoaded, token]);

  const selectedJob = jobs.find((job) => job.id === selectedJobId) || null;
  const identities = fleetSnapshot?.identities || [];
  const groups = fleetSnapshot?.groups || [];

  useEffect(() => {
    if (initialParamsAppliedRef.current || !jobs.length) return;
    initialParamsAppliedRef.current = true;
    const requestedJob = typeof params.automation === 'string' ? jobs.find((job) => job.id === params.automation) || null : null;
    if (requestedJob) setSelectedJobId(requestedJob.id);
    if (params.compose === 'edit' && requestedJob) {
      setEditor({ mode: 'edit', jobId: requestedJob.id, draft: draftFromAutomation(requestedJob), key: `edit-${requestedJob.id}` });
    } else if (params.compose === 'new') {
      setEditor({ mode: 'create', draft: emptyAutomationDraft(), key: `new-${Date.now()}` });
    }
  }, [jobs, params.automation, params.compose]);

  const selectedFeed = useMemo(() => selectedJob ? feed.filter((item) => cronFeedMatchesAutomation(item, selectedJob)).slice(0, 30) : [], [feed, selectedJob]);
  const selectedRuns = useMemo(() => selectedJob ? eventRuns.filter((item) => eventRunMatchesAutomation(item, selectedJob)).slice(0, 30) : [], [eventRuns, selectedJob]);
  const selectedProcessWaits = useMemo(() => selectedJob ? processWaits.filter((item) => processWaitMatchesAutomation(item, selectedJob)).slice(0, 30) : [], [processWaits, selectedJob]);
  const selectedPlannerContracts = useMemo(() => selectedJob ? plannerContracts.filter((item) => plannerContractMatchesAutomation(item, selectedJob)).slice(0, 30) : [], [plannerContracts, selectedJob]);
  const attentionCount = jobs.filter((job) => (job.error_count || 0) > 0 || ['failed', 'blocked', 'needs_review', 'needs_confirmation'].includes(String(job.status || '').toLowerCase())).length;

  const selectJob = (job: ScheduledJob) => {
    setSelectedJobId(job.id);
    setDetailTab('overview');
    setEditor(null);
    setRouteParams({ automation: job.id, view: 'overview', compose: undefined });
  };

  const openCreate = (draft = emptyAutomationDraft()) => {
    setEditor({ mode: 'create', draft, key: `new-${Date.now()}` });
    setRouteParams({ compose: 'new', automation: selectedJobId || undefined });
  };

  const openEdit = (job: ScheduledJob) => {
    setEditor({ mode: 'edit', jobId: job.id, draft: draftFromAutomation(job), key: `edit-${job.id}-${Date.now()}` });
    setRouteParams({ compose: 'edit', automation: job.id });
  };

  const closeEditor = async (dirty: boolean) => {
    if (dirty) {
      const discard = await confirm({
        title: 'Discard automation changes?',
        message: 'Your unsaved task, schedule, routing, and safety changes will be lost.',
        confirmLabel: 'Discard Changes',
        cancelLabel: 'Keep Editing',
        tone: 'danger',
      });
      if (!discard) return;
    }
    setEditor(null);
    setRouteParams({ compose: undefined });
  };

  const saveEditor = async (draft: AutomationEditorDraft) => {
    if (!apiBaseUrl || !token || !editor) return;
    setBusyAction('save');
    setStatus(editor.mode === 'edit' ? 'Saving changes…' : 'Creating automation…');
    try {
      const payload = automationPayloadFromDraft(draft);
      const saved = editor.mode === 'edit' && editor.jobId
        ? await updateJob(apiBaseUrl, token, editor.jobId, payload)
        : await createJob(apiBaseUrl, token, payload);
      await loadAutomations(true);
      setSelectedJobId(saved.id);
      setDetailTab('overview');
      setEditor(null);
      setRouteParams({ automation: saved.id, view: 'overview', compose: undefined });
      setStatus(editor.mode === 'edit' ? 'Automation updated.' : 'Automation created.');
    } catch (error) {
      showError(error, editor.mode === 'edit' ? 'Automation changes were not saved.' : 'Automation was not created.');
    } finally {
      setBusyAction(null);
    }
  };

  const runJobAction = async (job: ScheduledJob, action: 'run' | 'enable' | 'disable' | 'delete') => {
    if (!apiBaseUrl || !token || busyAction) return;
    let confirmationId: string | null = null;
    if (action === 'delete') {
      confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirm, {
        action_kind: 'automation_delete',
        title: 'Archive this automation?',
        message: 'Scheduling will stop immediately. The automation remains recoverable from Settings for 30 days.',
        risk_tier: 'danger',
        origin_surface: 'desktop',
        payload: { automation_id: job.id },
      }, { confirmLabel: 'Archive Automation', tone: 'danger' });
      if (!confirmationId) return;
    }
    const busyKey = action === 'delete' ? 'archive' : action === 'enable' || action === 'disable' ? 'toggle' : 'run';
    setBusyAction(busyKey);
    setStatus(action === 'run' ? 'Queueing run…' : action === 'delete' ? 'Archiving automation…' : 'Updating automation…');
    try {
      await actOnJob(apiBaseUrl, token, job.id, action, confirmationId);
      await loadAutomations(true);
      if (action === 'delete') {
        const nextJob = jobs.find((candidate) => candidate.id !== job.id) || null;
        setSelectedJobId(nextJob?.id || null);
        setDetailTab('overview');
        setRouteParams({ automation: nextJob?.id, view: 'overview' });
      }
      setStatus(action === 'run' ? 'Run queued.' : action === 'delete' ? 'Automation archived.' : 'Automation updated.');
    } catch (error) {
      showError(error, 'Automation was not updated.');
    } finally {
      setBusyAction(null);
    }
  };

  const handleRunAction = async (run: AutomationEventRun, action: 'cancel' | 'retry') => {
    if (!apiBaseUrl || !token) return;
    let confirmationId: string | null = null;
    if (action === 'cancel') {
      confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirm, {
        action_kind: 'automation_event_run_cancel', title: 'Cancel this run?', message: 'The queued or running automation will be marked canceled.', risk_tier: 'danger', origin_surface: 'desktop', payload: { event_run_id: run.event_run_id },
      }, { confirmLabel: 'Cancel Run', tone: 'danger' });
      if (!confirmationId) return;
    }
    setBusyAction(`run-${run.event_run_id}`);
    try {
      if (action === 'retry') await retryAutomationEventRun(apiBaseUrl, token, run.event_run_id, 'Retry requested from Automations.');
      else await cancelAutomationEventRun(apiBaseUrl, token, run.event_run_id, 'Canceled from Automations.', confirmationId);
      await loadAutomations(true);
      setStatus(action === 'retry' ? 'Run queued for retry.' : 'Run canceled.');
    } catch (error) {
      showError(error, 'The run was not updated.');
    } finally {
      setBusyAction(null);
    }
  };

  const handleProcessAction = async (item: ProcessWait, action: 'cancel' | 'stop' | 'persist' | 'unpersist') => {
    if (!apiBaseUrl || !token) return;
    let confirmationId: string | null = null;
    if (action === 'stop' || action === 'cancel') {
      confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirm, {
        action_kind: action === 'stop' ? 'process_wait_stop' : 'process_wait_cancel',
        title: action === 'stop' ? 'Stop this process?' : 'Cancel this process wait?',
        message: action === 'stop' ? 'EmploAI will stop only the exact recorded process.' : 'The wait will no longer resume the automation.',
        risk_tier: 'danger', origin_surface: 'desktop', payload: { process_wait_id: item.process_wait_id, command_id: item.command_id, action },
      }, { confirmLabel: action === 'stop' ? 'Stop Process' : 'Cancel Wait', tone: 'danger' });
      if (!confirmationId) return;
    }
    setBusyAction(`process-${item.process_wait_id}`);
    try {
      if (action === 'cancel') await cancelProcessWait(apiBaseUrl, token, item.process_wait_id, 'Canceled from Automations.', confirmationId);
      else if (action === 'stop') await stopProcessWait(apiBaseUrl, token, item.process_wait_id, 'Stopped from Automations.', confirmationId);
      else await setProcessWaitPersistent(apiBaseUrl, token, item.process_wait_id, action === 'persist', `${action} from Automations.`);
      await loadAutomations(true);
      setStatus('Background process updated.');
    } catch (error) {
      showError(error, 'The background process was not updated.');
    } finally {
      setBusyAction(null);
    }
  };

  const acknowledgeEvent = async (item: CronFeedItem) => {
    if (!apiBaseUrl || !token) return;
    try {
      await acknowledgeAutomationEvent(apiBaseUrl, token, item.id);
      await loadAutomations(true);
      setStatus('Output marked reviewed.');
    } catch (error) {
      showError(error, 'The output was not updated.');
    }
  };

  const markPlannerSatisfied = async (item: PlannerContract) => {
    if (!apiBaseUrl || !token) return;
    try {
      await updatePlannerContractStatus(apiBaseUrl, token, item.contract_id, 'satisfied');
      await loadAutomations(true);
      setStatus('Planner check marked satisfied.');
    } catch (error) {
      showError(error, 'The planner check was not updated.');
    }
  };

  const changeTab = (tab: AutomationDetailTab) => {
    setDetailTab(tab);
    setRouteParams({ view: tab, automation: selectedJobId || undefined });
  };

  return (
    <SafeAreaView edges={['top', 'left', 'right']} style={styles.container}>
      {confirmationDialog}
      <View style={styles.page}>
        <PageHeader
          title="Automations"
          fallbackHref="/desktop?tab=chat"
          right={(
            <View style={styles.headerActions}>
              {attentionCount ? <Text style={styles.warningTitle}>{attentionCount} need review</Text> : null}
              <Text accessibilityLiveRegion="polite" numberOfLines={1} style={styles.liveStatus}>{shortStatusText(status)}</Text>
              <Pressable accessibilityRole="button" disabled={Boolean(busyAction)} style={headerButtonStyle()} onPress={() => void loadAutomations()}>
                <Text style={styles.buttonText}>Refresh</Text>
              </Pressable>
              <Pressable accessibilityRole="button" disabled={Boolean(busyAction)} style={headerButtonStyle(true)} onPress={() => openCreate()}>
                <Text style={[styles.buttonText, styles.primaryButtonText]}>Create Automation</Text>
              </Pressable>
            </View>
          )}
        />

        <View style={[styles.workspace, stackedLayout ? { flexDirection: 'column' } : null]}>
          {!editor || !compactLayout ? (
            <DesktopAutomationList
              style={stackedLayout ? { width: '100%', height: 280, borderRightWidth: 0, borderBottomWidth: 1, borderBottomColor: '#222d3a' } : null}
              jobs={jobs}
              selectedJobId={selectedJobId}
              query={query}
              filter={filter}
              onQueryChange={(value) => { setQuery(value); setRouteParams({ q: value || undefined }); }}
              onFilterChange={(value) => { setFilter(value); setRouteParams({ filter: value === 'all' ? undefined : value }); }}
              onSelect={selectJob}
            />
          ) : null}
          <View style={styles.mainPane}>
            {editor ? (
              <DesktopAutomationEditor
                key={editor.key}
                mode={editor.mode}
                initialDraft={editor.draft}
                identities={identities}
                groups={groups}
                sessions={sessions}
                busy={busyAction === 'save'}
                onSave={saveEditor}
                onRequestClose={closeEditor}
              />
            ) : selectedJob ? (
              <DesktopAutomationDetail
                job={selectedJob}
                tab={detailTab}
                feed={selectedFeed}
                runs={selectedRuns}
                processWaits={selectedProcessWaits}
                plannerContracts={selectedPlannerContracts}
                busyAction={busyAction}
                onTabChange={changeTab}
                onEdit={() => openEdit(selectedJob)}
                onRun={() => void runJobAction(selectedJob, 'run')}
                onToggleEnabled={() => void runJobAction(selectedJob, selectedJob.enabled ? 'disable' : 'enable')}
                onArchive={() => void runJobAction(selectedJob, 'delete')}
                onOpenChat={(sessionId) => router.push({ pathname: '/desktop', params: { tab: 'chat', sessionId } })}
                onAcknowledge={(item) => void acknowledgeEvent(item)}
                onRunAction={(run, action) => void handleRunAction(run, action)}
                onProcessAction={(item, action) => void handleProcessAction(item, action)}
                onPlannerSatisfied={(item) => void markPlannerSatisfied(item)}
              />
            ) : (
              <View style={styles.heroEmpty}>
                <View style={styles.heroInner}>
                  <Text style={styles.heroTitle}>Schedule work.</Text>
                  <Text style={styles.heroCopy}>Runs locally with your chosen approval rules.</Text>
                  <View style={styles.templateGrid}>
                    {QUICK_TEMPLATES.map((template) => (
                      <Pressable
                        key={template.label}
                        accessibilityRole="button"
                        accessibilityLabel={`Create from ${template.label} template`}
                        style={({ hovered, pressed }: DesktopPressableState) => [styles.template, hovered ? styles.templateHover : null, pressed ? styles.buttonPressed : null]}
                        onPress={() => openCreate(template.draft)}
                      >
                        <Text style={styles.templateTitle}>{template.label}</Text>
                        <Text style={styles.templateCopy}>{template.description}</Text>
                        <Text style={styles.templateSchedule}>{template.schedule}</Text>
                      </Pressable>
                    ))}
                  </View>
                  <View style={styles.inlineActions}>
                    <Pressable accessibilityRole="button" style={headerButtonStyle(true)} onPress={() => openCreate()}>
                      <Text style={[styles.buttonText, styles.primaryButtonText]}>Start From Scratch</Text>
                    </Pressable>
                  </View>
                </View>
              </View>
            )}
          </View>
        </View>
      </View>
    </SafeAreaView>
  );
}
