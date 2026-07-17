import type { DesktopConversationScope } from './DesktopConversationScope';
import { useEffect } from 'react'; type NativeSyntheticEvent<T = any> = any; type ActiveCommandPanel = any; type ActivityItem = any; type AgentOverview = any; type ArtifactDetail = any; type ArtifactSummary = any; type ComposerInputOrigin = any; type ConversationSurfaceMode = any; type DesktopFleetEnrollment = any; type DesktopFleetIdentity = any; type DesktopFleetSnapshot = any; type DesktopFleetTask = any; type DesktopFleetWorker = any; type DesktopGitRepoState = any; type DesktopMessage = any; type DesktopPathStatus = any; type DesktopRuntimeStatus = any; type DesktopSidebarProjectActivity = any; type DesktopSidebarState = any; type DesktopVoicePackState = any; type DesktopVoiceRuntimeStatus = any; type InterruptPolicy = any; type JarvisSttBackend = any; type JarvisTtsBackend = any; type LayoutChangeEvent = any; type MessageSourceFormat = any; type ModelProviderGroup = any; type NativeScrollEvent = any; type PendingSearchJump = any; type QueuedComposerMessage = any; type QueuedMessage = any; type RealtimeChannel = any; type RealtimeEvent = any; type ReferenceEntry = any; type RuntimeOrchestratorStatus = any; type ScheduledJob = any; type SearchResultTarget = any; type SecurityPermissionMode = any; type SessionDetail = any; type SessionMessage = any; type SessionSearchResult = any; type SessionSummary = any; type SessionTimelineEvent = any; type SidebarChatTooltipState = any; type SidebarDragState = any; type SidebarDraftChat = any; type SidebarProjectGroup = any; type StartupReadinessState = any; type TaskBoard = any; type TelegramBotConfig = any; type TextInputContentSizeChangeEventData = any; type ToolPackInfoPopupState = any; type VoiceCaptureMode = any; type VoiceGateState = any;
import {
  configureDesktopFleetPreviewScheduler,
  stopDesktopFleetPreviewScheduler,
} from './desktopFleetPreviewScheduler';

const FLEET_ACTIVE_REFRESH_MS = 5000;
const FLEET_BACKGROUND_REFRESH_MS = 120000;

export function useDesktopConversationFleetEffects(scope: DesktopConversationScope) {
  const { activeCommandPanel, clearSidebarChatTooltipTimer, clearToolPackInfoHideTimer, conversationMode, defaultInterruptPolicy, draftChat, fleetSnapshot, hideSidebarChatTooltip, hideToolPackInfoPopup, normalizeInterruptPolicyValue, refreshFleetSnapshot, setActiveCommandPanel, setActivePermissionInfoId, setDraftBranchSearch, setDraftProjectSearch, setInterruptPolicy, sidebarExpanded, useEffect } = scope;
useEffect(() => {
    setInterruptPolicy(normalizeInterruptPolicyValue(defaultInterruptPolicy));
  }, [defaultInterruptPolicy]);

  useEffect(() => {
    let disposed = false;
    let inFlight = false;
    const refreshIntervalMs = conversationMode === 'fleet'
      ? FLEET_ACTIVE_REFRESH_MS
      : FLEET_BACKGROUND_REFRESH_MS;
    const runRefresh = async (quiet = true) => {
      if (inFlight || disposed) {
        return;
      }
      inFlight = true;
      try {
        await refreshFleetSnapshot({ quiet });
      } finally {
        inFlight = false;
      }
    };
    void runRefresh(conversationMode !== 'fleet');
    const intervalId = setInterval(() => {
      void runRefresh(true);
    }, refreshIntervalMs);
    return () => {
      disposed = true;
      clearInterval(intervalId);
    };
  }, [conversationMode]);

  useEffect(() => {
    configureDesktopFleetPreviewScheduler(fleetSnapshot, conversationMode === 'fleet');
  }, [conversationMode, fleetSnapshot]);

  useEffect(() => () => stopDesktopFleetPreviewScheduler(), []);

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
