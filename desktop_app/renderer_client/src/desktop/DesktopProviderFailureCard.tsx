import { useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { DESKTOP_UI as UI } from './desktopUiTokens';

type ProviderChoice = { providerId: string; modelId: string };

export function DesktopProviderFailureCard({
  failure,
  modelGroups,
  onRetry,
  onOpenSettings,
}: {
  failure: Record<string, any>;
  modelGroups: Array<Record<string, any>>;
  onRetry: (providerId: string, modelId: string) => void;
  onOpenSettings: () => void;
}) {
  const blockedUntilMs = useMemo(() => {
    const value = Date.parse(String(failure.blocked_until || failure.reset_at || ''));
    return Number.isFinite(value) ? value : 0;
  }, [failure.blocked_until, failure.reset_at]);
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    if (!blockedUntilMs || blockedUntilMs <= Date.now()) return undefined;
    const timer = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [blockedUntilMs]);
  const waitSeconds = blockedUntilMs > nowMs ? Math.max(1, Math.ceil((blockedUntilMs - nowMs) / 1000)) : 0;
  const currentProvider = String(failure.provider_id || '').trim();
  const currentModel = String(failure.model_id || '').trim();
  const providerScoped = String(failure.scope || '') === 'provider';
  const currentRetryAvailable = Boolean(failure.retryable) || Boolean(blockedUntilMs);
  const choices = useMemo(() => modelGroups.flatMap((group) => {
    const providerId = String(group.provider || group.provider_id || '').trim();
    return (Array.isArray(group.models) ? group.models : [])
      .map((model) => ({
        providerId,
        modelId: String(typeof model === 'string' ? model : model?.id || model?.model || '').trim(),
      }))
      .filter((choice) => choice.providerId && choice.modelId)
      .filter((choice) => {
        const sameProvider = choice.providerId === currentProvider;
        const sameModel = sameProvider && (
          choice.modelId === currentModel
          || choice.modelId.endsWith(`/${currentModel}`)
        );
        if (sameModel) return currentRetryAvailable;
        if (providerScoped && sameProvider) return false;
        return true;
      });
  }).sort((left, right) => {
    const leftWaiting = waitSeconds > 0 && left.providerId === currentProvider && (left.modelId === currentModel || left.modelId.endsWith(`/${currentModel}`));
    const rightWaiting = waitSeconds > 0 && right.providerId === currentProvider && (right.modelId === currentModel || right.modelId.endsWith(`/${currentModel}`));
    return Number(leftWaiting) - Number(rightWaiting);
  }), [currentModel, currentProvider, currentRetryAvailable, modelGroups, providerScoped, waitSeconds]);
  const [selected, setSelected] = useState<ProviderChoice | null>(() => choices[0] || null);
  useEffect(() => {
    if (!selected || !choices.some((choice) => choice.providerId === selected.providerId && choice.modelId === selected.modelId)) {
      setSelected(choices[0] || null);
    }
  }, [choices, selected]);
  const codeLabel = String(failure.code || 'provider_failed').replace(/_/g, ' ');
  const selectedIsWaiting = Boolean(
    selected
    && waitSeconds > 0
    && selected.providerId === currentProvider
    && (selected.modelId === currentModel || selected.modelId.endsWith(`/${currentModel}`))
  );
  const retryingCurrent = selected?.providerId === currentProvider && (
    selected?.modelId === currentModel
    || selected?.modelId.endsWith(`/${currentModel}`)
  );
  const currentChoice = choices.find((choice) => (
    choice.providerId === currentProvider
    && (choice.modelId === currentModel || choice.modelId.endsWith(`/${currentModel}`))
  )) || null;
  const waitLabel = waitSeconds >= 3600
    ? `${Math.floor(waitSeconds / 3600)}h ${Math.ceil((waitSeconds % 3600) / 60)}m`
    : waitSeconds >= 60
      ? `${Math.floor(waitSeconds / 60)}m ${waitSeconds % 60}s`
      : `${waitSeconds}s`;

  return (
    <View accessibilityLiveRegion="polite" style={styles.card}>
      <Text style={styles.eyebrow}>PROVIDER BLOCKED</Text>
      <Text style={styles.title}>{String(failure.user_message || 'The selected provider could not complete this turn.')}</Text>
      <Text style={styles.detail}>
        {`${String(failure.provider_id || 'Provider')} · ${String(failure.model_id || 'Model')} · ${codeLabel}`}
      </Text>
      {blockedUntilMs ? (
        <Text accessibilityLiveRegion="polite" style={styles.availability}>
          {waitSeconds > 0
            ? `Requests to this ${providerScoped ? 'provider' : 'model'} are paused for ${waitLabel}. You can switch providers now.`
            : 'The provider can be retried now.'}
        </Text>
      ) : null}
      {choices.length ? (
        <>
          <Text style={styles.label}>Retry this saved turn with</Text>
          <View style={styles.choices}>
            {choices.slice(0, 8).map((choice) => {
              const active = selected?.providerId === choice.providerId && selected?.modelId === choice.modelId;
              return (
                <Pressable
                  key={`${choice.providerId}:${choice.modelId}`}
                  accessibilityRole="radio"
                  accessibilityLabel={`${choice.providerId}, ${choice.modelId}`}
                  accessibilityState={{ checked: active }}
                  disabled={waitSeconds > 0 && choice.providerId === currentProvider && (choice.modelId === currentModel || choice.modelId.endsWith(`/${currentModel}`))}
                  onPress={() => setSelected(choice)}
                  style={[
                    styles.choice,
                    active ? styles.choiceActive : null,
                    waitSeconds > 0 && choice.providerId === currentProvider && (choice.modelId === currentModel || choice.modelId.endsWith(`/${currentModel}`)) ? styles.disabled : null,
                  ]}
                >
                  <Text style={[styles.choiceText, active ? styles.choiceTextActive : null]}>
                    {choice.providerId} · {choice.modelId}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </>
      ) : null}
      <View style={styles.actions}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={retryingCurrent ? 'Retry failed turn' : 'Switch provider and retry failed turn'}
          accessibilityState={{ disabled: !selected || selectedIsWaiting }}
          disabled={!selected || selectedIsWaiting}
          onPress={() => selected && onRetry(selected.providerId, selected.modelId)}
          style={[styles.primary, (!selected || selectedIsWaiting) ? styles.disabled : null]}
        >
          <Text style={styles.primaryText}>{retryingCurrent ? 'Retry' : 'Switch & Retry'}</Text>
        </Pressable>
        <Pressable accessibilityRole="button" onPress={onOpenSettings} style={styles.secondary}>
          <Text style={styles.secondaryText}>Open Settings</Text>
        </Pressable>
        {waitSeconds > 0 && currentChoice ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Check whether the provider is available now"
            onPress={() => onRetry(currentChoice.providerId, currentChoice.modelId)}
            style={styles.secondary}
          >
            <Text style={styles.secondaryText}>Check Again</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginVertical: 12,
    borderWidth: 1,
    borderColor: 'rgba(224, 120, 132, 0.38)',
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.dangerSoft,
    padding: 16,
    gap: 10,
  },
  eyebrow: { color: UI.color.danger, fontSize: 11, fontWeight: '700', letterSpacing: 0.55 },
  title: { color: UI.color.text, fontSize: 14, fontWeight: '700', lineHeight: 20 },
  detail: { color: UI.color.textMuted, fontSize: 12 },
  availability: { color: UI.color.text, fontSize: 12, lineHeight: 18 },
  label: { color: UI.color.textMuted, fontSize: 12, fontWeight: '600' },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  choice: {
    minHeight: 44,
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: UI.color.borderStrong,
    borderRadius: UI.radius.control,
    paddingHorizontal: 12,
    backgroundColor: UI.color.surfaceMuted,
  },
  choiceActive: { borderColor: UI.color.accent, backgroundColor: UI.color.accentSoft },
  choiceText: { color: UI.color.textMuted, fontSize: 12, fontWeight: '600' },
  choiceTextActive: { color: UI.color.accentStrong },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  primary: {
    minHeight: 44,
    justifyContent: 'center',
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accent,
    paddingHorizontal: 16,
  },
  primaryText: { color: UI.color.accentInk, fontSize: 13, fontWeight: '700' },
  secondary: {
    minHeight: 44,
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: UI.color.borderStrong,
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.surfaceMuted,
    paddingHorizontal: 16,
  },
  secondaryText: { color: UI.color.text, fontSize: 13, fontWeight: '600' },
  disabled: { opacity: 0.45 },
});
