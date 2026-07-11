import { Platform, StyleSheet } from 'react-native';

import { DESKTOP_UI as UI } from './desktopUiTokens';

const WEB_FONT = Platform.OS === 'web' ? UI.type.sans : undefined;
const WEB_MONO = Platform.OS === 'web' ? UI.type.mono : undefined;

// Jarvis keeps a distinctive instrument-panel composition while sharing the
// desktop product's palette, typography, surface, and control vocabulary.
export const desktopConversationJarvisVisualStyles = StyleSheet.create({
  surface: {
    backgroundColor: UI.color.canvas,
    color: UI.color.text,
    ...(Platform.OS === 'web'
      ? ({
          backgroundImage: 'radial-gradient(ellipse at 50% 44%, rgba(92,200,215,0.09), transparent 46%)',
          backgroundSize: '100% 100%',
        } as any)
      : null),
  },
  hudCorner: {
    borderColor: UI.color.borderStrong,
    opacity: 0.7,
  },
  topbar: {
    minHeight: 62,
    borderBottomColor: UI.color.border,
    paddingHorizontal: 32,
    paddingVertical: 16,
    backgroundColor: 'rgba(11, 17, 24, 0.72)',
  },
  systemDot: {
    backgroundColor: UI.color.accent,
    shadowColor: UI.color.accent,
    shadowOpacity: 0.28,
    shadowRadius: 6,
  },
  systemIdText: {
    color: UI.color.textMuted,
    fontFamily: WEB_MONO,
    fontWeight: '600',
    letterSpacing: 0.65,
  },
  systemRightText: {
    color: UI.color.textSubtle,
    fontFamily: WEB_MONO,
    letterSpacing: 0.45,
  },
  systemRightStrong: {
    color: UI.color.textMuted,
  },
  console: {
    paddingHorizontal: 32,
    gap: 22,
  },
  telemetry: {
    width: 216,
    gap: 20,
  },
  telemetryKey: {
    color: UI.color.textSubtle,
    fontFamily: WEB_MONO,
    fontWeight: '600',
    letterSpacing: 0.65,
  },
  telemetryValue: {
    color: UI.color.text,
    fontFamily: WEB_MONO,
    fontWeight: '500',
  },
  telemetryValueAccent: {
    color: UI.color.accentStrong,
  },
  telemetryDivider: {
    backgroundColor: UI.color.border,
  },
  sparkBar: {
    backgroundColor: UI.color.borderStrong,
  },
  sparkBarAccent: {
    backgroundColor: UI.color.accent,
  },
  controlStrip: {
    borderColor: UI.color.border,
    backgroundColor: UI.color.surfaceMuted,
    borderRadius: UI.radius.control,
  },
  controlStripHovered: {
    borderColor: UI.color.borderStrong,
    backgroundColor: UI.color.surfaceHover,
  },
  controlStripActive: {
    borderColor: UI.color.accentBorder,
    backgroundColor: UI.color.accentSoft,
  },
  controlStripValue: {
    color: UI.color.text,
    fontFamily: WEB_FONT,
    fontWeight: '600',
  },
  switchTrack: {
    borderColor: UI.color.borderStrong,
    backgroundColor: UI.color.canvas,
  },
  switchTrackActive: {
    borderColor: UI.color.accent,
    backgroundColor: UI.color.accentSoft,
  },
  switchKnob: {
    backgroundColor: UI.color.textSubtle,
  },
  switchKnobActive: {
    backgroundColor: UI.color.accentStrong,
  },
  ringOuter: {
    borderColor: UI.color.border,
  },
  tick: {
    backgroundColor: UI.color.border,
  },
  tickMedium: {
    backgroundColor: UI.color.borderStrong,
  },
  tickMajor: {
    backgroundColor: UI.color.textSubtle,
  },
  energySegment: {
    backgroundColor: UI.color.border,
  },
  energySegmentLit: {
    backgroundColor: UI.color.accent,
    shadowColor: UI.color.accent,
    shadowOpacity: 0.22,
    shadowRadius: 5,
  },
  ringDash: {
    borderColor: UI.color.borderStrong,
  },
  ringInnerLine: {
    borderColor: UI.color.border,
  },
  particle: {
    backgroundColor: UI.color.accentStrong,
    shadowColor: UI.color.accent,
    shadowOpacity: 0.36,
    shadowRadius: 5,
  },
  coreBloom: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
    shadowColor: UI.color.accent,
    shadowOpacity: 0.2,
    shadowRadius: 44,
  },
  coreShell: {
    borderColor: UI.color.accentBorder,
    backgroundColor: '#17343b',
    shadowColor: UI.color.accent,
    shadowOpacity: 0.22,
    shadowRadius: 34,
    ...(Platform.OS === 'web'
      ? ({
          backgroundImage: 'radial-gradient(circle at 38% 30%, #4b98a4, #24545d 42%, #102b32 76%, #0b1d22)',
        } as any)
      : null),
  },
  coreShellHovered: {
    borderColor: UI.color.accentStrong,
  },
  coreShellListening: {
    shadowOpacity: 0.34,
  },
  coreShellProcessing: {
    borderColor: UI.color.accentStrong,
  },
  coreShellMuted: {
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.borderStrong,
    shadowOpacity: 0.08,
  },
  coreShellError: {
    backgroundColor: '#442128',
    borderColor: UI.color.danger,
    shadowColor: UI.color.danger,
  },
  coreGlass: {
    ...(Platform.OS === 'web'
      ? ({
          backgroundImage: [
            'radial-gradient(circle at 38% 30%, rgba(255,255,255,0.26), rgba(255,255,255,0) 38%)',
            'radial-gradient(circle at 60% 72%, rgba(2,8,12,0.42), transparent 58%)',
          ].join(', '),
          mixBlendMode: 'screen',
        } as any)
      : null),
  },
  statusText: {
    color: UI.color.textMuted,
    fontFamily: WEB_FONT,
    fontWeight: '700',
    letterSpacing: 1.1,
  },
  statusTextAccent: {
    color: UI.color.accentStrong,
  },
  statusDetail: {
    color: UI.color.textSubtle,
    fontFamily: WEB_FONT,
  },
  waveBar: {
    backgroundColor: UI.color.textSubtle,
  },
  waveBarError: {
    backgroundColor: UI.color.danger,
  },
  drawerPanel: {
    width: '84%',
    maxWidth: 860,
    borderRadius: UI.radius.panel,
    borderColor: UI.color.border,
    backgroundColor: 'rgba(16, 23, 32, 0.96)',
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  drawerLabel: {
    color: UI.color.textSubtle,
    fontFamily: WEB_MONO,
    letterSpacing: 0.55,
  },
  drawerValue: {
    color: UI.color.text,
    fontFamily: WEB_FONT,
  },
  drawerHelper: {
    color: UI.color.textMuted,
    fontFamily: WEB_FONT,
  },
  engineButton: {
    borderRadius: UI.radius.control,
    borderColor: UI.color.border,
    backgroundColor: UI.color.surfaceMuted,
  },
  engineButtonHovered: {
    borderColor: UI.color.borderStrong,
    backgroundColor: UI.color.surfaceHover,
  },
  engineButtonActive: {
    borderColor: UI.color.accent,
    backgroundColor: UI.color.accent,
  },
  engineButtonText: {
    color: UI.color.textMuted,
    fontFamily: WEB_FONT,
    fontWeight: '600',
  },
  engineButtonTextActive: {
    color: UI.color.accentInk,
  },
  activityNotice: {
    borderRadius: UI.radius.control,
    borderColor: UI.color.accentBorder,
    backgroundColor: UI.color.accentSoft,
  },
  activityNoticeText: {
    color: UI.color.text,
    fontFamily: WEB_FONT,
  },
  activityDivider: {
    backgroundColor: UI.color.border,
  },
  activityText: {
    color: UI.color.textMuted,
    fontFamily: WEB_FONT,
  },
  activityEvent: {
    borderBottomColor: UI.color.border,
  },
  dock: {
    borderTopColor: UI.color.border,
    backgroundColor: 'rgba(11, 17, 24, 0.78)',
  },
  dockButton: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    borderColor: UI.color.border,
  },
  dockButtonPrimary: {
    backgroundColor: UI.color.accent,
    borderColor: UI.color.accentStrong,
  },
  dockButtonHovered: {
    backgroundColor: UI.color.surfaceHover,
    borderColor: UI.color.borderStrong,
  },
  dockButtonActive: {
    backgroundColor: UI.color.accentSoft,
    borderColor: UI.color.accentBorder,
  },
  dockTooltip: {
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceRaised,
    borderColor: UI.color.borderStrong,
    ...UI.elevation.low,
  },
  dockTooltipPrimary: {
    borderColor: UI.color.accentBorder,
  },
  dockTooltipText: {
    color: UI.color.text,
    fontFamily: WEB_FONT,
  },
  dockIcon: {
    color: UI.color.textMuted,
  },
  dockIconPrimary: {
    color: UI.color.accentInk,
  },
  dockText: {
    color: UI.color.textMuted,
    fontFamily: WEB_FONT,
    fontWeight: '600',
  },
  dockTextPrimary: {
    color: UI.color.accentInk,
  },
});
