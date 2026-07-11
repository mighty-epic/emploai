import { ActivityIndicator, Image, Platform, Pressable, ScrollView, Text, TextInput, View } from 'react-native';

import { FoldSection, MonoIcon } from './DesktopConversationView.components';
import { styles } from './DesktopConversationView.styles';
import type { DesktopConversationScope } from './DesktopConversationScope';

type DesktopConversationSidebarDockProps = {
  scope: DesktopConversationScope;
};

export function DesktopConversationSidebarDock({ scope }: DesktopConversationSidebarDockProps) {
    const { VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW, activeSessionArtifactCount, activity, alwaysOnEnabled, alwaysOnVoiceAutoSend, artifactDetailLoading, artifactError, artifacts, artifactsLoading, beginHorizontalResize, beginNewChat, cancelAlwaysOnSegment, chooseDraftProject, clearSidebarChatTooltipTimer, closeArtifactRail, closeReferenceRail, deleteSidebarSession, downloadArtifact, draftChat, englishVoicePack, formatAbsoluteTime, formatRelativeTime, handleVoiceEngineSelection, hebrewVoicePack, hideSidebarChatTooltip, hideVoicePanel, highlightedMessageIndex, historyAvailable, historyMessageLayoutRef, historyScrollRef, historySummary, hoveredProjectPath, hoveredSessionId, id, onOpenSetup, openArtifactExternally, openArtifactPreview, openChatContextMenu, openDraftChat, openProjectContextMenu, openProjectMenuPath, openReferenceRail, openSession, openSidebarSearchModal, pinnedChats, pinnedProjects, projectDragProps, projectGroups, projectPath, promptForProjectFolder, referenceEntries, referenceSummary, removeProjectFromSidebar, renameProject, rightSidebarWidth, router, scheduleSidebarChatTooltip, selectProjectPath, selectedArtifactDetail, selectedArtifactId, selectedArtifactSummary, selectedVoiceEngine, selectedVoicePackSummary, sessionDragProps, sessionId, sessionMeta, sessions, setHoveredProjectPath, setHoveredSessionId, setOpenProjectMenuPath, setOpenSessionMenuId, setProjectMenuRef, setProjectMenuTriggerRef, setRightSidebarWidth, setSelectedArtifactId, setSessionRowRef, setSidebarExpanded, setVoiceMode, shortStatusText, showArtifactRail, showReferenceRail, sidebarExpanded, sidebarSearchLauncherRef, sidebarState, startAlwaysOnVoice, startVoiceCapture, stopAlwaysOnVoice, stopVoiceCapture, timelineEntries, title, toggleProjectCollapsed, toggleProjectPin, toggleSessionPin, voiceDraft, voiceEngineChanging, voiceError, voiceMode, voicePackDiagnostics, voicePanelActive, voicePressActiveRef, voiceRecording, voiceRunning, voiceSummary } = scope;
    const sessionListLoading = Boolean(scope.sessionListLoading);
    const selectProjectForSidebar = (projectPathValue: string) => {
      setOpenProjectMenuPath(null);
      setOpenSessionMenuId(null);
      if (draftChat) {
        chooseDraftProject?.(projectPathValue);
      } else {
        selectProjectPath(projectPathValue);
      }
    };
    const historyAndArtifactsOpen = showReferenceRail || showArtifactRail;
    const openHistoryAndArtifacts = () => {
      openReferenceRail();
    };
    const closeHistoryAndArtifacts = () => {
      closeReferenceRail();
      closeArtifactRail();
    };

  return (
      <View
        style={[
          styles.sidebarDock,
          sidebarExpanded ? styles.sidebarDockExpanded : styles.sidebarDockCollapsed,
          sidebarExpanded ? { width: rightSidebarWidth } : null,
        ]}
      >
        {sidebarExpanded ? (
          <Pressable
            style={({ hovered }: any) => [
              styles.sidebarDockResizeHandle,
              hovered ? styles.panelResizeHandleHovered : null,
            ]}
            accessibilityRole="adjustable"
            accessibilityLabel="Resize left sidebar"
            onPressIn={(event: any) => beginHorizontalResize(event, {
              startWidth: rightSidebarWidth,
              minWidth: 276,
              maxWidth: 560,
              setWidth: setRightSidebarWidth,
            })}
          >
            {({ hovered }: any) => (
            <View style={[styles.panelResizeGrip, hovered ? styles.panelResizeGripVisible : null]}>
              <Text style={styles.panelResizeGripText}>⇔</Text>
            </View>
            )}
          </Pressable>
        ) : null}
        {sidebarExpanded ? (
          <View style={styles.sidebarDockBody}>
          <ScrollView
            style={styles.sidebarContentScroll}
            contentContainerStyle={styles.sidebarContentStack}
            onScroll={() => {
              clearSidebarChatTooltipTimer();
              hideSidebarChatTooltip();
            }}
            scrollEventThrottle={16}
          >
            <View style={styles.sidebarNavStack}>
              <Pressable
                style={({ hovered }: any) => [
                  styles.sidebarListRow,
                  hovered ? styles.sidebarListRowHovered : null,
                ]}
                onPress={() => void beginNewChat()}
              >
                <MonoIcon name="plus" style={styles.sidebarListRowIcon} />
                <Text style={styles.sidebarListRowTitle}>New chat</Text>
              </Pressable>

              <Pressable
                ref={sidebarSearchLauncherRef}
                style={({ hovered }: any) => [
                  styles.sidebarMenuRowMinimal,
                  hovered ? styles.sidebarMenuRowMinimalHovered : null,
                ]}
                onPress={openSidebarSearchModal}
              >
                <MonoIcon name="search" style={styles.sidebarSearchGlyph} />
                <Text style={styles.sidebarSearchButtonText}>Search</Text>
              </Pressable>

              <View style={styles.sidebarMenuList}>
                <Pressable
                  style={({ hovered }: any) => [
                    styles.sidebarMenuRowMinimal,
                    hovered ? styles.sidebarMenuRowMinimalHovered : null,
                    historyAndArtifactsOpen ? styles.sidebarMenuRowMinimalActive : null,
                  ]}
                  onPress={() => {
                    if (historyAndArtifactsOpen) {
                      closeHistoryAndArtifacts();
                    } else {
                      openHistoryAndArtifacts();
                    }
                  }}
                >
                  <MonoIcon name="archive" style={styles.sidebarMenuRowGlyph} />
                  <Text style={styles.sidebarMenuRowLabelMinimal}>History & Artifacts</Text>
                </Pressable>

                <Pressable
                  style={({ hovered }: any) => [
                    styles.sidebarMenuRowMinimal,
                    hovered ? styles.sidebarMenuRowMinimalHovered : null,
                  ]}
                  onPress={() => router.push('/cron')}
                >
                  <MonoIcon name="automation" style={styles.sidebarMenuRowGlyph} />
                  <Text style={styles.sidebarMenuRowLabelMinimal}>Automations</Text>
                </Pressable>

              </View>
            </View>

            {pinnedProjects.length || pinnedChats.length ? (
              <View style={styles.sidebarPinnedSection}>
                <View style={styles.sidebarListSectionHeader}>
                  <Text style={styles.sidebarListSectionTitle}>Pinned</Text>
                </View>
                <View style={styles.sidebarSimpleList}>
                  {pinnedChats.map(({ session }: any) => {
                    const pinnedChatActionsVisible = hoveredSessionId === session.id;
                    return (
                      <View
                        key={`pinned-chat-${session.id}`}
                        {...(Platform.OS === 'web'
                          ? {
                              onMouseEnter: () => {
                                setHoveredSessionId(session.id);
                                scheduleSidebarChatTooltip(session, session.workspace || null);
                              },
                              onMouseLeave: () => {
                                setHoveredSessionId((current: any) => (
                                  current === session.id ? null : current
                                ));
                                clearSidebarChatTooltipTimer();
                                hideSidebarChatTooltip(session.id);
                              },
                            } as any
                          : {})}
                      >
                        <Pressable
                          ref={setSessionRowRef(session.id)}
                          style={({ pressed }: any) => [
                            styles.sidebarSimpleRow,
                            pinnedChatActionsVisible ? styles.sidebarSimpleRowHovered : null,
                            session.id === sessionId ? styles.sidebarSimpleRowActive : null,
                            pressed ? styles.sidebarSimpleRowPressed : null,
                          ]}
                          onPress={() => {
                            clearSidebarChatTooltipTimer();
                            hideSidebarChatTooltip(session.id);
                            void openSession(session.id);
                          }}
                          {...(Platform.OS === 'web'
                            ? ({ onContextMenu: (event: any) => openChatContextMenu(event, session, session.workspace || null) } as any)
                            : {})}
                        >
                          <View style={styles.sidebarSimpleRowCopy}>
                            <View style={styles.sidebarRunningRow}>
                              {session.is_running ? <View style={styles.sidebarRunningDot} /> : null}
                              <Text style={styles.sidebarSimpleRowTitle} numberOfLines={1}>{session.name}</Text>
                            </View>
                          </View>
                          {pinnedChatActionsVisible ? (
                            <View style={styles.projectChatActions}>
                              <Pressable
                                accessibilityRole="button"
                                accessibilityLabel="Unpin chat"
                                style={styles.projectChatActionButton}
                                onPress={(event: any) => {
                                  event?.stopPropagation?.();
                                  event?.preventDefault?.();
                                  event?.nativeEvent?.stopPropagation?.();
                                  event?.nativeEvent?.preventDefault?.();
                                  clearSidebarChatTooltipTimer();
                                  hideSidebarChatTooltip(session.id);
                                  toggleSessionPin(session);
                                }}
                              >
                                <MonoIcon name="pin" style={[styles.projectChatActionText, styles.projectChatActionTextActive]} />
                              </Pressable>
                              <Pressable
                                accessibilityRole="button"
                                accessibilityLabel="Archive chat"
                                style={styles.projectChatActionButton}
                                onPress={(event: any) => {
                                  event?.stopPropagation?.();
                                  event?.preventDefault?.();
                                  event?.nativeEvent?.stopPropagation?.();
                                  event?.nativeEvent?.preventDefault?.();
                                  clearSidebarChatTooltipTimer();
                                  hideSidebarChatTooltip(session.id);
                                  void deleteSidebarSession(session);
                                }}
                              >
                                <MonoIcon name="archive" style={styles.projectChatActionText} />
                              </Pressable>
                            </View>
                          ) : (
                            <Text style={styles.sidebarSimpleRowMeta}>
                              {session.is_running ? 'Running' : formatRelativeTime(session.updated_at)}
                            </Text>
                          )}
                        </Pressable>
                      </View>
                    );
                  })}
                  {pinnedProjects.map((project: any) => (
                    <Pressable
                      key={`pinned-project-${project.path}`}
                      style={({ hovered }: any) => [
                        styles.sidebarSimpleRow,
                        hovered ? styles.sidebarSimpleRowHovered : null,
                      ]}
                      onPress={() => {
                        selectProjectForSidebar(project.path);
                        setSidebarExpanded(true);
                      }}
                      {...(Platform.OS === 'web'
                        ? ({ onContextMenu: (event: any) => openProjectContextMenu(event, project) } as any)
                        : {})}
                    >
                      <View style={styles.sidebarSimpleRowCopy}>
                        <Text style={styles.sidebarSimpleRowTitle} numberOfLines={1}>{project.label}</Text>
                        <Text style={styles.sidebarSimpleRowSubtle} numberOfLines={1}>{project.hint || project.path}</Text>
                      </View>
                      <Text style={styles.sidebarSimpleRowMeta}>Folder</Text>
                    </Pressable>
                  ))}
                </View>
              </View>
            ) : null}

            <View style={styles.sidebarProjectsSection}>
              <View style={styles.sidebarListSectionHeader}>
                <Text style={styles.sidebarListSectionTitle}>Projects</Text>
                <Pressable onPress={() => void promptForProjectFolder()}>
                  <Text style={styles.sidebarSectionActionText}>Add Folder</Text>
                </Pressable>
              </View>
                {sessionListLoading && projectGroups.length === 0 ? (
                  <View style={styles.sidebarLoadingCard}>
                    <ActivityIndicator color="#78b7ff" />
                    <Text style={styles.sidebarLoadingText}>Loading chats...</Text>
                  </View>
                ) : projectGroups.length === 0 ? (
                  <View style={styles.emptyCard}>
                    <Text style={styles.emptyTitle}>No folders yet</Text>
                    <Text style={styles.emptyText}>Add a folder or start a new chat to create the first project group in this sidebar.</Text>
                  </View>
                ) : (
                  <View style={styles.sidebarProjectList}>
                    {projectGroups.map((project: any) => {
                    const projectHasDraft = draftChat?.projectPath === project.path;
                    const projectActionsVisible = hoveredProjectPath === project.path || openProjectMenuPath === project.path || projectHasDraft;
                    return (
                      <View
                        key={`project-${project.path}`}
                        style={styles.projectCard}
                        {...(Platform.OS === 'web'
                          ? {
                              onMouseEnter: () => setHoveredProjectPath(project.path),
                              onMouseLeave: () => setHoveredProjectPath((current: any) => (
                                current === project.path ? null : current
                              )),
                              onContextMenu: (event: any) => openProjectContextMenu(event, project),
                            } as any
                          : {})}
                        {...projectDragProps(project.path)}
                      >
                        <View style={[
                          styles.projectHeaderRow,
                          projectActionsVisible ? styles.projectHeaderRowHovered : null,
                          projectHasDraft ? styles.projectHeaderRowActive : null,
                        ]}>
                          <Pressable
                            style={styles.projectHeaderMain}
                            onPress={() => {
                              selectProjectForSidebar(project.path);
                            }}
                          >
                            <Pressable
                              style={styles.projectFolderToggle}
                              onPress={() => toggleProjectCollapsed(project.path)}
                            >
                              <MonoIcon
                                name={project.collapsed ? 'folder_closed' : 'folder_open'}
                                style={styles.projectFolderToggleIcon}
                              />
                            </Pressable>
                            <Text style={styles.projectTitle} numberOfLines={1}>{project.label}</Text>
                            {projectActionsVisible ? (
                              <MonoIcon
                                name={project.collapsed ? 'chevron_down' : 'chevron_up'}
                                style={styles.projectFolderChevron}
                              />
                            ) : null}
                          </Pressable>
                          {projectActionsVisible ? (
                            <View style={styles.projectHeaderActions}>
                              <Pressable
                                ref={setProjectMenuTriggerRef(project.path)}
                                style={styles.projectHeaderActionButton}
                                onPress={() => setOpenProjectMenuPath((current: any) => (
                                  current === project.path ? null : project.path
                                ))}
                              >
                                <MonoIcon name="more" style={styles.projectHeaderActionText} />
                              </Pressable>
                              <Pressable
                                style={styles.projectHeaderActionButton}
                                onPress={() => {
                                  setOpenProjectMenuPath(null);
                                  void openDraftChat(project.path);
                                }}
                              >
                                <MonoIcon name="compose" style={styles.projectHeaderActionText} />
                              </Pressable>
                            </View>
                          ) : null}
                        </View>

	                        {openProjectMenuPath === project.path ? (
	                          <View ref={setProjectMenuRef(project.path)} style={styles.projectMenu}>
	                            <Pressable
	                              style={styles.projectMenuItem}
	                              onPress={() => {
	                                toggleProjectPin(project.path);
	                                setOpenProjectMenuPath(null);
	                              }}
	                            >
	                              <Text style={styles.projectMenuItemText}>{project.pinned ? 'Unpin folder' : 'Pin folder'}</Text>
	                            </Pressable>
	                            <Pressable
	                              style={styles.projectMenuItem}
	                              onPress={() => renameProject(project.path)}
	                            >
	                              <Text style={styles.projectMenuItemText}>Rename folder</Text>
                            </Pressable>
	                            <Pressable
	                              style={styles.projectMenuItem}
	                              onPress={() => removeProjectFromSidebar(project.path)}
	                            >
	                              <Text style={[styles.projectMenuItemText, styles.projectMenuItemTextWarn]}>Remove folder</Text>
	                            </Pressable>
	                          </View>
	                        ) : null}

                        {!project.collapsed ? (
                          <View style={styles.projectContent}>
                            {project.sessions.map((item: any) => {
                              const selected = item.id === sessionId;
                              const sessionActionsVisible = hoveredSessionId === item.id;
                              return (
                                <View
                                  key={item.id}
                                  {...(Platform.OS === 'web'
                                    ? {
                                        onMouseEnter: () => {
                                          setHoveredSessionId(item.id);
                                          scheduleSidebarChatTooltip(item, project.path);
                                        },
                                        onMouseLeave: () => {
                                          setHoveredSessionId((current: any) => (
                                            current === item.id ? null : current
                                          ));
                                          clearSidebarChatTooltipTimer();
                                          hideSidebarChatTooltip(item.id);
                                        },
                                      } as any
                                    : {})}
                                >
                                  <View
                                    ref={setSessionRowRef(item.id)}
                                    style={[
                                      styles.projectChatRow,
                                      sessionActionsVisible ? styles.projectChatRowHovered : null,
                                      selected ? styles.projectChatRowActive : null,
                                    ]}
                                    {...sessionDragProps(project.path, item.id)}
                                    {...(Platform.OS === 'web'
                                      ? ({ onContextMenu: (event: any) => openChatContextMenu(event, item, project.path) } as any)
                                      : {})}
                                  >
                                    <Pressable
                                      style={styles.projectChatPrimary}
                                      onPress={() => {
                                        setOpenSessionMenuId(null);
                                        clearSidebarChatTooltipTimer();
                                        hideSidebarChatTooltip(item.id);
                                        void openSession(item.id);
                                      }}
                                    >
                                      <View style={styles.projectChatTitleRow}>
                                        <View style={styles.sidebarRunningRow}>
                                          {item.is_running ? <View style={styles.sidebarRunningDot} /> : null}
                                          <Text style={styles.projectChatTitle} numberOfLines={1}>{item.name}</Text>
                                        </View>
                                        {!sessionActionsVisible ? (
                                          <Text style={styles.projectChatAge}>{item.is_running ? 'Running' : formatRelativeTime(item.updated_at)}</Text>
                                        ) : null}
                                      </View>
                                    </Pressable>
                                    {sessionActionsVisible ? (
                                      <View style={styles.projectChatActions}>
                                        <Pressable
                                          style={styles.projectChatActionButton}
                                          onPress={(event: any) => {
                                            event?.stopPropagation?.();
                                            event?.preventDefault?.();
                                            event?.nativeEvent?.stopPropagation?.();
                                            event?.nativeEvent?.preventDefault?.();
                                            clearSidebarChatTooltipTimer();
                                            hideSidebarChatTooltip(item.id);
                                            toggleSessionPin(item);
                                          }}
                                        >
                                          <MonoIcon
                                            name="pin"
                                            style={[
                                              styles.projectChatActionText,
                                              sidebarState.sessionMeta[item.id]?.pinned ? styles.projectChatActionTextActive : null,
                                            ]}
                                          />
                                        </Pressable>
                                        <Pressable
                                          style={styles.projectChatActionButton}
                                          onPress={(event: any) => {
                                            event?.stopPropagation?.();
                                            event?.preventDefault?.();
                                            event?.nativeEvent?.stopPropagation?.();
                                            event?.nativeEvent?.preventDefault?.();
                                            clearSidebarChatTooltipTimer();
                                            hideSidebarChatTooltip(item.id);
                                            void deleteSidebarSession(item);
                                          }}
                                        >
                                          <MonoIcon name="archive" style={styles.projectChatActionText} />
                                        </Pressable>
                                      </View>
                                    ) : null}
                                  </View>
                                </View>
                              );
                            })}

                            {project.activity.map((activityItem: any) => (
                              <View key={activityItem.id} style={styles.projectActivityRow}>
                                <Text style={styles.projectActivityText}>{activityItem.message}</Text>
                                <Text style={styles.projectActivityMeta}>{formatRelativeTime(activityItem.timestamp)}</Text>
                              </View>
                            ))}

                            {project.sessions.length === 0 && !projectHasDraft && project.activity.length === 0 ? (
                              <View style={styles.projectEmptyState}>
                                <Text style={styles.projectEmptyText}>No chats in this folder yet.</Text>
                              </View>
                            ) : null}
                          </View>
                        ) : null}
                      </View>
                    );
                  })}
                  </View>
                )}
              </View>

            {voicePanelActive ? (
              <>
              <View style={styles.sidebarInsetDivider} />
              <View style={styles.voicePanel}>
                <View style={styles.voicePanelHeader}>
                  <View style={styles.voicePanelHeaderCopy}>
                    <Text style={styles.voiceLabel}>Jarvis Voice State</Text>
                    <Text style={styles.voiceValue}>{voiceSummary}</Text>
                    <Text style={styles.voiceHint}>{selectedVoicePackSummary}</Text>
                    {voicePackDiagnostics ? (
                      <Text style={styles.voiceHint}>{voicePackDiagnostics}</Text>
                    ) : null}
                  </View>
                  <View style={styles.voicePanelHeaderActions}>
                    <Pressable style={styles.voicePanelHeaderAction} onPress={() => onOpenSetup?.()}>
                      <Text style={styles.voicePanelHeaderActionText}>Open Setup</Text>
                    </Pressable>
                    <Pressable style={styles.voicePanelHeaderAction} onPress={hideVoicePanel}>
                      <Text style={styles.voicePanelHeaderActionText}>Hide Jarvis</Text>
                    </Pressable>
                  </View>
                </View>

                <View style={styles.voiceLanguageRow}>
                  <Pressable
                    style={[
                      styles.voiceLanguageChip,
                      selectedVoiceEngine === VOICE_ENGINE_ENGLISH ? styles.voiceLanguageChipActive : null,
                      !englishVoicePack?.available || voiceEngineChanging ? styles.voiceModeChipDisabled : null,
                    ]}
                    onPress={() => {
                      void handleVoiceEngineSelection(VOICE_ENGINE_ENGLISH);
                    }}
                  >
                    <Text
                      style={[
                        styles.voiceLanguageChipText,
                        selectedVoiceEngine === VOICE_ENGINE_ENGLISH ? styles.voiceLanguageChipTextActive : null,
                      ]}
                    >
                      {voiceEngineChanging && selectedVoiceEngine !== VOICE_ENGINE_ENGLISH ? 'Switching…' : 'English Path'}
                    </Text>
                  </Pressable>
                  <Pressable
                    style={[
                      styles.voiceLanguageChip,
                      selectedVoiceEngine === VOICE_ENGINE_HEBREW ? styles.voiceLanguageChipActive : null,
                      !hebrewVoicePack?.available || voiceEngineChanging ? styles.voiceModeChipDisabled : null,
                    ]}
                    onPress={() => {
                      void handleVoiceEngineSelection(VOICE_ENGINE_HEBREW);
                    }}
                  >
                    <Text
                      style={[
                        styles.voiceLanguageChipText,
                        selectedVoiceEngine === VOICE_ENGINE_HEBREW ? styles.voiceLanguageChipTextActive : null,
                      ]}
                    >
                      {voiceEngineChanging && selectedVoiceEngine !== VOICE_ENGINE_HEBREW ? 'Switching…' : 'Hebrew Path'}
                    </Text>
                  </Pressable>
                </View>

                <View style={styles.voiceModeRow}>
                  <Pressable
                    style={[
                      styles.voiceModeChip,
                      voiceMode === 'push_to_talk' && !alwaysOnEnabled ? styles.voiceModeChipActive : null,
                      (voiceRunning || voiceRecording || alwaysOnEnabled) ? styles.voiceModeChipDisabled : null,
                    ]}
                    disabled={voiceRunning || voiceRecording || alwaysOnEnabled}
                    onPress={() => setVoiceMode('push_to_talk')}
                  >
                    <Text
                      style={[
                        styles.voiceModeChipText,
                        voiceMode === 'push_to_talk' && !alwaysOnEnabled ? styles.voiceModeChipTextActive : null,
                      ]}
                    >
                      Push To Talk
                    </Text>
                  </Pressable>
                  <Pressable
                    style={[
                      styles.voiceModeChip,
                      (voiceMode === 'always_on' || alwaysOnEnabled) ? styles.voiceModeChipActive : null,
                      (voiceRunning || voiceRecording) && !alwaysOnEnabled ? styles.voiceModeChipDisabled : null,
                    ]}
                    disabled={(voiceRunning || voiceRecording) && !alwaysOnEnabled}
                    onPress={() => setVoiceMode('always_on')}
                  >
                    <Text
                      style={[
                        styles.voiceModeChipText,
                        (voiceMode === 'always_on' || alwaysOnEnabled) ? styles.voiceModeChipTextActive : null,
                      ]}
                    >
                      Always On
                    </Text>
                  </Pressable>
                </View>

                <View style={styles.voiceRibbon}>
                  <View style={styles.voiceRibbonPrimary}>
                    <Text style={styles.voiceLabel}>
                      {voiceMode === 'always_on' || alwaysOnEnabled ? 'Always On' : 'Push To Talk'}
                    </Text>
                    <Text style={styles.voiceHint}>
                      {voiceMode === 'always_on' || alwaysOnEnabled
                        ? alwaysOnVoiceAutoSend
                          ? 'The mic stays open locally. Speech above the gate threshold is transcribed and sent when the segment ends.'
                          : 'The mic stays open locally. Speech above the gate threshold is transcribed into the message box for review.'
                        : 'Hold to record. Partial transcript appears below while you speak. Release to send the turn.'}
                    </Text>
                  </View>
                  <View style={styles.voiceRibbonActions}>
                    {voiceMode === 'always_on' || alwaysOnEnabled ? (
                      <>
                        <Pressable
                          style={[styles.ribbonButton, alwaysOnEnabled ? styles.ribbonButtonActive : null]}
                          disabled={voiceRunning && !alwaysOnEnabled}
                          onPress={() => {
                            if (alwaysOnEnabled) {
                              void stopAlwaysOnVoice();
                            } else {
                              void startAlwaysOnVoice();
                            }
                          }}
                        >
                          <Text style={styles.ribbonButtonText}>
                            {alwaysOnEnabled ? 'Stop Always On' : 'Start Always On'}
                          </Text>
                        </Pressable>
                        <Pressable
                          style={[
                            styles.ribbonButton,
                            styles.ribbonButtonMuted,
                            !voiceRecording ? styles.ribbonButtonDisabled : null,
                          ]}
                          disabled={!voiceRecording}
                          onPress={() => void cancelAlwaysOnSegment()}
                        >
                          <Text style={styles.ribbonButtonText}>Cancel Segment</Text>
                        </Pressable>
                      </>
                    ) : (
                      <>
                        <Pressable
                          style={[styles.ribbonButton, voiceRecording ? styles.ribbonButtonActive : null]}
                          disabled={voiceRunning}
                          onPressIn={() => {
                            if (!voiceRecording && !voiceRunning) {
                              void startVoiceCapture();
                            }
                          }}
                          onPressOut={() => {
                            if (voiceRecording || voicePressActiveRef.current) {
                              void stopVoiceCapture(true);
                            }
                          }}
                        >
                          <Text style={styles.ribbonButtonText}>{voiceRecording ? 'Release To Send' : 'Hold To Talk'}</Text>
                        </Pressable>
                        <Pressable
                          style={[styles.ribbonButton, styles.ribbonButtonMuted, !voiceRecording ? styles.ribbonButtonDisabled : null]}
                          disabled={!voiceRecording}
                          onPress={() => void stopVoiceCapture(false)}
                        >
                          <Text style={styles.ribbonButtonText}>Cancel</Text>
                        </Pressable>
                      </>
                    )}
                  </View>
                </View>

                {voiceDraft ? (
                  <View style={styles.transcriptDraft}>
                    <Text style={styles.transcriptLabel}>Live transcript draft</Text>
                    <Text style={styles.transcriptText}>{voiceDraft}</Text>
                  </View>
                ) : null}

                {voiceError ? (
                  <View style={styles.voiceErrorCard}>
                    <Text style={styles.voiceErrorTitle}>Jarvis diagnostics</Text>
                    <Text style={styles.voiceErrorText}>{shortStatusText(voiceError)}</Text>
                  </View>
                ) : null}
              </View>
              </>
            ) : null}

            {historyAndArtifactsOpen ? (
              <View style={styles.referencePanel}>
                <View style={styles.referencePanelHeader}>
                  <View style={styles.referencePanelHeaderCopy}>
                    <Text style={styles.referencePanelTitle}>History & Artifacts</Text>
                    <Text style={styles.referencePanelSummary}>
                      {historyAvailable
                        ? `${referenceEntries.length ? `${historySummary} · ${referenceSummary}` : historySummary} · ${activeSessionArtifactCount ? `${activeSessionArtifactCount} artifacts` : 'no artifacts'}`
                        : activeSessionArtifactCount
                          ? `${activeSessionArtifactCount} saved artifacts`
                          : 'No history or artifacts yet'}
                    </Text>
                  </View>
                  <Pressable style={styles.referencePanelCloseButton} onPress={closeHistoryAndArtifacts}>
                    <Text style={styles.referencePanelCloseText}>Close</Text>
                  </Pressable>
                </View>
                <View style={styles.referencePanelSection}>
                  <Text style={styles.referencePanelSectionTitle}>History</Text>
                  {historyAvailable ? (
                    <ScrollView ref={historyScrollRef} contentContainerStyle={styles.referenceStack}>
                      {timelineEntries.map((entry: any) => (
                        <View
                          key={`timeline-${entry.id}`}
                          onLayout={(event: any) => {
                            if (entry.kind === 'message') {
                              historyMessageLayoutRef.current[entry.sourceMessageIndex] = event.nativeEvent.layout.y;
                            }
                          }}
                          style={[
                            styles.referenceCard,
                            entry.kind === 'message' && highlightedMessageIndex === entry.sourceMessageIndex
                              ? styles.searchJumpHighlight
                              : null,
                            entry.tone === 'accent'
                              ? styles.activityItemAccent
                              : entry.tone === 'warn'
                                ? styles.activityItemWarn
                                : entry.tone === 'error'
                                  ? styles.activityItemError
                                  : null,
                          ]}
                        >
                          <View style={styles.referenceCardHeader}>
                            <Text style={styles.referenceCardEyebrow}>{entry.eyebrow}</Text>
                            <Text style={styles.referenceCardTitle}>{entry.label}</Text>
                          </View>
                          <Text style={styles.referenceCardMeta}>
                            {entry.timestamp ? formatAbsoluteTime(entry.timestamp) : 'timeline event'}
                          </Text>
                          <Text style={styles.referenceCardBody}>{entry.body}</Text>
                        </View>
                      ))}
                    </ScrollView>
                  ) : (
                    <View style={styles.emptyCard}>
                      <Text style={styles.emptyTitle}>No history yet</Text>
                      <Text style={styles.emptyText}>Chat timeline events and referenced messages for this session will appear here.</Text>
                    </View>
                  )}
                </View>
                {showArtifactRail ? (
                  <View style={styles.referencePanelSection}>
                    <Text style={styles.referencePanelSectionTitle}>Artifacts</Text>
                    {artifactsLoading ? (
                  <View style={styles.emptyCard}>
                    <Text style={styles.emptyTitle}>Loading artifacts…</Text>
                    <Text style={styles.emptyText}>Pulling saved files, screenshots, and command outputs for this chat.</Text>
                  </View>
                ) : artifactError ? (
                  <View style={styles.emptyCard}>
                    <Text style={styles.emptyTitle}>Artifact view unavailable</Text>
                    <Text style={styles.emptyText}>{shortStatusText(artifactError)}</Text>
                  </View>
                ) : artifacts.length === 0 ? (
                  <View style={styles.emptyCard}>
                    <Text style={styles.emptyTitle}>No artifacts yet</Text>
                    <Text style={styles.emptyText}>Files, screenshots, OCR, browser captures, uploads, and command outputs for this chat will land here.</Text>
                  </View>
                ) : (
                  <View style={styles.artifactPanelStack}>
                    <ScrollView style={styles.artifactListScroll} contentContainerStyle={styles.artifactList}>
                      {artifacts.map((artifact: any) => {
                        const selected = artifact.artifact_id === (selectedArtifactId || selectedArtifactSummary?.artifact_id);
                        return (
                          <Pressable
                            key={artifact.artifact_id}
                            style={[styles.artifactRow, selected ? styles.artifactRowActive : null]}
                            onPress={() => {
                              setSelectedArtifactId(artifact.artifact_id);
                              void openArtifactPreview(artifact.artifact_id);
                            }}
                          >
                            <Text style={styles.artifactRowTitle} numberOfLines={1}>{artifact.title}</Text>
                            <Text style={styles.artifactRowMeta} numberOfLines={1}>
                              {artifact.artifact_kind} · {formatRelativeTime(artifact.created_at)}
                            </Text>
                            <Text style={styles.artifactRowPreview} numberOfLines={2}>
                              {artifact.preview_text || artifact.summary_text || 'Saved artifact'}
                            </Text>
                          </Pressable>
                        );
                      })}
                    </ScrollView>
                    <View style={styles.artifactPreviewCard}>
                      <View style={styles.artifactPreviewHeader}>
                        <View style={styles.artifactPreviewHeaderCopy}>
                          <Text style={styles.artifactPreviewTitle} numberOfLines={1}>
                            {selectedArtifactDetail?.title || selectedArtifactSummary?.title || 'Artifact preview'}
                          </Text>
                          <Text style={styles.artifactPreviewMeta} numberOfLines={1}>
                            {selectedArtifactDetail?.artifact_kind || selectedArtifactSummary?.artifact_kind || 'artifact'}
                            {selectedArtifactDetail?.payload_file_name ? ` · ${selectedArtifactDetail.payload_file_name}` : ''}
                          </Text>
                        </View>
                        <View style={styles.artifactPreviewActions}>
                          {selectedArtifactSummary ? (
                            <>
                              <Pressable style={styles.referencePanelCloseButton} onPress={() => void openArtifactExternally(selectedArtifactSummary.artifact_id)}>
                                <Text style={styles.referencePanelCloseText}>Open</Text>
                              </Pressable>
                              <Pressable style={styles.referencePanelCloseButton} onPress={() => void downloadArtifact(selectedArtifactSummary.artifact_id)}>
                                <Text style={styles.referencePanelCloseText}>Download</Text>
                              </Pressable>
                            </>
                          ) : null}
                        </View>
                      </View>
                      {artifactDetailLoading ? (
                        <Text style={styles.emptyText}>Loading preview…</Text>
                      ) : selectedArtifactDetail?.image_base64 ? (
                        <Image
                          source={{ uri: `data:${selectedArtifactDetail.mime_type};base64,${selectedArtifactDetail.image_base64}` }}
                          style={styles.artifactPreviewImage}
                          resizeMode="contain"
                        />
                      ) : (
                        <ScrollView style={styles.artifactPreviewScroll}>
                          <Text style={styles.artifactPreviewText}>
                            {selectedArtifactDetail?.inline_text
                              || selectedArtifactDetail?.preview_text
                              || selectedArtifactSummary?.preview_text
                              || 'No inline preview available.'}
                          </Text>
                        </ScrollView>
                      )}
                    </View>
                  </View>
                    )}
                  </View>
                ) : null}
              </View>
            ) : null}

          </ScrollView>
          </View>
        ) : null}
      </View>
  );
}
