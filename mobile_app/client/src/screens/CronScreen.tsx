import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { loadAppConfig, type AppConnectionMode } from '../../lib/appConfig';
import { reconcileRemoteAccountConfig } from '../../lib/accountSession';
import { shortStatusText, userFacingError } from '../../lib/diagnostics';
import { markCronFeedSeen } from '@/lib/cronInbox';
import { AppDrawer, type DrawerTab } from '@/components/AppDrawer';
import { CollapsibleSection } from '@/components/CollapsibleSection';
import { InfoHint } from '@/components/InfoHint';
import { PageHeader } from '@/components/PageHeader';
import { useConfirmation } from '@/components/ConfirmationDialog';
import { BottomSheet, SectionTabs, StatusPill } from '@/components/ParityUI';
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

type ScheduleMode = 'interval' | 'daily' | 'delay' | 'advanced';
type RuntimeDetail =
  | { kind: 'event_run'; title: string; item: AutomationEventRun }
  | { kind: 'process_wait'; title: string; item: ProcessWait }
  | { kind: 'planner_contract'; title: string; item: PlannerContract }
  | { kind: 'automation'; title: string; item: ScheduledJob }
  | { kind: 'feed'; title: string; item: CronFeedItem };

const SCHEDULE_TABS = [
  { key: 'interval' as const, label: 'Interval' },
  { key: 'daily' as const, label: 'Daily' },
  { key: 'delay' as const, label: 'Delay' },
  { key: 'advanced' as const, label: 'Advanced' },
];

const TARGET_TABS = [
  { key: 'active_identity' as const, label: 'Active' },
  { key: 'manager' as const, label: 'Manager' },
  { key: 'identity' as const, label: 'Identity' },
  { key: 'group' as const, label: 'Group' },
];

const PERMISSION_TABS = [
  { key: 'standard' as const, label: 'Standard' },
  { key: 'low' as const, label: 'Low' },
  { key: 'full_permissions' as const, label: 'Full' },
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

export default function CronScreen() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [fleetSnapshot, setFleetSnapshot] = useState<FleetSnapshot | null>(null);
  const [feed, setFeed] = useState<CronFeedItem[]>([]);
  const [eventRuns, setEventRuns] = useState<AutomationEventRun[]>([]);
  const [processWaits, setProcessWaits] = useState<ProcessWait[]>([]);
  const [plannerContracts, setPlannerContracts] = useState<PlannerContract[]>([]);
  const [status, setStatus] = useState('idle');
  const [apiBaseUrl, setApiBaseUrl] = useState('');
  const [token, setToken] = useState('');
  const [connectionMode, setConnectionMode] = useState<AppConnectionMode>('direct_backend');
  const [pairedDesktopId, setPairedDesktopId] = useState('');
  const [configLoaded, setConfigLoaded] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>('cron');
  const [cronUnreadCount, setCronUnreadCount] = useState(0);
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
  const [detail, setDetail] = useState<RuntimeDetail | null>(null);
  const { confirm, confirmationDialog } = useConfirmation();

  const showCronError = (error: unknown, fallback = 'Automation action did not finish.') => {
    setStatus(userFacingError(error, fallback));
  };

  const schedule = useMemo(
    () => buildScheduleText(scheduleMode, { intervalAmount, intervalUnit, dailyTime, delayAmount, delayUnit, advancedSchedule }),
    [advancedSchedule, dailyTime, delayAmount, delayUnit, intervalAmount, intervalUnit, scheduleMode],
  );

  const automationsConnected = Boolean(apiBaseUrl && token && !(connectionMode === 'remote_cloud' && !pairedDesktopId));
  const automationsSetupStatus = !configLoaded
    ? 'loading automation setup'
    : !apiBaseUrl
      ? 'Connect automations: add the backend URL first'
      : !token
        ? 'Connect automations: sign in and pair this phone first'
        : connectionMode === 'remote_cloud' && !pairedDesktopId
          ? 'Connect automations: pair this phone with a desktop first'
        : 'Automations ready';
  const ensureAutomationConnection = () => {
    if (!automationsConnected) {
      setStatus(automationsSetupStatus);
      return false;
    }
    return true;
  };

  useEffect(() => {
    loadAppConfig()
      .then(async (loadedConfig) => {
        const { config } = await reconcileRemoteAccountConfig(loadedConfig);
        setApiBaseUrl(config.apiBaseUrl);
        setToken(config.accountToken || config.accessToken);
        setConnectionMode(config.connectionMode);
        setPairedDesktopId(config.pairedDesktopId);
        setConfigLoaded(true);
      })
      .catch(() => {
        setStatus('Setup needs attention.');
        setConfigLoaded(true);
      });
  }, []);

  const loadAutomations = async (quiet = false) => {
    if (!automationsConnected) {
      setStatus(automationsSetupStatus);
      return;
    }

    if (!quiet) {
      setStatus('loading');
    }
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
      setSessions(Array.isArray(sessionList) ? sessionList : []);
      setJobs(Array.isArray(jobList) ? jobList : []);
      setFleetSnapshot(fleetData);
      setFeed(Array.isArray(feedItems) ? feedItems : []);
      setEventRuns(Array.isArray(runItems) ? runItems : []);
      setProcessWaits(Array.isArray(processItems) ? processItems : []);
      setPlannerContracts(Array.isArray(plannerItems) ? plannerItems : []);
      await markCronFeedSeen(Array.isArray(feedItems) ? feedItems : []);
      setCronUnreadCount(0);
      setStatus('ready');
    } catch (error) {
      showCronError(error, 'Automations did not load.');
    }
  };

  useEffect(() => {
    if (!configLoaded) return;
    void loadAutomations();
  }, [apiBaseUrl, configLoaded, connectionMode, pairedDesktopId, token]);

  useEffect(() => {
    if (!configLoaded || !automationsConnected) return;

    const intervalId = setInterval(() => {
      void loadAutomations(true);
    }, 8000);

    return () => clearInterval(intervalId);
  }, [apiBaseUrl, automationsConnected, configLoaded, connectionMode, pairedDesktopId, token]);

  const createAutomation = async () => {
    if (!ensureAutomationConnection()) return;
    if (!name.trim() || !prompt.trim() || !schedule.trim()) {
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
      await createJob(apiBaseUrl, token, {
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
          created_from: 'mobile_automations',
          schedule_mode: scheduleMode,
          catch_up_policy: 'latest_only',
          cloud_mirror_policy: 'generated_artifacts_and_evidence',
        },
      });
      setName('');
      setPrompt('');
      setToolPacksText('');
      await loadAutomations();
    } catch (error) {
      showCronError(error, 'Automation was not created.');
    }
  };

  const runAction = async (jobId: string, action: 'run' | 'enable' | 'disable' | 'delete') => {
    if (!ensureAutomationConnection()) return;
    let confirmationId: string | null = null;
    if (action === 'delete') {
      confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirm, {
        action_kind: 'automation_delete',
        title: 'Delete this automation?',
        message: 'Paused automations can be resumed. Deleting removes this rule from the live scheduler.',
        risk_tier: 'danger',
        origin_surface: 'mobile',
        payload: { automation_id: jobId },
      }, {
        confirmLabel: 'Delete',
        tone: 'danger',
        details: ['Cloud recovery for deleted automations depends on the account archive store.', 'Use Pause when you only want it to stop running.'],
      });
      if (!confirmationId) return;
    }

    setStatus(action === 'run' ? 'Queuing run...' : action === 'delete' ? 'Deleting automation...' : action === 'enable' ? 'Resuming automation...' : 'Pausing automation...');
    try {
      await actOnJob(apiBaseUrl, token, jobId, action, confirmationId);
      await loadAutomations();
    } catch (error) {
      showCronError(error, 'Automation was not updated.');
    }
  };

  const acknowledgeEvent = async (item: CronFeedItem) => {
    if (!ensureAutomationConnection()) return;
    setStatus('marking event handled');
    try {
      await acknowledgeAutomationEvent(apiBaseUrl, token, item.id);
      await loadAutomations(true);
      setStatus('event handled');
    } catch (error) {
      showCronError(error, 'Event was not updated.');
    }
  };

  const handleEventRunAction = async (run: AutomationEventRun, action: 'cancel' | 'retry') => {
    if (!ensureAutomationConnection()) return;
    let confirmationId: string | null = null;
    if (action === 'cancel') {
      confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirm, {
        action_kind: 'automation_event_run_cancel',
        title: 'Cancel this event run?',
        message: 'The queued or running proactive event will be marked canceled.',
        risk_tier: 'danger',
        origin_surface: 'mobile',
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
      showCronError(error, 'Event run was not updated.');
    }
  };

  const handleProcessWaitAction = async (item: ProcessWait, action: 'cancel' | 'stop' | 'persist' | 'unpersist') => {
    if (!ensureAutomationConnection()) return;
    let confirmationId: string | null = null;
    if (action === 'stop' || action === 'cancel') {
      confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirm, {
        action_kind: action === 'stop' ? 'process_wait_stop' : 'process_wait_cancel',
        title: action === 'stop' ? 'Stop this process?' : 'Cancel this process wait?',
        message: action === 'stop'
          ? 'EmploAI will stop only the exact recorded process for this wait.'
          : 'The process wait will be canceled and will no longer resume the agent.',
        risk_tier: 'danger',
        origin_surface: 'mobile',
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
      showCronError(error, 'Process wait was not updated.');
    }
  };

  const handlePlannerStatus = async (item: PlannerContract, statusValue: string) => {
    if (!ensureAutomationConnection()) return;
    setStatus('updating planner contract');
    try {
      await updatePlannerContractStatus(apiBaseUrl, token, item.contract_id, statusValue);
      await loadAutomations(true);
      setStatus('planner contract updated');
    } catch (error) {
      showCronError(error, 'Planner status was not updated.');
    }
  };

  const openFeedSession = (item: CronFeedItem) => {
    if (!item.session_id) return;
    router.push({ pathname: '/chat', params: { sessionId: item.session_id } });
  };

  const enabledJobs = jobs.filter((job) => job.enabled).length;
  const dueJobs = jobs.filter((job) => job.due).length;
  const activeRuns = eventRuns.filter((run) => ['queued', 'running', 'retrying'].includes(run.status)).length;
  const waitingProcesses = processWaits.filter((item) => !item.completed_at && !['process_completed', 'process_failed'].includes(item.status)).length;
  const identities = fleetSnapshot?.identities || [];
  const groups = fleetSnapshot?.groups || [];
  const importantFeed = feed.filter((item) => !item.acknowledged_at && ['important', 'high', 'urgent'].includes(String(item.importance || '').toLowerCase()));
  const failedRuns = eventRuns.filter((run) => ['failed', 'blocked'].includes(String(run.status || '').toLowerCase()));
  const activeContracts = plannerContracts.filter((item) => ['active', 'injected', 'pending'].includes(String(item.status || '').toLowerCase()));
  const needsAttentionCount = importantFeed.length + failedRuns.length;
  const selectedIdentity = identities.find((identity) => identity.identity_id === targetIdentityId) || identities[0] || null;
  const selectedGroup = groups.find((group) => group.group_id === targetGroupId) || groups[0] || null;
  const targetSummary = targetKind === 'group'
    ? selectedGroup?.display_name || 'Choose group'
    : targetKind === 'identity'
      ? selectedIdentity?.display_name || 'Choose identity'
      : targetKind === 'manager'
        ? 'Manager'
        : 'Current active identity';

  return (
    <SafeAreaView edges={['top', 'left', 'right']} style={styles.container}>
      {confirmationDialog}
      <AppDrawer
        visible={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        initialTab={drawerTab}
        sessions={sessions}
        jobs={jobs}
        cronUnreadCount={cronUnreadCount}
        backendLabel={apiBaseUrl || 'Backend not configured'}
      />

      <BottomSheet
        visible={Boolean(detail)}
        title={detail?.title || 'Details'}
        subtitle={detail ? 'Runtime details are tucked away so the main automation view stays readable.' : undefined}
        onClose={() => setDetail(null)}
      >
        {detail ? (
          <View style={styles.detailBody}>
            {detail.kind === 'planner_contract' ? (
              <>
                <Text style={styles.detailLabel}>Success criteria</Text>
                {(contractList(detail.item.contract, 'success_criteria').length ? contractList(detail.item.contract, 'success_criteria') : ['No success criteria recorded.']).map((item) => (
                  <Text key={`success-${item}`} style={styles.detailBullet}>{item}</Text>
                ))}
                <Text style={styles.detailLabel}>Verification</Text>
                {(contractList(detail.item.contract, 'verification_steps').length ? contractList(detail.item.contract, 'verification_steps') : ['No verification steps recorded.']).map((item) => (
                  <Text key={`verify-${item}`} style={styles.detailBullet}>{item}</Text>
                ))}
              </>
            ) : null}
            <Text style={styles.detailLabel}>Raw details</Text>
            <Text selectable style={styles.detailJson}>{runtimeJson(detail.item)}</Text>
          </View>
        ) : null}
      </BottomSheet>

      <PageHeader
        title="Automations"
        subtitle="Schedules, event runs, and important updates"
        right={(
          <View style={styles.actionsRow}>
            <Pressable
              style={styles.topButton}
              onPress={() => {
                setDrawerTab('cron');
                setDrawerOpen(true);
              }}
            >
              <Text style={styles.topButtonText}>Sidebar</Text>
            </Pressable>
            <Pressable style={styles.topButton} onPress={() => void loadAutomations()}>
              <Text style={styles.topButtonText}>Refresh</Text>
            </Pressable>
          </View>
        )}
      />

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.summaryRow}>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Status</Text>
          <Text style={styles.summaryValue}>{shortStatusText(status)}</Text>
        </View>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Rules</Text>
          <Text style={styles.summaryValue}>{jobs.length} total</Text>
        </View>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Enabled</Text>
          <Text style={styles.summaryValue}>{enabledJobs}</Text>
        </View>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Ready</Text>
          <Text style={styles.summaryValue}>{dueJobs}</Text>
        </View>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Event runs</Text>
          <Text style={styles.summaryValue}>{activeRuns} active</Text>
        </View>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Processes</Text>
          <Text style={styles.summaryValue}>{waitingProcesses} waiting</Text>
        </View>
        <View style={[styles.summaryCard, needsAttentionCount ? styles.summaryCardWarn : null]}>
          <Text style={styles.summaryLabel}>Needs attention</Text>
          <Text style={styles.summaryValue}>{needsAttentionCount}</Text>
        </View>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Planner</Text>
          <Text style={styles.summaryValue}>{activeContracts.length ? 'Requirements locked' : 'Quiet'}</Text>
        </View>
      </ScrollView>

      <ScrollView style={styles.body} contentContainerStyle={styles.bodyContent}>
        <View style={styles.heroCard}>
          <Text style={styles.heroTitle}>Manual automations</Text>
          <Text style={styles.heroText}>Create schedules, run them on demand, pause them, and inspect the event feed.</Text>
        </View>

        <CollapsibleSection title="Create automation" meta={`${schedule} · ${targetSummary}`} defaultExpanded={false}>
          <Text style={styles.fieldLabel}>Name</Text>
          <TextInput
            style={styles.input}
            value={name}
            onChangeText={setName}
            placeholder="Automation name"
            placeholderTextColor="#7f8aa3"
            accessibilityLabel="Automation name"
          />
          <Text style={styles.fieldLabel}>Schedule</Text>
          <SectionTabs tabs={SCHEDULE_TABS} active={scheduleMode} onChange={setScheduleMode} />
          {scheduleMode === 'interval' ? (
            <View style={styles.formRow}>
              <TextInput
                style={[styles.input, styles.shortInput]}
                value={intervalAmount}
                onChangeText={setIntervalAmount}
                keyboardType="number-pad"
                placeholder="1"
                placeholderTextColor="#7f8aa3"
                accessibilityLabel="Interval amount"
              />
              {['minutes', 'hours', 'days'].map((unit) => (
                <Pressable
                  key={unit}
                  accessibilityRole="button"
                  accessibilityLabel={`Every ${unit}`}
                  accessibilityState={{ selected: intervalUnit === unit }}
                  style={[styles.choiceButton, intervalUnit === unit ? styles.choiceButtonActive : null]}
                  onPress={() => setIntervalUnit(unit)}
                >
                  <Text style={[styles.choiceButtonText, intervalUnit === unit ? styles.choiceButtonTextActive : null]}>{unit}</Text>
                </Pressable>
              ))}
            </View>
          ) : scheduleMode === 'daily' ? (
            <TextInput
              style={styles.input}
              value={dailyTime}
              onChangeText={setDailyTime}
              placeholder="08:00"
              placeholderTextColor="#7f8aa3"
              accessibilityLabel="Daily time"
            />
          ) : scheduleMode === 'delay' ? (
            <View style={styles.formRow}>
              <TextInput
                style={[styles.input, styles.shortInput]}
                value={delayAmount}
                onChangeText={setDelayAmount}
                keyboardType="number-pad"
                placeholder="20"
                placeholderTextColor="#7f8aa3"
                accessibilityLabel="Delay amount"
              />
              {['minutes', 'hours', 'days'].map((unit) => (
                <Pressable
                  key={unit}
                  accessibilityRole="button"
                  accessibilityLabel={`In ${unit}`}
                  accessibilityState={{ selected: delayUnit === unit }}
                  style={[styles.choiceButton, delayUnit === unit ? styles.choiceButtonActive : null]}
                  onPress={() => setDelayUnit(unit)}
                >
                  <Text style={[styles.choiceButtonText, delayUnit === unit ? styles.choiceButtonTextActive : null]}>{unit}</Text>
                </Pressable>
              ))}
            </View>
          ) : (
            <TextInput
              style={styles.input}
              value={advancedSchedule}
              onChangeText={setAdvancedSchedule}
              placeholder="every 1 hour"
              placeholderTextColor="#7f8aa3"
              accessibilityLabel="Advanced schedule"
            />
          )}
          <Text style={styles.generatedText}>Saves as: {schedule || 'Choose a schedule'}</Text>
          <Text style={styles.fieldLabel}>Target</Text>
          <SectionTabs tabs={TARGET_TABS} active={targetKind} onChange={setTargetKind} />
          {targetKind === 'identity' ? (
            <View style={styles.choiceGrid}>
              {identities.map((identity) => (
                <Pressable
                  key={identity.identity_id}
                  accessibilityRole="button"
                  accessibilityLabel={`Target ${identity.display_name}`}
                  accessibilityState={{ selected: targetIdentityId === identity.identity_id }}
                  style={[styles.choiceButton, targetIdentityId === identity.identity_id ? styles.choiceButtonActive : null]}
                  onPress={() => setTargetIdentityId(identity.identity_id)}
                >
                  <Text style={[styles.choiceButtonText, targetIdentityId === identity.identity_id ? styles.choiceButtonTextActive : null]} numberOfLines={1}>
                    {identity.display_name}
                  </Text>
                </Pressable>
              ))}
              {!identities.length ? <Text style={styles.empty}>No identities available yet.</Text> : null}
            </View>
          ) : null}
          {targetKind === 'group' ? (
            <View style={styles.choiceGrid}>
              {groups.map((group) => (
                <Pressable
                  key={group.group_id}
                  accessibilityRole="button"
                  accessibilityLabel={`Target ${group.display_name}`}
                  accessibilityState={{ selected: targetGroupId === group.group_id }}
                  style={[styles.choiceButton, targetGroupId === group.group_id ? styles.choiceButtonActive : null]}
                  onPress={() => setTargetGroupId(group.group_id)}
                >
                  <Text style={[styles.choiceButtonText, targetGroupId === group.group_id ? styles.choiceButtonTextActive : null]} numberOfLines={1}>
                    {group.display_name}
                  </Text>
                </Pressable>
              ))}
              {!groups.length ? <Text style={styles.empty}>No groups available yet.</Text> : null}
            </View>
          ) : null}
          <Text style={styles.fieldLabel}>Chat behavior</Text>
          <View style={styles.choiceGrid}>
            {[
              { key: 'existing_or_new', label: 'Use current or new' },
              { key: 'new_chat', label: 'New chat' },
              { key: 'existing_chat', label: 'Existing chat' },
            ].map((item) => (
              <Pressable
                key={item.key}
                accessibilityRole="button"
                accessibilityLabel={item.label}
                accessibilityState={{ selected: chatTarget === item.key }}
                style={[styles.choiceButton, chatTarget === item.key ? styles.choiceButtonActive : null]}
                onPress={() => setChatTarget(item.key)}
              >
                <Text style={[styles.choiceButtonText, chatTarget === item.key ? styles.choiceButtonTextActive : null]}>{item.label}</Text>
              </Pressable>
            ))}
          </View>
          {chatTarget === 'existing_chat' ? (
            <View style={styles.choiceGrid}>
              {sessions.slice(0, 8).map((session) => (
                <Pressable
                  key={session.id}
                  accessibilityRole="button"
                  accessibilityLabel={`Use chat ${session.name}`}
                  accessibilityState={{ selected: targetChatId === session.id }}
                  style={[styles.choiceButton, targetChatId === session.id ? styles.choiceButtonActive : null]}
                  onPress={() => setTargetChatId(session.id)}
                >
                  <Text style={[styles.choiceButtonText, targetChatId === session.id ? styles.choiceButtonTextActive : null]} numberOfLines={1}>
                    {session.name}
                  </Text>
                </Pressable>
              ))}
            </View>
          ) : null}
          <Text style={styles.fieldLabel}>Permission mode</Text>
          <SectionTabs tabs={PERMISSION_TABS} active={permissionMode} onChange={setPermissionMode} />
          {permissionMode === 'full_permissions' ? (
            <View style={styles.warningRow}>
              <Text style={styles.warningText}>Sensitive actions still ask.</Text>
              <InfoHint text="Full permissions are scoped to the automation session. Sensitive actions still require confirmation." />
            </View>
          ) : null}
          <TextInput
            style={styles.input}
            value={toolPacksText}
            onChangeText={setToolPacksText}
            placeholder="Optional tool packs, comma separated"
            placeholderTextColor="#7f8aa3"
            accessibilityLabel="Optional automation tool packs"
          />
          <Text style={styles.fieldLabel}>Task</Text>
          <TextInput
            style={[styles.input, styles.textarea]}
            value={prompt}
            onChangeText={setPrompt}
            placeholder="What should this automation do?"
            placeholderTextColor="#7f8aa3"
            multiline
            accessibilityLabel="Automation task"
          />
          <Pressable accessibilityRole="button" accessibilityLabel="Create automation" style={styles.primaryButton} onPress={() => void createAutomation()}>
            <Text style={styles.primaryButtonText}>Create automation</Text>
          </Pressable>
        </CollapsibleSection>

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Event feed</Text>
            <Text style={styles.sectionHint}>Auto-refreshes every few seconds</Text>
          </View>
          {feed.length === 0 ? (
            <Text style={styles.empty}>No automation events yet. Scheduled runs, process continuations, and important worker updates will land here.</Text>
          ) : (
            [...feed].reverse().map((item) => (
              <View
                key={item.id}
                style={[
                  styles.feedBubble,
                  item.kind === 'result' ? styles.feedBubbleResult : styles.feedBubbleAnnouncement,
                  item.acknowledged_at ? styles.feedBubbleAcknowledged : null,
                ]}
              >
                <View style={styles.feedHeader}>
                  <Text style={styles.feedKind}>{item.job_name || item.event_type || 'Automation event'}</Text>
                  <Text style={styles.feedTime}>{item.timestamp ? formatAbsoluteTime(item.timestamp) : 'unknown'}</Text>
                </View>
                <Text style={styles.feedType}>{item.event_type || (item.kind === 'announcement' ? 'Update' : item.kind === 'result' ? 'Result' : item.kind)}</Text>
                <Text style={styles.feedBody}>{item.content}</Text>
                <Text style={styles.feedMeta}>
                  {item.session_name ? `Chat: ${item.session_name}` : 'No linked chat'}
                  {item.telegram_bot_label ? ` · Bot: ${item.telegram_bot_label}` : ''}
                  {item.status ? ` · ${item.status}` : ''}
                  {item.timestamp ? ` · ${formatRelativeTime(item.timestamp)}` : ''}
                </Text>
                <View style={styles.actionsRow}>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="Open event details"
                    style={styles.secondaryButton}
                    onPress={() => setDetail({ kind: 'feed', title: item.job_name || item.event_type || 'Automation event', item })}
                  >
                    <Text style={styles.secondaryButtonText}>Details</Text>
                  </Pressable>
                  {item.session_id ? (
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel="Open linked chat"
                      style={styles.secondaryButton}
                      onPress={() => openFeedSession(item)}
                    >
                      <Text style={styles.secondaryButtonText}>Open Chat</Text>
                    </Pressable>
                  ) : null}
                  {!item.acknowledged_at ? (
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel="Mark event handled"
                      style={styles.secondaryButton}
                      onPress={() => void acknowledgeEvent(item)}
                    >
                      <Text style={styles.secondaryButtonText}>Handled</Text>
                    </Pressable>
                  ) : (
                    <StatusPill label="Handled" tone="good" />
                  )}
                </View>
              </View>
            ))
          )}
        </View>

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Event runs</Text>
            <Text style={styles.sectionHint}>Queued and resumed agent work</Text>
          </View>
          {eventRuns.length === 0 ? (
            <Text style={styles.empty}>No queued or recent event runs.</Text>
          ) : (
            eventRuns.slice(0, 12).map((run) => (
              <View key={run.event_run_id} style={styles.jobCard}>
                <View style={styles.jobHeader}>
                  <View style={styles.jobTitleBlock}>
                    <Text style={styles.jobTitle}>{run.automation_id || run.event_id || run.event_run_id}</Text>
                    <Text style={styles.jobMeta}>Attempt {run.attempt}/{run.max_attempts} · {run.status}</Text>
                  </View>
                  <Text style={styles.jobBadge}>{run.status}</Text>
                </View>
                {run.error ? (
                  <View style={styles.warningRow}>
                    <Text style={styles.feedBody}>Run needs attention.</Text>
                    <InfoHint text={run.error} />
                  </View>
                ) : null}
                {run.result ? <Text style={styles.jobStats} numberOfLines={2}>{run.result}</Text> : null}
                <Text style={styles.jobStats}>
                  Updated: {run.updated_at ? formatRelativeTime(run.updated_at) : 'unknown'}
                  {run.target_chat_id ? ` · Chat: ${run.target_chat_id}` : ''}
                </Text>
                <View style={styles.actionsRow}>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="Open event run details"
                    style={styles.secondaryButton}
                    onPress={() => setDetail({ kind: 'event_run', title: 'Event run details', item: run })}
                  >
                    <Text style={styles.secondaryButtonText}>Details</Text>
                  </Pressable>
                  {['queued', 'failed', 'blocked', 'canceled'].includes(String(run.status || '').toLowerCase()) ? (
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel="Retry event run"
                      style={styles.secondaryButton}
                      onPress={() => void handleEventRunAction(run, 'retry')}
                    >
                      <Text style={styles.secondaryButtonText}>Retry</Text>
                    </Pressable>
                  ) : null}
                  {['queued', 'running', 'retrying'].includes(String(run.status || '').toLowerCase()) ? (
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel="Cancel event run"
                      style={styles.deleteButton}
                      onPress={() => void handleEventRunAction(run, 'cancel')}
                    >
                      <Text style={styles.deleteButtonText}>Cancel</Text>
                    </Pressable>
                  ) : null}
                </View>
              </View>
            ))
          )}
        </View>

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Process waits</Text>
            <Text style={styles.sectionHint}>Background commands that can wake the agent</Text>
          </View>
          {processWaits.length === 0 ? (
            <Text style={styles.empty}>No background process waits.</Text>
          ) : (
            processWaits.slice(0, 12).map((item) => (
              <View key={item.process_wait_id} style={styles.jobCard}>
                <View style={styles.jobHeader}>
                  <View style={styles.jobTitleBlock}>
                    <Text style={styles.jobTitle}>{item.command_id}</Text>
                    <Text style={styles.jobMeta}>{item.status} · {item.resume_policy || 'on_exit'}{item.persistent ? ' · persistent' : ''}</Text>
                  </View>
                  <Text style={styles.jobBadge}>{item.pid || 'pid ?'}</Text>
                </View>
                <Text style={styles.jobPrompt}>{item.command || 'Unknown command'}</Text>
                <Text style={styles.jobStats}>
                  Last event: {item.last_event_at ? formatRelativeTime(item.last_event_at) : 'unknown'}
                  {item.session_id ? ` · Chat: ${item.session_id}` : ''}
                </Text>
                <View style={styles.actionsRow}>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="Open process wait details"
                    style={styles.secondaryButton}
                    onPress={() => setDetail({ kind: 'process_wait', title: 'Process wait details', item })}
                  >
                    <Text style={styles.secondaryButtonText}>Details</Text>
                  </Pressable>
                  {!item.completed_at ? (
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel="Cancel process wait"
                      style={styles.secondaryButton}
                      onPress={() => void handleProcessWaitAction(item, 'cancel')}
                    >
                      <Text style={styles.secondaryButtonText}>Cancel Wait</Text>
                    </Pressable>
                  ) : null}
                  {!item.completed_at ? (
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel="Stop recorded process"
                      style={styles.deleteButton}
                      onPress={() => void handleProcessWaitAction(item, 'stop')}
                    >
                      <Text style={styles.deleteButtonText}>Stop</Text>
                    </Pressable>
                  ) : null}
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={item.persistent ? 'Mark process wait task owned' : 'Mark process wait persistent'}
                    style={styles.secondaryButton}
                    onPress={() => void handleProcessWaitAction(item, item.persistent ? 'unpersist' : 'persist')}
                  >
                    <Text style={styles.secondaryButtonText}>{item.persistent ? 'Task-owned' : 'Persistent'}</Text>
                  </Pressable>
                </View>
              </View>
            ))
          )}
        </View>

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Planner contracts</Text>
            <Text style={styles.sectionHint}>Hidden requirements injected into long tasks</Text>
          </View>
          {plannerContracts.length === 0 ? (
            <Text style={styles.empty}>No planner contracts yet.</Text>
          ) : (
            plannerContracts.slice(0, 8).map((item) => {
              const contract = item.contract || {};
              const requirements = Array.isArray(contract.requirements) ? contract.requirements : [];
              return (
                <View key={item.contract_id} style={styles.jobCard}>
                  <View style={styles.jobHeader}>
                    <View style={styles.jobTitleBlock}>
                      <Text style={styles.jobTitle}>{item.action || 'planner'} · {item.status}</Text>
                      <Text style={styles.jobMeta}>
                        {item.session_id || 'unknown chat'}{item.turn_id ? ` · turn ${item.turn_id}` : ''}
                      </Text>
                    </View>
                    <Text style={styles.jobBadge}>{item.corrections?.length || 0} fixes</Text>
                  </View>
                  <Text style={styles.jobPrompt}>
                    {requirements.length > 0 ? String(requirements[0]) : 'Planner skipped or no requirements were needed.'}
                  </Text>
                  <Text style={styles.jobStats}>Updated: {item.updated_at ? formatRelativeTime(item.updated_at) : 'unknown'}</Text>
                  <View style={styles.actionsRow}>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel="Open planner contract details"
                      style={styles.secondaryButton}
                      onPress={() => setDetail({ kind: 'planner_contract', title: 'Planner requirements', item })}
                    >
                      <Text style={styles.secondaryButtonText}>Details</Text>
                    </Pressable>
                    {item.status !== 'satisfied' ? (
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel="Mark planner contract satisfied"
                        style={styles.secondaryButton}
                        onPress={() => void handlePlannerStatus(item, 'satisfied')}
                      >
                        <Text style={styles.secondaryButtonText}>Satisfied</Text>
                      </Pressable>
                    ) : null}
                    {item.status !== 'blocked' ? (
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel="Mark planner contract blocked"
                        style={styles.secondaryButton}
                        onPress={() => void handlePlannerStatus(item, 'blocked')}
                      >
                        <Text style={styles.secondaryButtonText}>Blocked</Text>
                      </Pressable>
                    ) : null}
                  </View>
                </View>
              );
            })
          )}
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Automation rules</Text>
          {jobs.length === 0 ? (
            <Text style={styles.empty}>No automations yet.</Text>
          ) : (
            jobs.map((job) => (
              <View key={job.id} style={styles.jobCard}>
                <View style={styles.jobHeader}>
                  <View style={styles.jobTitleBlock}>
                    <Text style={styles.jobTitle}>{job.name}</Text>
                    <Text style={styles.jobMeta}>
                      {job.enabled ? 'Enabled' : 'Paused'} · {job.schedule || 'No schedule'}
                    </Text>
                  </View>
                  <Text style={[styles.jobBadge, job.due ? styles.jobBadgeDue : null]}>
                    {job.due ? 'Ready' : 'Scheduled'}
                  </Text>
                </View>
                <Text style={styles.jobPrompt}>{job.prompt}</Text>
                <Text style={styles.jobStats}>
                  Next: {job.next_run_at ? `${formatRelativeTime(job.next_run_at)} (${formatAbsoluteTime(job.next_run_at)})` : 'unknown'}
                </Text>
                <Text style={styles.jobStats}>
                  Last: {job.last_run_at ? formatRelativeTime(job.last_run_at) : 'never'} · Runs: {job.run_count ?? 0} · Errors: {job.error_count ?? 0}
                </Text>
                <Text style={styles.jobStats}>
                  Origin: {sessions.find((session) => session.id === job.origin_session_id)?.name || job.origin_session_id || 'unknown chat'}
                  {job.origin_workspace ? ` · ${job.origin_workspace}` : ''}
                </Text>
                <Text style={styles.jobStats}>
                  Target: {job.target_kind || 'active identity'} · Permission: {job.permission_mode || 'standard'}
                </Text>
                <View style={styles.actionsRow}>
                  <Pressable accessibilityRole="button" accessibilityLabel={`Run ${job.name} now`} style={styles.secondaryButton} onPress={() => void runAction(job.id, 'run')}>
                    <Text style={styles.secondaryButtonText}>Run now</Text>
                  </Pressable>
                  {job.enabled ? (
                    <Pressable accessibilityRole="button" accessibilityLabel={`Pause ${job.name}`} style={styles.secondaryButton} onPress={() => void runAction(job.id, 'disable')}>
                      <Text style={styles.secondaryButtonText}>Pause</Text>
                    </Pressable>
                  ) : (
                    <Pressable accessibilityRole="button" accessibilityLabel={`Resume ${job.name}`} style={styles.secondaryButton} onPress={() => void runAction(job.id, 'enable')}>
                      <Text style={styles.secondaryButtonText}>Resume</Text>
                    </Pressable>
                  )}
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={`Open ${job.name} details`}
                    style={styles.secondaryButton}
                    onPress={() => setDetail({ kind: 'automation', title: job.name, item: job })}
                  >
                    <Text style={styles.secondaryButtonText}>Details</Text>
                  </Pressable>
                  <Pressable accessibilityRole="button" accessibilityLabel={`Delete ${job.name}`} style={styles.deleteButton} onPress={() => void runAction(job.id, 'delete')}>
                    <Text style={styles.deleteButtonText}>Delete</Text>
                  </Pressable>
                </View>
              </View>
            ))
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0b1020',
    paddingHorizontal: 16,
    paddingTop: 8,
    gap: 12,
  },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    flexWrap: 'wrap',
    gap: 8,
  },
  topButton: {
    backgroundColor: '#182342',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  topButtonText: {
    color: '#dce8ff',
    fontWeight: '700',
    fontSize: 13,
  },
  titleBlock: {
    flex: 1,
    gap: 4,
  },
  title: {
    color: '#ffffff',
    fontSize: 24,
    fontWeight: '700',
  },
  subtitle: {
    color: '#8fa2c8',
    fontSize: 13,
  },
  summaryRow: {
    gap: 8,
    paddingRight: 20,
  },
  summaryCard: {
    backgroundColor: '#141c33',
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
    minWidth: 112,
    gap: 4,
  },
  summaryCardWarn: {
    borderWidth: 1,
    borderColor: '#8a641d',
    backgroundColor: '#241d0d',
  },
  summaryLabel: {
    color: '#7f93bc',
    fontSize: 11,
    textTransform: 'uppercase',
  },
  summaryValue: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '700',
  },
  body: {
    flex: 1,
  },
  bodyContent: {
    gap: 14,
    paddingBottom: 16,
  },
  heroCard: {
    backgroundColor: '#141c33',
    borderRadius: 20,
    padding: 16,
    gap: 8,
  },
  heroTitle: {
    color: '#ffffff',
    fontSize: 17,
    fontWeight: '700',
  },
  heroText: {
    color: '#d5e3fb',
    fontSize: 15,
    lineHeight: 22,
  },
  section: {
    gap: 10,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 10,
  },
  sectionTitle: {
    color: '#ffffff',
    fontSize: 17,
    fontWeight: '700',
  },
  sectionHint: {
    color: '#8fa2c8',
    fontSize: 12,
  },
  fieldLabel: {
    color: '#9fb5d8',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  input: {
    backgroundColor: '#0f1730',
    color: '#ffffff',
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  shortInput: {
    width: 76,
  },
  textarea: {
    minHeight: 110,
    textAlignVertical: 'top',
  },
  formRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 8,
  },
  choiceGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  choiceButton: {
    minHeight: 40,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#263b61',
    backgroundColor: '#111b33',
    justifyContent: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  choiceButtonActive: {
    borderColor: '#74c8ff',
    backgroundColor: '#173c63',
  },
  choiceButtonText: {
    color: '#c6d7f2',
    fontWeight: '800',
    fontSize: 12,
  },
  choiceButtonTextActive: {
    color: '#ffffff',
  },
  generatedText: {
    color: '#9db0d4',
    fontSize: 12,
  },
  warningText: {
    color: '#ffd89f',
    backgroundColor: '#241d0d',
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontSize: 12,
    lineHeight: 17,
  },
  warningRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  primaryButton: {
    alignSelf: 'flex-start',
    backgroundColor: '#3b82f6',
    borderRadius: 14,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  primaryButtonText: {
    color: '#ffffff',
    fontWeight: '700',
  },
  feedBubble: {
    backgroundColor: '#141c33',
    borderRadius: 18,
    padding: 14,
    gap: 8,
  },
  feedBubbleAnnouncement: {
    borderLeftWidth: 3,
    borderLeftColor: '#7cc7ff',
  },
  feedBubbleResult: {
    borderLeftWidth: 3,
    borderLeftColor: '#4ade80',
  },
  feedBubbleAcknowledged: {
    opacity: 0.74,
  },
  feedHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 10,
  },
  feedKind: {
    color: '#ffffff',
    fontWeight: '700',
    fontSize: 13,
  },
  feedTime: {
    color: '#8194b9',
    fontSize: 11,
  },
  feedType: {
    color: '#7cc7ff',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  feedBody: {
    color: '#e8f0ff',
    fontSize: 14,
    lineHeight: 21,
  },
  feedMeta: {
    color: '#9db0d4',
    fontSize: 12,
  },
  empty: {
    color: '#9aa9c7',
    fontSize: 14,
  },
  jobCard: {
    backgroundColor: '#141c33',
    borderRadius: 18,
    padding: 14,
    gap: 8,
  },
  jobHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 10,
  },
  jobTitleBlock: {
    flex: 1,
    gap: 4,
  },
  jobTitle: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '700',
  },
  jobMeta: {
    color: '#9db0d4',
    fontSize: 12,
  },
  jobBadge: {
    color: '#cfe1ff',
    backgroundColor: '#223153',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    overflow: 'hidden',
    fontSize: 11,
    fontWeight: '700',
  },
  jobBadgeDue: {
    backgroundColor: '#73420d',
  },
  jobPrompt: {
    color: '#dce8ff',
    fontSize: 14,
    lineHeight: 20,
  },
  jobStats: {
    color: '#9db0d4',
    fontSize: 12,
  },
  actionsRow: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
    paddingTop: 4,
  },
  secondaryButton: {
    backgroundColor: '#223153',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  secondaryButtonText: {
    color: '#ffffff',
    fontWeight: '700',
    fontSize: 13,
  },
  deleteButton: {
    backgroundColor: '#6a2630',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  deleteButtonText: {
    color: '#ffffff',
    fontWeight: '700',
    fontSize: 13,
  },
  detailBody: {
    gap: 10,
  },
  detailLabel: {
    color: '#8fd3ff',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  detailBullet: {
    color: '#dce8ff',
    fontSize: 13,
    lineHeight: 19,
    borderRadius: 8,
    backgroundColor: '#101a2f',
    padding: 9,
  },
  detailJson: {
    color: '#c9d8ee',
    fontFamily: 'monospace',
    fontSize: 11,
    lineHeight: 16,
  },
});
