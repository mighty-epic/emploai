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
  const choices = useMemo(() => modelGroups.flatMap((group) => {
    const providerId = String(group.provider || group.provider_id || '').trim();
    return (Array.isArray(group.models) ? group.models : [])
      .map((model) => ({
        providerId,
        modelId: String(typeof model === 'string' ? model : model?.id || model?.model || '').trim(),
      }))
      .filter((choice) => choice.providerId && choice.modelId)
      .filter((choice) => (
        choice.providerId !== String(failure.provider_id || '')
        || choice.modelId !== String(failure.model_id || '')
      ));
  }), [failure.model_id, failure.provider_id, modelGroups]);
  const [selected, setSelected] = useState<ProviderChoice | null>(() => choices[0] || null);
  useEffect(() => {
    if (!selected && choices.length) setSelected(choices[0]);
  }, [choices, selected]);
  const codeLabel = String(failure.code || 'provider_failed').replace(/_/g, ' ');

  return (
    <View accessibilityLiveRegion="polite" style={styles.card}>
      <Text style={styles.eyebrow}>PROVIDER BLOCKED</Text>
      <Text style={styles.title}>{String(failure.user_message || 'The selected provider could not complete this turn.')}</Text>
      <Text style={styles.detail}>
        {`${String(failure.provider_id || 'Provider')} · ${String(failure.model_id || 'Model')} · ${codeLabel}`}
      </Text>
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
                  onPress={() => setSelected(choice)}
                  style={[styles.choice, active ? styles.choiceActive : null]}
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
          accessibilityLabel="Switch provider and retry failed turn"
          accessibilityState={{ disabled: !selected }}
          disabled={!selected}
          onPress={() => selected && onRetry(selected.providerId, selected.modelId)}
          style={[styles.primary, !selected ? styles.disabled : null]}
        >
          <Text style={styles.primaryText}>Switch & Retry</Text>
        </Pressable>
        <Pressable accessibilityRole="button" onPress={onOpenSettings} style={styles.secondary}>
          <Text style={styles.secondaryText}>Open Settings</Text>
        </Pressable>
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
