import { useEffect, useRef, useState } from 'react';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';

import { DESKTOP_UI as UI } from './desktopUiTokens';

type MenuName = 'File' | 'Edit' | 'View' | 'Help';
type MenuItem = {
  id: string;
  label: string;
  shortcut?: string;
  disabled?: boolean;
  action: () => void;
};

export function DesktopMenuBar({ menus }: { menus: Record<MenuName, MenuItem[]> }) {
  const [openMenu, setOpenMenu] = useState<MenuName | null>(null);
  const triggerRefs = useRef<Record<string, any>>({});
  const itemRefs = useRef<Record<string, any>>({});
  const names: MenuName[] = ['File', 'Edit', 'View', 'Help'];

  const closeMenu = (restoreFocus = true) => {
    const previous = openMenu;
    setOpenMenu(null);
    if (restoreFocus && previous) globalThis.setTimeout(() => triggerRefs.current[previous]?.focus?.(), 0);
  };

  const focusFirstEnabled = (menuName: MenuName) => {
    const item = menus[menuName].find((candidate) => !candidate.disabled);
    if (item) globalThis.setTimeout(() => itemRefs.current[item.id]?.focus?.(), 0);
  };

  const open = (menuName: MenuName) => {
    setOpenMenu(menuName);
    focusFirstEnabled(menuName);
  };

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return undefined;
    const handleDocumentKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && openMenu) {
        event.preventDefault();
        closeMenu(true);
      }
    };
    document.addEventListener('keydown', handleDocumentKey);
    return () => document.removeEventListener('keydown', handleDocumentKey);
  }, [openMenu]);

  const moveItemFocus = (menuName: MenuName, itemId: string, direction: number) => {
    const enabled = menus[menuName].filter((item) => !item.disabled);
    const index = enabled.findIndex((item) => item.id === itemId);
    const next = enabled[(index + direction + enabled.length) % enabled.length];
    next && itemRefs.current[next.id]?.focus?.();
  };

  const switchMenu = (menuName: MenuName, direction: number) => {
    const index = names.indexOf(menuName);
    open(names[(index + direction + names.length) % names.length]);
  };

  return (
    <View accessibilityRole="menubar" style={styles.bar}>
      {names.map((menuName) => (
        <View key={menuName} style={styles.menuRoot}>
          <Pressable
            ref={(node) => { triggerRefs.current[menuName] = node; }}
            accessibilityRole="button"
            accessibilityLabel={`${menuName} menu`}
            accessibilityState={{ expanded: openMenu === menuName }}
            onPress={() => openMenu === menuName ? closeMenu(false) : open(menuName)}
            {...({
              onKeyDown: (event: any) => {
                const key = event?.nativeEvent?.key || event?.key;
                if (key === 'ArrowDown' || key === 'Enter' || key === ' ') {
                  event.preventDefault?.();
                  open(menuName);
                }
                if (key === 'ArrowRight') switchMenu(menuName, 1);
                if (key === 'ArrowLeft') switchMenu(menuName, -1);
              },
            } as any)}
            style={({ hovered, pressed }) => [styles.trigger, (hovered || openMenu === menuName) ? styles.triggerActive : null, pressed ? styles.pressed : null]}
          >
            <Text style={styles.triggerText}>{menuName}</Text>
          </Pressable>
          {openMenu === menuName ? (
            <View accessibilityRole="menu" style={styles.popup}>
              {menus[menuName].map((item) => (
                <Pressable
                  key={item.id}
                  ref={(node) => { itemRefs.current[item.id] = node; }}
                  accessibilityRole="menuitem"
                  accessibilityLabel={item.label}
                  accessibilityState={{ disabled: item.disabled }}
                  disabled={item.disabled}
                  onPress={() => {
                    closeMenu(true);
                    item.action();
                  }}
                  {...({
                    onKeyDown: (event: any) => {
                      const key = event?.nativeEvent?.key || event?.key;
                      if (key === 'ArrowDown') { event.preventDefault?.(); moveItemFocus(menuName, item.id, 1); }
                      if (key === 'ArrowUp') { event.preventDefault?.(); moveItemFocus(menuName, item.id, -1); }
                      if (key === 'ArrowRight') { event.preventDefault?.(); switchMenu(menuName, 1); }
                      if (key === 'ArrowLeft') { event.preventDefault?.(); switchMenu(menuName, -1); }
                      if (key === 'Home') { event.preventDefault?.(); focusFirstEnabled(menuName); }
                      if (key === 'Escape') { event.preventDefault?.(); closeMenu(true); }
                    },
                  } as any)}
                  style={({ hovered, pressed }) => [styles.item, hovered ? styles.itemHovered : null, pressed ? styles.pressed : null, item.disabled ? styles.disabled : null]}
                >
                  <Text style={styles.itemText}>{item.label}</Text>
                  {item.shortcut ? <Text style={styles.shortcut}>{item.shortcut}</Text> : null}
                </Pressable>
              ))}
            </View>
          ) : null}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { flexDirection: 'row', alignItems: 'center' },
  menuRoot: { position: 'relative' },
  trigger: { minHeight: 34, justifyContent: 'center', paddingHorizontal: 9, borderRadius: UI.radius.small },
  triggerActive: { backgroundColor: UI.color.surfaceHover },
  triggerText: { color: UI.color.textMuted, fontSize: 12 },
  popup: {
    position: 'absolute', top: 34, left: 0, zIndex: 500, width: 260, padding: 6,
    borderRadius: UI.radius.panel, borderWidth: 1, borderColor: UI.color.borderStrong, backgroundColor: UI.color.surfaceRaised,
    ...UI.elevation.high,
  },
  item: { minHeight: 40, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, borderRadius: UI.radius.small, paddingHorizontal: 10 },
  itemHovered: { backgroundColor: UI.color.surfaceHover },
  itemText: { color: UI.color.text, fontSize: 13, fontWeight: '500' },
  shortcut: { color: UI.color.textSubtle, fontSize: 11 },
  pressed: { opacity: 0.72 },
  disabled: { opacity: 0.38 },
});
