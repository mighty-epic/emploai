import { useEffect, useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Link, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { CameraView, useCameraPermissions, type BarcodeScanningResult } from 'expo-camera';

import {
  fetchRemoteDesktops,
  remoteCompletePairing,
  type RemoteDesktop,
  type RemoteAccountProfile,
} from '../src/lib/appApi';
import { loadAppConfig, saveAppConfig } from '../lib/appConfig';
import { reconcileRemoteAccountConfig } from '../lib/accountSession';
import { PageHeader } from '../src/components/PageHeader';
import { shortStatusText, userFacingError } from '../lib/diagnostics';
import { InfoHint } from '../src/components/InfoHint';
import { extractPairingTokenFromInput } from '../src/lib/pairingQr';

type StepState = 'idle' | 'working' | 'done' | 'error';

type PairStep = {
  key: string;
  label: string;
  detail: string;
  state: StepState;
};

export default function PairScreen() {
  const router = useRouter();
  const [apiBaseUrl, setApiBaseUrl] = useState('');
  const [token, setToken] = useState('');
  const [pairingToken, setPairingToken] = useState('');
  const [profile, setProfile] = useState<RemoteAccountProfile | null>(null);
  const [desktops, setDesktops] = useState<RemoteDesktop[]>([]);
  const [busy, setBusy] = useState(false);
  const [scannerOpen, setScannerOpen] = useState(false);
  const [scanLocked, setScanLocked] = useState(false);
  const [scannerStatus, setScannerStatus] = useState('');
  const [status, setStatus] = useState('checking account');
  const [cameraPermission, requestCameraPermission] = useCameraPermissions();
  const [steps, setSteps] = useState<PairStep[]>([
    { key: 'cloud', label: 'Account', detail: 'Waiting for account check.', state: 'idle' },
    { key: 'desktop', label: 'Desktop bridge', detail: 'Waiting for desktop presence.', state: 'idle' },
    { key: 'token', label: 'Pairing QR', detail: 'Scan the desktop QR, or paste its fallback code.', state: 'idle' },
    { key: 'sync', label: 'Shared state', detail: 'Waiting for first sync.', state: 'idle' },
  ]);

  const setStep = (key: string, state: StepState, detail: string) => {
    setSteps((prev) => prev.map((step) => step.key === key ? { ...step, state, detail } : step));
  };

  const refresh = async () => {
    setBusy(true);
    setStatus('checking account');
    setStep('cloud', 'working', 'Checking saved session.');
    try {
      const { config, profile: reconciledProfile } = await reconcileRemoteAccountConfig(await loadAppConfig());
      const accountToken = config.accountToken || config.accessToken;
      setApiBaseUrl(config.apiBaseUrl);
      setToken(accountToken);
      if (!accountToken) {
        setStep('cloud', 'error', 'Sign in before pairing this phone.');
        setStatus('not signed in');
        router.replace('/auth');
        return;
      }
      const [nextProfile, nextDesktops] = await Promise.all([
        reconciledProfile ? Promise.resolve(reconciledProfile) : reconcileRemoteAccountConfig(config).then((result) => result.profile),
        fetchRemoteDesktops(config.apiBaseUrl, accountToken).catch(() => []),
      ]);
      if (!nextProfile) {
        throw new Error('Account session expired. Sign in again.');
      }
      setProfile(nextProfile);
      setDesktops(Array.isArray(nextDesktops) ? nextDesktops : []);
      setStep('cloud', 'done', 'Signed in.');
      const connectedDesktop = nextDesktops.find((desktop) => desktop.status === 'connected');
      if (connectedDesktop) {
        setStep('desktop', 'done', 'Desktop online.');
      } else if (nextDesktops.length) {
        setStep('desktop', 'error', 'A desktop exists, but it is not online yet.');
      } else {
        setStep('desktop', 'error', 'Sign in on the desktop app, then create a pairing QR.');
      }
      if (nextProfile.mobile?.paired_desktop_id) {
        setStep('token', 'done', 'This phone is already paired.');
        setStep('sync', 'done', 'Shared state is available.');
        setStatus('phone paired');
      } else {
        setStatus('ready for desktop pairing QR');
      }
    } catch (error) {
      const message = userFacingError(error, 'Account check failed.');
      setStep('cloud', 'error', message);
      setStatus(message);
    } finally {
      setBusy(false);
    }
  };

  const completePairing = async (rawPairingInput: string, source: 'manual' | 'qr') => {
    const cleanToken = extractPairingTokenFromInput(rawPairingInput, { allowRawToken: true });
    if (!apiBaseUrl || !token) {
      router.replace('/auth');
      return;
    }
    if (!cleanToken) {
      const message = source === 'qr'
        ? 'Scan the pairing QR shown on the desktop app.'
        : 'Paste the one-time code shown on desktop.';
      setStep('token', 'error', message);
      setStatus(source === 'qr' ? 'pairing QR required' : 'pairing code required');
      return;
    }

    setBusy(true);
    setStatus(source === 'qr' ? 'pairing from QR' : 'pairing with desktop');
    setStep('token', 'working', source === 'qr' ? 'Checking scanned pairing QR.' : 'Checking one-time pairing code.');
    setStep('sync', 'idle', 'Waiting for desktop sync.');
    try {
      setPairingToken(cleanToken);
      const result = await remoteCompletePairing(apiBaseUrl, token, cleanToken);
      const currentConfig = await loadAppConfig();
      await saveAppConfig({
        ...currentConfig,
        apiBaseUrl,
        accessToken: token,
        accountToken: token,
        pairedDesktopId: result.desktop.desktop_id,
        connectionMode: 'remote_cloud',
      });
      setStep('token', 'done', 'Code accepted.');
      setStep('sync', 'working', 'Refreshing shared desktop state.');
      const { profile: nextProfile } = await reconcileRemoteAccountConfig(await loadAppConfig());
      if (!nextProfile) {
        throw new Error('Pairing completed, but account refresh failed. Reopen this screen.');
      }
      setProfile(nextProfile);
      setStep('sync', 'done', 'Chat and sidebar state are synced.');
      setStatus('paired and ready');
      router.replace('/chat');
    } catch (error) {
      const message = userFacingError(error, 'Pairing failed.');
      setStep('token', 'error', message);
      setStatus(message);
    } finally {
      setBusy(false);
      setScanLocked(false);
    }
  };

  const pair = async () => {
    await completePairing(pairingToken, 'manual');
  };

  const openScanner = async () => {
    if (!apiBaseUrl || !token) {
      router.replace('/auth');
      return;
    }
    setScannerStatus('Preparing camera.');
    if (!cameraPermission?.granted) {
      const nextPermission = await requestCameraPermission();
      if (!nextPermission.granted) {
        const message = 'Camera permission is needed to scan the pairing QR. You can still paste the code.';
        setScannerStatus(message);
        setStep('token', 'error', message);
        setStatus('camera permission needed');
        return;
      }
    }
    setScanLocked(false);
    setScannerStatus('Point the camera at the QR code on the desktop app.');
    setScannerOpen(true);
  };

  const handleQrScanned = (result: BarcodeScanningResult) => {
    if (scanLocked || busy) {
      return;
    }
    const cleanToken = extractPairingTokenFromInput(result.data, { allowRawToken: true });
    if (!cleanToken) {
      setScannerStatus('That QR code does not contain a Kraitos pairing token.');
      return;
    }
    setScanLocked(true);
    setScannerStatus('QR accepted. Pairing this phone.');
    setScannerOpen(false);
    void completePairing(cleanToken, 'qr');
  };

  useEffect(() => {
    void refresh();
  }, []);

  const pairedDesktop = profile?.mobile?.paired_desktop_id || '';

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <PageHeader
          eyebrow="Pair phone"
          title="Connect to your desktop"
          subtitle="Scan the one-time QR shown on the desktop app while signed into this same account."
        />

        <Modal transparent visible={scannerOpen} animationType="slide" onRequestClose={() => setScannerOpen(false)}>
          <View style={styles.scannerOverlay}>
            <SafeAreaView style={styles.scannerShell}>
              <View style={styles.scannerHeader}>
                <View style={styles.scannerCopy}>
                  <Text style={styles.scannerTitle}>Scan pairing QR</Text>
                  <Text style={styles.scannerText}>{scannerStatus || 'Point the camera at the QR code on desktop.'}</Text>
                </View>
                <Pressable style={styles.scannerCloseButton} onPress={() => setScannerOpen(false)}>
                  <Text style={styles.scannerCloseText}>Close</Text>
                </Pressable>
              </View>
              <View style={styles.cameraFrame}>
                <CameraView
                  style={styles.camera}
                  facing="back"
                  mode="picture"
                  mute
                  barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
                  onBarcodeScanned={scanLocked || busy ? undefined : handleQrScanned}
                />
                <View pointerEvents="none" style={styles.scanTarget} />
              </View>
              <Text style={styles.scannerFooter}>The QR expires quickly and only works for your signed-in account.</Text>
            </SafeAreaView>
          </View>
        </Modal>

        <View style={styles.steps}>
          {steps.map((step, index) => (
            <View key={step.key} style={styles.stepRow}>
              <View style={[styles.stepIndex, step.state === 'done' ? styles.stepDone : step.state === 'error' ? styles.stepError : step.state === 'working' ? styles.stepWorking : null]}>
                <Text style={styles.stepIndexText}>{index + 1}</Text>
              </View>
              <View style={styles.stepCopy}>
                <Text style={styles.stepTitle}>{step.label}</Text>
                <Text style={styles.stepDetail}>{step.detail}</Text>
              </View>
            </View>
          ))}
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Desktops</Text>
          {desktops.length ? (
            desktops.map((desktop) => (
              <View key={desktop.desktop_id} style={styles.desktopRow}>
                <Text style={styles.desktopTitle}>{desktop.display_name || desktop.desktop_id}</Text>
                <View style={styles.desktopMetaRow}>
                  <Text style={styles.desktopMeta}>{shortStatusText(desktop.status || 'registered')}</Text>
                  {desktop.detail ? <InfoHint text={desktop.detail} /> : null}
                </View>
              </View>
            ))
          ) : (
            <Text style={styles.helper}>No desktop is signed into this account yet.</Text>
          )}
        </View>

        {!pairedDesktop ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Pairing QR</Text>
            <Pressable style={[styles.primaryButton, busy ? styles.disabled : null]} onPress={openScanner} disabled={busy}>
              <Text style={styles.primaryText}>{busy ? 'Working...' : 'Scan desktop QR'}</Text>
            </Pressable>
            <Text style={styles.helper}>Or paste the one-time code shown below the QR on desktop.</Text>
            <TextInput
              style={styles.input}
              value={pairingToken}
              onChangeText={setPairingToken}
              placeholder="Paste desktop pairing token"
              placeholderTextColor="#7f93b5"
              autoCapitalize="none"
              autoCorrect={false}
              editable={!busy}
            />
            <Pressable style={[styles.secondaryButton, busy ? styles.disabled : null]} onPress={pair} disabled={busy}>
              <Text style={styles.secondaryText}>{busy ? 'Working...' : 'Pair with pasted code'}</Text>
            </Pressable>
            {scannerStatus ? <Text style={styles.helper}>{shortStatusText(scannerStatus)}</Text> : null}
          </View>
        ) : (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Paired desktop</Text>
            <Text style={styles.helper}>{pairedDesktop}</Text>
            <Link href="/chat" style={styles.link}>Open chat</Link>
          </View>
        )}

        <Text style={styles.status}>{shortStatusText(status)}</Text>

        <View style={styles.actions}>
          <Pressable style={[styles.secondaryButton, busy ? styles.disabled : null]} onPress={refresh} disabled={busy}>
            <Text style={styles.secondaryText}>Refresh status</Text>
          </Pressable>
          <Link href="/settings" style={styles.link}>Account settings</Link>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0b1020',
  },
  content: {
    padding: 20,
    gap: 16,
  },
  header: {
    gap: 7,
  },
  eyebrow: {
    color: '#7cc7ff',
    fontSize: 13,
    fontWeight: '800',
  },
  title: {
    color: '#ffffff',
    fontSize: 26,
    fontWeight: '800',
  },
  subtitle: {
    color: '#b8c7e6',
    fontSize: 15,
    lineHeight: 22,
  },
  steps: {
    backgroundColor: '#111a31',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#223252',
    padding: 14,
    gap: 14,
  },
  stepRow: {
    flexDirection: 'row',
    gap: 12,
    alignItems: 'flex-start',
  },
  stepIndex: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#263659',
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepDone: {
    backgroundColor: '#047857',
  },
  stepWorking: {
    backgroundColor: '#2563eb',
  },
  stepError: {
    backgroundColor: '#b91c1c',
  },
  stepIndexText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '800',
  },
  stepCopy: {
    flex: 1,
    gap: 3,
  },
  stepTitle: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '800',
  },
  stepDetail: {
    color: '#b8c7e6',
    fontSize: 13,
    lineHeight: 19,
  },
  section: {
    backgroundColor: '#111a31',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#223252',
    padding: 14,
    gap: 10,
  },
  sectionTitle: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '800',
  },
  desktopRow: {
    gap: 3,
  },
  desktopTitle: {
    color: '#e8f0ff',
    fontSize: 15,
    fontWeight: '700',
  },
  desktopMeta: {
    color: '#8fa3c8',
    fontSize: 13,
  },
  desktopMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  helper: {
    color: '#b8c7e6',
    fontSize: 14,
    lineHeight: 20,
  },
  input: {
    minHeight: 48,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#263659',
    backgroundColor: '#0b1020',
    color: '#ffffff',
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
  },
  primaryButton: {
    minHeight: 48,
    borderRadius: 8,
    backgroundColor: '#3b82f6',
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryText: {
    color: '#ffffff',
    fontWeight: '800',
  },
  secondaryButton: {
    minHeight: 48,
    borderRadius: 8,
    backgroundColor: '#1b2745',
    alignItems: 'center',
    justifyContent: 'center',
  },
  secondaryText: {
    color: '#dce8ff',
    fontWeight: '800',
  },
  disabled: {
    opacity: 0.55,
  },
  status: {
    color: '#b8c7e6',
    fontSize: 13,
    lineHeight: 20,
  },
  actions: {
    gap: 10,
  },
  link: {
    color: '#7cc7ff',
    fontWeight: '800',
    minHeight: 44,
    paddingTop: 12,
  },
  scannerOverlay: {
    flex: 1,
    backgroundColor: 'rgba(4, 7, 14, 0.92)',
  },
  scannerShell: {
    flex: 1,
    padding: 18,
    gap: 14,
  },
  scannerHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
  },
  scannerCopy: {
    flex: 1,
    gap: 4,
  },
  scannerTitle: {
    color: '#ffffff',
    fontSize: 22,
    fontWeight: '900',
  },
  scannerText: {
    color: '#b8c7e6',
    fontSize: 13,
    lineHeight: 19,
  },
  scannerCloseButton: {
    minHeight: 40,
    borderRadius: 8,
    paddingHorizontal: 13,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#1b2745',
  },
  scannerCloseText: {
    color: '#dce8ff',
    fontWeight: '800',
  },
  cameraFrame: {
    flex: 1,
    minHeight: 360,
    borderRadius: 18,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#35527e',
    backgroundColor: '#050914',
  },
  camera: {
    flex: 1,
  },
  scanTarget: {
    position: 'absolute',
    left: '14%',
    right: '14%',
    top: '24%',
    bottom: '24%',
    borderRadius: 18,
    borderWidth: 3,
    borderColor: '#7cc7ff',
    backgroundColor: 'transparent',
  },
  scannerFooter: {
    color: '#8fa3c8',
    fontSize: 12,
    lineHeight: 18,
    textAlign: 'center',
  },
});
