import { Image, Modal, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AppDrawer } from '@/components/AppDrawer';
import { CollapsibleSection } from '@/components/CollapsibleSection';
import { ActionButton, ControlRow } from '@/components/ParityUI';
import { RunTimeline } from '@/components/RunTimeline';
import {
  appendAgentMemoryNote,
  clearAgentPendingFiles,
  fetchAgentConfig,
  fetchAgentSkills,
  fetchSubAgents,
  forgetLastAgentMessage,
  searchAgentMemory,
  updateAgentConfig,
} from '@/lib/appApi';
import { shortStatusText } from '../../lib/diagnostics';
import { formatConfigValue } from '@/screens/chatTimeline';
import { formatRelativeTime } from '@/lib/time';

import {
  CHAT_CONTROL_GROUPS,
  QUICK_TURN_OPTIONS,
  TOOL_PACK_DEFINITIONS,
  identityLabel,
  normalizeWorkspacePath,
} from './ChatScreen.helpers';
import { styles } from './ChatScreen.styles';

type ChatScreenViewProps = {
  scope: Record<string, any>;
};

export function ChatScreenView({ scope }: ChatScreenViewProps) {
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
    handleRealtimeEvent,
    uploadAttachment,
    refreshScreenshot,
    finishCurrentSegment,
    startSegmentRecording,
    startVoiceCapture,
    stopVoiceCapture,
    send,
    toggleVerboseMode,
    sessionUpdatedAt,
    subtitle,
    pairingPromptTitle,
    pairingPromptText,
    workspaceStatus,
    fleetIdentities,
    sendDisabled,
  } = scope;

  return (
    <SafeAreaView edges={['top', 'left', 'right']} style={styles.container}>
      <AppDrawer
        visible={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        initialTab={drawerTab}
        sessions={visibleSessions}
        jobs={jobs}
        cronUnreadCount={cronUnreadCount}
        activeSessionId={sessionId}
        backendLabel={connectionMode === 'remote_cloud' ? 'Kraitos cloud' : (apiBaseUrl || 'Backend not configured')}
        sidebarState={sidebarState}
        onSelectSession={(nextSessionId) => {
          void selectSession(nextSessionId, { updateRoute: false });
        }}
        onCreateSession={(workspace) => {
          openBlankChat(workspace);
        }}
        onDeleteSession={(nextSessionId) => {
          void deleteConversation(nextSessionId);
        }}
        onFolderRemoved={(workspace) => {
          if (normalizeWorkspacePath(currentSessionSummary?.workspace) === normalizeWorkspacePath(workspace)) {
            openBlankChat();
          }
        }}
        onSidebarStateChange={(nextState) => {
          void persistSidebarState(nextState);
        }}
      />
      {confirmationDialog}

      <Modal transparent visible={pairPromptOpen} animationType="fade" onRequestClose={() => setPairPromptOpen(false)}>
        <View style={styles.modalOverlay}>
          <Pressable style={styles.modalBackdrop} onPress={() => setPairPromptOpen(false)} />
          <View style={styles.promptCard}>
            <Text style={styles.promptTitle}>{pairingPromptTitle}</Text>
            <Text style={styles.promptText}>{pairingPromptText}</Text>
            <View style={styles.promptActions}>
              <Pressable
                style={styles.primaryButton}
                onPress={() => {
                  setPairPromptOpen(false);
                  router.push('/pair');
                }}
              >
                <Text style={styles.primaryButtonText}>Open Pair</Text>
              </Pressable>
              <Pressable
                style={styles.secondaryButton}
                onPress={() => {
                  setPairPromptOpen(false);
                  router.push('/settings');
                }}
              >
                <Text style={styles.secondaryButtonText}>Settings</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>

      <Modal transparent visible={workspacePanelOpen} animationType="slide" onRequestClose={() => setWorkspacePanelOpen(false)}>
        <View style={styles.sheetOverlay}>
          <Pressable style={styles.sheetBackdrop} onPress={() => setWorkspacePanelOpen(false)} />
          <SafeAreaView edges={['bottom']} style={styles.sheet}>
            <View style={styles.sheetHandle} />
            <View style={styles.sheetHeader}>
              <View style={styles.sheetHeading}>
                <Text style={styles.sheetTitle}>Chat controls</Text>
                <Text style={styles.sheetSubtitle}>Run controls, attachments, verbose output, and links into the shared agent surfaces.</Text>
              </View>
              <Pressable onPress={() => setWorkspacePanelOpen(false)}>
                <Text style={styles.sheetClose}>Done</Text>
              </Pressable>
            </View>

            <ScrollView contentContainerStyle={styles.sheetContent}>
              <View style={styles.rowWrap}>
                <Pressable
                  style={styles.secondaryButton}
                  onPress={() => {
                    setWorkspacePanelOpen(false);
                    openBlankChat();
                  }}
                >
                  <Text style={styles.secondaryButtonText}>New chat</Text>
                </Pressable>
                <Pressable
                  style={styles.secondaryButton}
                  onPress={() => {
                    setWorkspacePanelOpen(false);
                    setDrawerTab('chats');
                    setDrawerOpen(true);
                  }}
                >
                  <Text style={styles.secondaryButtonText}>Sidebar</Text>
                </Pressable>
                <Pressable
                  style={styles.secondaryButton}
                  onPress={() => {
                    void refreshSidebarData();
                    setWorkspacePanelOpen(false);
                  }}
                >
                  <Text style={styles.secondaryButtonText}>Refresh lists</Text>
                </Pressable>
                <Pressable
                  style={styles.secondaryButton}
                  onPress={() => {
                    setWorkspacePanelOpen(false);
                    router.push('/cron');
                  }}
                >
                  <Text style={styles.secondaryButtonText}>
                    {cronUnreadCount > 0 ? `Automations (${cronUnreadCount})` : 'Automations'}
                  </Text>
                </Pressable>
                <Pressable
                  style={[styles.secondaryButton, verboseMode ? styles.activeSecondary : null]}
                  onPress={() => void toggleVerboseMode()}
                >
                  <Text style={styles.secondaryButtonText}>{verboseMode ? 'Verbose on' : 'Verbose off'}</Text>
                </Pressable>
              </View>

              <CollapsibleSection
                title="Setup and help"
                meta="Account, pairing, setup"
                defaultExpanded={false}
              >
                <View style={styles.infoCard}>
                  <Text style={styles.infoCardLabel}>Connection</Text>
                  <Text style={styles.infoCardText}>
                    Kraitos mobile channel connected. Current model: {agentOverview?.current_model || 'Unknown'} · variant: {agentOverview?.current_variant || 'Unknown'} · max turns: {agentOverview?.max_turns || '-'}
                  </Text>
                </View>
                <View style={styles.infoCard}>
                  <Text style={styles.infoCardLabel}>Mode</Text>
                  <Text style={styles.infoCardText}>Auto mode is always on. The app uses the unified agent directly.</Text>
                </View>
                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Permission mode</Text>
                  <Text style={styles.helperText}>
                    Current chat: {activeSecurityPermissionLabel}. Full access lasts for this chat session and still asks before sensitive actions.
                  </Text>
                  <ControlRow>
                    {[
                      { id: 'low' as const, label: 'Ask' },
                      { id: 'standard' as const, label: 'Approve' },
                      { id: 'full_permissions' as const, label: 'Full access' },
                    ].map((mode) => (
                      <ActionButton
                        key={mode.id}
                        label={mode.label}
                        active={activeSecurityPermissionMode === mode.id || (!activeSecurityPermissionMode && mode.id === 'standard')}
                        onPress={() => void updateChatSecurityPermissionMode(mode.id)}
                      />
                    ))}
                  </ControlRow>
                </View>
                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Controls</Text>
                  {CHAT_CONTROL_GROUPS.map(([label, commands]) => (
                    <View key={label} style={styles.infoCard}>
                      <Text style={styles.infoCardLabel}>{label}</Text>
                      <Text style={styles.infoCardText}>{commands}</Text>
                    </View>
                  ))}
                </View>
                <View style={styles.rowWrap}>
                  <Pressable
                    style={styles.secondaryButton}
                    onPress={() => {
                      setWorkspacePanelOpen(false);
                      router.push(setupMissing ? '/pair' : '/settings');
                    }}
                  >
                    <Text style={styles.secondaryButtonText}>{setupMissing ? 'Open setup' : 'Open settings'}</Text>
                  </Pressable>
                  <Pressable
                    style={[styles.secondaryButton, agentControlsDisabled ? styles.disabledButton : null]}
                    onPress={() => void runTaskControl('restart')}
                    disabled={agentControlsDisabled}
                    accessibilityState={{ disabled: agentControlsDisabled }}
                  >
                    <Text style={styles.secondaryButtonText}>Restart backend</Text>
                  </Pressable>
                </View>
              </CollapsibleSection>

              <CollapsibleSection
                title="Task controls"
                meta="Composer, pause, stop, background tasks"
                defaultExpanded={false}
              >
                <Text style={styles.helperText}>
                  Use the normal composer to start or steer the current run.
                </Text>
                <View style={styles.rowWrap}>
                  <Pressable style={styles.secondaryButton} onPress={() => focusComposer()}>
                    <Text style={styles.secondaryButtonText}>Open composer</Text>
                  </Pressable>
                  <Pressable
                    style={[styles.secondaryButton, agentControlsDisabled ? styles.disabledButton : null]}
                    disabled={agentControlsDisabled}
                    accessibilityState={{ disabled: agentControlsDisabled }}
                    onPress={() => void runTaskControl('pause')}
                  >
                    <Text style={styles.secondaryButtonText}>Pause run</Text>
                  </Pressable>
                  <Pressable
                    style={[styles.secondaryButton, agentControlsDisabled ? styles.disabledButton : null]}
                    disabled={agentControlsDisabled}
                    accessibilityState={{ disabled: agentControlsDisabled }}
                    onPress={() => void runTaskControl('stop')}
                  >
                    <Text style={styles.secondaryButtonText}>Stop run</Text>
                  </Pressable>
                </View>

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Spawn sub-agent</Text>
                  <TextInput
                    style={styles.textAreaInput}
                    value={subAgentPrompt}
                    onChangeText={setSubAgentPrompt}
                    placeholder="Describe the background task"
                    placeholderTextColor="#7f8aa3"
                    multiline
                  />
                  <View style={styles.rowWrap}>
                    <Pressable
                      style={[styles.secondaryButton, subAgentSpawnDisabled ? styles.disabledButton : null]}
                      disabled={subAgentSpawnDisabled}
                      accessibilityState={{ disabled: subAgentSpawnDisabled }}
                      onPress={() => void spawnBackgroundTask()}
                    >
                      <Text style={styles.secondaryButtonText}>Spawn</Text>
                    </Pressable>
                    <Pressable
                      style={[styles.secondaryButton, agentControlsDisabled ? styles.disabledButton : null]}
                      disabled={agentControlsDisabled}
                      accessibilityState={{ disabled: agentControlsDisabled }}
                      onPress={() =>
                        void runWorkspaceAction(
                          'refreshing sub-agents',
                          async () => {
                            const result = await fetchSubAgents(apiBaseUrl, token, sessionIdRef.current);
                            setSubAgents(result);
                          },
                          { refreshControls: false }
                        )
                      }
                    >
                      <Text style={styles.secondaryButtonText}>Refresh list</Text>
                    </Pressable>
                  </View>
                </View>

                <View style={styles.infoCard}>
                  <Text style={styles.infoCardText}>
                    Sub-agents: {subAgents?.total_tasks || 0} total · {subAgents?.running || 0} running · {subAgents?.completed || 0} completed · {subAgents?.failed || 0} failed
                  </Text>
                </View>
                {(subAgents?.tasks || []).length ? (
                  subAgents!.tasks.map((task: any) => (
                    <View key={task.id} style={styles.infoCard}>
                      <Text style={styles.infoCardLabel}>{task.id} · {task.status}</Text>
                      <Text style={styles.infoCardText}>{task.prompt}</Text>
                      <Text style={styles.infoCardText}>
                        {task.completed_at
                          ? `Completed ${formatRelativeTime(task.completed_at)}`
                          : task.created_at
                            ? `Created ${formatRelativeTime(task.created_at)}`
                            : 'Waiting for timestamps'}
                      </Text>
                    </View>
                  ))
                ) : (
                  <Text style={styles.helperText}>No sub-agents yet.</Text>
                )}
              </CollapsibleSection>

              <CollapsibleSection
                title="Skills"
                meta="Skill activation and validation"
                defaultExpanded={false}
              >
                <Text style={styles.helperText}>Activate one skill for the next messages or validate it from the phone.</Text>
                <View style={styles.rowWrap}>
                  <Pressable
                    style={styles.secondaryButton}
                    onPress={() =>
                      void runWorkspaceAction(
                        'refreshing skills',
                        async () => {
                          const result = await fetchAgentSkills(apiBaseUrl, token, sessionIdRef.current);
                          setSkills(result.items || []);
                        },
                        { refreshControls: false }
                      )
                    }
                  >
                    <Text style={styles.secondaryButtonText}>Refresh skills</Text>
                  </Pressable>
                </View>
                {skills.length ? (
                  skills.map((skill: any) => (
                    <View key={skill.name} style={styles.infoCard}>
                      <Text style={styles.infoCardLabel}>
                        {skill.name}
                        {skill.active ? ' · active' : ''}
                        {!skill.available ? ' · gated' : ''}
                      </Text>
                      <Text style={styles.infoCardText}>
                        {skill.description}
                        {skill.unavailable_reason ? `\n${skill.unavailable_reason}` : ''}
                      </Text>
                      <View style={styles.rowWrap}>
                        <Pressable
                          style={[styles.secondaryButton, skill.active ? styles.activeSecondary : null, !skill.available ? styles.disabledButton : null]}
                          disabled={!skill.available}
                          onPress={() => void toggleSkill(skill.name, !skill.active)}
                        >
                          <Text style={styles.secondaryButtonText}>{skill.active ? 'Deactivate' : 'Activate'}</Text>
                        </Pressable>
                        <Pressable
                          style={styles.secondaryButton}
                          onPress={() => void runSkillValidation(skill.name)}
                        >
                          <Text style={styles.secondaryButtonText}>Validate</Text>
                        </Pressable>
                      </View>
                    </View>
                  ))
                ) : (
                  <Text style={styles.helperText}>No skills available.</Text>
                )}
                {skillValidation ? (
                  <View style={styles.infoCard}>
                    <Text style={styles.infoCardLabel}>{skillValidation.name} · {skillValidation.valid ? 'valid' : 'invalid'}</Text>
                    <Text style={styles.infoCardText}>
                      Scripts: {skillValidation.scripts_count} · References: {skillValidation.references_count} · Assets: {skillValidation.assets_count}
                    </Text>
                    {skillValidation.errors.map((item: any) => (
                      <Text key={`error-${item}`} style={styles.infoCardText}>Error: {item}</Text>
                    ))}
                    {skillValidation.warnings.map((item: any) => (
                      <Text key={`warning-${item}`} style={styles.infoCardText}>Warning: {item}</Text>
                    ))}
                  </View>
                ) : null}
              </CollapsibleSection>

              <CollapsibleSection title="Status" meta="Moved off the main chat to keep the screen clean" defaultExpanded={false}>
                {workspaceStatus.map((item: any) => (
                  <View key={item.label} style={styles.statusRowCompact}>
                    <Text style={styles.statusRowLabel}>{item.label}</Text>
                    <Text style={styles.statusRowValue}>{item.value}</Text>
                  </View>
                ))}
              </CollapsibleSection>

              <CollapsibleSection
                title="Quick controls"
                meta={
                  agentOverview
                    ? `${agentOverview.current_model} · ${agentOverview.current_variant} · ${agentOverview.max_turns} turns`
                    : 'Model, variant, settings, verbose'
                }
                defaultExpanded={false}
              >
                <Text style={styles.helperText}>Fast model and settings controls. Use Agent Controls for deeper inspection.</Text>

                {agentOverview?.model_groups.map((group: any) => (
                  <View key={group.provider} style={styles.quickControlBlock}>
                    <Text style={styles.quickControlLabel}>{group.provider.toUpperCase()}</Text>
                    <View style={styles.rowWrap}>
                      {group.models.map((model: any) => (
                        <Pressable
                          key={model}
                          style={[styles.secondaryButton, model === agentOverview.current_model ? styles.activeSecondary : null]}
                          onPress={() => void applyQuickAgentConfig({ model })}
                        >
                          <Text style={styles.secondaryButtonText}>{model}</Text>
                        </Pressable>
                      ))}
                    </View>
                  </View>
                ))}

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Variant</Text>
                  <View style={styles.rowWrap}>
                    {(agentOverview?.available_variants || []).map((variant: any) => (
                      <Pressable
                        key={variant}
                        style={[styles.secondaryButton, variant === agentOverview?.current_variant ? styles.activeSecondary : null]}
                        onPress={() => void applyQuickAgentConfig({ variant })}
                      >
                        <Text style={styles.secondaryButtonText}>{variant}</Text>
                      </Pressable>
                    ))}
                  </View>
                </View>

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Max turns</Text>
                  <View style={styles.rowWrap}>
                    {QUICK_TURN_OPTIONS.map((turns) => (
                      <Pressable
                        key={turns}
                        style={[styles.secondaryButton, turns === agentOverview?.max_turns ? styles.activeSecondary : null]}
                        onPress={() => void applyQuickAgentConfig({ max_turns: turns })}
                      >
                        <Text style={styles.secondaryButtonText}>{turns}</Text>
                      </Pressable>
                    ))}
                  </View>
                </View>

                <View style={styles.rowWrap}>
                  <Pressable
                    style={[styles.secondaryButton, verboseMode ? styles.activeSecondary : null, agentControlsDisabled ? styles.disabledButton : null]}
                    disabled={agentControlsDisabled}
                    accessibilityState={{ disabled: agentControlsDisabled }}
                    onPress={() => void toggleVerboseMode()}
                  >
                    <Text style={styles.secondaryButtonText}>{verboseMode ? 'Verbose on' : 'Verbose off'}</Text>
                  </Pressable>
                  <Pressable
                    style={styles.secondaryButton}
                    onPress={() => {
                      setWorkspacePanelOpen(false);
                      router.push('/agent');
                    }}
                  >
                    <Text style={styles.secondaryButtonText}>More controls</Text>
                  </Pressable>
                </View>
              </CollapsibleSection>

              <CollapsibleSection
                title="Runtime controls"
                meta={
                  agentOverview
                    ? `${agentOverview.bridge_enabled ? 'Real Chrome' : 'Selenium'} · ${agentOverview.headless_mode} · heartbeat ${agentOverview.heartbeat.enabled ? 'on' : 'off'}`
                    : 'Monitor, workspace, headless, heartbeat, bridge'
                }
                defaultExpanded={false}
              >
                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Monitor</Text>
                  <View style={styles.rowWrap}>
                    <Pressable
                      style={[styles.secondaryButton, agentOverview?.auto_reply_enabled ? styles.activeSecondary : null]}
                      onPress={() => void applyQuickAgentConfig({ auto_reply_enabled: true })}
                    >
                      <Text style={styles.secondaryButtonText}>Monitor on</Text>
                    </Pressable>
                    <Pressable
                      style={[styles.secondaryButton, agentOverview && !agentOverview.auto_reply_enabled ? styles.activeSecondary : null]}
                      onPress={() => void applyQuickAgentConfig({ auto_reply_enabled: false })}
                    >
                      <Text style={styles.secondaryButtonText}>Monitor off</Text>
                    </Pressable>
                  </View>
                </View>

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Browser bridge</Text>
                  <View style={styles.rowWrap}>
                    <Pressable
                      style={[styles.secondaryButton, agentOverview?.bridge_enabled ? styles.activeSecondary : null]}
                      onPress={() => void applyQuickAgentConfig({ bridge_enabled: true })}
                    >
                      <Text style={styles.secondaryButtonText}>Real Chrome</Text>
                    </Pressable>
                    <Pressable
                      style={[styles.secondaryButton, agentOverview && !agentOverview.bridge_enabled ? styles.activeSecondary : null]}
                      onPress={() => void applyQuickAgentConfig({ bridge_enabled: false })}
                    >
                      <Text style={styles.secondaryButtonText}>Selenium</Text>
                    </Pressable>
                  </View>
                </View>

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Browser mode</Text>
                  <View style={styles.rowWrap}>
                    <Pressable
                      style={[styles.secondaryButton, agentOverview?.headless_mode === 'headless' ? styles.activeSecondary : null]}
                      onPress={() => void applyQuickAgentConfig({ headless_mode: 'headless' })}
                    >
                      <Text style={styles.secondaryButtonText}>Headless</Text>
                    </Pressable>
                    <Pressable
                      style={[styles.secondaryButton, agentOverview?.headless_mode === 'headed' ? styles.activeSecondary : null]}
                      onPress={() => void applyQuickAgentConfig({ headless_mode: 'headed' })}
                    >
                      <Text style={styles.secondaryButtonText}>Headed</Text>
                    </Pressable>
                  </View>
                </View>

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Heartbeat</Text>
                  <View style={styles.rowWrap}>
                    <Pressable
                      style={[styles.secondaryButton, agentOverview?.heartbeat.enabled ? styles.activeSecondary : null]}
                      onPress={() => void applyQuickAgentConfig({ heartbeat_enabled: true })}
                    >
                      <Text style={styles.secondaryButtonText}>Heartbeat on</Text>
                    </Pressable>
                    <Pressable
                      style={[styles.secondaryButton, agentOverview && !agentOverview.heartbeat.enabled ? styles.activeSecondary : null]}
                      onPress={() => void applyQuickAgentConfig({ heartbeat_enabled: false })}
                    >
                      <Text style={styles.secondaryButtonText}>Heartbeat off</Text>
                    </Pressable>
                  </View>
                  <View style={styles.rowWrap}>
                    <TextInput
                      style={styles.workspaceInputCompact}
                      value={heartbeatDraft}
                      onChangeText={setHeartbeatDraft}
                      placeholder="1800"
                      placeholderTextColor="#7f8aa3"
                      keyboardType="number-pad"
                    />
                    <Pressable
                      style={styles.secondaryButton}
                      onPress={() => void applyQuickAgentConfig({ heartbeat_interval_seconds: Number(heartbeatDraft) || 1800 })}
                    >
                      <Text style={styles.secondaryButtonText}>Set interval</Text>
                    </Pressable>
                  </View>
                  <Text style={styles.helperText}>
                    {agentOverview?.heartbeat.last_heartbeat
                      ? `Last heartbeat ${formatRelativeTime(agentOverview.heartbeat.last_heartbeat)}`
                      : 'No heartbeat recorded yet.'}
                  </Text>
                </View>

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Workspace</Text>
                  <View style={styles.rowWrap}>
                    <TextInput
                      style={styles.workspaceInput}
                      value={workspaceDraft}
                      onChangeText={setWorkspaceDraft}
                      placeholder="Workspace path"
                      placeholderTextColor="#7f8aa3"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                    <Pressable
                      style={styles.secondaryButton}
                      onPress={() => void applyQuickAgentConfig({ workspace: workspaceDraft })}
                    >
                      <Text style={styles.secondaryButtonText}>Apply</Text>
                    </Pressable>
                  </View>
                </View>
              </CollapsibleSection>

              <CollapsibleSection
                title="Context and files"
                meta={
                  agentOverview
                    ? `${agentOverview.context_usage.message_count} messages · ${agentOverview.pending_files.length} pending files`
                    : 'History, context, files, reset'
                }
                defaultExpanded={false}
              >
                <View style={styles.infoCard}>
                  <Text style={styles.infoCardText}>
                    Context: {agentOverview?.context_usage.estimated_tokens || 0} / {agentOverview?.context_usage.max_tokens || 0} estimated tokens
                    {agentOverview ? ` (${agentOverview.context_usage.usage_percent}%)` : ''}
                  </Text>
                </View>

                {(agentOverview?.history || []).slice(0, 6).map((item: any, index: number) => (
                  <View key={`${item.timestamp || index}-${item.preview}`} style={styles.infoCard}>
                    <Text style={styles.infoCardLabel}>
                      {item.display_label || item.role}
                      {item.timestamp ? ` · ${formatRelativeTime(item.timestamp)}` : ''}
                    </Text>
                    <Text style={styles.infoCardText}>{item.preview}</Text>
                  </View>
                ))}

                {(agentOverview?.pending_files || []).slice(0, 6).map((item: any) => (
                  <View key={`${item.filename}-${item.uploaded_at || item.source_format || 'file'}`} style={styles.infoCard}>
                    <Text style={styles.infoCardLabel}>{item.filename}</Text>
                    <Text style={styles.infoCardText}>
                      {item.mime_type || 'unknown type'}
                      {item.size ? ` · ${item.size} bytes` : ''}
                      {item.uploaded_at ? ` · ${formatRelativeTime(item.uploaded_at)}` : ''}
                    </Text>
                  </View>
                ))}

                <View style={styles.rowWrap}>
                  <Pressable
                    style={styles.secondaryButton}
                    onPress={() =>
                      void runWorkspaceAction('clearing pending files', async () => {
                        await clearAgentPendingFiles(apiBaseUrl, token, sessionIdRef.current);
                      })
                    }
                  >
                    <Text style={styles.secondaryButtonText}>Clear files</Text>
                  </Pressable>
                  <Pressable
                    style={styles.secondaryButton}
                    onPress={() =>
                      void runWorkspaceAction('forgetting last message', async () => {
                        await forgetLastAgentMessage(apiBaseUrl, token, sessionIdRef.current);
                      })
                    }
                  >
                    <Text style={styles.secondaryButtonText}>Forget last</Text>
                  </Pressable>
                  <Pressable
                    style={styles.secondaryButton}
                    onPress={() => void resetCurrentContext()}
                  >
                    <Text style={styles.secondaryButtonText}>Reset context</Text>
                  </Pressable>
                </View>
              </CollapsibleSection>

              <CollapsibleSection
                title="Artifacts"
                meta={`${shortStatusText(artifactStatus)} · ${artifacts.length} item${artifacts.length === 1 ? '' : 's'}`}
                defaultExpanded={false}
              >
                <View style={styles.rowWrap}>
                  <Pressable
                    style={styles.secondaryButton}
                    onPress={() => void refreshArtifacts(sessionIdRef.current)}
                  >
                    <Text style={styles.secondaryButtonText}>Refresh artifacts</Text>
                  </Pressable>
                </View>

                {artifacts.length ? (
                  artifacts.map((artifact: any) => (
                    <Pressable
                      key={artifact.artifact_id}
                      style={[
                        styles.infoCard,
                        artifactDetail?.artifact_id === artifact.artifact_id ? styles.activeInfoCard : null,
                      ]}
                      onPress={() => void openArtifact(artifact)}
                    >
                      <Text style={styles.infoCardLabel}>{artifact.title || artifact.artifact_id}</Text>
                      <Text style={styles.infoCardText}>
                        {artifact.artifact_kind} · {artifact.mime_type} · {artifact.size_bytes} bytes
                        {artifact.created_at ? ` · ${formatRelativeTime(artifact.created_at)}` : ''}
                      </Text>
                      {artifact.preview_text ? (
                        <Text style={styles.infoCardText}>{artifact.preview_text}</Text>
                      ) : null}
                    </Pressable>
                  ))
                ) : (
                  <Text style={styles.helperText}>{shortStatusText(artifactStatus)}</Text>
                )}

                {artifactDetail ? (
                  <View style={styles.infoCard}>
                    <Text style={styles.infoCardLabel}>{artifactDetail.title || artifactDetail.artifact_id}</Text>
                    <Text style={styles.infoCardText}>
                      {artifactDetail.payload_file_name || artifactDetail.file_path || artifactDetail.mime_type}
                    </Text>
                    {artifactDetail.image_base64 ? (
                      <Image
                        style={styles.artifactImage}
                        source={{ uri: `data:${artifactDetail.mime_type};base64,${artifactDetail.image_base64}` }}
                        resizeMode="contain"
                      />
                    ) : null}
                    {artifactDetail.inline_text ? (
                      <ScrollView style={styles.artifactTextBox}>
                        <Text style={styles.artifactText}>{artifactDetail.inline_text}</Text>
                      </ScrollView>
                    ) : artifactDetail.summary_text ? (
                      <Text style={styles.infoCardText}>{artifactDetail.summary_text}</Text>
                    ) : null}
                  </View>
                ) : null}
              </CollapsibleSection>

              <CollapsibleSection
                title="Memory and config"
                meta="Memory, config, analytics, security"
                defaultExpanded={false}
              >
                <View style={styles.infoCard}>
                  <Text style={styles.infoCardText}>
                    Memory file: {agentOverview?.memory_summary.memory_file_exists ? 'present' : 'missing'} · daily logs: {agentOverview?.memory_summary.daily_log_count || 0}
                  </Text>
                  <Text style={styles.infoCardText}>
                    Analytics: {agentOverview?.analytics.total_messages || 0} messages · {agentOverview?.analytics.total_commands || 0} commands · {agentOverview?.analytics.total_tokens || 0} tokens
                  </Text>
                  <Text style={styles.infoCardText}>
                    Security: {agentOverview?.security.allowed_users_count || 0} allowed users · {agentOverview?.security.max_requests_per_minute || 0}/min · {agentOverview?.security.security_events_24h || 0} events in 24h
                  </Text>
                </View>

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Search memory</Text>
                  <View style={styles.rowWrap}>
                    <TextInput
                      style={styles.workspaceInput}
                      value={memoryQuery}
                      onChangeText={setMemoryQuery}
                      placeholder="Search memory"
                      placeholderTextColor="#7f8aa3"
                    />
                    <Pressable
                      style={styles.secondaryButton}
                      onPress={() =>
                        void runWorkspaceAction(
                          'searching memory',
                          async () => {
                            const result = await searchAgentMemory(apiBaseUrl, token, memoryQuery, sessionIdRef.current);
                            setMemoryResults(result.results || []);
                          },
                          { refreshControls: false }
                        )
                      }
                    >
                      <Text style={styles.secondaryButtonText}>Search</Text>
                    </Pressable>
                  </View>
                  {memoryResults.map((result: any, index: number) => (
                    <View key={`${result.source}-${result.line || index}`} style={styles.infoCard}>
                      <Text style={styles.infoCardLabel}>
                        {result.source}
                        {result.line ? `:${result.line}` : ''}
                      </Text>
                      <Text style={styles.infoCardText}>{result.content}</Text>
                    </View>
                  ))}
                </View>

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Save memory note</Text>
                  <TextInput
                    style={styles.textAreaInput}
                    value={memoryNote}
                    onChangeText={setMemoryNote}
                    placeholder="Add a durable note or preference"
                    placeholderTextColor="#7f8aa3"
                    multiline
                  />
                  <Pressable
                    style={styles.secondaryButton}
                    onPress={() =>
                      void runWorkspaceAction('saving memory note', async () => {
                        await appendAgentMemoryNote(apiBaseUrl, token, memoryNote, sessionIdRef.current);
                        setMemoryNote('');
                      })
                    }
                  >
                    <Text style={styles.secondaryButtonText}>Save note</Text>
                  </Pressable>
                </View>

                <View style={styles.quickControlBlock}>
                  <Text style={styles.quickControlLabel}>Config</Text>
                  <View style={styles.rowWrap}>
                    <TextInput
                      style={styles.workspaceInputCompact}
                      value={configKey}
                      onChangeText={setConfigKey}
                      placeholder="config.key"
                      placeholderTextColor="#7f8aa3"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                    <TextInput
                      style={styles.workspaceInput}
                      value={configValue}
                      onChangeText={setConfigValue}
                      placeholder="value"
                      placeholderTextColor="#7f8aa3"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                  </View>
                  <View style={styles.rowWrap}>
                    <Pressable
                      style={styles.secondaryButton}
                      onPress={() =>
                        void runWorkspaceAction(
                          'loading config',
                          async () => {
                            const result = await fetchAgentConfig(apiBaseUrl, token, configKey || undefined, sessionIdRef.current);
                            setConfigEntries(result.items || []);
                          },
                          { refreshControls: false }
                        )
                      }
                    >
                      <Text style={styles.secondaryButtonText}>Load key</Text>
                    </Pressable>
                    <Pressable
                      style={styles.secondaryButton}
                      onPress={() =>
                        void runWorkspaceAction('saving config', async () => {
                          await updateAgentConfig(apiBaseUrl, token, { key: configKey, value: configValue }, sessionIdRef.current);
                          setConfigValue('');
                        })
                      }
                    >
                      <Text style={styles.secondaryButtonText}>Set value</Text>
                    </Pressable>
                  </View>
                  {(configEntries.length ? configEntries : agentOverview?.config_preview || []).slice(0, 10).map((entry: any) => (
                    <View key={entry.key} style={styles.infoCard}>
                      <Text style={styles.infoCardLabel}>{entry.key}</Text>
                      <Text style={styles.infoCardText}>{formatConfigValue(entry.value)}</Text>
                    </View>
                  ))}
                </View>
              </CollapsibleSection>

              <CollapsibleSection title="Composer tools" meta="Uploads and steering" defaultExpanded={false}>
                <View style={styles.rowWrap}>
                  <Pressable style={styles.secondaryButton} onPress={() => void uploadAttachment('camera')}>
                    <Text style={styles.secondaryButtonText}>Camera</Text>
                  </Pressable>
                  <Pressable style={styles.secondaryButton} onPress={() => void uploadAttachment('gallery')}>
                    <Text style={styles.secondaryButtonText}>Gallery</Text>
                  </Pressable>
                  <Pressable style={styles.secondaryButton} onPress={() => void uploadAttachment('document')}>
                    <Text style={styles.secondaryButtonText}>Document</Text>
                  </Pressable>
                </View>
                {steeringBetaEnabled ? (
                  <View style={styles.betaBlock}>
                    <Text style={styles.helperText}>Beta steering</Text>
                    <View style={styles.rowWrap}>
                      <Pressable
                        style={[styles.secondaryButton, interruptPolicy === 'none' ? styles.activeSecondary : null]}
                        onPress={() => setInterruptPolicy('none')}
                      >
                        <Text style={styles.secondaryButtonText}>Standard</Text>
                      </Pressable>
                      <Pressable
                        style={[styles.secondaryButton, interruptPolicy === 'steer_now' ? styles.activeSecondary : null]}
                        onPress={() => setInterruptPolicy('steer_now')}
                      >
                        <Text style={styles.secondaryButtonText}>Steer now</Text>
                      </Pressable>
                      <Pressable
                        style={[styles.secondaryButton, interruptPolicy === 'after_tool' ? styles.activeSecondary : null]}
                        onPress={() => setInterruptPolicy('after_tool')}
                      >
                        <Text style={styles.secondaryButtonText}>After tool</Text>
                      </Pressable>
                    </View>
                  </View>
                ) : null}
              </CollapsibleSection>

              <CollapsibleSection
                title="Run feed"
                meta={`${verboseMode ? 'Verbose on' : 'Verbose off'} · ${toolLogs.length ? `${toolLogs.length} recent updates` : 'Quiet'}`}
                defaultExpanded={false}
              >
                {!verboseMode ? (
                  <Text style={styles.helperText}>Verbose feed is off. Turn it on to stream tool activity live.</Text>
                ) : toolLogs.length === 0 ? (
                  <Text style={styles.helperText}>No tool or status updates yet.</Text>
                ) : (
                  toolLogs.slice(0, 14).map((entry: any, index: number) => (
                    <Text key={`${entry}-${index}`} style={styles.logLine}>{entry}</Text>
                  ))
                )}
              </CollapsibleSection>
            </ScrollView>
          </SafeAreaView>
        </View>
      </Modal>

      <View style={styles.modeTabs}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Chat selected"
          accessibilityState={{ selected: true }}
          style={[styles.modeTab, styles.modeTabActive]}
        >
          <Text style={[styles.modeTabText, styles.modeTabTextActive]}>Chat</Text>
        </Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel="Open Fleet" style={styles.modeTab} onPress={() => router.push('/fleet' as any)}>
          <Text style={styles.modeTabText}>Fleet</Text>
        </Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel="Open Agent" style={styles.modeTab} onPress={() => router.push('/agent' as any)}>
          <Text style={styles.modeTabText}>Agent</Text>
        </Pressable>
      </View>

      {fleetIdentities.length ? (
        <View style={styles.identityStrip}>
          <Text style={styles.identityStripLabel}>Identity</Text>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.identityStripList}
          >
            {fleetIdentities.map((identity: any) => {
              const active = activeFleetIdentity?.identity_id === identity.identity_id;
              return (
                <Pressable
                  key={`chat-identity-${identity.identity_id}`}
                  style={[styles.identityChip, active ? styles.identityChipActive : null]}
                  onPress={() => void selectFleetIdentityFromChat(identity)}
                >
                  <Text style={[styles.identityChipName, active ? styles.identityChipNameActive : null]} numberOfLines={1}>
                    {identityLabel(identity)}
                  </Text>
                </Pressable>
              );
            })}
          </ScrollView>
        </View>
      ) : null}

      <View style={styles.topBar}>
        <Pressable
          style={styles.topButton}
          accessibilityRole="button"
          accessibilityLabel="Open sidebar"
          onPress={() => {
            setDrawerTab('chats');
            setDrawerOpen(true);
          }}
        >
          <Text style={styles.topButtonText}>☰</Text>
          {cronUnreadCount > 0 ? (
            <View style={styles.topButtonBadge}>
              <Text style={styles.topButtonBadgeText}>{cronUnreadCount > 9 ? '9+' : String(cronUnreadCount)}</Text>
            </View>
          ) : null}
        </Pressable>
        <View style={styles.titleBlock}>
          <Text style={styles.title}>{sessionName}</Text>
          <Text style={styles.subtitle}>{subtitle}</Text>
        </View>
        <Pressable style={styles.plusButton} onPress={() => openBlankChat()}>
          <Text style={styles.plusButtonText}>+</Text>
        </Pressable>
      </View>

      <ScrollView style={styles.messages} contentContainerStyle={styles.messagesContent}>
        <RunTimeline
          messages={messages}
          timelineEvents={timelineEvents}
          verboseMode={verboseMode}
          emptyText={chatBlocked ? (!configLoaded ? 'Loading chat setup.' : 'Tap the message field to connect this phone.') : 'Your conversation will appear here.'}
        />
      </ScrollView>

      {mobileVoiceEnabled && (voiceDraft || isRecording || isVoiceBusy) ? (
        <View style={styles.voiceBanner}>
          <Text style={styles.voiceBannerTitle}>Voice</Text>
          <Text style={styles.voiceBannerText}>
            {voiceDraft || (isRecording ? 'Listening... transcript will appear here.' : 'Finalizing voice input...')}
          </Text>
        </View>
      ) : null}

      <View style={styles.composerShell}>
        <View style={styles.composerActionRow}>
          <Pressable
            style={styles.plusButtonSmall}
            onPress={() => {
              openBlankChat();
            }}
          >
            <Text style={styles.plusButtonSmallText}>+</Text>
          </Pressable>
          <Pressable
            style={[styles.composerChip, composerMenu === 'model' ? styles.composerChipActive : null]}
            onPress={() => setComposerMenu((current: any) => current === 'model' ? null : 'model')}
          >
            <Text style={[styles.composerChipText, composerMenu === 'model' ? styles.composerChipTextActive : null]} numberOfLines={1}>
              {currentVariantLabel ? `${currentModelLabel} · ${currentVariantLabel}` : currentModelLabel}
            </Text>
          </Pressable>
          <Pressable
            style={[styles.composerChip, composerMenu === 'tools' ? styles.composerChipActive : null]}
            onPress={() => setComposerMenu((current: any) => current === 'tools' ? null : 'tools')}
          >
            <Text style={[styles.composerChipText, composerMenu === 'tools' ? styles.composerChipTextActive : null]}>
              Tools · {effectiveEnabledToolPacks.length}
            </Text>
          </Pressable>
          <Pressable
            style={[styles.composerChip, composerMenu === 'permissions' ? styles.composerChipActive : null]}
            onPress={() => setComposerMenu((current: any) => current === 'permissions' ? null : 'permissions')}
          >
            <Text style={[styles.composerChipText, composerMenu === 'permissions' ? styles.composerChipTextActive : null]}>
              {activeSecurityPermissionLabel}
            </Text>
          </Pressable>
          {mobileVoiceEnabled && isRecording ? (
            <>
              <Pressable style={styles.voiceStopButton} onPress={() => void stopVoiceCapture(true)}>
                <Text style={styles.voiceButtonText}>Stop and send</Text>
              </Pressable>
              <Pressable style={styles.voiceCancelButton} onPress={() => void stopVoiceCapture(false)}>
                <Text style={styles.voiceButtonText}>Cancel</Text>
              </Pressable>
            </>
          ) : mobileVoiceEnabled ? (
            <Pressable
              style={[styles.voiceStartButton, !canStartVoice ? styles.disabledButton : null]}
              onPress={() => void startVoiceCapture()}
              disabled={!canStartVoice}
            >
              <Text style={styles.voiceButtonText}>
                {isVoiceBusy ? (steeringArmed ? 'Interrupt with voice' : 'Voice busy') : 'Start voice'}
              </Text>
            </Pressable>
          ) : null}
        </View>

        {composerMenu ? (
          <View style={styles.composerMenuPanel}>
            {composerMenu === 'model' ? (
              <View style={styles.quickControlBlock}>
                {(agentOverview?.model_groups || []).map((group: any) => (
                  <View key={`composer-model-${group.provider}`} style={styles.quickControlBlock}>
                    <Text style={styles.composerMenuLabel}>{group.provider.toUpperCase()}</Text>
                    <View style={styles.rowWrap}>
                      {group.models.map((model: any) => {
                        const active = currentModelLabel === model;
                        return (
                          <Pressable
                            key={model}
                            style={[styles.composerMenuButton, active ? styles.composerMenuButtonActive : null]}
                            onPress={() => {
                              if (sessionIdRef.current) {
                                void applyQuickAgentConfig({ model });
                              } else {
                                setDraftModel(model);
                                setStatus(`Draft model: ${model}`);
                              }
                              setComposerMenu(null);
                            }}
                          >
                            <Text style={[styles.composerMenuButtonText, active ? styles.composerMenuButtonTextActive : null]}>{model}</Text>
                          </Pressable>
                        );
                      })}
                    </View>
                  </View>
                ))}
                {(agentOverview?.available_variants || []).length ? (
                  <View style={styles.quickControlBlock}>
                    <Text style={styles.composerMenuLabel}>Variant</Text>
                    <View style={styles.rowWrap}>
                      {(agentOverview?.available_variants || []).map((variant: any) => {
                        const active = currentVariantLabel === variant;
                        return (
                          <Pressable
                            key={`composer-variant-${variant}`}
                            style={[styles.composerMenuButton, active ? styles.composerMenuButtonActive : null]}
                            onPress={() => {
                              if (sessionIdRef.current) {
                                void applyQuickAgentConfig({ variant });
                              } else {
                                setDraftVariant(variant);
                                setStatus(`Draft variant: ${variant}`);
                              }
                              setComposerMenu(null);
                            }}
                          >
                            <Text style={[styles.composerMenuButtonText, active ? styles.composerMenuButtonTextActive : null]}>{variant}</Text>
                          </Pressable>
                        );
                      })}
                    </View>
                  </View>
                ) : null}
                {(agentOverview?.available_planner_models || []).length ? (
                  <View style={styles.quickControlBlock}>
                    <Text style={styles.composerMenuLabel}>Planner</Text>
                    <View style={styles.rowWrap}>
                      {(agentOverview?.available_planner_models || []).map((planner: any) => {
                        const active = draftPlanner === planner || agentOverview?.planner_model === planner;
                        return (
                          <Pressable
                            key={`composer-planner-${planner}`}
                            style={[styles.composerMenuButton, active ? styles.composerMenuButtonActive : null]}
                            onPress={() => {
                              if (sessionIdRef.current) {
                                void applyQuickAgentConfig({ planner_model: planner });
                              } else {
                                setDraftPlanner(planner);
                                setStatus(`Draft planner: ${planner}`);
                              }
                              setComposerMenu(null);
                            }}
                          >
                            <Text style={[styles.composerMenuButtonText, active ? styles.composerMenuButtonTextActive : null]}>{planner}</Text>
                          </Pressable>
                        );
                      })}
                    </View>
                  </View>
                ) : null}
              </View>
            ) : null}

            {composerMenu === 'tools' ? (
              <View style={styles.quickControlBlock}>
                {TOOL_PACK_DEFINITIONS.map((pack) => {
                  const available = currentAvailableToolPacks.includes(pack.id);
                  const enabled = available && effectiveEnabledToolPacks.includes(pack.id);
                  const reason = String(lockReasons[pack.id] || 'Unavailable while another chat owns the required runtime lock.');
                  return (
                    <Pressable
                      key={`composer-tool-${pack.id}`}
                      style={[styles.toolPackRow, enabled ? styles.toolPackRowEnabled : null, !available ? styles.toolPackRowLocked : null]}
                      onPress={() => void toggleChatToolPack(pack.id)}
                    >
                      <View style={styles.toolPackCopy}>
                        <Text style={[styles.toolPackTitle, !available ? styles.toolPackTitleLocked : null]}>{pack.label}</Text>
                        <Text style={styles.toolPackDescription}>{available ? pack.description : reason}</Text>
                      </View>
                      <View style={[styles.toolPackSwitch, enabled ? styles.toolPackSwitchOn : null, !available ? styles.toolPackSwitchLocked : null]}>
                        <View style={[styles.toolPackKnob, enabled ? styles.toolPackKnobOn : null]} />
                      </View>
                    </Pressable>
                  );
                })}
              </View>
            ) : null}

            {composerMenu === 'permissions' ? (
              <View style={styles.rowWrap}>
                {[
                  { id: 'low' as const, label: 'Ask' },
                  { id: 'standard' as const, label: 'Approve' },
                  { id: 'full_permissions' as const, label: 'Full access' },
                ].map((mode) => (
                  <Pressable
                    key={`composer-permission-${mode.id}`}
                    style={[styles.composerMenuButton, activeSecurityPermissionMode === mode.id ? styles.composerMenuButtonActive : null]}
                    onPress={() => void updateChatSecurityPermissionMode(mode.id)}
                  >
                    <Text style={[styles.composerMenuButtonText, activeSecurityPermissionMode === mode.id ? styles.composerMenuButtonTextActive : null]}>
                      {mode.label}
                    </Text>
                  </Pressable>
                ))}
              </View>
            ) : null}
          </View>
        ) : null}

        <View style={styles.inputRow}>
          {chatBlocked ? (
            <Pressable style={[styles.input, styles.lockedInput]} onPress={() => {
              if (configLoaded) setPairPromptOpen(true);
            }}>
              <Text style={styles.lockedInputText}>
                {!configLoaded
                  ? 'Loading setup...'
                  : connectionMode === 'remote_cloud'
                  ? 'Tap to sign in and pair this phone'
                  : (apiBaseUrl ? 'Tap to finish pairing' : 'Tap to add backend and pair')}
              </Text>
            </Pressable>
          ) : (
            <TextInput
              ref={composerInputRef}
              style={styles.input}
              value={input}
              onChangeText={setInput}
              placeholder="Message Kraitos"
              placeholderTextColor="#7f8aa3"
              multiline
            />
          )}
          <Pressable
            style={[styles.sendButton, sendDisabled ? styles.sendButtonDisabled : null]}
            disabled={sendDisabled}
            accessibilityState={{ disabled: sendDisabled }}
            onPress={() => void send()}
          >
            <Text style={styles.sendButtonText}>Send</Text>
          </Pressable>
        </View>
      </View>
    </SafeAreaView>
  );
}
