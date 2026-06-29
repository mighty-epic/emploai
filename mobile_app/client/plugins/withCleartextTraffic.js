const { AndroidConfig, withAndroidManifest } = require('@expo/config-plugins');

module.exports = function withCleartextTraffic(config, props = {}) {
  return withAndroidManifest(config, (nextConfig) => {
    const app = AndroidConfig.Manifest.getMainApplicationOrThrow(nextConfig.modResults);
    const envValue = String(process.env.KRAITOS_ALLOW_CLEARTEXT || '').trim().toLowerCase();
    const enabled = typeof props.enabled === 'boolean'
      ? props.enabled
      : ['1', 'true', 'yes', 'on'].includes(envValue);
    app.$['android:usesCleartextTraffic'] = enabled ? 'true' : 'false';
    return nextConfig;
  });
};
