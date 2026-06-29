import type { DesktopConversationScope } from './DesktopConversationScope';
import { useDesktopConversationDerivedTail } from './DesktopConversationDerivedTail';
import { useDesktopConversationDerivedValues } from './DesktopConversationDerivedValues';
import { useDesktopConversationFleetActions } from './DesktopConversationFleetActions';
import { useDesktopConversationFleetEffects } from './DesktopConversationFleetEffects';
import { useDesktopConversationSessionControls } from './DesktopConversationSessionControls';
import { useDesktopConversationSyncControls } from './DesktopConversationSyncControls';
import { useDesktopConversationVoiceControls } from './DesktopConversationVoiceControls';

export function useDesktopConversationController(baseScope: DesktopConversationScope) {
  const scope: DesktopConversationScope = { ...baseScope };
  Object.assign(scope, useDesktopConversationFleetActions(scope));
  Object.assign(scope, useDesktopConversationSessionControls(scope));
  useDesktopConversationFleetEffects(scope);
  Object.assign(scope, useDesktopConversationSyncControls(scope));
  Object.assign(scope, useDesktopConversationDerivedValues(scope));
  Object.assign(scope, useDesktopConversationVoiceControls(scope));
  Object.assign(scope, useDesktopConversationDerivedTail(scope));
  return scope;
}
