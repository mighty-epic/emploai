import type { DesktopConversationScope } from './DesktopConversationScope';
import { DesktopModelPickerMenu } from './DesktopModelPickerMenu';
import { DesktopFleetWorkspace } from './DesktopFleetWorkspace';
import { DesktopFleetInfoButton } from './DesktopFleetInfoButton';
import { fleetReportSummary, fleetWorkerStatusLabel } from './desktopFleetWorkerState';
import { useEffect } from 'react'; type NativeSyntheticEvent<T = any> = any; type ActiveCommandPanel = any; type ActivityItem = any; type AgentOverview = any; type ArtifactDetail = any; type ArtifactSummary = any; type ComposerInputOrigin = any; type ConversationSurfaceMode = any; type DesktopFleetEnrollment = any; type DesktopFleetIdentity = any; type DesktopFleetSnapshot = any; type DesktopFleetTask = any; type DesktopFleetWorker = any; type DesktopGitRepoState = any; type DesktopMessage = any; type DesktopPathStatus = any; type DesktopRuntimeStatus = any; type DesktopSidebarProjectActivity = any; type DesktopSidebarState = any; type DesktopVoicePackState = any; type DesktopVoiceRuntimeStatus = any; type InterruptPolicy = any; type JarvisSttBackend = any; type JarvisTtsBackend = any; type LayoutChangeEvent = any; type MessageSourceFormat = any; type ModelProviderGroup = any; type NativeScrollEvent = any; type PendingSearchJump = any; type QueuedComposerMessage = any; type QueuedMessage = any; type RealtimeChannel = any; type RealtimeEvent = any; type ReferenceEntry = any; type RuntimeOrchestratorStatus = any; type ScheduledJob = any; type SearchResultTarget = any; type SecurityPermissionMode = any; type SessionDetail = any; type SessionMessage = any; type SessionSearchResult = any; type SessionSummary = any; type SessionTimelineEvent = any; type SidebarChatTooltipState = any; type SidebarDragState = any; type SidebarDraftChat = any; type SidebarProjectGroup = any; type StartupReadinessState = any; type TaskBoard = any; type TelegramBotConfig = any; type TextInputContentSizeChangeEventData = any; type ToolPackInfoPopupState = any; type VoiceCaptureMode = any; type VoiceGateState = any;
import { useReducedMotion } from './useReducedMotion';

export function useDesktopConversationDerivedTail(scope: DesktopConversationScope) {
  const reducedMotion = useReducedMotion();
  const { Animated, DESKTOP_COMMAND_SUGGESTIONS, Easing, JARVIS_ENGLISH_VOICE_PATH_ERROR, MAX_COMMAND_SUGGESTIONS, MonoIcon, Platform, Pressable, ScrollView, TOOL_PACK_DEFINITIONS, Text, TextInput, VOICE_ENGINE_ENGLISH, View, activeCommandPanel, activeFleetIdentity, activeToolPackInfo, activeToolPackInfoAvailable, activeToolPackInfoConfiguredEnabled, activeToolPackInfoDisabledReason, activeToolPackInfoId, activity, agentRunActive, alwaysOnEnabled, alwaysOnEnabledRef, apiBaseUrl, apiVoiceInputActive, artifacts, assignFleetGroupTask, assignFleetTask, assistantDraft, attachmentUploadInFlight, beginNewChat, chooseDraftBranch, chooseDraftProject, chooseDraftProjectFolder, chooseDraftTelegramBot, chooseModel, choosePlannerModel, chooseVariant, closeSidebarSearchModal, commandSuggestionMenuRef, composerTextRegionRef, continueFleetQueue, conversationMode, copyFleetEnrollmentToken, createFleetEnrollment, createFleetGroupFromFirstWorker, createFleetLocalWorker, currentAvailableToolPacks, currentDisabledPackReasons, currentEnabledToolPacks, currentHeadlessBlockReason, currentJarvisSttLabel, currentModelLabel, currentPlannerLabel, currentVariant, currentVariantHasControls, currentVariantLabel, currentVariantOptions, deleteFleetGroup, describeError, dismissedCommandSuggestionInput, draftBranchSearch, draftBranchTriggerRef, draftChat, draftGitRepoLoading, draftGitRepoState, draftModelGroups, draftProjectSearch, draftProjectTriggerRef, draftTelegramBotConfigId, draftTelegramTriggerRef, dragState, englishVoicePack, expandedModelProviders, expandedPlannerProviders, externalSidebarToggleSignalRef, fetchSessionArtifactBlob, fetchSessionArtifactDetail, fetchSessionArtifacts, filteredDraftBranchChoices, filteredDraftProjects, fleetChatPanelWidth, fleetDashboardCollapsed, fleetEnrollment, fleetError, fleetGroupNameDraft, fleetGroupTaskDrafts, fleetLoading, fleetRenameDrafts, fleetSnapshot, fleetStatus, fleetTaskDrafts, fleetWorkerNameDraft, floatingPanelRef, formatAbsoluteTime, formatToolPackLockReason, getCommandSuggestionQuery, handleComposerInputChange, handleComposerKeyPress, handleVoiceEngineSelection, hideToolPackInfoPopup, input, isJarvisMode, jarvisHoldToTalkMode, jarvisLatestSpokenText, jarvisLatestTranscript, jarvisMuted, jarvisPulseProgress, jarvisPushToTalkActiveRef, jarvisSpaceHotkeyActiveRef, jarvisTtsBackendLabel, jarvisWarmRequestedRef, labelForMessage, lastAssistantOutputAt, liveVoiceStatus, modelTriggerRef, moveProjectOrder, moveSessionOrder, normalizeWorkspacePath, openComposerAttachmentPicker, openFleetWorkerMenuId, openProjectMenuPath, openSession, openSessionMenuId, permissionsTriggerRef, pinnedToolPackInfoId, plannerModelGroups, projectMenuRefs, projectMenuTriggerRefs, queueMessage, queuedComposerMessages, queuedComposerMessagesDisplay, referenceAutoOpenKeyRef, referenceDismissedKeyRef, referenceEntries, referenceRailKey, renameFleetWorker, requestFleetPreview, resetFleetWorker, resetFleetWorkerIdentity, revealProjectInSidebar, runControl, scheduleHideToolPackInfoPopup, selectFleetIdentity, selectedArtifactId, selectedVoiceEngine, selectedVoiceEngineState, sendButtonGlyph, sendButtonMode, sendQueuedComposerSlice, sendText, sessionId, sessionIdRef, sessionMenuRefs, sessionMenuTriggerRefs, sessions, setActiveCommandPanel, setArtifactDetailLoading, setArtifactError, setArtifacts, setArtifactsLoading, setDismissedCommandSuggestionInput, setDraftBranchSearch, setDraftProjectSearch, setDragState, setExpandedModelProviders, setExpandedPlannerProviders, setFleetChatPanelCollapsed, setFleetDashboardCollapsed, setFleetGroupNameDraft, setFleetGroupTaskDrafts, setFleetRenameDrafts, setFleetTaskDrafts, setFleetWorkerNameDraft, setHoveredToolPackInfoId, setJarvisHoldToTalkMode, setJarvisMuted, setJarvisStatusDrawerOpen, setJarvisVoiceSettingsOpen, setOpenFleetWorkerMenuId, setOpenProjectMenuPath, setOpenSessionMenuId, setPinnedToolPackInfoId, setQueuedComposerMessages, setSelectedArtifactDetail, setSelectedArtifactId, setShowArtifactRail, setShowReferenceRail, setShowVoicePanel, setSidebarExpanded, setSidebarSearchModalOpen, setStatus, setToolPackInfoButtonRef, setVoiceError, setVoiceMode, setVoicePanelHidden, setVoiceState, shortStatusText, shouldShowThinkingIndicator, showArtifactRail, showToolPackInfoPopup, sidebarExpanded, sidebarSearchLauncherRef, sidebarSearchModalOpen, sidebarSearchModalRef, sidebarToggleSignal, startAlwaysOnVoice, startJarvisPushToTalk, status, stopAllFleetWorkers, stopAlwaysOnVoice, stopFleetWorker, stopJarvisPushToTalk, styles, telegramBotConfigs, thinkingShineProgress, timelineEntries, toggleCurrentSessionToolPack, token, toolPackMutationInFlight, toolsTriggerRef, transcriptEntries, unavailableEnabledToolPackReason, useEffect, userFacingError, voiceDraft, voiceEngineChanging, voiceRecording, voiceRecordingRef, voiceRunning, voiceRunningRef, voiceState, warmSelectedVoicePath } = scope;
  const jarvisWakeProfileReady = Boolean(scope.jarvisWakeProfileReady);
  const setJarvisWakeEnrollmentOpen = scope.setJarvisWakeEnrollmentOpen as ((value: boolean) => void) | undefined;
useEffect(() => {
    const animate = !reducedMotion && conversationMode === 'jarvis' && (alwaysOnEnabled || voiceRecording || voiceRunning);
    jarvisPulseProgress.stopAnimation();
    jarvisPulseProgress.setValue(0);
    if (!animate) {
      return;
    }
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(jarvisPulseProgress, {
          toValue: 1,
          duration: voiceRecording ? 620 : 1100,
          easing: Easing.inOut(Easing.cubic),
          useNativeDriver: true,
        }),
        Animated.timing(jarvisPulseProgress, {
          toValue: 0,
          duration: voiceRecording ? 520 : 940,
          easing: Easing.inOut(Easing.cubic),
          useNativeDriver: true,
        }),
      ]),
    );
    animation.start();
    return () => {
      animation.stop();
      jarvisPulseProgress.stopAnimation();
      jarvisPulseProgress.setValue(0);
    };
  }, [alwaysOnEnabled, conversationMode, jarvisPulseProgress, reducedMotion, voiceRecording, voiceRunning]);

  useEffect(() => {
    if (conversationMode !== 'jarvis') {
      jarvisWarmRequestedRef.current = false;
      setJarvisStatusDrawerOpen(false);
      setJarvisVoiceSettingsOpen(false);
      setJarvisWakeEnrollmentOpen?.(false);
      setJarvisMuted(false);
      setJarvisHoldToTalkMode(false);
      setVoiceError((current: any) => (current === JARVIS_ENGLISH_VOICE_PATH_ERROR ? null : current));
      if (alwaysOnEnabledRef.current) {
        void stopAlwaysOnVoice();
      }
      return;
    }

    setActiveCommandPanel(null);
    setShowVoicePanel(false);
    setVoicePanelHidden(true);

    if (!apiVoiceInputActive && selectedVoiceEngine !== VOICE_ENGINE_ENGLISH) {
      if (englishVoicePack?.available && !voiceEngineChanging) {
        void handleVoiceEngineSelection(VOICE_ENGINE_ENGLISH);
      } else {
        setVoiceError(JARVIS_ENGLISH_VOICE_PATH_ERROR);
        setStatus('Jarvis needs the English voice path');
      }
      return;
    }

    if (liveVoiceStatus?.tts_enabled !== false && !jarvisWarmRequestedRef.current) {
      jarvisWarmRequestedRef.current = true;
      void warmSelectedVoicePath(apiVoiceInputActive ? selectedVoiceEngine : VOICE_ENGINE_ENGLISH).catch((error: any) => {
        const message = describeError(error);
        setVoiceError(message);
        setVoiceState('error');
        setStatus(message);
      });
    }

    if (jarvisHoldToTalkMode) {
      setVoiceMode('push_to_talk');
      if (!jarvisMuted) {
        setJarvisMuted(true);
      }
      if (alwaysOnEnabledRef.current && !jarvisPushToTalkActiveRef.current) {
        void stopAlwaysOnVoice();
      }
      return;
    }

    setVoiceMode('always_on');

    if (!jarvisWakeProfileReady) {
      setJarvisWakeEnrollmentOpen?.(true);
      setStatus('Train a local wake phrase before using Jarvis always-on listening');
      if (alwaysOnEnabledRef.current) {
        void stopAlwaysOnVoice();
      }
      return;
    }

    if (
      !jarvisMuted
      && !jarvisPushToTalkActiveRef.current
      && !alwaysOnEnabledRef.current
      && !voiceRunningRef.current
      && !voiceRecordingRef.current
      && voiceState !== 'connecting'
      && voiceState !== 'reconnecting'
      && voiceState !== 'error'
    ) {
      void startAlwaysOnVoice();
    }
  }, [
    conversationMode,
    apiVoiceInputActive,
    englishVoicePack?.available,
    jarvisHoldToTalkMode,
    jarvisMuted,
    selectedVoiceEngine,
    sessionId,
    token,
    liveVoiceStatus?.tts_enabled,
    liveVoiceStatus?.tts_ready,
    jarvisWakeProfileReady,
    voiceEngineChanging,
    voiceRecording,
    voiceRunning,
    voiceState,
  ]);

  useEffect(() => {
    if (!isJarvisMode || !jarvisHoldToTalkMode) {
      if (jarvisSpaceHotkeyActiveRef.current) {
        jarvisSpaceHotkeyActiveRef.current = false;
        void stopJarvisPushToTalk();
      }
      return;
    }
    if (Platform.OS !== 'web' || typeof globalThis.window === 'undefined') {
      return;
    }

    const isEditableTarget = (target: EventTarget | null) => {
      const element = target as HTMLElement | null;
      const tagName = String(element?.tagName || '').toLowerCase();
      return Boolean(
        element?.isContentEditable
        || tagName === 'input'
        || tagName === 'textarea'
        || tagName === 'select',
      );
    };
    const isSpaceKey = (event: KeyboardEvent) => event.code === 'Space' || event.key === ' ';
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!isSpaceKey(event) || event.repeat || !jarvisHoldToTalkMode || isEditableTarget(event.target)) {
        return;
      }
      event.preventDefault();
      if (jarvisSpaceHotkeyActiveRef.current) {
        return;
      }
      jarvisSpaceHotkeyActiveRef.current = true;
      void startJarvisPushToTalk();
    };
    const handleKeyUp = (event: KeyboardEvent) => {
      if (!isSpaceKey(event) || !jarvisHoldToTalkMode || isEditableTarget(event.target)) {
        return;
      }
      event.preventDefault();
      if (!jarvisSpaceHotkeyActiveRef.current) {
        return;
      }
      jarvisSpaceHotkeyActiveRef.current = false;
      void stopJarvisPushToTalk();
    };

    globalThis.window.addEventListener('keydown', handleKeyDown);
    globalThis.window.addEventListener('keyup', handleKeyUp);
    return () => {
      globalThis.window.removeEventListener('keydown', handleKeyDown);
      globalThis.window.removeEventListener('keyup', handleKeyUp);
    };
  }, [isJarvisMode, jarvisHoldToTalkMode, startJarvisPushToTalk, stopJarvisPushToTalk]);

  const historyAvailable = Boolean(timelineEntries.length || referenceEntries.length);
  const activeSessionArtifactCount = Number(
    sessions.find((item: any) => item.id === sessionId)?.artifact_count
    || sessions.find((item: any) => item.id === sessionIdRef.current)?.artifact_count
    || 0,
  );
  const selectedArtifactSummary = artifacts.find((item: any) => item.artifact_id === selectedArtifactId) || artifacts[0] || null;
  const commandSuggestionQuery = getCommandSuggestionQuery(input);
  const commandSuggestions = commandSuggestionQuery == null || dismissedCommandSuggestionInput === input
    ? []
    : DESKTOP_COMMAND_SUGGESTIONS.filter((suggestion: any) => (
      !commandSuggestionQuery
      || suggestion.name.startsWith(commandSuggestionQuery)
      || suggestion.name.includes(commandSuggestionQuery)
    )).slice(0, MAX_COMMAND_SUGGESTIONS);
  const floatingPanelKind = activeCommandPanel?.kind === 'model'
    ? 'model'
    : activeCommandPanel?.kind === 'tools'
      ? 'tools'
      : activeCommandPanel?.kind === 'permissions'
        ? 'permissions'
      : activeCommandPanel?.kind === 'draftProject'
        ? 'draftProject'
      : activeCommandPanel?.kind === 'draftBranch'
        ? 'draftBranch'
      : activeCommandPanel?.kind === 'draftTelegram'
        ? 'draftTelegram'
      : activeCommandPanel?.kind === 'session'
        ? 'session'
        : null;
  const floatingMenuKinds: Array<NonNullable<ActiveCommandPanel>['kind']> = ['model', 'tools', 'permissions', 'draftProject', 'draftBranch', 'draftTelegram', 'session'];
  const hasDismissibleFloatingPanel = floatingPanelKind != null && floatingMenuKinds.includes(floatingPanelKind);
  const floatingPanelPrefersBelow = floatingPanelKind === 'draftProject' || floatingPanelKind === 'draftBranch' || floatingPanelKind === 'draftTelegram';
  const activeToolsPanelSource = activeCommandPanel?.kind === 'tools' ? activeCommandPanel.source || 'main' : null;
  const shouldRenderGlobalFloatingPanel = floatingPanelKind != null && !floatingPanelPrefersBelow && activeToolsPanelSource !== 'fleet';
  const floatingPanelPositionStyle = floatingPanelKind === 'tools'
    ? styles.commandPanelFloatingTools
    : floatingPanelKind === 'permissions'
      ? styles.commandPanelFloatingPermissions
      : floatingPanelKind === 'model'
        ? styles.commandPanelFloatingModel
        : styles.commandPanelFloatingRight;
  const pendingRunMode = scope.pendingRunMode as 'plan' | 'goal' | 'normal' | null | undefined;
  const planMode = (scope.planMode && typeof scope.planMode === 'object') ? scope.planMode as Record<string, any> : null;
  const activeGoal = (scope.activeGoal && typeof scope.activeGoal === 'object') ? scope.activeGoal as Record<string, any> : null;
  const setPendingRunMode = scope.setPendingRunMode as ((mode: 'plan' | 'goal' | 'normal' | null) => void) | undefined;
  const exitPlanMode = scope.exitPlanMode as (() => void | Promise<void>) | undefined;
  const clearActiveGoal = scope.clearActiveGoal as (() => void | Promise<void>) | undefined;
  const toolPackCommandPanelContent = (
    <>
      <View style={styles.commandPanelHeader}>
        <View style={styles.commandPanelHeaderCopy}>
          <View style={styles.commandPanelHeaderLine}>
            <Text style={styles.commandPanelCompactTitle}>Add + Tools</Text>
            <Pressable
              style={styles.commandPanelInfoButton}
              accessibilityRole="button"
              accessibilityLabel="Add and tools information"
              accessibilityHint="Attach files or photos, then choose the packs this chat can use."
              {...(Platform.OS === 'web' ? ({ title: 'Attach files or photos, then choose the packs this chat can use.' } as any) : {})}
            >
              <MonoIcon name="info" style={styles.commandPanelInfoIcon} />
            </Pressable>
          </View>
          {currentHeadlessBlockReason ? (
            <Text style={styles.commandPanelWarningText}>{currentHeadlessBlockReason}</Text>
          ) : null}
        </View>
        <Pressable style={styles.commandPanelCloseButton} onPress={() => setActiveCommandPanel(null)}>
          <Text style={styles.commandPanelCloseText}>Close</Text>
        </Pressable>
      </View>
      <ScrollView style={styles.modelPickerScroll} contentContainerStyle={styles.modelPickerContent}>
        <View style={styles.composerAttachmentSection}>
          <Text style={styles.modelPickerSectionTitle}>Mode</Text>
          <View style={styles.composerModeActionGrid}>
            <Pressable
              style={({ hovered }: any) => [
                styles.composerModeAction,
                hovered ? styles.composerModeActionHovered : null,
                pendingRunMode === 'plan' || planMode ? styles.composerModeActionActive : null,
              ]}
              onPress={() => {
                setPendingRunMode?.('plan');
                setActiveCommandPanel(null);
              }}
            >
              <Text style={styles.composerModeActionTitle}>Plan</Text>
              <Text style={styles.composerModeActionText}>Inspect, ask, and produce a plan before edits.</Text>
            </Pressable>
            <Pressable
              style={({ hovered }: any) => [
                styles.composerModeAction,
                hovered ? styles.composerModeActionHovered : null,
                pendingRunMode === 'goal' ? styles.composerModeActionActive : null,
                activeGoal ? styles.composerModeActionDisabled : null,
              ]}
              disabled={Boolean(activeGoal)}
              onPress={() => {
                setPendingRunMode?.('goal');
                setActiveCommandPanel(null);
              }}
            >
              <Text style={styles.composerModeActionTitle}>Goal</Text>
              <Text style={styles.composerModeActionText}>
                {activeGoal ? 'A goal is already active in this chat.' : 'Keep pursuing this objective until done.'}
              </Text>
            </Pressable>
          </View>
        </View>
        <View style={styles.composerAttachmentSection}>
          <Text style={styles.modelPickerSectionTitle}>Attach</Text>
          <Pressable
            style={({ hovered }: any) => [
              styles.composerAttachmentAction,
              hovered ? styles.composerAttachmentActionHovered : null,
              attachmentUploadInFlight ? styles.composerAttachmentActionDisabled : null,
            ]}
            disabled={attachmentUploadInFlight}
            onPress={openComposerAttachmentPicker}
          >
            <Text style={styles.composerAttachmentIcon}>+</Text>
            <Text style={styles.composerAttachmentActionTitle} numberOfLines={1}>
              Attach file or photo
            </Text>
          </Pressable>
        </View>
        <View style={styles.toolPackCompactList}>
          {TOOL_PACK_DEFINITIONS.map((pack: any) => {
            const configuredEnabled = currentEnabledToolPacks.includes(pack.id);
            const available = currentAvailableToolPacks.includes(pack.id);
            const lockReason = configuredEnabled
              ? formatToolPackLockReason(currentDisabledPackReasons[pack.id] || null)
                || (!available ? unavailableEnabledToolPackReason : null)
              : null;
            const locked = Boolean(lockReason);
            const enabled = configuredEnabled && available && !locked;
            const infoVisible = activeToolPackInfoId === pack.id;
            return (
              <View key={`tool-pack-${pack.id}`} style={styles.toolPackCompactGroup}>
                <View
                  style={[
                    styles.toolPackCompactRow,
                    enabled ? styles.toolPackCompactRowEnabled : null,
                    locked ? styles.toolPackCompactRowUnavailable : null,
                  ]}
                >
                  <Text
                    style={[
                      styles.toolPackCompactLabel,
                      enabled ? styles.toolPackCompactLabelEnabled : null,
                      locked ? styles.toolPackCompactLabelUnavailable : null,
                    ]}
                    numberOfLines={1}
                  >
                    {pack.label}
                  </Text>
                  <View style={styles.toolPackCompactActions}>
                    <Pressable
                      ref={setToolPackInfoButtonRef(pack.id)}
                      onHoverIn={() => showToolPackInfoPopup(pack.id)}
                      onHoverOut={() => scheduleHideToolPackInfoPopup(pack.id)}
                      onPress={() => {
                        if (pinnedToolPackInfoId === pack.id) {
                          hideToolPackInfoPopup(pack.id);
                          return;
                        }
                        showToolPackInfoPopup(pack.id, { pinned: true });
                      }}
                      style={({ hovered }: any) => [
                        styles.toolPackInfoButton,
                        hovered ? styles.toolPackInfoButtonHovered : null,
                        infoVisible ? styles.toolPackInfoButtonActive : null,
                      ]}
                    >
                      <MonoIcon
                        name="info"
                        style={[
                          styles.toolPackInfoIcon,
                          infoVisible ? styles.toolPackInfoIconActive : null,
                        ]}
                      />
                    </Pressable>
                    <Pressable
                      style={[
                        styles.toolPackSwitch,
                        enabled ? styles.toolPackSwitchActive : null,
                        toolPackMutationInFlight === pack.id ? styles.toolPackSwitchSaving : null,
                        locked ? styles.toolPackSwitchDisabled : null,
                      ]}
                      onPress={() => void toggleCurrentSessionToolPack(pack.id)}
                      disabled={toolPackMutationInFlight === pack.id}
                    >
                      <View
                        style={[
                          styles.toolPackSwitchKnob,
                          enabled ? styles.toolPackSwitchKnobActive : null,
                        ]}
                      />
                    </Pressable>
                  </View>
                </View>
              </View>
            );
          })}
        </View>
      </ScrollView>
    </>
  );
  const draftProjectCommandPanel = (
    <View
      ref={activeCommandPanel?.kind === 'draftProject' ? floatingPanelRef : null}
      style={[styles.commandPanel, styles.commandPanelFloating, styles.draftChoiceCommandPanel, styles.draftComposerInlineDropdown]}
    >
      <View style={styles.draftChoiceSearchShell}>
        <MonoIcon name="search" style={styles.draftChoiceSearchGlyph} />
        <TextInput
          style={styles.draftChoiceSearchInput}
          value={draftProjectSearch}
          onChangeText={setDraftProjectSearch}
          placeholder="Search folders"
          placeholderTextColor="#7d889d"
        />
      </View>
      <Text style={styles.draftChoiceSectionLabel}>Folders</Text>
      {filteredDraftProjects.length ? (
        <ScrollView style={styles.draftChoiceScroll} contentContainerStyle={styles.draftChoiceList}>
          {filteredDraftProjects.map((project: any) => {
            const selected = normalizeWorkspacePath(draftChat?.projectPath) === project.path;
            return (
              <Pressable
                key={`draft-project-${project.path}`}
                style={({ hovered }: any) => [
                  styles.draftChoiceRow,
                  hovered ? styles.draftChoiceRowHovered : null,
                  selected ? styles.draftChoiceRowSelected : null,
                ]}
                onPress={() => chooseDraftProject(project.path)}
              >
                <MonoIcon
                  name={selected ? 'folder_open' : 'folder_closed'}
                  style={[styles.draftChoiceRowIcon, selected ? styles.draftChoiceRowIconSelected : null]}
                />
                <Text
                  style={[styles.draftChoiceRowTitle, selected ? styles.draftChoiceRowTitleSelected : null]}
                  numberOfLines={1}
                >
                  {project.label}
                </Text>
                {selected ? <MonoIcon name="check" style={styles.draftChoiceRowCheck} /> : null}
              </Pressable>
            );
          })}
        </ScrollView>
      ) : (
        <View style={styles.commandPanelEmpty}>
          <Text style={styles.commandPanelEmptyTitle}>No folders found</Text>
          <Text style={styles.commandPanelEmptyText}>
            Try a different search or add another folder for draft chats.
          </Text>
        </View>
      )}
      <View style={styles.draftChoiceFooter}>
        <Pressable
          style={({ hovered }: any) => [
            styles.draftChoiceFooterAction,
            hovered ? styles.draftChoiceFooterActionHovered : null,
          ]}
          onPress={() => void chooseDraftProjectFolder()}
        >
          <MonoIcon name="plus" style={styles.draftChoiceFooterActionIcon} />
          <Text style={styles.draftChoiceFooterActionText}>Add folder…</Text>
        </Pressable>
      </View>
    </View>
  );
  const draftBranchCommandPanel = (
    <View
      ref={activeCommandPanel?.kind === 'draftBranch' ? floatingPanelRef : null}
      style={[styles.commandPanel, styles.commandPanelFloating, styles.draftChoiceCommandPanel, styles.draftComposerInlineDropdown]}
    >
      <View style={styles.draftChoiceSearchShell}>
        <MonoIcon name="search" style={styles.draftChoiceSearchGlyph} />
        <TextInput
          style={styles.draftChoiceSearchInput}
          value={draftBranchSearch}
          onChangeText={setDraftBranchSearch}
          placeholder="Search branches"
          placeholderTextColor="#7d889d"
        />
      </View>
      <Text style={styles.draftChoiceSectionLabel}>Branches</Text>
      {draftGitRepoLoading ? (
        <View style={styles.commandPanelEmpty}>
          <Text style={styles.commandPanelEmptyTitle}>Loading branches</Text>
          <Text style={styles.commandPanelEmptyText}>
            Checking the selected folder for Git branches.
          </Text>
        </View>
      ) : draftGitRepoState?.isGitRepo && filteredDraftBranchChoices.length ? (
        <ScrollView style={styles.draftChoiceScroll} contentContainerStyle={styles.draftChoiceList}>
          {filteredDraftBranchChoices.map((branchName: any) => {
            const selected = branchName === (draftChat?.selectedBranch || draftGitRepoState.currentBranch);
            return (
              <Pressable
                key={`draft-branch-${branchName}`}
                style={({ hovered }: any) => [
                  styles.draftChoiceRow,
                  hovered ? styles.draftChoiceRowHovered : null,
                  selected ? styles.draftChoiceRowSelected : null,
                ]}
                onPress={() => chooseDraftBranch(branchName)}
              >
                <MonoIcon
                  name="branch"
                  style={[styles.draftChoiceRowIcon, selected ? styles.draftChoiceRowIconSelected : null]}
                />
                <Text
                  style={[styles.draftChoiceRowTitle, selected ? styles.draftChoiceRowTitleSelected : null]}
                  numberOfLines={1}
                >
                  {branchName}
                </Text>
                {selected ? <MonoIcon name="check" style={styles.draftChoiceRowCheck} /> : null}
              </Pressable>
            );
          })}
        </ScrollView>
      ) : draftGitRepoState?.isGitRepo ? (
        <View style={styles.commandPanelEmpty}>
          <Text style={styles.commandPanelEmptyTitle}>No branches found</Text>
          <Text style={styles.commandPanelEmptyText}>
            This repository did not report any selectable local branches.
          </Text>
        </View>
      ) : (
        <View style={styles.commandPanelEmpty}>
          <Text style={styles.commandPanelEmptyTitle}>No Git repo here</Text>
          <Text style={styles.commandPanelEmptyText}>
            Choose a repository folder if you want this chat to start from a specific branch.
          </Text>
        </View>
      )}
    </View>
  );
  const draftTelegramCommandPanel = (
    <View
      ref={activeCommandPanel?.kind === 'draftTelegram' ? floatingPanelRef : null}
      style={[styles.commandPanel, styles.commandPanelFloating, styles.draftChoiceCommandPanel, styles.draftComposerInlineDropdown]}
    >
      <Text style={styles.draftChoiceSectionLabel}>Telegram bots</Text>
      <ScrollView style={styles.draftChoiceScroll} contentContainerStyle={styles.draftChoiceList}>
        {telegramBotConfigs.map((bot: any) => {
          const selected = bot.id === draftTelegramBotConfigId;
          return (
            <Pressable
              key={`draft-telegram-${bot.id}`}
              style={({ hovered }: any) => [
                styles.draftChoiceRow,
                hovered ? styles.draftChoiceRowHovered : null,
                selected ? styles.draftChoiceRowSelected : null,
              ]}
              onPress={() => chooseDraftTelegramBot(bot.id)}
            >
              <MonoIcon
                name="telegram"
                style={[styles.draftChoiceRowIcon, selected ? styles.draftChoiceRowIconSelected : null]}
              />
              <View style={styles.draftChoiceRowCopy}>
                <Text
                  style={[styles.draftChoiceRowTitle, selected ? styles.draftChoiceRowTitleSelected : null]}
                  numberOfLines={1}
                >
                  {bot.label}
                </Text>
                <Text style={styles.draftChoiceRowSubtitle} numberOfLines={1}>{bot.bot_token}</Text>
              </View>
              {selected ? <MonoIcon name="check" style={styles.draftChoiceRowCheck} /> : null}
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );

  useEffect(() => {
    if (Platform.OS !== 'web') {
      return;
    }
    const hasDismissibleSurface = Boolean(
      openProjectMenuPath
      || openSessionMenuId
      || sidebarSearchModalOpen
      || hasDismissibleFloatingPanel
      || commandSuggestions.length,
    );
    if (!hasDismissibleSurface || typeof document === 'undefined') {
      return;
    }

    const containsTarget = (node: any, target: EventTarget | null) => {
      if (!node || !target || typeof node.contains !== 'function') {
        return false;
      }
      return node.contains(target);
    };

    const handlePointerAway = (event: MouseEvent) => {
      const target = event.target;
      const boundaries = [
        openProjectMenuPath ? projectMenuRefs.current[openProjectMenuPath] : null,
        openProjectMenuPath ? projectMenuTriggerRefs.current[openProjectMenuPath] : null,
        openSessionMenuId ? sessionMenuRefs.current[openSessionMenuId] : null,
        openSessionMenuId ? sessionMenuTriggerRefs.current[openSessionMenuId] : null,
        hasDismissibleFloatingPanel ? floatingPanelRef.current : null,
        activeCommandPanel?.kind === 'model' ? modelTriggerRef.current : null,
        activeCommandPanel?.kind === 'tools' ? toolsTriggerRef.current : null,
        activeCommandPanel?.kind === 'permissions' ? permissionsTriggerRef.current : null,
        activeCommandPanel?.kind === 'draftProject' ? draftProjectTriggerRef.current : null,
        activeCommandPanel?.kind === 'draftBranch' ? draftBranchTriggerRef.current : null,
        activeCommandPanel?.kind === 'draftTelegram' ? draftTelegramTriggerRef.current : null,
        sidebarSearchModalOpen ? sidebarSearchModalRef.current : null,
        sidebarSearchModalOpen ? sidebarSearchLauncherRef.current : null,
        commandSuggestions.length ? commandSuggestionMenuRef.current : null,
        commandSuggestions.length ? composerTextRegionRef.current : null,
      ];

      if (boundaries.some((node: any) => containsTarget(node, target))) {
        return;
      }

      setOpenProjectMenuPath(null);
      setOpenSessionMenuId(null);
      if (sidebarSearchModalOpen) {
        setSidebarSearchModalOpen(false);
      }
      if (hasDismissibleFloatingPanel) {
        setActiveCommandPanel((current: any) => (
          current && floatingMenuKinds.includes(current.kind) ? null : current
        ));
      }
      if (commandSuggestions.length) {
        setDismissedCommandSuggestionInput(input);
      }
    };

    document.addEventListener('mousedown', handlePointerAway, true);
    return () => {
      document.removeEventListener('mousedown', handlePointerAway, true);
    };
  }, [
    activeCommandPanel,
    commandSuggestions.length,
    hasDismissibleFloatingPanel,
    input,
    openProjectMenuPath,
    openSessionMenuId,
    sidebarSearchModalOpen,
  ]);

  useEffect(() => {
    if (activeCommandPanel?.kind === 'tools') {
      return;
    }
    setHoveredToolPackInfoId(null);
    setPinnedToolPackInfoId(null);
  }, [activeCommandPanel]);

  useEffect(() => {
    thinkingShineProgress.stopAnimation();
    thinkingShineProgress.setValue(0);
    if (!shouldShowThinkingIndicator || reducedMotion) {
      return;
    }
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(thinkingShineProgress, {
          toValue: 1,
          duration: 1320,
          easing: Easing.inOut(Easing.cubic),
          useNativeDriver: true,
        }),
        Animated.delay(120),
      ]),
    );
    animation.start();
    return () => {
      animation.stop();
      thinkingShineProgress.stopAnimation();
      thinkingShineProgress.setValue(0);
    };
  }, [reducedMotion, shouldShowThinkingIndicator, thinkingShineProgress]);

  useEffect(() => {
    if (agentRunActive || !sessionId) {
      return;
    }
    const nextQueuedMessage = queuedComposerMessages.find((item: any) => item.sessionId === sessionId);
    if (!nextQueuedMessage) {
      return;
    }
    setQueuedComposerMessages((current: any) => current.filter((item: any) => item.id !== nextQueuedMessage.id));
    queueMessage(nextQueuedMessage.text, nextQueuedMessage.sourceFormat, nextQueuedMessage.sessionId, 'none', nextQueuedMessage.modeOptions);
  }, [agentRunActive, queuedComposerMessages, sessionId]);

  useEffect(() => {
    if (!referenceEntries.length) {
      referenceAutoOpenKeyRef.current = null;
      referenceDismissedKeyRef.current = null;
      setShowReferenceRail(false);
      return;
    }

    if (
      referenceAutoOpenKeyRef.current === referenceRailKey
      || referenceDismissedKeyRef.current === referenceRailKey
    ) {
      return;
    }

    referenceAutoOpenKeyRef.current = referenceRailKey;
    setSidebarExpanded(true);
    setShowReferenceRail(true);
  }, [referenceEntries.length, referenceRailKey]);

  const openReferenceRail = () => {
    referenceDismissedKeyRef.current = null;
    setSidebarExpanded(true);
    setShowReferenceRail(true);
    setShowArtifactRail(true);
    void refreshArtifacts(sessionIdRef.current);
  };

  const closeReferenceRail = () => {
    referenceDismissedKeyRef.current = referenceRailKey;
    setShowReferenceRail(false);
  };

  async function refreshArtifacts(targetSessionId?: string | null) {
    const effectiveSessionId = String(targetSessionId || sessionIdRef.current || '').trim();
    if (!effectiveSessionId) {
      setArtifacts([]);
      setSelectedArtifactId(null);
      setSelectedArtifactDetail(null);
      return;
    }
    setArtifactsLoading(true);
    setArtifactError(null);
    try {
      const nextArtifacts = await fetchSessionArtifacts(apiBaseUrl, token, effectiveSessionId);
      setArtifacts(Array.isArray(nextArtifacts) ? nextArtifacts : []);
      setSelectedArtifactId((current: any) => {
        if (current && nextArtifacts.some((item: any) => item.artifact_id === current)) {
          return current;
        }
        return nextArtifacts[0]?.artifact_id || null;
      });
    } catch (error) {
      setArtifactError(userFacingError(error, 'Artifacts did not load.'));
    } finally {
      setArtifactsLoading(false);
    }
  }

  const openArtifactRail = () => {
    setSidebarExpanded(true);
    setShowArtifactRail(true);
    void refreshArtifacts(sessionIdRef.current);
  };

  const closeArtifactRail = () => {
    setShowArtifactRail(false);
  };

  const openArtifactPreview = async (artifactId: string) => {
    const effectiveSessionId = String(sessionIdRef.current || '').trim();
    if (!effectiveSessionId || !artifactId) {
      return;
    }
    setSelectedArtifactId(artifactId);
    setArtifactDetailLoading(true);
    setArtifactError(null);
    try {
      const detail = await fetchSessionArtifactDetail(apiBaseUrl, token, effectiveSessionId, artifactId);
      setSelectedArtifactDetail(detail);
    } catch (error) {
      setArtifactError(userFacingError(error, 'Artifact did not open.'));
    } finally {
      setArtifactDetailLoading(false);
    }
  };

  const openArtifactExternally = async (artifactId: string) => {
    const effectiveSessionId = String(sessionIdRef.current || '').trim();
    if (!effectiveSessionId || !artifactId || Platform.OS !== 'web') {
      return;
    }
    try {
      const payload = await fetchSessionArtifactBlob(apiBaseUrl, token, effectiveSessionId, artifactId);
      const objectUrl = window.URL.createObjectURL(payload.blob);
      window.open(objectUrl, '_blank', 'noopener,noreferrer');
      window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 60_000);
    } catch (error) {
      setArtifactError(userFacingError(error, 'Artifact did not open.'));
    }
  };

  const downloadArtifact = async (artifactId: string) => {
    const effectiveSessionId = String(sessionIdRef.current || '').trim();
    if (!effectiveSessionId || !artifactId || Platform.OS !== 'web') {
      return;
    }
    try {
      const payload = await fetchSessionArtifactBlob(apiBaseUrl, token, effectiveSessionId, artifactId);
      const objectUrl = window.URL.createObjectURL(payload.blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = payload.filename || `${artifactId}.bin`;
      anchor.rel = 'noopener noreferrer';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 60_000);
    } catch (error) {
      setArtifactError(userFacingError(error, 'Artifact did not download.'));
    }
  };

  const openSearchResult = async (target: SearchResultTarget) => {
    if (target.kind === 'project') {
      revealProjectInSidebar(target.projectPath);
      closeSidebarSearchModal();
      return;
    }

    closeSidebarSearchModal();
    await openSession(target.sessionId, {
      projectPath: target.projectPath,
      jumpMessageIndex: target.kind === 'message' ? target.messageIndex : null,
    });
  };

  const closeSidebar = () => {
    setSidebarExpanded(false);
  };

  useEffect(() => {
    if (!showArtifactRail) {
      return;
    }
    void refreshArtifacts(sessionId);
  }, [showArtifactRail, sessionId, lastAssistantOutputAt]);

  useEffect(() => {
    if (!showArtifactRail || !selectedArtifactId) {
      setSelectedArtifactDetail(null);
      return;
    }
    void openArtifactPreview(selectedArtifactId);
  }, [showArtifactRail, selectedArtifactId, sessionId]);

  const toggleSidebar = () => {
    if (sidebarExpanded) {
      closeSidebar();
      return;
    }
    setSidebarExpanded(true);
  };

  useEffect(() => {
    if (typeof sidebarToggleSignal !== 'number') {
      return;
    }
    if (externalSidebarToggleSignalRef.current === sidebarToggleSignal) {
      return;
    }
    externalSidebarToggleSignalRef.current = sidebarToggleSignal;
    toggleSidebar();
  }, [sidebarToggleSignal]);

  const beginHorizontalResize = (
    event: any,
    options: {
      startWidth: number;
      minWidth: number;
      maxWidth: number;
      invert?: boolean;
      setWidth: (width: number) => void;
    },
  ) => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') {
      return;
    }
    const startX = Number(event?.nativeEvent?.clientX ?? event?.nativeEvent?.pageX ?? event?.clientX ?? 0);
    if (!Number.isFinite(startX)) {
      return;
    }
    const clampWidth = (value: number) => Math.max(options.minWidth, Math.min(options.maxWidth, Math.round(value)));
    const handleMove = (moveEvent: MouseEvent) => {
      const nextX = Number((moveEvent as any).clientX ?? 0);
      if (!Number.isFinite(nextX)) {
        return;
      }
      const delta = nextX - startX;
      const nextWidth = options.startWidth + (options.invert ? -delta : delta);
      options.setWidth(clampWidth(nextWidth));
    };
    const handleEnd = () => {
      window.removeEventListener('mousemove', handleMove, true);
      window.removeEventListener('mouseup', handleEnd, true);
    };
    window.addEventListener('mousemove', handleMove, true);
    window.addEventListener('mouseup', handleEnd, true);
  };

  const projectDragProps = (projectPath: string) => {
    if (Platform.OS !== 'web') {
      return {};
    }
    return {
      draggable: true,
      onDragStart: () => setDragState({ kind: 'project', projectPath }),
      onDragOver: (event: any) => event.preventDefault(),
      onDrop: (event: any) => {
        event.preventDefault();
        if (dragState?.kind === 'project') {
          moveProjectOrder(dragState.projectPath, projectPath);
        }
        setDragState(null);
      },
      onDragEnd: () => setDragState(null),
    } as any;
  };

  const sessionDragProps = (projectPath: string, sessionEntryId: string) => {
    if (Platform.OS !== 'web') {
      return {};
    }
    return {
      draggable: true,
      onDragStart: () => setDragState({ kind: 'chat', projectPath, sessionId: sessionEntryId }),
      onDragOver: (event: any) => event.preventDefault(),
      onDrop: (event: any) => {
        event.preventDefault();
        if (dragState?.kind === 'chat' && dragState.projectPath === projectPath) {
          moveSessionOrder(projectPath, dragState.sessionId, sessionEntryId);
        }
        setDragState(null);
      },
      onDragEnd: () => setDragState(null),
    } as any;
  };

  const jarvisCircleMuted = jarvisMuted && !voiceRecording;
  const jarvisMuteButtonMuted = (jarvisHoldToTalkMode || jarvisMuted) && !voiceRecording;
  const jarvisTtsSummary = liveVoiceStatus?.tts_enabled === false
    ? 'TTS off'
    : liveVoiceStatus?.tts_ready
      ? `${jarvisTtsBackendLabel(liveVoiceStatus.tts_backend)} ready`
      : liveVoiceStatus?.tts_issues?.[0] || 'TTS warming';
  const jarvisInputSummary = liveVoiceStatus?.input_ok === false
    ? liveVoiceStatus?.issues?.[0] || 'Voice input needs attention'
    : `${currentJarvisSttLabel} ready`;
  const jarvisVoiceActivityPattern = /voice|speech|microphone|assistant audio|audio playback|always-on|push-to-talk|hold to talk|tts|no speech detected/i;
  const jarvisToolActivity = activity
    .filter((item: any) => !jarvisVoiceActivityPattern.test(item.text))
    .slice(0, 8);
  const jarvisToolSummary = jarvisToolActivity[0]?.text || 'No tool output yet.';
  const jarvisTranscriptOutput = voiceDraft.trim() || jarvisLatestTranscript || 'No transcript yet.';
  const jarvisSpokenOutput = jarvisLatestSpokenText || 'No spoken output yet.';
  const jarvisPushToTalkDisabled = Boolean(
    !apiBaseUrl
    || !token
    || voiceEngineChanging
    || liveVoiceStatus?.input_ok === false
    || (!apiVoiceInputActive && selectedVoiceEngineState === 'warming')
    || voiceState === 'connecting'
    || voiceState === 'reconnecting'
    || (voiceRunning && !voiceRecording)
  );
  const jarvisHoldCaptureDisabled = Boolean(!jarvisHoldToTalkMode || (jarvisPushToTalkDisabled && !voiceRecording));
  const jarvisHoldCaptureValue = voiceRecording
    ? 'Release to send'
    : voiceRunning
      ? 'Processing'
      : jarvisPushToTalkDisabled
        ? 'Unavailable'
        : jarvisHoldToTalkMode
          ? 'Hold to speak'
          : 'Arm mode first';
  const jarvisHoldCaptureDetail = voiceRecording
    ? 'Mic open'
    : voiceRunning
      ? 'Transcribing'
      : jarvisHoldToTalkMode
        ? 'Space or button'
        : 'Muted until armed';
  const fleetIdentities = fleetSnapshot?.identities || [];
  const fleetWorkers = fleetSnapshot?.workers || [];
  const fleetManagerDesktopId = String((fleetSnapshot?.manager as any)?.desktop_id || '');
  const fleetLocalWorkers = fleetWorkers.filter((worker: any) => (
    !fleetManagerDesktopId || String(worker.machine_desktop_id || '') === fleetManagerDesktopId
  ));
  const fleetTasks = fleetSnapshot?.tasks || [];
  const fleetReports = fleetSnapshot?.reports || [];
  const fleetGroups = fleetSnapshot?.groups || [];
  const fleetActiveTaskStatuses = new Set(['running', 'paused', 'blocked', 'needs_review']);
  const fleetSelectedChatIdForWorker = (worker: DesktopFleetWorker) => {
    const selectedByIdentity = fleetSnapshot?.selected_chat_by_identity || {};
    const candidateIdentityIds = [
      worker.instance_id,
      ...fleetIdentities
        .filter((identity: any) => identity.worker_id === worker.worker_id)
        .map((identity: any) => identity.identity_id),
    ].filter(Boolean);
    for (const identityId of Array.from(new Set(candidateIdentityIds))) {
      const selectedChatId = String(selectedByIdentity[String(identityId)] || '').trim();
      if (selectedChatId) {
        return selectedChatId;
      }
    }
    return null;
  };
  const fleetTaskForWorker = (worker: DesktopFleetWorker) => (
    (worker.active_task_id
      ? fleetTasks.find((task: any) => task.task_id === worker.active_task_id)
      : null)
    || fleetTasks.find((task: any) => task.worker_id === worker.worker_id && fleetActiveTaskStatuses.has(task.status))
    || null
  );
  const hasActiveFleetTask = fleetWorkers.some((worker: any) => Boolean(fleetTaskForWorker(worker)));
  const fleetLatestReportForWorker = (worker: DesktopFleetWorker) => (
    fleetReports.find((report: any) => report.worker_id === worker.worker_id) || null
  );
  const fleetManagerChatEntries = transcriptEntries.slice(-10);
  const fleetManagerIdentityName = activeFleetIdentity?.display_name || 'Manager';
  const fleetManagerChatEmpty = fleetManagerChatEntries.length === 0 && !assistantDraft && !shouldShowThinkingIndicator;
  const fleetManagerComposerPlaceholder = activeFleetIdentity?.role === 'worker'
    ? `Message ${fleetManagerIdentityName}`
    : 'Message the manager or delegate work';
  const fleetManagerChatEyebrow = activeFleetIdentity?.role === 'worker' ? 'Worker Chat' : 'Manager Chat';
  const fleetManagerChatPanel = (
    <View style={[styles.fleetManagerChatPanel, { width: fleetChatPanelWidth }]}>
      <View style={styles.fleetChatIdentitySelector}>
        <View style={styles.fleetChatIdentityHeaderRow}>
          <View style={styles.fleetChatIdentityHeader}>
            <Text style={styles.fleetEyebrow}>Identity</Text>
            <Text style={styles.fleetChatIdentityHint} numberOfLines={1}>
              Chat routes through the selected identity
            </Text>
          </View>
          <Pressable
            style={styles.panelCollapseButton}
            accessibilityRole="button"
            accessibilityLabel="Collapse fleet chat panel"
            onPress={() => setFleetChatPanelCollapsed(true)}
          >
            <Text style={styles.panelCollapseButtonText}>›</Text>
          </Pressable>
        </View>
        {fleetIdentities.length ? (
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator
            style={styles.fleetChatIdentityScroll}
            contentContainerStyle={styles.fleetChatIdentityList}
          >
            {fleetIdentities.map((identity: any) => {
              const active = activeFleetIdentity?.identity_id === identity.identity_id;
              return (
                <Pressable
                  key={`fleet-chat-identity-${identity.identity_id}`}
                  style={[
                    styles.fleetChatIdentityChip,
                    active ? styles.fleetChatIdentityChipActive : null,
                    fleetLoading ? styles.fleetActionDisabled : null,
                  ]}
                  disabled={fleetLoading}
                  onPress={() => void selectFleetIdentity(identity)}
                >
                  <Text style={[styles.fleetChatIdentityName, active ? styles.fleetChatIdentityNameActive : null]} numberOfLines={1}>
                    {identity.display_name}
                  </Text>
                  <Text style={[styles.fleetChatIdentityMeta, active ? styles.fleetChatIdentityMetaActive : null]} numberOfLines={1}>
                    {identity.role}{identity.status ? ` · ${identity.status}` : ''}
                  </Text>
                </Pressable>
              );
            })}
          </ScrollView>
        ) : (
          <Text style={styles.fleetChatIdentityEmpty}>Identities will appear when Fleet is ready.</Text>
        )}
      </View>

      <View style={styles.fleetManagerChatHeader}>
        <View style={styles.fleetManagerChatHeaderTop}>
          <View style={styles.fleetManagerChatHeaderCopy}>
            <Text style={styles.fleetEyebrow}>{fleetManagerChatEyebrow}</Text>
            <Text style={styles.fleetManagerChatTitle} numberOfLines={1}>{fleetManagerIdentityName}</Text>
          </View>
          <View style={styles.fleetManagerChatActions}>
            <Pressable
              style={({ hovered }: any) => [
                styles.fleetManagerChatActionButton,
                hovered ? styles.fleetManagerChatActionButtonHovered : null,
              ]}
              accessibilityRole="button"
              accessibilityLabel="Start a new fleet chat"
              onPress={() => void beginNewChat()}
            >
              <MonoIcon name="compose" style={styles.fleetManagerChatActionIcon} />
              <Text style={styles.fleetManagerChatActionText}>New</Text>
            </Pressable>
            <Pressable
              ref={modelTriggerRef}
              style={({ hovered }: any) => [
                styles.fleetManagerChatModelButton,
                hovered ? styles.fleetManagerChatActionButtonHovered : null,
                activeCommandPanel?.kind === 'model' ? styles.fleetManagerChatActionButtonActive : null,
              ]}
              accessibilityRole="button"
              accessibilityLabel="Change fleet chat model"
              onPress={() => setActiveCommandPanel((current: any) => current?.kind === 'model' ? null : { kind: 'model' })}
            >
              <View style={styles.fleetManagerChatActionCopy}>
                <Text style={styles.fleetManagerChatActionText}>Model</Text>
                <Text style={styles.fleetManagerChatActionMeta} numberOfLines={1}>
                  {currentModelLabel}{currentVariantLabel}
                </Text>
              </View>
              <MonoIcon name={activeCommandPanel?.kind === 'model' ? 'chevron_up' : 'chevron_down'} style={styles.fleetManagerChatActionIcon} />
            </Pressable>
          </View>
        </View>
        <View style={styles.fleetManagerChatMetaRow}>
          <Text style={styles.fleetManagerChatMeta} numberOfLines={1}>
            {currentModelLabel}{currentVariantLabel}
          </Text>
          <Text style={styles.fleetManagerChatMeta} numberOfLines={1}>
            Tools · {currentEnabledToolPacks.length}
          </Text>
        </View>
      </View>

      <ScrollView
        style={styles.fleetManagerTranscript}
        contentContainerStyle={styles.fleetManagerTranscriptContent}
      >
        {fleetManagerChatEmpty ? (
          <View style={styles.fleetManagerEmptyChat}>
            <Text style={styles.fleetManagerEmptyTitle}>Ready</Text>
            <Text style={styles.fleetManagerEmptyText}>
              Ask directly, assign work, or inspect the fleet from this sidebar.
            </Text>
          </View>
        ) : null}

        {fleetManagerChatEntries.map(({ fullIndex, message }: any, index: any) => {
          const messageOnLightSurface = message.role === 'user';
          return (
            <View
              key={message.messageKey || `${message.timestamp || 'ts'}-${fullIndex}-${index}`}
              style={[
                styles.fleetManagerMessage,
                message.role === 'assistant'
                  ? styles.fleetManagerMessageAssistant
                  : message.role === 'system'
                    ? styles.fleetManagerMessageSystem
                    : styles.fleetManagerMessageUser,
                message.pending ? styles.messageBubblePending : null,
              ]}
            >
              <View style={styles.fleetManagerMessageHeader}>
                <Text style={[styles.fleetManagerMessageLabel, messageOnLightSurface ? styles.fleetManagerMessageLabelOnLight : null]}>
                  {labelForMessage(message)}
                </Text>
                <Text style={[styles.fleetManagerMessageTime, messageOnLightSurface ? styles.fleetManagerMessageTimeOnLight : null]}>
                  {message.timestamp ? formatAbsoluteTime(message.timestamp) : 'pending'}
                </Text>
              </View>
              <Text
                style={[styles.fleetManagerMessageText, messageOnLightSurface ? styles.fleetManagerMessageTextOnLight : null]}
                numberOfLines={6}
              >
                {message.content}
              </Text>
            </View>
          );
        })}

        {assistantDraft ? (
          <View style={[styles.fleetManagerMessage, styles.fleetManagerMessageAssistant, styles.messageBubbleDraft]}>
            <View style={styles.fleetManagerMessageHeader}>
              <Text style={styles.fleetManagerMessageLabel}>Assistant</Text>
              <Text style={styles.fleetManagerMessageTime}>streaming</Text>
            </View>
            <Text style={styles.fleetManagerMessageText} numberOfLines={6}>{assistantDraft}</Text>
          </View>
        ) : null}

        {shouldShowThinkingIndicator ? (
          <View style={styles.fleetManagerThinkingRow}>
            <Text style={styles.fleetManagerThinkingText}>Thinking</Text>
          </View>
        ) : null}
      </ScrollView>

      {queuedComposerMessagesDisplay.length ? (
        <View style={styles.fleetManagerQueueStack}>
          {queuedComposerMessagesDisplay.slice(0, 2).map((item: any) => (
            <View key={item.id} style={styles.fleetManagerQueueRow}>
              <Text style={styles.fleetManagerQueueText} numberOfLines={1}>{item.text}</Text>
              <Pressable
                style={styles.fleetManagerQueueAction}
                onPress={() => {
                  sendQueuedComposerSlice([item], 'steer_now');
                }}
              >
                <Text style={styles.fleetManagerQueueActionText}>Steer</Text>
              </Pressable>
            </View>
          ))}
        </View>
      ) : null}

      <View style={styles.fleetManagerComposer}>
        {activeCommandPanel?.kind === 'model' ? (
          <View ref={floatingPanelRef} style={[styles.commandPanel, styles.commandPanelSlim, styles.fleetManagerComposerMenu]}>
            <View style={styles.commandPanelHeader}>
              <View style={styles.commandPanelHeaderCopy}>
                <View style={styles.commandPanelHeaderLine}>
                  <Text style={styles.commandPanelCompactTitle}>Model + Planner</Text>
                  <Pressable
                    style={styles.commandPanelInfoButton}
                    accessibilityRole="button"
                    accessibilityLabel="Fleet chat model information"
                    accessibilityHint="This changes the main model and planner model for the current chat or draft chat."
                    {...(Platform.OS === 'web' ? ({ title: 'This changes the main model and planner model for the current chat or draft chat.' } as any) : {})}
                  >
                    <MonoIcon name="info" style={styles.commandPanelInfoIcon} />
                  </Pressable>
                </View>
              </View>
              <Pressable style={styles.commandPanelCloseButton} onPress={() => setActiveCommandPanel(null)}>
                <Text style={styles.commandPanelCloseText}>Close</Text>
              </Pressable>
            </View>
            <DesktopModelPickerMenu
              styles={styles}
              MonoIcon={MonoIcon}
              draftModelGroups={draftModelGroups}
              currentModelLabel={currentModelLabel}
              currentVariant={currentVariant}
              currentVariantHasControls={currentVariantHasControls}
              currentVariantOptions={currentVariantOptions}
              currentPlannerLabel={currentPlannerLabel}
              plannerModelGroups={plannerModelGroups}
              expandedModelProviders={expandedModelProviders}
              expandedPlannerProviders={expandedPlannerProviders}
              setExpandedModelProviders={setExpandedModelProviders}
              setExpandedPlannerProviders={setExpandedPlannerProviders}
              chooseModel={chooseModel}
              chooseVariant={chooseVariant}
              choosePlannerModel={choosePlannerModel}
              scrollStyle={styles.fleetModelPickerScroll}
              emptyTitle="No configured models"
              emptyText="Add a provider in settings, then reopen this picker."
            />
          </View>
        ) : null}
        {activeCommandPanel?.kind === 'tools' && activeCommandPanel.source === 'fleet' ? (
          <View style={[styles.commandPanel, styles.commandPanelSlim, styles.fleetManagerComposerMenu]}>
            {toolPackCommandPanelContent}
            {activeToolPackInfo ? (
              <View style={styles.toolPackInfoBubble}>
                <Text style={styles.toolPackInfoTitle}>{activeToolPackInfo.label}</Text>
                <Text style={styles.toolPackInfoText}>{activeToolPackInfo.description}</Text>
                {activeToolPackInfoDisabledReason ? (
                  <Text style={styles.toolPackInfoWarning}>{activeToolPackInfoDisabledReason}</Text>
                ) : !activeToolPackInfoAvailable && activeToolPackInfoConfiguredEnabled ? (
                  <Text style={styles.toolPackInfoWarning}>{unavailableEnabledToolPackReason}</Text>
                ) : null}
              </View>
            ) : null}
          </View>
        ) : null}
        {pendingRunMode || planMode || activeGoal ? (
          <View style={styles.composerModeTray}>
            {pendingRunMode === 'plan' ? (
              <View style={styles.composerModeChip}>
                <Text style={styles.composerModeChipText}>Plan next message</Text>
                <Pressable style={styles.composerModeChipClose} onPress={() => setPendingRunMode?.(null)}>
                  <Text style={styles.composerModeChipCloseText}>x</Text>
                </Pressable>
              </View>
            ) : null}
            {pendingRunMode === 'goal' ? (
              <View style={styles.composerModeChip}>
                <Text style={styles.composerModeChipText}>Goal next message</Text>
                <Pressable style={styles.composerModeChipClose} onPress={() => setPendingRunMode?.(null)}>
                  <Text style={styles.composerModeChipCloseText}>x</Text>
                </Pressable>
              </View>
            ) : null}
            {planMode ? (
              <View style={styles.composerModeChipActive}>
                <Text style={styles.composerModeChipText}>Plan active</Text>
                <Pressable style={styles.composerModeChipClose} onPress={() => void exitPlanMode?.()}>
                  <Text style={styles.composerModeChipCloseText}>x</Text>
                </Pressable>
              </View>
            ) : null}
            {activeGoal ? (
              <View style={styles.composerModeChipGoal}>
                <Text style={styles.composerModeChipText} numberOfLines={1}>
                  Goal · {String(activeGoal.objective || 'active')}
                </Text>
                <Pressable style={styles.composerModeChipClose} onPress={() => void clearActiveGoal?.()}>
                  <Text style={styles.composerModeChipCloseText}>x</Text>
                </Pressable>
              </View>
            ) : null}
          </View>
        ) : null}
        <TextInput
          nativeID="desktop-fleet-composer-input"
          style={styles.fleetManagerComposerInput}
          value={input}
          onChangeText={handleComposerInputChange}
          onKeyPress={handleComposerKeyPress}
          placeholder={fleetManagerComposerPlaceholder}
          placeholderTextColor="#7e8fae"
          multiline
        />
        <View style={styles.fleetManagerComposerFooter}>
          <View style={styles.fleetManagerComposerFooterControls}>
            <Pressable
              style={({ hovered }: any) => [
                styles.composerIconButton,
                styles.fleetComposerIconButton,
                hovered ? styles.composerIconButtonHovered : null,
                activeCommandPanel?.kind === 'tools' && activeCommandPanel.source === 'fleet' ? styles.composerIconButtonActive : null,
              ]}
              accessibilityRole="button"
              accessibilityLabel="Open fleet chat tool menu"
              onPress={() => setActiveCommandPanel((current: any) => current?.kind === 'tools' && current.source === 'fleet' ? null : { kind: 'tools', source: 'fleet' })}
            >
              <MonoIcon name="plus" style={styles.composerIconButtonGlyph} />
            </Pressable>
            <Text style={styles.fleetManagerComposerStatus} numberOfLines={1}>{shortStatusText(status)}</Text>
          </View>
          <Pressable
            style={[
              styles.fleetManagerSendButton,
              sendButtonMode === 'idle' ? styles.sendButtonIdle : null,
              sendButtonMode === 'stop' ? styles.sendButtonStop : null,
              sendButtonMode === 'interrupt' ? styles.sendButtonInterrupt : null,
            ]}
            onPress={() => {
              if (sendButtonMode === 'stop') {
                void runControl('stop');
                return;
              }
              if (sendButtonMode === 'idle') {
                return;
              }
              void sendText();
            }}
          >
            <Text style={[styles.sendButtonText, sendButtonMode === 'idle' ? styles.sendButtonTextIdle : null]}>
              {sendButtonGlyph}
            </Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
  const fleetSidebarPanel = (
    <View style={styles.fleetSidebarPanel}>
      <View style={styles.fleetPanelHeader}>
        <View style={styles.fleetPanelHeaderCopy}>
          <Text style={styles.fleetEyebrow}>Fleet V1</Text>
          <Text style={styles.fleetPanelTitle}>Fleet Dashboard</Text>
        </View>
        <DesktopFleetInfoButton
          label="Fleet Dashboard"
          text="Manage connected computers, local worker identities, queues, reports, and private device enrollment from this workspace."
        />
        <Pressable
          style={styles.panelCollapseButton}
          accessibilityRole="button"
          accessibilityLabel={fleetDashboardCollapsed ? 'Expand Fleet dashboard' : 'Collapse Fleet dashboard'}
          onPress={() => setFleetDashboardCollapsed((current: any) => !current)}
        >
          <Text style={styles.panelCollapseButtonText}>{fleetDashboardCollapsed ? '›' : '‹'}</Text>
        </Pressable>
        <Pressable
          style={[styles.fleetSmallDangerAction, (fleetLoading || !hasActiveFleetTask) ? styles.fleetActionDisabled : null]}
          disabled={fleetLoading || !hasActiveFleetTask}
          onPress={() => void stopAllFleetWorkers()}
        >
          <Text style={styles.fleetSmallDangerActionText}>Stop All</Text>
        </Pressable>
      </View>

      <View style={styles.fleetStatusCard}>
        <Text style={styles.fleetStatusLabel}>Status</Text>
        <Text style={fleetError ? styles.fleetStatusError : styles.fleetStatusText}>{shortStatusText(fleetStatus)}</Text>
      </View>

      {fleetDashboardCollapsed ? (
        <View style={styles.fleetCollapsedNotice}>
          <Text style={styles.fleetSectionTitle}>Dashboard collapsed</Text>
          <Text style={styles.fleetPanelText}>Expand when you need worker cards, groups, queues, or enrollment controls.</Text>
        </View>
      ) : (
        <>

      <DesktopFleetWorkspace
        snapshot={fleetSnapshot}
        snapshotError={fleetError}
        snapshotRefreshing={fleetLoading}
        onSnapshotRetry={() => void scope.refreshFleetSnapshot?.()}
        onChanged={() => void scope.refreshFleetSnapshot?.({ quiet: true })}
        localComputerContent={(
          <>

      <View style={styles.fleetCreateCard}>
        <View style={styles.fleetWorkersHeader}>
          <Text style={styles.fleetSectionTitle}>Workers on this desktop</Text>
          <DesktopFleetInfoButton
            label="Local workers"
            text="Create an additional worker identity that runs only on this computer. It is not copied to connected computers."
          />
        </View>
        <TextInput
          style={styles.fleetInput}
          placeholder="Name the new local agent"
          placeholderTextColor="#667a9c"
          accessibilityLabel="New local agent name"
          value={fleetWorkerNameDraft}
          onChangeText={setFleetWorkerNameDraft}
        />
        <View style={styles.fleetActionRow}>
          <Pressable
            style={[styles.fleetPrimaryAction, fleetLoading || !fleetWorkerNameDraft.trim() ? styles.fleetActionDisabled : null]}
            disabled={fleetLoading || !fleetWorkerNameDraft.trim()}
            onPress={() => void createFleetLocalWorker()}
          >
            <Text style={styles.fleetPrimaryActionText}>Create local agent</Text>
          </Pressable>
        </View>
      </View>

      <View style={styles.fleetWorkersSection}>
        <View style={styles.fleetWorkersHeader}>
          <Text style={styles.fleetSectionTitle}>Workers</Text>
          <Text style={styles.fleetSectionMeta}>{fleetLocalWorkers.length}</Text>
        </View>
        {fleetLocalWorkers.length ? (
          <View style={styles.fleetWorkerGrid}>
            {fleetLocalWorkers.map((worker: any) => {
              const task = fleetTaskForWorker(worker);
              const report = fleetLatestReportForWorker(worker);
              const workerTasks = fleetTasks.filter((item: any) => item.worker_id === worker.worker_id);
              const queuedTasks = workerTasks.filter((item: any) => item.status === 'queued');
              const queuedCount = queuedTasks.length;
              const draft = fleetTaskDrafts[worker.worker_id] || '';
              const renameDraft = fleetRenameDrafts[worker.worker_id] || '';
              const workerMenuOpen = openFleetWorkerMenuId === worker.worker_id;
              const workerStatusLabel = fleetWorkerStatusLabel(worker, task);
              const queuePolicy = worker.queue_policy === 'auto_continue_success' ? 'auto_continue_success' : 'review_required';
              const awaitingReportReview = !task && queuedCount > 0 && Boolean(report);
              const workerQueueLabel = awaitingReportReview
                ? `Awaiting report review · ${queuedCount} task${queuedCount === 1 ? '' : 's'} queued`
                : `${worker.kind} · ${workerStatusLabel}${queuedCount ? ` · ${queuedCount} queued` : ''}`;
              return (
                <View key={worker.worker_id} style={styles.fleetWorkerCard}>
                  <View style={styles.fleetWorkerHeader}>
                    <View style={styles.fleetWorkerTitleBlock}>
                      <Text style={styles.fleetWorkerName} numberOfLines={1}>{worker.display_name}</Text>
                      <Text accessibilityLiveRegion="polite" style={styles.fleetWorkerMeta}>{workerQueueLabel}</Text>
                    </View>
                    <Pressable
                      style={[styles.fleetWorkerMenuButton, workerMenuOpen ? styles.fleetWorkerMenuButtonActive : null]}
                      accessibilityRole="button"
                      accessibilityLabel={`Open actions for ${worker.display_name}`}
                      onPress={() => setOpenFleetWorkerMenuId((current: any) => current === worker.worker_id ? null : worker.worker_id)}
                    >
                      <MonoIcon name="more" style={styles.fleetWorkerMenuIcon} />
                    </Pressable>
                  </View>

                  {workerMenuOpen ? (
                    <View style={styles.fleetWorkerMenu}>
                      <View style={styles.fleetWorkerMenuRenameRow}>
                        <TextInput
                          style={[styles.fleetInput, styles.fleetInlineInput]}
                          placeholder="Rename worker"
                          placeholderTextColor="#667a9c"
                          value={renameDraft}
                          onChangeText={(value: any) => setFleetRenameDrafts((previous: any) => ({ ...previous, [worker.worker_id]: value }))}
                        />
                        <Pressable
                          style={[styles.fleetSecondaryAction, styles.fleetWorkerMenuAction, (!renameDraft.trim() || fleetLoading) ? styles.fleetActionDisabled : null]}
                          disabled={!renameDraft.trim() || fleetLoading}
                          onPress={() => {
                            setOpenFleetWorkerMenuId(null);
                            void renameFleetWorker(worker);
                          }}
                        >
                          <Text style={styles.fleetSecondaryActionText}>Rename</Text>
                        </Pressable>
                      </View>
                      <View style={styles.fleetWorkerMenuActionGrid}>
                        <Pressable
                          accessibilityRole="radio"
                          accessibilityLabel="Require report review before starting the next task"
                          accessibilityState={{ checked: queuePolicy === 'review_required', disabled: fleetLoading }}
                          style={[styles.fleetSecondaryAction, styles.fleetWorkerMenuAction, queuePolicy === 'review_required' ? styles.fleetWorkerMenuButtonActive : null]}
                          disabled={fleetLoading}
                          onPress={() => void scope.updateFleetQueuePolicy?.(worker, 'review_required')}
                        >
                          <Text style={styles.fleetSecondaryActionText}>Review Reports</Text>
                        </Pressable>
                        <Pressable
                          accessibilityRole="radio"
                          accessibilityLabel="Automatically continue only safe successful reports"
                          accessibilityHint="Failed, blocked, low-confidence, or malformed reports always pause."
                          accessibilityState={{ checked: queuePolicy === 'auto_continue_success', disabled: fleetLoading }}
                          style={[styles.fleetSecondaryAction, styles.fleetWorkerMenuAction, queuePolicy === 'auto_continue_success' ? styles.fleetWorkerMenuButtonActive : null]}
                          disabled={fleetLoading}
                          onPress={() => void scope.updateFleetQueuePolicy?.(worker, 'auto_continue_success')}
                        >
                          <Text style={styles.fleetSecondaryActionText}>Auto-continue Safe Success</Text>
                        </Pressable>
                        <Pressable
                          style={[styles.fleetSmallDangerAction, styles.fleetWorkerMenuAction, (fleetLoading || !task) ? styles.fleetActionDisabled : null]}
                          disabled={fleetLoading || !task}
                          onPress={() => {
                            setOpenFleetWorkerMenuId(null);
                            void stopFleetWorker(worker);
                          }}
                        >
                          <Text style={styles.fleetSmallDangerActionText}>Stop</Text>
                        </Pressable>
                        <Pressable
                          style={[styles.fleetSmallDangerAction, styles.fleetWorkerMenuAction, fleetLoading ? styles.fleetActionDisabled : null]}
                          disabled={fleetLoading}
                          onPress={() => {
                            setOpenFleetWorkerMenuId(null);
                            void resetFleetWorkerIdentity(worker);
                          }}
                        >
                          <Text style={styles.fleetSmallDangerActionText}>Reset</Text>
                        </Pressable>
                        <Pressable
                          style={[styles.fleetSmallDangerAction, styles.fleetWorkerMenuAction, fleetLoading ? styles.fleetActionDisabled : null]}
                          disabled={fleetLoading}
                          onPress={() => {
                            setOpenFleetWorkerMenuId(null);
                            void resetFleetWorker(worker);
                          }}
                        >
                          <Text style={styles.fleetSmallDangerActionText}>Delete</Text>
                        </Pressable>
                      </View>
                    </View>
                  ) : null}

                  <View style={styles.fleetWorkerInfoGrid}>
                    <View style={styles.fleetWorkerInfoTile}>
                      <Text style={styles.fleetInfoLabel}>Current Task</Text>
                      <Text style={styles.fleetInfoValue} numberOfLines={3}>{task?.prompt || 'Idle'}</Text>
                      <Text style={styles.fleetInfoMeta}>{task?.status || 'ready'}</Text>
                    </View>
                    <View style={styles.fleetWorkerInfoTile} accessibilityLiveRegion="polite">
                      <Text style={styles.fleetInfoLabel}>Latest Report · {report?.confidence || 'unrated'} confidence</Text>
                      <Text style={styles.fleetInfoValue} numberOfLines={5}>{fleetReportSummary(report)}</Text>
                      <Text style={styles.fleetInfoMeta}>
                        {report
                          ? `${report.status} · ${(report.blockers || []).length} blocker${(report.blockers || []).length === 1 ? '' : 's'} · ${(report.evidence || []).length + (report.artifacts || []).length} evidence`
                          : 'waiting'}
                      </Text>
                      {report?.blockers?.length ? <Text style={styles.fleetInfoMeta}>Blocked by: {report.blockers.map((item: any) => typeof item === 'string' ? item : item?.message || item?.detail || 'reported blocker').join('; ')}</Text> : null}
                      {report?.next_suggested_action ? <Text style={styles.fleetInfoMeta}>Next: {report.next_suggested_action}</Text> : null}
                    </View>
                  </View>

                  <TextInput
                    style={[styles.fleetInput, styles.fleetTaskInput]}
                    placeholder={`Queue a task for ${worker.display_name}`}
                    placeholderTextColor="#667a9c"
                    value={draft}
                    multiline
                    onChangeText={(value: any) => {
                      setFleetTaskDrafts((previous: any) => ({ ...previous, [worker.worker_id]: value }));
                    }}
                  />
                  <Pressable
                    style={[
                      styles.fleetPrimaryAction,
                      (!draft.trim() || fleetLoading) ? styles.fleetActionDisabled : null,
                    ]}
                    disabled={!draft.trim() || fleetLoading}
                    onPress={() => void assignFleetTask(worker)}
                  >
                    <Text style={styles.fleetPrimaryActionText}>Assign Task</Text>
                  </Pressable>
                  {queuedCount ? (
                    <Pressable
                      style={[styles.fleetSecondaryAction, (fleetLoading || Boolean(task)) ? styles.fleetActionDisabled : null]}
                      disabled={fleetLoading || Boolean(task)}
                      onPress={() => void continueFleetQueue(worker)}
                    >
                      <Text style={styles.fleetSecondaryActionText}>Approve Report & Start Next Task</Text>
                    </Pressable>
                  ) : null}
                </View>
              );
            })}
          </View>
        ) : (
          <View style={styles.emptyCard}>
            <Text style={styles.emptyTitle}>No workers yet</Text>
            <Text style={styles.emptyText}>Create a local worker above, or connect another desktop through the private network panel.</Text>
          </View>
        )}
      </View>

          </>
        )}
      />

      <View style={styles.fleetCreateCard}>
        <Text style={styles.fleetSectionTitle}>Groups</Text>
        <View style={styles.fleetActionRow}>
          <TextInput
            style={[styles.fleetInput, styles.fleetInlineInput]}
            placeholder="Group name"
            placeholderTextColor="#667a9c"
            value={fleetGroupNameDraft}
            onChangeText={setFleetGroupNameDraft}
          />
          <Pressable
            style={[styles.fleetSecondaryAction, (!fleetGroupNameDraft.trim() || !fleetWorkers.length || fleetLoading) ? styles.fleetActionDisabled : null]}
            disabled={!fleetGroupNameDraft.trim() || !fleetWorkers.length || fleetLoading}
            onPress={() => void createFleetGroupFromFirstWorker()}
          >
            <Text style={styles.fleetSecondaryActionText}>Create</Text>
          </Pressable>
        </View>
        {fleetGroups.length ? (
          <View style={styles.fleetWorkerList}>
            {fleetGroups.map((group: any) => {
              const groupId = String(group.group_id || '').trim();
              const groupName = String(group.display_name || groupId || 'Group');
              const draft = fleetGroupTaskDrafts[groupId] || '';
              const workerIds = Array.isArray(group.worker_ids) ? group.worker_ids : [];
              return (
                <View key={groupId} style={styles.fleetWorkerInfoTile}>
                  <View style={styles.fleetWorkerHeader}>
                    <View style={styles.fleetWorkerTitleBlock}>
                      <Text style={styles.fleetWorkerName}>{groupName}</Text>
                      <Text style={styles.fleetWorkerMeta}>{workerIds.length} workers</Text>
                    </View>
                    <Pressable
                      style={[styles.fleetSmallDangerAction, fleetLoading ? styles.fleetActionDisabled : null]}
                      disabled={fleetLoading}
                      onPress={() => void deleteFleetGroup(group)}
                    >
                      <Text style={styles.fleetSmallDangerActionText}>Delete</Text>
                    </Pressable>
                  </View>
                  <TextInput
                    style={[styles.fleetInput, styles.fleetTaskInput]}
                    placeholder="Dispatch a task to this group"
                    placeholderTextColor="#667a9c"
                    value={draft}
                    multiline
                    onChangeText={(value: any) => setFleetGroupTaskDrafts((previous: any) => ({ ...previous, [groupId]: value }))}
                  />
                  <Pressable
                    style={[styles.fleetPrimaryAction, (!draft.trim() || fleetLoading) ? styles.fleetActionDisabled : null]}
                    disabled={!draft.trim() || fleetLoading}
                    onPress={() => void assignFleetGroupTask(group)}
                  >
                    <Text style={styles.fleetPrimaryActionText}>Dispatch Group Task</Text>
                  </Pressable>
                </View>
              );
            })}
          </View>
        ) : (
          <Text style={styles.emptyText}>No groups yet.</Text>
        )}
      </View>
        </>
      )}
    </View>
  );
  return { historyAvailable, activeSessionArtifactCount, selectedArtifactSummary, commandSuggestionQuery, commandSuggestions, floatingPanelKind, floatingMenuKinds, hasDismissibleFloatingPanel, floatingPanelPrefersBelow, activeToolsPanelSource, shouldRenderGlobalFloatingPanel, floatingPanelPositionStyle, toolPackCommandPanelContent, draftProjectCommandPanel, draftBranchCommandPanel, draftTelegramCommandPanel, openReferenceRail, closeReferenceRail, refreshArtifacts, openArtifactRail, closeArtifactRail, openArtifactPreview, openArtifactExternally, downloadArtifact, openSearchResult, closeSidebar, toggleSidebar, beginHorizontalResize, projectDragProps, sessionDragProps, jarvisCircleMuted, jarvisMuteButtonMuted, jarvisTtsSummary, jarvisInputSummary, jarvisVoiceActivityPattern, jarvisToolActivity, jarvisToolSummary, jarvisTranscriptOutput, jarvisSpokenOutput, jarvisPushToTalkDisabled, jarvisHoldCaptureDisabled, jarvisHoldCaptureValue, jarvisHoldCaptureDetail, fleetIdentities, fleetWorkers, fleetTasks, fleetReports, fleetGroups, fleetActiveTaskStatuses, fleetSelectedChatIdForWorker, fleetTaskForWorker, hasActiveFleetTask, fleetLatestReportForWorker, fleetManagerChatEntries, fleetManagerIdentityName, fleetManagerChatEmpty, fleetManagerComposerPlaceholder, fleetManagerChatEyebrow, fleetManagerChatPanel, fleetSidebarPanel };
}
