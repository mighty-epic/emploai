import { Platform, StyleSheet } from 'react-native';

import { DESKTOP_UI as UI } from './desktopUiTokens';

const WEB_FONT = Platform.OS === 'web' ? UI.type.sans : undefined;
const WEB_MONO = Platform.OS === 'web' ? UI.type.mono : undefined;

// This file is intentionally limited to visual overrides. Interaction state,
// component structure, and data flow remain in the existing feature modules.
export const desktopConversationVisualStyles = StyleSheet.create({
  monoIconBase: {
    color: UI.color.textMuted,
    fontFamily: WEB_FONT,
    fontWeight: '500',
  },
  shell: {
    backgroundColor: UI.color.canvas,
    fontFamily: WEB_FONT,
  },
  sidebarDock: {
    backgroundColor: UI.color.sidebar,
    borderRightColor: UI.color.border,
  },
  sidebarDockResizeHandle: {
    backgroundColor: 'transparent',
    borderRightColor: UI.color.border,
  },
  sidebarCollapsedHandle: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.border,
  },
  sidebarCollapsedHandleHovered: {
    backgroundColor: UI.color.surfaceHover,
    borderColor: UI.color.borderStrong,
  },
  sidebarHeaderCollapseButton: {
    borderRadius: UI.radius.control,
    backgroundColor: 'transparent',
    borderColor: 'transparent',
  },
  sidebarHeaderCollapseButtonHovered: {
    backgroundColor: UI.color.surfaceHover,
    borderColor: UI.color.border,
  },
  utilityRail: {
    backgroundColor: UI.color.chrome,
    borderRightColor: UI.color.border,
  },
  utilityRailButton: {
    borderRadius: UI.radius.control,
    borderColor: 'transparent',
    backgroundColor: 'transparent',
  },
  utilityRailButtonHovered: {
    backgroundColor: UI.color.surfaceHover,
    borderColor: UI.color.border,
  },
  utilityRailButtonActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  utilityRailIcon: {
    color: UI.color.textMuted,
  },
  utilityRailLabel: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  utilityRailLabelActive: {
    color: UI.color.accentStrong,
  },
  utilityRailDivider: {
    backgroundColor: UI.color.border,
  },
  utilityRailTab: {
    borderRadius: UI.radius.control,
    backgroundColor: 'transparent',
    borderColor: 'transparent',
  },
  utilityRailTabActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  utilityRailTabLabel: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  utilityRailTabLabelActive: {
    color: UI.color.accentStrong,
  },
  utilityRailTabMeta: {
    color: UI.color.textSubtle,
  },
  utilityRailTabMetaActive: {
    color: UI.color.accentStrong,
  },
  sessionsRail: {
    backgroundColor: UI.color.sidebar,
  },
  eyebrow: {
    color: UI.color.textSubtle,
    fontWeight: '600',
    letterSpacing: 0.45,
  },
  railTitle: {
    color: UI.color.text,
    fontWeight: '700',
    letterSpacing: -0.25,
  },
  railText: {
    color: UI.color.textMuted,
  },
  primaryRailButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accent,
  },
  primaryRailButtonText: {
    color: UI.color.accentInk,
    fontWeight: '700',
  },
  secondaryRailButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.border,
  },
  secondaryRailButtonText: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  railMetaCard: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.border,
  },
  metaLabel: {
    color: UI.color.textSubtle,
    letterSpacing: 0.4,
  },
  metaValue: {
    color: UI.color.text,
    fontWeight: '700',
  },
  sidebarAccountFooter: {
    borderTopColor: UI.color.border,
    backgroundColor: UI.color.sidebar,
  },
  sidebarAccountButton: {
    borderRadius: UI.radius.control,
    backgroundColor: 'transparent',
    borderColor: 'transparent',
  },
  sidebarAccountButtonHovered: {
    backgroundColor: UI.color.surfaceHover,
    borderColor: UI.color.border,
  },
  sidebarAccountButtonActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  sidebarAccountAvatar: {
    backgroundColor: UI.color.surfaceRaised,
    borderColor: UI.color.borderStrong,
  },
  sidebarAccountAvatarText: {
    color: UI.color.text,
  },
  sidebarAccountEmail: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  sidebarAccountMenu: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surfaceRaised,
    borderColor: UI.color.borderStrong,
    ...UI.elevation.high,
  },
  sidebarAccountMenuRowHovered: {
    backgroundColor: UI.color.surfaceHover,
  },
  sidebarListRow: {
    borderRadius: UI.radius.control,
    backgroundColor: 'transparent',
  },
  sidebarListRowHovered: {
    backgroundColor: UI.color.surfaceHover,
  },
  sidebarListRowIcon: {
    color: UI.color.textSubtle,
  },
  sidebarListRowTitle: {
    color: UI.color.text,
    fontWeight: '600',
  },
  sidebarListRowText: {
    color: UI.color.textSubtle,
  },
  sidebarSearchShell: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.border,
  },
  sidebarSearchGlyph: {
    color: UI.color.textSubtle,
  },
  sidebarSearchButtonText: {
    color: UI.color.textMuted,
  },
  sidebarComputerTab: {
    borderRadius: UI.radius.small,
    backgroundColor: 'transparent',
  },
  sidebarComputerTabActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  sidebarComputerTabText: {
    color: UI.color.textMuted,
  },
  sidebarComputerTabTextActive: {
    color: UI.color.accentStrong,
  },
  projectCard: {
    borderRadius: UI.radius.control,
    backgroundColor: 'transparent',
    borderColor: 'transparent',
  },
  projectCardSelected: {
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.border,
  },
  projectHeaderRowHovered: {
    backgroundColor: UI.color.surfaceHover,
  },
  projectTitle: {
    color: UI.color.text,
    fontWeight: '600',
  },
  projectMeta: {
    color: UI.color.textSubtle,
  },
  projectChatRow: {
    borderRadius: UI.radius.small,
    backgroundColor: 'transparent',
  },
  projectChatRowHovered: {
    backgroundColor: UI.color.surfaceHover,
  },
  projectChatRowActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  projectChatTitle: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  projectChatAge: {
    color: UI.color.textSubtle,
  },
  projectChatMeta: {
    color: UI.color.textSubtle,
  },
  projectChatPreview: {
    color: UI.color.textSubtle,
  },
  sidebarSimpleRow: {
    borderRadius: UI.radius.control,
    backgroundColor: 'transparent',
  },
  sidebarSimpleRowHovered: {
    backgroundColor: UI.color.surfaceHover,
  },
  sidebarSimpleRowActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  sidebarSimpleRowTitle: {
    color: UI.color.text,
    fontWeight: '600',
  },
  sidebarSimpleRowSubtle: {
    color: UI.color.textSubtle,
  },
  sidebarSimpleRowMeta: {
    color: UI.color.textSubtle,
  },
  sidebarChatsCard: {
    backgroundColor: 'transparent',
    borderColor: 'transparent',
  },
  sidebarChatsTitle: {
    color: UI.color.text,
    fontWeight: '700',
  },
  sidebarChatsText: {
    color: UI.color.textSubtle,
  },
  sidebarSearchCard: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.border,
  },
  sidebarSearchInput: {
    color: UI.color.text,
  },
  sidebarSearchModalOverlay: {
    backgroundColor: UI.color.overlay,
  },
  sidebarSearchModalCard: {
    borderRadius: UI.radius.large,
    backgroundColor: UI.color.surfaceRaised,
    borderColor: UI.color.borderStrong,
    ...UI.elevation.high,
  },
  folderChoiceOverlay: {
    backgroundColor: UI.color.overlay,
  },
  folderChoiceCard: {
    borderRadius: UI.radius.large,
    backgroundColor: UI.color.surfaceRaised,
    borderColor: UI.color.borderStrong,
    ...UI.elevation.high,
  },
  contextMenuCard: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surfaceRaised,
    borderColor: UI.color.borderStrong,
    ...UI.elevation.high,
  },
  contextMenuItem: {
    borderRadius: UI.radius.small,
  },
  contextMenuItemHovered: {
    backgroundColor: UI.color.surfaceHover,
  },
  contextMenuItemText: {
    color: UI.color.text,
    fontWeight: '600',
  },
  contextMenuItemTextWarn: {
    color: '#f0a3ad',
  },
  conversationColumn: {
    backgroundColor: UI.color.canvas,
  },
  jarvisStage: {
    backgroundColor: UI.color.canvas,
    borderColor: UI.color.border,
    borderRadius: UI.radius.panel,
  },
  surfaceModeTabsBar: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.border,
  },
  surfaceModeTab: {
    borderRadius: UI.radius.small,
  },
  surfaceModeTabHovered: {
    backgroundColor: UI.color.surfaceHover,
  },
  surfaceModeTabActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  surfaceModeTabText: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  surfaceModeTabTextActive: {
    color: UI.color.accentStrong,
  },
  compactHeader: {
    borderBottomColor: UI.color.border,
    backgroundColor: UI.color.canvas,
  },
  compactTitle: {
    color: UI.color.text,
    fontWeight: '700',
    letterSpacing: -0.25,
  },
  compactSubtitle: {
    color: UI.color.textSubtle,
  },
  agentStatusBar: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.border,
  },
  taskBoardCard: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surface,
    borderColor: UI.color.border,
  },
  taskBoardGoal: {
    color: UI.color.text,
    fontWeight: '700',
  },
  taskBoardMeta: {
    color: UI.color.textMuted,
  },
  taskBoardInfoChip: {
    borderRadius: UI.radius.small,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.border,
  },
  transcriptScroll: {
    borderRadius: 0,
    backgroundColor: UI.color.canvas,
  },
  transcriptContent: {
    paddingHorizontal: 28,
    paddingVertical: 22,
    gap: 16,
  },
  messageBubble: {
    paddingHorizontal: 16,
    paddingVertical: 13,
    gap: 7,
  },
  messageBubbleUser: {
    backgroundColor: '#15313a',
    borderRadius: UI.radius.panel,
    borderWidth: 1,
    borderColor: UI.color.accentBorder,
  },
  messageBubbleAssistant: {
    backgroundColor: 'transparent',
    borderWidth: 0,
    paddingHorizontal: 0,
    paddingVertical: 2,
  },
  messageBubbleSystem: {
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.borderStrong,
    borderRadius: UI.radius.control,
  },
  messageLabel: {
    color: UI.color.textSubtle,
    fontWeight: '600',
    textTransform: 'none',
    letterSpacing: 0.2,
  },
  messageLabelOnLight: {
    color: UI.color.accentStrong,
  },
  messageTime: {
    color: UI.color.textSubtle,
  },
  messageTimeOnLight: {
    color: UI.color.textMuted,
  },
  messageText: {
    color: UI.color.text,
    lineHeight: 23,
  },
  messageTextOnLight: {
    color: UI.color.text,
  },
  planQuestionCard: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surface,
    borderColor: UI.color.border,
  },
  proposedPlanCard: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surface,
    borderColor: UI.color.border,
  },
  planCardEyebrow: {
    color: UI.color.textSubtle,
  },
  planCardTitle: {
    color: UI.color.text,
    fontWeight: '700',
  },
  proposedPlanText: {
    color: UI.color.textMuted,
  },
  planQuestionOption: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 1,
    borderColor: UI.color.border,
  },
  planQuestionOptionHovered: {
    backgroundColor: UI.color.surfaceHover,
    borderColor: UI.color.borderStrong,
  },
  planQuestionOptionIndex: {
    backgroundColor: UI.color.accentSoft,
    color: UI.color.accentStrong,
  },
  planQuestionOptionLabel: {
    color: UI.color.text,
    fontWeight: '700',
  },
  planQuestionOptionDescription: {
    color: UI.color.textMuted,
  },
  planCardPrimaryAction: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accent,
  },
  planCardPrimaryActionText: {
    color: UI.color.accentInk,
    fontWeight: '700',
  },
  planCardSecondaryAction: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceRaised,
    borderWidth: 1,
    borderColor: UI.color.borderStrong,
  },
  panelToggleButtonActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  panelToggleButtonTextActive: {
    color: UI.color.accentStrong,
  },
  sidebarMenuRowActive: {
    borderBottomColor: UI.color.accent,
  },
  voiceLanguageChipActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  voiceLanguageChipTextActive: {
    color: UI.color.accentStrong,
  },
  voiceModeChipActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  voiceModeChipTextActive: {
    color: UI.color.accentStrong,
  },
  composerDock: {
    paddingHorizontal: 24,
    paddingBottom: 12,
  },
  syntheticThinkingTextHighlight: {
    color: UI.color.accentStrong,
  },
  pendingSwitchPrimaryAction: {
    backgroundColor: UI.color.accent,
  },
  pendingSwitchPrimaryActionText: {
    color: UI.color.accentInk,
  },
  composerShell: {
    borderRadius: UI.radius.large,
    backgroundColor: UI.color.surface,
    borderWidth: 1,
    borderColor: UI.color.borderStrong,
    ...UI.elevation.high,
  },
  composerModeChip: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.border,
  },
  composerModeChipActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  composerModeChipText: {
    color: UI.color.textMuted,
  },
  composerInput: {
    color: UI.color.text,
    fontFamily: WEB_FONT,
  },
  composerIconButton: {
    borderRadius: UI.radius.control,
  },
  composerIconButtonHovered: {
    backgroundColor: UI.color.surfaceHover,
    borderColor: UI.color.border,
  },
  composerIconButtonActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  composerIconButtonGlyph: {
    color: UI.color.textMuted,
  },
  composerPermissionButton: {
    borderRadius: UI.radius.control,
  },
  composerModelButton: {
    borderRadius: UI.radius.control,
  },
  composerModelButtonActive: {
    backgroundColor: UI.color.surfaceHover,
    borderColor: UI.color.border,
  },
  composerModelText: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  composerStatusText: {
    color: UI.color.textSubtle,
  },
  draftComposerMetaTray: {
    borderTopColor: UI.color.border,
    backgroundColor: UI.color.surfaceMuted,
    borderBottomLeftRadius: UI.radius.large,
    borderBottomRightRadius: UI.radius.large,
  },
  draftComposerMetaChip: {
    backgroundColor: 'transparent',
    borderRadius: UI.radius.control,
  },
  draftComposerMetaChipHovered: {
    backgroundColor: UI.color.surfaceHover,
  },
  draftComposerMetaChipActive: {
    backgroundColor: UI.color.accentSoft,
  },
  draftComposerMetaLabel: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  sendButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accent,
    shadowColor: UI.color.shadow,
    shadowOpacity: 0.2,
    shadowRadius: 8,
  },
  sendButtonIdle: {
    backgroundColor: UI.color.surfaceHover,
    borderWidth: 1,
    borderColor: UI.color.borderStrong,
  },
  sendButtonStop: {
    backgroundColor: UI.color.danger,
  },
  sendButtonInterrupt: {
    backgroundColor: UI.color.accentStrong,
  },
  sendButtonText: {
    color: UI.color.accentInk,
  },
  commandPanel: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surfaceRaised,
    borderColor: UI.color.borderStrong,
    ...UI.elevation.high,
  },
  commandPanelEyebrow: {
    color: UI.color.textSubtle,
    letterSpacing: 0.4,
  },
  commandPanelWarningText: {
    color: UI.color.warning,
  },
  commandPanelPrimaryAction: {
    backgroundColor: UI.color.accent,
  },
  commandPanelPrimaryActionText: {
    color: UI.color.accentInk,
    fontWeight: '700',
  },
  commandSuggestionMenu: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surfaceRaised,
    borderColor: UI.color.borderStrong,
  },
  commandSuggestionTitle: {
    color: UI.color.textSubtle,
    letterSpacing: 0.35,
  },
  commandSuggestionItem: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
  },
  commandSuggestionCommand: {
    color: UI.color.accentStrong,
    fontFamily: WEB_MONO,
  },
  commandSuggestionDescription: {
    color: UI.color.textMuted,
  },
  modelProviderDropdown: {
    borderColor: UI.color.border,
    backgroundColor: UI.color.surfaceMuted,
    borderRadius: UI.radius.control,
  },
  permissionOptionRowActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  permissionOptionTitleActive: {
    color: UI.color.accentStrong,
  },
  permissionOptionMetaActive: {
    color: UI.color.textMuted,
  },
  permissionInfoTitle: {
    color: UI.color.accentStrong,
  },
  modelPickerSectionTitle: {
    color: UI.color.textMuted,
    fontWeight: '700',
  },
  modelProviderDropdownHeaderHovered: {
    backgroundColor: UI.color.surfaceHover,
  },
  modelListItem: {
    borderRadius: UI.radius.control,
    backgroundColor: 'transparent',
  },
  modelListItemHovered: {
    backgroundColor: UI.color.surfaceHover,
  },
  modelListItemActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  modelListItemTitle: {
    color: UI.color.text,
    fontWeight: '600',
  },
  modelListItemTitleActive: {
    color: UI.color.accentStrong,
  },
  modelListItemMeta: {
    color: UI.color.textSubtle,
  },
  toolPackCompactLabelEnabled: {
    color: UI.color.accentStrong,
  },
  toolPackInfoIconActive: {
    color: UI.color.accentStrong,
  },
  toolPackInfoWarning: {
    color: UI.color.warning,
  },
  toolPackSwitchActive: {
    backgroundColor: UI.color.accent,
  },
  toolPackListItemTitleActive: {
    color: UI.color.accentStrong,
  },
  toolPackListItemMetaActive: {
    color: UI.color.textMuted,
  },
  sessionCommandCardActive: {
    borderColor: UI.color.accentBorder,
    backgroundColor: UI.color.accentSoft,
  },
  sessionCommandBadge: {
    backgroundColor: UI.color.accentSoft,
    borderWidth: 1,
    borderColor: UI.color.accentBorder,
  },
  sessionCommandBadgeText: {
    color: UI.color.accentStrong,
  },
  contextMeterOrbFillWarn: {
    backgroundColor: UI.color.warning,
  },
  timelineRunDisclosure: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surface,
    borderColor: UI.color.border,
  },
  timelineTranscriptCard: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surface,
    borderColor: UI.color.border,
  },
  editSummaryCard: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surface,
    borderColor: UI.color.border,
  },
  emptyCard: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.border,
  },
  emptyConversationCard: {
    borderRadius: UI.radius.panel,
    backgroundColor: 'transparent',
    borderColor: 'transparent',
  },
  emptyTitle: {
    color: UI.color.text,
    fontWeight: '700',
  },
  emptyText: {
    color: UI.color.textMuted,
  },
  fleetWorkspace: {
    backgroundColor: UI.color.canvas,
  },
  fleetManagerChatPanel: {
    backgroundColor: UI.color.canvas,
    borderRightColor: UI.color.border,
  },
  fleetManagerChatHeader: {
    backgroundColor: UI.color.sidebar,
    borderBottomColor: UI.color.border,
  },
  fleetManagerChatTitle: {
    color: UI.color.text,
    fontWeight: '700',
  },
  fleetManagerChatActionButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.border,
  },
  fleetManagerChatActionButtonHovered: {
    backgroundColor: UI.color.surfaceHover,
    borderColor: UI.color.borderStrong,
  },
  fleetManagerTranscript: {
    backgroundColor: UI.color.canvas,
  },
  fleetManagerMessageUser: {
    backgroundColor: '#15313a',
    borderColor: UI.color.accentBorder,
  },
  fleetManagerMessageAssistant: {
    backgroundColor: 'transparent',
  },
  fleetManagerComposer: {
    backgroundColor: UI.color.surface,
    borderColor: UI.color.borderStrong,
    borderRadius: UI.radius.large,
  },
  fleetSidebarPanel: {
    backgroundColor: UI.color.sidebar,
    borderLeftColor: UI.color.border,
  },
  fleetPanelTitle: {
    color: UI.color.text,
    fontWeight: '700',
  },
  fleetPanelText: {
    color: UI.color.textMuted,
  },
  fleetStatusCard: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.border,
  },
  fleetCreateCard: {
    borderRadius: UI.radius.panel,
    backgroundColor: 'transparent',
    borderColor: UI.color.border,
  },
  fleetInput: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.borderStrong,
    color: UI.color.text,
  },
  fleetPrimaryAction: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accent,
  },
  fleetPrimaryActionText: {
    color: UI.color.accentInk,
    fontWeight: '700',
  },
  fleetSecondaryAction: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.borderStrong,
  },
  fleetSecondaryActionText: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  fleetEnrollmentCard: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  fleetEnrollmentToken: {
    color: UI.color.accentStrong,
    fontFamily: WEB_MONO,
  },
  fleetWorkerGrid: {
    gap: 8,
    ...(Platform.OS === 'web'
      ? ({
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr)',
          alignItems: 'stretch',
        } as any)
      : {
          flexDirection: 'column',
        }),
  },
  fleetWorkerCard: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surface,
    borderColor: UI.color.border,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  fleetWorkerName: {
    color: UI.color.text,
    fontWeight: '700',
  },
  fleetWorkerMeta: {
    color: UI.color.textSubtle,
    fontWeight: '600',
    textTransform: 'none',
  },
  fleetWorkerMenuButton: {
    borderRadius: UI.radius.control,
    backgroundColor: 'transparent',
    borderColor: UI.color.border,
  },
  fleetWorkerMenuButtonActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  fleetWorkerMenu: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceRaised,
    borderColor: UI.color.borderStrong,
  },
  fleetWorkerInfoGrid: {
    gap: 0,
    borderTopWidth: 1,
    borderTopColor: UI.color.border,
  },
  fleetWorkerInfoTile: {
    borderRadius: 0,
    backgroundColor: 'transparent',
    borderWidth: 0,
    borderBottomWidth: 1,
    borderBottomColor: UI.color.border,
    paddingHorizontal: 0,
    paddingVertical: 9,
  },
  fleetInfoLabel: {
    color: UI.color.textSubtle,
    fontWeight: '600',
    letterSpacing: 0.35,
  },
  fleetInfoValue: {
    color: UI.color.textMuted,
  },
  fleetInfoMeta: {
    color: UI.color.accentStrong,
  },
});
