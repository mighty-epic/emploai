import type { DesktopConversationScope } from './DesktopConversationScope'; type NativeSyntheticEvent<T = any> = any; type ActiveCommandPanel = any; type ActivityItem = any; type AgentOverview = any; type ArtifactDetail = any; type ArtifactSummary = any; type ComposerInputOrigin = any; type ConversationSurfaceMode = any; type DesktopFleetEnrollment = any; type DesktopFleetIdentity = any; type DesktopFleetSnapshot = any; type DesktopFleetTask = any; type DesktopFleetWorker = any; type DesktopGitRepoState = any; type DesktopMessage = any; type DesktopPathStatus = any; type DesktopRuntimeStatus = any; type DesktopSidebarProjectActivity = any; type DesktopSidebarState = any; type DesktopVoicePackState = any; type DesktopVoiceRuntimeStatus = any; type InterruptPolicy = any; type JarvisSttBackend = any; type JarvisTtsBackend = any; type LayoutChangeEvent = any; type MessageSourceFormat = any; type ModelProviderGroup = any; type NativeScrollEvent = any; type PendingSearchJump = any; type QueuedComposerMessage = any; type QueuedMessage = any; type RealtimeChannel = any; type RealtimeEvent = any; type ReferenceEntry = any; type RuntimeOrchestratorStatus = any; type ScheduledJob = any; type SearchResultTarget = any; type SecurityPermissionMode = any; type SessionDetail = any; type SessionMessage = any; type SessionSearchResult = any; type SessionSummary = any; type SessionTimelineEvent = any; type SidebarChatTooltipState = any; type SidebarDragState = any; type SidebarDraftChat = any; type SidebarProjectGroup = any; type StartupReadinessState = any; type TaskBoard = any; type TelegramBotConfig = any; type TextInputContentSizeChangeEventData = any; type ToolPackInfoPopupState = any; type VoiceCaptureMode = any; type VoiceGateState = any;
import { updateDesktopFleetWorkerQueuePolicy } from '@/lib/desktopBridge';

export function useDesktopConversationFleetActions(scope: DesktopConversationScope) {
  const { HEBREW_VOICE_GATE_MAX_MS, HEBREW_VOICE_GATE_PREROLL_MS, Platform, VOICE_GATE_MAX_MS, VOICE_GATE_PREROLL_MS, apiBaseUrl, assignDesktopFleetGroupTask, assignDesktopFleetTask, confirmAction, continueDesktopFleetWorkerQueue, copyDesktopText, createApprovedConfirmation, createDesktopFleetEnrollment, createDesktopFleetGroup, createDesktopFleetLocalWorker, deleteDesktopFleetGroup, deleteDesktopFleetWorker, describeError, fleetEnrollment, fleetGroupNameDraft, fleetGroupTaskDrafts, fleetRenameDrafts, fleetSnapshot, fleetTaskBatchStatusMessage, fleetTaskDrafts, fleetTaskStatusMessage, fleetWorkerNameDraft, fleetWorkers, floatingPanelRef, isBlockedFleetTask, loadDesktopFleetSnapshot, pinnedToolPackInfoId, projectMenuRefs, projectMenuTriggerRefs, remoteAuthStatus, renameDesktopFleetWorker, requestDesktopFleetWorkerPreview, resetDesktopFleetWorker, sessionBelongsToFleetIdentity, sessionId, sessionMenuRefs, sessionMenuTriggerRefs, sessionRowRefs, sessions, setDesktopFleetActiveIdentity, setFleetEnrollment, setFleetError, setFleetGroupNameDraft, setFleetGroupTaskDrafts, setFleetLoading, setFleetRenameDrafts, setFleetSnapshot, setFleetStatus, setFleetTaskDrafts, setFleetWorkerNameDraft, setHoveredToolPackInfoId, setPinnedToolPackInfoId, setSidebarChatTooltip, setToolPackInfoPopup, shellRef, sidebarChatTooltipTimerRef, status, stopAllDesktopFleetWorkers, stopDesktopFleetWorker, token, toolPackInfoButtonRefs, toolPackInfoHideTimerRef, userFacingError, usingHebrewVoiceEngine } = scope;
  const openSession = (...args: any[]) => scope.openSession?.(...args);
  const clearConversationSelection = (...args: any[]) => scope.clearConversationSelection?.(...args);
  const fleetSelectedChatIdForWorker = (...args: any[]) => scope.fleetSelectedChatIdForWorker?.(...args);
  const telegramBotLabelForSession = (...args: any[]) => scope.telegramBotLabelForSession?.(...args);
  const setFleetPreview = scope.setFleetPreview as ((value: any) => void) | undefined;
const setProjectMenuRef = (projectPath: string) => (node: any) => {
    if (node) {
      projectMenuRefs.current[projectPath] = node;
      return;
    }
    delete projectMenuRefs.current[projectPath];
  };

  const setProjectMenuTriggerRef = (projectPath: string) => (node: any) => {
    if (node) {
      projectMenuTriggerRefs.current[projectPath] = node;
      return;
    }
    delete projectMenuTriggerRefs.current[projectPath];
  };

  const setSessionRowRef = (targetSessionId: string) => (node: any) => {
    if (node) {
      sessionRowRefs.current[targetSessionId] = node;
      return;
    }
    delete sessionRowRefs.current[targetSessionId];
  };

  const setSessionMenuRef = (targetSessionId: string) => (node: any) => {
    if (node) {
      sessionMenuRefs.current[targetSessionId] = node;
      return;
    }
    delete sessionMenuRefs.current[targetSessionId];
  };

  const setSessionMenuTriggerRef = (targetSessionId: string) => (node: any) => {
    if (node) {
      sessionMenuTriggerRefs.current[targetSessionId] = node;
      return;
    }
    delete sessionMenuTriggerRefs.current[targetSessionId];
  };

  const setToolPackInfoButtonRef = (packId: string) => (node: any) => {
    if (node) {
      toolPackInfoButtonRefs.current[packId] = node;
      return;
    }
    delete toolPackInfoButtonRefs.current[packId];
  };
  const activeVoiceGatePrerollMs = usingHebrewVoiceEngine ? HEBREW_VOICE_GATE_PREROLL_MS : VOICE_GATE_PREROLL_MS;
  const activeVoiceGateMaxMs = usingHebrewVoiceEngine ? HEBREW_VOICE_GATE_MAX_MS : VOICE_GATE_MAX_MS;

  const normalizeFleetSnapshotManagers = (snapshot: DesktopFleetSnapshot | null | undefined): DesktopFleetSnapshot | null | undefined => {
    if (!snapshot) {
      return snapshot;
    }
    const currentDesktopId = String(
      remoteAuthStatus?.desktop?.desktop_id
      || snapshot.manager?.desktop_id
      || '',
    ).trim();
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
      instances.find((item: any) => String(item?.role || '').toLowerCase() === 'manager')
      || identities.find((item: any) => String(item?.role || '').toLowerCase() === 'manager')
      || snapshotManager
      || null
    );
    const visibleIdentityIds = new Set(identities.map((item: any) => String(item?.identity_id || '').trim()).filter(Boolean));
    const selectedChatByIdentity = Object.fromEntries(
      Object.entries(snapshot.selected_chat_by_identity || {})
        .filter(([identityId]) => visibleIdentityIds.has(String(identityId || '').trim())),
    );
    const activeIdentityVisible = snapshot.active_identity?.identity_id
      && visibleIdentityIds.has(String(snapshot.active_identity.identity_id));
    const activeIdentity = activeIdentityVisible
      ? snapshot.active_identity
      : identities.find((item: any) => String(item?.identity_id || '') === String(currentManager?.identity_id || currentManager?.instance_id || ''))
        || currentManager
        || identities[0]
        || null;
    return {
      ...snapshot,
      identities,
      instances,
      manager: currentManager,
      active_identity: activeIdentity,
      active_identity_id: activeIdentity?.identity_id || activeIdentity?.instance_id || null,
      selected_chat_by_identity: selectedChatByIdentity,
    };
  };

  const clearSidebarChatTooltipTimer = () => {
    if (sidebarChatTooltipTimerRef.current) {
      clearTimeout(sidebarChatTooltipTimerRef.current);
      sidebarChatTooltipTimerRef.current = null;
    }
  };

  const hideSidebarChatTooltip = (targetSessionId?: string | null) => {
    setSidebarChatTooltip((current: any) => {
      if (!current) {
        return null;
      }
      if (targetSessionId && current.sessionId !== targetSessionId) {
        return current;
      }
      return null;
    });
  };

  const clearToolPackInfoHideTimer = () => {
    if (toolPackInfoHideTimerRef.current) {
      clearTimeout(toolPackInfoHideTimerRef.current);
      toolPackInfoHideTimerRef.current = null;
    }
  };

  const hideToolPackInfoPopup = (targetPackId?: string | null) => {
    clearToolPackInfoHideTimer();
    setToolPackInfoPopup((current: any) => {
      if (!current) {
        return null;
      }
      if (targetPackId && current.packId !== targetPackId) {
        return current;
      }
      return null;
    });
    setHoveredToolPackInfoId((current: any) => (
      !targetPackId || current === targetPackId ? null : current
    ));
    setPinnedToolPackInfoId((current: any) => (
      !targetPackId || current === targetPackId ? null : current
    ));
  };

  const showToolPackInfoPopup = (packId: string, options?: { pinned?: boolean }) => {
    clearToolPackInfoHideTimer();
    if (options?.pinned) {
      setPinnedToolPackInfoId(packId);
    } else {
      setHoveredToolPackInfoId(packId);
    }
    if (Platform.OS !== 'web') {
      setToolPackInfoPopup({
        packId,
        top: 0,
        left: 0,
      });
      return;
    }
    const buttonNode = toolPackInfoButtonRefs.current[packId];
    const layerNode = floatingPanelRef.current;
    if (
      !buttonNode
      || !layerNode
      || typeof buttonNode.getBoundingClientRect !== 'function'
      || typeof layerNode.getBoundingClientRect !== 'function'
    ) {
      setToolPackInfoPopup({
        packId,
        top: 0,
        left: 0,
      });
      return;
    }
    const buttonRect = buttonNode.getBoundingClientRect();
    const layerRect = layerNode.getBoundingClientRect();
    const bubbleWidth = 292;
    const bubbleHeight = 136;
    const leftPreferred = buttonRect.left - layerRect.left - bubbleWidth - 12;
    const leftFallback = buttonRect.right - layerRect.left + 12;
    const nextLeft = leftPreferred >= 12
      ? leftPreferred
      : Math.max(12, Math.min(layerRect.width - bubbleWidth - 12, leftFallback));
    const unclampedTop = buttonRect.top - layerRect.top + buttonRect.height / 2 - bubbleHeight / 2;
    const nextTop = Math.max(12, Math.min(layerRect.height - bubbleHeight - 12, unclampedTop));
    setToolPackInfoPopup({
      packId,
      top: nextTop,
      left: nextLeft,
    });
  };

  const scheduleHideToolPackInfoPopup = (packId: string) => {
    clearToolPackInfoHideTimer();
    toolPackInfoHideTimerRef.current = setTimeout(() => {
      setHoveredToolPackInfoId((current: any) => (current === packId ? null : current));
      setToolPackInfoPopup((current: any) => {
        if (!current || current.packId !== packId || pinnedToolPackInfoId === packId) {
          return current;
        }
        return null;
      });
    }, 120);
  };

  const showSidebarChatTooltip = (targetSession: SessionSummary, projectPath: string) => {
    if (Platform.OS !== 'web') {
      return;
    }
    const rowNode = sessionRowRefs.current[targetSession.id];
    const shellNode = shellRef.current;
    if (
      !rowNode
      || !shellNode
      || typeof rowNode.getBoundingClientRect !== 'function'
      || typeof shellNode.getBoundingClientRect !== 'function'
    ) {
      return;
    }
    const rowRect = rowNode.getBoundingClientRect();
    const shellRect = shellNode.getBoundingClientRect();
    const tooltipWidth = 296;
    const tooltipHeight = 86;
    const nextLeft = Math.max(14, rowRect.left - shellRect.left - tooltipWidth - 16);
    const unclampedTop = rowRect.top - shellRect.top + rowRect.height / 2 - tooltipHeight / 2;
    const nextTop = Math.max(14, Math.min(shellRect.height - tooltipHeight - 14, unclampedTop));
    setSidebarChatTooltip({
      sessionId: targetSession.id,
      title: targetSession.name,
      projectPath,
      botLabel: telegramBotLabelForSession(targetSession),
      top: nextTop,
      left: nextLeft,
    });
  };

  const scheduleSidebarChatTooltip = (targetSession: SessionSummary, projectPath: string) => {
    if (Platform.OS !== 'web') {
      return;
    }
    clearSidebarChatTooltipTimer();
    sidebarChatTooltipTimerRef.current = setTimeout(() => {
      showSidebarChatTooltip(targetSession, projectPath);
    }, 2000);
  };

  const refreshFleetSnapshot = async (options?: { quiet?: boolean }) => {
    if (!options?.quiet) {
      setFleetLoading(true);
      setFleetStatus('Refreshing fleet');
    }
    try {
      const snapshot = normalizeFleetSnapshotManagers(await loadDesktopFleetSnapshot());
      if (!snapshot) {
        throw new Error('Desktop fleet bridge is not available.');
      }
      setFleetSnapshot(snapshot);
      setFleetError(null);
      setFleetStatus(snapshot.workers.length ? `${snapshot.workers.length} worker${snapshot.workers.length === 1 ? '' : 's'} linked` : 'No workers yet');
      return snapshot;
    } catch (error) {
      const detail = userFacingError(error, 'Fleet did not refresh.');
      setFleetError(detail);
      setFleetStatus(detail);
      return null;
    } finally {
      if (!options?.quiet) {
        setFleetLoading(false);
      }
    }
  };

  const createFleetLocalWorker = async () => {
    setFleetLoading(true);
    setFleetStatus('Creating local worker');
    try {
      const worker = await createDesktopFleetLocalWorker(fleetWorkerNameDraft.trim() || null);
      if (!worker) {
        throw new Error('Desktop fleet bridge is not available.');
      }
      setFleetWorkerNameDraft('');
      setFleetError(null);
      setFleetStatus(`${worker.display_name} created`);
      await refreshFleetSnapshot({ quiet: true });
    } catch (error) {
      const detail = describeError(error);
      setFleetError(detail);
      setFleetStatus(detail);
    } finally {
      setFleetLoading(false);
    }
  };

  const createFleetEnrollment = async () => {
    setFleetLoading(true);
    setFleetStatus('Creating enrollment code');
    try {
      const enrollment = await createDesktopFleetEnrollment(fleetWorkerNameDraft.trim() || null);
      if (!enrollment) {
        throw new Error('Desktop fleet bridge is not available.');
      }
      setFleetEnrollment(enrollment);
      setFleetError(null);
      setFleetStatus(`Enrollment ready for ${enrollment.display_name || 'remote worker'}`);
      await refreshFleetSnapshot({ quiet: true });
    } catch (error) {
      const detail = describeError(error);
      setFleetError(detail);
      setFleetStatus(detail);
    } finally {
      setFleetLoading(false);
    }
  };

  const assignFleetTask = async (worker: DesktopFleetWorker) => {
    const prompt = (fleetTaskDrafts[worker.worker_id] || '').trim();
    if (!prompt) {
      setFleetStatus(`Add a task for ${worker.display_name}`);
      return;
    }
    setFleetLoading(true);
    setFleetStatus(`Queueing task for ${worker.display_name}`);
    try {
      const targetSessionId = fleetSelectedChatIdForWorker(worker);
      const task = await assignDesktopFleetTask(
        worker.worker_id,
        prompt,
        {
          assigned_from: 'desktop_fleet_panel',
          ...(targetSessionId ? { target_session_id: targetSessionId } : {}),
        },
        { targetSessionId },
      );
      if (!task) {
        throw new Error('Desktop fleet bridge is not available.');
      }
      const nextStatus = fleetTaskStatusMessage(task, worker.display_name);
      setFleetTaskDrafts((previous: any) => ({ ...previous, [worker.worker_id]: '' }));
      setFleetError(isBlockedFleetTask(task) ? nextStatus : null);
      setFleetStatus(nextStatus);
      await refreshFleetSnapshot({ quiet: true });
    } catch (error) {
      const detail = describeError(error);
      setFleetError(detail);
      setFleetStatus(detail);
    } finally {
      setFleetLoading(false);
    }
  };

  const resetFleetWorker = async (worker: DesktopFleetWorker) => {
    const confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirmAction, {
      action_kind: 'fleet_worker_delete',
      title: `Delete ${worker.display_name}?`,
      message: 'This stops active work and removes the worker from the live fleet.',
      risk_tier: 'danger',
      origin_surface: 'desktop',
      payload: { worker_id: worker.worker_id, display_name: worker.display_name },
    }, {
      confirmLabel: 'Delete',
      tone: 'danger',
      details: ['Reports and task history should remain recoverable through the cloud archive where supported.', 'The live worker will no longer receive new work.'],
    });
    if (!confirmationId) {
      return;
    }
    setFleetLoading(true);
    setFleetStatus(`Deleting ${worker.display_name}`);
    try {
      await deleteDesktopFleetWorker(worker.worker_id, true, confirmationId);
      setFleetError(null);
      setFleetStatus(`${worker.display_name} deleted`);
      await refreshFleetSnapshot({ quiet: true });
    } catch (error) {
      const detail = describeError(error);
      setFleetError(detail);
      setFleetStatus(detail);
    } finally {
      setFleetLoading(false);
    }
  };

  const resetFleetWorkerIdentity = async (worker: DesktopFleetWorker) => {
    const confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirmAction, {
      action_kind: 'fleet_worker_reset',
      title: `Reset ${worker.display_name}?`,
      message: 'This stops active work, revokes live access, and resets the worker identity.',
      risk_tier: 'danger',
      origin_surface: 'desktop',
      payload: { worker_id: worker.worker_id, display_name: worker.display_name },
    }, {
      confirmLabel: 'Reset',
      tone: 'danger',
      details: ['Reports and task history should remain recoverable through the cloud archive where supported.'],
    });
    if (!confirmationId) {
      return;
    }
    setFleetLoading(true);
    setFleetStatus(`Resetting ${worker.display_name}`);
    try {
      await resetDesktopFleetWorker(worker.worker_id, 'Reset from desktop Fleet', { reset_from: 'desktop_fleet_panel' }, confirmationId);
      setFleetError(null);
      setFleetStatus(`${worker.display_name} reset`);
      await refreshFleetSnapshot({ quiet: true });
    } catch (error) {
      const detail = describeError(error);
      setFleetError(detail);
      setFleetStatus(detail);
    } finally {
      setFleetLoading(false);
    }
  };

  const renameFleetWorker = async (worker: DesktopFleetWorker) => {
    const nextName = (fleetRenameDrafts[worker.worker_id] || '').trim();
    if (!nextName) {
      setFleetStatus(`Add a new name for ${worker.display_name}`);
      return;
    }
    setFleetLoading(true);
    setFleetStatus(`Renaming ${worker.display_name}`);
    try {
      await renameDesktopFleetWorker(worker.worker_id, nextName, { renamed_from: 'desktop_fleet_panel' });
      setFleetRenameDrafts((previous: any) => ({ ...previous, [worker.worker_id]: '' }));
      setFleetError(null);
      setFleetStatus('Worker renamed');
      await refreshFleetSnapshot({ quiet: true });
    } catch (error) {
      const detail = describeError(error);
      setFleetError(detail);
      setFleetStatus(detail);
    } finally {
      setFleetLoading(false);
    }
  };

  const stopFleetWorker = async (worker: DesktopFleetWorker) => {
    setFleetLoading(true);
    setFleetStatus(`Stopping ${worker.display_name}`);
    try {
      await stopDesktopFleetWorker(worker.worker_id, 'Stopped from desktop Fleet', { stopped_from: 'desktop_fleet_panel' });
      setFleetError(null);
      setFleetStatus(`${worker.display_name} stopped`);
      await refreshFleetSnapshot({ quiet: true });
    } catch (error) {
      const detail = describeError(error);
      setFleetError(detail);
      setFleetStatus(detail);
    } finally {
      setFleetLoading(false);
    }
  };

  const stopAllFleetWorkers = async () => {
    const confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirmAction, {
      action_kind: 'fleet_stop_all',
      title: 'Stop all workers?',
      message: 'This stops every reachable active Fleet run. Use this only when the whole fleet should stop now.',
      risk_tier: 'danger',
      origin_surface: 'desktop',
      payload: { stopped_from: 'desktop_fleet_panel' },
    }, {
      confirmLabel: 'Stop All',
      tone: 'danger',
      details: ['The normal red Stop targets the visible identity and its delegation chain.', 'This action is broader than the visible task.'],
    });
    if (!confirmationId) {
      return;
    }
    setFleetLoading(true);
    setFleetStatus('Stopping all workers');
    try {
      await stopAllDesktopFleetWorkers('Stopped all from desktop Fleet', { stopped_from: 'desktop_fleet_panel' }, confirmationId);
      setFleetError(null);
      setFleetStatus('All active worker tasks stopped');
      await refreshFleetSnapshot({ quiet: true });
    } catch (error) {
      const detail = describeError(error);
      setFleetError(detail);
      setFleetStatus(detail);
    } finally {
      setFleetLoading(false);
    }
  };

  const requestFleetPreview = async (worker: DesktopFleetWorker) => {
    setFleetLoading(true);
    setFleetStatus(`Requesting preview for ${worker.display_name}`);
    try {
      const preview = await requestDesktopFleetWorkerPreview(worker.worker_id);
      if (!preview?.capture?.image_base64) {
        throw new Error(preview?.detail || 'The worker did not return a preview image.');
      }
      setFleetPreview?.(preview);
      setFleetError(null);
      setFleetStatus('Preview captured');
      await refreshFleetSnapshot({ quiet: true });
    } catch (error) {
      const detail = describeError(error);
      setFleetError(detail);
      setFleetStatus(detail);
    } finally {
      setFleetLoading(false);
    }
  };

  const continueFleetQueue = async (worker: DesktopFleetWorker) => {
    const latestReport = (fleetSnapshot?.reports || []).find((report: any) => report.worker_id === worker.worker_id);
    setFleetLoading(true);
    setFleetStatus(`Continuing ${worker.display_name}`);
    try {
      await continueDesktopFleetWorkerQueue(worker.worker_id, latestReport?.report_id || null, { continued_from: 'desktop_fleet_panel' });
      setFleetError(null);
      setFleetStatus('Next queued task started');
      await refreshFleetSnapshot({ quiet: true });
    } catch (error) {
      const detail = describeError(error);
      setFleetError(detail);
      setFleetStatus(detail);
    } finally {
      setFleetLoading(false);
    }
  };

  const updateFleetQueuePolicy = async (worker: DesktopFleetWorker, queuePolicy: 'review_required' | 'auto_continue_success') => {
    setFleetLoading(true);
    setFleetStatus(`Updating ${worker.display_name} queue policy`);
    try {
      await updateDesktopFleetWorkerQueuePolicy(worker.worker_id, queuePolicy);
      setFleetError(null);
      setFleetStatus(queuePolicy === 'auto_continue_success' ? 'Safe successful reports will continue automatically' : 'Report review required');
      await refreshFleetSnapshot({ quiet: true });
    } catch (error) {
      setFleetError(userFacingError(error, 'Queue policy was not updated.'));
    } finally {
      setFleetLoading(false);
    }
  };

  const createFleetGroupFromFirstWorker = async () => {
    const name = fleetGroupNameDraft.trim();
    const firstWorkerId = fleetSnapshot?.workers?.[0]?.worker_id || '';
    if (!name || !firstWorkerId) {
      setFleetStatus('Add a group name after creating at least one worker');
      return;
    }
    setFleetLoading(true);
    setFleetStatus('Creating group');
    try {
      await createDesktopFleetGroup(name, [firstWorkerId], null, { created_from: 'desktop_fleet_panel' });
      setFleetGroupNameDraft('');
      setFleetError(null);
      setFleetStatus('Group created');
      await refreshFleetSnapshot({ quiet: true });
    } catch (error) {
      const detail = describeError(error);
      setFleetError(detail);
      setFleetStatus(detail);
    } finally {
      setFleetLoading(false);
    }
  };

  const deleteFleetGroup = async (group: Record<string, any>) => {
    const groupId = String(group.group_id || '').trim();
    const label = String(group.display_name || groupId || 'group');
    if (!groupId) {
      return;
    }
    const confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirmAction, {
      action_kind: 'fleet_group_delete',
      title: `Delete ${label}?`,
      message: 'The workers remain in the fleet. Only this group is removed.',
      risk_tier: 'danger',
      origin_surface: 'desktop',
      payload: { group_id: groupId, display_name: label },
    }, {
      confirmLabel: 'Delete Group',
      tone: 'danger',
    });
    if (!confirmationId) {
      return;
    }
    setFleetLoading(true);
    setFleetStatus(`Deleting ${label}`);
    try {
      await deleteDesktopFleetGroup(groupId, confirmationId);
      setFleetError(null);
      setFleetStatus('Group deleted');
      await refreshFleetSnapshot({ quiet: true });
    } catch (error) {
      const detail = describeError(error);
      setFleetError(detail);
      setFleetStatus(detail);
    } finally {
      setFleetLoading(false);
    }
  };

  const assignFleetGroupTask = async (group: Record<string, any>) => {
    const groupId = String(group.group_id || '').trim();
    const prompt = (fleetGroupTaskDrafts[groupId] || '').trim();
    const label = String(group.display_name || groupId || 'group');
    if (!groupId || !prompt) {
      setFleetStatus(`Add a task for ${label}`);
      return;
    }
    const workerIds = Array.isArray(group.worker_ids) ? group.worker_ids : [];
    const targetWorkers = (scope.fleetWorkers || []).filter((worker: any) => workerIds.includes(worker.worker_id));
    const confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirmAction, {
      action_kind: 'fleet_group_dispatch',
      title: `Dispatch to ${label}?`,
      message: `${targetWorkers.length || workerIds.length || 0} workers will receive this task. Busy workers queue it by default.`,
      risk_tier: 'access',
      origin_surface: 'desktop',
      payload: { group_id: groupId, worker_count: targetWorkers.length || workerIds.length || 0, prompt_preview: prompt.slice(0, 240) },
    }, {
      confirmLabel: 'Dispatch',
      tone: 'access',
      details: targetWorkers.slice(0, 8).map((worker: any) => `${worker.display_name}: ${worker.status}`),
    });
    if (!confirmationId) {
      return;
    }
    setFleetLoading(true);
    setFleetStatus(`Dispatching ${label}`);
    try {
      const tasks = await assignDesktopFleetGroupTask(groupId, prompt, { assigned_from: 'desktop_fleet_panel', bulk_dispatch_confirmed: true }, undefined, confirmationId);
      if (!tasks) {
        throw new Error('Desktop fleet bridge is not available.');
      }
      const nextStatus = fleetTaskBatchStatusMessage(tasks, label);
      setFleetGroupTaskDrafts((previous: any) => ({ ...previous, [groupId]: '' }));
      setFleetError(tasks.some((task: DesktopFleetTask) => isBlockedFleetTask(task)) ? nextStatus : null);
      setFleetStatus(nextStatus);
      await refreshFleetSnapshot({ quiet: true });
    } catch (error) {
      const detail = describeError(error);
      setFleetError(detail);
      setFleetStatus(detail);
    } finally {
      setFleetLoading(false);
    }
  };

  const selectFleetIdentity = async (identity: DesktopFleetIdentity) => {
    if (!identity.identity_id) {
      return;
    }
    setFleetLoading(true);
    setFleetStatus(`Switching to ${identity.display_name}`);
    try {
      const selectedChatId = fleetSnapshot?.selected_chat_by_identity?.[identity.identity_id] || null;
      const result = await setDesktopFleetActiveIdentity(identity.identity_id, selectedChatId, 'desktop');
      const nextSnapshot = await refreshFleetSnapshot({ quiet: true });
      const nextSelectedChatId = String(
        selectedChatId
        || (result as Record<string, any> | null | undefined)?.selected_chat_id
        || nextSnapshot?.selected_chat_by_identity?.[identity.identity_id]
        || '',
      ).trim();
      setFleetError(null);
      setFleetStatus(`Active identity: ${identity.display_name}`);
      const fallbackIdentitySessionId = sessions.find((item: any) => sessionBelongsToFleetIdentity(item, identity))?.id || '';
      const nextTargetChatId = nextSelectedChatId || fallbackIdentitySessionId;
      if (nextTargetChatId) {
        void openSession(nextTargetChatId);
      } else {
        clearConversationSelection(null, { clearSidebarProject: true });
      }
    } catch (error) {
      const detail = describeError(error);
      setFleetError(detail);
      setFleetStatus(detail);
    } finally {
      setFleetLoading(false);
    }
  };

  const copyFleetEnrollmentToken = async () => {
    if (!fleetEnrollment?.enrollment_token) {
      return;
    }
    try {
      await copyDesktopText(fleetEnrollment.enrollment_token);
      setFleetStatus('Enrollment token copied');
    } catch (error) {
      setFleetStatus(userFacingError(error, 'Enrollment token was not copied.'));
    }
  };
  return { setProjectMenuRef, setProjectMenuTriggerRef, setSessionRowRef, setSessionMenuRef, setSessionMenuTriggerRef, setToolPackInfoButtonRef, activeVoiceGatePrerollMs, activeVoiceGateMaxMs, clearSidebarChatTooltipTimer, hideSidebarChatTooltip, clearToolPackInfoHideTimer, hideToolPackInfoPopup, showToolPackInfoPopup, scheduleHideToolPackInfoPopup, showSidebarChatTooltip, scheduleSidebarChatTooltip, refreshFleetSnapshot, createFleetLocalWorker, createFleetEnrollment, assignFleetTask, resetFleetWorker, resetFleetWorkerIdentity, renameFleetWorker, updateFleetQueuePolicy, stopFleetWorker, stopAllFleetWorkers, requestFleetPreview, continueFleetQueue, createFleetGroupFromFirstWorker, deleteFleetGroup, assignFleetGroupTask, selectFleetIdentity, copyFleetEnrollmentToken };
}
