import { useCallback, useRef, useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { InfoHint } from './InfoHint';
import { DESKTOP_UI as UI } from '../desktop/desktopUiTokens';

export type ConfirmationTone = 'normal' | 'danger' | 'access';

export type ConfirmationOptions = {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: ConfirmationTone;
  details?: string[];
};

type PendingConfirmation = ConfirmationOptions & {
  resolve: (confirmed: boolean) => void;
};

export function useConfirmation() {
  const [pending, setPending] = useState<PendingConfirmation | null>(null);
  const pendingRef = useRef<PendingConfirmation | null>(null);

  const close = useCallback((confirmed: boolean) => {
    const current = pendingRef.current;
    pendingRef.current = null;
    setPending(null);
    current?.resolve(confirmed);
  }, []);

  const confirm = useCallback((options: ConfirmationOptions) => {
    if (pendingRef.current) {
      pendingRef.current.resolve(false);
    }
    return new Promise<boolean>((resolve) => {
      const next = { ...options, resolve };
      pendingRef.current = next;
      setPending(next);
    });
  }, []);

  const confirmationDialog = pending ? (
    <ConfirmationDialog
      visible
      title={pending.title}
      message={pending.message}
      confirmLabel={pending.confirmLabel}
      cancelLabel={pending.cancelLabel}
      tone={pending.tone}
      details={pending.details}
      onCancel={() => close(false)}
      onConfirm={() => close(true)}
    />
  ) : null;

  return { confirm, confirmationDialog };
}

export function ConfirmationDialog({
  visible,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone = 'normal',
  details,
  onCancel,
  onConfirm,
}: ConfirmationOptions & {
  visible: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Modal transparent visible={visible} animationType="fade" onRequestClose={onCancel}>
      <View style={styles.overlay}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Cancel confirmation"
          style={styles.backdrop}
          onPress={onCancel}
        />
        <View
          accessibilityRole="alert"
          accessibilityLabel={title}
          style={[styles.card, tone === 'danger' ? styles.cardDanger : tone === 'access' ? styles.cardAccess : null]}
        >
          {tone !== 'normal' ? (
            <Text style={[styles.kicker, tone === 'danger' ? styles.kickerDanger : styles.kickerAccess]}>
              {tone === 'danger' ? 'Needs confirmation' : 'Access change'}
            </Text>
          ) : null}
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.message}>{message}</Text>
          {details?.length ? (
            <View style={styles.details}>
              <Text style={styles.detailLabel}>Details</Text>
              <InfoHint placement="top" text={details.join('\n')} />
            </View>
          ) : null}
          <View style={styles.actions}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={cancelLabel}
              style={styles.cancelButton}
              onPress={onCancel}
            >
              <Text style={styles.cancelText}>{cancelLabel}</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={confirmLabel}
              style={[styles.confirmButton, tone === 'danger' ? styles.confirmDanger : tone === 'access' ? styles.confirmAccess : null]}
              onPress={onConfirm}
            >
              <Text style={[styles.confirmText, tone === 'danger' ? styles.confirmDangerText : tone === 'access' ? styles.confirmAccessText : null]}>{confirmLabel}</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: UI.color.overlay,
    padding: 20,
  },
  backdrop: {
    ...StyleSheet.absoluteFillObject,
  },
  card: {
    width: '100%',
    maxWidth: 460,
    borderRadius: UI.radius.large,
    borderWidth: 1,
    borderColor: UI.color.borderStrong,
    backgroundColor: UI.color.surfaceRaised,
    padding: 20,
    gap: 10,
    ...UI.elevation.high,
  },
  cardDanger: {
    borderLeftWidth: 2,
    borderLeftColor: UI.color.danger,
  },
  cardAccess: {
    borderLeftWidth: 2,
    borderLeftColor: UI.color.warning,
  },
  kicker: {
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  kickerDanger: { color: UI.color.danger },
  kickerAccess: { color: UI.color.warning },
  title: {
    color: UI.color.text,
    fontSize: 20,
    fontWeight: '700',
  },
  message: {
    color: UI.color.textMuted,
    fontSize: 14,
    lineHeight: 21,
  },
  details: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderRadius: 8,
    backgroundColor: UI.color.surfaceMuted,
    paddingHorizontal: 10,
    paddingVertical: 8,
    gap: 10,
  },
  detailLabel: {
    color: UI.color.textMuted,
    fontSize: 12,
    fontWeight: '800',
  },
  actions: {
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'flex-end',
    paddingTop: 6,
  },
  cancelButton: {
    minHeight: 42,
    borderRadius: 8,
    backgroundColor: UI.color.surfaceMuted,
    justifyContent: 'center',
    paddingHorizontal: 14,
  },
  cancelText: {
    color: UI.color.text,
    fontWeight: '600',
  },
  confirmButton: {
    minHeight: 42,
    borderRadius: 8,
    justifyContent: 'center',
    backgroundColor: UI.color.accent,
    paddingHorizontal: 14,
  },
  confirmDanger: {
    backgroundColor: UI.color.danger,
  },
  confirmAccess: {
    backgroundColor: UI.color.warning,
  },
  confirmText: {
    color: UI.color.accentInk,
    fontWeight: '700',
  },
  confirmDangerText: { color: UI.color.text },
  confirmAccessText: {
    color: '#1a1204',
  },
});
