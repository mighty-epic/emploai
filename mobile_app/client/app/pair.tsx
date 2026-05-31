import { useEffect, useState } from 'react';
import { Link, useRouter } from 'expo-router';
import { Platform, Pressable, SafeAreaView, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  fetchRemoteAccountProfile,
  fetchRemoteDesktops,
  remoteCompletePairing,
  remoteLogin,
  remoteRegisterAccount,
  type RemoteDesktop,
} from '../src/lib/appApi';
import { describeError } from '../lib/diagnostics';
import { isSupportedApiBaseUrl, loadAppConfig, normalizeApiBaseUrl, saveAppConfig } from '../lib/appConfig';

export default function PairScreen() {
  const router = useRouter();
  const [apiBaseUrl, setApiBaseUrl] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [pairingToken, setPairingToken] = useState('');
  const [deviceName, setDeviceName] = useState('My EmploAI Phone');
  const [accountToken, setAccountToken] = useState('');
  const [pairedDesktopId, setPairedDesktopId] = useState('');
  const [desktops, setDesktops] = useState<RemoteDesktop[]>([]);
  const [status, setStatus] = useState('idle');
  const [isBusy, setIsBusy] = useState(false);

  useEffect(() => {
    let active = true;
    loadAppConfig()
      .then((config) => {
        if (!active) return;
        setApiBaseUrl(config.apiBaseUrl);
        setAccountToken(config.accountToken || config.accessToken);
        setPairedDesktopId(config.pairedDesktopId);
        setStatus('ready');
      })
      .catch(() => {
        if (!active) return;
        setStatus('load error');
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!apiBaseUrl || !accountToken) return;
    let active = true;
    fetchRemoteDesktops(apiBaseUrl, accountToken)
      .then((items) => {
        if (!active) return;
        setDesktops(Array.isArray(items) ? items : []);
      })
      .catch(() => {
        if (!active) return;
        setDesktops([]);
      });
    return () => {
      active = false;
    };
  }, [apiBaseUrl, accountToken]);

  const normalizeBaseUrlOrStatus = () => {
    const normalizedBaseUrl = normalizeApiBaseUrl(apiBaseUrl);
    if (!normalizedBaseUrl) {
      setStatus('missing service URL');
      return null;
    }
    if (!isSupportedApiBaseUrl(normalizedBaseUrl)) {
      setStatus('service URL must start with http:// or https://');
      return null;
    }
    return normalizedBaseUrl;
  };

  const persistRemoteConfig = async (next: { baseUrl: string; token: string; pairedDesktopId?: string | null }) => {
    const normalized = await saveAppConfig({
      apiBaseUrl: next.baseUrl,
      accessToken: next.token,
      accountToken: next.token,
      pairedDesktopId: (next.pairedDesktopId || '').trim(),
      connectionMode: 'remote_cloud',
    });
    setApiBaseUrl(normalized.apiBaseUrl);
    setAccountToken(normalized.accountToken);
    setPairedDesktopId(normalized.pairedDesktopId);
  };

  const signIn = async () => {
    const normalizedBaseUrl = normalizeBaseUrlOrStatus();
    if (!normalizedBaseUrl) return;
    if (!email.trim() || !password.trim()) {
      setStatus('email and password required');
      return;
    }
    setIsBusy(true);
    setStatus('signing in');
    try {
      const result = await remoteLogin(normalizedBaseUrl, {
        email: email.trim(),
        password,
        actor_kind: 'mobile',
        device_name: deviceName.trim() || 'My EmploAI Phone',
        device_platform: Platform.OS,
      });
      await persistRemoteConfig({
        baseUrl: normalizedBaseUrl,
        token: result.session_token,
        pairedDesktopId: result.mobile?.paired_desktop_id || '',
      });
      const desktopItems = await fetchRemoteDesktops(normalizedBaseUrl, result.session_token).catch(() => []);
      setDesktops(Array.isArray(desktopItems) ? desktopItems : []);
      setStatus(result.mobile?.paired_desktop_id ? 'signed in and paired' : 'signed in');
      if (result.mobile?.paired_desktop_id) {
        router.replace('/chat');
      }
    } catch (error) {
      setStatus(describeError(error));
    } finally {
      setIsBusy(false);
    }
  };

  const registerAndSignIn = async () => {
    const normalizedBaseUrl = normalizeBaseUrlOrStatus();
    if (!normalizedBaseUrl) return;
    if (!email.trim() || !password.trim()) {
      setStatus('email and password required');
      return;
    }
    setIsBusy(true);
    setStatus('creating account');
    try {
      await remoteRegisterAccount(normalizedBaseUrl, {
        email: email.trim(),
        password,
        display_name: email.trim().split('@', 1)[0],
      });
      setStatus('account created');
      await signIn();
    } catch (error) {
      setStatus(describeError(error));
      setIsBusy(false);
    }
  };

  const completePairing = async () => {
    const normalizedBaseUrl = normalizeBaseUrlOrStatus();
    if (!normalizedBaseUrl) return;
    if (!accountToken.trim()) {
      setStatus('sign in first');
      return;
    }
    if (!pairingToken.trim()) {
      setStatus('missing pairing token');
      return;
    }
    setIsBusy(true);
    setStatus('pairing phone with desktop');
    try {
      const result = await remoteCompletePairing(normalizedBaseUrl, accountToken, pairingToken.trim());
      await persistRemoteConfig({
        baseUrl: normalizedBaseUrl,
        token: accountToken,
        pairedDesktopId: result.desktop.desktop_id,
      });
      setPairingToken('');
      setStatus(`paired to ${result.desktop.display_name || result.desktop.desktop_id}`);
      router.replace('/chat');
    } catch (error) {
      setStatus(describeError(error));
    } finally {
      setIsBusy(false);
    }
  };

  const refreshAccount = async () => {
    const normalizedBaseUrl = normalizeBaseUrlOrStatus();
    if (!normalizedBaseUrl || !accountToken.trim()) {
      setStatus('sign in first');
      return;
    }
    setStatus('refreshing account');
    try {
      const profile = await fetchRemoteAccountProfile(normalizedBaseUrl, accountToken);
      setPairedDesktopId(profile.mobile?.paired_desktop_id || '');
      const desktopItems = await fetchRemoteDesktops(normalizedBaseUrl, accountToken).catch(() => []);
      setDesktops(Array.isArray(desktopItems) ? desktopItems : []);
      setStatus(profile.mobile?.paired_desktop_id ? 'account ready' : 'signed in, not yet paired');
    } catch (error) {
      setStatus(describeError(error));
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.title}>Connect Phone</Text>
        <Text style={styles.help}>
          Sign in to your EmploAI cloud account, then paste the short-lived pairing token shown by your desktop. The phone
          stays linked through the VPS, so it can reach your computer from any network while that desktop stays online.
        </Text>

        <Text style={styles.text}>Service URL</Text>
        <TextInput
          style={styles.input}
          value={apiBaseUrl}
          onChangeText={setApiBaseUrl}
          autoCapitalize="none"
          autoCorrect={false}
          placeholder="https://your-emploai-domain"
          placeholderTextColor="#7f8aa3"
        />

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Account</Text>
          <TextInput
            style={styles.input}
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            autoCorrect={false}
            placeholder="you@example.com"
            placeholderTextColor="#7f8aa3"
          />
          <TextInput
            style={styles.input}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoCapitalize="none"
            autoCorrect={false}
            placeholder="password"
            placeholderTextColor="#7f8aa3"
          />
          <TextInput
            style={styles.input}
            value={deviceName}
            onChangeText={setDeviceName}
            autoCorrect={false}
            placeholder="Pixel 9 / Work phone"
            placeholderTextColor="#7f8aa3"
          />
          <View style={styles.actions}>
            <Pressable style={[styles.button, isBusy ? styles.buttonDisabled : null]} onPress={() => void signIn()} disabled={isBusy}>
              <Text style={styles.buttonText}>{isBusy ? 'Working...' : 'Sign In'}</Text>
            </Pressable>
            <Pressable style={styles.secondaryButton} onPress={() => void registerAndSignIn()} disabled={isBusy}>
              <Text style={styles.buttonText}>Register</Text>
            </Pressable>
            <Pressable style={styles.ghostButton} onPress={() => void refreshAccount()} disabled={isBusy}>
              <Text style={styles.ghostButtonText}>Refresh</Text>
            </Pressable>
          </View>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Pair With Desktop</Text>
          <TextInput
            style={[styles.input, styles.tokenInput]}
            value={pairingToken}
            onChangeText={setPairingToken}
            autoCapitalize="none"
            autoCorrect={false}
            multiline
            placeholder="Paste the one-time desktop pairing token or QR payload here"
            placeholderTextColor="#7f8aa3"
          />
          <Pressable style={[styles.button, isBusy ? styles.buttonDisabled : null]} onPress={() => void completePairing()} disabled={isBusy}>
            <Text style={styles.buttonText}>Complete Pairing</Text>
          </Pressable>
          <Text style={styles.meta}>Status: {status}</Text>
          <Text style={styles.meta}>Paired desktop: {pairedDesktopId || 'not paired yet'}</Text>
          {desktops.length ? (
            <View style={styles.stepsCard}>
              <Text style={styles.stepsTitle}>Desktops on this account</Text>
              {desktops.map((desktop) => (
                <Text key={desktop.desktop_id} style={styles.step}>
                  {desktop.display_name || desktop.desktop_id} · {desktop.status}
                </Text>
              ))}
            </View>
          ) : null}
        </View>

        <View style={styles.stepsCard}>
          <Text style={styles.stepsTitle}>What happens next</Text>
          <Text style={styles.step}>1. Desktop signs into the same cloud account and creates a short-lived pairing token.</Text>
          <Text style={styles.step}>2. Phone signs in here, pastes that token, and binds to the desktop.</Text>
          <Text style={styles.step}>3. After pairing, chat and live state come through the VPS while the desktop remains the execution machine.</Text>
        </View>

        <View style={styles.actions}>
          <Link href="/settings" style={styles.link}>Open Settings</Link>
          <Link href="/diagnostics" style={styles.link}>Open Diagnostics</Link>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0b1020', padding: 20 },
  card: { backgroundColor: '#141c33', borderRadius: 16, padding: 16, gap: 12 },
  title: { color: '#fff', fontSize: 24, fontWeight: '700' },
  text: { color: '#d7def0', fontSize: 16 },
  meta: { color: '#9aa9c7', fontSize: 14 },
  help: { color: '#b5c2dd', fontSize: 14, lineHeight: 20 },
  section: { gap: 10 },
  sectionTitle: { color: '#fff', fontWeight: '700', fontSize: 15 },
  link: { color: '#7cc7ff', fontSize: 15, fontWeight: '600' },
  input: {
    backgroundColor: '#0f1730',
    color: '#fff',
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  tokenInput: {
    minHeight: 100,
    textAlignVertical: 'top',
  },
  actions: { flexDirection: 'row', gap: 12, flexWrap: 'wrap', alignItems: 'center' },
  button: {
    alignSelf: 'flex-start',
    backgroundColor: '#3b82f6',
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  secondaryButton: {
    alignSelf: 'flex-start',
    backgroundColor: '#223153',
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  ghostButton: {
    alignSelf: 'flex-start',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#31518e',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  ghostButtonText: { color: '#c5d4f2', fontWeight: '700' },
  buttonDisabled: { opacity: 0.65 },
  buttonText: { color: '#fff', fontWeight: '700' },
  stepsCard: {
    backgroundColor: '#0f1730',
    borderRadius: 12,
    padding: 12,
    gap: 6,
  },
  stepsTitle: { color: '#fff', fontWeight: '700', fontSize: 14 },
  step: { color: '#c6d2ec', fontSize: 13, lineHeight: 18 },
});
