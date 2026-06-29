import type { DesktopConversationScope } from './DesktopConversationScope';
import {
  filterModelGroupsByConfiguredProviders,
  filterModelsByConfiguredList,
  modelExistsInGroups,
} from './modelProviders';
import { useEffect } from 'react'; type NativeSyntheticEvent<T = any> = any; type ActiveCommandPanel = any; type ActivityItem = any; type AgentOverview = any; type ArtifactDetail = any; type ArtifactSummary = any; type ComposerInputOrigin = any; type ConversationSurfaceMode = any; type DesktopFleetEnrollment = any; type DesktopFleetIdentity = any; type DesktopFleetSnapshot = any; type DesktopFleetTask = any; type DesktopFleetWorker = any; type DesktopGitRepoState = any; type DesktopMessage = any; type DesktopPathStatus = any; type DesktopRuntimeStatus = any; type DesktopSidebarProjectActivity = any; type DesktopSidebarState = any; type DesktopVoicePackState = any; type DesktopVoiceRuntimeStatus = any; type InterruptPolicy = any; type JarvisSttBackend = any; type JarvisTtsBackend = any; type LayoutChangeEvent = any; type MessageSourceFormat = any; type ModelProviderGroup = any; type NativeScrollEvent = any; type PendingSearchJump = any; type QueuedComposerMessage = any; type QueuedMessage = any; type RealtimeChannel = any; type RealtimeEvent = any; type ReferenceEntry = any; type RuntimeOrchestratorStatus = any; type ScheduledJob = any; type SearchResultTarget = any; type SecurityPermissionMode = any; type SessionDetail = any; type SessionMessage = any; type SessionSearchResult = any; type SessionSummary = any; type SessionTimelineEvent = any; type SidebarChatTooltipState = any; type SidebarDragState = any; type SidebarDraftChat = any; type SidebarProjectGroup = any; type StartupReadinessState = any; type TaskBoard = any; type TelegramBotConfig = any; type TextInputContentSizeChangeEventData = any; type ToolPackInfoPopupState = any; type VoiceCaptureMode = any; type VoiceGateState = any;

export function useDesktopConversationDerivedValues(scope: DesktopConversationScope) {
  const { ALWAYS_ON_VOICE_AUTO_SEND, JARVIS_ENGLISH_VOICE_PATH_ERROR, TOOL_PACK_DEFINITIONS, VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW, VOICE_ENGINE_NONE, activeCommandPanel, activePermissionInfoId, activity, allowedWorkspaceRoot, alwaysOnEnabled, alwaysOnEnabledRef, apiVoiceInputActive, assistantDraft, availableToolPackIdsFrom, cachedModelGroups, cachedPlannerModels, chatRunActive, clampUsagePercent, clearConversationSelection, completedTaskBoards, configuredModelGroups, configuredPlannerModels, conversationMode, defaultToolPackIds, describeError, draftBranchSearch, draftChat, draftGitRepoLoading, draftGitRepoState, draftProjectSearch, enabledToolPackIdsFrom, extractReferenceTitle, fleetSnapshot, formatRelativeTime, formatStatusNumber, formatToolPackLockReasonText, groupPlannerModelsByProvider, hoveredToolPackInfoId, input, isReferenceSidebarMessage, jarvisPulseProgress, jobs, lastAssistantOutputAt, lastVoiceWarmRequestEngineRef, liveVoiceStatus, mergeTimelineEntries, messages, modelProviderKey, normalizeWorkspacePath, onOpenSetup, onSelectVoiceEngine, openSession, orchestratorStatus, overview, pendingDraftSecurityPermissionMode, pendingSessionSwitch, pinnedToolPackInfoId, preferredModelFromGroups, projectDisplayName, projectPathBasename, projectPathHint, projectPathStatuses, pushActivity, queuedComposerMessages, resetVoiceCaptureBuffers, runtimeRunState, runtimeStatus, selectedProjectPath, selectedVoiceEngine, sessionBelongsToFleetIdentity, sessionId, sessionIdRef, sessionName, sessionSidebarSortComparator, sessions, setAlwaysOnEnabled, setExpandedModelProviders, setExpandedPlannerProviders, setStatus, setVoiceEngineChanging, setVoiceError, setVoiceRecording, setVoiceRunning, setVoiceState, shortStatusText, shouldKeepSidebarProjectPath, showVoicePanel, sidebarSearch, sidebarSearchModalOpen, sidebarSearchResults, sidebarState, status, stopVoiceTracks, summarizeReferenceContent, summarizeRuntimeStatus, taskBoard, taskBoardStatusLabel, telegramBotConfigs, thinking, thinkingShineProgress, timelineEvents, toolPackInfoPopup, useEffect, voiceDraft, voiceEngineChanging, voiceError, voicePackState, voicePanelHidden, voiceRecording, voiceRecordingRef, voiceRunning, voiceRunningRef, voiceState, warmSelectedVoicePath, workspaceSortOrder } = scope;
const dueJobs = jobs.filter((job: any) => job.due).length;
  const heartbeatLabel = overview?.heartbeat
    ? `${overview.heartbeat.interval_seconds}s${overview.heartbeat.running ? ' · running' : ''}`
    : 'unknown';
  const runtimeLabel = summarizeRuntimeStatus(runtimeStatus);
  const activeFleetIdentity = (
    fleetSnapshot?.active_identity
    || fleetSnapshot?.identities?.find((identity: any) => identity.identity_id === fleetSnapshot.active_identity_id)
    || null
  );
  const activeFleetIdentityId = activeFleetIdentity?.identity_id || '';
  const visibleSessions = activeFleetIdentity
    ? sessions.filter((item: any) => sessionBelongsToFleetIdentity(item, activeFleetIdentity))
    : sessions;
  const activeFleetIdentitySelectedChatId = activeFleetIdentityId
    ? String(fleetSnapshot?.selected_chat_by_identity?.[activeFleetIdentityId] || '').trim()
    : '';
  const activeFleetIdentityTargetChatId = activeFleetIdentity
    ? activeFleetIdentitySelectedChatId || visibleSessions[0]?.id || ''
    : '';
  const activeSession = sessions.find((item: any) => item.id === sessionId);
  useEffect(() => {
    if (!activeFleetIdentity) {
      return;
    }
    if (draftChat) {
      return;
    }

    const currentSummary = sessionId ? sessions.find((item: any) => item.id === sessionId) || null : null;
    if (currentSummary && sessionBelongsToFleetIdentity(currentSummary, activeFleetIdentity)) {
      return;
    }

    if (activeFleetIdentityTargetChatId) {
      if (activeFleetIdentityTargetChatId !== sessionIdRef.current) {
        void openSession(activeFleetIdentityTargetChatId);
      }
      return;
    }

    if (sessionIdRef.current || messages.length || timelineEvents.length || overview || selectedProjectPath) {
      clearConversationSelection(null, { clearSidebarProject: true });
      setStatus(`Active identity: ${activeFleetIdentity.display_name}`);
    }
  }, [
    activeFleetIdentity,
    activeFleetIdentityTargetChatId,
    draftChat,
    messages.length,
    overview,
    selectedProjectPath,
    sessionId,
    sessions,
    timelineEvents.length,
  ]);
  const setupModelGroups = Array.isArray(configuredModelGroups) ? configuredModelGroups : [];
  const rawModelGroups = overview?.model_groups?.length ? overview.model_groups : cachedModelGroups;
  const draftModelGroups = setupModelGroups.length
    ? filterModelGroupsByConfiguredProviders(rawModelGroups.length ? rawModelGroups : setupModelGroups, setupModelGroups)
    : [];
  const setupPlannerModels = Array.isArray(configuredPlannerModels) ? configuredPlannerModels : [];
  const rawPlannerModels = overview?.available_planner_models?.length ? overview.available_planner_models : cachedPlannerModels;
  const draftPlannerModels = setupPlannerModels.length
    ? filterModelsByConfiguredList(rawPlannerModels.length ? rawPlannerModels : setupPlannerModels, setupPlannerModels)
    : [];
  const defaultTelegramBotConfigId = telegramBotConfigs.find((item: any) => item.is_default)?.id || telegramBotConfigs[0]?.id || null;
  const draftEnabledToolPacks = draftChat?.enabledToolPacks ?? defaultToolPackIds();
  const fallbackCatalogModel = preferredModelFromGroups(draftModelGroups);
  const currentEnabledToolPacks = draftChat
    ? draftEnabledToolPacks
    : Array.isArray(activeSession?.enabled_tool_packs) && activeSession.enabled_tool_packs.length > 0
      ? activeSession.enabled_tool_packs
      : enabledToolPackIdsFrom(overview?.enabled_tool_packs);
  const currentAvailableToolPacks = draftChat
    ? defaultToolPackIds()
    : availableToolPackIdsFrom(activeSession?.available_tool_packs, overview?.available_tool_packs);
  const currentSecurityPermissionMode = String(
    draftChat?.securityPermissionMode
    || (!sessionId && !activeSession ? pendingDraftSecurityPermissionMode : activeSession?.security_permission_mode)
    || 'standard'
  );
  const currentSecurityPermissionLabel = currentSecurityPermissionMode === 'full_permissions'
    ? 'Full access'
    : currentSecurityPermissionMode === 'low'
      ? 'Ask for approval'
      : 'Approve for me';
  const securityPermissionOptions: Array<{
    id: SecurityPermissionMode;
    title: string;
    caption: string;
  }> = [
    {
      id: 'low',
      title: 'Ask for approval',
      caption: 'Ask before app opens, browser navigation, desktop input, and other active computer actions.',
    },
    {
      id: 'standard',
      title: 'Approve for me',
      caption: 'Only ask for actions detected as potentially unsafe.',
    },
    {
      id: 'full_permissions',
      title: 'Full access',
      caption: 'Use the computer freely in this chat. Sensitive actions still require confirmation.',
    },
  ];
  const activePermissionInfo = activePermissionInfoId
    ? securityPermissionOptions.find((mode: any) => mode.id === activePermissionInfoId) || null
    : null;
  const currentLockStatus = (draftChat ? {} : activeSession?.lock_status || overview?.lock_status || {}) as Record<string, any>;
  const currentDisabledPackReasons = (currentLockStatus.disabled_pack_reasons || {}) as Record<string, string>;
  const formatToolPackLockReason = (reason?: string | null) => formatToolPackLockReasonText(reason, sessions);
  const unavailableEnabledToolPackReason = 'Enabled for this chat, but temporarily unavailable while another running chat owns it.';
  const activeToolPackInfoId = toolPackInfoPopup?.packId || pinnedToolPackInfoId || hoveredToolPackInfoId;
  const activeToolPackInfo = activeToolPackInfoId
    ? TOOL_PACK_DEFINITIONS.find((item: any) => item.id === activeToolPackInfoId) || null
    : null;
  const activeToolPackInfoDisabledReason = activeToolPackInfoId
    ? formatToolPackLockReason(currentDisabledPackReasons[activeToolPackInfoId] || null)
    : null;
  const activeToolPackInfoAvailable = activeToolPackInfoId
    ? currentAvailableToolPacks.includes(activeToolPackInfoId)
    : false;
  const activeToolPackInfoConfiguredEnabled = activeToolPackInfoId
    ? currentEnabledToolPacks.includes(activeToolPackInfoId)
    : false;
  const currentHeadlessBlockReason = typeof currentDisabledPackReasons.__headless__ === 'string'
    ? currentDisabledPackReasons.__headless__
    : null;
  const currentSessionTelegramBotConfigId = activeSession?.telegram_bot_config_id || defaultTelegramBotConfigId;
  const currentSessionTelegramBot = telegramBotConfigs.find((item: any) => item.id === currentSessionTelegramBotConfigId) || null;
  const telegramBotLabelForSession = (targetSession: SessionSummary | null | undefined) => {
    const targetBotId = targetSession?.telegram_bot_config_id || defaultTelegramBotConfigId;
    const bot = telegramBotConfigs.find((item: any) => item.id === targetBotId) || null;
    return bot?.label || 'No Telegram bot';
  };
  const currentSessionSleepBotConfigId = currentSessionTelegramBotConfigId || defaultTelegramBotConfigId;
  const currentSleepSessionIdForBot = currentSessionSleepBotConfigId
    ? orchestratorStatus?.default_sleep_session_by_bot?.[currentSessionSleepBotConfigId] || null
    : null;
  const currentSessionIsSleepChat = Boolean(sessionId && currentSleepSessionIdForBot === sessionId);
  const chatSettingsSessionId = activeCommandPanel?.kind === 'session' ? activeCommandPanel.sessionId : null;
  const chatSettingsSession = chatSettingsSessionId
    ? sessions.find((item: any) => item.id === chatSettingsSessionId) || (chatSettingsSessionId === sessionId ? activeSession || null : null)
    : null;
  const permissionSettingsSessionId = activeCommandPanel?.kind === 'permissions' ? activeCommandPanel.sessionId || null : null;
  const permissionSettingsSession = permissionSettingsSessionId
    ? sessions.find((item: any) => item.id === permissionSettingsSessionId) || (permissionSettingsSessionId === sessionId ? activeSession || null : null)
    : null;
  const permissionSettingsIsDraft = activeCommandPanel?.kind === 'permissions' && !permissionSettingsSession;
  const permissionSettingsDraftMode = draftChat?.securityPermissionMode || pendingDraftSecurityPermissionMode || 'standard';
  const chatSettingsBotConfigId = chatSettingsSession?.telegram_bot_config_id || defaultTelegramBotConfigId;
  const chatSettingsSleepSessionId = chatSettingsBotConfigId
    ? orchestratorStatus?.default_sleep_session_by_bot?.[chatSettingsBotConfigId] || null
    : null;
  const pendingSwitchTargetLabel = pendingSessionSwitch?.mode === 'session'
    ? sessions.find((item: any) => item.id === pendingSessionSwitch.sessionId)?.name || 'selected chat'
    : pendingSessionSwitch
      ? `new chat in ${projectPathBasename(pendingSessionSwitch.projectPath)}`
      : null;
  const sessionProjectPaths = new Set(
    visibleSessions
      .map((item: any) => normalizeWorkspacePath(item.workspace))
      .filter(Boolean),
  );
  const projectPaths = Array.from(new Set([
    ...sidebarState.projectOrder.map((item: any) => normalizeWorkspacePath(item)),
    ...Object.keys(sidebarState.projects).map((item: any) => normalizeWorkspacePath(item)),
    ...visibleSessions.map((item: any) => normalizeWorkspacePath(item.workspace)),
    ...(draftChat ? [draftChat.projectPath] : []),
  ].filter(Boolean))).filter((projectPath: any) => shouldKeepSidebarProjectPath(projectPath, {
    allowedRoot: allowedWorkspaceRoot,
    sessionProjectPaths,
    draftProjectPath: draftChat?.projectPath,
  }));
  const projectGroups: SidebarProjectGroup[] = projectPaths
    .map((projectPath: any) => {
      const projectSessions = visibleSessions
        .filter((item: any) => normalizeWorkspacePath(item.workspace) === projectPath)
        .sort((left: any, right: any) => sessionSidebarSortComparator(left, right, sidebarState.sessionMeta));
      const projectState = sidebarState.projects[projectPath] || {};
      const projectPathStatus = projectPathStatuses[projectPath];
      const folderAvailable = projectPathStatus ? Boolean(projectPathStatus.exists && projectPathStatus.isDirectory) : true;
      return {
        path: projectPath,
        label: projectDisplayName(projectPath, projectState),
        hint: folderAvailable ? projectPathHint(projectPath) : `Folder unavailable · ${projectPathHint(projectPath)}`,
        pinned: Boolean(projectState.pinned),
        collapsed: Boolean(projectState.collapsed),
        folderAvailable,
        activity: Array.isArray(projectState.recentActivity) ? projectState.recentActivity : [],
        sessions: projectSessions,
        matchesSearch: true,
      };
    })
    .filter((group: any) => !Boolean(sidebarState.projects[group.path]?.hidden))
    .sort((left: any, right: any) => {
      if (left.pinned !== right.pinned) {
        return left.pinned ? -1 : 1;
      }
      const leftOrder = workspaceSortOrder(sidebarState.projectOrder, left.path);
      const rightOrder = workspaceSortOrder(sidebarState.projectOrder, right.path);
      if (leftOrder !== rightOrder) {
        return leftOrder - rightOrder;
      }
      if (left.folderAvailable !== right.folderAvailable) {
        return left.folderAvailable ? -1 : 1;
      }
      return left.label.localeCompare(right.label);
    });
  const pinnedProjects = projectGroups.filter((group: any) => group.pinned);
  const pinnedChats = projectGroups.flatMap((group: any) => (
    group.sessions
      .filter((item: any) => Boolean(sidebarState.sessionMeta[item.id]?.pinned))
      .map((item: any) => ({ session: item, project: group }))
  ));
  const sidebarSearchQuery = sidebarSearch.trim();
  const sidebarSearchOpen = sidebarSearchModalOpen;
  const mergedSidebarSearchResults = sidebarSearchResults.filter((item: any) => item.kind !== 'project');
  const recentSearchSessions = visibleSessions.slice(0, 8);
  const contextUsage = overview?.context_usage || null;
  const contextPercent = clampUsagePercent(contextUsage?.usage_percent);
  const contextPercentLabel = contextUsage
    ? `${contextPercent.toFixed(contextPercent >= 10 ? 0 : 1)}%`
    : 'loading';
  const contextTokenLabel = contextUsage
    ? `${formatStatusNumber(contextUsage.estimated_tokens)} / ${formatStatusNumber(contextUsage.max_tokens)}`
    : 'loading';
  const contextStateLabel = contextUsage
    ? [
        contextUsage.compaction_state === 'needs_compaction'
          ? 'Needs Compact'
          : contextUsage.compaction_state === 'compacted'
            ? 'Compacted'
            : 'OK',
        contextUsage.token_strategy ? contextUsage.token_strategy : null,
        typeof contextUsage.tool_schema_count === 'number' && contextUsage.tool_schema_count > 0
          ? `${formatStatusNumber(contextUsage.tool_schema_count)} tools`
          : null,
      ].filter(Boolean).join(' · ')
    : 'loading';
  const currentModelCandidate = String(
    (draftChat ? draftChat.model : overview?.current_model || activeSession?.model) || '',
  ).trim();
  const currentModelLabel = currentModelCandidate && modelExistsInGroups(currentModelCandidate, draftModelGroups)
    ? currentModelCandidate
    : fallbackCatalogModel || 'Choose model';
  const currentVariantLabel = draftChat?.variant
    ? ` · ${draftChat.variant}`
    : overview?.current_variant
      ? ` · ${overview.current_variant}`
      : '';
  const currentPlannerCandidate = String(
    (draftChat ? draftChat.plannerModel : overview?.planner_model) || '',
  ).trim();
  const currentPlannerLabel = (
    !currentPlannerCandidate
    || currentPlannerCandidate === 'auto'
    || draftPlannerModels.includes(currentPlannerCandidate)
  )
    ? currentPlannerCandidate || 'auto'
    : 'auto';
  const plannerModelGroups = groupPlannerModelsByProvider(draftPlannerModels, draftModelGroups);
  const currentModelProviderKey = modelProviderKey(
    draftModelGroups.find((group: any) => group.models.includes(currentModelLabel))?.provider,
  );
  const currentPlannerProviderKey = currentPlannerLabel === 'auto'
    ? ''
    : modelProviderKey(plannerModelGroups.find((group: any) => group.models.includes(currentPlannerLabel))?.provider);
  useEffect(() => {
    if (activeCommandPanel?.kind !== 'model') {
      setExpandedModelProviders({});
      setExpandedPlannerProviders({});
      return;
    }
    setExpandedModelProviders((current: any) => (
      Object.keys(current).length
        ? current
        : currentModelProviderKey
          ? { [currentModelProviderKey]: true }
          : {}
    ));
    setExpandedPlannerProviders((current: any) => (
      Object.keys(current).length
        ? current
        : currentPlannerProviderKey
          ? { [currentPlannerProviderKey]: true }
          : {}
    ));
  }, [activeCommandPanel?.kind, currentModelProviderKey, currentPlannerProviderKey]);
  const draftFolderLabel = projectPathBasename(draftChat?.projectPath || '') || 'Choose folder';
  const showFolderComposerMeta = Boolean(draftChat) || (!sessionId && !selectedProjectPath);
  const draftBranchChoices = Array.isArray(draftGitRepoState?.branches) ? draftGitRepoState.branches : [];
  const normalizedDraftProjectSearch = draftProjectSearch.trim().toLowerCase();
  const normalizedDraftBranchSearch = draftBranchSearch.trim().toLowerCase();
  const filteredDraftProjects = projectGroups.filter((group: any) => (
    !normalizedDraftProjectSearch
    || group.label.toLowerCase().includes(normalizedDraftProjectSearch)
    || group.path.toLowerCase().includes(normalizedDraftProjectSearch)
    || group.hint.toLowerCase().includes(normalizedDraftProjectSearch)
  ));
  const filteredDraftBranchChoices = draftBranchChoices.filter((branchName: any) => (
    !normalizedDraftBranchSearch || branchName.toLowerCase().includes(normalizedDraftBranchSearch)
  ));
  const draftBranchLabel = draftGitRepoLoading
    ? 'Loading branch'
    : draftChat?.selectedBranch
      ? draftChat.selectedBranch
      : draftGitRepoState?.isGitRepo
        ? draftGitRepoState.currentBranch || 'Choose branch'
        : 'No git repo';
  const draftTelegramBotConfigId = draftChat?.telegramBotConfigId || defaultTelegramBotConfigId;
  const draftTelegramBot = telegramBotConfigs.find((bot: any) => bot.id === draftTelegramBotConfigId) || null;
  const draftTelegramBotLabel = draftTelegramBot?.label || 'No Telegram bot';
  const contextUsageRatio = Math.max(0, Math.min(1, contextPercent / 100));
  const contextBreakdownLabel = contextUsage
    ? [
        typeof contextUsage.system_prompt_tokens === 'number' && contextUsage.system_prompt_tokens > 0
          ? `sys ${formatStatusNumber(contextUsage.system_prompt_tokens)}`
          : null,
        typeof contextUsage.injected_context_tokens === 'number' && contextUsage.injected_context_tokens > 0
          ? `ctx ${formatStatusNumber(contextUsage.injected_context_tokens)}`
          : null,
        typeof contextUsage.tool_schema_tokens === 'number' && contextUsage.tool_schema_tokens > 0
          ? `tools ${formatStatusNumber(contextUsage.tool_schema_tokens)}`
          : null,
        typeof contextUsage.chat_history_tokens === 'number' && contextUsage.chat_history_tokens > 0
          ? `chat ${formatStatusNumber(contextUsage.chat_history_tokens)}`
          : null,
      ].filter(Boolean).join(' · ')
    : '';
  const contextUsageHoverLabel = contextUsage
    ? `Live prompt ${contextTokenLabel} · ${contextPercentLabel}${contextBreakdownLabel ? ` · ${contextBreakdownLabel}` : ''}`
    : 'Context loading';
  const activeTaskBoard = runtimeRunState === 'running' && taskBoard?.status === 'active' ? taskBoard : null;
  const taskBoardStatusText = taskBoardStatusLabel(activeTaskBoard?.status);
  const taskBoardUpdatedLabel = activeTaskBoard?.updated_at ? formatRelativeTime(activeTaskBoard.updated_at) : null;
  const taskBoardSummary = activeTaskBoard?.status === 'completed'
    ? activeTaskBoard?.completion_summary || activeTaskBoard?.progress_summary || activeTaskBoard?.latest_summary || null
    : activeTaskBoard?.progress_summary || activeTaskBoard?.latest_summary || null;
  const taskBoardTone = activeTaskBoard?.status === 'completed'
    ? 'complete'
    : activeTaskBoard?.status === 'blocked' || activeTaskBoard?.pending_reassessment_reason
      ? 'warn'
      : 'active';
  const hasCompletedTaskBoards = completedTaskBoards.length > 0;
  const voiceSummary = alwaysOnEnabled
    ? voiceRecording
      ? `${voiceState} · always-on segment`
      : voiceRunning
        ? `${voiceState} · processing`
        : 'always-on listening'
    : voiceRecording
      ? `${voiceState} · push-to-talk`
      : voiceRunning
        ? `${voiceState} · processing`
        : voiceState;
  const extendedVoiceStatus = liveVoiceStatus as (DesktopVoiceRuntimeStatus & {
    english_pack_manifest?: Record<string, unknown> | null;
    english_pack_manifest_verified?: boolean;
    hebrew_pack_manifest?: Record<string, unknown> | null;
    hebrew_pack_manifest_verified?: boolean;
  }) | null;
  const voicePacks = voicePackState?.packs ?? [];
  const englishVoicePack = voicePacks.find((pack: any) => pack.id === VOICE_ENGINE_ENGLISH) ?? null;
  const hebrewVoicePack = voicePacks.find((pack: any) => pack.id === VOICE_ENGINE_HEBREW) ?? null;
  const selectedVoicePack = voicePacks.find((pack: any) => pack.id === selectedVoiceEngine) ?? null;
  const selectedVoiceEngineState = String(extendedVoiceStatus?.selected_engine_state || '').trim().toLowerCase();
  const selectedVoiceManifest = selectedVoiceEngine === VOICE_ENGINE_ENGLISH
    ? (extendedVoiceStatus?.english_pack_manifest ?? null)
    : selectedVoiceEngine === VOICE_ENGINE_HEBREW
      ? (extendedVoiceStatus?.hebrew_pack_manifest ?? null)
      : null;
  const selectedVoiceManifestVerified = selectedVoiceEngine === VOICE_ENGINE_ENGLISH
    ? Boolean(extendedVoiceStatus?.english_pack_manifest_verified)
    : selectedVoiceEngine === VOICE_ENGINE_HEBREW
      ? Boolean(extendedVoiceStatus?.hebrew_pack_manifest_verified)
      : false;
  const selectedVoicePackProvenance = selectedVoiceManifestVerified
    ? String(
        selectedVoiceManifest?.['asset_name']
        || selectedVoiceManifest?.['pack_id']
        || selectedVoiceManifest?.['tuning_preset']
        || selectedVoiceManifest?.['repo_id']
        || 'verified pack',
      )
    : null;
  const selectedVoicePackModel = extendedVoiceStatus?.stt_model || selectedVoicePack?.path || null;
  const selectedVoicePackPath = selectedVoicePack?.path || null;
  const selectedVoicePackSummary = apiVoiceInputActive
    ? `Realtime voice input ready${selectedVoicePackModel ? ` · ${selectedVoicePackModel}` : ''}`
    : selectedVoiceEngine === VOICE_ENGINE_NONE
    ? 'Voice input is off. Open setup to re-enable a local path.'
    : selectedVoiceEngineState === 'warming'
      ? `Warming ${selectedVoicePack?.title || 'selected voice path'} so it is fully ready before capture starts.`
    : selectedVoicePack?.available
      ? `${selectedVoicePack.title} ready${selectedVoicePackModel ? ` · ${selectedVoicePackModel}` : ''}${selectedVoicePackProvenance ? ` · ${selectedVoicePackProvenance}` : ''}`
      : `${selectedVoicePack?.title || 'Selected voice path'} is not installed yet. Open setup to install it.`;
  const voicePackDiagnostics = apiVoiceInputActive
    ? null
    : selectedVoicePack?.available && selectedVoicePackPath
      ? `Installed pack path: ${selectedVoicePackPath}${selectedVoiceManifestVerified ? ' · verified pack' : ''}`
      : extendedVoiceStatus?.issues?.[0] || null;
  const activitySummary = activity.length ? `${activity.length} recent events` : 'No recent runtime events';
  const referenceEntries = (messages as any[]).reduce<ReferenceEntry[]>((items: any, message: any, index: any) => {
    if (!isReferenceSidebarMessage(message, sessionName)) {
      return items;
    }

    const fallbackTitle = sessionName || `Reference ${items.length + 1}`;
    items.push({
      id: `${message.timestamp || 'reference'}-${index}`,
      index,
      title: extractReferenceTitle(message.content, fallbackTitle),
      summary: summarizeReferenceContent(message.content),
      message,
    });
    return items;
  }, []);
  const referenceIndexSet = new Set(referenceEntries.map((entry: any) => entry.index));
  const transcriptEntries = (messages as any[]).reduce<Array<{ fullIndex: number; message: DesktopMessage }>>((items: any, message: any, index: any) => {
    if (!referenceIndexSet.has(index)) {
      items.push({ fullIndex: index, message });
    }
    return items;
  }, []);
  const transcriptTimelineEvents = timelineEvents.filter((event: any) => (
    event.kind === 'tool'
    || event.kind === 'command'
    || (event.kind === 'runtime' && (event.tone === 'warn' || event.tone === 'error'))
  ));
  const verboseModeOn = Boolean(overview?.verbose_mode);
  const timelineEntries = mergeTimelineEntries(
    messages.map((message: any, index: any) => ({ fullIndex: index, message })),
    timelineEvents,
  );
  const transcriptTimelineEntries = mergeTimelineEntries(transcriptEntries, transcriptTimelineEvents);
  const historySummary = timelineEntries.length === 1
    ? '1 timeline item'
    : `${timelineEntries.length} timeline items`;
  const referenceSummary = referenceEntries.length === 1
    ? referenceEntries[0].title
    : `${referenceEntries.length} saved reference notes`;
  const referenceRailKey = `${sessionId || 'none'}:${referenceEntries.length}`;
  const isJarvisMode = conversationMode === 'jarvis';
  const isFleetMode = conversationMode === 'fleet';
  const isDraftConversationEmpty = Boolean(
    transcriptTimelineEntries.length === 0
    && referenceEntries.length === 0
    && !assistantDraft
    && !activeTaskBoard
    && !hasCompletedTaskBoards
  );
  const voiceBannerRequested = Boolean(voiceDraft)
    || Boolean(voiceError)
    || alwaysOnEnabled
    || voiceRecording
    || voiceRunning
    || ['connecting', 'reconnecting', 'error', 'warming'].includes(voiceState)
    || (!apiVoiceInputActive && selectedVoiceEngineState === 'warming');
  const suppressPassiveJarvisVoiceBannerOnDraft = Boolean(
    isDraftConversationEmpty
    && !isJarvisMode
    && !voiceDraft
    && !voiceRecording
    && !voiceRunning
    && (
      voiceError === JARVIS_ENGLISH_VOICE_PATH_ERROR
      || alwaysOnEnabled
      || voiceState === 'warming'
      || (!apiVoiceInputActive && selectedVoiceEngineState === 'warming')
    )
  );
  const showVoiceBanner = voiceBannerRequested && !suppressPassiveJarvisVoiceBannerOnDraft;
  const alwaysOnVoiceAutoSend = isJarvisMode || ALWAYS_ON_VOICE_AUTO_SEND;
  const voicePanelActive = !voicePanelHidden && (
    showVoicePanel
    || Boolean(voiceDraft)
    || Boolean(voiceError)
    || alwaysOnEnabled
    || voiceRecording
    || voiceRunning
  );
  const isCenteredDraftComposerStage = isDraftConversationEmpty;
  const agentRunActive = runtimeRunState === 'running' || chatRunActive || Boolean(assistantDraft) || Boolean(thinking);
  const shouldShowThinkingIndicator = agentRunActive && (lastAssistantOutputAt === null || Date.now() - lastAssistantOutputAt > 1200);
  const thinkingShineTranslate = thinkingShineProgress.interpolate({
    inputRange: [0, 1],
    outputRange: [-64, 100],
  });
  const thinkingTextCounterTranslate = thinkingShineProgress.interpolate({
    inputRange: [0, 1],
    outputRange: [64, -100],
  });
  const jarvisPulseScale = jarvisPulseProgress.interpolate({
    inputRange: [0, 1],
    outputRange: [0.94, 1.14],
  });
  const jarvisPulseOpacity = jarvisPulseProgress.interpolate({
    inputRange: [0, 1],
    outputRange: [0.22, 0.58],
  });
  const hasComposerText = input.trim().length > 0;
  const currentSessionQueuedMessages = queuedComposerMessages.filter((item: any) => item.sessionId === sessionId);
  const queuedComposerMessagesDisplay = [...currentSessionQueuedMessages].reverse();
  const sendButtonMode = agentRunActive
    ? hasComposerText ? 'interrupt' : 'stop'
    : hasComposerText ? 'send' : 'idle';
  const sendButtonGlyph = sendButtonMode === 'stop'
    ? '■'
    : sendButtonMode === 'interrupt'
      ? '↪'
      : '↑';
  const voiceBannerText = voiceError
    ? shortStatusText(voiceError)
      : voiceDraft
      ? voiceDraft
      : (!apiVoiceInputActive && selectedVoiceEngineState === 'warming') || voiceState === 'warming'
        ? apiVoiceInputActive
          ? 'Warming realtime voice input and assistant audio.'
          : 'Warming the Hebrew voice path so the local pass-3 model is fully ready before capture starts.'
      : alwaysOnEnabled && voiceRecording
        ? alwaysOnVoiceAutoSend
          ? apiVoiceInputActive
            ? 'Always-on voice detected speech. Realtime transcription is streaming and will send when the gate closes.'
            : 'Always-on voice detected speech. Local Whisper is drafting the transcript and will send when the gate closes.'
          : apiVoiceInputActive
            ? 'Always-on voice detected speech. Realtime transcription is streaming and will place the final text in the message box.'
            : 'Always-on voice detected speech. Local Whisper is drafting the transcript and will place the final text in the message box.'
      : alwaysOnEnabled
        ? alwaysOnVoiceAutoSend
          ? apiVoiceInputActive
            ? 'Always-on realtime voice is listening. Speech above the gate threshold will be transcribed and sent automatically.'
            : 'Always-on voice is listening locally. Speech above the gate threshold will be transcribed and sent automatically.'
          : apiVoiceInputActive
            ? 'Always-on realtime voice is listening. Speech above the gate threshold will become editable text before you send it.'
            : 'Always-on voice is listening locally. Speech above the gate threshold will become editable text before you send it.'
      : voiceRecording
        ? 'Push-to-talk is live. Keep holding to continue transcribing and release to send.'
        : voiceState === 'finalizing'
          ? 'Finishing the voice transcript and sending it through the shared session.'
          : voiceState === 'generating'
            ? 'Generating the assistant reply for the voice transcript.'
            : voiceState === 'synthesizing'
              ? 'Preparing assistant audio.'
              : voiceState === 'speaking'
                ? 'Playing assistant audio.'
      : voiceState === 'ready'
        ? apiVoiceInputActive
          ? 'Hold the push-to-talk button or switch to always-on realtime voice.'
          : 'Hold the push-to-talk button or switch to always-on local Whisper.'
        : `Voice ${voiceState}`;
  const handleVoiceEngineSelection = async (engine: typeof VOICE_ENGINE_ENGLISH | typeof VOICE_ENGINE_HEBREW) => {
    const targetPack = engine === VOICE_ENGINE_HEBREW ? hebrewVoicePack : englishVoicePack;
    if (voiceEngineChanging) {
      return;
    }
    if (voiceRecording || voiceRunning) {
      setVoiceError('Finish the current voice capture before switching paths.');
      pushActivity('Finish the current voice capture before switching paths.', 'warn');
      return;
    }
    if (!targetPack?.available) {
      const message = `${engine === VOICE_ENGINE_HEBREW ? 'Hebrew' : 'English'} voice pack is not ready yet. Open setup to install it.`;
      setVoiceError(message);
      pushActivity(message, 'warn');
      onOpenSetup?.();
      return;
    }
    if (selectedVoiceEngine === engine) {
      return;
    }

    setVoiceEngineChanging(true);
    setVoiceError(null);
    alwaysOnEnabledRef.current = false;
    setAlwaysOnEnabled(false);
    stopVoiceTracks();
    resetVoiceCaptureBuffers({ clearProgrammaticComposerInput: true });
    voiceRunningRef.current = false;
    voiceRecordingRef.current = false;
    setVoiceRunning(false);
    setVoiceRecording(false);
    lastVoiceWarmRequestEngineRef.current = null;
    if (engine === VOICE_ENGINE_HEBREW) {
      setVoiceState('warming');
      setStatus('warming Hebrew voice path');
    }
    try {
      const switched = await onSelectVoiceEngine?.(engine);
      if (switched === false) {
        setVoiceError('Voice path did not switch.');
        setVoiceState('error');
      } else if (engine === VOICE_ENGINE_HEBREW) {
        await warmSelectedVoicePath(engine);
      } else {
        await warmSelectedVoicePath(engine);
      }
    } catch (error) {
      const message = describeError(error);
      setVoiceError(message);
      setVoiceState('error');
      pushActivity(`Voice path switch failed: ${message}`, 'error');
    } finally {
      setVoiceEngineChanging(false);
    }
  };
  return { dueJobs, heartbeatLabel, runtimeLabel, activeFleetIdentity, activeFleetIdentityId, visibleSessions, activeFleetIdentitySelectedChatId, activeFleetIdentityTargetChatId, activeSession, draftModelGroups, draftPlannerModels, defaultTelegramBotConfigId, draftEnabledToolPacks, fallbackCatalogModel, currentEnabledToolPacks, currentAvailableToolPacks, currentSecurityPermissionMode, currentSecurityPermissionLabel, securityPermissionOptions, activePermissionInfo, currentLockStatus, currentDisabledPackReasons, formatToolPackLockReason, unavailableEnabledToolPackReason, activeToolPackInfoId, activeToolPackInfo, activeToolPackInfoDisabledReason, activeToolPackInfoAvailable, activeToolPackInfoConfiguredEnabled, currentHeadlessBlockReason, currentSessionTelegramBotConfigId, currentSessionTelegramBot, telegramBotLabelForSession, currentSessionSleepBotConfigId, currentSleepSessionIdForBot, currentSessionIsSleepChat, chatSettingsSessionId, chatSettingsSession, permissionSettingsSessionId, permissionSettingsSession, permissionSettingsIsDraft, permissionSettingsDraftMode, chatSettingsBotConfigId, chatSettingsSleepSessionId, pendingSwitchTargetLabel, sessionProjectPaths, projectPaths, projectGroups, pinnedProjects, pinnedChats, sidebarSearchQuery, sidebarSearchOpen, mergedSidebarSearchResults, recentSearchSessions, contextUsage, contextPercent, contextPercentLabel, contextTokenLabel, contextStateLabel, currentModelLabel, currentVariantLabel, currentPlannerLabel, plannerModelGroups, currentModelProviderKey, currentPlannerProviderKey, draftFolderLabel, showFolderComposerMeta, draftBranchChoices, normalizedDraftProjectSearch, normalizedDraftBranchSearch, filteredDraftProjects, filteredDraftBranchChoices, draftBranchLabel, draftTelegramBotConfigId, draftTelegramBot, draftTelegramBotLabel, contextUsageRatio, contextBreakdownLabel, contextUsageHoverLabel, activeTaskBoard, taskBoardStatusText, taskBoardUpdatedLabel, taskBoardSummary, taskBoardTone, hasCompletedTaskBoards, voiceSummary, extendedVoiceStatus, voicePacks, englishVoicePack, hebrewVoicePack, selectedVoicePack, selectedVoiceEngineState, selectedVoiceManifest, selectedVoiceManifestVerified, selectedVoicePackProvenance, selectedVoicePackModel, selectedVoicePackPath, selectedVoicePackSummary, voicePackDiagnostics, activitySummary, referenceEntries, referenceIndexSet, transcriptEntries, transcriptTimelineEvents, verboseModeOn, timelineEntries, transcriptTimelineEntries, historySummary, referenceSummary, referenceRailKey, isJarvisMode, isFleetMode, isDraftConversationEmpty, voiceBannerRequested, suppressPassiveJarvisVoiceBannerOnDraft, showVoiceBanner, alwaysOnVoiceAutoSend, voicePanelActive, isCenteredDraftComposerStage, agentRunActive, shouldShowThinkingIndicator, thinkingShineTranslate, thinkingTextCounterTranslate, jarvisPulseScale, jarvisPulseOpacity, hasComposerText, currentSessionQueuedMessages, queuedComposerMessagesDisplay, sendButtonMode, sendButtonGlyph, voiceBannerText, handleVoiceEngineSelection };
}
