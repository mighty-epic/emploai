import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { loadAppConfig } from '../../lib/appConfig';
import { shortStatusText, userFacingError } from '../../lib/diagnostics';
import { InfoHint } from '@/components/InfoHint';
import { useConfirmation } from '@/components/ConfirmationDialog';
import { createApprovedConfirmation } from '@/lib/sharedConfirmations';
import { PageHeader } from '@/components/PageHeader';
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
  updatePlannerContractStatus,
  type AutomationEventRun,
  type CronFeedItem,
  type FleetSnapshot,
  type PlannerContract,
  type ProcessWait,
  type ScheduledJob,
  type SessionSummary,
} from '@/lib/appApi';
import { formatAbsoluteTime, formatRelativeTime } from '@/lib/time';
import { desktopAutomationsVisualStyles } from './DesktopAutomationsScreen.visualStyles';
import { mergeDesktopVisualStyles } from './mergeDesktopVisualStyles';

type ScheduleMode = 'interval' | 'daily' | 'delay' | 'advanced';
type DetailTab = 'overview' | 'output' | 'runs' | 'processes' | 'planner';

const SCHEDULE_OPTIONS: Array<{ key: ScheduleMode; label: string }> = [
  { key: 'interval', label: 'Interval' },
  { key: 'daily', label: 'Daily time' },
  { key: 'delay', label: 'One-time delay' },
  { key: 'advanced', label: 'Advanced text' },
];

const TARGET_OPTIONS = [
  { key: 'active_identity', label: 'Active identity' },
  { key: 'manager', label: 'Manager' },
  { key: 'identity', label: 'Specific identity' },
  { key: 'group', label: 'Group' },
] as const;

const PERMISSION_OPTIONS = [
  { key: 'standard', label: 'Approve risky actions' },
  { key: 'low', label: 'Ask before acting' },
  { key: 'full_permissions', label: 'Full access' },
] as const;

const QUICK_TEMPLATES = [
  {
    label: 'Daily brief',
    name: 'Daily brief',
    prompt: 'Give me a short daily brief with anything important I should know before starting work.',
    mode: 'daily' as const,
    dailyTime: '08:00',
  },
  {
    label: 'Weekly review',
    name: 'Weekly review',
    prompt: 'Review the past week of work, summarize progress, blockers, and next actions.',
    mode: 'advanced' as const,
    advancedSchedule: 'every monday at 09:00',
  },
  {
    label: 'Project monitor',
    name: 'Project monitor',
    prompt: 'Check the active project for stalled tasks or failed background work and tell me what needs attention.',
    mode: 'interval' as const,
    intervalAmount: '2',
    intervalUnit: 'hours',
  },
];

function positiveInt(value: string, fallback: number) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function buildScheduleText(mode: ScheduleMode, values: {
  intervalAmount: string;
  intervalUnit: string;
  dailyTime: string;
  delayAmount: string;
  delayUnit: string;
  advancedSchedule: string;
}) {
  if (mode === 'daily') {
    return `every day at ${values.dailyTime.trim() || '08:00'}`;
  }
  if (mode === 'delay') {
    return `in ${positiveInt(values.delayAmount, 20)} ${values.delayUnit}`;
  }
  if (mode === 'advanced') {
    return values.advancedSchedule.trim();
  }
  return `every ${positiveInt(values.intervalAmount, 1)} ${values.intervalUnit}`;
}

function splitToolPacks(value: string) {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function runtimeJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function contractList(contract: Record<string, unknown>, key: string) {
  const value = contract[key];
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

function displayTime(value?: string | null) {
  if (!value) return 'Not yet';
  return `${formatRelativeTime(value)} · ${formatAbsoluteTime(value)}`;
}

function automationKey(job: ScheduledJob) {
  return job.automation_id || job.id;
}

function matchesAutomation(job: ScheduledJob, value?: { automation_id?: string | null; job_id?: string | null }) {
  const key = automationKey(job);
  return Boolean(
    value
    && (
      value.automation_id === key
      || value.automation_id === job.id
      || value.job_id === key
      || value.job_id === job.id
    ),
  );
}

function compactPrompt(value: string) {
  const trimmed = value.trim();
  if (trimmed.length <= 150) return trimmed;
  return `${trimmed.slice(0, 147)}...`;
}

export default function DesktopAutomationsScreen() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [fleetSnapshot, setFleetSnapshot] = useState<FleetSnapshot | null>(null);
  const [feed, setFeed] = useState<CronFeedItem[]>([]);
  const [eventRuns, setEventRuns] = useState<AutomationEventRun[]>([]);
  const [processWaits, setProcessWaits] = useState<ProcessWait[]>([]);
  const [plannerContracts, setPlannerContracts] = useState<PlannerContract[]>([]);
  const [status, setStatus] = useState('loading');
  const [apiBaseUrl, setApiBaseUrl] = useState('');
  const [token, setToken] = useState('');
  const [configLoaded, setConfigLoaded] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [detailTab, setDetailTab] = useState<DetailTab>('overview');
  const [composeOpen, setComposeOpen] = useState(false);
  const [name, setName] = useState('');
  const [prompt, setPrompt] = useState('');
  const [scheduleMode, setScheduleMode] = useState<ScheduleMode>('interval');
  const [intervalAmount, setIntervalAmount] = useState('1');
  const [intervalUnit, setIntervalUnit] = useState('hour');
  const [dailyTime, setDailyTime] = useState('08:00');
  const [delayAmount, setDelayAmount] = useState('20');
  const [delayUnit, setDelayUnit] = useState('minutes');
  const [advancedSchedule, setAdvancedSchedule] = useState('every 1 hour');
  const [targetKind, setTargetKind] = useState<'active_identity' | 'manager' | 'identity' | 'group'>('active_identity');
  const [targetIdentityId, setTargetIdentityId] = useState('');
  const [targetGroupId, setTargetGroupId] = useState('');
  const [targetChatId, setTargetChatId] = useState('');
  const [chatTarget, setChatTarget] = useState('existing_or_new');
  const [permissionMode, setPermissionMode] = useState<'standard' | 'low' | 'full_permissions'>('standard');
  const [toolPacksText, setToolPacksText] = useState('');
  const { confirm, confirmationDialog } = useConfirmation();

  const showAutomationError = (error: unknown, fallback = 'Automation action did not finish.') => {
    setStatus(userFacingError(error, fallback));
  };

  const schedule = useMemo(
    () => buildScheduleText(scheduleMode, { intervalAmount, intervalUnit, dailyTime, delayAmount, delayUnit, advancedSchedule }),
    [advancedSchedule, dailyTime, delayAmount, delayUnit, intervalAmount, intervalUnit, scheduleMode],
  );

  useEffect(() => {
    loadAppConfig()
      .then((config) => {
        setApiBaseUrl(config.apiBaseUrl);
        setToken(config.accessToken);
        setConfigLoaded(true);
      })
      .catch((error) => {
        showAutomationError(error, 'Setup needs attention.');
        setConfigLoaded(true);
      });
  }, []);

  const loadAutomations = async (quiet = false) => {
    if (!apiBaseUrl || !token) {
      if (!quiet) setStatus(!apiBaseUrl ? 'Connect backend first.' : 'Sign in first.');
      return;
    }
    if (!quiet) setStatus('loading');
    try {
      const [sessionList, jobList, feedItems, runItems, processItems, plannerItems, fleetData] = await Promise.all([
        fetchSessions(apiBaseUrl, token),
        fetchJobs(apiBaseUrl, token),
        fetchCronFeed(apiBaseUrl, token),
        fetchAutomationEventRuns(apiBaseUrl, token),
        fetchProcessWaits(apiBaseUrl, token),
        fetchPlannerContracts(apiBaseUrl, token),
        fetchFleetSnapshot(apiBaseUrl, token).catch(() => null),
      ]);
      const safeJobs = Array.isArray(jobList) ? jobList : [];
      setSessions(Array.isArray(sessionList) ? sessionList : []);
      setJobs(safeJobs);
      setFleetSnapshot(fleetData);
      setFeed(Array.isArray(feedItems) ? feedItems : []);
      setEventRuns(Array.isArray(runItems) ? runItems : []);
      setProcessWaits(Array.isArray(processItems) ? processItems : []);
      setPlannerContracts(Array.isArray(plannerItems) ? plannerItems : []);
      setSelectedJobId((current) => {
        if (current && safeJobs.some((job) => job.id === current)) return current;
        return safeJobs[0]?.id || null;
      });
      setStatus('ready');
    } catch (error) {
      showAutomationError(error, 'Automations did not load.');
    }
  };

  useEffect(() => {
    if (!configLoaded) return;
    void loadAutomations();
  }, [apiBaseUrl, configLoaded, token]);

  useEffect(() => {
    if (!configLoaded || !apiBaseUrl || !token) return;
    const intervalId = setInterval(() => {
      void loadAutomations(true);
    }, 8000);
    return () => clearInterval(intervalId);
  }, [apiBaseUrl, configLoaded, token]);

  const selectedJob = jobs.find((job) => job.id === selectedJobId) || jobs[0] || null;
  const identities = fleetSnapshot?.identities || [];
  const groups = fleetSnapshot?.groups || [];
  const selectedIdentity = identities.find((identity) => identity.identity_id === targetIdentityId) || identities[0] || null;
  const selectedGroup = groups.find((group) => group.group_id === targetGroupId) || groups[0] || null;
  const selectedFeed = selectedJob ? feed.filter((item) => matchesAutomation(selectedJob, item)).slice(0, 12) : feed.slice(0, 12);
  const selectedRuns = selectedJob ? eventRuns.filter((run) => matchesAutomation(selectedJob, run)).slice(0, 12) : eventRuns.slice(0, 12);
  const activeRuns = eventRuns.filter((run) => ['queued', 'running', 'retrying'].includes(String(run.status || '').toLowerCase()));
  const importantFeed = feed.filter((item) => !item.acknowledged_at && ['important', 'high', 'urgent'].includes(String(item.importance || '').toLowerCase()));
  const waitingProcesses = processWaits.filter((item) => !item.completed_at && !['process_completed', 'process_failed'].includes(String(item.status || '').toLowerCase()));
  const activeContracts = plannerContracts.filter((item) => ['active', 'injected', 'pending'].includes(String(item.status || '').toLowerCase()));
  const canCreate = Boolean(name.trim() && prompt.trim() && schedule.trim());

  const targetSummary = targetKind === 'group'
    ? selectedGroup?.display_name || 'Choose group'
    : targetKind === 'identity'
      ? selectedIdentity?.display_name || 'Choose identity'
      : targetKind === 'manager'
        ? 'Manager'
        : 'Current active identity';

  const resetComposer = () => {
    setName('');
    setPrompt('');
    setToolPacksText('');
    setTargetChatId('');
    setTargetKind('active_identity');
    setScheduleMode('interval');
    setIntervalAmount('1');
    setIntervalUnit('hour');
    setDailyTime('08:00');
    setDelayAmount('20');
    setDelayUnit('minutes');
    setAdvancedSchedule('every 1 hour');
    setPermissionMode('standard');
    setChatTarget('existing_or_new');
  };

  const applyTemplate = (template: typeof QUICK_TEMPLATES[number]) => {
    resetComposer();
    setName(template.name);
    setPrompt(template.prompt);
    setScheduleMode(template.mode);
    if ('dailyTime' in template && template.dailyTime) setDailyTime(template.dailyTime);
    if ('advancedSchedule' in template && template.advancedSchedule) setAdvancedSchedule(template.advancedSchedule);
    if ('intervalAmount' in template && template.intervalAmount) setIntervalAmount(template.intervalAmount);
    if ('intervalUnit' in template && template.intervalUnit) setIntervalUnit(template.intervalUnit);
    setComposeOpen(true);
  };

  const createAutomation = async () => {
    if (!apiBaseUrl || !token || !canCreate) {
      setStatus('Name, task, and schedule required.');
      return;
    }
    if (targetKind === 'identity' && !targetIdentityId) {
      setStatus('Choose an identity.');
      return;
    }
    if (targetKind === 'group' && !targetGroupId) {
      setStatus('Choose a group.');
      return;
    }

    setStatus('creating automation');
    try {
      const created = await createJob(apiBaseUrl, token, {
        name: name.trim(),
        prompt: prompt.trim(),
        schedule,
        target_kind: targetKind,
        target_identity_id: targetKind === 'identity' ? targetIdentityId : null,
        target_group_id: targetKind === 'group' ? targetGroupId : null,
        target_chat_id: targetChatId || null,
        chat_target: chatTarget,
        permission_mode: permissionMode,
        tool_packs: splitToolPacks(toolPacksText),
        metadata: {
          created_from: 'desktop_automations',
          schedule_mode: scheduleMode,
          catch_up_policy: 'latest_only',
          cloud_mirror_policy: 'generated_artifacts_and_evidence',
        },
      });
      resetComposer();
      setComposeOpen(false);
      setSelectedJobId(created.id);
      setDetailTab('overview');
      await loadAutomations(true);
      setStatus('automation created');
    } catch (error) {
      showAutomationError(error, 'Automation was not created.');
    }
  };

  const runAction = async (job: ScheduledJob, action: 'run' | 'enable' | 'disable' | 'delete') => {
    if (!apiBaseUrl || !token) return;
    let confirmationId: string | null = null;
    if (action === 'delete') {
      confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirm, {
        action_kind: 'automation_delete',
        title: 'Delete this automation?',
        message: 'The rule will be archived and can be recovered from Settings for 30 days.',
        risk_tier: 'danger',
        origin_surface: 'desktop',
        payload: { automation_id: job.id },
      }, {
        confirmLabel: 'Delete',
        tone: 'danger',
      });
      if (!confirmationId) return;
    }

    setStatus(action === 'run' ? 'queueing run' : `${action} automation`);
    try {
      await actOnJob(apiBaseUrl, token, job.id, action, confirmationId);
      await loadAutomations(true);
      setStatus(action === 'run' ? 'run queued' : 'automation updated');
    } catch (error) {
      showAutomationError(error, 'Automation was not updated.');
    }
  };

  const handleEventRunAction = async (run: AutomationEventRun, action: 'cancel' | 'retry') => {
    if (!apiBaseUrl || !token) return;
    let confirmationId: string | null = null;
    if (action === 'cancel') {
      confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirm, {
        action_kind: 'automation_event_run_cancel',
        title: 'Cancel this event run?',
        message: 'The queued or running proactive event will be marked canceled.',
        risk_tier: 'danger',
        origin_surface: 'desktop',
        payload: { event_run_id: run.event_run_id },
      }, {
        confirmLabel: 'Cancel run',
        tone: 'danger',
      });
      if (!confirmationId) return;
    }
    setStatus(action === 'retry' ? 'retrying event run' : 'canceling event run');
    try {
      if (action === 'retry') {
        await retryAutomationEventRun(apiBaseUrl, token, run.event_run_id, 'Retry requested from Automations.');
      } else {
        await cancelAutomationEventRun(apiBaseUrl, token, run.event_run_id, 'Canceled from Automations.', confirmationId);
      }
      await loadAutomations(true);
      setStatus(action === 'retry' ? 'event run queued for retry' : 'event run canceled');
    } catch (error) {
      showAutomationError(error, 'Event run was not updated.');
    }
  };

  const handleProcessWaitAction = async (item: ProcessWait, action: 'cancel' | 'stop' | 'persist' | 'unpersist') => {
    if (!apiBaseUrl || !token) return;
    let confirmationId: string | null = null;
    if (action === 'stop' || action === 'cancel') {
      confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirm, {
        action_kind: action === 'stop' ? 'process_wait_stop' : 'process_wait_cancel',
        title: action === 'stop' ? 'Stop this process?' : 'Cancel this process wait?',
        message: action === 'stop'
          ? 'EmploAI will stop only the exact recorded process for this wait.'
          : 'The process wait will be canceled and will no longer resume the agent.',
        risk_tier: 'danger',
        origin_surface: 'desktop',
        payload: { process_wait_id: item.process_wait_id, command_id: item.command_id, action },
      }, {
        confirmLabel: action === 'stop' ? 'Stop process' : 'Cancel wait',
        tone: 'danger',
      });
      if (!confirmationId) return;
    }
    setStatus(`${action} process wait`);
    try {
      if (action === 'cancel') {
        await cancelProcessWait(apiBaseUrl, token, item.process_wait_id, 'Canceled from Automations.', confirmationId);
      } else if (action === 'stop') {
        await stopProcessWait(apiBaseUrl, token, item.process_wait_id, 'Stopped from Automations.', confirmationId);
      } else {
        await setProcessWaitPersistent(apiBaseUrl, token, item.process_wait_id, action === 'persist', `${action} from Automations.`);
      }
      await loadAutomations(true);
      setStatus('process wait updated');
    } catch (error) {
      showAutomationError(error, 'Process wait was not updated.');
    }
  };

  const acknowledgeEvent = async (item: CronFeedItem) => {
    if (!apiBaseUrl || !token) return;
    setStatus('marking event handled');
    try {
      await acknowledgeAutomationEvent(apiBaseUrl, token, item.id);
      await loadAutomations(true);
      setStatus('event handled');
    } catch (error) {
      showAutomationError(error, 'Event was not updated.');
    }
  };

  const handlePlannerStatus = async (item: PlannerContract, statusValue: string) => {
    if (!apiBaseUrl || !token) return;
    setStatus('updating planner contract');
    try {
      await updatePlannerContractStatus(apiBaseUrl, token, item.contract_id, statusValue);
      await loadAutomations(true);
      setStatus('planner contract updated');
    } catch (error) {
      showAutomationError(error, 'Planner status was not updated.');
    }
  };

  const openFeedSession = (item: CronFeedItem) => {
    if (!item.session_id) return;
    router.push({ pathname: '/chat', params: { sessionId: item.session_id } });
  };

  return (
    <SafeAreaView edges={['top', 'left', 'right']} style={styles.container}>
      {confirmationDialog}
      <View style={styles.page}>
        <PageHeader
          title="Automations"
          subtitle="Scheduled work, follow-ups, and background continuations."
          right={(
          <View style={styles.headerActions}>
            {importantFeed.length ? (
              <View style={styles.attentionPill}>
                <Text style={styles.attentionPillText}>{importantFeed.length} needs attention</Text>
              </View>
            ) : null}
            <Text style={styles.statusText}>{shortStatusText(status)}</Text>
            <Pressable accessibilityRole="button" style={styles.secondaryButton} onPress={() => void loadAutomations()}>
              <Text style={styles.secondaryButtonText}>Refresh</Text>
            </Pressable>
            <Pressable accessibilityRole="button" style={styles.primaryButton} onPress={() => setComposeOpen(true)}>
              <Text style={styles.primaryButtonText}>New automation</Text>
            </Pressable>
          </View>
          )}
        />

        <View style={styles.content}>
          <View style={styles.leftPane}>
            <View style={styles.listHeader}>
              <Text style={styles.sectionTitle}>Rules</Text>
              <Text style={styles.sectionMeta}>{jobs.length} total</Text>
            </View>
            <ScrollView style={styles.ruleList} contentContainerStyle={styles.ruleListContent}>
              {jobs.length ? (
                jobs.map((job) => {
                  const selected = selectedJob?.id === job.id;
                  return (
                    <Pressable
                      key={job.id}
                      accessibilityRole="button"
                      accessibilityLabel={`Open ${job.name}`}
                      style={[styles.ruleRow, selected ? styles.ruleRowSelected : null]}
                      onPress={() => {
                        setSelectedJobId(job.id);
                        setDetailTab('overview');
                      }}
                    >
                      <View style={styles.ruleStatusDotWrap}>
                        <View style={[styles.ruleStatusDot, job.enabled ? styles.ruleStatusDotEnabled : styles.ruleStatusDotPaused]} />
                      </View>
                      <View style={styles.ruleRowBody}>
                        <View style={styles.ruleRowTop}>
                          <Text numberOfLines={1} style={styles.ruleName}>{job.name}</Text>
                          {job.due ? <Text style={styles.readyBadge}>Ready</Text> : null}
                        </View>
                        <Text numberOfLines={1} style={styles.ruleMeta}>{job.schedule || 'No schedule'}</Text>
                        <Text numberOfLines={2} style={styles.rulePrompt}>{compactPrompt(job.prompt || '')}</Text>
                      </View>
                    </Pressable>
                  );
                })
              ) : (
                <View style={styles.emptyList}>
                  <Text style={styles.emptyTitle}>No automations yet</Text>
                  <Text style={styles.emptyText}>Create a scheduled task or a small recurring check.</Text>
                </View>
              )}
            </ScrollView>
          </View>

          <View style={styles.mainPane}>
            {composeOpen ? (
              <ScrollView style={styles.detailScroll} contentContainerStyle={styles.detailContent}>
                <View style={styles.detailHeader}>
                  <View>
                    <Text style={styles.detailEyebrow}>Create</Text>
                    <Text style={styles.detailTitle}>New automation</Text>
                  </View>
                  <Pressable accessibilityRole="button" style={styles.ghostButton} onPress={() => setComposeOpen(false)}>
                    <Text style={styles.ghostButtonText}>Close</Text>
                  </Pressable>
                </View>
                <View style={styles.formGrid}>
                  <View style={styles.fieldWide}>
                    <Text style={styles.fieldLabel}>Name</Text>
                    <TextInput
                      style={styles.input}
                      value={name}
                      onChangeText={setName}
                      placeholder="Daily brief"
                      placeholderTextColor="#7184a9"
                    />
                  </View>
                  <View style={styles.fieldWide}>
                    <Text style={styles.fieldLabel}>Task</Text>
                    <TextInput
                      style={[styles.input, styles.textArea]}
                      value={prompt}
                      onChangeText={setPrompt}
                      multiline
                      placeholder="What should EmploAI do when this automation runs?"
                      placeholderTextColor="#7184a9"
                    />
                  </View>

                  <View style={styles.fieldWide}>
                    <Text style={styles.fieldLabel}>Schedule</Text>
                    <View style={styles.segmentRow}>
                      {SCHEDULE_OPTIONS.map((item) => (
                        <Pressable
                          key={item.key}
                          style={[styles.segment, scheduleMode === item.key ? styles.segmentActive : null]}
                          onPress={() => setScheduleMode(item.key)}
                        >
                          <Text style={[styles.segmentText, scheduleMode === item.key ? styles.segmentTextActive : null]}>{item.label}</Text>
                        </Pressable>
                      ))}
                    </View>
                    {scheduleMode === 'daily' ? (
                      <TextInput style={styles.input} value={dailyTime} onChangeText={setDailyTime} placeholder="08:00" placeholderTextColor="#7184a9" />
                    ) : null}
                    {scheduleMode === 'delay' ? (
                      <View style={styles.inlineFields}>
                        <TextInput style={[styles.input, styles.shortInput]} value={delayAmount} onChangeText={setDelayAmount} keyboardType="numeric" placeholder="20" placeholderTextColor="#7184a9" />
                        <TextInput style={[styles.input, styles.shortInput]} value={delayUnit} onChangeText={setDelayUnit} placeholder="minutes" placeholderTextColor="#7184a9" />
                      </View>
                    ) : null}
                    {scheduleMode === 'advanced' ? (
                      <TextInput style={styles.input} value={advancedSchedule} onChangeText={setAdvancedSchedule} placeholder="every monday at 09:00" placeholderTextColor="#7184a9" />
                    ) : null}
                    {scheduleMode === 'interval' ? (
                      <View style={styles.inlineFields}>
                        <TextInput style={[styles.input, styles.shortInput]} value={intervalAmount} onChangeText={setIntervalAmount} keyboardType="numeric" placeholder="1" placeholderTextColor="#7184a9" />
                        <TextInput style={[styles.input, styles.shortInput]} value={intervalUnit} onChangeText={setIntervalUnit} placeholder="hour" placeholderTextColor="#7184a9" />
                      </View>
                    ) : null}
                    <Text style={styles.generatedSchedule}>{schedule || 'Add a schedule'}</Text>
                  </View>

                  <View style={styles.fieldWide}>
                    <Text style={styles.fieldLabel}>Target</Text>
                    <View style={styles.segmentRow}>
                      {TARGET_OPTIONS.map((item) => (
                        <Pressable
                          key={item.key}
                          style={[styles.segment, targetKind === item.key ? styles.segmentActive : null]}
                          onPress={() => setTargetKind(item.key)}
                        >
                          <Text style={[styles.segmentText, targetKind === item.key ? styles.segmentTextActive : null]}>{item.label}</Text>
                        </Pressable>
                      ))}
                    </View>
                    {targetKind === 'identity' ? (
                      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipScroller}>
                        {identities.map((identity) => (
                          <Pressable
                            key={identity.identity_id}
                            style={[styles.choiceChip, targetIdentityId === identity.identity_id ? styles.choiceChipActive : null]}
                            onPress={() => setTargetIdentityId(identity.identity_id)}
                          >
                            <Text style={[styles.choiceChipText, targetIdentityId === identity.identity_id ? styles.choiceChipTextActive : null]}>{identity.display_name}</Text>
                          </Pressable>
                        ))}
                      </ScrollView>
                    ) : null}
                    {targetKind === 'group' ? (
                      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipScroller}>
                        {groups.length ? groups.map((group) => (
                          <Pressable
                            key={group.group_id}
                            style={[styles.choiceChip, targetGroupId === group.group_id ? styles.choiceChipActive : null]}
                            onPress={() => setTargetGroupId(group.group_id)}
                          >
                            <Text style={[styles.choiceChipText, targetGroupId === group.group_id ? styles.choiceChipTextActive : null]}>{group.display_name}</Text>
                          </Pressable>
                        )) : <Text style={styles.emptyText}>No groups yet.</Text>}
                      </ScrollView>
                    ) : null}
                    <Text style={styles.generatedSchedule}>{targetSummary}</Text>
                  </View>

                  <View style={styles.field}>
                    <Text style={styles.fieldLabel}>Chat target</Text>
                    <TextInput style={styles.input} value={chatTarget} onChangeText={setChatTarget} placeholder="existing_or_new" placeholderTextColor="#7184a9" />
                  </View>
                  <View style={styles.field}>
                    <Text style={styles.fieldLabel}>Specific chat</Text>
                    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipScroller}>
                      <Pressable style={[styles.choiceChip, !targetChatId ? styles.choiceChipActive : null]} onPress={() => setTargetChatId('')}>
                        <Text style={[styles.choiceChipText, !targetChatId ? styles.choiceChipTextActive : null]}>Auto</Text>
                      </Pressable>
                      {sessions.slice(0, 20).map((session) => (
                        <Pressable
                          key={session.id}
                          style={[styles.choiceChip, targetChatId === session.id ? styles.choiceChipActive : null]}
                          onPress={() => setTargetChatId(session.id)}
                        >
                          <Text numberOfLines={1} style={[styles.choiceChipText, targetChatId === session.id ? styles.choiceChipTextActive : null]}>
                            {session.name || session.id}
                          </Text>
                        </Pressable>
                      ))}
                    </ScrollView>
                  </View>

                  <View style={styles.field}>
                    <Text style={styles.fieldLabel}>Permission</Text>
                    <View style={styles.segmentColumn}>
                      {PERMISSION_OPTIONS.map((item) => (
                        <Pressable
                          key={item.key}
                          style={[styles.compactChoice, permissionMode === item.key ? styles.compactChoiceActive : null]}
                          onPress={() => setPermissionMode(item.key)}
                        >
                          <Text style={[styles.compactChoiceText, permissionMode === item.key ? styles.compactChoiceTextActive : null]}>{item.label}</Text>
                        </Pressable>
                      ))}
                    </View>
                  </View>
                  <View style={styles.field}>
                    <Text style={styles.fieldLabel}>Tool packs</Text>
                    <TextInput style={styles.input} value={toolPacksText} onChangeText={setToolPacksText} placeholder="optional, comma separated" placeholderTextColor="#7184a9" />
                  </View>
                </View>
                <View style={styles.formActions}>
                  <Pressable accessibilityRole="button" style={styles.secondaryButton} onPress={resetComposer}>
                    <Text style={styles.secondaryButtonText}>Reset</Text>
                  </Pressable>
                  <Pressable accessibilityRole="button" style={[styles.primaryButton, !canCreate ? styles.disabledButton : null]} disabled={!canCreate} onPress={() => void createAutomation()}>
                    <Text style={styles.primaryButtonText}>Create automation</Text>
                  </Pressable>
                </View>
              </ScrollView>
            ) : selectedJob ? (
              <ScrollView style={styles.detailScroll} contentContainerStyle={styles.detailContent}>
                <View style={styles.detailHeader}>
                  <View style={styles.detailTitleBlock}>
                    <Text style={styles.detailEyebrow}>{selectedJob.enabled ? 'Enabled' : 'Paused'}</Text>
                    <Text style={styles.detailTitle}>{selectedJob.name}</Text>
                    <Text style={styles.detailSubtitle}>{selectedJob.schedule || 'No schedule'} · {selectedJob.permission_mode || 'standard'}</Text>
                  </View>
                  <View style={styles.detailActions}>
                    <Pressable accessibilityRole="button" style={styles.secondaryButton} onPress={() => void runAction(selectedJob, 'run')}>
                      <Text style={styles.secondaryButtonText}>Run now</Text>
                    </Pressable>
                    <Pressable accessibilityRole="button" style={styles.secondaryButton} onPress={() => void runAction(selectedJob, selectedJob.enabled ? 'disable' : 'enable')}>
                      <Text style={styles.secondaryButtonText}>{selectedJob.enabled ? 'Pause' : 'Resume'}</Text>
                    </Pressable>
                    <Pressable accessibilityRole="button" style={styles.deleteButton} onPress={() => void runAction(selectedJob, 'delete')}>
                      <Text style={styles.deleteButtonText}>Delete</Text>
                    </Pressable>
                  </View>
                </View>
                <View style={styles.tabRow}>
                  {(['overview', 'output', 'runs', 'processes', 'planner'] as DetailTab[]).map((tab) => (
                    <Pressable key={tab} style={[styles.tabButton, detailTab === tab ? styles.tabButtonActive : null]} onPress={() => setDetailTab(tab)}>
                      <Text style={[styles.tabText, detailTab === tab ? styles.tabTextActive : null]}>{tab}</Text>
                    </Pressable>
                  ))}
                </View>

                {detailTab === 'overview' ? (
                  <View style={styles.detailGrid}>
                    <InfoCard label="Task" value={selectedJob.prompt || 'No task prompt.'} wide />
                    <InfoCard label="Next run" value={displayTime(selectedJob.next_run_at)} />
                    <InfoCard label="Last run" value={displayTime(selectedJob.last_run_at)} />
                    <InfoCard label="Runs" value={`${selectedJob.run_count || 0} total`} />
                    <InfoCard label="Errors" value={`${selectedJob.error_count || 0}`} />
                    <InfoCard label="Target" value={selectedJob.target_kind || 'active identity'} />
                    <InfoCard label="Chat" value={selectedJob.target_chat_id || selectedJob.chat_target || 'automatic'} />
                    <InfoCard label="Tool packs" value={(selectedJob.tool_packs || []).join(', ') || 'Default'} wide />
                  </View>
                ) : null}

                {detailTab === 'output' ? (
                  <View style={styles.panelStack}>
                    <SectionHeader title="Recent output" meta={`${selectedFeed.length} items`} />
                    {selectedFeed.length ? selectedFeed.map((item) => (
                      <View key={item.id} style={styles.timelineItem}>
                        <View style={styles.timelineDot} />
                        <View style={styles.timelineBody}>
                          <View style={styles.timelineHeader}>
                            <Text style={styles.timelineTitle}>{item.job_name || item.event_type || item.kind}</Text>
                            <Text style={styles.timelineMeta}>{displayTime(item.timestamp)}</Text>
                          </View>
                          <Text style={styles.timelineText}>{item.content}</Text>
                          <View style={styles.inlineActions}>
                            {!item.acknowledged_at ? (
                              <Pressable style={styles.textButton} onPress={() => void acknowledgeEvent(item)}>
                                <Text style={styles.textButtonText}>Acknowledge</Text>
                              </Pressable>
                            ) : null}
                            {item.session_id ? (
                              <Pressable style={styles.textButton} onPress={() => openFeedSession(item)}>
                                <Text style={styles.textButtonText}>Open chat</Text>
                              </Pressable>
                            ) : null}
                          </View>
                        </View>
                      </View>
                    )) : <EmptyState title="No output yet" text="Runs and important updates from this automation will appear here." />}
                  </View>
                ) : null}

                {detailTab === 'runs' ? (
                  <View style={styles.panelStack}>
                    <SectionHeader title="Event runs" meta={`${selectedRuns.length} recent`} />
                    {selectedRuns.length ? selectedRuns.map((run) => (
                      <View key={run.event_run_id} style={styles.runtimeRow}>
                        <View>
                          <Text style={styles.runtimeTitle}>{run.status}</Text>
                          <Text style={styles.runtimeMeta}>Attempt {run.attempt}/{run.max_attempts} · {displayTime(run.created_at)}</Text>
                          {run.error ? (
                            <View style={styles.errorRow}>
                              <Text style={styles.errorText}>Run needs attention.</Text>
                              <InfoHint text={run.error} />
                            </View>
                          ) : null}
                          {run.result ? <Text style={styles.timelineText}>{run.result}</Text> : null}
                        </View>
                        <View style={styles.inlineActions}>
                          {['queued', 'running'].includes(String(run.status || '').toLowerCase()) ? (
                            <Pressable style={styles.textButton} onPress={() => void handleEventRunAction(run, 'cancel')}>
                              <Text style={styles.textButtonDanger}>Cancel</Text>
                            </Pressable>
                          ) : null}
                          {['failed', 'blocked', 'canceled'].includes(String(run.status || '').toLowerCase()) ? (
                            <Pressable style={styles.textButton} onPress={() => void handleEventRunAction(run, 'retry')}>
                              <Text style={styles.textButtonText}>Retry</Text>
                            </Pressable>
                          ) : null}
                        </View>
                      </View>
                    )) : <EmptyState title="No event runs" text="Manual and scheduled runs will be listed here." />}
                  </View>
                ) : null}

                {detailTab === 'processes' ? (
                  <View style={styles.panelStack}>
                    <SectionHeader title="Process waits" meta={`${waitingProcesses.length} waiting`} />
                    {processWaits.length ? processWaits.slice(0, 16).map((item) => (
                      <View key={item.process_wait_id} style={styles.runtimeRow}>
                        <View>
                          <Text style={styles.runtimeTitle}>{item.command_id}</Text>
                          <Text style={styles.runtimeMeta}>{item.status} · {item.resume_policy || 'on_exit'}{item.persistent ? ' · persistent' : ''}</Text>
                          {item.command ? <Text style={styles.codeLine}>{item.command}</Text> : null}
                        </View>
                        <View style={styles.inlineActions}>
                          {!item.completed_at ? (
                            <>
                              <Pressable style={styles.textButton} onPress={() => void handleProcessWaitAction(item, 'cancel')}>
                                <Text style={styles.textButtonDanger}>Cancel</Text>
                              </Pressable>
                              <Pressable style={styles.textButton} onPress={() => void handleProcessWaitAction(item, 'stop')}>
                                <Text style={styles.textButtonDanger}>Stop</Text>
                              </Pressable>
                            </>
                          ) : null}
                          <Pressable style={styles.textButton} onPress={() => void handleProcessWaitAction(item, item.persistent ? 'unpersist' : 'persist')}>
                            <Text style={styles.textButtonText}>{item.persistent ? 'Unmark' : 'Persistent'}</Text>
                          </Pressable>
                        </View>
                      </View>
                    )) : <EmptyState title="No process waits" text="Background commands that can wake the agent will appear here." />}
                  </View>
                ) : null}

                {detailTab === 'planner' ? (
                  <View style={styles.panelStack}>
                    <SectionHeader title="Planner contracts" meta={`${activeContracts.length} active`} />
                    {plannerContracts.length ? plannerContracts.slice(0, 12).map((item) => {
                      const requirements = contractList(item.contract || {}, 'requirements');
                      const verification = contractList(item.contract || {}, 'verification_steps');
                      return (
                        <View key={item.contract_id} style={styles.runtimeRow}>
                          <View>
                            <Text style={styles.runtimeTitle}>{item.action || 'planner'} · {item.status}</Text>
                            <Text style={styles.runtimeMeta}>{item.session_id || 'unknown chat'}{item.turn_id ? ` · turn ${item.turn_id}` : ''}</Text>
                            {requirements.slice(0, 3).map((itemText) => (
                              <Text key={`req-${item.contract_id}-${itemText}`} style={styles.bulletText}>- {itemText}</Text>
                            ))}
                            {verification.length ? <Text style={styles.runtimeMeta}>{verification.length} verification steps</Text> : null}
                          </View>
                          {item.status !== 'satisfied' ? (
                            <Pressable style={styles.textButton} onPress={() => void handlePlannerStatus(item, 'satisfied')}>
                              <Text style={styles.textButtonText}>Mark satisfied</Text>
                            </Pressable>
                          ) : null}
                        </View>
                      );
                    }) : <EmptyState title="No planner contracts" text="Long-running task requirements will stay tucked away here." />}
                  </View>
                ) : null}
              </ScrollView>
            ) : (
              <View style={styles.centerEmpty}>
                <Text style={styles.title}>Scheduled</Text>
                <Text style={styles.subtitle}>Ask EmploAI to schedule tasks, set reminders, or monitor for updates.</Text>
                <View style={styles.quickCenter}>
                  <Text style={styles.emptyTitle}>Create your first automation</Text>
                  <View style={styles.templateRow}>
                    {QUICK_TEMPLATES.map((template) => (
                      <Pressable key={template.label} style={styles.templateButton} onPress={() => applyTemplate(template)}>
                        <Text style={styles.templateButtonText}>{template.label}</Text>
                      </Pressable>
                    ))}
                  </View>
                  <Pressable style={styles.primaryButton} onPress={() => setComposeOpen(true)}>
                    <Text style={styles.primaryButtonText}>Start blank</Text>
                  </Pressable>
                </View>
              </View>
            )}
          </View>

          <View style={styles.rightPane}>
            <SectionHeader title="Activity" meta="Live" />
            <View style={styles.compactStat}>
              <Text style={styles.compactStatValue}>{activeRuns.length}</Text>
              <Text style={styles.compactStatLabel}>active runs</Text>
            </View>
            <View style={styles.compactStat}>
              <Text style={styles.compactStatValue}>{waitingProcesses.length}</Text>
              <Text style={styles.compactStatLabel}>process waits</Text>
            </View>
            <View style={styles.compactStat}>
              <Text style={styles.compactStatValue}>{activeContracts.length}</Text>
              <Text style={styles.compactStatLabel}>planner checks</Text>
            </View>
            <View style={styles.quickTemplates}>
              <Text style={styles.sectionTitle}>Quick starts</Text>
              {QUICK_TEMPLATES.map((template) => (
                <Pressable key={template.label} style={styles.quickTemplateButton} onPress={() => applyTemplate(template)}>
                  <Text style={styles.quickTemplateText}>{template.label}</Text>
                </Pressable>
              ))}
            </View>
          </View>
        </View>
      </View>
    </SafeAreaView>
  );
}

function SectionHeader({ title, meta }: { title: string; meta?: string }) {
  return (
    <View style={styles.sectionHeader}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {meta ? <Text style={styles.sectionMeta}>{meta}</Text> : null}
    </View>
  );
}

function InfoCard({ label, value, wide = false }: { label: string; value: string; wide?: boolean }) {
  return (
    <View style={[styles.infoCard, wide ? styles.infoCardWide : null]}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text selectable style={styles.infoValue}>{value}</Text>
    </View>
  );
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return (
    <View style={styles.emptyPanel}>
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.emptyText}>{text}</Text>
    </View>
  );
}

const baseStyles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#070b13',
  },
  page: {
    flex: 1,
    padding: 18,
    gap: 14,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 18,
  },
  title: {
    color: '#f5f8ff',
    fontSize: 26,
    fontWeight: '800',
  },
  subtitle: {
    color: '#93a2bc',
    fontSize: 13,
    marginTop: 4,
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  statusText: {
    color: '#8fa2c8',
    fontSize: 12,
  },
  attentionPill: {
    borderRadius: 999,
    backgroundColor: '#33220b',
    borderWidth: 1,
    borderColor: '#a86f13',
    paddingVertical: 7,
    paddingHorizontal: 10,
  },
  attentionPillText: {
    color: '#ffd089',
    fontSize: 12,
    fontWeight: '800',
  },
  content: {
    flex: 1,
    flexDirection: 'row',
    gap: 14,
    minHeight: 0,
  },
  leftPane: {
    width: 320,
    borderRadius: 14,
    backgroundColor: '#0d1422',
    borderWidth: 1,
    borderColor: '#18263f',
    padding: 12,
    gap: 10,
  },
  mainPane: {
    flex: 1,
    minWidth: 0,
    borderRadius: 16,
    backgroundColor: '#0b111d',
    borderWidth: 1,
    borderColor: '#17243a',
    overflow: 'hidden',
  },
  rightPane: {
    width: 220,
    borderRadius: 14,
    backgroundColor: '#0d1422',
    borderWidth: 1,
    borderColor: '#18263f',
    padding: 12,
    gap: 10,
  },
  listHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  sectionTitle: {
    color: '#f2f6ff',
    fontSize: 14,
    fontWeight: '800',
  },
  sectionMeta: {
    color: '#7789a8',
    fontSize: 12,
  },
  ruleList: {
    flex: 1,
  },
  ruleListContent: {
    gap: 8,
    paddingBottom: 12,
  },
  ruleRow: {
    flexDirection: 'row',
    gap: 10,
    borderRadius: 12,
    padding: 11,
    backgroundColor: '#0a101b',
    borderWidth: 1,
    borderColor: '#162237',
  },
  ruleRowSelected: {
    backgroundColor: '#102337',
    borderColor: '#24d9ee',
  },
  ruleStatusDotWrap: {
    paddingTop: 5,
  },
  ruleStatusDot: {
    width: 8,
    height: 8,
    borderRadius: 999,
  },
  ruleStatusDotEnabled: {
    backgroundColor: '#d7ff4d',
  },
  ruleStatusDotPaused: {
    backgroundColor: '#6f7e98',
  },
  ruleRowBody: {
    flex: 1,
    minWidth: 0,
    gap: 4,
  },
  ruleRowTop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  ruleName: {
    flex: 1,
    color: '#f7fbff',
    fontSize: 14,
    fontWeight: '800',
  },
  ruleMeta: {
    color: '#8aa0c1',
    fontSize: 12,
  },
  rulePrompt: {
    color: '#b6c4dc',
    fontSize: 12,
    lineHeight: 17,
  },
  readyBadge: {
    color: '#061019',
    backgroundColor: '#d7ff4d',
    borderRadius: 999,
    paddingVertical: 3,
    paddingHorizontal: 7,
    overflow: 'hidden',
    fontSize: 10,
    fontWeight: '900',
  },
  emptyList: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 22,
    gap: 6,
  },
  centerEmpty: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 40,
    gap: 8,
  },
  quickCenter: {
    marginTop: 170,
    alignItems: 'center',
    gap: 14,
  },
  templateRow: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
    justifyContent: 'center',
  },
  templateButton: {
    borderRadius: 9,
    borderWidth: 1,
    borderColor: '#333f52',
    backgroundColor: '#151a24',
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  templateButtonText: {
    color: '#f1f5ff',
    fontWeight: '700',
    fontSize: 12,
  },
  detailScroll: {
    flex: 1,
  },
  detailContent: {
    padding: 18,
    gap: 16,
  },
  detailHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 16,
  },
  detailTitleBlock: {
    flex: 1,
    minWidth: 0,
  },
  detailEyebrow: {
    color: '#77eaff',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
    letterSpacing: 0,
    marginBottom: 5,
  },
  detailTitle: {
    color: '#f7fbff',
    fontSize: 24,
    fontWeight: '800',
  },
  detailSubtitle: {
    color: '#94a7c5',
    fontSize: 13,
    marginTop: 5,
  },
  detailActions: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
    justifyContent: 'flex-end',
  },
  primaryButton: {
    borderRadius: 10,
    backgroundColor: '#23d7e6',
    paddingVertical: 10,
    paddingHorizontal: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryButtonText: {
    color: '#06111b',
    fontSize: 12,
    fontWeight: '900',
  },
  secondaryButton: {
    borderRadius: 10,
    backgroundColor: '#111c2d',
    borderWidth: 1,
    borderColor: '#233753',
    paddingVertical: 9,
    paddingHorizontal: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  secondaryButtonText: {
    color: '#dce9ff',
    fontSize: 12,
    fontWeight: '800',
  },
  ghostButton: {
    borderRadius: 10,
    backgroundColor: '#17233a',
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  ghostButtonText: {
    color: '#dce9ff',
    fontSize: 12,
    fontWeight: '800',
  },
  deleteButton: {
    borderRadius: 10,
    backgroundColor: '#351020',
    borderWidth: 1,
    borderColor: '#74304b',
    paddingVertical: 9,
    paddingHorizontal: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  deleteButtonText: {
    color: '#ffb8ca',
    fontSize: 12,
    fontWeight: '900',
  },
  disabledButton: {
    opacity: 0.45,
  },
  tabRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#17243a',
    paddingBottom: 10,
  },
  tabButton: {
    borderRadius: 999,
    paddingVertical: 7,
    paddingHorizontal: 11,
    backgroundColor: '#101826',
  },
  tabButtonActive: {
    backgroundColor: '#1fd9e8',
  },
  tabText: {
    color: '#9eb0cb',
    fontSize: 12,
    fontWeight: '800',
    textTransform: 'capitalize',
  },
  tabTextActive: {
    color: '#06111b',
  },
  detailGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  infoCard: {
    width: '48%',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#1b2a42',
    backgroundColor: '#0a101b',
    padding: 12,
    gap: 7,
  },
  infoCardWide: {
    width: '100%',
  },
  infoLabel: {
    color: '#7fe8ff',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  infoValue: {
    color: '#eaf1ff',
    fontSize: 13,
    lineHeight: 19,
  },
  panelStack: {
    gap: 10,
  },
  timelineItem: {
    flexDirection: 'row',
    gap: 10,
    paddingVertical: 9,
  },
  timelineDot: {
    width: 8,
    height: 8,
    borderRadius: 999,
    backgroundColor: '#25d9e8',
    marginTop: 5,
  },
  timelineBody: {
    flex: 1,
    borderBottomWidth: 1,
    borderBottomColor: '#17243a',
    paddingBottom: 10,
    gap: 5,
  },
  timelineHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 14,
  },
  timelineTitle: {
    color: '#f4f8ff',
    fontSize: 13,
    fontWeight: '800',
  },
  timelineMeta: {
    color: '#788aa7',
    fontSize: 11,
  },
  timelineText: {
    color: '#bfd0e8',
    fontSize: 13,
    lineHeight: 19,
  },
  runtimeRow: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#1b2a42',
    backgroundColor: '#0a101b',
    padding: 12,
    gap: 10,
  },
  runtimeTitle: {
    color: '#f4f8ff',
    fontSize: 14,
    fontWeight: '800',
  },
  runtimeMeta: {
    color: '#8fa2c8',
    fontSize: 12,
    marginTop: 4,
  },
  errorText: {
    color: '#ff9db5',
    fontSize: 12,
    marginTop: 6,
  },
  errorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 4,
  },
  codeLine: {
    color: '#b8c8df',
    fontFamily: 'monospace',
    fontSize: 11,
    marginTop: 6,
  },
  bulletText: {
    color: '#c9d7ee',
    fontSize: 12,
    lineHeight: 18,
    marginTop: 5,
  },
  inlineActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    alignItems: 'center',
  },
  textButton: {
    paddingVertical: 4,
    paddingHorizontal: 0,
  },
  textButtonText: {
    color: '#82eaff',
    fontSize: 12,
    fontWeight: '900',
  },
  textButtonDanger: {
    color: '#ff9db5',
    fontSize: 12,
    fontWeight: '900',
  },
  emptyPanel: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#1b2a42',
    backgroundColor: '#0a101b',
    padding: 22,
    alignItems: 'center',
    gap: 7,
  },
  emptyTitle: {
    color: '#f6f9ff',
    fontSize: 15,
    fontWeight: '800',
  },
  emptyText: {
    color: '#8fa2c8',
    fontSize: 12,
    lineHeight: 18,
    textAlign: 'center',
  },
  formGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  field: {
    width: '48%',
    gap: 8,
  },
  fieldWide: {
    width: '100%',
    gap: 8,
  },
  fieldLabel: {
    color: '#dce8ff',
    fontSize: 12,
    fontWeight: '800',
  },
  input: {
    minHeight: 42,
    borderRadius: 11,
    borderWidth: 1,
    borderColor: '#1d304d',
    backgroundColor: '#070d17',
    color: '#edf4ff',
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 13,
  },
  textArea: {
    minHeight: 92,
    textAlignVertical: 'top',
  },
  inlineFields: {
    flexDirection: 'row',
    gap: 8,
  },
  shortInput: {
    flex: 1,
  },
  generatedSchedule: {
    color: '#88eaff',
    fontSize: 12,
    fontWeight: '800',
  },
  segmentRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
  },
  segment: {
    borderRadius: 999,
    backgroundColor: '#111a2a',
    paddingVertical: 7,
    paddingHorizontal: 11,
  },
  segmentActive: {
    backgroundColor: '#23d7e6',
  },
  segmentText: {
    color: '#9eb0cb',
    fontSize: 12,
    fontWeight: '800',
  },
  segmentTextActive: {
    color: '#06111b',
  },
  segmentColumn: {
    gap: 7,
  },
  compactChoice: {
    borderRadius: 10,
    backgroundColor: '#101826',
    paddingVertical: 9,
    paddingHorizontal: 10,
  },
  compactChoiceActive: {
    backgroundColor: '#d7ff4d',
  },
  compactChoiceText: {
    color: '#b6c7e1',
    fontSize: 12,
    fontWeight: '800',
  },
  compactChoiceTextActive: {
    color: '#09111a',
  },
  chipScroller: {
    gap: 7,
    paddingVertical: 2,
  },
  choiceChip: {
    borderRadius: 999,
    backgroundColor: '#101826',
    borderWidth: 1,
    borderColor: '#203350',
    paddingVertical: 7,
    paddingHorizontal: 10,
    maxWidth: 220,
  },
  choiceChipActive: {
    backgroundColor: '#23d7e6',
    borderColor: '#23d7e6',
  },
  choiceChipText: {
    color: '#b8c8df',
    fontSize: 12,
    fontWeight: '800',
  },
  choiceChipTextActive: {
    color: '#06111b',
  },
  formActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 10,
  },
  compactStat: {
    borderRadius: 12,
    backgroundColor: '#0a101b',
    borderWidth: 1,
    borderColor: '#1b2a42',
    padding: 12,
    gap: 3,
  },
  compactStatValue: {
    color: '#f5f8ff',
    fontSize: 20,
    fontWeight: '900',
  },
  compactStatLabel: {
    color: '#8fa2c8',
    fontSize: 12,
  },
  quickTemplates: {
    marginTop: 8,
    gap: 8,
  },
  quickTemplateButton: {
    borderRadius: 10,
    backgroundColor: '#101826',
    paddingVertical: 10,
    paddingHorizontal: 10,
  },
  quickTemplateText: {
    color: '#e9f2ff',
    fontSize: 12,
    fontWeight: '800',
  },
});

const styles = mergeDesktopVisualStyles(baseStyles, desktopAutomationsVisualStyles);
