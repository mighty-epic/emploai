import { useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  bootstrapDesktopFleetYggdrasil,
  copyDesktopText,
  createDesktopFleetYggdrasilPairing,
  joinDesktopFleetYggdrasil,
  loadDesktopFleetYggdrasilStatus,
  setDesktopFleetConnectionPermissions,
  decideDesktopFleetPermissionRequest,
  type DesktopFleetYggdrasilPairing,
  type DesktopFleetYggdrasilStatus,
} from '@/lib/desktopBridge';
import { userFacingError } from '../../lib/diagnostics';
import { DesktopFleetInfoButton } from './DesktopFleetInfoButton';
import { FLEET_TYPE as TYPE } from './desktopFleetUi';
import { DESKTOP_UI as UI } from './desktopUiTokens';

type BusyAction = 'refresh' | 'bootstrap' | 'pair' | 'join' | 'permissions' | null;

function connectionSummary(status: DesktopFleetYggdrasilStatus | null) {
  if (!status) return 'Checking private network…';
  if (!status.available) return 'Private network is not installed';
  if (!status.running) return 'Private network is installed but stopped';
  if (status.connection?.configured) {
    const relay = status.connection.relayState ? ` · relay ${status.connection.relayState}` : '';
    const host = status.connection.hostRegistered ? ' · starts with Windows' : ' · background start needs repair';
    return `Paired to a Fleet manager${relay}${host}`;
  }
  return 'Private network ready · this desktop can manage paired computers';
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
  const [computerName, setComputerName] = useState('Additional computer');
  const [deviceName, setDeviceName] = useState('Additional computer');
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
  const connectedToManager = Boolean(status?.connection?.configured);
  const connectionPermissions = status?.connection?.permissions || {
    delegate_manager: true,
    delegate_workers: true,
    create_workers: false,
    configure_manager_tools: false,
    manage_runtime: true,
    manage_updates: true,
  };
  const pendingPermissionRequest = status?.connection?.pendingRequest as Record<string, any> | null | undefined;

  const updatePermission = async (key: keyof typeof connectionPermissions) => {
    setBusy('permissions');
    setError(null);
    try {
      await setDesktopFleetConnectionPermissions({ ...connectionPermissions, [key]: !connectionPermissions[key] });
      await refresh(true);
      setMessage('Connection permissions saved on this computer. The manager will see the change automatically.');
    } catch (permissionError) {
      setError(userFacingError(permissionError, 'Connection permissions could not be saved.'));
    } finally {
      setBusy(null);
    }
  };

  const decidePermission = async (approve: boolean) => {
    const requestId = String(pendingPermissionRequest?.requestId || '');
    if (!requestId) return;
    setBusy('permissions');
    setError(null);
    try {
      await decideDesktopFleetPermissionRequest(requestId, approve);
      await refresh(true);
      setMessage(approve ? 'Permission request approved.' : 'Permission request denied.');
    } catch (permissionError) {
      setError(userFacingError(permissionError, 'The permission request could not be decided.'));
    } finally {
      setBusy(null);
    }
  };

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
    setMessage('Preparing Yggdrasil and creating one code for this computer connection…');
    try {
      const result = await createDesktopFleetYggdrasilPairing(computerName, 30 * 60);
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
      setMessage('Pairing code copied. Paste it only into Fleet on the computer you want to connect.');
    } catch (copyError) {
      setError(userFacingError(copyError, 'The pairing code was not copied.'));
    }
  };

  const joinManager = async () => {
    setBusy('join');
    setError(null);
    setMessage('Preparing Yggdrasil, enrolling this computer, and saving its durable Fleet connection…');
    try {
      const result = await joinDesktopFleetYggdrasil(joinCode, deviceName);
      if (!result?.ok) throw new Error('The manager did not accept this desktop.');
      setJoinCode('');
      await refresh(true);
      setMessage(`Connected as ${result.deviceName || deviceName}. No agents or chats were copied; this pairing now survives restarts.`);
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
        </View>
        <View style={styles.headerActions}>
          <DesktopFleetInfoButton
            label="Private desktop network"
            text="One code connects the computers. No EmploAI account or hosted relay is involved; chats, agents, settings, files, and provider state stay local."
          />
          <View style={[styles.statusPill, networkReady ? styles.statusPillReady : null]}>
            <Text style={[styles.statusDot, networkReady ? styles.statusDotReady : null]}>{networkReady ? '●' : '○'}</Text>
            <Text style={styles.statusText}>{connectionSummary(status)}</Text>
          </View>
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
            <Text style={styles.stepText}>EmploAI prepares Yggdrasil, creates a computer-only enrollment, and copies one complete code for the other desktop.</Text>
            <Text style={styles.inputLabel}>Other computer’s name</Text>
            <TextInput
              accessibilityLabel="Name for the computer being connected"
              value={computerName}
              onChangeText={setComputerName}
              placeholder="Example: Windows VPS"
              placeholderTextColor={UI.color.textSubtle}
              style={styles.input}
            />
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Create and copy one Yggdrasil Fleet connection code"
              accessibilityState={{ disabled: busy !== null || connectedToManager }}
              disabled={busy !== null || connectedToManager}
              onPress={() => void createPairing()}
              style={[styles.primaryButton, (busy !== null || connectedToManager) ? styles.disabled : null]}
            >
              <Text style={styles.primaryButtonText}>{busy === 'pair' ? 'Preparing & Creating…' : 'Create & Copy Connection Code'}</Text>
            </Pressable>
            {connectedToManager ? <Text style={styles.roleHint}>This computer is already paired to a manager. Create additional codes on that manager computer.</Text> : null}
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
              accessibilityLabel="Name of this computer"
              value={deviceName}
              onChangeText={setDeviceName}
              placeholder="Example: Windows VPS"
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
              accessibilityLabel="Connect this computer to the Fleet manager"
              accessibilityState={{ disabled: busy !== null || !joinCode.trim() || connectedToManager }}
              disabled={busy !== null || !joinCode.trim() || connectedToManager}
              onPress={() => void joinManager()}
              style={[styles.secondaryButton, (busy !== null || !joinCode.trim() || connectedToManager) ? styles.disabled : null]}
            >
              <Text style={styles.secondaryButtonText}>{busy === 'join' ? 'Preparing & Connecting…' : connectedToManager ? 'Paired Permanently' : 'Connect This Computer'}</Text>
            </Pressable>
            {connectedToManager ? (
              <View style={styles.connectedDetail}>
                <Text style={styles.connectedTitle}>{status?.connection?.desktopName || 'Computer connected'}</Text>
                <Text style={styles.roleHint}>{status?.connection?.relayDetail || `Manager ${status?.connection?.managerYggdrasilIp || status?.connection?.managerUrl || ''}`}</Text>
                <Text style={status?.connection?.hostRegistered ? styles.hostReady : styles.hostWarning}>
                  {status?.connection?.hostRegistered ? '● BACKGROUND HOST READY' : '◐ BACKGROUND HOST NEEDS REPAIR'}
                </Text>
                <Text style={styles.roleHint}>{status?.connection?.hostDetail || 'Fleet will repair background startup the next time this desktop starts.'}</Text>
              </View>
            ) : null}
          </View>
        </View>

      {connectedToManager ? (
        <View style={styles.permissionSection}>
          <View style={styles.permissionHeading}>
            <View>
              <Text style={styles.stepLabel}>THIS COMPUTER CONTROLS ACCESS</Text>
              <Text style={styles.stepTitle}>What the paired manager may request</Text>
            </View>
            <Text style={styles.roleHint}>Changes stay on this computer and take effect immediately.</Text>
          </View>
          {pendingPermissionRequest ? (
            <View style={styles.permissionRequest} accessibilityLiveRegion="polite">
              <View style={styles.permissionRequestCopy}>
                <Text style={styles.connectedTitle}>Manager permission request</Text>
                <Text style={styles.roleHint}>{String(pendingPermissionRequest.reason || 'The manager requested different connection permissions.')}</Text>
              </View>
              <View style={styles.requestActions}>
                <Pressable accessibilityRole="button" accessibilityLabel="Deny manager permission request" accessibilityState={{ disabled: busy !== null }} disabled={busy !== null} onPress={() => void decidePermission(false)} style={styles.ghostButton}><Text style={styles.ghostButtonText}>Deny</Text></Pressable>
                <Pressable accessibilityRole="button" accessibilityLabel="Approve manager permission request" accessibilityState={{ disabled: busy !== null }} disabled={busy !== null} onPress={() => void decidePermission(true)} style={styles.secondaryButton}><Text style={styles.secondaryButtonText}>Approve</Text></Pressable>
              </View>
            </View>
          ) : null}
          <View style={styles.permissionGrid}>
            {([
              ['delegate_manager', 'Delegate to this computer’s manager agent', 'Task messages in; reports and requests out.'],
              ['delegate_workers', 'Delegate to existing local workers', 'The manager supplies a local worker name; identities are not copied.'],
              ['create_workers', 'Create new workers on this computer', 'Creates the worker here only when explicitly requested.'],
              ['configure_manager_tools', 'Configure this manager’s optional tools', 'Allows the directly connected manager above to change this manager’s execution packs. Manager Core always remains enabled.'],
              ['manage_runtime', 'Start EmploAI from the manager above', 'Keeps the small Yggdrasil host available and allows it to start this backend or desktop app when closed.'],
              ['manage_updates', 'Update EmploAI from the manager above', 'Allows a confirmed fast-forward source update with local-change backup, rebuild, restart, and recovery status.'],
            ] as const).map(([key, label, detail]) => {
              const enabled = Boolean(connectionPermissions[key]);
              return (
                <Pressable
                  key={key}
                  accessibilityRole="switch"
                  accessibilityHint={detail}
                  accessibilityState={{ checked: enabled, disabled: busy !== null }}
                  disabled={busy !== null}
                  onPress={() => void updatePermission(key)}
                  style={[styles.permissionRow, enabled ? styles.permissionRowEnabled : null]}
                >
                  <View style={styles.permissionCopy}>
                    <Text style={styles.permissionLabel}>{label}</Text>
                  </View>
                  <Text style={[styles.permissionValue, enabled ? styles.permissionValueOn : null]}>{enabled ? 'ALLOWED' : 'BLOCKED'}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      ) : null}

      <View style={styles.howToConnect}>
        <Text style={styles.stepLabel}>CONNECT TWO OR MORE COMPUTERS</Text>
        <DesktopFleetInfoButton
          label="Connecting two or more computers"
          text="Create one code on the manager for each additional computer, then paste each code once on its destination. Repeat from the same manager for computer three, four, and beyond; completed pairings reconnect after restarts."
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  shell: { borderWidth: 0, borderRadius: UI.radius.large, backgroundColor: UI.color.surfaceMuted, overflow: 'hidden' },
  header: { position: 'relative', zIndex: 20, padding: 18, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, backgroundColor: UI.color.accentSoft },
  headerCopy: { flex: 1, minWidth: 280 },
  headerActions: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'flex-end', gap: 6 },
  eyebrow: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: TYPE.eyebrow, fontWeight: '800', letterSpacing: 1.2 },
  title: { marginTop: 6, color: UI.color.text, fontSize: TYPE.heroTitle, fontWeight: '800' },
  statusPill: { minHeight: 36, maxWidth: 330, paddingHorizontal: 12, borderRadius: UI.radius.pill, borderWidth: 0, backgroundColor: UI.color.surface, flexDirection: 'row', alignItems: 'center', gap: 8 },
  statusPillReady: { borderColor: UI.color.accentBorder },
  statusDot: { color: UI.color.warning, fontSize: 12 },
  statusDotReady: { color: UI.color.success },
  statusText: { flexShrink: 1, color: UI.color.textMuted, fontSize: TYPE.body, fontWeight: '700' },
  notice: { minHeight: 34, paddingHorizontal: 18, paddingVertical: 9, borderTopWidth: 1, borderBottomWidth: 1, borderColor: UI.color.border, backgroundColor: UI.color.surface },
  noticeError: { backgroundColor: UI.color.dangerSoft, borderColor: UI.color.danger },
  noticeText: { color: UI.color.textMuted, fontSize: TYPE.body },
  errorText: { color: UI.color.danger, fontSize: TYPE.body, fontWeight: '700' },
  setupRow: { padding: 18, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 16 },
  setupCopy: { flex: 1, minWidth: 260 },
  addressRow: { paddingHorizontal: 18, paddingVertical: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, borderBottomWidth: 1, borderColor: UI.color.border },
  address: { marginTop: 4, color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: TYPE.control },
  roleGrid: { flexDirection: 'row', flexWrap: 'wrap' },
  rolePane: { flex: 1, minWidth: 300, padding: 18, gap: 9, borderBottomWidth: 1, borderRightWidth: 1, borderColor: UI.color.border },
  stepLabel: { color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: TYPE.eyebrow, fontWeight: '800', letterSpacing: 1 },
  stepTitle: { color: UI.color.text, fontSize: TYPE.sectionTitle, fontWeight: '800' },
  stepText: { color: UI.color.textMuted, fontSize: TYPE.body, lineHeight: TYPE.bodyLine },
  inputLabel: { marginTop: 3, color: UI.color.textMuted, fontSize: TYPE.body, fontWeight: '700' },
  input: { minHeight: 48, paddingHorizontal: 12, paddingVertical: 10, borderRadius: UI.radius.control, borderWidth: 1, borderColor: UI.color.borderStrong, backgroundColor: UI.color.canvas, color: UI.color.text, fontSize: TYPE.control },
  codeInput: { minHeight: 76, fontFamily: UI.type.mono, textAlignVertical: 'top' },
  primaryButton: { minHeight: 44, paddingHorizontal: 15, borderRadius: UI.radius.control, backgroundColor: UI.color.accent, alignItems: 'center', justifyContent: 'center' },
  primaryButtonText: { color: UI.color.accentInk, fontSize: TYPE.body, fontWeight: '900' },
  secondaryButton: { minHeight: 44, paddingHorizontal: 15, borderRadius: UI.radius.control, borderWidth: 0, backgroundColor: UI.color.accentSoft, alignItems: 'center', justifyContent: 'center' },
  secondaryButtonText: { color: UI.color.accentStrong, fontSize: TYPE.body, fontWeight: '800' },
  ghostButton: { minHeight: 44, paddingHorizontal: 13, borderRadius: UI.radius.control, borderWidth: 0, backgroundColor: UI.color.surfaceRaised, alignItems: 'center', justifyContent: 'center' },
  ghostButtonText: { color: UI.color.textMuted, fontSize: TYPE.body, fontWeight: '800' },
  disabled: { opacity: 0.42 },
  codeBox: { marginTop: 3, padding: 12, gap: 9, borderRadius: UI.radius.panel, borderWidth: 1, borderColor: UI.color.accentBorder, backgroundColor: UI.color.canvas },
  codeBoxExpired: { borderColor: UI.color.danger },
  codeHeader: { flexDirection: 'row', justifyContent: 'space-between', gap: 12 },
  codeLabel: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '800' },
  codeExpiry: { color: UI.color.warning, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '800' },
  code: { color: UI.color.textMuted, fontFamily: UI.type.mono, fontSize: TYPE.meta, lineHeight: TYPE.compactLine },
  roleHint: { color: UI.color.textSubtle, fontSize: TYPE.body, lineHeight: TYPE.bodyLine },
  connectedDetail: { padding: 11, borderRadius: UI.radius.control, borderWidth: 0, backgroundColor: UI.color.surface },
  connectedTitle: { color: UI.color.success, fontSize: TYPE.control, fontWeight: '800' },
  hostReady: { marginTop: 8, color: UI.color.success, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  hostWarning: { marginTop: 8, color: UI.color.warning, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  permissionSection: { padding: 18, gap: 12, borderTopWidth: 1, borderColor: UI.color.border, backgroundColor: UI.color.surface },
  permissionHeading: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12 },
  permissionGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  permissionRow: { flexGrow: 1, flexBasis: 300, minWidth: 260, minHeight: 64, padding: 11, borderWidth: 0, borderRadius: UI.radius.control, backgroundColor: UI.color.canvas, flexDirection: 'row', alignItems: 'center', gap: 12 },
  permissionRowEnabled: { backgroundColor: UI.color.accentSoft },
  permissionCopy: { flex: 1, gap: 3 },
  permissionLabel: { color: UI.color.text, fontSize: TYPE.body, fontWeight: '800' },
  permissionValue: { color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  permissionValueOn: { color: UI.color.success },
  permissionRequest: { padding: 11, borderWidth: 0, borderRadius: UI.radius.control, backgroundColor: UI.color.warningSoft, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 12 },
  permissionRequestCopy: { flex: 1, minWidth: 240, gap: 4 },
  requestActions: { flexDirection: 'row', gap: 8 },
  howToConnect: { position: 'relative', zIndex: 20, paddingHorizontal: 18, paddingVertical: 8, borderTopWidth: 1, borderColor: UI.color.border, backgroundColor: UI.color.canvas, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
});
