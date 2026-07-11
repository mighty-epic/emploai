function cloudBackendEnabled() {
  return false;
}

function mobileConnectionEnabled() {
  return false;
}

function standaloneDesktopEnabled() {
  return true;
}

module.exports = {
  cloudBackendEnabled,
  mobileConnectionEnabled,
  standaloneDesktopEnabled,
};
