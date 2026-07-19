import { Platform, StyleSheet } from 'react-native';

import { DESKTOP_UI as UI } from './desktopUiTokens';

const WEB_FONT = Platform.OS === 'web' ? UI.type.sans : undefined;

// Visual-only refinements. Keeping these overrides separate makes it difficult
// for a presentation pass to accidentally alter shell behavior or routing.
export const desktopAppShellVisualStyles = StyleSheet.create({
  page: {
    backgroundColor: UI.color.canvas,
    fontFamily: WEB_FONT,
  },
  startupPage: {
    backgroundColor: UI.color.canvas,
  },
  startupGateCard: {
    borderRadius: UI.radius.large,
    backgroundColor: UI.color.surface,
    borderWidth: 0,
    ...UI.elevation.high,
  },
  startupGateTitle: {
    color: UI.color.text,
    fontWeight: '700',
    letterSpacing: -0.4,
  },
  startupGateText: {
    color: UI.color.textMuted,
  },
  startupHintText: {
    color: UI.color.textSubtle,
  },
  accountModeRow: {
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
    borderRadius: UI.radius.control,
  },
  accountModeButton: {
    borderRadius: UI.radius.small,
  },
  accountModeButtonActive: {
    backgroundColor: UI.color.accentSoft,
    borderWidth: 1,
    borderColor: UI.color.accentBorder,
  },
  accountModeText: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  accountModeTextActive: {
    color: UI.color.accentStrong,
  },
  accountInput: {
    borderRadius: UI.radius.control,
    borderColor: UI.color.borderStrong,
    backgroundColor: UI.color.surfaceMuted,
    color: UI.color.text,
  },
  accountPasswordInputRow: {
    borderRadius: UI.radius.control,
    borderColor: UI.color.borderStrong,
    backgroundColor: UI.color.surfaceMuted,
  },
  accountPeekButtonText: {
    color: UI.color.accentStrong,
    fontWeight: '700',
  },
  rememberBox: {
    borderRadius: UI.radius.small,
    borderColor: UI.color.borderStrong,
    backgroundColor: UI.color.surfaceMuted,
  },
  rememberBoxActive: {
    backgroundColor: UI.color.accent,
    borderColor: UI.color.accent,
  },
  startupPrimaryButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accent,
  },
  startupPrimaryButtonText: {
    color: UI.color.accentInk,
    fontWeight: '700',
  },
  startupSecondaryButton: {
    borderRadius: UI.radius.control,
    borderWidth: 0,
    backgroundColor: UI.color.surfaceRaised,
  },
  startupSecondaryButtonText: {
    color: UI.color.text,
    fontWeight: '600',
  },
  startupOverlay: {
    backgroundColor: UI.color.canvas,
  },
  skeletonShell: {
    backgroundColor: UI.color.canvas,
  },
  skeletonTranscript: {
    borderRadius: UI.radius.large,
    backgroundColor: UI.color.surface,
    borderWidth: 0,
  },
  startupGlyphCore: {
    backgroundColor: UI.color.surfaceRaised,
    borderColor: UI.color.borderStrong,
  },
  startupGlyphOrbit: {
    borderColor: UI.color.borderStrong,
  },
  startupGlyphDot: {
    backgroundColor: UI.color.accent,
  },
  windowChromeBar: {
    backgroundColor: UI.color.chrome,
    borderBottomColor: UI.color.border,
  },
  windowChromeIconButton: {
    borderRadius: UI.radius.small,
  },
  windowChromeButtonHovered: {
    backgroundColor: UI.color.surfaceHover,
    borderColor: 'transparent',
  },
  windowChromeIconText: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  windowChromeMenuButton: {
    borderRadius: UI.radius.small,
  },
  windowChromeMenuButtonHovered: {
    backgroundColor: UI.color.surfaceHover,
  },
  windowChromeMenuText: {
    color: UI.color.textMuted,
  },
  windowChromeUpdateButton: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  windowChromeUpdateText: {
    color: UI.color.accentStrong,
  },
  headerSurfaceTabs: {
    borderRadius: UI.radius.small,
    backgroundColor: 'transparent',
    borderWidth: 0,
  },
  headerSurfaceTab: {
    borderRadius: UI.radius.small,
  },
  headerSurfaceTabHovered: {
    backgroundColor: UI.color.surfaceHover,
  },
  headerSurfaceTabActive: {
    backgroundColor: UI.color.surfaceRaised,
    borderWidth: 0,
  },
  headerSurfaceTabText: {
    color: UI.color.textMuted,
    fontWeight: '600',
  },
  headerSurfaceTabTextActive: {
    color: UI.color.accentStrong,
  },
  headerIdentityStopButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.dangerSoft,
    borderColor: 'rgba(224, 120, 132, 0.44)',
  },
  headerIdentityStopButtonHovered: {
    backgroundColor: 'rgba(224, 120, 132, 0.2)',
    borderColor: UI.color.danger,
  },
  headerIdentityStopText: {
    color: '#f3b5bd',
  },
  windowChromeStartButton: {
    backgroundColor: UI.color.successSoft,
    borderColor: 'rgba(117, 198, 154, 0.32)',
  },
  windowChromeStopButtonActive: {
    backgroundColor: UI.color.dangerSoft,
    borderColor: 'rgba(224, 120, 132, 0.4)',
  },
  headerBar: {
    backgroundColor: UI.color.sidebar,
    borderBottomColor: UI.color.border,
  },
  headerTitle: {
    color: UI.color.text,
    fontWeight: '700',
    letterSpacing: -0.15,
  },
  headerMeta: {
    color: UI.color.textSubtle,
  },
  headerSession: {
    color: UI.color.textSubtle,
  },
  headerVersion: {
    color: UI.color.textSubtle,
  },
  headerIconButton: {
    borderRadius: UI.radius.control,
    borderWidth: 0,
    backgroundColor: 'transparent',
  },
  headerIconButtonHovered: {
    borderColor: UI.color.accentBorder,
    backgroundColor: UI.color.surfaceHover,
  },
  headerUpdateButton: {
    backgroundColor: UI.color.accent,
    borderColor: UI.color.accentStrong,
  },
  headerActionButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accent,
  },
  headerActionPrimary: {
    backgroundColor: UI.color.accent,
  },
  headerActionWarn: {
    backgroundColor: UI.color.dangerSoft,
    borderWidth: 0,
  },
  headerActionText: {
    color: UI.color.accentInk,
    fontWeight: '700',
  },
  headerSettingsButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  headerSettingsButtonHovered: {
    backgroundColor: UI.color.surfaceHover,
    borderColor: UI.color.borderStrong,
  },
  headerSettingsButtonActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  headerSettingsGlyph: {
    color: UI.color.textMuted,
  },
  headerSettingsText: {
    color: UI.color.text,
    fontWeight: '600',
  },
  accountMenuPopover: {
    borderRadius: UI.radius.panel,
    borderColor: UI.color.borderStrong,
    backgroundColor: UI.color.surfaceRaised,
    ...UI.elevation.high,
  },
  controlsButtonActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  controlsButtonTextActive: {
    color: UI.color.accentStrong,
  },
  controlsUpdateButton: {
    backgroundColor: UI.color.accent,
    borderColor: UI.color.accentStrong,
  },
  controlsUpdateButtonText: {
    color: UI.color.accentInk,
  },
  loadingTitle: {
    color: UI.color.text,
    fontWeight: '700',
  },
  loadingText: {
    color: UI.color.textMuted,
  },
  offlineMetaCard: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  offlineMetaLabel: {
    color: UI.color.textSubtle,
  },
  offlineMetaValue: {
    color: UI.color.text,
    fontWeight: '700',
  },
  offlineMetaText: {
    color: UI.color.textMuted,
  },
  runtimeButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accent,
  },
  runtimeButtonText: {
    color: UI.color.accentInk,
    fontWeight: '700',
  },
  secondaryRuntimeButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceRaised,
    borderWidth: 0,
  },
  secondaryRuntimeButtonText: {
    color: UI.color.text,
    fontWeight: '600',
  },
  remoteBody: {
    gap: 12,
    padding: 18,
    backgroundColor: UI.color.canvas,
  },
  remoteIntro: {
    borderRadius: 0,
    backgroundColor: 'transparent',
    borderWidth: 0,
    paddingHorizontal: 2,
    paddingVertical: 8,
  },
  remoteIntroTitle: {
    color: UI.color.text,
    fontWeight: '700',
    letterSpacing: -0.3,
  },
  remoteIntroText: {
    color: UI.color.textMuted,
  },
  remotePrimaryButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accent,
  },
  remotePrimaryButtonText: {
    color: UI.color.accentInk,
    fontWeight: '700',
  },
  remoteSecondaryButton: {
    borderRadius: UI.radius.control,
    borderWidth: 0,
    backgroundColor: UI.color.surfaceMuted,
  },
  remoteSecondaryButtonText: {
    color: UI.color.text,
    fontWeight: '600',
  },
  remoteEnrollment: {
    borderRadius: UI.radius.control,
    borderColor: UI.color.accentBorder,
    backgroundColor: UI.color.accentSoft,
  },
  remoteEnrollmentLabel: {
    color: UI.color.textSubtle,
  },
  remoteEnrollmentCode: {
    color: UI.color.accentStrong,
    fontFamily: Platform.OS === 'web' ? UI.type.mono : undefined,
  },
  remoteEmpty: {
    borderWidth: 0,
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surfaceMuted,
  },
  remoteCard: {
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
    paddingHorizontal: 18,
    paddingVertical: 15,
    gap: 10,
  },
  remoteTitle: {
    color: UI.color.text,
    fontWeight: '700',
  },
  remoteMeta: {
    color: UI.color.textSubtle,
  },
  remoteStatusBadge: {
    borderRadius: UI.radius.small,
    backgroundColor: UI.color.accentSoft,
    borderWidth: 0,
  },
  remoteStatusText: {
    color: UI.color.accentStrong,
    fontWeight: '700',
    textTransform: 'none',
  },
  remoteDetail: {
    color: UI.color.textMuted,
  },
  remoteReport: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.canvas,
    borderWidth: 0,
  },
  remoteSectionLabel: {
    color: UI.color.textSubtle,
    letterSpacing: 0.35,
  },
  remoteWorker: {
    borderTopColor: UI.color.border,
  },
  remoteWorkerName: {
    color: UI.color.text,
  },
  remotePreviewButton: {
    borderRadius: UI.radius.control,
    borderWidth: 0,
    backgroundColor: UI.color.surfaceMuted,
  },
  remotePreviewPanel: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderWidth: 0,
  },
  remotePreviewImage: {
    backgroundColor: UI.color.canvas,
  },
  remoteErrorText: {
    color: '#f0a3ad',
  },
});
