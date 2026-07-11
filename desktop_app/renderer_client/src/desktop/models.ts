export type DesktopMode = 'local' | 'remote';

export type RemotePreviewState = {
  state: 'planned' | 'offline' | 'connecting' | 'live';
  message: string;
  width?: number;
  height?: number;
  updatedAt?: string | null;
};

export type RemoteRuntimeSummary = {
  id: string;
  name: string;
  hostLabel: string;
  status: 'planned' | 'offline' | 'connected';
  detail: string;
  preview: RemotePreviewState;
  workerCount?: number;
  activeCount?: number;
  queuedCount?: number;
  latestReport?: string | null;
  workers?: Array<{
    id: string;
    name: string;
    status: string;
    activeTaskId?: string | null;
  }>;
};
