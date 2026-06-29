import { fetchRemoteAccountProfile, type RemoteAccountProfile } from '../src/lib/appApi';
import { clearRemoteAccountConfig, type AppConfig, saveAppConfig } from './appConfig';

export type AccountConfigReconcileResult = {
  config: AppConfig;
  profile: RemoteAccountProfile | null;
  changed: boolean;
};

function isUnauthorizedError(error: unknown) {
  return error instanceof Error && /\b401\b|unauthorized|invalid token/i.test(error.message || '');
}

export async function reconcileRemoteAccountConfig(config: AppConfig): Promise<AccountConfigReconcileResult> {
  if (config.connectionMode !== 'remote_cloud') {
    return { config, profile: null, changed: false };
  }

  const token = (config.accountToken || config.accessToken || '').trim();
  if (!config.apiBaseUrl || !token) {
    const nextConfig = config.pairedDesktopId ? { ...config, pairedDesktopId: '' } : config;
    if (nextConfig !== config) {
      await saveAppConfig(nextConfig);
    }
    return { config: nextConfig, profile: null, changed: nextConfig !== config };
  }

  try {
    const profile = await fetchRemoteAccountProfile(config.apiBaseUrl, token);
    const pairedDesktopId = String(profile.mobile?.paired_desktop_id || '').trim();
    const nextConfig: AppConfig = {
      ...config,
      accessToken: token,
      accountToken: token,
      accountUserId: String(profile.user?.user_id || '').trim(),
      accountEmail: String(profile.user?.email || '').trim().toLowerCase(),
      accountMobileId: String(profile.mobile?.mobile_id || '').trim(),
      pairedDesktopId,
      connectionMode: 'remote_cloud',
    };
    const changed = (
      nextConfig.accessToken !== config.accessToken
      || nextConfig.accountToken !== config.accountToken
      || nextConfig.accountUserId !== config.accountUserId
      || nextConfig.accountEmail !== config.accountEmail
      || nextConfig.accountMobileId !== config.accountMobileId
      || nextConfig.pairedDesktopId !== config.pairedDesktopId
      || nextConfig.connectionMode !== config.connectionMode
    );
    if (changed) {
      await saveAppConfig(nextConfig);
    }
    return { config: nextConfig, profile, changed };
  } catch (error) {
    if (isUnauthorizedError(error)) {
      return { config: await clearRemoteAccountConfig(), profile: null, changed: true };
    }
    throw error;
  }
}
