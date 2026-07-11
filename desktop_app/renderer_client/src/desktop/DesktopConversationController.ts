import { useState } from 'react';
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
  const [pendingRunMode, setPendingRunMode] = useState<'normal' | 'plan' | 'goal' | null>(null);
  const [planMode, setPlanMode] = useState<Record<string, any> | null>(null);
  const [activeGoal, setActiveGoal] = useState<Record<string, any> | null>(null);
  const [fleetPreview, setFleetPreview] = useState<Record<string, any> | null>(null);
  const [providerFailure, setProviderFailure] = useState<Record<string, any> | null>(null);
  const [archiveUndo, setArchiveUndo] = useState<Record<string, any> | null>(null);
  scope.pendingRunMode = pendingRunMode;
  scope.setPendingRunMode = setPendingRunMode;
  scope.planMode = planMode;
  scope.setPlanMode = setPlanMode;
  scope.activeGoal = activeGoal;
  scope.setActiveGoal = setActiveGoal;
  scope.fleetPreview = fleetPreview;
  scope.setFleetPreview = setFleetPreview;
  scope.providerFailure = providerFailure;
  scope.setProviderFailure = setProviderFailure;
  scope.archiveUndo = archiveUndo;
  scope.setArchiveUndo = setArchiveUndo;
  Object.assign(scope, useDesktopConversationFleetActions(scope));
  Object.assign(scope, useDesktopConversationSessionControls(scope));
  useDesktopConversationFleetEffects(scope);
  Object.assign(scope, useDesktopConversationSyncControls(scope));
  Object.assign(scope, useDesktopConversationDerivedValues(scope));
  Object.assign(scope, useDesktopConversationVoiceControls(scope));
  Object.assign(scope, useDesktopConversationDerivedTail(scope));
  return scope;
}
