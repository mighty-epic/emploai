import { Pressable, StyleSheet, Text, View } from 'react-native';

import { DESKTOP_UI as UI } from './desktopUiTokens';

export function DesktopArchiveUndoToast({ name, onUndo }: { name: string; onUndo: () => void }) {
  return (
    <View accessibilityLiveRegion="polite" style={styles.toast}>
      <Text style={styles.text} numberOfLines={1}>{name || 'Chat'} archived</Text>
      <Pressable accessibilityRole="button" accessibilityLabel="Undo archive chat" onPress={onUndo} style={styles.button}>
        <Text style={styles.buttonText}>Undo</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  toast: {
    position: 'absolute',
    left: 20,
    bottom: 18,
    zIndex: 80,
    maxWidth: 420,
    minHeight: 52,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    borderWidth: 1,
    borderColor: UI.color.borderStrong,
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surfaceRaised,
    paddingHorizontal: 14,
    ...UI.elevation.high,
  },
  text: { flexShrink: 1, color: UI.color.text, fontSize: 13, fontWeight: '600' },
  button: {
    minWidth: 64,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accent,
    paddingHorizontal: 12,
  },
  buttonText: { color: UI.color.accentInk, fontSize: 13, fontWeight: '700' },
});
