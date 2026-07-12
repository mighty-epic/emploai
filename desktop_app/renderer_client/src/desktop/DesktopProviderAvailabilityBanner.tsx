import { useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { DESKTOP_UI as UI } from './desktopUiTokens';


function formatWait(seconds: number) {
  if (seconds >= 3600) return `${Math.floor(seconds / 3600)}h ${Math.ceil((seconds % 3600) / 60)}m`;
  if (seconds >= 60) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  return `${seconds}s`;
}

export function DesktopProviderAvailabilityBanner({
  records,
  onOpenSettings,
}: {
  records: Array<Record<string, any>>;
  onOpenSettings: () => void;
}) {
  const active = useMemo(() => [...records].sort((left, right) => (
    Date.parse(String(right.blocked_until || '')) - Date.parse(String(left.blocked_until || ''))
  ))[0] || null, [records]);
  const blockedUntilMs = active ? Date.parse(String(active.blocked_until || active.reset_at || '')) : 0;
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!Number.isFinite(blockedUntilMs) || blockedUntilMs <= Date.now()) return undefined;
    const timer = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [blockedUntilMs]);

  if (!active || !Number.isFinite(blockedUntilMs) || blockedUntilMs <= nowMs) return null;
  const waitSeconds = Math.max(1, Math.ceil((blockedUntilMs - nowMs) / 1000));
  const provider = String(active.provider_id || 'Provider');
  const additionalCount = Math.max(0, records.length - 1);

  return (
    <View accessibilityLiveRegion="polite" style={styles.banner}>
      <View style={styles.copy}>
        <Text style={styles.eyebrow}>PROVIDER PAUSED</Text>
        <Text style={styles.title}>
          {`${provider} is paused for ${formatWait(waitSeconds)}${additionalCount ? ` · ${additionalCount} more provider block${additionalCount === 1 ? '' : 's'}` : ''}`}
        </Text>
        <Text style={styles.detail}>
          {String(active.user_message || 'Requests are paused to prevent repeated failures. Local tools remain available.')}
        </Text>
      </View>
      <Pressable accessibilityRole="button" onPress={onOpenSettings} style={styles.action}>
        <Text style={styles.actionText}>Provider Settings</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    marginVertical: 10,
    borderWidth: 1,
    borderColor: UI.color.borderStrong,
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surfaceMuted,
    padding: 14,
    gap: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  copy: { flex: 1, gap: 4 },
  eyebrow: { color: UI.color.warning, fontSize: 11, fontWeight: '700', letterSpacing: 0.5 },
  title: { color: UI.color.text, fontSize: 13, fontWeight: '700' },
  detail: { color: UI.color.textMuted, fontSize: 12, lineHeight: 18 },
  action: {
    minHeight: 44,
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: UI.color.borderStrong,
    borderRadius: UI.radius.control,
    paddingHorizontal: 12,
  },
  actionText: { color: UI.color.text, fontSize: 12, fontWeight: '700' },
});
