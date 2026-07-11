import { loadDesktopBootstrap } from '../src/lib/desktopBridge';

export type AppConnectionMode = 'desktop_local' | 'remote_cloud' | 'direct_backend';

export type AppConfig = {
  apiBaseUrl: string;
  accessToken: string;
  accountToken: string;
  accountTokenExpiresAt?: number | null;
  accountRememberMe?: boolean;
  accountUserId: string;
  accountEmail: string;
  accountMobileId: string;
  pairedDesktopId: string;
  connectionMode: AppConnectionMode;
};

export const DEFAULT_REMOTE_API_BASE_URL = 'http://127.0.0.1:8787';
export const DESKTOP_RENDERER_RELEASE = {
  version: '0.1.0-beta.14.6',
  channel: 'beta',
  apiBaseUrl: DEFAULT_REMOTE_API_BASE_URL,
} as const;

const DEFAULT_API_BASE_URL = (
  process.env.EXPO_PUBLIC_EMPLOAI_APP_URL
  || process.env.EXPO_PUBLIC_EMPLOAI_REMOTE_URL
  || DEFAULT_REMOTE_API_BASE_URL
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

function emptyDesktopConfig(): AppConfig {
  return {
    apiBaseUrl: normalizeApiBaseUrl(DEFAULT_API_BASE_URL),
    accessToken: DEFAULT_ACCESS_TOKEN.trim(),
    accountToken: '',
    accountTokenExpiresAt: null,
    accountRememberMe: false,
    accountUserId: '',
    accountEmail: '',
    accountMobileId: '',
    pairedDesktopId: '',
    connectionMode: 'desktop_local',
  };
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
  if (!desktopBootstrap) {
    return emptyDesktopConfig();
  }
  return {
    apiBaseUrl: normalizeApiBaseUrl(desktopBootstrap.apiBaseUrl || DEFAULT_API_BASE_URL),
    accessToken: (desktopBootstrap.accessToken || DEFAULT_ACCESS_TOKEN).trim(),
    accountToken: '',
    accountTokenExpiresAt: null,
    accountRememberMe: false,
    accountUserId: desktopBootstrap.userId ? String(desktopBootstrap.userId) : '',
    accountEmail: '',
    accountMobileId: '',
    pairedDesktopId: desktopBootstrap.deviceId || '',
    connectionMode: 'desktop_local',
  };
}

export async function saveAppConfig(config: AppConfig): Promise<AppConfig> {
  return {
    apiBaseUrl: normalizeApiBaseUrl(config.apiBaseUrl || DEFAULT_API_BASE_URL),
    accessToken: (config.accessToken || DEFAULT_ACCESS_TOKEN).trim(),
    accountToken: (config.accountToken || '').trim(),
    accountTokenExpiresAt: config.accountTokenExpiresAt || null,
    accountRememberMe: Boolean(config.accountRememberMe),
    accountUserId: (config.accountUserId || '').trim(),
    accountEmail: (config.accountEmail || '').trim().toLowerCase(),
    accountMobileId: (config.accountMobileId || '').trim(),
    pairedDesktopId: (config.pairedDesktopId || '').trim(),
    connectionMode: 'desktop_local',
  };
}

export async function clearRemoteAccountConfig(): Promise<AppConfig> {
  return emptyDesktopConfig();
}
