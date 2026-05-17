import { getDesktopBridge, loadDesktopBootstrap } from '../src/lib/desktopBridge';

export type AppConfig = {
  apiBaseUrl: string;
  accessToken: string;
};

const API_BASE_KEY = 'emploai.apiBaseUrl';
const ACCESS_TOKEN_KEY = 'emploai.accessToken';

const DEFAULT_API_BASE_URL = (process.env.EXPO_PUBLIC_EMPLOAI_APP_URL || '').trim();
const DEFAULT_ACCESS_TOKEN = process.env.EXPO_PUBLIC_EMPLOAI_APP_TOKEN || '';

export function normalizeApiBaseUrl(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return '';
  return trimmed.replace(/\/+$/, '');
}

export function isSupportedApiBaseUrl(value: string) {
  const normalized = normalizeApiBaseUrl(value);
  if (!normalized) return false;
  return /^https?:\/\//i.test(normalized);
}

export function buildWsBaseUrl(apiBaseUrl: string) {
  const normalized = normalizeApiBaseUrl(apiBaseUrl);
  if (!normalized) return '';
  return normalized.replace(/^http:/i, 'ws:').replace(/^https:/i, 'wss:');
}

export function getConnectionSetupState(config: AppConfig) {
  if (!normalizeApiBaseUrl(config.apiBaseUrl)) {
    return 'missing_backend' as const;
  }
  if (!config.accessToken.trim()) {
    return 'missing_token' as const;
  }
  return 'ready' as const;
}

export async function loadAppConfig(): Promise<AppConfig> {
  const desktopBootstrap = await loadDesktopBootstrap();
  if (desktopBootstrap) {
    return {
      apiBaseUrl: normalizeApiBaseUrl(desktopBootstrap.apiBaseUrl),
      accessToken: (desktopBootstrap.accessToken || '').trim(),
    };
  }

  const SecureStore = await import('expo-secure-store');
  const [apiBaseUrl, accessToken] = await Promise.all([
    SecureStore.getItemAsync(API_BASE_KEY),
    SecureStore.getItemAsync(ACCESS_TOKEN_KEY),
  ]);

  return {
    apiBaseUrl: normalizeApiBaseUrl(apiBaseUrl || DEFAULT_API_BASE_URL),
    accessToken: (accessToken || DEFAULT_ACCESS_TOKEN).trim(),
  };
}

export async function saveAppConfig(config: AppConfig): Promise<AppConfig> {
  if (getDesktopBridge()) {
    return {
      apiBaseUrl: normalizeApiBaseUrl(config.apiBaseUrl),
      accessToken: config.accessToken.trim(),
    };
  }

  const SecureStore = await import('expo-secure-store');
  const normalized = {
    apiBaseUrl: normalizeApiBaseUrl(config.apiBaseUrl),
    accessToken: config.accessToken.trim(),
  };

  await Promise.all([
    SecureStore.setItemAsync(API_BASE_KEY, normalized.apiBaseUrl),
    SecureStore.setItemAsync(ACCESS_TOKEN_KEY, normalized.accessToken),
  ]);

  return normalized;
}
