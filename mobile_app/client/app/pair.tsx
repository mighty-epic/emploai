import { useEffect, useState } from 'react';
import { Link, useRouter } from 'expo-router';
import { Platform, Pressable, SafeAreaView, StyleSheet, Text, TextInput, View } from 'react-native';

import { isSupportedApiBaseUrl, loadAppConfig, normalizeApiBaseUrl, saveAppConfig } from '../lib/appConfig';
import { requestJson } from '../lib/appHttp';
import { describeError } from '../lib/diagnostics';

export default function PairScreen() {
  const router = useRouter();
  const [apiBaseUrl, setApiBaseUrl] = useState('');
  const [pairingToken, setPairingToken] = useState('');
  const [deviceName, setDeviceName] = useState('My EmploAI Device');
  const [status, setStatus] = useState('idle');
  const [isPairing, setIsPairing] = useState(false);

  useEffect(() => {
    loadAppConfig()
      .then((config) => {
        setApiBaseUrl(config.apiBaseUrl);
        setStatus('ready');
      })
      .catch(() => setStatus('load error'));
  }, []);

  const pairDevice = async () => {
    const normalizedBaseUrl = normalizeApiBaseUrl(apiBaseUrl);

    if (!normalizedBaseUrl) {
      setStatus('missing backend');
      return;
    }
    if (!isSupportedApiBaseUrl(normalizedBaseUrl)) {
      setStatus('backend must start with http:// or https://');
      return;
    }
    if (!pairingToken.trim()) {
      setStatus('missing pairing token');
      return;
    }

    setStatus('pairing');
    setIsPairing(true);
    try {
      const data = await requestJson<{ access_token?: string }>({
        scope: 'pair.complete',
        url: `${normalizedBaseUrl}/api/app/pair/complete`,
        init: {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            pairing_token: pairingToken.trim(),
            device_name: deviceName.trim() || 'My EmploAI Device',
            device_platform: Platform.OS,
          }),
        },
      });

      await saveAppConfig({
        apiBaseUrl: normalizedBaseUrl,
        accessToken: String(data.access_token || ''),
      });
      setPairingToken('');
      setStatus('paired');
      router.replace('/chat');
    } catch (error) {
      setStatus(describeError(error));
    } finally {
      setIsPairing(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.title}>Pair Device</Text>
        <Text style={styles.help}>
          Save the backend URL, then paste the short-lived pairing token created on the server. Use HTTPS for VPS access, or
          http://LAN-IP:8787 for same-Wi-Fi local testing.
        </Text>
        <Text style={styles.text}>Backend URL</Text>
        <TextInput
          style={styles.input}
          value={apiBaseUrl}
          onChangeText={setApiBaseUrl}
          autoCapitalize="none"
          autoCorrect={false}
          placeholder="https://your-vps-host or http://192.168.x.x:8787"
          placeholderTextColor="#7f8aa3"
        />
        <Text style={styles.text}>Device name</Text>
        <TextInput
          style={styles.input}
          value={deviceName}
          onChangeText={setDeviceName}
          autoCorrect={false}
          placeholder="Pixel 9 / Work phone"
          placeholderTextColor="#7f8aa3"
        />
        <Text style={styles.text}>Pairing token</Text>
        <TextInput
          style={[styles.input, styles.tokenInput]}
          value={pairingToken}
          onChangeText={setPairingToken}
          autoCapitalize="none"
          autoCorrect={false}
          multiline
          placeholder="Paste the short-lived token generated on the VPS"
          placeholderTextColor="#7f8aa3"
        />
        <Text style={styles.meta}>Status: {status}</Text>
        <Text style={styles.help}>
          The token should come from the app backend. This screen stores the device token locally once pairing succeeds.
        </Text>
        <View style={styles.actions}>
          <Pressable style={[styles.button, isPairing ? styles.buttonDisabled : null]} onPress={() => void pairDevice()} disabled={isPairing}>
            <Text style={styles.buttonText}>{isPairing ? 'Pairing...' : 'Complete Pairing'}</Text>
          </Pressable>
          <Link href="/settings" style={styles.link}>Open Settings</Link>
          <Link href="/diagnostics" style={styles.link}>Open Diagnostics</Link>
        </View>
        <View style={styles.stepsCard}>
          <Text style={styles.stepsTitle}>What the VPS needs to provide</Text>
          <Text style={styles.step}>1. HTTPS URL for VPS use, or an HTTP LAN URL for same-network local testing.</Text>
          <Text style={styles.step}>2. `POST /api/app/pair/complete` enabled.</Text>
          <Text style={styles.step}>3. A short-lived pairing token for this device.</Text>
          <Text style={styles.step}>4. A bearer token response after pairing succeeds.</Text>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0b1020', padding: 20 },
  card: { backgroundColor: '#141c33', borderRadius: 16, padding: 16, gap: 10 },
  title: { color: '#fff', fontSize: 24, fontWeight: '700' },
  text: { color: '#d7def0', fontSize: 16 },
  meta: { color: '#9aa9c7', fontSize: 14 },
  help: { color: '#b5c2dd', fontSize: 14, lineHeight: 20 },
  link: { color: '#7cc7ff', fontSize: 15, fontWeight: '600' },
  input: {
    backgroundColor: '#0f1730',
    color: '#fff',
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  tokenInput: {
    minHeight: 110,
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
