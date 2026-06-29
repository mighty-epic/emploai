import type { DesktopSetupValues } from '@/lib/desktopBridge';

export const LOCAL_SETUP_SECRET_FIELDS = new Set<string>([
  'OPENAI_API_KEY',
  'ANTHROPIC_API_KEY',
  'GOOGLE_API_KEY',
  'GEMINI_API_KEY',
  'XAI_API_KEY',
  'DEEPSEEK_API_KEY',
  'NVIDIA_API_KEY',
  'OPENROUTER_API_KEY',
  'TELEGRAM_BOT_TOKEN',
  'EMPLOAI_TELEGRAM_BOT_TOKENS_JSON',
  'EMPLOAI_REMOTE_CONTROL_PASSWORD',
  'EMPLOAI_REMOTE_CONTROL_SESSION_TOKEN',
  'GMAIL_LOGIN_EMAIL',
  'GMAIL_LOGIN_PASSWORD',
  'GMAIL_EMAIL',
  'GMAIL_PASSWORD',
]);

export const PROVIDER_SETUP_SECRET_FIELDS = new Set<string>([
  'OPENAI_API_KEY',
  'ANTHROPIC_API_KEY',
  'GOOGLE_API_KEY',
  'GEMINI_API_KEY',
  'XAI_API_KEY',
  'DEEPSEEK_API_KEY',
  'NVIDIA_API_KEY',
  'OPENROUTER_API_KEY',
]);

export const LOCAL_RUNTIME_SETUP_SECRET_FIELDS = new Set<string>([
  ...PROVIDER_SETUP_SECRET_FIELDS,
  'TELEGRAM_BOT_TOKEN',
  'EMPLOAI_TELEGRAM_BOT_TOKENS_JSON',
]);

export const RESTART_REQUIRED_SETUP_SECRET_FIELDS = new Set<string>([
  'TELEGRAM_BOT_TOKEN',
  'EMPLOAI_TELEGRAM_BOT_TOKENS_JSON',
]);

export const LIVE_APPLY_SETUP_SECRET_FIELDS = new Set<string>([
  ...PROVIDER_SETUP_SECRET_FIELDS,
]);

export const RESTART_REQUIRED_SETUP_FIELDS = new Set<keyof DesktopSetupValues>([
  'ALLOWED_USER_IDS',
  'EMPLOAI_REMOTE_CONTROL_BASE_URL',
  'EMPLOAI_REMOTE_CONTROL_EMAIL',
  'EMPLOAI_REMOTE_CONTROL_PASSWORD',
  'EMPLOAI_REMOTE_DESKTOP_NAME',
  'EMPLOAI_REMOTE_DESKTOP_KEY',
]);

export const LIVE_APPLY_SETUP_FIELDS = new Set<keyof DesktopSetupValues>([
  'DEFAULT_WORKSPACE',
  'PLANNER_MODEL',
  'INTERRUPT_POLICY_DEFAULT',
  'VOICE_DEFAULT_ENGINE',
  'VOICE_ENGLISH_REQUESTED',
  'VOICE_HEBREW_REQUESTED',
]);

export const SETUP_PROVIDER_SECRET_LABELS: Record<string, string> = {
  OPENAI_API_KEY: 'OpenAI API key',
  ANTHROPIC_API_KEY: 'Anthropic API key',
  GOOGLE_API_KEY: 'Google Gemini API key',
  XAI_API_KEY: 'xAI Grok API key',
  DEEPSEEK_API_KEY: 'DeepSeek API key',
  NVIDIA_API_KEY: 'NVIDIA API key',
  OPENROUTER_API_KEY: 'OpenRouter API key',
};

export const SETUP_PROVIDER_SECRET_PROVIDER_KEYS: Record<string, string> = {
  OPENAI_API_KEY: 'openai',
  ANTHROPIC_API_KEY: 'anthropic',
  GOOGLE_API_KEY: 'google',
  XAI_API_KEY: 'xai',
  DEEPSEEK_API_KEY: 'deepseek',
  NVIDIA_API_KEY: 'nvidia',
  OPENROUTER_API_KEY: 'openrouter',
};

export const SETUP_PROVIDER_DISPLAY_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  google: 'Google Gemini',
  xai: 'xAI',
  deepseek: 'DeepSeek',
  nvidia: 'NVIDIA NIM',
  openrouter: 'OpenRouter',
};

export function setupProviderKeyFromLabel(provider: string) {
  const normalized = String(provider || '').trim().toLowerCase();
  if (!normalized) {
    return '';
  }
  const compact = normalized.replace(/[^a-z0-9]/g, '');
  const matched = Object.entries(SETUP_PROVIDER_DISPLAY_LABELS).find(([, label]) => (
    label.toLowerCase() === normalized
    || label.toLowerCase().replace(/[^a-z0-9]/g, '') === compact
  ));
  return matched?.[0] || normalized;
}

export function configuredProviderChipLabels(configuredProviders: string[], lockedProviderSecretNames: string[]) {
  const labels: string[] = [];
  const seen = new Set<string>();

  const addProviderKey = (rawProvider: string) => {
    const providerKey = setupProviderKeyFromLabel(rawProvider);
    if (!providerKey || seen.has(providerKey)) {
      return;
    }
    seen.add(providerKey);
    labels.push(SETUP_PROVIDER_DISPLAY_LABELS[providerKey] || rawProvider);
  };

  configuredProviders.forEach(addProviderKey);
  lockedProviderSecretNames
    .map((secretName) => SETUP_PROVIDER_SECRET_PROVIDER_KEYS[secretName])
    .filter(Boolean)
    .forEach(addProviderKey);

  return labels;
}

export function sanitizeLocalSetupValues(values: Partial<DesktopSetupValues>) {
  const cleanValues: Partial<DesktopSetupValues> = {};
  Object.entries(values || {}).forEach(([key, value]) => {
    if (LOCAL_SETUP_SECRET_FIELDS.has(key)) {
      return;
    }
    cleanValues[key as keyof DesktopSetupValues] = value as never;
  });
  return cleanValues;
}

export function setupValuesForRuntimeSave(values: Partial<DesktopSetupValues>) {
  const cleanValues = sanitizeLocalSetupValues(values);
  Object.entries(values || {}).forEach(([key, value]) => {
    const cleanValue = String(value || '').trim();
    if (LOCAL_RUNTIME_SETUP_SECRET_FIELDS.has(key) && cleanValue) {
      cleanValues[key as keyof DesktopSetupValues] = value as never;
    }
  });
  return cleanValues;
}

export function hasFilledSetupSecret(values: Partial<DesktopSetupValues>) {
  return Object.entries(values || {}).some(([key, value]) => (
    LOCAL_SETUP_SECRET_FIELDS.has(key) && String(value || '').trim().length > 0
  ));
}

export function hasFilledRestartRequiredSetupSecret(values: Partial<DesktopSetupValues>) {
  return Object.entries(values || {}).some(([key, value]) => (
    RESTART_REQUIRED_SETUP_SECRET_FIELDS.has(key) && String(value || '').trim().length > 0
  ));
}

export function hasFilledLiveApplySetupSecret(values: Partial<DesktopSetupValues>) {
  return Object.entries(values || {}).some(([key, value]) => (
    LIVE_APPLY_SETUP_SECRET_FIELDS.has(key) && String(value || '').trim().length > 0
  ));
}

export function normalizeSetupValue(value: string | undefined) {
  return String(value ?? '').trim();
}

export function changedSetupFields(
  nextValues: Partial<DesktopSetupValues>,
  baseline: Partial<DesktopSetupValues> | null | undefined,
) {
  if (!baseline) {
    return Object.keys(nextValues || {}) as Array<keyof DesktopSetupValues>;
  }
  const keys = new Set<keyof DesktopSetupValues>([
    ...(Object.keys(nextValues || {}) as Array<keyof DesktopSetupValues>),
    ...(Object.keys(baseline || {}) as Array<keyof DesktopSetupValues>),
  ]);
  return Array.from(keys).filter((key) => normalizeSetupValue(nextValues[key]) !== normalizeSetupValue(baseline[key]));
}
