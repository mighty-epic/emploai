const { contextBridge, ipcRenderer } = require('electron');

function subscribe(channel, callback) {
  const listener = (_event, payload) => {
    callback(payload);
  };
  ipcRenderer.on(channel, listener);
  return () => {
    ipcRenderer.removeListener(channel, listener);
  };
}

contextBridge.exposeInMainWorld('emploaiDesktop', {
  bootstrap: (payload) => ipcRenderer.invoke('emploai:bootstrap', payload),
  getRuntimeStatus: () => ipcRenderer.invoke('emploai:get-runtime-status'),
  runtime: {
    start: (payload) => ipcRenderer.invoke('emploai:runtime:start', payload),
    stop: () => ipcRenderer.invoke('emploai:runtime:stop'),
  },
  setup: {
    save: (payload) => ipcRenderer.invoke('emploai:setup:save', payload),
    validateField: (payload) => ipcRenderer.invoke('emploai:setup:validate-field', payload),
  },
  remoteAuth: {
    status: () => ipcRenderer.invoke('emploai:remote-auth:status'),
    login: (payload) => ipcRenderer.invoke('emploai:remote-auth:login', payload),
    googleLogin: (payload) => ipcRenderer.invoke('emploai:remote-auth:google-login', payload),
    register: (payload) => ipcRenderer.invoke('emploai:remote-auth:register', payload),
    verifyOtp: (payload) => ipcRenderer.invoke('emploai:remote-auth:otp-verify', payload),
    resendOtp: (payload) => ipcRenderer.invoke('emploai:remote-auth:otp-resend', payload),
    logout: () => ipcRenderer.invoke('emploai:remote-auth:logout'),
    createPairingToken: () => ipcRenderer.invoke('emploai:remote-auth:create-pairing-token'),
    listSecrets: (payload) => ipcRenderer.invoke('emploai:remote-auth:list-secrets', payload),
    saveSetupSecrets: (payload) => ipcRenderer.invoke('emploai:remote-auth:save-setup-secrets', payload),
    saveSecrets: (payload) => ipcRenderer.invoke('emploai:remote-auth:save-secrets', payload),
    applyAccountData: () => ipcRenderer.invoke('emploai:remote-auth:apply-account-data'),
    deleteSecret: (payload) => ipcRenderer.invoke('emploai:remote-auth:delete-secret', payload),
    deleteAccountData: (payload) => ipcRenderer.invoke('emploai:remote-auth:delete-account-data', payload),
    profile: () => ipcRenderer.invoke('emploai:remote-auth:profile'),
    updateProfile: (payload) => ipcRenderer.invoke('emploai:remote-auth:update-profile', payload),
    applySetupSecrets: (payload) => ipcRenderer.invoke('emploai:remote-auth:apply-setup-secrets', payload),
  },
  fleet: {
    snapshot: () => ipcRenderer.invoke('emploai:fleet:snapshot'),
    setActiveIdentity: (payload) => ipcRenderer.invoke('emploai:fleet:set-active-identity', payload),
    setIdentityActiveChat: (payload) => ipcRenderer.invoke('emploai:fleet:set-identity-active-chat', payload),
    createLocalWorker: (payload) => ipcRenderer.invoke('emploai:fleet:create-local-worker', payload),
    createEnrollment: (payload) => ipcRenderer.invoke('emploai:fleet:create-enrollment', payload),
    renameWorker: (payload) => ipcRenderer.invoke('emploai:fleet:rename-worker', payload),
    resetWorker: (payload) => ipcRenderer.invoke('emploai:fleet:reset-worker', payload),
    deleteWorker: (payload) => ipcRenderer.invoke('emploai:fleet:delete-worker', payload),
    stopWorker: (payload) => ipcRenderer.invoke('emploai:fleet:stop-worker', payload),
    stopAll: (payload) => ipcRenderer.invoke('emploai:fleet:stop-all', payload),
    requestWorkerPreview: (payload) => ipcRenderer.invoke('emploai:fleet:request-worker-preview', payload),
    createGroup: (payload) => ipcRenderer.invoke('emploai:fleet:create-group', payload),
    updateGroup: (payload) => ipcRenderer.invoke('emploai:fleet:update-group', payload),
    deleteGroup: (payload) => ipcRenderer.invoke('emploai:fleet:delete-group', payload),
    assignTask: (payload) => ipcRenderer.invoke('emploai:fleet:assign-task', payload),
    assignGroupTask: (payload) => ipcRenderer.invoke('emploai:fleet:assign-group-task', payload),
    continueWorkerQueue: (payload) => ipcRenderer.invoke('emploai:fleet:continue-worker-queue', payload),
    reorderTasks: (payload) => ipcRenderer.invoke('emploai:fleet:reorder-tasks', payload),
    redirectTask: (payload) => ipcRenderer.invoke('emploai:fleet:redirect-task', payload),
    updateTaskStatus: (payload) => ipcRenderer.invoke('emploai:fleet:update-task-status', payload),
    createTaskReport: (payload) => ipcRenderer.invoke('emploai:fleet:create-task-report', payload),
    searchReports: (payload) => ipcRenderer.invoke('emploai:fleet:search-reports', payload),
    upsertWorkspaceBinding: (payload) => ipcRenderer.invoke('emploai:fleet:upsert-workspace-binding', payload),
    requestToolGrant: (payload) => ipcRenderer.invoke('emploai:fleet:request-tool-grant', payload),
    decideToolGrant: (payload) => ipcRenderer.invoke('emploai:fleet:decide-tool-grant', payload),
  },
  voicePacks: {
    install: (packId) => ipcRenderer.invoke('emploai:voice-packs:install', packId),
    remove: (packId) => ipcRenderer.invoke('emploai:voice-packs:remove', packId),
    setDefaultEngine: (engine) => ipcRenderer.invoke('emploai:voice-packs:set-default-engine', engine),
  },
  updates: {
    check: (payload) => ipcRenderer.invoke('emploai:updates:check', payload),
    install: () => ipcRenderer.invoke('emploai:updates:install'),
  },
  shell: {
    openPath: (targetPath) => ipcRenderer.invoke('emploai:shell:open-path', targetPath),
    openChromeExtensions: () => ipcRenderer.invoke('emploai:shell:open-chrome-extensions'),
  },
  clipboard: {
    writeText: (textValue) => ipcRenderer.invoke('emploai:clipboard:write-text', textValue),
  },
  memory: {
    read: () => ipcRenderer.invoke('emploai:memory:read'),
    write: (payload) => ipcRenderer.invoke('emploai:memory:write', payload),
  },
  sidebar: {
    readState: () => ipcRenderer.invoke('emploai:sidebar:read-state'),
    writeState: (payload) => ipcRenderer.invoke('emploai:sidebar:write-state', payload),
    pickFolder: (payload) => ipcRenderer.invoke('emploai:sidebar:pick-folder', payload),
    createFolder: (payload) => ipcRenderer.invoke('emploai:sidebar:create-folder', payload),
    pathStatus: (payload) => ipcRenderer.invoke('emploai:sidebar:path-status', payload),
    gitRepoInfo: (payload) => ipcRenderer.invoke('emploai:sidebar:git-repo-info', payload),
    checkoutBranch: (payload) => ipcRenderer.invoke('emploai:sidebar:checkout-branch', payload),
  },
  window: {
    hideForSleepMode: () => ipcRenderer.invoke('emploai:window:sleep-hide'),
  },
  onRuntimeEvent: (callback) => subscribe('emploai:runtime-event', callback),
});
