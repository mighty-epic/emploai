import type { DesktopConversationScope } from './DesktopConversationScope';
import { useEffect } from 'react'; type NativeSyntheticEvent<T = any> = any; type ActiveCommandPanel = any; type ActivityItem = any; type AgentOverview = any; type ArtifactDetail = any; type ArtifactSummary = any; type ComposerInputOrigin = any; type ConversationSurfaceMode = any; type DesktopFleetEnrollment = any; type DesktopFleetIdentity = any; type DesktopFleetSnapshot = any; type DesktopFleetTask = any; type DesktopFleetWorker = any; type DesktopGitRepoState = any; type DesktopMessage = any; type DesktopPathStatus = any; type DesktopRuntimeStatus = any; type DesktopSidebarProjectActivity = any; type DesktopSidebarState = any; type DesktopVoicePackState = any; type DesktopVoiceRuntimeStatus = any; type InterruptPolicy = any; type JarvisSttBackend = any; type JarvisTtsBackend = any; type LayoutChangeEvent = any; type MessageSourceFormat = any; type ModelProviderGroup = any; type NativeScrollEvent = any; type PendingSearchJump = any; type QueuedComposerMessage = any; type QueuedMessage = any; type RealtimeChannel = any; type RealtimeEvent = any; type ReferenceEntry = any; type RuntimeOrchestratorStatus = any; type ScheduledJob = any; type SearchResultTarget = any; type SecurityPermissionMode = any; type SessionDetail = any; type SessionMessage = any; type SessionSearchResult = any; type SessionSummary = any; type SessionTimelineEvent = any; type SidebarChatTooltipState = any; type SidebarDragState = any; type SidebarDraftChat = any; type SidebarProjectGroup = any; type StartupReadinessState = any; type TaskBoard = any; type TelegramBotConfig = any; type TextInputContentSizeChangeEventData = any; type ToolPackInfoPopupState = any; type VoiceCaptureMode = any; type VoiceGateState = any;

export function useDesktopConversationFleetEffects(scope: DesktopConversationScope) {
  const { SIDEBAR_REFRESH_MS, activeCommandPanel, clearSidebarChatTooltipTimer, clearToolPackInfoHideTimer, conversationMode, defaultInterruptPolicy, draftChat, fleetPanelOpen, hideSidebarChatTooltip, hideToolPackInfoPopup, normalizeInterruptPolicyValue, refreshFleetSnapshot, setActiveCommandPanel, setActivePermissionInfoId, setDraftBranchSearch, setDraftProjectSearch, setInterruptPolicy, sidebarExpanded, useEffect } = scope;
useEffect(() => {
    setInterruptPolicy(normalizeInterruptPolicyValue(defaultInterruptPolicy));
  }, [defaultInterruptPolicy]);

  useEffect(() => {
    if (!fleetPanelOpen && conversationMode !== 'fleet') {
      return;
    }
    void refreshFleetSnapshot();
    const intervalId = setInterval(() => {
      void refreshFleetSnapshot({ quiet: true });
    }, SIDEBAR_REFRESH_MS);
    return () => clearInterval(intervalId);
  }, [conversationMode, fleetPanelOpen]);

  useEffect(() => (
    () => {
      clearSidebarChatTooltipTimer();
      clearToolPackInfoHideTimer();
    }
  ), []);

  useEffect(() => {
    if (sidebarExpanded) {
      return;
    }
    clearSidebarChatTooltipTimer();
    hideSidebarChatTooltip();
  }, [sidebarExpanded]);

  useEffect(() => {
    if (activeCommandPanel?.kind === 'tools') {
      return;
    }
    hideToolPackInfoPopup();
  }, [activeCommandPanel]);

  useEffect(() => {
    if (activeCommandPanel?.kind === 'permissions') {
      return;
    }
    setActivePermissionInfoId(null);
  }, [activeCommandPanel]);

  useEffect(() => {
    if (
      draftChat
      || (
        activeCommandPanel?.kind !== 'draftBranch'
        && activeCommandPanel?.kind !== 'draftProject'
        && activeCommandPanel?.kind !== 'draftTelegram'
      )
    ) {
      return;
    }
    setActiveCommandPanel(null);
  }, [draftChat, activeCommandPanel]);

  useEffect(() => {
    if (activeCommandPanel?.kind !== 'draftProject') {
      setDraftProjectSearch('');
    }
    if (activeCommandPanel?.kind !== 'draftBranch') {
      setDraftBranchSearch('');
    }
  }, [activeCommandPanel]);
}
