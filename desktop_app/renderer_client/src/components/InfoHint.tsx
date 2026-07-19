import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { DesktopPressableState } from '../lib/pressableState';
import { DESKTOP_UI as UI } from '../desktop/desktopUiTokens';

type InfoHintProps = {
  label?: string;
  placement?: 'bottom' | 'top';
  text: string;
  width?: number;
};

export function InfoHint({ label = 'More information', placement = 'bottom', text, width = 260 }: InfoHintProps) {
  const [visible, setVisible] = useState(false);

  return (
    <View style={styles.wrap}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={label}
        onHoverIn={() => setVisible(true)}
        onHoverOut={() => setVisible(false)}
        onPress={() => setVisible((current) => !current)}
        style={({ pressed, hovered }: DesktopPressableState) => [
          styles.button,
          hovered || visible ? styles.buttonActive : null,
          pressed ? styles.buttonPressed : null,
        ]}
      >
        <Text style={styles.icon}>i</Text>
      </Pressable>
      {visible ? (
        <View style={[styles.bubble, placement === 'top' ? styles.bubbleTop : styles.bubbleBottom, { width }]}>
          <Text style={styles.bubbleText}>{text}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'relative',
    alignSelf: 'flex-start',
  },
  button: {
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: UI.color.surfaceMuted,
  },
  buttonActive: {
    backgroundColor: UI.color.accentSoft,
  },
  buttonPressed: {
    transform: [{ scale: 0.96 }],
  },
  icon: {
    color: UI.color.textMuted,
    fontSize: 13,
    fontWeight: '900',
    lineHeight: 16,
  },
  bubble: {
    position: 'absolute',
    zIndex: 50,
    right: 0,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: UI.color.borderStrong,
    backgroundColor: UI.color.surfaceRaised,
    padding: 10,
    ...UI.elevation.high,
  },
  bubbleBottom: {
    top: 30,
  },
  bubbleTop: {
    bottom: 30,
  },
  bubbleText: {
    color: UI.color.textMuted,
    fontSize: 12,
    lineHeight: 17,
  },
});
