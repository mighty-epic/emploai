import { useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  copyDesktopText,
  createDesktopFleetYggdrasilPairing,
  loadDesktopFleetYggdrasilStatus,
  type DesktopFleetYggdrasilPairing,
} from '@/lib/desktopBridge';
import { userFacingError } from '../../lib/diagnostics';
import { DESKTOP_UI as UI } from './desktopUiTokens';

export function DesktopFleetChildConnectionPanel({
  onClose,
  onChanged,
}: {
  onClose?: () => void;
  onChanged?: () => void;
}) {
  const [computerName, setComputerName] = useState('Additional computer');
  const [pairing, setPairing] = useState<DesktopFleetYggdrasilPairing | null>(null);
  const [nowSeconds, setNowSeconds] = useState(Math.floor(Date.now() / 1000));
  const [busy, setBusy] = useState(false);
  const [address, setAddress] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadDesktopFleetYggdrasilStatus().then((status) => setAddress(status?.address || null));
  }, []);

  useEffect(() => {
    if (!pairing) return undefined;
    const timer = globalThis.setInterval(() => setNowSeconds(Math.floor(Date.now() / 1000)), 1000);
    return () => globalThis.clearInterval(timer);
  }, [pairing]);

  const remaining = useMemo(
    () => pairing ? Math.max(0, Number(pairing.expiresAt || 0) - nowSeconds) : 0,
    [pairing, nowSeconds],
  );

  const createCode = async () => {
    setBusy(true);
    setError(null);
    setMessage('Preparing the private connection…');
    try {
      const result = await createDesktopFleetYggdrasilPairing(computerName, 30 * 60);
      if (!result?.pairingToken) throw new Error('A complete connection code was not returned.');
      setPairing(result);
      setNowSeconds(Math.floor(Date.now() / 1000));
      await copyDesktopText(result.pairingToken);
      const status = await loadDesktopFleetYggdrasilStatus();
      setAddress(status?.address || null);
      setMessage('Code created and copied. Paste it once into Fleet on the computer you are adding.');
      onChanged?.();
    } catch (createError) {
      setError(userFacingError(createError, 'The connection code could not be created.'));
      setMessage(null);
    } finally {
      setBusy(false);
    }
  };

  const copyCode = async () => {
    if (!pairing?.pairingToken || remaining <= 0) return;
    try {
      await copyDesktopText(pairing.pairingToken);
      setMessage('Connection code copied.');
    } catch (copyError) {
      setError(userFacingError(copyError, 'The connection code could not be copied.'));
    }
  };

  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;

  return (
    <View style={styles.panel} accessibilityLiveRegion="polite">
      <View style={styles.header}>
        <View style={styles.headerCopy}>
          <Text style={styles.eyebrow}>ADD BELOW THIS COMPUTER</Text>
          <Text style={styles.title}>Connect another computer</Text>
          <Text style={styles.detail}>This creates a direct child of this computer. The connection is local-only over Yggdrasil and reconnects after restarts.</Text>
        </View>
        {onClose ? (
          <Pressable accessibilityRole="button" accessibilityLabel="Close connection setup" onPress={onClose} style={styles.closeButton}>
            <Text style={styles.closeButtonText}>×</Text>
          </Pressable>
        ) : null}
      </View>

      {address ? (
        <View style={styles.addressRow}>
          <Text style={styles.addressLabel}>THIS COMPUTER</Text>
          <Text selectable style={styles.address}>{address}</Text>
        </View>
      ) : null}

      <View style={styles.form}>
        <Text style={styles.inputLabel}>Name shown in this Fleet</Text>
        <TextInput
          accessibilityLabel="Name for the computer being connected"
          value={computerName}
          onChangeText={setComputerName}
          placeholder="Example: Build VPS"
          placeholderTextColor={UI.color.textSubtle}
          style={styles.input}
        />
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: busy || !computerName.trim() }}
          disabled={busy || !computerName.trim()}
          onPress={() => void createCode()}
          style={[styles.primaryButton, (busy || !computerName.trim()) ? styles.disabled : null]}
        >
          <Text style={styles.primaryButtonText}>{busy ? 'Creating…' : 'Create & copy code'}</Text>
        </Pressable>
      </View>

      {pairing ? (
        <View style={[styles.codeBox, remaining <= 0 ? styles.codeExpired : null]}>
          <View style={styles.codeHeader}>
            <Text style={styles.codeLabel}>SINGLE-USE CODE</Text>
            <Text style={styles.expiry}>{remaining > 0 ? `${minutes}:${String(seconds).padStart(2, '0')} remaining` : 'Expired'}</Text>
          </View>
          <Text selectable numberOfLines={5} style={styles.code}>{pairing.pairingToken}</Text>
          <Pressable
            accessibilityRole="button"
            disabled={remaining <= 0}
            onPress={() => void copyCode()}
            style={[styles.secondaryButton, remaining <= 0 ? styles.disabled : null]}
          ><Text style={styles.secondaryButtonText}>Copy again</Text></Pressable>
        </View>
      ) : null}

      {error || message ? (
        <View style={[styles.notice, error ? styles.noticeError : null]}>
          <Text style={error ? styles.noticeErrorText : styles.noticeText}>{error || message}</Text>
        </View>
      ) : null}

      <Text style={styles.footnote}>On the other computer: open Fleet → Connect to a manager → paste this code. You do not need to copy Yggdrasil addresses or create a separate enrollment.</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { padding: 16, gap: 13, borderWidth: 1, borderColor: UI.color.accentBorder, borderRadius: UI.radius.large, backgroundColor: UI.color.canvas },
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  headerCopy: { flex: 1 },
  eyebrow: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  title: { marginTop: 4, color: UI.color.text, fontSize: 16, fontWeight: '900' },
  detail: { marginTop: 5, maxWidth: 680, color: UI.color.textMuted, fontSize: 10, lineHeight: 16 },
  closeButton: { width: 44, height: 44, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.control, alignItems: 'center', justifyContent: 'center' },
  closeButtonText: { color: UI.color.textMuted, fontSize: 20 },
  addressRow: { padding: 10, borderWidth: 1, borderColor: UI.color.border, borderRadius: UI.radius.control, backgroundColor: UI.color.surface },
  addressLabel: { color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: 7, fontWeight: '900', letterSpacing: 0.8 },
  address: { marginTop: 4, color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: 10 },
  form: { gap: 8 },
  inputLabel: { color: UI.color.textMuted, fontSize: 9, fontWeight: '800' },
  input: { minHeight: 44, paddingHorizontal: 11, borderWidth: 1, borderColor: UI.color.borderStrong, borderRadius: UI.radius.control, backgroundColor: UI.color.surface, color: UI.color.text, fontSize: 10 },
  primaryButton: { minHeight: 44, paddingHorizontal: 14, borderRadius: UI.radius.control, backgroundColor: UI.color.accent, alignItems: 'center', justifyContent: 'center' },
  primaryButtonText: { color: UI.color.accentInk, fontSize: 10, fontWeight: '900' },
  secondaryButton: { minHeight: 44, paddingHorizontal: 12, borderWidth: 1, borderColor: UI.color.accentBorder, borderRadius: UI.radius.control, backgroundColor: UI.color.accentSoft, alignItems: 'center', justifyContent: 'center' },
  secondaryButtonText: { color: UI.color.accentStrong, fontSize: 10, fontWeight: '900' },
  disabled: { opacity: 0.4 },
  codeBox: { padding: 11, gap: 9, borderWidth: 1, borderColor: UI.color.accentBorder, borderRadius: UI.radius.control, backgroundColor: UI.color.surface },
  codeExpired: { borderColor: UI.color.danger },
  codeHeader: { flexDirection: 'row', justifyContent: 'space-between', gap: 10 },
  codeLabel: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: 8, fontWeight: '900' },
  expiry: { color: UI.color.warning, fontFamily: UI.type.mono, fontSize: 8, fontWeight: '900' },
  code: { color: UI.color.textMuted, fontFamily: UI.type.mono, fontSize: 8, lineHeight: 13 },
  notice: { padding: 10, borderWidth: 1, borderColor: UI.color.accentBorder, borderRadius: UI.radius.control, backgroundColor: UI.color.accentSoft },
  noticeError: { borderColor: UI.color.danger, backgroundColor: UI.color.dangerSoft },
  noticeText: { color: UI.color.textMuted, fontSize: 9 },
  noticeErrorText: { color: UI.color.danger, fontSize: 9, fontWeight: '700' },
  footnote: { color: UI.color.textSubtle, fontSize: 9, lineHeight: 14 },
});
