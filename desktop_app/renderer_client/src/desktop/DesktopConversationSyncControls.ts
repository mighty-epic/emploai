import type { DesktopConversationScope } from './DesktopConversationScope';
import { createLatestRequestGate } from './desktopAsyncCoordination';
import { useRef } from 'react';
import { useEffect } from 'react'; type NativeSyntheticEvent<T = any> = any; type ActiveCommandPanel = any; type ActivityItem = any; type AgentOverview = any; type ArtifactDetail = any; type ArtifactSummary = any; type ComposerInputOrigin = any; type ConversationSurfaceMode = any; type DesktopFleetEnrollment = any; type DesktopFleetIdentity = any; type DesktopFleetSnapshot = any; type DesktopFleetTask = any; type DesktopFleetWorker = any; type DesktopGitRepoState = any; type DesktopMessage = any; type DesktopPathStatus = any; type DesktopRuntimeStatus = any; type DesktopSidebarProjectActivity = any; type DesktopSidebarState = any; type DesktopVoicePackState = any; type DesktopVoiceRuntimeStatus = any; type InterruptPolicy = any; type JarvisSttBackend = any; type JarvisTtsBackend = any; type LayoutChangeEvent = any; type MessageSourceFormat = any; type ModelProviderGroup = any; type NativeScrollEvent = any; type PendingSearchJump = any; type QueuedComposerMessage = any; type QueuedMessage = any; type RealtimeChannel = any; type RealtimeEvent = any; type ReferenceEntry = any; type RuntimeOrchestratorStatus = any; type ScheduledJob = any; type SearchResultTarget = any; type SecurityPermissionMode = any; type SessionDetail = any; type SessionMessage = any; type SessionSearchResult = any; type SessionSummary = any; type SessionTimelineEvent = any; type SidebarChatTooltipState = any; type SidebarDragState = any; type SidebarDraftChat = any; type SidebarProjectGroup = any; type StartupReadinessState = any; type TaskBoard = any; type TelegramBotConfig = any; type TextInputContentSizeChangeEventData = any; type ToolPackInfoPopupState = any; type VoiceCaptureMode = any; type VoiceGateState = any;

export function useDesktopConversationSyncControls(scope: DesktopConversationScope) {
  const { DESKTOP_SIDEBAR_ACTIVITY_LIMIT, MAX_ACTIVITY_ITEMS, SIDEBAR_REFRESH_MS, TRANSCRIPT_AUTO_SCROLL_IDLE_MS, TRANSCRIPT_SCROLL_MOVE_THRESHOLD, TRANSCRIPT_SCROLL_UP_THRESHOLD, VOICE_ENGINE_HEBREW, activateSessionWithRecovery, allowedWorkspaceRoot, alwaysOnEnabled, alwaysOnEnabledRef, apiBaseUrl, assistantDeltaBufferRef, assistantDeltaFlushTimerRef, assistantDraft, buildDraftChatState, chatRunActive, chatRunActiveRef, clearConversationSelection, coerceSidebarState, completedTaskBoards, configureVoiceSttBackend, configureVoiceTtsBackend, configuredModelGroups, configuredPlannerModels, conversationMode, conversationModeRef, createEmptySidebarState, currentJarvisSttBackend, currentJarvisTtsBackend, currentWorkspaceBySessionRef, describeError, draftChat, draftChatRef, ensureSidebarProjectEntries, ensureSidebarProjectEntry, existingSessionIdFrom, fetchAgentConfig, fetchAgentOverview, fetchJobs, fetchProfile, fetchRuntimeOrchestratorStatus, fetchSessionDetail, fetchSessions, fetchTelegramBotConfigs, fetchVoiceRuntimeStatus, fleetSnapshot, getDesktopGitRepoInfo, getDesktopPathStatus, historyMessageLayoutRef, historyScrollRef, initialSessionId, initialSurfaceMode, isReferenceSidebarMessage, jarvisSttBackendLabel, jarvisTtsBackendLabel, lastVoiceWarmRequestEngineRef, liveVoiceStatus, loadDesktopSidebarState, mergeTimelineEventState, messageTimestampValue, messages, normalizeCompletedTaskBoards, normalizeJarvisSttBackend, normalizeJarvisTtsBackend, normalizeTimelineEvents, normalizeWorkspacePath, onStartupStateChange, overview, overviewRefreshInFlightRef, pendingSearchJump, preferredProjectPath, projectPathBasename, projectPaths, resetConversationForDraft, resolveTaskBoardState, saveDesktopSidebarState, scrollRef, searchHighlightTimerRef, searchJumpTimerRef, searchSessions, selectedProjectPath, selectedVoiceEngine, sessionId, sessionIdRef, sessionName, sessionProjectPaths, sessions, setActivity, setArtifactError, setArtifacts, setAssistantDraft, setCachedModelGroups, setCachedPlannerModels, setChatRunActive, setCompletedTaskBoards, setConversationMode, setDraftChat, setDraftGitRepoLoading, setDraftGitRepoState, setExpandedCompletedTaskIds, setHighlightedMessageIndex, setJobs, setKeepRuntimeOnAppClose, setLastAssistantOutputAt, setLiveVoiceStatus, setMessages, setOrchestratorStatus, setOverview, setPendingSearchJump, setProjectPathStatuses, setRuntimeRunState, setSelectedArtifactDetail, setSelectedArtifactId, setSessionId, setSessionName, setSessions, setShowReferenceRail, setShowVoicePanel, setSidebarExpanded, setSidebarSearch, setSidebarSearchError, setSidebarSearchLoading, setSidebarSearchModalOpen, setSidebarSearchResults, setSidebarState, setSidebarStateReady, setStatus, setSttBackendChanging, setTaskBoard, setTaskBoardArmedNextTurnState, setTaskBoardCollapsed, setTelegramBotConfigs, setThinking, setTimelineEvents, setTtsBackendChanging, setVoiceError, setVoicePanelHidden, setVoiceState, shouldKeepSidebarProjectPath, showReferenceRail, sidebarCollectionsRefreshInFlightRef, sidebarSearch, sidebarSearchInputRef, sidebarSearchModalOpen, sidebarSearchRequestIdRef, sidebarState, sidebarStateReady, startupChatSocketReadyRef, startupSessionStateReadyRef, startupSidebarReadyRef, startupTerminalStateRef, status, sttBackendChanging, taskBoard, taskBoardStateRef, timelineEventMergeKey, toDesktopMessages, token, transcriptAutoScrollResumeTimerRef, transcriptAutoScrollSuspendedRef, transcriptContentHeightRef, transcriptLastScrollOffsetYRef, transcriptLastSignatureRef, transcriptMessageLayoutRef, transcriptPendingAutoScrollRef, transcriptProgrammaticScrollUntilRef, transcriptViewportHeightRef, ttsBackendChanging, useEffect, userFacingError, voiceCaptureModeRef, voiceDraft, voiceEngineChanging, voiceError, voiceMode, voicePanelHidden, voiceRecording, voiceRecordingRef, voiceRunning, voiceRunningRef, voiceStatus, warmVoiceRuntime } = scope;
  const setComposerInputValue = (...args: any[]) => scope.setComposerInputValue?.(...args);
  const sidebarCollectionsRequests = useRef(createLatestRequestGate()).current;
  const overviewRequests = useRef(createLatestRequestGate()).current;
  const sidebarStateRequests = useRef(createLatestRequestGate()).current;
  const startupSidebarLoadKeyRef = useRef('');
const lastMessage = messages.length > 0 ? messages[messages.length - 1] : null;
  const lastMessageSignature = lastMessage
    ? [
        lastMessage.role,
        lastMessage.channel || '',
        lastMessage.timestamp || '',
        lastMessage.content.slice(-120),
      ].join('|')
    : 'none';
  const transcriptSignature = [
    sessionId || 'none',
    String(messages.length),
    lastMessageSignature,
    assistantDraft,
  ].join('|');

  useEffect(() => {
    chatRunActiveRef.current = chatRunActive;
  }, [chatRunActive]);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    draftChatRef.current = draftChat;
  }, [draftChat]);

  useEffect(() => {
    if (!draftChat?.projectPath) {
      setDraftGitRepoState(null);
      setDraftGitRepoLoading(false);
      return;
    }
    let disposed = false;
    setDraftGitRepoLoading(true);
    void getDesktopGitRepoInfo(draftChat.projectPath).then((nextState: any) => {
      if (disposed) {
        return;
      }
      setDraftGitRepoState(nextState);
      setDraftGitRepoLoading(false);
      if (!nextState?.isGitRepo) {
        setDraftChat((current: any) => (
          current?.projectPath === draftChat.projectPath && current.selectedBranch
            ? {
                ...current,
                selectedBranch: null,
              }
            : current
        ));
        return;
      }
      const currentBranch = String(nextState.currentBranch || '').trim() || null;
      const branches = Array.isArray(nextState.branches) ? nextState.branches : [];
      setDraftChat((current: any) => {
        if (!current || current.projectPath !== draftChat.projectPath) {
          return current;
        }
        if (current.selectedBranch && branches.includes(current.selectedBranch)) {
          return current;
        }
        return {
          ...current,
          selectedBranch: currentBranch,
        };
      });
    }).catch(() => {
      if (!disposed) {
        setDraftGitRepoState(null);
        setDraftGitRepoLoading(false);
      }
    });
    return () => {
      disposed = true;
    };
  }, [draftChat?.projectPath]);

  useEffect(() => {
    if (configuredModelGroups.length) {
      setCachedModelGroups(configuredModelGroups);
    }
  }, [configuredModelGroups]);

  useEffect(() => {
    if (configuredPlannerModels.length) {
      setCachedPlannerModels(configuredPlannerModels);
    }
  }, [configuredPlannerModels]);

  useEffect(() => {
    if (!configuredModelGroups.length && overview?.model_groups?.length) {
      setCachedModelGroups(overview.model_groups);
    }
    if (!configuredPlannerModels.length && overview?.available_planner_models?.length) {
      setCachedPlannerModels(overview.available_planner_models);
    }
  }, [configuredModelGroups.length, configuredPlannerModels.length, overview]);

  useEffect(() => {
    let disposed = false;
    void loadDesktopSidebarState().then((stored: any) => {
      if (disposed) {
        return;
      }
      const storedState = coerceSidebarState(stored);
      setSidebarState((current: any) => {
        const currentState = coerceSidebarState(current);
        const hasLocalChanges = Boolean(
          currentState.projectOrder.length
          || Object.keys(currentState.projects).length
          || Object.keys(currentState.sessionMeta).length
          || currentState.selectedProjectPath
          || currentState.lastSelectedProjectPath
        );
        if (!hasLocalChanges) {
          return storedState;
        }
        const projectOrder = Array.from(new Set([
          ...storedState.projectOrder,
          ...currentState.projectOrder,
        ].map((item: any) => normalizeWorkspacePath(item)).filter(Boolean)));
        return coerceSidebarState({
          ...storedState,
          projectOrder,
          projects: {
            ...storedState.projects,
            ...currentState.projects,
          },
          sessionMeta: {
            ...storedState.sessionMeta,
            ...currentState.sessionMeta,
          },
          selectedProjectPath: currentState.selectedProjectPath || storedState.selectedProjectPath,
          lastSelectedProjectPath: currentState.lastSelectedProjectPath || storedState.lastSelectedProjectPath,
        });
      });
      setSidebarStateReady(true);
    }).catch(() => {
      if (!disposed) {
        setSidebarState((current: any) => {
          const currentState = coerceSidebarState(current);
          return (
            currentState.projectOrder.length
            || Object.keys(currentState.projects).length
            || Object.keys(currentState.sessionMeta).length
            || currentState.selectedProjectPath
            || currentState.lastSelectedProjectPath
          )
            ? currentState
            : createEmptySidebarState();
        });
        setSidebarStateReady(true);
      }
    });

    return () => {
      disposed = true;
    };
  }, []);

  useEffect(() => {
    if (!sidebarStateReady) {
      return;
    }
    void saveDesktopSidebarState(sidebarState).catch(() => {});
  }, [sidebarState, sidebarStateReady]);

  useEffect(() => {
    let disposed = false;
    const sessionProjectPaths = new Set(
      sessions
        .map((item: any) => normalizeWorkspacePath(item.workspace))
        .filter(Boolean),
    );
    const manualProjectPaths = new Set([
      ...sidebarState.projectOrder.map((item: any) => normalizeWorkspacePath(item)),
      ...Object.keys(sidebarState.projects).map((item: any) => normalizeWorkspacePath(item)),
    ].filter(Boolean));
    const projectPaths = Array.from(new Set([
      ...manualProjectPaths,
      ...sessions.map((item: any) => normalizeWorkspacePath(item.workspace)),
      ...(draftChat ? [draftChat.projectPath] : []),
    ].filter(Boolean))).filter((projectPath: any) => manualProjectPaths.has(projectPath) || shouldKeepSidebarProjectPath(projectPath, {
      allowedRoot: allowedWorkspaceRoot,
      sessionProjectPaths,
      draftProjectPath: draftChat?.projectPath,
    }));
    if (!projectPaths.length) {
      setProjectPathStatuses({});
      return () => {
        disposed = true;
      };
    }
    void Promise.all(projectPaths.map(async (projectPath: any) => [projectPath, await getDesktopPathStatus(projectPath)] as const))
      .then((entries: any) => {
        if (disposed) {
          return;
        }
        setProjectPathStatuses((current: any) => {
          const next: Record<string, DesktopPathStatus> = {};
          for (const [projectPath, status] of entries) {
            if (projectPath && status) {
              next[projectPath] = status;
            } else if (projectPath && current[projectPath]) {
              next[projectPath] = current[projectPath];
            }
          }
          return next;
        });
      })
      .catch(() => {
        if (!disposed) {
          setProjectPathStatuses((current: any) => current);
        }
      });

    return () => {
      disposed = true;
    };
  }, [allowedWorkspaceRoot, draftChat, sessions, sidebarState.projectOrder, sidebarState.projects]);

  useEffect(() => (
    () => {
      if (searchJumpTimerRef.current) {
        clearTimeout(searchJumpTimerRef.current);
        searchJumpTimerRef.current = null;
      }
      if (searchHighlightTimerRef.current) {
        clearTimeout(searchHighlightTimerRef.current);
        searchHighlightTimerRef.current = null;
      }
    }
  ), []);

  useEffect(() => {
    if (!sidebarSearchModalOpen) {
      return;
    }
    const timerId = setTimeout(() => {
      sidebarSearchInputRef.current?.focus();
    }, 20);
    return () => clearTimeout(timerId);
  }, [sidebarSearchModalOpen]);

  useEffect(() => {
    const normalizedQuery = sidebarSearch.trim();
    if (!sidebarSearchModalOpen || !normalizedQuery) {
      sidebarSearchRequestIdRef.current += 1;
      setSidebarSearchLoading(false);
      setSidebarSearchError(null);
      setSidebarSearchResults([]);
      return;
    }

    const requestId = ++sidebarSearchRequestIdRef.current;
    const timerId = setTimeout(() => {
      setSidebarSearchLoading(true);
      setSidebarSearchError(null);
      void searchSessions(apiBaseUrl, token, normalizedQuery, 40)
        .then((response: any) => {
          if (sidebarSearchRequestIdRef.current !== requestId) {
            return;
          }
          setSidebarSearchResults(response.results || []);
          setSidebarSearchLoading(false);
        })
        .catch((error: any) => {
          if (sidebarSearchRequestIdRef.current !== requestId) {
            return;
          }
          setSidebarSearchResults([]);
          setSidebarSearchLoading(false);
          setSidebarSearchError(userFacingError(error, 'Search did not finish.'));
        });
    }, 220);

    return () => clearTimeout(timerId);
  }, [apiBaseUrl, sidebarSearch, sidebarSearchModalOpen, token]);

  const emitStartupState = (state: StartupReadinessState, detail?: string) => {
    if (!onStartupStateChange) {
      return;
    }
    if (startupTerminalStateRef.current && state !== 'warming') {
      return;
    }
    if (state === 'chat_ready' || state === 'fatal_error') {
      startupTerminalStateRef.current = state;
    }
    onStartupStateChange(state, detail);
  };

  const maybeResolveStartupReady = () => {
    if (startupTerminalStateRef.current) {
      return;
    }
    if (
      startupSidebarReadyRef.current
      && startupSessionStateReadyRef.current
      && startupChatSocketReadyRef.current
    ) {
      emitStartupState('chat_ready');
    }
  };

  useEffect(() => {
    voiceCaptureModeRef.current = voiceMode;
  }, [voiceMode]);

  useEffect(() => {
    conversationModeRef.current = conversationMode;
  }, [conversationMode]);

  useEffect(() => {
    if (initialSurfaceMode !== conversationModeRef.current) {
      setConversationMode(initialSurfaceMode);
      conversationModeRef.current = initialSurfaceMode;
    }
  }, [initialSurfaceMode]);

  useEffect(() => {
    alwaysOnEnabledRef.current = alwaysOnEnabled;
  }, [alwaysOnEnabled]);

  useEffect(() => {
    if (!pendingSearchJump || pendingSearchJump.sessionId !== sessionId) {
      return;
    }

    if (searchJumpTimerRef.current) {
      clearTimeout(searchJumpTimerRef.current);
      searchJumpTimerRef.current = null;
    }

    const targetInHistory = messages.some((message: any, index: any) => (
      index === pendingSearchJump.messageIndex && isReferenceSidebarMessage(message, sessionName)
    ));
    if (targetInHistory && !showReferenceRail) {
      setSidebarExpanded(true);
      setShowReferenceRail(true);
      return;
    }

    const targetY = targetInHistory
      ? historyMessageLayoutRef.current[pendingSearchJump.messageIndex]
      : transcriptMessageLayoutRef.current[pendingSearchJump.messageIndex];

    if (typeof targetY === 'number') {
      if (targetInHistory) {
        historyScrollRef.current?.scrollTo({
          y: Math.max(0, targetY - 20),
          animated: true,
        });
      } else {
        transcriptProgrammaticScrollUntilRef.current = Date.now() + 800;
        scrollRef.current?.scrollTo({
          y: Math.max(0, targetY - 24),
          animated: true,
        });
      }

      setHighlightedMessageIndex(pendingSearchJump.messageIndex);
      if (searchHighlightTimerRef.current) {
        clearTimeout(searchHighlightTimerRef.current);
      }
      searchHighlightTimerRef.current = setTimeout(() => {
        setHighlightedMessageIndex((current: any) => (
          current === pendingSearchJump.messageIndex ? null : current
        ));
      }, 3200);
      setPendingSearchJump(null);
      return;
    }

    if (pendingSearchJump.attempt >= 18) {
      setPendingSearchJump(null);
      return;
    }

    searchJumpTimerRef.current = setTimeout(() => {
      setPendingSearchJump((current: any) => {
        if (!current || current.sessionId !== pendingSearchJump.sessionId || current.messageIndex !== pendingSearchJump.messageIndex) {
          return current;
        }
        return {
          ...current,
          attempt: current.attempt + 1,
        };
      });
    }, 80);

    return () => {
      if (searchJumpTimerRef.current) {
        clearTimeout(searchJumpTimerRef.current);
        searchJumpTimerRef.current = null;
      }
    };
  }, [messages, pendingSearchJump, sessionId, sessionName, showReferenceRail]);

  useEffect(() => {
    if (!taskBoard) {
      taskBoardStateRef.current = { taskId: null, status: null };
      return;
    }

    const previous = taskBoardStateRef.current;
    const nextTaskId = taskBoard.task_id || null;
    const nextStatus = taskBoard.status || null;
    const isNewTask = previous.taskId !== nextTaskId;
    const becameCompleted = previous.status !== nextStatus && nextStatus === 'completed';

    if (isNewTask || becameCompleted || taskBoard.pending_reassessment_reason) {
      setTaskBoardCollapsed(false);
    }

    taskBoardStateRef.current = { taskId: nextTaskId, status: nextStatus };
  }, [taskBoard]);

  useEffect(() => {
    setExpandedCompletedTaskIds((previous: any) => {
      const allowedIds = new Set(completedTaskBoards.map((board: any) => board.task_id));
      const next: Record<string, boolean> = {};
      for (const [taskId, isExpanded] of Object.entries(previous)) {
        if (allowedIds.has(taskId)) {
          next[taskId] = Boolean(isExpanded);
        }
      }
      return next;
    });
  }, [completedTaskBoards]);

  useEffect(() => {
    voiceRunningRef.current = voiceRunning;
  }, [voiceRunning]);

  useEffect(() => {
    voiceRecordingRef.current = voiceRecording;
  }, [voiceRecording]);

  const clearAssistantDeltaFlushTimer = () => {
    if (assistantDeltaFlushTimerRef.current) {
      clearTimeout(assistantDeltaFlushTimerRef.current);
      assistantDeltaFlushTimerRef.current = null;
    }
  };

  const flushAssistantDeltaBuffer = () => {
    clearAssistantDeltaFlushTimer();
    if (!assistantDeltaBufferRef.current) {
      return;
    }
    const delta = assistantDeltaBufferRef.current;
    assistantDeltaBufferRef.current = '';
    setAssistantDraft((previous: any) => previous + delta);
  };

  const clearTranscriptAutoScrollResumeTimer = () => {
    if (transcriptAutoScrollResumeTimerRef.current) {
      clearTimeout(transcriptAutoScrollResumeTimerRef.current);
      transcriptAutoScrollResumeTimerRef.current = null;
    }
  };

  const scrollTranscriptToEnd = (animated = true) => {
    transcriptProgrammaticScrollUntilRef.current = Date.now() + 300;
    scrollRef.current?.scrollToEnd({ animated });
  };

  const resumeTranscriptAutoScrollAtBottom = () => {
    clearTranscriptAutoScrollResumeTimer();
    transcriptAutoScrollSuspendedRef.current = false;
    if (transcriptPendingAutoScrollRef.current) {
      transcriptPendingAutoScrollRef.current = false;
      scrollTranscriptToEnd(true);
    }
  };

  const scheduleTranscriptAutoScrollResume = () => {
    const distanceFromBottom = Math.max(
      0,
      transcriptContentHeightRef.current - (
        transcriptLastScrollOffsetYRef.current + transcriptViewportHeightRef.current
      ),
    );
    if (distanceFromBottom <= 24) {
      resumeTranscriptAutoScrollAtBottom();
    }
  };

  const resetTranscriptAutoScrollState = () => {
    transcriptAutoScrollSuspendedRef.current = false;
    transcriptPendingAutoScrollRef.current = false;
    transcriptLastScrollOffsetYRef.current = 0;
    clearTranscriptAutoScrollResumeTimer();
  };

  useEffect(() => () => {
    clearTranscriptAutoScrollResumeTimer();
    clearAssistantDeltaFlushTimer();
  }, []);

  useEffect(() => {
    if (transcriptSignature === transcriptLastSignatureRef.current) {
      return;
    }

    transcriptLastSignatureRef.current = transcriptSignature;
    if (transcriptAutoScrollSuspendedRef.current) {
      transcriptPendingAutoScrollRef.current = true;
      return;
    }

    transcriptPendingAutoScrollRef.current = false;
    const timer = setTimeout(() => {
      scrollTranscriptToEnd(true);
    }, 0);
    return () => clearTimeout(timer);
  }, [transcriptSignature]);

  useEffect(() => {
    if (conversationMode === 'jarvis') {
      return;
    }
    if ((voiceDraft || voiceError || voiceRecording) && !voicePanelHidden) {
      setShowVoicePanel(true);
    }
  }, [conversationMode, voiceDraft, voiceError, voiceRecording, voicePanelHidden]);

  const openVoicePanel = () => {
    setVoicePanelHidden(false);
    setSidebarExpanded(true);
    setShowVoicePanel(true);
  };

  const hideVoicePanel = () => {
    setVoicePanelHidden(true);
    setShowVoicePanel(false);
  };

  const pushActivity = (text: string, tone: ActivityItem['tone'] = 'neutral') => {
    const normalized = text.trim();
    if (!normalized) return;
    setActivity((previous: any) => [
      {
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        text: normalized,
        tone,
        timestamp: Date.now(),
      },
      ...previous,
    ].slice(0, MAX_ACTIVITY_ITEMS));
  };

  const updateSidebarState = (
    updater: (current: DesktopSidebarState) => DesktopSidebarState,
  ) => {
    setSidebarState((current: any) => coerceSidebarState(updater(coerceSidebarState(current))));
  };

  const selectProjectPath = (projectPath: string | null | undefined) => {
    const normalized = normalizeWorkspacePath(projectPath);
    updateSidebarState((current: any) => {
      if (!normalized) {
        return {
          ...current,
          selectedProjectPath: null,
        };
      }
      const ensured = ensureSidebarProjectEntry(current, normalized);
      return {
        ...ensured,
        selectedProjectPath: normalized,
        lastSelectedProjectPath: normalized,
      };
    });
  };

  const revealProjectInSidebar = (projectPath: string | null | undefined) => {
    const normalized = normalizeWorkspacePath(projectPath);
    if (!normalized) {
      return;
    }
    updateSidebarState((current: any) => {
      const ensured = ensureSidebarProjectEntry(current, normalized);
      const existing = ensured.projects[normalized] || {};
      return {
        ...ensured,
        selectedProjectPath: normalized,
        lastSelectedProjectPath: normalized,
        projects: {
          ...ensured.projects,
          [normalized]: {
            ...existing,
            collapsed: false,
            hidden: false,
          },
        },
      };
    });
    setSidebarExpanded(true);
  };

  const openSidebarSearchModal = () => {
    setSidebarSearchModalOpen(true);
  };

  const clearSidebarSearch = () => {
    sidebarSearchRequestIdRef.current += 1;
    setSidebarSearch('');
    setSidebarSearchLoading(false);
    setSidebarSearchError(null);
    setSidebarSearchResults([]);
  };

  const closeSidebarSearchModal = () => {
    setSidebarSearchModalOpen(false);
    clearSidebarSearch();
  };

  const discardDraftChat = (options?: { clearInput?: boolean }) => {
    draftChatRef.current = null;
    setDraftChat(null);
    if (options?.clearInput) {
      setComposerInputValue('');
    }
  };

  const pushProjectActivity = (sourceProjectPath: string, destinationProjectPath: string, movedSession: SessionSummary) => {
    const sourcePath = normalizeWorkspacePath(sourceProjectPath);
    const destinationPath = normalizeWorkspacePath(destinationProjectPath);
    if (!sourcePath || !destinationPath || sourcePath === destinationPath) {
      return;
    }

    const timestamp = new Date().toISOString();
    const sourceLabel = projectPathBasename(sourcePath);
    const destinationLabel = projectPathBasename(destinationPath);
    updateSidebarState((current: any) => {
      let next = ensureSidebarProjectEntries(current, [sourcePath, destinationPath]);
      const appendActivity = (projectPath: string, message: string, relatedProjectPath: string) => {
        const existing = next.projects[projectPath] || {};
        const recentActivity = [
          {
            id: `${movedSession.id}:${timestamp}:${projectPath}`,
            message,
            timestamp,
            sessionId: movedSession.id,
            relatedProjectPath,
          },
          ...(existing.recentActivity || []),
        ].slice(0, DESKTOP_SIDEBAR_ACTIVITY_LIMIT);
        next = {
          ...next,
          projects: {
            ...next.projects,
            [projectPath]: {
              ...existing,
              recentActivity,
            },
          },
        };
      };

      appendActivity(sourcePath, `${movedSession.name} moved to ${destinationLabel}`, destinationPath);
      appendActivity(destinationPath, `${movedSession.name} moved here from ${sourceLabel}`, sourcePath);
      return next;
    });
  };

  const reconcileSidebarProjects = (
    nextSessions: SessionSummary[],
    options?: {
      preferredSelectedProjectPath?: string | null;
      activeSessionWorkspace?: string | null;
    },
  ) => {
    const nextWorkspaceBySession: Record<string, string> = {};
    const projectPaths = new Set<string>();
    for (const item of nextSessions) {
      const workspace = normalizeWorkspacePath(item.workspace);
      if (!workspace) {
        continue;
      }
      nextWorkspaceBySession[item.id] = workspace;
      projectPaths.add(workspace);
      const previousWorkspace = currentWorkspaceBySessionRef.current[item.id];
      if (previousWorkspace && previousWorkspace !== workspace) {
        pushProjectActivity(previousWorkspace, workspace, item);
      }
    }
    currentWorkspaceBySessionRef.current = nextWorkspaceBySession;

    const preferredSelected = normalizeWorkspacePath(
      options?.preferredSelectedProjectPath
      || options?.activeSessionWorkspace
      || draftChatRef.current?.projectPath
      || '',
    );

    updateSidebarState((current: any) => {
      let next = ensureSidebarProjectEntries(current, Array.from(projectPaths));
      const fallbackSelection = normalizeWorkspacePath(
        preferredSelected
        || current.selectedProjectPath
        || current.lastSelectedProjectPath
        || Array.from(projectPaths)[0]
        || '',
      );
      next = {
        ...next,
        selectedProjectPath: fallbackSelection || null,
        lastSelectedProjectPath: fallbackSelection || current.lastSelectedProjectPath || null,
      };
      return next;
    });
  };

  const mergeLocalMessages = (
    syncedMessages: DesktopMessage[],
    previousMessages: DesktopMessage[],
    nextSessionId: string,
  ) => {
    const syncedConfirmsLocalMessage = (synced: any, local: any) => {
      if (!local.pending || synced.role !== local.role || synced.role !== 'user') {
        return false;
      }
      const localMessageId = String(local.clientMessageId || local.raw?.client_message_id || '').trim();
      const syncedMessageId = String(synced.clientMessageId || synced.raw?.client_message_id || '').trim();
      if (localMessageId && syncedMessageId) {
        return localMessageId === syncedMessageId;
      }
      const localClientId = String(local.sourceClientId || '').trim();
      const syncedClientId = String(synced.sourceClientId || '').trim();
      if (!localClientId || !syncedClientId || localClientId !== syncedClientId) {
        return false;
      }
      return (
        String(synced.content || '') === String(local.content || '')
        && String(synced.channel || '') === String(local.channel || '')
        && String(synced.sourceFormat || '') === String(local.sourceFormat || '')
      );
    };
    const localMessages = previousMessages.filter((message: any) => (
      (message.localOnly || message.pending)
      && message.localSessionId === nextSessionId
      && !syncedMessages.some((synced: any) => syncedConfirmsLocalMessage(synced, message))
    ));
    return [...syncedMessages, ...localMessages]
      .map((message: any, index: any) => ({
        message,
        index,
        timestamp: messageTimestampValue(message),
      }))
      .sort((left: any, right: any) => {
        if (left.timestamp != null && right.timestamp != null && left.timestamp !== right.timestamp) {
          return left.timestamp - right.timestamp;
        }
        if (left.timestamp != null && right.timestamp == null) {
          return -1;
        }
        if (left.timestamp == null && right.timestamp != null) {
          return 1;
        }
        return left.index - right.index;
      })
      .map((entry: any) => entry.message);
  };

  const applySessionDetail = (detail: SessionDetail, options?: { preserveActiveRun?: boolean }) => {
    const switchingSessions = detail.id !== sessionIdRef.current;
    const nextEnabledToolPacks = Array.isArray(detail.enabled_tool_packs) ? detail.enabled_tool_packs : [];
    const nextAvailableToolPacks = Array.isArray(detail.available_tool_packs) ? detail.available_tool_packs : [];
    const nextLockStatus = detail.lock_status || {};
    if (switchingSessions) {
      resetTranscriptAutoScrollState();
      setTaskBoardCollapsed(false);
      setExpandedCompletedTaskIds({});
      transcriptMessageLayoutRef.current = {};
      historyMessageLayoutRef.current = {};
      setArtifacts([]);
      setSelectedArtifactId(null);
      setSelectedArtifactDetail(null);
      setArtifactError(null);
      assistantDeltaBufferRef.current = '';
      clearAssistantDeltaFlushTimer();
      setAssistantDraft('');
      setThinking('');
      setLastAssistantOutputAt(null);
    }
    const nextRunState = options?.preserveActiveRun || detail.run_state === 'running' || detail.is_running ? 'running' : 'idle';
    sessionIdRef.current = detail.id;
    setSessionId(detail.id);
    setSessionName(detail.name);
    scope.setPlanMode?.((detail.plan_mode && typeof detail.plan_mode === 'object') ? detail.plan_mode : null);
    scope.setActiveGoal?.((detail.active_goal && typeof detail.active_goal === 'object') ? detail.active_goal : null);
    setRuntimeRunState(nextRunState);
    chatRunActiveRef.current = nextRunState === 'running';
    setChatRunActive(nextRunState === 'running');
    if (nextRunState === 'idle') {
      setAssistantDraft('');
      setThinking('');
      setLastAssistantOutputAt(null);
    }
    setTaskBoard(resolveTaskBoardState(detail.task_board, detail.id, sessionIdRef.current));
    setCompletedTaskBoards(normalizeCompletedTaskBoards(detail.completed_task_boards));
    setTaskBoardArmedNextTurnState(Boolean(detail.task_board_armed_next_turn));
    setTimelineEvents((previous: any) => (
      switchingSessions
        ? normalizeTimelineEvents(detail.timeline_events || [])
        : mergeTimelineEventState(previous, detail.timeline_events || [])
    ));
    const syncedMessages = toDesktopMessages(detail.messages || []);
    setMessages((previous: any) => mergeLocalMessages(syncedMessages, previous, detail.id));
    const detailMessages = Array.isArray(detail.messages) ? detail.messages : [];
    const latestDetailMessage = [...detailMessages].reverse().find((message: any) => String(message?.content || '').trim());
    const detailSummary = {
      id: detail.id,
      name: detail.name,
      created_at: detail.created_at,
      updated_at: detail.updated_at,
      model: detail.model,
      variant: detail.variant,
      message_count: detailMessages.length,
      workspace: detail.workspace,
      latest_preview: latestDetailMessage ? String(latestDetailMessage.content || '').slice(0, 140) : null,
      origin_channels: Array.from(new Set(detailMessages.map((message: any) => message?.channel).filter(Boolean))),
      enabled_tool_packs: nextEnabledToolPacks,
      available_tool_packs: nextAvailableToolPacks,
      lock_status: nextLockStatus,
      telegram_bot_config_id: detail.telegram_bot_config_id ?? null,
      headless_eligible: Boolean(detail.headless_eligible),
      security_permission_mode: detail.security_permission_mode || 'standard',
      artifact_count: Number(detail.artifact_count || 0),
      latest_artifact_at: detail.latest_artifact_at ?? null,
      is_running: nextRunState === 'running',
      run_state: nextRunState,
      workspace_id: detail.workspace_id ?? null,
      workspace_binding_status: detail.workspace_binding_status ?? null,
      fleet_identity_id: detail.fleet_identity_id ?? null,
      fleet_identity_role: detail.fleet_identity_role ?? null,
      fleet_worker_id: detail.fleet_worker_id ?? null,
      plan_mode: detail.plan_mode ?? null,
      active_goal: detail.active_goal ?? null,
    };
    setSessions((previous: any) => {
      let updated = false;
      const next = previous.map((item: any) => {
        if (item.id !== detail.id) {
          return item;
        }
        updated = true;
        return {
          ...item,
          ...detailSummary,
          telegram_bot_config_id: detail.telegram_bot_config_id ?? item.telegram_bot_config_id ?? null,
          latest_artifact_at: detail.latest_artifact_at ?? item.latest_artifact_at ?? null,
          run_state: detail.run_state || item.run_state,
        };
      });
      return updated ? next : [detailSummary, ...next];
    });
    setOverview((previous: any) => {
      if (!previous || previous.session_id !== detail.id) {
        return previous;
      }
      return {
        ...previous,
        current_model: detail.model || previous.current_model,
        current_variant: detail.variant || previous.current_variant,
        planner_model: detail.planner_model ?? previous.planner_model,
        run_state: nextRunState,
        enabled_tool_packs: nextEnabledToolPacks,
        available_tool_packs: nextAvailableToolPacks,
        lock_status: nextLockStatus,
      };
    });
    discardDraftChat();
    selectProjectPath(detail.workspace);
  };

  const appendTimelineEvent = (event: SessionTimelineEvent) => {
    if (!event) {
      return;
    }
    setTimelineEvents((previous: any) => {
      const existingIndex = previous.findIndex((item: any) => timelineEventMergeKey(item) === timelineEventMergeKey(event));
      if (existingIndex < 0) {
        return normalizeTimelineEvents([...previous, event]);
      }
      const next = previous.slice();
      next[existingIndex] = event;
      return normalizeTimelineEvents(next);
    });
  };

  const handleTranscriptScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    const nativeEvent = event.nativeEvent;
    const nextOffsetY = Math.max(0, nativeEvent.contentOffset?.y ?? 0);
    const previousOffsetY = transcriptLastScrollOffsetYRef.current;
    transcriptLastScrollOffsetYRef.current = nextOffsetY;
    transcriptContentHeightRef.current = nativeEvent.contentSize?.height ?? transcriptContentHeightRef.current;
    transcriptViewportHeightRef.current = nativeEvent.layoutMeasurement?.height ?? transcriptViewportHeightRef.current;

    if (Date.now() < transcriptProgrammaticScrollUntilRef.current) {
      return;
    }

    const distanceFromBottom = Math.max(
      0,
      transcriptContentHeightRef.current - (nextOffsetY + transcriptViewportHeightRef.current),
    );
    const isAtBottom = distanceFromBottom <= 24;

    if (transcriptAutoScrollSuspendedRef.current && isAtBottom) {
      resumeTranscriptAutoScrollAtBottom();
      return;
    }

    const deltaY = nextOffsetY - previousOffsetY;
    if (Math.abs(deltaY) < TRANSCRIPT_SCROLL_MOVE_THRESHOLD) {
      return;
    }

    if (deltaY < -TRANSCRIPT_SCROLL_UP_THRESHOLD) {
      transcriptAutoScrollSuspendedRef.current = true;
      transcriptPendingAutoScrollRef.current = distanceFromBottom > 24;
      clearTranscriptAutoScrollResumeTimer();
      return;
    }

    if (transcriptAutoScrollSuspendedRef.current) {
      transcriptPendingAutoScrollRef.current = transcriptPendingAutoScrollRef.current || distanceFromBottom > 24;
    }
  };

  const applySessionSync = (payload: Record<string, any>, options?: { preserveActiveRun?: boolean }) => {
    const detail = payload.session as SessionDetail | undefined;
    const syncedSessions = payload.sessions as SessionSummary[] | undefined;
    const syncedRuntime = payload.runtime as RuntimeOrchestratorStatus | undefined;
    if (Array.isArray(syncedSessions)) {
      reconcileSidebarProjects(syncedSessions, {
        preferredSelectedProjectPath: draftChatRef.current?.projectPath || undefined,
        activeSessionWorkspace: detail?.workspace,
      });
      setSessions(syncedSessions);
    }
    if (syncedRuntime) {
      setOrchestratorStatus(syncedRuntime);
    }
    if (detail?.id) {
      const detailSessionId = String(detail.id || '').trim();
      const selectedSessionId = String(sessionIdRef.current || '').trim();
      if (selectedSessionId && detailSessionId && detailSessionId !== selectedSessionId) {
        return;
      }
      const modelChanged = Boolean(
        overview && (
          overview.current_model !== detail.model
          || overview.context_usage?.model !== detail.model
        )
      );
      applySessionDetail(detail, options);
      setOverview((previous: any) => {
        if (!previous) {
          return previous;
        }
        return {
          ...previous,
          session_id: detail.id,
          planner_model: detail.planner_model ?? previous.planner_model ?? null,
          task_board_armed_next_turn: Boolean(detail.task_board_armed_next_turn),
          task_board: detail.task_board ?? null,
          completed_task_boards: normalizeCompletedTaskBoards(detail.completed_task_boards),
          context_usage: {
            ...previous.context_usage,
            model: detail.model,
          },
        };
      });
      if (modelChanged) {
        void refreshOverviewState(detail.id);
      }
    }
  };

  const refreshSidebarCollections = async (preferredSessionId?: string | null, quiet = true) => {
    const requestId = sidebarCollectionsRequests.begin();
    sidebarCollectionsRefreshInFlightRef.current = true;
    try {
      const [profile, sessionList, jobList, botConfigList, runtimeSummary] = await Promise.all([
        fetchProfile(apiBaseUrl, token),
        fetchSessions(apiBaseUrl, token),
        fetchJobs(apiBaseUrl, token),
        fetchTelegramBotConfigs(apiBaseUrl, token).catch(() => []),
        fetchRuntimeOrchestratorStatus(apiBaseUrl, token).catch(() => null),
      ]);

      if (!sidebarCollectionsRequests.isCurrent(requestId)) {
        return;
      }

      const currentSelectedSessionId = sessionIdRef.current || sessionId || null;
      const resolvedSessionId = draftChatRef.current
        ? null
        : existingSessionIdFrom(
          sessionList,
          preferredSessionId,
          profile.current_session_id,
          currentSelectedSessionId,
          sessionList[0]?.id,
        );
      const activeSessionWorkspace = resolvedSessionId
        ? currentWorkspaceBySessionRef.current[resolvedSessionId]
          || sessions.find((item: any) => item.id === resolvedSessionId)?.workspace
        : undefined;

      reconcileSidebarProjects(sessionList, {
        preferredSelectedProjectPath: draftChatRef.current?.projectPath || undefined,
        activeSessionWorkspace,
      });
      setSessions(sessionList);
      setJobs(jobList);
      setTelegramBotConfigs(Array.isArray(botConfigList) ? botConfigList : []);
      setOrchestratorStatus(runtimeSummary);
      if (!quiet) {
        setStatus('ready');
        maybeResolveStartupReady();
      }
    } catch (error) {
      if (!sidebarCollectionsRequests.isCurrent(requestId)) {
        return;
      }
      if (!quiet) {
        const message = describeError(error);
        setStatus(message);
        if (!startupTerminalStateRef.current) {
          emitStartupState('fatal_error', message);
        }
      }
    } finally {
      if (sidebarCollectionsRequests.isCurrent(requestId)) {
        sidebarCollectionsRefreshInFlightRef.current = false;
      }
    }
  };

  const refreshOverviewState = async (
    preferredSessionId?: string | null,
    options?: { includeCloseBehavior?: boolean; quiet?: boolean },
  ) => {
    const requestId = overviewRequests.begin();
    const includeCloseBehavior = Boolean(options?.includeCloseBehavior);
    const quiet = Boolean(options?.quiet);
    const resolvedSessionId = draftChatRef.current
      ? null
      : preferredSessionId || sessionIdRef.current || null;
    if (!resolvedSessionId) {
      overviewRefreshInFlightRef.current = false;
      if (!quiet) {
        setOverview(null);
      }
      return;
    }

    overviewRefreshInFlightRef.current = true;
    try {
      const [nextOverview, closeBehaviorConfig] = await Promise.all([
        fetchAgentOverview(apiBaseUrl, token, {
          sessionId: resolvedSessionId || undefined,
        }),
        includeCloseBehavior
          ? fetchAgentConfig(
              apiBaseUrl,
              token,
              'channels.desktop.keep_runtime_on_app_close',
              resolvedSessionId || undefined,
            ).catch(() => ({ items: [] }))
          : Promise.resolve<{ items: Array<{ value?: unknown }> }>({ items: [] }),
      ]);
      if (
        !overviewRequests.isCurrent(requestId)
        || String(sessionIdRef.current || '').trim() !== String(resolvedSessionId || '').trim()
      ) {
        return;
      }
      setOverview((previous: any) => {
        if (nextOverview) {
          return nextOverview;
        }
        if (resolvedSessionId && previous?.session_id === resolvedSessionId) {
          return previous;
        }
        return null;
      });
      setRuntimeRunState(nextOverview?.run_state ?? 'idle');
      setTaskBoardArmedNextTurnState(Boolean(nextOverview?.task_board_armed_next_turn ?? false));
      setTaskBoard(resolveTaskBoardState(nextOverview?.task_board ?? null, resolvedSessionId, sessionIdRef.current));
      setCompletedTaskBoards(normalizeCompletedTaskBoards(nextOverview?.completed_task_boards ?? []));
      if (includeCloseBehavior) {
        setKeepRuntimeOnAppClose(Boolean(closeBehaviorConfig.items?.[0]?.value));
      }
    } catch (error) {
      if (!overviewRequests.isCurrent(requestId)) {
        return;
      }
      if (!quiet) {
        const message = describeError(error);
        setStatus(message);
        if (!startupTerminalStateRef.current) {
          emitStartupState('fatal_error', message);
        }
      }
    } finally {
      if (overviewRequests.isCurrent(requestId)) {
        overviewRefreshInFlightRef.current = false;
      }
    }
  };

  const refreshSidebarState = async (preferredSessionId?: string | null, quiet = false) => {
    const requestId = sidebarStateRequests.begin();
    if (!quiet) {
      setStatus('loading shared session');
      emitStartupState('warming', 'Loading shared session');
    }

    try {
      const fastInitialLoad = !quiet;
      let profile;
      let sessionList: SessionSummary[];
      let jobList: ScheduledJob[] = [];
      let botConfigList: TelegramBotConfig[] = [];
      let runtimeSummary: RuntimeOrchestratorStatus | null = null;

      if (fastInitialLoad) {
        [profile, sessionList] = await Promise.all([
          fetchProfile(apiBaseUrl, token),
          fetchSessions(apiBaseUrl, token),
        ]);
        if (!sidebarStateRequests.isCurrent(requestId)) {
          return;
        }
        void Promise.all([
          fetchJobs(apiBaseUrl, token),
          fetchTelegramBotConfigs(apiBaseUrl, token).catch(() => []),
          fetchRuntimeOrchestratorStatus(apiBaseUrl, token).catch(() => null),
        ])
          .then(([deferredJobs, deferredBotConfigs, deferredRuntimeSummary]) => {
            if (!sidebarStateRequests.isCurrent(requestId)) {
              return;
            }
            setJobs(deferredJobs);
            setTelegramBotConfigs(Array.isArray(deferredBotConfigs) ? deferredBotConfigs : []);
            setOrchestratorStatus(deferredRuntimeSummary);
          })
          .catch((error: any) => {
            if (sidebarStateRequests.isCurrent(requestId)) {
              setStatus(userFacingError(error, 'Chat data did not finish loading.'));
            }
          });
      } else {
        [profile, sessionList, jobList, botConfigList, runtimeSummary] = await Promise.all([
          fetchProfile(apiBaseUrl, token),
          fetchSessions(apiBaseUrl, token),
          fetchJobs(apiBaseUrl, token),
          fetchTelegramBotConfigs(apiBaseUrl, token).catch(() => []),
          fetchRuntimeOrchestratorStatus(apiBaseUrl, token).catch(() => null),
        ]);
      }

      if (!sidebarStateRequests.isCurrent(requestId)) {
        return;
      }

      const currentSelectedSessionId = sessionIdRef.current || sessionId || null;
      let resolvedSessionId = existingSessionIdFrom(
        sessionList,
        preferredSessionId,
        profile.current_session_id,
        currentSelectedSessionId,
        sessionList[0]?.id,
      );
      let detail: SessionDetail | null = null;
      if (draftChatRef.current) {
        resolvedSessionId = null;
      }

      if (!detail && resolvedSessionId) {
        detail = preferredSessionId && preferredSessionId !== profile.current_session_id
          ? await activateSessionWithRecovery(resolvedSessionId)
          : await fetchSessionDetail(apiBaseUrl, token, resolvedSessionId);
      }

      if (!sidebarStateRequests.isCurrent(requestId)) {
        return;
      }

      let nextOverview: AgentOverview | null = null;
      let closeBehaviorConfig: { items: Array<{ value?: unknown }> } = { items: [] };
      if (resolvedSessionId && !fastInitialLoad) {
        [nextOverview, closeBehaviorConfig] = await Promise.all([
          fetchAgentOverview(apiBaseUrl, token, {
            sessionId: resolvedSessionId || undefined,
          }),
          fetchAgentConfig(
            apiBaseUrl,
            token,
            'channels.desktop.keep_runtime_on_app_close',
            resolvedSessionId || undefined
          ).catch(() => ({ items: [] })),
        ]);
      }

      if (!sidebarStateRequests.isCurrent(requestId)) {
        return;
      }

      reconcileSidebarProjects(sessionList, {
        preferredSelectedProjectPath: draftChatRef.current?.projectPath || undefined,
        activeSessionWorkspace: detail?.workspace,
      });
      setSessions(sessionList);
      if (!fastInitialLoad) {
        setJobs(jobList);
        setTelegramBotConfigs(Array.isArray(botConfigList) ? botConfigList : []);
        setOrchestratorStatus(runtimeSummary);
      }
      setOverview(nextOverview);
      setRuntimeRunState(nextOverview?.run_state ?? 'idle');
      setTaskBoardArmedNextTurnState(Boolean(nextOverview?.task_board_armed_next_turn ?? detail?.task_board_armed_next_turn ?? false));
      setTaskBoard(resolveTaskBoardState(nextOverview?.task_board ?? detail?.task_board ?? null, resolvedSessionId, sessionIdRef.current));
      setCompletedTaskBoards(normalizeCompletedTaskBoards(nextOverview?.completed_task_boards ?? detail?.completed_task_boards ?? []));
      setKeepRuntimeOnAppClose(Boolean(closeBehaviorConfig.items?.[0]?.value));
      if (detail) {
        applySessionDetail(detail);
      } else if (draftChatRef.current) {
        setSessionId(undefined);
        setSessionName(draftChatRef.current.title);
        setMessages([]);
        setTimelineEvents([]);
        setTaskBoard(null);
        setCompletedTaskBoards([]);
        setTaskBoardArmedNextTurnState(false);
      } else if (preferredProjectPath) {
        resetConversationForDraft(preferredProjectPath);
        setDraftChat(buildDraftChatState(preferredProjectPath));
      } else {
        clearConversationSelection();
      }
      startupSidebarReadyRef.current = true;
      startupSessionStateReadyRef.current = true;
      setStatus('ready');
      maybeResolveStartupReady();
      if (fastInitialLoad && resolvedSessionId) {
        void refreshOverviewState(resolvedSessionId, {
          includeCloseBehavior: true,
          quiet: true,
        });
      }
    } catch (error) {
      if (!sidebarStateRequests.isCurrent(requestId)) {
        return;
      }
      const message = describeError(error);
      setStatus(message);
      if (!startupTerminalStateRef.current) {
        emitStartupState('fatal_error', message);
      }
    }
  };

  const refreshVoiceRuntimeState = async () => {
    if (conversationModeRef.current !== 'jarvis') {
      setLiveVoiceStatus(null);
      return null;
    }
    if (!apiBaseUrl || !token) {
      return null;
    }
    const next = await fetchVoiceRuntimeStatus(apiBaseUrl, token);
    setLiveVoiceStatus(next as DesktopVoiceRuntimeStatus);
    return next as DesktopVoiceRuntimeStatus;
  };

  const warmSelectedVoicePath = async (engineOverride?: string) => {
    const engine = engineOverride || selectedVoiceEngine;
    if (conversationModeRef.current !== 'jarvis') {
      return refreshVoiceRuntimeState();
    }
    if (!apiBaseUrl || !token) {
      return refreshVoiceRuntimeState();
    }
    lastVoiceWarmRequestEngineRef.current = engine;
    if (engine === VOICE_ENGINE_HEBREW) {
      setVoiceState('warming');
      setStatus('warming Hebrew voice path');
    } else if (conversationModeRef.current === 'jarvis') {
      setStatus('warming Jarvis voice');
    }
    const warmed = await warmVoiceRuntime(apiBaseUrl, token);
    setLiveVoiceStatus(warmed as DesktopVoiceRuntimeStatus);
    if (warmed?.input_ok === false) {
      const message = warmed.issues?.[0] || 'Jarvis voice input is not ready.';
      setVoiceError(String(message));
      setVoiceState('error');
      setStatus(String(message));
    } else if ((warmed?.selected_engine_state || '') === 'ready' || engine !== VOICE_ENGINE_HEBREW) {
      setVoiceState(alwaysOnEnabledRef.current ? 'always_on' : 'ready');
      setStatus('voice ready');
    } else if (warmed?.issues?.[0]) {
      setVoiceError(String(warmed.issues[0]));
      setVoiceState('error');
      setStatus(String(warmed.issues[0]));
    }
    return warmed as DesktopVoiceRuntimeStatus;
  };

  const handleJarvisSttBackendSelection = async (backend: JarvisSttBackend) => {
    if (conversationModeRef.current !== 'jarvis' || !apiBaseUrl || !token || sttBackendChanging) {
      return;
    }
    const normalizedBackend = normalizeJarvisSttBackend(backend);
    if (currentJarvisSttBackend === normalizedBackend && liveVoiceStatus?.input_ok) {
      return;
    }
    const targetLabel = jarvisSttBackendLabel(normalizedBackend);
    setSttBackendChanging(normalizedBackend);
    setStatus(`switching voice input to ${targetLabel}`);
    try {
      const next = await configureVoiceSttBackend(apiBaseUrl, token, normalizedBackend);
      setLiveVoiceStatus(next as DesktopVoiceRuntimeStatus);
      if (next.stt_switch?.ok === false) {
        const message = next.stt_switch.issues?.[0] || `${targetLabel} input is not ready.`;
        setStatus(message);
        pushActivity(`Voice input switch failed: ${message}`, 'warn');
        return;
      }
      if (next.input_ok === false) {
        const message = next.issues?.[0] || `${targetLabel} input is not ready.`;
        setStatus(message);
        pushActivity(message, 'warn');
        return;
      }
      setStatus(`${targetLabel} voice input ready`);
      pushActivity(`Jarvis input switched to ${targetLabel}`, 'accent');
    } catch (error) {
      const message = describeError(error);
      setStatus(message);
      pushActivity(`Voice input switch failed: ${message}`, 'error');
    } finally {
      setSttBackendChanging(null);
    }
  };

  const handleJarvisTtsBackendSelection = async (backend: JarvisTtsBackend) => {
    if (conversationModeRef.current !== 'jarvis' || !apiBaseUrl || !token || ttsBackendChanging) {
      return;
    }
    const normalizedBackend = normalizeJarvisTtsBackend(backend) as JarvisTtsBackend;
    if (currentJarvisTtsBackend === normalizedBackend && liveVoiceStatus?.tts_ready) {
      return;
    }
    const targetLabel = jarvisTtsBackendLabel(normalizedBackend);
    setTtsBackendChanging(normalizedBackend);
    setStatus(`switching voice to ${targetLabel}`);
    try {
      const next = await configureVoiceTtsBackend(apiBaseUrl, token, normalizedBackend);
      setLiveVoiceStatus(next as DesktopVoiceRuntimeStatus);
      if (next.tts_switch?.ok === false) {
        const message = next.tts_switch.issues?.[0] || `${targetLabel} is not ready.`;
        setStatus(message);
        pushActivity(`Voice switch failed: ${message}`, 'warn');
        return;
      }
      if (next.tts_ready === false) {
        const message = next.tts_issues?.[0] || `${targetLabel} is not ready.`;
        setStatus(message);
        pushActivity(message, 'warn');
        return;
      }
      setStatus(`${targetLabel} voice ready`);
      pushActivity(`Jarvis voice switched to ${targetLabel}`, 'accent');
    } catch (error) {
      const message = describeError(error);
      setStatus(message);
      pushActivity(`Voice switch failed: ${message}`, 'error');
    } finally {
      setTtsBackendChanging(null);
    }
  };

  useEffect(() => {
    if (!apiBaseUrl || !token || !fleetSnapshot) return;
    const startupKey = `${apiBaseUrl}|${String(initialSessionId || '')}`;
    if (startupSidebarLoadKeyRef.current === startupKey) return;
    const activeIdentityId = String(
      fleetSnapshot.active_identity?.identity_id
      || fleetSnapshot.active_identity_id
      || '',
    ).trim();
    const selectedIdentityChatId = activeIdentityId
      ? String(fleetSnapshot.selected_chat_by_identity?.[activeIdentityId] || '').trim()
      : '';
    startupSidebarLoadKeyRef.current = startupKey;
    void refreshSidebarState(initialSessionId || selectedIdentityChatId || null, false);
  }, [apiBaseUrl, fleetSnapshot !== null, initialSessionId, token]);

  useEffect(() => {
    setLiveVoiceStatus(conversationMode === 'jarvis' ? voiceStatus || null : null);
  }, [conversationMode, voiceStatus]);

  useEffect(() => {
    if (conversationMode !== 'jarvis') {
      lastVoiceWarmRequestEngineRef.current = null;
      return;
    }
    if (!apiBaseUrl || !token) {
      return;
    }
    if (selectedVoiceEngine !== VOICE_ENGINE_HEBREW) {
      lastVoiceWarmRequestEngineRef.current = null;
      return;
    }
    if ((liveVoiceStatus?.selected_engine_state || '') === 'ready') {
      lastVoiceWarmRequestEngineRef.current = selectedVoiceEngine;
      return;
    }
    if (lastVoiceWarmRequestEngineRef.current === selectedVoiceEngine || voiceEngineChanging) {
      return;
    }
    void warmSelectedVoicePath(selectedVoiceEngine);
  }, [apiBaseUrl, conversationMode, token, selectedVoiceEngine, liveVoiceStatus?.selected_engine_state, voiceEngineChanging]);

  useEffect(() => {
    if (!apiBaseUrl || !token || !sessionId) return;

    const intervalId = setInterval(() => {
      if (chatRunActiveRef.current) {
        return;
      }
      void refreshSidebarCollections(sessionId, true);
    }, SIDEBAR_REFRESH_MS);

    return () => clearInterval(intervalId);
  }, [apiBaseUrl, sessionId, token]);
  return { lastMessage, lastMessageSignature, transcriptSignature, emitStartupState, maybeResolveStartupReady, clearAssistantDeltaFlushTimer, flushAssistantDeltaBuffer, clearTranscriptAutoScrollResumeTimer, scrollTranscriptToEnd, scheduleTranscriptAutoScrollResume, resetTranscriptAutoScrollState, openVoicePanel, hideVoicePanel, pushActivity, updateSidebarState, selectProjectPath, revealProjectInSidebar, openSidebarSearchModal, clearSidebarSearch, closeSidebarSearchModal, discardDraftChat, pushProjectActivity, reconcileSidebarProjects, mergeLocalMessages, applySessionDetail, appendTimelineEvent, handleTranscriptScroll, applySessionSync, refreshSidebarCollections, refreshOverviewState, refreshSidebarState, refreshVoiceRuntimeState, warmSelectedVoicePath, handleJarvisSttBackendSelection, handleJarvisTtsBackendSelection };
}
