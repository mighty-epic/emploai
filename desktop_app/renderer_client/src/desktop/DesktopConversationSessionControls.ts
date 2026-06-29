import type { DesktopConversationScope } from './DesktopConversationScope';
import { modelExistsInGroups } from './modelProviders';
type NativeSyntheticEvent<T = any> = any; type ActiveCommandPanel = any; type ActivityItem = any; type AgentOverview = any; type ArtifactDetail = any; type ArtifactSummary = any; type ComposerInputOrigin = any; type ConversationSurfaceMode = any; type DesktopFleetEnrollment = any; type DesktopFleetIdentity = any; type DesktopFleetSnapshot = any; type DesktopFleetTask = any; type DesktopFleetWorker = any; type DesktopGitRepoState = any; type DesktopMessage = any; type DesktopPathStatus = any; type DesktopRuntimeStatus = any; type DesktopSidebarProjectActivity = any; type DesktopSidebarState = any; type DesktopVoicePackState = any; type DesktopVoiceRuntimeStatus = any; type InterruptPolicy = any; type JarvisSttBackend = any; type JarvisTtsBackend = any; type LayoutChangeEvent = any; type MessageSourceFormat = any; type ModelProviderGroup = any; type NativeScrollEvent = any; type PendingSearchJump = any; type QueuedComposerMessage = any; type QueuedMessage = any; type RealtimeChannel = any; type RealtimeEvent = any; type ReferenceEntry = any; type RuntimeOrchestratorStatus = any; type ScheduledJob = any; type SearchResultTarget = any; type SecurityPermissionMode = any; type SessionDetail = any; type SessionMessage = any; type SessionSearchResult = any; type SessionSummary = any; type SessionTimelineEvent = any; type SidebarChatTooltipState = any; type SidebarDragState = any; type SidebarDraftChat = any; type SidebarProjectGroup = any; type StartupReadinessState = any; type TaskBoard = any; type TelegramBotConfig = any; type TextInputContentSizeChangeEventData = any; type ToolPackInfoPopupState = any; type VoiceCaptureMode = any; type VoiceGateState = any;

export function useDesktopConversationSessionControls(scope: DesktopConversationScope) {
  const { SIDEBAR_DRAFT_CHAT_ID, activateSession, activeFleetIdentity, allowedWorkspaceRoot, alwaysOnEnabledRef, apiBaseUrl, checkoutDesktopGitBranch, configureAgent, configuredModelGroups, controlAgentRun, createDesktopFolder, createSession, currentWorkspaceBySessionRef, defaultTelegramBotConfigId, defaultToolPackIds, deleteSession, describeError, draftChat, draftChatRef, enabledToolPackIdsFrom, ensureSidebarProjectEntries, ensureSidebarProjectEntry, fetchSessionDetail, fleetSessionCreateFields, fleetSnapshot, folderChoiceResolveRef, getDesktopPathStatus, interruptPolicy, isAbsoluteWindowsPath, isWorkspacePathAllowed, keepRuntimeOnAppClose, loadDesktopBootstrap, normalizeWorkspacePath, overview, pendingDraftSecurityPermissionMode, pendingMessagesRef, pendingSessionSwitch, pickDesktopFolder, preferredModelFromGroups, projectDisplayName, projectPathBasename, projectPathStatuses, sessionBelongsToFleetIdentity, sessionId, sessionIdRef, sessionSidebarSortComparator, sessions, setActiveCommandPanel, setAlwaysOnEnabled, setAssistantDraft, setChatRunActive, setCompletedTaskBoards, setDraftChat, setDraftGitRepoState, setExpandedCompletedTaskIds, setFolderChoiceBusy, setFolderChoiceOpen, setKeepRuntimeOnAppClose, setMessages, setOpenProjectMenuPath, setOpenSessionMenuId, setOverview, setPendingSearchJump, setPendingSessionSwitch, setRuntimeRunState, setSavingCloseBehavior, setSessionId, setSessionName, setShowReferenceRail, setSidebarExpanded, setStatus, setTaskBoard, setTaskBoardArmedNextTurn, setTaskBoardArmedNextTurnState, setTaskBoardCollapsed, setThinking, setTimelineEvents, setVoiceRecording, setVoiceRunning, setVoiceState, sidebarState, status, strOrNull, taskBoardArmedNextTurn, telegramBotConfigs, token, updateAgentConfig, userFacingError, voicePressActiveRef, voiceRecordingRef, voiceRunningRef, voiceStartInFlightRef, voiceWsRef } = scope;
  const applySessionDetail = (...args: any[]) => scope.applySessionDetail?.(...args);
  const discardDraftChat = (...args: any[]) => scope.discardDraftChat?.(...args);
  const pushActivity = (...args: any[]) => scope.pushActivity?.(...args);
  const refreshOverviewState = (...args: any[]) => scope.refreshOverviewState?.(...args);
  const refreshSidebarCollections = (...args: any[]) => scope.refreshSidebarCollections?.(...args);
  const refreshSidebarState = (...args: any[]) => scope.refreshSidebarState?.(...args);
  const revealProjectInSidebar = (...args: any[]) => scope.revealProjectInSidebar?.(...args);
  const selectProjectPath = (...args: any[]) => scope.selectProjectPath?.(...args);
  const updateSidebarState = (...args: any[]) => scope.updateSidebarState?.(...args);
  const cleanupAssistantAudio = (...args: any[]) => scope.cleanupAssistantAudio?.(...args);
  const flushPendingMessages = (...args: any[]) => scope.flushPendingMessages?.(...args);
  const requireActiveDesktopSession = (...args: any[]) => scope.requireActiveDesktopSession?.(...args);
  const resetVoiceCaptureBuffers = (...args: any[]) => scope.resetVoiceCaptureBuffers?.(...args);
  const setComposerInputValue = (...args: any[]) => scope.setComposerInputValue?.(...args);
  const stopVoiceTracks = (...args: any[]) => scope.stopVoiceTracks?.(...args);
const isBusySessionSwitchError = (error: unknown) => (
    describeError(error).toLowerCase().includes('finish or stop the current task')
  );

  const isRecoverableSessionActivationError = (error: unknown) => {
    const detail = describeError(error).toLowerCase();
    return (
      detail.includes('failed to fetch')
      || detail.includes('networkerror')
      || detail.includes('network request failed')
      || detail.includes('load failed')
    );
  };

  const activateSessionWithRecovery = async (targetSessionId: string) => {
    try {
      return await activateSession(apiBaseUrl, token, targetSessionId);
    } catch (error) {
      if (isBusySessionSwitchError(error)) {
        setStatus('showing chat while the current run continues');
        return fetchSessionDetail(apiBaseUrl, token, targetSessionId);
      }
      if (!isRecoverableSessionActivationError(error)) {
        throw error;
      }

      setStatus('reconnecting local runtime');
      await loadDesktopBootstrap({ force: true }).catch(() => null);
      await new Promise((resolve: any) => setTimeout(resolve, 700));
      return activateSession(apiBaseUrl, token, targetSessionId);
    }
  };

  const selectedProjectPathCandidate = normalizeWorkspacePath(
    draftChat?.projectPath
    || sidebarState.selectedProjectPath
    || sidebarState.lastSelectedProjectPath
    || sessions.find((item: any) => item.id === sessionIdRef.current)?.workspace
    || '',
  );
  const selectedProjectPath = isWorkspacePathAllowed(selectedProjectPathCandidate, allowedWorkspaceRoot)
    ? selectedProjectPathCandidate
    : '';
  const preferredProjectPath = selectedProjectPath;
  const preferredFolderPickerPath = preferredProjectPath && isWorkspacePathAllowed(preferredProjectPath, allowedWorkspaceRoot)
    ? preferredProjectPath
    : (allowedWorkspaceRoot || null);
  const emptyConversationProjectPath = normalizeWorkspacePath(
    draftChat?.projectPath
    || selectedProjectPath
    || currentWorkspaceBySessionRef.current[sessionIdRef.current || '']
    || sessions.find((item: any) => item.id === sessionIdRef.current)?.workspace
    || '',
  );
  const emptyConversationProjectName = emptyConversationProjectPath
    ? projectPathBasename(emptyConversationProjectPath)
    : '';

  const securityPermissionModeForProject = (
    projectPath: string,
    fallback: SecurityPermissionMode = 'standard',
  ): SecurityPermissionMode => {
    const normalizedProjectPath = normalizeWorkspacePath(projectPath);
    const matchingSession = normalizedProjectPath
      ? sessions.find((item: any) => (
          normalizeWorkspacePath(item.workspace) === normalizedProjectPath
          && item.security_permission_mode
        ))
      : null;
    return (matchingSession?.security_permission_mode || fallback || 'standard') as SecurityPermissionMode;
  };

  const buildDraftChatState = (
    projectPath: string,
    telegramBotConfigId?: string | null,
  ): SidebarDraftChat => {
    const currentSessionSummary = sessions.find((item: any) => item.id === sessionIdRef.current || item.id === sessionId) || null;
    const availableDraftModelGroups = Array.isArray(configuredModelGroups) ? configuredModelGroups : [];
    const overviewModel = strOrNull(overview?.current_model);
    const sessionModel = strOrNull(currentSessionSummary?.model);
    const fallbackModel = strOrNull(preferredModelFromGroups(availableDraftModelGroups) || '');
    const nextDraftModel = modelExistsInGroups(overviewModel, availableDraftModelGroups)
      ? overviewModel
      : modelExistsInGroups(sessionModel, availableDraftModelGroups)
        ? sessionModel
        : fallbackModel;
    const nextDraftVariant = strOrNull(overview?.current_variant || '');
    const nextDraftPlannerModel = strOrNull(
      overview?.planner_model || '',
    );
    const nextDraftEnabledToolPacks = enabledToolPackIdsFrom(
      overview?.enabled_tool_packs,
      currentSessionSummary?.enabled_tool_packs,
    );
    const projectPermissionMode = securityPermissionModeForProject(
      projectPath,
      currentSessionSummary?.security_permission_mode || 'standard',
    );
    const nextDraftSecurityPermissionMode = (
      pendingDraftSecurityPermissionMode
      || projectPermissionMode
      || 'standard'
    ) as SecurityPermissionMode;
    return {
      id: SIDEBAR_DRAFT_CHAT_ID,
      projectPath,
      title: 'New chat',
      telegramBotConfigId: strOrNull(telegramBotConfigId) || scope.defaultTelegramBotConfigId,
      model: nextDraftModel,
      variant: nextDraftVariant,
      plannerModel: nextDraftPlannerModel,
      enabledToolPacks: nextDraftEnabledToolPacks,
      securityPermissionMode: nextDraftSecurityPermissionMode,
      selectedBranch: null,
    };
  };

  const resetConversationForDraft = (projectPath: string) => {
    sessionIdRef.current = undefined;
    voiceStartInFlightRef.current = false;
    voicePressActiveRef.current = false;
    alwaysOnEnabledRef.current = false;
    setAlwaysOnEnabled(false);
    if (voiceWsRef.current) {
      voiceWsRef.current.close();
      voiceWsRef.current = null;
    }
    stopVoiceTracks();
    resetVoiceCaptureBuffers({ clearProgrammaticComposerInput: true });
    voiceRunningRef.current = false;
    voiceRecordingRef.current = false;
    setVoiceRunning(false);
    setVoiceRecording(false);
    setVoiceState(apiBaseUrl && token ? 'idle' : 'unavailable');
    void cleanupAssistantAudio();
    setSessionId(undefined);
    setSessionName('New chat');
    setMessages([]);
    setTimelineEvents([]);
    setTaskBoardArmedNextTurnState(false);
    setRuntimeRunState('idle');
    setTaskBoard(null);
    setCompletedTaskBoards([]);
    setTaskBoardCollapsed(false);
    setExpandedCompletedTaskIds({});
    setAssistantDraft('');
    setThinking('');
    setShowReferenceRail(false);
    selectProjectPath(projectPath);
  };

  const clearConversationSelection = (
    projectPath?: string | null,
    options?: { clearSidebarProject?: boolean },
  ) => {
    sessionIdRef.current = undefined;
    voiceStartInFlightRef.current = false;
    voicePressActiveRef.current = false;
    alwaysOnEnabledRef.current = false;
    setAlwaysOnEnabled(false);
    if (voiceWsRef.current) {
      voiceWsRef.current.close();
      voiceWsRef.current = null;
    }
    stopVoiceTracks();
    resetVoiceCaptureBuffers({ clearProgrammaticComposerInput: true });
    voiceRunningRef.current = false;
    voiceRecordingRef.current = false;
    setVoiceRunning(false);
    setVoiceRecording(false);
    setVoiceState(apiBaseUrl && token ? 'idle' : 'unavailable');
    void cleanupAssistantAudio();
    setSessionId(undefined);
    setSessionName('New chat');
    setMessages([]);
    setTimelineEvents([]);
    setOverview(null);
    setTaskBoardArmedNextTurnState(false);
    setRuntimeRunState('idle');
    setTaskBoard(null);
    setCompletedTaskBoards([]);
    setTaskBoardCollapsed(false);
    setExpandedCompletedTaskIds({});
    setAssistantDraft('');
    setThinking('');
    setShowReferenceRail(false);
    if (projectPath) {
      selectProjectPath(projectPath);
    } else if (options?.clearSidebarProject) {
      updateSidebarState((current: any) => ({
        ...current,
        selectedProjectPath: null,
        lastSelectedProjectPath: null,
      }));
    }
  };

  const resolveAllowedProjectPath = async (projectPath: string) => {
    const normalized = normalizeWorkspacePath(projectPath);
    if (!normalized) {
      return { requestedPath: '', targetPath: '', status: null as DesktopPathStatus | null };
    }

    const knownStatus = projectPathStatuses[normalized] || null;
    const status = knownStatus || await getDesktopPathStatus(normalized).catch(() => null);
    const resolvedStatusPath = normalizeWorkspacePath(status?.resolvedPath || '');
    const fallbackRootCandidate = (
      !isAbsoluteWindowsPath(normalized) && allowedWorkspaceRoot
        ? normalizeWorkspacePath(`${allowedWorkspaceRoot}\\${normalized.replace(/^\\+/, '')}`)
        : ''
    );
    const allowedCandidates = [
      resolvedStatusPath,
      normalized,
      fallbackRootCandidate,
    ].filter((candidate: any, index: any, values: any) => (
      Boolean(candidate)
      && values.indexOf(candidate) === index
      && isWorkspacePathAllowed(candidate, allowedWorkspaceRoot)
    ));

    let targetPath = allowedCandidates[0] || '';
    if (!targetPath && fallbackRootCandidate) {
      const fallbackStatus = await getDesktopPathStatus(fallbackRootCandidate).catch(() => null);
      if (fallbackStatus?.exists && fallbackStatus.isDirectory) {
        targetPath = normalizeWorkspacePath(fallbackStatus.resolvedPath || fallbackRootCandidate) || fallbackRootCandidate;
      }
    }

    return {
      requestedPath: normalized,
      targetPath,
      status,
    };
  };

  const rememberProjectFolder = (projectPath: string) => {
    const normalized = normalizeWorkspacePath(projectPath);
    if (!normalized) {
      return '';
    }
    updateSidebarState((current: any) => {
      const ensured = ensureSidebarProjectEntry(current, normalized);
      return {
        ...ensured,
        selectedProjectPath: normalized,
        lastSelectedProjectPath: normalized,
        projects: {
          ...ensured.projects,
          [normalized]: {
            ...(ensured.projects[normalized] || {}),
            hidden: false,
          },
        },
      };
    });
    setSidebarExpanded(true);
    return normalized;
  };

  const promptForProjectFolder = async () => {
    const picked = await pickDesktopFolder(preferredFolderPickerPath || null);
    if (!picked) {
      return null;
    }
    const normalized = normalizeWorkspacePath(picked);
    if (!isWorkspacePathAllowed(normalized, allowedWorkspaceRoot)) {
      setStatus(
        allowedWorkspaceRoot
          ? `Choose a folder inside ${allowedWorkspaceRoot}`
          : 'Choose a valid workspace folder',
      );
      return null;
    }
    return rememberProjectFolder(normalized);
  };

  const automaticProjectParentPath = () => (
    allowedWorkspaceRoot
      ? normalizeWorkspacePath(`${allowedWorkspaceRoot}\\EmploAI Chats`)
      : null
  );

  const createAutomaticProjectFolderPath = async () => {
    setFolderChoiceBusy('auto');
    try {
      const created = await createDesktopFolder(automaticProjectParentPath(), null);
      const normalized = normalizeWorkspacePath(created?.path || '');
      if (!normalized) {
        setStatus('automatic folder could not be created');
        return null;
      }
      if (!isWorkspacePathAllowed(normalized, allowedWorkspaceRoot)) {
        setStatus(
          allowedWorkspaceRoot
            ? `Automatic folder must be inside ${allowedWorkspaceRoot}`
            : 'Automatic folder is not available here',
        );
        return null;
      }
      rememberProjectFolder(normalized);
      setStatus(`created folder ${projectPathBasename(normalized)}`);
      return normalized;
    } catch (error) {
      setStatus(userFacingError(error, 'Folder was not created.'));
      return null;
    } finally {
      setFolderChoiceBusy(null);
    }
  };

  const closeFolderChoice = (projectPath: string | null) => {
    const resolver = folderChoiceResolveRef.current;
    folderChoiceResolveRef.current = null;
    setFolderChoiceOpen(false);
    setFolderChoiceBusy(null);
    resolver?.(projectPath);
  };

  const askForProjectFolderChoice = async () => {
    if (folderChoiceResolveRef.current) {
      folderChoiceResolveRef.current(null);
      folderChoiceResolveRef.current = null;
    }
    setActiveCommandPanel(null);
    setFolderChoiceBusy(null);
    setFolderChoiceOpen(true);
    return new Promise<string | null>((resolve: any) => {
      folderChoiceResolveRef.current = resolve;
    });
  };

  const chooseFolderFromChoice = async () => {
    setFolderChoiceBusy('choose');
    try {
      const pickedProject = await promptForProjectFolder();
      closeFolderChoice(pickedProject || null);
    } finally {
      setFolderChoiceBusy(null);
    }
  };

  const createAutomaticFolderFromChoice = async () => {
    const createdProject = await createAutomaticProjectFolderPath();
    if (createdProject) {
      closeFolderChoice(createdProject);
    }
  };

  const resolveProjectForNewChatStart = async () => {
    if (preferredProjectPath) {
      return preferredProjectPath;
    }
    return askForProjectFolderChoice();
  };

  const resolveProjectPathForNewChat = async (projectPath: string) => {
    const { requestedPath, targetPath, status } = await resolveAllowedProjectPath(projectPath);
    if (!requestedPath) {
      return null;
    }
    if (!targetPath) {
      setStatus(`"${projectPathBasename(requestedPath)}" is outside the current workspace root · choose a replacement folder`);
      const replacement = await promptForProjectFolder();
      return replacement || null;
    }
    if (!status) {
      return targetPath;
    }
    if (status.exists && status.isDirectory) {
      return normalizeWorkspacePath(status.resolvedPath || targetPath) || targetPath;
    }

    setStatus(`"${projectPathBasename(targetPath)}" is no longer available · choose a replacement folder`);
    const replacement = await promptForProjectFolder();
    return replacement || null;
  };

  const openDraftChat = async (projectPath: string, telegramBotConfigId?: string | null) => {
    const resolvedProjectPath = await resolveProjectPathForNewChat(projectPath);
    if (!resolvedProjectPath) {
      return;
    }
    const resolvedBotConfigId = strOrNull(telegramBotConfigId) || scope.defaultTelegramBotConfigId;
    discardDraftChat({ clearInput: true });
    const nextDraft = buildDraftChatState(resolvedProjectPath, resolvedBotConfigId);
    setSidebarExpanded(true);
    resetConversationForDraft(resolvedProjectPath);
    setDraftChat(nextDraft);
    setStatus(`new chat in ${projectPathBasename(resolvedProjectPath)}`);
  };

  const chooseDraftProjectFolder = async () => {
    if (!draftChatRef.current) {
      return;
    }
    const pickedProject = await promptForProjectFolder();
    if (!pickedProject) {
      return;
    }
    resetConversationForDraft(pickedProject);
    setDraftChat((current: any) => (
      current
        ? {
            ...current,
            projectPath: pickedProject,
            selectedBranch: null,
          }
        : current
    ));
    setActiveCommandPanel((current: any) => (
      current?.kind === 'draftBranch' || current?.kind === 'draftProject'
        ? null
        : current
    ));
    setStatus(`draft folder ${projectPathBasename(pickedProject)}`);
  };

  const chooseDraftProject = (projectPath: string) => {
    const normalized = normalizeWorkspacePath(projectPath);
    const currentDraft = draftChatRef.current;
    if (!currentDraft || !normalized) {
      return;
    }
    if (normalizeWorkspacePath(currentDraft.projectPath) === normalized) {
      selectProjectPath(normalized);
      setActiveCommandPanel((current: any) => current?.kind === 'draftProject' ? null : current);
      return;
    }
    resetConversationForDraft(normalized);
    setDraftChat((current: any) => (
      current
        ? {
            ...current,
            projectPath: normalized,
            selectedBranch: null,
          }
        : current
    ));
    setDraftGitRepoState(null);
    setActiveCommandPanel((current: any) => (
      current?.kind === 'draftBranch' || current?.kind === 'draftProject'
        ? null
        : current
    ));
    setStatus(`draft folder ${projectPathBasename(normalized)}`);
  };

  const chooseDraftBranch = (branchName: string) => {
    if (!draftChatRef.current) {
      return;
    }
    setDraftChat((current: any) => (
      current
        ? {
            ...current,
            selectedBranch: branchName,
          }
        : current
    ));
    setActiveCommandPanel((current: any) => current?.kind === 'draftBranch' ? null : current);
    setStatus(`draft branch ${branchName}`);
  };

  const chooseDraftTelegramBot = (telegramBotConfigId: string | null) => {
    if (!draftChatRef.current) {
      return;
    }
    const nextBotId = strOrNull(telegramBotConfigId);
    setDraftChat((current: any) => (
      current
        ? {
            ...current,
            telegramBotConfigId: nextBotId,
          }
        : current
    ));
    setActiveCommandPanel((current: any) => current?.kind === 'draftTelegram' ? null : current);
    const nextBot = telegramBotConfigs.find((bot: any) => bot.id === nextBotId) || null;
    setStatus(`draft Telegram bot ${nextBot?.label || 'none'}`);
  };

  const beginNewChat = async () => {
    const targetProject = await resolveProjectForNewChatStart();
    if (!targetProject) {
      setStatus('choose or create a folder to start a new chat');
      return;
    }
    await openDraftChat(targetProject);
  };

  const materializeDraftSession = async (projectPath: string) => {
    const { requestedPath, targetPath, status } = await resolveAllowedProjectPath(projectPath);
    if (!requestedPath || !targetPath) {
      throw new Error(
        allowedWorkspaceRoot
          ? `Choose a folder inside ${allowedWorkspaceRoot}`
          : 'Choose a folder to start a new chat',
      );
    }
    const targetProjectPath = targetPath;
    const pathStatus = status || await getDesktopPathStatus(targetProjectPath).catch(() => null);
    if (pathStatus && (!pathStatus.exists || !pathStatus.isDirectory)) {
      throw new Error(`"${projectPathBasename(targetProjectPath)}" is no longer available. Choose another folder for the new chat.`);
    }
    setStatus('creating chat');
    const draftSnapshot = draftChatRef.current;
    const selectedDraftBranch = strOrNull(draftSnapshot?.selectedBranch);
    if (selectedDraftBranch) {
      setStatus(`switching to ${selectedDraftBranch}`);
      const switchedBranch = await checkoutDesktopGitBranch(targetProjectPath, selectedDraftBranch).catch(() => null);
      if (switchedBranch?.error) {
        throw new Error(String(switchedBranch.error));
      }
    }
    setStatus('creating chat');
    const nextSecurityPermissionMode = draftSnapshot?.securityPermissionMode
      || pendingDraftSecurityPermissionMode
      || securityPermissionModeForProject(targetProjectPath);
    const created = await createSession(apiBaseUrl, token, {
      workspace: targetProjectPath,
      telegram_bot_config_id: draftSnapshot?.telegramBotConfigId || scope.defaultTelegramBotConfigId,
      enabled_tool_packs: draftSnapshot?.enabledToolPacks ?? defaultToolPackIds(),
      security_permission_mode: nextSecurityPermissionMode,
      ...fleetSessionCreateFields(scope.activeFleetIdentity),
    });
    const draftModel = strOrNull(draftSnapshot?.model);
    const draftVariant = strOrNull(draftSnapshot?.variant);
    const draftPlannerModel = draftSnapshot?.plannerModel === undefined
      ? undefined
      : draftSnapshot?.plannerModel;
    const nextConfigPayload: Record<string, unknown> = {};
    if (draftModel && draftModel !== created.session.model) {
      nextConfigPayload.model = draftModel;
    }
    if (draftVariant && draftVariant !== created.session.variant) {
      nextConfigPayload.variant = draftVariant;
    }
    if (draftPlannerModel !== undefined && draftPlannerModel !== created.session.planner_model) {
      nextConfigPayload.planner_model = draftPlannerModel;
    }
    if (Object.keys(nextConfigPayload).length > 0) {
      await configureAgent(apiBaseUrl, token, nextConfigPayload, created.session.id);
    }
    applySessionDetail(created.session);
    void Promise.all([
      refreshSidebarCollections(created.session.id, true),
      refreshOverviewState(created.session.id, { quiet: true }),
    ]).catch((error: any) => {
      setStatus(userFacingError(error, 'Chat sidebar did not refresh.'));
    });
    return created.session.id;
  };

  const ensureSessionForOutgoingMessage = async () => {
    if (draftChatRef.current) {
      return materializeDraftSession(draftChatRef.current.projectPath);
    }

    if (sessionIdRef.current) {
      const currentSummary = sessions.find((item: any) => item.id === sessionIdRef.current) || null;
      if (!currentSummary) {
        const fallbackProject = preferredProjectPath || selectedProjectPath || '';
        sessionIdRef.current = undefined;
        setSessionId(undefined);
        setStatus('selected chat was no longer available · creating a new chat');
        if (fallbackProject) {
          return materializeDraftSession(fallbackProject);
        }
        const targetProject = await resolveProjectForNewChatStart();
        return targetProject ? materializeDraftSession(targetProject) : null;
      }
      if (!scope.activeFleetIdentity || (currentSummary && sessionBelongsToFleetIdentity(currentSummary, scope.activeFleetIdentity))) {
        return sessionIdRef.current;
      }
      const selectedChatId = String(fleetSnapshot?.selected_chat_by_identity?.[scope.activeFleetIdentity.identity_id] || '').trim();
      if (selectedChatId && sessions.some((item: any) => item.id === selectedChatId)) {
        return selectedChatId;
      }
      const fallbackProject = preferredProjectPath || currentSummary?.workspace || '';
      if (fallbackProject) {
        return materializeDraftSession(fallbackProject);
      }
      return null;
    }

    if (scope.activeFleetIdentity) {
      const selectedChatId = String(fleetSnapshot?.selected_chat_by_identity?.[scope.activeFleetIdentity.identity_id] || '').trim();
      if (selectedChatId && sessions.some((item: any) => item.id === selectedChatId)) {
        return selectedChatId;
      }
    }

    const targetProject = await resolveProjectForNewChatStart();
    if (!targetProject) {
      return null;
    }

    return materializeDraftSession(targetProject);
  };

  const openSession = async (
    nextSessionId: string,
    options?: { jumpMessageIndex?: number | null; projectPath?: string | null },
  ) => {
    if (!nextSessionId) {
      return;
    }
    if (nextSessionId === sessionIdRef.current && !draftChatRef.current) {
      if (typeof options?.jumpMessageIndex === 'number') {
        setPendingSearchJump({
          sessionId: nextSessionId,
          messageIndex: options.jumpMessageIndex,
          attempt: 0,
        });
      }
      if (options?.projectPath) {
        revealProjectInSidebar(options.projectPath);
      }
      return;
    }

    discardDraftChat({ clearInput: true });
    setOpenSessionMenuId(null);
    if (options?.projectPath) {
      revealProjectInSidebar(options.projectPath);
    }
    setStatus('switching shared session');
    setAssistantDraft('');
    setThinking('');
    try {
      const detail = await activateSessionWithRecovery(nextSessionId);
      applySessionDetail(detail);
      await Promise.all([
        refreshSidebarCollections(nextSessionId, true),
        refreshOverviewState(nextSessionId, { quiet: true }),
      ]);
      if (typeof options?.jumpMessageIndex === 'number') {
        setPendingSearchJump({
          sessionId: nextSessionId,
          messageIndex: options.jumpMessageIndex,
          attempt: 0,
        });
      }
    } catch (error) {
      setStatus(userFacingError(error, 'Chat did not open.'));
    }
  };

  const confirmPendingSessionSwitch = async () => {
    if (!pendingSessionSwitch) {
      return;
    }

    const nextAction = pendingSessionSwitch;
    setPendingSessionSwitch(null);
    setStatus('stopping current run');
    try {
      await controlAgentRun(apiBaseUrl, token, 'stop', sessionIdRef.current);
      await refreshSidebarState(sessionIdRef.current, true);
      if (nextAction.mode === 'session') {
        await openSession(nextAction.sessionId, {
          jumpMessageIndex: nextAction.jumpMessageIndex ?? null,
        });
        return;
      }

      const nextSessionId = await materializeDraftSession(nextAction.projectPath);
      pendingMessagesRef.current.push({
        text: nextAction.text,
        sourceFormat: nextAction.sourceFormat,
        interruptPolicy,
        sessionId: nextSessionId,
      });
      setMessages((previous: any) => [
        ...previous,
        {
          role: 'user',
          content: nextAction.text,
          timestamp: new Date().toISOString(),
          displayLabel: nextAction.sourceFormat === 'app_voice_transcript' ? 'Voice' : 'You',
          channel: 'app',
          sourceFormat: nextAction.sourceFormat,
          messageKey: `pending:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
          pending: true,
          localSessionId: nextSessionId,
          sourceClientId: scope.appClientIdRef.current,
        },
      ]);
      flushPendingMessages();
      setStatus(nextAction.sourceFormat === 'app_voice_transcript' ? 'sending voice transcript' : 'sending message');
    } catch (error) {
      setStatus(userFacingError(error, 'Session switch did not finish.'));
    }
  };

  const dismissPendingSessionSwitch = () => {
    if (!pendingSessionSwitch) {
      return;
    }
    if (pendingSessionSwitch.mode === 'draft_send') {
      setComposerInputValue(pendingSessionSwitch.text);
      setStatus('kept the draft message unsent');
    } else {
      setStatus('chat switch cancelled');
    }
    setPendingSessionSwitch(null);
  };

  const toggleProjectPin = (projectPath: string) => {
    const normalized = normalizeWorkspacePath(projectPath);
    updateSidebarState((current: any) => {
      const ensured = ensureSidebarProjectEntry(current, normalized);
      const existing = ensured.projects[normalized] || {};
      return {
        ...ensured,
        projects: {
          ...ensured.projects,
          [normalized]: {
            ...existing,
            pinned: !existing.pinned,
          },
        },
      };
    });
  };

  const toggleSessionPin = (sessionEntry: SessionSummary) => {
    updateSidebarState((current: any) => {
      const existing = current.sessionMeta[sessionEntry.id] || {};
      return {
        ...current,
        sessionMeta: {
          ...current.sessionMeta,
          [sessionEntry.id]: {
            ...existing,
            pinned: !existing.pinned,
          },
        },
      };
    });
  };

  const toggleProjectCollapsed = (projectPath: string) => {
    const normalized = normalizeWorkspacePath(projectPath);
    updateSidebarState((current: any) => {
      const ensured = ensureSidebarProjectEntry(current, normalized);
      const existing = ensured.projects[normalized] || {};
      return {
        ...ensured,
        projects: {
          ...ensured.projects,
          [normalized]: {
            ...existing,
            collapsed: !existing.collapsed,
          },
        },
      };
    });
  };

  const renameProject = (projectPath: string) => {
    const normalized = normalizeWorkspacePath(projectPath);
    if (!normalized) {
      return;
    }
    const existingState = sidebarState.projects[normalized] || {};
    const currentName = projectDisplayName(normalized, existingState);
    const promptValue = globalThis.prompt?.('Rename folder in sidebar', currentName);
    if (typeof promptValue !== 'string') {
      return;
    }
    const nextName = promptValue.trim();
    updateSidebarState((current: any) => {
      const ensured = ensureSidebarProjectEntry(current, normalized);
      const existing = ensured.projects[normalized] || {};
      return {
        ...ensured,
        projects: {
          ...ensured.projects,
          [normalized]: {
            ...existing,
            displayName: nextName || null,
            hidden: false,
          },
        },
      };
    });
    setOpenProjectMenuPath(null);
  };

  const removeProjectFromSidebar = (projectPath: string) => {
    const normalized = normalizeWorkspacePath(projectPath);
    if (!normalized) {
      return;
    }
    if (draftChatRef.current?.projectPath === normalized) {
      discardDraftChat({ clearInput: true });
    }
    updateSidebarState((current: any) => {
      const ensured = ensureSidebarProjectEntry(current, normalized);
      const existing = ensured.projects[normalized] || {};
      const fallbackProjectPath = [...ensured.projectOrder, ...Object.keys(ensured.projects)]
        .map((item: any) => normalizeWorkspacePath(item))
        .find((item: any) => item && item !== normalized && !ensured.projects[item]?.hidden) || null;
      return {
        ...ensured,
        selectedProjectPath: ensured.selectedProjectPath === normalized ? fallbackProjectPath : ensured.selectedProjectPath,
        lastSelectedProjectPath: ensured.lastSelectedProjectPath === normalized ? fallbackProjectPath : ensured.lastSelectedProjectPath,
        projects: {
          ...ensured.projects,
          [normalized]: {
            ...existing,
            hidden: true,
          },
        },
      };
    });
    setOpenProjectMenuPath(null);
  };

  const moveDeletedCurrentSessionToDraft = (deletedSession: SessionSummary) => {
    const projectPath = (
      normalizeWorkspacePath(deletedSession.workspace)
      || selectedProjectPath
      || preferredProjectPath
    );
    if (!projectPath) {
      clearConversationSelection();
      return;
    }

    const nextDraft = buildDraftChatState(projectPath, deletedSession.telegram_bot_config_id ?? scope.defaultTelegramBotConfigId);
    draftChatRef.current = nextDraft;
    resetConversationForDraft(projectPath);
    setDraftChat(nextDraft);
    setSidebarExpanded(true);
  };

  const deleteSidebarSession = async (session: SessionSummary) => {
    if (!session?.id) {
      return;
    }

    setOpenSessionMenuId(null);
    setStatus(`deleting ${session.name}`);
    const deletingCurrentSession = sessionIdRef.current === session.id && !draftChatRef.current;

    try {
      const result = await deleteSession(apiBaseUrl, token, session.id);
      const nextCurrentSessionId = result.current_session_id || null;
      if (deletingCurrentSession) {
        moveDeletedCurrentSessionToDraft(session);
        await refreshSidebarState(null, true);
        setStatus(`new chat in ${projectPathBasename(normalizeWorkspacePath(session.workspace) || selectedProjectPath || preferredProjectPath)}`);
      } else {
        await refreshSidebarState(nextCurrentSessionId, true);
        setStatus('chat deleted');
      }
      pushActivity(`Deleted chat: ${session.name}`, 'accent');
    } catch (error) {
      const message = describeError(error);
      setStatus(message);
      pushActivity(`Delete chat failed: ${message}`, 'error');
    }
  };

  const moveProjectOrder = (draggedProjectPath: string, targetProjectPath: string) => {
    const dragged = normalizeWorkspacePath(draggedProjectPath);
    const target = normalizeWorkspacePath(targetProjectPath);
    if (!dragged || !target || dragged === target) {
      return;
    }
    updateSidebarState((current: any) => {
      const ensured = ensureSidebarProjectEntries(current, [dragged, target]);
      const order = [...ensured.projectOrder.filter((item: any) => item !== dragged)];
      const targetIndex = order.indexOf(target);
      if (targetIndex < 0) {
        order.push(dragged);
      } else {
        order.splice(targetIndex, 0, dragged);
      }
      return {
        ...ensured,
        projectOrder: order,
      };
    });
  };

  const moveSessionOrder = (projectPath: string, draggedSessionId: string, targetSessionId: string) => {
    if (!draggedSessionId || !targetSessionId || draggedSessionId === targetSessionId) {
      return;
    }
    const normalizedProjectPath = normalizeWorkspacePath(projectPath);
    const projectSessions = sessions
      .filter((item: any) => normalizeWorkspacePath(item.workspace) === normalizedProjectPath)
      .sort((left: any, right: any) => sessionSidebarSortComparator(left, right, sidebarState.sessionMeta));
    const order = projectSessions.map((item: any) => item.id).filter((sessionEntryId: any) => sessionEntryId !== draggedSessionId);
    const targetIndex = order.indexOf(targetSessionId);
    if (targetIndex < 0) {
      return;
    }
    order.splice(targetIndex, 0, draggedSessionId);
    updateSidebarState((current: any) => {
      const nextSessionMeta = { ...current.sessionMeta };
      order.forEach((sessionEntryId: any, index: any) => {
        nextSessionMeta[sessionEntryId] = {
          ...(nextSessionMeta[sessionEntryId] || {}),
          order: index,
        };
      });
      return {
        ...current,
        sessionMeta: nextSessionMeta,
      };
    });
  };

  const runControl = async (action: 'pause' | 'stop' | 'restart') => {
    const activeSessionId = requireActiveDesktopSession();
    if (!activeSessionId) return;
    setStatus(`${action} requested`);
    try {
      await controlAgentRun(apiBaseUrl, token, action, activeSessionId);
      if (action === 'stop') {
        setChatRunActive(false);
        setRuntimeRunState('idle');
        setAssistantDraft('');
        setThinking('');
        setTaskBoard(null);
        setOverview((previous: any) => (
          previous
            ? {
                ...previous,
                run_state: 'idle',
                task_board: null,
              }
            : previous
        ));
      }
      pushActivity(`Run control: ${action}`, action === 'stop' ? 'warn' : 'accent');
      await refreshSidebarState(activeSessionId, true);
    } catch (error) {
      setStatus(userFacingError(error, 'Run control did not finish.'));
    }
  };

  const toggleTaskBoardArmNextTurn = async () => {
    const activeSessionId = sessionIdRef.current;
    if (!activeSessionId) {
      setStatus('select a shared chat before arming long task mode');
      return;
    }

    const nextArmed = !taskBoardArmedNextTurn;
    setStatus(nextArmed ? 'arming long task mode for the next message' : 'disarming long task mode');
    try {
      const result = await setTaskBoardArmedNextTurn(apiBaseUrl, token, nextArmed, activeSessionId);
      const armed = Boolean(result.task_board_armed_next_turn);
      setTaskBoardArmedNextTurnState(armed);
      setOverview((previous: any) => (
        previous
          ? {
              ...previous,
              task_board_armed_next_turn: armed,
            }
          : previous
      ));
      setStatus(armed ? 'long task mode armed for the next message' : 'long task mode cleared');
      pushActivity(
        armed
          ? 'Long task mode armed. The next message will open a managed task board.'
          : 'Long task mode cleared. The next message will stay conversational unless it asks for real work.',
        armed ? 'accent' : 'neutral',
      );
    } catch (error) {
      const message = userFacingError(error, 'Long task mode was not updated.');
      setStatus(message);
      pushActivity(message, 'error');
    }
  };

  const toggleKeepRuntimeOnAppClose = async () => {
    const nextValue = !keepRuntimeOnAppClose;
    setSavingCloseBehavior(true);
    setStatus(nextValue ? 'saving keep-alive on desktop close' : 'saving stop-on-close behavior');
    try {
      await updateAgentConfig(
        apiBaseUrl,
        token,
        {
          key: 'channels.desktop.keep_runtime_on_app_close',
          value: nextValue,
        },
        sessionIdRef.current
      );
      setKeepRuntimeOnAppClose(nextValue);
      pushActivity(
        nextValue
          ? 'Desktop close behavior updated: keep the local agent alive after the desktop app closes.'
          : 'Desktop close behavior updated: closing the desktop app will stop the local agent.',
        'accent'
      );
      setStatus(
        nextValue
          ? 'desktop close will keep the local agent alive'
          : 'desktop close will stop the local agent'
      );
    } catch (error) {
      setStatus(userFacingError(error, 'Close behavior was not saved.'));
    } finally {
      setSavingCloseBehavior(false);
    }
  };
  return { isBusySessionSwitchError, isRecoverableSessionActivationError, activateSessionWithRecovery, selectedProjectPathCandidate, selectedProjectPath, preferredProjectPath, preferredFolderPickerPath, emptyConversationProjectPath, emptyConversationProjectName, buildDraftChatState, resetConversationForDraft, clearConversationSelection, resolveAllowedProjectPath, rememberProjectFolder, promptForProjectFolder, automaticProjectParentPath, createAutomaticProjectFolderPath, closeFolderChoice, askForProjectFolderChoice, chooseFolderFromChoice, createAutomaticFolderFromChoice, resolveProjectForNewChatStart, resolveProjectPathForNewChat, openDraftChat, chooseDraftProjectFolder, chooseDraftProject, chooseDraftBranch, chooseDraftTelegramBot, beginNewChat, materializeDraftSession, ensureSessionForOutgoingMessage, openSession, confirmPendingSessionSwitch, dismissPendingSessionSwitch, toggleProjectPin, toggleSessionPin, toggleProjectCollapsed, renameProject, removeProjectFromSidebar, moveDeletedCurrentSessionToDraft, deleteSidebarSession, moveProjectOrder, moveSessionOrder, runControl, toggleTaskBoardArmNextTurn, toggleKeepRuntimeOnAppClose };
}
