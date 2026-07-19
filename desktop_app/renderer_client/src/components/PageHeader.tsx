import type { ReactNode } from 'react';
import { useRouter } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { DesktopPressableState } from '../lib/pressableState';
import { DESKTOP_UI as UI } from '../desktop/desktopUiTokens';

type PageHeaderProps = {
  title: string;
  subtitle?: string;
  eyebrow?: string;
  right?: ReactNode;
  fallbackHref?: string;
};

export function PageHeader({
  title,
  subtitle,
  eyebrow,
  right,
  fallbackHref = '/chat',
}: PageHeaderProps) {
  const router = useRouter();

  const goBack = () => {
    if (typeof window !== 'undefined' && window.history.length > 1) {
      router.back();
      return;
    }
    router.replace(fallbackHref as never);
  };

  return (
    <View style={styles.header}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Go back"
        style={({ pressed, hovered }: DesktopPressableState) => [
          styles.backButton,
          hovered ? styles.backButtonHover : null,
          pressed ? styles.backButtonPressed : null,
        ]}
        onPress={goBack}
      >
        <Text style={styles.backButtonText}>‹</Text>
      </Pressable>
      <View style={styles.copy}>
        {eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}
        <Text style={styles.title}>{title}</Text>
        {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
      </View>
      {right ? <View style={styles.right}>{right}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  backButton: {
    width: 34,
    height: 34,
    borderRadius: UI.radius.control,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: UI.color.surfaceMuted,
  },
  backButtonHover: {
    backgroundColor: UI.color.surfaceHover,
  },
  backButtonPressed: {
    transform: [{ scale: 0.97 }],
  },
  backButtonText: {
    color: UI.color.textMuted,
    fontSize: 24,
    fontWeight: '700',
    lineHeight: 26,
  },
  copy: {
    flex: 1,
    minWidth: 0,
    gap: 3,
  },
  eyebrow: {
    color: UI.color.accentStrong,
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0,
    textTransform: 'uppercase',
  },
  title: {
    color: UI.color.text,
    fontSize: 24,
    fontWeight: '700',
  },
  subtitle: {
    color: UI.color.textMuted,
    fontSize: 13,
    lineHeight: 19,
  },
  right: {
    flexShrink: 0,
  },
});
