import { Pressable, StyleSheet, Text, View } from 'react-native';

import { DESKTOP_UI as UI } from './desktopUiTokens';

export function DesktopExitDialog({
  visible,
  busy,
  error,
  hasActiveWork,
  onChoice,
}: {
  visible: boolean;
  busy: boolean;
  error?: string | null;
  hasActiveWork: boolean;
  onChoice: (choice: 'keep_running' | 'stop_everything' | 'force' | 'cancel' | 'default') => void;
}) {
  if (!visible) return null;
  return (
    <View accessibilityViewIsModal style={styles.overlay}>
      <Pressable accessibilityLabel="Cancel exit" style={styles.backdrop} onPress={() => !busy && onChoice('cancel')} />
      <View accessibilityRole="alert" style={styles.dialog}>
        <Text style={styles.title}>{error ? 'EmploAI could not exit safely' : hasActiveWork ? 'Work is still running' : 'Exit EmploAI?'}</Text>
        <Text style={styles.body}>
          {error || (hasActiveWork
            ? 'Choose whether the local runtime should keep working, or stop all active Chat, Jarvis, Fleet, monitor, and command activity before the app closes.'
            : 'The local runtime will follow your current close preference.')}
        </Text>
        <View style={styles.actions}>
          {error ? (
            <Pressable accessibilityRole="button" disabled={busy} onPress={() => onChoice('force')} style={[styles.danger, busy ? styles.disabled : null]}>
              <Text style={styles.dangerText}>Force Exit</Text>
            </Pressable>
          ) : hasActiveWork ? (
            <>
              <Pressable accessibilityRole="button" disabled={busy} onPress={() => onChoice('keep_running')} style={[styles.secondary, busy ? styles.disabled : null]}>
                <Text style={styles.secondaryText}>Keep Running</Text>
              </Pressable>
              <Pressable accessibilityRole="button" disabled={busy} onPress={() => onChoice('stop_everything')} style={[styles.primary, busy ? styles.disabled : null]}>
                <Text style={styles.primaryText}>{busy ? 'Stopping…' : 'Stop Everything'}</Text>
              </Pressable>
            </>
          ) : (
            <Pressable accessibilityRole="button" disabled={busy} onPress={() => onChoice('default')} style={[styles.primary, busy ? styles.disabled : null]}>
              <Text style={styles.primaryText}>{busy ? 'Exiting…' : 'Exit'}</Text>
            </Pressable>
          )}
          <Pressable accessibilityRole="button" disabled={busy} onPress={() => onChoice('cancel')} style={[styles.cancel, busy ? styles.disabled : null]}>
            <Text style={styles.cancelText}>Cancel</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, zIndex: 1000, alignItems: 'center', justifyContent: 'center' },
  backdrop: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, backgroundColor: UI.color.overlay },
  dialog: { width: 520, maxWidth: '92%', borderRadius: UI.radius.large, borderWidth: 1, borderColor: UI.color.borderStrong, backgroundColor: UI.color.surfaceRaised, padding: 22, gap: 12, ...UI.elevation.high },
  title: { color: UI.color.text, fontSize: 20, fontWeight: '700', letterSpacing: -0.25 },
  body: { color: UI.color.textMuted, lineHeight: 21 },
  actions: { flexDirection: 'row', justifyContent: 'flex-end', flexWrap: 'wrap', gap: 9, marginTop: 6 },
  primary: { minHeight: 44, justifyContent: 'center', borderRadius: UI.radius.control, backgroundColor: UI.color.accent, paddingHorizontal: 16 },
  primaryText: { color: UI.color.accentInk, fontWeight: '700' },
  secondary: { minHeight: 44, justifyContent: 'center', borderRadius: UI.radius.control, borderWidth: 1, borderColor: UI.color.borderStrong, backgroundColor: UI.color.surfaceMuted, paddingHorizontal: 16 },
  secondaryText: { color: UI.color.text, fontWeight: '600' },
  danger: { minHeight: 44, justifyContent: 'center', borderRadius: UI.radius.control, backgroundColor: UI.color.danger, paddingHorizontal: 16 },
  dangerText: { color: UI.color.text, fontWeight: '700' },
  cancel: { minHeight: 44, justifyContent: 'center', borderRadius: UI.radius.control, paddingHorizontal: 14 },
  cancelText: { color: UI.color.textMuted, fontWeight: '600' },
  disabled: { opacity: 0.5 },
});
