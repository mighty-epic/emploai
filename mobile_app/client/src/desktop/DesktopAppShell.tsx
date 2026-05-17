import { useEffect, useMemo, useRef, useState } from 'react';
import { Animated, Easing, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import { DesktopConversationView } from './DesktopConversationView';
import { DesktopSetupPanel } from './DesktopSetupPanel';
import type { DesktopMode, RemoteRuntimeSummary } from './models';
import {
  checkDesktopUpdates,
  copyDesktopText,
  installDesktopVoicePack,
  installDesktopUpdate,
  isDesktopEnvironment,
  loadDesktopMemory,
  loadDesktopBootstrap,
  loadDesktopRuntimeStatus,
  openDesktopChromeExtensions,
  openDesktopPath,
  removeDesktopVoicePack,
  saveDesktopMemory,
  saveDesktopSetup,
  setDesktopVoiceDefaultEngine,
  startDesktopRuntime,
  stopDesktopRuntime,
  subscribeDesktopRuntime,
  type DesktopBootstrap,
  type DesktopMemoryState,
  type DesktopRuntimeStatus,
  type DesktopSetupValues,
  type DesktopUpdateStatus,
} from '@/lib/desktopBridge';

function normalizeParam(value: string | string[] | undefined) {
  if (Array.isArray(value)) {
    return value[0];
  }
  return value;
}

function runtimeLabel(runtimeStatus: DesktopRuntimeStatus | null, fallback: string) {
  if (!runtimeStatus) {
    return fallback;
  }
  return runtimeStatus.degraded ? `${runtimeStatus.state} · degraded` : runtimeStatus.state;
}

function normalizeSetupValue(value: string | undefined) {
  return String(value ?? '').trim();
}

function setupValuesChanged(
  nextValues: Partial<DesktopSetupValues>,
  baseline: DesktopSetupValues | null | undefined,
) {
  if (!baseline) {
    return true;
  }
  const keys = Object.keys(baseline) as Array<keyof DesktopSetupValues>;
  return keys.some((key) => normalizeSetupValue(nextValues[key]) !== normalizeSetupValue(baseline[key]));
}

function delay(ms: number) {
  return new Promise((resolve) => {
    globalThis.setTimeout(resolve, ms);
  });
}

const STARTUP_WATCHDOG_MS = 120_000;
const DESKTOP_RUNTIME_RESTART_WAIT_MS = 95_000;

type StartupPhase =
  | 'bootstrapping'
  | 'setup_required'
  | 'starting_runtime'
  | 'warming_ui'
  | 'ready'
  | 'startup_error';

type StartupReadinessState = 'warming' | 'chat_ready' | 'fatal_error';

function isStartupPending(phase: StartupPhase) {
  return phase === 'bootstrapping' || phase === 'starting_runtime' || phase === 'warming_ui';
}

function startupStatusLabel(phase: StartupPhase, detail: string | null) {
  if (phase === 'warming_ui' && detail) {
    return detail;
  }
  switch (phase) {
    case 'bootstrapping':
      return 'Preparing desktop runtime';
    case 'starting_runtime':
      return 'Starting local backend';
    case 'warming_ui':
      return 'Loading shared session';
    default:
      return detail || 'Starting EmploAI';
  }
}

function StartupGlyph() {
  const spin = useRef(new Animated.Value(0)).current;
  const pulse = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const spinLoop = Animated.loop(
      Animated.timing(spin, {
        toValue: 1,
        duration: 1800,
        easing: Easing.linear,
        useNativeDriver: true,
      })
    );
    const pulseLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1,
          duration: 900,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 0,
          duration: 900,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
        }),
      ])
    );

    spinLoop.start();
    pulseLoop.start();

    return () => {
      spinLoop.stop();
      pulseLoop.stop();
    };
  }, [pulse, spin]);

  const orbitRotation = spin.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg'],
  });
  const pulseScale = pulse.interpolate({
    inputRange: [0, 1],
    outputRange: [0.95, 1.08],
  });
  const pulseOpacity = pulse.interpolate({
    inputRange: [0, 1],
    outputRange: [0.45, 0.95],
  });

  return (
    <View style={styles.startupGlyphFrame}>
      <Animated.View
        style={[
          styles.startupGlyphCore,
          {
            transform: [{ scale: pulseScale }],
            opacity: pulseOpacity,
          },
        ]}
      />
      <Animated.View
        style={[
          styles.startupGlyphOrbit,
          {
            transform: [{ rotate: orbitRotation }],
          },
        ]}
      >
        <View style={styles.startupGlyphDot} />
      </Animated.View>
    </View>
  );
}

const webBackdropBlurStyle =
  Platform.OS === 'web'
    ? ({ backdropFilter: 'blur(18px)', WebkitBackdropFilter: 'blur(18px)' } as any)
    : null;

export function DesktopAppShell() {
  const params = useLocalSearchParams<{ sessionId?: string | string[]; tab?: string | string[] }>();
  const requestedSessionId = normalizeParam(params.sessionId);
  const requestedTab = normalizeParam(params.tab);

  const [activeTab, setActiveTab] = useState<DesktopMode>('local');
  const [bootstrap, setBootstrap] = useState<DesktopBootstrap | null>(null);
  const [runtimeStatus, setRuntimeStatus] = useState<DesktopRuntimeStatus | null>(null);
  const [updateStatus, setUpdateStatus] = useState<DesktopUpdateStatus | null>(null);
  const [loadingState, setLoadingState] = useState('bootstrapping desktop shell');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [startupPhase, setStartupPhase] = useState<StartupPhase>('bootstrapping');
  const [startupErrorDetail, setStartupErrorDetail] = useState<string | null>(null);
  const [showSetup, setShowSetup] = useState(false);
  const [startingRuntime, setStartingRuntime] = useState(false);
  const [stoppingRuntime, setStoppingRuntime] = useState(false);
  const [savingSetup, setSavingSetup] = useState(false);
  const [voicePackBusyId, setVoicePackBusyId] = useState<string | null>(null);
  const [checkingUpdates, setCheckingUpdates] = useState(false);
  const [installingUpdate, setInstallingUpdate] = useState(false);
  const [memoryState, setMemoryState] = useState<DesktopMemoryState | null>(null);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [memorySaving, setMemorySaving] = useState(false);
  const startupPhaseRef = useRef<StartupPhase>('bootstrapping');
  const startupWatchdogTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const postStartupSetupNoticeSentRef = useRef(false);

  useEffect(() => {
    setActiveTab('local');
  }, [requestedTab]);

  useEffect(() => {
    startupPhaseRef.current = startupPhase;
  }, [startupPhase]);

  const applyBootstrap = (
    payload: DesktopBootstrap,
    options: { keepSetupClosed?: boolean } = {}
  ) => {
    setBootstrap(payload);
    if (payload.runtimeStatus) {
      setRuntimeStatus(payload.runtimeStatus);
    }
    if (options.keepSetupClosed) {
      setShowSetup(false);
    }
    if (payload.accessToken && (payload.runtimeStatus?.ok ?? false)) {
      setLoadingState('Loading shared session');
      return;
    }
    if (payload.setupState?.required) {
      setLoadingState('Setup required');
      return;
    }
    setLoadingState(payload.runtimeStatus?.detail || 'Preparing desktop runtime');
  };

  const failStartup = (message: string) => {
    setStartupErrorDetail(message);
    setError(message);
    setStartupPhase('startup_error');
  };

  const beginStartup = async (options?: { forceBootstrap?: boolean }) => {
    if (!isDesktopEnvironment()) {
      failStartup('Desktop preload bridge is unavailable. Launch this route inside the Electron shell.');
      return;
    }

    setError(null);
    setNotice(null);
    setShowSetup(false);
    setStartupErrorDetail(null);
    setStartupPhase('bootstrapping');
    setBootstrap(null);
    setRuntimeStatus(null);
    setLoadingState('Preparing desktop runtime');

    try {
      const payload = await loadDesktopBootstrap({ force: options?.forceBootstrap });
      if (!payload) {
        throw new Error('Desktop bootstrap is unavailable in this shell.');
      }

      applyBootstrap(payload, { keepSetupClosed: true });

      if (payload.setupState?.required) {
        setStartupPhase('setup_required');
        return;
      }

      let readyPayload = payload;
      if (!(payload.accessToken && payload.runtimeStatus?.ok)) {
        setStartupPhase('starting_runtime');
        setLoadingState('Starting local backend');
        const started = await startDesktopRuntime();
        if (!started) {
          throw new Error('Desktop runtime controls are unavailable in this shell.');
        }
        readyPayload = started;
        applyBootstrap(readyPayload, { keepSetupClosed: true });
      }

      if (readyPayload.setupState?.required) {
        setStartupPhase('setup_required');
        return;
      }

      if (!(readyPayload.accessToken && readyPayload.runtimeStatus?.ok)) {
        throw new Error(
          readyPayload.runtimeStatus?.detail ||
          'Local runtime did not become ready. Check the desktop runtime logs and try again.'
        );
      }

      setStartupPhase('warming_ui');
      setLoadingState('Loading shared session');
    } catch (startupError) {
      failStartup(String(startupError));
    }
  };

  const refreshUpdateStatus = async (force = false) => {
    setCheckingUpdates(true);
    try {
      const next = await checkDesktopUpdates({ force });
      if (next) {
        setUpdateStatus(next);
      }
    } catch (updateError) {
      setUpdateStatus({
        ok: false,
        currentVersion: bootstrap?.releaseVersion || bootstrap?.setupState?.releaseVersion || 'unknown',
        releaseTag: bootstrap?.releaseVersion || 'unknown',
        channel: 'beta',
        repo: 'unknown',
        intervalHours: 0,
        checked: true,
        updateAvailable: false,
        update: null,
        lastError: String(updateError),
      });
    } finally {
      setCheckingUpdates(false);
    }
  };

  useEffect(() => {
    if (!isDesktopEnvironment()) {
      failStartup('Desktop preload bridge is unavailable. Launch this route inside the Electron shell.');
      return;
    }

    let disposed = false;

    void beginStartup();

    loadDesktopRuntimeStatus()
      .then((status) => {
        if (disposed || !status) {
          return;
        }
        setRuntimeStatus(status);
      })
      .catch(() => {});

    void refreshUpdateStatus(false);

    const unsubscribe = subscribeDesktopRuntime((event) => {
      if (disposed) {
        return;
      }

      const payload = event.payload as DesktopBootstrap | DesktopRuntimeStatus | undefined;
      if (event.type === 'runtime_status' && payload) {
        setRuntimeStatus(payload as DesktopRuntimeStatus);
        return;
      }

      if (
        event.type === 'bootstrap_ready' ||
        event.type === 'runtime_started' ||
        event.type === 'runtime_stopped' ||
        event.type === 'setup_saved'
      ) {
        const bootstrapPayload = payload as DesktopBootstrap | undefined;
        if (bootstrapPayload?.apiBaseUrl) {
          applyBootstrap(bootstrapPayload);
          if (
            event.type === 'runtime_stopped' &&
            isStartupPending(startupPhaseRef.current) &&
            !bootstrapPayload.runtimeStatus?.ok
          ) {
            failStartup(
              bootstrapPayload.runtimeStatus?.detail ||
              'The local runtime stopped before the desktop app became ready.'
            );
          }
        }
      }
    });

    return () => {
      disposed = true;
      unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!isStartupPending(startupPhase)) {
      if (startupWatchdogTimerRef.current) {
        clearTimeout(startupWatchdogTimerRef.current);
        startupWatchdogTimerRef.current = null;
      }
      return;
    }

    if (startupWatchdogTimerRef.current) {
      clearTimeout(startupWatchdogTimerRef.current);
    }
    startupWatchdogTimerRef.current = setTimeout(() => {
      if (isStartupPending(startupPhaseRef.current)) {
        failStartup('Startup is taking longer than expected. The desktop app did not become ready within 60 seconds.');
      }
    }, STARTUP_WATCHDOG_MS);

    return () => {
      if (startupWatchdogTimerRef.current) {
        clearTimeout(startupWatchdogTimerRef.current);
        startupWatchdogTimerRef.current = null;
      }
    };
  }, [startupPhase]);

  const remoteRuntimes = useMemo<RemoteRuntimeSummary[]>(
    () => [
      {
        id: 'remote-1',
        name: 'Primary VPS Slot',
        hostLabel: 'Not connected',
        status: 'planned',
        detail: 'Reserved for future hosted agents with preview streaming and remote control.',
        preview: {
          state: 'planned',
          message: 'Preview surfaces will appear here once remote runtime plumbing exists.',
        },
      },
      {
        id: 'remote-2',
        name: 'Secondary Worker Slot',
        hostLabel: 'Not connected',
        status: 'planned',
        detail: 'Additional remote runtime entry point for server-side or VPS agents.',
        preview: {
          state: 'planned',
          message: 'No remote preview yet',
        },
      },
    ],
    []
  );

  const localRuntimeReady = Boolean(
    bootstrap?.apiBaseUrl &&
    bootstrap?.accessToken &&
    (runtimeStatus?.ok ?? bootstrap?.runtimeStatus?.ok)
  );
  const runtimeProcessDetected = Boolean(
    bootstrap?.runtimeProcessDetected ||
    runtimeStatus?.process_id ||
    runtimeStatus?.processId ||
    bootstrap?.runtimeStatus?.process_id ||
    bootstrap?.runtimeStatus?.processId
  );
  const setupBlocksRuntime = Boolean(bootstrap?.setupState?.required);
  const startupOverlayVisible = isStartupPending(startupPhase);
  const startupStatusText = startupStatusLabel(startupPhase, loadingState);

  const handleConversationStartupState = (state: StartupReadinessState, detail?: string) => {
    if (state === 'warming') {
      if (startupPhaseRef.current !== 'ready' && detail) {
        setLoadingState(detail);
      }
      if (startupPhaseRef.current === 'starting_runtime' || startupPhaseRef.current === 'bootstrapping') {
        setStartupPhase('warming_ui');
      }
      return;
    }

    if (state === 'fatal_error') {
      failStartup(detail || 'The desktop chat UI failed to finish initializing.');
      return;
    }

    setStartupPhase('ready');
    setLoadingState('Ready');
  };

  const retryStartup = async () => {
    await beginStartup({ forceBootstrap: true });
  };

  useEffect(() => {
    if (
      startupPhase !== 'ready' ||
      !bootstrap?.setupState?.versioned ||
      bootstrap.setupState.required ||
      postStartupSetupNoticeSentRef.current
    ) {
      return;
    }
    postStartupSetupNoticeSentRef.current = true;
    setNotice((current) => current || 'Setup review is available from Settings.');
  }, [bootstrap?.setupState?.required, bootstrap?.setupState?.versioned, startupPhase]);

  const startLocalRuntime = async () => {
    setStartingRuntime(true);
    setError(null);
    setNotice(null);
    setLoadingState('starting local runtime');
    try {
      const payload = await startDesktopRuntime();
      if (!payload) {
        setError('Desktop runtime controls are unavailable in this shell.');
        setLoadingState('runtime controls unavailable');
        return;
      }
      applyBootstrap(payload);
      if (!payload.runtimeStatus?.ok || !payload.accessToken) {
        setError(
          payload.runtimeStatus?.detail ||
          'Local runtime did not become ready. Check the desktop runtime logs and try again.'
        );
      }
    } catch (runtimeError) {
      setError(String(runtimeError));
      setLoadingState('runtime start failed');
    } finally {
      setStartingRuntime(false);
    }
  };

  const stopLocalRuntimeNow = async () => {
    setStoppingRuntime(true);
    setError(null);
    setNotice(null);
    try {
      const payload = await stopDesktopRuntime();
      if (!payload) {
        setError('Desktop runtime stop controls are unavailable in this shell.');
        return;
      }
      applyBootstrap(payload);
    } catch (runtimeError) {
      setError(String(runtimeError));
    } finally {
      setStoppingRuntime(false);
    }
  };

  const saveSetup = async (values: Partial<DesktopSetupValues>) => {
    const changed = setupValuesChanged(values, bootstrap?.setupState?.values);
    if (!changed) {
      setError(null);
      setNotice(null);
      setShowSetup(false);
      return;
    }

    const runtimeWasRunning = Boolean(runtimeProcessDetected || localRuntimeReady);
    if (runtimeWasRunning && typeof window !== 'undefined' && typeof window.confirm === 'function') {
      const confirmed = window.confirm(
        'Saving these settings will restart the local agent runtime on this computer. Continue?'
      );
      if (!confirmed) {
        return;
      }
    }

    setSavingSetup(true);
    setError(null);
    setNotice(null);
    if (runtimeWasRunning) {
      setLoadingState('restarting local runtime');
    }
    try {
      const payload = await saveDesktopSetup(values);
      if (!payload) {
        setError('Desktop setup controls are unavailable in this shell.');
        return;
      }

      let finalPayload = payload;
      if (runtimeWasRunning && (!payload.runtimeStatus?.ok || !payload.accessToken)) {
        const deadline = Date.now() + DESKTOP_RUNTIME_RESTART_WAIT_MS;
        while (Date.now() < deadline) {
          await delay(600);
          const refreshed = await loadDesktopBootstrap({ force: true });
          if (refreshed) {
            finalPayload = refreshed;
          }
          const refreshedStatus = await loadDesktopRuntimeStatus().catch(() => null);
          if (refreshedStatus) {
            setRuntimeStatus(refreshedStatus);
            if (finalPayload) {
              finalPayload = {
                ...finalPayload,
                runtimeStatus: refreshedStatus,
              };
            }
          }
          if (finalPayload?.accessToken && finalPayload.runtimeStatus?.ok) {
            break;
          }
        }
      }

      applyBootstrap(finalPayload, { keepSetupClosed: true });
      const reconnected = Boolean(finalPayload.accessToken && finalPayload.runtimeStatus?.ok);
      const shouldResumeStartup = startupPhaseRef.current !== 'ready' && !finalPayload.setupState?.required;
      if (shouldResumeStartup) {
        setNotice('Settings saved. Continuing startup...');
        await beginStartup({ forceBootstrap: true });
        return;
      }
      if (runtimeWasRunning) {
        setNotice(
          reconnected
            ? 'Settings saved. Local runtime restarted and reconnected.'
            : 'Settings saved. Local runtime is still restarting.'
        );
      } else {
        setNotice(reconnected ? 'Settings saved. Local runtime connected.' : 'Settings saved. Start the local runtime when ready.');
      }
      await refreshUpdateStatus(true);
    } catch (saveError) {
      setError(String(saveError));
    } finally {
      setSavingSetup(false);
    }
  };

  const refreshMemory = async () => {
    setMemoryLoading(true);
    try {
      const next = await loadDesktopMemory();
      if (next) {
        setMemoryState(next);
      }
    } catch (memoryError) {
      setError(String(memoryError));
    } finally {
      setMemoryLoading(false);
    }
  };

  const saveMemory = async (content: string) => {
    setMemorySaving(true);
    setError(null);
    setNotice(null);
    try {
      const next = await saveDesktopMemory(content);
      if (!next) {
        setError('Desktop memory controls are unavailable in this shell.');
        return;
      }
      setMemoryState(next);
      setNotice('Memory saved.');
    } catch (memoryError) {
      setError(String(memoryError));
    } finally {
      setMemorySaving(false);
    }
  };

  const installVoicePack = async (packId: string) => {
    setVoicePackBusyId(packId);
    setError(null);
    setNotice(`Installing ${packId === 'hebrew_local' ? 'Hebrew' : 'English'} voice pack...`);
    try {
      const payload = await installDesktopVoicePack(packId);
      if (!payload) {
        setError('Voice pack controls are unavailable in this shell.');
        return;
      }
      applyBootstrap(payload, { keepSetupClosed: false });
      setNotice(`${packId === 'hebrew_local' ? 'Hebrew' : 'English'} voice pack installed.`);
    } catch (installError) {
      setError(installError instanceof Error ? installError.message : String(installError));
    } finally {
      setVoicePackBusyId(null);
    }
  };

  const removeVoicePack = async (packId: string) => {
    setVoicePackBusyId(packId);
    setError(null);
    setNotice(`Removing ${packId === 'hebrew_local' ? 'Hebrew' : 'English'} voice pack...`);
    try {
      const payload = await removeDesktopVoicePack(packId);
      if (!payload) {
        setError('Voice pack controls are unavailable in this shell.');
        return;
      }
      applyBootstrap(payload, { keepSetupClosed: false });
      setNotice(`${packId === 'hebrew_local' ? 'Hebrew' : 'English'} voice pack removed.`);
    } catch (removeError) {
      setError(removeError instanceof Error ? removeError.message : String(removeError));
    } finally {
      setVoicePackBusyId(null);
    }
  };

  const selectVoiceEngine = async (engine: string) => {
    setError(null);
    setNotice(`Switching voice path to ${engine === 'hebrew_local' ? 'Hebrew' : engine === 'english_local' ? 'English' : 'off'}...`);
    try {
      const payload = await setDesktopVoiceDefaultEngine(engine);
      if (!payload) {
        setError('Voice engine controls are unavailable in this shell.');
        return false;
      }
      applyBootstrap(payload, { keepSetupClosed: false });
      setNotice(
        engine === 'hebrew_local'
          ? 'Voice path switched to Hebrew.'
          : engine === 'english_local'
            ? 'Voice path switched to English.'
            : 'Voice input turned off.'
      );
      return true;
    } catch (selectionError) {
      setError(selectionError instanceof Error ? selectionError.message : String(selectionError));
      return false;
    }
  };

  const installUpdateNow = async () => {
    setInstallingUpdate(true);
    setError(null);
    try {
      const result = await installDesktopUpdate();
      if (result && result.message && !result.launched) {
        setError(String(result.message));
      }
    } catch (installError) {
      setError(String(installError));
    } finally {
      setInstallingUpdate(false);
    }
  };

  const runtimeSummary = runtimeLabel(runtimeStatus || bootstrap?.runtimeStatus || null, loadingState);

  useEffect(() => {
    if (!showSetup || memoryLoading || memoryState || !isDesktopEnvironment()) {
      return;
    }
    void refreshMemory();
  }, [showSetup, memoryLoading, memoryState]);

  if (startupPhase === 'setup_required') {
    return (
      <SafeAreaView edges={['top', 'left', 'right', 'bottom']} style={styles.startupPage}>
        {showSetup && bootstrap?.setupState ? (
          <View style={styles.startupSetupShell}>
            <DesktopSetupPanel
              setupState={bootstrap.setupState}
              saving={savingSetup}
              voicePackBusyId={voicePackBusyId}
              onSave={(values) => void saveSetup(values)}
              onInstallVoicePack={(packId) => void installVoicePack(packId)}
              onRemoveVoicePack={(packId) => void removeVoicePack(packId)}
              onDismiss={undefined}
              onOpenPath={(targetPath) => void openDesktopPath(targetPath)}
              onOpenChromeExtensions={() => void openDesktopChromeExtensions()}
              onCopyText={(textValue) => void copyDesktopText(textValue)}
              memoryState={memoryState}
              memoryLoading={memoryLoading}
              memorySaving={memorySaving}
              onReloadMemory={() => void refreshMemory()}
              onSaveMemory={(content) => void saveMemory(content)}
              updateStatus={updateStatus}
              checkingUpdates={checkingUpdates}
              installingUpdate={installingUpdate}
              onCheckUpdates={() => void refreshUpdateStatus(true)}
              onInstallUpdate={() => void installUpdateNow()}
            />
          </View>
        ) : (
          <View style={styles.startupGateCard}>
            <StartupGlyph />
            <Text style={styles.startupGateTitle}>Finish setup to start EmploAI</Text>
            <Text style={styles.startupGateText}>
              The desktop app is installed, but the local backend cannot finish starting until the required setup values are saved.
            </Text>
            <Pressable style={styles.startupPrimaryButton} onPress={() => setShowSetup(true)}>
              <Text style={styles.startupPrimaryButtonText}>Open Setup</Text>
            </Pressable>
          </View>
        )}
      </SafeAreaView>
    );
  }

  if (startupPhase === 'startup_error') {
    return (
      <SafeAreaView edges={['top', 'left', 'right', 'bottom']} style={styles.startupPage}>
        {showSetup && bootstrap?.setupState ? (
          <View style={styles.startupSetupShell}>
            <DesktopSetupPanel
              setupState={bootstrap.setupState}
              saving={savingSetup}
              voicePackBusyId={voicePackBusyId}
              onSave={(values) => void saveSetup(values)}
              onInstallVoicePack={(packId) => void installVoicePack(packId)}
              onRemoveVoicePack={(packId) => void removeVoicePack(packId)}
              onDismiss={() => setShowSetup(false)}
              onOpenPath={(targetPath) => void openDesktopPath(targetPath)}
              onOpenChromeExtensions={() => void openDesktopChromeExtensions()}
              onCopyText={(textValue) => void copyDesktopText(textValue)}
              memoryState={memoryState}
              memoryLoading={memoryLoading}
              memorySaving={memorySaving}
              onReloadMemory={() => void refreshMemory()}
              onSaveMemory={(content) => void saveMemory(content)}
              updateStatus={updateStatus}
              checkingUpdates={checkingUpdates}
              installingUpdate={installingUpdate}
              onCheckUpdates={() => void refreshUpdateStatus(true)}
              onInstallUpdate={() => void installUpdateNow()}
            />
          </View>
        ) : (
          <View style={styles.startupGateCard}>
            <StartupGlyph />
            <Text style={styles.startupGateTitle}>Startup needs attention</Text>
            <Text style={styles.startupGateText}>
              {startupErrorDetail || error || 'The desktop app could not finish becoming ready.'}
            </Text>
            <View style={styles.startupActionRow}>
              <Pressable
                style={[styles.startupPrimaryButton, startingRuntime ? styles.startupPrimaryButtonDisabled : null]}
                onPress={() => void retryStartup()}
                disabled={startingRuntime}
              >
                <Text style={styles.startupPrimaryButtonText}>{startingRuntime ? 'Retrying...' : 'Retry Startup'}</Text>
              </Pressable>
              {bootstrap?.setupState ? (
                <Pressable style={styles.startupSecondaryButton} onPress={() => setShowSetup(true)}>
                  <Text style={styles.startupSecondaryButtonText}>Open Setup</Text>
                </Pressable>
              ) : null}
            </View>
          </View>
        )}
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView edges={['top', 'left', 'right', 'bottom']} style={styles.page}>
      {/* ── Compact header bar ── */}
      <View style={styles.headerBar}>
        <View style={styles.headerLeft}>
          <View style={[styles.statusDot, localRuntimeReady ? styles.statusDotOnline : styles.statusDotOffline]} />
          <Text style={styles.headerTitle}>EmploAI</Text>
          <Text style={styles.headerMeta}>{runtimeSummary}</Text>
          {bootstrap?.currentSessionId ? (
            <Text style={styles.headerSession}>· {bootstrap.currentSessionId.slice(0, 8)}</Text>
          ) : null}
        </View>
        <View style={styles.headerRight}>
          <Text style={styles.headerVersion}>
            {bootstrap?.releaseVersion || bootstrap?.setupState?.releaseVersion || 'beta'}
          </Text>
          <Pressable
            style={[
              styles.headerActionButton,
              runtimeProcessDetected ? styles.headerActionWarn : styles.headerActionPrimary,
              (startingRuntime || stoppingRuntime || (setupBlocksRuntime && !runtimeProcessDetected)) ? styles.headerActionDisabled : null,
            ]}
            onPress={() => void (runtimeProcessDetected ? stopLocalRuntimeNow() : startLocalRuntime())}
            disabled={startingRuntime || stoppingRuntime || (setupBlocksRuntime && !runtimeProcessDetected)}
          >
            <Text style={[styles.headerActionText, runtimeProcessDetected ? styles.headerActionTextLight : null]}>
              {stoppingRuntime ? '■ Stopping' : runtimeProcessDetected ? '■ Stop' : startingRuntime ? '▶ Starting' : '▶ Start'}
            </Text>
          </Pressable>
        </View>
      </View>

      {/* ── Error banner ── */}
      {error ? (
      <View style={styles.errorBanner}>
          <Text style={styles.errorBannerText}>⚠ {error}</Text>
        </View>
      ) : null}

      {notice && !error ? (
        <View style={styles.noticeBanner}>
          <Text style={styles.noticeBannerText}>{notice}</Text>
        </View>
      ) : null}

      {/* ── Main content: conversation fills all remaining space ── */}
      {setupBlocksRuntime ? (
        <View style={styles.tabBody}>
          <View style={styles.loadingCard}>
            <Text style={styles.loadingTitle}>Finish setup to start the local agent</Text>
            <Text style={styles.loadingText}>
              The desktop app is installed and running, but the local backend will stay offline until the required setup values are saved.
            </Text>
            <Pressable style={styles.runtimeButton} onPress={() => setShowSetup(true)}>
              <Text style={styles.runtimeButtonText}>Open Setup</Text>
            </Pressable>
          </View>
        </View>
      ) : activeTab === 'local' ? (
        <View style={styles.tabBody}>
          {bootstrap && localRuntimeReady ? (
            <DesktopConversationView
              apiBaseUrl={bootstrap.apiBaseUrl}
              token={bootstrap.accessToken}
              initialSessionId={requestedSessionId || bootstrap.currentSessionId || undefined}
              runtimeMode={bootstrap.runtimeMode}
              runtimeStatus={runtimeStatus || bootstrap.runtimeStatus || null}
              envFilePath={bootstrap.envFilePath || undefined}
              defaultInterruptPolicy={bootstrap.setupState?.values.INTERRUPT_POLICY_DEFAULT || 'none'}
              voicePackState={bootstrap.setupState?.voicePacks || null}
              voiceStatus={bootstrap.setupState?.voiceStatus || null}
              onSelectVoiceEngine={(engine) => selectVoiceEngine(engine)}
              onStartupStateChange={handleConversationStartupState}
              onOpenSetup={() => setShowSetup(true)}
              setupOpen={showSetup}
            />
          ) : (
            <View style={styles.loadingCard}>
              <Text style={styles.loadingTitle}>Desktop shell is running</Text>
              <Text style={styles.loadingText}>
                Start the runtime to host the agent on this computer, or open setup to configure keys, updates, and local tools.
              </Text>
              <View style={styles.offlineMetaCard}>
                <Text style={styles.offlineMetaLabel}>Local runtime</Text>
                <Text style={styles.offlineMetaValue}>{runtimeSummary}</Text>
                <Text style={styles.offlineMetaText}>
                  {runtimeProcessDetected
                    ? 'Runtime process detected but unhealthy. Stop it, then start again.'
                    : runtimeStatus?.detail || bootstrap?.runtimeStatus?.detail || 'No local runtime attached yet.'}
                </Text>
              </View>
              <View style={styles.offlineActionRow}>
                <Pressable
                  style={[
                    runtimeProcessDetected ? styles.secondaryRuntimeButton : styles.runtimeButton,
                    (runtimeProcessDetected ? stoppingRuntime : startingRuntime) ? styles.runtimeButtonDisabled : null,
                  ]}
                  onPress={() => void (runtimeProcessDetected ? stopLocalRuntimeNow() : startLocalRuntime())}
                  disabled={runtimeProcessDetected ? stoppingRuntime : startingRuntime}
                >
                  <Text style={runtimeProcessDetected ? styles.secondaryRuntimeButtonText : styles.runtimeButtonText}>
                    {runtimeProcessDetected
                      ? stoppingRuntime ? 'Stopping...' : 'Force Stop Runtime'
                      : startingRuntime ? 'Starting...' : 'Start Local Runtime'}
                  </Text>
                </Pressable>
              </View>
            </View>
          )}
        </View>
      ) : (
        <ScrollView style={styles.tabBody} contentContainerStyle={styles.remoteBody}>
          <View style={styles.remoteIntro}>
            <Text style={styles.remoteIntroTitle}>Remote runtime control is planned</Text>
            <Text style={styles.remoteIntroText}>
              This tab accounts for hosted agents and multi-computer orchestration. Only the local tab is functional in this beta.
            </Text>
          </View>
          {remoteRuntimes.map((runtime) => (
            <View key={runtime.id} style={styles.remoteCard}>
              <View style={styles.remoteHeader}>
                <View>
                  <Text style={styles.remoteTitle}>{runtime.name}</Text>
                  <Text style={styles.remoteMeta}>{runtime.hostLabel}</Text>
                </View>
                <View style={styles.remoteStatusBadge}>
                  <Text style={styles.remoteStatusText}>{runtime.status}</Text>
                </View>
              </View>
              <Text style={styles.remoteDetail}>{runtime.detail}</Text>
            </View>
          ))}
        </ScrollView>
      )}
      {startupOverlayVisible ? (
        <View style={styles.startupOverlay}>
          <View style={styles.startupOverlayCard}>
            <StartupGlyph />
            <Text style={styles.startupOverlayTitle}>EmploAI</Text>
            <Text style={styles.startupOverlayText}>{startupStatusText}</Text>
          </View>
        </View>
      ) : null}
      {showSetup && bootstrap?.setupState ? (
        <View style={styles.setupOverlay} pointerEvents="box-none">
          <View style={[styles.setupOverlayBackdrop, webBackdropBlurStyle]} />
          <View style={styles.setupOverlayFrame} pointerEvents="box-none">
            <View style={styles.setupOverlaySurface}>
              <DesktopSetupPanel
                setupState={bootstrap.setupState}
                saving={savingSetup}
                voicePackBusyId={voicePackBusyId}
                onSave={(values) => void saveSetup(values)}
                onInstallVoicePack={(packId) => void installVoicePack(packId)}
                onRemoveVoicePack={(packId) => void removeVoicePack(packId)}
                onDismiss={bootstrap.setupState.required ? undefined : () => setShowSetup(false)}
                onOpenPath={(targetPath) => void openDesktopPath(targetPath)}
                onOpenChromeExtensions={() => void openDesktopChromeExtensions()}
                onCopyText={(textValue) => void copyDesktopText(textValue)}
                memoryState={memoryState}
                memoryLoading={memoryLoading}
                memorySaving={memorySaving}
                onReloadMemory={() => void refreshMemory()}
                onSaveMemory={(content) => void saveMemory(content)}
                updateStatus={updateStatus}
                checkingUpdates={checkingUpdates}
                installingUpdate={installingUpdate}
                onCheckUpdates={() => void refreshUpdateStatus(true)}
                onInstallUpdate={() => void installUpdateNow()}
              />
            </View>
          </View>
        </View>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: {
    flex: 1,
    backgroundColor: '#07111f',
  },
  startupPage: {
    flex: 1,
    backgroundColor: '#07111f',
    paddingHorizontal: 24,
    paddingVertical: 28,
    justifyContent: 'center',
  },
  startupSetupShell: {
    width: '100%',
    maxWidth: 1120,
    alignSelf: 'center',
  },
  startupGateCard: {
    width: '100%',
    maxWidth: 560,
    alignSelf: 'center',
    alignItems: 'center',
    gap: 14,
    paddingHorizontal: 28,
    paddingVertical: 34,
    borderRadius: 28,
    backgroundColor: '#0f172d',
    borderWidth: 1,
    borderColor: '#223052',
  },
  startupGateTitle: {
    color: '#f6fbff',
    fontSize: 24,
    fontWeight: '800',
    textAlign: 'center',
  },
  startupGateText: {
    color: '#97add3',
    fontSize: 14,
    lineHeight: 21,
    textAlign: 'center',
    maxWidth: 420,
  },
  startupActionRow: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 6,
    flexWrap: 'wrap',
    justifyContent: 'center',
  },
  startupPrimaryButton: {
    minWidth: 160,
    borderRadius: 999,
    paddingHorizontal: 18,
    paddingVertical: 12,
    backgroundColor: '#d4ff65',
    alignItems: 'center',
  },
  startupPrimaryButtonDisabled: {
    opacity: 0.55,
  },
  startupPrimaryButtonText: {
    color: '#081324',
    fontSize: 13,
    fontWeight: '800',
  },
  startupSecondaryButton: {
    minWidth: 140,
    borderRadius: 999,
    paddingHorizontal: 18,
    paddingVertical: 12,
    borderWidth: 1,
    borderColor: '#30456d',
    backgroundColor: '#13203a',
    alignItems: 'center',
  },
  startupSecondaryButtonText: {
    color: '#d7e7ff',
    fontSize: 13,
    fontWeight: '700',
  },
  startupOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(7, 17, 31, 0.96)',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 50,
  },
  startupOverlayCard: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: 14,
    paddingHorizontal: 28,
    paddingVertical: 30,
    borderRadius: 28,
    backgroundColor: 'rgba(15, 23, 45, 0.88)',
    borderWidth: 1,
    borderColor: '#223052',
    minWidth: 300,
  },
  startupOverlayTitle: {
    color: '#f6fbff',
    fontSize: 24,
    fontWeight: '800',
  },
  startupOverlayText: {
    color: '#8ea4cb',
    fontSize: 14,
    textAlign: 'center',
  },
  setupOverlay: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 45,
  },
  setupOverlayBackdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(4, 10, 20, 0.42)',
  },
  setupOverlayFrame: {
    ...StyleSheet.absoluteFillObject,
    paddingHorizontal: 24,
    paddingVertical: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  setupOverlaySurface: {
    width: '100%',
    maxWidth: 1320,
    maxHeight: '92%',
    shadowColor: '#01040b',
    shadowOpacity: 0.38,
    shadowRadius: 26,
    shadowOffset: { width: 0, height: 18 },
    elevation: 20,
  },
  startupGlyphFrame: {
    width: 74,
    height: 74,
    alignItems: 'center',
    justifyContent: 'center',
  },
  startupGlyphCore: {
    position: 'absolute',
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: '#173158',
    borderWidth: 1,
    borderColor: '#284a81',
  },
  startupGlyphOrbit: {
    width: 66,
    height: 66,
    borderRadius: 33,
    borderWidth: 1,
    borderColor: '#284064',
    alignItems: 'center',
    justifyContent: 'flex-start',
    paddingTop: 3,
  },
  startupGlyphDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#d4ff65',
  },
  /* ── Compact header bar ── */
  headerBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: '#0c1729',
    borderBottomWidth: 1,
    borderBottomColor: '#1a2a48',
    minHeight: 48,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  statusDotOnline: {
    backgroundColor: '#4ade80',
  },
  statusDotOffline: {
    backgroundColor: '#6b7280',
  },
  headerTitle: {
    color: '#f6fbff',
    fontSize: 15,
    fontWeight: '800',
  },
  headerMeta: {
    color: '#7f97bc',
    fontSize: 13,
  },
  headerSession: {
    color: '#5472a4',
    fontSize: 12,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  headerVersion: {
    color: '#5472a4',
    fontSize: 12,
  },
  headerActionButton: {
    borderRadius: 0,
    paddingHorizontal: 14,
    paddingVertical: 6,
    backgroundColor: '#d4ff65',
  },
  headerActionPrimary: {
    backgroundColor: '#d4ff65',
  },
  headerActionWarn: {
    backgroundColor: '#5f3440',
  },
  headerActionDisabled: {
    opacity: 0.5,
  },
  headerActionText: {
    color: '#081324',
    fontSize: 12,
    fontWeight: '800',
  },
  headerActionTextLight: {
    color: '#f6fbff',
  },
  headerGearButton: {
    width: 36,
    height: 36,
    borderRadius: 0,
    backgroundColor: '#13203a',
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerGearText: {
    color: '#9fb4d8',
    fontSize: 18,
  },
  /* ── Error banner ── */
  errorBanner: {
    backgroundColor: '#3a1620',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#6a3040',
  },
  errorBannerText: {
    color: '#ffd3db',
    fontSize: 13,
  },
  noticeBanner: {
    backgroundColor: '#102c24',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#235545',
  },
  noticeBannerText: {
    color: '#c9f7df',
    fontSize: 13,
    fontWeight: '700',
  },
  /* ── Collapsible controls panel ── */
  controlsPanel: {
    backgroundColor: '#0f182e',
    borderBottomWidth: 1,
    borderBottomColor: '#1e2b47',
    maxHeight: 280,
  },
  controlsPanelHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 16,
    paddingTop: 14,
    paddingBottom: 4,
  },
  controlsPanelTitle: {
    color: '#f6fbff',
    fontSize: 18,
    fontWeight: '800',
  },
  controlsPanelCloseButton: {
    borderRadius: 999,
    backgroundColor: '#1a2a48',
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  controlsPanelCloseText: {
    color: '#cfe0ff',
    fontSize: 12,
    fontWeight: '800',
  },
  controlsPanelScroll: {
    flex: 1,
  },
  controlsPanelContent: {
    padding: 16,
    gap: 16,
  },
  controlsSection: {
    gap: 8,
  },
  controlsSectionTitle: {
    color: '#7f97bc',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  controlsButtonRow: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
  },
  controlsButton: {
    borderRadius: 999,
    backgroundColor: '#1a2a48',
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  controlsButtonActive: {
    backgroundColor: '#d4ff65',
  },
  controlsButtonDisabled: {
    opacity: 0.45,
  },
  controlsButtonText: {
    color: '#cfe0ff',
    fontSize: 13,
    fontWeight: '700',
  },
  controlsButtonTextActive: {
    color: '#081324',
  },
  controlsDetailText: {
    color: '#b7c9e8',
    fontSize: 13,
    lineHeight: 19,
  },
  controlsMetaText: {
    color: '#7f97bc',
    fontSize: 12,
  },
  controlsUpdateButton: {
    borderRadius: 12,
    backgroundColor: '#d4ff65',
    paddingHorizontal: 14,
    paddingVertical: 8,
    alignSelf: 'flex-start',
  },
  controlsUpdateButtonText: {
    color: '#081324',
    fontWeight: '800',
    fontSize: 13,
  },
  /* ── Main content area ── */
  tabBody: {
    flex: 1,
  },
  loadingCard: {
    flex: 1,
    backgroundColor: '#101a31',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    gap: 10,
  },
  loadingTitle: {
    color: '#f6fbff',
    fontSize: 22,
    fontWeight: '800',
    textAlign: 'center',
  },
  loadingText: {
    color: '#9db1d2',
    textAlign: 'center',
    maxWidth: 640,
    lineHeight: 21,
  },
  offlineMetaCard: {
    width: '100%',
    maxWidth: 720,
    borderRadius: 20,
    backgroundColor: '#0a1324',
    borderWidth: 1,
    borderColor: '#1e2b47',
    padding: 18,
    gap: 6,
  },
  offlineMetaLabel: {
    color: '#8ea4cb',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  offlineMetaValue: {
    color: '#f6fbff',
    fontSize: 20,
    fontWeight: '800',
  },
  offlineMetaText: {
    color: '#9db1d2',
    lineHeight: 20,
  },
  offlineActionRow: {
    flexDirection: 'row',
    gap: 10,
  },
  runtimeButton: {
    borderRadius: 999,
    backgroundColor: '#d4ff65',
    paddingHorizontal: 18,
    paddingVertical: 12,
  },
  runtimeButtonDisabled: {
    opacity: 0.7,
  },
  runtimeButtonText: {
    color: '#081324',
    fontWeight: '800',
  },
  secondaryRuntimeButton: {
    borderRadius: 999,
    backgroundColor: '#17253f',
    paddingHorizontal: 18,
    paddingVertical: 12,
  },
  secondaryRuntimeButtonText: {
    color: '#d4e2fb',
    fontWeight: '800',
  },
  /* ── Remote tab ── */
  remoteBody: {
    gap: 16,
    padding: 16,
  },
  remoteIntro: {
    borderRadius: 20,
    backgroundColor: '#111c32',
    borderWidth: 1,
    borderColor: '#1e2e52',
    padding: 20,
    gap: 8,
  },
  remoteIntroTitle: {
    color: '#f6fbff',
    fontSize: 20,
    fontWeight: '800',
  },
  remoteIntroText: {
    color: '#a7bbdc',
    lineHeight: 21,
  },
  remoteCard: {
    borderRadius: 20,
    backgroundColor: '#0f182e',
    borderWidth: 1,
    borderColor: '#1d2b49',
    padding: 18,
    gap: 12,
  },
  remoteHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  remoteTitle: {
    color: '#ffffff',
    fontSize: 18,
    fontWeight: '800',
  },
  remoteMeta: {
    color: '#94abd1',
  },
  remoteStatusBadge: {
    borderRadius: 999,
    backgroundColor: '#233656',
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  remoteStatusText: {
    color: '#a8dbff',
    fontWeight: '800',
    textTransform: 'uppercase',
    fontSize: 11,
  },
  remoteDetail: {
    color: '#a7bbdc',
    lineHeight: 20,
  },
});
