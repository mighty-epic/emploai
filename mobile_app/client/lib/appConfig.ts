export type AppConnectionMode = 'remote_cloud' | 'direct_backend';

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

const API_BASE_KEY = 'emploai.apiBaseUrl';
const ACCESS_TOKEN_KEY = 'emploai.accessToken';
const ACCOUNT_TOKEN_KEY = 'emploai.accountToken';
const ACCOUNT_TOKEN_EXPIRES_AT_KEY = 'emploai.accountTokenExpiresAt';
const ACCOUNT_REMEMBER_ME_KEY = 'emploai.accountRememberMe';
const ACCOUNT_USER_ID_KEY = 'emploai.accountUserId';
const ACCOUNT_EMAIL_KEY = 'emploai.accountEmail';
const ACCOUNT_MOBILE_ID_KEY = 'emploai.accountMobileId';
const PAIRED_DESKTOP_ID_KEY = 'emploai.pairedDesktopId';
const CONNECTION_MODE_KEY = 'emploai.connectionMode';
const MOBILE_DEVICE_KEY = 'emploai.mobileDeviceKey';
export const DEFAULT_REMOTE_API_BASE_URL = 'https://api.kraitos.app';
export const MOBILE_RELEASE = {
  version: '0.1.0-beta.14.6',
  channel: 'beta',
  desktopCompatibility: '0.1.0-beta.14.6',
  apiBaseUrl: DEFAULT_REMOTE_API_BASE_URL,
} as const;

const DEFAULT_API_BASE_URL = (
  process.env.EXPO_PUBLIC_EMPLOAI_REMOTE_URL
  || process.env.EXPO_PUBLIC_EMPLOAI_APP_URL
  || DEFAULT_REMOTE_API_BASE_URL
).trim();
const DEFAULT_ACCESS_TOKEN = process.env.EXPO_PUBLIC_EMPLOAI_APP_TOKEN || '';
let volatileAppConfig: AppConfig | null = null;

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

function createMobileDeviceKey() {
  const cryptoApi = globalThis.crypto as Crypto | undefined;
  if (typeof cryptoApi?.randomUUID === 'function') {
    return `mobile-${cryptoApi.randomUUID()}`;
  }
  const bytes = new Uint8Array(16);
  if (typeof cryptoApi?.getRandomValues === 'function') {
    cryptoApi.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  return `mobile-${Array.from(bytes).map((value) => value.toString(16).padStart(2, '0')).join('')}`;
}

export async function getOrCreateMobileDeviceKey() {
  const SecureStore = await import('expo-secure-store');
  const existing = (await SecureStore.getItemAsync(MOBILE_DEVICE_KEY))?.trim();
  if (existing) {
    return existing;
  }
  const created = createMobileDeviceKey();
  await SecureStore.setItemAsync(MOBILE_DEVICE_KEY, created);
  return created;
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
  if (volatileAppConfig) {
    return volatileAppConfig;
  }

  const SecureStore = await import('expo-secure-store');
  const [
    apiBaseUrl,
    accessToken,
    accountToken,
    accountTokenExpiresAt,
    accountRememberMe,
    accountUserId,
    accountEmail,
    accountMobileId,
    pairedDesktopId,
    connectionMode,
  ] = await Promise.all([
    SecureStore.getItemAsync(API_BASE_KEY),
    SecureStore.getItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.getItemAsync(ACCOUNT_TOKEN_KEY),
    SecureStore.getItemAsync(ACCOUNT_TOKEN_EXPIRES_AT_KEY),
    SecureStore.getItemAsync(ACCOUNT_REMEMBER_ME_KEY),
    SecureStore.getItemAsync(ACCOUNT_USER_ID_KEY),
    SecureStore.getItemAsync(ACCOUNT_EMAIL_KEY),
    SecureStore.getItemAsync(ACCOUNT_MOBILE_ID_KEY),
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

  const parsedExpiresAt = Number(accountTokenExpiresAt || 0);
  const storedAccountToken = (accountToken || '').trim();
  const storedAccessToken = (accessToken || '').trim();
  const hasStoredRemoteAccount = Boolean(storedAccountToken || storedAccessToken);
  const tokenExpired = Boolean(storedAccountToken && Number.isFinite(parsedExpiresAt) && parsedExpiresAt > 0 && parsedExpiresAt <= Date.now());
  if (tokenExpired) {
    await Promise.all([
      SecureStore.deleteItemAsync(ACCOUNT_TOKEN_KEY),
      SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY),
      SecureStore.deleteItemAsync(ACCOUNT_TOKEN_EXPIRES_AT_KEY),
      SecureStore.deleteItemAsync(ACCOUNT_REMEMBER_ME_KEY),
      SecureStore.deleteItemAsync(ACCOUNT_USER_ID_KEY),
      SecureStore.deleteItemAsync(ACCOUNT_EMAIL_KEY),
      SecureStore.deleteItemAsync(ACCOUNT_MOBILE_ID_KEY),
      SecureStore.deleteItemAsync(PAIRED_DESKTOP_ID_KEY),
    ]);
  }

  return {
    apiBaseUrl: normalizedApiBaseUrl,
    accessToken: tokenExpired ? '' : (storedAccessToken || DEFAULT_ACCESS_TOKEN).trim(),
    accountToken: tokenExpired ? '' : storedAccountToken,
    accountTokenExpiresAt: tokenExpired ? null : (Number.isFinite(parsedExpiresAt) && parsedExpiresAt > 0 ? parsedExpiresAt : null),
    accountRememberMe: accountRememberMe === '1',
    accountUserId: tokenExpired || !hasStoredRemoteAccount ? '' : (accountUserId || '').trim(),
    accountEmail: tokenExpired || !hasStoredRemoteAccount ? '' : (accountEmail || '').trim().toLowerCase(),
    accountMobileId: tokenExpired || !hasStoredRemoteAccount ? '' : (accountMobileId || '').trim(),
    pairedDesktopId: tokenExpired ? '' : (pairedDesktopId || '').trim(),
    connectionMode: normalizedMode,
  };
}

export async function saveAppConfig(config: AppConfig): Promise<AppConfig> {
  const SecureStore = await import('expo-secure-store');
  const normalized = {
    apiBaseUrl: normalizeApiBaseUrl(config.apiBaseUrl),
    accessToken: config.accessToken.trim(),
    accountToken: config.accountToken.trim(),
    accountTokenExpiresAt: config.accountTokenExpiresAt || null,
    accountRememberMe: Boolean(config.accountRememberMe),
    accountUserId: (config.accountUserId || '').trim(),
    accountEmail: (config.accountEmail || '').trim().toLowerCase(),
    accountMobileId: (config.accountMobileId || '').trim(),
    pairedDesktopId: config.pairedDesktopId.trim(),
    connectionMode: config.connectionMode,
  };

  const accountTokenIsEphemeral = Boolean(
    normalized.connectionMode === 'remote_cloud'
    && normalized.accountToken
    && !normalized.accountRememberMe
  );
  volatileAppConfig = accountTokenIsEphemeral ? normalized : null;

  await Promise.all([
    SecureStore.setItemAsync(API_BASE_KEY, normalized.apiBaseUrl),
    accountTokenIsEphemeral
      ? SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY)
      : SecureStore.setItemAsync(ACCESS_TOKEN_KEY, normalized.accessToken),
    accountTokenIsEphemeral
      ? SecureStore.deleteItemAsync(ACCOUNT_TOKEN_KEY)
      : SecureStore.setItemAsync(ACCOUNT_TOKEN_KEY, normalized.accountToken),
    normalized.accountTokenExpiresAt && !accountTokenIsEphemeral
      ? SecureStore.setItemAsync(ACCOUNT_TOKEN_EXPIRES_AT_KEY, String(normalized.accountTokenExpiresAt))
      : SecureStore.deleteItemAsync(ACCOUNT_TOKEN_EXPIRES_AT_KEY),
    SecureStore.setItemAsync(ACCOUNT_REMEMBER_ME_KEY, normalized.accountRememberMe ? '1' : '0'),
    accountTokenIsEphemeral
      ? SecureStore.deleteItemAsync(ACCOUNT_USER_ID_KEY)
      : SecureStore.setItemAsync(ACCOUNT_USER_ID_KEY, normalized.accountUserId),
    accountTokenIsEphemeral
      ? SecureStore.deleteItemAsync(ACCOUNT_EMAIL_KEY)
      : SecureStore.setItemAsync(ACCOUNT_EMAIL_KEY, normalized.accountEmail),
    accountTokenIsEphemeral
      ? SecureStore.deleteItemAsync(ACCOUNT_MOBILE_ID_KEY)
      : SecureStore.setItemAsync(ACCOUNT_MOBILE_ID_KEY, normalized.accountMobileId),
    SecureStore.setItemAsync(PAIRED_DESKTOP_ID_KEY, normalized.pairedDesktopId),
    SecureStore.setItemAsync(CONNECTION_MODE_KEY, normalized.connectionMode),
  ]);

  return normalized;
}

export async function clearRemoteAccountConfig(): Promise<AppConfig> {
  volatileAppConfig = null;
  return saveAppConfig({
    apiBaseUrl: DEFAULT_REMOTE_API_BASE_URL,
    accessToken: '',
    accountToken: '',
    accountTokenExpiresAt: null,
    accountRememberMe: false,
    accountUserId: '',
    accountEmail: '',
    accountMobileId: '',
    pairedDesktopId: '',
    connectionMode: 'remote_cloud',
  });
}
