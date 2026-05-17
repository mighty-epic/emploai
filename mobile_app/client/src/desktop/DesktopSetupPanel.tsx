import { useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import type {
  DesktopSetupFieldValidation,
  DesktopMemoryState,
  DesktopSetupState,
  DesktopSetupValues,
  DesktopUpdateStatus,
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
};

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
];

export function DesktopSetupPanel({
  setupState,
  saving,
  voicePackBusyId,
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
}: Props) {
  const [values, setValues] = useState<DesktopSetupValues>(setupState.values);
  const [memoryDraft, setMemoryDraft] = useState(memoryState?.content || '');
  const [fieldValidation, setFieldValidation] = useState<Record<string, DesktopSetupFieldValidation>>({});
  const validationTimersRef = useRef<Record<string, ReturnType<typeof setTimeout> | null>>({});
  const validationRunRef = useRef<Record<string, number>>({});

  useEffect(() => {
    setValues(setupState.values);
    setFieldValidation({});
  }, [setupState]);

  useEffect(() => {
    setMemoryDraft(memoryState?.content || '');
  }, [memoryState?.content, memoryState?.memoryFilePath]);

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
      clearTimeout(validationTimersRef.current[fieldKey]);
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
  const englishVoicePack = voicePacks.find((pack) => pack.id === VOICE_ENGINE_ENGLISH) ?? null;
  const hebrewVoicePack = voicePacks.find((pack) => pack.id === VOICE_ENGINE_HEBREW) ?? null;
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

  const setVoiceDefaultEngine = (nextEngine: string) => {
    setValues((current) => {
      const englishRequested = current.VOICE_ENGLISH_REQUESTED !== '0';
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
        const fallbackEngine =
          current.VOICE_HEBREW_REQUESTED === '1' ? VOICE_ENGINE_HEBREW : VOICE_ENGINE_NONE;
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
      const fallbackEngine =
        current.VOICE_ENGLISH_REQUESTED !== '0' ? VOICE_ENGINE_ENGLISH : VOICE_ENGINE_NONE;
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
          <Text style={styles.sectionTitle}>Voice input packs</Text>
          <Text style={styles.helperText}>
            The app now tracks voice input by pack. English and Hebrew use the same desktop capture flow, and each pack can be enabled or disabled separately.
          </Text>

          <View style={styles.voiceModeRow}>
            <Pressable
              style={[styles.voiceModeButton, selectedVoiceEngine === VOICE_ENGINE_NONE ? styles.voiceModeButtonActive : null]}
              onPress={() => setVoiceDefaultEngine(VOICE_ENGINE_NONE)}
            >
              <Text style={[styles.voiceModeButtonText, selectedVoiceEngine === VOICE_ENGINE_NONE ? styles.voiceModeButtonTextActive : null]}>No voice</Text>
            </Pressable>
            <Pressable
              style={[
                styles.voiceModeButton,
                selectedVoiceEngine === VOICE_ENGINE_ENGLISH ? styles.voiceModeButtonActive : null,
                values.VOICE_ENGLISH_REQUESTED === '0' || !englishVoicePack?.available ? styles.voiceModeButtonDisabled : null,
              ]}
              onPress={() => setVoiceDefaultEngine(VOICE_ENGINE_ENGLISH)}
              disabled={values.VOICE_ENGLISH_REQUESTED === '0' || !englishVoicePack?.available}
            >
              <Text style={[styles.voiceModeButtonText, selectedVoiceEngine === VOICE_ENGINE_ENGLISH ? styles.voiceModeButtonTextActive : null]}>English</Text>
            </Pressable>
            <Pressable
              style={[
                styles.voiceModeButton,
                selectedVoiceEngine === VOICE_ENGINE_HEBREW ? styles.voiceModeButtonActive : null,
                values.VOICE_HEBREW_REQUESTED !== '1' || !hebrewVoicePack?.available ? styles.voiceModeButtonDisabled : null,
              ]}
              onPress={() => setVoiceDefaultEngine(VOICE_ENGINE_HEBREW)}
              disabled={values.VOICE_HEBREW_REQUESTED !== '1' || !hebrewVoicePack?.available}
            >
              <Text style={[styles.voiceModeButtonText, selectedVoiceEngine === VOICE_ENGINE_HEBREW ? styles.voiceModeButtonTextActive : null]}>Hebrew</Text>
            </Pressable>
          </View>

          <Text style={styles.voiceModeHelper}>
            Selected engine: {selectedVoicePack?.title || 'No voice'} · Source: {voiceSelectionSource}
          </Text>

          <View style={styles.voicePackList}>
            {voicePacks.map((pack) => (
              <View key={pack.id} style={styles.voicePackCard}>
                <View style={styles.voicePackHeader}>
                  <View style={styles.voicePackCopy}>
                    <Text style={styles.voicePackTitle}>{pack.title}</Text>
                    <Text style={styles.voicePackDescription}>{pack.description}</Text>
                  </View>
                  <View style={[styles.voicePackStatusBadge, pack.placeholder ? styles.voicePackStatusPlaceholder : styles.voicePackStatusReady]}>
                    <Text style={styles.voicePackStatusText}>{pack.status.replace(/_/g, ' ')}</Text>
                  </View>
                </View>
                <Text style={styles.voicePackMeta}>
                  Requested: {pack.id === VOICE_ENGINE_ENGLISH ? (values.VOICE_ENGLISH_REQUESTED === '0' ? 'no' : 'yes') : values.VOICE_HEBREW_REQUESTED === '1' ? 'yes' : 'no'}
                  {' · '}
                  Installed: {pack.installed ? 'yes' : 'no'}
                  {pack.source ? ` · Source: ${pack.source}` : ''}
                  {pack.supportsAlwaysOn ? ' · Always-on target included' : ''}
                </Text>
                {pack.issues?.length ? (
                  <Text style={styles.metaIssue}>{pack.issues[0]}</Text>
                ) : null}
                <View style={styles.voicePackActionRow}>
                  <Pressable style={styles.voicePackActionButton} onPress={() => toggleVoicePackRequest(pack)}>
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
                        {isVoicePackBusy(pack.id) ? 'Installing...' : 'Install Pack'}
                      </Text>
                    </Pressable>
                  )}
                  {pack.id === VOICE_ENGINE_ENGLISH ? (
                    <Pressable
                      style={[
                        styles.voicePackActionButtonSecondary,
                        values.VOICE_ENGLISH_REQUESTED === '0' || !pack.available ? styles.voiceModeButtonDisabled : null,
                      ]}
                      onPress={() => setVoiceDefaultEngine(VOICE_ENGINE_ENGLISH)}
                      disabled={values.VOICE_ENGLISH_REQUESTED === '0' || !pack.available}
                    >
                      <Text style={styles.voicePackActionTextSecondary}>Use English</Text>
                    </Pressable>
                  ) : (
                    <Pressable
                      style={[
                        styles.voicePackActionButtonSecondary,
                        values.VOICE_HEBREW_REQUESTED !== '1' || !pack.available ? styles.voiceModeButtonDisabled : null,
                      ]}
                      onPress={() => setVoiceDefaultEngine(VOICE_ENGINE_HEBREW)}
                      disabled={values.VOICE_HEBREW_REQUESTED !== '1' || !pack.available}
                    >
                      <Text style={styles.voicePackActionTextSecondary}>Use Hebrew</Text>
                    </Pressable>
                  )}
                </View>
              </View>
            ))}
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
      </ScrollView>

      <View style={styles.footer}>
        {onDismiss ? (
          <Pressable style={styles.secondaryButton} onPress={onDismiss} disabled={saving}>
            <Text style={styles.secondaryButtonText}>Close</Text>
          </Pressable>
        ) : <View />}
        <Pressable style={[styles.primaryButton, saving ? styles.primaryButtonDisabled : null]} onPress={() => onSave(values)} disabled={saving}>
          <Text style={styles.primaryButtonText}>{saving ? 'Saving...' : primaryActionLabel}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  shell: {
    borderRadius: 28,
    backgroundColor: '#0f172d',
    borderWidth: 1,
    borderColor: '#223052',
    padding: 20,
    gap: 16,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 16,
  },
  headerCopy: {
    flex: 1,
    gap: 6,
  },
  eyebrow: {
    color: '#8ea4cb',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.9,
  },
  title: {
    color: '#f6fbff',
    fontSize: 26,
    fontWeight: '800',
  },
  subtitle: {
    color: '#a8bbda',
    lineHeight: 20,
    maxWidth: 760,
  },
  versionBadge: {
    width: 190,
    borderRadius: 20,
    backgroundColor: '#15203a',
    padding: 14,
    gap: 4,
  },
  versionLabel: {
    color: '#8ea4cb',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  versionValue: {
    color: '#f6fbff',
    fontSize: 18,
    fontWeight: '800',
  },
  formScroll: {
    maxHeight: 620,
  },
  formContent: {
    gap: 16,
    paddingBottom: 4,
  },
  warningCard: {
    borderRadius: 20,
    backgroundColor: '#361821',
    borderWidth: 1,
    borderColor: '#6a3244',
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
    borderRadius: 22,
    backgroundColor: '#121d35',
    borderWidth: 1,
    borderColor: '#1d2c4a',
    padding: 16,
    gap: 10,
  },
  sectionTitle: {
    color: '#f6fbff',
    fontSize: 18,
    fontWeight: '800',
  },
  helperText: {
    color: '#9fb4d6',
    lineHeight: 20,
  },
  fieldBlock: {
    gap: 6,
  },
  fieldLabel: {
    color: '#dbe7ff',
    fontSize: 13,
    fontWeight: '700',
  },
  input: {
    borderRadius: 16,
    backgroundColor: '#0a1327',
    borderWidth: 1,
    borderColor: '#38507a',
    color: '#f6fbff',
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  memoryEditor: {
    minHeight: 240,
    lineHeight: 20,
    borderColor: '#47628f',
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
  pathValue: {
    color: '#d5e3ff',
    lineHeight: 20,
  },
  pathActions: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  pathButton: {
    borderRadius: 14,
    backgroundColor: '#f4f8ff',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  buttonDisabled: {
    opacity: 0.55,
  },
  pathButtonText: {
    color: '#0c1a35',
    fontWeight: '800',
  },
  providerRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  providerChip: {
    borderRadius: 999,
    backgroundColor: '#1d3154',
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  providerChipText: {
    color: '#a8ddff',
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  noteCard: {
    borderRadius: 18,
    backgroundColor: '#0c1428',
    borderWidth: 1,
    borderColor: '#1e2f4e',
    padding: 14,
    gap: 6,
  },
  noteLine: {
    color: '#d7e4ff',
    lineHeight: 20,
  },
  voiceModeRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  voiceModeButton: {
    borderRadius: 14,
    backgroundColor: '#0c1428',
    borderWidth: 1,
    borderColor: '#263758',
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
    color: '#d7e4ff',
    fontWeight: '800',
  },
  voiceModeButtonTextActive: {
    color: '#081324',
  },
  voiceModeHelper: {
    color: '#9fb4d6',
    lineHeight: 18,
  },
  voicePackList: {
    gap: 10,
  },
  voicePackCard: {
    borderRadius: 18,
    backgroundColor: '#0c1428',
    borderWidth: 1,
    borderColor: '#1e2f4e',
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
    color: '#eef6ff',
    fontWeight: '800',
  },
  voicePackDescription: {
    color: '#bfd0ec',
    lineHeight: 18,
  },
  voicePackStatusBadge: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    alignSelf: 'flex-start',
  },
  voicePackStatusReady: {
    backgroundColor: '#14345c',
  },
  voicePackStatusPlaceholder: {
    backgroundColor: '#3a2946',
  },
  voicePackStatusText: {
    color: '#f4f8ff',
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  voicePackMeta: {
    color: '#d7e4ff',
    lineHeight: 19,
  },
  voicePackActionRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  voicePackActionButton: {
    borderRadius: 14,
    backgroundColor: '#f4f8ff',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  voicePackActionButtonSecondary: {
    borderRadius: 14,
    backgroundColor: '#15203a',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  voicePackActionText: {
    color: '#0c1a35',
    fontWeight: '800',
  },
  voicePackActionTextSecondary: {
    color: '#d7e4ff',
    fontWeight: '800',
  },
  voicePackComingSoon: {
    borderRadius: 14,
    backgroundColor: '#17233d',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  voicePackComingSoonText: {
    color: '#a8bbda',
    fontWeight: '700',
  },
  metaRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  extensionGuideCard: {
    borderRadius: 18,
    backgroundColor: '#0c1428',
    borderWidth: 1,
    borderColor: '#2c4c82',
    padding: 14,
    gap: 6,
  },
  extensionGuideTitle: {
    color: '#eef6ff',
    fontWeight: '800',
  },
  extensionGuideStep: {
    color: '#d7e4ff',
    lineHeight: 20,
  },
  extensionActionRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  metaCard: {
    flex: 1,
    minWidth: 190,
    borderRadius: 18,
    backgroundColor: '#0c1428',
    borderWidth: 1,
    borderColor: '#1e2f4e',
    padding: 14,
    gap: 4,
  },
  metaLabel: {
    color: '#91a6ca',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  metaValue: {
    color: '#f4f8ff',
    lineHeight: 20,
    fontWeight: '700',
  },
  metaIssue: {
    color: '#ffb3a6',
    fontSize: 12,
    lineHeight: 17,
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  secondaryButton: {
    borderRadius: 16,
    backgroundColor: '#1a2641',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  secondaryButtonText: {
    color: '#d9e7ff',
    fontWeight: '800',
  },
  primaryButton: {
    borderRadius: 16,
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
