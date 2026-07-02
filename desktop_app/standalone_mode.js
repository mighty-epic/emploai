const TRUTHY = new Set(['1', 'true', 'yes', 'on', 'enabled']);
const FALSY = new Set(['0', 'false', 'no', 'off', 'disabled']);

function envFlag(name) {
  if (!Object.prototype.hasOwnProperty.call(process.env, name)) {
    return null;
  }
  const value = String(process.env[name] || '').trim().toLowerCase();
  if (TRUTHY.has(value)) {
    return true;
  }
  if (FALSY.has(value)) {
    return false;
  }
  return null;
}

function cloudBackendEnabled() {
  const explicitCloud = envFlag('EMPLOAI_CLOUD_BACKEND_ENABLED');
  if (explicitCloud !== null) {
    return explicitCloud;
  }
  const explicitStandalone = envFlag('EMPLOAI_STANDALONE_DESKTOP');
  if (explicitStandalone !== null) {
    return !explicitStandalone;
  }
  return false;
}

function mobileConnectionEnabled() {
  const explicitMobile = envFlag('EMPLOAI_MOBILE_CONNECTION_ENABLED');
  if (explicitMobile !== null) {
    return explicitMobile;
  }
  return cloudBackendEnabled();
}

function standaloneDesktopEnabled() {
  const explicitStandalone = envFlag('EMPLOAI_STANDALONE_DESKTOP');
  if (explicitStandalone !== null) {
    return explicitStandalone;
  }
  return !cloudBackendEnabled();
}

module.exports = {
  cloudBackendEnabled,
  mobileConnectionEnabled,
  standaloneDesktopEnabled,
};
