import { useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, Text, TextInput, View } from 'react-native';

import { styles } from './DesktopSetupPanel.styles';
import { DesktopSetupRecoverySection } from './DesktopSetupRecoverySection';
import { DesktopSetupLocalIntelligenceSection } from './DesktopSetupLocalIntelligenceSection';
import { DesktopSetupOnboardingSection } from './DesktopSetupOnboardingSection';
import { DesktopSetupSharedSettingsSection } from './DesktopSetupSharedSettingsSection';
import { DesktopSetupVoiceSection } from './DesktopSetupVoiceSection';
import { VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW, VOICE_ENGINE_NONE } from './desktopVoicePolicy';
import { configuredProviderChipLabels, normalizeDesktopSetupValues } from './setupValues';
import { buildOnboardingSuggestion, type OnboardingSuggestion } from './desktopOnboardingStatus';
import { PairingQrCode } from '../components/PairingQrCode';
import { buildPairingQrValue } from '../lib/pairingQr';

import {
  fetchProjectOnboarding,
  type PendingConfirmation,
  type ProjectOnboardingProfile,
  type RecoveryArchiveItem,
  type RuntimeOrchestratorStatus,
  type SessionSummary,
  type TelegramBotConfig,
} from '@/lib/appApi';
import type {
  DesktopRemoteAccountDesktop,
  DesktopCodexAuthStatus,
  DesktopCodexDeviceLogin,
  DesktopRemoteAuthStatus,
  DesktopRemotePairingToken,
  DesktopRemoteSecretItem,
  DesktopSetupFieldValidation,
  DesktopMemoryState,
  DesktopSetupState,
  DesktopSetupValues,
  DesktopUpdateStatus,
  DesktopVoicePackInstallProgress,
  DesktopVoicePackSummary,
} from '@/lib/desktopBridge';
import {
  createDesktopShortcut,
  loadDesktopCodexAuthStatus,
  logoutDesktopCodexAuth,
  pollDesktopCodexDeviceLogin,
  startDesktopCodexDeviceLogin,
  validateDesktopSetupField,
} from '@/lib/desktopBridge';
import { InfoHint } from '@/components/InfoHint';
import { shortStatusText, userFacingError } from '../../lib/diagnostics';
import type { SharedSettingsDraft } from '@/lib/accountProfile';

type Props = {
  setupState: DesktopSetupState;
  saving: boolean;
  voicePackBusyId?: string | null;
  voicePackProgress?: DesktopVoicePackInstallProgress | null;
  onSave: (values: Partial<DesktopSetupValues>) => boolean | void | Promise<boolean | void>;
  onInstallVoicePack?: (packId: string) => void;
  onSelectTtsVoicePack?: (pack: DesktopVoicePackSummary) => void;
  onRemoveVoicePack?: (packId: string) => void;
  onDismiss?: () => void;
  onOpenPath?: (targetPath: string) => void;
  onOpenChromeExtensions?: () => void;
  onCopyText?: (textValue: string) => void;
  memoryState?: DesktopMemoryState | null;
  memoryLoading?: boolean;
  memorySaving?: boolean;
  onReloadMemory?: () => void;
  onSaveMemory?: (content: string) => boolean | void | Promise<boolean | void>;
  localIntelligenceApi?: {
    apiBaseUrl?: string | null;
    token?: string | null;
    sessionId?: string | null;
  } | null;
  updateStatus?: DesktopUpdateStatus | null;
  checkingUpdates?: boolean;
  installingUpdate?: boolean;
  onCheckUpdates?: () => void;
  onInstallUpdate?: () => void;
  telegramBotConfigs?: TelegramBotConfig[];
  sessions?: SessionSummary[];
  runtimeOrchestratorStatus?: RuntimeOrchestratorStatus | null;
  currentMaxTurns?: number | null;
  onCreateTelegramBotConfig?: (payload: { label: string; bot_token: string }) => void;
  onUpdateTelegramBotConfig?: (botConfigId: string, payload: { label?: string; bot_token?: string; is_default?: boolean }) => void;
  onDeleteTelegramBotConfig?: (botConfigId: string) => void;
  onConfigureRuntimeOrchestrator?: (payload: { enabled?: boolean; default_max_concurrent_chats?: number | null }) => void;
  onUpdateGeneralAgentConfig?: (payload: { max_turns?: number }) => void;
  remoteAuthStatus?: DesktopRemoteAuthStatus | null;
  onRefreshRemoteAuth?: () => Promise<DesktopRemoteAuthStatus | null> | DesktopRemoteAuthStatus | null | void;
  onCreateRemotePairingToken?: () => Promise<DesktopRemotePairingToken | null> | DesktopRemotePairingToken | null | void;
  remoteSecretItems?: DesktopRemoteSecretItem[];
  remoteSecretsBusy?: boolean;
  remoteSecretsMessage?: string | null;
  onRefreshRemoteSecrets?: () => void;
  onSaveSetupSecrets?: (values: Partial<DesktopSetupValues>) => void;
  onSaveLoginCredentials?: (payload: { email?: string; password?: string }) => void;
  onApplySetupSecrets?: () => void;
  onDeleteRemoteSecret?: (namespace: string, name: string) => void;
  onRemoveLocalRuntimeSecret?: (name: keyof DesktopSetupValues) => void;
  onDeleteRemoteAccountData?: () => void;
  recoveryItems?: RecoveryArchiveItem[];
  pendingConfirmations?: PendingConfirmation[];
  recoveryBusyId?: string | null;
  recoveryMessage?: string | null;
  onRefreshRecovery?: () => void;
  onApprovePendingConfirmation?: (confirmationId: string) => void;
  onDenyPendingConfirmation?: (confirmationId: string) => void;
  onRestoreRecoveryItem?: (archiveId: string) => void;
  onPermanentDeleteRecoveryItem?: (archiveId: string) => void;
  onRestoreManagedWorkspace?: () => void;
  cloudChatBackupEnabled?: boolean;
  cloudBackupPreferenceBusy?: boolean;
  onToggleCloudChatBackup?: (enabled: boolean) => void;
  sharedSettingsDraft?: SharedSettingsDraft | null;
  sharedSettingsSaving?: boolean;
  sharedSettingsStatus?: string | null;
  onSharedSettingsDraftChange?: (draft: SharedSettingsDraft) => void;
  onSaveSharedSettings?: () => boolean | void | Promise<boolean | void>;
};

type SettingsTabKey = 'general' | 'onboarding' | 'chrome' | 'remote' | 'telegram' | 'voice' | 'recovery';

const SETTINGS_TABS: Array<{ key: SettingsTabKey; label: string; description: string }> = [
  { key: 'general', label: 'General', description: 'Models, keys, workspace, memory' },
  { key: 'onboarding', label: 'Onboarding', description: 'Project identity, tools, and workflows' },
  { key: 'chrome', label: 'Chrome Extension', description: 'Browser helper and screen reading' },
  { key: 'remote', label: 'Devices', description: 'Sign-in, phone pairing, other computers' },
  { key: 'telegram', label: 'Telegram', description: 'Bot connection and routing' },
  { key: 'voice', label: 'Voice', description: 'Speech input, voices, and Jarvis' },
  { key: 'recovery', label: 'Recovery', description: 'Restore archived app data' },
];

const API_KEY_FIELDS: { key: keyof DesktopSetupValues; label: string }[] = [
  { key: 'OPENAI_API_KEY', label: 'OpenAI API key' },
  { key: 'ANTHROPIC_API_KEY', label: 'Anthropic API key' },
  { key: 'GOOGLE_API_KEY', label: 'Google Gemini API key' },
  { key: 'XAI_API_KEY', label: 'xAI Grok API key' },
  { key: 'DEEPSEEK_API_KEY', label: 'DeepSeek API key' },
  { key: 'NVIDIA_API_KEY', label: 'NVIDIA API key' },
  { key: 'OPENROUTER_API_KEY', label: 'OpenRouter API key' },
];

function setupValuesWithoutPlannerOverride(values: Partial<DesktopSetupValues> | null | undefined): DesktopSetupValues {
  return {
    ...normalizeDesktopSetupValues(values),
    PLANNER_MODEL: '',
  };
}

const LIVE_VALIDATION_FIELDS: Array<keyof DesktopSetupValues> = [
  'OPENAI_API_KEY',
  'ANTHROPIC_API_KEY',
  'GOOGLE_API_KEY',
  'XAI_API_KEY',
  'DEEPSEEK_API_KEY',
  'NVIDIA_API_KEY',
  'OPENROUTER_API_KEY',
  'TELEGRAM_BOT_TOKEN',
  'ALLOWED_USER_IDS',
];

function parseTelegramUserIds(value: string) {
  const ids: string[] = [];
  String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
    .forEach((item) => {
      const normalized = item.startsWith('+') ? item.slice(1) : item;
      if (/^\d+$/.test(normalized) && !ids.includes(normalized)) {
        ids.push(normalized);
      }
    });
  return ids;
}

function formatTelegramUserIds(ids: string[]) {
  return ids.map((item) => item.trim()).filter(Boolean).join(', ');
}

export function DesktopSetupPanel({
  setupState,
  saving,
  voicePackBusyId,
  voicePackProgress,
  onSave,
  onInstallVoicePack,
  onSelectTtsVoicePack,
  onRemoveVoicePack,
  onDismiss,
  onOpenPath,
  onOpenChromeExtensions,
  onCopyText,
  memoryState,
  memoryLoading = false,
  memorySaving = false,
  onReloadMemory,
  onSaveMemory,
  localIntelligenceApi,
  updateStatus,
  checkingUpdates = false,
  installingUpdate = false,
  onCheckUpdates,
  onInstallUpdate,
  telegramBotConfigs = [],
  sessions = [],
  runtimeOrchestratorStatus,
  onCreateTelegramBotConfig,
  onUpdateTelegramBotConfig,
  onDeleteTelegramBotConfig,
  onConfigureRuntimeOrchestrator,
  remoteAuthStatus,
  onRefreshRemoteAuth,
  onCreateRemotePairingToken,
  remoteSecretItems = [],
  remoteSecretsBusy = false,
  onSaveLoginCredentials,
  onDeleteRemoteSecret,
  onRemoveLocalRuntimeSecret,
  onDeleteRemoteAccountData,
  recoveryItems = [],
  pendingConfirmations = [],
  recoveryBusyId = null,
  recoveryMessage = null,
  onRefreshRecovery,
  onApprovePendingConfirmation,
  onDenyPendingConfirmation,
  onRestoreRecoveryItem,
  onPermanentDeleteRecoveryItem,
  onRestoreManagedWorkspace,
  cloudChatBackupEnabled = true,
  cloudBackupPreferenceBusy = false,
  onToggleCloudChatBackup,
  sharedSettingsDraft,
  sharedSettingsSaving = false,
  sharedSettingsStatus = null,
  onSharedSettingsDraftChange,
  onSaveSharedSettings,
}: Props) {
  const [values, setValues] = useState<DesktopSetupValues>(() => setupValuesWithoutPlannerOverride(setupState.values));
  const [memoryDraft, setMemoryDraft] = useState(memoryState?.content || '');
  const [fieldValidation, setFieldValidation] = useState<Record<string, DesktopSetupFieldValidation>>({});
  const [newTelegramBotLabel, setNewTelegramBotLabel] = useState('');
  const [newTelegramBotToken, setNewTelegramBotToken] = useState('');
  const [newTelegramUserId, setNewTelegramUserId] = useState('');
  const [gmailLoginEmail, setGmailLoginEmail] = useState('');
  const [gmailLoginPassword, setGmailLoginPassword] = useState('');
  const [maxConcurrentChatsDraft, setMaxConcurrentChatsDraft] = useState(String(runtimeOrchestratorStatus?.max_concurrent_chats || 4));
  const [activeTab, setActiveTab] = useState<SettingsTabKey>('general');
  const [onboardingSuggestion, setOnboardingSuggestion] = useState<OnboardingSuggestion | null>(null);
  const [remoteBusy, setRemoteBusy] = useState(false);
  const [remotePairingToken, setRemotePairingToken] = useState('');
  const [remotePairingUri, setRemotePairingUri] = useState('');
  const [remotePairingExpiresIn, setRemotePairingExpiresIn] = useState<number | null>(null);
  const [remoteMessage, setRemoteMessage] = useState('');
  const [remoteDesktops, setRemoteDesktops] = useState<DesktopRemoteAccountDesktop[]>([]);
  const [codexAuthStatus, setCodexAuthStatus] = useState<DesktopCodexAuthStatus | null>(setupState.codexAuth || null);
  const [codexDeviceLogin, setCodexDeviceLogin] = useState<DesktopCodexDeviceLogin | null>(null);
  const [codexBusy, setCodexBusy] = useState(false);
  const [codexMessage, setCodexMessage] = useState('');
  const [desktopShortcutBusy, setDesktopShortcutBusy] = useState(false);
  const [desktopShortcutMessage, setDesktopShortcutMessage] = useState('');
  const [desktopShortcutFailed, setDesktopShortcutFailed] = useState(false);
  const [dismissPromptOpen, setDismissPromptOpen] = useState(false);
  const [dismissSaveError, setDismissSaveError] = useState('');
  const [savingChanges, setSavingChanges] = useState(false);
  const [saveFeedback, setSaveFeedback] = useState<{ tone: 'neutral' | 'success' | 'error'; message: string } | null>(null);
  const validationTimersRef = useRef<Record<string, ReturnType<typeof setTimeout> | null>>({});
  const validationRunRef = useRef<Record<string, number>>({});
  const editedValueKeysRef = useRef<Set<keyof DesktopSetupValues>>(new Set());
  const codexPollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sharedSettingsBaselineRef = useRef(sharedSettingsDraft ? JSON.stringify(sharedSettingsDraft) : '');
  const memoryBaselineRef = useRef(memoryState?.content || '');

  useEffect(() => {
    setValues((current) => {
      const nextValues = setupValuesWithoutPlannerOverride(setupState.values);
      editedValueKeysRef.current.forEach((fieldKey) => {
        nextValues[fieldKey] = current[fieldKey];
      });
      return nextValues;
    });
    setFieldValidation((current) => {
      const next: Record<string, DesktopSetupFieldValidation> = {};
      editedValueKeysRef.current.forEach((fieldKey) => {
        const validation = current[String(fieldKey)];
        if (validation) {
          next[String(fieldKey)] = validation;
        }
      });
      return next;
    });
    setCodexAuthStatus(setupState.codexAuth || null);
  }, [setupState]);

  useEffect(() => {
    setMaxConcurrentChatsDraft(String(runtimeOrchestratorStatus?.max_concurrent_chats || 4));
  }, [runtimeOrchestratorStatus?.max_concurrent_chats]);

  useEffect(() => {
    const nextContent = memoryState?.content || '';
    memoryBaselineRef.current = nextContent;
    setMemoryDraft(nextContent);
  }, [memoryState?.content, memoryState?.memoryFilePath]);

  useEffect(() => {
    if (String(sharedSettingsStatus || '').toLowerCase().includes('saved')) {
      sharedSettingsBaselineRef.current = sharedSettingsDraft ? JSON.stringify(sharedSettingsDraft) : '';
    }
  }, [sharedSettingsDraft, sharedSettingsStatus]);

  useEffect(() => {
    const apiBaseUrl = localIntelligenceApi?.apiBaseUrl;
    const token = localIntelligenceApi?.token;
    const workspace = String(setupState.values.DEFAULT_WORKSPACE || '').trim();
    if (!apiBaseUrl || !token || !workspace) {
      setOnboardingSuggestion(null);
      return;
    }

    let disposed = false;
    void (async () => {
      try {
        const response = await fetchProjectOnboarding(apiBaseUrl, token, workspace);
        if (!disposed) {
          setOnboardingSuggestion(buildOnboardingSuggestion(response.profile, workspace));
        }
      } catch {
        if (!disposed) {
          setOnboardingSuggestion(null);
        }
      }
    })();

    return () => {
      disposed = true;
    };
  }, [localIntelligenceApi?.apiBaseUrl, localIntelligenceApi?.token, setupState.values.DEFAULT_WORKSPACE, setupState.releaseVersion]);

  useEffect(() => {
    setActiveTab('general');
  }, [setupState.required, setupState.releaseVersion]);

  useEffect(() => {
    setRemotePairingToken('');
    setRemotePairingUri('');
    setRemotePairingExpiresIn(null);
    setRemoteMessage('');
    setRemoteDesktops(remoteAuthStatus?.desktop ? [remoteAuthStatus.desktop] : []);
  }, [remoteAuthStatus?.desktop?.desktop_id, remoteAuthStatus?.signedIn, setupState.releaseVersion]);

  useEffect(() => () => {
    Object.values(validationTimersRef.current).forEach((timer) => {
      if (timer) {
        clearTimeout(timer);
      }
    });
    if (codexPollTimerRef.current) {
      clearTimeout(codexPollTimerRef.current);
      codexPollTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    let disposed = false;
    void (async () => {
      try {
        const status = await loadDesktopCodexAuthStatus();
        if (!disposed && status) {
          setCodexAuthStatus(status);
        }
      } catch {
        // Keep setup usable if the local shell cannot inspect ChatGPT auth yet.
      }
    })();
    return () => {
      disposed = true;
    };
  }, [setupState.releaseVersion]);

  const scheduleCodexDevicePoll = (delaySeconds = 5) => {
    if (codexPollTimerRef.current) {
      clearTimeout(codexPollTimerRef.current);
    }
    codexPollTimerRef.current = setTimeout(() => {
      void (async () => {
        try {
          const status = await pollDesktopCodexDeviceLogin();
          if (!status) {
            setCodexMessage('ChatGPT sign-in polling is unavailable in this desktop shell.');
            return;
          }
          setCodexAuthStatus(status);
          if (status.ok || status.configured || status.state === 'connected') {
            setCodexDeviceLogin(null);
            setCodexMessage('ChatGPT subscription connected. Save settings to refresh active model lists and workers.');
            return;
          }
          if (status.state === 'pending') {
            scheduleCodexDevicePoll(5);
            return;
          }
          setCodexMessage(status.detail || status.error || 'ChatGPT sign-in did not complete.');
        } catch (error) {
          setCodexMessage(userFacingError(error, 'ChatGPT sign-in polling failed.'));
        }
      })();
    }, Math.max(1, delaySeconds) * 1000);
  };

  const beginCodexDeviceLogin = async () => {
    setCodexBusy(true);
    setCodexMessage('');
    try {
      const login = await startDesktopCodexDeviceLogin();
      if (!login) {
        setCodexMessage('ChatGPT sign-in is unavailable in this desktop shell.');
        return;
      }
      setCodexDeviceLogin(login);
      const code = login.userCode || login.user_code || '';
      setCodexMessage(code ? `Browser opened. Enter code ${code} to connect ChatGPT.` : 'Browser opened for ChatGPT sign-in.');
      scheduleCodexDevicePoll(Number(login.intervalSeconds || login.interval_seconds || 5));
    } catch (error) {
      setCodexMessage(userFacingError(error, 'Could not start ChatGPT sign-in.'));
    } finally {
      setCodexBusy(false);
    }
  };

  const disconnectCodexAuth = async () => {
    setCodexBusy(true);
    setCodexMessage('');
    try {
      const status = await logoutDesktopCodexAuth();
      setCodexAuthStatus(status || { configured: false });
      setCodexDeviceLogin(null);
      if (codexPollTimerRef.current) {
        clearTimeout(codexPollTimerRef.current);
        codexPollTimerRef.current = null;
      }
      setCodexMessage('Deleted the local ChatGPT subscription sign-in from this computer.');
    } catch (error) {
      setCodexMessage(userFacingError(error, 'Could not delete ChatGPT sign-in.'));
    } finally {
      setCodexBusy(false);
    }
  };

  const addDesktopShortcut = async () => {
    setDesktopShortcutBusy(true);
    setDesktopShortcutMessage('');
    setDesktopShortcutFailed(false);
    try {
      const result = await createDesktopShortcut();
      if (!result) {
        throw new Error('Desktop shortcut controls are unavailable in this shell.');
      }
      setDesktopShortcutMessage(result.message || `Desktop shortcut created: ${result.shortcutPath || 'EmploAI.lnk'}`);
    } catch (error) {
      setDesktopShortcutFailed(true);
      setDesktopShortcutMessage(userFacingError(error, 'Desktop shortcut was not created.'));
    } finally {
      setDesktopShortcutBusy(false);
    }
  };

  const scheduleFieldValidation = (key: keyof DesktopSetupValues, nextValue: string) => {
    const fieldKey = String(key);
    const trimmed = nextValue.trim();

    if (validationTimersRef.current[fieldKey]) {
      clearTimeout(validationTimersRef.current[fieldKey]!);
      validationTimersRef.current[fieldKey] = null;
    }

    if (!trimmed) {
      setFieldValidation((current) => {
        const next = { ...current };
        delete next[fieldKey];
        return next;
      });
      return;
    }

    const runId = (validationRunRef.current[fieldKey] || 0) + 1;
    validationRunRef.current[fieldKey] = runId;
    setFieldValidation((current) => ({
      ...current,
      [fieldKey]: {
        field: key,
        status: 'checking',
        message: 'Checking…',
      },
    }));

    validationTimersRef.current[fieldKey] = setTimeout(() => {
      void (async () => {
        try {
          const result = await validateDesktopSetupField(key, nextValue);
          if (validationRunRef.current[fieldKey] !== runId) {
            return;
          }
          if (!result) {
            setFieldValidation((current) => ({
              ...current,
              [fieldKey]: {
                field: key,
                status: 'error',
                message: 'Validation unavailable in this environment',
              },
            }));
            return;
          }
          setFieldValidation((current) => ({
            ...current,
            [fieldKey]: result,
          }));
        } catch (error) {
          if (validationRunRef.current[fieldKey] !== runId) {
            return;
          }
          setFieldValidation((current) => ({
            ...current,
            [fieldKey]: {
              field: key,
              status: 'error',
              message: userFacingError(error, 'Validation failed.'),
            },
          }));
        }
      })();
    }, 450);
  };

  const updateValue = (key: keyof DesktopSetupValues, nextValue: string) => {
    editedValueKeysRef.current.add(key);
    setSaveFeedback(null);
    setValues((current) => ({ ...current, [key]: nextValue }));
    if (LIVE_VALIDATION_FIELDS.includes(key)) {
      scheduleFieldValidation(key, nextValue);
    }
  };

  const applyOnboardingProfileSuggestion = (profile: ProjectOnboardingProfile) => {
    const workspace = String(profile.workspace || values.DEFAULT_WORKSPACE || setupState.values.DEFAULT_WORKSPACE || '').trim();
    setOnboardingSuggestion(buildOnboardingSuggestion(profile, workspace));
  };

  const setupSecretByName = new Map(
    remoteSecretItems
      .filter((item) => item.namespace === 'setup')
      .map((item) => [item.name, item] as const),
  );
  const codexConnected = Boolean(codexAuthStatus?.configured);
  const openAiProviderMode = values.OPENAI_PROVIDER_MODE === 'chatgpt' ? 'chatgpt' : 'api_key';
  const openAiApiKeyAvailable = Boolean(
    setupSecretByName.get('OPENAI_API_KEY')
    || String(setupState.localRuntimeSecrets?.OPENAI_API_KEY?.redacted_value || '').trim()
    || String(values.OPENAI_API_KEY || '').trim()
  );
  const showOpenAiProviderMode = codexConnected && openAiApiKeyAvailable;
  const lockedProviderSecretNames = new Set<keyof DesktopSetupValues>(
    API_KEY_FIELDS
      .filter((field) => setupSecretByName.has(String(field.key)))
      .map((field) => field.key),
  );
  const displayedConfiguredProviders = configuredProviderChipLabels(
    setupState.configuredProviders,
    Array.from(lockedProviderSecretNames).map(String),
  );
  const visibleConfiguredProviders = (() => {
    const providers = [...displayedConfiguredProviders];
    if (codexConnected && !providers.includes('OpenAI Codex (ChatGPT)')) {
      providers.push('OpenAI Codex (ChatGPT)');
    }
    return providers;
  })();
  const valuesWithoutLockedProviderKeys = () => {
    const nextValues = setupValuesWithoutPlannerOverride(values);
    lockedProviderSecretNames.forEach((fieldKey) => {
      nextValues[fieldKey] = '';
    });
    return nextValues;
  };
  const saveEditedValues = async () => {
    const nextValues = valuesWithoutLockedProviderKeys();
    const saved = await onSave(nextValues);
    if (saved === false) throw new Error('Setup values were not saved.');
    editedValueKeysRef.current.clear();
    setFieldValidation({});
    return true;
  };

  const title = setupState.required ? 'Desktop setup is required' : 'Setup and settings';
  const primaryActionLabel = setupState.required ? 'Save Setup And Continue' : 'Save Settings';
  const subtitle = setupState.required
    ? 'Complete the local runtime settings before EmploAI starts the agent on this machine.'
    : setupState.versioned
      ? 'This release reopened setup once so you can review paths, keys, and optional Telegram access.'
      : 'Change API keys, Telegram access, workspace, extension help, and bundled runtime checks at any time.';

  const voicePackState = setupState.voicePacks;
  const voicePacks = voicePackState?.packs ?? [];
  const sttVoicePacks = voicePacks.filter((pack) => pack.kind !== 'tts');
  const ttsVoicePacks = voicePacks.filter((pack) => pack.kind === 'tts');
  const selectedVoiceEngine = values.VOICE_DEFAULT_ENGINE || voicePackState?.defaultEngine || VOICE_ENGINE_NONE;
  const selectedVoicePack = voicePacks.find((pack) => pack.id === selectedVoiceEngine) ?? null;
  const selectedTtsBackend = String(setupState.voiceStatus?.tts_backend || '').trim();
  const voiceIssues = setupState.voiceStatus?.issues?.filter(Boolean) ?? [];
  const voiceModel = setupState.voiceStatus?.stt_model || 'local whisper';
  const voiceDraftModel = setupState.voiceStatus?.draft_model;
  const voiceSelectionSource = voicePackState?.selectionSource || 'settings';
  const voiceMetaSummary = selectedVoiceEngine === VOICE_ENGINE_NONE
    ? 'Voice input is off'
    : setupState.voiceAvailable
      ? `${selectedVoicePack?.title || 'English voice pack'} ready (${voiceModel}${voiceDraftModel ? ` + ${voiceDraftModel}` : ''})`
      : `${selectedVoicePack?.title || 'Voice pack'} unavailable`;
  const visibleVoiceIssue = selectedVoiceEngine === VOICE_ENGINE_NONE ? null : voiceIssues[0];
  const standaloneMode = Boolean(remoteAuthStatus?.cloudDisabled || remoteAuthStatus?.standalone);
  useEffect(() => {
    if (standaloneMode && activeTab === 'remote') setActiveTab('general');
  }, [standaloneMode, activeTab]);
  const memoryDirty = memoryDraft !== memoryBaselineRef.current;
  const sharedSettingsDirty = Boolean(
    sharedSettingsDraft
    && JSON.stringify(sharedSettingsDraft) !== sharedSettingsBaselineRef.current
  );
  const settingsDirty = editedValueKeysRef.current.size > 0 || memoryDirty || sharedSettingsDirty;
  const saveBusy = Boolean(saving || memorySaving || sharedSettingsSaving || savingChanges);
  const requestDismiss = () => {
    if (!onDismiss) return;
    if (settingsDirty) {
      setDismissSaveError('');
      setDismissPromptOpen(true);
      return;
    }
    onDismiss();
  };
  const persistDirtySections = async () => {
    const savedSections: Array<'setup' | 'memory' | 'local'> = [];
    if (editedValueKeysRef.current.size > 0) {
      await saveEditedValues();
      savedSections.push('setup');
    }
    if (memoryDirty) {
      if (!onSaveMemory) throw new Error('Memory saving is unavailable.');
      const memorySaved = await onSaveMemory(memoryDraft);
      if (memorySaved === false) throw new Error('Memory was not saved.');
      memoryBaselineRef.current = memoryDraft;
      savedSections.push('memory');
    }
    if (sharedSettingsDirty) {
      if (!onSaveSharedSettings) throw new Error('Local settings saving is unavailable.');
      const sharedSaved = await onSaveSharedSettings();
      if (sharedSaved === false) throw new Error(standaloneMode ? 'Local settings were not saved.' : 'Shared settings were not saved.');
      sharedSettingsBaselineRef.current = sharedSettingsDraft ? JSON.stringify(sharedSettingsDraft) : '';
      savedSections.push('local');
    }
    return savedSections;
  };
  const saveAllChanges = async () => {
    if (!settingsDirty || saveBusy) return;
    setSavingChanges(true);
    setSaveFeedback(null);
    try {
      const savedSections = await persistDirtySections();
      const localOnly = savedSections.length === 1 && savedSections[0] === 'local';
      setSaveFeedback({
        tone: 'success',
        message: localOnly ? 'Local runtime settings saved and applied.' : 'All changes saved and applied.',
      });
    } catch (saveError) {
      setSaveFeedback({
        tone: 'error',
        message: saveError instanceof Error ? saveError.message : 'Settings were not saved.',
      });
    } finally {
      setSavingChanges(false);
    }
  };
  const saveSharedSettingsSection = async () => {
    if (!onSaveSharedSettings || saveBusy) return;
    setSavingChanges(true);
    setSaveFeedback(null);
    try {
      const sharedSaved = await onSaveSharedSettings();
      if (sharedSaved === false) throw new Error(standaloneMode ? 'Local settings were not saved.' : 'Shared settings were not saved.');
      sharedSettingsBaselineRef.current = sharedSettingsDraft ? JSON.stringify(sharedSettingsDraft) : '';
      setSaveFeedback({
        tone: 'success',
        message: standaloneMode ? 'Local runtime settings saved and applied.' : 'Shared settings saved.',
      });
    } catch (saveError) {
      setSaveFeedback({
        tone: 'error',
        message: saveError instanceof Error ? saveError.message : 'Settings were not saved.',
      });
    } finally {
      setSavingChanges(false);
    }
  };
  const saveDirtySections = async () => {
    if (saveBusy) return;
    setDismissSaveError('');
    setSavingChanges(true);
    try {
      await persistDirtySections();
      setDismissPromptOpen(false);
      onDismiss?.();
    } catch (saveError) {
      setDismissSaveError(saveError instanceof Error ? saveError.message : 'Settings were not saved.');
      setDismissPromptOpen(true);
    } finally {
      setSavingChanges(false);
    }
  };
  const discardDirtySections = () => {
    editedValueKeysRef.current.clear();
    setValues(setupValuesWithoutPlannerOverride(setupState.values));
    setFieldValidation({});
    setMemoryDraft(memoryState?.content || '');
    memoryBaselineRef.current = memoryState?.content || '';
    if (sharedSettingsDraft && onSharedSettingsDraftChange && sharedSettingsBaselineRef.current) {
      try {
        onSharedSettingsDraftChange(JSON.parse(sharedSettingsBaselineRef.current));
      } catch {
        // Keep the current shared draft if its baseline is unavailable.
      }
    }
    setDismissPromptOpen(false);
    onDismiss?.();
  };
  const updateSummary = updateStatus?.message
    ? updateStatus.message
    : updateStatus?.updateAvailable
    ? `Update ready: ${updateStatus.update?.tagName || updateStatus.update?.version}`
    : updateStatus?.lastError
      ? `Check failed: ${updateStatus.lastError}`
      : updateStatus?.checked
        ? 'No update pending'
        : 'Update check pending';

  const validationTone = (status?: DesktopSetupFieldValidation['status']) => {
    if (status === 'valid') {
      return styles.validationTextValid;
    }
    if (status === 'invalid') {
      return styles.validationTextInvalid;
    }
    if (status === 'error') {
      return styles.validationTextError;
    }
    return styles.validationTextChecking;
  };

  const fallbackBotId = telegramBotConfigs[0]?.id || null;
  const allowedTelegramUserIds = parseTelegramUserIds(values.ALLOWED_USER_IDS);
  const settingsTabs = standaloneMode
    ? SETTINGS_TABS.filter((tab) => tab.key !== 'remote')
    : SETTINGS_TABS;
  const selectedSettingsTab = settingsTabs.find((item) => item.key === activeTab) || settingsTabs[0];
  const maxConcurrentValue = Math.min(12, Math.max(1, Number.parseInt(maxConcurrentChatsDraft || '4', 10) || 4));
  const codexUserCode = codexDeviceLogin?.userCode || codexDeviceLogin?.user_code || '';
  const codexVerificationUri = codexDeviceLogin?.verificationUri || codexDeviceLogin?.verification_uri || 'https://auth.openai.com/codex/device';
  const codexExpiresAt = codexAuthStatus?.expiresAtIso ? new Date(codexAuthStatus.expiresAtIso) : null;
  const codexExpiresAtLabel = codexExpiresAt && !Number.isNaN(codexExpiresAt.getTime())
    ? codexExpiresAt.toLocaleString()
    : '';
  const codexTokenExpired = codexConnected && codexAuthStatus?.accessTokenUsable === false;
  const codexCanRefreshToken = Boolean(codexAuthStatus?.hasRefreshToken);
  const codexNeedsSignIn = !codexConnected || (codexTokenExpired && !codexCanRefreshToken);
  const codexStatusTone = codexDeviceLogin
    ? 'pending'
    : codexConnected
      ? codexTokenExpired
        ? codexCanRefreshToken ? 'warning' : 'error'
        : 'connected'
      : 'offline';
  const codexStatusLabel = codexDeviceLogin
    ? 'Pending'
    : codexConnected
      ? codexTokenExpired ? 'Expired' : 'Connected'
      : 'Not connected';
  const codexPrimaryLabel = codexBusy
    ? 'Working...'
    : codexNeedsSignIn
      ? codexConnected ? 'Sign In Again' : 'Sign In With ChatGPT'
      : 'ChatGPT Connected';
  const codexPrimaryDisabled = codexBusy || Boolean(codexDeviceLogin) || !codexNeedsSignIn;
  const codexConnectionDetail = codexConnected
    ? codexTokenExpired
      ? codexCanRefreshToken
        ? 'Current access token expired; it will refresh locally on the next ChatGPT request.'
        : 'ChatGPT sign-in expired. Sign in again to use subscription models.'
      : `${codexAuthStatus?.accountId ? `Account ${codexAuthStatus.accountId}. ` : ''}${codexExpiresAtLabel ? `Current token expires ${codexExpiresAtLabel}.` : 'Token refresh is handled locally when needed.'}`
    : 'Not connected. Tokens are saved only on this computer after sign-in.';
  const codexStatusMessage = codexMessage || codexConnectionDetail;
  const codexStatusMessageStyle = codexStatusTone === 'connected'
    ? styles.validationTextValid
    : codexStatusTone === 'error'
      ? styles.validationTextInvalid
      : codexStatusTone === 'warning'
        ? styles.validationTextError
        : styles.validationTextChecking;

  const setVoiceDefaultEngine = (nextEngine: string) => {
    setValues((current) => {
      if (nextEngine === VOICE_ENGINE_ENGLISH) {
        return {
          ...current,
          VOICE_ENGLISH_REQUESTED: '1',
          VOICE_DEFAULT_ENGINE: VOICE_ENGINE_ENGLISH,
        };
      }
      if (nextEngine === VOICE_ENGINE_HEBREW) {
        return {
          ...current,
          VOICE_HEBREW_REQUESTED: '1',
          VOICE_DEFAULT_ENGINE: VOICE_ENGINE_HEBREW,
        };
      }
      return {
        ...current,
        VOICE_DEFAULT_ENGINE: VOICE_ENGINE_NONE,
      };
    });
  };

  const toggleVoicePackRequest = (pack: DesktopVoicePackSummary) => {
    setValues((current) => {
      if (pack.id === VOICE_ENGINE_ENGLISH) {
        const nextRequested = current.VOICE_ENGLISH_REQUESTED === '0';
        const fallbackEngine = current.VOICE_HEBREW_REQUESTED === '1' ? VOICE_ENGINE_HEBREW : VOICE_ENGINE_NONE;
        return {
          ...current,
          VOICE_ENGLISH_REQUESTED: nextRequested ? '1' : '0',
          VOICE_DEFAULT_ENGINE:
            !nextRequested && current.VOICE_DEFAULT_ENGINE === VOICE_ENGINE_ENGLISH
              ? fallbackEngine
              : current.VOICE_DEFAULT_ENGINE,
        };
      }

      const nextRequested = current.VOICE_HEBREW_REQUESTED !== '1';
      const fallbackEngine = current.VOICE_ENGLISH_REQUESTED !== '0' ? VOICE_ENGINE_ENGLISH : VOICE_ENGINE_NONE;
      return {
        ...current,
        VOICE_HEBREW_REQUESTED: nextRequested ? '1' : '0',
        VOICE_DEFAULT_ENGINE:
          !nextRequested && current.VOICE_DEFAULT_ENGINE === VOICE_ENGINE_HEBREW
            ? fallbackEngine
            : current.VOICE_DEFAULT_ENGINE,
      };
    });
  };

  const adjustMaxConcurrentChats = (delta: number) => setMaxConcurrentChatsDraft(String(Math.min(12, Math.max(1, maxConcurrentValue + delta))));
  const addTelegramUserId = () => {
    const nextId = newTelegramUserId.trim().replace(/^\+/, '');
    if (!/^\d+$/.test(nextId)) {
      setFieldValidation((current) => ({
        ...current,
        ALLOWED_USER_IDS: {
          field: 'ALLOWED_USER_IDS',
          status: 'invalid',
          message: 'Telegram user IDs must be numeric.',
        },
      }));
      return;
    }
    const nextIds = allowedTelegramUserIds.includes(nextId)
      ? allowedTelegramUserIds
      : [...allowedTelegramUserIds, nextId];
    updateValue('ALLOWED_USER_IDS', formatTelegramUserIds(nextIds));
    setNewTelegramUserId('');
  };
  const removeTelegramUserId = (userId: string) => {
    const nextIds = allowedTelegramUserIds.filter((item) => item !== userId);
    updateValue('ALLOWED_USER_IDS', formatTelegramUserIds(nextIds));
  };
  const remoteWorkerStatus = setupState.remoteControlStatus;
  const remoteConfigured = Boolean(remoteAuthStatus?.signedIn || setupState.remoteControlConfigured);
  const remotePartial = Boolean(setupState.remoteControlPartiallyConfigured);
  const remoteAccountEmail = remoteAuthStatus?.user?.email || 'not signed in';
  const remoteDesktopName =
    remoteAuthStatus?.desktop?.display_name ||
    remoteWorkerStatus?.desktopName ||
    remoteWorkerStatus?.desktop_name ||
    values.EMPLOAI_REMOTE_DESKTOP_NAME.trim() ||
    'EmploAI Desktop';

  const refreshRemoteConnection = async () => {
    setRemoteBusy(true);
    setRemoteMessage('Checking desktop connection...');
    try {
      if (!onRefreshRemoteAuth) {
        throw new Error('Remote account controls are unavailable in this shell.');
      }
      const status = await onRefreshRemoteAuth();
      const nextStatus = status || remoteAuthStatus;
      setRemoteDesktops(nextStatus?.desktop ? [nextStatus.desktop] : []);
      setRemoteMessage(
        nextStatus?.signedIn
          ? 'Desktop connected.'
          : nextStatus?.error
            ? userFacingError(nextStatus.error, 'Sign in to connect this desktop.')
            : 'Sign in to connect this desktop.'
      );
    } catch (error) {
      setRemoteMessage(userFacingError(error, 'Connection check failed.'));
    } finally {
      setRemoteBusy(false);
    }
  };

  const createRemotePairingToken = async () => {
    setRemoteBusy(true);
    setRemoteMessage('Creating one-time phone pairing token...');
    try {
      if (!onCreateRemotePairingToken) {
        throw new Error('Pairing token controls are unavailable in this shell.');
      }
      const pairing = await onCreateRemotePairingToken();
      if (!pairing) {
        throw new Error('Pairing token could not be created.');
      }
      setRemotePairingToken(pairing.pairing_token);
      setRemotePairingUri(buildPairingQrValue(pairing.pairing_uri, pairing.pairing_token));
      setRemotePairingExpiresIn(pairing.expires_in_seconds);
      setRemoteMessage(`Pairing QR ready for ${pairing.desktop_name || remoteDesktopName}.`);
    } catch (error) {
      setRemoteMessage(userFacingError(error, 'Pairing code was not created.'));
    } finally {
      setRemoteBusy(false);
    }
  };

  return (
    <View style={styles.shell}>
      <View style={styles.header}>
        <View style={styles.headerCopy}>
          <Text style={styles.eyebrow}>Desktop Setup</Text>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.subtitle}>{subtitle}</Text>
        </View>
        <View style={styles.versionBadge}>
          <Text style={styles.versionLabel}>Release</Text>
          <Text style={styles.versionValue}>{setupState.releaseVersion}</Text>
        </View>
      </View>

      <View style={styles.settingsFrame}>
        <View style={styles.settingsSidebar}>
          {onDismiss ? (
            <Pressable style={styles.backToAppButton} onPress={requestDismiss} disabled={saving}>
              <Text style={styles.backToAppButtonText}>Back to app</Text>
            </Pressable>
          ) : (
            <View style={styles.backToAppPlaceholder}>
              <Text style={styles.backToAppPlaceholderText}>Setup required</Text>
            </View>
          )}
          <View style={styles.settingsNavList}>
            {settingsTabs.map((tab) => {
              const selected = activeTab === tab.key;
              return (
                <Pressable
                  key={tab.key}
                  style={[styles.settingsNavItem, selected ? styles.settingsNavItemActive : null]}
                  onPress={() => setActiveTab(tab.key)}
                >
                  <Text style={[styles.settingsNavItemTitle, selected ? styles.settingsNavItemTitleActive : null]}>
                    {tab.label}
                  </Text>
                  <Text style={styles.settingsNavItemDescription}>{tab.description}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        <View style={styles.settingsContentPane}>
          <View style={styles.settingsContentHeader}>
            <View style={styles.settingsContentHeaderCopy}>
              <Text style={styles.settingsContentTitle}>{selectedSettingsTab.label}</Text>
              <Text style={styles.settingsContentSubtitle}>{selectedSettingsTab.description}</Text>
            </View>
          </View>

          <ScrollView style={styles.formScroll} contentContainerStyle={styles.formContent}>
            {setupState.validationIssues.length ? (
              <View style={styles.warningCard}>
                <Text style={styles.warningTitle}>Setup requirements</Text>
                {setupState.validationIssues.map((issue) => (
                  <Text key={issue} style={styles.warningLine}>
                    {`\u2022 ${issue}`}
                  </Text>
                ))}
              </View>
            ) : null}

            {onboardingSuggestion && activeTab !== 'onboarding' ? (
              <View style={styles.onboardingSuggestionCard}>
                <View style={styles.onboardingSuggestionCopy}>
                  <Text style={styles.onboardingSuggestionEyebrow}>Optional setup suggestion</Text>
                  <Text style={styles.onboardingSuggestionTitle}>{onboardingSuggestion.title}</Text>
                  <Text style={styles.onboardingSuggestionText}>{onboardingSuggestion.message}</Text>
                  {onboardingSuggestion.missingLabels.length ? (
                    <Text style={styles.onboardingSuggestionMeta}>
                      Missing: {onboardingSuggestion.missingLabels.join(', ')}
                    </Text>
                  ) : null}
                </View>
                <Pressable style={styles.compactActionButton} onPress={() => setActiveTab('onboarding')}>
                  <Text style={styles.compactActionButtonText}>{onboardingSuggestion.actionLabel}</Text>
                </Pressable>
              </View>
            ) : null}

            {activeTab === 'general' ? (
              <>
                {sharedSettingsDraft && onSharedSettingsDraftChange && onSaveSharedSettings ? (
                  <DesktopSetupSharedSettingsSection
                    draft={sharedSettingsDraft}
                    saving={saveBusy}
                    status={sharedSettingsStatus}
                    standaloneMode={standaloneMode}
                    onChange={(draft) => {
                      setSaveFeedback(null);
                      onSharedSettingsDraftChange(draft);
                    }}
                    onSave={() => void saveSharedSettingsSection()}
                  />
                ) : null}

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Runtime workers</Text>
                  <Text style={styles.helperText}>
                    Control how many independent chats may work at the same time when this desktop is not in a managed Fleet role.
                  </Text>
                  <View style={styles.settingCard}>
                    <View style={styles.settingRow}>
                      <View style={styles.settingRowCopy}>
                        <Text style={styles.settingRowTitle}>Running chats</Text>
                      </View>
                      <View style={styles.settingRowControls}>
                        <View style={styles.stepperControl}>
                          <Pressable style={styles.stepperButton} onPress={() => adjustMaxConcurrentChats(-1)}>
                            <Text style={styles.stepperButtonText}>-</Text>
                          </Pressable>
                          <TextInput
                            value={maxConcurrentChatsDraft}
                            onChangeText={setMaxConcurrentChatsDraft}
                            style={[styles.input, styles.numberInput]}
                            placeholder="4"
                            placeholderTextColor="#7f93b5"
                            autoCapitalize="none"
                            autoCorrect={false}
                          />
                          <Pressable style={styles.stepperButton} onPress={() => adjustMaxConcurrentChats(1)}>
                            <Text style={styles.stepperButtonText}>+</Text>
                          </Pressable>
                        </View>
                        <Pressable
                          style={[styles.compactActionButton, !onConfigureRuntimeOrchestrator ? styles.buttonDisabled : null]}
                          onPress={() => onConfigureRuntimeOrchestrator?.({ default_max_concurrent_chats: maxConcurrentValue })}
                          disabled={!onConfigureRuntimeOrchestrator}
                        >
                          <Text style={styles.compactActionButtonText}>Apply</Text>
                        </Pressable>
                      </View>
                    </View>
                  </View>
                </View>

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Desktop shortcut</Text>
                  <Text style={styles.helperText}>
                    Add a Windows desktop shortcut that starts this local Electron app through the repo startup script.
                  </Text>
                  <View style={styles.pathActions}>
                    <Pressable
                      style={[styles.pathButton, desktopShortcutBusy ? styles.buttonDisabled : null]}
                      onPress={() => void addDesktopShortcut()}
                      disabled={desktopShortcutBusy}
                    >
                      <Text style={styles.pathButtonText}>{desktopShortcutBusy ? 'Creating...' : 'Add Desktop Shortcut'}</Text>
                    </Pressable>
                  </View>
                  {desktopShortcutMessage ? (
                    <Text style={[styles.validationText, desktopShortcutFailed ? styles.validationTextError : styles.validationTextValid]}>
                      {desktopShortcutMessage}
                    </Text>
                  ) : null}
                </View>

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Workspace</Text>
                  <View style={styles.settingCard}>
                    <Text style={styles.settingCardTitle}>Default workspace folder</Text>
                    <Text style={styles.settingCardDescription}>
                      The starting folder the agent uses for file work on this computer. Chats can still be moved to another folder later.
                    </Text>
                    <TextInput
                      value={values.DEFAULT_WORKSPACE}
                      onChangeText={(next) => updateValue('DEFAULT_WORKSPACE', next)}
                      style={styles.input}
                      placeholder="C:\\Users\\You\\Documents"
                      placeholderTextColor="#7f93b5"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                  </View>
                </View>

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Model providers</Text>
                  <Text style={styles.helperText}>
                    Add at least one model provider so EmploAI knows which models it can use.
                  </Text>

                  <View style={styles.settingCard}>
                    <Text style={styles.settingCardTitle}>Provider keys</Text>
                    <Text style={styles.settingCardDescription}>
                      {standaloneMode
                        ? 'Keys are saved on this computer only. Use Delete local key to remove a provider key from local storage and the running runtime.'
                        : 'Paste the keys for the providers you want available in chat, Jarvis, Telegram, and Fleet workers.'}
                    </Text>
                    <View style={styles.providerRow}>
                      {(visibleConfiguredProviders.length ? visibleConfiguredProviders : ['none yet']).map((provider) => (
                        <View key={provider} style={styles.providerChip}>
                          <Text style={styles.providerChipText}>{provider}</Text>
                        </View>
                      ))}
                    </View>

                    {showOpenAiProviderMode ? (
                      <View style={styles.fieldBlock}>
                        <Text style={styles.settingRowTitle}>OpenAI model source</Text>
                        <Text style={styles.voiceModeHelper}>
                          Both an OpenAI API key and ChatGPT sign-in are available. Choose which OpenAI source should be used for defaults and model lists.
                        </Text>
                        <View style={styles.voiceModeRow}>
                          {[
                            { value: 'api_key', label: 'API key' },
                            { value: 'chatgpt', label: 'ChatGPT' },
                          ].map((option) => {
                            const selected = openAiProviderMode === option.value;
                            return (
                              <Pressable
                                key={option.value}
                                style={[styles.voiceModeButton, selected ? styles.voiceModeButtonActive : null]}
                                onPress={() => updateValue('OPENAI_PROVIDER_MODE', option.value)}
                              >
                                <Text style={[styles.voiceModeButtonText, selected ? styles.voiceModeButtonTextActive : null]}>
                                  {option.label}
                                </Text>
                              </Pressable>
                            );
                          })}
                        </View>
                      </View>
                    ) : null}

                    {API_KEY_FIELDS.map((field) => {
                      const vaultItem = setupSecretByName.get(String(field.key));
                      const lockedByVault = Boolean(vaultItem);
                      const localRuntimeSecret = setupState.localRuntimeSecrets?.[String(field.key)];
                      const localRuntimeRedactedValue = String(localRuntimeSecret?.redacted_value || '').trim();
                      const localDraftValue = String(values[field.key] || '').trim();
                      const hasSavedLocalKey = Boolean(localRuntimeRedactedValue);
                      const hasTypedLocalKey = Boolean(localDraftValue);
                      const showingLocalRuntimePreview = !lockedByVault
                        && !localDraftValue
                        && hasSavedLocalKey;
                      const hasLocalKey = !lockedByVault && (hasTypedLocalKey || hasSavedLocalKey);
                      const localKeyStatusText = hasSavedLocalKey
                        ? hasTypedLocalKey
                          ? 'Replacement typed; saved local key still exists until you save or delete it.'
                          : 'Saved locally on this computer.'
                        : 'Typed key is not saved yet.';
                      const inputValue = lockedByVault
                        ? (vaultItem?.redacted_value || 'Already saved')
                        : showingLocalRuntimePreview
                          ? localRuntimeRedactedValue
                          : values[field.key];
                      return (
                        <View key={field.key} style={styles.fieldBlock}>
                          <View style={styles.fieldLabelRow}>
                            <Text style={styles.fieldLabel}>{field.label}</Text>
                            {vaultItem ? (
                              <View style={styles.infoBadge}>
                                <Text style={styles.infoBadgeText}>i</Text>
                              </View>
                            ) : null}
                          </View>
                          <TextInput
                            value={inputValue}
                            onChangeText={(next) => {
                              if (!lockedByVault && !showingLocalRuntimePreview) {
                                updateValue(field.key, next);
                              }
                            }}
                            style={[styles.input, (lockedByVault || showingLocalRuntimePreview) ? styles.inputDisabled : null]}
                            placeholder={lockedByVault ? 'Already saved' : 'Enter key'}
                            placeholderTextColor="#7f93b5"
                            autoCapitalize="none"
                            autoCorrect={false}
                            secureTextEntry={!lockedByVault && !showingLocalRuntimePreview}
                            editable={!lockedByVault && !showingLocalRuntimePreview}
                            selectTextOnFocus={!lockedByVault && !showingLocalRuntimePreview}
                          />
                          {vaultItem ? (
                            <View style={styles.providerVaultStatus}>
                              <Text style={styles.providerVaultStatusText}>Saved in account vault.</Text>
                              <Pressable
                                style={[
                                  styles.providerVaultDeleteButton,
                                  (remoteSecretsBusy || !onDeleteRemoteSecret) ? styles.voiceModeButtonDisabled : null,
                                ]}
                                onPress={() => onDeleteRemoteSecret?.('setup', String(field.key))}
                                disabled={remoteSecretsBusy || !onDeleteRemoteSecret}
                              >
                                <Text style={styles.providerVaultDeleteText}>Delete saved key</Text>
                              </Pressable>
                            </View>
                          ) : null}
                          {hasLocalKey ? (
                            <View style={styles.providerVaultStatus}>
                              <Text style={styles.providerVaultStatusText}>{localKeyStatusText}</Text>
                              <Pressable
                                style={[
                                  styles.providerVaultDeleteButton,
                                  (saving || (hasSavedLocalKey && !onRemoveLocalRuntimeSecret)) ? styles.voiceModeButtonDisabled : null,
                                ]}
                                onPress={() => {
                                  updateValue(field.key, '');
                                  if (hasSavedLocalKey) {
                                    onRemoveLocalRuntimeSecret?.(field.key);
                                  }
                                }}
                                disabled={saving || (hasSavedLocalKey && !onRemoveLocalRuntimeSecret)}
                              >
                                <Text style={styles.providerVaultDeleteText}>{hasSavedLocalKey ? 'Delete local key' : 'Clear typed key'}</Text>
                              </Pressable>
                            </View>
                          ) : null}
                          {fieldValidation[field.key]?.message && !lockedByVault && !showingLocalRuntimePreview ? (
                            <Text style={[styles.validationText, validationTone(fieldValidation[field.key]?.status)]}>
                              {fieldValidation[field.key]?.message}
                            </Text>
                          ) : null}
                        </View>
                      );
                    })}
                  </View>

                  <View style={styles.settingCard}>
                    <View style={styles.settingRow}>
                      <View style={styles.settingRowCopy}>
                        <Text style={styles.settingCardTitle}>ChatGPT subscription</Text>
                        <Text style={styles.settingCardDescription}>
                          Sign in with OpenAI in the browser to use the local Codex provider without an OpenAI API key.
                        </Text>
                      </View>
                      <View style={[styles.sleepModeStatusBadge, codexStatusTone === 'connected' ? styles.sleepModeStatusActive : null]}>
                        <Text style={styles.sleepModeStatusText}>{codexStatusLabel}</Text>
                      </View>
                    </View>
                    <Text style={styles.voiceModeHelper}>
                      {codexConnectionDetail}
                    </Text>
                    {codexDeviceLogin ? (
                      <View style={styles.providerVaultStatus}>
                        <Text style={styles.providerVaultStatusText}>
                          Open {codexVerificationUri} and enter code {codexUserCode || 'shown by OpenAI'}.
                        </Text>
                      </View>
                    ) : null}
                    <View style={styles.sleepModeActionRow}>
                      <Pressable
                        style={[styles.sleepModeActionButton, styles.codexAuthButton, codexPrimaryDisabled ? styles.buttonDisabled : null]}
                        onPress={beginCodexDeviceLogin}
                        disabled={codexPrimaryDisabled}
                      >
                        <View
                          style={[
                            styles.codexAuthStatusDot,
                            codexStatusTone === 'connected' ? styles.codexAuthStatusDotConnected : null,
                            codexStatusTone === 'pending' ? styles.codexAuthStatusDotPending : null,
                            codexStatusTone === 'warning' ? styles.codexAuthStatusDotWarning : null,
                            codexStatusTone === 'error' ? styles.codexAuthStatusDotError : null,
                          ]}
                        />
                        <Text style={styles.sleepModeActionButtonText}>{codexPrimaryLabel}</Text>
                      </Pressable>
                      {codexConnected ? (
                        <Pressable
                          style={[styles.providerVaultDeleteButton, codexBusy ? styles.voiceModeButtonDisabled : null]}
                          onPress={disconnectCodexAuth}
                          disabled={codexBusy}
                        >
                          <Text style={styles.providerVaultDeleteText}>Delete local sign-in</Text>
                        </Pressable>
                      ) : null}
                    </View>
                    <Text style={[styles.validationText, codexStatusMessageStyle]}>
                      {codexStatusMessage}
                    </Text>
                  </View>

                  <View style={styles.settingCard}>
                    <Text style={styles.settingCardTitle}>Gmail login</Text>
                    <Text style={styles.settingCardDescription}>
                      Optional login details the agent can use when a task reaches a Gmail sign-in page.
                    </Text>
                    <View style={styles.vaultCredentialRow}>
                      <TextInput
                        value={gmailLoginEmail}
                        onChangeText={setGmailLoginEmail}
                        style={[styles.input, styles.vaultCredentialInput]}
                        placeholder="Gmail address"
                        placeholderTextColor="#7f93b5"
                        autoCapitalize="none"
                        autoCorrect={false}
                        keyboardType="email-address"
                      />
                      <TextInput
                        value={gmailLoginPassword}
                        onChangeText={setGmailLoginPassword}
                        style={[styles.input, styles.vaultCredentialInput]}
                        placeholder="Gmail password"
                        placeholderTextColor="#7f93b5"
                        autoCapitalize="none"
                        autoCorrect={false}
                        secureTextEntry
                      />
                      <Pressable
                        style={[
                          styles.voicePackActionButtonSecondary,
                          (!remoteAuthStatus?.signedIn || remoteSecretsBusy || (!gmailLoginEmail.trim() && !gmailLoginPassword.trim()))
                            ? styles.voiceModeButtonDisabled
                            : null,
                        ]}
                        onPress={() => {
                          onSaveLoginCredentials?.({
                            email: gmailLoginEmail.trim(),
                            password: gmailLoginPassword.trim(),
                          });
                          setGmailLoginPassword('');
                        }}
                        disabled={!remoteAuthStatus?.signedIn || remoteSecretsBusy || (!gmailLoginEmail.trim() && !gmailLoginPassword.trim())}
                      >
                        <Text style={styles.voicePackActionTextSecondary}>Save Gmail Login</Text>
                      </Pressable>
                    </View>
                    <Text style={styles.voiceModeHelper}>
                      Leave this blank if you prefer to sign in manually when Gmail is needed.
                    </Text>
                  </View>

                </View>

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Desktop updates</Text>
                  <Text style={styles.helperText}>
                    Check the public Git repository for new commits, pull fast-forward updates, rebuild, and restart EmploAI.
                  </Text>

                  <View style={styles.pathActions}>
                    <Pressable
                      style={[styles.pathButton, checkingUpdates ? styles.buttonDisabled : null]}
                      onPress={() => onCheckUpdates?.()}
                      disabled={checkingUpdates}
                    >
                      <Text style={styles.pathButtonText}>{checkingUpdates ? 'Checking...' : 'Check Updates'}</Text>
                    </Pressable>
                    {updateStatus?.updateAvailable && !updateStatus?.blocked ? (
                      <Pressable
                        style={[styles.pathButton, installingUpdate ? styles.buttonDisabled : null]}
                        onPress={() => onInstallUpdate?.()}
                        disabled={installingUpdate}
                      >
                        <Text style={styles.pathButtonText}>{installingUpdate ? 'Updating...' : 'Update And Restart'}</Text>
                      </Pressable>
                    ) : null}
                  </View>

                  <View style={styles.metaRow}>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Current version</Text>
                      <Text style={styles.metaValue}>{updateStatus?.currentVersion || setupState.releaseVersion}</Text>
                    </View>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Update status</Text>
                      <Text style={styles.metaValue}>{updateSummary}</Text>
                    </View>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Last checked</Text>
                      <Text style={styles.metaValue}>{updateStatus?.lastCheckedAt || 'Not checked yet'}</Text>
                    </View>
                  </View>
                </View>

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Memory and local intelligence</Text>
                  <Text style={styles.helperText}>
                    Edit the curated `MEMORY.md` and view local skills from one local intelligence surface.
                  </Text>

                  {memoryState ? (
                    <>
                      <Text style={styles.fieldLabel}>Memory file</Text>
                      <Text style={styles.pathValue}>{memoryState.memoryFilePath}</Text>

                      <View style={styles.metaRow}>
                        <View style={styles.metaCard}>
                          <Text style={styles.metaLabel}>File state</Text>
                          <Text style={styles.metaValue}>{memoryState.exists ? 'Saved on disk' : 'Template only'}</Text>
                        </View>
                        <View style={styles.metaCard}>
                          <Text style={styles.metaLabel}>Daily logs</Text>
                          <Text style={styles.metaValue}>{String(memoryState.dailyLogCount)}</Text>
                        </View>
                        <View style={styles.metaCard}>
                          <Text style={styles.metaLabel}>Newest log</Text>
                          <Text style={styles.metaValue}>{memoryState.newestLog || 'None yet'}</Text>
                        </View>
                      </View>
                    </>
                  ) : null}

                  <TextInput
                    value={memoryDraft}
                    onChangeText={(value) => {
                      setSaveFeedback(null);
                      setMemoryDraft(value);
                    }}
                    style={[styles.input, styles.memoryEditor]}
                    placeholder="Long-term memory will appear here"
                    placeholderTextColor="#7f93b5"
                    autoCapitalize="none"
                    autoCorrect={false}
                    multiline
                    textAlignVertical="top"
                  />

                  <View style={styles.pathActions}>
                    <Pressable
                      style={[styles.pathButton, memoryLoading ? styles.buttonDisabled : null]}
                      onPress={() => onReloadMemory?.()}
                      disabled={memoryLoading}
                    >
                      <Text style={styles.pathButtonText}>{memoryLoading ? 'Loading...' : 'Reload Memory'}</Text>
                    </Pressable>
                    <Pressable
                      style={[styles.pathButton, (!memoryDirty || memorySaving) ? styles.buttonDisabled : null]}
                      onPress={() => onSaveMemory?.(memoryDraft)}
                      disabled={!memoryDirty || memorySaving}
                    >
                      <Text style={styles.pathButtonText}>{memorySaving ? 'Saving...' : 'Save Memory'}</Text>
                    </Pressable>
                    {memoryState?.memoryFilePath ? (
                      <Pressable style={styles.pathButton} onPress={() => onOpenPath?.(memoryState.memoryFilePath)}>
                        <Text style={styles.pathButtonText}>Open Memory File</Text>
                      </Pressable>
                    ) : null}
                    {memoryState?.memoryDirPath ? (
                      <Pressable style={styles.pathButton} onPress={() => onOpenPath?.(memoryState.memoryDirPath)}>
                        <Text style={styles.pathButtonText}>Open Memory Folder</Text>
                      </Pressable>
                    ) : null}
                  </View>

                  <DesktopSetupLocalIntelligenceSection
                    apiBaseUrl={localIntelligenceApi?.apiBaseUrl}
                    token={localIntelligenceApi?.token}
                    sessionId={localIntelligenceApi?.sessionId}
                    onOpenPath={onOpenPath}
                    embedded
                  />
                </View>
              </>
            ) : null}

            {activeTab === 'onboarding' ? (
              <DesktopSetupOnboardingSection
                apiBaseUrl={localIntelligenceApi?.apiBaseUrl}
                token={localIntelligenceApi?.token}
                sessions={sessions}
                defaultWorkspace={values.DEFAULT_WORKSPACE}
                onProfileChange={applyOnboardingProfileSuggestion}
              />
            ) : null}

            {activeTab === 'chrome' ? (
              <>
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Browser helper</Text>
                  <Text style={styles.helperText}>Use these controls when the browser helper needs to be installed or inspected.</Text>

                  <Text style={styles.fieldLabel}>App workspace</Text>
                  <Text style={styles.pathValue}>{setupState.runtimeHome}</Text>

                  <Text style={styles.fieldLabel}>Advanced configuration file</Text>
                  <Text style={styles.pathValue}>{setupState.envFilePath}</Text>

                  <Text style={styles.fieldLabel}>Browser extension folder</Text>
                  <Text style={styles.pathValue}>{setupState.extensionPath}</Text>

                  <View style={styles.pathActions}>
                    <Pressable style={styles.pathButton} onPress={() => onOpenPath?.(setupState.envFilePath)}>
                      <Text style={styles.pathButtonText}>Open Env File</Text>
                    </Pressable>
                    <Pressable style={styles.pathButton} onPress={() => onOpenPath?.(setupState.extensionPath)}>
                      <Text style={styles.pathButtonText}>Open Extension Folder</Text>
                    </Pressable>
                  </View>
                </View>

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Browser extension and OCR</Text>
                  <Text style={styles.helperText}>
                    The extension folder is already placed on disk by the release backend. OCR remains bundled with the Windows release.
                  </Text>
                  <View style={styles.extensionGuideCard}>
                    <Text style={styles.extensionGuideTitle}>Load the Chrome extension in this order</Text>
                    <Text style={styles.extensionGuideStep}>1. Click `Open Chrome Extensions`.</Text>
                    <Text style={styles.extensionGuideStep}>2. In Chrome, enable `Developer mode` in the top-right.</Text>
                    <Text style={styles.extensionGuideStep}>3. Click `Load unpacked`.</Text>
                    <Text style={styles.extensionGuideStep}>4. Click `Open Extension Folder` here and select that folder in Chrome.</Text>
                    <Text style={styles.extensionGuideStep}>5. Return to EmploAI after Chrome shows the extension card.</Text>
                  </View>
                  <View style={styles.extensionActionRow}>
                    <Pressable style={styles.pathButton} onPress={() => onOpenChromeExtensions?.()}>
                      <Text style={styles.pathButtonText}>Open Chrome Extensions</Text>
                    </Pressable>
                    <Pressable style={styles.pathButton} onPress={() => onOpenPath?.(setupState.extensionPath)}>
                      <Text style={styles.pathButtonText}>Open Extension Folder</Text>
                    </Pressable>
                    <Pressable style={styles.pathButton} onPress={() => onOpenPath?.(setupState.extensionGuidePath)}>
                      <Text style={styles.pathButtonText}>Open Guide File</Text>
                    </Pressable>
                    <Pressable style={styles.pathButton} onPress={() => onCopyText?.(setupState.extensionPath)}>
                      <Text style={styles.pathButtonText}>Copy Extension Path</Text>
                    </Pressable>
                  </View>
                  <View style={styles.metaRow}>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Extension</Text>
                      <Text style={styles.metaValue}>Load unpacked from the folder above</Text>
                    </View>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>OCR</Text>
                      <Text style={styles.metaValue}>
                        {setupState.ocrAvailable ? `Available (${setupState.ocrSource || 'detected'})` : 'Unavailable'}
                      </Text>
                    </View>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Voice</Text>
                      <Text style={styles.metaValue}>{voiceMetaSummary}</Text>
                      {visibleVoiceIssue ? <Text style={styles.metaIssue}>{visibleVoiceIssue}</Text> : null}
                    </View>
                  </View>
                </View>
              </>
            ) : null}

            {activeTab === 'telegram' ? (
              <>
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Telegram (optional)</Text>
                  <Text style={styles.helperText}>Connect Telegram so messages can reach the same chats you use in the desktop app.</Text>

                  <View style={styles.fieldBlock}>
                    <Text style={styles.fieldLabel}>Telegram bot token</Text>
                    <TextInput
                      value={values.TELEGRAM_BOT_TOKEN}
                      onChangeText={(next) => updateValue('TELEGRAM_BOT_TOKEN', next)}
                      style={styles.input}
                      placeholder="123456789:AA..."
                      placeholderTextColor="#7f93b5"
                      autoCapitalize="none"
                      autoCorrect={false}
                      secureTextEntry
                    />
                    {fieldValidation.TELEGRAM_BOT_TOKEN?.message ? (
                      <Text style={[styles.validationText, validationTone(fieldValidation.TELEGRAM_BOT_TOKEN?.status)]}>
                        {fieldValidation.TELEGRAM_BOT_TOKEN?.message}
                      </Text>
                    ) : null}
                  </View>

                  <View style={styles.fieldBlock}>
                    <Text style={styles.fieldLabel}>Allowed Telegram users</Text>
                    <View style={styles.telegramUserList}>
                      {allowedTelegramUserIds.length ? (
                        allowedTelegramUserIds.map((userId) => (
                          <Pressable
                            key={userId}
                            style={styles.telegramUserChip}
                            onPress={() => removeTelegramUserId(userId)}
                          >
                            <Text style={styles.telegramUserChipText}>{userId} x</Text>
                          </Pressable>
                        ))
                      ) : (
                        <Text style={styles.voiceModeHelper}>No Telegram users added yet.</Text>
                      )}
                    </View>
                    <View style={styles.vaultCredentialRow}>
                      <TextInput
                        value={newTelegramUserId}
                        onChangeText={setNewTelegramUserId}
                        style={[styles.input, styles.telegramUserInput]}
                        placeholder="Numeric Telegram user ID"
                        placeholderTextColor="#7f93b5"
                        autoCapitalize="none"
                        autoCorrect={false}
                        keyboardType="number-pad"
                        onSubmitEditing={addTelegramUserId}
                      />
                      <Pressable
                        style={[
                          styles.voicePackActionButtonSecondary,
                          !newTelegramUserId.trim() ? styles.voiceModeButtonDisabled : null,
                        ]}
                        onPress={addTelegramUserId}
                        disabled={!newTelegramUserId.trim()}
                      >
                        <Text style={styles.voicePackActionTextSecondary}>Add User</Text>
                      </Pressable>
                    </View>
                    {fieldValidation.ALLOWED_USER_IDS?.message ? (
                      <Text style={[styles.validationText, validationTone(fieldValidation.ALLOWED_USER_IDS?.status)]}>
                        {fieldValidation.ALLOWED_USER_IDS?.message}
                      </Text>
                    ) : null}
                  </View>

                  <View style={styles.noteCard}>
                    <Text style={styles.noteLine}>1. Open Telegram and talk to `@BotFather`.</Text>
                    <Text style={styles.noteLine}>2. Create a bot and paste the token here.</Text>
                    <Text style={styles.noteLine}>3. Get your numeric user ID from `@userinfobot`.</Text>
                    <Text style={styles.noteLine}>4. Save setup. Desktop, Telegram, and mobile will then stay in sync.</Text>
                  </View>
                </View>

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Telegram bot routing</Text>
                  <Text style={styles.helperText}>
                    When a chat has no specific bot selected, EmploAI uses the first bot in this list.
                  </Text>

                  <View style={styles.voicePackList}>
                    {telegramBotConfigs.map((bot) => {
                      const assignedCount = sessions.filter((session) => (session.telegram_bot_config_id || fallbackBotId) === bot.id).length;
                      return (
                        <View key={bot.id} style={styles.voicePackCard}>
                          <View style={styles.voicePackHeader}>
                            <View style={styles.voicePackCopy}>
                              <Text style={styles.voicePackTitle}>{bot.label}</Text>
                              <Text style={styles.voicePackDescription}>{bot.bot_token}</Text>
                            </View>
                            <View style={[styles.voicePackStatusBadge, styles.voicePackStatusReady]}>
                              <Text style={styles.voicePackStatusText}>{bot.id === fallbackBotId ? 'first' : 'bot'}</Text>
                            </View>
                          </View>
                          <Text style={styles.voicePackMeta}>Assigned chats: {assignedCount}</Text>
                          <View style={styles.voicePackActionRow}>
                            <Pressable
                              style={styles.voicePackActionButtonSecondary}
                              onPress={() => onDeleteTelegramBotConfig?.(bot.id)}
                            >
                              <Text style={styles.voicePackActionTextSecondary}>Delete Bot</Text>
                            </Pressable>
                          </View>
                        </View>
                      );
                    })}

                    <View style={styles.voicePackCard}>
                      <Text style={styles.voicePackTitle}>Add Telegram bot</Text>
                      <Text style={styles.voicePackDescription}>
                        This adds an additional bot configuration. The allowed Telegram user ID stays universal.
                      </Text>
                      <View style={styles.fieldBlock}>
                        <Text style={styles.fieldLabel}>Label</Text>
                        <TextInput
                          value={newTelegramBotLabel}
                          onChangeText={setNewTelegramBotLabel}
                          style={styles.input}
                          placeholder="Build bot"
                          placeholderTextColor="#7f93b5"
                          autoCapitalize="none"
                          autoCorrect={false}
                        />
                      </View>
                      <View style={styles.fieldBlock}>
                        <Text style={styles.fieldLabel}>Bot token</Text>
                        <TextInput
                          value={newTelegramBotToken}
                          onChangeText={setNewTelegramBotToken}
                          style={styles.input}
                          placeholder="123456789:AA..."
                          placeholderTextColor="#7f93b5"
                          autoCapitalize="none"
                          autoCorrect={false}
                          secureTextEntry
                        />
                      </View>
                      <View style={styles.voicePackActionRow}>
                        <Pressable
                          style={[
                            styles.voicePackActionButton,
                            !newTelegramBotLabel.trim() || !newTelegramBotToken.trim() ? styles.voiceModeButtonDisabled : null,
                          ]}
                          onPress={() => {
                            onCreateTelegramBotConfig?.({
                              label: newTelegramBotLabel.trim(),
                              bot_token: newTelegramBotToken.trim(),
                            });
                            setNewTelegramBotLabel('');
                            setNewTelegramBotToken('');
                          }}
                          disabled={!newTelegramBotLabel.trim() || !newTelegramBotToken.trim()}
                        >
                          <Text style={styles.voicePackActionText}>Add Bot</Text>
                        </Pressable>
                      </View>
                    </View>
                  </View>
                </View>
              </>
            ) : null}

            {activeTab === 'remote' ? (
              standaloneMode ? (
              <>
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Standalone Desktop</Text>
                  <Text style={styles.helperText}>
                    EmploAI is running without account login, phone pairing, or the cloud backend. Local chat, Jarvis, automations, and fleet control use this computer&apos;s local app session.
                  </Text>
                  <View style={styles.metaRow}>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Mode</Text>
                      <Text style={styles.metaValue}>Local</Text>
                    </View>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Cloud account</Text>
                      <Text style={styles.metaValue}>Off</Text>
                    </View>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Mobile pairing</Text>
                      <Text style={styles.metaValue}>Off</Text>
                    </View>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Desktop</Text>
                      <Text style={styles.metaValue}>{remoteDesktopName || 'EmploAI Desktop'}</Text>
                    </View>
                  </View>
                  {remoteAuthStatus?.detail ? <Text style={styles.voiceModeHelper}>{remoteAuthStatus.detail}</Text> : null}
                </View>

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Other Computers</Text>
                  <Text style={styles.helperText}>
                    Use Fleet in the main app to create local workers or enrollment tokens for other machines. This path stays local to the desktop backend and does not require an EmploAI account.
                  </Text>
                  <View style={styles.noteCard}>
                    <Text style={styles.noteLine}>1. Open Fleet from the main app.</Text>
                    <Text style={styles.noteLine}>2. Create a local worker or enrollment token.</Text>
                    <Text style={styles.noteLine}>3. Connect the other machine to this desktop&apos;s local fleet controller.</Text>
                  </View>
                </View>
              </>
              ) : (
              <>
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Connected devices</Text>
                  <Text style={styles.helperText}>
                    Check this desktop&apos;s account status and connect your phone.
                  </Text>
                </View>

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Status</Text>
                  <Text style={styles.helperText}>
                    Shows whether this desktop is signed in and ready for paired devices.
                  </Text>
                  <View style={styles.metaRow}>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Account</Text>
                      <View style={styles.valueWithInfo}>
                        <Text style={styles.metaValue}>{remoteAuthStatus?.signedIn ? 'Signed in' : 'Signed out'}</Text>
                        {remoteAuthStatus?.signedIn && remoteAccountEmail !== 'not signed in' ? <InfoHint text={remoteAccountEmail} /> : null}
                      </View>
                      {remoteAuthStatus?.error ? (
                        <View style={styles.metaIssueRow}>
                          <Text style={styles.metaIssue}>Sign-in needs attention.</Text>
                          <InfoHint text={remoteAuthStatus.error} />
                        </View>
                      ) : null}
                    </View>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Connection</Text>
                      <Text style={styles.metaValue}>{remoteAuthStatus?.signedIn ? 'Ready' : 'Needs sign-in'}</Text>
                    </View>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Worker</Text>
                      <Text style={styles.metaValue}>{remoteWorkerStatus?.state || 'not_configured'}</Text>
                      {remoteWorkerStatus?.detail ? (
                        <View style={styles.metaIssueRow}>
                          <Text style={styles.metaIssue}>Worker needs attention.</Text>
                          <InfoHint text={remoteWorkerStatus.detail} />
                        </View>
                      ) : null}
                    </View>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Desktop</Text>
                      <Text style={styles.metaValue}>
                        {remoteDesktopName || 'not attached yet'}
                      </Text>
                      {remoteWorkerStatus?.desktopId || remoteWorkerStatus?.desktop_id ? (
                        <View style={styles.metaIssueRow}>
                          <Text style={styles.metaIssue}>Desktop ID</Text>
                          <InfoHint text={String(remoteWorkerStatus.desktopId || remoteWorkerStatus.desktop_id)} />
                        </View>
                      ) : null}
                    </View>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Configuration</Text>
                      <Text style={styles.metaValue}>
                        {remoteConfigured ? 'Configured' : remotePartial ? 'Incomplete' : 'Off'}
                      </Text>
                    </View>
                  </View>
                  <View style={styles.voicePackActionRow}>
                    <Pressable
                      style={[styles.voicePackActionButton, remoteBusy ? styles.voiceModeButtonDisabled : null]}
                      onPress={() => refreshRemoteConnection()}
                      disabled={remoteBusy}
                    >
                      <Text style={styles.voicePackActionText}>{remoteBusy ? 'Working...' : 'Refresh'}</Text>
                    </Pressable>
                    <Pressable
                      style={[
                        styles.voicePackActionButtonSecondary,
                        remoteBusy || !remoteAuthStatus?.signedIn ? styles.voiceModeButtonDisabled : null,
                      ]}
                      onPress={() => createRemotePairingToken()}
                      disabled={remoteBusy || !remoteAuthStatus?.signedIn}
                    >
                      <Text style={styles.voicePackActionTextSecondary}>Create Pairing QR</Text>
                    </Pressable>
                  </View>
                  {remoteMessage ? <Text style={styles.voiceModeHelper}>{shortStatusText(remoteMessage)}</Text> : null}
                  {remoteDesktops.length ? (
                    <View style={styles.noteCard}>
                      {remoteDesktops.map((desktop) => (
                        <View key={desktop.desktop_id || desktop.display_name || 'desktop'} style={styles.noteLineWithInfo}>
                          <Text style={styles.noteLine}>
                            {desktop.display_name || 'Desktop'}: {desktop.status || 'registered'}
                          </Text>
                          {desktop.desktop_id || desktop.detail ? (
                            <InfoHint text={[desktop.desktop_id ? `ID: ${desktop.desktop_id}` : '', desktop.detail || ''].filter(Boolean).join('\n')} />
                          ) : null}
                        </View>
                      ))}
                    </View>
                  ) : null}
                </View>

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Pair your phone</Text>
                  <Text style={styles.helperText}>
                    Generate a short-lived QR code here, then scan it from the phone&apos;s Connect screen.
                  </Text>
                  <View style={styles.noteCard}>
                    <Text style={styles.noteLine}>1. Sign in on this desktop.</Text>
                    <Text style={styles.noteLine}>2. Make sure the desktop runtime is running.</Text>
                    <Text style={styles.noteLine}>3. Click Create Pairing QR.</Text>
                    <Text style={styles.noteLine}>4. On the phone, sign in and scan this QR from Pairing.</Text>
                  </View>
                  {remotePairingUri ? (
                    <View style={styles.pairingQrCard}>
                      <PairingQrCode value={remotePairingUri} size={196} />
                      <View style={styles.pairingQrCopy}>
                        <Text style={styles.pairingQrTitle}>Ready to scan</Text>
                        <Text style={styles.voiceModeHelper}>
                          This QR contains only the one-time pairing token. It still requires the phone to be signed into the same account.
                        </Text>
                      </View>
                    </View>
                  ) : null}
                  <View style={styles.fieldBlock}>
                    <Text style={styles.fieldLabel}>One-time pairing code</Text>
                    <TextInput
                      value={remotePairingToken}
                      editable={false}
                      style={styles.input}
                      placeholder="No code generated yet"
                      placeholderTextColor="#7f93b5"
                    />
                    {remotePairingExpiresIn ? (
                      <Text style={styles.voiceModeHelper}>Expires in about {remotePairingExpiresIn} seconds.</Text>
                    ) : null}
                  </View>
                  <View style={styles.voicePackActionRow}>
                    <Pressable
                      style={[styles.voicePackActionButtonSecondary, !remotePairingToken ? styles.voiceModeButtonDisabled : null]}
                      onPress={() => onCopyText?.(remotePairingToken)}
                      disabled={!remotePairingToken}
                    >
                      <Text style={styles.voicePackActionTextSecondary}>Copy Code</Text>
                    </Pressable>
                  </View>
                </View>

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Danger zone</Text>
                  <Text style={styles.helperText}>
                    Delete saved preferences, connected-device state, and saved access for this account.
                  </Text>
                  <View style={styles.voicePackActionRow}>
                    <Pressable
                      style={[
                        styles.dangerOutlineButton,
                        (!remoteAuthStatus?.signedIn || remoteSecretsBusy || !onDeleteRemoteAccountData) ? styles.voiceModeButtonDisabled : null,
                      ]}
                      onPress={() => onDeleteRemoteAccountData?.()}
                      disabled={!remoteAuthStatus?.signedIn || remoteSecretsBusy || !onDeleteRemoteAccountData}
                    >
                      <Text style={styles.dangerOutlineText}>{remoteSecretsBusy ? 'Working...' : 'Delete Saved Account Data'}</Text>
                    </Pressable>
                  </View>
                </View>
              </>
              )
            ) : null}

            {activeTab === 'voice' ? (
              <DesktopSetupVoiceSection
                values={values}
                selectedVoiceEngine={selectedVoiceEngine}
                selectedVoicePack={selectedVoicePack}
                voiceModel={voiceModel}
                voiceDraftModel={voiceDraftModel}
                voiceSelectionSource={voiceSelectionSource}
                sttVoicePacks={sttVoicePacks}
                ttsVoicePacks={ttsVoicePacks}
                selectedTtsBackend={selectedTtsBackend}
                voicePackBusyId={voicePackBusyId}
                voicePackProgress={voicePackProgress}
                onSetVoiceDefaultEngine={setVoiceDefaultEngine}
                onToggleVoicePackRequest={toggleVoicePackRequest}
                onInstallVoicePack={onInstallVoicePack}
                onSelectTtsVoicePack={onSelectTtsVoicePack}
                onRemoveVoicePack={onRemoveVoicePack}
              />
            ) : null}

            {activeTab === 'recovery' ? (
              <DesktopSetupRecoverySection
                pendingConfirmations={pendingConfirmations}
                recoveryItems={recoveryItems}
                recoveryBusyId={recoveryBusyId}
                recoveryMessage={recoveryMessage}
                remoteAccountSignedIn={Boolean(remoteAuthStatus?.signedIn)}
                standaloneMode={standaloneMode}
                remoteSecretsBusy={remoteSecretsBusy}
                cloudChatBackupEnabled={cloudChatBackupEnabled}
                cloudBackupPreferenceBusy={cloudBackupPreferenceBusy}
                onToggleCloudChatBackup={onToggleCloudChatBackup}
                onRefreshRecovery={onRefreshRecovery}
                onApprovePendingConfirmation={onApprovePendingConfirmation}
                onDenyPendingConfirmation={onDenyPendingConfirmation}
                onRestoreRecoveryItem={onRestoreRecoveryItem}
                onPermanentDeleteRecoveryItem={onPermanentDeleteRecoveryItem}
                onRestoreManagedWorkspace={onRestoreManagedWorkspace}
                onDeleteRemoteAccountData={onDeleteRemoteAccountData}
              />
            ) : null}
          </ScrollView>
        </View>
      </View>

      {dismissPromptOpen ? (
        <View style={{ position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, zIndex: 90, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(2,7,15,0.72)', padding: 24 }}>
          <View accessibilityRole="alert" style={{ width: '100%', maxWidth: 480, borderRadius: 14, borderWidth: 1, borderColor: '#3b516a', backgroundColor: '#0d1724', padding: 20, gap: 14 }}>
            <Text style={{ color: '#f4f7fb', fontSize: 18, fontWeight: '800' }}>Save settings changes?</Text>
            <Text style={{ color: '#aeb9ca', fontSize: 13, lineHeight: 19 }}>
              Setup values, memory, or shared settings have unsaved changes. Save them, discard them, or return to Settings.
            </Text>
            {dismissSaveError ? <Text accessibilityLiveRegion="polite" style={{ color: '#ff9b9b', fontSize: 13 }}>{dismissSaveError}</Text> : null}
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, justifyContent: 'flex-end' }}>
              <Pressable accessibilityRole="button" disabled={saveBusy} onPress={() => setDismissPromptOpen(false)} style={[styles.secondaryButton, { minHeight: 44, justifyContent: 'center' }, saveBusy ? styles.primaryButtonDisabled : null]}>
                <Text style={styles.secondaryButtonText}>Cancel</Text>
              </Pressable>
              <Pressable accessibilityRole="button" disabled={saveBusy} onPress={discardDirtySections} style={[styles.secondaryButton, { minHeight: 44, justifyContent: 'center' }, saveBusy ? styles.primaryButtonDisabled : null]}>
                <Text style={styles.secondaryButtonText}>Discard</Text>
              </Pressable>
              <Pressable accessibilityRole="button" disabled={saveBusy} onPress={() => void saveDirtySections()} style={[styles.primaryButton, { minHeight: 44, justifyContent: 'center' }, saveBusy ? styles.primaryButtonDisabled : null]}>
                <Text style={styles.primaryButtonText}>{saveBusy ? 'Saving…' : 'Save'}</Text>
              </Pressable>
            </View>
          </View>
        </View>
      ) : null}

      <View style={styles.footer}>
        <View style={styles.footerLeading}>
          {onDismiss ? (
            <Pressable accessibilityRole="button" style={styles.secondaryButton} onPress={requestDismiss} disabled={saveBusy}>
              <Text style={styles.secondaryButtonText}>Close</Text>
            </Pressable>
          ) : null}
          <View accessibilityLiveRegion="polite" style={styles.footerStatus}>
            <View style={[
              styles.footerStatusDot,
              saveFeedback?.tone === 'success' ? styles.footerStatusDotSuccess : null,
              saveFeedback?.tone === 'error' ? styles.footerStatusDotError : null,
            ]} />
            <Text style={[
              styles.footerStatusText,
              saveFeedback?.tone === 'success' ? styles.footerStatusTextSuccess : null,
              saveFeedback?.tone === 'error' ? styles.footerStatusTextError : null,
            ]}>
              {saveFeedback?.message || (settingsDirty ? 'Unsaved changes' : 'No unsaved changes')}
            </Text>
          </View>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Save settings changes"
          style={[styles.primaryButton, (!settingsDirty || saveBusy) ? styles.primaryButtonDisabled : null]}
          onPress={() => void saveAllChanges()}
          disabled={!settingsDirty || saveBusy}
        >
          <Text style={styles.primaryButtonText}>{saveBusy ? 'Saving…' : setupState.required ? primaryActionLabel : 'Save Changes'}</Text>
        </Pressable>
      </View>
    </View>
  );
}
