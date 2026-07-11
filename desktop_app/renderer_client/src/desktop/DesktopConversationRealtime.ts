import type { DesktopConversationScope } from './DesktopConversationScope';
import type {
  ArtifactSummary,
  SessionDetail,
  SessionMessage,
  SessionTimelineEvent,
  TaskBoard,
} from '@/lib/appApi';
import type { DesktopFleetSnapshot } from '@/lib/desktopBridge';
import { composeVoiceDraftInput } from '@/desktop/desktopVoicePolicy';
import type { DesktopRealtimeEvent, RealtimeChannel } from './desktopRealtimeProtocol';

type DesktopConversationRealtimeContext = DesktopConversationScope;

const realtimeVoiceSetupMessage = 'Realtime voice needs a valid OpenAI API key. Add or replace OPENAI_API_KEY in Settings, or switch Jarvis input to Local Whisper or Gemini.';

function isTerminalVoiceSetupError(message: string) {
  const normalized = String(message || '').toLowerCase();
  return (
    normalized.includes('invalid api key')
    || normalized.includes('error.invalid api key')
    || normalized.includes('openai_api_key is not configured')
    || normalized.includes('openai_api_key is required')
  );
}

export function handleDesktopConversationRealtimeEvent(
  context: DesktopConversationRealtimeContext,
  event: DesktopRealtimeEvent,
  channel: RealtimeChannel,
) {
    const { acceptJarvisBargeInTranscript, activeVoiceUtteranceIdRef, alwaysOnEnabledRef, appendLocalSystemMessage, appendTimelineEvent, appendVoiceTranscriptSegment, applySessionSync, artifacts, assistantDeltaBufferRef, assistantDeltaFlushTimerRef, clearAssistantDeltaFlushTimer, clearConversationSelection, clearJarvisBargeInCandidate, conversationModeRef, createLocalToolTimelineEvent, drainDeferredAlwaysOnFrames, flushAssistantDeltaBuffer, id, lastComposerInputOriginRef, normalizeCompletedTaskBoards, playAssistantAudio, pushActivity, refreshOverviewState, refreshSidebarCollections, refreshSidebarState, remoteAuthStatus, resolveTaskBoardState, run_state, selectedArtifactId, sessionIdRef, setArtifacts, setAssistantDraft, setChatRunActive, setCompletedTaskBoards, setComposerInputValue, setFleetError, setFleetSnapshot, setFleetStatus, setInput, setJarvisLatestTranscript, setLastAssistantOutputAt, setMessages, setOverview, setRuntimeRunState, setSelectedArtifactId, setSessionId, setSocketState, setStatus, setTaskBoard, setTaskBoardArmedNextTurnState, setThinking, setVoiceDraft, setVoiceError, setVoiceRecording, setVoiceRunning, setVoiceState, shouldAutoSendAlwaysOnVoice, status, summarizeToolPayload, toLiveDesktopMessage, voiceComposerBaseInputRef, voiceComposerDraftRef, voiceRecordingRef, voiceRunningRef } = context;
    const payload = (event.payload || {}) as Record<string, any>;
    const payloadTurnId = typeof payload.turn_id === 'string' ? payload.turn_id.trim() : '';
    const incomingSessionId = typeof event.session_id === 'string' ? event.session_id.trim() : '';
    const selectedSessionId = String(sessionIdRef.current || '').trim();
    const eventTargetsSelectedSession = !incomingSessionId || Boolean(selectedSessionId && incomingSessionId === selectedSessionId);
    const refreshNonSelectedSession = () => {
      if (incomingSessionId) {
        void refreshSidebarCollections(incomingSessionId, true);
      }
    };
    const ignoreIfNotSelectedSession = () => {
      if (eventTargetsSelectedSession) {
        return false;
      }
      refreshNonSelectedSession();
      return true;
    };
    const shouldPreserveCurrentJarvisRecording = () => {
      const activeTurnId = activeVoiceUtteranceIdRef.current;
      return (
        conversationModeRef.current === 'jarvis'
        && Boolean(activeTurnId)
        && (!payloadTurnId || payloadTurnId !== activeTurnId)
      );
    };
    const normalizeFleetSnapshotManagers = (snapshot: DesktopFleetSnapshot): DesktopFleetSnapshot => {
      const currentDesktopId = String(
        remoteAuthStatus?.desktop?.desktop_id
        || snapshot.manager?.desktop_id
        || '',
      ).trim();
      if (!currentDesktopId) {
        return snapshot;
      }
      const managerFilter = (item: any) => (
        String(item?.role || '').toLowerCase() !== 'manager'
        || String(item?.desktop_id || '').trim() === currentDesktopId
      );
      const identities = Array.isArray(snapshot.identities) ? snapshot.identities.filter(managerFilter) : [];
      const instances = Array.isArray(snapshot.instances) ? snapshot.instances.filter(managerFilter) : [];
      const snapshotManagerDesktopId = String(snapshot.manager?.desktop_id || '').trim();
      const snapshotManager = (!snapshotManagerDesktopId || snapshotManagerDesktopId === currentDesktopId)
        ? snapshot.manager
        : null;
      const currentManager: any = (
        instances.find((item: any) => String(item?.role || '').toLowerCase() === 'manager')
        || identities.find((item: any) => String(item?.role || '').toLowerCase() === 'manager')
        || snapshotManager
        || null
      );
      const visibleIdentityIds = new Set(identities.map((item: any) => String(item?.identity_id || '').trim()).filter(Boolean));
      const selectedChatByIdentity = Object.fromEntries(
        Object.entries(snapshot.selected_chat_by_identity || {})
          .filter(([identityId]) => visibleIdentityIds.has(String(identityId || '').trim())),
      );
      const activeIdentityVisible = snapshot.active_identity?.identity_id
        && visibleIdentityIds.has(String(snapshot.active_identity.identity_id));
      const activeIdentity: any = activeIdentityVisible
        ? snapshot.active_identity
        : identities.find((item: any) => String(item?.identity_id || '') === String(currentManager?.identity_id || currentManager?.instance_id || ''))
          || currentManager
          || identities[0]
          || null;
      return {
        ...snapshot,
        identities,
        instances,
        manager: currentManager,
        active_identity: activeIdentity,
        active_identity_id: activeIdentity?.identity_id || activeIdentity?.instance_id || null,
        selected_chat_by_identity: selectedChatByIdentity,
      };
    };

    if (event.type.startsWith('fleet_')) {
      const snapshot = payload.snapshot as DesktopFleetSnapshot | undefined;
      if (snapshot && Array.isArray(snapshot.workers)) {
        const normalizedSnapshot = normalizeFleetSnapshotManagers(snapshot);
        setFleetSnapshot(normalizedSnapshot);
        setFleetError(null);
        setFleetStatus(normalizedSnapshot.workers.length ? `${normalizedSnapshot.workers.length} worker${normalizedSnapshot.workers.length === 1 ? '' : 's'} linked` : 'No workers yet');
      }
      if (
        event.type === 'fleet_identity_changed'
        || event.type === 'fleet_task_assigned'
        || event.type === 'fleet_queue_updated'
        || event.type === 'fleet_task_report'
        || event.type === 'fleet_worker_presence'
      ) {
        void refreshSidebarCollections(sessionIdRef.current, true);
      }
      return;
    }

    if (event.type === 'session_snapshot') {
      setSocketState('connected');
      if (!eventTargetsSelectedSession) {
        refreshNonSelectedSession();
        return;
      }
      if (incomingSessionId && !selectedSessionId) {
        setSessionId(incomingSessionId);
      }
      setChatRunActive(false);
      setLastAssistantOutputAt(null);
      setStatus('ready');
      return;
    }

    if (event.type === 'session_sync') {
      const syncDetail = payload.session as SessionDetail | undefined;
      const syncSessionId = String(syncDetail?.id || '').trim();
      if (syncSessionId && selectedSessionId && syncSessionId !== selectedSessionId) {
        refreshNonSelectedSession();
        return;
      }
      applySessionSync(payload);
      setStatus('ready');
      return;
    }

    if (event.type === 'session_config') {
      if (ignoreIfNotSelectedSession()) return;
      setOverview((previous: any) => (
        previous
          ? {
              ...previous,
              current_model: String(payload.model || previous.current_model || ''),
              current_variant: String(payload.variant || previous.current_variant || ''),
              planner_model: payload.planner_model ?? null,
              max_turns: typeof payload.max_turns === 'number' ? payload.max_turns : previous.max_turns,
              auto_reply_enabled: typeof payload.auto_reply_enabled === 'boolean'
                ? payload.auto_reply_enabled
                : previous.auto_reply_enabled,
              verbose_mode: typeof payload.verbose_mode === 'boolean'
                ? payload.verbose_mode
                : previous.verbose_mode,
              bridge_enabled: typeof payload.bridge_enabled === 'boolean'
                ? payload.bridge_enabled
                : previous.bridge_enabled,
              headless_mode: payload.headless_mode || previous.headless_mode,
              enabled_tool_packs: Array.isArray(payload.enabled_tool_packs)
                ? payload.enabled_tool_packs
                : previous.enabled_tool_packs,
            }
          : previous
      ));
      return;
    }

    if (event.type === 'user_message') {
      if (ignoreIfNotSelectedSession()) return;
      const message = payload.message as SessionMessage | undefined;
      if (message) {
        setMessages((previous: any) => [...previous, toLiveDesktopMessage(message, previous)]);
      }
      return;
    }

    if (event.type === 'assistant_delta') {
      if (ignoreIfNotSelectedSession()) return;
      setChatRunActive(true);
      setRuntimeRunState('running');
      setLastAssistantOutputAt(Date.now());
      assistantDeltaBufferRef.current += String(payload.delta || '');
      if (!assistantDeltaFlushTimerRef.current) {
        assistantDeltaFlushTimerRef.current = setTimeout(() => {
          flushAssistantDeltaBuffer();
        }, 40);
      }
      setOverview((previous: any) => (
        previous
          ? {
              ...previous,
              run_state: 'running',
            }
          : previous
      ));
      if (channel === 'voice') {
        setVoiceRunning(true);
      }
      return;
    }

    if (event.type === 'assistant_final') {
      if (ignoreIfNotSelectedSession()) return;
      context.setProviderFailure?.(null);
      const finalText = String(payload.text || '');
      const message = payload.message as SessionMessage | undefined;
      assistantDeltaBufferRef.current = '';
      clearAssistantDeltaFlushTimer();
      setAssistantDraft('');
      setThinking('');
      setLastAssistantOutputAt(Date.now());
      if (channel === 'voice') {
        voiceRunningRef.current = false;
        setVoiceRunning(false);
        if (!shouldPreserveCurrentJarvisRecording()) {
          voiceRecordingRef.current = false;
          setVoiceRecording(false);
        }
      }
      if (message) {
        setMessages((previous: any) => [
          ...previous,
          toLiveDesktopMessage(message, previous),
        ]);
      } else if (finalText.trim()) {
        setMessages((previous: any) => [
          ...previous,
          {
            role: 'assistant',
            content: finalText,
            timestamp: new Date().toISOString(),
            displayLabel: 'Assistant',
            channel: 'app',
            sourceFormat: 'app_text',
            messageKey: `assistant:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
          },
        ]);
      }
      setChatRunActive(false);
      setRuntimeRunState('idle');
      setOverview((previous: any) => (
        previous
          ? {
              ...previous,
              run_state: 'idle',
            }
          : previous
      ));
      setStatus('ready');
      void refreshSidebarCollections(event.session_id || sessionIdRef.current, true);
      void refreshOverviewState(event.session_id || sessionIdRef.current, { quiet: true });
      return;
    }

    if (event.type === 'run_failed') {
      if (ignoreIfNotSelectedSession()) return;
      context.setProviderFailure?.(payload);
      const message = String(payload.user_message || 'The selected provider could not complete this turn.');
      setAssistantDraft('');
      setThinking('');
      setChatRunActive(false);
      setRuntimeRunState('idle');
      setStatus(`Provider blocked · ${message}`);
      setOverview((previous: any) => (
        previous ? { ...previous, run_state: 'idle', provider_blocked: payload } : previous
      ));
      pushActivity(message, 'error');
      return;
    }

    if (event.type === 'assistant_audio') {
      if (ignoreIfNotSelectedSession()) return;
      void playAssistantAudio(
        String(payload.audio_base64 || ''),
        String(payload.mime_type || 'audio/mpeg'),
        String(payload.text || ''),
      );
      return;
    }

    if (event.type === 'voice_confirmation_required') {
      if (ignoreIfNotSelectedSession()) return;
      const action = String(payload.action || payload.tool_name || 'action');
      const summary = String(payload.summary || payload.spoken_prompt || '').trim();
      setStatus(`Jarvis needs confirmation for ${action}`);
      pushActivity(summary || `Jarvis needs yes or no confirmation for ${action}.`, 'warn');
      return;
    }

    if (event.type === 'thinking') {
      if (ignoreIfNotSelectedSession()) return;
      setChatRunActive(true);
      setRuntimeRunState('running');
      setThinking(String(payload.formatted || payload.text || ''));
      setOverview((previous: any) => (
        previous
          ? {
              ...previous,
              run_state: 'running',
            }
          : previous
      ));
      return;
    }

    if (event.type === 'tool_event') {
      if (ignoreIfNotSelectedSession()) return;
      setChatRunActive(true);
      setRuntimeRunState('running');
      setOverview((previous: any) => (
        previous
          ? {
              ...previous,
              run_state: 'running',
            }
          : previous
      ));
      const toolTimelineEvent = createLocalToolTimelineEvent(payload);
      if (toolTimelineEvent) {
        appendTimelineEvent(toolTimelineEvent);
      }
      pushActivity(summarizeToolPayload(payload), 'accent');
      return;
    }

    if (event.type === 'artifact_created') {
      if (ignoreIfNotSelectedSession()) return;
      const created = Array.isArray(payload.artifacts) ? payload.artifacts as ArtifactSummary[] : [];
      if (created.length > 0) {
        setArtifacts((previous: any) => {
          const seen = new Set(previous.map((item: any) => item.artifact_id));
          const merged = [...created.filter((item: any) => !seen.has(item.artifact_id)), ...previous];
          return merged.sort((left: any, right: any) => String(right.created_at || '').localeCompare(String(left.created_at || '')));
        });
        if (!selectedArtifactId) {
          setSelectedArtifactId(created[0].artifact_id);
        }
      }
      return;
    }

    if (event.type === 'timeline_event') {
      if (ignoreIfNotSelectedSession()) return;
      const timelineEvent = (payload.event as SessionTimelineEvent | undefined) ?? null;
      if (timelineEvent) {
        appendTimelineEvent(timelineEvent);
      }
      return;
    }

    if (event.type === 'task_board') {
      if (ignoreIfNotSelectedSession()) return;
      const board = (payload.board as TaskBoard | null | undefined) ?? null;
      const completedBoards = normalizeCompletedTaskBoards(payload.completed_task_boards as TaskBoard[] | undefined);
      const summary = String(payload.summary || '').trim();
      const eventSessionId = event.session_id || sessionIdRef.current;
      setTaskBoard(resolveTaskBoardState(board, eventSessionId, sessionIdRef.current));
      setCompletedTaskBoards(completedBoards);
      if (board?.status === 'active') {
        setTaskBoardArmedNextTurnState(false);
      }
      setOverview((previous: any) => (
        previous
          ? {
              ...previous,
              task_board: resolveTaskBoardState(board, eventSessionId, sessionIdRef.current),
              completed_task_boards: completedBoards,
              task_board_armed_next_turn: board?.status === 'active'
                ? false
                : previous.task_board_armed_next_turn,
            }
          : previous
      ));
      if (summary) {
        const tone = board?.status === 'blocked' || board?.pending_reassessment_reason
          ? 'warn'
          : board?.status === 'completed'
            ? 'accent'
            : 'neutral';
        pushActivity(`Task board: ${summary}`, tone);
      }
      return;
    }

    if (event.type === 'current_session_changed') {
      const rawCurrentSessionId = payload.current_session_id;
      const currentSessionKnown = rawCurrentSessionId === null || rawCurrentSessionId === undefined
        ? null
        : String(rawCurrentSessionId || '').trim();
      const nextSessionId = currentSessionKnown !== null
        ? (currentSessionKnown || null)
        : event.session_id || sessionIdRef.current;
      void refreshSidebarCollections(nextSessionId, true);
      return;
    }

    if (event.type === 'log') {
      if (ignoreIfNotSelectedSession()) return;
      const message = String(payload.message || '');
      const tone = payload.level === 'error' ? 'error' : payload.level === 'warn' ? 'warn' : 'neutral';
      pushActivity(message, tone);
      return;
    }

    if (event.type === 'status') {
      if (ignoreIfNotSelectedSession()) return;
      const message = String(payload.message || event.message || '');
      const runState = payload.run_state === 'running'
        ? 'running'
        : payload.run_state === 'idle'
          ? 'idle'
          : message === 'running'
            ? 'running'
            : message === 'ready'
              ? 'idle'
              : null;
      if (runState) {
        setRuntimeRunState(runState);
        setChatRunActive(runState === 'running');
        if (runState === 'idle') {
          setAssistantDraft('');
          setThinking('');
          setLastAssistantOutputAt(null);
        }
        setOverview((previous: any) => (
          previous
            ? {
                ...previous,
                run_state: runState,
              }
            : previous
        ));
      }
      if (message) {
        if (message === 'ready') {
          setChatRunActive(false);
        }
        setStatus(message);
        pushActivity(message, 'neutral');
      }
      return;
    }

    if (event.type === 'warning') {
      if (ignoreIfNotSelectedSession()) return;
      const message = String(payload.message || event.message || 'warning');
      if (String(payload.code || '') === 'session_unavailable') {
        clearConversationSelection(null, { clearSidebarProject: false });
        void refreshSidebarState(null, true);
        setStatus('chat was no longer available · start a new message');
        pushActivity(message, 'warn');
        return;
      }
      clearJarvisBargeInCandidate(payloadTurnId);
      setStatus(message);
      setAssistantDraft('');
      setThinking('');
      if (channel === 'voice') {
        voiceRunningRef.current = false;
        setVoiceRunning(false);
        if (!shouldPreserveCurrentJarvisRecording()) {
          voiceRecordingRef.current = false;
          setVoiceRecording(false);
        }
      }
      setChatRunActive(false);
      setRuntimeRunState('idle');
      setLastAssistantOutputAt(null);
      setOverview((previous: any) => (
        previous
          ? {
              ...previous,
              run_state: 'idle',
            }
          : previous
      ));
      void refreshSidebarCollections(event.session_id || sessionIdRef.current, true);
      if (channel === 'chat') {
        appendLocalSystemMessage(message, 'Warning');
      }
      pushActivity(message, 'warn');
      return;
    }

    if (event.type === 'error') {
      if (ignoreIfNotSelectedSession()) return;
      const rawMessage = String(payload.message || event.message || 'runtime error');
      const terminalVoiceSetupError = channel === 'voice' && isTerminalVoiceSetupError(rawMessage);
      const message = terminalVoiceSetupError ? realtimeVoiceSetupMessage : rawMessage;
      if (String(payload.code || '') === 'session_unavailable') {
        clearConversationSelection(null, { clearSidebarProject: false });
        void refreshSidebarState(null, true);
        setStatus('chat was no longer available · start a new message');
        pushActivity(message, 'warn');
        return;
      }
      clearJarvisBargeInCandidate(payloadTurnId);
      if (terminalVoiceSetupError) {
        alwaysOnEnabledRef.current = false;
        context.setAlwaysOnEnabled?.(false);
        context.voicePressActiveRef.current = false;
        context.stopVoiceTracks?.();
        context.resetVoiceCaptureBuffers?.();
        context.setJarvisMuted?.(true);
        context.setVoiceMode?.('push_to_talk');
        context.setLiveVoiceStatus?.((previous: any) => ({
          ...(previous || {}),
          ok: false,
          input_ok: false,
          issues: [message],
          selected_engine_state: 'error',
        }));
      }
      setStatus(message);
      setAssistantDraft('');
      setThinking('');
      if (channel === 'voice') {
        setVoiceError(message);
        setVoiceState('error');
        voiceRunningRef.current = false;
        setVoiceRunning(false);
        if (!shouldPreserveCurrentJarvisRecording()) {
          voiceRecordingRef.current = false;
          setVoiceRecording(false);
        }
      }
      setChatRunActive(false);
      setRuntimeRunState('idle');
      setLastAssistantOutputAt(null);
      setOverview((previous: any) => (
        previous
          ? {
              ...previous,
              run_state: 'idle',
            }
          : previous
      ));
      if (channel === 'chat') {
        appendLocalSystemMessage(message, 'Error');
      }
      pushActivity(message, 'error');
      return;
    }

    if (channel === 'voice' && event.type === 'voice_state') {
      if (ignoreIfNotSelectedSession()) return;
      const rawState = String(payload.state || 'idle');
      const nextState = rawState === 'connected' ? 'ready' : rawState;
      if (['idle', 'cancelled', 'error', 'unavailable', 'ready'].includes(nextState)) {
        clearJarvisBargeInCandidate(payloadTurnId);
      }
      if ((nextState === 'idle' || nextState === 'cancelled') && shouldPreserveCurrentJarvisRecording()) {
        setVoiceError(null);
        voiceRunningRef.current = false;
        setVoiceRunning(false);
        return;
      }
      setVoiceState(nextState);
      setVoiceError(null);
      const nextRunning = !['ready', 'idle', 'cancelled', 'error', 'unavailable', 'connected', 'always_on'].includes(nextState);
      voiceRunningRef.current = nextRunning;
      setVoiceRunning(nextRunning);
      if (nextState === 'idle' || nextState === 'cancelled') {
        if (!shouldPreserveCurrentJarvisRecording()) {
          voiceRecordingRef.current = false;
          setVoiceRecording(false);
        }
        if (alwaysOnEnabledRef.current && nextState === 'idle') {
          setVoiceState('always_on');
          setTimeout(drainDeferredAlwaysOnFrames, 0);
        }
      }
      return;
    }

    if (channel === 'voice' && event.type === 'voice_partial') {
      if (ignoreIfNotSelectedSession()) return;
      const text = String(payload.text || '');
      setVoiceDraft(text);
      if (text.trim()) {
        setJarvisLatestTranscript(text.trim());
      }
      setVoiceState('listening');
      voiceRunningRef.current = true;
      setVoiceRunning(true);
      if (alwaysOnEnabledRef.current && conversationModeRef.current !== 'jarvis') {
        voiceComposerDraftRef.current = text;
        setComposerInputValue(
          composeVoiceDraftInput(voiceComposerBaseInputRef.current, text),
          { syncVoiceBase: false, origin: 'voice' }
        );
      }
      return;
    }

    if (channel === 'voice' && event.type === 'voice_transcript') {
      if (ignoreIfNotSelectedSession()) return;
      const text = String(payload.text || '').trim();
      if (!text) {
        return;
      }
      setJarvisLatestTranscript(text);
      acceptJarvisBargeInTranscript(payloadTurnId, text);
      if (alwaysOnEnabledRef.current && !shouldAutoSendAlwaysOnVoice()) {
        const nextInput = appendVoiceTranscriptSegment(voiceComposerBaseInputRef.current, text);
        voiceComposerBaseInputRef.current = nextInput;
        voiceComposerDraftRef.current = '';
        setComposerInputValue(nextInput, { syncVoiceBase: false, origin: 'voice' });
      } else if (conversationModeRef.current === 'jarvis') {
        voiceComposerDraftRef.current = '';
      } else {
        setInput((current: any) => {
          const existing = current.trim();
          const nextInput = existing ? `${existing} ${text}` : text;
          voiceComposerBaseInputRef.current = nextInput;
          voiceComposerDraftRef.current = '';
          lastComposerInputOriginRef.current = 'voice';
          return nextInput;
        });
      }
      setVoiceDraft(text);
      voiceRunningRef.current = false;
      setVoiceRunning(false);
      if (!shouldPreserveCurrentJarvisRecording()) {
        voiceRecordingRef.current = false;
        setVoiceRecording(false);
      }
      setVoiceState(alwaysOnEnabledRef.current ? 'always_on' : 'ready');
      setStatus('voice transcript ready to review');
      pushActivity(`Voice transcript ready: ${text}`, 'accent');
      return;
    }

    if (channel === 'voice' && event.type === 'voice_final') {
      if (ignoreIfNotSelectedSession()) return;
      const text = String(payload.text || '').trim();
      if (!text) {
        return;
      }
      setJarvisLatestTranscript(text);
      acceptJarvisBargeInTranscript(payloadTurnId, text);
      setVoiceDraft(text);
      voiceRunningRef.current = true;
      setVoiceRunning(true);
      if (!shouldPreserveCurrentJarvisRecording()) {
        voiceRecordingRef.current = false;
        setVoiceRecording(false);
      }
      setMessages((previous: any) => [
        ...previous,
        {
          role: 'user',
          content: text,
          timestamp: new Date().toISOString(),
          displayLabel: 'Voice',
          channel: 'app',
          sourceFormat: 'app_voice_transcript',
          messageKey: `voice:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`,
        },
      ]);
      pushActivity(`Voice transcript captured: ${text}`, 'accent');
    }
}
