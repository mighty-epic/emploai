import { useEffect, useState } from 'react';
import { Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { loadAppConfig } from '../lib/appConfig';

type Job = {
  id: string;
  name: string;
  prompt: string;
  schedule?: string | null;
  enabled: boolean;
  next_run_at?: string | null;
  run_count?: number | null;
  error_count?: number | null;
};

export default function JobsScreen() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [status, setStatus] = useState('idle');
  const [name, setName] = useState('');
  const [prompt, setPrompt] = useState('');
  const [schedule, setSchedule] = useState('every 1 hour');
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

  const loadJobs = async () => {
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
      const response = await fetch(`${apiBaseUrl}/api/app/jobs`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      setJobs(Array.isArray(data) ? data : []);
      setStatus('ready');
    } catch {
      setStatus('error');
    }
  };

  useEffect(() => {
    if (!configLoaded) return;
    loadJobs();
  }, [apiBaseUrl, configLoaded, token]);

  const createJob = async () => {
    if (!apiBaseUrl || !token || !name.trim() || !prompt.trim() || !schedule.trim()) return;
    setStatus('creating');
    try {
      const response = await fetch(`${apiBaseUrl}/api/app/jobs`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name: name.trim(), prompt: prompt.trim(), schedule: schedule.trim() }),
      });
      if (!response.ok) throw new Error('create failed');
      setName('');
      setPrompt('');
      await loadJobs();
    } catch {
      setStatus('error');
    }
  };

  const act = async (jobId: string, action: 'run' | 'enable' | 'disable' | 'delete') => {
    if (!apiBaseUrl || !token) return;
    setStatus(`${action}...`);
    try {
      const method = action === 'delete' ? 'DELETE' : 'POST';
      const url = action === 'delete'
        ? `${apiBaseUrl}/api/app/jobs/${jobId}`
        : `${apiBaseUrl}/api/app/jobs/${jobId}/${action}`;
      const response = await fetch(url, {
        method,
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('action failed');
      await loadJobs();
    } catch {
      setStatus('error');
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Jobs and scheduler</Text>
        <Text style={styles.meta}>Status: {status}</Text>
        <Text style={styles.meta}>Backend: {apiBaseUrl || 'not set'}</Text>
        <Pressable style={styles.primaryButton} onPress={loadJobs}>
          <Text style={styles.primaryButtonText}>Refresh</Text>
        </Pressable>
      </View>

      <View style={styles.composeCard}>
        <Text style={styles.sectionTitle}>Create job</Text>
        <TextInput style={styles.input} value={name} onChangeText={setName} placeholder="Job name" placeholderTextColor="#7f8aa3" />
        <TextInput style={styles.input} value={schedule} onChangeText={setSchedule} placeholder="Schedule" placeholderTextColor="#7f8aa3" />
        <TextInput style={[styles.input, styles.textarea]} value={prompt} onChangeText={setPrompt} placeholder="Prompt" placeholderTextColor="#7f8aa3" multiline />
        <Pressable style={styles.primaryButton} onPress={createJob}>
          <Text style={styles.primaryButtonText}>Create</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.list}>
        {jobs.map((job) => (
          <View key={job.id} style={styles.card}>
            <Text style={styles.cardTitle}>{job.name}</Text>
            <Text style={styles.cardMeta}>{job.id}</Text>
            <Text style={styles.cardMeta}>Schedule: {job.schedule || 'unknown'}</Text>
            <Text style={styles.cardMeta}>Enabled: {job.enabled ? 'yes' : 'no'} · Runs: {job.run_count ?? 0} · Errors: {job.error_count ?? 0}</Text>
            <Text style={styles.preview}>{job.prompt}</Text>
            <View style={styles.actionsRow}>
              <Pressable style={styles.actionButton} onPress={() => act(job.id, 'run')}><Text style={styles.actionText}>Run</Text></Pressable>
              {job.enabled ? (
                <Pressable style={styles.actionButton} onPress={() => act(job.id, 'disable')}><Text style={styles.actionText}>Disable</Text></Pressable>
              ) : (
                <Pressable style={styles.actionButton} onPress={() => act(job.id, 'enable')}><Text style={styles.actionText}>Enable</Text></Pressable>
              )}
              <Pressable style={[styles.actionButton, styles.deleteButton]} onPress={() => act(job.id, 'delete')}><Text style={styles.actionText}>Delete</Text></Pressable>
            </View>
          </View>
        ))}
        {jobs.length === 0 && <Text style={styles.empty}>No jobs yet.</Text>}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0b1020', padding: 16, gap: 12 },
  header: { gap: 8 },
  title: { color: '#fff', fontSize: 24, fontWeight: '700' },
  meta: { color: '#9aa9c7' },
  sectionTitle: { color: '#fff', fontWeight: '700', fontSize: 16 },
  composeCard: { backgroundColor: '#141c33', borderRadius: 16, padding: 14, gap: 10 },
  input: { backgroundColor: '#0f1730', color: '#fff', borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10 },
  textarea: { minHeight: 90, textAlignVertical: 'top' },
  primaryButton: { alignSelf: 'flex-start', backgroundColor: '#3b82f6', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10 },
  primaryButtonText: { color: '#fff', fontWeight: '700' },
  list: { gap: 12, paddingBottom: 20 },
  card: { backgroundColor: '#141c33', borderRadius: 16, padding: 14, gap: 8 },
  cardTitle: { color: '#fff', fontWeight: '700', fontSize: 17 },
  cardMeta: { color: '#8da0c5', fontSize: 12 },
  preview: { color: '#dce6fb', fontSize: 14 },
  actionsRow: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  actionButton: { backgroundColor: '#223153', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8 },
  deleteButton: { backgroundColor: '#6a2630' },
  actionText: { color: '#fff', fontWeight: '700', fontSize: 12 },
  empty: { color: '#9aa9c7' },
});
