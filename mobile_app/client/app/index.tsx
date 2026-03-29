import { Link } from 'expo-router';
import { useEffect, useState } from 'react';
import { SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';

import { AppConfig, getConnectionSetupState, loadAppConfig } from '../lib/appConfig';

const screens = [
  { href: '/pair' as const, label: 'Pair device', detail: 'Enter the VPS URL and finish trusted-device pairing.' },
  { href: '/chat' as const, label: 'Chat', detail: 'Live chat, voice capture, uploads, and VPS screen preview.' },
  { href: '/sessions' as const, label: 'Sessions', detail: 'Shared session list across the app and Telegram.' },
  { href: '/jobs' as const, label: 'Jobs', detail: 'Scheduler controls and run-now actions.' },
  { href: '/settings' as const, label: 'Settings', detail: 'Verify the backend connection and inspect device state.' },
];

const emptyConfig: AppConfig = {
  apiBaseUrl: '',
  accessToken: '',
};

export default function HomeScreen() {
  const [config, setConfig] = useState<AppConfig>(emptyConfig);
  const [status, setStatus] = useState('loading');

  useEffect(() => {
    let active = true;
    loadAppConfig()
      .then((nextConfig) => {
        if (!active) return;
        setConfig(nextConfig);
        setStatus('ready');
      })
      .catch(() => {
        if (!active) return;
        setStatus('config error');
      });

    return () => {
      active = false;
    };
  }, []);

  const setupState = getConnectionSetupState(config);
  const setupTitle = setupState === 'ready'
    ? 'Ready to connect'
    : setupState === 'missing_token'
      ? 'Backend saved, pairing still needed'
      : 'Backend not configured';
  const setupDetail = setupState === 'ready'
    ? 'This phone already has both the VPS URL and an app token saved.'
    : setupState === 'missing_token'
      ? 'Open Pair device next, paste the short-lived pairing token from the VPS, and this device will be trusted.'
      : 'Open Pair device or Settings first and enter the HTTPS URL of the VPS app backend.';

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>EmploAI App</Text>
        <Text style={styles.subtitle}>
          Android-first client for the VPS-hosted EmploAI app channel.
        </Text>

        <View style={styles.card}>
          <Text style={styles.sectionTitle}>{setupTitle}</Text>
          <Text style={styles.body}>{setupDetail}</Text>
          <Text style={styles.meta}>Config: {status}</Text>
          <Text style={styles.meta}>Backend: {config.apiBaseUrl || 'not set'}</Text>
          <Text style={styles.meta}>Token: {config.accessToken ? 'saved' : 'not saved'}</Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.sectionTitle}>Setup order</Text>
          <Text style={styles.body}>
            1. Save the VPS URL. 2. Pair this device. 3. Open chat. 4. Use sessions, jobs, and settings as management surfaces.
          </Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.sectionTitle}>Screens</Text>
          {screens.map((screen) => (
            <View key={screen.href} style={styles.screenRow}>
              <Link href={screen.href} style={styles.link}>{screen.label}</Link>
              <Text style={styles.body}>{screen.detail}</Text>
            </View>
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0b1020' },
  content: { padding: 20, gap: 16 },
  title: { color: '#ffffff', fontSize: 30, fontWeight: '700' },
  subtitle: { color: '#b6c0d4', fontSize: 16 },
  card: {
    backgroundColor: '#141c33',
    borderRadius: 16,
    padding: 16,
    gap: 10,
  },
  sectionTitle: { color: '#ffffff', fontSize: 18, fontWeight: '600' },
  body: { color: '#d7def0', fontSize: 15, lineHeight: 22 },
  meta: { color: '#93a3c6', fontSize: 13 },
  screenRow: { gap: 4 },
  link: { color: '#7cc7ff', fontSize: 16 },
});
