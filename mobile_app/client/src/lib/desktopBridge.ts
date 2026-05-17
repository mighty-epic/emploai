export type DesktopRuntimeStatus = {
  ok: boolean;
  state: string;
  mode: string;
  api_base_url?: string;
  apiBaseUrl?: string;
  startup_state?: string | null;
  degraded?: boolean;
  issues?: string[] | null;
  detail?: string | null;
  process_id?: number | null;
  processId?: number | null;
};

export type DesktopSetupValues = {
  TELEGRAM_BOT_TOKEN: string;
  ALLOWED_USER_IDS: string;
  DEFAULT_WORKSPACE: string;
  PLANNER_MODEL: string;
  INTERRUPT_POLICY_DEFAULT: string;
  OPENAI_API_KEY: string;
  ANTHROPIC_API_KEY: string;
  GOOGLE_API_KEY: string;
  XAI_API_KEY: string;
  DEEPSEEK_API_KEY: string;
  OPENROUTER_API_KEY: string;
  VOICE_DEFAULT_ENGINE: string;
  VOICE_ENGLISH_REQUESTED: string;
  VOICE_HEBREW_REQUESTED: string;
};

export type DesktopVoiceRuntimeStatus = {
  ok?: boolean;
  input_ok?: boolean;
  issues?: string[];
  stt_backend?: string | null;
  stt_model?: string | null;
  draft_model?: string | null;
  binary_flavor?: string | null;
  tts_enabled?: boolean;
  selected_engine?: string | null;
  english_requested?: boolean;
  hebrew_requested?: boolean;
  english_pack_ready?: boolean;
  hebrew_pack_ready?: boolean;
};

export type DesktopVoicePackSummary = {
  id: string;
  title: string;
  description: string;
  requested: boolean;
  installed: boolean;
  available: boolean;
  enabled: boolean;
  placeholder: boolean;
  supportsAlwaysOn: boolean;
  status: string;
  removable?: boolean;
  source?: string;
  path?: string | null;
  issues?: string[];
};

export type DesktopVoicePackState = {
  defaultEngine: string;
  selectionSource: string;
  packs: DesktopVoicePackSummary[];
};

export type DesktopSetupState = {
  required: boolean;
  versioned: boolean;
  releaseVersion: string;
  runtimeHome: string;
  envFilePath: string;
  extensionPath: string;
  extensionGuidePath: string;
  values: DesktopSetupValues;
  validationIssues: string[];
  configuredProviders: string[];
  telegramConfigured: boolean;
  telegramPartiallyConfigured: boolean;
  ocrAvailable: boolean;
  ocrSource?: string | null;
  voiceAvailable: boolean;
  voiceStatus?: DesktopVoiceRuntimeStatus | null;
  voicePacks?: DesktopVoicePackState | null;
};

export type DesktopMemoryState = {
  ok: boolean;
  exists: boolean;
  memoryFilePath: string;
  memoryDirPath: string;
  content: string;
  dailyLogCount: number;
  oldestLog?: string | null;
  newestLog?: string | null;
};

export type DesktopUpdateStatus = {
  ok: boolean;
  currentVersion: string;
  releaseTag: string;
  channel: string;
  repo: string;
  intervalHours: number;
  checked: boolean;
  updateAvailable: boolean;
  update?: {
    version: string;
    tagName: string;
    assetName: string;
    assetUrl: string;
    publishedAt?: string | null;
  } | null;
  lastCheckedAt?: string | null;
  lastError?: string | null;
};

export type DesktopBootstrap = {
  ok: boolean;
  apiBaseUrl: string;
  accessToken: string;
  currentSessionId?: string | null;
  runtimeMode: string;
  runtimeStatus?: DesktopRuntimeStatus | null;
  deviceId?: string | null;
  userId?: number | null;
  runtimeAvailable?: boolean;
  canLaunchLocalRuntime?: boolean;
  runtimeProcessDetected?: boolean;
  workspaceRoot?: string | null;
  runtimeHome?: string | null;
  envFilePath?: string | null;
  desktopLogPath?: string | null;
  releaseVersion?: string | null;
  setupState?: DesktopSetupState | null;
};

export type DesktopSetupFieldValidation = {
  field: keyof DesktopSetupValues | string;
  status: 'idle' | 'checking' | 'valid' | 'invalid' | 'error';
  message: string;
};

export type DesktopBridgeEvent = {
  type: string;
  payload?: Record<string, any>;
  runtimeMode?: string;
  runtimeStatus?: DesktopRuntimeStatus | null;
  currentSessionId?: string | null;
};

export type DesktopSidebarProjectActivity = {
  id: string;
  message: string;
  timestamp: string;
  sessionId?: string | null;
  relatedProjectPath?: string | null;
};

export type DesktopSidebarProjectState = {
  pinned?: boolean;
  collapsed?: boolean;
  displayName?: string | null;
  hidden?: boolean;
  recentActivity?: DesktopSidebarProjectActivity[];
};

export type DesktopSidebarSessionState = {
  pinned?: boolean;
  order?: number | null;
};

export type DesktopSidebarState = {
  version: number;
  projectOrder: string[];
  projects: Record<string, DesktopSidebarProjectState>;
  sessionMeta: Record<string, DesktopSidebarSessionState>;
  selectedProjectPath?: string | null;
  lastSelectedProjectPath?: string | null;
};

type DesktopBridge = {
  bootstrap: () => Promise<DesktopBootstrap>;
  getRuntimeStatus: () => Promise<DesktopRuntimeStatus>;
  runtime?: {
    start: () => Promise<DesktopBootstrap>;
    stop: () => Promise<DesktopBootstrap>;
  };
  setup?: {
    save: (payload: { values: Partial<DesktopSetupValues> }) => Promise<DesktopBootstrap>;
    validateField: (payload: { field: keyof DesktopSetupValues | string; value: string }) => Promise<DesktopSetupFieldValidation>;
  };
  voicePacks?: {
    install: (packId: string) => Promise<DesktopBootstrap>;
    remove: (packId: string) => Promise<DesktopBootstrap>;
    setDefaultEngine: (engine: string) => Promise<DesktopBootstrap>;
  };
  updates?: {
    check: (payload?: { force?: boolean }) => Promise<DesktopUpdateStatus>;
    install: () => Promise<Record<string, any>>;
  };
  shell?: {
    openPath: (targetPath: string) => Promise<string>;
    openChromeExtensions: () => Promise<string>;
  };
  clipboard?: {
    writeText: (textValue: string) => Promise<Record<string, any>>;
  };
  memory?: {
    read: () => Promise<DesktopMemoryState>;
    write: (payload: { content: string }) => Promise<DesktopMemoryState>;
  };
  sidebar?: {
    readState: () => Promise<DesktopSidebarState | null>;
    writeState: (payload: { state: DesktopSidebarState | null }) => Promise<DesktopSidebarState | null>;
    pickFolder: (payload?: { defaultPath?: string | null }) => Promise<string | null>;
  };
  onRuntimeEvent: (callback: (event: DesktopBridgeEvent) => void) => () => void;
};

declare global {
  interface Window {
    emploaiDesktop?: DesktopBridge;
  }
}

let bootstrapPromise: Promise<DesktopBootstrap> | null = null;

export function getDesktopBridge(): DesktopBridge | undefined {
  if (typeof window === 'undefined') {
    return undefined;
  }
  return window.emploaiDesktop;
}

export function isDesktopEnvironment() {
  return Boolean(getDesktopBridge());
}

export async function loadDesktopBootstrap(options?: { force?: boolean }) {
  const bridge = getDesktopBridge();
  if (!bridge) {
    return null;
  }
  if (options?.force) {
    bootstrapPromise = null;
  }
  if (!bootstrapPromise) {
    bootstrapPromise = bridge.bootstrap();
  }
  return bootstrapPromise;
}

export async function startDesktopRuntime() {
  const bridge = getDesktopBridge();
  if (!bridge?.runtime?.start) {
    return null;
  }
  const payload = await bridge.runtime.start();
  bootstrapPromise = Promise.resolve(payload);
  return payload;
}

export async function stopDesktopRuntime() {
  const bridge = getDesktopBridge();
  if (!bridge?.runtime?.stop) {
    return null;
  }
  const payload = await bridge.runtime.stop();
  bootstrapPromise = Promise.resolve(payload);
  return payload;
}

export async function saveDesktopSetup(values: Partial<DesktopSetupValues>) {
  const bridge = getDesktopBridge();
  if (!bridge?.setup?.save) {
    return null;
  }
  const payload = await bridge.setup.save({ values });
  bootstrapPromise = Promise.resolve(payload);
  return payload;
}

export async function validateDesktopSetupField(field: keyof DesktopSetupValues | string, value: string) {
  const bridge = getDesktopBridge();
  if (!bridge?.setup?.validateField) {
    return null;
  }
  return bridge.setup.validateField({ field, value });
}

export async function installDesktopVoicePack(packId: string) {
  const bridge = getDesktopBridge();
  if (!bridge?.voicePacks?.install) {
    return null;
  }
  const payload = await bridge.voicePacks.install(packId);
  bootstrapPromise = Promise.resolve(payload);
  return payload;
}

export async function removeDesktopVoicePack(packId: string) {
  const bridge = getDesktopBridge();
  if (!bridge?.voicePacks?.remove) {
    return null;
  }
  const payload = await bridge.voicePacks.remove(packId);
  bootstrapPromise = Promise.resolve(payload);
  return payload;
}

export async function setDesktopVoiceDefaultEngine(engine: string) {
  const bridge = getDesktopBridge();
  if (!bridge?.voicePacks?.setDefaultEngine) {
    return null;
  }
  const payload = await bridge.voicePacks.setDefaultEngine(engine);
  bootstrapPromise = Promise.resolve(payload);
  return payload;
}

export async function loadDesktopRuntimeStatus() {
  const bridge = getDesktopBridge();
  if (!bridge) {
    return null;
  }
  return bridge.getRuntimeStatus();
}

export function subscribeDesktopRuntime(callback: (event: DesktopBridgeEvent) => void) {
  const bridge = getDesktopBridge();
  if (!bridge) {
    return () => {};
  }
  return bridge.onRuntimeEvent(callback);
}

export async function checkDesktopUpdates(options?: { force?: boolean }) {
  const bridge = getDesktopBridge();
  if (!bridge?.updates?.check) {
    return null;
  }
  return bridge.updates.check(options);
}

export async function installDesktopUpdate() {
  const bridge = getDesktopBridge();
  if (!bridge?.updates?.install) {
    return null;
  }
  return bridge.updates.install();
}

export async function openDesktopPath(targetPath: string) {
  const bridge = getDesktopBridge();
  if (!bridge?.shell?.openPath) {
    return null;
  }
  return bridge.shell.openPath(targetPath);
}

export async function openDesktopChromeExtensions() {
  const bridge = getDesktopBridge();
  if (!bridge?.shell?.openChromeExtensions) {
    return null;
  }
  return bridge.shell.openChromeExtensions();
}

export async function copyDesktopText(textValue: string) {
  const bridge = getDesktopBridge();
  if (!bridge?.clipboard?.writeText) {
    return null;
  }
  return bridge.clipboard.writeText(textValue);
}

export async function loadDesktopMemory() {
  const bridge = getDesktopBridge();
  if (!bridge?.memory?.read) {
    return null;
  }
  return bridge.memory.read();
}

export async function saveDesktopMemory(content: string) {
  const bridge = getDesktopBridge();
  if (!bridge?.memory?.write) {
    return null;
  }
  return bridge.memory.write({ content });
}

export async function loadDesktopSidebarState() {
  const bridge = getDesktopBridge();
  if (!bridge?.sidebar?.readState) {
    return null;
  }
  return bridge.sidebar.readState();
}

export async function saveDesktopSidebarState(state: DesktopSidebarState | null) {
  const bridge = getDesktopBridge();
  if (!bridge?.sidebar?.writeState) {
    return null;
  }
  return bridge.sidebar.writeState({ state });
}

export async function pickDesktopFolder(defaultPath?: string | null) {
  const bridge = getDesktopBridge();
  if (!bridge?.sidebar?.pickFolder) {
    return null;
  }
  return bridge.sidebar.pickFolder({ defaultPath: defaultPath || null });
}
