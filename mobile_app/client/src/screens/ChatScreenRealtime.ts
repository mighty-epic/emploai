import { logDiagnostic, shortStatusText } from '../../lib/diagnostics';
import { mergeLiveMessage, toChatMessage } from '@/screens/chatMessages';
import {
  formatLogLine,
  formatRealtimeToolEntry,
  formatTimelineLogEntry,
  isUserVisibleRuntimeMessage,
  isUserVisibleTimelineEvent,
  mergeTimelineEvents,
  realtimeLogEventToTimelineEvent,
  realtimeToolEventToTimelineEvent,
  type ChatEvent,
} from '@/screens/chatTimeline';
import type { FleetSnapshot, SessionMessage, SessionTimelineEvent } from '@/lib/appApi';

type ChatRealtimeContext = Record<string, any>;

export function handleChatRealtimeEvent(context: ChatRealtimeContext, data: ChatEvent, channel: 'chat' | 'voice' | 'screen') {
  const {
    router,
    params,
    requestedSessionId,
    requestedNewSession,
    requestedWorkspace,
    sessionId,
    setSessionId,
    sessionName,
    setSessionName,
    input,
    setInput,
    messages,
    setMessages,
    sessions,
    setSessions,
    fleetSnapshot,
    setFleetSnapshot,
    jobs,
    setJobs,
    sidebarState,
    setSidebarState,
    toolLogs,
    setToolLogs,
    timelineEvents,
    setTimelineEvents,
    status,
    setStatus,
    voiceState,
    setVoiceState,
    voiceDraft,
    setVoiceDraft,
    isRecording,
    setIsRecording,
    isVoiceBusy,
    setIsVoiceBusy,
    screenPreview,
    setScreenPreview,
    screenStatus,
    setScreenStatus,
    screenLiveState,
    setScreenLiveState,
    isScreenLive,
    setIsScreenLive,
    steeringBetaEnabled,
    setSteeringBetaEnabled,
    interruptPolicy,
    setInterruptPolicy,
    apiBaseUrl,
    setApiBaseUrl,
    token,
    setToken,
    connectionMode,
    setConnectionMode,
    pairedDesktopId,
    setPairedDesktopId,
    configLoaded,
    setConfigLoaded,
    drawerOpen,
    setDrawerOpen,
    drawerTab,
    setDrawerTab,
    cronUnreadCount,
    setCronUnreadCount,
    pairPromptOpen,
    setPairPromptOpen,
    workspacePanelOpen,
    setWorkspacePanelOpen,
    composerMenu,
    setComposerMenu,
    draftModel,
    setDraftModel,
    draftVariant,
    setDraftVariant,
    draftPlanner,
    setDraftPlanner,
    draftEnabledToolPacks,
    setDraftEnabledToolPacks,
    draftSecurityPermissionMode,
    setDraftSecurityPermissionMode,
    draftSessionWorkspace,
    setDraftSessionWorkspace,
    telegramBots,
    setTelegramBots,
    verboseMode,
    setVerboseMode,
    agentOverview,
    setAgentOverview,
    skills,
    setSkills,
    skillValidation,
    setSkillValidation,
    memoryQuery,
    setMemoryQuery,
    memoryNote,
    setMemoryNote,
    memoryResults,
    setMemoryResults,
    configKey,
    setConfigKey,
    configValue,
    setConfigValue,
    configEntries,
    setConfigEntries,
    workspaceDraft,
    setWorkspaceDraft,
    heartbeatDraft,
    setHeartbeatDraft,
    subAgentPrompt,
    setSubAgentPrompt,
    subAgents,
    setSubAgents,
    artifacts,
    setArtifacts,
    artifactDetail,
    setArtifactDetail,
    artifactStatus,
    setArtifactStatus,
    confirm,
    confirmationDialog,
    chatWsRef,
    voiceWsRef,
    screenWsRef,
    appClientIdRef,
    composerInputRef,
    recordingRef,
    assistantSoundRef,
    assistantAudioPathRef,
    pendingMessagesRef,
    outboundRetryRef,
    segmentTimeoutRef,
    chatReconnectRef,
    voiceReconnectRef,
    screenReconnectRef,
    segmentSequenceRef,
    voiceActiveRef,
    finishingSegmentRef,
    sessionIdRef,
    blankChatRequestedRef,
    steeringArmed,
    canStartVoice,
    mobileVoiceEnabled,
    chatConnected,
    chatBlocked,
    setupMissing,
    hasActiveChatSession,
    agentControlsDisabled,
    subAgentSpawnDisabled,
    activeSessionSummary,
    activeSecurityPermissionMode,
    activeSecurityPermissionLabel,
    showChatError,
    runtimeStatusText,
    missingConnectionStatus,
    requireChatConnection,
    ensureChatActiveSession,
    refreshArtifacts,
    openArtifact,
    applySessionDetail,
    updateChatSecurityPermissionMode,
    clearVisibleSession,
    syncOverviewFromSessionDetail,
    applySessionSync,
    refreshSidebarData,
    refreshAgentControls,
    applyQuickAgentConfig,
    runWorkspaceAction,
    resetCurrentContext,
    focusComposer,
    toggleSkill,
    runSkillValidation,
    spawnBackgroundTask,
    runTaskControl,
    persistSidebarState,
    selectSession,
    deleteConversation,
    activeFleetIdentity,
    activeFleetIdentityId,
    visibleSessions,
    activeFleetIdentitySelectedChatId,
    activeFleetIdentityTargetChatId,
    currentSessionSummary,
    selectFleetIdentityFromChat,
    currentEnabledToolPacks,
    currentAvailableToolPacks,
    lockReasons,
    effectiveEnabledToolPacks,
    currentModelLabel,
    currentVariantLabel,
    toggleChatToolPack,
    openBlankChat,
    ensureSessionForSend,
    appendLog,
    appendSystemMessage,
    appendAssistantDelta,
    applyAssistantFinal,
    appendUserMessage,
    canSendOverChatSocket,
    closeFailedChatSocket,
    schedulePendingFlush,
    expirePendingMessages,
    flushPendingMessages,
    queuePendingMessage,
    cleanupAssistantAudio,
    audioExtensionForMime,
    playAssistantAudio,
    clearReconnectTimers,
    applyScreenPayload,
  } = context;
    const eventSessionId = data.session_id || '';
    const activeSessionId = sessionIdRef.current || '';
    const transcriptEventTypes = new Set([
      'assistant_delta',
      'assistant_final',
      'user_message',
      'thinking',
      'tool_event',
      'timeline_event',
      'log',
      'status',
      'warning',
      'error',
      'artifact_created',
    ]);
    if (
      channel !== 'screen'
      && eventSessionId
      && activeSessionId
      && eventSessionId !== activeSessionId
      && transcriptEventTypes.has(data.type)
    ) {
      void refreshSidebarData();
      return;
    }

    if (
      blankChatRequestedRef.current
      && !activeSessionId
      && eventSessionId
      && (data.type === 'session_snapshot' || data.type === 'session_sync')
    ) {
      void refreshSidebarData();
      return;
    }

    if (data.type === 'session_snapshot' && data.session_id && (!activeSessionId || data.session_id === activeSessionId)) {
      sessionIdRef.current = data.session_id;
      setSessionId(data.session_id);
    }

    if (channel === 'screen') {
      if (data.type === 'screen_frame') {
        applyScreenPayload(data.payload);
        setScreenStatus('live');
        return;
      }

      if (data.type === 'screen_state') {
        const nextState = String(data.payload?.state || 'idle');
        setScreenLiveState(nextState);
        setScreenStatus(`live ${nextState}`);
        return;
      }
    }

    if (data.type.startsWith('fleet_')) {
      const nextSnapshot = data.payload?.snapshot as FleetSnapshot | undefined;
      if (nextSnapshot && Array.isArray(nextSnapshot.workers)) {
        setFleetSnapshot(nextSnapshot);
      }
      void refreshSidebarData();
      return;
    }

    if (data.type === 'assistant_delta') {
      appendAssistantDelta(String(data.payload?.delta || ''));
      return;
    }

    if (data.type === 'user_message') {
      const message = data.payload?.message as (SessionMessage & { pending?: boolean }) | undefined;
      if (message) {
        setMessages((prev: any) => mergeLiveMessage(prev, {
          ...toChatMessage(message),
          localSessionId: data.session_id || sessionIdRef.current || null,
          pendingLocal: Boolean(message.pending),
        }));
      }
      return;
    }

    if (data.type === 'session_sync') {
      applySessionSync(data.payload);
      if (channel !== 'screen') {
        setStatus('connected');
      }
      return;
    }

    if (data.type === 'assistant_final') {
      const message = data.payload?.message as SessionMessage | undefined;
      if (message) {
        setMessages((prev: any) => mergeLiveMessage(prev, {
          ...toChatMessage(message),
          localSessionId: data.session_id || sessionIdRef.current || null,
          ephemeralLocal: true,
        }));
      } else {
        applyAssistantFinal(String(data.payload?.text || ''));
      }
      if (channel !== 'voice') {
        setIsVoiceBusy(false);
      }
      void refreshSidebarData();
      return;
    }

    if (data.type === 'artifact_created') {
      const created = data.payload?.artifacts;
      if (Array.isArray(created) && created.length) {
        appendLog(`[artifact] ${created.length} new artifact${created.length === 1 ? '' : 's'}`);
      }
      void refreshArtifacts(data.session_id || sessionIdRef.current);
      void refreshSidebarData();
      return;
    }

    if (data.type === 'thinking') {
      const formatted = String(data.payload?.formatted || data.payload?.text || '').trim();
      const raw = String(data.payload?.text || '').trim();
      if (formatted) {
        appendSystemMessage(formatted, 'Thinking');
      }
      if (raw) {
        appendLog(`[thinking] ${raw}`);
      }
      return;
    }

    if (data.type === 'assistant_audio') {
      const audioBase64 = String(data.payload?.audio_base64 || '');
      const mimeType = String(data.payload?.mime_type || 'audio/mpeg');
      void playAssistantAudio(audioBase64, mimeType);
      return;
    }

    if (data.type === 'tool_event') {
      const entry = formatRealtimeToolEntry(data.payload);
      appendLog(entry);
      const event = realtimeToolEventToTimelineEvent(data.payload, data.session_id || sessionIdRef.current);
      if (event) {
        setTimelineEvents((previous: any) => mergeTimelineEvents(previous, [event]));
      }
      logDiagnostic(
        `${channel}.tool`,
        'tool event',
        data.payload,
        data.payload?.level === 'error' ? 'error' : 'info'
      );
      return;
    }

    if (data.type === 'timeline_event') {
      const event = data.payload?.event as SessionTimelineEvent | undefined;
      if (!isUserVisibleTimelineEvent(event)) {
        return;
      }
      const entry = event ? formatTimelineLogEntry(event) : '';
      appendLog(entry);
      if (event) {
        setTimelineEvents((previous: any) => mergeTimelineEvents(previous, [event]));
      }
      return;
    }

    if (data.type === 'warning') {
      const message = String(data.payload?.message || data.message || 'warning');
      const detail = String(data.payload?.detail || '').trim();
      const visibleMessage = runtimeStatusText(message, channel === 'screen' ? 'Screen needs attention.' : 'Run needs attention.');
      if (channel === 'screen') {
        setScreenStatus(visibleMessage);
        setScreenLiveState('warning');
        appendLog(`[screen] ${visibleMessage}`);
        if (detail) appendLog(`[screen] ${detail}`);
      } else {
        setStatus(visibleMessage);
        if (channel === 'voice') {
          setIsVoiceBusy(false);
        }
        appendLog(`[warn] ${visibleMessage}`);
        if (detail) appendLog(detail);
      }
      logDiagnostic(`${channel}.runtime`, 'warning event', data.payload || data, 'warn');
      return;
    }

    if (data.type === 'error') {
      const message = String(data.payload?.message || data.message || 'error');
      const detail = String(data.payload?.detail || '').trim();
      const visibleMessage = runtimeStatusText(message || detail, channel === 'voice' ? 'Voice needs attention.' : channel === 'screen' ? 'Screen needs attention.' : 'Run needs attention.');
      if (channel === 'screen') {
        setScreenStatus(visibleMessage);
        setScreenLiveState('error');
        appendLog(`[screen] ${visibleMessage}`);
        if (detail) appendLog(`[screen] ${detail}`);
      } else {
        setStatus(visibleMessage);
        if (channel === 'voice') {
          setVoiceState('error');
          setIsVoiceBusy(false);
        }
        appendLog(`[error] ${visibleMessage}`);
        if (detail) appendLog(detail);
        appendSystemMessage(visibleMessage, 'Error');
      }
      logDiagnostic(`${channel}.runtime`, 'error event', data.payload || data, 'error');
      return;
    }

    if (data.type === 'status' || data.type === 'log') {
      const message = String(data.payload?.message || data.message || '');
      if (message && !isUserVisibleRuntimeMessage(message)) {
        return;
      }
      const level = typeof data.payload?.level === 'string' ? data.payload.level : undefined;
      const formatted = message ? formatLogLine(message, level) : '';
      if (formatted) appendLog(formatted);
      const event = realtimeLogEventToTimelineEvent(data, data.session_id || sessionIdRef.current);
      if (event) {
        setTimelineEvents((previous: any) => mergeTimelineEvents(previous, [event]));
      }
      if (data.type === 'status') {
        if (channel === 'screen') {
          setScreenStatus(shortStatusText(message || screenStatus));
        } else {
          setStatus(shortStatusText(message || status));
        }
      }
      if (message) {
        logDiagnostic(
          `${channel}.runtime`,
          `${data.type} event`,
          data.payload || data,
          level === 'error' ? 'error' : level === 'warn' ? 'warn' : 'info'
        );
      }
      return;
    }

    if (channel === 'voice') {
      if (data.type === 'voice_state') {
        const nextState = String(data.payload?.state || 'idle');
        setVoiceState(nextState);
        if (nextState === 'idle' || nextState === 'cancelled') {
          setIsVoiceBusy(false);
        }
        if (nextState !== 'listening') {
          setStatus(`voice ${nextState}`);
        }
        return;
      }

      if (data.type === 'voice_partial') {
        setVoiceDraft(String(data.payload?.text || ''));
        return;
      }

      if (data.type === 'voice_final') {
        const transcript = String(data.payload?.text || '');
        setVoiceDraft(transcript);
        appendUserMessage(transcript, data.session_id || sessionIdRef.current || null);
        setVoiceState('processing');
        void refreshSidebarData();
      }
    }
}
