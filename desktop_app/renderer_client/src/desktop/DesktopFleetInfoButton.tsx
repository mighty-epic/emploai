import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { DESKTOP_UI as UI } from './desktopUiTokens';
import { FLEET_TYPE as TYPE } from './desktopFleetUi';

export function DesktopFleetInfoButton({
  label,
  text,
  align = 'right',
}: {
  label: string;
  text: string;
  align?: 'left' | 'right';
}) {
  const [pinned, setPinned] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const anchorRef = useRef<View>(null);
  const open = pinned || hovered || focused;

  useEffect(() => {
    if (!pinned || typeof document === 'undefined') return;
    const dismissOutside = (event: MouseEvent) => {
      const anchor = anchorRef.current as unknown as { contains?: (target: EventTarget | null) => boolean } | null;
      if (!anchor?.contains?.(event.target)) setPinned(false);
    };
    const dismissWithEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPinned(false);
    };
    document.addEventListener('mousedown', dismissOutside, true);
    document.addEventListener('keydown', dismissWithEscape, true);
    return () => {
      document.removeEventListener('mousedown', dismissOutside, true);
      document.removeEventListener('keydown', dismissWithEscape, true);
    };
  }, [pinned]);

  return (
    <View ref={anchorRef} style={styles.anchor}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`About ${label}`}
        accessibilityHint={text}
        accessibilityState={{ expanded: open }}
        onPress={() => setPinned((current) => !current)}
        onHoverIn={() => setHovered(true)}
        onHoverOut={() => setHovered(false)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        style={({ pressed }) => [styles.button, open ? styles.buttonOpen : null, pressed ? styles.buttonPressed : null]}
      >
        <View style={styles.iconCircle}>
          <Text style={styles.icon}>i</Text>
        </View>
      </Pressable>
      {open ? (
        <View
          accessibilityRole="summary"
          style={[styles.tooltip, align === 'left' ? styles.tooltipLeft : styles.tooltipRight]}
        >
          <Text style={styles.tooltipLabel}>{label}</Text>
          <Text style={styles.tooltipText}>{text}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  anchor: { position: 'relative', zIndex: 60, flexShrink: 0 },
  button: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center', borderRadius: UI.radius.control },
  buttonOpen: { backgroundColor: UI.color.accentSoft },
  buttonPressed: { opacity: 0.72 },
  iconCircle: { width: 24, height: 24, borderWidth: 1, borderColor: UI.color.borderStrong, borderRadius: UI.radius.pill, backgroundColor: UI.color.surfaceRaised, alignItems: 'center', justifyContent: 'center' },
  icon: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: 13, lineHeight: 15, fontWeight: '900' },
  tooltip: { position: 'absolute', top: 40, width: 300, maxWidth: 300, padding: 12, gap: 5, borderWidth: 1, borderColor: UI.color.accentBorder, borderRadius: UI.radius.control, backgroundColor: UI.color.surfaceRaised, shadowColor: UI.color.shadow, shadowOpacity: 0.42, shadowRadius: 18, shadowOffset: { width: 0, height: 10 }, elevation: 12 },
  tooltipRight: { right: 0 },
  tooltipLeft: { left: 0 },
  tooltipLabel: { color: UI.color.text, fontSize: TYPE.body, fontWeight: '900' },
  tooltipText: { color: UI.color.textMuted, fontSize: TYPE.body, lineHeight: TYPE.bodyLine },
});
