import { useEffect, useState } from 'react';
import { Link } from 'expo-router';
import { Pressable, SafeAreaView, StyleSheet, Text, TextInput, View } from 'react-native';

import { fetchRemoteAccountProfile } from '../src/lib/appApi';
import { isSupportedApiBaseUrl, loadAppConfig, normalizeApiBaseUrl, saveAppConfig, type AppConnectionMode } from '../lib/appConfig';
import { requestJson } from '../lib/appHttp';
import { describeError } from '../lib/diagnostics';

type DeviceStatus = {
  user_id?: number;
  current_session_id?: string | null;
  current_model?: string | null;
  current_variant?: string | null;
  device_id?: string | null;
  device_name?: string | null;
  device_platform?: string | null;
};

export default function SettingsScreen() {
  const [apiBaseUrl, setApiBaseUrl] = useState('');
  const [accessToken, setAccessToken] = useState('');
  const [accountToken, setAccountToken] = useState('');
  const [pairedDesktopId, setPairedDesktopId] = useState('');
  const [connectionMode, setConnectionMode] = useState<AppConnectionMode>('remote_cloud');
  const [status, setStatus] = useState('idle');
  const [deviceStatus, setDeviceStatus] = useState<DeviceStatus | null>(null);
  const [accountSummary, setAccountSummary] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    loadAppConfig()
      .then((config) => {
        setApiBaseUrl(config.apiBaseUrl);
        setAccessToken(config.accessToken);
        setAccountToken(config.accountToken);
        setPairedDesktopId(config.pairedDesktopId);
        setConnectionMode(config.connectionMode);
        setStatus('ready');
      })
      .catch(() => setStatus('load error'));
  }, []);

  const save = async () => {
    const normalizedBaseUrl = normalizeApiBaseUrl(apiBaseUrl);
    if (normalizedBaseUrl && !isSupportedApiBaseUrl(normalizedBaseUrl)) {
      setStatus('service URL must start with http:// or https://');
      return;
    }
    setStatus('saving');
    setIsSaving(true);
    try {
      const config = await saveAppConfig({
        apiBaseUrl: normalizedBaseUrl,
        accessToken,
        accountToken,
        pairedDesktopId,
        connectionMode,
      });
      setApiBaseUrl(config.apiBaseUrl);
      setAccessToken(config.accessToken);
      setAccountToken(config.accountToken);
      setPairedDesktopId(config.pairedDesktopId);
      setConnectionMode(config.connectionMode);
      setStatus('saved');
    } catch {
      setStatus('save error');
    } finally {
      setIsSaving(false);
    }
  };

  const verify = async () => {
    const normalizedBaseUrl = normalizeApiBaseUrl(apiBaseUrl);
    if (!normalizedBaseUrl) {
      setStatus('missing service URL');
      return;
    }
    if (!isSupportedApiBaseUrl(normalizedBaseUrl)) {
      setStatus('service URL must start with http:// or https://');
      return;
    }

    setStatus('verifying');
    try {
      await requestJson({
        scope: 'settings.health',
        url: `${normalizedBaseUrl}/api/app/health`,
      });

      if (accountToken.trim()) {
        const profile = await fetchRemoteAccountProfile(normalizedBaseUrl, accountToken);
        setAccountSummary(`${profile.user.email} · ${profile.mobile?.paired_desktop_id || 'not paired'}`);
      } else {
        setAccountSummary(null);
      }

      if (!accessToken.trim()) {
        setDeviceStatus(null);
        setStatus('service reachable');
        return;
      }

      const meData = await requestJson<DeviceStatus>({
        scope: 'settings.me',
        url: `${normalizedBaseUrl}/api/app/me`,
        init: {
          headers: {
            Authorization: `Bearer ${accessToken.trim()}`,
          },
        },
      });

      setDeviceStatus(meData);
      setStatus('connected');
    } catch (error) {
      setDeviceStatus(null);
      setAccountSummary(null);
      setStatus(describeError(error));
    }
  };

  const clearTokens = async () => {
    setStatus('clearing tokens');
    try {
      await saveAppConfig({
        apiBaseUrl: normalizeApiBaseUrl(apiBaseUrl),
        accessToken: '',
        accountToken: '',
        pairedDesktopId: '',
        connectionMode,
      });
      setAccessToken('');
      setAccountToken('');
      setPairedDesktopId('');
      setDeviceStatus(null);
      setAccountSummary(null);
      setStatus('tokens cleared');
    } catch {
      setStatus('clear error');
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.title}>Settings</Text>
        <Text style={styles.help}>
          Mobile v1 targets the public EmploAI control plane. The phone signs into the service, pairs to a desktop, then
          uses the same `/api/app` chat surface through the VPS instead of talking directly to a user-entered desktop URL.
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
        <Text style={styles.text}>Connection mode</Text>
        <Text style={styles.meta}>{connectionMode}</Text>
        <Text style={styles.text}>Account token</Text>
        <TextInput
          style={styles.input}
          value={accountToken}
          onChangeText={setAccountToken}
          autoCapitalize="none"
          autoCorrect={false}
          placeholder="Remote account session token"
          placeholderTextColor="#7f8aa3"
        />
        <Text style={styles.text}>App token</Text>
        <TextInput
          style={styles.input}
          value={accessToken}
          onChangeText={setAccessToken}
          autoCapitalize="none"
          autoCorrect={false}
          placeholder="Effective app token"
          placeholderTextColor="#7f8aa3"
        />
        <Text style={styles.text}>Paired desktop ID</Text>
        <TextInput
          style={styles.input}
          value={pairedDesktopId}
          onChangeText={setPairedDesktopId}
          autoCapitalize="none"
          autoCorrect={false}
          placeholder="Desktop id after pairing"
          placeholderTextColor="#7f8aa3"
        />
        <Text style={styles.meta}>Status: {status}</Text>
        {accountSummary ? (
          <View style={styles.infoCard}>
            <Text style={styles.infoLine}>Account: {accountSummary}</Text>
          </View>
        ) : null}
        {deviceStatus ? (
          <View style={styles.infoCard}>
            <Text style={styles.infoLine}>Device: {deviceStatus.device_name || 'Unknown'}</Text>
            <Text style={styles.infoLine}>Platform: {deviceStatus.device_platform || 'Unknown'}</Text>
            <Text style={styles.infoLine}>Model: {deviceStatus.current_model || 'Unknown'}</Text>
            <Text style={styles.infoLine}>Session: {deviceStatus.current_session_id || 'None'}</Text>
          </View>
        ) : null}
        <View style={styles.actions}>
          <Pressable style={[styles.primaryButton, isSaving ? styles.disabledButton : null]} onPress={() => void save()} disabled={isSaving}>
            <Text style={styles.buttonText}>{isSaving ? 'Saving...' : 'Save'}</Text>
          </Pressable>
          <Pressable style={styles.secondaryButton} onPress={() => void verify()}>
            <Text style={styles.buttonText}>Verify</Text>
          </Pressable>
          <Pressable style={styles.dangerButton} onPress={() => void clearTokens()}>
            <Text style={styles.buttonText}>Clear Tokens</Text>
          </Pressable>
          <Link href="/pair" style={styles.link}>Connect or Pair</Link>
          <Link href="/diagnostics" style={styles.link}>Open Diagnostics</Link>
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
  input: {
    backgroundColor: '#0f1730',
    color: '#fff',
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  actions: { flexDirection: 'row', gap: 10, flexWrap: 'wrap' },
  link: { color: '#7cc7ff', fontWeight: '600', alignSelf: 'center' },
  primaryButton: {
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
  dangerButton: {
    alignSelf: 'flex-start',
    backgroundColor: '#6a2630',
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  disabledButton: { opacity: 0.65 },
  infoCard: {
    backgroundColor: '#0f1730',
    borderRadius: 12,
    padding: 12,
    gap: 6,
  },
  infoLine: { color: '#d7def0', fontSize: 14 },
  buttonText: { color: '#fff', fontWeight: '700' },
});
