import type { DesktopFleetSnapshot, DesktopFleetWorker } from '../lib/desktopBridge';
import type { RemoteRuntimeSummary } from './models';

function text(value: unknown) {
  return String(value || '').trim();
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
  const manager = fleet.manager && typeof fleet.manager === 'object' ? fleet.manager : null;
  const managerDesktopId = text(manager?.desktop_id);
  const grouped = new Map<string, DesktopFleetWorker[]>();

  for (const worker of workers) {
    const desktopId = text(worker.machine_desktop_id);
    if (!desktopId) continue;
    const machineWorkers = grouped.get(desktopId) || [];
    machineWorkers.push(worker);
    grouped.set(desktopId, machineWorkers);
  }
  if (managerDesktopId && !grouped.has(managerDesktopId)) {
    grouped.set(managerDesktopId, []);
  }

  return Array.from(grouped.entries()).map(([desktopId, machineWorkers]) => {
    const workerIds = new Set(machineWorkers.map((worker) => worker.worker_id));
    const activeCount = tasks.filter((task) => workerIds.has(task.worker_id) && task.status === 'running').length;
    const queuedCount = tasks.filter((task) => workerIds.has(task.worker_id) && task.status === 'queued').length;
    const latestReport = reports.find((report) => workerIds.has(report.worker_id));
    const lastSeenAt = machineWorkers
      .map((worker) => text(worker.last_seen_at))
      .filter(Boolean)
      .sort()
      .at(-1) || '';
    const isManager = desktopId === managerDesktopId;
    const connected = isManager || machineWorkers.some((worker) => !['offline', 'disconnected'].includes(text(worker.status).toLowerCase()));

    return {
      id: desktopId,
      name: isManager ? text(manager?.display_name) || 'This computer' : machineName(machineWorkers[0]),
      hostLabel: lastSeenAt ? `Last seen ${lastSeenAt}` : isManager ? 'Local manager' : 'No heartbeat yet',
      status: connected ? 'connected' : 'offline',
      detail: `${machineWorkers.length} workers · ${activeCount} active · ${queuedCount} queued`,
      workerCount: machineWorkers.length,
      activeCount,
      queuedCount,
      latestReport: latestReport?.summary || null,
      workers: machineWorkers.map((worker) => ({
        id: worker.worker_id,
        name: worker.display_name,
        status: worker.status,
        activeTaskId: worker.active_task_id || null,
      })),
      preview: {
        state: connected ? 'connecting' : 'offline',
        message: connected ? 'Manual view-only previews are requested from a worker.' : 'Computer is offline.',
        updatedAt: null,
      },
    };
  });
}
