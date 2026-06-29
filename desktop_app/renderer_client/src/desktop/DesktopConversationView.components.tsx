import { useState, type ReactNode } from 'react';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';

import { styles } from './DesktopConversationView.styles';

type MonoIconName =
  | 'menu'
  | 'settings'
  | 'compose'
  | 'search'
  | 'info'
  | 'voice'
  | 'history'
  | 'folder_closed'
  | 'folder_open'
  | 'branch'
  | 'telegram'
  | 'chevron_down'
  | 'chevron_up'
  | 'check'
  | 'pin'
  | 'more'
  | 'plus';

const COMPOSER_MIN_LINES = 1;
const COMPOSER_MAX_LINES = 8;
const COMPOSER_LINE_HEIGHT = 22;
const COMPOSER_MIN_HEIGHT = COMPOSER_MIN_LINES * COMPOSER_LINE_HEIGHT;
const COMPOSER_MAX_HEIGHT = COMPOSER_MAX_LINES * COMPOSER_LINE_HEIGHT;
const MONO_ICON_GLYPHS: Record<MonoIconName, string> = {
  menu: '≡',
  settings: '⛭',
  compose: '✎',
  search: '⌕',
  info: '',
  voice: '◌',
  history: '◷',
  folder_closed: '',
  folder_open: '',
  branch: '⎇',
  telegram: 'T',
  chevron_down: '',
  chevron_up: '',
  check: '✓',
  pin: '⌖',
  more: '⋯',
  plus: '+',
};

const SIDEBAR_ICON_STYLE = Platform.OS === 'web'
  ? ({
      fontFamily: 'Segoe UI Symbol, Segoe UI, sans-serif',
      fontVariant: ['tabular-nums'],
    } as any)
  : null;

type FoldSectionProps = {
  title: string;
  summary: string;
  defaultOpen?: boolean;
  children: ReactNode;
};

export function createClientId() {
  return `desktop-${Math.random().toString(36).slice(2, 10)}`;
}

export function MonoIcon({
  name,
  style,
}: {
  name: MonoIconName;
  style?: any;
}) {
  const flattened = StyleSheet.flatten(style) || {};
  const color = typeof flattened.color === 'string' ? flattened.color : '#dfe8f5';
  const size = typeof flattened.fontSize === 'number' ? flattened.fontSize : 14;
  if (name === 'voice') {
    return (
      <View style={[flattened, { width: size + 2, height: size + 2, alignItems: 'center', justifyContent: 'center' }]}>
        <View style={{ width: size, height: size, position: 'relative' }}>
          <View
            style={{
              position: 'absolute',
              left: size * 0.31,
              top: size * 0.08,
              width: size * 0.38,
              height: size * 0.48,
              borderWidth: 1.5,
              borderColor: color,
              borderRadius: size * 0.2,
            }}
          />
          <View
            style={{
              position: 'absolute',
              left: size * 0.49,
              top: size * 0.56,
              width: 1.5,
              height: size * 0.16,
              backgroundColor: color,
            }}
          />
          <View
            style={{
              position: 'absolute',
              left: size * 0.24,
              top: size * 0.48,
              width: size * 0.52,
              height: size * 0.26,
              borderWidth: 1.5,
              borderTopWidth: 0,
              borderColor: color,
              borderBottomLeftRadius: size * 0.18,
              borderBottomRightRadius: size * 0.18,
            }}
          />
          <View
            style={{
              position: 'absolute',
              left: size * 0.34,
              top: size * 0.82,
              width: size * 0.32,
              height: 1.5,
              backgroundColor: color,
            }}
          />
        </View>
      </View>
    );
  }
  if (name === 'info') {
    return (
      <View style={[flattened, { width: size + 2, height: size + 2, alignItems: 'center', justifyContent: 'center' }]}>
        <View style={{ width: size, height: size, position: 'relative' }}>
          <View
            style={{
              position: 'absolute',
              left: size * 0.12,
              top: size * 0.12,
              width: size * 0.76,
              height: size * 0.76,
              borderWidth: 1.4,
              borderColor: color,
              borderRadius: size * 0.38,
            }}
          />
          <View
            style={{
              position: 'absolute',
              left: size * 0.45,
              top: size * 0.28,
              width: size * 0.1,
              height: size * 0.1,
              borderRadius: size * 0.05,
              backgroundColor: color,
            }}
          />
          <View
            style={{
              position: 'absolute',
              left: size * 0.46,
              top: size * 0.42,
              width: size * 0.08,
              height: size * 0.22,
              backgroundColor: color,
              borderRadius: 999,
            }}
          />
        </View>
      </View>
    );
  }
  if (name === 'folder_closed' || name === 'folder_open') {
    return (
      <View style={[flattened, { width: size + 2, height: size, alignItems: 'center', justifyContent: 'center' }]}>
        <View style={{ width: size, height: size, position: 'relative' }}>
          <View
            style={{
              position: 'absolute',
              left: size * 0.1,
              top: size * 0.16,
              width: size * 0.28,
              height: size * 0.12,
              borderWidth: 1.5,
              borderBottomWidth: 0,
              borderColor: color,
              borderTopLeftRadius: 2,
              borderTopRightRadius: 2,
            }}
          />
          <View
            style={{
              position: 'absolute',
              left: size * 0.08,
              top: name === 'folder_open' ? size * 0.34 : size * 0.28,
              width: size * 0.82,
              height: size * 0.44,
              borderWidth: 1.5,
              borderColor: color,
              borderRadius: 2,
            }}
          />
          {name === 'folder_open' ? (
            <View
              style={{
                position: 'absolute',
                left: size * 0.14,
                top: size * 0.26,
                width: size * 0.44,
                height: 1.5,
                backgroundColor: color,
                transform: [{ rotate: '-14deg' }],
              }}
            />
          ) : null}
        </View>
      </View>
    );
  }
  if (name === 'chevron_down' || name === 'chevron_up') {
    const isUp = name === 'chevron_up';
    return (
      <View style={[flattened, { width: size, height: size, alignItems: 'center', justifyContent: 'center' }]}>
        <View style={{ width: size, height: size * 0.7, position: 'relative' }}>
          <View
            style={{
              position: 'absolute',
              left: size * 0.19,
              top: size * 0.26,
              width: size * 0.36,
              height: 1.5,
              backgroundColor: color,
              borderRadius: 999,
              transform: [{ rotate: isUp ? '-42deg' : '42deg' }],
            }}
          />
          <View
            style={{
              position: 'absolute',
              right: size * 0.19,
              top: size * 0.26,
              width: size * 0.36,
              height: 1.5,
              backgroundColor: color,
              borderRadius: 999,
              transform: [{ rotate: isUp ? '42deg' : '-42deg' }],
            }}
          />
        </View>
      </View>
    );
  }
  return <Text style={[styles.monoIconBase, style]}>{MONO_ICON_GLYPHS[name]}</Text>;
}

export function FoldSection({ title, summary, defaultOpen = false, children }: FoldSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <View style={styles.foldSection}>
      <Pressable style={styles.foldSectionHeader} onPress={() => setOpen((current) => !current)}>
        <View style={styles.foldSectionHeaderCopy}>
          <Text style={styles.foldSectionTitle}>{title}</Text>
          <Text style={styles.foldSectionSummary}>{summary}</Text>
        </View>
        <View style={styles.foldSectionToggle}>
          <Text style={styles.foldSectionToggleText}>{open ? '‹' : '›'}</Text>
        </View>
      </Pressable>
      {open ? <View style={styles.foldSectionBody}>{children}</View> : null}
    </View>
  );
}
