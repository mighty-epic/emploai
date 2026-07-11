import { Platform, StyleSheet } from 'react-native';

import { DESKTOP_UI as UI } from './desktopUiTokens';

const WEB_FONT = Platform.OS === 'web' ? UI.type.sans : undefined;
const WEB_MONO = Platform.OS === 'web' ? UI.type.mono : undefined;

export const desktopAutomationsVisualStyles = StyleSheet.create({
  container: {
    backgroundColor: UI.color.canvas,
    fontFamily: WEB_FONT,
  },
  page: {
    backgroundColor: UI.color.canvas,
  },
  title: {
    color: UI.color.text,
    fontWeight: '700',
    letterSpacing: -0.4,
  },
  subtitle: {
    color: UI.color.textMuted,
  },
  statusText: {
    color: UI.color.textSubtle,
  },
  attentionPill: {
    borderRadius: UI.radius.small,
    backgroundColor: UI.color.warningSoft,
    borderColor: 'rgba(215, 174, 106, 0.38)',
  },
  attentionPillText: {
    color: UI.color.warning,
    fontWeight: '600',
  },
  content: {
    gap: 1,
    borderRadius: UI.radius.panel,
    overflow: 'hidden',
    backgroundColor: UI.color.border,
    borderWidth: 1,
    borderColor: UI.color.border,
  },
  leftPane: {
    borderRadius: 0,
    backgroundColor: UI.color.sidebar,
    borderWidth: 0,
  },
  mainPane: {
    borderRadius: 0,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  rightPane: {
    borderRadius: 0,
    backgroundColor: UI.color.sidebar,
    borderWidth: 0,
  },
  sectionTitle: {
    color: UI.color.text,
    fontWeight: '700',
  },
  sectionMeta: {
    color: UI.color.textSubtle,
  },
  ruleRow: {
    borderRadius: UI.radius.control,
    backgroundColor: 'transparent',
    borderColor: 'transparent',
  },
  ruleRowSelected: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  ruleStatusDotEnabled: {
    backgroundColor: UI.color.success,
  },
  ruleStatusDotPaused: {
    backgroundColor: UI.color.textSubtle,
  },
  ruleName: {
    color: UI.color.text,
    fontWeight: '600',
  },
  ruleMeta: {
    color: UI.color.textSubtle,
  },
  rulePrompt: {
    color: UI.color.textMuted,
  },
  readyBadge: {
    color: UI.color.success,
    backgroundColor: UI.color.successSoft,
    borderRadius: UI.radius.small,
    borderWidth: 1,
    borderColor: 'rgba(117, 198, 154, 0.3)',
    fontWeight: '600',
  },
  templateButton: {
    borderRadius: UI.radius.control,
    borderColor: UI.color.borderStrong,
    backgroundColor: UI.color.surfaceMuted,
  },
  templateButtonText: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  detailTitleBlock: {
    gap: 4,
  },
  detailEyebrow: {
    color: UI.color.textSubtle,
    fontWeight: '600',
    textTransform: 'none',
    letterSpacing: 0.35,
  },
  detailTitle: {
    color: UI.color.text,
    fontWeight: '700',
    letterSpacing: -0.35,
  },
  detailSubtitle: {
    color: UI.color.textMuted,
  },
  primaryButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accent,
  },
  primaryButtonText: {
    color: UI.color.accentInk,
    fontWeight: '700',
  },
  secondaryButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.borderStrong,
  },
  secondaryButtonText: {
    color: UI.color.text,
    fontWeight: '600',
  },
  ghostButton: {
    borderRadius: UI.radius.control,
    backgroundColor: 'transparent',
  },
  ghostButtonText: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  deleteButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.dangerSoft,
    borderColor: 'rgba(224, 120, 132, 0.38)',
  },
  deleteButtonText: {
    color: '#f3b5bd',
    fontWeight: '700',
  },
  tabRow: {
    gap: 4,
    borderBottomColor: UI.color.border,
  },
  tabButton: {
    borderRadius: UI.radius.control,
    backgroundColor: 'transparent',
  },
  tabButtonActive: {
    backgroundColor: UI.color.accentSoft,
    borderWidth: 1,
    borderColor: UI.color.accentBorder,
  },
  tabText: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  tabTextActive: {
    color: UI.color.accentStrong,
  },
  detailGrid: {
    gap: 1,
    borderRadius: UI.radius.panel,
    overflow: 'hidden',
    backgroundColor: UI.color.border,
  },
  infoCard: {
    borderRadius: 0,
    borderWidth: 0,
    backgroundColor: UI.color.surface,
  },
  infoLabel: {
    color: UI.color.textSubtle,
    fontWeight: '600',
    textTransform: 'none',
  },
  infoValue: {
    color: UI.color.textMuted,
  },
  timelineDot: {
    backgroundColor: UI.color.accent,
  },
  timelineBody: {
    borderBottomColor: UI.color.border,
  },
  timelineTitle: {
    color: UI.color.text,
    fontWeight: '600',
  },
  timelineMeta: {
    color: UI.color.textSubtle,
  },
  timelineText: {
    color: UI.color.textMuted,
  },
  runtimeRow: {
    borderRadius: UI.radius.control,
    borderColor: UI.color.border,
    backgroundColor: UI.color.surface,
  },
  runtimeTitle: {
    color: UI.color.text,
    fontWeight: '600',
  },
  runtimeMeta: {
    color: UI.color.textMuted,
  },
  errorText: {
    color: UI.color.danger,
  },
  codeLine: {
    color: UI.color.textMuted,
    fontFamily: WEB_MONO,
  },
  bulletText: {
    color: UI.color.textMuted,
  },
  textButtonText: {
    color: UI.color.accentStrong,
    fontWeight: '600',
  },
  textButtonDanger: {
    color: UI.color.danger,
    fontWeight: '600',
  },
  emptyPanel: {
    borderRadius: UI.radius.panel,
    borderColor: UI.color.border,
    backgroundColor: UI.color.surface,
  },
  emptyTitle: {
    color: UI.color.text,
    fontWeight: '700',
  },
  emptyText: {
    color: UI.color.textMuted,
  },
  fieldLabel: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  input: {
    borderRadius: UI.radius.control,
    borderColor: UI.color.borderStrong,
    backgroundColor: UI.color.canvas,
    color: UI.color.text,
  },
  generatedSchedule: {
    color: UI.color.accentStrong,
    fontWeight: '600',
  },
  segment: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 1,
    borderColor: UI.color.border,
  },
  segmentActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  segmentText: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  segmentTextActive: {
    color: UI.color.accentStrong,
  },
  compactChoice: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 1,
    borderColor: UI.color.border,
  },
  compactChoiceActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  compactChoiceText: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  compactChoiceTextActive: {
    color: UI.color.accentStrong,
  },
  choiceChip: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.border,
  },
  choiceChipActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  choiceChipText: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  choiceChipTextActive: {
    color: UI.color.accentStrong,
  },
  compactStat: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surface,
    borderColor: UI.color.border,
  },
  compactStatValue: {
    color: UI.color.text,
    fontWeight: '700',
  },
  compactStatLabel: {
    color: UI.color.textMuted,
  },
  quickTemplateButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 1,
    borderColor: UI.color.border,
  },
  quickTemplateText: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
});
