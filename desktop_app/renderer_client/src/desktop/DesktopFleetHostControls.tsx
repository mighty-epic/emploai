import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import {
  checkDesktopFleetComputerUpdate,
  getDesktopFleetComputerHostStatus,
  getDesktopFleetComputerUpdateStatus,
  startDesktopFleetComputerDesktop,
  startDesktopFleetComputerRuntime,
  startDesktopFleetComputerUpdate,
  type DesktopFleetHostStatus,
  type DesktopFleetUpdateStatus,
} from '@/lib/desktopBridge';
import { userFacingError } from '../../lib/diagnostics';
import { DesktopFleetInfoButton } from './DesktopFleetInfoButton';
import { FLEET_TYPE as TYPE } from './desktopFleetUi';
import { DESKTOP_UI as UI } from './desktopUiTokens';

export function DesktopFleetHostControls({
  desktopId,
  desktopName,
  online,
  allowed,
  updateAllowed,
  supported,
  updateSupported,
}: {
  desktopId: string;
  desktopName: string;
  online: boolean;
  allowed: boolean;
  updateAllowed: boolean;
  supported: boolean;
  updateSupported: boolean;
}) {
  const [status, setStatus] = useState<DesktopFleetHostStatus | null>(null);
  const [updateStatus, setUpdateStatus] = useState<DesktopFleetUpdateStatus | null>(null);
  const [busy, setBusy] = useState<'status' | 'runtime' | 'desktop' | null>(null);
  const [updateBusy, setUpdateBusy] = useState<'status' | 'check' | 'start' | null>(null);
  const [confirmCommit, setConfirmCommit] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = async () => {
    if (!online || !supported) return;
    setBusy('status');
    setError(null);
    try {
      setStatus(await getDesktopFleetComputerHostStatus(desktopId));
    } catch (statusError) {
      setError(userFacingError(statusError, `Could not read ${desktopName} host status.`));
    } finally {
      setBusy(null);
    }
  };

  useEffect(() => {
    setStatus(null);
    setUpdateStatus(null);
    setConfirmCommit(null);
    setError(null);
    void loadStatus();
    if (online && updateSupported) {
      void getDesktopFleetComputerUpdateStatus(desktopId).then((next) => {
        if (next) setUpdateStatus(next);
      }).catch(() => null);
    }
  }, [desktopId, online, supported, updateSupported]);

  useEffect(() => {
    if (!online || !updateSupported || !updateStatus?.active) return undefined;
    const timer = setInterval(() => {
      void getDesktopFleetComputerUpdateStatus(desktopId).then((next) => {
        if (next) setUpdateStatus(next);
      }).catch(() => null);
    }, 2500);
    return () => clearInterval(timer);
  }, [desktopId, online, updateSupported, updateStatus?.active]);

  const run = async (
    action: 'runtime' | 'desktop',
    operation: () => Promise<DesktopFleetHostStatus | null>,
  ) => {
    setBusy(action);
    setError(null);
    try {
      const next = await operation();
      if (next) setStatus(next);
    } catch (actionError) {
      setError(userFacingError(actionError, `Could not start EmploAI on ${desktopName}.`));
    } finally {
      setBusy(null);
    }
  };

  const runtimeReady = Boolean(status?.runtime.ready);
  const desktopRunning = Boolean(status?.desktop.running);
  const disabled = Boolean(busy) || !online || !allowed || !supported;
  const updateCheck = updateStatus?.last_check || null;
  const updateJob = updateStatus?.job || null;
  const targetCommit = String(updateCheck?.target_commit || '');
  const completedCommit = updateJob?.state === 'completed' ? String(updateJob.current_commit || updateJob.target_commit || '') : '';
  const updateAvailable = Boolean(updateCheck?.update_available && updateCheck?.can_update && targetCommit && targetCommit !== completedCommit);
  const updateDisabled = Boolean(updateBusy) || Boolean(updateStatus?.active) || !online || !updateAllowed || !updateSupported;

  const checkUpdate = async () => {
    setUpdateBusy('check');
    setConfirmCommit(null);
    setError(null);
    try {
      const next = await checkDesktopFleetComputerUpdate(desktopId);
      if (next) setUpdateStatus(next);
    } catch (updateError) {
      setError(userFacingError(updateError, `Could not check ${desktopName} for updates.`));
    } finally {
      setUpdateBusy(null);
    }
  };

  const startUpdate = async () => {
    if (!targetCommit) return;
    if (confirmCommit !== targetCommit) {
      setConfirmCommit(targetCommit);
      return;
    }
    setUpdateBusy('start');
    setError(null);
    try {
      const next = await startDesktopFleetComputerUpdate(desktopId, targetCommit);
      if (next) setUpdateStatus(next);
      setConfirmCommit(null);
    } catch (updateError) {
      setError(userFacingError(updateError, `Could not update EmploAI on ${desktopName}.`));
    } finally {
      setUpdateBusy(null);
    }
  };

  return (
    <View style={styles.section} accessibilityLiveRegion="polite">
      <View style={styles.headingRow}>
        <View style={styles.headingCopy}>
          <Text style={styles.eyebrow}>ALWAYS-ON HOST</Text>
          <Text style={styles.title}>Recover EmploAI on {desktopName}</Text>
        </View>
        <DesktopFleetInfoButton
          label="Persistent Fleet host"
          text="This small authenticated process stays connected over Yggdrasil when the EmploAI window and backend are closed. It can start them again, but it cannot provide mouse or keyboard control."
        />
      </View>

      {!supported ? (
        <Text style={styles.warning}>Update EmploAI on this computer to enable independent recovery controls.</Text>
      ) : (
        <View style={styles.statusRow}>
          <Text style={[styles.status, online ? styles.statusReady : styles.statusMuted]}>{online ? '● HOST CONNECTED' : '○ HOST OFFLINE'}</Text>
          <Text style={[styles.status, runtimeReady ? styles.statusReady : styles.statusMuted]}>{runtimeReady ? '● BACKEND READY' : '○ BACKEND STOPPED'}</Text>
          <Text style={[styles.status, desktopRunning ? styles.statusReady : styles.statusMuted]}>{desktopRunning ? '● APP OPEN' : '○ APP CLOSED'}</Text>
          {status?.app_version ? <Text style={styles.version}>v{status.app_version}</Text> : null}
        </View>
      )}

      <View style={styles.actions}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Refresh ${desktopName} host status`}
          disabled={Boolean(busy) || !online || !supported}
          onPress={() => void loadStatus()}
          style={[styles.secondaryButton, (Boolean(busy) || !online || !supported) ? styles.disabled : null]}
        ><Text style={styles.secondaryText}>{busy === 'status' ? 'Checking…' : 'Refresh status'}</Text></Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Start ${desktopName} backend`}
          disabled={disabled || runtimeReady}
          onPress={() => void run('runtime', () => startDesktopFleetComputerRuntime(desktopId))}
          style={[styles.secondaryButton, (disabled || runtimeReady) ? styles.disabled : null]}
        ><Text style={styles.secondaryText}>{busy === 'runtime' ? 'Starting backend…' : runtimeReady ? 'Backend ready' : 'Start backend'}</Text></Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Open EmploAI on ${desktopName}`}
          disabled={disabled || desktopRunning}
          onPress={() => void run('desktop', () => startDesktopFleetComputerDesktop(desktopId))}
          style={[styles.primaryButton, (disabled || desktopRunning) ? styles.disabled : null]}
        ><Text style={styles.primaryText}>{busy === 'desktop' ? 'Opening EmploAI…' : desktopRunning ? 'EmploAI is open' : 'Open EmploAI'}</Text></Pressable>
      </View>
      {!allowed && supported ? <Text style={styles.warning}>That computer has not allowed its manager to start EmploAI.</Text> : null}

      <View style={styles.updatePanel}>
        <View style={styles.headingRow}>
          <View style={styles.headingCopy}>
            <Text style={styles.eyebrow}>REMOTE UPDATE</Text>
            <Text style={styles.title}>Update and restart this computer</Text>
          </View>
          <DesktopFleetInfoButton
            label="Remote EmploAI updates"
            text="Checks this computer’s configured Git branch, backs up local project changes, fast-forwards to the exact confirmed commit, installs dependency changes, rebuilds, and restarts the backend, desktop app, and persistent host. Diverged branches are never overwritten."
          />
        </View>

        {!updateSupported ? (
          <Text style={styles.warning}>This computer’s persistent host is too old to receive remote updates. Update it once locally first.</Text>
        ) : updateJob && updateJob.state !== 'completed' && updateJob.state !== 'failed' ? (
          <View style={styles.updateStatusCard}>
            <Text style={styles.updatePhase}>{String(updateJob.phase || updateJob.state).toUpperCase()}</Text>
            <Text style={styles.updateMessage}>{updateJob.message || 'Updating EmploAI…'}</Text>
            <Text style={styles.updateMeta}>Keep this computer online. Fleet may disconnect briefly while its persistent host reloads.</Text>
          </View>
        ) : updateJob?.state === 'completed' ? (
          <View style={styles.updateStatusCard}>
            <Text style={[styles.updatePhase, styles.statusReady]}>UPDATE COMPLETE</Text>
            <Text style={styles.updateMessage}>{updateJob.message || 'EmploAI was updated and restarted.'}</Text>
          </View>
        ) : updateJob?.state === 'failed' ? (
          <View style={[styles.updateStatusCard, styles.updateFailed]}>
            <Text style={[styles.updatePhase, styles.error]}>UPDATE FAILED</Text>
            <Text style={styles.updateMessage}>{updateJob.message || 'The remote update failed.'}</Text>
          </View>
        ) : updateCheck ? (
          <View style={styles.updateStatusCard}>
            <Text style={[styles.updatePhase, updateAvailable ? styles.statusReady : null]}>
              {updateAvailable ? 'UPDATE AVAILABLE' : String(updateCheck.state || 'CHECKED').toUpperCase()}
            </Text>
            <Text style={styles.updateMessage}>{updateCheck.message || 'Update status checked.'}</Text>
            <Text style={styles.updateMeta}>
              {updateCheck.branch || 'branch'} · {updateCheck.current_short_commit || 'unknown'}
              {updateAvailable ? ` → ${updateCheck.target_short_commit || targetCommit.slice(0, 8)}` : ''}
              {updateCheck.target_version ? ` · v${updateCheck.target_version}` : ''}
            </Text>
            {updateCheck.local_changes_will_be_preserved ? (
              <Text style={styles.warning}>{updateCheck.dirty_count} local project change{updateCheck.dirty_count === 1 ? '' : 's'} will be saved in an automatic Git backup.</Text>
            ) : null}
          </View>
        ) : null}

        <View style={styles.actions}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Check ${desktopName} for updates`}
            accessibilityState={{ disabled: updateDisabled }}
            disabled={updateDisabled}
            onPress={() => void checkUpdate()}
            style={[styles.secondaryButton, updateDisabled ? styles.disabled : null]}
          ><Text style={styles.secondaryText}>{updateBusy === 'check' ? 'Checking…' : 'Check for update'}</Text></Pressable>
          {updateAvailable ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Update and restart EmploAI on ${desktopName}`}
              accessibilityState={{ disabled: updateDisabled }}
              disabled={updateDisabled}
              onPress={() => void startUpdate()}
              style={[styles.primaryButton, updateDisabled ? styles.disabled : null]}
            ><Text style={styles.primaryText}>{updateBusy === 'start' ? 'Starting update…' : confirmCommit === targetCommit ? 'Confirm update & restart' : `Update to ${updateCheck?.target_short_commit || targetCommit.slice(0, 8)}`}</Text></Pressable>
          ) : null}
          {confirmCommit ? (
            <Pressable accessibilityRole="button" onPress={() => setConfirmCommit(null)} style={styles.secondaryButton}>
              <Text style={styles.secondaryText}>Cancel</Text>
            </Pressable>
          ) : null}
        </View>
        {!updateAllowed && updateSupported ? <Text style={styles.warning}>That computer has not allowed its manager to install updates.</Text> : null}
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    padding: 14,
    gap: 12,
    borderWidth: 0,
    borderRadius: UI.radius.panel,
    backgroundColor: UI.color.surfaceMuted,
  },
  headingRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 },
  headingCopy: { flex: 1, gap: 4 },
  eyebrow: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: TYPE.eyebrow, fontWeight: '900', letterSpacing: 0.8 },
  title: { color: UI.color.text, fontSize: TYPE.sectionTitle, fontWeight: '900' },
  statusRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 },
  status: { fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900' },
  statusReady: { color: UI.color.success },
  statusMuted: { color: UI.color.textSubtle },
  version: { marginLeft: 'auto', color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: TYPE.micro },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  updatePanel: { gap: 10, paddingTop: 12, borderTopWidth: 1, borderTopColor: UI.color.border },
  updateStatusCard: { gap: 5, padding: 12, borderWidth: 0, borderRadius: UI.radius.control, backgroundColor: UI.color.surface },
  updateFailed: { borderColor: UI.color.danger },
  updatePhase: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '900', letterSpacing: 0.7 },
  updateMessage: { color: UI.color.text, fontSize: TYPE.body, lineHeight: TYPE.bodyLine, fontWeight: '700' },
  updateMeta: { color: UI.color.textMuted, fontFamily: UI.type.mono, fontSize: TYPE.meta, lineHeight: TYPE.compactLine },
  primaryButton: { minHeight: 44, paddingHorizontal: 16, alignItems: 'center', justifyContent: 'center', borderRadius: UI.radius.control, backgroundColor: UI.color.accentStrong },
  primaryText: { color: UI.color.accentInk, fontSize: TYPE.body, fontWeight: '900' },
  secondaryButton: { minHeight: 44, paddingHorizontal: 14, alignItems: 'center', justifyContent: 'center', borderWidth: 0, borderRadius: UI.radius.control, backgroundColor: UI.color.surfaceRaised },
  secondaryText: { color: UI.color.text, fontSize: TYPE.body, fontWeight: '800' },
  disabled: { opacity: 0.42 },
  warning: { color: UI.color.warning, fontSize: TYPE.body, lineHeight: TYPE.bodyLine, fontWeight: '700' },
  error: { color: UI.color.danger, fontSize: TYPE.body, lineHeight: TYPE.bodyLine, fontWeight: '700' },
});
