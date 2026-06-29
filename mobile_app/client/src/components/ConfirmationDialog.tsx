import { useCallback, useRef, useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { InfoHint } from './InfoHint';

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
          <Text style={styles.kicker}>
            {tone === 'danger' ? 'Needs confirmation' : tone === 'access' ? 'Access change' : 'Confirm action'}
          </Text>
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
              <Text style={[styles.confirmText, tone === 'access' ? styles.confirmAccessText : null]}>{confirmLabel}</Text>
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
    backgroundColor: 'rgba(3, 7, 18, 0.62)',
    padding: 20,
  },
  backdrop: {
    ...StyleSheet.absoluteFillObject,
  },
  card: {
    width: '100%',
    maxWidth: 460,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#2d4467',
    backgroundColor: '#0d1728',
    padding: 18,
    gap: 10,
  },
  cardDanger: {
    borderColor: '#8b2f49',
  },
  cardAccess: {
    borderColor: '#8a641d',
  },
  kicker: {
    color: '#7cc7ff',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  title: {
    color: '#ffffff',
    fontSize: 20,
    fontWeight: '900',
  },
  message: {
    color: '#cfddf5',
    fontSize: 14,
    lineHeight: 21,
  },
  details: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderRadius: 8,
    backgroundColor: '#101f35',
    paddingHorizontal: 10,
    paddingVertical: 8,
    gap: 10,
  },
  detailLabel: {
    color: '#aebfdb',
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
    borderWidth: 1,
    borderColor: '#2c3c5b',
    justifyContent: 'center',
    paddingHorizontal: 14,
  },
  cancelText: {
    color: '#d8e6ff',
    fontWeight: '900',
  },
  confirmButton: {
    minHeight: 42,
    borderRadius: 8,
    justifyContent: 'center',
    backgroundColor: '#2d77d5',
    paddingHorizontal: 14,
  },
  confirmDanger: {
    backgroundColor: '#8b2343',
  },
  confirmAccess: {
    backgroundColor: '#f5b841',
  },
  confirmText: {
    color: '#ffffff',
    fontWeight: '900',
  },
  confirmAccessText: {
    color: '#1a1204',
  },
});
