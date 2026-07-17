import { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';

import { loadAppConfig, type AppConnectionMode } from '../../lib/appConfig';
import { reconcileRemoteAccountConfig } from '../../lib/accountSession';
import { shortStatusText, userFacingError } from '../../lib/diagnostics';
import { AppDrawer } from '@/components/AppDrawer';
import { useConfirmation } from '@/components/ConfirmationDialog';
import { PageHeader } from '@/components/PageHeader';
import { BottomSheet, StatusPill } from '@/components/ParityUI';
import { createApprovedConfirmation } from '@/lib/sharedConfirmations';
import {
  assignFleetGroupTask,
  assignFleetWorkerTask,
  continueFleetWorkerQueue,
  createFleetGroup,
  createFleetEnrollment,
  createFleetLocalWorker,
  decideFleetToolGrant,
  deleteSession,
  deleteFleetGroup,
  deleteFleetWorker,
  fetchFleetSnapshot,
  fetchJobs,
  fetchSessions,
  fetchSidebarState,
  renameFleetWorker,
  reorderFleetTasks,
  requestFleetWorkerPreview,
  resetFleetWorker,
  redirectFleetTask,
  setFleetActiveIdentity,
  stopAllFleetWorkers,
  stopFleetWorker,
  updateSidebarState,
  updateFleetTaskStatus,
  type FleetGroup,
  type FleetIdentity,
  type FleetReport,
  type FleetSnapshot,
  type FleetTask,
  type FleetToolGrant,
  type FleetWorker,
  type ScheduledJob,
  type SessionSummary,
  type SidebarState,
} from '@/lib/appApi';
import { formatRelativeTime } from '@/lib/time';
import { fleetTaskBatchStatusMessage, fleetTaskStatusMessage } from '@/lib/fleetStatus';

const TERMINAL_TASK_STATUSES = new Set(['completed', 'failed', 'stopped', 'canceled']);
const ACTIVE_TASK_STATUSES = new Set(['running', 'paused', 'blocked', 'needs_review']);

function identityLabel(identity?: FleetIdentity | null) {
  if (!identity) return 'Manager';
  return identity.display_name || identity.identity_id || 'Identity';
}

function activeTaskForWorker(worker: FleetWorker, tasks: FleetTask[]) {
  return (
    (worker.active_task_id ? tasks.find((task) => task.task_id === worker.active_task_id) : null)
    || tasks.find((task) => task.worker_id === worker.worker_id && ACTIVE_TASK_STATUSES.has(task.status))
    || null
  );
}

function latestReportForWorker(worker: FleetWorker, reports: FleetReport[]) {
  return reports.find((report) => report.worker_id === worker.worker_id) || null;
}

function selectedChatIdForWorker(
  worker: FleetWorker,
  identities: FleetIdentity[],
  selectedByIdentity?: Record<string, string | null>,
) {
  const candidateIdentityIds = [
    worker.instance_id,
    ...identities
      .filter((identity) => identity.worker_id === worker.worker_id)
      .map((identity) => identity.identity_id),
  ].filter(Boolean);
  for (const identityId of Array.from(new Set(candidateIdentityIds))) {
    const selectedChatId = String(selectedByIdentity?.[String(identityId)] || '').trim();
    if (selectedChatId) {
      return selectedChatId;
    }
  }
  return null;
}

function groupLabel(group: FleetGroup) {
  return group.display_name || group.group_id || 'Group';
}

function grantLabel(grant: FleetToolGrant) {
  return `${grant.tool_pack_id || 'tool pack'} for ${grant.target_id || grant.target_kind}`;
}

function normalizeFleetSnapshotManagers(snapshot: FleetSnapshot, desktopId?: string | null): FleetSnapshot {
  const currentDesktopId = String(desktopId || snapshot.manager?.desktop_id || '').trim();
  if (!currentDesktopId) {
    return snapshot;
  }
  const managerFilter = (item: any) => (
    String(item?.role || '').toLowerCase() !== 'manager'
    || String(item?.desktop_id || '').trim() === currentDesktopId
  );
  const identities = Array.isArray(snapshot.identities)
    ? snapshot.identities.filter(managerFilter)
    : [];
  const instances = Array.isArray(snapshot.instances)
    ? snapshot.instances.filter(managerFilter)
    : [];
  const snapshotManagerDesktopId = String(snapshot.manager?.desktop_id || '').trim();
  const snapshotManager = (!snapshotManagerDesktopId || snapshotManagerDesktopId === currentDesktopId)
    ? snapshot.manager
    : null;
  const currentManager = (
    identities.find((item) => String(item?.role || '').toLowerCase() === 'manager')
    || snapshotManager
    || null
  ) as FleetIdentity | null;
  const visibleIdentityIds = new Set(identities.map((item) => String(item.identity_id || '').trim()).filter(Boolean));
  const selectedChatByIdentity = Object.fromEntries(
    Object.entries(snapshot.selected_chat_by_identity || {})
      .filter(([identityId]) => visibleIdentityIds.has(String(identityId || '').trim())),
  );
  const activeIdentityVisible = snapshot.active_identity?.identity_id
    && visibleIdentityIds.has(String(snapshot.active_identity.identity_id));
  const activeIdentity = activeIdentityVisible
    ? snapshot.active_identity
    : currentManager || identities[0] || null;
  return {
    ...snapshot,
    identities,
    instances,
    manager: currentManager,
    active_identity: activeIdentity,
    active_identity_id: activeIdentity?.identity_id || null,
    selected_chat_by_identity: selectedChatByIdentity,
  };
}

export default function FleetScreen() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { confirm, confirmationDialog } = useConfirmation();
  const [apiBaseUrl, setApiBaseUrl] = useState('');
  const [token, setToken] = useState('');
  const [connectionMode, setConnectionMode] = useState<AppConnectionMode>('direct_backend');
  const [pairedDesktopId, setPairedDesktopId] = useState('');
  const [configLoaded, setConfigLoaded] = useState(false);
  const [snapshot, setSnapshot] = useState<FleetSnapshot | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [sidebarState, setSidebarState] = useState<SidebarState | null>(null);
  const [status, setStatus] = useState('loading fleet');
  const [loading, setLoading] = useState(false);
  const [workerNameDraft, setWorkerNameDraft] = useState('');
  const [enrollmentToken, setEnrollmentToken] = useState('');
  const [taskDrafts, setTaskDrafts] = useState<Record<string, string>>({});
  const [redirectDrafts, setRedirectDrafts] = useState<Record<string, string>>({});
  const [renameDrafts, setRenameDrafts] = useState<Record<string, string>>({});
  const [groupNameDraft, setGroupNameDraft] = useState('');
  const [groupTaskDrafts, setGroupTaskDrafts] = useState<Record<string, string>>({});
  const [selectedWorkerId, setSelectedWorkerId] = useState<string | null>(null);
  const [workerDetailOpen, setWorkerDetailOpen] = useState(false);
  const [workerActionMenuOpen, setWorkerActionMenuOpen] = useState(false);

  const showFleetError = (error: unknown, fallback = 'Fleet action did not finish.') => {
    setStatus(userFacingError(error, fallback));
  };

  useEffect(() => {
    let active = true;
    loadAppConfig()
      .then(async (loadedConfig) => {
        const { config } = await reconcileRemoteAccountConfig(loadedConfig);
        if (!active) return;
        setApiBaseUrl(config.apiBaseUrl);
        setToken(config.accountToken || config.accessToken);
        setConnectionMode(config.connectionMode);
        setPairedDesktopId(config.pairedDesktopId);
        setConfigLoaded(true);
      })
      .catch((error) => {
        if (!active) return;
        showFleetError(error, 'Fleet setup failed.');
        setConfigLoaded(true);
      });
    return () => {
      active = false;
    };
  }, []);

  const fleetConnected = Boolean(apiBaseUrl && token && !(connectionMode === 'remote_cloud' && !pairedDesktopId));
  const fleetSetupMissing = configLoaded && !fleetConnected;
  const actionDisabled = loading || !configLoaded || !fleetConnected;
  const fleetSetupMessage = !configLoaded
    ? 'Loading Fleet setup.'
    : !apiBaseUrl
      ? 'Add the backend URL before Fleet can create workers or dispatch tasks.'
      : !token
        ? 'Sign in and pair this phone before Fleet can create workers or dispatch tasks.'
        : connectionMode === 'remote_cloud' && !pairedDesktopId
          ? 'Pair this phone with a desktop before Fleet can create workers or dispatch tasks.'
          : '';
  const requireFleetConnection = () => {
    if (!fleetConnected) {
      setStatus(fleetSetupMessage || 'Fleet setup incomplete');
      return false;
    }
    return true;
  };

  const refresh = async (quiet = false) => {
    if (!fleetConnected) {
      setStatus(fleetSetupMessage || (configLoaded ? 'sign in and pair a desktop first' : 'loading setup'));
      return null;
    }
    if (!quiet) {
      setLoading(true);
      setStatus('refreshing fleet');
    }
    try {
      const [next, nextSessions, nextJobs, nextSidebar] = await Promise.all([
        fetchFleetSnapshot(apiBaseUrl, token),
        fetchSessions(apiBaseUrl, token).catch(() => []),
        fetchJobs(apiBaseUrl, token).catch(() => []),
        fetchSidebarState(apiBaseUrl, token).catch(() => null),
      ]);
      const normalizedNext = normalizeFleetSnapshotManagers(next, pairedDesktopId);
      setSnapshot(normalizedNext);
      setSessions(Array.isArray(nextSessions) ? nextSessions : []);
      setJobs(Array.isArray(nextJobs) ? nextJobs : []);
      if (nextSidebar?.state) {
        setSidebarState(nextSidebar.state);
      }
      setStatus(normalizedNext.workers.length ? `${normalizedNext.workers.length} worker${normalizedNext.workers.length === 1 ? '' : 's'} linked` : 'No workers yet');
      setSelectedWorkerId((current) => current || normalizedNext.workers[0]?.worker_id || null);
      return normalizedNext;
    } catch (error) {
      showFleetError(error, 'Fleet did not refresh.');
      return null;
    } finally {
      if (!quiet) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    if (!configLoaded || !fleetConnected) return;
    let cancelled = false;
    const run = async () => {
      if (!cancelled) {
        await refresh(true);
      }
    };
    void run();
    const intervalId = setInterval(() => {
      if (!cancelled) void refresh(true);
    }, 4000);
    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [apiBaseUrl, configLoaded, connectionMode, pairedDesktopId, token]);

  const workers = snapshot?.workers || [];
  const tasks = snapshot?.tasks || [];
  const reports = snapshot?.reports || [];
  const identities = snapshot?.identities || [];
  const groups = snapshot?.groups || [];
  const toolGrants = snapshot?.tool_grants || [];
  const pendingToolGrants = toolGrants.filter((grant) => String(grant.status || '').toLowerCase() === 'pending');
  const selectedWorker = workers.find((worker) => worker.worker_id === selectedWorkerId) || workers[0] || null;
  const selectedTask = selectedWorker ? activeTaskForWorker(selectedWorker, tasks) : null;
  const selectedReport = selectedWorker ? latestReportForWorker(selectedWorker, reports) : null;
  const hasActiveFleetTask = workers.some((worker) => Boolean(activeTaskForWorker(worker, tasks)));
  const workerCardWidth = width >= 900 ? '31.8%' : width >= 620 ? '48.5%' : '100%';
  const queuedTasks = useMemo(
    () => (selectedWorker ? tasks.filter((task) => task.worker_id === selectedWorker.worker_id && task.status === 'queued') : []),
    [selectedWorker, tasks],
  );

  const selectIdentity = async (identity: FleetIdentity) => {
    if (!requireFleetConnection()) return;
    setLoading(true);
    setStatus(`switching to ${identityLabel(identity)}`);
    try {
      await setFleetActiveIdentity(apiBaseUrl, token, identity.identity_id, snapshot?.selected_chat_by_identity?.[identity.identity_id] || null, 'mobile');
      await refresh(true);
      setStatus(`active identity: ${identityLabel(identity)}`);
    } catch (error) {
      showFleetError(error, 'Identity was not switched.');
    } finally {
      setLoading(false);
    }
  };

  const persistSidebarState = async (nextState: SidebarState) => {
    setSidebarState(nextState);
    if (!fleetConnected) return;
    try {
      const result = await updateSidebarState(apiBaseUrl, token, nextState);
      if (result.state) {
        setSidebarState(result.state);
      }
    } catch {
      // Sidebar persistence should not interrupt Fleet controls.
    }
  };

  const deleteConversation = async (sessionId: string) => {
    if (!requireFleetConnection()) return;
    setLoading(true);
    setStatus('deleting chat');
    try {
      await deleteSession(apiBaseUrl, token, sessionId);
      await refresh(true);
      setStatus('chat deleted');
    } catch (error) {
      showFleetError(error, 'Chat was not deleted.');
    } finally {
      setLoading(false);
    }
  };

  const addLocalWorker = async () => {
    if (!requireFleetConnection()) return;
    const displayName = workerNameDraft.trim();
    if (!displayName) {
      setStatus('enter a name for the new local agent');
      return;
    }
    setLoading(true);
    setStatus('creating local worker');
    try {
      const worker = await createFleetLocalWorker(apiBaseUrl, token, displayName, { created_by: 'mobile_user_request' });
      setWorkerNameDraft('');
      setSelectedWorkerId(worker.worker_id);
      await refresh(true);
      setStatus(`${worker.display_name} created`);
    } catch (error) {
      showFleetError(error, 'Worker was not created.');
    } finally {
      setLoading(false);
    }
  };

  const createEnrollmentCode = async () => {
    if (!requireFleetConnection()) return;
    setLoading(true);
    setStatus('creating enrollment code');
    try {
      const enrollment = await createFleetEnrollment(apiBaseUrl, token, workerNameDraft.trim() || null, 1800, { created_from: 'mobile_fleet' });
      setEnrollmentToken(enrollment.enrollment_token);
      setWorkerNameDraft('');
      await refresh(true);
      setStatus(`enrollment ready for ${enrollment.display_name || 'remote worker'}`);
    } catch (error) {
      showFleetError(error, 'Enrollment was not created.');
    } finally {
      setLoading(false);
    }
  };

  const assignTask = async (worker: FleetWorker) => {
    const prompt = (taskDrafts[worker.worker_id] || '').trim();
    if (!prompt || !requireFleetConnection()) return;
    setLoading(true);
    setStatus(`assigning ${worker.display_name}`);
    try {
      const targetSessionId = selectedChatIdForWorker(worker, identities, snapshot?.selected_chat_by_identity);
      const task = await assignFleetWorkerTask(
        apiBaseUrl,
        token,
        worker.worker_id,
        prompt,
        {
          assigned_from: 'mobile_fleet',
          ...(targetSessionId ? { target_session_id: targetSessionId } : {}),
        },
        {
          target_session_id: targetSessionId,
          target_mode: 'auto',
        },
      );
      setTaskDrafts((previous) => ({ ...previous, [worker.worker_id]: '' }));
      await refresh(true);
      setStatus(fleetTaskStatusMessage(task, worker.display_name));
    } catch (error) {
      showFleetError(error, 'Task was not assigned.');
    } finally {
      setLoading(false);
    }
  };

  const stopTask = async (task: FleetTask | null) => {
    if (!selectedWorker || !task || !requireFleetConnection()) return;
    setLoading(true);
    setStatus('stopping worker task');
    try {
      await stopFleetWorker(apiBaseUrl, token, selectedWorker.worker_id, 'Stopped from mobile Fleet', { stopped_from: 'mobile_fleet', task_id: task.task_id });
      await refresh(true);
      setStatus('task stopped');
    } catch (error) {
      showFleetError(error, 'Task was not stopped.');
    } finally {
      setLoading(false);
    }
  };

  const stopAllWorkers = async () => {
    if (!requireFleetConnection()) return;
    const confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirm, {
      action_kind: 'fleet_stop_all',
      title: 'Stop all workers?',
      message: 'This stops every reachable active Fleet run. Use this only when the whole fleet should stop now.',
      risk_tier: 'danger',
      origin_surface: 'mobile',
      payload: { stopped_from: 'mobile_fleet' },
    }, {
      confirmLabel: 'Stop All',
      tone: 'danger',
      details: ['The normal red Stop targets the visible identity and its delegation chain.', 'This action is broader than the visible task.'],
    });
    if (!confirmationId) return;
    setLoading(true);
    setStatus('stopping all workers');
    try {
      await stopAllFleetWorkers(apiBaseUrl, token, 'Stopped all from mobile Fleet', { stopped_from: 'mobile_fleet' }, confirmationId);
      await refresh(true);
      setStatus('all active worker tasks stopped');
    } catch (error) {
      showFleetError(error, 'Workers were not stopped.');
    } finally {
      setLoading(false);
    }
  };

  const redirectTask = async (task: FleetTask | null) => {
    if (!task) return;
    const direction = (redirectDrafts[task.task_id] || '').trim();
    if (!direction || !requireFleetConnection()) return;
    setLoading(true);
    setStatus('redirecting worker');
    try {
      await redirectFleetTask(apiBaseUrl, token, task.task_id, direction, { redirected_from: 'mobile_fleet' });
      setRedirectDrafts((previous) => ({ ...previous, [task.task_id]: '' }));
      await refresh(true);
      setStatus('redirect sent');
    } catch (error) {
      showFleetError(error, 'Redirect was not sent.');
    } finally {
      setLoading(false);
    }
  };

  const renameWorker = async (worker: FleetWorker) => {
    const displayName = (renameDrafts[worker.worker_id] || '').trim();
    if (!displayName || !requireFleetConnection()) return;
    setLoading(true);
    setStatus(`renaming ${worker.display_name}`);
    try {
      await renameFleetWorker(apiBaseUrl, token, worker.worker_id, displayName, { renamed_from: 'mobile_fleet' });
      setRenameDrafts((previous) => ({ ...previous, [worker.worker_id]: '' }));
      await refresh(true);
      setStatus('worker renamed');
    } catch (error) {
      showFleetError(error, 'Worker was not renamed.');
    } finally {
      setLoading(false);
    }
  };

  const deleteOrResetWorker = async (worker: FleetWorker, mode: 'delete' | 'reset') => {
    if (!requireFleetConnection()) return;
    const title = mode === 'reset' ? `Reset ${worker.display_name}?` : `Delete ${worker.display_name}?`;
    const message = mode === 'reset'
      ? 'This stops active work, revokes live access, and resets the worker identity.'
      : 'This stops active work and removes the worker from the live fleet.';
    const confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirm, {
      action_kind: mode === 'reset' ? 'fleet_worker_reset' : 'fleet_worker_delete',
      title,
      message,
      risk_tier: 'danger',
      origin_surface: 'mobile',
      payload: { worker_id: worker.worker_id, display_name: worker.display_name, mode },
    }, {
      confirmLabel: mode === 'reset' ? 'Reset' : 'Delete',
      tone: 'danger',
      details: ['Reports and task history should remain recoverable through the cloud archive where supported.', 'The live worker will no longer receive new work.'],
    });
    if (!confirmationId) return;
    setLoading(true);
    setStatus(`${mode === 'reset' ? 'resetting' : 'deleting'} ${worker.display_name}`);
    try {
      if (mode === 'reset') {
        await resetFleetWorker(apiBaseUrl, token, worker.worker_id, 'Reset from mobile Fleet', { reset_from: 'mobile_fleet' }, confirmationId);
      } else {
        await deleteFleetWorker(apiBaseUrl, token, worker.worker_id, true, confirmationId);
      }
      setSelectedWorkerId(null);
      setWorkerDetailOpen(false);
      await refresh(true);
      setStatus(`worker ${mode === 'reset' ? 'reset' : 'deleted'}`);
    } catch (error) {
      showFleetError(error, mode === 'reset' ? 'Worker was not reset.' : 'Worker was not deleted.');
    } finally {
      setLoading(false);
    }
  };

  const requestPreview = async (worker: FleetWorker) => {
    if (!requireFleetConnection()) return;
    setLoading(true);
    setStatus('requesting worker preview');
    try {
      await requestFleetWorkerPreview(apiBaseUrl, token, worker.worker_id);
      await refresh(true);
      setStatus('preview requested');
    } catch (error) {
      showFleetError(error, 'Preview was not requested.');
    } finally {
      setLoading(false);
    }
  };

  const cancelQueuedTask = async (task: FleetTask) => {
    if (!requireFleetConnection()) return;
    setLoading(true);
    setStatus('canceling queued task');
    try {
      await updateFleetTaskStatus(apiBaseUrl, token, task.task_id, 'canceled', { canceled_from: 'mobile_fleet' });
      await refresh(true);
      setStatus('queued task canceled');
    } catch (error) {
      showFleetError(error, 'Queued task was not canceled.');
    } finally {
      setLoading(false);
    }
  };

  const continueQueue = async (worker: FleetWorker) => {
    if (!requireFleetConnection()) return;
    setLoading(true);
    setStatus('continuing worker queue');
    try {
      const report = latestReportForWorker(worker, reports);
      await continueFleetWorkerQueue(apiBaseUrl, token, worker.worker_id, report?.report_id || null, { continued_from: 'mobile_fleet' });
      await refresh(true);
      setStatus('next queued task started');
    } catch (error) {
      showFleetError(error, 'Queue was not continued.');
    } finally {
      setLoading(false);
    }
  };

  const moveQueuedTask = async (task: FleetTask, direction: -1 | 1) => {
    if (!selectedWorker || !requireFleetConnection()) return;
    const ordered = [...queuedTasks].sort((left, right) => left.queue_position - right.queue_position);
    const index = ordered.findIndex((item) => item.task_id === task.task_id);
    const nextIndex = index + direction;
    if (index < 0 || nextIndex < 0 || nextIndex >= ordered.length) return;
    const next = [...ordered];
    const [moved] = next.splice(index, 1);
    next.splice(nextIndex, 0, moved);
    setLoading(true);
    setStatus('reordering queue');
    try {
      await reorderFleetTasks(apiBaseUrl, token, selectedWorker.worker_id, next.map((item) => item.task_id));
      await refresh(true);
      setStatus('queue reordered');
    } catch (error) {
      showFleetError(error, 'Queue was not reordered.');
    } finally {
      setLoading(false);
    }
  };

  const createSelectedWorkerGroup = async () => {
    const name = groupNameDraft.trim();
    if (!name || !selectedWorker || !requireFleetConnection()) return;
    setLoading(true);
    setStatus('creating group');
    try {
      await createFleetGroup(apiBaseUrl, token, name, [selectedWorker.worker_id], null, { created_from: 'mobile_fleet' });
      setGroupNameDraft('');
      await refresh(true);
      setStatus('group created');
    } catch (error) {
      showFleetError(error, 'Group was not created.');
    } finally {
      setLoading(false);
    }
  };

  const deleteGroup = async (group: FleetGroup) => {
    if (!requireFleetConnection()) return;
    const confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirm, {
      action_kind: 'fleet_group_delete',
      title: `Delete ${groupLabel(group)}?`,
      message: 'The workers remain in the fleet. Only this group is removed.',
      risk_tier: 'danger',
      origin_surface: 'mobile',
      payload: { group_id: group.group_id, display_name: group.display_name },
    }, {
      confirmLabel: 'Delete Group',
      tone: 'danger',
    });
    if (!confirmationId) return;
    setLoading(true);
    setStatus('deleting group');
    try {
      await deleteFleetGroup(apiBaseUrl, token, group.group_id, confirmationId);
      await refresh(true);
      setStatus('group deleted');
    } catch (error) {
      showFleetError(error, 'Group was not deleted.');
    } finally {
      setLoading(false);
    }
  };

  const assignGroupTask = async (group: FleetGroup) => {
    const prompt = (groupTaskDrafts[group.group_id] || '').trim();
    if (!prompt || !requireFleetConnection()) return;
    const targetWorkers = workers.filter((worker) => group.worker_ids?.includes(worker.worker_id));
    const confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirm, {
      action_kind: 'fleet_group_dispatch',
      title: `Dispatch to ${groupLabel(group)}?`,
      message: `${targetWorkers.length || group.worker_ids?.length || 0} workers will receive this task. Busy workers queue it by default.`,
      risk_tier: 'access',
      origin_surface: 'mobile',
      payload: { group_id: group.group_id, worker_count: targetWorkers.length || group.worker_ids?.length || 0, prompt_preview: prompt.slice(0, 240) },
    }, {
      confirmLabel: 'Dispatch',
      tone: 'access',
      details: targetWorkers.slice(0, 8).map((worker) => `${worker.display_name}: ${worker.status}`),
    });
    if (!confirmationId) return;
    setLoading(true);
    setStatus('dispatching group task');
    try {
      const tasks = await assignFleetGroupTask(apiBaseUrl, token, group.group_id, prompt, {
        assigned_from: 'mobile_fleet',
        bulk_dispatch_confirmed: true,
      }, undefined, confirmationId);
      setGroupTaskDrafts((previous) => ({ ...previous, [group.group_id]: '' }));
      await refresh(true);
      setStatus(fleetTaskBatchStatusMessage(tasks, groupLabel(group)));
    } catch (error) {
      showFleetError(error, 'Group task was not dispatched.');
    } finally {
      setLoading(false);
    }
  };

  const decideGrant = async (grant: FleetToolGrant, approved: boolean) => {
    if (!requireFleetConnection()) return;
    setLoading(true);
    setStatus(approved ? 'approving tool grant' : 'denying tool grant');
    try {
      await decideFleetToolGrant(apiBaseUrl, token, grant.grant_id, approved, approved ? Math.min(10, grant.requested_turns || 10) : null);
      await refresh(true);
      setStatus(approved ? 'grant approved' : 'grant denied');
    } catch (error) {
      showFleetError(error, 'Tool grant was not updated.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      {confirmationDialog}
      <AppDrawer
        visible={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        sessions={sessions}
        jobs={jobs}
        activeSessionId={undefined}
        backendLabel={apiBaseUrl || 'Backend not configured'}
        sidebarState={sidebarState}
        onCreateSession={(workspace) => {
          setDrawerOpen(false);
          router.push({ pathname: '/chat', params: { newSession: '1', workspace } });
        }}
        onSelectSession={(sessionId) => {
          setDrawerOpen(false);
          router.push({ pathname: '/chat', params: { sessionId } });
        }}
        onDeleteSession={(sessionId) => {
          void deleteConversation(sessionId);
        }}
        onSidebarStateChange={(nextState) => {
          void persistSidebarState(nextState);
        }}
      />
      <View style={styles.modeTabs}>
        <Pressable accessibilityRole="button" accessibilityLabel="Open sidebar" style={styles.sidebarButton} onPress={() => setDrawerOpen(true)}>
          <Text style={styles.sidebarButtonText}>☰</Text>
        </Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel="Open Chat" style={styles.modeTab} onPress={() => router.push('/chat')}>
          <Text style={styles.modeTabText}>Chat</Text>
        </Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel="Fleet selected" accessibilityState={{ selected: true }} style={[styles.modeTab, styles.modeTabActive]}>
          <Text style={[styles.modeTabText, styles.modeTabTextActive]}>Fleet</Text>
        </Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel="Open Agent" style={styles.modeTab} onPress={() => router.push('/agent')}>
          <Text style={styles.modeTabText}>Agent</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <PageHeader
          eyebrow="Fleet V1"
          title="Workers"
          subtitle={shortStatusText(status)}
          right={(
          <View style={styles.headerActions}>
            <Pressable accessibilityRole="button" accessibilityLabel="Refresh Fleet" disabled={loading} style={[styles.smallButton, loading ? styles.disabled : null]} onPress={() => void refresh()}>
              <Text style={styles.smallButtonText}>Refresh</Text>
            </Pressable>
            <Pressable accessibilityRole="button" accessibilityLabel="Stop all workers" disabled={actionDisabled || !hasActiveFleetTask} style={[styles.smallDangerButton, (actionDisabled || !hasActiveFleetTask) ? styles.disabled : null]} onPress={() => void stopAllWorkers()}>
              <Text style={styles.smallDangerButtonText}>Stop All</Text>
            </Pressable>
          </View>
          )}
        />

        {fleetSetupMissing ? (
          <View style={styles.setupCard}>
            <Text style={styles.setupTitle}>Connect Fleet</Text>
            <Text style={styles.setupText}>{fleetSetupMessage}</Text>
            <View style={styles.row}>
              <Pressable accessibilityRole="button" accessibilityLabel="Open Pair from Fleet" style={styles.secondaryButton} onPress={() => router.push('/pair')}>
                <Text style={styles.secondaryText}>Open Pair</Text>
              </Pressable>
              <Pressable accessibilityRole="button" accessibilityLabel="Open Settings from Fleet" style={styles.secondaryButton} onPress={() => router.push('/settings')}>
                <Text style={styles.secondaryText}>Settings</Text>
              </Pressable>
            </View>
          </View>
        ) : null}

        <View style={styles.card}>
          <Text style={styles.sectionTitle}>Add Worker</Text>
          <TextInput
            style={styles.input}
            value={workerNameDraft}
            onChangeText={setWorkerNameDraft}
            placeholder="Name the new local agent"
            placeholderTextColor="#7285a6"
            accessibilityLabel="New local agent name"
          />
          <View style={styles.row}>
            <Pressable accessibilityRole="button" accessibilityLabel="Create local agent" disabled={actionDisabled || !workerNameDraft.trim()} style={[styles.primaryButton, actionDisabled || !workerNameDraft.trim() ? styles.disabled : null]} onPress={() => void addLocalWorker()}>
              <Text style={styles.primaryText}>Create local agent</Text>
            </Pressable>
            <Pressable accessibilityRole="button" accessibilityLabel="Create remote enrollment code" disabled={actionDisabled} style={[styles.secondaryButton, actionDisabled ? styles.disabled : null]} onPress={() => void createEnrollmentCode()}>
              <Text style={styles.secondaryText}>Enrollment Code</Text>
            </Pressable>
          </View>
          {enrollmentToken ? (
            <View style={styles.tokenBox}>
              <Text style={styles.tokenLabel}>Remote enrollment token</Text>
              <Text style={styles.tokenText} selectable>{enrollmentToken}</Text>
            </View>
          ) : null}
        </View>

        <View style={styles.workerGrid}>
          {workers.map((worker) => {
            const task = activeTaskForWorker(worker, tasks);
            const report = latestReportForWorker(worker, reports);
            const selected = selectedWorker?.worker_id === worker.worker_id;
            const queueCount = tasks.filter((item) => item.worker_id === worker.worker_id && item.status === 'queued').length;
            return (
              <Pressable
                key={worker.worker_id}
                style={[styles.workerCard, { width: workerCardWidth }, selected ? styles.workerCardActive : null]}
                accessibilityRole="button"
                accessibilityLabel={`Open ${worker.display_name}`}
                onPress={() => {
                  setSelectedWorkerId(worker.worker_id);
                  setWorkerActionMenuOpen(false);
                  setWorkerDetailOpen(true);
                }}
              >
                <View style={styles.workerHeader}>
                  <View style={styles.workerTitleBlock}>
                    <Text style={styles.workerName}>{worker.display_name}</Text>
                    <Text style={styles.workerMeta}>{worker.kind} · {worker.status}{queueCount ? ` · ${queueCount} queued` : ''}</Text>
                  </View>
                  <StatusPill label={task ? task.status : 'Idle'} tone={task ? 'accent' : 'good'} />
                </View>
                <Text style={styles.cardLabel}>Current</Text>
                <Text style={styles.cardValue} numberOfLines={3}>{task?.prompt || 'Idle'}</Text>
                <Text style={styles.cardLabel}>Latest Report</Text>
                <Text style={styles.cardValue} numberOfLines={3}>{report?.summary || 'No report yet'}</Text>
              </Pressable>
            );
          })}
          {!workers.length ? (
            <View style={styles.emptyCard}>
              <Text style={styles.emptyTitle}>{fleetSetupMissing ? 'Fleet not connected' : 'No workers yet'}</Text>
              <Text style={styles.empty}>{fleetSetupMissing ? 'Pair this phone before creating local workers or remote enrollment codes.' : 'Create a local worker or enroll a remote machine.'}</Text>
            </View>
          ) : null}
        </View>

        {selectedWorker ? (
          <BottomSheet
            visible={workerDetailOpen}
            title={selectedWorker.display_name}
            subtitle={selectedTask ? `${selectedTask.status}: ${selectedTask.prompt}` : 'Ready for assignment'}
            onClose={() => {
              setWorkerActionMenuOpen(false);
              setWorkerDetailOpen(false);
            }}
          >
          <View style={styles.detailSheetContent}>
            <Text style={styles.bodyText}>
              {selectedTask ? `${selectedTask.status}: ${selectedTask.prompt}` : 'Ready for assignment'}
            </Text>
            <View style={styles.compactPanel}>
              <View style={styles.sectionHeaderRow}>
                <Text style={styles.cardLabel}>Worker controls</Text>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Open worker actions"
                  style={styles.overflowButton}
                  onPress={() => setWorkerActionMenuOpen((current) => !current)}
                >
                  <Text style={styles.overflowText}>...</Text>
                </Pressable>
              </View>
              {workerActionMenuOpen ? (
                <>
                  <TextInput
                    style={styles.input}
                    value={renameDrafts[selectedWorker.worker_id] || ''}
                    onChangeText={(value) => setRenameDrafts((previous) => ({ ...previous, [selectedWorker.worker_id]: value }))}
                    placeholder="Rename worker"
                    placeholderTextColor="#7285a6"
                  />
                  <View style={styles.wrapRow}>
                    <Pressable
                      disabled={actionDisabled || !(renameDrafts[selectedWorker.worker_id] || '').trim()}
                      style={[styles.secondaryButton, (actionDisabled || !(renameDrafts[selectedWorker.worker_id] || '').trim()) ? styles.disabled : null]}
                      onPress={() => void renameWorker(selectedWorker)}
                    >
                      <Text style={styles.secondaryText}>Rename</Text>
                    </Pressable>
                    {String(selectedWorker.kind || '').trim().toLowerCase() !== 'local' ? (
                      <Pressable disabled={actionDisabled} style={[styles.secondaryButton, actionDisabled ? styles.disabled : null]} onPress={() => void requestPreview(selectedWorker)}>
                        <Text style={styles.secondaryText}>Preview</Text>
                      </Pressable>
                    ) : null}
                  </View>
                  <View style={styles.wrapRow}>
                    <Pressable disabled={actionDisabled || !selectedTask} style={[styles.dangerButton, (actionDisabled || !selectedTask) ? styles.disabled : null]} onPress={() => void stopTask(selectedTask)}>
                      <Text style={styles.dangerText}>Stop Worker</Text>
                    </Pressable>
                    <Pressable disabled={actionDisabled} style={[styles.dangerButton, actionDisabled ? styles.disabled : null]} onPress={() => void deleteOrResetWorker(selectedWorker, 'reset')}>
                      <Text style={styles.dangerText}>Reset</Text>
                    </Pressable>
                    <Pressable disabled={actionDisabled} style={[styles.dangerButton, actionDisabled ? styles.disabled : null]} onPress={() => void deleteOrResetWorker(selectedWorker, 'delete')}>
                      <Text style={styles.dangerText}>Delete</Text>
                    </Pressable>
                  </View>
                </>
              ) : (
                <Text style={styles.bodyText}>Assign work below. Use the menu for rename, stop, reset, delete, and remote preview.</Text>
              )}
            </View>
            <TextInput
              style={[styles.input, styles.multilineInput]}
              value={taskDrafts[selectedWorker.worker_id] || ''}
              onChangeText={(value) => setTaskDrafts((previous) => ({ ...previous, [selectedWorker.worker_id]: value }))}
              placeholder="Assign a task"
              placeholderTextColor="#7285a6"
              multiline
            />
            <Pressable
              disabled={actionDisabled || !(taskDrafts[selectedWorker.worker_id] || '').trim()}
              style={[styles.primaryButton, (actionDisabled || !(taskDrafts[selectedWorker.worker_id] || '').trim()) ? styles.disabled : null]}
              onPress={() => void assignTask(selectedWorker)}
            >
              <Text style={styles.primaryText}>Assign Task</Text>
            </Pressable>

            {selectedTask ? (
              <View style={styles.taskControls}>
                <TextInput
                  style={[styles.input, styles.multilineInput]}
                  value={redirectDrafts[selectedTask.task_id] || ''}
                  onChangeText={(value) => setRedirectDrafts((previous) => ({ ...previous, [selectedTask.task_id]: value }))}
                  placeholder="Redirect active task"
                  placeholderTextColor="#7285a6"
                  multiline
                />
                <View style={styles.row}>
                  <Pressable disabled={actionDisabled} style={[styles.secondaryButton, actionDisabled ? styles.disabled : null]} onPress={() => void redirectTask(selectedTask)}>
                    <Text style={styles.secondaryText}>Redirect</Text>
                  </Pressable>
                  <Pressable disabled={actionDisabled} style={[styles.dangerButton, actionDisabled ? styles.disabled : null]} onPress={() => void stopTask(selectedTask)}>
                    <Text style={styles.dangerText}>Stop</Text>
                  </Pressable>
                </View>
              </View>
            ) : null}

            {queuedTasks.length ? (
              <View style={styles.queueList}>
                <View style={styles.sectionHeaderRow}>
                  <Text style={styles.cardLabel}>Queue</Text>
                  <Pressable
                    disabled={actionDisabled || Boolean(selectedTask)}
                    style={[styles.miniButton, (actionDisabled || Boolean(selectedTask)) ? styles.disabled : null]}
                    onPress={() => void continueQueue(selectedWorker)}
                  >
                    <Text style={styles.miniButtonText}>Continue</Text>
                  </Pressable>
                </View>
                {[...queuedTasks].sort((left, right) => left.queue_position - right.queue_position).slice(0, 8).map((task, index) => (
                  <View key={task.task_id} style={styles.queueRow}>
                    <Text style={styles.queueItem} numberOfLines={2}>
                      {task.queue_position}. {task.prompt}
                    </Text>
                    <View style={styles.queueActions}>
                      <Pressable disabled={actionDisabled || index === 0} style={[styles.queueActionButton, (actionDisabled || index === 0) ? styles.disabled : null]} onPress={() => void moveQueuedTask(task, -1)}>
                        <Text style={styles.queueActionText}>Up</Text>
                      </Pressable>
                      <Pressable disabled={actionDisabled || index === queuedTasks.length - 1} style={[styles.queueActionButton, (actionDisabled || index === queuedTasks.length - 1) ? styles.disabled : null]} onPress={() => void moveQueuedTask(task, 1)}>
                        <Text style={styles.queueActionText}>Down</Text>
                      </Pressable>
                      <Pressable disabled={actionDisabled} style={[styles.queueDangerButton, actionDisabled ? styles.disabled : null]} onPress={() => void cancelQueuedTask(task)}>
                        <Text style={styles.queueDangerText}>Cancel</Text>
                      </Pressable>
                    </View>
                  </View>
                ))}
              </View>
            ) : null}

            {selectedReport ? (
              <View style={styles.reportBox}>
                <Text style={styles.cardLabel}>Latest structured report</Text>
                <Text style={styles.cardValue}>{selectedReport.summary}</Text>
                <Text style={styles.reportMeta}>
                  {selectedReport.status} · {selectedReport.confidence || 'confidence unknown'} · {selectedReport.created_at ? formatRelativeTime(selectedReport.created_at) : 'recent'}
                </Text>
                {selectedReport.next_suggested_action ? (
                  <Text style={styles.cardValue}>{selectedReport.next_suggested_action}</Text>
                ) : null}
              </View>
            ) : null}
          </View>
          </BottomSheet>
        ) : null}

        <View style={styles.card}>
          <Text style={styles.sectionTitle}>Groups</Text>
          <Text style={styles.bodyText}>Create a group from the selected worker, then dispatch tasks to the whole group.</Text>
          <View style={styles.row}>
            <TextInput
              style={[styles.input, styles.flexInput]}
              value={groupNameDraft}
              onChangeText={setGroupNameDraft}
              placeholder="New group name"
              placeholderTextColor="#7285a6"
            />
            <Pressable
              disabled={actionDisabled || !selectedWorker || !groupNameDraft.trim()}
              style={[styles.secondaryButton, (actionDisabled || !selectedWorker || !groupNameDraft.trim()) ? styles.disabled : null]}
              onPress={() => void createSelectedWorkerGroup()}
            >
              <Text style={styles.secondaryText}>Create</Text>
            </Pressable>
          </View>
          {groups.length ? (
            <View style={styles.groupList}>
              {groups.map((group) => (
                <View key={group.group_id} style={styles.groupRow}>
                  <View style={styles.groupHeader}>
                    <View style={styles.workerTitleBlock}>
                      <Text style={styles.workerName}>{groupLabel(group)}</Text>
                      <Text style={styles.workerMeta}>{group.worker_ids?.length || 0} workers</Text>
                    </View>
                    <Pressable disabled={actionDisabled} style={[styles.queueDangerButton, actionDisabled ? styles.disabled : null]} onPress={() => void deleteGroup(group)}>
                      <Text style={styles.queueDangerText}>Delete</Text>
                    </Pressable>
                  </View>
                  <TextInput
                    style={[styles.input, styles.multilineInput]}
                    value={groupTaskDrafts[group.group_id] || ''}
                    onChangeText={(value) => setGroupTaskDrafts((previous) => ({ ...previous, [group.group_id]: value }))}
                    placeholder="Dispatch a task to this group"
                    placeholderTextColor="#7285a6"
                    multiline
                  />
                  <Pressable
                    disabled={actionDisabled || !(groupTaskDrafts[group.group_id] || '').trim()}
                    style={[styles.primaryButton, (actionDisabled || !(groupTaskDrafts[group.group_id] || '').trim()) ? styles.disabled : null]}
                    onPress={() => void assignGroupTask(group)}
                  >
                    <Text style={styles.primaryText}>Dispatch Group Task</Text>
                  </Pressable>
                </View>
              ))}
            </View>
          ) : (
            <Text style={styles.empty}>No groups yet.</Text>
          )}
        </View>

        <View style={styles.card}>
          <Text style={styles.sectionTitle}>Tool Grants</Text>
          <Text style={styles.bodyText}>Approve or deny temporary worker tool-pack requests.</Text>
          {pendingToolGrants.length ? (
            <View style={styles.groupList}>
              {pendingToolGrants.map((grant) => (
                <View key={grant.grant_id} style={styles.grantRow}>
                  <Text style={styles.cardValue}>{grantLabel(grant)}</Text>
                  {grant.reason ? <Text style={styles.bodyText}>{grant.reason}</Text> : null}
                  <View style={styles.row}>
                    <Pressable disabled={actionDisabled} style={[styles.primaryButton, actionDisabled ? styles.disabled : null]} onPress={() => void decideGrant(grant, true)}>
                      <Text style={styles.primaryText}>Approve</Text>
                    </Pressable>
                    <Pressable disabled={actionDisabled} style={[styles.dangerButton, actionDisabled ? styles.disabled : null]} onPress={() => void decideGrant(grant, false)}>
                      <Text style={styles.dangerText}>Deny</Text>
                    </Pressable>
                  </View>
                </View>
              ))}
            </View>
          ) : (
            <Text style={styles.empty}>No pending tool grants.</Text>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: '#081120',
  },
  modeTabs: {
    flexDirection: 'row',
    gap: 8,
    paddingHorizontal: 16,
    paddingTop: 10,
    paddingBottom: 8,
    backgroundColor: '#0d172a',
    borderBottomWidth: 1,
    borderBottomColor: '#1e2b45',
  },
  sidebarButton: {
    width: 44,
    minHeight: 42,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#14203a',
  },
  sidebarButtonText: {
    color: '#d7e6ff',
    fontSize: 18,
    fontWeight: '900',
  },
  modeTab: {
    flex: 1,
    minHeight: 42,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#14203a',
  },
  modeTabActive: {
    backgroundColor: '#2dd4bf',
  },
  modeTabText: {
    color: '#d7e6ff',
    fontWeight: '800',
  },
  modeTabTextActive: {
    color: '#04111d',
  },
  content: {
    padding: 16,
    gap: 14,
    paddingBottom: 32,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
  },
  headerActions: {
    gap: 8,
    minWidth: 96,
  },
  headerCopy: {
    flex: 1,
    gap: 4,
  },
  eyebrow: {
    color: '#2dd4bf',
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  title: {
    color: '#f8fbff',
    fontSize: 30,
    fontWeight: '900',
  },
  subtitle: {
    color: '#91a4c4',
    fontSize: 13,
    lineHeight: 18,
  },
  card: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#1f3650',
    backgroundColor: '#0d1a2d',
    padding: 14,
    gap: 10,
  },
  setupCard: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#7b5423',
    backgroundColor: '#1b160c',
    padding: 14,
    gap: 10,
  },
  setupTitle: {
    color: '#ffd89f',
    fontSize: 16,
    fontWeight: '900',
  },
  setupText: {
    color: '#fff4df',
    fontSize: 13,
    lineHeight: 19,
  },
  sectionTitle: {
    color: '#f5f9ff',
    fontSize: 16,
    fontWeight: '900',
  },
  bodyText: {
    color: '#a6b6d2',
    fontSize: 13,
    lineHeight: 19,
  },
  identityGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  identityChip: {
    minWidth: 128,
    flexGrow: 1,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#24425f',
    backgroundColor: '#0a1424',
    padding: 10,
    gap: 3,
  },
  identityChipActive: {
    borderColor: '#2dd4bf',
    backgroundColor: '#12353f',
  },
  identityName: {
    color: '#e9f3ff',
    fontWeight: '900',
  },
  identityNameActive: {
    color: '#ffffff',
  },
  identityMeta: {
    color: '#7e91b1',
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  identityMetaActive: {
    color: '#9ff5ea',
  },
  input: {
    minHeight: 42,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#25415f',
    color: '#f4f9ff',
    backgroundColor: '#07111f',
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
  },
  flexInput: {
    flex: 1,
  },
  multilineInput: {
    minHeight: 86,
    textAlignVertical: 'top',
  },
  row: {
    flexDirection: 'row',
    gap: 10,
  },
  wrapRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  primaryButton: {
    flex: 1,
    minHeight: 44,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#2dd4bf',
    paddingHorizontal: 12,
  },
  primaryText: {
    color: '#04111d',
    fontWeight: '900',
  },
  secondaryButton: {
    flex: 1,
    minHeight: 44,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#2b5070',
    backgroundColor: '#10243a',
    paddingHorizontal: 12,
  },
  secondaryText: {
    color: '#d9efff',
    fontWeight: '900',
  },
  smallButton: {
    minHeight: 40,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#2b5070',
    paddingHorizontal: 12,
    backgroundColor: '#10243a',
  },
  smallButtonText: {
    color: '#d9efff',
    fontWeight: '900',
  },
  smallDangerButton: {
    minHeight: 40,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#7f2342',
    paddingHorizontal: 12,
    backgroundColor: '#3a1020',
  },
  smallDangerButtonText: {
    color: '#ffc8d8',
    fontWeight: '900',
  },
  dangerButton: {
    flex: 1,
    minHeight: 44,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#7f2342',
    backgroundColor: '#3a1020',
    paddingHorizontal: 12,
  },
  dangerText: {
    color: '#ffc8d8',
    fontWeight: '900',
  },
  disabled: {
    opacity: 0.55,
  },
  tokenBox: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#7b5423',
    backgroundColor: '#1b160c',
    padding: 10,
    gap: 6,
  },
  tokenLabel: {
    color: '#ffd89f',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  tokenText: {
    color: '#fff4df',
    fontSize: 13,
    lineHeight: 18,
  },
  workerGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  workerCard: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#1f3650',
    backgroundColor: '#0d1a2d',
    padding: 13,
    gap: 8,
  },
  detailSheetContent: {
    gap: 12,
  },
  workerCardActive: {
    borderColor: '#2dd4bf',
  },
  workerHeader: {
    flexDirection: 'row',
    gap: 10,
  },
  workerTitleBlock: {
    flex: 1,
    gap: 2,
  },
  workerName: {
    color: '#f8fbff',
    fontSize: 17,
    fontWeight: '900',
  },
  workerMeta: {
    color: '#8fa4c4',
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  cardLabel: {
    color: '#7d94b8',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  cardValue: {
    color: '#e8f2ff',
    fontSize: 13,
    lineHeight: 19,
  },
  compactPanel: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#24425f',
    backgroundColor: '#07111f',
    padding: 10,
    gap: 8,
  },
  taskControls: {
    gap: 10,
  },
  queueList: {
    gap: 6,
  },
  sectionHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  miniButton: {
    minHeight: 32,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#2b5070',
    backgroundColor: '#10243a',
    paddingHorizontal: 10,
  },
  miniButtonText: {
    color: '#d9efff',
    fontSize: 12,
    fontWeight: '900',
  },
  overflowButton: {
    minWidth: 36,
    minHeight: 32,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#2b5070',
    backgroundColor: '#10243a',
    alignItems: 'center',
    justifyContent: 'center',
  },
  overflowText: {
    color: '#d9efff',
    fontSize: 18,
    lineHeight: 18,
    fontWeight: '900',
  },
  queueRow: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#203754',
    backgroundColor: '#081526',
    padding: 9,
    gap: 8,
  },
  queueItem: {
    flex: 1,
    color: '#cad9f2',
    fontSize: 13,
    lineHeight: 18,
  },
  queueActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  queueActionButton: {
    minHeight: 30,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#2b5070',
    backgroundColor: '#10243a',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 9,
  },
  queueActionText: {
    color: '#d9efff',
    fontSize: 11,
    fontWeight: '900',
  },
  queueDangerButton: {
    minHeight: 30,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#7f2342',
    backgroundColor: '#3a1020',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 9,
  },
  queueDangerText: {
    color: '#ffc8d8',
    fontSize: 11,
    fontWeight: '900',
  },
  reportBox: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#24425f',
    backgroundColor: '#07111f',
    padding: 10,
    gap: 7,
  },
  reportMeta: {
    color: '#9ff5ea',
    fontSize: 12,
    fontWeight: '800',
  },
  emptyCard: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#1f3650',
    backgroundColor: '#0d1a2d',
    padding: 16,
    gap: 6,
  },
  emptyTitle: {
    color: '#f8fbff',
    fontSize: 16,
    fontWeight: '900',
  },
  empty: {
    color: '#93a6c5',
    fontSize: 13,
    lineHeight: 19,
  },
  groupList: {
    gap: 10,
  },
  groupRow: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#24425f',
    backgroundColor: '#07111f',
    padding: 10,
    gap: 9,
  },
  groupHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  grantRow: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#24425f',
    backgroundColor: '#07111f',
    padding: 10,
    gap: 8,
  },
});
