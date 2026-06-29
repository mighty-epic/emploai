import type { DesktopConversationScope } from './DesktopConversationScope';
import { useEffect } from 'react'; type NativeSyntheticEvent<T = any> = any; type ActiveCommandPanel = any; type ActivityItem = any; type AgentOverview = any; type ArtifactDetail = any; type ArtifactSummary = any; type ComposerInputOrigin = any; type ConversationSurfaceMode = any; type DesktopFleetEnrollment = any; type DesktopFleetIdentity = any; type DesktopFleetSnapshot = any; type DesktopFleetTask = any; type DesktopFleetWorker = any; type DesktopGitRepoState = any; type DesktopMessage = any; type DesktopPathStatus = any; type DesktopRuntimeStatus = any; type DesktopSidebarProjectActivity = any; type DesktopSidebarState = any; type DesktopVoicePackState = any; type DesktopVoiceRuntimeStatus = any; type InterruptPolicy = any; type JarvisSttBackend = any; type JarvisTtsBackend = any; type LayoutChangeEvent = any; type MessageSourceFormat = any; type ModelProviderGroup = any; type NativeScrollEvent = any; type PendingSearchJump = any; type QueuedComposerMessage = any; type QueuedMessage = any; type RealtimeChannel = any; type RealtimeEvent = any; type ReferenceEntry = any; type RuntimeOrchestratorStatus = any; type ScheduledJob = any; type SearchResultTarget = any; type SecurityPermissionMode = any; type SessionDetail = any; type SessionMessage = any; type SessionSearchResult = any; type SessionSummary = any; type SessionTimelineEvent = any; type SidebarChatTooltipState = any; type SidebarDragState = any; type SidebarDraftChat = any; type SidebarProjectGroup = any; type StartupReadinessState = any; type TaskBoard = any; type TelegramBotConfig = any; type TextInputContentSizeChangeEventData = any; type ToolPackInfoPopupState = any; type VoiceCaptureMode = any; type VoiceGateState = any;

const desktopSecurityPermissionMutationsInFlight = new Set<string>();

export function useDesktopConversationVoiceControls(scope: DesktopConversationScope) {
  const { ALWAYS_ON_VOICE_AUTO_SEND, COMPOSER_MAX_HEIGHT, COMPOSER_MIN_HEIGHT, DESKTOP_COMMAND_SUGGESTIONS, DESKTOP_NO_ACTIVE_SESSION_STATUS, JARVIS_BARGE_IN_MIN_VOICED_MS, Platform, SOCKET_RECONNECT_MS, VOICE_DEFERRED_FRAME_MAX_MS, VOICE_ENGINE_NONE, VOICE_GATE_ATTACK_MS, VOICE_GATE_FRAME_MS, VOICE_GATE_MIN_MS, VOICE_PROCESSOR_BUFFER_SIZE, activeCommandPanel, activeJarvisBargeInGateDbfs, activePermissionInfoId, activeVoiceBargeInCandidateRef, activeVoiceBargeInReferenceTextRef, activeVoiceGateDbfs, activeVoiceGateMaxMs, activeVoiceGatePrerollMs, activeVoiceGateReleaseMs, activeVoiceSegmentMs, activeVoiceUtteranceIdRef, activity, agentRunActive, allowedWorkspaceRoot, alwaysOnEnabled, alwaysOnEnabledRef, apiBaseUrl, apiVoiceInputActive, appClientIdRef, appendSessionTimelineEvent, appendTimelineEvent, appendVoiceTranscriptSegment, applySessionDetail, applySessionSync, artifactDetailLoading, artifactError, artifacts, artifactsLoading, assignFleetGroupTask, assignFleetTask, assistantAudioRef, assistantAudioTextRef, assistantDeltaBufferRef, assistantDeltaFlushTimerRef, assistantDraft, attachmentUploadInFlight, buildWsBaseUrl, bytesToBase64, chatRunActive, chatRunActiveRef, chatWsRef, clearAssistantDeltaFlushTimer, clearSidebarChatTooltipTimer, clearSidebarSearch, clearToolPackInfoHideTimer, clearTranscriptAutoScrollResumeTimer, closeSidebarSearchModal, commandSuggestionMenuRef, completedTaskBoards, composerInputHeight, composerTextRegionRef, concatFloat32, configureAgent, configureHeadlessRuntime, configuredHebrewVoiceGateDbfs, configuredJarvisBargeInGateDbfs, configuredModelGroups, configuredVoiceGateDbfs, confirmAction, confirmationDialog, contextUsageHovered, continueFleetQueue, conversationMode, conversationModeRef, copyFleetEnrollmentToken, createApprovedConfirmation, createAudioContext, createClientId, createFleetEnrollment, createFleetGroupFromFirstWorker, createFleetLocalWorker, createLocalToolTimelineEvent, createVoiceGateState, currentAvailableToolPacks, currentDisabledPackReasons, currentEnabledToolPacks, currentJarvisSttBackend, currentJarvisSttLabel, currentJarvisTtsBackend, currentJarvisTtsLabel, currentWorkspaceBySessionRef, defaultTelegramBotConfigId, deferredAlwaysOnFramesRef, deferredAlwaysOnSampleCountRef, deleteFleetGroup, describeError, discardDraftChat, dismissedCommandSuggestionInput, draftBranchSearch, draftBranchTriggerRef, draftChat, draftChatRef, draftGitRepoLoading, draftGitRepoState, draftProjectSearch, draftProjectTriggerRef, draftTelegramTriggerRef, dragState, drainingDeferredAlwaysOnFramesRef, emitStartupState, encodePcm16Wav, ensureSessionForOutgoingMessage, envFilePath, expandedCompletedTaskIds, expandedModelProviders, expandedPlannerProviders, externalSidebarToggleSignalRef, fleetChatPanelCollapsed, fleetChatPanelWidth, fleetDashboardCollapsed, fleetEnrollment, fleetError, fleetGroupNameDraft, fleetGroupTaskDrafts, fleetLoading, fleetPanelOpen, fleetRenameDrafts, fleetSnapshot, fleetStatus, fleetTaskBatchStatusMessage, fleetTaskDrafts, fleetTaskStatusMessage, fleetWorkerNameDraft, floatingPanelRef, flushAssistantDeltaBuffer, folderChoiceBusy, folderChoiceOpen, folderChoiceResolveRef, formatToolPackLockReason, handleDesktopConversationRealtimeEvent, handleJarvisSttBackendSelection, handleJarvisTtsBackendSelection, handleTranscriptScroll, hideSidebarChatTooltip, hideToolPackInfoPopup, hideVoicePanel, highlightedMessageIndex, historyMessageLayoutRef, historyScrollRef, hoveredProjectPath, hoveredSessionId, hoveredToolPackInfoId, input, interruptPolicy, isBlockedFleetTask, isDesktopSlashCommand, isJarvisMode, isMeaningfulJarvisBargeInText, jarvisBargeInCandidateUtteranceIdsRef, jarvisHoldToTalkMode, jarvisLatestSpokenText, jarvisLatestTranscript, jarvisMuted, jarvisPulseProgress, jarvisPushToTalkActiveRef, jarvisSpaceHotkeyActiveRef, jarvisStatusDrawerOpen, jarvisVoiceSettingsOpen, jarvisWarmRequestedRef, jobs, keepRuntimeOnAppClose, lastAssistantOutputAt, lastComposerInputOriginRef, lastMessage, lastMessageSignature, lastVoiceWarmRequestEngineRef, liveVoiceStatus, logDiagnostic, maybeResolveStartupReady, mergeLocalMessages, mergeTimelineEventState, messages, modelTriggerRef, normalizeCompletedTaskBoards, openFleetWorkerMenuId, openProjectMenuPath, openSessionMenuId, openSidebarSearchModal, openVoicePanel, orchestratorStatus, overview, overviewRefreshInFlightRef, parseComposerSlashCommand, pendingDraftSecurityPermissionMode, pendingMessagesRef, pendingSearchJump, pendingSessionSwitch, permissionsTriggerRef, pinnedToolPackInfoId, projectMenuRefs, projectMenuTriggerRefs, projectPathStatuses, pushActivity, pushProjectActivity, queuedComposerMessages, reconcileSidebarProjects, reconnectRef, referenceAutoOpenKeyRef, referenceDismissedKeyRef, refreshFleetSnapshot, refreshOverviewState, refreshSidebarCollections, refreshSidebarState, refreshVoiceRuntimeState, renameFleetWorker, requestFleetPreview, resetFleetWorker, resetFleetWorkerIdentity, resetTranscriptAutoScrollState, resolveTaskBoardState, revealProjectInSidebar, rightSidebarWidth, router, runDesktopSlashCommand, runtimeRunState, samplesDbfs, savingCloseBehavior, scheduleHideToolPackInfoPopup, scheduleSidebarChatTooltip, scheduleTranscriptAutoScrollResume, scrollRef, scrollTranscriptToEnd, searchHighlightTimerRef, searchJumpTimerRef, selectFleetIdentity, selectProjectPath, selectedArtifactDetail, selectedArtifactId, selectedVoiceEngine, selectedVoiceEngineState, sessionId, sessionIdRef, sessionMenuRefs, sessionMenuTriggerRefs, sessionName, sessionRowRefs, sessionSettingsMutationInFlight, sessions, setActiveCommandPanel, setActivePermissionInfoId, setActivity, setAlwaysOnEnabled, setArtifactDetailLoading, setArtifactError, setArtifacts, setArtifactsLoading, setAssistantDraft, setAttachmentUploadInFlight, setCachedModelGroups, setCachedPlannerModels, setChatRunActive, setCompletedTaskBoards, setComposerInputHeight, setContextUsageHovered, setConversationMode, setDismissedCommandSuggestionInput, setDraftBranchSearch, setDraftChat, setDraftGitRepoLoading, setDraftGitRepoState, setDraftProjectSearch, setDragState, setExpandedCompletedTaskIds, setExpandedModelProviders, setExpandedPlannerProviders, setFleetChatPanelCollapsed, setFleetChatPanelWidth, setFleetDashboardCollapsed, setFleetEnrollment, setFleetError, setFleetGroupNameDraft, setFleetGroupTaskDrafts, setFleetLoading, setFleetPanelOpen, setFleetRenameDrafts, setFleetSnapshot, setFleetStatus, setFleetTaskDrafts, setFleetWorkerNameDraft, setFolderChoiceBusy, setFolderChoiceOpen, setHighlightedMessageIndex, setHoveredProjectPath, setHoveredSessionId, setHoveredToolPackInfoId, setInput, setInterruptPolicy, setJarvisHoldToTalkMode, setJarvisLatestSpokenText, setJarvisLatestTranscript, setJarvisMuted, setJarvisStatusDrawerOpen, setJarvisVoiceSettingsOpen, setJobs, setKeepRuntimeOnAppClose, setLastAssistantOutputAt, setLiveVoiceStatus, setMessages, setOpenFleetWorkerMenuId, setOpenProjectMenuPath, setOpenSessionMenuId, setOrchestratorStatus, setOverview, setPendingDraftSecurityPermissionMode, setPendingSearchJump, setPendingSessionSwitch, setPinnedToolPackInfoId, setProjectMenuRef, setProjectMenuTriggerRef, setProjectPathStatuses, setQueuedComposerMessages, setRightSidebarWidth, setRuntimeRunState, setSavingCloseBehavior, setSelectedArtifactDetail, setSelectedArtifactId, setSessionId, setSessionMenuRef, setSessionMenuTriggerRef, setSessionName, setSessionRowRef, setSessionSettingsMutationInFlight, setSessions, setShowArtifactRail, setShowReferenceRail, setShowVoicePanel, setSidebarChatTooltip, setSidebarExpanded, setSidebarSearch, setSidebarSearchError, setSidebarSearchLoading, setSidebarSearchModalOpen, setSidebarSearchResults, setSidebarState, setSidebarStateReady, setSocketState, setStatus, setSttBackendChanging, setTaskBoard, setTaskBoardArmedNextTurnState, setTaskBoardCollapsed, setTelegramBotConfigs, setThinking, setTimelineEvents, setToolPackInfoButtonRef, setToolPackInfoPopup, setToolPackMutationInFlight, setTtsBackendChanging, setVoiceDraft, setVoiceEngineChanging, setVoiceError, setVoiceMode, setVoicePanelHidden, setVoiceRecording, setVoiceRunning, setVoiceState, shellRef, shortStatusText, showArtifactRail, showReferenceRail, showSidebarChatTooltip, showToolPackInfoPopup, showVoicePanel, sidebarChatTooltip, sidebarChatTooltipTimerRef, sidebarCollectionsRefreshInFlightRef, sidebarExpanded, sidebarSearch, sidebarSearchError, sidebarSearchInputRef, sidebarSearchLauncherRef, sidebarSearchLoading, sidebarSearchModalOpen, sidebarSearchModalRef, sidebarSearchRequestIdRef, sidebarSearchResults, sidebarState, sidebarStateReady, socketState, startupChatSocketReadyRef, startupSessionStateReadyRef, startupSidebarReadyRef, startupTerminalStateRef, status, stopAllFleetWorkers, stopFleetWorker, sttBackendChanging, summarizeToolPayload, takeGateFrame, taskBoard, taskBoardArmedNextTurn, taskBoardCollapsed, taskBoardStateRef, telegramBotConfigs, thinking, thinkingShineProgress, timelineEvents, toLiveDesktopMessage, toggleToolPackId, token, toolPackInfoButtonRefs, toolPackInfoHideTimerRef, toolPackInfoPopup, toolPackLabel, toolPackMutationInFlight, toolsTriggerRef, transcriptAutoScrollResumeTimerRef, transcriptAutoScrollSuspendedRef, transcriptContentHeightRef, transcriptLastScrollOffsetYRef, transcriptLastSignatureRef, transcriptMessageLayoutRef, transcriptPendingAutoScrollRef, transcriptProgrammaticScrollUntilRef, transcriptSignature, transcriptViewportHeightRef, ttsBackendChanging, unavailableEnabledToolPackReason, updateSessionHeadlessEligibility, updateSessionSecurityPermissionMode, updateSessionTelegramBotAssignment, updateSessionToolPacks, updateSidebarState, uploadAppAttachment, useEffect, userFacingError, usingHebrewVoiceEngine, voiceAudioContextRef, voiceAudioSourceRef, voiceCaptureModeRef, voiceChunkChainRef, voiceChunkSampleCountRef, voiceChunkSamplesRef, voiceChunkSequenceRef, voiceComposerBaseInputRef, voiceComposerDraftRef, voiceDraft, voiceEngineChanging, voiceError, voiceGateStateRef, voiceMode, voicePanelHidden, voicePressActiveRef, voiceProcessorRef, voiceReconnectRef, voiceRecording, voiceRecordingRef, voiceRunning, voiceRunningRef, voiceSampleRateRef, voiceStartInFlightRef, voiceState, voiceStreamRef, voiceWsRef, warmSelectedVoicePath } = scope;
  const refreshArtifacts = (...args: any[]) => scope.refreshArtifacts?.(...args);
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
const flushPendingMessages = () => {
    const ws = chatWsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return;
    }

    while (pendingMessagesRef.current.length && ws.readyState === WebSocket.OPEN) {
      const next = pendingMessagesRef.current.shift();
      if (!next) break;
      ws.send(JSON.stringify({
        text: next.text,
        session_id: next.sessionId,
        interrupt_policy: next.interruptPolicy,
        source_format: next.sourceFormat,
      }));
    }
  };

  const queueMessage = (
    text: string,
    sourceFormat: MessageSourceFormat,
    explicitSessionId?: string,
    policyOverride?: InterruptPolicy,
  ) => {
    const activeSessionId = explicitSessionId || sessionIdRef.current;
    if (!activeSessionId) {
      setStatus('missing session');
      return;
    }
    if (blockMissingProviderApiKey()) {
      return;
    }

    setMessages((previous: any) => [
      ...previous,
      {
        role: 'user',
        content: text,
        timestamp: new Date().toISOString(),
        displayLabel: sourceFormat === 'app_voice_transcript' ? 'Voice' : 'You',
        channel: 'app',
        sourceFormat,
        messageKey: `pending:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
        pending: true,
        localSessionId: activeSessionId,
        sourceClientId: appClientIdRef.current,
      },
    ]);

    pendingMessagesRef.current.push({
      text,
      sourceFormat,
      interruptPolicy: policyOverride ?? interruptPolicy,
      sessionId: activeSessionId,
    });
    setChatRunActive(true);
    setRuntimeRunState('running');
    setLastAssistantOutputAt(null);

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

    const ws = chatWsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      flushPendingMessages();
      setStatus(sourceFormat === 'app_voice_transcript' ? 'sending voice transcript' : 'sending message');
    } else {
      setStatus('chat reconnecting · message queued');
    }
  };

  const queueComposerMessage = (text: string, sourceFormat: MessageSourceFormat, explicitSessionId?: string) => {
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
    const processor = voiceProcessorRef.current;
    voiceProcessorRef.current = null;
    if (processor) {
      processor.onaudioprocess = null;
      try {
        processor.disconnect();
      } catch {
        // no-op
      }
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
      await audio.play();
    } catch (error) {
      if (assistantAudioRef.current === audio) {
        assistantAudioRef.current = null;
        assistantAudioTextRef.current = '';
      }
      pushActivity('Assistant audio did not play.', 'warn');
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
    ws.send(JSON.stringify({
      type: 'voice_start',
      session_id: sessionIdRef.current,
      surface_mode: conversationModeRef.current,
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
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: commit ? 'voice_commit' : 'voice_cancel',
        session_id: sessionIdRef.current,
        surface_mode: conversationModeRef.current,
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
    const attackFrames = Math.max(1, Math.ceil(VOICE_GATE_ATTACK_MS / VOICE_GATE_FRAME_MS));
    const releaseFrames = Math.max(1, Math.ceil(activeVoiceGateReleaseMs / VOICE_GATE_FRAME_MS));
    const prerollFrames = Math.max(1, Math.ceil(activeVoiceGatePrerollMs / VOICE_GATE_FRAME_MS));
    const minFrames = Math.max(1, Math.ceil(VOICE_GATE_MIN_MS / VOICE_GATE_FRAME_MS));
    const bargeInMinFrames = Math.max(minFrames, Math.ceil(JARVIS_BARGE_IN_MIN_VOICED_MS / VOICE_GATE_FRAME_MS));
    const maxFrames = Math.max(minFrames, Math.ceil(activeVoiceGateMaxMs / VOICE_GATE_FRAME_MS));

    if (!gate.recording) {
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
      if (gate.aboveFrames < attackFrames) {
        return;
      }

      if (!beginVoiceSegment('always_on', {
        preserveAssistantAudio: assistantAudioActive,
        bargeInCandidate: assistantAudioActive,
      })) {
        voiceGateStateRef.current = createVoiceGateState();
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
    if (!isMeaningfulJarvisBargeInText(text)) {
      return false;
    }
    jarvisBargeInCandidateUtteranceIdsRef.current.delete(normalizedTurnId);
    if (assistantAudioRef.current) {
      void cleanupAssistantAudio();
      setStatus('Jarvis interruption accepted');
      pushActivity(`Jarvis heard you while speaking: ${text}`, 'accent');
    }
    return true;
  };

  const clearJarvisBargeInCandidate = (turnId: string) => {
    const normalizedTurnId = String(turnId || '').trim();
    if (normalizedTurnId) {
      jarvisBargeInCandidateUtteranceIdsRef.current.delete(normalizedTurnId);
    }
  };

  const handleRealtimeEvent = (event: RealtimeEvent, channel: RealtimeChannel) => handleDesktopConversationRealtimeEvent(scope, event, channel);
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
      await refreshSidebarState(activeSessionId, true);
      setStatus(`model ${model}`);
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
    setStatus(plannerModel ? `switching planner to ${plannerModel}` : 'restoring automatic planner selection');
    try {
      await configureAgent(apiBaseUrl, token, { planner_model: plannerModel }, activeSessionId);
      setActiveCommandPanel(null);
      appendLocalSystemMessage(
        plannerModel
          ? `Planner model pinned to ${plannerModel}.`
          : 'Planner model reset to automatic cheapest supported selection.',
        'Command Result',
      );
      pushActivity(
        plannerModel
          ? `Planner model pinned to ${plannerModel}`
          : 'Planner model reset to automatic selection',
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
    setQueuedComposerMessages((current: any) => current.filter((entry: any) => !items.some((item: any) => item.id === entry.id)));
    items.forEach((item: any) => {
      queueMessage(item.text, item.sourceFormat, item.sessionId, actionPolicy);
    });
    setStatus(actionPolicy === 'after_tool' ? 'queued steering for the next safe tool boundary' : 'steering current run');
  };

  const sendText = async () => {
    const trimmed = input.trim();
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

    const rawInput = input;
    const runWasActive = agentRunActive;
    setComposerInputValue('');
    setAssistantDraft('');
    setThinking('Thinking');
    setLastAssistantOutputAt(null);
    setVoiceDraft('');
    setChatRunActive(true);
    setRuntimeRunState('running');
    setStatus(draftChatRef.current || !sessionIdRef.current ? 'preparing chat' : 'sending message');

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
      if (interruptPolicy === 'none') {
        queueComposerMessage(trimmed, 'app_text', targetSessionId);
      } else {
        queueMessage(trimmed, 'app_text', targetSessionId, interruptPolicy);
      }
      return;
    }

    queueMessage(trimmed, 'app_text', targetSessionId);
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

    let disposed = false;

    const connect = () => {
      if (disposed) return;
      const wsBase = buildWsBaseUrl(apiBaseUrl);
      if (!wsBase) {
        setSocketState('Connect backend first.');
        return;
      }

      const params = new URLSearchParams({
        token,
        client_id: appClientIdRef.current,
      });
      if (sessionIdRef.current) {
        params.set('session_id', sessionIdRef.current);
      }

      setSocketState('connecting');
      emitStartupState('warming', 'Connecting chat');
      const ws = new WebSocket(`${wsBase}/ws/app/chat?${params.toString()}`);
      chatWsRef.current = ws;

      ws.onopen = () => {
        if (disposed) return;
        setSocketState('connected');
        startupChatSocketReadyRef.current = true;
        flushPendingMessages();
        maybeResolveStartupReady();
      };

      ws.onmessage = (messageEvent: any) => {
        if (disposed) return;
        try {
          handleRealtimeEvent(JSON.parse(String(messageEvent.data || '{}')) as RealtimeEvent, 'chat');
        } catch (error) {
          pushActivity('Realtime event was skipped.', 'warn');
        }
      };

      ws.onclose = () => {
        if (chatWsRef.current === ws) {
          chatWsRef.current = null;
        }
        if (!disposed) {
          startupChatSocketReadyRef.current = false;
          setSocketState('reconnecting');
          reconnectRef.current = setTimeout(connect, SOCKET_RECONNECT_MS);
        }
      };

      ws.onerror = () => {
        startupChatSocketReadyRef.current = false;
        setSocketState('error');
      };
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
        reconnectRef.current = null;
      }
      if (chatWsRef.current) {
        chatWsRef.current.close();
        chatWsRef.current = null;
      }
    };
  }, [apiBaseUrl, sessionId, token]);

  useEffect(() => {
    if (!apiBaseUrl || !token) {
      setVoiceState('unavailable');
      setVoiceRunning(false);
      return;
    }
    if (!sessionId) {
      setVoiceState('idle');
      setVoiceRunning(false);
      return;
    }

    let disposed = false;
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
        setVoiceState('ready');
        setVoiceError(null);
        logDiagnostic('desktop.voice.ws', 'connected', { sessionId: sessionIdRef.current || null });
      };

      ws.onmessage = (messageEvent: any) => {
        if (disposed || isStaleVoiceSocket()) return;
        try {
          handleRealtimeEvent(JSON.parse(String(messageEvent.data || '{}')) as RealtimeEvent, 'voice');
        } catch (error) {
          const message = describeError(error);
          pushActivity(`Voice websocket parse failed: ${message}`, 'warn');
          logDiagnostic('desktop.voice.ws', 'message parse failed', message, 'warn');
        }
      };

      ws.onclose = () => {
        if (voiceWsRef.current === ws) {
          voiceWsRef.current = null;
        }
        if (!disposed && !isStaleVoiceSocket()) {
          voicePressActiveRef.current = false;
          alwaysOnEnabledRef.current = false;
          setAlwaysOnEnabled(false);
          stopVoiceTracks();
          voiceRunningRef.current = false;
          voiceRecordingRef.current = false;
          setVoiceRunning(false);
          setVoiceRecording(false);
          setVoiceState('reconnecting');
          voiceReconnectRef.current = setTimeout(connect, SOCKET_RECONNECT_MS);
        }
      };

      ws.onerror = () => {
        if (disposed || isStaleVoiceSocket()) {
          return;
        }
        voicePressActiveRef.current = false;
        alwaysOnEnabledRef.current = false;
        setAlwaysOnEnabled(false);
        stopVoiceTracks();
        voiceRunningRef.current = false;
        voiceRecordingRef.current = false;
        setVoiceRunning(false);
        setVoiceRecording(false);
        setVoiceState('error');
        setVoiceError('voice socket error');
      };
    };

    connect();

    return () => {
      disposed = true;
      if (voiceReconnectRef.current) {
        clearTimeout(voiceReconnectRef.current);
        voiceReconnectRef.current = null;
      }
      if (voiceWsRef.current) {
        voiceWsRef.current.close();
        voiceWsRef.current = null;
      }
      alwaysOnEnabledRef.current = false;
      setAlwaysOnEnabled(false);
      stopVoiceTracks();
      resetVoiceCaptureBuffers();
      voiceRunningRef.current = false;
      voiceRecordingRef.current = false;
      void cleanupAssistantAudio();
    };
  }, [apiBaseUrl, sessionId, selectedVoiceEngine, token]);

  const ensureSessionForVoiceCapture = async () => {
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
    if ((!apiVoiceInputActive && selectedVoiceEngine === VOICE_ENGINE_NONE) || liveVoiceStatus?.input_ok === false) {
      voicePressActiveRef.current = false;
      setStatus(liveVoiceStatus?.issues?.[0] || 'Select an English or Hebrew voice path first.');
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
      const processor = context.createScriptProcessor(VOICE_PROCESSOR_BUFFER_SIZE, 1, 1);
      voiceAudioSourceRef.current = source;
      voiceProcessorRef.current = processor;
      processor.onaudioprocess = (event: any) => {
        const input = event.inputBuffer.getChannelData(0);
        processVoiceSamples(new Float32Array(input));
      };
      source.connect(processor);
      processor.connect(context.destination);
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
    if (voiceStartInFlightRef.current) {
      return;
    }
    if (!apiBaseUrl || !token) {
      setVoiceState('unavailable');
      setStatus('voice unavailable');
      return;
    }
    if ((!apiVoiceInputActive && selectedVoiceEngine === VOICE_ENGINE_NONE) || liveVoiceStatus?.input_ok === false) {
      setStatus(liveVoiceStatus?.issues?.[0] || 'Select an English or Hebrew voice path first.');
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
      setStatus('always-on voice listening');
      voiceGateStateRef.current = createVoiceGateState();
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
      const processor = context.createScriptProcessor(VOICE_PROCESSOR_BUFFER_SIZE, 1, 1);
      voiceAudioSourceRef.current = source;
      voiceProcessorRef.current = processor;
      processor.onaudioprocess = (event: any) => {
        const input = event.inputBuffer.getChannelData(0);
        processVoiceSamples(new Float32Array(input));
      };
      source.connect(processor);
      processor.connect(context.destination);
      pushActivity(apiVoiceInputActive ? 'Always-on realtime voice mode enabled.' : 'Always-on local Whisper voice mode enabled.', 'accent');
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
    if (jarvisHoldToTalkMode || jarvisMuted || !alwaysOnEnabledRef.current) {
      setJarvisHoldToTalkMode(false);
      jarvisPushToTalkActiveRef.current = false;
      if (jarvisHoldToTalkMode && (voiceRecordingRef.current || voicePressActiveRef.current)) {
        void stopVoiceCapture(true);
      }
      setVoiceMode('always_on');
      setJarvisMuted(false);
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
    setStatus('Push To Talk enabled');
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
    deferredAlwaysOnFramesRef.current = [];
    deferredAlwaysOnSampleCountRef.current = 0;
    activeVoiceUtteranceIdRef.current = null;
    activeVoiceBargeInCandidateRef.current = false;
    activeVoiceBargeInReferenceTextRef.current = '';
    await finishVoiceSegment(false, 'always_on');
  };
  return { flushPendingMessages, queueMessage, queueComposerMessage, setComposerInputValue, handleComposerContentSizeChange, handleComposerMeasureLayout, handleComposerInputChange, appendLocalMessage, appendLocalSystemMessage, requireActiveDesktopSession, stopVoiceTracks, resetVoiceCaptureBuffers, cleanupAssistantAudio, playAssistantAudio, sendVoiceChunk, flushVoiceChunk, appendVoiceChunkSamples, beginVoiceSegment, shouldAutoSendAlwaysOnVoice, finishVoiceSegment, rememberDeferredAlwaysOnFrame, processAlwaysOnFrame, drainDeferredAlwaysOnFrames, processVoiceSamples, acceptJarvisBargeInTranscript, clearJarvisBargeInCandidate, handleRealtimeEvent, executeSlashCommand, runSlashCommandFromComposer, runVerboseCommand, openCommandPanelForInput, chooseModel, choosePlannerModel, toggleCurrentSessionToolPack, updateChatTelegramBotAssignment, updateChatHeadlessEligibility, updateChatSecurityPermissionMode, updateDraftSecurityPermissionMode, setSleepChatForBot, sendQueuedComposerSlice, sendText, uploadComposerAttachments, openComposerAttachmentPicker, selectCommandSuggestion, handleComposerKeyPress, ensureSessionForVoiceCapture, waitForVoiceSocketOpen, startVoiceCapture, stopVoiceCapture, startAlwaysOnVoice, stopAlwaysOnVoice, pauseJarvisMicrophone, toggleJarvisMute, setJarvisPushToTalkMode, startJarvisPushToTalk, stopJarvisPushToTalk, cancelAlwaysOnSegment };
}
