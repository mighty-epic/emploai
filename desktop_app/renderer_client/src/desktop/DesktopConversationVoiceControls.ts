import type { DesktopConversationScope } from './DesktopConversationScope';
import { JARVIS_WAKE_PHRASE } from './desktopVoicePolicy';
import {
  JARVIS_WAKE_MATCH_MAX_MS,
  JARVIS_WAKE_MATCH_MIN_MS,
  JARVIS_WAKE_MATCH_RELEASE_MS,
  JARVIS_WAKE_MATCH_SCORE_EVERY_MS,
  createJarvisWakeMatchState,
  scoreJarvisWakeCandidate,
} from './desktopJarvisWakeProfile';
import { updateSessionModeState } from '@/lib/appApi';
import { modelVariantDisplayLabel } from './modelProviders';
import {
  chatReconnectDelayMs,
  createClientMessageId,
  parseDesktopRealtimeEvent,
  realtimeEventMatchesSession,
  shouldReconnectChatSocket,
} from './desktopRealtimeProtocol';
import type { DesktopRealtimeEvent, PendingChatMessage } from './desktopRealtimeProtocol';
import { createDesktopAudioCapture } from './desktopAudioCapture';
import { playJarvisWakeTone } from './desktopJarvisTone';
import { useEffect, useRef } from 'react'; type NativeSyntheticEvent<T = any> = any; type ActiveCommandPanel = any; type ActivityItem = any; type AgentOverview = any; type ArtifactDetail = any; type ArtifactSummary = any; type ComposerInputOrigin = any; type ComposerModeOptions = any; type ConversationSurfaceMode = any; type DesktopFleetEnrollment = any; type DesktopFleetIdentity = any; type DesktopFleetSnapshot = any; type DesktopFleetTask = any; type DesktopFleetWorker = any; type DesktopGitRepoState = any; type DesktopMessage = any; type DesktopPathStatus = any; type DesktopRuntimeStatus = any; type DesktopSidebarProjectActivity = any; type DesktopSidebarState = any; type DesktopVoicePackState = any; type DesktopVoiceRuntimeStatus = any; type InterruptPolicy = any; type JarvisSttBackend = any; type JarvisTtsBackend = any; type LayoutChangeEvent = any; type MessageSourceFormat = any; type ModelProviderGroup = any; type NativeScrollEvent = any; type PendingSearchJump = any; type QueuedComposerMessage = any; type ReferenceEntry = any; type RuntimeOrchestratorStatus = any; type ScheduledJob = any; type SearchResultTarget = any; type SecurityPermissionMode = any; type SessionDetail = any; type SessionMessage = any; type SessionSearchResult = any; type SessionSummary = any; type SessionTimelineEvent = any; type SidebarChatTooltipState = any; type SidebarDragState = any; type SidebarDraftChat = any; type SidebarProjectGroup = any; type StartupReadinessState = any; type TaskBoard = any; type TelegramBotConfig = any; type TextInputContentSizeChangeEventData = any; type ToolPackInfoPopupState = any; type VoiceCaptureMode = any; type VoiceGateState = any;

const desktopSecurityPermissionMutationsInFlight = new Set<string>();

export function useDesktopConversationVoiceControls(scope: DesktopConversationScope) {
  const { ALWAYS_ON_VOICE_AUTO_SEND, COMPOSER_MAX_HEIGHT, COMPOSER_MIN_HEIGHT, DESKTOP_COMMAND_SUGGESTIONS, DESKTOP_NO_ACTIVE_SESSION_STATUS, JARVIS_BARGE_IN_MIN_VOICED_MS, Platform, SOCKET_RECONNECT_MS, VOICE_DEFERRED_FRAME_MAX_MS, VOICE_ENGINE_NONE, VOICE_GATE_ATTACK_MS, VOICE_GATE_FRAME_MS, VOICE_GATE_MIN_MS, activeCommandPanel, activeJarvisBargeInGateDbfs, activePermissionInfoId, activeVoiceBargeInCandidateRef, activeVoiceBargeInReferenceTextRef, activeVoiceGateDbfs, activeVoiceGateMaxMs, activeVoiceGatePrerollMs, activeVoiceGateReleaseMs, activeVoiceSegmentMs, activeVoiceUtteranceIdRef, activity, agentRunActive, allowedWorkspaceRoot, alwaysOnEnabled, alwaysOnEnabledRef, apiBaseUrl, apiVoiceInputActive, appClientIdRef, appendSessionTimelineEvent, appendTimelineEvent, appendVoiceTranscriptSegment, applySessionDetail, applySessionSync, artifactDetailLoading, artifactError, artifacts, artifactsLoading, assignFleetGroupTask, assignFleetTask, assistantAudioRef, assistantAudioTextRef, assistantDeltaBufferRef, assistantDeltaFlushTimerRef, assistantDraft, attachmentUploadInFlight, buildWsBaseUrl, bytesToBase64, chatRunActive, chatRunActiveRef, chatWsRef, clearAssistantDeltaFlushTimer, clearSidebarChatTooltipTimer, clearSidebarSearch, clearToolPackInfoHideTimer, clearTranscriptAutoScrollResumeTimer, closeSidebarSearchModal, commandSuggestionMenuRef, completedTaskBoards, composerInputHeight, composerTextRegionRef, concatFloat32, configureAgent, configureHeadlessRuntime, configuredHebrewVoiceGateDbfs, configuredJarvisBargeInGateDbfs, configuredModelGroups, configuredVoiceGateDbfs, confirmAction, confirmationDialog, contextUsageHovered, continueFleetQueue, conversationMode, conversationModeRef, copyFleetEnrollmentToken, createApprovedConfirmation, createAudioContext, createClientId, createFleetEnrollment, createFleetGroupFromFirstWorker, createFleetLocalWorker, createLocalToolTimelineEvent, createVoiceGateState, currentAvailableToolPacks, currentDisabledPackReasons, currentEnabledToolPacks, currentJarvisSttBackend, currentJarvisSttLabel, currentJarvisTtsBackend, currentJarvisTtsLabel, currentWorkspaceBySessionRef, defaultTelegramBotConfigId, deferredAlwaysOnFramesRef, deferredAlwaysOnSampleCountRef, deleteFleetGroup, describeError, discardDraftChat, dismissedCommandSuggestionInput, draftBranchSearch, draftBranchTriggerRef, draftChat, draftChatRef, draftGitRepoLoading, draftGitRepoState, draftProjectSearch, draftProjectTriggerRef, draftTelegramTriggerRef, dragState, drainingDeferredAlwaysOnFramesRef, emitStartupState, encodePcm16Wav, ensureSessionForOutgoingMessage, envFilePath, expandedCompletedTaskIds, expandedModelProviders, expandedPlannerProviders, externalSidebarToggleSignalRef, fleetChatPanelCollapsed, fleetChatPanelWidth, fleetDashboardCollapsed, fleetEnrollment, fleetError, fleetGroupNameDraft, fleetGroupTaskDrafts, fleetLoading, fleetPanelOpen, fleetRenameDrafts, fleetSnapshot, fleetStatus, fleetTaskBatchStatusMessage, fleetTaskDrafts, fleetTaskStatusMessage, fleetWorkerNameDraft, floatingPanelRef, flushAssistantDeltaBuffer, folderChoiceBusy, folderChoiceOpen, folderChoiceResolveRef, formatToolPackLockReason, handleDesktopConversationRealtimeEvent, handleJarvisSttBackendSelection, handleJarvisTtsBackendSelection, handleTranscriptScroll, hideSidebarChatTooltip, hideToolPackInfoPopup, hideVoicePanel, highlightedMessageIndex, historyMessageLayoutRef, historyScrollRef, hoveredProjectPath, hoveredSessionId, hoveredToolPackInfoId, input, interruptPolicy, isBlockedFleetTask, isDesktopSlashCommand, isJarvisMode, isMeaningfulJarvisBargeInText, jarvisBargeInCandidateUtteranceIdsRef, jarvisHoldToTalkMode, jarvisLatestSpokenText, jarvisLatestTranscript, jarvisMuted, jarvisPulseProgress, jarvisPushToTalkActiveRef, jarvisSpaceHotkeyActiveRef, jarvisStatusDrawerOpen, jarvisVoiceSettingsOpen, jarvisWarmRequestedRef, jobs, keepRuntimeOnAppClose, lastAssistantOutputAt, lastComposerInputOriginRef, lastMessage, lastMessageSignature, lastVoiceWarmRequestEngineRef, liveVoiceStatus, logDiagnostic, maybeResolveStartupReady, mergeLocalMessages, mergeTimelineEventState, messages, modelTriggerRef, normalizeCompletedTaskBoards, openFleetWorkerMenuId, openProjectMenuPath, openSessionMenuId, openSidebarSearchModal, openVoicePanel, orchestratorStatus, overview, overviewRefreshInFlightRef, parseComposerSlashCommand, pendingDraftSecurityPermissionMode, pendingMessagesRef, pendingSearchJump, pendingSessionSwitch, permissionsTriggerRef, pinnedToolPackInfoId, projectMenuRefs, projectMenuTriggerRefs, projectPathStatuses, pushActivity, pushProjectActivity, queuedComposerMessages, reconcileSidebarProjects, reconnectRef, referenceAutoOpenKeyRef, referenceDismissedKeyRef, refreshFleetSnapshot, refreshOverviewState, refreshSidebarCollections, refreshSidebarState, refreshVoiceRuntimeState, renameFleetWorker, requestFleetPreview, resetFleetWorker, resetFleetWorkerIdentity, resetTranscriptAutoScrollState, resolveTaskBoardState, revealProjectInSidebar, rightSidebarWidth, router, runDesktopSlashCommand, runtimeRunState, samplesDbfs, savingCloseBehavior, scheduleHideToolPackInfoPopup, scheduleSidebarChatTooltip, scheduleTranscriptAutoScrollResume, scrollRef, scrollTranscriptToEnd, searchHighlightTimerRef, searchJumpTimerRef, selectFleetIdentity, selectProjectPath, selectedArtifactDetail, selectedArtifactId, selectedVoiceEngine, selectedVoiceEngineState, sessionId, sessionIdRef, sessionMenuRefs, sessionMenuTriggerRefs, sessionName, sessionRowRefs, sessionSettingsMutationInFlight, sessions, setActiveCommandPanel, setActivePermissionInfoId, setActivity, setAlwaysOnEnabled, setArtifactDetailLoading, setArtifactError, setArtifacts, setArtifactsLoading, setAssistantDraft, setAttachmentUploadInFlight, setCachedModelGroups, setCachedPlannerModels, setChatRunActive, setCompletedTaskBoards, setComposerInputHeight, setContextUsageHovered, setConversationMode, setDismissedCommandSuggestionInput, setDraftBranchSearch, setDraftChat, setDraftGitRepoLoading, setDraftGitRepoState, setDraftProjectSearch, setDragState, setExpandedCompletedTaskIds, setExpandedModelProviders, setExpandedPlannerProviders, setFleetChatPanelCollapsed, setFleetChatPanelWidth, setFleetDashboardCollapsed, setFleetEnrollment, setFleetError, setFleetGroupNameDraft, setFleetGroupTaskDrafts, setFleetLoading, setFleetPanelOpen, setFleetRenameDrafts, setFleetSnapshot, setFleetStatus, setFleetTaskDrafts, setFleetWorkerNameDraft, setFolderChoiceBusy, setFolderChoiceOpen, setHighlightedMessageIndex, setHoveredProjectPath, setHoveredSessionId, setHoveredToolPackInfoId, setInput, setInterruptPolicy, setJarvisHoldToTalkMode, setJarvisLatestSpokenText, setJarvisLatestTranscript, setJarvisMuted, setJarvisStatusDrawerOpen, setJarvisVoiceSettingsOpen, setJobs, setKeepRuntimeOnAppClose, setLastAssistantOutputAt, setLiveVoiceStatus, setMessages, setOpenFleetWorkerMenuId, setOpenProjectMenuPath, setOpenSessionMenuId, setOrchestratorStatus, setOverview, setPendingDraftSecurityPermissionMode, setPendingSearchJump, setPendingSessionSwitch, setPinnedToolPackInfoId, setProjectMenuRef, setProjectMenuTriggerRef, setProjectPathStatuses, setQueuedComposerMessages, setRightSidebarWidth, setRuntimeRunState, setSavingCloseBehavior, setSelectedArtifactDetail, setSelectedArtifactId, setSessionId, setSessionMenuRef, setSessionMenuTriggerRef, setSessionName, setSessionRowRef, setSessionSettingsMutationInFlight, setSessions, setShowArtifactRail, setShowReferenceRail, setShowVoicePanel, setSidebarChatTooltip, setSidebarExpanded, setSidebarSearch, setSidebarSearchError, setSidebarSearchLoading, setSidebarSearchModalOpen, setSidebarSearchResults, setSidebarState, setSidebarStateReady, setSocketState, setStatus, setSttBackendChanging, setTaskBoard, setTaskBoardArmedNextTurnState, setTaskBoardCollapsed, setTelegramBotConfigs, setThinking, setTimelineEvents, setToolPackInfoButtonRef, setToolPackInfoPopup, setToolPackMutationInFlight, setTtsBackendChanging, setVoiceDraft, setVoiceEngineChanging, setVoiceError, setVoiceMode, setVoicePanelHidden, setVoiceRecording, setVoiceRunning, setVoiceState, shellRef, shortStatusText, showArtifactRail, showReferenceRail, showSidebarChatTooltip, showToolPackInfoPopup, showVoicePanel, sidebarChatTooltip, sidebarChatTooltipTimerRef, sidebarCollectionsRefreshInFlightRef, sidebarExpanded, sidebarSearch, sidebarSearchError, sidebarSearchInputRef, sidebarSearchLauncherRef, sidebarSearchLoading, sidebarSearchModalOpen, sidebarSearchModalRef, sidebarSearchRequestIdRef, sidebarSearchResults, sidebarState, sidebarStateReady, socketState, startupChatSocketReadyRef, startupSessionStateReadyRef, startupSidebarReadyRef, startupTerminalStateRef, status, stopAllFleetWorkers, stopFleetWorker, sttBackendChanging, summarizeToolPayload, takeGateFrame, taskBoard, taskBoardArmedNextTurn, taskBoardCollapsed, taskBoardStateRef, telegramBotConfigs, thinking, thinkingShineProgress, timelineEvents, toLiveDesktopMessage, toggleToolPackId, token, toolPackInfoButtonRefs, toolPackInfoHideTimerRef, toolPackInfoPopup, toolPackLabel, toolPackMutationInFlight, toolsTriggerRef, transcriptAutoScrollResumeTimerRef, transcriptAutoScrollSuspendedRef, transcriptContentHeightRef, transcriptLastScrollOffsetYRef, transcriptLastSignatureRef, transcriptMessageLayoutRef, transcriptPendingAutoScrollRef, transcriptProgrammaticScrollUntilRef, transcriptSignature, transcriptViewportHeightRef, ttsBackendChanging, unavailableEnabledToolPackReason, updateSessionHeadlessEligibility, updateSessionSecurityPermissionMode, updateSessionTelegramBotAssignment, updateSessionToolPacks, updateSidebarState, uploadAppAttachment, useEffect, userFacingError, usingHebrewVoiceEngine, voiceAudioContextRef, voiceAudioSourceRef, voiceCaptureModeRef, voiceChunkChainRef, voiceChunkSampleCountRef, voiceChunkSamplesRef, voiceChunkSequenceRef, voiceComposerBaseInputRef, voiceComposerDraftRef, voiceDraft, voiceEngineChanging, voiceError, voiceGateStateRef, voiceMode, voicePanelHidden, voicePressActiveRef, voiceCaptureNodeRef, voiceReconnectRef, voiceRecording, voiceRecordingRef, voiceRunning, voiceRunningRef, voiceSampleRateRef, voiceStartInFlightRef, voiceState, voiceStreamRef, voiceWsRef, warmSelectedVoicePath } = scope;
  const jarvisWakeMatchStateRef = scope.jarvisWakeMatchStateRef;
  const jarvisWakeProfileRef = scope.jarvisWakeProfileRef;
  const pendingRunMode = scope.pendingRunMode as 'normal' | 'plan' | 'goal' | null | undefined;
  const setPendingRunMode = scope.setPendingRunMode as ((mode: 'normal' | 'plan' | 'goal' | null) => void) | undefined;
  const currentJarvisWakePhrase = String(scope.currentJarvisWakePhrase || JARVIS_WAKE_PHRASE).trim() || JARVIS_WAKE_PHRASE;
  const jarvisWakeProfileReady = Boolean(scope.jarvisWakeProfileReady);
  const setJarvisWakeEnrollmentOpen = scope.setJarvisWakeEnrollmentOpen as ((value: boolean) => void) | undefined;
  const refreshArtifacts = (...args: any[]) => scope.refreshArtifacts?.(...args);
  const chatSocketsBySessionRef = useRef<Record<string, WebSocket>>({});
  const chatSocketReconnectTimersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const chatSocketReconnectAttemptsRef = useRef<Record<string, number>>({});
  const chatSocketRunActiveBySessionRef = useRef<Record<string, boolean>>({});
  const missingProviderApiKeyMessage = 'You have not set an API key yet. Add an API key in Setup before sending a message.';
  const hasConfiguredModelProvider = () => {
    const groups = Array.isArray(configuredModelGroups) ? configuredModelGroups : [];
    return Array.isArray(groups) && groups.some((group: any) => Array.isArray(group?.models) && group.models.length > 0);
  };
  const blockMissingProviderApiKey = () => {
    if (hasConfiguredModelProvider()) {
      return false;
    }
    setStatus(missingProviderApiKeyMessage);
    setAssistantDraft('');
    setThinking('');
    setVoiceDraft('');
    setChatRunActive(false);
    setRuntimeRunState('idle');
    setLastAssistantOutputAt(null);
    pushActivity(missingProviderApiKeyMessage, 'warn');
    return true;
  };
  const voiceInputIssueForStatus = (status: any) => {
    const issues = Array.isArray(status?.issues) ? status.issues.map((item: any) => String(item || '').trim()).filter(Boolean) : [];
    if (status?.input_ok === false) {
      return issues[0] || `${currentJarvisSttLabel} voice input is not ready.`;
    }
    if (!apiVoiceInputActive && selectedVoiceEngine === VOICE_ENGINE_NONE) {
      return issues[0] || 'Select an English or Hebrew voice path first.';
    }
    return null;
  };
  const ensureJarvisVoiceInputReady = async () => {
    let status: any = liveVoiceStatus || null;
    let issue = voiceInputIssueForStatus(status);
    if (!issue && apiVoiceInputActive && !status) {
      try {
        status = await refreshVoiceRuntimeState();
        issue = voiceInputIssueForStatus(status);
      } catch (error) {
        issue = userFacingError(error, `${currentJarvisSttLabel} voice input is not ready.`);
      }
    }
    if (!issue) {
      return true;
    }
    voicePressActiveRef.current = false;
    setVoiceState('error');
    setVoiceError(issue);
    setStatus(issue);
    pushActivity(issue, 'warn');
    return false;
  };
  const normalizeChatSessionId = (value: unknown) => String(value || '').trim();

  const hasPendingMessagesForSession = (targetSessionId: string) => {
    const normalizedTargetSessionId = normalizeChatSessionId(targetSessionId);
    return Boolean(normalizedTargetSessionId)
      && pendingMessagesRef.current.some((item: PendingChatMessage) => normalizeChatSessionId(item?.sessionId) === normalizedTargetSessionId);
  };

  const clearChatSocketReconnectTimer = (targetSessionId: string) => {
    const timer = chatSocketReconnectTimersRef.current[targetSessionId];
    if (timer) {
      clearTimeout(timer);
      delete chatSocketReconnectTimersRef.current[targetSessionId];
    }
  };

  const closeSessionChatSocket = (targetSessionId: string) => {
    const normalizedTargetSessionId = normalizeChatSessionId(targetSessionId);
    if (!normalizedTargetSessionId) {
      return;
    }
    clearChatSocketReconnectTimer(normalizedTargetSessionId);
    const socket = chatSocketsBySessionRef.current[normalizedTargetSessionId];
    delete chatSocketsBySessionRef.current[normalizedTargetSessionId];
    delete chatSocketRunActiveBySessionRef.current[normalizedTargetSessionId];
    delete chatSocketReconnectAttemptsRef.current[normalizedTargetSessionId];
    if (socket && socket.readyState !== WebSocket.CLOSED && socket.readyState !== WebSocket.CLOSING) {
      socket.close();
    }
    if (chatWsRef.current === socket) {
      chatWsRef.current = null;
    }
  };

  const closeIdleBackgroundChatSocket = (targetSessionId: string, delayMs = 1500) => {
    const normalizedTargetSessionId = normalizeChatSessionId(targetSessionId);
    if (!normalizedTargetSessionId || normalizedTargetSessionId === normalizeChatSessionId(sessionIdRef.current)) {
      return;
    }
    clearChatSocketReconnectTimer(normalizedTargetSessionId);
    chatSocketReconnectTimersRef.current[normalizedTargetSessionId] = setTimeout(() => {
      if (
        normalizedTargetSessionId !== normalizeChatSessionId(sessionIdRef.current)
        && !hasPendingMessagesForSession(normalizedTargetSessionId)
        && !chatSocketRunActiveBySessionRef.current[normalizedTargetSessionId]
      ) {
        closeSessionChatSocket(normalizedTargetSessionId);
      }
    }, delayMs);
  };

  const sendPendingMessagesForSession = (targetSessionId: string, ws?: WebSocket | null) => {
    const normalizedTargetSessionId = normalizeChatSessionId(targetSessionId);
    const socket = ws || chatSocketsBySessionRef.current[normalizedTargetSessionId] || null;
    if (!normalizedTargetSessionId || !socket || socket.readyState !== WebSocket.OPEN) {
      return false;
    }

    let sentAny = false;
    const remainingMessages: PendingChatMessage[] = [];
    for (const next of pendingMessagesRef.current as PendingChatMessage[]) {
      if (normalizeChatSessionId(next?.sessionId) !== normalizedTargetSessionId) {
        remainingMessages.push(next);
        continue;
      }
      if (next.deliveryState === 'sent') {
        remainingMessages.push(next);
        continue;
      }
      if (socket.readyState !== WebSocket.OPEN) {
        remainingMessages.push(next);
        continue;
      }
      try {
        socket.send(JSON.stringify({
          text: next.text,
          session_id: normalizedTargetSessionId,
          interrupt_policy: next.interruptPolicy,
          source_format: next.sourceFormat,
          source_client_id: appClientIdRef.current,
          client_message_id: next.clientMessageId,
          run_mode: next.modeOptions?.runMode || undefined,
          plan_action: next.modeOptions?.planAction || undefined,
          plan_answer: next.modeOptions?.planAnswer || undefined,
        }));
        next.deliveryState = 'sent';
        chatSocketRunActiveBySessionRef.current[normalizedTargetSessionId] = true;
        sentAny = true;
      } catch (error) {
        next.deliveryState = 'queued';
        pushActivity('Message delivery paused while chat reconnects.', 'warn');
        try {
          socket.close();
        } catch (_closeError) {
          // The close handler will reconnect when the platform exposes it.
        }
      }
      remainingMessages.push(next);
    }
    pendingMessagesRef.current = remainingMessages;
    return sentAny;
  };

  const flushPendingMessages = (targetSessionId?: string, ws?: WebSocket | null) => {
    const normalizedTargetSessionId = normalizeChatSessionId(targetSessionId);
    if (normalizedTargetSessionId) {
      return sendPendingMessagesForSession(normalizedTargetSessionId, ws);
    }

    let sentAny = false;
    const pendingSessionIds = Array.from(new Set(
      (pendingMessagesRef.current as PendingChatMessage[])
        .map((item: PendingChatMessage) => normalizeChatSessionId(item?.sessionId))
        .filter(Boolean),
    ));
    for (const pendingSessionId of pendingSessionIds) {
      const socket = chatSocketsBySessionRef.current[pendingSessionId]
        || (pendingSessionId === normalizeChatSessionId(sessionIdRef.current) ? chatWsRef.current : null);
      if (sendPendingMessagesForSession(pendingSessionId, socket)) {
        sentAny = true;
      }
    }
    return sentAny;
  };

  const markChatSocketRunStateFromEvent = (targetSessionId: string, event: DesktopRealtimeEvent) => {
    const normalizedTargetSessionId = normalizeChatSessionId(targetSessionId);
    if (!normalizedTargetSessionId) {
      return;
    }
    const eventType = String(event?.type || '');
    const payload = (event?.payload || {}) as Record<string, any>;
    const statusMessage = String(payload.message || event?.message || '').toLowerCase();
    const payloadRunState = String(payload.run_state || '').toLowerCase();
    const startsRun = (
      eventType === 'assistant_delta'
      || eventType === 'thinking'
      || eventType === 'tool_event'
      || (eventType === 'status' && (payloadRunState === 'running' || statusMessage === 'running'))
    );
    const endsRun = (
      eventType === 'assistant_final'
      || eventType === 'run_failed'
      || eventType === 'error'
      || eventType === 'warning'
      || (eventType === 'status' && (
        payloadRunState === 'idle'
        || statusMessage === 'ready'
        || statusMessage === 'idle'
      ))
    );
    if (startsRun) {
      chatSocketRunActiveBySessionRef.current[normalizedTargetSessionId] = true;
    }
    if (endsRun) {
      chatSocketRunActiveBySessionRef.current[normalizedTargetSessionId] = false;
      closeIdleBackgroundChatSocket(normalizedTargetSessionId);
    }
  };

  const ensureChatSocketForSession = (targetSessionId: string, options?: { selected?: boolean }) => {
    const normalizedTargetSessionId = normalizeChatSessionId(targetSessionId);
    if (!apiBaseUrl || !token || !normalizedTargetSessionId) {
      return null;
    }

    const existing = chatSocketsBySessionRef.current[normalizedTargetSessionId];
    if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
      if (options?.selected) {
        chatWsRef.current = existing;
        if (existing.readyState === WebSocket.OPEN) {
          setSocketState('connected');
          startupChatSocketReadyRef.current = true;
          maybeResolveStartupReady();
        } else {
          setSocketState('connecting');
        }
      }
      return existing;
    }

    const wsBase = buildWsBaseUrl(apiBaseUrl);
    if (!wsBase) {
      if (options?.selected) {
        setSocketState('Connect backend first.');
      }
      return null;
    }

    clearChatSocketReconnectTimer(normalizedTargetSessionId);
    const params = new URLSearchParams({
      token,
      client_id: appClientIdRef.current,
      session_id: normalizedTargetSessionId,
    });
    if (options?.selected) {
      setSocketState('connecting');
      emitStartupState('warming', 'Connecting chat');
    }

    const ws = new WebSocket(`${wsBase}/ws/app/chat?${params.toString()}`);
    chatSocketsBySessionRef.current[normalizedTargetSessionId] = ws;
    if (options?.selected) {
      chatWsRef.current = ws;
    }

    const isCurrentSocket = () => chatSocketsBySessionRef.current[normalizedTargetSessionId] === ws;
    const isSelectedSession = () => normalizeChatSessionId(sessionIdRef.current) === normalizedTargetSessionId;

    ws.onopen = () => {
      if (!isCurrentSocket()) {
        return;
      }
      if (isSelectedSession()) {
        chatWsRef.current = ws;
        setSocketState('connected');
        startupChatSocketReadyRef.current = true;
        maybeResolveStartupReady();
      }
      chatSocketReconnectAttemptsRef.current[normalizedTargetSessionId] = 0;
      flushPendingMessages(normalizedTargetSessionId, ws);
    };

    ws.onmessage = (messageEvent: any) => {
      if (!isCurrentSocket()) {
        return;
      }
      try {
        const event = parseDesktopRealtimeEvent(String(messageEvent.data || '{}'));
        if (!realtimeEventMatchesSession(event, normalizedTargetSessionId)) {
          pushActivity('A realtime event for another chat was ignored.', 'warn');
          return;
        }
        if (event.type === 'message_ack') {
          const clientMessageId = String(event.payload.client_message_id || '').trim();
          const status = String(event.payload.status || '').trim();
          const retryable = event.payload.retryable === true;
          if (clientMessageId && ['accepted', 'duplicate', 'steering'].includes(status)) {
            pendingMessagesRef.current = (pendingMessagesRef.current as PendingChatMessage[])
              .filter((item) => item.clientMessageId !== clientMessageId);
            setMessages((previous: any) => previous.map((item: any) => (
              item.messageKey === `pending:${clientMessageId}`
                ? { ...item, pending: false }
                : item
            )));
          } else if (clientMessageId && status === 'rejected') {
            if (retryable) {
              for (const item of pendingMessagesRef.current as PendingChatMessage[]) {
                if (item.clientMessageId === clientMessageId) {
                  item.deliveryState = 'queued';
                }
              }
              setTimeout(() => flushPendingMessages(normalizedTargetSessionId, ws), 250);
            } else {
              pendingMessagesRef.current = (pendingMessagesRef.current as PendingChatMessage[])
                .filter((item) => item.clientMessageId !== clientMessageId);
              const deliveryError = String(event.payload.message || 'Message was not accepted.');
              setMessages((previous: any) => previous.map((item: any) => (
                item.messageKey === `pending:${clientMessageId}`
                  ? { ...item, pending: false, raw: { ...(item.raw || {}), delivery_error: deliveryError } }
                  : item
              )));
            }
          }
        }
        markChatSocketRunStateFromEvent(normalizedTargetSessionId, event);
        handleRealtimeEvent(event, 'chat');
      } catch (error) {
        pushActivity('Realtime event was skipped.', 'warn');
      }
    };

    ws.onclose = (closeEvent) => {
      if (chatSocketsBySessionRef.current[normalizedTargetSessionId] === ws) {
        delete chatSocketsBySessionRef.current[normalizedTargetSessionId];
      }
      if (chatWsRef.current === ws) {
        chatWsRef.current = null;
      }
      for (const item of pendingMessagesRef.current as PendingChatMessage[]) {
        if (normalizeChatSessionId(item.sessionId) === normalizedTargetSessionId && item.deliveryState === 'sent') {
          item.deliveryState = 'queued';
        }
      }

      if (!shouldReconnectChatSocket(closeEvent.code)) {
        clearChatSocketReconnectTimer(normalizedTargetSessionId);
        delete chatSocketReconnectAttemptsRef.current[normalizedTargetSessionId];
        if (isSelectedSession()) {
          startupChatSocketReadyRef.current = false;
          setSocketState('authentication required');
          setStatus('Chat connection authorization expired. Reopen or sign in again.');
        }
        return;
      }

      const shouldReconnect = (
        hasPendingMessagesForSession(normalizedTargetSessionId)
        || Boolean(chatSocketRunActiveBySessionRef.current[normalizedTargetSessionId])
      );
      if (!shouldReconnect) {
        delete chatSocketRunActiveBySessionRef.current[normalizedTargetSessionId];
        if (isSelectedSession()) {
          startupChatSocketReadyRef.current = false;
          setSocketState('reconnecting');
          const reconnectAttempt = chatSocketReconnectAttemptsRef.current[normalizedTargetSessionId] || 0;
          chatSocketReconnectAttemptsRef.current[normalizedTargetSessionId] = reconnectAttempt + 1;
          chatSocketReconnectTimersRef.current[normalizedTargetSessionId] = setTimeout(() => {
            ensureChatSocketForSession(normalizedTargetSessionId, { selected: true });
          }, chatReconnectDelayMs(reconnectAttempt, SOCKET_RECONNECT_MS));
        }
        return;
      }

      const reconnectAttempt = chatSocketReconnectAttemptsRef.current[normalizedTargetSessionId] || 0;
      chatSocketReconnectAttemptsRef.current[normalizedTargetSessionId] = reconnectAttempt + 1;
      chatSocketReconnectTimersRef.current[normalizedTargetSessionId] = setTimeout(() => {
        ensureChatSocketForSession(normalizedTargetSessionId, { selected: isSelectedSession() });
      }, chatReconnectDelayMs(reconnectAttempt, SOCKET_RECONNECT_MS));
      if (isSelectedSession()) {
        startupChatSocketReadyRef.current = false;
        setSocketState('reconnecting');
      }
    };

    ws.onerror = () => {
      if (isSelectedSession()) {
        startupChatSocketReadyRef.current = false;
        setSocketState('error');
      }
    };

    return ws;
  };

  const queueMessage = (
    text: string,
    sourceFormat: MessageSourceFormat,
    explicitSessionId?: string,
    policyOverride?: InterruptPolicy,
    modeOptions?: ComposerModeOptions,
  ) => {
    const activeSessionId = explicitSessionId || sessionIdRef.current;
    if (!activeSessionId) {
      setStatus('missing session');
      return;
    }
    if (blockMissingProviderApiKey()) {
      return;
    }

    const clientMessageId = createClientMessageId(appClientIdRef.current);
    const isSelectedSessionMessage = activeSessionId === sessionIdRef.current;
    if (isSelectedSessionMessage) {
      setMessages((previous: any) => [
        ...previous,
        {
          role: 'user',
          content: text,
          timestamp: new Date().toISOString(),
          displayLabel: sourceFormat === 'app_voice_transcript' ? 'Voice' : 'You',
          channel: 'app',
          sourceFormat,
          runMode: modeOptions?.runMode || null,
          raw: {
            client_message_id: clientMessageId,
            run_mode: modeOptions?.runMode || null,
            plan_action: modeOptions?.planAction || null,
            plan_answer: modeOptions?.planAnswer || null,
          },
          messageKey: `pending:${clientMessageId}`,
          pending: true,
          localSessionId: activeSessionId,
          sourceClientId: appClientIdRef.current,
        },
      ]);
    }

    pendingMessagesRef.current.push({
      clientMessageId,
      text,
      sourceFormat,
      interruptPolicy: policyOverride ?? interruptPolicy,
      sessionId: activeSessionId,
      deliveryState: 'queued',
      modeOptions,
    });
    chatSocketRunActiveBySessionRef.current[activeSessionId] = true;
    if (isSelectedSessionMessage) {
      setChatRunActive(true);
      setRuntimeRunState('running');
      setLastAssistantOutputAt(null);
    }

    if (taskBoardArmedNextTurn && activeSessionId === sessionIdRef.current) {
      setTaskBoardArmedNextTurnState(false);
      setOverview((previous: any) => (
        previous
          ? {
              ...previous,
              task_board_armed_next_turn: false,
            }
          : previous
      ));
    }

    const ws = ensureChatSocketForSession(activeSessionId, { selected: isSelectedSessionMessage });
    if (ws && ws.readyState === WebSocket.OPEN) {
      flushPendingMessages(activeSessionId, ws);
      if (isSelectedSessionMessage) {
        setStatus(sourceFormat === 'app_voice_transcript' ? 'sending voice transcript' : 'sending message');
      }
    } else {
      setStatus(isSelectedSessionMessage ? 'chat reconnecting · message queued' : 'message queued in background chat');
    }
  };

  const queueComposerMessage = (text: string, sourceFormat: MessageSourceFormat, explicitSessionId?: string, modeOptions?: ComposerModeOptions) => {
    const activeSessionId = explicitSessionId || sessionIdRef.current;
    if (!activeSessionId) {
      setStatus('missing session');
      return;
    }
    setQueuedComposerMessages((current: any) => [
      ...current,
      {
        id: `queued-${Date.now()}-${current.length}`,
        text,
        sourceFormat,
        sessionId: activeSessionId,
        modeOptions,
        queuedAt: Date.now(),
      },
    ]);
    setStatus('message queued for the current run');
  };

  const setComposerInputValue = (
    nextInput: string,
    options?: { syncVoiceBase?: boolean; origin?: ComposerInputOrigin },
  ) => {
    setInput(nextInput);
    lastComposerInputOriginRef.current = options?.origin ?? 'system';
    if (options?.syncVoiceBase === false) {
      return;
    }
    voiceComposerBaseInputRef.current = nextInput;
    if (!nextInput) {
      voiceComposerDraftRef.current = '';
    }
  };

  const handleComposerContentSizeChange = (
    event: NativeSyntheticEvent<TextInputContentSizeChangeEventData>,
  ) => {
    const nextHeight = event.nativeEvent.contentSize?.height;
    if (typeof nextHeight !== 'number' || Number.isNaN(nextHeight)) {
      return;
    }
    const clampedHeight = Math.max(COMPOSER_MIN_HEIGHT, Math.min(COMPOSER_MAX_HEIGHT, Math.ceil(nextHeight)));
    setComposerInputHeight((current: any) => (
      Math.abs(current - clampedHeight) < 1 ? current : clampedHeight
    ));
  };

  const handleComposerMeasureLayout = (event: LayoutChangeEvent) => {
    if (Platform.OS !== 'web') {
      return;
    }
    const nextHeight = event.nativeEvent.layout.height;
    if (typeof nextHeight !== 'number' || Number.isNaN(nextHeight)) {
      return;
    }
    const clampedHeight = Math.max(COMPOSER_MIN_HEIGHT, Math.min(COMPOSER_MAX_HEIGHT, Math.ceil(nextHeight)));
    setComposerInputHeight((current: any) => (
      Math.abs(current - clampedHeight) < 1 ? current : clampedHeight
    ));
  };

  const handleComposerInputChange = (nextInput: string) => {
    setComposerInputValue(nextInput, { syncVoiceBase: false, origin: 'manual' });
    if (!(voiceCaptureModeRef.current === 'always_on' && (voiceRecordingRef.current || voiceRunningRef.current))) {
      voiceComposerBaseInputRef.current = nextInput;
      voiceComposerDraftRef.current = '';
    }
  };

  useEffect(() => {
    if (!input) {
      setComposerInputHeight(COMPOSER_MIN_HEIGHT);
    }
  }, [input]);

  const appendLocalMessage = (
    content: string,
    role: DesktopMessage['role'],
    displayLabel: string,
    channel: DesktopMessage['channel'] = 'system',
  ) => {
    const normalized = content.trim();
    if (!normalized) {
      return;
    }
    const activeSessionId = sessionIdRef.current;
    setMessages((previous: any) => [
      ...previous,
      {
        role,
        content: normalized,
        timestamp: new Date().toISOString(),
        displayLabel,
        channel,
        sourceFormat: 'app_system',
        messageKey: `local:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
        localOnly: true,
        localSessionId: activeSessionId,
      },
    ]);
  };

  const appendLocalSystemMessage = (content: string, displayLabel = 'Command') => {
    appendLocalMessage(content, 'system', displayLabel, 'system');
  };

  const requireActiveDesktopSession = () => {
    const activeSessionId = String(sessionIdRef.current || '').trim();
    if (activeSessionId) {
      return activeSessionId;
    }
    setStatus(DESKTOP_NO_ACTIVE_SESSION_STATUS);
    pushActivity(DESKTOP_NO_ACTIVE_SESSION_STATUS, 'warn');
    appendLocalSystemMessage(DESKTOP_NO_ACTIVE_SESSION_STATUS, 'Warning');
    return null;
  };

  const stopVoiceTracks = () => {
    const captureNode = voiceCaptureNodeRef.current;
    voiceCaptureNodeRef.current = null;
    if (captureNode) {
      captureNode.stop();
    }

    const source = voiceAudioSourceRef.current;
    voiceAudioSourceRef.current = null;
    if (source) {
      try {
        source.disconnect();
      } catch {
        // no-op
      }
    }

    const context = voiceAudioContextRef.current;
    voiceAudioContextRef.current = null;
    if (context && context.state !== 'closed') {
      void context.close().catch(() => undefined);
    }

    const stream = voiceStreamRef.current;
    voiceStreamRef.current = null;
    if (stream) {
      for (const track of stream.getTracks()) {
        track.stop();
      }
    }

    voiceGateStateRef.current = createVoiceGateState();
    jarvisWakeMatchStateRef.current = createJarvisWakeMatchState();
    deferredAlwaysOnFramesRef.current = [];
    deferredAlwaysOnSampleCountRef.current = 0;
    activeVoiceUtteranceIdRef.current = null;
    activeVoiceBargeInCandidateRef.current = false;
    activeVoiceBargeInReferenceTextRef.current = '';
    jarvisBargeInCandidateUtteranceIdsRef.current.clear();
  };

  const resetVoiceCaptureBuffers = (options?: { clearProgrammaticComposerInput?: boolean }) => {
    voiceChunkSequenceRef.current = 0;
    voiceChunkChainRef.current = Promise.resolve();
    voiceChunkSamplesRef.current = [];
    voiceChunkSampleCountRef.current = 0;
    activeVoiceUtteranceIdRef.current = null;
    voiceGateStateRef.current = createVoiceGateState();
    jarvisWakeMatchStateRef.current = createJarvisWakeMatchState();
    deferredAlwaysOnFramesRef.current = [];
    deferredAlwaysOnSampleCountRef.current = 0;
    drainingDeferredAlwaysOnFramesRef.current = false;
    voiceComposerBaseInputRef.current = '';
    voiceComposerDraftRef.current = '';
    activeVoiceBargeInCandidateRef.current = false;
    activeVoiceBargeInReferenceTextRef.current = '';
    jarvisBargeInCandidateUtteranceIdsRef.current.clear();
    const lastInputOrigin = lastComposerInputOriginRef.current;
    lastComposerInputOriginRef.current = 'system';
    setVoiceDraft('');
    setVoiceError(null);
    if (options?.clearProgrammaticComposerInput && lastInputOrigin !== 'manual') {
      setComposerInputValue('', { syncVoiceBase: false, origin: 'system' });
    }
  };

  const cleanupAssistantAudio = async () => {
    const audio = assistantAudioRef.current;
    assistantAudioRef.current = null;
    assistantAudioTextRef.current = '';
    if (!audio) {
      return;
    }
    try {
      audio.pause();
    } catch {
      // no-op
    }
    audio.src = '';
  };

  const deactivateVoiceRuntime = (nextState = 'idle') => {
    if (voiceReconnectRef.current) {
      clearTimeout(voiceReconnectRef.current);
      voiceReconnectRef.current = null;
    }
    if (voiceWsRef.current) {
      voiceWsRef.current.close();
      voiceWsRef.current = null;
    }
    voiceStartInFlightRef.current = false;
    voicePressActiveRef.current = false;
    alwaysOnEnabledRef.current = false;
    setAlwaysOnEnabled(false);
    stopVoiceTracks();
    resetVoiceCaptureBuffers();
    voiceRunningRef.current = false;
    voiceRecordingRef.current = false;
    setVoiceRunning(false);
    setVoiceRecording(false);
    setVoiceMode('push_to_talk');
    setVoiceDraft('');
    setVoiceError(null);
    setLiveVoiceStatus(null);
    setJarvisLatestTranscript('');
    setJarvisLatestSpokenText('');
    setVoiceState(nextState);
    void cleanupAssistantAudio();
  };

  const playAssistantAudio = async (audioBase64: string, mimeType: string, text?: string) => {
    if (!audioBase64 || typeof globalThis.Audio === 'undefined') {
      return;
    }
    await cleanupAssistantAudio();
    const spokenText = String(text || '').trim();
    const audio = new globalThis.Audio(`data:${mimeType || 'audio/mpeg'};base64,${audioBase64}`);
    assistantAudioRef.current = audio;
    assistantAudioTextRef.current = spokenText;
    if (spokenText) {
      setJarvisLatestSpokenText(spokenText);
    }
    audio.onended = () => {
      if (assistantAudioRef.current === audio) {
        assistantAudioRef.current = null;
        assistantAudioTextRef.current = '';
      }
      if (conversationModeRef.current === 'jarvis' && alwaysOnEnabledRef.current && !voiceRecordingRef.current && !voiceRunningRef.current) {
        setVoiceState('always_on');
      }
    };
    try {
      if (conversationModeRef.current === 'jarvis') {
        setVoiceState('speaking');
      }
      await audio.play();
    } catch (error) {
      if (assistantAudioRef.current === audio) {
        assistantAudioRef.current = null;
        assistantAudioTextRef.current = '';
      }
      pushActivity('Assistant audio did not play.', 'warn');
      if (conversationModeRef.current === 'jarvis' && alwaysOnEnabledRef.current) {
        setVoiceState('always_on');
      }
      logDiagnostic('desktop.voice.audio', 'assistant audio playback failed', describeError(error), 'warn');
    }
  };

  const sendVoiceChunk = (samples: Float32Array, sampleRate: number) => {
    if (!samples.length) {
      return;
    }
    const wavBytes = new Uint8Array(encodePcm16Wav(samples, sampleRate));
    voiceChunkChainRef.current = voiceChunkChainRef.current
      .catch(() => undefined)
      .then(async () => {
        const ws = voiceWsRef.current;
        if (!ws || ws.readyState !== WebSocket.OPEN) {
          throw new Error('Voice socket unavailable');
        }
        voiceChunkSequenceRef.current += 1;
        ws.send(JSON.stringify({
          type: 'voice_chunk',
          session_id: sessionIdRef.current,
          surface_mode: conversationModeRef.current,
          utterance_id: activeVoiceUtteranceIdRef.current,
          sequence: voiceChunkSequenceRef.current,
          mime_type: 'audio/wav',
          audio_base64: bytesToBase64(wavBytes),
        }));
        logDiagnostic('desktop.voice.ws', 'sent voice chunk', {
          sequence: voiceChunkSequenceRef.current,
          samples: samples.length,
          sampleRate,
          sessionId: sessionIdRef.current || null,
        });
      })
      .catch((error: any) => {
        const message = describeError(error);
        setVoiceState('error');
        setVoiceError(message);
        setVoiceRunning(false);
        setVoiceRecording(false);
        pushActivity(`Voice chunk failed: ${message}`, 'error');
        logDiagnostic('desktop.voice.ws', 'voice chunk failed', message, 'error');
      });
  };

  const flushVoiceChunk = () => {
    const sampleCount = voiceChunkSampleCountRef.current;
    if (sampleCount <= 0) {
      return voiceChunkChainRef.current;
    }
    const samples = concatFloat32(voiceChunkSamplesRef.current, sampleCount);
    voiceChunkSamplesRef.current = [];
    voiceChunkSampleCountRef.current = 0;
    sendVoiceChunk(samples, voiceSampleRateRef.current);
    return voiceChunkChainRef.current;
  };

  const appendVoiceChunkSamples = (samples: Float32Array, force = false) => {
    if (!samples.length) return;
    voiceChunkSamplesRef.current.push(samples);
    voiceChunkSampleCountRef.current += samples.length;
    const chunkTarget = Math.max(1, Math.round(voiceSampleRateRef.current * activeVoiceSegmentMs / 1000));
    if (force || voiceChunkSampleCountRef.current >= chunkTarget) {
      void flushVoiceChunk();
    }
  };

  const beginVoiceSegment = (
    mode: VoiceCaptureMode,
    options?: { preserveAssistantAudio?: boolean; bargeInCandidate?: boolean },
  ) => {
    const ws = voiceWsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setStatus('voice socket unavailable');
      return false;
    }
    if (conversationModeRef.current === 'jarvis' && assistantAudioRef.current && !options?.preserveAssistantAudio) {
      setStatus('Jarvis is speaking. Use interrupt to stop it.');
      return false;
    }

    voiceCaptureModeRef.current = mode;
    voiceChunkSequenceRef.current = 0;
    voiceChunkChainRef.current = Promise.resolve();
    voiceChunkSamplesRef.current = [];
    voiceChunkSampleCountRef.current = 0;
    const utteranceId = createClientId();
    activeVoiceUtteranceIdRef.current = utteranceId;
    activeVoiceBargeInCandidateRef.current = Boolean(options?.bargeInCandidate);
    if (options?.bargeInCandidate) {
      jarvisBargeInCandidateUtteranceIdsRef.current.add(utteranceId);
      activeVoiceBargeInReferenceTextRef.current = assistantAudioTextRef.current;
    } else {
      activeVoiceBargeInReferenceTextRef.current = '';
    }
    if (mode === 'always_on') {
      // Only seed always-on accumulation from a real manual composer draft.
      // Older programmatic voice text should not leak into a new segment.
      if (lastComposerInputOriginRef.current === 'manual') {
        voiceComposerBaseInputRef.current = input;
      } else if (!voiceComposerBaseInputRef.current) {
        voiceComposerBaseInputRef.current = '';
      }
      voiceComposerDraftRef.current = '';
    }
    setVoiceDraft('');
    setVoiceError(null);
    setAssistantDraft('');
    setThinking('');
    setVoiceState('listening');
    voiceRunningRef.current = true;
    voiceRecordingRef.current = true;
    setVoiceRunning(true);
    setVoiceRecording(true);
    setStatus(mode === 'always_on' ? 'always-on voice segment detected' : 'voice listening');
    const wakeVerifiedLocally = (
      mode === 'always_on'
      && conversationModeRef.current === 'jarvis'
      && !jarvisHoldToTalkMode
    );
    ws.send(JSON.stringify({
      type: 'voice_start',
      session_id: sessionIdRef.current,
      surface_mode: conversationModeRef.current,
      capture_mode: mode,
      wake_phrase: mode === 'always_on' && conversationModeRef.current === 'jarvis' ? currentJarvisWakePhrase : undefined,
      wake_verified_locally: wakeVerifiedLocally || undefined,
      utterance_id: utteranceId,
      barge_in_candidate: options?.bargeInCandidate || undefined,
    }));
    logDiagnostic('desktop.voice.ws', 'sent voice_start', {
      mode,
      sampleRate: voiceSampleRateRef.current,
      sessionId: sessionIdRef.current || null,
    });
    if (!options?.preserveAssistantAudio) {
      void cleanupAssistantAudio();
    }
    return true;
  };

  const shouldAutoSendAlwaysOnVoice = () => (
    conversationModeRef.current === 'jarvis' || ALWAYS_ON_VOICE_AUTO_SEND
  );

  const finishVoiceSegment = async (commit: boolean, mode: VoiceCaptureMode) => {
    await flushVoiceChunk().catch(() => undefined);
    await voiceChunkChainRef.current.catch(() => undefined);

    const ws = voiceWsRef.current;
    const autoSend = commit && mode === 'always_on' ? shouldAutoSendAlwaysOnVoice() : true;
    const utteranceId = activeVoiceUtteranceIdRef.current;
    const bargeInCandidate = activeVoiceBargeInCandidateRef.current;
    const wakeVerifiedLocally = (
      mode === 'always_on'
      && conversationModeRef.current === 'jarvis'
      && !jarvisHoldToTalkMode
    );
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: commit ? 'voice_commit' : 'voice_cancel',
        session_id: sessionIdRef.current,
        surface_mode: conversationModeRef.current,
        capture_mode: mode,
        wake_phrase: mode === 'always_on' && conversationModeRef.current === 'jarvis' ? currentJarvisWakePhrase : undefined,
        wake_verified_locally: wakeVerifiedLocally || undefined,
        utterance_id: utteranceId,
        interrupt_policy: commit ? interruptPolicy : 'none',
        auto_send: autoSend,
        barge_in_candidate: commit && bargeInCandidate ? true : undefined,
        barge_in_reference_text: commit && bargeInCandidate
          ? activeVoiceBargeInReferenceTextRef.current.slice(0, 1200)
          : undefined,
      }));
      logDiagnostic('desktop.voice.ws', commit ? 'sent voice_commit' : 'sent voice_cancel', {
        mode,
        sessionId: sessionIdRef.current || null,
        interruptPolicy: commit ? interruptPolicy : 'none',
        autoSend,
        bargeInCandidate,
        utteranceId,
      });
    }
    if (!commit && utteranceId) {
      jarvisBargeInCandidateUtteranceIdsRef.current.delete(utteranceId);
    }
    activeVoiceUtteranceIdRef.current = null;
    activeVoiceBargeInCandidateRef.current = false;
    activeVoiceBargeInReferenceTextRef.current = '';

    voiceRecordingRef.current = false;
    setVoiceRecording(false);
    if (commit) {
      voiceRunningRef.current = true;
      setVoiceRunning(true);
      setVoiceState('finalizing');
      setStatus(
        mode === 'always_on' && !autoSend
          ? 'always-on transcript finalizing'
          : mode === 'always_on'
            ? 'always-on voice segment finalizing'
            : 'voice finalizing'
      );
      if (mode === 'always_on' && alwaysOnEnabledRef.current && conversationModeRef.current === 'jarvis') {
        setTimeout(drainDeferredAlwaysOnFrames, 0);
      }
    } else {
      if (mode === 'always_on') {
        voiceComposerDraftRef.current = '';
        setComposerInputValue(voiceComposerBaseInputRef.current, { syncVoiceBase: false, origin: 'voice' });
      }
      setVoiceDraft('');
      voiceRunningRef.current = false;
      setVoiceRunning(false);
      setVoiceState(mode === 'always_on' && alwaysOnEnabledRef.current ? 'always_on' : 'cancelled');
      setStatus(mode === 'always_on' && alwaysOnEnabledRef.current ? 'always-on voice listening' : 'voice cancelled');
    }
  };

  const rememberDeferredAlwaysOnFrame = (frame: Float32Array) => {
    if (!alwaysOnEnabledRef.current || frame.length === 0) {
      return;
    }

    deferredAlwaysOnFramesRef.current.push(frame);
    deferredAlwaysOnSampleCountRef.current += frame.length;

    const maxSamples = Math.max(
      frame.length,
      Math.round(voiceSampleRateRef.current * VOICE_DEFERRED_FRAME_MAX_MS / 1000)
    );
    while (deferredAlwaysOnSampleCountRef.current > maxSamples && deferredAlwaysOnFramesRef.current.length > 1) {
      const dropped = deferredAlwaysOnFramesRef.current.shift();
      deferredAlwaysOnSampleCountRef.current -= dropped?.length || 0;
    }
  };

  const processAlwaysOnFrame = (frame: Float32Array) => {
    if (!alwaysOnEnabledRef.current) {
      return;
    }

    const gate = voiceGateStateRef.current;
    const frameDbfs = samplesDbfs(frame);
    const aboveThreshold = frameDbfs >= activeVoiceGateDbfs;
    const aboveBargeInThreshold = frameDbfs >= activeJarvisBargeInGateDbfs;
    const assistantAudioActive = conversationModeRef.current === 'jarvis' && Boolean(assistantAudioRef.current);
    const isJarvisAlwaysOn = conversationModeRef.current === 'jarvis';
    const attackFrames = Math.max(1, Math.ceil(VOICE_GATE_ATTACK_MS / VOICE_GATE_FRAME_MS));
    const releaseMs = isJarvisAlwaysOn ? Math.max(activeVoiceGateReleaseMs, 2000) : activeVoiceGateReleaseMs;
    const releaseFrames = Math.max(1, Math.ceil(releaseMs / VOICE_GATE_FRAME_MS));
    const prerollFrames = Math.max(1, Math.ceil(activeVoiceGatePrerollMs / VOICE_GATE_FRAME_MS));
    const minFrames = Math.max(1, Math.ceil(VOICE_GATE_MIN_MS / VOICE_GATE_FRAME_MS));
    const bargeInMinFrames = Math.max(minFrames, Math.ceil(JARVIS_BARGE_IN_MIN_VOICED_MS / VOICE_GATE_FRAME_MS));
    const maxFrames = Math.max(minFrames, Math.ceil(activeVoiceGateMaxMs / VOICE_GATE_FRAME_MS));
    const requiresWakeAudioMatch = isJarvisAlwaysOn && !jarvisHoldToTalkMode;
    const wakeMinFrames = Math.max(1, Math.ceil(JARVIS_WAKE_MATCH_MIN_MS / VOICE_GATE_FRAME_MS));
    const wakeMaxFrames = Math.max(wakeMinFrames, Math.ceil(JARVIS_WAKE_MATCH_MAX_MS / VOICE_GATE_FRAME_MS));
    const wakeReleaseFrames = Math.max(1, Math.ceil(JARVIS_WAKE_MATCH_RELEASE_MS / VOICE_GATE_FRAME_MS));
    const wakeScoreEveryFrames = Math.max(1, Math.ceil(JARVIS_WAKE_MATCH_SCORE_EVERY_MS / VOICE_GATE_FRAME_MS));

    if (!gate.recording) {
      if (isJarvisAlwaysOn && (assistantAudioActive || voiceRunningRef.current || voiceRecordingRef.current)) {
        gate.prerollFrames = [];
        gate.aboveFrames = 0;
        jarvisWakeMatchStateRef.current = createJarvisWakeMatchState();
        return;
      }
      const startAboveThreshold = assistantAudioActive ? aboveBargeInThreshold : aboveThreshold;
      const canStartQueuedJarvisSegment = (
        apiVoiceInputActive
        && conversationModeRef.current === 'jarvis'
        && !voiceRecordingRef.current
      );
      if ((voiceRunningRef.current || voiceRecordingRef.current) && !canStartQueuedJarvisSegment) {
        rememberDeferredAlwaysOnFrame(frame);
        return;
      }
      gate.prerollFrames.push(frame);
      while (gate.prerollFrames.length > prerollFrames) {
        gate.prerollFrames.shift();
      }
      gate.aboveFrames = startAboveThreshold ? gate.aboveFrames + 1 : 0;
      const wakeState = jarvisWakeMatchStateRef.current;
      if (!wakeState.active && gate.aboveFrames < attackFrames) {
        return;
      }

      if (requiresWakeAudioMatch) {
        const profile = jarvisWakeProfileRef?.current || null;
        if (!jarvisWakeProfileReady || !profile) {
          setJarvisWakeEnrollmentOpen?.(true);
          setStatus('Train a local wake phrase before using Jarvis always-on listening');
          voiceGateStateRef.current = createVoiceGateState();
          jarvisWakeMatchStateRef.current = createJarvisWakeMatchState();
          return;
        }

        if (!wakeState.active) {
          wakeState.active = true;
          wakeState.frames = [...gate.prerollFrames];
          wakeState.sampleCount = wakeState.frames.reduce((sum: number, item: Float32Array) => sum + item.length, 0);
          wakeState.frameCount = wakeState.frames.length;
          wakeState.voicedFrames = gate.aboveFrames;
          wakeState.belowFrames = aboveThreshold ? 0 : 1;
          wakeState.lastScoreFrame = 0;
          wakeState.bestDistance = null;
        } else {
          wakeState.frames.push(frame);
          wakeState.sampleCount += frame.length;
          wakeState.frameCount += 1;
          if (aboveThreshold) {
            wakeState.voicedFrames += 1;
            wakeState.belowFrames = 0;
          } else {
            wakeState.belowFrames += 1;
          }
        }

        const shouldScoreWake = (
          wakeState.frameCount >= wakeMinFrames
          && wakeState.frameCount - wakeState.lastScoreFrame >= wakeScoreEveryFrames
        );
        if (shouldScoreWake) {
          wakeState.lastScoreFrame = wakeState.frameCount;
          const score = scoreJarvisWakeCandidate(
            concatFloat32(wakeState.frames, wakeState.sampleCount),
            voiceSampleRateRef.current,
            profile,
          );
          wakeState.bestDistance = Math.min(wakeState.bestDistance ?? Number.POSITIVE_INFINITY, score.distance);
          wakeState.matchedFrames = score.matched ? wakeState.matchedFrames + 1 : 0;
          if (wakeState.matchedFrames >= 2) {
            const matchedAudio = concatFloat32(wakeState.frames, wakeState.sampleCount);
            const profileDurationMs = profile.signatures.reduce(
              (sum: number, signature: any) => sum + Number(signature.durationMs || 0),
              0,
            ) / Math.max(1, profile.signatures.length);
            const wakeSampleCount = Math.max(
              0,
              Math.min(matchedAudio.length, Math.round(voiceSampleRateRef.current * profileDurationMs / 1000)),
            );
            const commandTail = matchedAudio.subarray(wakeSampleCount);
            playJarvisWakeTone();
            if (!beginVoiceSegment('always_on')) {
              voiceGateStateRef.current = createVoiceGateState();
              jarvisWakeMatchStateRef.current = createJarvisWakeMatchState();
              return;
            }

            gate.recording = true;
            gate.activeFrames = Math.ceil(commandTail.length / Math.max(1, frame.length));
            gate.voicedFrames = gate.activeFrames;
            gate.belowFrames = 0;
            gate.prerollFrames = [];
            if (commandTail.length) {
              appendVoiceChunkSamples(commandTail);
            }
            jarvisWakeMatchStateRef.current = createJarvisWakeMatchState();
            setStatus(`Wake phrase "${currentJarvisWakePhrase}" matched · listening`);
            logDiagnostic('desktop.voice.wake', 'wake phrase matched', {
              phrase: currentJarvisWakePhrase,
              distance: score.distance,
              threshold: score.threshold,
              durationMs: score.durationMs,
              releaseMs,
            });
            return;
          }
        }

        const shouldRejectWake = wakeState.belowFrames >= wakeReleaseFrames || wakeState.frameCount >= wakeMaxFrames;
        if (shouldRejectWake) {
          logDiagnostic('desktop.voice.wake', 'ignored audio without wake match', {
            phrase: currentJarvisWakePhrase,
            bestDistance: wakeState.bestDistance,
            frameCount: wakeState.frameCount,
          });
          voiceGateStateRef.current = createVoiceGateState();
          jarvisWakeMatchStateRef.current = createJarvisWakeMatchState();
        }
        return;
      }

      if (!beginVoiceSegment('always_on')) {
        voiceGateStateRef.current = createVoiceGateState();
        jarvisWakeMatchStateRef.current = createJarvisWakeMatchState();
        return;
      }

      gate.recording = true;
      gate.activeFrames = gate.prerollFrames.length;
      gate.voicedFrames = gate.aboveFrames;
      gate.belowFrames = 0;
      for (const preroll of gate.prerollFrames) {
        appendVoiceChunkSamples(preroll);
      }
      return;
    }

    appendVoiceChunkSamples(frame);
    gate.activeFrames += 1;
    const activeVoiced = activeVoiceBargeInCandidateRef.current ? aboveBargeInThreshold : aboveThreshold;
    if (activeVoiced) {
      gate.voicedFrames += 1;
      gate.belowFrames = 0;
    } else {
      gate.belowFrames += 1;
    }

    const shouldClose = gate.belowFrames >= releaseFrames || gate.activeFrames >= maxFrames;
    if (!shouldClose) {
      return;
    }

    const requiredVoicedFrames = activeVoiceBargeInCandidateRef.current ? bargeInMinFrames : minFrames;
    const shouldCommit = gate.voicedFrames >= requiredVoicedFrames;
    voiceGateStateRef.current = createVoiceGateState();
    jarvisWakeMatchStateRef.current = createJarvisWakeMatchState();
    void finishVoiceSegment(shouldCommit, 'always_on');
  };

  const drainDeferredAlwaysOnFrames = () => {
    const blockedByRunningTurn = voiceRunningRef.current && conversationModeRef.current !== 'jarvis';
    if (
      !alwaysOnEnabledRef.current
      || blockedByRunningTurn
      || voiceRecordingRef.current
      || drainingDeferredAlwaysOnFramesRef.current
      || deferredAlwaysOnFramesRef.current.length === 0
    ) {
      return;
    }

    const frames = deferredAlwaysOnFramesRef.current.splice(0);
    deferredAlwaysOnSampleCountRef.current = 0;
    drainingDeferredAlwaysOnFramesRef.current = true;
    try {
      for (const frame of frames) {
        if (!alwaysOnEnabledRef.current) {
          break;
        }
        processAlwaysOnFrame(frame);
      }
    } finally {
      drainingDeferredAlwaysOnFramesRef.current = false;
    }
  };

  const processVoiceSamples = (samples: Float32Array) => {
    if (voiceCaptureModeRef.current === 'push_to_talk') {
      appendVoiceChunkSamples(samples);
      return;
    }

    const gate = voiceGateStateRef.current;
    gate.pendingFrames.push(samples);
    gate.pendingSampleCount += samples.length;
    const frameSamples = Math.max(1, Math.round(voiceSampleRateRef.current * VOICE_GATE_FRAME_MS / 1000));
    let frame = takeGateFrame(gate, frameSamples);
    while (frame) {
      processAlwaysOnFrame(frame);
      frame = takeGateFrame(gate, frameSamples);
    }
  };

  const acceptJarvisBargeInTranscript = (turnId: string, text: string) => {
    const normalizedTurnId = String(turnId || '').trim();
    if (!normalizedTurnId || !jarvisBargeInCandidateUtteranceIdsRef.current.has(normalizedTurnId)) {
      return false;
    }
    jarvisBargeInCandidateUtteranceIdsRef.current.delete(normalizedTurnId);
    void cleanupAssistantAudio();
    setStatus('Jarvis interrupted · applying your correction');
    pushActivity(`Jarvis accepted voice interrupt: ${text}`, 'accent');
    return true;
  };

  const clearJarvisBargeInCandidate = (turnId: string) => {
    const normalizedTurnId = String(turnId || '').trim();
    if (normalizedTurnId) {
      jarvisBargeInCandidateUtteranceIdsRef.current.delete(normalizedTurnId);
    }
  };

  const handleRealtimeEvent = (event: DesktopRealtimeEvent, channel: 'chat' | 'voice') => handleDesktopConversationRealtimeEvent(scope, event, channel);
  const executeSlashCommand = async (text: string) => {
    const commandLabel = text.trim().split(/\s+/, 1)[0] || '/command';
    setStatus(`${commandLabel} requested`);
    setAssistantDraft('');
    setThinking('');
    setVoiceDraft('');
    appendLocalMessage(text, 'user', 'Command', 'app');

    const result = await runDesktopSlashCommand(text, {
      apiBaseUrl,
      token,
      sessionId: sessionIdRef.current,
      overview,
      sessions,
      jobs,
      envFilePath,
    });

    const timelineSessionId = result.nextSessionId || sessionIdRef.current;
    let commandTimelineRecorded = false;
    if (timelineSessionId) {
      const timelineContent = result.output || `${commandLabel} completed.`;
      const response = await appendSessionTimelineEvent(apiBaseUrl, token, timelineSessionId, {
        kind: 'command',
        title: `Command · ${text.trim()}`,
        content: timelineContent,
        tone: 'accent',
        channel: 'app',
        source_format: 'app_system',
        metadata: {
          command: text.trim(),
          status: result.status || null,
        },
        source_client_id: appClientIdRef.current,
      }).catch(() => null);
      if (response?.event) {
        appendTimelineEvent(response.event);
        commandTimelineRecorded = true;
      }
    }

    if (result.refresh || result.nextSessionId) {
      await refreshSidebarState(result.nextSessionId || sessionIdRef.current, true);
    }

    if (result.output) {
      if (!commandTimelineRecorded) {
        appendLocalSystemMessage(result.output, 'Command Result');
      }
      const activityPreview = result.output.split('\n', 1)[0]?.trim();
      if (activityPreview) {
        pushActivity(activityPreview, 'accent');
      }
    } else if (result.handled && !commandTimelineRecorded) {
      appendLocalSystemMessage(`${commandLabel} completed.`, 'Command Result');
    }
    setStatus(result.status || 'ready');
  };

  const runSlashCommandFromComposer = async (text: string) => {
    try {
      await executeSlashCommand(text);
    } catch (error) {
      const message = describeError(error);
      setStatus(message);
      pushActivity(message, 'error');
      let commandTimelineRecorded = false;
      if (sessionIdRef.current) {
        const response = await appendSessionTimelineEvent(apiBaseUrl, token, sessionIdRef.current, {
          kind: 'command',
          title: `Command · ${text.trim()}`,
          content: message,
          tone: 'error',
          channel: 'app',
          source_format: 'app_system',
          metadata: {
            command: text.trim(),
            error: true,
          },
          source_client_id: appClientIdRef.current,
        }).catch(() => null);
        if (response?.event) {
          appendTimelineEvent(response.event);
          commandTimelineRecorded = true;
        }
      }
      if (!commandTimelineRecorded) {
        appendLocalSystemMessage(message, 'Command Error');
      }
    }
  };

  const runVerboseCommand = async (arg?: 'on' | 'off' | 'status') => {
    const commandText = arg ? `/verbose ${arg}` : '/verbose';
    setActiveCommandPanel(null);
    if (arg === 'on' || arg === 'off') {
      const nextVerboseMode = arg === 'on';
      setOverview((previous: any) => (
        previous
          ? {
              ...previous,
              verbose_mode: nextVerboseMode,
            }
          : previous
      ));
    }
    await runSlashCommandFromComposer(commandText);
  };

  const openCommandPanelForInput = (text: string) => {
    const command = parseComposerSlashCommand(text);
    if (!command || command.rawArgs) {
      return false;
    }

    if (command.name === 'model' || command.name === 'models') {
      setActiveCommandPanel({ kind: 'model' });
      setStatus('choose a model');
      return true;
    }

    if (command.name === 'planner') {
      setActiveCommandPanel({ kind: 'model' });
      setStatus('choose a planner model');
      return true;
    }

    if (command.name === 'session') {
      setSidebarExpanded(true);
      setStatus('choose a chat in the sidebar');
      return true;
    }

    if (command.name === 'verbose') {
      setActiveCommandPanel({ kind: 'verbose' });
      setStatus('choose verbose mode');
      return true;
    }

    if (command.name === 'compact') {
      return false;
    }

    const suggestion = DESKTOP_COMMAND_SUGGESTIONS.find((item: any) => item.name === command.name);
    setActiveCommandPanel({
      kind: 'command',
      command: `/${command.name}`,
      description: suggestion?.description || 'Run this command.',
    });
    setStatus(`review /${command.name}`);
    return true;
  };

  const chooseModel = async (model: string) => {
    if (!sessionIdRef.current && draftChatRef.current) {
      setDraftChat((current: any) => (
        current
          ? {
              ...current,
              model,
              variant: null,
            }
          : current
      ));
      setActiveCommandPanel(null);
      setStatus(`draft model ${model}`);
      return;
    }
    const activeSessionId = requireActiveDesktopSession();
    if (!activeSessionId) return;
    setStatus(`switching model to ${model}`);
    try {
      await configureAgent(apiBaseUrl, token, { model }, activeSessionId);
      setActiveCommandPanel(null);
      appendLocalSystemMessage(`Model switched to ${model}.`, 'Command Result');
      pushActivity(`Model switched to ${model}`, 'accent');
      await Promise.all([
        refreshSidebarState(activeSessionId, true),
        refreshOverviewState(activeSessionId, { quiet: true }),
      ]);
      setStatus(`model ${model}`);
    } catch (error) {
      const message = describeError(error);
      setStatus(message);
      appendLocalSystemMessage(message, 'Command Error');
      pushActivity(message, 'error');
    }
  };

  const chooseVariant = async (variant: string) => {
    const label = modelVariantDisplayLabel(variant);
    if (!sessionIdRef.current && draftChatRef.current) {
      setDraftChat((current: any) => (
        current
          ? {
              ...current,
              variant,
            }
          : current
      ));
      setActiveCommandPanel(null);
      setStatus(`draft variant ${label}`);
      return;
    }
    const activeSessionId = requireActiveDesktopSession();
    if (!activeSessionId) return;
    setStatus(`switching variant to ${label}`);
    try {
      await configureAgent(apiBaseUrl, token, { variant }, activeSessionId);
      setOverview((previous: any) => (
        previous
          ? {
              ...previous,
              current_variant: variant,
            }
          : previous
      ));
      setActiveCommandPanel(null);
      appendLocalSystemMessage(`Variant switched to ${label}.`, 'Command Result');
      pushActivity(`Variant switched to ${label}`, 'accent');
      await Promise.all([
        refreshSidebarState(activeSessionId, true),
        refreshOverviewState(activeSessionId, { quiet: true }),
      ]);
      setStatus(`variant ${label}`);
    } catch (error) {
      const message = describeError(error);
      setStatus(message);
      appendLocalSystemMessage(message, 'Command Error');
      pushActivity(message, 'error');
    }
  };

  const choosePlannerModel = async (plannerModel: string | null) => {
    if (!sessionIdRef.current && draftChatRef.current) {
      setDraftChat((current: any) => (
        current
          ? {
              ...current,
              plannerModel,
            }
          : current
      ));
      setActiveCommandPanel(null);
      setStatus(plannerModel ? `draft planner ${plannerModel}` : 'draft planner auto');
      return;
    }
    const activeSessionId = requireActiveDesktopSession();
    if (!activeSessionId) return;
    setStatus(plannerModel ? `switching planner to ${plannerModel}` : 'setting planner to mirror the main model');
    try {
      await configureAgent(apiBaseUrl, token, { planner_model: plannerModel }, activeSessionId);
      setActiveCommandPanel(null);
      appendLocalSystemMessage(
        plannerModel
          ? `Planner model pinned to ${plannerModel}.`
          : 'Planner model set to automatic. It will mirror the main model.',
        'Command Result',
      );
      pushActivity(
        plannerModel
          ? `Planner model pinned to ${plannerModel}`
          : 'Planner model set to automatic',
        'accent',
      );
      await refreshSidebarState(activeSessionId, true);
      setStatus(plannerModel ? `planner ${plannerModel}` : 'planner auto');
    } catch (error) {
      const message = describeError(error);
      setStatus(message);
      appendLocalSystemMessage(message, 'Command Error');
      pushActivity(message, 'error');
    }
  };

  const toggleCurrentSessionToolPack = async (packId: string) => {
    const activeSessionId = sessionIdRef.current;
    if (!activeSessionId && draftChatRef.current) {
      setDraftChat((current: any) => {
        if (!current) {
          return current;
        }
        const nextEnabled = toggleToolPackId(current.enabledToolPacks, packId);
        return {
          ...current,
          enabledToolPacks: nextEnabled,
        };
      });
      setPinnedToolPackInfoId(null);
      setHoveredToolPackInfoId(null);
      setToolPackInfoPopup(null);
      setStatus(`${currentEnabledToolPacks.includes(packId) ? 'disabled' : 'enabled'} ${toolPackLabel(packId)}`);
      return;
    }
    if (!activeSessionId) {
      setStatus('open a chat before changing tool packs');
      return;
    }
    const currentlyEnabled = currentEnabledToolPacks.includes(packId);
    const currentlyAvailable = currentAvailableToolPacks.includes(packId);
    const lockReason = currentlyEnabled
      ? formatToolPackLockReason(currentDisabledPackReasons[packId] || null)
        || (!currentlyAvailable ? unavailableEnabledToolPackReason : null)
      : null;
    if (lockReason) {
      showToolPackInfoPopup(packId, { pinned: true });
      setStatus(shortStatusText(lockReason));
      return;
    }
    const nextEnabled = toggleToolPackId(currentEnabledToolPacks, packId);
    setToolPackMutationInFlight(packId);
    try {
      const detail = await updateSessionToolPacks(apiBaseUrl, token, activeSessionId, {
        enabled_tool_packs: nextEnabled,
      });
      applySessionDetail(detail);
      setPinnedToolPackInfoId(null);
      setHoveredToolPackInfoId(null);
      setToolPackInfoPopup(null);
      await refreshSidebarState(activeSessionId, true);
      setStatus(`${currentlyEnabled ? 'disabled' : 'enabled'} ${toolPackLabel(packId)}`);
    } catch (error) {
      setStatus(userFacingError(error, 'Tools were not updated.'));
    } finally {
      setToolPackMutationInFlight(null);
    }
  };

  const updateChatTelegramBotAssignment = async (targetSessionId: string, telegramBotConfigId: string | null) => {
    setSessionSettingsMutationInFlight(true);
    try {
      const detail = await updateSessionTelegramBotAssignment(apiBaseUrl, token, targetSessionId, {
        telegram_bot_config_id: telegramBotConfigId,
      });
      if (detail.id === sessionIdRef.current) {
        applySessionDetail(detail);
      }
      await refreshSidebarState(sessionIdRef.current, true);
      const nextBot = telegramBotConfigs.find((item: any) => item.id === (telegramBotConfigId || defaultTelegramBotConfigId)) || null;
      setStatus(nextBot ? `chat assigned to ${nextBot.label}` : 'chat bot assignment cleared');
    } catch (error) {
      setStatus(userFacingError(error, 'Chat assignment was not updated.'));
    } finally {
      setSessionSettingsMutationInFlight(false);
    }
  };

  const updateChatHeadlessEligibility = async (targetSessionId: string, headlessEligible: boolean) => {
    setSessionSettingsMutationInFlight(true);
    try {
      const detail = await updateSessionHeadlessEligibility(apiBaseUrl, token, targetSessionId, {
        headless_eligible: headlessEligible,
      });
      if (detail.id === sessionIdRef.current) {
        applySessionDetail(detail);
      }
      await refreshSidebarState(sessionIdRef.current, true);
      setStatus(headlessEligible ? 'chat can be used as a Telegram sleep chat' : 'chat removed from Telegram sleep eligibility');
    } catch (error) {
      setStatus(userFacingError(error, 'Sleep-chat setting was not updated.'));
    } finally {
      setSessionSettingsMutationInFlight(false);
    }
  };

  const updateChatSecurityPermissionMode = async (targetSessionId: string, permissionMode: SecurityPermissionMode) => {
    const currentMode = (
      sessions.find((item: any) => item?.id === targetSessionId)?.security_permission_mode || 'standard'
    ) as SecurityPermissionMode;
    if (currentMode === permissionMode) {
      setStatus(permissionMode === 'full_permissions' ? 'Full access is already enabled for this chat session' : `Permission mode: ${permissionMode}`);
      return;
    }
    const mutationKey = `${targetSessionId}:${permissionMode}`;
    if (desktopSecurityPermissionMutationsInFlight.has(mutationKey)) {
      return;
    }
    desktopSecurityPermissionMutationsInFlight.add(mutationKey);
    setSessionSettingsMutationInFlight(true);
    try {
      let confirmationId: string | null = null;
      if (permissionMode === 'full_permissions') {
        confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirmAction, {
          action_kind: 'session_full_permissions',
          title: 'Enable Full access?',
          message: 'This gives this chat broader computer-control permission. Sensitive actions will still ask before execution.',
          risk_tier: 'access',
          origin_surface: 'desktop',
          origin_chat_id: targetSessionId,
          payload: { session_id: targetSessionId },
        }, {
          confirmLabel: 'Enable Full access',
          tone: 'access',
          details: ['Full access lasts only for this chat session.', 'The app will still block hard safety risks and ask before sensitive actions.'],
        });
        if (!confirmationId) {
          return;
        }
      }
      const detail = await updateSessionSecurityPermissionMode(apiBaseUrl, token, targetSessionId, {
        security_permission_mode: permissionMode,
      }, confirmationId);
      setSessions((previous: any) => previous.map((item: any) => (
        item.id === detail.id
          ? {
              ...item,
              security_permission_mode: detail.security_permission_mode || permissionMode,
              updated_at: detail.updated_at || item.updated_at,
            }
          : item
      )));
      if (detail.id === sessionIdRef.current) {
        applySessionDetail(detail);
      }
      await refreshSidebarState(detail.id || targetSessionId, true);
      setStatus(permissionMode === 'full_permissions' ? 'Full access enabled for this chat session' : `Permission mode: ${permissionMode}`);
    } catch (error) {
      setStatus(userFacingError(error, 'Tools were not updated.'));
    } finally {
      desktopSecurityPermissionMutationsInFlight.delete(mutationKey);
      setSessionSettingsMutationInFlight(false);
    }
  };

  const updateDraftSecurityPermissionMode = async (permissionMode: SecurityPermissionMode) => {
    const currentDraftMode = (pendingDraftSecurityPermissionMode || draftChat?.securityPermissionMode || 'standard') as SecurityPermissionMode;
    if (currentDraftMode === permissionMode) {
      setStatus(permissionMode === 'full_permissions' ? 'draft permission already Full access' : `draft permission: ${permissionMode}`);
      return;
    }
    const mutationKey = `draft:${permissionMode}`;
    if (desktopSecurityPermissionMutationsInFlight.has(mutationKey)) {
      return;
    }
    desktopSecurityPermissionMutationsInFlight.add(mutationKey);
    setSessionSettingsMutationInFlight(true);
    try {
      if (permissionMode === 'full_permissions') {
        const confirmed = await confirmAction({
          title: 'Use Full access for this new chat?',
          message: 'The first message will create a chat with broader computer-control permission. Sensitive actions will still ask before execution.',
          confirmLabel: 'Use Full access',
          cancelLabel: 'Cancel',
          tone: 'access',
          details: ['Full access applies only to the chat created from this draft.', 'The app still blocks hard safety risks.'],
        });
        if (!confirmed) {
          return;
        }
      }
      setPendingDraftSecurityPermissionMode(permissionMode);
      setDraftChat((current: any) => (
        current
          ? {
              ...current,
              securityPermissionMode: permissionMode,
            }
          : current
      ));
      setStatus(permissionMode === 'full_permissions' ? 'draft permission: Full access' : `draft permission: ${permissionMode}`);
    } catch (error) {
      setStatus(userFacingError(error, 'Chat assignment was not updated.'));
    } finally {
      desktopSecurityPermissionMutationsInFlight.delete(mutationKey);
      setSessionSettingsMutationInFlight(false);
    }
  };

  const setSleepChatForBot = async (botConfigId: string, targetSessionId: string | null) => {
    setSessionSettingsMutationInFlight(true);
    try {
      const nextRuntime = await configureHeadlessRuntime(apiBaseUrl, token, {
        default_sleep_session_by_bot: {
          [botConfigId]: targetSessionId,
        },
      });
      setOrchestratorStatus(nextRuntime);
      setStatus(targetSessionId ? 'sleep chat updated' : 'sleep chat cleared');
    } catch (error) {
      setStatus(userFacingError(error, 'Sleep chat was not updated.'));
    } finally {
      setSessionSettingsMutationInFlight(false);
    }
  };

  const sendQueuedComposerSlice = (items: QueuedComposerMessage[], actionPolicy: InterruptPolicy) => {
    if (!items.length) {
      return;
    }
    const sendableItems = items.filter((item: any) => {
      const itemRunMode = String(item.modeOptions?.runMode || '').trim();
      return !(agentRunActive && (itemRunMode === 'plan' || itemRunMode === 'goal'));
    });
    if (!sendableItems.length) {
      setStatus('mode-tagged messages stay queued until the current run finishes');
      return;
    }
    setQueuedComposerMessages((current: any) => current.filter((entry: any) => !sendableItems.some((item: any) => item.id === entry.id)));
    sendableItems.forEach((item: any) => {
      queueMessage(item.text, item.sourceFormat, item.sessionId, actionPolicy, item.modeOptions);
    });
    setStatus(actionPolicy === 'after_tool' ? 'queued steering for the next safe tool boundary' : 'steering current run');
  };

  const sendTextValue = async (textValue: string, options?: ComposerModeOptions) => {
    const trimmed = textValue.trim();
    if (!trimmed) return;

    if (isDesktopSlashCommand(trimmed)) {
      setComposerInputValue('');
      setAssistantDraft('');
      setThinking('');
      setLastAssistantOutputAt(null);
      if (openCommandPanelForInput(trimmed)) {
        return;
      }
      await runSlashCommandFromComposer(trimmed);
      return;
    }

    if (blockMissingProviderApiKey()) {
      return;
    }

    const rawInput = textValue;
    const selectedRunMode = options?.runMode || pendingRunMode || null;
    const modeOptions: ComposerModeOptions | undefined = selectedRunMode || options?.planAction || options?.planAnswer
      ? {
          runMode: selectedRunMode || 'normal',
          planAction: options?.planAction || null,
          planAnswer: options?.planAnswer || null,
        }
      : undefined;
    const runWasActive = agentRunActive;
    setComposerInputValue('');
    setPendingRunMode?.(null);
    setAssistantDraft('');
    setThinking('Thinking');
    setLastAssistantOutputAt(null);
    setVoiceDraft('');
    setChatRunActive(true);
    setRuntimeRunState('running');
    setStatus(draftChatRef.current || !sessionIdRef.current ? 'preparing chat' : 'sending message');

    if (runWasActive && draftChatRef.current) {
      setPendingSessionSwitch({
        mode: 'draft_send',
        projectPath: draftChatRef.current.projectPath,
        text: trimmed,
        sourceFormat: 'app_text',
        modeOptions,
      });
      setThinking('');
      setStatus('Current run is still active. Stop it before creating and sending to the new chat.');
      return;
    }

    let targetSessionId: string | null = null;
    try {
      targetSessionId = await ensureSessionForOutgoingMessage();
    } catch (error) {
      setComposerInputValue(rawInput, { syncVoiceBase: false, origin: 'manual' });
      setChatRunActive(false);
      setRuntimeRunState('idle');
      setThinking('');
      setStatus(userFacingError(error, 'Chat was not prepared.'));
      return;
    }
    if (!targetSessionId) {
      setComposerInputValue(rawInput, { syncVoiceBase: false, origin: 'manual' });
      setChatRunActive(false);
      setRuntimeRunState('idle');
      setThinking('');
      setStatus('choose or create a folder to start a new chat');
      return;
    }

    if (runWasActive) {
      if (selectedRunMode === 'plan' || selectedRunMode === 'goal' || interruptPolicy === 'none') {
        queueComposerMessage(trimmed, 'app_text', targetSessionId, modeOptions);
      } else {
        queueMessage(trimmed, 'app_text', targetSessionId, interruptPolicy, modeOptions);
      }
      return;
    }

    queueMessage(trimmed, 'app_text', targetSessionId, undefined, modeOptions);
  };

  const sendText = async () => {
    await sendTextValue(input);
  };

  const approveProposedPlan = async (planText: string) => {
    const trimmedPlan = String(planText || '').trim();
    if (!trimmedPlan) {
      return;
    }
    await sendTextValue(`PLEASE IMPLEMENT THIS PLAN:\n${trimmedPlan}`, {
      runMode: 'normal',
      planAction: 'approve',
    });
  };

  const answerPlanQuestion = async (
    questionId: string,
    answerText: string,
    optionId?: string | null,
  ) => {
    const trimmedAnswer = String(answerText || '').trim();
    const trimmedQuestionId = String(questionId || '').trim();
    if (!trimmedQuestionId || !trimmedAnswer) {
      return;
    }
    await sendTextValue(trimmedAnswer, {
      runMode: 'plan',
      planAction: 'answer_question',
      planAnswer: {
        question_id: trimmedQuestionId,
        option_id: optionId || null,
        freeform_text: optionId ? null : trimmedAnswer,
      },
    });
  };

  const updateModeState = async (action: 'exit_plan' | 'dismiss_plan' | 'clear_goal', reason?: string) => {
    const activeSessionId = sessionIdRef.current;
    if (!activeSessionId) {
      setStatus('missing session');
      return;
    }
    try {
      const detail = await updateSessionModeState(apiBaseUrl, token, activeSessionId, { action, reason });
      applySessionDetail(detail);
      setStatus(action === 'clear_goal' ? 'goal cleared' : 'plan mode closed');
    } catch (error) {
      setStatus(userFacingError(error, 'Mode state was not updated.'));
    }
  };

  const dismissPlanMode = async () => {
    await updateModeState('dismiss_plan', 'Dismissed from desktop composer');
  };

  const exitPlanMode = async () => {
    await updateModeState('exit_plan', 'Exited from desktop composer');
  };

  const clearActiveGoal = async () => {
    await updateModeState('clear_goal', 'Cleared by user');
  };

  const uploadComposerAttachments = async (files: File[]) => {
    if (!files.length || attachmentUploadInFlight) {
      return;
    }
    if (!apiBaseUrl || !token) {
      setStatus('local API is not ready for uploads');
      return;
    }

    let targetSessionId: string | null = null;
    try {
      targetSessionId = await ensureSessionForOutgoingMessage();
    } catch (error) {
      setStatus(userFacingError(error, 'Chat was not prepared.'));
      return;
    }
    if (!targetSessionId) {
      setStatus('choose or create a folder before attaching a file');
      return;
    }

    setAttachmentUploadInFlight(true);
    setStatus(files.length === 1 ? `attaching ${files[0].name || 'file'}` : `attaching ${files.length} files`);
    try {
      const uploadedNames: string[] = [];
      let effectiveSessionId = targetSessionId;
      for (const file of files) {
        const result = await uploadAppAttachment(apiBaseUrl, token, file, {
          filename: file.name || 'upload',
          sessionId: effectiveSessionId,
        });
        effectiveSessionId = result.session_id || effectiveSessionId;
        uploadedNames.push(result.filename || file.name || 'upload');
      }
      if (effectiveSessionId) {
        await refreshSidebarState(effectiveSessionId, true);
        await refreshArtifacts(effectiveSessionId);
      }
      const label = uploadedNames.length === 1
        ? uploadedNames[0]
        : `${uploadedNames.length} files`;
      appendLocalSystemMessage(`Attached ${label}.`, 'Attachment');
      setStatus(`attached ${label}`);
    } catch (error) {
      setStatus(userFacingError(error, 'Attachment was not added.'));
    } finally {
      setAttachmentUploadInFlight(false);
    }
  };

  const openComposerAttachmentPicker = () => {
    setActiveCommandPanel(null);
    if (Platform.OS !== 'web' || typeof document === 'undefined' || !document.body) {
      setStatus('file picker is not available in this renderer');
      return;
    }
    if (attachmentUploadInFlight) {
      setStatus('attachment upload already in progress');
      return;
    }

    const inputElement = document.createElement('input');
    inputElement.type = 'file';
    inputElement.multiple = true;
    inputElement.accept = '';
    inputElement.style.position = 'fixed';
    inputElement.style.left = '-10000px';
    inputElement.style.top = '-10000px';
    inputElement.style.opacity = '0';

    const cleanup = () => {
      inputElement.onchange = null;
      inputElement.remove();
    };
    inputElement.onchange = () => {
      const selectedFiles = Array.from(inputElement.files || []);
      cleanup();
      if (!selectedFiles.length) {
        return;
      }
      void uploadComposerAttachments(selectedFiles);
    };
    document.body.appendChild(inputElement);
    inputElement.click();
  };

  const selectCommandSuggestion = async (command: string) => {
    setComposerInputValue('');
    setAssistantDraft('');
    setThinking('');
    setLastAssistantOutputAt(null);
    setDismissedCommandSuggestionInput(null);
    if (openCommandPanelForInput(command)) {
      return;
    }
    await runSlashCommandFromComposer(command);
  };

  const handleComposerKeyPress = (event: any) => {
    const nativeEvent = event.nativeEvent || {};
    if (nativeEvent.key !== 'Enter' || nativeEvent.shiftKey) {
      return;
    }

    event.preventDefault?.();
    void sendText();
  };

  useEffect(() => {
    if (!apiBaseUrl || !token) return;
    if (!sessionId) {
      startupChatSocketReadyRef.current = true;
      setSocketState('idle');
      maybeResolveStartupReady();
      return;
    }

    const selectedChatSessionId = normalizeChatSessionId(sessionId);
    const selectedSocket = ensureChatSocketForSession(selectedChatSessionId, { selected: true });

    return () => {
      if (chatWsRef.current === selectedSocket) {
        chatWsRef.current = null;
      }
      if (
        selectedChatSessionId
        && !hasPendingMessagesForSession(selectedChatSessionId)
        && !chatSocketRunActiveBySessionRef.current[selectedChatSessionId]
      ) {
        closeSessionChatSocket(selectedChatSessionId);
      }
    };
  }, [apiBaseUrl, sessionId, token]);

  useEffect(() => () => {
    for (const targetSessionId of Object.keys(chatSocketReconnectTimersRef.current)) {
      clearChatSocketReconnectTimer(targetSessionId);
    }
    for (const targetSessionId of Object.keys(chatSocketsBySessionRef.current)) {
      closeSessionChatSocket(targetSessionId);
    }
  }, []);

  useEffect(() => {
    if (!isJarvisMode) {
      deactivateVoiceRuntime('idle');
      return;
    }
    if (!apiBaseUrl || !token) {
      deactivateVoiceRuntime('unavailable');
      return;
    }
    if (!sessionId) {
      deactivateVoiceRuntime('idle');
      return;
    }

    let disposed = false;
    let reconnectAttempt = 0;
    const connect = () => {
      if (disposed) return;
      const wsBase = buildWsBaseUrl(apiBaseUrl);
      if (!wsBase) {
        setVoiceState('unavailable');
        return;
      }

      const params = new URLSearchParams({
        token,
        client_id: appClientIdRef.current,
      });
      if (sessionIdRef.current) {
        params.set('session_id', sessionIdRef.current);
      }

      setVoiceState('connecting');
      const ws = new WebSocket(`${wsBase}/ws/app/voice?${params.toString()}`);
      voiceWsRef.current = ws;
      const isStaleVoiceSocket = () => sessionIdRef.current !== sessionId;

      ws.onopen = () => {
        if (disposed || isStaleVoiceSocket()) return;
        reconnectAttempt = 0;
        if (alwaysOnEnabledRef.current && voiceStreamRef.current) {
          setVoiceState('always_on');
          setStatus(`always-on voice listening for "${currentJarvisWakePhrase}"`);
        } else {
          setVoiceState('ready');
        }
        setVoiceError(null);
        logDiagnostic('desktop.voice.ws', 'connected', { sessionId: sessionIdRef.current || null });
      };

      ws.onmessage = (messageEvent: any) => {
        if (disposed || isStaleVoiceSocket()) return;
        try {
          const event = parseDesktopRealtimeEvent(String(messageEvent.data || '{}'));
          if (!realtimeEventMatchesSession(event, sessionId)) {
            pushActivity('A voice event for another chat was ignored.', 'warn');
            return;
          }
          handleRealtimeEvent(event, 'voice');
        } catch (error) {
          const message = describeError(error);
          pushActivity(`Voice websocket parse failed: ${message}`, 'warn');
          logDiagnostic('desktop.voice.ws', 'message parse failed', message, 'warn');
        }
      };

      ws.onclose = (closeEvent) => {
        if (voiceWsRef.current === ws) {
          voiceWsRef.current = null;
        }
        if (!disposed && !isStaleVoiceSocket()) {
          const reconnectable = shouldReconnectChatSocket(closeEvent.code);
          const preserveAlwaysOnCapture = (
            reconnectable
            && voiceCaptureModeRef.current === 'always_on'
            && alwaysOnEnabledRef.current
            && Boolean(voiceStreamRef.current)
          );
          voicePressActiveRef.current = false;
          voiceRunningRef.current = false;
          voiceRecordingRef.current = false;
          setVoiceRunning(false);
          setVoiceRecording(false);
          resetVoiceCaptureBuffers();
          if (!preserveAlwaysOnCapture) {
            alwaysOnEnabledRef.current = false;
            setAlwaysOnEnabled(false);
            stopVoiceTracks();
          }
          if (!reconnectable) {
            setVoiceState('authentication required');
            setVoiceError('Voice connection authorization expired. Reopen or sign in again.');
            setStatus('Voice connection authorization expired. Reopen or sign in again.');
            return;
          }
          setVoiceState('reconnecting');
          const delayMs = chatReconnectDelayMs(reconnectAttempt, SOCKET_RECONNECT_MS);
          reconnectAttempt += 1;
          voiceReconnectRef.current = setTimeout(connect, delayMs);
        }
      };

      ws.onerror = () => {
        if (disposed || isStaleVoiceSocket()) {
          return;
        }
        setVoiceState('error');
        setVoiceError('voice socket error');
        logDiagnostic('desktop.voice.ws', 'voice socket error', { sessionId: sessionIdRef.current || null }, 'warn');
        try {
          ws.close();
        } catch {
          // The close handler owns capture cleanup and reconnect state.
        }
      };
    };

    connect();

    return () => {
      disposed = true;
      deactivateVoiceRuntime('idle');
    };
  }, [apiBaseUrl, isJarvisMode, sessionId, selectedVoiceEngine, token]);

  const ensureSessionForVoiceCapture = async () => {
    if (agentRunActive && draftChatRef.current) {
      setStatus('Stop the current task before starting voice in a new chat.');
      return null;
    }
    let targetSessionId: string | null = null;
    try {
      targetSessionId = await ensureSessionForOutgoingMessage();
    } catch (error) {
      setStatus(userFacingError(error, 'Chat was not prepared.'));
      return null;
    }
    if (!targetSessionId) {
      setStatus('choose or create a folder to start a voice chat');
      return null;
    }
    sessionIdRef.current = targetSessionId;
    return targetSessionId;
  };

  const waitForVoiceSocketOpen = async (timeoutMs = 4000) => {
    if (!isJarvisMode) {
      return false;
    }
    if (voiceWsRef.current?.readyState === WebSocket.OPEN) {
      return true;
    }
    const startedAt = Date.now();
    setStatus('connecting voice socket');
    while (Date.now() - startedAt < timeoutMs) {
      await new Promise((resolve: any) => setTimeout(resolve, 100));
      if (voiceWsRef.current?.readyState === WebSocket.OPEN) {
        return true;
      }
    }
    return false;
  };

  const startVoiceCapture = async () => {
    if (!isJarvisMode) {
      voicePressActiveRef.current = false;
      return;
    }
    if (voiceStartInFlightRef.current) {
      voicePressActiveRef.current = false;
      return;
    }
    if (!apiBaseUrl || !token) {
      voicePressActiveRef.current = false;
      setVoiceState('unavailable');
      setStatus('voice unavailable');
      return;
    }
    if (!await ensureJarvisVoiceInputReady()) {
      return;
    }
    if (voiceEngineChanging || (!apiVoiceInputActive && selectedVoiceEngineState === 'warming')) {
      voicePressActiveRef.current = false;
      setStatus('Local voice path is still warming up');
      return;
    }
    if (alwaysOnEnabledRef.current) {
      setStatus('always-on voice is already active');
      return;
    }
    if (voiceRecording) {
      return;
    }
    if (voiceRunning) {
      voicePressActiveRef.current = false;
      setStatus('voice still processing');
      return;
    }
    if (!globalThis.navigator?.mediaDevices?.getUserMedia) {
      voicePressActiveRef.current = false;
      setVoiceState('error');
      setVoiceError('Microphone capture is not available in this desktop renderer.');
      return;
    }
    voiceStartInFlightRef.current = true;
    const targetSessionId = await ensureSessionForVoiceCapture();
    if (!targetSessionId) {
      voiceStartInFlightRef.current = false;
      voicePressActiveRef.current = false;
      return;
    }
    if (!await waitForVoiceSocketOpen()) {
      voiceStartInFlightRef.current = false;
      voicePressActiveRef.current = false;
      setStatus('voice socket is still connecting');
      return;
    }

    try {
      voicePressActiveRef.current = true;
      voiceCaptureModeRef.current = 'push_to_talk';
      setVoiceMode('push_to_talk');
      await cleanupAssistantAudio();
      const stream = await globalThis.navigator.mediaDevices.getUserMedia({ audio: true });
      if (!voicePressActiveRef.current) {
        for (const track of stream.getTracks()) {
          track.stop();
        }
        return;
      }
      voiceStreamRef.current = stream;
      const context = createAudioContext();
      voiceAudioContextRef.current = context;
      if (context.state === 'suspended') {
        await context.resume();
      }
      voiceSampleRateRef.current = context.sampleRate;
      const source = context.createMediaStreamSource(stream);
      voiceAudioSourceRef.current = source;
      voiceCaptureNodeRef.current = await createDesktopAudioCapture(context, source, processVoiceSamples);
      if (!voicePressActiveRef.current) {
        stopVoiceTracks();
        return;
      }
      if (!beginVoiceSegment('push_to_talk')) {
        stopVoiceTracks();
      }
    } catch (error) {
      stopVoiceTracks();
      voicePressActiveRef.current = false;
      voiceRecordingRef.current = false;
      voiceRunningRef.current = false;
      setVoiceRecording(false);
      setVoiceRunning(false);
      setVoiceState('error');
      const message = userFacingError(error, 'Voice did not start.');
      setVoiceError(message);
      setStatus(message);
      logDiagnostic('desktop.voice.ws', 'voice start failed', describeError(error), 'error');
    } finally {
      voiceStartInFlightRef.current = false;
    }
  };

  const stopVoiceCapture = async (commit: boolean) => {
    voicePressActiveRef.current = false;
    stopVoiceTracks();
    await finishVoiceSegment(commit, 'push_to_talk');
  };

  const startAlwaysOnVoice = async () => {
    if (!isJarvisMode) {
      return;
    }
    if (!jarvisWakeProfileReady) {
      setJarvisWakeEnrollmentOpen?.(true);
      setStatus('Train a local wake phrase before using Jarvis always-on listening');
      return;
    }
    if (voiceStartInFlightRef.current) {
      return;
    }
    if (!apiBaseUrl || !token) {
      setVoiceState('unavailable');
      setStatus('voice unavailable');
      return;
    }
    if (!await ensureJarvisVoiceInputReady()) {
      return;
    }
    if (voiceEngineChanging || (!apiVoiceInputActive && selectedVoiceEngineState === 'warming')) {
      setStatus('Local voice path is still warming up');
      return;
    }
    if (!globalThis.navigator?.mediaDevices?.getUserMedia) {
      setVoiceState('error');
      setVoiceError('Microphone capture is not available in this desktop renderer.');
      return;
    }
    if (alwaysOnEnabledRef.current) {
      return;
    }
    voiceStartInFlightRef.current = true;
    const targetSessionId = await ensureSessionForVoiceCapture();
    if (!targetSessionId) {
      voiceStartInFlightRef.current = false;
      return;
    }
    if (!await waitForVoiceSocketOpen()) {
      voiceStartInFlightRef.current = false;
      setStatus('voice socket is still connecting');
      return;
    }

    try {
      await cleanupAssistantAudio();
      voiceCaptureModeRef.current = 'always_on';
      alwaysOnEnabledRef.current = true;
      setVoiceMode('always_on');
      setAlwaysOnEnabled(true);
      setVoiceDraft('');
      setVoiceError(null);
      voiceRunningRef.current = false;
      voiceRecordingRef.current = false;
      setVoiceRunning(false);
      setVoiceRecording(false);
      setVoiceState('always_on');
      setStatus(`always-on voice listening for "${currentJarvisWakePhrase}"`);
      voiceGateStateRef.current = createVoiceGateState();
      jarvisWakeMatchStateRef.current = createJarvisWakeMatchState();
      deferredAlwaysOnFramesRef.current = [];
      deferredAlwaysOnSampleCountRef.current = 0;
      activeVoiceUtteranceIdRef.current = null;
      const stream = await globalThis.navigator.mediaDevices.getUserMedia({ audio: true });
      if (!alwaysOnEnabledRef.current) {
        for (const track of stream.getTracks()) {
          track.stop();
        }
        return;
      }
      voiceStreamRef.current = stream;
      const context = createAudioContext();
      voiceAudioContextRef.current = context;
      if (context.state === 'suspended') {
        await context.resume();
      }
      voiceSampleRateRef.current = context.sampleRate;
      const source = context.createMediaStreamSource(stream);
      voiceAudioSourceRef.current = source;
      voiceCaptureNodeRef.current = await createDesktopAudioCapture(context, source, processVoiceSamples);
      if (!alwaysOnEnabledRef.current) {
        stopVoiceTracks();
        return;
      }
      pushActivity(apiVoiceInputActive ? 'Always-on API voice mode enabled.' : 'Always-on local Whisper voice mode enabled.', 'accent');
    } catch (error) {
      alwaysOnEnabledRef.current = false;
      setAlwaysOnEnabled(false);
      stopVoiceTracks();
      voiceRecordingRef.current = false;
      voiceRunningRef.current = false;
      setVoiceRecording(false);
      setVoiceRunning(false);
      setVoiceState('error');
      const message = userFacingError(error, 'Always-on voice did not start.');
      setVoiceError(message);
      setStatus(message);
      logDiagnostic('desktop.voice.ws', 'always-on voice start failed', describeError(error), 'error');
    } finally {
      voiceStartInFlightRef.current = false;
    }
  };

  const stopAlwaysOnVoice = async () => {
    alwaysOnEnabledRef.current = false;
    setAlwaysOnEnabled(false);
    const wasRecording = voiceGateStateRef.current.recording || voiceRecording;
    voiceGateStateRef.current = createVoiceGateState();
    jarvisWakeMatchStateRef.current = createJarvisWakeMatchState();
    deferredAlwaysOnFramesRef.current = [];
    deferredAlwaysOnSampleCountRef.current = 0;
    activeVoiceUtteranceIdRef.current = null;
    activeVoiceBargeInCandidateRef.current = false;
    activeVoiceBargeInReferenceTextRef.current = '';
    jarvisBargeInCandidateUtteranceIdsRef.current.clear();
    stopVoiceTracks();
    if (wasRecording) {
      await finishVoiceSegment(false, 'always_on');
    } else {
      voiceRecordingRef.current = false;
      voiceRunningRef.current = false;
      setVoiceRecording(false);
      setVoiceRunning(false);
      setVoiceState('ready');
      setStatus('always-on voice stopped');
    }
  };

  const pauseJarvisMicrophone = async () => {
    alwaysOnEnabledRef.current = false;
    setAlwaysOnEnabled(false);
    const wasRecording = voiceGateStateRef.current.recording || voiceRecordingRef.current;
    voiceGateStateRef.current = createVoiceGateState();
    jarvisWakeMatchStateRef.current = createJarvisWakeMatchState();
    deferredAlwaysOnFramesRef.current = [];
    deferredAlwaysOnSampleCountRef.current = 0;
    activeVoiceUtteranceIdRef.current = null;
    activeVoiceBargeInCandidateRef.current = false;
    activeVoiceBargeInReferenceTextRef.current = '';
    jarvisBargeInCandidateUtteranceIdsRef.current.clear();
    stopVoiceTracks();
    if (wasRecording) {
      await finishVoiceSegment(false, 'always_on');
      return;
    }
    setVoiceRecording(false);
    voiceRecordingRef.current = false;
    setStatus('Jarvis microphone muted');
  };

  const toggleJarvisMute = () => {
    if (!isJarvisMode) {
      return;
    }
    if (jarvisHoldToTalkMode) {
      jarvisPushToTalkActiveRef.current = false;
      if (voiceRecordingRef.current || voicePressActiveRef.current) {
        void stopVoiceCapture(true);
      }
      setJarvisMuted(true);
      setVoiceMode('push_to_talk');
      setStatus('Push To Talk is armed; hold the core to speak');
      return;
    }
    if (jarvisMuted || !alwaysOnEnabledRef.current) {
      setJarvisMuted(false);
      setVoiceMode('always_on');
      if (!voiceRunningRef.current && !voiceRecordingRef.current) {
        void startAlwaysOnVoice();
      } else {
        setStatus('Jarvis microphone will resume after the current response');
      }
      return;
    }
    setJarvisMuted(true);
    void pauseJarvisMicrophone();
  };

  const setJarvisPushToTalkMode = async (enabled: boolean) => {
    if (!isJarvisMode || voiceStartInFlightRef.current) {
      return;
    }
    if (enabled === jarvisHoldToTalkMode) {
      return;
    }
    if (!enabled) {
      if (voiceRecordingRef.current || voicePressActiveRef.current) {
        await stopVoiceCapture(true);
      }
      jarvisPushToTalkActiveRef.current = false;
      setJarvisHoldToTalkMode(false);
      setVoiceMode('always_on');
      setJarvisMuted(false);
      if (!voiceRunningRef.current && !voiceRecordingRef.current) {
        void startAlwaysOnVoice();
      } else {
        setStatus('Jarvis microphone will resume after the current response');
      }
      return;
    }
    setJarvisHoldToTalkMode(true);
    setJarvisMuted(true);
    setVoiceMode('push_to_talk');
    if (alwaysOnEnabledRef.current) {
      await stopAlwaysOnVoice();
    }
    setStatus('Push To Talk enabled. Hold the core or Space to speak.');
  };

  const startJarvisPushToTalk = async () => {
    if (!isJarvisMode || voiceStartInFlightRef.current) {
      return;
    }
    if (!jarvisHoldToTalkMode) {
      setStatus('Enable Hold To Talk mode first');
      return;
    }
    jarvisPushToTalkActiveRef.current = true;
    if (voiceRecordingRef.current) {
      return;
    }
    if (voiceRunningRef.current) {
      jarvisPushToTalkActiveRef.current = false;
      return;
    }
    if (alwaysOnEnabledRef.current) {
      await stopAlwaysOnVoice();
    }
    setVoiceMode('push_to_talk');
    try {
      await startVoiceCapture();
      if (!jarvisPushToTalkActiveRef.current && (voiceRecordingRef.current || voicePressActiveRef.current)) {
        await stopVoiceCapture(true);
      }
    } catch {
      jarvisPushToTalkActiveRef.current = false;
    }
  };

  const stopJarvisPushToTalk = async () => {
    if (voiceRecordingRef.current || voicePressActiveRef.current) {
      await stopVoiceCapture(true);
    }
    jarvisPushToTalkActiveRef.current = false;
    if (jarvisHoldToTalkMode) {
      setJarvisMuted(true);
      setVoiceMode('push_to_talk');
    }
  };

  const cancelAlwaysOnSegment = async () => {
    voiceGateStateRef.current = createVoiceGateState();
    jarvisWakeMatchStateRef.current = createJarvisWakeMatchState();
    deferredAlwaysOnFramesRef.current = [];
    deferredAlwaysOnSampleCountRef.current = 0;
    activeVoiceUtteranceIdRef.current = null;
    activeVoiceBargeInCandidateRef.current = false;
    activeVoiceBargeInReferenceTextRef.current = '';
    await finishVoiceSegment(false, 'always_on');
  };
  const retryFailedTurn = (failure: Record<string, any>, providerId: string, modelId: string) => {
    const targetSessionId = normalizeChatSessionId(sessionIdRef.current);
    const runId = String(failure?.run_id || '').trim();
    if (!targetSessionId || !runId || !providerId || !modelId) {
      setStatus('Choose an available provider and model before retrying.');
      return;
    }
    const socket = ensureChatSocketForSession(targetSessionId, { selected: true });
    if (!socket) {
      setStatus('Chat connection is unavailable. Reconnect before retrying.');
      return;
    }
    const sendRetry = () => {
      socket.send(JSON.stringify({
        type: 'retry_failed_turn',
        session_id: targetSessionId,
        run_id: runId,
        provider_id: providerId,
        model_id: modelId,
        source_client_id: appClientIdRef.current,
      }));
      chatSocketRunActiveBySessionRef.current[targetSessionId] = true;
      scope.setProviderFailure?.(null);
      setChatRunActive(true);
      setRuntimeRunState('running');
      setThinking('Retrying');
      setStatus(`Retrying with ${modelId}`);
    };
    if (socket.readyState === WebSocket.OPEN) {
      sendRetry();
    } else {
      socket.addEventListener('open', sendRetry, { once: true });
    }
  };
  scope.retryFailedTurn = retryFailedTurn;
  useEffect(() => {
    if (
      isJarvisMode
      && !jarvisHoldToTalkMode
      && !jarvisMuted
      && jarvisWakeProfileReady
      && apiBaseUrl
      && token
      && !alwaysOnEnabledRef.current
    ) {
      void startAlwaysOnVoice();
    }
    return () => {
      if (alwaysOnEnabledRef.current) {
        void stopAlwaysOnVoice();
      }
    };
  }, [apiBaseUrl, isJarvisMode, jarvisHoldToTalkMode, jarvisMuted, jarvisWakeProfileReady, token]);
  return { flushPendingMessages, queueMessage, queueComposerMessage, setComposerInputValue, handleComposerContentSizeChange, handleComposerMeasureLayout, handleComposerInputChange, appendLocalMessage, appendLocalSystemMessage, requireActiveDesktopSession, stopVoiceTracks, resetVoiceCaptureBuffers, cleanupAssistantAudio, playAssistantAudio, sendVoiceChunk, flushVoiceChunk, appendVoiceChunkSamples, beginVoiceSegment, shouldAutoSendAlwaysOnVoice, finishVoiceSegment, rememberDeferredAlwaysOnFrame, processAlwaysOnFrame, drainDeferredAlwaysOnFrames, processVoiceSamples, acceptJarvisBargeInTranscript, clearJarvisBargeInCandidate, handleRealtimeEvent, executeSlashCommand, runSlashCommandFromComposer, runVerboseCommand, openCommandPanelForInput, chooseModel, chooseVariant, choosePlannerModel, toggleCurrentSessionToolPack, updateChatTelegramBotAssignment, updateChatHeadlessEligibility, updateChatSecurityPermissionMode, updateDraftSecurityPermissionMode, setSleepChatForBot, sendQueuedComposerSlice, sendTextValue, sendText, approveProposedPlan, answerPlanQuestion, dismissPlanMode, exitPlanMode, clearActiveGoal, uploadComposerAttachments, openComposerAttachmentPicker, selectCommandSuggestion, handleComposerKeyPress, ensureSessionForVoiceCapture, waitForVoiceSocketOpen, startVoiceCapture, stopVoiceCapture, startAlwaysOnVoice, stopAlwaysOnVoice, pauseJarvisMicrophone, toggleJarvisMute, setJarvisPushToTalkMode, startJarvisPushToTalk, stopJarvisPushToTalk, cancelAlwaysOnSegment };
}
