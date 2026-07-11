import { useState, type ComponentType, type ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Archive from 'lucide-react-native/icons/archive';
import Bot from 'lucide-react-native/icons/bot';
import Check from 'lucide-react-native/icons/check';
import ChevronDown from 'lucide-react-native/icons/chevron-down';
import ChevronUp from 'lucide-react-native/icons/chevron-up';
import Clock3 from 'lucide-react-native/icons/clock-3';
import Ellipsis from 'lucide-react-native/icons/ellipsis';
import Folder from 'lucide-react-native/icons/folder';
import FolderOpen from 'lucide-react-native/icons/folder-open';
import GitBranch from 'lucide-react-native/icons/git-branch';
import History from 'lucide-react-native/icons/history';
import Info from 'lucide-react-native/icons/info';
import Menu from 'lucide-react-native/icons/menu';
import Mic from 'lucide-react-native/icons/mic';
import Pin from 'lucide-react-native/icons/pin';
import Plus from 'lucide-react-native/icons/plus';
import Search from 'lucide-react-native/icons/search';
import Send from 'lucide-react-native/icons/send';
import Settings from 'lucide-react-native/icons/settings';
import Square from 'lucide-react-native/icons/square';
import SquarePen from 'lucide-react-native/icons/square-pen';

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
  | 'archive'
  | 'automation'
  | 'stop'
  | 'plus';

const COMPOSER_MIN_LINES = 1;
const COMPOSER_MAX_LINES = 8;
const COMPOSER_LINE_HEIGHT = 22;
const COMPOSER_MIN_HEIGHT = COMPOSER_MIN_LINES * COMPOSER_LINE_HEIGHT;
const COMPOSER_MAX_HEIGHT = COMPOSER_MAX_LINES * COMPOSER_LINE_HEIGHT;

type FoldSectionProps = {
  title: string;
  summary: string;
  defaultOpen?: boolean;
  children: ReactNode;
};

type LucideIconComponent = ComponentType<{
  color?: string;
  size?: number;
  strokeWidth?: number;
  fill?: string;
  style?: any;
}>;

const LUCIDE_ICON_MAP: Record<MonoIconName, LucideIconComponent> = {
  menu: Menu,
  settings: Settings,
  compose: SquarePen,
  search: Search,
  info: Info,
  voice: Mic,
  history: History,
  folder_closed: Folder,
  folder_open: FolderOpen,
  branch: GitBranch,
  telegram: Send,
  chevron_down: ChevronDown,
  chevron_up: ChevronUp,
  check: Check,
  pin: Pin,
  more: Ellipsis,
  archive: Archive,
  automation: Clock3,
  stop: Square,
  plus: Plus,
};

const FILLED_ICON_NAMES = new Set<MonoIconName>(['pin', 'stop']);

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
  const flattened = (StyleSheet.flatten(style) || {}) as Record<string, any>;
  const Icon = LUCIDE_ICON_MAP[name] || Bot;
  const color = typeof flattened.color === 'string' ? flattened.color : '#dfe8f5';
  const size = typeof flattened.fontSize === 'number' ? flattened.fontSize : 15;
  const explicitWidth = typeof flattened.width === 'number' ? flattened.width : size + 3;
  const explicitHeight = typeof flattened.height === 'number' ? flattened.height : size + 3;
  const iconSize = Math.max(10, Math.min(size, explicitWidth, explicitHeight));
  const strokeWidth = size <= 12 ? 2.35 : size >= 18 ? 2.05 : 2.25;
  const iconFill = FILLED_ICON_NAMES.has(name) ? color : 'none';
  const iconStyle = {
    transform: name === 'pin' ? [{ rotate: '-18deg' }] : undefined,
  };
  const containerStyle = { ...flattened };
  delete containerStyle.color;
  delete containerStyle.fontFamily;
  delete containerStyle.fontSize;
  delete containerStyle.fontVariant;
  delete containerStyle.fontWeight;
  delete containerStyle.letterSpacing;
  delete containerStyle.lineHeight;
  delete containerStyle.textAlign;

  return (
    <View
      style={[
        {
          width: explicitWidth,
          height: explicitHeight,
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: typeof flattened.flexShrink === 'number' ? flattened.flexShrink : undefined,
        },
        containerStyle,
      ]}
    >
      <Icon
        color={color}
        size={iconSize}
        strokeWidth={strokeWidth}
        fill={iconFill}
        style={iconStyle}
      />
    </View>
  );
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
