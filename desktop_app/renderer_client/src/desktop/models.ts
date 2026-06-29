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
};
