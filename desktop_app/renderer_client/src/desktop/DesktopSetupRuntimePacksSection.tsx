import { useEffect, useRef, useState } from 'react';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';

import {
  fetchManagerContextInspectionSetting,
  fetchRuntimePackProgress,
  fetchRuntimePacks,
  installRuntimePack,
  removeRuntimePack,
  setManagerContextInspectionSetting,
} from '@/lib/appApi';
import { DESKTOP_UI as UI } from './desktopUiTokens';

type RuntimePack = {
  id: string;
  kind?: string;
  title?: string;
  description?: string;
  installed?: boolean;
  available?: boolean;
  removable?: boolean;
  approx_size_mb?: number;
  model_id?: string;
  issues?: string[];
  progress?: Record<string, any>;
};

type Props = {
  apiBaseUrl?: string | null;
  token?: string | null;
  focusPackId?: string | null;
};

function packKindLabel(pack: RuntimePack) {
  if (pack.kind === 'context_index') return 'Context index';
  return 'Voice';
}

export function DesktopSetupRuntimePacksSection({ apiBaseUrl, token, focusPackId }: Props) {
  const [packs, setPacks] = useState<RuntimePack[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyPackId, setBusyPackId] = useState<string | null>(null);
  const [confirmPack, setConfirmPack] = useState<RuntimePack | null>(null);
  const [progress, setProgress] = useState<Record<string, any> | null>(null);
  const [message, setMessage] = useState('');
  const [inspectionEnabled, setInspectionEnabled] = useState(false);
  const [inspectionBusy, setInspectionBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = async () => {
    if (!apiBaseUrl || !token) return;
    setLoading(true);
    try {
      const [summary, inspection] = await Promise.all([
        fetchRuntimePacks(apiBaseUrl, token),
        fetchManagerContextInspectionSetting(apiBaseUrl, token),
      ]);
      setPacks((summary.packs || []) as RuntimePack[]);
      setInspectionEnabled(Boolean(inspection.enabled));
      setMessage('');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Runtime pack status could not be loaded.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [apiBaseUrl, token]);
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);
  useEffect(() => {
    if (!focusPackId || Platform.OS !== 'web' || typeof document === 'undefined') return;
    const timer = setTimeout(() => document.getElementById(`runtime-pack-${focusPackId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 80);
    return () => clearTimeout(timer);
  }, [focusPackId, packs.length]);

  const install = async (pack: RuntimePack) => {
    if (!apiBaseUrl || !token || busyPackId) return;
    setConfirmPack(null);
    setBusyPackId(pack.id);
    setMessage('');
    setProgress({ state: 'installing', phase: 'prepare', percent: 0, message: `Preparing ${pack.title || pack.id}…` });
    pollRef.current = setInterval(() => {
      void fetchRuntimePackProgress(apiBaseUrl, token, pack.id).then(setProgress).catch(() => undefined);
    }, 750);
    try {
      await installRuntimePack(apiBaseUrl, token, pack.id);
      setMessage(`${pack.title || pack.id} is ready.`);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'The runtime pack could not be installed.');
    } finally {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
      setBusyPackId(null);
    }
  };

  const remove = async (pack: RuntimePack) => {
    if (!apiBaseUrl || !token || busyPackId) return;
    setBusyPackId(pack.id);
    setMessage('');
    try {
      await removeRuntimePack(apiBaseUrl, token, pack.id);
      setMessage(`${pack.title || pack.id} was removed.`);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'The runtime pack could not be removed.');
    } finally {
      setBusyPackId(null);
    }
  };

  const toggleInspection = async () => {
    if (!apiBaseUrl || !token || inspectionBusy) return;
    setInspectionBusy(true);
    setMessage('');
    try {
      const setting = await setManagerContextInspectionSetting(apiBaseUrl, token, !inspectionEnabled);
      setInspectionEnabled(Boolean(setting.enabled));
      setMessage(setting.enabled
        ? 'Manager context inspection is enabled from this point forward.'
        : 'Context inspection is disabled. The existing local index is retained.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Context inspection could not be updated.');
    } finally {
      setInspectionBusy(false);
    }
  };

  return (
    <>
      <View style={styles.section}>
        <View style={styles.headingRow}>
          <View style={styles.headingCopy}>
            <Text style={styles.title}>Available packs</Text>
          </View>
          <Pressable style={styles.refreshButton} disabled={loading} onPress={() => void load()}>
            <Text style={styles.refreshText}>{loading ? 'Checking…' : 'Refresh'}</Text>
          </Pressable>
        </View>
        {message ? <Text style={styles.message}>{message}</Text> : null}
      </View>

      <View style={styles.section}>
        <View style={styles.headingRow}>
          <View style={styles.headingCopy}>
            <Text style={styles.title}>Manager context inspection</Text>
            <Text style={styles.helper}>
              Lets managers search redacted descendant activity created while enabled.
            </Text>
          </View>
          <Pressable
            accessibilityRole="switch"
            accessibilityState={{ checked: inspectionEnabled, disabled: inspectionBusy }}
            style={[styles.toggle, inspectionEnabled ? styles.toggleOn : null]}
            disabled={inspectionBusy}
            onPress={() => void toggleInspection()}
          >
            <View style={[styles.toggleKnob, inspectionEnabled ? styles.toggleKnobOn : null]} />
          </Pressable>
        </View>
        {inspectionEnabled ? <Text style={styles.meta}>Indexing new eligible activity</Text> : null}
      </View>

      <View style={styles.packList}>
        {packs.map((pack) => {
          const busy = busyPackId === pack.id;
          const highlighted = focusPackId === pack.id;
          const activeProgress = busy ? progress : pack.progress;
          return (
            <View
              key={pack.id}
              nativeID={`runtime-pack-${pack.id}`}
              style={[styles.card, highlighted ? styles.cardHighlighted : null]}
            >
              <View style={styles.headingRow}>
                <View style={styles.headingCopy}>
                  <Text style={styles.eyebrow}>{packKindLabel(pack)}</Text>
                  <Text style={styles.cardTitle}>{pack.title || pack.id}</Text>
                  {pack.kind === 'context_index' && pack.description ? <Text style={styles.helper}>{pack.description}</Text> : null}
                </View>
                <View style={[styles.badge, pack.available ? styles.badgeReady : null]}>
                  <Text style={[styles.badgeText, pack.available ? styles.badgeTextReady : null]}>
                    {pack.available ? 'Ready' : pack.installed ? 'Needs attention' : 'Not installed'}
                  </Text>
                </View>
              </View>
              <Text style={styles.meta}>
                {pack.approx_size_mb ? `About ${pack.approx_size_mb} MB` : ''}{pack.kind === 'context_index' && pack.model_id ? `${pack.approx_size_mb ? ' · ' : ''}${pack.model_id}` : ''}
              </Text>
              {pack.installed && pack.issues?.[0] ? <Text style={styles.issue}>{pack.issues[0]}</Text> : null}
              {activeProgress?.state === 'installing' ? (
                <View style={styles.progressBlock}>
                  <View style={styles.progressTrack}>
                    <View style={[styles.progressFill, { width: `${Math.max(2, Number(activeProgress.percent || 0))}%` }]} />
                  </View>
                  <Text style={styles.meta}>{String(activeProgress.message || 'Installing…')}</Text>
                </View>
              ) : null}
              {confirmPack?.id === pack.id ? (
                <View style={styles.confirmCard}>
                  <Text style={styles.confirmTitle}>Download {pack.title || pack.id}?</Text>
                  <Text style={styles.helper}>
                    This installs the pack on this computer{pack.approx_size_mb ? ` and downloads about ${pack.approx_size_mb} MB` : ''}. Nothing is downloaded until you confirm.
                  </Text>
                  <View style={styles.actionRow}>
                    <Pressable style={styles.primaryButton} onPress={() => void install(pack)}>
                      <Text style={styles.primaryText}>Download pack</Text>
                    </Pressable>
                    <Pressable style={styles.secondaryButton} onPress={() => setConfirmPack(null)}>
                      <Text style={styles.secondaryText}>Cancel</Text>
                    </Pressable>
                  </View>
                </View>
              ) : (
                <View style={styles.actionRow}>
                  {!pack.available ? (
                    <Pressable style={[styles.primaryButton, busy ? styles.disabled : null]} disabled={busy} onPress={() => setConfirmPack(pack)}>
                      <Text style={styles.primaryText}>{busy ? 'Installing…' : pack.installed ? 'Reinstall' : 'Install'}</Text>
                    </Pressable>
                  ) : null}
                  {pack.installed && pack.removable ? (
                    <Pressable style={[styles.secondaryButton, busy ? styles.disabled : null]} disabled={busy} onPress={() => void remove(pack)}>
                      <Text style={styles.secondaryText}>Remove</Text>
                    </Pressable>
                  ) : null}
                </View>
              )}
            </View>
          );
        })}
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  section: { borderTopWidth: 1, borderTopColor: UI.color.border, paddingVertical: 20, gap: 10 },
  headingRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 14 },
  headingCopy: { flex: 1, minWidth: 0 },
  title: { color: UI.color.text, fontSize: 16, fontWeight: '700' },
  helper: { color: UI.color.textMuted, fontSize: 12, lineHeight: 18, marginTop: 4 },
  message: { color: UI.color.accentStrong, fontSize: 12 },
  refreshButton: { borderRadius: 8, paddingHorizontal: 11, paddingVertical: 7, backgroundColor: UI.color.surfaceRaised },
  refreshText: { color: UI.color.textMuted, fontSize: 11, fontWeight: '600' },
  toggle: { width: 42, height: 24, borderRadius: 12, padding: 3, backgroundColor: '#303741' },
  toggleOn: { backgroundColor: '#3abccd' },
  toggleKnob: { width: 18, height: 18, borderRadius: 9, backgroundColor: '#d6dbe1' },
  toggleKnobOn: { alignSelf: 'flex-end', backgroundColor: '#071417' },
  meta: { color: UI.color.textSubtle, fontSize: 10, lineHeight: 15 },
  packList: { gap: 0, paddingBottom: 20 },
  card: { borderTopWidth: 1, borderTopColor: UI.color.border, backgroundColor: 'transparent', paddingVertical: 16, gap: 10 },
  cardHighlighted: { borderLeftWidth: 2, borderLeftColor: UI.color.accent, backgroundColor: UI.color.accentSoft, paddingHorizontal: 14 },
  eyebrow: { color: UI.color.accentStrong, fontSize: 10, fontWeight: '600', letterSpacing: 0.7, textTransform: 'uppercase' },
  cardTitle: { color: UI.color.text, fontSize: 15, fontWeight: '700', marginTop: 3 },
  badge: { borderRadius: 999, paddingHorizontal: 9, paddingVertical: 4, backgroundColor: UI.color.surfaceRaised },
  badgeReady: { backgroundColor: UI.color.successSoft },
  badgeText: { color: '#a6afb9', fontSize: 9, fontWeight: '800', textTransform: 'uppercase' },
  badgeTextReady: { color: '#75dca6' },
  issue: { color: '#d8ad75', fontSize: 11 },
  progressBlock: { gap: 6 },
  progressTrack: { height: 5, borderRadius: 3, backgroundColor: '#303640', overflow: 'hidden' },
  progressFill: { height: 5, borderRadius: 3, backgroundColor: '#55d1df' },
  confirmCard: { borderTopWidth: 1, borderTopColor: UI.color.border, paddingTop: 11, gap: 8 },
  confirmTitle: { color: UI.color.text, fontSize: 13, fontWeight: '700' },
  actionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  primaryButton: { borderRadius: 8, backgroundColor: '#5bcbd9', paddingHorizontal: 12, paddingVertical: 8 },
  primaryText: { color: '#071114', fontSize: 11, fontWeight: '800' },
  secondaryButton: { borderRadius: 8, backgroundColor: UI.color.surfaceRaised, paddingHorizontal: 12, paddingVertical: 8 },
  secondaryText: { color: UI.color.textMuted, fontSize: 11, fontWeight: '600' },
  disabled: { opacity: 0.45 },
});
