import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

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
        style={({ pressed, hovered }) => [
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
    borderWidth: 1,
    borderColor: '#385476',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#101b31',
  },
  buttonActive: {
    borderColor: '#7cc7ff',
    backgroundColor: '#162742',
  },
  buttonPressed: {
    transform: [{ scale: 0.96 }],
  },
  icon: {
    color: '#d9f6ff',
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
    borderColor: '#2e4568',
    backgroundColor: '#08111f',
    padding: 10,
  },
  bubbleBottom: {
    top: 30,
  },
  bubbleTop: {
    bottom: 30,
  },
  bubbleText: {
    color: '#c7d7ef',
    fontSize: 12,
    lineHeight: 17,
  },
});
