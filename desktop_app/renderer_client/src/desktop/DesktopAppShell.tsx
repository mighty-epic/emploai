import { useEffect, useRef, useState } from 'react';
import { useLocalSearchParams } from 'expo-router';

import {
  configureAgent,
  configureHeadlessRuntime,
  controlAgentRun,
  approvePendingConfirmation,
  createPendingConfirmation,
  denyPendingConfirmation,
  createTelegramBotConfig,
  fetchAgentOverview,
  fetchAgentConfig,
  fetchPendingConfirmations,
  fetchRecoveryItems,
  fetchRuntimeOrchestratorStatus,
  fetchSessions,
  fetchTelegramBotConfigs,
  permanentlyDeleteRecoveryItem,
  restoreRecoveryItem,
  restoreWorkspaceFiles,
  updateTelegramBotConfig,
  deleteTelegramBotConfig,
  warmVoiceRuntime,
  type RuntimeOrchestratorStatus,
  type PendingConfirmation,
  type RecoveryArchiveItem,
  type SessionSummary,
  type TelegramBotConfig,
} from '@/lib/appApi';
import { describeError, shortStatusText, userFacingError } from '../../lib/diagnostics';
import { firstSignupPasswordError } from '@/lib/remoteAuthPasswordPolicy';
import {
  LIVE_APPLY_SETUP_FIELDS,
  RESTART_REQUIRED_SETUP_FIELDS,
  SETUP_PROVIDER_SECRET_LABELS,
  changedSetupFields,
  hasFilledRestartRequiredSetupSecret,
  hasFilledSetupSecret,
  sanitizeLocalSetupValues,
  setupValuesForRuntimeSave,
} from './setupValues';
import { useConfirmation } from '@/components/ConfirmationDialog';
import { createApprovedConfirmation } from '@/lib/sharedConfirmations';
import { createDesktopAppShellActions } from './DesktopAppShellActions';
import { DesktopAppShellView } from './DesktopAppShellView';
import { createLatestRequestGate } from './desktopAsyncCoordination';
import type { DesktopMode, RemoteRuntimeSummary } from './models';
import { profileToSharedSettingsDraft, type SharedSettingsDraft } from '@/lib/accountProfile';
import {
  checkDesktopUpdates,
  copyDesktopText,
  createDesktopRemotePairingToken,
  applyDesktopAccountData,
  deleteDesktopRemoteAccountData,
  deleteDesktopRemoteSecret,
  hideDesktopWindowForSleepMode,
  installDesktopVoicePack,
  installDesktopUpdate,
  isDesktopEnvironment,
  loadDesktopMemory,
  loadDesktopBootstrap,
  normalizeDesktopBootstrapRuntimeStatus,
  loadDesktopRemoteAuthStatus,
  loadDesktopRuntimeStatus,
  loginDesktopRemoteAuth,
  loginDesktopRemoteGoogle,
  logoutDesktopRemoteAuth,
  listDesktopRemoteSecrets,
  listDesktopRemoteAccountDesktops,
  loadDesktopFleetSnapshot,
  openDesktopChromeExtensions,
  openDesktopPath,
  removeDesktopVoicePack,
  registerDesktopRemoteAuth,
  resendDesktopRemoteAuthOtp,
  saveDesktopSetupSecrets,
  saveDesktopRemoteSecrets,
  saveDesktopMemory,
  saveDesktopSetup,
  setDesktopVoiceDefaultEngine,
  startDesktopRuntime,
  stopDesktopRuntime,
  subscribeDesktopRuntime,
  verifyDesktopRemoteAuthOtp,
  type DesktopBootstrap,
  type DesktopMemoryState,
  type DesktopRemoteAuthOtpChallenge,
  type DesktopRemoteAuthStatus,
  type DesktopRemoteSecretItem,
  type DesktopRuntimeStatus,
  type DesktopTelegramStatus,
  type DesktopSetupValues,
  type DesktopUpdateStatus,
  type DesktopVoicePackInstallProgress,
} from '@/lib/desktopBridge';

function normalizeParam(value: string | string[] | undefined) {
  if (Array.isArray(value)) {
    return value[0];
  }
  return value;
}

type DesktopSurfaceRoute = 'chat' | 'fleet' | 'jarvis';

function normalizeDesktopTab(value: string | undefined): { mode: DesktopMode; surface: DesktopSurfaceRoute } {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'remote') {
    return { mode: 'remote', surface: 'chat' };
  }
  if (normalized === 'fleet') {
    return { mode: 'local', surface: 'fleet' };
  }
  if (normalized === 'jarvis' || normalized === 'agent') {
    return { mode: 'local', surface: 'jarvis' };
  }
  return { mode: 'local', surface: 'chat' };
}

function runtimeLabel(runtimeStatus: DesktopRuntimeStatus | null, fallback: string) {
  if (!runtimeStatus) {
    return fallback;
  }
  return runtimeStatus.degraded ? `${runtimeStatus.state} · degraded` : runtimeStatus.state;
}

function telegramStatusLabel(status: DesktopTelegramStatus | null | undefined) {
  if (!status) {
    return 'Telegram unknown';
  }
  switch (status.state) {
    case 'running':
      return 'Telegram ready';
    case 'starting':
      return 'Telegram starting';
    case 'degraded':
      return 'Telegram degraded';
    case 'not_configured':
      return 'Telegram setup needed';
    case 'disabled':
      return 'Telegram off';
    default:
      return 'Telegram offline';
  }
}

function desktopVoicePackLabel(packId: string) {
  if (packId === 'hebrew_local') {
    return 'Hebrew';
  }
  if (packId === 'kokoro_tts') {
    return 'Kokoro';
  }
  if (packId === 'kyutai_clone_tts') {
    return 'Kyutai clone';
  }
  return 'English';
}

function delay(ms: number) {
  return new Promise((resolve) => {
    globalThis.setTimeout(resolve, ms);
  });
}

async function fetchDesktopApiJson<T>(url: string, token: string, timeoutMs = 5000): Promise<T> {
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const timeoutId = controller
    ? globalThis.setTimeout(() => controller.abort(), timeoutMs)
    : null;
  try {
    const response = await fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
      signal: controller?.signal,
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => '');
      throw new Error(`${response.status} ${response.statusText}${detail ? `: ${detail}` : ''}`);
    }
    return (await response.json()) as T;
  } finally {
    if (timeoutId != null) {
      globalThis.clearTimeout(timeoutId);
    }
  }
}

const DESKTOP_RUNTIME_RESTART_WAIT_MS = 40_000;
const STARTUP_INITIAL_TIMEOUT_SECONDS = 20;
const STARTUP_FIRST_AUTO_RETRY_TIMEOUT_SECONDS = 60;
const STARTUP_RETRY_INCREMENT_SECONDS = 10;
const STARTUP_RETRY_MAX_TIMEOUT_SECONDS = 120;
const STARTUP_WATCHDOG_GRACE_MS = 20_000;
const STATUS_BANNER_AUTO_DISMISS_MS = 60_000;
const RUNTIME_HEALTH_POLL_MS = 5_000;
const RUNTIME_OFFLINE_CONFIRMATIONS = 2;

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

function clampStartupTimeoutSeconds(timeoutSeconds: number) {
  return Math.min(
    Math.max(STARTUP_INITIAL_TIMEOUT_SECONDS, Math.trunc(timeoutSeconds)),
    STARTUP_RETRY_MAX_TIMEOUT_SECONDS
  );
}

function nextStartupRetryTimeoutSeconds(currentTimeoutSeconds: number) {
  return clampStartupTimeoutSeconds(currentTimeoutSeconds + STARTUP_RETRY_INCREMENT_SECONDS);
}

function runtimeFailureDetail(status: DesktopRuntimeStatus | null | undefined) {
  if (!status || status.ok) {
    return null;
  }
  const detail = String(status.detail || '').trim();
  if (!detail) {
    return null;
  }
  return detail;
}

function isLaunchableRuntimePrestartDetail(detail: string | null | undefined, canLaunchLocalRuntime: boolean | null | undefined) {
  if (!canLaunchLocalRuntime) {
    return false;
  }
  const normalized = String(detail || '').trim().toLowerCase();
  if (!normalized) {
    return false;
  }
  return (
    normalized.includes('desktop runtime is offline and auto-start is disabled') ||
    normalized.includes('no compatible local runtime responded on the configured desktop host/port')
  );
}

function isRuntimeConnectivityMessage(message: string | null | undefined) {
  const normalized = String(message || '').trim().toLowerCase();
  if (!normalized) {
    return false;
  }
  return (
    normalized.includes('failed to fetch') ||
    normalized.includes('networkerror') ||
    normalized.includes('no compatible local runtime responded on the configured desktop host/port') ||
    normalized.includes('local runtime did not become ready') ||
    normalized.includes('desktop runtime did not become ready') ||
    normalized.includes('runtime did not become ready within') ||
    normalized.includes('the local runtime stopped before the desktop app became ready')
  );
}

function isStartupTimeoutMessage(message: string | null | undefined) {
  const normalized = String(message || '').trim().toLowerCase();
  if (!normalized) {
    return false;
  }
  return (
    normalized.includes('no compatible local runtime responded on the configured desktop host/port') ||
    normalized.includes('local runtime did not become ready') ||
    normalized.includes('desktop runtime did not become ready') ||
    normalized.includes('runtime did not become ready within') ||
    normalized.includes('startup is taking longer than expected')
  );
}

function isAuthTokenMessage(message: string | null | undefined) {
  const normalized = String(message || '').trim().toLowerCase();
  if (!normalized) {
    return false;
  }
  return (
    normalized.includes('401') ||
    normalized.includes('unauthorized') ||
    normalized.includes('invalid token') ||
    normalized.includes('missing bearer token')
  );
}

async function waitForDesktopApiReady(
  apiBaseUrl: string,
  token: string,
  timeoutMs: number,
) {
  const deadline = Date.now() + timeoutMs;
  let lastError: string | null = null;

  while (Date.now() < deadline) {
    try {
      const profile = await fetchDesktopApiJson<{ current_session_id?: string | null }>(
        `${apiBaseUrl}/api/app/me`,
        token,
        5000,
      );
      await fetchDesktopApiJson<unknown[]>(
        `${apiBaseUrl}/api/app/sessions`,
        token,
        5000,
      );
      return profile;
    } catch (error) {
      lastError = describeError(error);
      if (isAuthTokenMessage(lastError)) {
        throw new Error(lastError);
      }
      await delay(600);
    }
  }

  throw new Error(
    lastError
      ? `Local API did not finish becoming responsive: ${lastError}`
      : 'Local API did not finish becoming responsive.',
  );
}

export function DesktopAppShell() {
  const { confirm: confirmAction, confirmationDialog } = useConfirmation();
  const params = useLocalSearchParams<{ sessionId?: string | string[]; tab?: string | string[]; setup?: string | string[]; settings?: string | string[] }>();
  const requestedSessionId = normalizeParam(params.sessionId);
  const requestedTab = normalizeParam(params.tab);
  const requestedSettings = normalizeParam(params.setup) === '1' || normalizeParam(params.settings) === '1';
  const requestedDesktopRoute = normalizeDesktopTab(requestedTab);
  const requestedDesktopMode = requestedDesktopRoute.mode;
  const requestedSurfaceMode = requestedDesktopRoute.surface;

  const [activeTab, setActiveTab] = useState<DesktopMode>('local');
  const [bootstrap, setBootstrap] = useState<DesktopBootstrap | null>(null);
  const [runtimeStatus, setRuntimeStatus] = useState<DesktopRuntimeStatus | null>(null);
  const [updateStatus, setUpdateStatus] = useState<DesktopUpdateStatus | null>(null);
  const [loadingState, setLoadingState] = useState('bootstrapping desktop shell');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [conversationSidebarToggleSignal, setConversationSidebarToggleSignal] = useState(0);
  const [startupPhase, setStartupPhase] = useState<StartupPhase>('bootstrapping');
  const [startupErrorDetail, setStartupErrorDetail] = useState<string | null>(null);
  const [startupCurrentTimeoutSeconds, setStartupCurrentTimeoutSeconds] = useState(STARTUP_INITIAL_TIMEOUT_SECONDS);
  const [showSetup, setShowSetup] = useState(requestedSettings);
  const [startingRuntime, setStartingRuntime] = useState(false);
  const [stoppingRuntime, setStoppingRuntime] = useState(false);
  const [savingSetup, setSavingSetup] = useState(false);
  const [voicePackBusyId, setVoicePackBusyId] = useState<string | null>(null);
  const [voicePackProgress, setVoicePackProgress] = useState<DesktopVoicePackInstallProgress | null>(null);
  const [checkingUpdates, setCheckingUpdates] = useState(false);
  const [installingUpdate, setInstallingUpdate] = useState(false);
  const [memoryState, setMemoryState] = useState<DesktopMemoryState | null>(null);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [memorySaving, setMemorySaving] = useState(false);
  const [telegramBotConfigs, setTelegramBotConfigs] = useState<TelegramBotConfig[]>([]);
  const [orchestratorStatus, setOrchestratorStatus] = useState<RuntimeOrchestratorStatus | null>(null);
  const [setupSessions, setSetupSessions] = useState<SessionSummary[]>([]);
  const [setupMaxTurns, setSetupMaxTurns] = useState<number | null>(null);
  const [recoveryItems, setRecoveryItems] = useState<RecoveryArchiveItem[]>([]);
  const [pendingConfirmations, setPendingConfirmations] = useState<PendingConfirmation[]>([]);
  const [recoveryBusyId, setRecoveryBusyId] = useState<string | null>(null);
  const [recoveryMessage, setRecoveryMessage] = useState<string | null>(null);
  const [remoteAuthStatus, setRemoteAuthStatus] = useState<DesktopRemoteAuthStatus | null>(null);
  const [sharedSettingsDraft, setSharedSettingsDraft] = useState<SharedSettingsDraft>(() => profileToSharedSettingsDraft(null));
  const [sharedSettingsSaving, setSharedSettingsSaving] = useState(false);
  const [sharedSettingsStatus, setSharedSettingsStatus] = useState<string | null>(null);
  const [remoteAuthLoading, setRemoteAuthLoading] = useState(true);
  const [remoteAuthBusy, setRemoteAuthBusy] = useState(false);
  const [remoteAuthLoggingOut, setRemoteAuthLoggingOut] = useState(false);
  const [remoteAuthMode, setRemoteAuthMode] = useState<'login' | 'signup'>('login');
  const [remoteAuthEmail, setRemoteAuthEmail] = useState('');
  const [remoteAuthPassword, setRemoteAuthPassword] = useState('');
  const [remoteAuthConfirmPassword, setRemoteAuthConfirmPassword] = useState('');
  const [remoteAuthDisplayName, setRemoteAuthDisplayName] = useState('');
  const [remoteAuthRememberMe, setRemoteAuthRememberMe] = useState(false);
  const [remoteAuthOtpChallenge, setRemoteAuthOtpChallenge] = useState<DesktopRemoteAuthOtpChallenge | null>(null);
  const [remoteAuthOtpCode, setRemoteAuthOtpCode] = useState('');
  const [remoteAuthMessage, setRemoteAuthMessage] = useState('');
  const [remoteSecretItems, setRemoteSecretItems] = useState<DesktopRemoteSecretItem[]>([]);
  const [remoteSecretsBusy, setRemoteSecretsBusy] = useState(false);
  const [remoteSecretsMessage, setRemoteSecretsMessage] = useState<string | null>(null);
  const [remoteAccountHydrating, setRemoteAccountHydrating] = useState(false);
  const startupPhaseRef = useRef<StartupPhase>('bootstrapping');
  const startupWatchdogTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startupFlowInFlightRef = useRef(false);
  const startupInitializedRef = useRef(false);
  const startupAutoRetryAttemptedRef = useRef(false);
  const startupAutoRetryInFlightRef = useRef(false);
  const startupDeferredRetryTimeoutRef = useRef<number | null>(null);
  const startupRecoveryInFlightRef = useRef(false);
  const postStartupRefreshKeyRef = useRef('');
  const postStartupSetupNoticeSentRef = useRef(false);
  const previousTelegramStateRef = useRef<string | null>(null);
  const bootstrapRef = useRef<DesktopBootstrap | null>(null);
  const runtimeStatusRef = useRef<DesktopRuntimeStatus | null>(null);
  const startupSleepWakeAttemptedRef = useRef(false);
  const startupVoiceWarmKeyRef = useRef('');
  const remoteAccountHydratedKeyRef = useRef<string | null>(null);
  const remoteAccountHydrationInFlightKeyRef = useRef<string | null>(null);
  const runtimeDowngradeRecheckInFlightRef = useRef(false);
  const runtimeOfflinePollsRef = useRef(0);
  const runtimeHealthPollInFlightRef = useRef(false);
  const startupRequests = useRef(createLatestRequestGate()).current;
  const accountHydrationRequests = useRef(createLatestRequestGate()).current;

  const setStartupPhaseState = (nextPhase: StartupPhase) => {
    startupPhaseRef.current = nextPhase;
    setStartupPhase(nextPhase);
  };

  const resetAccountStartupState = () => {
    startupRequests.invalidate();
    accountHydrationRequests.invalidate();
    remoteAccountHydratedKeyRef.current = null;
    remoteAccountHydrationInFlightKeyRef.current = null;
    setRemoteAccountHydrating(false);
    startupInitializedRef.current = false;
    startupFlowInFlightRef.current = false;
    startupAutoRetryAttemptedRef.current = false;
    startupAutoRetryInFlightRef.current = false;
    startupDeferredRetryTimeoutRef.current = null;
    startupRecoveryInFlightRef.current = false;
    postStartupRefreshKeyRef.current = '';
    postStartupSetupNoticeSentRef.current = false;
    startupSleepWakeAttemptedRef.current = false;
    startupVoiceWarmKeyRef.current = '';
  };

  useEffect(() => {
    setActiveTab(requestedDesktopMode);
  }, [requestedDesktopMode]);

  useEffect(() => {
    if (requestedSettings) {
      setShowSetup(true);
    }
  }, [bootstrap?.setupState, requestedSettings]);

  useEffect(() => {
    setSharedSettingsDraft(profileToSharedSettingsDraft(remoteAuthStatus?.profile as any));
  }, [remoteAuthStatus?.profile]);

  useEffect(() => {
    const standaloneMode = Boolean(remoteAuthStatus?.cloudDisabled || remoteAuthStatus?.standalone);
    if (!standaloneMode || !bootstrap?.apiBaseUrl || !bootstrap?.accessToken) {
      return;
    }
    let disposed = false;
    const configKeys = [
      'agent.custom_system_prompt_append',
      'agent.max_turns',
      'memory.prompt_context_enabled',
      'memory.search_enabled',
      'memory.write_enabled',
    ];
    Promise.all(
      configKeys.map((key) => (
        fetchAgentConfig(bootstrap.apiBaseUrl, bootstrap.accessToken, key, bootstrap.currentSessionId || undefined)
          .then((result) => result.items?.[0] || null)
          .catch(() => null)
      )),
    ).then((items) => {
      if (disposed) {
        return;
      }
      const valueFor = (key: string) => items.find((item) => item?.key === key)?.value;
      const promptValue = valueFor('agent.custom_system_prompt_append');
      const maxTurnsValue = valueFor('agent.max_turns');
      setSharedSettingsDraft((current) => ({
        ...(current || profileToSharedSettingsDraft(null)),
        cloudChatBackupEnabled: false,
        customSystemPromptAppend: typeof promptValue === 'string' ? promptValue : current?.customSystemPromptAppend || '',
        maxTurns: typeof maxTurnsValue === 'number' && maxTurnsValue > 0
          ? String(maxTurnsValue)
          : setupMaxTurns
            ? String(setupMaxTurns)
            : current?.maxTurns || '',
        sleepModeEnabled: Boolean(orchestratorStatus?.headless_mode_enabled),
        memoryPromptContextEnabled: valueFor('memory.prompt_context_enabled') !== false,
        memorySearchEnabled: valueFor('memory.search_enabled') !== false,
        memoryWriteEnabled: valueFor('memory.write_enabled') !== false,
      }));
    });
    return () => {
      disposed = true;
    };
  }, [
    bootstrap?.accessToken,
    bootstrap?.apiBaseUrl,
    bootstrap?.currentSessionId,
    orchestratorStatus?.headless_mode_enabled,
    remoteAuthStatus?.cloudDisabled,
    remoteAuthStatus?.standalone,
    setupMaxTurns,
  ]);

  useEffect(() => {
    bootstrapRef.current = bootstrap;
  }, [bootstrap]);

  useEffect(() => {
    runtimeStatusRef.current = runtimeStatus;
  }, [runtimeStatus]);

  useEffect(() => {
    startupPhaseRef.current = startupPhase;
  }, [startupPhase]);

  useEffect(() => {
    if (!error) {
      return;
    }
    const timer = globalThis.setTimeout(() => {
      setError(null);
    }, STATUS_BANNER_AUTO_DISMISS_MS);
    return () => {
      globalThis.clearTimeout(timer);
    };
  }, [error]);

  useEffect(() => {
    if (!notice || error) {
      return;
    }
    const timer = globalThis.setTimeout(() => {
      setNotice(null);
    }, STATUS_BANNER_AUTO_DISMISS_MS);
    return () => {
      globalThis.clearTimeout(timer);
    };
  }, [error, notice]);

  const refreshRemoteAuthStatus = async () => {
    const status = await loadDesktopRemoteAuthStatus();
    if (status) {
      setRemoteAuthStatus(status);
    }
    return status;
  };

  const applyRemoteAuthOtpChallenge = (challenge: DesktopRemoteAuthOtpChallenge) => {
    setRemoteAuthOtpChallenge(challenge);
    setRemoteAuthOtpCode('');
  };

  const clearRemoteAuthOtpChallenge = () => {
    setRemoteAuthOtpChallenge(null);
    setRemoteAuthOtpCode('');
  };

  const submitRemoteAuth = async (options?: { confirmPassword?: string }) => {
    const email = remoteAuthEmail.trim();
    const password = remoteAuthPassword.trim();
    const confirmPassword = String(options?.confirmPassword ?? remoteAuthConfirmPassword).trim();
    const displayName = remoteAuthDisplayName.trim();
    if (!email || !password) {
      setRemoteAuthMessage('Email and password are required.');
      return;
    }
    if (remoteAuthMode === 'signup') {
      const passwordError = firstSignupPasswordError(
        password,
        confirmPassword,
        email,
        displayName,
      );
      if (passwordError) {
        setRemoteAuthMessage(passwordError);
        return;
      }
    }

    setRemoteAuthBusy(true);
    resetAccountStartupState();
    setRemoteAuthMessage(remoteAuthMode === 'signup' ? 'Creating account…' : 'Signing in…');
    try {
      const payload = {
        email,
        password,
        displayName: displayName || undefined,
        rememberMe: remoteAuthRememberMe,
      };
      const authResult = remoteAuthMode === 'signup'
        ? await registerDesktopRemoteAuth(payload)
        : await loginDesktopRemoteAuth(payload);
      if (!authResult) {
        throw new Error('Desktop remote account controls are unavailable in this shell.');
      }
      if ('signedIn' in authResult) {
        const status = authResult as DesktopRemoteAuthStatus;
        setRemoteAuthStatus(status);
        if (!status.signedIn) {
          setRemoteAuthMessage(status.error ? userFacingError(status.error, 'Sign-in did not complete.') : 'Sign-in did not complete.');
          return;
        }
        clearRemoteAuthOtpChallenge();
        setRemoteAuthPassword('');
        setRemoteAuthConfirmPassword('');
        setRemoteAuthMessage('Signed in.');
        resetAccountStartupState();
        return;
      }
      const challenge = authResult;
      applyRemoteAuthOtpChallenge(challenge);
      setRemoteAuthMessage('Verification code sent.');
    } catch (authError) {
      setRemoteAuthMessage(userFacingError(authError, remoteAuthMode === 'signup' ? 'Account was not created.' : 'Sign-in failed.'));
    } finally {
      setRemoteAuthBusy(false);
    }
  };

  const verifyRemoteAuthOtp = async () => {
    if (!remoteAuthOtpChallenge) {
      setRemoteAuthMessage('Start sign-in again.');
      return;
    }
    const code = remoteAuthOtpCode.trim();
    if (!code) {
      setRemoteAuthMessage('Enter the code.');
      return;
    }
    setRemoteAuthBusy(true);
    resetAccountStartupState();
    setRemoteAuthMessage('Verifying code…');
    try {
      const status = await verifyDesktopRemoteAuthOtp({
        challengeId: remoteAuthOtpChallenge.challenge_id,
        code,
      });
      if (!status) {
        throw new Error('Desktop verification controls are unavailable in this shell.');
      }
      setRemoteAuthStatus(status);
      if (!status.signedIn) {
        setRemoteAuthMessage(status.error ? userFacingError(status.error, 'Check the code and try again.') : 'Check the code and try again.');
        return;
      }
      setRemoteAuthPassword('');
      setRemoteAuthConfirmPassword('');
      setRemoteAuthOtpCode('');
      clearRemoteAuthOtpChallenge();
      setRemoteAuthMessage('Signed in. Loading saved setup…');
      resetAccountStartupState();
    } catch (authError) {
      setRemoteAuthMessage(userFacingError(authError, 'Check the code and try again.'));
    } finally {
      setRemoteAuthBusy(false);
    }
  };

  const resendRemoteAuthOtp = async () => {
    if (!remoteAuthOtpChallenge) {
      setRemoteAuthMessage('Start sign-in again.');
      return;
    }
    setRemoteAuthBusy(true);
    setRemoteAuthMessage('Sending a new code…');
    try {
      const challenge = await resendDesktopRemoteAuthOtp({ challengeId: remoteAuthOtpChallenge.challenge_id });
      if (!challenge) {
        throw new Error('Desktop verification controls are unavailable in this shell.');
      }
      applyRemoteAuthOtpChallenge(challenge);
      setRemoteAuthMessage('New code sent.');
    } catch (authError) {
      setRemoteAuthMessage(userFacingError(authError, 'Code was not sent.'));
    } finally {
      setRemoteAuthBusy(false);
    }
  };

  const submitRemoteGoogleAuth = async () => {
    setRemoteAuthBusy(true);
    resetAccountStartupState();
    setRemoteAuthMessage('Opening Google sign-in…');
    try {
      const status = await loginDesktopRemoteGoogle({ rememberMe: remoteAuthRememberMe });
      if (!status) {
        throw new Error('Desktop Google sign-in controls are unavailable in this shell.');
      }
      setRemoteAuthStatus(status);
      if (!status.signedIn) {
        setRemoteAuthMessage(status.error ? userFacingError(status.error, 'Google sign-in did not complete.') : 'Google sign-in did not complete.');
        return;
      }
      setRemoteAuthPassword('');
      setRemoteAuthMessage('Signed in with Google. Loading saved setup…');
      resetAccountStartupState();
    } catch (authError) {
      setRemoteAuthMessage(userFacingError(authError, 'Google sign-in did not finish.'));
    } finally {
      setRemoteAuthBusy(false);
    }
  };

  const currentStartupWatchdogMs = startupCurrentTimeoutSeconds * 1000 + STARTUP_WATCHDOG_GRACE_MS;
  const nextStartupRetryWindowSeconds = nextStartupRetryTimeoutSeconds(startupCurrentTimeoutSeconds);

  const setRuntimeStatusWithRef = (nextStatus: DesktopRuntimeStatus | null) => {
    runtimeStatusRef.current = nextStatus;
    setRuntimeStatus(nextStatus);
  };

  const shouldPreserveReadyRuntimeStatus = (
    nextStatus: DesktopRuntimeStatus | null | undefined,
    options?: { allowReadyDowngrade?: boolean },
  ) => {
    if (options?.allowReadyDowngrade || !nextStatus || nextStatus.ok || startupPhaseRef.current !== 'ready') {
      return false;
    }
    return Boolean(
      bootstrapRef.current?.apiBaseUrl
        && bootstrapRef.current?.accessToken
        && (runtimeStatusRef.current?.ok || bootstrapRef.current?.runtimeStatus?.ok)
    );
  };

  const remoteAccountHydrationKey = () => {
    if (!remoteAuthStatus?.signedIn || remoteAuthStatus?.cloudDisabled) {
      return null;
    }
    return [
      remoteAuthStatus.user?.email || 'account',
      remoteAuthStatus.desktop?.desktop_id || 'desktop',
      remoteAuthStatus.apiBaseUrl || 'api',
    ].join(':');
  };

  const shouldDeferSetupForAccountHydration = () => {
    const hydrationKey = remoteAccountHydrationKey();
    return Boolean(
      remoteAuthStatus?.signedIn
      && !remoteAuthStatus?.cloudDisabled
      && hydrationKey
      && remoteAccountHydratedKeyRef.current !== hydrationKey
    );
  };

  function scheduleReadyRuntimeDowngradeRecheck(nextStatus: DesktopRuntimeStatus) {
    if (nextStatus.runtimeProcessDetected || runtimeDowngradeRecheckInFlightRef.current) {
      return;
    }
    runtimeDowngradeRecheckInFlightRef.current = true;
    void (async () => {
      try {
        await delay(500);
        const refreshed = await loadDesktopBootstrap({ force: true });
        if (refreshed?.accessToken && refreshed.runtimeStatus?.ok && !refreshed.setupState?.required) {
          applyBootstrap(refreshed, { keepSetupClosed: true, preserveLoadingState: true });
          return;
        }
        setRuntimeStatusWithRef(nextStatus);
      } catch (_error) {
        setRuntimeStatusWithRef(nextStatus);
      } finally {
        runtimeDowngradeRecheckInFlightRef.current = false;
      }
    })();
  }

  const applyBootstrap = (
    payload: DesktopBootstrap,
    options: { keepSetupClosed?: boolean; preserveLoadingState?: boolean; allowReadyDowngrade?: boolean } = {}
  ) => {
    payload = normalizeDesktopBootstrapRuntimeStatus(payload);
    const preserveIncomingRuntimeStatus = shouldPreserveReadyRuntimeStatus(payload.runtimeStatus, options);
    setBootstrap((current) => {
      const nextRuntimeStatus = preserveIncomingRuntimeStatus
        ? current?.runtimeStatus ?? bootstrapRef.current?.runtimeStatus ?? payload.runtimeStatus ?? null
        : payload.runtimeStatus ?? current?.runtimeStatus ?? null;
      const nextAccessToken = payload.accessToken || current?.accessToken || '';
      const nextApiBaseUrl = payload.apiBaseUrl || current?.apiBaseUrl || '';
      const nextBootstrap = {
        ...current,
        ...payload,
        apiBaseUrl: nextApiBaseUrl,
        accessToken: nextAccessToken,
        runtimeStatus: nextRuntimeStatus,
        currentSessionId: payload.currentSessionId ?? current?.currentSessionId ?? null,
        deviceId: payload.deviceId ?? current?.deviceId ?? null,
        setupState: payload.setupState ?? current?.setupState ?? null,
      };
      bootstrapRef.current = nextBootstrap;
      return nextBootstrap;
    });
    if (payload.runtimeStatus) {
      if (preserveIncomingRuntimeStatus) {
        scheduleReadyRuntimeDowngradeRecheck(payload.runtimeStatus);
      } else {
        setRuntimeStatusWithRef(payload.runtimeStatus);
      }
    }
    if (payload.runtimeStatus?.ok && payload.accessToken) {
      setError((current) => (isRuntimeConnectivityMessage(current) ? null : current));
      setStartupErrorDetail((current) => (isRuntimeConnectivityMessage(current) ? null : current));
    }
    // Runtime/bootstrap refreshes should not close Settings while the user is editing them.
    if (options.preserveLoadingState || startupPhaseRef.current === 'ready') {
      return;
    }
    if (payload.accessToken && (payload.runtimeStatus?.ok ?? false)) {
      setLoadingState('Loading shared session');
      return;
    }
    if (payload.setupState?.required) {
      if (shouldDeferSetupForAccountHydration()) {
        setLoadingState('Loading saved setup');
        return;
      }
      setLoadingState('Setup required');
      setStartupPhaseState('setup_required');
      return;
    }
    if (isLaunchableRuntimePrestartDetail(payload.runtimeStatus?.detail, payload.canLaunchLocalRuntime)) {
      setLoadingState('Preparing desktop runtime');
      return;
    }
    setLoadingState(payload.runtimeStatus?.detail || 'Preparing desktop runtime');
  };

  const hydrateSignedInAccountData = async () => {
    if (!remoteAuthStatus?.signedIn || remoteAuthStatus?.cloudDisabled) {
      return null;
    }
    const requestId = accountHydrationRequests.begin();
    const requestIsCurrent = () => accountHydrationRequests.isCurrent(requestId);
    setRemoteAccountHydrating(true);
    setRemoteSecretsMessage('Loading saved setup…');
    try {
      const result = await applyDesktopAccountData();
      if (!result) {
        throw new Error('Desktop account hydration controls are unavailable in this shell.');
      }
      if (!requestIsCurrent()) {
        return null;
      }
      let hydratedBootstrap = result.bootstrap || null;
      if (!hydratedBootstrap && result.count) {
        hydratedBootstrap = await loadDesktopBootstrap({ force: true }).catch(() => null);
      }
      if (!requestIsCurrent()) {
        return null;
      }
      if (hydratedBootstrap) {
        applyBootstrap(hydratedBootstrap, { keepSetupClosed: true, preserveLoadingState: true });
      }
      if (
        startupPhaseRef.current !== 'ready'
        && hydratedBootstrap
        && !hydratedBootstrap.setupState?.required
      ) {
        setNotice('Saved setup loaded. Continuing startup…');
        await beginStartup({ forceBootstrap: true, attachTimeoutSeconds: STARTUP_INITIAL_TIMEOUT_SECONDS });
      }
      if (!requestIsCurrent()) {
        return null;
      }
      const nextMessage = result.applied
        ? `Loaded ${result.count} saved setting${result.count === 1 ? '' : 's'}.`
        : (result.detail || 'No saved setup found.');
      setRemoteSecretsMessage(nextMessage);
      await refreshRemoteSecretItems();
      return result;
    } catch (hydrateError) {
      if (!requestIsCurrent()) {
        return null;
      }
      const message = describeError(hydrateError);
      setRemoteSecretsMessage(`Account setup load failed: ${message}`);
      return null;
    } finally {
      if (requestIsCurrent()) {
        setRemoteAccountHydrating(false);
      }
    }
  };

  const failStartup = (message: string) => {
    setStartupErrorDetail(message);
    setError(message);
    setStartupPhaseState('startup_error');
  };

  const retryStartupSilently = async (timeoutSeconds: number) => {
    if (startupFlowInFlightRef.current) {
      startupDeferredRetryTimeoutRef.current = timeoutSeconds;
      return;
    }
    startupAutoRetryAttemptedRef.current = true;
    startupAutoRetryInFlightRef.current = true;
    setStartingRuntime(true);
    setStartupCurrentTimeoutSeconds(timeoutSeconds);
    setError(null);
    setStartupErrorDetail(null);
    const retryPromise = beginStartup({ forceBootstrap: true, attachTimeoutSeconds: timeoutSeconds });
    setNotice(null);
    setLoadingState('Finishing startup');
    try {
      await retryPromise;
    } finally {
      startupAutoRetryInFlightRef.current = false;
      setStartingRuntime(false);
    }
  };

  const handleStartupFailure = (message: string) => {
    const detail = String(message || '').trim() || 'The desktop app could not finish becoming ready.';
    failStartup(detail);
  };

  const beginStartup = async (options?: { forceBootstrap?: boolean; attachTimeoutSeconds?: number }) => {
    if (startupFlowInFlightRef.current) {
      return;
    }
    if (startupPhaseRef.current === 'ready' && !options?.forceBootstrap) {
      return;
    }
    const requestId = startupRequests.begin();
    const requestIsCurrent = () => startupRequests.isCurrent(requestId);
    startupFlowInFlightRef.current = true;
    if (!isDesktopEnvironment()) {
      failStartup('Desktop preload bridge is unavailable. Launch this route inside the Electron shell.');
      startupFlowInFlightRef.current = false;
      return;
    }

    setError(null);
    setNotice(null);
    setShowSetup(false);
    setStartupErrorDetail(null);
    setStartupPhaseState('bootstrapping');
    setBootstrap(null);
    setRuntimeStatus(null);
    setLoadingState('Preparing desktop runtime');

    try {
      const payload = await loadDesktopBootstrap({
        force: options?.forceBootstrap,
        deferServices: true,
      });
      if (!payload) {
        throw new Error('Desktop bootstrap is unavailable in this shell.');
      }
      if (!requestIsCurrent()) {
        return;
      }

      applyBootstrap(payload, { keepSetupClosed: true });

      if (payload.setupState?.required) {
        if (shouldDeferSetupForAccountHydration()) {
          setLoadingState('Loading saved setup');
          return;
        }
        setStartupPhaseState('setup_required');
        return;
      }

      let readyPayload = payload;
      if (!(payload.accessToken && payload.runtimeStatus?.ok)) {
        setStartupPhaseState('starting_runtime');
        setLoadingState('Starting local agent');
        const started = await startDesktopRuntime({
          attachTimeoutSeconds: options?.attachTimeoutSeconds,
          restartAttachTimeoutSeconds: options?.attachTimeoutSeconds,
          deferServices: true,
        });
        if (!started) {
          throw new Error('Desktop runtime controls are unavailable in this shell.');
        }
        if (!requestIsCurrent()) {
          return;
        }
        readyPayload = started;
        applyBootstrap(readyPayload, { keepSetupClosed: true });
      }

      if (readyPayload.setupState?.required) {
        if (shouldDeferSetupForAccountHydration()) {
          setLoadingState('Loading saved setup');
          return;
        }
        setStartupPhaseState('setup_required');
        return;
      }

      if (!(readyPayload.accessToken && readyPayload.runtimeStatus?.ok)) {
        if (!requestIsCurrent()) {
          return;
        }
        const recovered = await recoverReadyRuntimeFromStatus({ attempts: 10, delayMs: 750 });
        if (!requestIsCurrent()) {
          return;
        }
        if (recovered) {
          return;
        }
        throw new Error(
          readyPayload.runtimeStatus?.detail ||
          'Local runtime did not become ready. Check the desktop runtime logs and try again.'
        );
      }

      setStartupPhaseState('warming_ui');
      setLoadingState('Waiting for local API');
      let apiProfile;
      try {
        apiProfile = await waitForDesktopApiReady(
          readyPayload.apiBaseUrl,
          readyPayload.accessToken,
          Math.max(20_000, (options?.attachTimeoutSeconds ?? STARTUP_INITIAL_TIMEOUT_SECONDS) * 1000),
        );
        if (!requestIsCurrent()) {
          return;
        }
      } catch (readyError) {
        if (!requestIsCurrent()) {
          return;
        }
        if (!isAuthTokenMessage(describeError(readyError))) {
          throw readyError;
        }
        setLoadingState('Refreshing local API token');
        const refreshed = await loadDesktopBootstrap({ force: true });
        if (!requestIsCurrent()) {
          return;
        }
        if (!(refreshed?.accessToken && refreshed.runtimeStatus?.ok)) {
          throw readyError;
        }
        readyPayload = refreshed;
        applyBootstrap(readyPayload, { keepSetupClosed: true });
        apiProfile = await waitForDesktopApiReady(
          readyPayload.apiBaseUrl,
          readyPayload.accessToken,
          20_000,
        );
        if (!requestIsCurrent()) {
          return;
        }
      }
      setBootstrap((current) => (
        current
          ? {
              ...current,
              currentSessionId: apiProfile.current_session_id ?? current.currentSessionId ?? null,
            }
          : current
      ));
      setStartupPhaseState('ready');
      setLoadingState('Ready');
    } catch (startupError) {
      if (!requestIsCurrent()) {
        return;
      }
      const startupMessage = String(startupError);
      if (
        isStartupTimeoutMessage(startupMessage) &&
        await recoverReadyRuntimeFromStatus({ attempts: 10, delayMs: 750 })
      ) {
        return;
      }
      handleStartupFailure(startupMessage);
    } finally {
      if (requestIsCurrent()) {
        startupFlowInFlightRef.current = false;
        const deferredRetryTimeout = startupDeferredRetryTimeoutRef.current;
        startupDeferredRetryTimeoutRef.current = null;
        if (deferredRetryTimeout && isStartupPending(startupPhaseRef.current)) {
          void retryStartupSilently(deferredRetryTimeout);
        }
      }
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

  const wakeDesktopFromSleepMode = async (
    reason: 'startup' | 'reopen',
    sourceBootstrap?: DesktopBootstrap | null,
    options?: { retryAuth?: boolean; attempts?: number },
  ) => {
    const maxAttempts = Math.max(1, Math.trunc(Number(options?.attempts || 4)));
    let currentBootstrap = sourceBootstrap || bootstrapRef.current;

    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      if (attempt > 0) {
        await delay(750);
        const refreshed = await loadDesktopBootstrap({ force: true }).catch(() => null);
        if (refreshed) {
          currentBootstrap = refreshed;
          bootstrapRef.current = refreshed;
          runtimeStatusRef.current = refreshed.runtimeStatus || null;
          applyBootstrap(refreshed, { keepSetupClosed: true, preserveLoadingState: true });
        }
      }

      const apiBaseUrl = currentBootstrap?.apiBaseUrl || '';
      const accessToken = currentBootstrap?.accessToken || '';
      const currentRuntimeStatus = runtimeStatusRef.current || currentBootstrap?.runtimeStatus || null;
      const runtimeReady = Boolean(apiBaseUrl && accessToken && (currentRuntimeStatus?.ok ?? currentBootstrap?.runtimeStatus?.ok));
      if (!runtimeReady) {
        continue;
      }

      try {
        const currentOrchestrator = await fetchRuntimeOrchestratorStatus(
          apiBaseUrl,
          accessToken,
        );
        setOrchestratorStatus(currentOrchestrator);
        if (!currentOrchestrator.headless_mode_enabled) {
          return false;
        }

        const nextOrchestrator = await configureHeadlessRuntime(
          apiBaseUrl,
          accessToken,
          { enabled: false },
        );
        setOrchestratorStatus(nextOrchestrator);
        setNotice(
          reason === 'reopen'
            ? 'Desktop app reopened. Sleep mode is off and the UI is reconnected.'
            : 'Desktop UI connected. Sleep mode has been turned off.'
        );
        return true;
      } catch (wakeError) {
        const message = describeError(wakeError);
        if (options?.retryAuth !== false && isAuthTokenMessage(message)) {
          const refreshed = await loadDesktopBootstrap({ force: true });
          if (refreshed?.accessToken && refreshed.runtimeStatus?.ok) {
            bootstrapRef.current = refreshed;
            runtimeStatusRef.current = refreshed.runtimeStatus || null;
            applyBootstrap(refreshed, { keepSetupClosed: true, preserveLoadingState: true });
            return wakeDesktopFromSleepMode(reason, refreshed, { retryAuth: false, attempts: maxAttempts });
          }
        }
        if (isRuntimeConnectivityMessage(message)) {
          continue;
        }
        setError('Sleep mode did not turn off.');
        return false;
      }
    }

    return false;
  };

  const reconnectDesktopAfterWindowReopen = async () => {
    setError(null);
    setNotice('Reconnecting desktop UI…');
    try {
      const payload = await loadDesktopBootstrap({ force: true });
      if (payload) {
        bootstrapRef.current = payload;
        runtimeStatusRef.current = payload.runtimeStatus || null;
        applyBootstrap(payload, { keepSetupClosed: true, preserveLoadingState: true });
        if (payload.accessToken && payload.runtimeStatus?.ok && !payload.setupState?.required) {
          setStartupPhaseState('ready');
          setLoadingState('Ready');
        }
      }
      const woke = await wakeDesktopFromSleepMode('reopen', payload);
      if (!woke) {
        setNotice('Desktop UI reconnected.');
      }
    } catch (reconnectError) {
      setError(userFacingError(reconnectError, 'Desktop UI did not reconnect.'));
    }
  };

  const recoverReadyRuntimeFromStatus = async (options?: { attempts?: number; delayMs?: number }) => {
    if (startupRecoveryInFlightRef.current) {
      return false;
    }
    if (startupPhaseRef.current === 'ready') {
      return true;
    }

    startupRecoveryInFlightRef.current = true;
    setLoadingState('Reconnecting local runtime');
    try {
      const attempts = Math.max(1, Math.trunc(Number(options?.attempts || 1)));
      const delayMs = Math.max(100, Math.trunc(Number(options?.delayMs || 750)));
      for (let attempt = 0; attempt < attempts; attempt += 1) {
        if (attempt > 0) {
          await delay(delayMs);
        }
        const refreshed = await loadDesktopBootstrap({ force: true });
        if (!(refreshed?.accessToken && refreshed.runtimeStatus?.ok) || refreshed.setupState?.required) {
          if (refreshed) {
            applyBootstrap(refreshed, { keepSetupClosed: true });
          }
          continue;
        }

        applyBootstrap(refreshed, { keepSetupClosed: true });
        const apiProfile = await waitForDesktopApiReady(
          refreshed.apiBaseUrl,
          refreshed.accessToken,
          20_000,
        );
        setBootstrap((current) => (
          current
            ? {
                ...current,
                currentSessionId: apiProfile.current_session_id ?? current.currentSessionId ?? null,
              }
            : current
        ));
        setError((current) => (isRuntimeConnectivityMessage(current) ? null : current));
        setStartupErrorDetail((current) => (isRuntimeConnectivityMessage(current) ? null : current));
        setNotice((current) => (current && isStartupTimeoutMessage(current) ? null : current));
        setStartupPhaseState('ready');
        setLoadingState('Ready');
        return true;
      }
      return false;
    } catch (recoveryError) {
      setStartupErrorDetail(userFacingError(recoveryError, 'Startup recovery failed.'));
      return false;
    } finally {
      startupRecoveryInFlightRef.current = false;
    }
  };

  useEffect(() => {
    if (!isDesktopEnvironment()) {
      setRemoteAuthLoading(false);
      failStartup('Desktop preload bridge is unavailable. Launch this route inside the Electron shell.');
      return;
    }

    let disposed = false;
    setRemoteAuthLoading(true);
    loadDesktopRemoteAuthStatus()
      .then((status) => {
        if (disposed) {
          return;
        }
        setRemoteAuthStatus(status);
        if (status?.error && !status.signedIn) {
          setRemoteAuthMessage(userFacingError(status.error, 'Sign-in status did not load.'));
        }
      })
      .catch((authError) => {
        if (disposed) {
          return;
        }
        const message = userFacingError(authError, 'Sign-in status did not load.');
        setRemoteAuthStatus({ signedIn: false, error: message, apiBaseUrl: 'https://api.kraitos.app' });
        setRemoteAuthMessage(message);
      })
      .finally(() => {
        if (!disposed) {
          setRemoteAuthLoading(false);
        }
      });

    return () => {
      disposed = true;
    };
  }, []);

  useEffect(() => {
    if (!remoteAuthStatus?.signedIn) {
      setRemoteSecretItems([]);
      setRemoteSecretsMessage(null);
      return;
    }
    void refreshRemoteSecretItems();
  }, [remoteAuthStatus?.signedIn, remoteAuthStatus?.user?.email]);

  useEffect(() => {
    if (!isDesktopEnvironment()) {
      failStartup('Desktop preload bridge is unavailable. Launch this route inside the Electron shell.');
      return;
    }
    if (remoteAuthLoading) {
      setLoadingState('Checking account');
      return;
    }
    const accountHydrationEnabled = Boolean(remoteAuthStatus?.signedIn && !remoteAuthStatus?.cloudDisabled);
    const hydrationKey = accountHydrationEnabled ? remoteAccountHydrationKey() : '';
    if (accountHydrationEnabled && hydrationKey && remoteAccountHydratedKeyRef.current !== hydrationKey) {
      if (remoteAccountHydrationInFlightKeyRef.current === hydrationKey || remoteAccountHydrating) {
        setLoadingState('Loading saved setup');
        return;
      }
      remoteAccountHydrationInFlightKeyRef.current = hydrationKey;
      setLoadingState('Loading saved setup');
      void hydrateSignedInAccountData()
        .finally(() => {
          if (remoteAccountHydrationInFlightKeyRef.current === hydrationKey) {
            remoteAccountHydratedKeyRef.current = hydrationKey;
            remoteAccountHydrationInFlightKeyRef.current = null;
          }
          if (startupPhaseRef.current !== 'ready') {
            startupInitializedRef.current = false;
          }
        });
      return;
    }
    if (startupInitializedRef.current) {
      return;
    }
    startupInitializedRef.current = true;

    let disposed = false;

    startupAutoRetryAttemptedRef.current = false;
    startupAutoRetryInFlightRef.current = false;
    setStartupCurrentTimeoutSeconds(STARTUP_INITIAL_TIMEOUT_SECONDS);
    void beginStartup({ attachTimeoutSeconds: STARTUP_INITIAL_TIMEOUT_SECONDS });

    const unsubscribe = subscribeDesktopRuntime((event) => {
      if (disposed) {
        return;
      }

      const payload = event.payload as DesktopBootstrap | DesktopRuntimeStatus | undefined;
      if (event.type === 'desktop_window_reopened') {
        void reconnectDesktopAfterWindowReopen();
        return;
      }

      if (event.type === 'voice_pack_progress' && event.payload) {
        const progress = event.payload as DesktopVoicePackInstallProgress;
        setVoicePackProgress(progress);
        if (progress.packId) {
          if (progress.state === 'error' || progress.state === 'ready') {
            setVoicePackBusyId(null);
          } else {
            setVoicePackBusyId(progress.packId);
          }
        }
        if (progress.message) {
          setNotice(progress.message);
        }
        if (progress.state === 'error') {
          setError(progress.message || 'Voice pack installation failed.');
        }
        return;
      }

      if (event.type === 'update_status' && event.payload) {
        setUpdateStatus(event.payload as DesktopUpdateStatus);
        setInstallingUpdate(false);
        return;
      }

      if (event.type === 'update_installing') {
        setInstallingUpdate(true);
        setNotice('Pulling the latest desktop update…');
        return;
      }

      if (event.type === 'update_install_result' && event.payload) {
        setInstallingUpdate(false);
        const result = event.payload as { launched?: boolean; message?: string; blocked?: boolean };
        if (result.launched) {
          setNotice(result.message || 'Desktop update installed. Restarting EmploAI…');
        } else if (result.blocked || result.message) {
          setError(result.message || 'Desktop update did not start.');
        }
        return;
      }

      if (event.type === 'runtime_status' && payload) {
        const nextStatus = payload as DesktopRuntimeStatus;
        if (shouldPreserveReadyRuntimeStatus(nextStatus)) {
          scheduleReadyRuntimeDowngradeRecheck(nextStatus);
          return;
        }
        setRuntimeStatusWithRef(nextStatus);
        const failureDetail = runtimeFailureDetail(nextStatus);
        if (
          failureDetail &&
          startupFlowInFlightRef.current &&
          startupPhaseRef.current === 'starting_runtime'
        ) {
          return;
        }
        if (
          failureDetail &&
          isStartupPending(startupPhaseRef.current) &&
          !isLaunchableRuntimePrestartDetail(failureDetail, bootstrap?.canLaunchLocalRuntime)
        ) {
          handleStartupFailure(failureDetail);
        }
        if (nextStatus.ok && startupPhaseRef.current !== 'ready' && !startupFlowInFlightRef.current) {
          void recoverReadyRuntimeFromStatus();
        }
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
          applyBootstrap(bootstrapPayload, {
            allowReadyDowngrade: event.type === 'runtime_stopped',
          });
          const failureDetail = runtimeFailureDetail(bootstrapPayload.runtimeStatus);
          if (
            failureDetail &&
            startupFlowInFlightRef.current &&
            startupPhaseRef.current === 'starting_runtime'
          ) {
            return;
          }
          if (
            failureDetail &&
            isStartupPending(startupPhaseRef.current) &&
            !isLaunchableRuntimePrestartDetail(failureDetail, bootstrapPayload.canLaunchLocalRuntime)
          ) {
            handleStartupFailure(failureDetail);
            return;
          }
          if (
            event.type === 'runtime_stopped' &&
            isStartupPending(startupPhaseRef.current) &&
            !bootstrapPayload.runtimeStatus?.ok
          ) {
            handleStartupFailure(
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
  }, [
    remoteAccountHydrating,
    remoteAuthLoading,
    remoteAuthStatus?.apiBaseUrl,
    remoteAuthStatus?.desktop?.desktop_id,
    remoteAuthStatus?.signedIn,
    remoteAuthStatus?.user?.email,
  ]);

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
        handleStartupFailure(
          `Startup is taking longer than expected. The desktop app did not become ready within the current startup window (${startupCurrentTimeoutSeconds}s runtime budget).`
        );
      }
    }, currentStartupWatchdogMs);

    return () => {
      if (startupWatchdogTimerRef.current) {
        clearTimeout(startupWatchdogTimerRef.current);
        startupWatchdogTimerRef.current = null;
      }
    };
  }, [startupCurrentTimeoutSeconds, currentStartupWatchdogMs, startupPhase]);

  const [remoteRuntimes, setRemoteRuntimes] = useState<RemoteRuntimeSummary[]>([]);
  useEffect(() => {
    if (!remoteAuthStatus?.signedIn) {
      setRemoteRuntimes([]);
      return;
    }
    let disposed = false;
    void Promise.all([
      listDesktopRemoteAccountDesktops(),
      loadDesktopFleetSnapshot(),
    ]).then(([desktops, fleet]) => {
      if (disposed) return;
      const workers = Array.isArray(fleet?.workers) ? fleet.workers : [];
      const tasks = Array.isArray(fleet?.tasks) ? fleet.tasks : [];
      const reports = Array.isArray(fleet?.reports) ? fleet.reports : [];
      setRemoteRuntimes((Array.isArray(desktops) ? desktops : []).map((desktop) => {
        const desktopWorkers = workers.filter((worker) => worker.machine_desktop_id === desktop.desktop_id);
        const workerIds = new Set(desktopWorkers.map((worker) => worker.worker_id));
        const activeCount = tasks.filter((task) => workerIds.has(task.worker_id) && task.status === 'running').length;
        const queuedCount = tasks.filter((task) => workerIds.has(task.worker_id) && task.status === 'queued').length;
        const latestReport = reports.find((report) => workerIds.has(report.worker_id));
        const connected = desktop.status === 'connected';
        return {
          id: String(desktop.desktop_id || ''),
          name: desktop.display_name || 'Paired desktop',
          hostLabel: desktop.last_seen_at ? `Last seen ${desktop.last_seen_at}` : 'No heartbeat yet',
          status: connected ? 'connected' : 'offline',
          detail: desktop.detail || `${desktopWorkers.length} workers · ${activeCount} active · ${queuedCount} queued`,
          workerCount: desktopWorkers.length,
          activeCount,
          queuedCount,
          latestReport: latestReport?.summary || null,
          workers: desktopWorkers.map((worker) => ({
            id: worker.worker_id,
            name: worker.display_name,
            status: worker.status,
            activeTaskId: worker.active_task_id || null,
          })),
          preview: {
            state: connected ? 'connecting' : 'offline',
            message: connected ? 'Manual view-only previews are requested from a worker.' : 'Desktop is offline.',
            updatedAt: null,
          },
        } as RemoteRuntimeSummary;
      }));
    }).catch((remoteError) => {
      if (!disposed) setNotice(userFacingError(remoteError, 'Paired desktops could not be loaded.'));
    });
    return () => {
      disposed = true;
    };
  }, [remoteAuthStatus?.signedIn, activeTab]);

  const effectiveRuntimeStatus = runtimeStatus || bootstrap?.runtimeStatus || null;

  const localRuntimeReady = Boolean(
    bootstrap?.apiBaseUrl &&
    bootstrap?.accessToken &&
    effectiveRuntimeStatus?.ok
  );
  const runtimeProcessDetected = Boolean(
    effectiveRuntimeStatus?.ok && (
      effectiveRuntimeStatus?.process_id ||
      effectiveRuntimeStatus?.processId ||
      bootstrap?.runtimeProcessDetected
    )
  );
  const remoteAccountSetupCheckPending = shouldDeferSetupForAccountHydration();
  const setupBlocksRuntime = Boolean(bootstrap?.setupState?.required);
  const chatSkeletonVisible = startupPhase === 'warming_ui' && localRuntimeReady;

  useEffect(() => {
    if (!setupBlocksRuntime || startupPhase === 'setup_required' || startupPhase === 'ready') {
      return;
    }
    if (remoteAccountSetupCheckPending) {
      setLoadingState('Loading saved setup');
      return;
    }
    setStartupPhaseState('setup_required');
    setLoadingState('Setup required');
    setStartupErrorDetail(null);
    setError((current) => (isRuntimeConnectivityMessage(current) ? null : current));
  }, [
    remoteAccountHydrating,
    remoteAuthStatus?.apiBaseUrl,
    remoteAuthStatus?.desktop?.desktop_id,
    remoteAuthStatus?.signedIn,
    remoteAuthStatus?.user?.email,
    setupBlocksRuntime,
    startupPhase,
    remoteAccountSetupCheckPending,
  ]);

  useEffect(() => {
    if (startupPhase === 'ready' || startupPhase === 'setup_required' || setupBlocksRuntime) {
      return;
    }

    let disposed = false;
    const pollRuntimeReadiness = async () => {
      if (
        startupRecoveryInFlightRef.current ||
        startupFlowInFlightRef.current ||
        startupPhaseRef.current === 'ready'
      ) {
        return;
      }
      try {
        const status = await loadDesktopRuntimeStatus();
        if (disposed || !status) {
          return;
        }
        setRuntimeStatus(status);
        if (status.ok) {
          await recoverReadyRuntimeFromStatus();
        }
      } catch (_error) {
        // Startup already has a visible failure path; transient status probe failures
        // should not replace a more useful runtime message.
      }
    };

    void pollRuntimeReadiness();
    const timer = globalThis.setInterval(() => {
      void pollRuntimeReadiness();
    }, 2500);
    return () => {
      disposed = true;
      globalThis.clearInterval(timer);
    };
  }, [setupBlocksRuntime, startupPhase]);

  useEffect(() => {
    if (startupPhase !== 'ready' || setupBlocksRuntime) {
      runtimeOfflinePollsRef.current = 0;
      return;
    }

    let disposed = false;
    const pollRuntimeHealth = async () => {
      if (runtimeHealthPollInFlightRef.current) {
        return;
      }
      runtimeHealthPollInFlightRef.current = true;
      try {
        const status = await loadDesktopRuntimeStatus();
        if (disposed || !status) {
          return;
        }
        if (status.ok) {
          runtimeOfflinePollsRef.current = 0;
          setRuntimeStatusWithRef(status);
          setBootstrap((current) => {
            if (!current) {
              return current;
            }
            const next = { ...current, runtimeStatus: status };
            bootstrapRef.current = next;
            return next;
          });
          return;
        }

        if (status.runtimeProcessDetected) {
          runtimeOfflinePollsRef.current = 0;
          return;
        }

        runtimeOfflinePollsRef.current += 1;
        if (runtimeOfflinePollsRef.current < RUNTIME_OFFLINE_CONFIRMATIONS) {
          return;
        }
        setRuntimeStatusWithRef(status);
        setBootstrap((current) => {
          if (!current) {
            return current;
          }
          const next = {
            ...current,
            runtimeStatus: status,
            runtimeProcessDetected: false,
          };
          bootstrapRef.current = next;
          return next;
        });
      } catch (_error) {
        // The IPC probe itself can fail transiently. A returned offline status is
        // required before changing the visible runtime state.
      } finally {
        runtimeHealthPollInFlightRef.current = false;
      }
    };

    void pollRuntimeHealth();
    const timer = globalThis.setInterval(() => {
      void pollRuntimeHealth();
    }, RUNTIME_HEALTH_POLL_MS);
    return () => {
      disposed = true;
      globalThis.clearInterval(timer);
    };
  }, [setupBlocksRuntime, startupPhase]);

  useEffect(() => {
    if (!localRuntimeReady) {
      return;
    }
    setError((current) => (isRuntimeConnectivityMessage(current) ? null : current));
    setStartupErrorDetail((current) => (isRuntimeConnectivityMessage(current) ? null : current));
    setNotice((current) => (current && isStartupTimeoutMessage(current) ? null : current));
  }, [localRuntimeReady]);

  useEffect(() => {
    if (
      startupPhase !== 'ready'
      || !localRuntimeReady
      || !bootstrap?.apiBaseUrl
      || !bootstrap?.accessToken
    ) {
      return;
    }
    if (startupSleepWakeAttemptedRef.current) {
      return;
    }
    startupSleepWakeAttemptedRef.current = true;
    const timer = globalThis.setTimeout(() => {
      void wakeDesktopFromSleepMode('startup');
    }, 3000);
    return () => {
      globalThis.clearTimeout(timer);
    };
  }, [bootstrap?.accessToken, bootstrap?.apiBaseUrl, localRuntimeReady, startupPhase]);

  useEffect(() => {
    if (
      startupPhase !== 'ready'
      || !localRuntimeReady
      || !bootstrap?.apiBaseUrl
      || !bootstrap?.accessToken
    ) {
      return;
    }

    const refreshKey = `${bootstrap.apiBaseUrl}|${bootstrap.accessToken}|${bootstrap.releaseVersion || 'dev'}`;
    if (postStartupRefreshKeyRef.current === refreshKey) {
      return;
    }
    postStartupRefreshKeyRef.current = refreshKey;

    let disposed = false;
    const statusTimer = globalThis.setTimeout(() => {
      loadDesktopRuntimeStatus()
        .then((status) => {
          if (!disposed && status) {
            if (shouldPreserveReadyRuntimeStatus(status)) {
              scheduleReadyRuntimeDowngradeRecheck(status);
              return;
            }
            setRuntimeStatusWithRef(status);
          }
        })
        .catch(() => {});
    }, 1000);
    const serviceTimer = globalThis.setTimeout(() => {
      loadDesktopBootstrap({ force: true })
        .then((payload) => {
          if (!disposed && payload) {
            applyBootstrap(payload, { keepSetupClosed: true, preserveLoadingState: true });
          }
        })
        .catch(() => {});
    }, 2500);
    const updateTimer = globalThis.setTimeout(() => {
      if (!disposed) {
        void refreshUpdateStatus(true);
      }
    }, 6000);
    const dailyUpdateTimer = globalThis.setInterval(() => {
      if (!disposed) {
        void refreshUpdateStatus(true);
      }
    }, 24 * 60 * 60 * 1000);

    return () => {
      disposed = true;
      globalThis.clearTimeout(statusTimer);
      globalThis.clearTimeout(serviceTimer);
      globalThis.clearTimeout(updateTimer);
      globalThis.clearInterval(dailyUpdateTimer);
    };
  }, [
    bootstrap?.accessToken,
    bootstrap?.apiBaseUrl,
    bootstrap?.releaseVersion,
    localRuntimeReady,
    startupPhase,
  ]);

  useEffect(() => {
    if (
      startupPhase !== 'ready'
      || !localRuntimeReady
      || !bootstrap?.apiBaseUrl
      || !bootstrap?.accessToken
      || bootstrap.setupState?.required
    ) {
      return;
    }

    const voiceStatus = bootstrap.setupState?.voiceStatus as Record<string, any> | null | undefined;
    const selectedEngine = String(voiceStatus?.selected_engine || bootstrap.setupState?.voicePacks?.defaultEngine || '').trim();
    const sttBackend = String(voiceStatus?.stt_backend || '').trim().toLowerCase();
    const apiSttBackendActive = sttBackend === 'openai_realtime' || sttBackend === 'openai' || sttBackend === 'gemini';
    if ((!apiSttBackendActive && (!selectedEngine || selectedEngine === 'none')) || voiceStatus?.input_ok === false) {
      return;
    }

    const warmKey = `${bootstrap.apiBaseUrl}|${bootstrap.accessToken}|${selectedEngine || 'none'}|${sttBackend || 'local'}`;
    if (startupVoiceWarmKeyRef.current === warmKey) {
      return;
    }
    startupVoiceWarmKeyRef.current = warmKey;

    const timer = globalThis.setTimeout(() => {
      void warmVoiceRuntime(bootstrap.apiBaseUrl, bootstrap.accessToken)
        .then((warmedVoiceStatus) => {
          setBootstrap((current) => (
            current
              ? {
                  ...current,
                  setupState: current.setupState
                    ? {
                        ...current.setupState,
                        voiceStatus: warmedVoiceStatus as any,
                      }
                    : current.setupState,
                }
              : current
          ));
        })
        .catch(() => {
          startupVoiceWarmKeyRef.current = '';
        });
    }, 8000);
    return () => {
      globalThis.clearTimeout(timer);
    };
  }, [
    bootstrap?.accessToken,
    bootstrap?.apiBaseUrl,
    bootstrap?.setupState?.required,
    bootstrap?.setupState?.voicePacks?.defaultEngine,
    bootstrap?.setupState?.voiceStatus,
    localRuntimeReady,
    startupPhase,
  ]);

  const handleConversationStartupState = (state: StartupReadinessState, detail?: string) => {
    if (startupPhaseRef.current === 'ready') {
      return;
    }

    if (state === 'warming') {
      if (detail) {
        setLoadingState(detail);
      }
      if (startupPhaseRef.current === 'starting_runtime' || startupPhaseRef.current === 'bootstrapping') {
        setStartupPhaseState('warming_ui');
      }
      return;
    }

    if (state === 'fatal_error') {
      failStartup(detail || 'The desktop chat UI failed to finish initializing.');
      return;
    }

    setStartupPhaseState('ready');
    setLoadingState('Ready');
  };

  useEffect(() => {
    if (startupPhase !== 'startup_error') {
      return;
    }
    if (setupBlocksRuntime || !bootstrap?.accessToken || !localRuntimeReady) {
      return;
    }

    setError((current) => (isRuntimeConnectivityMessage(current) ? null : current));
    setStartupErrorDetail((current) => (isRuntimeConnectivityMessage(current) ? null : current));
    setLoadingState('Recovered local runtime');
    setStartupPhaseState('ready');
  }, [bootstrap?.accessToken, localRuntimeReady, setupBlocksRuntime, startupPhase]);

  const refreshSetupRuntimeControls = async () => {
    if (!bootstrap?.apiBaseUrl || !bootstrap?.accessToken || !(runtimeStatus?.ok ?? bootstrap?.runtimeStatus?.ok)) {
      setTelegramBotConfigs([]);
      setOrchestratorStatus(null);
      setSetupSessions([]);
      setSetupMaxTurns(null);
      setRecoveryItems([]);
      setPendingConfirmations([]);
      return;
    }
    try {
      const currentSessionId = typeof bootstrap.currentSessionId === 'string' && bootstrap.currentSessionId.trim()
        ? bootstrap.currentSessionId.trim()
        : null;
      const [botConfigs, runtimeOrchestrator, sessions, overview, recovery, confirmations] = await Promise.all([
        fetchTelegramBotConfigs(bootstrap.apiBaseUrl, bootstrap.accessToken).catch(() => []),
        fetchRuntimeOrchestratorStatus(bootstrap.apiBaseUrl, bootstrap.accessToken).catch(() => null),
        fetchSessions(bootstrap.apiBaseUrl, bootstrap.accessToken).catch(() => []),
        currentSessionId
          ? fetchAgentOverview(
              bootstrap.apiBaseUrl,
              bootstrap.accessToken,
              { sessionId: currentSessionId },
            ).catch(() => null)
          : Promise.resolve(null),
        fetchRecoveryItems(bootstrap.apiBaseUrl, bootstrap.accessToken).catch(() => ({ items: [] })),
        fetchPendingConfirmations(bootstrap.apiBaseUrl, bootstrap.accessToken).catch(() => ({ items: [] })),
      ]);
      setTelegramBotConfigs(Array.isArray(botConfigs) ? botConfigs : []);
      setOrchestratorStatus(runtimeOrchestrator);
      setSetupSessions(Array.isArray(sessions) ? sessions : []);
      setSetupMaxTurns(typeof overview?.max_turns === 'number' ? overview.max_turns : null);
      setRecoveryItems(Array.isArray(recovery?.items) ? recovery.items : []);
      setPendingConfirmations(Array.isArray(confirmations?.items) ? confirmations.items : []);
    } catch {
      setTelegramBotConfigs([]);
      setOrchestratorStatus(null);
      setSetupSessions([]);
      setSetupMaxTurns(null);
      setRecoveryItems([]);
      setPendingConfirmations([]);
    }
  };

  const retryStartup = async () => {
    const nextTimeoutSeconds = nextStartupRetryWindowSeconds;
    startupAutoRetryAttemptedRef.current = false;
    startupAutoRetryInFlightRef.current = false;
    setStartupCurrentTimeoutSeconds(nextTimeoutSeconds);
    setStartingRuntime(true);
    setNotice(`Retrying startup with a ${nextTimeoutSeconds}-second runtime window.`);
    try {
      await beginStartup({ forceBootstrap: true, attachTimeoutSeconds: nextTimeoutSeconds });
    } finally {
      setStartingRuntime(false);
    }
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

  const {
    startLocalRuntime,
    stopLocalRuntimeNow,
    logoutRemoteAccount,
    deleteRemoteAccountData,
    refreshRecovery,
    setCloudChatBackupEnabled,
    saveSharedSettings,
    approveSharedConfirmation,
    denySharedConfirmation,
    restoreArchivedItem,
    permanentlyDeleteArchivedItem,
    restoreManagedWorkspace,
    deleteRemoteSecretFromCloud,
    createRemotePairingTokenFromAccount,
    refreshRemoteSecretItems,
    saveCurrentSetupSecretsToCloud,
    saveLoginCredentialSecretsToCloud,
    saveTelegramBotSecretToCloud,
    applyCloudSetupSecrets,
    saveSetup,
    refreshMemory,
    saveMemory,
    installVoicePack,
    selectTtsVoicePack,
    removeVoicePack,
    selectVoiceEngine,
    installUpdateNow,
    createSetupTelegramBot,
    updateSetupTelegramBot,
    deleteSetupTelegramBot,
    configureRuntimeOrchestratorFromSetup,
    updateSetupGeneralAgentConfig,
  } = createDesktopAppShellActions({ confirmAction, confirmationDialog, params, requestedSessionId, requestedTab, requestedDesktopRoute, requestedDesktopMode, requestedSurfaceMode, activeTab, setActiveTab, bootstrap, setBootstrap, runtimeStatus, setRuntimeStatus, updateStatus, setUpdateStatus, loadingState, setLoadingState, error, setError, notice, setNotice, accountMenuOpen, setAccountMenuOpen, conversationSidebarToggleSignal, setConversationSidebarToggleSignal, startupPhase, setStartupPhase: setStartupPhaseState, startupErrorDetail, setStartupErrorDetail, startupCurrentTimeoutSeconds, setStartupCurrentTimeoutSeconds, showSetup, setShowSetup, startingRuntime, setStartingRuntime, stoppingRuntime, setStoppingRuntime, savingSetup, setSavingSetup, voicePackBusyId, setVoicePackBusyId, voicePackProgress, setVoicePackProgress, checkingUpdates, setCheckingUpdates, installingUpdate, setInstallingUpdate, memoryState, setMemoryState, memoryLoading, setMemoryLoading, memorySaving, setMemorySaving, telegramBotConfigs, setTelegramBotConfigs, orchestratorStatus, setOrchestratorStatus, setupSessions, setSetupSessions, setupMaxTurns, setSetupMaxTurns, recoveryItems, setRecoveryItems, pendingConfirmations, setPendingConfirmations, recoveryBusyId, setRecoveryBusyId, recoveryMessage, setRecoveryMessage, sharedSettingsDraft, setSharedSettingsDraft, sharedSettingsSaving, setSharedSettingsSaving, sharedSettingsStatus, setSharedSettingsStatus, remoteAuthStatus, setRemoteAuthStatus, remoteAuthLoading, setRemoteAuthLoading, remoteAuthBusy, setRemoteAuthBusy, remoteAuthLoggingOut, setRemoteAuthLoggingOut, remoteAuthMode, setRemoteAuthMode, remoteAuthEmail, setRemoteAuthEmail, remoteAuthPassword, setRemoteAuthPassword, remoteAuthDisplayName, setRemoteAuthDisplayName, remoteAuthRememberMe, setRemoteAuthRememberMe, remoteAuthOtpChallenge, setRemoteAuthOtpChallenge, remoteAuthOtpCode, setRemoteAuthOtpCode, remoteAuthMessage, setRemoteAuthMessage, remoteSecretItems, setRemoteSecretItems, remoteSecretsBusy, setRemoteSecretsBusy, remoteSecretsMessage, setRemoteSecretsMessage, remoteAccountHydrating, setRemoteAccountHydrating, startupPhaseRef, startupWatchdogTimerRef, startupFlowInFlightRef, startupInitializedRef, startupAutoRetryAttemptedRef, startupAutoRetryInFlightRef, startupDeferredRetryTimeoutRef, startupRecoveryInFlightRef, postStartupRefreshKeyRef, postStartupSetupNoticeSentRef, previousTelegramStateRef, bootstrapRef, runtimeStatusRef, startupSleepWakeAttemptedRef, startupVoiceWarmKeyRef, remoteAccountHydratedKeyRef, remoteAccountHydrationInFlightKeyRef, runtimeDowngradeRecheckInFlightRef, resetAccountStartupState, refreshRemoteAuthStatus, submitRemoteAuth, verifyRemoteAuthOtp, resendRemoteAuthOtp, submitRemoteGoogleAuth, currentStartupWatchdogMs, nextStartupRetryWindowSeconds, setRuntimeStatusWithRef, shouldPreserveReadyRuntimeStatus, scheduleReadyRuntimeDowngradeRecheck, applyBootstrap, remoteAccountHydrationKey, hydrateSignedInAccountData, failStartup, retryStartupSilently, handleStartupFailure, beginStartup, refreshUpdateStatus, wakeDesktopFromSleepMode, reconnectDesktopAfterWindowReopen, recoverReadyRuntimeFromStatus, remoteRuntimes, effectiveRuntimeStatus, localRuntimeReady, runtimeProcessDetected, setupBlocksRuntime, chatSkeletonVisible, handleConversationStartupState, refreshSetupRuntimeControls, retryStartup, DESKTOP_RUNTIME_RESTART_WAIT_MS, delay, desktopVoicePackLabel });

  const runtimeSummary = runtimeLabel(effectiveRuntimeStatus, loadingState);
  const showStartupRuntimeSummary = Boolean(
    runtimeSummary &&
    runtimeSummary !== 'bootstrapping desktop shell' &&
    runtimeSummary.trim().toLowerCase() !== String(loadingState || '').trim().toLowerCase()
  );
  const updateAvailable = Boolean(updateStatus?.updateAvailable && updateStatus.update && !updateStatus.blocked);
  const accountEmail = remoteAuthStatus?.user?.email || remoteAuthEmail || 'Not signed in';
  const telegramStatus = bootstrap?.telegramStatus || null;
  const telegramSummary = telegramStatusLabel(telegramStatus);
  const telegramStatusTone =
    telegramStatus?.state === 'running'
      ? 'ready'
      : telegramStatus?.state === 'starting'
        ? 'starting'
        : telegramStatus?.state === 'disabled'
          ? 'muted'
          : telegramStatus?.state === 'not_configured'
            ? 'warning'
            : telegramStatus?.state === 'degraded'
              ? 'warning'
              : 'offline';

  useEffect(() => {
    if (!showSetup || memoryLoading || memoryState || !isDesktopEnvironment()) {
      return;
    }
    void refreshMemory();
  }, [showSetup, memoryLoading, memoryState]);

  useEffect(() => {
    if (!showSetup) {
      return;
    }
    void refreshSetupRuntimeControls();
  }, [showSetup, bootstrap?.apiBaseUrl, bootstrap?.accessToken, runtimeStatus?.ok, bootstrap?.runtimeStatus?.ok]);

  useEffect(() => {
    const nextState = telegramStatus?.state || null;
    const previousState = previousTelegramStateRef.current;
    previousTelegramStateRef.current = nextState;
    if (nextState === 'running' && previousState && previousState !== 'running') {
      setNotice('Telegram backend is ready. You can use EmploAI from Telegram now.');
    }
  }, [telegramStatus?.state]);

  useEffect(() => {
    if (!isDesktopEnvironment()) {
      return;
    }
    if (!localRuntimeReady || !telegramStatus?.enabled || !telegramStatus.configured) {
      return;
    }
    if (telegramStatus.state === 'running' || telegramStatus.state === 'disabled' || telegramStatus.state === 'not_configured') {
      return;
    }

    let disposed = false;
    const poll = async () => {
      try {
        const payload = await loadDesktopBootstrap({ force: true });
        if (disposed || !payload) {
          return;
        }
        applyBootstrap(payload, { preserveLoadingState: true });
      } catch {
        // Keep the last known Telegram status visible until the next successful poll.
      }
    };

    void poll();
    const intervalId = globalThis.setInterval(() => {
      void poll();
    }, 3000);

    return () => {
      disposed = true;
      globalThis.clearInterval(intervalId);
    };
  }, [localRuntimeReady, telegramStatus?.configured, telegramStatus?.enabled, telegramStatus?.state]);

  const navigateWindowHistory = (direction: 'back' | 'forward') => {
    if (typeof window === 'undefined') {
      return;
    }
    if (direction === 'back') {
      if (window.history.length > 1) {
        window.history.back();
      } else {
        setNotice('No previous page to go back to.');
      }
      return;
    }
    window.history.forward();
  };

  return <DesktopAppShellView scope={{ confirmAction, confirmationDialog, params, requestedSessionId, requestedTab, requestedDesktopRoute, requestedDesktopMode, requestedSurfaceMode, activeTab, setActiveTab, bootstrap, setBootstrap, runtimeStatus, setRuntimeStatus, updateStatus, setUpdateStatus, loadingState, setLoadingState, error, setError, notice, setNotice, accountMenuOpen, setAccountMenuOpen, conversationSidebarToggleSignal, setConversationSidebarToggleSignal, startupPhase, setStartupPhase: setStartupPhaseState, startupErrorDetail, setStartupErrorDetail, startupCurrentTimeoutSeconds, setStartupCurrentTimeoutSeconds, showSetup, setShowSetup, startingRuntime, setStartingRuntime, stoppingRuntime, setStoppingRuntime, savingSetup, setSavingSetup, voicePackBusyId, setVoicePackBusyId, voicePackProgress, setVoicePackProgress, checkingUpdates, setCheckingUpdates, installingUpdate, setInstallingUpdate, memoryState, setMemoryState, memoryLoading, setMemoryLoading, memorySaving, setMemorySaving, telegramBotConfigs, setTelegramBotConfigs, orchestratorStatus, setOrchestratorStatus, setupSessions, setSetupSessions, setupMaxTurns, setSetupMaxTurns, recoveryItems, setRecoveryItems, pendingConfirmations, setPendingConfirmations, recoveryBusyId, setRecoveryBusyId, recoveryMessage, setRecoveryMessage, sharedSettingsDraft, setSharedSettingsDraft, sharedSettingsSaving, setSharedSettingsSaving, sharedSettingsStatus, setSharedSettingsStatus, remoteAuthStatus, setRemoteAuthStatus, remoteAuthLoading, setRemoteAuthLoading, remoteAuthBusy, setRemoteAuthBusy, remoteAuthLoggingOut, setRemoteAuthLoggingOut, remoteAuthMode, setRemoteAuthMode, remoteAuthEmail, setRemoteAuthEmail, remoteAuthPassword, setRemoteAuthPassword, remoteAuthDisplayName, setRemoteAuthDisplayName, remoteAuthRememberMe, setRemoteAuthRememberMe, remoteAuthOtpChallenge, setRemoteAuthOtpChallenge, remoteAuthOtpCode, setRemoteAuthOtpCode, remoteAuthMessage, setRemoteAuthMessage, remoteSecretItems, setRemoteSecretItems, remoteSecretsBusy, setRemoteSecretsBusy, remoteSecretsMessage, setRemoteSecretsMessage, remoteAccountHydrating, setRemoteAccountHydrating, remoteAccountSetupCheckPending, startupPhaseRef, startupWatchdogTimerRef, startupFlowInFlightRef, startupInitializedRef, startupAutoRetryAttemptedRef, startupAutoRetryInFlightRef, startupDeferredRetryTimeoutRef, startupRecoveryInFlightRef, postStartupRefreshKeyRef, postStartupSetupNoticeSentRef, previousTelegramStateRef, bootstrapRef, runtimeStatusRef, startupSleepWakeAttemptedRef, startupVoiceWarmKeyRef, remoteAccountHydratedKeyRef, remoteAccountHydrationInFlightKeyRef, runtimeDowngradeRecheckInFlightRef, resetAccountStartupState, refreshRemoteAuthStatus, submitRemoteAuth, verifyRemoteAuthOtp, resendRemoteAuthOtp, submitRemoteGoogleAuth, currentStartupWatchdogMs, nextStartupRetryWindowSeconds, setRuntimeStatusWithRef, shouldPreserveReadyRuntimeStatus, scheduleReadyRuntimeDowngradeRecheck, applyBootstrap, remoteAccountHydrationKey, hydrateSignedInAccountData, failStartup, retryStartupSilently, handleStartupFailure, beginStartup, refreshUpdateStatus, wakeDesktopFromSleepMode, reconnectDesktopAfterWindowReopen, recoverReadyRuntimeFromStatus, remoteRuntimes, effectiveRuntimeStatus, localRuntimeReady, runtimeProcessDetected, setupBlocksRuntime, chatSkeletonVisible, handleConversationStartupState, refreshSetupRuntimeControls, retryStartup, startLocalRuntime, stopLocalRuntimeNow, logoutRemoteAccount, deleteRemoteAccountData, refreshRecovery, setCloudChatBackupEnabled, saveSharedSettings, approveSharedConfirmation, denySharedConfirmation, restoreArchivedItem, permanentlyDeleteArchivedItem, restoreManagedWorkspace, deleteRemoteSecretFromCloud, createRemotePairingTokenFromAccount, refreshRemoteSecretItems, saveCurrentSetupSecretsToCloud, saveLoginCredentialSecretsToCloud, saveTelegramBotSecretToCloud, applyCloudSetupSecrets, saveSetup, refreshMemory, saveMemory, installVoicePack, selectTtsVoicePack, removeVoicePack, selectVoiceEngine, installUpdateNow, createSetupTelegramBot, updateSetupTelegramBot, deleteSetupTelegramBot, configureRuntimeOrchestratorFromSetup, updateSetupGeneralAgentConfig, runtimeSummary, showStartupRuntimeSummary, updateAvailable, accountEmail, telegramStatus, telegramSummary, telegramStatusTone, navigateWindowHistory }} />;
}
