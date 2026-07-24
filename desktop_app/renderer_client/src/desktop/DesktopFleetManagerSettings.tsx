import { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { setFleetIdentityToolPacks } from '@/lib/appApi';
import {
  loadDesktopFleetSnapshot,
  type DesktopFleetRemoteTarget,
  type DesktopFleetSnapshot,
} from '@/lib/desktopBridge';
import { userFacingError } from '../../lib/diagnostics';
import { DesktopFleetManagerTools } from './DesktopFleetManagerTools';
import { DESKTOP_UI as UI } from './desktopUiTokens';

export function DesktopFleetManagerSettings({
  apiBaseUrl,
  token,
}: {
  apiBaseUrl?: string | null;
  token?: string | null;
}) {
  const [snapshot, setSnapshot] = useState<DesktopFleetSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      setSnapshot(await loadDesktopFleetSnapshot());
    } catch (refreshError) {
      setError(userFacingError(refreshError, 'This computer’s manager settings could not be loaded.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const localManager = (snapshot?.identities || []).find((identity) => identity.role === 'manager') || null;
  const localManagerTarget: DesktopFleetRemoteTarget | null = localManager ? {
    target_kind: 'manager',
    target_selector: localManager.identity_id,
    identity_id: localManager.identity_id,
    display_name: localManager.display_name,
    role: 'manager',
    status: localManager.status,
    tool_profile: localManager.tool_profile,
    enabled_tool_packs: localManager.enabled_tool_packs,
    capability_tags: localManager.capability_tags,
  } : null;

  const save = async (enabledToolPacks: string[]) => {
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      if (!apiBaseUrl || !token || !localManager) throw new Error('The local app API is unavailable.');
      await setFleetIdentityToolPacks(apiBaseUrl, token, localManager.identity_id, enabledToolPacks);
      setMessage('This computer’s manager tools were updated.');
      await refresh();
      return true;
    } catch (saveError) {
      setError(userFacingError(saveError, 'The manager setting could not be changed.'));
      return false;
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.stack}>
      <View style={styles.header}>
        <Text style={styles.eyebrow}>THIS COMPUTER</Text>
        <Text style={styles.title}>{localManager?.display_name || 'Local manager'}</Text>
        <Text style={styles.body}>Manager Core handles coordination. Optional packs let this manager act directly; disabled work routes to the default worker.</Text>
      </View>
      {loading && !snapshot ? <Text style={styles.muted}>Loading manager…</Text> : null}
      {!loading && !localManager ? <Text style={styles.muted}>No local manager identity is available.</Text> : null}
      {localManager ? (
        <DesktopFleetManagerTools
          desktopId={`local:${localManager.identity_id}`}
          desktopName="this computer"
          manager={localManagerTarget}
          allowed={Boolean(apiBaseUrl && token)}
          online
          busy={busy}
          onSave={save}
        />
      ) : null}
      {message ? <Text style={styles.success}>{message}</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 12 },
  header: { gap: 5 },
  eyebrow: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: 10, fontWeight: '900', letterSpacing: 0.9 },
  title: { color: UI.color.text, fontSize: 21, fontWeight: '900' },
  body: { maxWidth: 720, color: UI.color.textMuted, fontSize: 13, lineHeight: 19 },
  muted: { color: UI.color.textSubtle, fontSize: 13 },
  success: { color: UI.color.success, fontSize: 12, fontWeight: '700' },
  error: { color: UI.color.danger, fontSize: 12, fontWeight: '700' },
});
