import { Platform, StyleSheet } from 'react-native';

import { DESKTOP_UI as UI } from './desktopUiTokens';

const WEB_FONT = Platform.OS === 'web' ? UI.type.sans : undefined;
const WEB_MONO = Platform.OS === 'web' ? UI.type.mono : undefined;

// Presentation-only settings refinements. The settings form and save/discard
// behavior stay in DesktopSetupPanel and its focused feature sections.
export const desktopSetupPanelVisualStyles = StyleSheet.create({
  shell: {
    borderRadius: 0,
    backgroundColor: UI.color.canvas,
    borderColor: 'transparent',
    padding: 18,
    gap: 16,
    fontFamily: WEB_FONT,
  },
  eyebrow: {
    color: UI.color.textSubtle,
    fontWeight: '600',
    letterSpacing: 0.45,
  },
  title: {
    color: UI.color.text,
    fontWeight: '700',
    letterSpacing: -0.4,
  },
  subtitle: {
    color: UI.color.textMuted,
  },
  versionBadge: {
    width: 168,
    backgroundColor: 'transparent',
    borderWidth: 0,
    borderRadius: 0,
    paddingHorizontal: 0,
    paddingVertical: 4,
  },
  versionLabel: {
    color: UI.color.textSubtle,
    letterSpacing: 0.35,
    fontWeight: '600',
  },
  versionValue: {
    color: UI.color.text,
    fontSize: 15,
    fontWeight: '700',
    fontFamily: WEB_MONO,
  },
  settingsFrame: {
    gap: 0,
    minHeight: 640,
    borderRadius: 0,
    overflow: 'hidden',
    backgroundColor: UI.color.canvas,
    borderWidth: 0,
  },
  settingsSidebar: {
    width: 244,
    backgroundColor: UI.color.sidebar,
    borderWidth: 0,
    borderRadius: 0,
    padding: 12,
    gap: 12,
  },
  backToAppButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  backToAppButtonText: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  backToAppPlaceholderText: {
    color: UI.color.textSubtle,
    fontWeight: '600',
  },
  settingsNavList: {
    gap: 3,
  },
  settingsNavItem: {
    borderRadius: UI.radius.control,
    paddingHorizontal: 11,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  settingsNavItemActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: 'transparent',
  },
  settingsNavItemTitle: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  settingsNavItemTitleActive: {
    color: UI.color.accentStrong,
  },
  settingsNavItemDescription: {
    display: 'none',
  },
  settingsContentPane: {
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
    borderRadius: 0,
  },
  settingsContentHeader: {
    paddingHorizontal: 24,
    paddingTop: 20,
    paddingBottom: 17,
    borderBottomColor: UI.color.border,
    backgroundColor: UI.color.canvas,
  },
  settingsContentTitle: {
    color: UI.color.text,
    fontWeight: '700',
    letterSpacing: -0.25,
  },
  settingsContentSubtitle: {
    color: UI.color.textMuted,
  },
  formContent: {
    gap: 0,
    paddingHorizontal: 24,
    paddingTop: 4,
    paddingBottom: 24,
  },
  warningCard: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.dangerSoft,
    borderColor: 'rgba(224, 120, 132, 0.34)',
    marginTop: 16,
  },
  warningTitle: {
    color: '#f3b5bd',
    fontWeight: '700',
  },
  warningLine: {
    color: '#e8c3c8',
  },
  onboardingSuggestionCard: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accentSoft,
    borderWidth: 0,
    marginTop: 16,
  },
  onboardingSuggestionEyebrow: {
    color: UI.color.textSubtle,
    fontWeight: '600',
    letterSpacing: 0.35,
  },
  onboardingSuggestionTitle: {
    color: UI.color.text,
    fontWeight: '700',
  },
  onboardingSuggestionText: {
    color: UI.color.textMuted,
  },
  onboardingSuggestionMeta: {
    color: UI.color.textSubtle,
  },
  section: {
    borderRadius: 0,
    backgroundColor: 'transparent',
    borderWidth: 0,
    borderTopWidth: 1,
    borderTopColor: UI.color.border,
    paddingHorizontal: 0,
    paddingVertical: 20,
    gap: 12,
  },
  sectionTitle: {
    color: UI.color.text,
    fontSize: 16,
    fontWeight: '700',
  },
  helperText: {
    color: UI.color.textMuted,
  },
  settingStack: {
    gap: 0,
    backgroundColor: 'transparent',
    borderRadius: 0,
    overflow: 'visible',
    borderWidth: 0,
  },
  settingCard: {
    borderRadius: 0,
    backgroundColor: 'transparent',
    borderWidth: 0,
    borderBottomWidth: 1,
    borderBottomColor: UI.color.border,
    paddingHorizontal: 15,
    paddingVertical: 13,
    gap: 10,
  },
  settingCardInner: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  settingCardTitle: {
    color: UI.color.text,
    fontWeight: '600',
  },
  settingCardDescription: {
    color: UI.color.textMuted,
  },
  fieldLabel: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  infoBadge: {
    borderColor: UI.color.borderStrong,
    backgroundColor: UI.color.surfaceMuted,
  },
  infoBadgeText: {
    color: UI.color.accentStrong,
  },
  input: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.borderStrong,
    color: UI.color.text,
    paddingHorizontal: 12,
    paddingVertical: 11,
  },
  inputDisabled: {
    backgroundColor: UI.color.surface,
    borderColor: UI.color.border,
    color: UI.color.textSubtle,
  },
  telegramUserChip: {
    borderRadius: UI.radius.small,
    backgroundColor: UI.color.accentSoft,
    borderWidth: 1,
    borderColor: UI.color.accentBorder,
  },
  telegramUserChipText: {
    color: UI.color.accentStrong,
    fontWeight: '600',
  },
  localEmbeddedSection: {
    borderTopColor: UI.color.border,
  },
  localColumn: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  localRow: {
    borderRadius: UI.radius.control,
    backgroundColor: 'transparent',
    borderWidth: 0,
  },
  localRowTitle: {
    color: UI.color.text,
    fontWeight: '600',
  },
  localRowBody: {
    color: UI.color.textMuted,
  },
  localActionButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceRaised,
    borderWidth: 0,
  },
  localActionButtonText: {
    color: UI.color.text,
    fontWeight: '600',
  },
  localDangerButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.dangerSoft,
    borderColor: 'rgba(224, 120, 132, 0.36)',
  },
  localDangerButtonText: {
    color: '#f3b5bd',
  },
  localEmptyText: {
    color: UI.color.textSubtle,
  },
  localStatusText: {
    color: UI.color.textMuted,
  },
  localCodePreview: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.canvas,
    borderColor: UI.color.border,
    color: UI.color.textMuted,
    fontFamily: WEB_MONO,
  },
  validationTextChecking: {
    color: UI.color.textMuted,
  },
  validationTextValid: {
    color: UI.color.success,
  },
  validationTextInvalid: {
    color: UI.color.warning,
  },
  validationTextError: {
    color: UI.color.danger,
  },
  settingRow: {
    borderTopColor: UI.color.border,
  },
  settingRowTitle: {
    color: UI.color.text,
    fontWeight: '600',
  },
  settingRowDescription: {
    color: UI.color.textMuted,
  },
  sleepModeCard: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  sleepModeStatusBadge: {
    borderRadius: UI.radius.small,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  sleepModeStatusActive: {
    backgroundColor: UI.color.successSoft,
    borderColor: 'rgba(117, 198, 154, 0.34)',
  },
  sleepModeActionButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  sleepModeActionButtonActive: {
    backgroundColor: UI.color.accent,
    borderColor: UI.color.accentStrong,
  },
  sleepModeActionButtonText: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  sleepModeActionButtonTextActive: {
    color: UI.color.accentInk,
  },
  sleepModeSecondaryButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  sleepModeSecondaryButtonText: {
    color: UI.color.textMuted,
  },
  sleepModeConfirmPanel: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.warningSoft,
    borderColor: 'rgba(215, 174, 106, 0.34)',
  },
  stepperControl: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.border,
  },
  stepperButton: {
    backgroundColor: UI.color.surfaceRaised,
  },
  stepperButtonText: {
    color: UI.color.text,
  },
  compactActionButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceRaised,
    borderWidth: 0,
  },
  compactActionButtonText: {
    color: UI.color.text,
    fontWeight: '600',
  },
  toggleSwitch: {
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.borderStrong,
  },
  toggleSwitchActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accent,
  },
  toggleSwitchKnob: {
    backgroundColor: UI.color.textSubtle,
  },
  toggleSwitchKnobActive: {
    backgroundColor: UI.color.accentStrong,
  },
  pathValue: {
    color: UI.color.textMuted,
    fontFamily: WEB_MONO,
  },
  pathButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceRaised,
    borderWidth: 0,
  },
  pathButtonText: {
    color: UI.color.text,
    fontWeight: '600',
  },
  providerChip: {
    borderRadius: UI.radius.small,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  providerChipText: {
    color: UI.color.textMuted,
  },
  providerVaultStatus: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  providerVaultStatusText: {
    color: UI.color.textMuted,
  },
  providerVaultDeleteButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.dangerSoft,
    borderColor: 'rgba(224, 120, 132, 0.34)',
  },
  providerVaultDeleteText: {
    color: '#f3b5bd',
  },
  noteCard: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  noteLine: {
    color: UI.color.textMuted,
  },
  pairingQrCard: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surface,
    borderWidth: 0,
  },
  voiceModeButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  voiceModeButtonActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  voiceModeButtonText: {
    color: UI.color.textMuted,
  },
  voiceModeButtonTextActive: {
    color: UI.color.accentStrong,
  },
  voicePackCard: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  voicePackTitle: {
    color: UI.color.text,
    fontWeight: '700',
  },
  voicePackDescription: {
    color: UI.color.textMuted,
  },
  voicePackStatusBadge: {
    borderRadius: UI.radius.small,
  },
  voicePackProgressCard: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.canvas,
    borderWidth: 0,
  },
  voicePackProgressTrack: {
    backgroundColor: UI.color.border,
  },
  voicePackProgressFill: {
    backgroundColor: UI.color.accent,
  },
  voicePackActionButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accent,
  },
  voicePackActionButtonSecondary: {
    backgroundColor: UI.color.surfaceRaised,
    borderColor: UI.color.borderStrong,
  },
  dangerOutlineButton: {
    borderRadius: UI.radius.control,
    borderColor: 'rgba(224, 120, 132, 0.42)',
    backgroundColor: UI.color.dangerSoft,
  },
  metaCard: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  metaLabel: {
    color: UI.color.textSubtle,
    letterSpacing: 0.35,
  },
  metaValue: {
    color: UI.color.text,
    fontFamily: WEB_MONO,
  },
  extensionGuideCard: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  footer: {
    borderTopColor: UI.color.border,
    backgroundColor: UI.color.surface,
  },
  footerStatusDot: {
    backgroundColor: UI.color.textSubtle,
  },
  footerStatusDotSuccess: {
    backgroundColor: UI.color.success,
  },
  footerStatusDotError: {
    backgroundColor: UI.color.danger,
  },
  footerStatusText: {
    color: UI.color.textSubtle,
  },
  footerStatusTextSuccess: {
    color: UI.color.success,
  },
  footerStatusTextError: {
    color: UI.color.danger,
  },
  secondaryButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  secondaryButtonText: {
    color: UI.color.text,
    fontWeight: '600',
  },
  primaryButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accent,
  },
  primaryButtonText: {
    color: UI.color.accentInk,
    fontWeight: '700',
  },
});
