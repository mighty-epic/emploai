import { useEffect, useState } from 'react';
import { Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';

import { loadAppConfig } from '../lib/appConfig';
import { requestJson } from '../lib/appHttp';
import { describeError } from '../lib/diagnostics';

type SessionSummary = {
  id: string;
  name: string;
  updated_at: string;
  latest_preview?: string | null;
  origin_channels: string[];
  message_count: number;
};

export default function SessionsScreen() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [status, setStatus] = useState('idle');
  const [apiBaseUrl, setApiBaseUrl] = useState('');
  const [token, setToken] = useState('');
  const [configLoaded, setConfigLoaded] = useState(false);

  useEffect(() => {
    loadAppConfig()
      .then((config) => {
        setApiBaseUrl(config.apiBaseUrl);
        setToken(config.accessToken);
        setConfigLoaded(true);
      })
      .catch(() => {
        setStatus('config error');
        setConfigLoaded(true);
      });
  }, []);

  const loadSessions = async () => {
    if (!apiBaseUrl) {
      setStatus('missing backend');
      return;
    }
    if (!token) {
      setStatus('missing token');
      return;
    }
    setStatus('loading');
    try {
      const data = await requestJson<SessionSummary[]>({
        scope: 'sessions.list',
        url: `${apiBaseUrl}/api/app/sessions`,
        init: {
          headers: { Authorization: `Bearer ${token}` },
        },
      });
      setSessions(Array.isArray(data) ? data : []);
      setStatus('ready');
    } catch (error) {
      setStatus(describeError(error));
    }
  };

  useEffect(() => {
    if (!configLoaded) return;
    loadSessions();
  }, [apiBaseUrl, configLoaded, token]);

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Shared sessions</Text>
        <Text style={styles.meta}>Status: {status}</Text>
        <Text style={styles.meta}>Backend: {apiBaseUrl || 'not set'}</Text>
        <Pressable style={styles.button} onPress={loadSessions}>
          <Text style={styles.buttonText}>Refresh</Text>
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={styles.list}>
        {sessions.map((session) => (
          <View key={session.id} style={styles.card}>
            <Text style={styles.cardTitle}>{session.name}</Text>
            <Text style={styles.cardMeta}>{session.id} · {session.message_count} msgs</Text>
            <Text style={styles.cardMeta}>Channels: {session.origin_channels.join(', ') || 'none'}</Text>
            <Text style={styles.preview}>{session.latest_preview || 'No preview yet'}</Text>
          </View>
        ))}
        {sessions.length === 0 && <Text style={styles.empty}>No sessions loaded yet.</Text>}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0b1020', padding: 16, gap: 12 },
  header: { gap: 8 },
  title: { color: '#fff', fontSize: 24, fontWeight: '700' },
  meta: { color: '#9aa9c7' },
  button: { alignSelf: 'flex-start', backgroundColor: '#3b82f6', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10 },
  buttonText: { color: '#fff', fontWeight: '700' },
  list: { gap: 12, paddingBottom: 20 },
  card: { backgroundColor: '#141c33', borderRadius: 16, padding: 14, gap: 8 },
  cardTitle: { color: '#fff', fontWeight: '700', fontSize: 17 },
  cardMeta: { color: '#8da0c5', fontSize: 12 },
  preview: { color: '#dce6fb', fontSize: 14 },
  empty: { color: '#9aa9c7' },
});
