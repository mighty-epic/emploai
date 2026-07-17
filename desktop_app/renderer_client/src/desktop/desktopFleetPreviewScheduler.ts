import {
  requestDesktopFleetComputerPreview,
  type DesktopFleetPreviewResult,
  type DesktopFleetSnapshot,
} from '@/lib/desktopBridge';
import { userFacingError } from '../../lib/diagnostics';
import { remoteRuntimesFromFleetSnapshot } from './desktopRemoteRuntimes';

export const FLEET_PREVIEW_ACTIVE_INTERVAL_MS = 10_000;
export const FLEET_PREVIEW_BACKGROUND_INTERVAL_MS = 120_000;

export type DesktopFleetPreviewState = {
  preview: DesktopFleetPreviewResult | null;
  latestResult: DesktopFleetPreviewResult | null;
  loading: boolean;
  error: string | null;
};

type PreviewTarget = {
  desktopId: string;
  desktopName: string;
  online: boolean;
};

const EMPTY_STATE: DesktopFleetPreviewState = Object.freeze({
  preview: null,
  latestResult: null,
  loading: false,
  error: null,
});

const states = new Map<string, DesktopFleetPreviewState>();
const listeners = new Map<string, Set<() => void>>();
const inFlight = new Map<string, number>();
const automaticCaptureBlocked = new Set<string>();

let targets = new Map<string, PreviewTarget>();
let fleetActive = false;
let intervalId: ReturnType<typeof globalThis.setInterval> | null = null;
let intervalMs: number | null = null;
let requestSequence = 0;

function text(value: unknown) {
  return String(value || '').trim();
}

function emit(desktopId: string) {
  for (const listener of listeners.get(desktopId) || []) listener();
}

function updateState(
  desktopId: string,
  update: (current: DesktopFleetPreviewState) => DesktopFleetPreviewState,
) {
  states.set(desktopId, update(states.get(desktopId) || EMPTY_STATE));
  emit(desktopId);
}

export function fleetPreviewTargets(snapshot: DesktopFleetSnapshot | null | undefined): PreviewTarget[] {
  if (!snapshot) return [];
  const localDesktopId = text(snapshot.manager?.desktop_id);
  const pairedIds = new Set(
    (snapshot.connection_permissions || [])
      .filter((permission) => text(permission.source).toLowerCase() === 'paired_desktop')
      .map((permission) => text(permission.desktop_id))
      .filter((desktopId) => desktopId && desktopId !== localDesktopId),
  );

  return remoteRuntimesFromFleetSnapshot(snapshot)
    .filter((runtime) => pairedIds.has(runtime.id))
    .map((runtime) => ({
      desktopId: runtime.id,
      desktopName: runtime.name,
      online: runtime.status === 'connected',
    }));
}

export function getDesktopFleetPreviewState(desktopId: string): DesktopFleetPreviewState {
  return states.get(desktopId) || EMPTY_STATE;
}

export function subscribeDesktopFleetPreview(desktopId: string, listener: () => void) {
  const desktopListeners = listeners.get(desktopId) || new Set<() => void>();
  desktopListeners.add(listener);
  listeners.set(desktopId, desktopListeners);
  return () => {
    desktopListeners.delete(listener);
    if (!desktopListeners.size) listeners.delete(desktopId);
  };
}

export async function captureDesktopFleetPreview(
  desktopId: string,
  desktopName?: string,
  options: { automatic?: boolean } = {},
) {
  if (
    !desktopId
    || inFlight.has(desktopId)
    || (options.automatic && automaticCaptureBlocked.has(desktopId))
  ) return;
  const name = desktopName || targets.get(desktopId)?.desktopName || 'the connected computer';
  const requestId = ++requestSequence;
  inFlight.set(desktopId, requestId);
  updateState(desktopId, (current) => ({ ...current, loading: true, error: null }));
  try {
    const result = await requestDesktopFleetComputerPreview(desktopId);
    if (inFlight.get(desktopId) !== requestId) return;
    if (!result) throw new Error('Desktop preview controls are unavailable in this shell.');
    const captured = result.dispatch_status === 'captured' && Boolean(result.capture?.image_base64);
    if (!captured) {
      if (result.capture_capability?.available === false) {
        automaticCaptureBlocked.add(desktopId);
      }
      updateState(desktopId, (current) => ({
        ...current,
        latestResult: result,
        loading: false,
        error: result.detail || 'This computer did not return a preview.',
      }));
      return;
    }
    automaticCaptureBlocked.delete(desktopId);
    updateState(desktopId, (current) => ({
      ...current,
      preview: result,
      latestResult: result,
      loading: false,
      error: null,
    }));
  } catch (captureError) {
    if (inFlight.get(desktopId) !== requestId) return;
    updateState(desktopId, (current) => ({
      ...current,
      loading: false,
      error: userFacingError(captureError, `Could not capture ${name}.`),
    }));
  } finally {
    if (inFlight.get(desktopId) === requestId) inFlight.delete(desktopId);
  }
}

function captureConnectedTargets() {
  for (const target of targets.values()) {
    if (target.online) {
      void captureDesktopFleetPreview(target.desktopId, target.desktopName, { automatic: true });
    }
  }
}

function replaceInterval(nextIntervalMs: number | null) {
  if (intervalId !== null) globalThis.clearInterval(intervalId);
  intervalId = null;
  intervalMs = nextIntervalMs;
  if (nextIntervalMs === null) return;
  intervalId = globalThis.setInterval(captureConnectedTargets, nextIntervalMs);
}

export function configureDesktopFleetPreviewScheduler(
  snapshot: DesktopFleetSnapshot | null | undefined,
  active: boolean,
) {
  const nextTargets = new Map(
    fleetPreviewTargets(snapshot).map((target) => [target.desktopId, target]),
  );
  const previouslyConnected = new Set(
    Array.from(targets.values()).filter((target) => target.online).map((target) => target.desktopId),
  );
  const nextConnected = Array.from(nextTargets.values()).filter((target) => target.online);
  const cadence = nextConnected.length
    ? (active ? FLEET_PREVIEW_ACTIVE_INTERVAL_MS : FLEET_PREVIEW_BACKGROUND_INTERVAL_MS)
    : null;
  const cadenceChanged = cadence !== intervalMs;
  const becameFleetActive = active && !fleetActive;

  for (const desktopId of states.keys()) {
    if (!nextTargets.has(desktopId)) {
      states.delete(desktopId);
      automaticCaptureBlocked.delete(desktopId);
      emit(desktopId);
    }
  }
  targets = nextTargets;
  fleetActive = active;

  if (cadenceChanged) replaceInterval(cadence);
  if (becameFleetActive) {
    captureConnectedTargets();
    return;
  }
  for (const target of nextConnected) {
    if (!previouslyConnected.has(target.desktopId)) {
      automaticCaptureBlocked.delete(target.desktopId);
      void captureDesktopFleetPreview(target.desktopId, target.desktopName);
    }
  }
}

export function stopDesktopFleetPreviewScheduler() {
  replaceInterval(null);
  targets = new Map();
  fleetActive = false;
  inFlight.clear();
  automaticCaptureBlocked.clear();
  states.clear();
  for (const desktopListeners of listeners.values()) {
    for (const listener of desktopListeners) listener();
  }
}
