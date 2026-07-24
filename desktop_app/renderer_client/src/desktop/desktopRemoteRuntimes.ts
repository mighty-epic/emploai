import type { DesktopFleetSnapshot, DesktopFleetWorker } from '../lib/desktopBridge';
import type { RemoteRuntimeSummary } from './models';
import { fleetReportSummary } from './desktopFleetWorkerState';
import { fleetDirectChildDesktopIds } from './desktopFleetSnapshot';

function text(value: unknown) {
  return String(value || '').trim();
}

function formatLastSeen(value: unknown) {
  const raw = text(value);
  const timestamp = Date.parse(raw);
  if (!raw || !Number.isFinite(timestamp)) return '';
  const elapsedSeconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  if (elapsedSeconds < 15) return 'Last seen just now';
  if (elapsedSeconds < 60) return `Last seen ${elapsedSeconds}s ago`;
  const elapsedMinutes = Math.round(elapsedSeconds / 60);
  if (elapsedMinutes < 60) return `Last seen ${elapsedMinutes}m ago`;
  const elapsedHours = Math.round(elapsedMinutes / 60);
  if (elapsedHours < 24) return `Last seen ${elapsedHours}h ago`;
  return `Last seen ${new Date(timestamp).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })}`;
}

function machineName(worker: DesktopFleetWorker) {
  const metadata = worker.metadata || {};
  return text(metadata.machine_name || metadata.device_name || metadata.desktop_name) || 'Paired computer';
}

export function remoteRuntimesFromFleetSnapshot(
  fleet: DesktopFleetSnapshot | null | undefined,
): RemoteRuntimeSummary[] {
  if (!fleet) return [];

  const workers = Array.isArray(fleet.workers) ? fleet.workers : [];
  const tasks = Array.isArray(fleet.tasks) ? fleet.tasks : [];
  const reports = Array.isArray(fleet.reports) ? fleet.reports : [];
  const desktops = Array.isArray(fleet.desktops) ? fleet.desktops : [];
  const childDesktopIds = fleetDirectChildDesktopIds(fleet);
  const grouped = new Map<string, DesktopFleetWorker[]>();

  for (const worker of workers) {
    const desktopId = text(worker.machine_desktop_id);
    if (!desktopId || !childDesktopIds.includes(desktopId)) continue;
    const machineWorkers = grouped.get(desktopId) || [];
    machineWorkers.push(worker);
    grouped.set(desktopId, machineWorkers);
  }
  for (const desktopId of childDesktopIds) {
    if (!grouped.has(desktopId)) grouped.set(desktopId, []);
  }

  return Array.from(grouped.entries()).map(([desktopId, machineWorkers]) => {
    const desktop = desktops.find((item) => text(item.desktop_id) === desktopId);
    const workerIds = new Set(machineWorkers.map((worker) => worker.worker_id));
    const activeCount = tasks.filter((task) => workerIds.has(task.worker_id) && task.status === 'running').length;
    const queuedCount = tasks.filter((task) => workerIds.has(task.worker_id) && task.status === 'queued').length;
    const latestReport = reports.find((report) => workerIds.has(report.worker_id));
    const workerLastSeenAt = machineWorkers
      .map((worker) => text(worker.last_seen_at))
      .filter(Boolean)
      .sort()
      .at(-1) || '';
    const lastSeenAt = text(desktop?.last_heartbeat_at || desktop?.last_seen_at) || workerLastSeenAt;
    const desktopStatus = text(desktop?.status).toLowerCase();
    const connected = desktop
      ? desktopStatus === 'connected' || desktopStatus === 'online'
      : machineWorkers.some((worker) => !['offline', 'disconnected', 'stale'].includes(text(worker.status).toLowerCase()));

    return {
      id: desktopId,
      name: text(desktop?.display_name) || machineName(machineWorkers[0]),
      hostLabel: lastSeenAt ? formatLastSeen(lastSeenAt) : 'No heartbeat yet',
      status: connected ? 'connected' : 'offline',
      detail: `${machineWorkers.length} local agents visible here · ${activeCount} active · ${queuedCount} queued`,
      workerCount: machineWorkers.length,
      activeCount,
      queuedCount,
      latestReport: latestReport ? fleetReportSummary(latestReport) : null,
      workers: machineWorkers.map((worker) => ({
        id: worker.worker_id,
        name: worker.display_name,
        status: worker.status,
        activeTaskId: worker.active_task_id || null,
      })),
      preview: {
        state: 'offline',
        message: 'View-only preview has not been requested.',
        updatedAt: null,
      },
    };
  });
}
