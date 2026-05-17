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
  bootstrap: () => ipcRenderer.invoke('emploai:bootstrap'),
  getRuntimeStatus: () => ipcRenderer.invoke('emploai:get-runtime-status'),
  runtime: {
    start: () => ipcRenderer.invoke('emploai:runtime:start'),
    stop: () => ipcRenderer.invoke('emploai:runtime:stop'),
  },
  setup: {
    save: (payload) => ipcRenderer.invoke('emploai:setup:save', payload),
    validateField: (payload) => ipcRenderer.invoke('emploai:setup:validate-field', payload),
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
  },
  onRuntimeEvent: (callback) => subscribe('emploai:runtime-event', callback),
});
