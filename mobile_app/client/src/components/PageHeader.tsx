import type { ReactNode } from 'react';
import { useRouter } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { CrossPlatformPressableState } from '../lib/pressableState';

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
        style={({ pressed, hovered }: CrossPlatformPressableState) => [
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
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#1f3f62',
    backgroundColor: '#0b172a',
  },
  backButtonHover: {
    borderColor: '#2dd4ff',
    backgroundColor: '#10233d',
  },
  backButtonPressed: {
    transform: [{ scale: 0.97 }],
  },
  backButtonText: {
    color: '#d9f6ff',
    fontSize: 24,
    fontWeight: '900',
    lineHeight: 26,
  },
  copy: {
    flex: 1,
    minWidth: 0,
    gap: 3,
  },
  eyebrow: {
    color: '#7cc7ff',
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0,
    textTransform: 'uppercase',
  },
  title: {
    color: '#ffffff',
    fontSize: 24,
    fontWeight: '800',
  },
  subtitle: {
    color: '#aebdd8',
    fontSize: 13,
    lineHeight: 19,
  },
  right: {
    flexShrink: 0,
  },
});
