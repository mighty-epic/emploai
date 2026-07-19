import { useEffect, useMemo, useState } from 'react';
import { Animated, Platform, Pressable, StyleSheet, Text, View } from 'react-native';

import {
  JARVIS_WAKE_PHRASE,
  jarvisSttBackendLabel,
  jarvisTtsBackendLabel,
  type JarvisSttBackend,
  type JarvisTtsBackend,
} from '@/desktop/desktopVoicePolicy';
import type { DesktopConversationScope } from './DesktopConversationScope';
import { isFleetWorkerAvailable } from './desktopFleetWorkerState';
import { DesktopJarvisWakeEnrollmentPanel } from './DesktopJarvisWakeEnrollmentPanel';
import { desktopConversationJarvisVisualStyles } from './DesktopConversationJarvisStage.visualStyles';
import { MonoIcon } from './DesktopConversationView.components';
import { DesktopProviderAvailabilityBanner } from './DesktopProviderAvailabilityBanner';
import { DesktopProviderFailureCard } from './DesktopProviderFailureCard';
import { mergeDesktopVisualStyles } from './mergeDesktopVisualStyles';

type JarvisStageProps = {
  scope: DesktopConversationScope;
};

const RING_TICKS = Array.from({ length: 120 }, (_, index) => index);
const ENERGY_SEGMENTS = Array.from({ length: 48 }, (_, index) => index);
const WAVE_BARS = Array.from({ length: 28 }, (_, index) => index);
const SPARK_PATTERN = [9, 15, 11, 19, 13, 22, 16, 24, 12, 18, 10, 20];

function clockLabel() {
  const now = new Date();
  return [
    String(now.getHours()).padStart(2, '0'),
    String(now.getMinutes()).padStart(2, '0'),
    String(now.getSeconds()).padStart(2, '0'),
  ].join(':');
}

function firstFiniteNumber(...values: unknown[]) {
  for (const value of values) {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) {
      return numeric;
    }
  }
  return null;
}

function statusWord(scope: DesktopConversationScope) {
  if (scope.providerFailure) {
    return 'ERROR';
  }
  if (
    scope.voiceError
    || scope.liveVoiceStatus?.input_ok === false
    || (
      scope.liveVoiceStatus?.tts_enabled !== false
      && scope.liveVoiceStatus?.tts_ready === false
      && Array.isArray(scope.liveVoiceStatus?.tts_issues)
      && scope.liveVoiceStatus.tts_issues.length > 0
    )
  ) {
    return 'ERROR';
  }
  if (scope.jarvisMuted || scope.jarvisCircleMuted) {
    return 'MUTED';
  }
  const machineState = String(scope.jarvisState || '').trim().toUpperCase();
  if (['UNAVAILABLE', 'ARMED', 'LISTENING', 'PROCESSING', 'SPEAKING', 'MUTED', 'ERROR'].includes(machineState)) {
    return machineState;
  }
  if (scope.voiceRecording) {
    return 'LISTENING';
  }
  if (scope.voiceRunning) {
    return 'PROCESSING';
  }
  if (scope.liveVoiceStatus?.tts_ready === false || scope.voiceState === 'warming') {
    return 'WARMING';
  }
  return 'ARMED';
}

function compactText(value: unknown, fallback: string) {
  const text = String(value ?? '').trim();
  return text || fallback;
}

function TelemetryItem({
  label,
  value,
  accent,
  spark,
  alignRight,
}: {
  label: string;
  value: string;
  accent?: boolean;
  spark?: boolean;
  alignRight?: boolean;
}) {
  return (
    <View style={[hudStyles.telemetryItem, alignRight ? hudStyles.telemetryItemRight : null]}>
      <Text style={hudStyles.telemetryKey}>{label}</Text>
      <Text style={[hudStyles.telemetryValue, accent ? hudStyles.telemetryValueAccent : null]}>{value}</Text>
      {spark ? (
        <View style={[hudStyles.sparkLine, alignRight ? hudStyles.sparkLineRight : null]}>
          {SPARK_PATTERN.map((height, index) => (
            <View
              key={`${label}-spark-${index}`}
              style={[
                hudStyles.sparkBar,
                accent ? hudStyles.sparkBarAccent : null,
                { height },
              ]}
            />
          ))}
        </View>
      ) : null}
    </View>
  );
}

function DockButton({
  icon,
  label,
  tooltip,
  active,
  primary,
  disabled,
  onPress,
  onPressIn,
  onPressOut,
}: {
  icon?: 'settings' | 'voice' | 'history' | 'compose' | 'stop';
  label?: string;
  tooltip?: string;
  active?: boolean;
  primary?: boolean;
  disabled?: boolean;
  onPress?: () => void;
  onPressIn?: () => void;
  onPressOut?: () => void;
}) {
  const [showTooltip, setShowTooltip] = useState(false);
  return (
    <View style={hudStyles.dockButtonWrap}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={tooltip || label}
        accessibilityState={{ disabled: Boolean(disabled) }}
        style={({ hovered, pressed }: any) => [
          hudStyles.dockButton,
          primary ? hudStyles.dockButtonPrimary : null,
          active ? hudStyles.dockButtonActive : null,
          hovered && !disabled ? hudStyles.dockButtonHovered : null,
          pressed && !disabled ? hudStyles.dockButtonPressed : null,
          disabled ? hudStyles.dockButtonDisabled : null,
        ]}
        onHoverIn={() => setShowTooltip(true)}
        onHoverOut={() => setShowTooltip(false)}
        onPress={disabled ? undefined : onPress}
        onPressIn={disabled ? undefined : onPressIn}
        onPressOut={disabled ? undefined : onPressOut}
      >
        {icon ? (
          <MonoIcon name={icon} style={[hudStyles.dockIcon, primary ? hudStyles.dockIconPrimary : null]} />
        ) : (
          <Text style={[hudStyles.dockText, primary ? hudStyles.dockTextPrimary : null]}>{label}</Text>
        )}
      </Pressable>
      {tooltip && showTooltip ? (
        <View pointerEvents="none" style={[hudStyles.dockTooltip, primary ? hudStyles.dockTooltipPrimary : null]}>
          <Text style={hudStyles.dockTooltipText}>{tooltip}</Text>
        </View>
      ) : null}
    </View>
  );
}

function EngineButton({
  label,
  active,
  changing,
  disabled,
  onPress,
}: {
  label: string;
  active: boolean;
  changing: boolean;
  disabled: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${label} voice engine`}
      accessibilityState={{ selected: active, disabled }}
      disabled={disabled}
      style={({ hovered }: any) => [
        hudStyles.engineButton,
        active ? hudStyles.engineButtonActive : null,
        hovered && !disabled ? hudStyles.engineButtonHovered : null,
        disabled && !changing ? hudStyles.engineButtonDisabled : null,
      ]}
      onPress={onPress}
    >
      <Text style={[hudStyles.engineButtonText, active ? hudStyles.engineButtonTextActive : null]}>
        {changing ? 'Switching' : label}
      </Text>
    </Pressable>
  );
}

function JarvisSettingsPanel({ scope }: JarvisStageProps) {
  const sttOptions = [
    { backend: scope.STT_BACKEND_OPENAI_REALTIME as JarvisSttBackend, label: 'Realtime API' },
    { backend: scope.STT_BACKEND_GEMINI as JarvisSttBackend, label: 'Gemini API' },
    { backend: scope.STT_BACKEND_LOCAL_WHISPER as JarvisSttBackend, label: 'Local Whisper' },
  ].filter((item) => Boolean(item.backend));
  const ttsOptions = [
    { backend: scope.TTS_BACKEND_KOKORO as JarvisTtsBackend, label: 'Kokoro' },
    { backend: scope.TTS_BACKEND_KYUTAI as JarvisTtsBackend, label: 'Kyutai clone' },
  ].filter((item) => Boolean(item.backend));

  return (
    <View style={hudStyles.drawerPanel}>
      <View style={hudStyles.drawerSection}>
        <View style={hudStyles.drawerHeader}>
          <Text style={hudStyles.drawerLabel}>WAKE PROFILE</Text>
          <Text style={hudStyles.drawerValue}>
            {scope.jarvisWakeProfileReady ? compactText(scope.currentJarvisWakePhrase, JARVIS_WAKE_PHRASE) : 'Training needed'}
          </Text>
        </View>
        <Text style={hudStyles.drawerHelper}>
          Always-on Jarvis matches your local wake phrase profile before audio reaches transcription.
        </Text>
        <View style={hudStyles.engineRow}>
          <EngineButton
            label={scope.jarvisWakeProfileReady ? 'Redo Training' : 'Train Wake Phrase'}
            active={!scope.jarvisWakeProfileReady}
            changing={false}
            disabled={Boolean(scope.voiceRecording)}
            onPress={() => scope.setJarvisWakeEnrollmentOpen?.(true)}
          />
          {scope.jarvisWakeProfileReady ? (
            <EngineButton
              label="Clear"
              active={false}
              changing={false}
              disabled={Boolean(scope.voiceRecording)}
              onPress={() => scope.clearLocalJarvisWakeProfile?.()}
            />
          ) : null}
        </View>
      </View>

      <View style={hudStyles.drawerSection}>
        <View style={hudStyles.drawerHeader}>
          <Text style={hudStyles.drawerLabel}>INPUT ENGINE</Text>
          <Text style={hudStyles.drawerValue}>
            {scope.sttBackendChanging
              ? `Switching to ${jarvisSttBackendLabel(scope.sttBackendChanging)}`
              : compactText(scope.currentJarvisSttLabel, 'Not ready')}
          </Text>
        </View>
        <View style={hudStyles.engineRow}>
          {sttOptions.map((item) => {
            const active = scope.currentJarvisSttBackend === item.backend;
            const changing = scope.sttBackendChanging === item.backend;
            const disabled = Boolean(scope.sttBackendChanging || scope.voiceRecording);
            return (
              <EngineButton
                key={`jarvis-hud-stt-${item.backend}`}
                label={item.label}
                active={active}
                changing={changing}
                disabled={disabled}
                onPress={() => {
                  void scope.handleJarvisSttBackendSelection?.(item.backend);
                }}
              />
            );
          })}
        </View>
      </View>

      <View style={hudStyles.drawerSection}>
        <View style={hudStyles.drawerHeader}>
          <Text style={hudStyles.drawerLabel}>VOICE ENGINE</Text>
          <Text style={hudStyles.drawerValue}>
            {scope.ttsBackendChanging
              ? `Switching to ${jarvisTtsBackendLabel(scope.ttsBackendChanging)}`
              : scope.liveVoiceStatus?.tts_ready === false
                ? compactText(scope.jarvisTtsSummary, 'Warming')
                : compactText(scope.currentJarvisTtsLabel, 'Not ready')}
          </Text>
        </View>
        <View style={hudStyles.engineRow}>
          {ttsOptions.map((item) => {
            const active = scope.currentJarvisTtsBackend === item.backend;
            const changing = scope.ttsBackendChanging === item.backend;
            const disabled = Boolean(scope.ttsBackendChanging);
            return (
              <EngineButton
                key={`jarvis-hud-tts-${item.backend}`}
                label={item.label}
                active={active}
                changing={changing}
                disabled={disabled}
                onPress={() => {
                  void scope.handleJarvisTtsBackendSelection?.(item.backend);
                }}
              />
            );
          })}
        </View>
      </View>
    </View>
  );
}

function JarvisActivityPanel({ scope }: JarvisStageProps) {
  const activity = Array.isArray(scope.jarvisToolActivity) ? scope.jarvisToolActivity.slice(0, 4) : [];
  return (
    <View style={hudStyles.drawerPanel}>
      {scope.activeTaskBoard ? (
        <View style={hudStyles.activityNotice}>
          <Text style={hudStyles.drawerLabel}>MANAGED TASK</Text>
          <Text style={hudStyles.activityNoticeText} numberOfLines={2}>
            {scope.taskBoardSummary || scope.activeTaskBoard.main_goal}
          </Text>
        </View>
      ) : null}
      <View style={hudStyles.activityColumns}>
        <View style={hudStyles.activityColumn}>
          <Text style={hudStyles.drawerLabel}>TRANSCRIPTION</Text>
          <Text style={hudStyles.activityText} numberOfLines={2}>
            {compactText(scope.jarvisTranscriptOutput, 'No transcript yet.')}
          </Text>
        </View>
        <View style={hudStyles.activityDivider} />
        <View style={hudStyles.activityColumn}>
          <Text style={hudStyles.drawerLabel}>TTS</Text>
          <Text style={hudStyles.activityText} numberOfLines={2}>
            {compactText(scope.jarvisSpokenOutput, 'No spoken output yet.')}
          </Text>
        </View>
      </View>
      <View style={hudStyles.activityList}>
        {activity.length ? activity.map((item: any) => (
          <Text key={`jarvis-hud-activity-${item.id}`} style={hudStyles.activityEvent} numberOfLines={1}>
            {item.text}
          </Text>
        )) : (
          <Text style={hudStyles.activityEvent}>No tool output yet.</Text>
        )}
      </View>
    </View>
  );
}

export function DesktopConversationJarvisStage({ scope }: JarvisStageProps) {
  const [clock, setClock] = useState(clockLabel);

  useEffect(() => {
    const timer = setInterval(() => setClock(clockLabel()), 1000);
    return () => clearInterval(timer);
  }, []);

  const workers = useMemo(() => {
    if (Array.isArray(scope.fleetWorkers)) {
      return scope.fleetWorkers;
    }
    return Array.isArray(scope.fleetSnapshot?.workers) ? scope.fleetSnapshot.workers : [];
  }, [scope.fleetSnapshot?.workers, scope.fleetWorkers]);

  const onlineWorkers = workers.filter(isFleetWorkerAvailable).length;
  const totalWorkers = workers.length;
  const latencyMs = firstFiniteNumber(scope.liveVoiceStatus?.latency_ms, scope.liveVoiceStatus?.rtt_ms);
  const latencyLabel = latencyMs === null ? '--ms' : `${Math.max(1, Math.round(latencyMs))}ms`;
  const activeStatus = statusWord(scope);
  const sessionLabel = scope.sessionId ? 'ACTIVE' : 'NO SESSION';
  const contextValue = compactText(scope.contextTokenLabel, 'No context data');
  const assistantAudioActive = Boolean(scope.assistantAudioRef?.current);
  const interruptible = Boolean(
    assistantAudioActive
    || scope.voiceRunning
    || scope.agentRunActive
    || scope.chatRunActive
    || scope.runtimeRunState === 'running'
  );
  const inputIssues = Array.isArray(scope.liveVoiceStatus?.issues)
    ? scope.liveVoiceStatus.issues.map((item: unknown) => String(item || '').trim()).filter(Boolean)
    : [];
  const ttsIssues = Array.isArray(scope.liveVoiceStatus?.tts_issues)
    ? scope.liveVoiceStatus.tts_issues.map((item: unknown) => String(item || '').trim()).filter(Boolean)
    : [];
  const localPacksMissing = Boolean(
    !scope.apiVoiceInputActive
    && scope.liveVoiceStatus?.input_ok === false
    && scope.liveVoiceStatus?.english_pack_ready === false
    && scope.liveVoiceStatus?.hebrew_pack_ready === false
  );
  const voiceReadinessIssue = scope.liveVoiceStatus?.input_ok === false
    ? compactText(
        inputIssues[0],
        localPacksMissing
          ? 'No local voice packs are installed. Open setup or choose an API input engine.'
          : 'Voice input needs setup.',
      )
    : scope.liveVoiceStatus?.tts_enabled !== false && scope.liveVoiceStatus?.tts_ready === false
      ? compactText(ttsIssues[0], 'Assistant audio needs setup.')
      : '';
  const wakePhraseLabel = compactText(scope.currentJarvisWakePhrase, JARVIS_WAKE_PHRASE);
  const statusDetail = scope.voiceError
    ? compactText(scope.voiceBannerText || scope.status, 'Voice error')
    : voiceReadinessIssue && !assistantAudioActive && !scope.voiceRecording && !scope.voiceRunning
      ? voiceReadinessIssue
    : assistantAudioActive
      ? 'Speaking. Press interrupt to stop.'
    : scope.voiceRecording
      ? compactText(scope.jarvisHoldCaptureValue, 'Listening')
    : scope.voiceRunning
      ? 'Processing response'
    : scope.jarvisMuted || scope.jarvisCircleMuted
      ? 'Muted'
    : !scope.jarvisWakeProfileReady && !scope.jarvisHoldToTalkMode
      ? 'Train a local wake phrase to enable always-on'
    : scope.alwaysOnEnabled && !scope.jarvisHoldToTalkMode
      ? `Say "${wakePhraseLabel}" before a request`
      : compactText(scope.voiceBannerText || scope.jarvisInputSummary, 'Voice path ready');
  const holdModeActive = Boolean(scope.jarvisHoldToTalkMode);
  const micDisabled = Boolean(scope.voiceStartInFlightRef?.current || assistantAudioActive);
  const holdCaptureDisabled = Boolean(micDisabled || scope.jarvisHoldCaptureDisabled);
  const pttToggleDisabled = Boolean(scope.voiceStartInFlightRef?.current || scope.voiceRecording);
  const energyLitCount = scope.voiceError
    ? 12
    : scope.voiceRecording
      ? 42
      : scope.voiceRunning
        ? 35
        : scope.jarvisMuted || scope.jarvisCircleMuted
          ? 8
          : 31;

  return (
    <View style={hudStyles.surface}>
      <View pointerEvents="none" style={[hudStyles.hudCorner, hudStyles.hudCornerTopLeft]} />
      <View pointerEvents="none" style={[hudStyles.hudCorner, hudStyles.hudCornerTopRight]} />
      <View pointerEvents="none" style={[hudStyles.hudCorner, hudStyles.hudCornerBottomLeft]} />
      <View pointerEvents="none" style={[hudStyles.hudCorner, hudStyles.hudCornerBottomRight]} />

      <View style={hudStyles.topbar}>
        <View style={hudStyles.systemId}>
          <View style={hudStyles.systemDot} />
          <Text style={hudStyles.systemIdText}>EMPLOAI · JARVIS</Text>
        </View>
        <View style={hudStyles.systemRight}>
          <Text style={hudStyles.systemRightText}>{clock}</Text>
        </View>
      </View>

      {scope.providerFailure ? (
        <View style={hudStyles.providerAlert}>
          <DesktopProviderFailureCard
            failure={scope.providerFailure}
            modelGroups={Array.isArray(scope.draftModelGroups) ? scope.draftModelGroups : []}
            onRetry={(providerId, modelId) => scope.retryFailedTurn?.(scope.providerFailure, providerId, modelId)}
            onOpenSettings={() => scope.onOpenSetup?.()}
          />
        </View>
      ) : Array.isArray(scope.overview?.provider_availability) ? (
        <View style={hudStyles.providerAlert}>
          <DesktopProviderAvailabilityBanner
            records={scope.overview.provider_availability}
            onOpenSettings={() => scope.onOpenSetup?.()}
          />
        </View>
      ) : null}

      <View style={hudStyles.console}>
        <View style={hudStyles.telemetry}>
          <TelemetryItem label="WORKERS ONLINE" value={`${onlineWorkers} / ${totalWorkers || 0}`} accent />
          <View style={hudStyles.telemetryDivider} />
          <TelemetryItem label="WAKE PHRASE" value={wakePhraseLabel.toUpperCase()} accent />
          <View style={hudStyles.telemetryDivider} />
          <Pressable
            accessibilityRole="switch"
            accessibilityLabel="Push to talk"
            accessibilityHint="Switch between wake phrase mode and hold-to-talk mode"
            accessibilityState={{ checked: holdModeActive, disabled: micDisabled }}
            disabled={micDisabled}
            style={({ hovered }: any) => [
              hudStyles.controlStrip,
              holdModeActive ? hudStyles.controlStripActive : null,
              hovered && !micDisabled ? hudStyles.controlStripHovered : null,
              micDisabled ? hudStyles.controlStripDisabled : null,
            ]}
            onPress={() => {
              void scope.setJarvisPushToTalkMode?.(!holdModeActive);
            }}
          >
            <View>
              <Text style={hudStyles.telemetryKey}>PUSH TO TALK</Text>
              <Text style={hudStyles.controlStripValue}>{holdModeActive ? 'ARMED' : 'ALWAYS ON'}</Text>
            </View>
            <View style={[hudStyles.switchTrack, holdModeActive ? hudStyles.switchTrackActive : null]}>
              <View style={[hudStyles.switchKnob, holdModeActive ? hudStyles.switchKnobActive : null]} />
            </View>
          </Pressable>
        </View>

        <View style={hudStyles.coreWrap}>
          <View style={hudStyles.ringStage}>
            <View pointerEvents="none" style={hudStyles.ringOuter}>
              {RING_TICKS.map((index) => {
                const major = index % 10 === 0;
                const medium = index % 5 === 0;
                return (
                  <View
                    key={`jarvis-hud-tick-${index}`}
                    style={[
                      hudStyles.tickRay,
                      { transform: [{ rotate: `${index * 3}deg` }] },
                    ]}
                  >
                    <View
                      style={[
                        hudStyles.tick,
                        medium ? hudStyles.tickMedium : null,
                        major ? hudStyles.tickMajor : null,
                      ]}
                    />
                  </View>
                );
              })}
            </View>
            <View pointerEvents="none" style={hudStyles.energyRing}>
              {ENERGY_SEGMENTS.map((index) => (
                <View
                  key={`jarvis-hud-energy-${index}`}
                  style={[
                    hudStyles.energySegment,
                    index < energyLitCount ? hudStyles.energySegmentLit : null,
                    {
                      transform: [
                        { rotate: `${index * 7.5}deg` },
                        { translateY: -168 },
                      ],
                    },
                  ]}
                />
              ))}
            </View>
            <View pointerEvents="none" style={hudStyles.ringDash} />
            <View pointerEvents="none" style={hudStyles.ringInnerLine} />
            <View pointerEvents="none" style={[hudStyles.particle, hudStyles.particleOne]} />
            <View pointerEvents="none" style={[hudStyles.particle, hudStyles.particleTwo]} />
            <View pointerEvents="none" style={[hudStyles.particle, hudStyles.particleThree]} />

            <Animated.View
              pointerEvents="none"
              style={[
                hudStyles.coreBloom,
                {
                  opacity: scope.jarvisPulseOpacity || 0.36,
                  transform: [{ scale: scope.jarvisPulseScale || 1 }],
                },
              ]}
            />
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={holdModeActive ? 'Hold to speak to Jarvis' : `Jarvis ${activeStatus.toLowerCase()}`}
              accessibilityHint={holdModeActive ? 'Hold while speaking, then release to send' : `Say ${wakePhraseLabel} before your request`}
              accessibilityState={{ disabled: holdCaptureDisabled }}
              disabled={holdCaptureDisabled}
              style={({ hovered, pressed }: any) => [
                hudStyles.coreShell,
                scope.voiceRecording ? hudStyles.coreShellListening : null,
                scope.voiceRunning && !scope.voiceRecording ? hudStyles.coreShellProcessing : null,
                scope.voiceError ? hudStyles.coreShellError : null,
                scope.jarvisMuted || scope.jarvisCircleMuted ? hudStyles.coreShellMuted : null,
                hovered && !holdCaptureDisabled ? hudStyles.coreShellHovered : null,
                pressed && !holdCaptureDisabled ? hudStyles.coreShellPressed : null,
              ]}
              onPressIn={holdModeActive && !holdCaptureDisabled
                ? () => {
                    void scope.startJarvisPushToTalk?.();
                  }
                : undefined}
              onPressOut={holdModeActive && !holdCaptureDisabled
                ? () => {
                    void scope.stopJarvisPushToTalk?.();
                  }
                : undefined}
            >
              <View pointerEvents="none" style={hudStyles.coreGlass} />
            </Pressable>
          </View>

          <View style={hudStyles.statusBlock}>
            <Text accessibilityLiveRegion="polite" style={hudStyles.statusText}>
              <Text style={hudStyles.statusTextAccent}>{activeStatus}</Text>
            </Text>
            <Text style={hudStyles.statusDetail} numberOfLines={1}>{statusDetail}</Text>
            <View style={hudStyles.waveform}>
              {WAVE_BARS.map((index) => {
                const activeHeight = scope.voiceRecording
                  ? 6 + ((index * 7 + clock.charCodeAt(7)) % 16)
                  : scope.voiceRunning
                    ? 5 + ((index * 5 + clock.charCodeAt(6)) % 13)
                    : 4 + (index % 5);
                return (
                  <View
                    key={`jarvis-hud-wave-${index}`}
                    style={[
                      hudStyles.waveBar,
                      scope.voiceError ? hudStyles.waveBarError : null,
                      scope.jarvisMuted || scope.jarvisCircleMuted ? hudStyles.waveBarMuted : null,
                      { height: activeHeight },
                    ]}
                  />
                );
              })}
            </View>
          </View>
        </View>

        <View style={[hudStyles.telemetry, hudStyles.telemetryRight]}>
          <TelemetryItem label="LATENCY" value={latencyLabel} accent spark alignRight />
          <View style={hudStyles.telemetryDivider} />
          <TelemetryItem label="SESSION" value={sessionLabel} accent alignRight />
          <View style={hudStyles.telemetryDivider} />
          <TelemetryItem label="CONTEXT" value={contextValue} alignRight />
        </View>
      </View>

      {scope.jarvisVoiceSettingsOpen ? <JarvisSettingsPanel scope={scope} /> : null}
      {scope.jarvisStatusDrawerOpen ? <JarvisActivityPanel scope={scope} /> : null}
      <DesktopJarvisWakeEnrollmentPanel
        visible={Boolean(scope.jarvisWakeEnrollmentOpen || (!scope.jarvisWakeProfileReady && !scope.jarvisHoldToTalkMode))}
        profile={scope.jarvisWakeProfile || null}
        required={!scope.jarvisWakeProfileReady && !scope.jarvisHoldToTalkMode}
        onSave={(profile) => scope.saveLocalJarvisWakeProfile?.(profile)}
        onCancel={() => scope.setJarvisWakeEnrollmentOpen?.(false)}
        onUsePushToTalk={() => {
          scope.setJarvisWakeEnrollmentOpen?.(false);
          void scope.setJarvisPushToTalkMode?.(true);
        }}
      />

      <View style={hudStyles.dock}>
        <DockButton
          icon="settings"
          tooltip="Open voice settings"
          active={Boolean(scope.jarvisVoiceSettingsOpen)}
          onPress={() => scope.setJarvisVoiceSettingsOpen?.((current: any) => !current)}
        />
        <DockButton
          label="PTT"
          tooltip="Toggle push-to-talk"
          active={holdModeActive}
          disabled={pttToggleDisabled}
          onPress={() => {
            void scope.setJarvisPushToTalkMode?.(!holdModeActive);
          }}
        />
        <DockButton
          icon="voice"
          tooltip={scope.jarvisMuteButtonMuted ? 'Unmute microphone' : 'Mute microphone'}
          primary
          active={Boolean(scope.jarvisMuteButtonMuted)}
          onPress={() => {
            scope.toggleJarvisMute?.();
          }}
        />
        <DockButton
          icon="history"
          tooltip="Show Jarvis activity"
          active={Boolean(scope.jarvisStatusDrawerOpen)}
          onPress={() => scope.setJarvisStatusDrawerOpen?.((current: any) => !current)}
        />
        {interruptible ? (
          <DockButton
            icon="stop"
            tooltip="Interrupt speech or run"
            active
            onPress={() => {
              void scope.cleanupAssistantAudio?.();
              if (scope.voiceRunning || scope.agentRunActive || scope.chatRunActive || scope.runtimeRunState === 'running') {
                void scope.runControl?.('stop');
              } else {
                scope.setStatus?.('Jarvis speech stopped');
              }
            }}
          />
        ) : null}
      </View>
    </View>
  );
}

const MONO_FONT = Platform.OS === 'web' ? 'JetBrains Mono, Consolas, monospace' : undefined;
const BODY_FONT = Platform.OS === 'web' ? 'Inter, Segoe UI, sans-serif' : undefined;

const hudBaseStyles = StyleSheet.create({
  surface: {
    flex: 1,
    minHeight: 640,
    width: '100%',
    backgroundColor: '#030304',
    color: '#edeeee',
    overflow: 'hidden',
    position: 'relative',
    ...(Platform.OS === 'web'
      ? ({
          backgroundImage: [
            'radial-gradient(ellipse at 50% 45%, rgba(232,69,47,0.08), transparent 56%)',
            'linear-gradient(rgba(255,255,255,0.012) 1px, transparent 1px)',
            'linear-gradient(90deg, rgba(255,255,255,0.012) 1px, transparent 1px)',
          ].join(', '),
          backgroundSize: '100% 100%, 34px 34px, 34px 34px',
        } as any)
      : null),
  },
  providerAlert: {
    position: 'absolute',
    top: 58,
    left: 18,
    right: 18,
    zIndex: 10,
  },
  hudCorner: {
    position: 'absolute',
    width: 22,
    height: 22,
    borderColor: '#3e4045',
    zIndex: 4,
  },
  hudCornerTopLeft: {
    top: 14,
    left: 14,
    borderTopWidth: 1,
    borderLeftWidth: 1,
  },
  hudCornerTopRight: {
    top: 14,
    right: 14,
    borderTopWidth: 1,
    borderRightWidth: 1,
  },
  hudCornerBottomLeft: {
    bottom: 14,
    left: 14,
    borderBottomWidth: 1,
    borderLeftWidth: 1,
  },
  hudCornerBottomRight: {
    bottom: 14,
    right: 14,
    borderBottomWidth: 1,
    borderRightWidth: 1,
  },
  topbar: {
    minHeight: 66,
    borderBottomWidth: 1,
    borderBottomColor: '#1a1b1e',
    paddingHorizontal: 40,
    paddingVertical: 18,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 18,
    zIndex: 2,
  },
  systemId: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    minWidth: 0,
  },
  systemDot: {
    width: 6,
    height: 6,
    borderRadius: 999,
    backgroundColor: '#e8452f',
    shadowColor: '#e8452f',
    shadowOpacity: 0.75,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 0 },
  },
  systemIdText: {
    color: '#6e7076',
    fontFamily: MONO_FONT,
    fontSize: 11,
    fontWeight: '600',
    letterSpacing: 1.1,
  },
  systemRight: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 28,
    flexWrap: 'wrap',
  },
  systemRightText: {
    color: '#3e4045',
    fontFamily: MONO_FONT,
    fontSize: 11,
    fontWeight: '500',
    letterSpacing: 0.9,
  },
  systemRightStrong: {
    color: '#6e7076',
  },
  console: {
    flex: 1,
    minHeight: 460,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 40,
    paddingVertical: 8,
    gap: 28,
    zIndex: 2,
  },
  telemetry: {
    width: 230,
    minHeight: 360,
    justifyContent: 'center',
    gap: 22,
  },
  telemetryRight: {
    alignItems: 'flex-end',
  },
  telemetryItem: {
    gap: 5,
  },
  telemetryItemRight: {
    alignItems: 'flex-end',
  },
  telemetryKey: {
    color: '#3e4045',
    fontFamily: MONO_FONT,
    fontSize: 10,
    fontWeight: '600',
    letterSpacing: 1,
  },
  telemetryValue: {
    color: '#edeeee',
    fontFamily: MONO_FONT,
    fontSize: 16,
    fontWeight: '500',
  },
  telemetryValueAccent: {
    color: '#e8452f',
  },
  telemetryDivider: {
    width: '100%',
    height: 1,
    backgroundColor: '#1a1b1e',
  },
  sparkLine: {
    width: 112,
    height: 26,
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 3,
    marginTop: 2,
  },
  sparkLineRight: {
    justifyContent: 'flex-end',
  },
  sparkBar: {
    width: 5,
    borderRadius: 999,
    backgroundColor: '#5c5f66',
  },
  sparkBarAccent: {
    backgroundColor: '#e8452f',
  },
  controlStrip: {
    minHeight: 52,
    borderWidth: 1,
    borderColor: '#1a1b1e',
    backgroundColor: '#0b0c0e',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 9,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  controlStripHovered: {
    borderColor: '#5c5f66',
  },
  controlStripActive: {
    borderColor: '#e8452f',
    backgroundColor: '#13100f',
  },
  controlStripDisabled: {
    opacity: 0.52,
  },
  controlStripValue: {
    color: '#edeeee',
    fontFamily: MONO_FONT,
    fontSize: 13,
    fontWeight: '600',
    marginTop: 4,
  },
  switchTrack: {
    width: 42,
    height: 22,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#26282c',
    backgroundColor: '#030304',
    padding: 2,
  },
  switchTrackActive: {
    borderColor: '#e8452f',
    backgroundColor: '#2a0d09',
  },
  switchKnob: {
    width: 16,
    height: 16,
    borderRadius: 999,
    backgroundColor: '#5c5f66',
  },
  switchKnobActive: {
    backgroundColor: '#ff8a5c',
    transform: [{ translateX: 18 }],
  },
  coreWrap: {
    flex: 1,
    minWidth: 420,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ringStage: {
    width: 400,
    height: 400,
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  ringOuter: {
    position: 'absolute',
    width: 392,
    height: 392,
    borderRadius: 196,
    borderWidth: 1,
    borderColor: '#17181b',
  },
  tickRay: {
    position: 'absolute',
    left: 195,
    top: 0,
    width: 2,
    height: 392,
    alignItems: 'center',
  },
  tick: {
    width: 1,
    height: 12,
    borderRadius: 1,
    backgroundColor: '#212226',
  },
  tickMedium: {
    height: 17,
    backgroundColor: '#3a3c42',
  },
  tickMajor: {
    height: 24,
    backgroundColor: '#5c5f66',
  },
  energyRing: {
    position: 'absolute',
    width: 400,
    height: 400,
    alignItems: 'center',
    justifyContent: 'center',
  },
  energySegment: {
    position: 'absolute',
    width: 16,
    height: 3,
    borderRadius: 999,
    backgroundColor: '#1e1f22',
  },
  energySegmentLit: {
    backgroundColor: '#e8452f',
    shadowColor: '#e8452f',
    shadowOpacity: 0.45,
    shadowRadius: 7,
    shadowOffset: { width: 0, height: 0 },
  },
  ringDash: {
    position: 'absolute',
    width: 296,
    height: 296,
    borderRadius: 148,
    borderWidth: 1,
    borderColor: '#3a3c42',
    borderStyle: 'dashed',
  },
  ringInnerLine: {
    position: 'absolute',
    width: 244,
    height: 244,
    borderRadius: 122,
    borderWidth: 1,
    borderColor: '#26282c',
  },
  particle: {
    position: 'absolute',
    width: 4,
    height: 4,
    borderRadius: 999,
    backgroundColor: '#ff8a5c',
    shadowColor: '#ff8a5c',
    shadowOpacity: 0.9,
    shadowRadius: 7,
    shadowOffset: { width: 0, height: 0 },
  },
  particleOne: {
    top: 72,
    left: 300,
  },
  particleTwo: {
    top: 292,
    left: 82,
  },
  particleThree: {
    top: 96,
    left: 88,
  },
  coreBloom: {
    position: 'absolute',
    width: 196,
    height: 196,
    borderRadius: 98,
    backgroundColor: 'rgba(232,69,47,0.1)',
    borderWidth: 1,
    borderColor: 'rgba(232,69,47,0.36)',
    shadowColor: '#e8452f',
    shadowOpacity: 0.42,
    shadowRadius: 70,
    shadowOffset: { width: 0, height: 0 },
  },
  coreShell: {
    width: 180,
    height: 180,
    borderRadius: 90,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: 'rgba(255,138,92,0.62)',
    backgroundColor: '#e8452f',
    overflow: 'hidden',
    shadowColor: '#e8452f',
    shadowOpacity: 0.4,
    shadowRadius: 46,
    shadowOffset: { width: 0, height: 0 },
    ...(Platform.OS === 'web'
      ? ({
          backgroundImage: 'conic-gradient(from 0deg, #7a1e12, #e8452f, #ff8a5c, #e8452f, #7a1e12, #e8452f, #ff8a5c, #7a1e12)',
        } as any)
      : null),
  },
  coreShellHovered: {
    borderColor: '#ffb28c',
  },
  coreShellPressed: {
    transform: [{ scale: 0.98 }],
  },
  coreShellListening: {
    shadowOpacity: 0.62,
  },
  coreShellProcessing: {
    borderColor: '#ff8a5c',
  },
  coreShellMuted: {
    backgroundColor: '#26110d',
    borderColor: '#5e1d12',
    shadowOpacity: 0.12,
  },
  coreShellError: {
    backgroundColor: '#4c1014',
    borderColor: '#ff5c66',
    shadowColor: '#ff5c66',
  },
  coreGlass: {
    width: '100%',
    height: '100%',
    borderRadius: 90,
    ...(Platform.OS === 'web'
      ? ({
          backgroundImage: [
            'radial-gradient(circle at 38% 30%, rgba(255,255,255,0.5), rgba(255,255,255,0) 40%)',
            'radial-gradient(circle at 60% 70%, rgba(0,0,0,0.5), transparent 60%)',
          ].join(', '),
          mixBlendMode: 'overlay',
        } as any)
      : null),
  },
  statusBlock: {
    marginTop: 30,
    alignItems: 'center',
    gap: 9,
    width: '100%',
  },
  statusText: {
    color: '#6e7076',
    fontFamily: MONO_FONT,
    fontSize: 12,
    fontWeight: '600',
    letterSpacing: 1.9,
  },
  statusTextAccent: {
    color: '#e8452f',
  },
  statusDetail: {
    maxWidth: 420,
    color: '#5c5f66',
    fontFamily: BODY_FONT,
    fontSize: 12,
    fontWeight: '500',
    textAlign: 'center',
  },
  waveform: {
    height: 22,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
  },
  waveBar: {
    width: 3,
    borderRadius: 999,
    backgroundColor: '#5c5f66',
  },
  waveBarError: {
    backgroundColor: '#ff5c66',
  },
  waveBarMuted: {
    opacity: 0.38,
  },
  drawerPanel: {
    width: '82%',
    maxWidth: 820,
    alignSelf: 'center',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#2d1b18',
    backgroundColor: 'rgba(11,12,14,0.96)',
    paddingHorizontal: 14,
    paddingVertical: 12,
    gap: 12,
    zIndex: 3,
  },
  drawerSection: {
    gap: 9,
  },
  drawerHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  drawerLabel: {
    color: '#5c5f66',
    fontFamily: MONO_FONT,
    fontSize: 10,
    fontWeight: '600',
    letterSpacing: 1,
  },
  drawerValue: {
    color: '#edeeee',
    fontFamily: BODY_FONT,
    fontSize: 12,
    fontWeight: '600',
    textAlign: 'right',
  },
  drawerHelper: {
    color: '#868a92',
    fontFamily: BODY_FONT,
    fontSize: 12,
    lineHeight: 17,
  },
  engineRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  engineButton: {
    minHeight: 44,
    minWidth: 116,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#26282c',
    backgroundColor: '#0b0c0e',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  engineButtonHovered: {
    borderColor: '#5c5f66',
  },
  engineButtonActive: {
    borderColor: '#e8452f',
    backgroundColor: '#e8452f',
  },
  engineButtonDisabled: {
    opacity: 0.5,
  },
  engineButtonText: {
    color: '#edeeee',
    fontFamily: BODY_FONT,
    fontSize: 12,
    fontWeight: '700',
  },
  engineButtonTextActive: {
    color: '#030304',
  },
  activityNotice: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(232,69,47,0.34)',
    backgroundColor: '#130807',
    paddingHorizontal: 10,
    paddingVertical: 8,
    gap: 4,
  },
  activityNoticeText: {
    color: '#edeeee',
    fontFamily: BODY_FONT,
    fontSize: 12,
    lineHeight: 17,
  },
  activityColumns: {
    flexDirection: 'row',
    alignItems: 'stretch',
    gap: 12,
  },
  activityColumn: {
    flex: 1,
    minWidth: 0,
    gap: 5,
  },
  activityDivider: {
    width: 1,
    backgroundColor: '#1a1b1e',
  },
  activityText: {
    color: '#edeeee',
    fontFamily: BODY_FONT,
    fontSize: 12,
    lineHeight: 17,
  },
  activityList: {
    gap: 6,
  },
  activityEvent: {
    color: '#6e7076',
    fontFamily: MONO_FONT,
    fontSize: 11,
    lineHeight: 16,
  },
  dock: {
    minHeight: 96,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    paddingTop: 22,
    paddingBottom: 30,
    zIndex: 2,
  },
  dockButtonWrap: {
    position: 'relative',
    alignItems: 'center',
    justifyContent: 'center',
  },
  dockButton: {
    width: 44,
    height: 44,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#1a1b1e',
    backgroundColor: '#0b0c0e',
    alignItems: 'center',
    justifyContent: 'center',
  },
  dockButtonPrimary: {
    width: 52,
    height: 52,
    backgroundColor: '#131417',
    borderColor: '#3a3c42',
    shadowColor: '#e8452f',
    shadowOpacity: 0.16,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 0 },
  },
  dockButtonHovered: {
    borderColor: '#5c5f66',
  },
  dockButtonPressed: {
    backgroundColor: '#17110f',
  },
  dockButtonActive: {
    borderColor: '#e8452f',
  },
  dockButtonDisabled: {
    opacity: 0.45,
  },
  dockTooltip: {
    position: 'absolute',
    bottom: 52,
    minWidth: 118,
    maxWidth: 150,
    borderRadius: 7,
    borderWidth: 1,
    borderColor: '#2d1b18',
    backgroundColor: '#131417',
    paddingHorizontal: 9,
    paddingVertical: 6,
    shadowColor: '#000',
    shadowOpacity: 0.35,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
    zIndex: 6,
  },
  dockTooltipPrimary: {
    bottom: 62,
    borderColor: 'rgba(232,69,47,0.48)',
  },
  dockTooltipText: {
    color: '#edeeee',
    fontFamily: BODY_FONT,
    fontSize: 11,
    fontWeight: '600',
    lineHeight: 15,
    textAlign: 'center',
  },
  dockIcon: {
    color: '#6e7076',
    fontSize: 17,
  },
  dockIconPrimary: {
    color: '#edeeee',
    fontSize: 20,
  },
  dockText: {
    color: '#6e7076',
    fontFamily: MONO_FONT,
    fontSize: 12,
    fontWeight: '700',
  },
  dockTextPrimary: {
    color: '#edeeee',
  },
});

const hudStyles = mergeDesktopVisualStyles(hudBaseStyles, desktopConversationJarvisVisualStyles);
