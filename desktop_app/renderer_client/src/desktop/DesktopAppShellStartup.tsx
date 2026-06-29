import { useEffect, useRef } from 'react';
import { Animated, Easing, Platform, Pressable, Text, View } from 'react-native';

import { styles } from './DesktopAppShell.styles';

export function StartupGlyph() {
  const spin = useRef(new Animated.Value(0)).current;
  const pulse = useRef(new Animated.Value(0)).current;
  const useNativeDriver = Platform.OS !== 'web';

  useEffect(() => {
    const spinLoop = Animated.loop(
      Animated.timing(spin, {
        toValue: 1,
        duration: 1800,
        easing: Easing.linear,
        useNativeDriver,
      })
    );
    const pulseLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1,
          duration: 900,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver,
        }),
        Animated.timing(pulse, {
          toValue: 0,
          duration: 900,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver,
        }),
      ])
    );

    spinLoop.start();
    pulseLoop.start();

    return () => {
      spinLoop.stop();
      pulseLoop.stop();
    };
  }, [pulse, spin, useNativeDriver]);

  const orbitRotation = spin.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg'],
  });
  const pulseScale = pulse.interpolate({
    inputRange: [0, 1],
    outputRange: [0.95, 1.08],
  });
  const pulseOpacity = pulse.interpolate({
    inputRange: [0, 1],
    outputRange: [0.45, 0.95],
  });

  return (
    <View style={styles.startupGlyphFrame}>
      <Animated.View
        style={[
          styles.startupGlyphCore,
          {
            transform: [{ scale: pulseScale }],
            opacity: pulseOpacity,
          },
        ]}
      />
      <Animated.View
        style={[
          styles.startupGlyphOrbit,
          {
            transform: [{ rotate: orbitRotation }],
          },
        ]}
      >
        <View style={styles.startupGlyphDot} />
      </Animated.View>
    </View>
  );
}

export function DesktopStatusBanner({
  tone,
  message,
  onDismiss,
  actions,
}: {
  tone: 'error' | 'notice';
  message: string;
  onDismiss: () => void;
  actions?: Array<{
    label: string;
    onPress: () => void;
    disabled?: boolean;
  }>;
}) {
  return (
    <View style={[styles.statusBanner, tone === 'error' ? styles.errorBanner : styles.noticeBanner]}>
      <Text style={[styles.statusBannerText, tone === 'error' ? styles.errorBannerText : styles.noticeBannerText]}>
        {tone === 'error' ? `Warning: ${message}` : message}
      </Text>
      {actions?.map((action) => (
        <Pressable
          key={action.label}
          accessibilityRole="button"
          accessibilityLabel={action.label}
          style={[styles.statusBannerActionButton, action.disabled ? styles.statusBannerActionButtonDisabled : null]}
          onPress={action.onPress}
          disabled={action.disabled}
        >
          <Text style={styles.statusBannerActionText}>{action.label}</Text>
        </Pressable>
      ))}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Dismiss status message"
        style={styles.statusBannerCloseButton}
        onPress={onDismiss}
      >
        <Text style={styles.statusBannerCloseText}>x</Text>
      </Pressable>
    </View>
  );
}

function SkeletonBlock({ style, shimmerTranslate }: { style?: any; shimmerTranslate?: any }) {
  return (
    <View style={[styles.skeletonBlock, style]}>
      {shimmerTranslate ? (
        <Animated.View
          style={[
            styles.skeletonGlint,
            {
              transform: [{ translateX: shimmerTranslate }, { rotate: '12deg' }],
            },
          ]}
        />
      ) : null}
    </View>
  );
}

export function DesktopConversationSkeleton() {
  const shimmer = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    shimmer.setValue(0);
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(shimmer, {
          toValue: 1,
          duration: 1700,
          easing: Easing.inOut(Easing.cubic),
          useNativeDriver: Platform.OS !== 'web',
        }),
        Animated.delay(650),
      ])
    );
    loop.start();
    return () => {
      loop.stop();
    };
  }, [shimmer]);

  const shimmerTranslate = shimmer.interpolate({
    inputRange: [0, 1],
    outputRange: [-170, 360],
  });

  return (
    <View style={styles.skeletonShell} pointerEvents="none">
      <View style={styles.skeletonMain}>
        <View style={styles.skeletonTranscript}>
          <View style={styles.skeletonMessageStack}>
            <View style={[styles.skeletonMessageRow, styles.skeletonMessageRowLeft]}>
              <SkeletonBlock style={styles.skeletonTinyLine} shimmerTranslate={shimmerTranslate} />
              <SkeletonBlock style={styles.skeletonLongLine} shimmerTranslate={shimmerTranslate} />
              <SkeletonBlock style={styles.skeletonMediumLine} shimmerTranslate={shimmerTranslate} />
            </View>
            <View style={[styles.skeletonMessageRow, styles.skeletonMessageRowRight]}>
              <SkeletonBlock style={styles.skeletonTinyLine} shimmerTranslate={shimmerTranslate} />
              <SkeletonBlock style={styles.skeletonShortBubble} shimmerTranslate={shimmerTranslate} />
            </View>
            <View style={[styles.skeletonMessageRow, styles.skeletonMessageRowLeftWide]}>
              <SkeletonBlock style={styles.skeletonTinyLine} shimmerTranslate={shimmerTranslate} />
              <SkeletonBlock style={styles.skeletonLongLine} shimmerTranslate={shimmerTranslate} />
              <SkeletonBlock style={styles.skeletonLongLine} shimmerTranslate={shimmerTranslate} />
              <SkeletonBlock style={styles.skeletonMediumLine} shimmerTranslate={shimmerTranslate} />
            </View>
          </View>
        </View>
        <View style={styles.skeletonComposer}>
          <SkeletonBlock style={styles.skeletonComposerLine} shimmerTranslate={shimmerTranslate} />
          <View style={styles.skeletonComposerFooter}>
            <SkeletonBlock style={styles.skeletonComposerChip} shimmerTranslate={shimmerTranslate} />
            <SkeletonBlock style={styles.skeletonComposerChipShort} shimmerTranslate={shimmerTranslate} />
            <SkeletonBlock style={styles.skeletonComposerChipShort} shimmerTranslate={shimmerTranslate} />
            <SkeletonBlock style={styles.skeletonSendButton} shimmerTranslate={shimmerTranslate} />
          </View>
        </View>
      </View>
      <View style={styles.skeletonRail}>
        <SkeletonBlock style={styles.skeletonRailIcon} shimmerTranslate={shimmerTranslate} />
        <SkeletonBlock style={styles.skeletonRailIcon} shimmerTranslate={shimmerTranslate} />
        <SkeletonBlock style={styles.skeletonRailIcon} shimmerTranslate={shimmerTranslate} />
        <View style={styles.skeletonRailSection}>
          <SkeletonBlock style={styles.skeletonRailHeading} shimmerTranslate={shimmerTranslate} />
          <SkeletonBlock style={styles.skeletonRailSearch} shimmerTranslate={shimmerTranslate} />
          <SkeletonBlock style={styles.skeletonRailLine} shimmerTranslate={shimmerTranslate} />
          <SkeletonBlock style={styles.skeletonRailLineShort} shimmerTranslate={shimmerTranslate} />
        </View>
        <View style={styles.skeletonRailSection}>
          <SkeletonBlock style={styles.skeletonRailHeading} shimmerTranslate={shimmerTranslate} />
          <SkeletonBlock style={styles.skeletonRailRow} shimmerTranslate={shimmerTranslate} />
          <SkeletonBlock style={styles.skeletonRailRow} shimmerTranslate={shimmerTranslate} />
          <SkeletonBlock style={styles.skeletonRailRowActive} shimmerTranslate={shimmerTranslate} />
        </View>
      </View>
    </View>
  );
}
