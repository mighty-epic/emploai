import { useEffect, useState } from 'react';
import { Link } from 'expo-router';
import { Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';

import { loadAppConfig } from '../lib/appConfig';
import { requestJson } from '../lib/appHttp';
import { clearDiagnostics, listDiagnostics, shortStatusText, subscribeDiagnostics, type DiagnosticEntry, userFacingError } from '../lib/diagnostics';
import { PageHeader } from '../src/components/PageHeader';

export default function DiagnosticsScreen() {
  const [entries, setEntries] = useState<DiagnosticEntry[]>(() => listDiagnostics());
  const [apiBaseUrl, setApiBaseUrl] = useState('');
  const [status, setStatus] = useState('idle');

  useEffect(() => {
    loadAppConfig()
      .then((config) => {
        setApiBaseUrl(config.apiBaseUrl);
      })
      .catch(() => {
        setStatus('Setup needs attention.');
      });
  }, []);

  useEffect(() => {
    return subscribeDiagnostics(() => {
      setEntries(listDiagnostics());
    });
  }, []);

  const runHealthProbe = async () => {
    if (!apiBaseUrl) {
      setStatus('Connect backend first.');
      return;
    }

    setStatus('probing');
    try {
      await requestJson({
        scope: 'diagnostics.health',
        url: `${apiBaseUrl}/api/app/health`,
      });
      setStatus('health ok');
    } catch (error) {
      setStatus(userFacingError(error, 'Health probe failed.'));
    }
  };

  const clearAll = () => {
    clearDiagnostics();
    setStatus('cleared');
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <PageHeader title="Diagnostics" subtitle={`Status: ${shortStatusText(status)} · Backend: ${apiBaseUrl || 'not set'}`} fallbackHref="/settings" />
        <View style={styles.actions}>
          <Pressable style={styles.button} onPress={() => void runHealthProbe()}>
            <Text style={styles.buttonText}>Run Health Probe</Text>
          </Pressable>
          <Pressable style={styles.secondaryButton} onPress={clearAll}>
            <Text style={styles.buttonText}>Clear Logs</Text>
          </Pressable>
          <Link href="/settings" style={styles.link}>Back to Settings</Link>
        </View>
      </View>

      <ScrollView contentContainerStyle={styles.list}>
        {entries.map((entry) => (
          <View key={entry.id} style={styles.card}>
            <Text style={styles.cardTitle}>
              [{entry.level.toUpperCase()}] {entry.scope}
            </Text>
            <Text style={styles.cardMeta}>{entry.at}</Text>
            <Text style={styles.cardBody}>{entry.message}</Text>
            {entry.detail ? <Text style={styles.cardDetail}>{entry.detail}</Text> : null}
          </View>
        ))}
        {entries.length === 0 ? (
          <Text style={styles.empty}>No diagnostics yet. Trigger a request, then reopen this screen.</Text>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0b1020', padding: 16, gap: 12 },
  header: { gap: 8 },
  title: { color: '#fff', fontSize: 24, fontWeight: '700' },
  meta: { color: '#9aa9c7' },
  actions: { flexDirection: 'row', gap: 10, flexWrap: 'wrap', alignItems: 'center' },
  button: { backgroundColor: '#3b82f6', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10 },
  secondaryButton: { backgroundColor: '#334155', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10 },
  buttonText: { color: '#fff', fontWeight: '700' },
  link: { color: '#7cc7ff', fontWeight: '600' },
  list: { gap: 12, paddingBottom: 20 },
  card: { backgroundColor: '#141c33', borderRadius: 14, padding: 12, gap: 6 },
  cardTitle: { color: '#fff', fontSize: 14, fontWeight: '700' },
  cardMeta: { color: '#7f8aa3', fontSize: 12 },
  cardBody: { color: '#dce6fb', fontSize: 14 },
  cardDetail: { color: '#b7c4df', fontSize: 12, lineHeight: 18 },
  empty: { color: '#9aa9c7' },
});
