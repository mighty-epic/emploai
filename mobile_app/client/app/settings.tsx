import { useEffect, useState } from 'react';
import { Pressable, SafeAreaView, StyleSheet, Text, TextInput, View } from 'react-native';

import { isSupportedApiBaseUrl, loadAppConfig, normalizeApiBaseUrl, saveAppConfig } from '../lib/appConfig';

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
  const [status, setStatus] = useState('idle');
  const [deviceStatus, setDeviceStatus] = useState<DeviceStatus | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    loadAppConfig()
      .then((config) => {
        setApiBaseUrl(config.apiBaseUrl);
        setAccessToken(config.accessToken);
        setStatus('ready');
      })
      .catch(() => setStatus('load error'));
  }, []);

  const save = async () => {
    const normalizedBaseUrl = normalizeApiBaseUrl(apiBaseUrl);
    if (normalizedBaseUrl && !isSupportedApiBaseUrl(normalizedBaseUrl)) {
      setStatus('backend must start with http:// or https://');
      return;
    }

    setStatus('saving');
    setIsSaving(true);
    try {
      const config = await saveAppConfig({ apiBaseUrl: normalizedBaseUrl, accessToken });
      setApiBaseUrl(config.apiBaseUrl);
      setAccessToken(config.accessToken);
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
      setStatus('missing backend');
      return;
    }
    if (!isSupportedApiBaseUrl(normalizedBaseUrl)) {
      setStatus('backend must start with http:// or https://');
      return;
    }

    setStatus('verifying');
    try {
      const healthResponse = await fetch(`${normalizedBaseUrl}/api/app/health`);
      if (!healthResponse.ok) {
        throw new Error('backend unavailable');
      }

      if (!accessToken.trim()) {
        setDeviceStatus(null);
        setStatus('backend reachable');
        return;
      }

      const meResponse = await fetch(`${normalizedBaseUrl}/api/app/me`, {
        headers: {
          Authorization: `Bearer ${accessToken.trim()}`,
        },
      });
      const meData = await meResponse.json();
      if (!meResponse.ok) {
        throw new Error(String(meData?.detail || 'token invalid'));
      }

      setDeviceStatus(meData);
      setStatus('connected');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'verify error';
      setDeviceStatus(null);
      setStatus(message);
    }
  };

  const clearToken = async () => {
    setStatus('clearing token');
    try {
      await saveAppConfig({
        apiBaseUrl: normalizeApiBaseUrl(apiBaseUrl),
        accessToken: '',
      });
      setAccessToken('');
      setDeviceStatus(null);
      setStatus('token cleared');
    } catch {
      setStatus('clear error');
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.title}>Settings</Text>
        <Text style={styles.help}>
          This app should point to the VPS app backend over HTTPS. Save the URL here once, then verify the device token.
        </Text>
        <Text style={styles.text}>Backend URL</Text>
        <TextInput
          style={styles.input}
          value={apiBaseUrl}
          onChangeText={setApiBaseUrl}
          autoCapitalize="none"
          autoCorrect={false}
          placeholder="https://your-vps-host"
          placeholderTextColor="#7f8aa3"
        />
        <Text style={styles.text}>Access token</Text>
        <TextInput
          style={styles.input}
          value={accessToken}
          onChangeText={setAccessToken}
          autoCapitalize="none"
          autoCorrect={false}
          placeholder="Paste app token"
          placeholderTextColor="#7f8aa3"
        />
        <Text style={styles.meta}>Status: {status}</Text>
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
          <Pressable style={styles.dangerButton} onPress={() => void clearToken()}>
            <Text style={styles.buttonText}>Clear Token</Text>
          </Pressable>
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
