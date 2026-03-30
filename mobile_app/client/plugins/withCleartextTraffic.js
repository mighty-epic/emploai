const { AndroidConfig, withAndroidManifest } = require('@expo/config-plugins');

module.exports = function withCleartextTraffic(config) {
  return withAndroidManifest(config, (nextConfig) => {
    const app = AndroidConfig.Manifest.getMainApplicationOrThrow(nextConfig.modResults);
    app.$['android:usesCleartextTraffic'] = 'true';
    return nextConfig;
  });
};
