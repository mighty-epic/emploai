import { useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  bootstrapDesktopFleetYggdrasil,
  copyDesktopText,
  createDesktopFleetYggdrasilPairing,
  joinDesktopFleetYggdrasil,
  loadDesktopFleetYggdrasilStatus,
  type DesktopFleetYggdrasilPairing,
  type DesktopFleetYggdrasilStatus,
} from '@/lib/desktopBridge';
import { userFacingError } from '../../lib/diagnostics';
import { DESKTOP_UI as UI } from './desktopUiTokens';

type BusyAction = 'refresh' | 'bootstrap' | 'pair' | 'join' | null;

function connectionSummary(status: DesktopFleetYggdrasilStatus | null) {
  if (!status) return 'Checking private network…';
  if (!status.available) return 'Private network is not installed';
  if (!status.running) return 'Private network is installed but stopped';
  if (status.connection?.configured) {
    const relay = status.connection.relayState ? ` · relay ${status.connection.relayState}` : '';
    return `Connected to a Fleet manager${relay}`;
  }
  return 'Private network ready · this desktop can manage workers';
}

function formatRemaining(seconds: number) {
  if (seconds <= 0) return 'expired';
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return minutes ? `${minutes}m ${remainder}s` : `${remainder}s`;
}

export function DesktopFleetConnectionPanel({ onFleetChanged }: { onFleetChanged?: () => void }) {
  const [status, setStatus] = useState<DesktopFleetYggdrasilStatus | null>(null);
  const [busy, setBusy] = useState<BusyAction>('refresh');
  const [message, setMessage] = useState('Checking how this desktop is connected…');
  const [error, setError] = useState<string | null>(null);
  const [pairing, setPairing] = useState<DesktopFleetYggdrasilPairing | null>(null);
  const [workerName, setWorkerName] = useState('Remote worker');
  const [deviceName, setDeviceName] = useState('EmploAI worker');
  const [joinCode, setJoinCode] = useState('');
  const [nowSeconds, setNowSeconds] = useState(() => Math.floor(Date.now() / 1000));

  const refresh = async (quiet = false) => {
    if (!quiet) setBusy('refresh');
    setError(null);
    try {
      const next = await loadDesktopFleetYggdrasilStatus();
      if (!next) throw new Error('The desktop Fleet connection bridge is unavailable.');
      setStatus(next);
      if (!quiet) setMessage(connectionSummary(next));
    } catch (refreshError) {
      setError(userFacingError(refreshError, 'Fleet connection status could not be checked.'));
    } finally {
      if (!quiet) setBusy(null);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (!pairing) return undefined;
    const timer = globalThis.setInterval(() => setNowSeconds(Math.floor(Date.now() / 1000)), 1000);
    return () => globalThis.clearInterval(timer);
  }, [pairing]);

  const pairingRemaining = useMemo(
    () => pairing ? Math.max(0, Number(pairing.expiresAt || 0) - nowSeconds) : 0,
    [pairing, nowSeconds],
  );
  const networkReady = Boolean(status?.running && status?.address);
  const connectedAsWorker = Boolean(status?.connection?.configured);

  const prepareNetwork = async () => {
    setBusy('bootstrap');
    setError(null);
    setMessage('Installing or starting Yggdrasil. Windows may ask for administrator approval…');
    try {
      const result = await bootstrapDesktopFleetYggdrasil();
      if (!result || result.ok === false) throw new Error('Yggdrasil did not become ready.');
      await refresh(true);
      setMessage('Private network ready. This desktop can now create or accept Fleet pairing codes.');
    } catch (setupError) {
      setError(userFacingError(setupError, 'The private Fleet network could not be prepared.'));
    } finally {
      setBusy(null);
    }
  };

  const createPairing = async () => {
    setBusy('pair');
    setError(null);
    setMessage('Preparing Yggdrasil and creating one code for both the private connection and worker enrollment…');
    try {
      const result = await createDesktopFleetYggdrasilPairing(workerName, 30 * 60);
      if (!result?.pairingToken) throw new Error('A complete Yggdrasil pairing code was not returned.');
      setPairing(result);
      setNowSeconds(Math.floor(Date.now() / 1000));
      await refresh(true);
      try {
        await copyDesktopText(result.pairingToken);
        setMessage('Connection code created and copied. Paste it once into Fleet on the other desktop.');
      } catch {
        setMessage('Connection code created. Copy it below and paste it once into Fleet on the other desktop.');
      }
    } catch (pairError) {
      setError(userFacingError(pairError, 'A Fleet pairing code could not be created.'));
    } finally {
      setBusy(null);
    }
  };

  const copyPairing = async () => {
    if (!pairing?.pairingToken) return;
    try {
      await copyDesktopText(pairing.pairingToken);
      setMessage('Pairing code copied. Paste it only into Fleet on the worker desktop.');
    } catch (copyError) {
      setError(userFacingError(copyError, 'The pairing code was not copied.'));
    }
  };

  const joinManager = async () => {
    setBusy('join');
    setError(null);
    setMessage('Preparing Yggdrasil, enrolling this worker, and saving its permanent Fleet connection…');
    try {
      const result = await joinDesktopFleetYggdrasil(joinCode, deviceName);
      if (!result?.ok) throw new Error('The manager did not accept this desktop.');
      setJoinCode('');
      await refresh(true);
      setMessage(`Connected as ${result.deviceName || deviceName}. This pairing now survives restarts until the manager removes the worker.`);
      onFleetChanged?.();
    } catch (joinError) {
      setError(userFacingError(joinError, 'This desktop could not join the Fleet. Check that both desktops are online and the code has not expired.'));
    } finally {
      setBusy(null);
    }
  };

  return (
    <View style={styles.shell}>
      <View style={styles.header}>
        <View style={styles.headerCopy}>
          <Text style={styles.eyebrow}>PRIVATE DESKTOP NETWORK</Text>
          <Text style={styles.title}>Connect computers with Yggdrasil</Text>
          <Text style={styles.description}>
            One code prepares the direct connection and enrolls the worker. No EmploAI account, hosted relay, or remote input.
          </Text>
        </View>
        <View style={[styles.statusPill, networkReady ? styles.statusPillReady : null]}>
          <Text style={[styles.statusDot, networkReady ? styles.statusDotReady : null]}>{networkReady ? '●' : '○'}</Text>
          <Text style={styles.statusText}>{connectionSummary(status)}</Text>
        </View>
      </View>

      <View accessibilityLiveRegion="polite" style={[styles.notice, error ? styles.noticeError : null]}>
        <Text style={error ? styles.errorText : styles.noticeText}>{error || message}</Text>
      </View>

      {!networkReady ? (
        <View style={styles.setupRow}>
          <View style={styles.setupCopy}>
            <Text style={styles.stepLabel}>OPTIONAL TROUBLESHOOTING</Text>
            <Text style={styles.stepTitle}>Prepare or repair the private network</Text>
            <Text style={styles.stepText}>
              Create or Connect below does this automatically. Use this button only if you want to prepare Yggdrasil first or repair it.
            </Text>
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Set up the Yggdrasil private network"
            accessibilityState={{ disabled: busy !== null }}
            disabled={busy !== null}
            onPress={() => void prepareNetwork()}
            style={[styles.primaryButton, busy !== null ? styles.disabled : null]}
          >
            <Text style={styles.primaryButtonText}>{busy === 'bootstrap' ? 'Preparing…' : 'Prepare / Repair Network'}</Text>
          </Pressable>
        </View>
      ) : (
        <View style={styles.addressRow}>
          <View>
            <Text style={styles.stepLabel}>THIS DESKTOP</Text>
            <Text selectable style={styles.address}>{status?.address}</Text>
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Refresh Fleet connection status"
            disabled={busy !== null}
            onPress={() => void refresh()}
            style={[styles.ghostButton, busy !== null ? styles.disabled : null]}
          >
            <Text style={styles.ghostButtonText}>{busy === 'refresh' ? 'Checking…' : 'Refresh'}</Text>
          </Pressable>
        </View>
      )}

      <View style={styles.roleGrid}>
          <View style={styles.rolePane}>
            <Text style={styles.stepLabel}>ON THE MANAGER</Text>
            <Text style={styles.stepTitle}>1. Create the single connection code</Text>
            <Text style={styles.stepText}>EmploAI prepares Yggdrasil, creates the enrollment, and copies one complete code for the other desktop.</Text>
            <Text style={styles.inputLabel}>Worker name</Text>
            <TextInput
              accessibilityLabel="Name for the remote Fleet worker"
              value={workerName}
              onChangeText={setWorkerName}
              placeholder="Remote worker"
              placeholderTextColor={UI.color.textSubtle}
              style={styles.input}
            />
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Create and copy one Yggdrasil Fleet connection code"
              accessibilityState={{ disabled: busy !== null || connectedAsWorker }}
              disabled={busy !== null || connectedAsWorker}
              onPress={() => void createPairing()}
              style={[styles.primaryButton, (busy !== null || connectedAsWorker) ? styles.disabled : null]}
            >
              <Text style={styles.primaryButtonText}>{busy === 'pair' ? 'Preparing & Creating…' : 'Create & Copy Connection Code'}</Text>
            </Pressable>
            {connectedAsWorker ? <Text style={styles.roleHint}>This desktop is already configured as a worker. Create codes from its manager instead.</Text> : null}
            {pairing ? (
              <View style={[styles.codeBox, pairingRemaining === 0 ? styles.codeBoxExpired : null]}>
                <View style={styles.codeHeader}>
                  <Text style={styles.codeLabel}>SINGLE-USE CONNECTION CODE</Text>
                  <Text style={styles.codeExpiry}>{formatRemaining(pairingRemaining)}</Text>
                </View>
                <Text selectable numberOfLines={4} style={styles.code}>{pairing.pairingToken}</Text>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Copy Fleet pairing code"
                  disabled={pairingRemaining === 0}
                  onPress={() => void copyPairing()}
                  style={[styles.secondaryButton, pairingRemaining === 0 ? styles.disabled : null]}
                >
                  <Text style={styles.secondaryButtonText}>Copy Code</Text>
                </Pressable>
              </View>
            ) : null}
          </View>

          <View style={styles.rolePane}>
            <Text style={styles.stepLabel}>ON THE OTHER DESKTOP</Text>
            <Text style={styles.stepTitle}>2. Paste once and connect</Text>
            <Text style={styles.stepText}>EmploAI prepares Yggdrasil automatically, enrolls this machine, and saves a durable connection.</Text>
            <Text style={styles.inputLabel}>This desktop’s name</Text>
            <TextInput
              accessibilityLabel="Name of this worker desktop"
              value={deviceName}
              onChangeText={setDeviceName}
              placeholder="EmploAI worker"
              placeholderTextColor={UI.color.textSubtle}
              style={styles.input}
            />
            <Text style={styles.inputLabel}>Pairing code from the manager</Text>
            <TextInput
              accessibilityLabel="Yggdrasil Fleet pairing code from the manager"
              value={joinCode}
              onChangeText={setJoinCode}
              placeholder="emploai-yggdrasil-v1…"
              placeholderTextColor={UI.color.textSubtle}
              autoCapitalize="none"
              autoCorrect={false}
              multiline
              style={[styles.input, styles.codeInput]}
            />
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Connect this desktop to the Fleet manager as a worker"
              accessibilityState={{ disabled: busy !== null || !joinCode.trim() || connectedAsWorker }}
              disabled={busy !== null || !joinCode.trim() || connectedAsWorker}
              onPress={() => void joinManager()}
              style={[styles.secondaryButton, (busy !== null || !joinCode.trim() || connectedAsWorker) ? styles.disabled : null]}
            >
              <Text style={styles.secondaryButtonText}>{busy === 'join' ? 'Preparing & Connecting…' : connectedAsWorker ? 'Connected Permanently' : 'Connect This Desktop'}</Text>
            </Pressable>
            {connectedAsWorker ? (
              <View style={styles.connectedDetail}>
                <Text style={styles.connectedTitle}>{status?.connection?.workerName || status?.connection?.desktopName || 'Worker connected'}</Text>
                <Text style={styles.roleHint}>{status?.connection?.relayDetail || `Manager ${status?.connection?.managerYggdrasilIp || status?.connection?.managerUrl || ''}`}</Text>
              </View>
            ) : null}
          </View>
        </View>

      <Text style={styles.footerText}>
        The code expires after one use or 30 minutes; the completed connection does not expire. It reconnects after restarts until the manager resets or removes that worker.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  shell: { borderWidth: 1, borderColor: UI.color.accentBorder, borderRadius: UI.radius.large, backgroundColor: UI.color.surfaceMuted, overflow: 'hidden' },
  header: { padding: 18, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, backgroundColor: UI.color.accentSoft },
  headerCopy: { flex: 1, minWidth: 280 },
  eyebrow: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: 10, fontWeight: '800', letterSpacing: 1.2 },
  title: { marginTop: 5, color: UI.color.text, fontSize: 18, fontWeight: '800' },
  description: { marginTop: 6, color: UI.color.textMuted, fontSize: 12, lineHeight: 18, maxWidth: 620 },
  statusPill: { minHeight: 36, maxWidth: 330, paddingHorizontal: 12, borderRadius: UI.radius.pill, borderWidth: 1, borderColor: UI.color.borderStrong, backgroundColor: UI.color.surface, flexDirection: 'row', alignItems: 'center', gap: 8 },
  statusPillReady: { borderColor: UI.color.accentBorder },
  statusDot: { color: UI.color.warning, fontSize: 12 },
  statusDotReady: { color: UI.color.success },
  statusText: { flexShrink: 1, color: UI.color.textMuted, fontSize: 10, fontWeight: '700' },
  notice: { minHeight: 34, paddingHorizontal: 18, paddingVertical: 9, borderTopWidth: 1, borderBottomWidth: 1, borderColor: UI.color.border, backgroundColor: UI.color.surface },
  noticeError: { backgroundColor: UI.color.dangerSoft, borderColor: UI.color.danger },
  noticeText: { color: UI.color.textMuted, fontSize: 11 },
  errorText: { color: UI.color.danger, fontSize: 11, fontWeight: '700' },
  setupRow: { padding: 18, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 16 },
  setupCopy: { flex: 1, minWidth: 260 },
  addressRow: { paddingHorizontal: 18, paddingVertical: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, borderBottomWidth: 1, borderColor: UI.color.border },
  address: { marginTop: 3, color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: 12 },
  roleGrid: { flexDirection: 'row', flexWrap: 'wrap' },
  rolePane: { flex: 1, minWidth: 300, padding: 18, gap: 9, borderBottomWidth: 1, borderRightWidth: 1, borderColor: UI.color.border },
  stepLabel: { color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  stepTitle: { color: UI.color.text, fontSize: 14, fontWeight: '800' },
  stepText: { color: UI.color.textMuted, fontSize: 11, lineHeight: 17 },
  inputLabel: { marginTop: 3, color: UI.color.textMuted, fontSize: 10, fontWeight: '700' },
  input: { minHeight: 44, paddingHorizontal: 12, paddingVertical: 10, borderRadius: UI.radius.control, borderWidth: 1, borderColor: UI.color.borderStrong, backgroundColor: UI.color.canvas, color: UI.color.text, fontSize: 12 },
  codeInput: { minHeight: 76, fontFamily: UI.type.mono, textAlignVertical: 'top' },
  primaryButton: { minHeight: 44, paddingHorizontal: 15, borderRadius: UI.radius.control, backgroundColor: UI.color.accent, alignItems: 'center', justifyContent: 'center' },
  primaryButtonText: { color: UI.color.accentInk, fontSize: 11, fontWeight: '900' },
  secondaryButton: { minHeight: 44, paddingHorizontal: 15, borderRadius: UI.radius.control, borderWidth: 1, borderColor: UI.color.accentBorder, backgroundColor: UI.color.accentSoft, alignItems: 'center', justifyContent: 'center' },
  secondaryButtonText: { color: UI.color.accentStrong, fontSize: 11, fontWeight: '800' },
  ghostButton: { minHeight: 40, paddingHorizontal: 13, borderRadius: UI.radius.control, borderWidth: 1, borderColor: UI.color.border, alignItems: 'center', justifyContent: 'center' },
  ghostButtonText: { color: UI.color.textMuted, fontSize: 10, fontWeight: '800' },
  disabled: { opacity: 0.42 },
  codeBox: { marginTop: 3, padding: 12, gap: 9, borderRadius: UI.radius.panel, borderWidth: 1, borderColor: UI.color.accentBorder, backgroundColor: UI.color.canvas },
  codeBoxExpired: { borderColor: UI.color.danger },
  codeHeader: { flexDirection: 'row', justifyContent: 'space-between', gap: 12 },
  codeLabel: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: 9, fontWeight: '800' },
  codeExpiry: { color: UI.color.warning, fontFamily: UI.type.mono, fontSize: 9, fontWeight: '800' },
  code: { color: UI.color.textMuted, fontFamily: UI.type.mono, fontSize: 9, lineHeight: 14 },
  roleHint: { color: UI.color.textSubtle, fontSize: 10, lineHeight: 15 },
  connectedDetail: { padding: 11, borderRadius: UI.radius.control, borderWidth: 1, borderColor: UI.color.border, backgroundColor: UI.color.surface },
  connectedTitle: { color: UI.color.success, fontSize: 11, fontWeight: '800' },
  footerText: { paddingHorizontal: 18, paddingVertical: 13, color: UI.color.textSubtle, fontSize: 10, lineHeight: 15 },
});
