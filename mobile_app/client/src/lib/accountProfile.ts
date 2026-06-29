import type { RemoteAccountCloudProfile } from './appApiTypes';

export type SharedSettingsDraft = {
  telegramAllowedUserIds: string;
  interruptPolicy: 'none' | 'steer_now' | 'after_tool';
  verboseMode: boolean;
  cloudChatBackupEnabled: boolean;
  customSystemPromptAppend: string;
  maxTurns: string;
  sleepModeEnabled: boolean;
  memoryPromptContextEnabled: boolean;
  memorySearchEnabled: boolean;
  memoryWriteEnabled: boolean;
};

const DEFAULT_MEMORY_CONTROLS = {
  prompt_context_enabled: true,
  search_enabled: true,
  write_enabled: true,
};

export function normalizeTelegramIds(value: string) {
  return value
    .split(',')
    .map((part) => part.trim().replace(/^\+/, ''))
    .filter((part, index, items) => /^-?\d+$/.test(part) && items.indexOf(part) === index);
}

function supportedInterruptPolicy(value: unknown): SharedSettingsDraft['interruptPolicy'] {
  return value === 'steer_now' || value === 'after_tool' ? value : 'none';
}

function stringOrEmpty(value: unknown) {
  return typeof value === 'string' ? value : '';
}

export function profileToSharedSettingsDraft(profile?: RemoteAccountCloudProfile | null): SharedSettingsDraft {
  const preferences = profile?.preferences || {};
  const memoryControls = preferences.memory_controls || {};
  const telegram = profile?.integrations?.telegram || {};
  const ids = Array.isArray(telegram.allowed_user_ids)
    ? telegram.allowed_user_ids
    : Array.isArray(telegram.allowedUserIds)
      ? telegram.allowedUserIds
      : [];
  const maxTurns = typeof preferences.max_turns === 'number' && preferences.max_turns > 0
    ? String(preferences.max_turns)
    : '';
  return {
    telegramAllowedUserIds: ids.map((item) => String(item)).join(', '),
    interruptPolicy: supportedInterruptPolicy(preferences.interrupt_policy_default),
    verboseMode: Boolean(preferences.verbose_mode),
    cloudChatBackupEnabled: preferences.cloud_chat_backup_enabled !== false,
    customSystemPromptAppend: stringOrEmpty(preferences.custom_system_prompt_append),
    maxTurns,
    sleepModeEnabled: Boolean(preferences.sleep_mode_enabled),
    memoryPromptContextEnabled: memoryControls.prompt_context_enabled !== false,
    memorySearchEnabled: memoryControls.search_enabled !== false,
    memoryWriteEnabled: memoryControls.write_enabled !== false,
  };
}

export function validateSharedSettingsDraft(draft: SharedSettingsDraft) {
  const prompt = draft.customSystemPromptAppend.trim();
  if (prompt.length > 8000) {
    return 'Custom instructions must be 8000 characters or less.';
  }
  const turnsText = draft.maxTurns.trim();
  if (turnsText) {
    const turns = Number(turnsText);
    if (!Number.isInteger(turns) || turns < 10 || turns > 1000) {
      return 'Max turns must be a whole number between 10 and 1000.';
    }
  }
  return null;
}

export function sharedMaxTurnsFromDraft(draft: SharedSettingsDraft) {
  const turnsText = draft.maxTurns.trim();
  if (!turnsText) return null;
  return Number(turnsText);
}

export function applySharedSettingsDraftToProfile(
  profile: RemoteAccountCloudProfile | null | undefined,
  draft: SharedSettingsDraft,
): RemoteAccountCloudProfile {
  const current = profile || {};
  const currentPreferences = current.preferences || {};
  const currentIntegrations = current.integrations || {};
  const currentTelegram = currentIntegrations.telegram || {};
  const currentSetup = current.setup || {};
  const ids = normalizeTelegramIds(draft.telegramAllowedUserIds);
  return {
    ...current,
    schema_version: 1,
    preferences: {
      ...currentPreferences,
      verbose_mode: draft.verboseMode,
      cloud_chat_backup_enabled: draft.cloudChatBackupEnabled,
      interrupt_policy_default: draft.interruptPolicy,
      custom_system_prompt_append: draft.customSystemPromptAppend.trim() || null,
      max_turns: sharedMaxTurnsFromDraft(draft),
      sleep_mode_enabled: draft.sleepModeEnabled,
      memory_controls: {
        ...DEFAULT_MEMORY_CONTROLS,
        ...(currentPreferences.memory_controls || {}),
        prompt_context_enabled: draft.memoryPromptContextEnabled,
        search_enabled: draft.memorySearchEnabled,
        write_enabled: draft.memoryWriteEnabled,
      },
    },
    setup: {
      ...currentSetup,
      desktop: currentSetup.desktop && typeof currentSetup.desktop === 'object' ? currentSetup.desktop : {},
      mobile: currentSetup.mobile && typeof currentSetup.mobile === 'object' ? currentSetup.mobile : {},
    },
    integrations: {
      ...currentIntegrations,
      telegram: {
        ...currentTelegram,
        enabled: ids.length > 0 || Boolean(currentTelegram.enabled),
        allowed_user_ids: ids,
      },
    },
  };
}
