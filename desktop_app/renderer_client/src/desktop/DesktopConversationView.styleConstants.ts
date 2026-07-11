import { DESKTOP_UI as UI } from './desktopUiTokens';

export const COMPOSER_MIN_LINES = 1;
export const COMPOSER_MAX_LINES = 8;
export const COMPOSER_LINE_HEIGHT = 22;
export const COMPOSER_MIN_HEIGHT = COMPOSER_MIN_LINES * COMPOSER_LINE_HEIGHT;
export const COMPOSER_MAX_HEIGHT = COMPOSER_MAX_LINES * COMPOSER_LINE_HEIGHT;

export const HUD = {
  cyan: UI.color.accent,
  cyanSoft: UI.color.accentStrong,
  cyanDim: UI.color.accentBorder,
  cyanFaint: UI.color.accentSoft,
  blue: UI.color.accent,
  panel: UI.color.surface,
  panelRaised: UI.color.surfaceRaised,
  panelGlass: 'rgba(16, 23, 32, 0.9)',
  edge: UI.color.accentBorder,
  magenta: UI.color.danger,
  amber: UI.color.warning,
};
