import { useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  fetchRemoteDesktops,
  remoteLogin,
  remoteStartPairing,
  type RemoteDesktop,
  type RuntimeOrchestratorStatus,
  type SessionSummary,
  type TelegramBotConfig,
} from '@/lib/appApi';
import type {
  DesktopSetupFieldValidation,
  DesktopMemoryState,
  DesktopSetupState,
  DesktopSetupValues,
  DesktopUpdateStatus,
  DesktopVoicePackInstallProgress,
  DesktopVoicePackSummary,
} from '@/lib/desktopBridge';
import { validateDesktopSetupField } from '@/lib/desktopBridge';

const VOICE_ENGINE_NONE = 'none';
const VOICE_ENGINE_ENGLISH = 'english_local';
const VOICE_ENGINE_HEBREW = 'hebrew_local';

const INTERRUPT_POLICY_OPTIONS: Array<{
  key: DesktopSetupValues['INTERRUPT_POLICY_DEFAULT'];
  label: string;
  description: string;
}> = [
  {
    key: 'none',
    label: 'Queue',
    description: 'Hold messages locally while a run is active. They can auto-send later or be steered from the queue.',
  },
  {
    key: 'steer_now',
    label: 'Steer Now',
    description: 'Send messages during an active run as immediate steering instructions.',
  },
  {
    key: 'after_tool',
    label: 'After Tool',
    description: 'Send messages during an active run at the next safe tool boundary.',
  },
];

type Props = {
  setupState: DesktopSetupState;
  saving: boolean;
  voicePackBusyId?: string | null;
  voicePackProgress?: DesktopVoicePackInstallProgress | null;
  onSave: (values: Partial<DesktopSetupValues>) => void;
  onInstallVoicePack?: (packId: string) => void;
  onRemoveVoicePack?: (packId: string) => void;
  onDismiss?: () => void;
  onOpenPath?: (targetPath: string) => void;
  onOpenChromeExtensions?: () => void;
  onCopyText?: (textValue: string) => void;
  memoryState?: DesktopMemoryState | null;
  memoryLoading?: boolean;
  memorySaving?: boolean;
  onReloadMemory?: () => void;
  onSaveMemory?: (content: string) => void;
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
};

type SettingsTabKey = 'general' | 'chrome' | 'remote' | 'telegram' | 'voice';

const SETTINGS_TABS: Array<{ key: SettingsTabKey; label: string; description: string }> = [
  { key: 'general', label: 'General', description: 'Runtime defaults, providers, memory' },
  { key: 'chrome', label: 'Chrome Extension', description: 'Extension, OCR, runtime paths' },
  { key: 'remote', label: 'Remote', description: 'Cloud control plane and phone pairing' },
  { key: 'telegram', label: 'Telegram', description: 'Bot connection and routing' },
  { key: 'voice', label: 'Voice', description: 'Voice path, packs, and warmup state' },
];

const API_KEY_FIELDS: { key: keyof DesktopSetupValues; label: string }[] = [
  { key: 'OPENAI_API_KEY', label: 'OpenAI API key' },
  { key: 'ANTHROPIC_API_KEY', label: 'Anthropic API key' },
  { key: 'GOOGLE_API_KEY', label: 'Google Gemini API key' },
  { key: 'XAI_API_KEY', label: 'xAI Grok API key' },
  { key: 'DEEPSEEK_API_KEY', label: 'DeepSeek API key' },
  { key: 'OPENROUTER_API_KEY', label: 'OpenRouter API key' },
];

const LIVE_VALIDATION_FIELDS: Array<keyof DesktopSetupValues> = [
  'OPENAI_API_KEY',
  'ANTHROPIC_API_KEY',
  'GOOGLE_API_KEY',
  'XAI_API_KEY',
  'DEEPSEEK_API_KEY',
  'OPENROUTER_API_KEY',
  'TELEGRAM_BOT_TOKEN',
  'ALLOWED_USER_IDS',
  'EMPLOAI_REMOTE_CONTROL_BASE_URL',
  'EMPLOAI_REMOTE_CONTROL_EMAIL',
];

export function DesktopSetupPanel({
  setupState,
  saving,
  voicePackBusyId,
  voicePackProgress,
  onSave,
  onInstallVoicePack,
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
  updateStatus,
  checkingUpdates = false,
  installingUpdate = false,
  onCheckUpdates,
  onInstallUpdate,
  telegramBotConfigs = [],
  sessions = [],
  runtimeOrchestratorStatus,
  currentMaxTurns = null,
  onCreateTelegramBotConfig,
  onUpdateTelegramBotConfig,
  onDeleteTelegramBotConfig,
  onConfigureRuntimeOrchestrator,
  onUpdateGeneralAgentConfig,
}: Props) {
  const [values, setValues] = useState<DesktopSetupValues>(setupState.values);
  const [memoryDraft, setMemoryDraft] = useState(memoryState?.content || '');
  const [fieldValidation, setFieldValidation] = useState<Record<string, DesktopSetupFieldValidation>>({});
  const [newTelegramBotLabel, setNewTelegramBotLabel] = useState('');
  const [newTelegramBotToken, setNewTelegramBotToken] = useState('');
  const [maxConcurrentChatsDraft, setMaxConcurrentChatsDraft] = useState(String(runtimeOrchestratorStatus?.max_concurrent_chats || 4));
  const [maxTurnsDraft, setMaxTurnsDraft] = useState(String(currentMaxTurns || 80));
  const [activeTab, setActiveTab] = useState<SettingsTabKey>('general');
  const [remoteBusy, setRemoteBusy] = useState(false);
  const [remotePairingToken, setRemotePairingToken] = useState('');
  const [remotePairingExpiresIn, setRemotePairingExpiresIn] = useState<number | null>(null);
  const [remoteMessage, setRemoteMessage] = useState('');
  const [remoteDesktops, setRemoteDesktops] = useState<RemoteDesktop[]>([]);
  const validationTimersRef = useRef<Record<string, ReturnType<typeof setTimeout> | null>>({});
  const validationRunRef = useRef<Record<string, number>>({});

  useEffect(() => {
    setValues(setupState.values);
    setFieldValidation({});
  }, [setupState]);

  useEffect(() => {
    setMaxConcurrentChatsDraft(String(runtimeOrchestratorStatus?.max_concurrent_chats || 4));
  }, [runtimeOrchestratorStatus?.max_concurrent_chats]);

  useEffect(() => {
    setMaxTurnsDraft(String(currentMaxTurns || 80));
  }, [currentMaxTurns]);

  useEffect(() => {
    setMemoryDraft(memoryState?.content || '');
  }, [memoryState?.content, memoryState?.memoryFilePath]);

  useEffect(() => {
    setActiveTab('general');
  }, [setupState.required, setupState.releaseVersion]);

  useEffect(() => {
    setRemotePairingToken('');
    setRemotePairingExpiresIn(null);
    setRemoteMessage('');
    setRemoteDesktops([]);
  }, [setupState.releaseVersion, setupState.values.EMPLOAI_REMOTE_CONTROL_BASE_URL, setupState.values.EMPLOAI_REMOTE_CONTROL_EMAIL]);

  useEffect(() => () => {
    Object.values(validationTimersRef.current).forEach((timer) => {
      if (timer) {
        clearTimeout(timer);
      }
    });
  }, []);

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
              message: String(error),
            },
          }));
        }
      })();
    }, 450);
  };

  const updateValue = (key: keyof DesktopSetupValues, nextValue: string) => {
    setValues((current) => ({ ...current, [key]: nextValue }));
    if (LIVE_VALIDATION_FIELDS.includes(key)) {
      scheduleFieldValidation(key, nextValue);
    }
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
  const selectedVoiceEngine = values.VOICE_DEFAULT_ENGINE || voicePackState?.defaultEngine || VOICE_ENGINE_NONE;
  const selectedVoicePack = voicePacks.find((pack) => pack.id === selectedVoiceEngine) ?? null;
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
  const isVoicePackBusy = (packId: string) => voicePackBusyId === packId;
  const memoryDirty = memoryDraft !== (memoryState?.content || '');
  const updateSummary = updateStatus?.updateAvailable
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

  const defaultBotId = telegramBotConfigs.find((item) => item.is_default)?.id || telegramBotConfigs[0]?.id || null;
  const selectedSettingsTab = SETTINGS_TABS.find((item) => item.key === activeTab) || SETTINGS_TABS[0];
  const maxTurnsValue = Math.min(1000, Math.max(10, Number.parseInt(maxTurnsDraft || String(currentMaxTurns || 80), 10) || 80));
  const maxConcurrentValue = Math.min(12, Math.max(1, Number.parseInt(maxConcurrentChatsDraft || '4', 10) || 4));
  const sleepModeEnabled = runtimeOrchestratorStatus?.headless_mode_enabled ?? false;

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

  const adjustMaxTurns = (delta: number) => setMaxTurnsDraft(String(Math.min(1000, Math.max(10, maxTurnsValue + delta))));
  const adjustMaxConcurrentChats = (delta: number) => setMaxConcurrentChatsDraft(String(Math.min(12, Math.max(1, maxConcurrentValue + delta))));
  const remoteWorkerStatus = setupState.remoteControlStatus;
  const remoteConfigured = Boolean(setupState.remoteControlConfigured);
  const remotePartial = Boolean(setupState.remoteControlPartiallyConfigured);
  const remoteDesktopName = values.EMPLOAI_REMOTE_DESKTOP_NAME.trim() || 'EmploAI Desktop';
  const remoteDesktopKey = values.EMPLOAI_REMOTE_DESKTOP_KEY.trim() || 'desktop-default';

  const normalizedRemoteUrl = () => {
    const value = values.EMPLOAI_REMOTE_CONTROL_BASE_URL.trim().replace(/\/+$/, '');
    if (!value) {
      throw new Error('Remote control service URL is required.');
    }
    if (!(value.startsWith('https://') || value.startsWith('http://'))) {
      throw new Error('Remote control service URL must start with http:// or https://.');
    }
    return value;
  };

  const remoteCredentials = () => {
    const baseUrl = normalizedRemoteUrl();
    const email = values.EMPLOAI_REMOTE_CONTROL_EMAIL.trim();
    const password = values.EMPLOAI_REMOTE_CONTROL_PASSWORD.trim();
    if (!email || !password) {
      throw new Error('Remote control account email and password are required.');
    }
    return { baseUrl, email, password };
  };

  const refreshRemoteConnection = async () => {
    setRemoteBusy(true);
    setRemoteMessage('Checking cloud desktop connection...');
    try {
      const { baseUrl, email, password } = remoteCredentials();
      const login = await remoteLogin(baseUrl, {
        email,
        password,
        actor_kind: 'desktop',
        device_name: remoteDesktopName,
        device_platform: 'desktop-electron',
        device_key: remoteDesktopKey,
      });
      const desktops = await fetchRemoteDesktops(baseUrl, login.session_token).catch(() => []);
      setRemoteDesktops(Array.isArray(desktops) ? desktops : []);
      const connectedDesktop = (Array.isArray(desktops) ? desktops : []).find((item) => item.desktop_id === login.desktop?.desktop_id);
      setRemoteMessage(
        connectedDesktop
          ? `Cloud desktop ready as ${connectedDesktop.display_name || connectedDesktop.desktop_id}.`
          : `Desktop login succeeded as ${login.desktop?.display_name || login.desktop?.desktop_id || remoteDesktopName}.`
      );
    } catch (error) {
      setRemoteMessage(String(error));
    } finally {
      setRemoteBusy(false);
    }
  };

  const createRemotePairingToken = async () => {
    setRemoteBusy(true);
    setRemoteMessage('Creating one-time phone pairing token...');
    try {
      const { baseUrl, email, password } = remoteCredentials();
      const login = await remoteLogin(baseUrl, {
        email,
        password,
        actor_kind: 'desktop',
        device_name: remoteDesktopName,
        device_platform: 'desktop-electron',
        device_key: remoteDesktopKey,
      });
      const desktops = await fetchRemoteDesktops(baseUrl, login.session_token).catch(() => []);
      setRemoteDesktops(Array.isArray(desktops) ? desktops : []);
      const pairing = await remoteStartPairing(baseUrl, login.session_token, login.desktop?.desktop_id);
      setRemotePairingToken(pairing.pairing_token);
      setRemotePairingExpiresIn(pairing.expires_in_seconds);
      setRemoteMessage(`Pairing token ready for ${login.desktop?.display_name || remoteDesktopName}.`);
    } catch (error) {
      setRemoteMessage(String(error));
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
            <Pressable style={styles.backToAppButton} onPress={onDismiss} disabled={saving}>
              <Text style={styles.backToAppButtonText}>Back to app</Text>
            </Pressable>
          ) : (
            <View style={styles.backToAppPlaceholder}>
              <Text style={styles.backToAppPlaceholderText}>Setup required</Text>
            </View>
          )}
          <View style={styles.settingsNavList}>
            {SETTINGS_TABS.map((tab) => {
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

            {activeTab === 'general' ? (
              <>
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>General controls</Text>
                  <Text style={styles.helperText}>
                    These are the broad runtime controls that shape how the app behaves before you get into per-chat settings.
                  </Text>

                  <View style={styles.settingRow}>
                    <View style={styles.settingRowCopy}>
                      <Text style={styles.settingRowTitle}>Turn limit</Text>
                      <Text style={styles.settingRowDescription}>Maximum turns the runtime can spend on a run before handing control back.</Text>
                    </View>
                    <View style={styles.settingRowControls}>
                      <View style={styles.stepperControl}>
                        <Pressable style={styles.stepperButton} onPress={() => adjustMaxTurns(-10)}>
                          <Text style={styles.stepperButtonText}>-</Text>
                        </Pressable>
                        <TextInput
                          value={maxTurnsDraft}
                          onChangeText={setMaxTurnsDraft}
                          style={[styles.input, styles.numberInput]}
                          placeholder="80"
                          placeholderTextColor="#7f93b5"
                          autoCapitalize="none"
                          autoCorrect={false}
                        />
                        <Pressable style={styles.stepperButton} onPress={() => adjustMaxTurns(10)}>
                          <Text style={styles.stepperButtonText}>+</Text>
                        </Pressable>
                      </View>
                      <Pressable style={styles.compactActionButton} onPress={() => onUpdateGeneralAgentConfig?.({ max_turns: maxTurnsValue })}>
                        <Text style={styles.compactActionButtonText}>Apply</Text>
                      </Pressable>
                    </View>
                  </View>

                  <View style={styles.settingRow}>
                    <View style={styles.settingRowCopy}>
                      <Text style={styles.settingRowTitle}>Running chats</Text>
                      <Text style={styles.settingRowDescription}>Maximum chats allowed to run at the same time under the shared orchestrator.</Text>
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
                        style={styles.compactActionButton}
                        onPress={() => onConfigureRuntimeOrchestrator?.({ default_max_concurrent_chats: maxConcurrentValue })}
                      >
                        <Text style={styles.compactActionButtonText}>Apply</Text>
                      </Pressable>
                    </View>
                  </View>

                  <View style={styles.settingRow}>
                    <View style={styles.settingRowCopy}>
                      <Text style={styles.settingRowTitle}>Sleep mode</Text>
                      <Text style={styles.settingRowDescription}>
                        Headless rules apply when this is enabled. Sleep-chat assignment is managed per bot from chat settings.
                      </Text>
                    </View>
                    <Pressable
                      style={[styles.toggleSwitch, sleepModeEnabled ? styles.toggleSwitchActive : null]}
                      onPress={() => onConfigureRuntimeOrchestrator?.({ enabled: !sleepModeEnabled })}
                    >
                      <View style={[styles.toggleSwitchKnob, sleepModeEnabled ? styles.toggleSwitchKnobActive : null]} />
                    </Pressable>
                  </View>

                  <View style={styles.fieldBlock}>
                    <Text style={styles.fieldLabel}>Active-run message behavior</Text>
                    <Text style={styles.helperText}>
                      Choose what happens when you send a text message while the agent is already working in this chat.
                    </Text>
                    <View style={styles.voiceModeRow}>
                      {INTERRUPT_POLICY_OPTIONS.map((option) => {
                        const selected = (values.INTERRUPT_POLICY_DEFAULT || 'none') === option.key;
                        return (
                          <Pressable
                            key={option.key}
                            style={[styles.voiceModeButton, selected ? styles.voiceModeButtonActive : null]}
                            onPress={() => updateValue('INTERRUPT_POLICY_DEFAULT', option.key)}
                          >
                            <Text style={[styles.voiceModeButtonText, selected ? styles.voiceModeButtonTextActive : null]}>
                              {option.label}
                            </Text>
                          </Pressable>
                        );
                      })}
                    </View>
                    <Text style={styles.voiceModeHelper}>
                      {INTERRUPT_POLICY_OPTIONS.find((option) => option.key === (values.INTERRUPT_POLICY_DEFAULT || 'none'))?.description}
                    </Text>
                  </View>
                </View>

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Workspace</Text>
                  <Text style={styles.helperText}>This is the default root for file operations on this computer.</Text>
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

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Model providers</Text>
                  <Text style={styles.helperText}>At least one provider key is required. The agent will only offer models for the providers you configure.</Text>
                  <View style={styles.providerRow}>
                    {(setupState.configuredProviders.length ? setupState.configuredProviders : ['none yet']).map((provider) => (
                      <View key={provider} style={styles.providerChip}>
                        <Text style={styles.providerChipText}>{provider}</Text>
                      </View>
                    ))}
                  </View>

                  {API_KEY_FIELDS.map((field) => (
                    <View key={field.key} style={styles.fieldBlock}>
                      <Text style={styles.fieldLabel}>{field.label}</Text>
                      <TextInput
                        value={values[field.key]}
                        onChangeText={(next) => updateValue(field.key, next)}
                        style={styles.input}
                        placeholder="Enter key or clear it"
                        placeholderTextColor="#7f93b5"
                        autoCapitalize="none"
                        autoCorrect={false}
                        secureTextEntry
                      />
                      {fieldValidation[field.key]?.message ? (
                        <Text style={[styles.validationText, validationTone(fieldValidation[field.key]?.status)]}>
                          {fieldValidation[field.key]?.message}
                        </Text>
                      ) : null}
                    </View>
                  ))}

                  <View style={styles.fieldBlock}>
                    <Text style={styles.fieldLabel}>Planner model override</Text>
                    <TextInput
                      value={values.PLANNER_MODEL}
                      onChangeText={(next) => updateValue('PLANNER_MODEL', next)}
                      style={styles.input}
                      placeholder="Leave blank for automatic cheapest supported planner"
                      placeholderTextColor="#7f93b5"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                    <Text style={styles.helperText}>
                      This sets the desktop runtime default for new sessions. Session-level `/planner` changes can still override it later.
                    </Text>
                  </View>
                </View>

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Desktop updates</Text>
                  <Text style={styles.helperText}>
                    Check for release updates here. If an installer is available, EmploAI can launch it directly from this panel.
                  </Text>

                  <View style={styles.pathActions}>
                    <Pressable
                      style={[styles.pathButton, checkingUpdates ? styles.buttonDisabled : null]}
                      onPress={() => onCheckUpdates?.()}
                      disabled={checkingUpdates}
                    >
                      <Text style={styles.pathButtonText}>{checkingUpdates ? 'Checking...' : 'Check Updates'}</Text>
                    </Pressable>
                    {updateStatus?.updateAvailable ? (
                      <Pressable
                        style={[styles.pathButton, installingUpdate ? styles.buttonDisabled : null]}
                        onPress={() => onInstallUpdate?.()}
                        disabled={installingUpdate}
                      >
                        <Text style={styles.pathButtonText}>{installingUpdate ? 'Launching...' : 'Update And Restart'}</Text>
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
                  <Text style={styles.sectionTitle}>Long-term memory</Text>
                  <Text style={styles.helperText}>
                    This is the curated `MEMORY.md` file injected into the agent prompt. Edit it here to inspect, add, delete, or correct durable memory directly.
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
                    onChangeText={setMemoryDraft}
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
                </View>
              </>
            ) : null}

            {activeTab === 'chrome' ? (
              <>
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Runtime paths</Text>
                  <Text style={styles.helperText}>The installer keeps the desktop app in Program Files and the editable runtime state in your local EmploAI home.</Text>

                  <Text style={styles.fieldLabel}>Runtime home</Text>
                  <Text style={styles.pathValue}>{setupState.runtimeHome}</Text>

                  <Text style={styles.fieldLabel}>Editable env file</Text>
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
                  <Text style={styles.helperText}>Configure this only if you want Telegram to attach to the same shared sessions as the desktop app.</Text>

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
                    <Text style={styles.fieldLabel}>Allowed Telegram user ID(s)</Text>
                    <TextInput
                      value={values.ALLOWED_USER_IDS}
                      onChangeText={(next) => updateValue('ALLOWED_USER_IDS', next)}
                      style={styles.input}
                      placeholder="123456789 or comma-separated IDs"
                      placeholderTextColor="#7f93b5"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
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
                    <Text style={styles.noteLine}>4. Save setup. Desktop, Telegram, and mobile will then share the same session rail.</Text>
                  </View>
                </View>

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Telegram bot routing</Text>
                  <Text style={styles.helperText}>
                    The original setup token stays the default bot. Add more bots here when you want different chats to mirror to different Telegram bots.
                  </Text>

                  <View style={styles.voicePackList}>
                    {telegramBotConfigs.map((bot) => {
                      const assignedCount = sessions.filter((session) => (session.telegram_bot_config_id || defaultBotId) === bot.id).length;
                      return (
                        <View key={bot.id} style={styles.voicePackCard}>
                          <View style={styles.voicePackHeader}>
                            <View style={styles.voicePackCopy}>
                              <Text style={styles.voicePackTitle}>{bot.label}</Text>
                              <Text style={styles.voicePackDescription}>{bot.bot_token}</Text>
                            </View>
                            <View style={[styles.voicePackStatusBadge, styles.voicePackStatusReady]}>
                              <Text style={styles.voicePackStatusText}>{bot.is_default ? 'default' : 'secondary'}</Text>
                            </View>
                          </View>
                          <Text style={styles.voicePackMeta}>Assigned chats: {assignedCount}</Text>
                          <View style={styles.voicePackActionRow}>
                            {!bot.is_default ? (
                              <Pressable
                                style={styles.voicePackActionButton}
                                onPress={() => onUpdateTelegramBotConfig?.(bot.id, { is_default: true })}
                              >
                                <Text style={styles.voicePackActionText}>Make Default</Text>
                              </Pressable>
                            ) : null}
                            {!bot.is_default ? (
                              <Pressable
                                style={styles.voicePackActionButtonSecondary}
                                onPress={() => onDeleteTelegramBotConfig?.(bot.id)}
                              >
                                <Text style={styles.voicePackActionTextSecondary}>Delete Bot</Text>
                              </Pressable>
                            ) : null}
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
              <>
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Remote control plane</Text>
                  <Text style={styles.helperText}>
                    Save the VPS service URL and account here. When this desktop runtime is healthy, the managed remote-control worker
                    will keep this computer attached to the EmploAI cloud so your phone can reach it from any network.
                  </Text>

                  <View style={styles.fieldBlock}>
                    <Text style={styles.fieldLabel}>Service URL</Text>
                    <TextInput
                      value={values.EMPLOAI_REMOTE_CONTROL_BASE_URL}
                      onChangeText={(next) => updateValue('EMPLOAI_REMOTE_CONTROL_BASE_URL', next)}
                      style={styles.input}
                      placeholder="https://your-emploai-domain"
                      placeholderTextColor="#7f93b5"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                    {fieldValidation.EMPLOAI_REMOTE_CONTROL_BASE_URL?.message ? (
                      <Text style={[styles.validationText, validationTone(fieldValidation.EMPLOAI_REMOTE_CONTROL_BASE_URL?.status)]}>
                        {fieldValidation.EMPLOAI_REMOTE_CONTROL_BASE_URL?.message}
                      </Text>
                    ) : null}
                  </View>

                  <View style={styles.fieldBlock}>
                    <Text style={styles.fieldLabel}>Account email</Text>
                    <TextInput
                      value={values.EMPLOAI_REMOTE_CONTROL_EMAIL}
                      onChangeText={(next) => updateValue('EMPLOAI_REMOTE_CONTROL_EMAIL', next)}
                      style={styles.input}
                      placeholder="you@example.com"
                      placeholderTextColor="#7f93b5"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                    {fieldValidation.EMPLOAI_REMOTE_CONTROL_EMAIL?.message ? (
                      <Text style={[styles.validationText, validationTone(fieldValidation.EMPLOAI_REMOTE_CONTROL_EMAIL?.status)]}>
                        {fieldValidation.EMPLOAI_REMOTE_CONTROL_EMAIL?.message}
                      </Text>
                    ) : null}
                  </View>

                  <View style={styles.fieldBlock}>
                    <Text style={styles.fieldLabel}>Account password</Text>
                    <TextInput
                      value={values.EMPLOAI_REMOTE_CONTROL_PASSWORD}
                      onChangeText={(next) => updateValue('EMPLOAI_REMOTE_CONTROL_PASSWORD', next)}
                      style={styles.input}
                      placeholder="Cloud account password"
                      placeholderTextColor="#7f93b5"
                      autoCapitalize="none"
                      autoCorrect={false}
                      secureTextEntry
                    />
                  </View>

                  <View style={styles.fieldBlock}>
                    <Text style={styles.fieldLabel}>Desktop display name</Text>
                    <TextInput
                      value={values.EMPLOAI_REMOTE_DESKTOP_NAME}
                      onChangeText={(next) => updateValue('EMPLOAI_REMOTE_DESKTOP_NAME', next)}
                      style={styles.input}
                      placeholder="EmploAI Desktop"
                      placeholderTextColor="#7f93b5"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                  </View>

                  <View style={styles.fieldBlock}>
                    <Text style={styles.fieldLabel}>Stable desktop key</Text>
                    <TextInput
                      value={values.EMPLOAI_REMOTE_DESKTOP_KEY}
                      onChangeText={(next) => updateValue('EMPLOAI_REMOTE_DESKTOP_KEY', next)}
                      style={styles.input}
                      placeholder="desktop-default"
                      placeholderTextColor="#7f93b5"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                  </View>
                </View>

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Status</Text>
                  <Text style={styles.helperText}>
                    Save these settings first, then the desktop app will keep a managed cloud bridge alive whenever the local runtime is running.
                  </Text>
                  <View style={styles.metaRow}>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Configuration</Text>
                      <Text style={styles.metaValue}>
                        {remoteConfigured ? 'Configured' : remotePartial ? 'Incomplete' : 'Off'}
                      </Text>
                    </View>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Worker</Text>
                      <Text style={styles.metaValue}>{remoteWorkerStatus?.state || 'not_configured'}</Text>
                      {remoteWorkerStatus?.detail ? <Text style={styles.metaIssue}>{remoteWorkerStatus.detail}</Text> : null}
                    </View>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Desktop Id</Text>
                      <Text style={styles.metaValue}>
                        {remoteWorkerStatus?.desktopName || remoteWorkerStatus?.desktop_name || remoteWorkerStatus?.desktopId || remoteWorkerStatus?.desktop_id || 'not attached yet'}
                      </Text>
                    </View>
                  </View>
                  <View style={styles.voicePackActionRow}>
                    <Pressable
                      style={[styles.voicePackActionButton, remoteBusy ? styles.voiceModeButtonDisabled : null]}
                      onPress={() => refreshRemoteConnection()}
                      disabled={remoteBusy}
                    >
                      <Text style={styles.voicePackActionText}>{remoteBusy ? 'Working...' : 'Check Cloud Login'}</Text>
                    </Pressable>
                    <Pressable
                      style={[styles.voicePackActionButtonSecondary, remoteBusy ? styles.voiceModeButtonDisabled : null]}
                      onPress={() => createRemotePairingToken()}
                      disabled={remoteBusy}
                    >
                      <Text style={styles.voicePackActionTextSecondary}>Create Pairing Token</Text>
                    </Pressable>
                  </View>
                  {remoteMessage ? <Text style={styles.voiceModeHelper}>{remoteMessage}</Text> : null}
                  {remoteDesktops.length ? (
                    <View style={styles.noteCard}>
                      {remoteDesktops.map((desktop) => (
                        <Text key={desktop.desktop_id} style={styles.noteLine}>
                          {desktop.display_name || desktop.desktop_id}: {desktop.status}{desktop.detail ? ` · ${desktop.detail}` : ''}
                        </Text>
                      ))}
                    </View>
                  ) : null}
                </View>

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Pair your phone</Text>
                  <Text style={styles.helperText}>
                    Generate a short-lived token here, then use the phone&apos;s Connect screen to sign into the same account and paste that token.
                  </Text>
                  <View style={styles.noteCard}>
                    <Text style={styles.noteLine}>1. Save the remote settings in this tab.</Text>
                    <Text style={styles.noteLine}>2. Start the local desktop runtime if it is offline.</Text>
                    <Text style={styles.noteLine}>3. Click `Create Pairing Token`.</Text>
                    <Text style={styles.noteLine}>4. On the phone, sign in and paste that token into `Connect Phone`.</Text>
                  </View>
                  <View style={styles.fieldBlock}>
                    <Text style={styles.fieldLabel}>One-time pairing token</Text>
                    <TextInput
                      value={remotePairingToken}
                      editable={false}
                      style={styles.input}
                      placeholder="No token generated yet"
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
                      <Text style={styles.voicePackActionTextSecondary}>Copy Token</Text>
                    </Pressable>
                  </View>
                </View>
              </>
            ) : null}

            {activeTab === 'voice' ? (
              <>
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Voice</Text>
                  <Text style={styles.helperText}>
                    Choose the desktop voice path, install packs, and review what the runtime will use for drafts vs final transcription.
                  </Text>
                  <View style={styles.metaRow}>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Selected path</Text>
                      <Text style={styles.metaValue}>
                        {selectedVoiceEngine === VOICE_ENGINE_NONE ? 'Off' : selectedVoicePack?.title || selectedVoiceEngine}
                      </Text>
                      {selectedVoicePack ? <Text style={styles.metaIssue}>{selectedVoicePack.description}</Text> : null}
                    </View>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Input runtime</Text>
                      <Text style={styles.metaValue}>{voiceModel}</Text>
                      {voiceDraftModel ? <Text style={styles.metaIssue}>Live drafts: {voiceDraftModel}</Text> : null}
                    </View>
                    <View style={styles.metaCard}>
                      <Text style={styles.metaLabel}>Selection source</Text>
                      <Text style={styles.metaValue}>
                        {voiceSelectionSource === 'settings'
                          ? 'Manual settings'
                          : voiceSelectionSource === 'installer'
                            ? 'Installer selection'
                            : voiceSelectionSource}
                      </Text>
                    </View>
                  </View>

                  <View style={styles.voiceModeRow}>
                    <Pressable
                      style={[styles.voiceModeButton, selectedVoiceEngine === VOICE_ENGINE_NONE ? styles.voiceModeButtonActive : null]}
                      onPress={() => setVoiceDefaultEngine(VOICE_ENGINE_NONE)}
                    >
                      <Text style={[styles.voiceModeButtonText, selectedVoiceEngine === VOICE_ENGINE_NONE ? styles.voiceModeButtonTextActive : null]}>
                        No voice
                      </Text>
                    </Pressable>
                    <Pressable
                      style={[
                        styles.voiceModeButton,
                        selectedVoiceEngine === VOICE_ENGINE_ENGLISH ? styles.voiceModeButtonActive : null,
                        values.VOICE_ENGLISH_REQUESTED === '0' ? styles.voiceModeButtonDisabled : null,
                      ]}
                      onPress={() => setVoiceDefaultEngine(VOICE_ENGINE_ENGLISH)}
                      disabled={values.VOICE_ENGLISH_REQUESTED === '0'}
                    >
                      <Text style={[styles.voiceModeButtonText, selectedVoiceEngine === VOICE_ENGINE_ENGLISH ? styles.voiceModeButtonTextActive : null]}>
                        English
                      </Text>
                    </Pressable>
                    <Pressable
                      style={[
                        styles.voiceModeButton,
                        selectedVoiceEngine === VOICE_ENGINE_HEBREW ? styles.voiceModeButtonActive : null,
                        values.VOICE_HEBREW_REQUESTED !== '1' ? styles.voiceModeButtonDisabled : null,
                      ]}
                      onPress={() => setVoiceDefaultEngine(VOICE_ENGINE_HEBREW)}
                      disabled={values.VOICE_HEBREW_REQUESTED !== '1'}
                    >
                      <Text style={[styles.voiceModeButtonText, selectedVoiceEngine === VOICE_ENGINE_HEBREW ? styles.voiceModeButtonTextActive : null]}>
                        Hebrew
                      </Text>
                    </Pressable>
                  </View>
                </View>

                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Voice packs</Text>
                  <View style={styles.voicePackList}>
                    {voicePacks.map((pack) => {
                      const activeProgress = isVoicePackBusy(pack.id) ? voicePackProgress : null;
                      const progressPercent = activeProgress?.percent ?? 0;
                      return (
                        <View key={pack.id} style={styles.voicePackCard}>
                          <View style={styles.voicePackHeader}>
                            <View style={styles.voicePackCopy}>
                              <Text style={styles.voicePackTitle}>{pack.title}</Text>
                              <Text style={styles.voicePackDescription}>{pack.description}</Text>
                            </View>
                            <View
                              style={[
                                styles.voicePackStatusBadge,
                                pack.available ? styles.voicePackStatusReady : styles.voicePackStatusPlaceholder,
                              ]}
                            >
                              <Text style={styles.voicePackStatusText}>
                                {pack.available ? 'Ready' : pack.installed ? 'Installed' : 'Optional'}
                              </Text>
                            </View>
                          </View>
                          <Text style={styles.voicePackMeta}>
                            Installed: {pack.installed ? 'yes' : 'no'}
                            {pack.source ? ` · Source: ${pack.source}` : ''}
                            {pack.supportsAlwaysOn ? ' · Always-on target included' : ''}
                          </Text>
                          {pack.issues?.length ? <Text style={styles.metaIssue}>{pack.issues[0]}</Text> : null}
                          {activeProgress ? (
                            <View style={styles.voicePackProgressCard}>
                              <Text style={styles.voicePackProgressTitle}>{activeProgress.message}</Text>
                              <View style={styles.voicePackProgressTrack}>
                                <View style={[styles.voicePackProgressFill, { width: `${progressPercent}%` }]} />
                              </View>
                              <Text style={styles.voicePackProgressMeta}>
                                {activeProgress.phase.replace(/_/g, ' ')}
                                {typeof activeProgress.percent === 'number' ? ` · ${Math.round(activeProgress.percent)}%` : ''}
                              </Text>
                            </View>
                          ) : null}
                          <View style={styles.voicePackActionRow}>
                            <Pressable
                              style={[styles.voicePackActionButton, isVoicePackBusy(pack.id) ? styles.voiceModeButtonDisabled : null]}
                              onPress={() => toggleVoicePackRequest(pack)}
                              disabled={isVoicePackBusy(pack.id)}
                            >
                              <Text style={styles.voicePackActionText}>
                                {pack.id === VOICE_ENGINE_ENGLISH
                                  ? values.VOICE_ENGLISH_REQUESTED === '0'
                                    ? 'Enable English pack'
                                    : 'Disable English pack'
                                  : values.VOICE_HEBREW_REQUESTED === '1'
                                    ? 'Disable Hebrew pack'
                                    : 'Enable Hebrew pack'}
                              </Text>
                            </Pressable>
                            {pack.installed ? (
                              <Pressable
                                style={[
                                  styles.voicePackActionButtonSecondary,
                                  !pack.removable || isVoicePackBusy(pack.id) ? styles.voiceModeButtonDisabled : null,
                                ]}
                                onPress={() => onRemoveVoicePack?.(pack.id)}
                                disabled={!pack.removable || isVoicePackBusy(pack.id)}
                              >
                                <Text style={styles.voicePackActionTextSecondary}>
                                  {isVoicePackBusy(pack.id) ? 'Removing...' : 'Delete Pack'}
                                </Text>
                              </Pressable>
                            ) : (
                              <Pressable
                                style={[
                                  styles.voicePackActionButtonSecondary,
                                  isVoicePackBusy(pack.id) ? styles.voiceModeButtonDisabled : null,
                                ]}
                                onPress={() => onInstallVoicePack?.(pack.id)}
                                disabled={isVoicePackBusy(pack.id)}
                              >
                                <Text style={styles.voicePackActionTextSecondary}>
                                  {isVoicePackBusy(pack.id) ? 'Installing...' : 'Install and Use'}
                                </Text>
                              </Pressable>
                            )}
                            {pack.id === VOICE_ENGINE_ENGLISH ? (
                              <Pressable
                                style={[
                                  styles.voicePackActionButtonSecondary,
                                  values.VOICE_ENGLISH_REQUESTED === '0' || !pack.available || isVoicePackBusy(pack.id) ? styles.voiceModeButtonDisabled : null,
                                ]}
                                onPress={() => setVoiceDefaultEngine(VOICE_ENGINE_ENGLISH)}
                                disabled={values.VOICE_ENGLISH_REQUESTED === '0' || !pack.available || isVoicePackBusy(pack.id)}
                              >
                                <Text style={styles.voicePackActionTextSecondary}>Use English</Text>
                              </Pressable>
                            ) : (
                              <Pressable
                                style={[
                                  styles.voicePackActionButtonSecondary,
                                  values.VOICE_HEBREW_REQUESTED !== '1' || !pack.available || isVoicePackBusy(pack.id) ? styles.voiceModeButtonDisabled : null,
                                ]}
                                onPress={() => setVoiceDefaultEngine(VOICE_ENGINE_HEBREW)}
                                disabled={values.VOICE_HEBREW_REQUESTED !== '1' || !pack.available || isVoicePackBusy(pack.id)}
                              >
                                <Text style={styles.voicePackActionTextSecondary}>Use Hebrew</Text>
                              </Pressable>
                            )}
                          </View>
                        </View>
                      );
                    })}
                  </View>
                </View>
              </>
            ) : null}
          </ScrollView>
        </View>
      </View>

      <View style={styles.footer}>
        {onDismiss ? (
          <Pressable style={styles.secondaryButton} onPress={onDismiss} disabled={saving}>
            <Text style={styles.secondaryButtonText}>Close</Text>
          </Pressable>
        ) : <View />}
        <Pressable
          style={[styles.primaryButton, saving ? styles.primaryButtonDisabled : null]}
          onPress={() => onSave(values)}
          disabled={saving}
        >
          <Text style={styles.primaryButtonText}>{saving ? 'Saving...' : primaryActionLabel}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  shell: {
    borderRadius: 26,
    backgroundColor: '#111111',
    borderWidth: 1,
    borderColor: '#252525',
    padding: 20,
    gap: 18,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 18,
  },
  headerCopy: {
    flex: 1,
    gap: 6,
  },
  eyebrow: {
    color: '#848484',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.9,
  },
  title: {
    color: '#f3f3f3',
    fontSize: 24,
    fontWeight: '800',
  },
  subtitle: {
    color: '#989898',
    fontSize: 13,
    lineHeight: 20,
    maxWidth: 760,
  },
  versionBadge: {
    width: 188,
    backgroundColor: '#181818',
    borderWidth: 1,
    borderColor: '#262626',
    borderRadius: 18,
    padding: 14,
    gap: 4,
  },
  versionLabel: {
    color: '#7f7f7f',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  versionValue: {
    color: '#f3f3f3',
    fontSize: 18,
    fontWeight: '800',
  },
  settingsFrame: {
    flexDirection: 'row',
    gap: 18,
    minHeight: 640,
  },
  settingsSidebar: {
    width: 260,
    backgroundColor: '#161616',
    borderWidth: 1,
    borderColor: '#252525',
    borderRadius: 20,
    padding: 14,
    gap: 14,
  },
  backToAppButton: {
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 14,
    backgroundColor: '#1b1b1b',
  },
  backToAppButtonText: {
    color: '#d8d8d8',
    fontSize: 13,
    fontWeight: '700',
  },
  backToAppPlaceholder: {
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  backToAppPlaceholderText: {
    color: '#8e8e8e',
    fontSize: 13,
    fontWeight: '700',
  },
  settingsNavList: {
    gap: 8,
  },
  settingsNavItem: {
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 12,
    gap: 3,
  },
  settingsNavItemActive: {
    backgroundColor: '#242424',
  },
  settingsNavItemTitle: {
    color: '#e5e5e5',
    fontSize: 14,
    fontWeight: '700',
  },
  settingsNavItemTitleActive: {
    color: '#ffffff',
  },
  settingsNavItemDescription: {
    color: '#7b7b7b',
    fontSize: 11,
    lineHeight: 15,
  },
  settingsContentPane: {
    flex: 1,
    backgroundColor: '#151515',
    borderWidth: 1,
    borderColor: '#252525',
    borderRadius: 20,
    overflow: 'hidden',
  },
  settingsContentHeader: {
    paddingHorizontal: 24,
    paddingTop: 22,
    paddingBottom: 18,
    borderBottomWidth: 1,
    borderBottomColor: '#242424',
  },
  settingsContentHeaderCopy: {
    gap: 4,
  },
  settingsContentTitle: {
    color: '#f5f5f5',
    fontSize: 22,
    fontWeight: '800',
  },
  settingsContentSubtitle: {
    color: '#8f8f8f',
    fontSize: 13,
  },
  formScroll: {
    flex: 1,
    maxHeight: 620,
  },
  formContent: {
    gap: 16,
    paddingHorizontal: 24,
    paddingTop: 20,
    paddingBottom: 24,
  },
  warningCard: {
    borderRadius: 18,
    backgroundColor: '#2a1719',
    borderWidth: 1,
    borderColor: '#553138',
    padding: 16,
    gap: 8,
  },
  warningTitle: {
    color: '#ffd7dd',
    fontWeight: '800',
  },
  warningLine: {
    color: '#ffecef',
    lineHeight: 20,
  },
  section: {
    borderRadius: 18,
    backgroundColor: '#1a1a1a',
    borderWidth: 1,
    borderColor: '#282828',
    padding: 16,
    gap: 10,
  },
  sectionTitle: {
    color: '#f0f0f0',
    fontSize: 18,
    fontWeight: '800',
  },
  helperText: {
    color: '#989898',
    lineHeight: 20,
  },
  fieldBlock: {
    gap: 6,
  },
  fieldLabel: {
    color: '#dfdfdf',
    fontSize: 13,
    fontWeight: '700',
  },
  input: {
    borderRadius: 14,
    backgroundColor: '#111111',
    borderWidth: 1,
    borderColor: '#3a3a3a',
    color: '#f6f6f6',
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  numberInput: {
    width: 74,
    textAlign: 'center',
    paddingHorizontal: 10,
  },
  memoryEditor: {
    minHeight: 240,
    lineHeight: 20,
  },
  validationText: {
    fontSize: 12,
    lineHeight: 17,
  },
  validationTextChecking: {
    color: '#8fb4dc',
  },
  validationTextValid: {
    color: '#9cf0b7',
  },
  validationTextInvalid: {
    color: '#ffb2a4',
  },
  validationTextError: {
    color: '#ffd27a',
  },
  settingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 16,
    paddingVertical: 6,
  },
  settingRowCopy: {
    flex: 1,
    gap: 4,
  },
  settingRowTitle: {
    color: '#f0f0f0',
    fontSize: 14,
    fontWeight: '700',
  },
  settingRowDescription: {
    color: '#8f8f8f',
    fontSize: 12,
    lineHeight: 18,
  },
  settingRowControls: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  stepperControl: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  stepperButton: {
    width: 34,
    height: 34,
    borderRadius: 12,
    backgroundColor: '#232323',
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepperButtonText: {
    color: '#f3f3f3',
    fontSize: 18,
    fontWeight: '800',
  },
  compactActionButton: {
    borderRadius: 12,
    backgroundColor: '#2f2f2f',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  compactActionButtonText: {
    color: '#f0f0f0',
    fontWeight: '800',
    fontSize: 12,
  },
  toggleSwitch: {
    width: 52,
    height: 30,
    borderRadius: 999,
    backgroundColor: '#2d2d2d',
    padding: 4,
    justifyContent: 'center',
  },
  toggleSwitchActive: {
    backgroundColor: '#53a4ff',
  },
  toggleSwitchKnob: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: '#f3f3f3',
  },
  toggleSwitchKnobActive: {
    alignSelf: 'flex-end',
  },
  pathValue: {
    color: '#dadada',
    lineHeight: 20,
  },
  pathActions: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  pathButton: {
    borderRadius: 12,
    backgroundColor: '#efefef',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  pathButtonText: {
    color: '#101010',
    fontWeight: '800',
  },
  buttonDisabled: {
    opacity: 0.55,
  },
  providerRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  providerChip: {
    borderRadius: 999,
    backgroundColor: '#262626',
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  providerChipText: {
    color: '#cdcdcd',
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  noteCard: {
    borderRadius: 16,
    backgroundColor: '#121212',
    borderWidth: 1,
    borderColor: '#242424',
    padding: 14,
    gap: 6,
  },
  noteLine: {
    color: '#d7d7d7',
    lineHeight: 20,
  },
  voiceModeRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  voiceModeButton: {
    borderRadius: 12,
    backgroundColor: '#121212',
    borderWidth: 1,
    borderColor: '#282828',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  voiceModeButtonActive: {
    backgroundColor: '#d4ff65',
    borderColor: '#d4ff65',
  },
  voiceModeButtonDisabled: {
    opacity: 0.45,
  },
  voiceModeButtonText: {
    color: '#dfdfdf',
    fontWeight: '800',
  },
  voiceModeButtonTextActive: {
    color: '#081324',
  },
  voiceModeHelper: {
    color: '#969696',
    lineHeight: 18,
  },
  voicePackList: {
    gap: 10,
  },
  voicePackCard: {
    borderRadius: 16,
    backgroundColor: '#121212',
    borderWidth: 1,
    borderColor: '#242424',
    padding: 14,
    gap: 10,
  },
  voicePackHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 12,
  },
  voicePackCopy: {
    flex: 1,
    gap: 4,
  },
  voicePackTitle: {
    color: '#f2f2f2',
    fontWeight: '800',
  },
  voicePackDescription: {
    color: '#b6b6b6',
    lineHeight: 18,
  },
  voicePackStatusBadge: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    alignSelf: 'flex-start',
  },
  voicePackStatusReady: {
    backgroundColor: '#203654',
  },
  voicePackStatusPlaceholder: {
    backgroundColor: '#353535',
  },
  voicePackStatusText: {
    color: '#f4f8ff',
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  voicePackMeta: {
    color: '#d7d7d7',
    lineHeight: 19,
  },
  voicePackProgressCard: {
    gap: 8,
    borderRadius: 14,
    backgroundColor: '#171717',
    borderWidth: 1,
    borderColor: '#2b2b2b',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  voicePackProgressTitle: {
    color: '#efefef',
    fontWeight: '700',
  },
  voicePackProgressTrack: {
    height: 8,
    borderRadius: 999,
    overflow: 'hidden',
    backgroundColor: '#242424',
  },
  voicePackProgressFill: {
    height: '100%',
    borderRadius: 999,
    backgroundColor: '#9bf24c',
  },
  voicePackProgressMeta: {
    color: '#9b9b9b',
    fontSize: 12,
    textTransform: 'capitalize',
  },
  voicePackActionRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  voicePackActionButton: {
    borderRadius: 12,
    backgroundColor: '#efefef',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  voicePackActionButtonSecondary: {
    borderRadius: 12,
    backgroundColor: '#1f1f1f',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  voicePackActionText: {
    color: '#111111',
    fontWeight: '800',
  },
  voicePackActionTextSecondary: {
    color: '#e2e2e2',
    fontWeight: '800',
  },
  metaRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  metaCard: {
    flex: 1,
    minWidth: 190,
    borderRadius: 16,
    backgroundColor: '#121212',
    borderWidth: 1,
    borderColor: '#242424',
    padding: 14,
    gap: 4,
  },
  metaLabel: {
    color: '#8f8f8f',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  metaValue: {
    color: '#f4f4f4',
    lineHeight: 20,
    fontWeight: '700',
  },
  metaIssue: {
    color: '#ffb3a6',
    fontSize: 12,
    lineHeight: 17,
  },
  extensionGuideCard: {
    borderRadius: 16,
    backgroundColor: '#121212',
    borderWidth: 1,
    borderColor: '#242424',
    padding: 14,
    gap: 6,
  },
  extensionGuideTitle: {
    color: '#f2f2f2',
    fontWeight: '800',
  },
  extensionGuideStep: {
    color: '#d7d7d7',
    lineHeight: 20,
  },
  extensionActionRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  secondaryButton: {
    borderRadius: 14,
    backgroundColor: '#1e1e1e',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  secondaryButtonText: {
    color: '#d9d9d9',
    fontWeight: '800',
  },
  primaryButton: {
    borderRadius: 14,
    backgroundColor: '#d4ff65',
    paddingHorizontal: 18,
    paddingVertical: 12,
  },
  primaryButtonDisabled: {
    opacity: 0.7,
  },
  primaryButtonText: {
    color: '#081324',
    fontWeight: '800',
  },
});
