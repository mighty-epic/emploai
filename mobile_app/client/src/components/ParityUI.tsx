import type { ReactNode } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

type SectionTab<T extends string> = {
  key: T;
  label: string;
  badge?: string | number | null;
};

type SectionTabsProps<T extends string> = {
  tabs: SectionTab<T>[];
  active: T;
  onChange: (key: T) => void;
};

type BottomSheetProps = {
  visible: boolean;
  title: string;
  subtitle?: string;
  doneLabel?: string;
  onClose: () => void;
  children: ReactNode;
};

export function SectionTabs<T extends string>({ tabs, active, onChange }: SectionTabsProps<T>) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.tabs}>
      {tabs.map((tab) => (
        <Pressable
          key={tab.key}
          accessibilityRole="button"
          accessibilityLabel={tab.label}
          accessibilityState={{ selected: active === tab.key }}
          style={[styles.tabButton, active === tab.key ? styles.tabButtonActive : null]}
          onPress={() => onChange(tab.key)}
        >
          <Text style={[styles.tabText, active === tab.key ? styles.tabTextActive : null]}>{tab.label}</Text>
          {tab.badge ? (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>{String(tab.badge)}</Text>
            </View>
          ) : null}
        </Pressable>
      ))}
    </ScrollView>
  );
}

export function StatusPill({
  label,
  tone = 'neutral',
}: {
  label: string;
  tone?: 'neutral' | 'good' | 'warn' | 'error' | 'accent';
}) {
  return (
    <View style={[styles.pill, styles[`pill_${tone}`]]}>
      <Text style={styles.pillText}>{label}</Text>
    </View>
  );
}

export function BottomSheet({ visible, title, subtitle, doneLabel = 'Done', onClose, children }: BottomSheetProps) {
  return (
    <Modal transparent visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={styles.sheetOverlay}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Close ${title}`}
          style={styles.sheetBackdrop}
          onPress={onClose}
        />
        <SafeAreaView edges={['bottom']} style={styles.sheet}>
          <View style={styles.sheetHandle} />
          <View style={styles.sheetHeader}>
            <View style={styles.sheetHeading}>
              <Text style={styles.sheetTitle}>{title}</Text>
              {subtitle ? <Text style={styles.sheetSubtitle}>{subtitle}</Text> : null}
            </View>
            <Pressable accessibilityRole="button" accessibilityLabel={doneLabel} style={styles.doneButton} onPress={onClose}>
              <Text style={styles.doneText}>{doneLabel}</Text>
            </Pressable>
          </View>
          <ScrollView contentContainerStyle={styles.sheetContent}>{children}</ScrollView>
        </SafeAreaView>
      </View>
    </Modal>
  );
}

export function ControlRow({ children }: { children: ReactNode }) {
  return <View style={styles.controlRow}>{children}</View>;
}

export function ActionButton({
  label,
  onPress,
  active,
  disabled,
  tone = 'neutral',
}: {
  label: string;
  onPress?: () => void;
  active?: boolean;
  disabled?: boolean;
  tone?: 'neutral' | 'primary' | 'danger';
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: Boolean(disabled), selected: Boolean(active) }}
      style={[
        styles.actionButton,
        tone === 'primary' ? styles.actionPrimary : null,
        tone === 'danger' ? styles.actionDanger : null,
        active ? styles.actionActive : null,
        disabled ? styles.actionDisabled : null,
      ]}
      onPress={onPress}
      disabled={disabled}
    >
      <Text style={styles.actionText}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  tabs: {
    gap: 8,
    paddingVertical: 2,
  },
  tabButton: {
    minHeight: 40,
    borderRadius: 8,
    paddingHorizontal: 13,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    backgroundColor: '#151d30',
    borderWidth: 1,
    borderColor: '#25324f',
  },
  tabButtonActive: {
    backgroundColor: '#274775',
    borderColor: '#4779b6',
  },
  tabText: {
    color: '#a9b8d0',
    fontWeight: '800',
    fontSize: 12,
  },
  tabTextActive: {
    color: '#ffffff',
  },
  badge: {
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 5,
    backgroundColor: '#3b82f6',
  },
  badgeText: {
    color: '#ffffff',
    fontSize: 10,
    fontWeight: '800',
  },
  pill: {
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 9,
    paddingVertical: 5,
    backgroundColor: '#151d30',
    borderColor: '#2a3855',
  },
  pill_good: {
    backgroundColor: '#123225',
    borderColor: '#1f8a5c',
  },
  pill_warn: {
    backgroundColor: '#302711',
    borderColor: '#8a641d',
  },
  pill_error: {
    backgroundColor: '#32151a',
    borderColor: '#8b2d37',
  },
  pill_accent: {
    backgroundColor: '#122238',
    borderColor: '#2d5c88',
  },
  pill_neutral: {},
  pillText: {
    color: '#e8f1ff',
    fontSize: 11,
    fontWeight: '800',
  },
  sheetOverlay: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(5, 8, 18, 0.42)',
  },
  sheetBackdrop: {
    flex: 1,
  },
  sheet: {
    maxHeight: '88%',
    backgroundColor: '#0e1526',
    borderTopLeftRadius: 18,
    borderTopRightRadius: 18,
    borderTopWidth: 1,
    borderColor: '#26324f',
    paddingHorizontal: 18,
    paddingTop: 10,
  },
  sheetHandle: {
    width: 44,
    height: 4,
    borderRadius: 999,
    backgroundColor: '#3a4968',
    alignSelf: 'center',
    marginBottom: 12,
  },
  sheetHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 14,
    paddingBottom: 12,
  },
  sheetHeading: {
    flex: 1,
    gap: 4,
  },
  sheetTitle: {
    color: '#ffffff',
    fontSize: 20,
    fontWeight: '900',
  },
  sheetSubtitle: {
    color: '#8fa1bf',
    fontSize: 12,
    lineHeight: 17,
  },
  doneButton: {
    minHeight: 40,
    justifyContent: 'center',
  },
  doneText: {
    color: '#8fd3ff',
    fontWeight: '900',
  },
  sheetContent: {
    gap: 14,
    paddingBottom: 28,
  },
  controlRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  actionButton: {
    minHeight: 42,
    borderRadius: 8,
    paddingHorizontal: 13,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#17223a',
    borderWidth: 1,
    borderColor: '#283756',
  },
  actionPrimary: {
    backgroundColor: '#2563eb',
    borderColor: '#3b82f6',
  },
  actionDanger: {
    backgroundColor: '#32151a',
    borderColor: '#8b2d37',
  },
  actionActive: {
    backgroundColor: '#24476e',
    borderColor: '#68bdf6',
  },
  actionDisabled: {
    opacity: 0.45,
  },
  actionText: {
    color: '#f4f8ff',
    fontWeight: '800',
    fontSize: 13,
  },
});
