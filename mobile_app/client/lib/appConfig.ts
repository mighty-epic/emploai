import { getDesktopBridge, loadDesktopBootstrap } from '../src/lib/desktopBridge';

export type AppConnectionMode = 'desktop_local' | 'remote_cloud' | 'direct_backend';

export type AppConfig = {
  apiBaseUrl: string;
  accessToken: string;
  accountToken: string;
  pairedDesktopId: string;
  connectionMode: AppConnectionMode;
};

const API_BASE_KEY = 'emploai.apiBaseUrl';
const ACCESS_TOKEN_KEY = 'emploai.accessToken';
const ACCOUNT_TOKEN_KEY = 'emploai.accountToken';
const PAIRED_DESKTOP_ID_KEY = 'emploai.pairedDesktopId';
const CONNECTION_MODE_KEY = 'emploai.connectionMode';

const DEFAULT_API_BASE_URL = (
  process.env.EXPO_PUBLIC_EMPLOAI_REMOTE_URL
  || process.env.EXPO_PUBLIC_EMPLOAI_APP_URL
  || ''
).trim();
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
  if (config.connectionMode === 'remote_cloud') {
    if (!config.accountToken.trim()) {
      return 'missing_account' as const;
    }
    if (!config.pairedDesktopId.trim()) {
      return 'missing_pairing' as const;
    }
    return 'ready' as const;
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
      accountToken: '',
      pairedDesktopId: '',
      connectionMode: 'desktop_local',
    };
  }

  const SecureStore = await import('expo-secure-store');
  const [apiBaseUrl, accessToken, accountToken, pairedDesktopId, connectionMode] = await Promise.all([
    SecureStore.getItemAsync(API_BASE_KEY),
    SecureStore.getItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.getItemAsync(ACCOUNT_TOKEN_KEY),
    SecureStore.getItemAsync(PAIRED_DESKTOP_ID_KEY),
    SecureStore.getItemAsync(CONNECTION_MODE_KEY),
  ]);

  const normalizedApiBaseUrl = normalizeApiBaseUrl(apiBaseUrl || DEFAULT_API_BASE_URL);
  const normalizedMode = (
    connectionMode === 'direct_backend'
      ? 'direct_backend'
      : connectionMode === 'remote_cloud'
        ? 'remote_cloud'
        : normalizedApiBaseUrl
          ? 'remote_cloud'
          : 'direct_backend'
  ) as AppConnectionMode;

  return {
    apiBaseUrl: normalizedApiBaseUrl,
    accessToken: (accessToken || DEFAULT_ACCESS_TOKEN).trim(),
    accountToken: (accountToken || '').trim(),
    pairedDesktopId: (pairedDesktopId || '').trim(),
    connectionMode: normalizedMode,
  };
}

export async function saveAppConfig(config: AppConfig): Promise<AppConfig> {
  if (getDesktopBridge()) {
    return {
      apiBaseUrl: normalizeApiBaseUrl(config.apiBaseUrl),
      accessToken: config.accessToken.trim(),
      accountToken: config.accountToken.trim(),
      pairedDesktopId: config.pairedDesktopId.trim(),
      connectionMode: 'desktop_local',
    };
  }

  const SecureStore = await import('expo-secure-store');
  const normalized = {
    apiBaseUrl: normalizeApiBaseUrl(config.apiBaseUrl),
    accessToken: config.accessToken.trim(),
    accountToken: config.accountToken.trim(),
    pairedDesktopId: config.pairedDesktopId.trim(),
    connectionMode: config.connectionMode,
  };

  await Promise.all([
    SecureStore.setItemAsync(API_BASE_KEY, normalized.apiBaseUrl),
    SecureStore.setItemAsync(ACCESS_TOKEN_KEY, normalized.accessToken),
    SecureStore.setItemAsync(ACCOUNT_TOKEN_KEY, normalized.accountToken),
    SecureStore.setItemAsync(PAIRED_DESKTOP_ID_KEY, normalized.pairedDesktopId),
    SecureStore.setItemAsync(CONNECTION_MODE_KEY, normalized.connectionMode),
  ]);

  return normalized;
}
