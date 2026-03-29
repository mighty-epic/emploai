import { useEffect, useMemo, useState } from 'react';
import { Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';

const API_BASE = process.env.EXPO_PUBLIC_EMPLOAI_APP_URL || 'http://127.0.0.1:8765';

type SessionSummary = {
  id: string;
  name: string;
  updated_at: string;
  latest_preview?: string | null;
  origin_channels: string[];
  message_count: number;
};

export default function SessionsScreen() {
  const token = useMemo(() => process.env.EXPO_PUBLIC_EMPLOAI_APP_TOKEN || '', []);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [status, setStatus] = useState('idle');

  const loadSessions = async () => {
    if (!token) {
      setStatus('missing token');
      return;
    }
    setStatus('loading');
    try {
      const response = await fetch(`${API_BASE}/api/app/sessions`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      setSessions(Array.isArray(data) ? data : []);
      setStatus('ready');
    } catch (error) {
      setStatus('error');
    }
  };

  useEffect(() => {
    loadSessions();
  }, []);

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Shared sessions</Text>
        <Text style={styles.meta}>Status: {status}</Text>
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
