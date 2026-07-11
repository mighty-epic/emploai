import { useEffect, useState } from 'react';
import { Animated, Image, Platform, Pressable, ScrollView, Text, TextInput, View } from 'react-native';

import { DESKTOP_COMMAND_PLACEHOLDER } from '@/desktop/desktopCommands';
import { DesktopModelPickerMenu } from '@/desktop/DesktopModelPickerMenu';
import { labelForMessage } from '@/desktop/desktopMessages';
import { taskBoardStatusLabel } from '@/desktop/desktopTaskBoard';
import { FoldSection, MonoIcon } from './DesktopConversationView.components';
import { COMPOSER_MAX_HEIGHT } from './DesktopConversationView.styleConstants';
import { styles } from './DesktopConversationView.styles';
import { DesktopConversationJarvisStage } from './DesktopConversationJarvisStage';
import { DesktopConversationOverlays } from './DesktopConversationOverlays';
import { DesktopConversationSidebarDock } from './DesktopConversationSidebarDock';
import { DesktopLiveCommandCard } from './DesktopLiveCommandCard';
import { DesktopProviderFailureCard } from './DesktopProviderFailureCard';
import { DesktopArchiveUndoToast } from './DesktopArchiveUndoToast';
import type { DesktopConversationScope } from './DesktopConversationScope';
import { extractProposedPlan, planQuestionFromMessage, visiblePlanText, modeStatusLabel } from './desktopChatModes';

type DesktopConversationRenderProps = {
  scope: DesktopConversationScope;
};

function timelineEventDisplayParts(entry: any) {
  const entryKind = String(entry.eyebrow || '').toLowerCase();
  const isToolEntry = entryKind === 'tool';
  const isCommandEntry = entryKind === 'command';
  const isLiveCommandEntry = isCommandEntry && entry.metadata?.live_command === true;
  const toolSections = isToolEntry ? String(entry.body || '').split(/\n(?:->|→)\s*/) : [];
  const commandText = isToolEntry
    ? (toolSections[0] || entry.body)
    : isCommandEntry
      ? String(entry.label || '').replace(/^command\s*·\s*/i, '').trim() || entry.label
      : entry.body;
  const resultText = isToolEntry
    ? (toolSections.length > 1 ? toolSections.slice(1).join('\n-> ') : '')
    : isCommandEntry
      ? entry.body
      : '';
  const toolContextText = resultText
    ? `${commandText}\n\nCommand Result\n${resultText}`
    : commandText;
  return {
    entryKind,
    isToolEntry,
    isCommandEntry,
    isLiveCommandEntry,
    commandText: String(commandText || ''),
    resultText: String(resultText || ''),
    toolContextText: String(toolContextText || ''),
    eyebrowLabel: isToolEntry || isCommandEntry ? 'Command' : entry.label,
  };
}

function pluralizeRunCount(count: number, singular: string) {
  return `${count} ${singular}${count === 1 ? '' : 's'}`;
}

function formatDurationMs(durationMs: number) {
  const totalSeconds = Math.max(0, Math.round(durationMs / 1000));
  if (totalSeconds < 60) {
    return `${totalSeconds}s`;
  }
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes < 60) {
    return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

function runDurationLabel(entry: any, isActive: boolean) {
  const events = Array.isArray(entry.events) ? entry.events : [];
  const firstTime = Date.parse(events[0]?.timestamp || entry.timestamp || '');
  const lastEventTime = Date.parse(events[events.length - 1]?.timestamp || entry.timestamp || '');
  if (!Number.isFinite(firstTime)) {
    return isActive ? 'Working' : 'Worked';
  }
  const endTime = isActive ? Date.now() : (Number.isFinite(lastEventTime) ? lastEventTime : firstTime);
  return `${isActive ? 'Working' : 'Worked'} for ${formatDurationMs(endTime - firstTime)}`;
}

function compactRunActivityLabel(entry: any) {
  const parts = [
    entry.commandCount ? pluralizeRunCount(entry.commandCount, 'command') : null,
    entry.toolCount && entry.toolCount !== entry.commandCount ? pluralizeRunCount(entry.toolCount, 'tool') : null,
    entry.errorCount ? pluralizeRunCount(entry.errorCount, 'error') : null,
  ].filter(Boolean);
  return parts.length ? `Ran ${parts.join(' · ')}` : `${pluralizeRunCount(entry.eventCount || 0, 'event')}`;
}

function editSummaryFromMessage(message: any) {
  const metadata = (message?.raw?.metadata || {}) as Record<string, any>;
  const summary = metadata.edit_summary || message?.raw?.edit_summary;
  if (!summary || typeof summary !== 'object' || !Array.isArray(summary.files) || !summary.files.length) {
    return null;
  }
  const files = summary.files
    .map((file: any) => ({
      path: String(file?.path || '').trim(),
      additions: Number(file?.additions || 0),
      deletions: Number(file?.deletions || 0),
      binary: Boolean(file?.binary),
    }))
    .filter((file: any) => file.path);
  if (!files.length) {
    return null;
  }
  return {
    fileCount: Number(summary.file_count || files.length),
    additions: Number(summary.additions || 0),
    deletions: Number(summary.deletions || 0),
    files,
    truncated: Boolean(summary.truncated),
  };
}

export function DesktopConversationRender({ scope }: DesktopConversationRenderProps) {
    const { STT_BACKEND_LOCAL_WHISPER, STT_BACKEND_OPENAI_REALTIME, TTS_BACKEND_KOKORO, TTS_BACKEND_KYUTAI, activeCommandPanel, activePermissionInfo, activePermissionInfoId, activeTaskBoard, activeToolPackInfo, activeToolPackInfoAvailable, activeToolPackInfoConfiguredEnabled, activeToolPackInfoDisabledReason, askForProjectFolderChoice, assistantDraft, beginHorizontalResize, chatSettingsBotConfigId, chatSettingsSession, chatSettingsSleepSessionId, chooseModel, choosePlannerModel, chooseVariant, clearToolPackInfoHideTimer, commandSuggestionMenuRef, commandSuggestions, completedTaskBoards, composerInputHeight, composerTextRegionRef, confirmPendingSessionSwitch, confirmationDialog, contextBreakdownLabel, contextPercent, contextPercentLabel, contextStateLabel, contextTokenLabel, contextUsage, contextUsageHoverLabel, contextUsageHovered, contextUsageRatio, conversationMode, createAutomaticProjectFolderPath, currentJarvisSttBackend, currentJarvisSttLabel, currentJarvisTtsBackend, currentJarvisTtsLabel, currentModelLabel, currentPlannerLabel, currentSecurityPermissionLabel, currentSessionQueuedMessages, currentVariant, currentVariantHasControls, currentVariantLabel, currentVariantOptions, dismissPendingSessionSwitch, draftBranchCommandPanel, draftBranchLabel, draftBranchTriggerRef, draftChat, draftFolderLabel, draftGitRepoLoading, draftGitRepoState, draftModelGroups, draftPlannerModels, draftProjectCommandPanel, draftProjectTriggerRef, draftTelegramBotLabel, draftTelegramCommandPanel, draftTelegramTriggerRef, emptyConversationProjectName, expandedCompletedTaskIds, expandedModelProviders, expandedPlannerProviders, fleetChatPanelCollapsed, fleetChatPanelWidth, fleetManagerChatPanel, fleetSidebarPanel, floatingPanelKind, floatingPanelPositionStyle, floatingPanelRef, folderChoiceBusy, formatAbsoluteTime, formatRelativeTime, handleComposerContentSizeChange, handleComposerInputChange, handleComposerKeyPress, handleComposerMeasureLayout, handleJarvisSttBackendSelection, handleJarvisTtsBackendSelection, handleTranscriptScroll, hasCompletedTaskBoards, highlightedMessageIndex, id, input, isCenteredDraftComposerStage, isFleetMode, isJarvisMode, jarvisCircleMuted, jarvisHoldCaptureDetail, jarvisHoldCaptureDisabled, jarvisHoldCaptureValue, jarvisHoldToTalkMode, jarvisInputSummary, jarvisMuteButtonMuted, jarvisPulseOpacity, jarvisPulseScale, jarvisSpokenOutput, jarvisStatusDrawerOpen, jarvisToolActivity, jarvisToolSummary, jarvisTranscriptOutput, jarvisTtsSummary, jarvisVoiceSettingsOpen, killLiveCommand, liveVoiceStatus, messages, modelTriggerRef, openDraftChat, openMessageContextMenu, openReferenceRail, openToolContextMenu, overview, pendingSessionSwitch, pendingSwitchTargetLabel, permissionSettingsDraftMode, permissionSettingsIsDraft, permissionSettingsSession, permissionsTriggerRef, pinnedToolPackInfoId, plannerModelGroups, promptForProjectFolder, queuedComposerMessagesDisplay, referenceEntries, refreshFleetSnapshot, runControl, runSlashCommandFromComposer, runVerboseCommand, scheduleHideToolPackInfoPopup, scrollRef, securityPermissionOptions, selectCommandSuggestion, sendButtonGlyph, sendButtonMode, sendQueuedComposerSlice, sendText, sessionId, sessionSettingsMutationInFlight, setActiveCommandPanel, setActivePermissionInfoId, setContextUsageHovered, setConversationMode, setDismissedCommandSuggestionInput, setExpandedCompletedTaskIds, setExpandedModelProviders, setExpandedPlannerProviders, setFleetChatPanelCollapsed, setFleetChatPanelWidth, setFolderChoiceBusy, setHoveredToolPackInfoId, setJarvisPushToTalkMode, setJarvisStatusDrawerOpen, setJarvisVoiceSettingsOpen, setSleepChatForBot, setTaskBoardCollapsed, shellRef, shortStatusText, shouldRenderGlobalFloatingPanel, shouldShowThinkingIndicator, showFolderComposerMeta, showReferenceRail, showVoiceBanner, startJarvisPushToTalk, status, stopCurrentIdentity, stopJarvisPushToTalk, sttBackendChanging, taskBoardCollapsed, taskBoardStatusText, taskBoardStepPrefix, taskBoardSummary, taskBoardTone, taskBoardUpdatedLabel, telegramBotConfigs, thinkingShineTranslate, thinkingTextCounterTranslate, title, toggleJarvisMute, toolPackCommandPanelContent, toolPackInfoPopup, toolsTriggerRef, transcriptMessageLayoutRef, transcriptTimelineEntries, ttsBackendChanging, unavailableEnabledToolPackReason, updateChatHeadlessEligibility, updateChatSecurityPermissionMode, updateChatTelegramBotAssignment, updateDraftSecurityPermissionMode, verboseModeOn, voiceBannerText, voiceError, voiceRecording, voiceRunning, voiceStartInFlightRef } = scope;
  const activeVisualMonitorCount = Number(overview?.active_visual_monitors || 0);
  const identityStopActive = Boolean(scope.agentRunActive || activeVisualMonitorCount > 0 || scope.hasActiveFleetTask);
  const pendingRunMode = scope.pendingRunMode as 'plan' | 'goal' | 'normal' | null | undefined;
  const planMode = (scope.planMode && typeof scope.planMode === 'object') ? scope.planMode as Record<string, any> : null;
  const activeGoal = (scope.activeGoal && typeof scope.activeGoal === 'object') ? scope.activeGoal as Record<string, any> : null;
  const setPendingRunMode = scope.setPendingRunMode as ((mode: 'plan' | 'goal' | 'normal' | null) => void) | undefined;
  const approveProposedPlan = scope.approveProposedPlan as ((planText: string) => void | Promise<void>) | undefined;
  const answerPlanQuestion = scope.answerPlanQuestion as ((questionId: string, answerText: string, optionId?: string | null) => void | Promise<void>) | undefined;
  const dismissPlanMode = scope.dismissPlanMode as (() => void | Promise<void>) | undefined;
  const exitPlanMode = scope.exitPlanMode as (() => void | Promise<void>) | undefined;
  const clearActiveGoal = scope.clearActiveGoal as (() => void | Promise<void>) | undefined;
  const setComposerInputValue = scope.setComposerInputValue as ((nextInput: string, options?: any) => void) | undefined;
  const [expandedRunIds, setExpandedRunIds] = useState<Record<string, boolean>>({});
  const [expandedEditSummaryIds, setExpandedEditSummaryIds] = useState<Record<string, boolean>>({});
  const [transcriptWindowSize, setTranscriptWindowSize] = useState(200);
  const transcriptWindowStart = Math.max(0, transcriptTimelineEntries.length - transcriptWindowSize);
  const visibleTranscriptTimelineEntries = transcriptTimelineEntries.slice(transcriptWindowStart);
  useEffect(() => setTranscriptWindowSize(200), [sessionId]);
  const latestRunId = [...(transcriptTimelineEntries || [])]
    .reverse()
    .find((entry: any) => entry.kind === 'run')?.runId || null;

  return (
    <View ref={shellRef} style={styles.shell}>
      {scope.archiveUndo ? (
        <DesktopArchiveUndoToast
          name={String(scope.archiveUndo.sessionName || 'Chat')}
          onUndo={() => void scope.undoArchiveChat?.()}
        />
      ) : null}
      {confirmationDialog}
      <View style={[styles.conversationColumn, isCenteredDraftComposerStage && !isJarvisMode && !isFleetMode ? styles.conversationColumnDraftStage : null]}>
        {isFleetMode ? (
          <View style={[styles.centeredConversationBlock, styles.fleetWorkspace]}>
            <ScrollView
              style={styles.fleetMainScroll}
              contentContainerStyle={styles.fleetMainContent}
            >
              {fleetSidebarPanel}
            </ScrollView>
            {fleetChatPanelCollapsed ? (
              <View style={styles.fleetCollapsedRail}>
                <Pressable
                  style={styles.panelCollapseButton}
                  accessibilityRole="button"
                  accessibilityLabel="Expand fleet chat panel"
                  onPress={() => setFleetChatPanelCollapsed(false)}
                >
                  <Text style={styles.panelCollapseButtonText}>‹</Text>
                </Pressable>
                <Text style={styles.fleetCollapsedRailText}>Chat</Text>
              </View>
            ) : (
              <>
                <Pressable
                  style={({ hovered }: any) => [
                    styles.verticalPanelResizeHandle,
                    hovered ? styles.panelResizeHandleHovered : null,
                  ]}
                  accessibilityRole="adjustable"
                  accessibilityLabel="Resize fleet chat panel"
                  onPressIn={(event: any) => beginHorizontalResize(event, {
                    startWidth: fleetChatPanelWidth,
                    minWidth: 300,
                    maxWidth: 760,
                    invert: true,
                    setWidth: setFleetChatPanelWidth,
                  })}
                >
                  {({ hovered }: any) => (
                  <View style={[styles.panelResizeGrip, hovered ? styles.panelResizeGripVisible : null]}>
                    <Text style={styles.panelResizeGripText}>⇔</Text>
                  </View>
                  )}
                </Pressable>
                {fleetManagerChatPanel}
              </>
            )}
          </View>
        ) : isJarvisMode ? (
          <DesktopConversationJarvisStage scope={scope} />
        ) : (
          <>
        <ScrollView
          ref={scrollRef}
          style={[
            styles.transcriptScroll,
            styles.centeredConversationBlock,
            isCenteredDraftComposerStage ? styles.transcriptScrollDraftStage : null,
          ]}
          contentContainerStyle={[
            styles.transcriptContent,
            isCenteredDraftComposerStage ? styles.transcriptContentDraftStage : null,
          ]}
          onScroll={handleTranscriptScroll}
          scrollEventThrottle={16}
        >
          {referenceEntries.length > 0 ? (
            <View style={styles.referenceMovedCard}>
              <View style={styles.referenceMovedCopy}>
                <Text style={styles.referenceMovedTitle}>Reference note moved to History & Artifacts</Text>
                <Text style={styles.referenceMovedText}>
                  Long structured overview content, runtime history, and saved artifacts are tucked into the collapsible sidebar so the main chat stays readable.
                </Text>
              </View>
              <Pressable style={styles.referenceMovedButton} onPress={openReferenceRail}>
                <Text style={styles.referenceMovedButtonText}>{showReferenceRail ? 'Panel Open' : 'Open Panel'}</Text>
              </Pressable>
            </View>
          ) : null}

          {transcriptTimelineEntries.length === 0 && referenceEntries.length === 0 ? (
            <View style={[
              styles.emptyConversationCard,
              emptyConversationProjectName ? styles.emptyConversationDraftCard : null,
            ]}>
              {emptyConversationProjectName ? (
                <>
                  <Text style={styles.emptyDraftPrompt}>
                    What should we work on in {emptyConversationProjectName}?
                  </Text>
                  <View style={styles.emptyDraftFolderRow}>
                    <Text style={styles.emptyDraftFolderIcon}>⌂</Text>
                    <Text style={styles.emptyDraftFolderText}>{emptyConversationProjectName}</Text>
                  </View>
                  <Text style={[styles.emptyText, styles.emptyDraftSupportingText]}>
                    Start typing below or use voice. This new chat will stay in the folder shown here.
                  </Text>
                </>
              ) : (
                <>
                  <Text style={styles.emptyDraftPrompt}>What should we work on?</Text>
                  <View style={styles.emptyDraftFolderRow}>
                    <MonoIcon name="folder_closed" style={styles.emptyDraftFolderIcon} />
                    <Text style={styles.emptyDraftFolderText}>Choose folder</Text>
                  </View>
                  <Text style={[styles.emptyText, styles.emptyDraftSupportingText]}>
                    Pick where this chat should work, or create an automatic folder for it.
                  </Text>
                  <View style={styles.emptyFolderActionRow}>
                    <Pressable
                      style={[styles.emptyFolderActionButton, folderChoiceBusy === 'auto' ? styles.emptyFolderActionButtonDisabled : null]}
                      disabled={Boolean(folderChoiceBusy)}
                      onPress={async () => {
                        const createdProject = await createAutomaticProjectFolderPath();
                        if (createdProject) {
                          await openDraftChat(createdProject);
                        }
                      }}
                    >
                      <Text style={styles.emptyFolderActionButtonText}>
                        {folderChoiceBusy === 'auto' ? 'Creating…' : 'Automatic folder'}
                      </Text>
                    </Pressable>
                    <Pressable
                      style={[styles.emptyFolderActionButton, styles.emptyFolderActionButtonSecondary, folderChoiceBusy === 'choose' ? styles.emptyFolderActionButtonDisabled : null]}
                      disabled={Boolean(folderChoiceBusy)}
                      onPress={async () => {
                        setFolderChoiceBusy('choose');
                        try {
                          const pickedProject = await promptForProjectFolder();
                          if (pickedProject) {
                            await openDraftChat(pickedProject);
                          }
                        } finally {
                          setFolderChoiceBusy(null);
                        }
                      }}
                    >
                      <Text style={[styles.emptyFolderActionButtonText, styles.emptyFolderActionButtonTextSecondary]}>
                        {folderChoiceBusy === 'choose' ? 'Opening…' : 'Choose location'}
                      </Text>
                    </Pressable>
                  </View>
                </>
              )}
            </View>
          ) : null}

          {transcriptWindowStart > 0 ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Show ${Math.min(200, transcriptWindowStart)} earlier conversation items`}
              style={styles.referenceMovedButton}
              onPress={() => setTranscriptWindowSize((current) => current + 200)}
            >
              <Text style={styles.referenceMovedButtonText}>Show earlier conversation</Text>
            </Pressable>
          ) : null}

          {visibleTranscriptTimelineEntries.map((entry: any, index: any) => {
            if (entry.kind === 'message') {
              const message = messages[entry.sourceMessageIndex];
              if (!message) {
                return null;
              }
              const fullIndex = entry.sourceMessageIndex;
              const messageOnLightSurface = message.role === 'user';
              const planQuestion = planQuestionFromMessage(message);
              const proposedPlan = message.role === 'assistant' ? extractProposedPlan(message.content) : null;
              const displayContent = planQuestion ? '' : (proposedPlan ? visiblePlanText(message.content) : message.content);
              const editSummary = message.role === 'assistant' ? editSummaryFromMessage(message) : null;
              const editSummaryKey = message.messageKey || `${message.timestamp || 'message'}-${fullIndex}`;
              const editSummaryExpanded = Boolean(expandedEditSummaryIds[editSummaryKey]);
              const editSummaryFiles = editSummary
                ? (editSummaryExpanded ? editSummary.files : editSummary.files.slice(0, 3))
                : [];
              const hiddenEditSummaryCount = editSummary
                ? Math.max(0, editSummary.files.length - editSummaryFiles.length)
                : 0;
              return (
                <View
                  key={message.messageKey || `${message.timestamp || 'ts'}-${fullIndex}-${index}`}
                  onLayout={(event: any) => {
                    transcriptMessageLayoutRef.current[fullIndex] = event.nativeEvent.layout.y;
                  }}
                  {...(Platform.OS === 'web' && (message.role === 'user' || message.role === 'assistant')
                    ? ({ onContextMenu: (event: any) => openMessageContextMenu(event, message) } as any)
                    : {})}
                  style={[
                    styles.messageBubble,
                    message.role === 'assistant'
                      ? styles.messageBubbleAssistant
                      : message.role === 'system'
                        ? styles.messageBubbleSystem
                        : styles.messageBubbleUser,
                    highlightedMessageIndex === fullIndex ? styles.searchJumpHighlight : null,
                    message.pending ? styles.messageBubblePending : null,
                  ]}
                >
                  <View style={styles.messageHeader}>
                    <Text style={[styles.messageLabel, messageOnLightSurface ? styles.messageLabelOnLight : null]}>
                      {labelForMessage(message)}
                    </Text>
                    <Text style={[styles.messageTime, messageOnLightSurface ? styles.messageTimeOnLight : null]}>
                      {message.timestamp ? formatAbsoluteTime(message.timestamp) : 'pending'}
                    </Text>
                  </View>
                  {displayContent ? (
                    <Text style={[styles.messageText, messageOnLightSurface ? styles.messageTextOnLight : null]}>
                      {displayContent}
                    </Text>
                  ) : null}
                  {planQuestion ? (
                    <View style={styles.planQuestionCard}>
                      <Text style={styles.planCardEyebrow}>{planQuestion.header || 'Plan'}</Text>
                      <Text style={styles.planCardTitle}>{planQuestion.question}</Text>
                      <View style={styles.planQuestionOptions}>
                        {planQuestion.options.map((option: any, optionIndex: number) => (
                          <Pressable
                            key={`${planQuestion.question_id}-${option.id}`}
                            style={({ hovered }: any) => [
                              styles.planQuestionOption,
                              hovered ? styles.planQuestionOptionHovered : null,
                            ]}
                            onPress={() => {
                              void answerPlanQuestion?.(
                                planQuestion.question_id,
                                `${option.label}${option.description ? `: ${option.description}` : ''}`,
                                option.id,
                              );
                            }}
                          >
                            <Text style={styles.planQuestionOptionIndex}>{optionIndex + 1}</Text>
                            <View style={styles.planQuestionOptionCopy}>
                              <Text style={styles.planQuestionOptionLabel}>{option.label}</Text>
                              {option.description ? (
                                <Text style={styles.planQuestionOptionDescription}>{option.description}</Text>
                              ) : null}
                            </View>
                          </Pressable>
                        ))}
                      </View>
                      <View style={styles.planCardActions}>
                        <Pressable
                          style={styles.planCardSecondaryAction}
                          onPress={() => {
                            setPendingRunMode?.('plan');
                            setComposerInputValue?.('', { origin: 'manual', syncVoiceBase: false });
                          }}
                        >
                          <Text style={styles.planCardSecondaryActionText}>Tell Differently</Text>
                        </Pressable>
                        <Pressable style={styles.planCardSecondaryAction} onPress={() => void dismissPlanMode?.()}>
                          <Text style={styles.planCardSecondaryActionText}>Dismiss</Text>
                        </Pressable>
                      </View>
                    </View>
                  ) : null}
                  {proposedPlan ? (
                    <View style={styles.proposedPlanCard}>
                      <Text style={styles.planCardEyebrow}>Plan</Text>
                      <Text style={styles.planCardTitle}>Proposed Plan</Text>
                      <Text style={styles.proposedPlanText}>{proposedPlan}</Text>
                      <View style={styles.planCardActions}>
                        <Pressable style={styles.planCardPrimaryAction} onPress={() => void approveProposedPlan?.(proposedPlan)}>
                          <Text style={styles.planCardPrimaryActionText}>Implement This Plan</Text>
                        </Pressable>
                        <Pressable style={styles.planCardSecondaryAction} onPress={() => void dismissPlanMode?.()}>
                          <Text style={styles.planCardSecondaryActionText}>Dismiss</Text>
                        </Pressable>
                      </View>
                    </View>
                  ) : null}
                  {editSummary ? (
                    <View style={styles.editSummaryCard}>
                      <View style={styles.editSummaryHeader}>
                        <View style={styles.editSummaryIconBox}>
                          <Text style={styles.editSummaryIcon}>+/-</Text>
                        </View>
                        <View style={styles.editSummaryHeaderCopy}>
                          <Text style={styles.editSummaryTitle}>
                            Edited {editSummary.fileCount} {editSummary.fileCount === 1 ? 'file' : 'files'}
                          </Text>
                          <Text style={styles.editSummaryTotals}>
                            <Text style={styles.editSummaryAdditions}>+{editSummary.additions}</Text>
                            {' '}
                            <Text style={styles.editSummaryDeletions}>-{editSummary.deletions}</Text>
                          </Text>
                        </View>
                      </View>
                      <View style={styles.editSummaryFileList}>
                        {editSummaryFiles.map((file: any) => (
                          <View key={file.path} style={styles.editSummaryFileRow}>
                            <Text style={styles.editSummaryPath} numberOfLines={1}>{file.path}</Text>
                            {file.binary ? (
                              <Text style={styles.editSummaryBinary}>binary</Text>
                            ) : (
                              <Text style={styles.editSummaryFileCounts}>
                                <Text style={styles.editSummaryAdditions}>+{file.additions}</Text>
                                {' '}
                                <Text style={styles.editSummaryDeletions}>-{file.deletions}</Text>
                              </Text>
                            )}
                          </View>
                        ))}
                      </View>
                      {editSummary.files.length > 3 ? (
                        <Pressable
                          style={({ hovered }: any) => [
                            styles.editSummaryToggle,
                            hovered ? styles.editSummaryToggleHovered : null,
                          ]}
                          accessibilityRole="button"
                          onPress={() => {
                            setExpandedEditSummaryIds((previous) => ({
                              ...previous,
                              [editSummaryKey]: !editSummaryExpanded,
                            }));
                          }}
                        >
                          <Text style={styles.editSummaryToggleText}>
                            {editSummaryExpanded ? 'Show fewer files' : `Show ${hiddenEditSummaryCount} more ${hiddenEditSummaryCount === 1 ? 'file' : 'files'}`}
                          </Text>
                          <Text style={styles.editSummaryToggleChevron}>{editSummaryExpanded ? '^' : 'v'}</Text>
                        </Pressable>
                      ) : null}
                    </View>
                  ) : null}
                </View>
              );
            }

            if (entry.kind === 'run') {
              const hasManualExpansion = Object.prototype.hasOwnProperty.call(expandedRunIds, entry.runId);
              const expanded = hasManualExpansion
                ? Boolean(expandedRunIds[entry.runId])
                : Boolean(scope.agentRunActive && entry.runId === latestRunId);
              const runIsActive = Boolean(scope.agentRunActive && entry.runId === latestRunId);
              const runLabel = runDurationLabel(entry, runIsActive);
              const runActivityLabel = compactRunActivityLabel(entry);
              return (
                <View
                  key={`${entry.id}-${index}`}
                  style={[
                    styles.timelineRunDisclosure,
                    entry.tone === 'warn' ? styles.timelineRunDisclosureWarn : null,
                    entry.tone === 'error' ? styles.timelineRunDisclosureError : null,
                  ]}
                >
                  <Pressable
                    style={({ hovered }: any) => [
                      styles.timelineRunHeader,
                      hovered ? styles.timelineRunHeaderHovered : null,
                    ]}
                    accessibilityRole="button"
                    accessibilityLabel={`${expanded ? 'Collapse' : 'Expand'} ${entry.label}`}
                    onPress={() => {
                      setExpandedRunIds((previous) => ({
                        ...previous,
                        [entry.runId]: !expanded,
                      }));
                    }}
                  >
                    <View style={styles.timelineRunHeaderCopy}>
                      <Text style={styles.timelineRunTitle}>{runLabel}</Text>
                    </View>
                    <Text style={styles.timelineRunToggle}>{expanded ? '^' : 'v'}</Text>
                  </Pressable>
                  {!expanded ? (
                    <View style={styles.timelineRunCollapsedRow}>
                      <Text style={styles.timelineRunCollapsedIcon}>-</Text>
                      <Text style={styles.timelineRunPreview} numberOfLines={1}>{runActivityLabel}</Text>
                    </View>
                  ) : (
                    <View style={styles.timelineRunEventList}>
                      {entry.events.map((runEvent: any, runEventIndex: number) => {
                        const parts = timelineEventDisplayParts(runEvent);
                        return (
                          <View
                            key={`${runEvent.id}-${runEventIndex}`}
                            {...(Platform.OS === 'web' && parts.isToolEntry
                              ? ({ onContextMenu: (event: any) => openToolContextMenu(event, parts.toolContextText) } as any)
                              : {})}
                            style={[
                              styles.timelineRunEventRow,
                              runEvent.tone === 'warn' ? styles.timelineRunEventRowWarn : null,
                              runEvent.tone === 'error' ? styles.timelineRunEventRowError : null,
                            ]}
                          >
                            <View style={styles.timelineRunEventHeader}>
                              <Text style={styles.timelineRunEventEyebrow}>{parts.eyebrowLabel}</Text>
                              <Text style={styles.timelineRunEventTime}>
                                {runEvent.timestamp ? formatAbsoluteTime(runEvent.timestamp) : 'event'}
                              </Text>
                            </View>
                            <Text style={styles.timelineRunEventBody} numberOfLines={5}>{parts.commandText}</Text>
                            {parts.resultText ? (
                              <Text style={styles.timelineRunEventResult} numberOfLines={5}>{parts.resultText}</Text>
                            ) : null}
                          </View>
                        );
                      })}
                    </View>
                  )}
                </View>
              );
            }

            const {
              isToolEntry,
              isLiveCommandEntry,
              commandText,
              resultText,
              toolContextText,
              eyebrowLabel,
            } = timelineEventDisplayParts(entry);
            if (isLiveCommandEntry) {
              return (
                <DesktopLiveCommandCard
                  key={`${entry.id}-${index}`}
                  entry={entry}
                  formatAbsoluteTime={formatAbsoluteTime}
                  openToolContextMenu={openToolContextMenu}
                  killLiveCommand={killLiveCommand}
                />
              );
            }
            return (
              <View
                key={`${entry.id}-${index}`}
                {...(Platform.OS === 'web' && isToolEntry
                  ? ({ onContextMenu: (event: any) => openToolContextMenu(event, toolContextText) } as any)
                  : {})}
                style={[
                  styles.timelineTranscriptCard,
                  entry.tone === 'accent'
                    ? styles.timelineTranscriptCardAccent
                    : entry.tone === 'warn'
                      ? styles.timelineTranscriptCardWarn
                      : entry.tone === 'error'
                        ? styles.timelineTranscriptCardError
                        : null,
                ]}
              >
                <View style={styles.timelineTranscriptHeader}>
                  <Text style={styles.timelineTranscriptEyebrow}>{eyebrowLabel}</Text>
                  <Text style={styles.timelineTranscriptTime}>
                    {entry.timestamp ? formatAbsoluteTime(entry.timestamp) : 'event'}
                  </Text>
                </View>
                <Text style={styles.timelineTranscriptBody} numberOfLines={10}>{commandText}</Text>
                {resultText ? (
                  <View style={styles.timelineTranscriptResultBlock}>
                    <Text style={styles.timelineTranscriptResultEyebrow}>Command Result</Text>
                    <Text style={styles.timelineTranscriptResultText} numberOfLines={8}>{resultText}</Text>
                  </View>
                ) : null}
              </View>
            );
          })}

          {scope.providerFailure ? (
            <DesktopProviderFailureCard
              failure={scope.providerFailure}
              modelGroups={Array.isArray(scope.draftModelGroups) ? scope.draftModelGroups : []}
              onRetry={(providerId, modelId) => scope.retryFailedTurn?.(scope.providerFailure, providerId, modelId)}
              onOpenSettings={() => scope.onOpenSetup?.()}
            />
          ) : null}

          {assistantDraft ? (
            <View style={[styles.messageBubble, styles.messageBubbleAssistant, styles.messageBubbleDraft]}>
              <View style={styles.messageHeader}>
                <Text style={styles.messageLabel}>Assistant</Text>
                <Text style={styles.messageTime}>streaming</Text>
              </View>
              <Text style={styles.messageText}>{assistantDraft}</Text>
            </View>
          ) : null}

          {shouldShowThinkingIndicator ? (
            <View style={styles.syntheticThinkingRow}>
              <View style={styles.syntheticThinkingTextWrap}>
                <Text style={styles.syntheticThinkingText}>Thinking</Text>
                <Animated.View
                  pointerEvents="none"
                  style={[
                    styles.syntheticThinkingHighlightMask,
                    {
                      transform: [{ translateX: thinkingShineTranslate }],
                    },
                  ]}
                >
                  <Animated.Text
                    style={[
                      styles.syntheticThinkingText,
                      styles.syntheticThinkingTextHighlight,
                      { transform: [{ translateX: thinkingTextCounterTranslate }] },
                    ]}
                  >
                    Thinking
                  </Animated.Text>
                </Animated.View>
              </View>
            </View>
          ) : null}
        </ScrollView>

        {showVoiceBanner ? (
          <View style={[styles.centeredConversationBlock, styles.voiceBanner, voiceError ? styles.voiceBannerError : null]}>
            <Text style={styles.voiceBannerTitle}>Jarvis</Text>
            <Text style={styles.voiceBannerText}>{voiceBannerText}</Text>
          </View>
        ) : null}

        {activeTaskBoard ? (
          <View
            style={[
              styles.centeredConversationBlock,
              styles.taskBoardCard,
              taskBoardTone === 'complete'
                ? styles.taskBoardCardComplete
                : taskBoardTone === 'warn'
                  ? styles.taskBoardCardWarn
                  : null,
            ]}
          >
            <View style={styles.taskBoardHeader}>
              <View style={styles.taskBoardHeaderCopy}>
                <Text style={styles.taskBoardEyebrow}>Managed Task</Text>
                <Text style={styles.taskBoardGoal}>{activeTaskBoard.main_goal}</Text>
                <Text style={styles.taskBoardMeta}>
                  {taskBoardSummary || `${activeTaskBoard.completed_sub_goals}/${activeTaskBoard.total_sub_goals} sub-goals complete`}
                  {taskBoardUpdatedLabel ? ` · updated ${taskBoardUpdatedLabel}` : ''}
                </Text>
              </View>
              <View style={styles.taskBoardHeaderActions}>
                <Pressable
                  style={styles.taskBoardToggleButton}
                  onPress={() => setTaskBoardCollapsed((current: any) => !current)}
                >
                  <Text style={styles.taskBoardToggleButtonText}>{taskBoardCollapsed ? 'Expand' : 'Collapse'}</Text>
                </Pressable>
                <View
                  style={[
                    styles.taskBoardBadge,
                    taskBoardTone === 'complete'
                      ? styles.taskBoardBadgeComplete
                      : taskBoardTone === 'warn'
                        ? styles.taskBoardBadgeWarn
                        : null,
                  ]}
                >
                  <Text style={styles.taskBoardBadgeText}>{taskBoardStatusText}</Text>
                </View>
              </View>
            </View>

            {!taskBoardCollapsed ? (
              <>
                {activeTaskBoard.pending_reassessment_reason ? (
                  <View style={styles.taskBoardAlert}>
                    <Text style={styles.taskBoardAlertLabel}>Reassessing</Text>
                    <Text style={styles.taskBoardAlertText}>{activeTaskBoard.pending_reassessment_reason}</Text>
                  </View>
                ) : null}

                <View style={styles.taskBoardInfoRow}>
                  <View style={styles.taskBoardInfoChip}>
                    <Text style={styles.taskBoardInfoLabel}>Current Focus</Text>
                    <Text style={styles.taskBoardInfoValue}>
                      {activeTaskBoard.status === 'completed'
                        ? 'Task complete'
                        : activeTaskBoard.current_focus || 'Choose next sub-goal'}
                    </Text>
                  </View>
                  <View style={styles.taskBoardInfoChip}>
                    <Text style={styles.taskBoardInfoLabel}>Next Method</Text>
                    <Text style={styles.taskBoardInfoValue}>
                      {activeTaskBoard.status === 'completed'
                        ? activeTaskBoard.completion_summary || 'Task complete. No next method is needed.'
                        : activeTaskBoard.next_method || 'Not set yet'}
                    </Text>
                  </View>
                </View>

                <View style={styles.taskBoardSteps}>
                  {activeTaskBoard.sub_goals.map((subGoal: any) => (
                    <View key={subGoal.id} style={styles.taskBoardStepRow}>
                      <Text style={styles.taskBoardStepPrefix}>{taskBoardStepPrefix(subGoal.status)}</Text>
                      <View style={styles.taskBoardStepCopy}>
                        <Text style={styles.taskBoardStepTitle}>{subGoal.title}</Text>
                        {subGoal.completion_reason ? (
                          <Text style={styles.taskBoardStepMeta}>{subGoal.completion_reason}</Text>
                        ) : subGoal.completion_evidence ? (
                          <Text style={styles.taskBoardStepMeta}>{subGoal.completion_evidence}</Text>
                        ) : null}
                      </View>
                    </View>
                  ))}
                  <View style={styles.taskBoardStepRow}>
                    <Text style={styles.taskBoardStepPrefix}>{activeTaskBoard.verification_status === 'done' ? '[x]' : '[ ]'}</Text>
                    <View style={styles.taskBoardStepCopy}>
                      <Text style={styles.taskBoardStepTitle}>Verify the requested result and close the task</Text>
                      {activeTaskBoard.verification_summary ? (
                        <Text style={styles.taskBoardStepMeta}>{activeTaskBoard.verification_summary}</Text>
                      ) : (
                        <Text style={styles.taskBoardStepMeta}>
                          {activeTaskBoard.status === 'completed'
                            ? 'Waiting for verification summary.'
                            : 'This final check closes only after the requested result is verified.'}
                        </Text>
                      )}
                    </View>
                  </View>
                </View>
              </>
            ) : null}
          </View>
        ) : null}

        {hasCompletedTaskBoards ? (
          <View style={[styles.centeredConversationBlock, styles.completedTaskBoardsSection]}>
            <View style={styles.completedTaskBoardsHeader}>
              <View style={styles.completedTaskBoardsHeaderCopy}>
                <Text style={styles.completedTaskBoardsEyebrow}>Task History</Text>
                <Text style={styles.completedTaskBoardsTitle}>Managed Task History</Text>
              </View>
              <Text style={styles.completedTaskBoardsSummary}>{completedTaskBoards.length} kept</Text>
            </View>

            <View style={styles.completedTaskBoardsList}>
              {completedTaskBoards.map((board: any) => {
                const expanded = Boolean(expandedCompletedTaskIds[board.task_id]);
                const completedAtLabel = board.collapsed_completed_at || board.completed_at;
                const summaryText = board.collapsed_completion_summary || board.completion_summary || board.verification_summary || 'Completed';
                return (
                  <View key={`completed-task-${board.task_id}`} style={styles.completedTaskCard}>
                    <Pressable
                      style={styles.completedTaskCardHeader}
                      onPress={() => {
                        setExpandedCompletedTaskIds((previous: any) => ({
                          ...previous,
                          [board.task_id]: !expanded,
                        }));
                      }}
                    >
                      <View style={styles.completedTaskCardCopy}>
                        <Text style={styles.completedTaskCardTitle}>{board.collapsed_title || `[x] ${board.main_goal}`}</Text>
                        <Text style={styles.completedTaskCardMeta}>
                          {completedAtLabel ? `${formatRelativeTime(completedAtLabel)} · ` : ''}{taskBoardStatusLabel(board.status)} · {summaryText}
                        </Text>
                      </View>
                      <View style={styles.taskBoardHeaderActions}>
                        <View
                          style={[
                            styles.taskBoardBadge,
                            board.status === 'completed'
                              ? styles.taskBoardBadgeComplete
                              : board.status === 'blocked'
                                ? styles.taskBoardBadgeWarn
                                : null,
                          ]}
                        >
                          <Text style={styles.taskBoardBadgeText}>{taskBoardStatusLabel(board.status)}</Text>
                        </View>
                        <Text style={styles.completedTaskCardToggle}>{expanded ? 'Collapse' : 'Expand'}</Text>
                      </View>
                    </Pressable>

                    {expanded ? (
                      <View style={styles.completedTaskCardBody}>
                        <View style={styles.completedTaskCardSteps}>
                          {board.sub_goals.map((subGoal: any) => (
                            <View key={`${board.task_id}-${subGoal.id}`} style={styles.taskBoardStepRow}>
                              <Text style={styles.taskBoardStepPrefix}>{taskBoardStepPrefix(subGoal.status)}</Text>
                              <View style={styles.taskBoardStepCopy}>
                                <Text style={styles.taskBoardStepTitle}>{subGoal.title}</Text>
                                {subGoal.completion_reason ? (
                                  <Text style={styles.taskBoardStepMeta}>{subGoal.completion_reason}</Text>
                                ) : subGoal.completion_evidence ? (
                                  <Text style={styles.taskBoardStepMeta}>{subGoal.completion_evidence}</Text>
                                ) : null}
                              </View>
                            </View>
                          ))}
                        </View>
                        <View style={styles.completedTaskCardSummaryBox}>
                          <Text style={styles.completedTaskCardSummaryLabel}>Verification summary</Text>
                          <Text style={styles.completedTaskCardSummaryText}>{summaryText}</Text>
                        </View>
                      </View>
                    ) : null}
                  </View>
                );
              })}
            </View>
          </View>
        ) : null}

        <View style={[styles.composerDock, isCenteredDraftComposerStage ? styles.composerDockDraftStage : null]}>
        <View style={[styles.composerShell, isCenteredDraftComposerStage ? styles.composerShellDraftStage : null]}>
          {pendingSessionSwitch ? (
            <View style={styles.pendingSwitchCard}>
              <View style={styles.pendingSwitchCopy}>
                <Text style={styles.pendingSwitchEyebrow}>Switch Chat</Text>
                <Text style={styles.pendingSwitchTitle}>Current run is still active</Text>
                <Text style={styles.pendingSwitchText}>
                  Stop the current task to continue with {pendingSwitchTargetLabel || 'the selected chat'}.
                </Text>
              </View>
              <View style={styles.pendingSwitchActions}>
                <Pressable style={styles.pendingSwitchPrimaryAction} onPress={() => void confirmPendingSessionSwitch()}>
                  <Text style={styles.pendingSwitchPrimaryActionText}>Stop And Switch</Text>
                </Pressable>
                <Pressable style={styles.pendingSwitchSecondaryAction} onPress={dismissPendingSessionSwitch}>
                  <Text style={styles.pendingSwitchSecondaryActionText}>Cancel</Text>
                </Pressable>
              </View>
            </View>
          ) : null}

          {queuedComposerMessagesDisplay.length ? (
            <View style={styles.queuedComposerStack}>
              {queuedComposerMessagesDisplay.map((item: any) => {
                const originalIndex = currentSessionQueuedMessages.findIndex((entry: any) => entry.id === item.id);
                const steerLabel = currentSessionQueuedMessages.length > 1 && originalIndex === currentSessionQueuedMessages.length - 1
                  ? 'Steer All'
                  : 'Steer Now';
                return (
                  <View key={item.id} style={styles.queuedComposerRow}>
                    <Text style={styles.queuedComposerText} numberOfLines={1}>{item.text}</Text>
                    <Pressable
                      style={styles.queuedComposerAction}
                      onPress={() => {
                        const slice = currentSessionQueuedMessages.slice(0, originalIndex + 1);
                        sendQueuedComposerSlice(slice, 'steer_now');
                      }}
                    >
                      <Text style={styles.queuedComposerActionText}>{steerLabel}</Text>
                    </Pressable>
                  </View>
                );
              })}
            </View>
          ) : null}

          {activeCommandPanel?.kind === 'verbose' ? (
            <View style={styles.commandPanel}>
              <View style={styles.commandPanelHeader}>
                <View style={styles.commandPanelHeaderCopy}>
                  <View style={styles.commandPanelHeaderLine}>
                    <Text style={styles.commandPanelCompactTitle}>Tool Logging</Text>
                    <Pressable
                      style={styles.commandPanelInfoButton}
                      accessibilityRole="button"
                      accessibilityLabel="Tool logging information"
                      accessibilityHint={`Verbose mode is currently ${overview?.verbose_mode ? 'on' : 'off'}. Choose how tool activity should appear in the shared chat.`}
                      {...(Platform.OS === 'web' ? ({ title: `Verbose mode is currently ${overview?.verbose_mode ? 'on' : 'off'}. Choose how tool activity should appear in the shared chat.` } as any) : {})}
                    >
                      <MonoIcon name="info" style={styles.commandPanelInfoIcon} />
                    </Pressable>
                  </View>
                </View>
                <Pressable style={styles.commandPanelCloseButton} onPress={() => setActiveCommandPanel(null)}>
                  <Text style={styles.commandPanelCloseText}>Close</Text>
                </Pressable>
              </View>
              <View style={styles.commandPanelActionRow}>
                <Pressable
                  style={verboseModeOn ? styles.commandPanelPrimaryAction : styles.commandPanelSecondaryAction}
                  onPress={() => { void runVerboseCommand('on'); }}
                >
                  <Text style={verboseModeOn ? styles.commandPanelPrimaryActionText : styles.commandPanelSecondaryActionText}>
                    Turn Verbose On
                  </Text>
                </Pressable>
                <Pressable
                  style={!verboseModeOn ? styles.commandPanelPrimaryAction : styles.commandPanelSecondaryAction}
                  onPress={() => { void runVerboseCommand('off'); }}
                >
                  <Text style={!verboseModeOn ? styles.commandPanelPrimaryActionText : styles.commandPanelSecondaryActionText}>
                    Turn Verbose Off
                  </Text>
                </Pressable>
                <Pressable style={styles.commandPanelSecondaryAction} onPress={() => { void runVerboseCommand('status'); }}>
                  <Text style={styles.commandPanelSecondaryActionText}>Show Status</Text>
                </Pressable>
              </View>
            </View>
          ) : null}

          {activeCommandPanel?.kind === 'command' ? (
            <View style={styles.commandPanel}>
              <View style={styles.commandPanelHeader}>
                <View style={styles.commandPanelHeaderCopy}>
                  <View style={styles.commandPanelHeaderLine}>
                    <Text style={styles.commandPanelCompactTitle}>{activeCommandPanel.command}</Text>
                    <Pressable
                      style={styles.commandPanelInfoButton}
                      accessibilityRole="button"
                      accessibilityLabel={`${activeCommandPanel.command} information`}
                      accessibilityHint={activeCommandPanel.description}
                      {...(Platform.OS === 'web' ? ({ title: activeCommandPanel.description } as any) : {})}
                    >
                      <MonoIcon name="info" style={styles.commandPanelInfoIcon} />
                    </Pressable>
                  </View>
                </View>
                <Pressable style={styles.commandPanelCloseButton} onPress={() => setActiveCommandPanel(null)}>
                  <Text style={styles.commandPanelCloseText}>Close</Text>
                </Pressable>
              </View>
              <View style={styles.commandPanelActionRow}>
                <Pressable
                  style={styles.commandPanelPrimaryAction}
                  onPress={() => {
                    const commandToRun = activeCommandPanel.command;
                    setActiveCommandPanel(null);
                    void runSlashCommandFromComposer(commandToRun);
                  }}
                >
                  <Text style={styles.commandPanelPrimaryActionText}>Run {activeCommandPanel.command}</Text>
                </Pressable>
              </View>
            </View>
          ) : null}

          <View style={styles.composerUtilityAnchor}>
            {shouldRenderGlobalFloatingPanel ? (
              <View
                ref={floatingPanelRef}
                style={[
                  styles.commandPanelFloatingLayer,
                  floatingPanelPositionStyle,
                ]}
              >
                {floatingPanelKind === 'model' ? (
                  <View style={[styles.commandPanel, styles.commandPanelSlim, styles.commandPanelFloating]}>
                    <View style={styles.commandPanelHeader}>
                    <View style={styles.commandPanelHeaderCopy}>
                      <View style={styles.commandPanelHeaderLine}>
                        <Text style={styles.commandPanelCompactTitle}>Model + Planner</Text>
                        <Pressable
                          style={styles.commandPanelInfoButton}
                          accessibilityRole="button"
                          accessibilityLabel="Model and planner information"
                          accessibilityHint={`The main model handles the chat. Planner is currently set to ${currentPlannerLabel === 'auto' ? `automatic, mirroring ${currentModelLabel}` : currentPlannerLabel} for task decomposition and reassessment.`}
                          {...(Platform.OS === 'web' ? ({ title: `The main model handles the chat. Planner is currently set to ${currentPlannerLabel === 'auto' ? `automatic, mirroring ${currentModelLabel}` : currentPlannerLabel} for task decomposition and reassessment.` } as any) : {})}
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
                      emptyTitle="No configured model providers"
                      emptyText="Add an API key in setup/settings, then reopen the model chooser."
                    />
                  </View>
                ) : null}
                {floatingPanelKind === 'tools' ? (
                  <View style={[styles.commandPanel, styles.commandPanelSlim, styles.commandPanelFloating, styles.toolPackCommandPanel]}>
                    {toolPackCommandPanelContent}
                  </View>
                ) : null}
                {floatingPanelKind === 'tools' && toolPackInfoPopup && activeToolPackInfo ? (
                  <Pressable
                    style={[
                      styles.toolPackInfoFloatingBubble,
                      {
                        top: toolPackInfoPopup.top,
                        left: toolPackInfoPopup.left,
                      },
                    ]}
                    onHoverIn={() => {
                      clearToolPackInfoHideTimer();
                      if (!pinnedToolPackInfoId) {
                        setHoveredToolPackInfoId(activeToolPackInfo.id);
                      }
                    }}
                    onHoverOut={() => {
                      if (pinnedToolPackInfoId === activeToolPackInfo.id) {
                        return;
                      }
                      scheduleHideToolPackInfoPopup(activeToolPackInfo.id);
                    }}
                  >
                    <Text style={styles.toolPackInfoTitle}>{activeToolPackInfo.label}</Text>
                    <Text style={styles.toolPackInfoText}>{activeToolPackInfo.description}</Text>
                    {activeToolPackInfoDisabledReason ? (
                      <Text style={styles.toolPackInfoWarning}>{activeToolPackInfoDisabledReason}</Text>
                    ) : !activeToolPackInfoAvailable && activeToolPackInfoConfiguredEnabled ? (
                      <Text style={styles.toolPackInfoWarning}>
                        {unavailableEnabledToolPackReason}
                      </Text>
                    ) : null}
                  </Pressable>
                ) : null}
                {floatingPanelKind === 'permissions' ? (
                  <View
                    ref={floatingPanelRef}
                    style={[styles.commandPanel, styles.commandPanelSlim, styles.commandPanelFloating, styles.permissionCommandPanel]}
                  >
                    <View style={styles.commandPanelHeader}>
                      <View style={styles.commandPanelHeaderCopy}>
                        <View style={styles.commandPanelHeaderLine}>
                          <Text style={styles.commandPanelCompactTitle}>Permissions</Text>
                          <Pressable
                            style={styles.commandPanelInfoButton}
                            accessibilityRole="button"
                            accessibilityLabel="Permissions information"
                            accessibilityHint="Choose how much this chat can act on the computer before asking."
                            {...(Platform.OS === 'web' ? ({ title: 'Choose how much this chat can act on the computer before asking.' } as any) : {})}
                          >
                            <MonoIcon name="info" style={styles.commandPanelInfoIcon} />
                          </Pressable>
                        </View>
                      </View>
                      <Pressable style={styles.commandPanelCloseButton} onPress={() => setActiveCommandPanel(null)}>
                        <Text style={styles.commandPanelCloseText}>Close</Text>
                      </Pressable>
                    </View>
                    {permissionSettingsSession || permissionSettingsIsDraft ? (
                      <View style={styles.permissionOptionList}>
                        {securityPermissionOptions.map((mode: any) => {
                          const selected = (
                            permissionSettingsSession
                              ? (
                                  permissionSettingsSession.security_permission_mode === mode.id
                                  || (!permissionSettingsSession.security_permission_mode && mode.id === 'standard')
                                )
                              : permissionSettingsDraftMode === mode.id
                          );
                          return (
                            <View
                              key={`quick-permission-${mode.id}`}
                              style={[
                                styles.permissionOptionRow,
                                selected ? styles.permissionOptionRowActive : null,
                              ]}
                            >
                              <Pressable
                                style={({ hovered }: any) => [
                                  styles.permissionOptionSelect,
                                  hovered ? styles.permissionOptionSelectHovered : null,
                                  sessionSettingsMutationInFlight ? styles.permissionOptionDisabled : null,
                                ]}
                                disabled={sessionSettingsMutationInFlight}
                                onPress={async () => {
                                  if (permissionSettingsSession) {
                                    await updateChatSecurityPermissionMode(permissionSettingsSession.id, mode.id);
                                  } else {
                                    await updateDraftSecurityPermissionMode(mode.id);
                                  }
                                  setActivePermissionInfoId(null);
                                  setActiveCommandPanel(null);
                                }}
                              >
                                <Text style={[styles.permissionOptionTitle, selected ? styles.permissionOptionTitleActive : null]} numberOfLines={1}>
                                  {mode.title}
                                </Text>
                                <Text style={[styles.permissionOptionMeta, selected ? styles.permissionOptionMetaActive : null]} numberOfLines={1}>
                                  {selected ? 'Active' : 'Use'}
                                </Text>
                              </Pressable>
                              <Pressable
                                style={({ hovered }: any) => [
                                  styles.permissionInfoButton,
                                  hovered || activePermissionInfoId === mode.id ? styles.permissionInfoButtonActive : null,
                                ]}
                                accessibilityRole="button"
                                accessibilityLabel={`${mode.title} permission information`}
                                accessibilityHint={mode.caption}
                                onHoverIn={() => setActivePermissionInfoId(mode.id)}
                                onHoverOut={() => setActivePermissionInfoId((current: any) => (current === mode.id ? null : current))}
                                onPress={() => setActivePermissionInfoId((current: any) => (current === mode.id ? null : mode.id))}
                              >
                                <MonoIcon name="info" style={styles.permissionInfoIcon} />
                              </Pressable>
                            </View>
                          );
                        })}
                        {activePermissionInfo ? (
                          <View style={styles.permissionInfoBubble}>
                            <Text style={styles.permissionInfoTitle}>{activePermissionInfo.title}</Text>
                            <Text style={styles.permissionInfoText}>{activePermissionInfo.caption}</Text>
                          </View>
                        ) : null}
                      </View>
                    ) : (
                      <View style={styles.commandPanelEmpty}>
                        <Text style={styles.commandPanelEmptyTitle}>Chat not available</Text>
                        <Text style={styles.commandPanelEmptyText}>
                          Start or open a chat before changing permissions.
                        </Text>
                      </View>
                    )}
                  </View>
                ) : null}
                {floatingPanelKind === 'session' ? (
                  <View style={[styles.commandPanel, styles.commandPanelSlim, styles.commandPanelFloating]}>
                    <View style={styles.commandPanelHeader}>
                      <View style={styles.commandPanelHeaderCopy}>
                        <View style={styles.commandPanelHeaderLine}>
                          <Text style={styles.commandPanelCompactTitle}>Chat Settings</Text>
                          <Pressable
                            style={styles.commandPanelInfoButton}
                            accessibilityRole="button"
                            accessibilityLabel="Chat settings information"
                            accessibilityHint="Assign this chat to a Telegram bot and choose whether it can be used as a sleep chat."
                            {...(Platform.OS === 'web' ? ({ title: 'Assign this chat to a Telegram bot and choose whether it can be used as a sleep chat.' } as any) : {})}
                          >
                            <MonoIcon name="info" style={styles.commandPanelInfoIcon} />
                          </Pressable>
                        </View>
                      </View>
                      <Pressable style={styles.commandPanelCloseButton} onPress={() => setActiveCommandPanel(null)}>
                        <Text style={styles.commandPanelCloseText}>Close</Text>
                      </Pressable>
                    </View>
                    {chatSettingsSession ? (
                      <ScrollView style={styles.modelPickerScroll} contentContainerStyle={styles.modelPickerContent}>
                        <View style={styles.modelProviderBlock}>
                          <Text style={styles.modelProviderTitle}>Telegram Bot</Text>
                          <Text style={styles.modelProviderCaption}>
                            App messages from this chat are mirrored only to the selected bot.
                          </Text>
                          <View style={styles.modelList}>
                            {telegramBotConfigs.length ? telegramBotConfigs.map((bot: any) => {
                              const selected = bot.id === chatSettingsBotConfigId;
                              return (
                                <Pressable
                                  key={`chat-bot-${bot.id}`}
                                  style={({ hovered }: any) => [
                                    styles.modelListItem,
                                    hovered ? styles.modelListItemHovered : null,
                                    selected ? styles.modelListItemActive : null,
                                  ]}
                                  disabled={sessionSettingsMutationInFlight}
                                  onPress={() => void updateChatTelegramBotAssignment(chatSettingsSession.id, bot.id)}
                                >
                                  <View style={styles.modelListItemCopy}>
                                    <Text style={[styles.modelListItemTitle, selected ? styles.modelListItemTitleActive : null]}>
                                      {bot.label}
                                    </Text>
                                    <Text style={styles.modelProviderCaption}>{bot.bot_token}</Text>
                                  </View>
                                  <Text style={[styles.modelListItemMeta, selected ? styles.modelListItemMetaActive : null]}>
                                    {selected ? 'Assigned' : 'Use'}
                                  </Text>
                                </Pressable>
                              );
                            }) : (
                              <View style={styles.commandPanelEmpty}>
                                <Text style={styles.commandPanelEmptyTitle}>No Telegram bots yet</Text>
                                <Text style={styles.commandPanelEmptyText}>
                                  Add more bot configs in setup/settings to route chats separately.
                                </Text>
                              </View>
                            )}
                          </View>
                        </View>

                        <View style={styles.modelProviderBlock}>
                          <Text style={styles.modelProviderTitle}>Permission Mode</Text>
                          <Text style={styles.modelProviderCaption}>
                            Choose how freely this chat can control apps, files, browsers, and other active surfaces.
                          </Text>
                          <View style={styles.modelList}>
                            {securityPermissionOptions.map((mode: any) => {
                              const selected = chatSettingsSession.security_permission_mode === mode.id || (!chatSettingsSession.security_permission_mode && mode.id === 'standard');
                              return (
                                <Pressable
                                  key={`chat-permission-${mode.id}`}
                                  style={({ hovered }: any) => [
                                    styles.modelListItem,
                                    hovered ? styles.modelListItemHovered : null,
                                    selected ? styles.modelListItemActive : null,
                                  ]}
                                  disabled={sessionSettingsMutationInFlight}
                                  onPress={() => void updateChatSecurityPermissionMode(chatSettingsSession.id, mode.id)}
                                >
                                  <View style={styles.modelListItemCopy}>
                                    <Text style={[styles.modelListItemTitle, selected ? styles.modelListItemTitleActive : null]}>
                                      {mode.title}
                                    </Text>
                                    <Text style={styles.modelProviderCaption}>{mode.caption}</Text>
                                  </View>
                                  <Text style={[styles.modelListItemMeta, selected ? styles.modelListItemMetaActive : null]}>
                                    {selected ? 'Active' : 'Use'}
                                  </Text>
                                </Pressable>
                              );
                            })}
                          </View>
                        </View>

                        <View style={styles.modelProviderBlock}>
                          <Text style={styles.modelProviderTitle}>Sleep Mode</Text>
                          <Text style={styles.modelProviderCaption}>
                            Telegram uses designated sleep chats while the desktop UI is asleep. Local automations can still dispatch through the desktop runtime.
                          </Text>
                          <View style={styles.modelList}>
                            <Pressable
                              style={({ hovered }: any) => [
                                styles.modelListItem,
                                hovered ? styles.modelListItemHovered : null,
                                chatSettingsSession.headless_eligible ? styles.modelListItemActive : null,
                              ]}
                              disabled={sessionSettingsMutationInFlight}
                              onPress={() => void updateChatHeadlessEligibility(chatSettingsSession.id, !chatSettingsSession.headless_eligible)}
                            >
                              <View style={styles.modelListItemCopy}>
                                <Text style={[styles.modelListItemTitle, chatSettingsSession.headless_eligible ? styles.modelListItemTitleActive : null]}>
                                  {chatSettingsSession.headless_eligible ? 'Sleep eligible' : 'Not sleep eligible'}
                                </Text>
                                <Text style={styles.modelProviderCaption}>
                                  {chatSettingsSession.headless_eligible
                                    ? 'This chat can be chosen as the sleep chat for its bot.'
                                    : 'Turn this on before assigning the chat as a sleep target.'}
                                </Text>
                              </View>
                              <Text style={[styles.modelListItemMeta, chatSettingsSession.headless_eligible ? styles.modelListItemMetaActive : null]}>
                                {chatSettingsSession.headless_eligible ? 'On' : 'Off'}
                              </Text>
                            </Pressable>
                            <Pressable
                              style={({ hovered }: any) => [
                                styles.modelListItem,
                                hovered ? styles.modelListItemHovered : null,
                                chatSettingsSleepSessionId === chatSettingsSession.id ? styles.modelListItemActive : null,
                                !chatSettingsSession.headless_eligible ? styles.modelListItemDisabled : null,
                              ]}
                              disabled={sessionSettingsMutationInFlight || !chatSettingsSession.headless_eligible || !chatSettingsBotConfigId}
                              onPress={() => {
                                if (!chatSettingsBotConfigId) {
                                  return;
                                }
                                const nextSessionId = chatSettingsSleepSessionId === chatSettingsSession.id ? null : chatSettingsSession.id;
                                void setSleepChatForBot(chatSettingsBotConfigId, nextSessionId);
                              }}
                            >
                              <View style={styles.modelListItemCopy}>
                                <Text style={[styles.modelListItemTitle, chatSettingsSleepSessionId === chatSettingsSession.id ? styles.modelListItemTitleActive : null]}>
                                  {chatSettingsSleepSessionId === chatSettingsSession.id ? 'Designated sleep chat' : 'Make this the sleep chat'}
                                </Text>
                                <Text style={styles.modelProviderCaption}>
                                  {chatSettingsSleepSessionId === chatSettingsSession.id
                                    ? 'Telegram and automations can keep using this chat while the UI is asleep.'
                                    : 'Assign this chat as the active sleep target for its Telegram bot.'}
                                </Text>
                              </View>
                              <Text style={[styles.modelListItemMeta, chatSettingsSleepSessionId === chatSettingsSession.id ? styles.modelListItemMetaActive : null]}>
                                {chatSettingsSleepSessionId === chatSettingsSession.id ? 'Assigned' : 'Choose'}
                              </Text>
                            </Pressable>
                          </View>
                        </View>
                      </ScrollView>
                    ) : (
                      <View style={styles.commandPanelEmpty}>
                        <Text style={styles.commandPanelEmptyTitle}>Chat not available</Text>
                        <Text style={styles.commandPanelEmptyText}>
                          Reopen the panel after the chat list refreshes.
                        </Text>
                      </View>
                    )}
                  </View>
                ) : null}

              </View>
            ) : null}
          </View>

          {commandSuggestions.length ? (
            <View ref={commandSuggestionMenuRef} style={styles.commandSuggestionMenu}>
              <View style={styles.commandSuggestionHeader}>
                <Text style={styles.commandSuggestionTitle}>Commands</Text>
                <Pressable
                  style={styles.commandSuggestionCloseButton}
                  onPress={() => setDismissedCommandSuggestionInput(input)}
                >
                  <Text style={styles.commandSuggestionCloseText}>Dismiss</Text>
                </Pressable>
              </View>
              <View style={styles.commandSuggestionList}>
                {commandSuggestions.map((suggestion: any) => (
                  <Pressable
                    key={suggestion.name}
                    style={styles.commandSuggestionItem}
                    onPress={() => void selectCommandSuggestion(suggestion.command)}
                  >
                    <Text style={styles.commandSuggestionCommand}>{suggestion.command}</Text>
                    <Text style={styles.commandSuggestionDescription} numberOfLines={1}>
                      {suggestion.description}
                    </Text>
                  </Pressable>
                ))}
              </View>
            </View>
          ) : null}

          <View ref={composerTextRegionRef} style={styles.composerTextRegion}>
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
                    <Text style={styles.composerModeChipText}>Plan · {modeStatusLabel(planMode)}</Text>
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
            {Platform.OS === 'web' ? (
              <View pointerEvents="none" style={styles.composerInputMeasureShell}>
                <Text
                  style={styles.composerInputMeasureText}
                  onLayout={handleComposerMeasureLayout}
                >
                  {(input || ' ') + '\u200b'}
                </Text>
              </View>
            ) : null}
            <TextInput
              nativeID="desktop-composer-input"
              style={[styles.composerInput, { height: composerInputHeight }]}
              value={input}
              onChangeText={handleComposerInputChange}
              onContentSizeChange={handleComposerContentSizeChange}
              onKeyPress={handleComposerKeyPress}
              placeholder={DESKTOP_COMMAND_PLACEHOLDER}
              placeholderTextColor="#8f9ebb"
              multiline
              scrollEnabled={composerInputHeight >= COMPOSER_MAX_HEIGHT}
            />

            <View style={styles.composerFooterRow}>
              <View style={styles.composerFooterControls}>
                <Pressable
                  ref={toolsTriggerRef}
                  style={({ hovered }: any) => [
                    styles.composerIconButton,
                    hovered ? styles.composerIconButtonHovered : null,
                    activeCommandPanel?.kind === 'tools' && activeCommandPanel.source !== 'fleet' ? styles.composerIconButtonActive : null,
                  ]}
                  accessibilityRole="button"
                  accessibilityLabel="Open tool menu"
                  onPress={() => setActiveCommandPanel((current: any) => current?.kind === 'tools' && current.source !== 'fleet' ? null : { kind: 'tools', source: 'main' })}
                >
                  <MonoIcon name="plus" style={styles.composerIconButtonGlyph} />
                </Pressable>

                <Pressable
                  ref={permissionsTriggerRef}
                  style={({ hovered }: any) => [
                    styles.composerPermissionButton,
                    hovered ? styles.statusSurfaceHovered : null,
                    activeCommandPanel?.kind === 'permissions' ? styles.composerPermissionButtonActive : null,
                  ]}
                  accessibilityRole="button"
                  accessibilityLabel="Open permissions menu"
                  onPress={() => {
                    const targetSessionId = sessionId || null;
                    setActiveCommandPanel((current: any) => current?.kind === 'permissions' ? null : { kind: 'permissions', sessionId: targetSessionId });
                  }}
                >
                  <Text style={styles.composerPermissionIcon}>!</Text>
                  <Text style={styles.composerPermissionText} numberOfLines={1}>
                    {currentSecurityPermissionLabel}
                  </Text>
                  <MonoIcon name={activeCommandPanel?.kind === 'permissions' ? 'chevron_up' : 'chevron_down'} style={styles.composerInlineChevron} />
                </Pressable>
                <Text
                  style={styles.composerStatusText}
                  numberOfLines={1}
                  accessibilityLiveRegion="polite"
                >
                  {shortStatusText(status)}
                </Text>
              </View>

              <View style={styles.composerFooterActions}>
                <Pressable
                  ref={modelTriggerRef}
                  style={({ hovered }: any) => [
                    styles.composerModelButton,
                    hovered ? styles.statusSurfaceHovered : null,
                    activeCommandPanel?.kind === 'model' ? styles.composerModelButtonActive : null,
                  ]}
                  accessibilityRole="button"
                  accessibilityLabel="Open model menu"
                  onPress={() => setActiveCommandPanel((current: any) => current?.kind === 'model' ? null : { kind: 'model' })}
                >
                  <Text style={styles.composerModelText} numberOfLines={1}>
                    {currentModelLabel}{currentVariantLabel}
                  </Text>
                  <MonoIcon name={activeCommandPanel?.kind === 'model' ? 'chevron_up' : 'chevron_down'} style={styles.composerInlineChevron} />
                </Pressable>
                <Pressable
                  style={({ hovered }: any) => [
                    styles.contextMeterButton,
                    contextUsageHovered ? styles.contextMeterButtonExpanded : styles.contextMeterButtonCollapsed,
                    hovered ? styles.statusSurfaceHovered : null,
                  ]}
                  onHoverIn={() => setContextUsageHovered(true)}
                  onHoverOut={() => setContextUsageHovered(false)}
                >
                  <View style={styles.contextMeterOrb}>
                    <View
                      style={[
                        styles.contextMeterOrbFill,
                        contextUsage?.compaction_state === 'needs_compaction'
                          ? styles.contextMeterOrbFillWarn
                          : contextUsage?.compaction_state === 'compacted'
                            ? styles.contextMeterOrbFillCompact
                            : null,
                        { height: `${Math.max(contextUsageRatio * 100, contextUsageRatio > 0 ? 8 : 0)}%` },
                      ]}
                    />
                    <View style={styles.contextMeterOrbCore} />
                  </View>
                  {contextUsageHovered ? (
                    <View style={styles.contextMeterDetail}>
                      <Text style={styles.contextMeterDetailTitle}>Context</Text>
                      <Text style={styles.contextMeterDetailText} numberOfLines={1}>{contextUsageHoverLabel}</Text>
                      <Text style={styles.contextMeterDetailMeta} numberOfLines={1}>{contextStateLabel}</Text>
                    </View>
                  ) : null}
                </Pressable>
                <Pressable
                  style={[
                    styles.sendButton,
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

            {showFolderComposerMeta ? (
              <View style={styles.draftComposerMetaTray}>
                <View style={styles.draftComposerMetaRow}>
                  <View style={styles.draftComposerMetaControl}>
                    <Pressable
                      ref={draftProjectTriggerRef}
                      style={({ hovered }: any) => [
                        styles.draftComposerMetaChip,
                        hovered ? styles.draftComposerMetaChipHovered : null,
                        activeCommandPanel?.kind === 'draftProject' ? styles.draftComposerMetaChipActive : null,
                      ]}
                      onPress={() => {
                        if (!draftChat) {
                          void askForProjectFolderChoice();
                          return;
                        }
                        setActiveCommandPanel((current: any) => current?.kind === 'draftProject' ? null : { kind: 'draftProject' });
                      }}
                    >
                      <MonoIcon name="folder_closed" style={styles.draftComposerMetaIcon} />
                      <Text style={styles.draftComposerMetaLabel} numberOfLines={1}>{draftFolderLabel}</Text>
                      <MonoIcon
                        name={activeCommandPanel?.kind === 'draftProject' ? 'chevron_up' : 'chevron_down'}
                        style={styles.draftComposerMetaChevronIcon}
                      />
                    </Pressable>
                    {draftChat && activeCommandPanel?.kind === 'draftProject' ? draftProjectCommandPanel : null}
                  </View>
                  {draftChat ? (
                  <View style={styles.draftComposerMetaControl}>
                    <Pressable
                      ref={draftBranchTriggerRef}
                      style={({ hovered }: any) => [
                        styles.draftComposerMetaChip,
                        hovered ? styles.draftComposerMetaChipHovered : null,
                        activeCommandPanel?.kind === 'draftBranch' ? styles.draftComposerMetaChipActive : null,
                        !draftGitRepoState?.isGitRepo && !draftGitRepoLoading ? styles.draftComposerMetaChipDisabled : null,
                      ]}
                      disabled={!draftGitRepoState?.isGitRepo && !draftGitRepoLoading}
                      onPress={() => setActiveCommandPanel((current: any) => current?.kind === 'draftBranch' ? null : { kind: 'draftBranch' })}
                    >
                      <MonoIcon name="branch" style={styles.draftComposerMetaIcon} />
                      <Text style={styles.draftComposerMetaLabel} numberOfLines={1}>{draftBranchLabel}</Text>
                      <MonoIcon
                        name={activeCommandPanel?.kind === 'draftBranch' ? 'chevron_up' : 'chevron_down'}
                        style={styles.draftComposerMetaChevronIcon}
                      />
                    </Pressable>
                    {activeCommandPanel?.kind === 'draftBranch' ? draftBranchCommandPanel : null}
                  </View>
                  ) : null}
                  {draftChat && telegramBotConfigs.length > 1 ? (
                    <View style={styles.draftComposerMetaControl}>
                      <Pressable
                        ref={draftTelegramTriggerRef}
                        style={({ hovered }: any) => [
                          styles.draftComposerMetaChip,
                          hovered ? styles.draftComposerMetaChipHovered : null,
                          activeCommandPanel?.kind === 'draftTelegram' ? styles.draftComposerMetaChipActive : null,
                        ]}
                        onPress={() => setActiveCommandPanel((current: any) => current?.kind === 'draftTelegram' ? null : { kind: 'draftTelegram' })}
                      >
                        <MonoIcon name="telegram" style={styles.draftComposerMetaIcon} />
                        <Text style={styles.draftComposerMetaLabel} numberOfLines={1}>{draftTelegramBotLabel}</Text>
                        <MonoIcon
                          name={activeCommandPanel?.kind === 'draftTelegram' ? 'chevron_up' : 'chevron_down'}
                          style={styles.draftComposerMetaChevronIcon}
                        />
                      </Pressable>
                      {activeCommandPanel?.kind === 'draftTelegram' ? draftTelegramCommandPanel : null}
                    </View>
                  ) : null}
                </View>
              </View>
            ) : null}
          </View>
        </View>
        </View>
        </>
        )}
      </View>

      <DesktopConversationSidebarDock scope={scope} />
      <DesktopConversationOverlays scope={scope} />
    </View>
  );
}
