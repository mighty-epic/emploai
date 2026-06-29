import {
  approvePendingConfirmation,
  createPendingConfirmation,
  type ConfirmationCreatePayload,
} from './appApi';

export type LocalConfirm = (options: {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: 'danger' | 'access' | 'normal';
  details?: string[];
}) => Promise<boolean>;

export async function createApprovedConfirmation(
  apiBaseUrl: string,
  token: string,
  localConfirm: LocalConfirm,
  payload: ConfirmationCreatePayload,
  options?: {
    confirmLabel?: string;
    cancelLabel?: string;
    tone?: 'danger' | 'access' | 'normal';
    details?: string[];
    decidedBySurface?: string;
  },
) {
  const ok = await localConfirm({
    title: payload.title,
    message: payload.message,
    confirmLabel: options?.confirmLabel,
    cancelLabel: options?.cancelLabel,
    tone: options?.tone,
    details: options?.details,
  });
  if (!ok) {
    return null;
  }
  const confirmation = await createPendingConfirmation(apiBaseUrl, token, payload);
  const approved = await approvePendingConfirmation(
    apiBaseUrl,
    token,
    confirmation.confirmation_id,
    options?.decidedBySurface || payload.origin_surface || 'app',
  );
  return approved.confirmation_id;
}
