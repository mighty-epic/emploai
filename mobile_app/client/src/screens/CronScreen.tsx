import { useEffect, useState } from 'react';
import { useRouter } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { loadAppConfig } from '../../lib/appConfig';
import { describeError } from '../../lib/diagnostics';
import { markCronFeedSeen } from '@/lib/cronInbox';
import { AppDrawer, type DrawerTab } from '@/components/AppDrawer';
import { CollapsibleSection } from '@/components/CollapsibleSection';
import {
  actOnJob,
  createJob,
  fetchCronFeed,
  fetchJobs,
  fetchSessions,
  type CronFeedItem,
  type ScheduledJob,
  type SessionSummary,
} from '@/lib/appApi';
import { formatAbsoluteTime, formatRelativeTime } from '@/lib/time';

export default function CronScreen() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [feed, setFeed] = useState<CronFeedItem[]>([]);
  const [status, setStatus] = useState('idle');
  const [apiBaseUrl, setApiBaseUrl] = useState('');
  const [token, setToken] = useState('');
  const [configLoaded, setConfigLoaded] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>('cron');
  const [cronUnreadCount, setCronUnreadCount] = useState(0);
  const [name, setName] = useState('');
  const [prompt, setPrompt] = useState('');
  const [schedule, setSchedule] = useState('every 1 hour');

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

  const loadCronCenter = async (quiet = false) => {
    if (!apiBaseUrl) {
      setStatus('missing backend');
      return;
    }
    if (!token) {
      setStatus('missing token');
      return;
    }

    if (!quiet) {
      setStatus('loading');
    }
    try {
      const [sessionList, jobList, feedItems] = await Promise.all([
        fetchSessions(apiBaseUrl, token),
        fetchJobs(apiBaseUrl, token),
        fetchCronFeed(apiBaseUrl, token),
      ]);
      setSessions(Array.isArray(sessionList) ? sessionList : []);
      setJobs(Array.isArray(jobList) ? jobList : []);
      setFeed(Array.isArray(feedItems) ? feedItems : []);
      await markCronFeedSeen(Array.isArray(feedItems) ? feedItems : []);
      setCronUnreadCount(0);
      setStatus('ready');
    } catch (error) {
      setStatus(describeError(error));
    }
  };

  useEffect(() => {
    if (!configLoaded) return;
    void loadCronCenter();
  }, [apiBaseUrl, configLoaded, token]);

  useEffect(() => {
    if (!configLoaded || !apiBaseUrl || !token) return;

    const intervalId = setInterval(() => {
      void loadCronCenter(true);
    }, 8000);

    return () => clearInterval(intervalId);
  }, [apiBaseUrl, configLoaded, token]);

  const createCronJob = async () => {
    if (!apiBaseUrl || !token || !name.trim() || !prompt.trim() || !schedule.trim()) {
      setStatus('name, prompt, and schedule are required');
      return;
    }

    setStatus('creating job');
    try {
      await createJob(apiBaseUrl, token, {
        name: name.trim(),
        prompt: prompt.trim(),
        schedule: schedule.trim(),
      });
      setName('');
      setPrompt('');
      await loadCronCenter();
    } catch (error) {
      setStatus(describeError(error));
    }
  };

  const runAction = async (jobId: string, action: 'run' | 'enable' | 'disable' | 'delete') => {
    if (!apiBaseUrl || !token) return;

    setStatus(`${action}...`);
    try {
      await actOnJob(apiBaseUrl, token, jobId, action);
      await loadCronCenter();
    } catch (error) {
      setStatus(describeError(error));
    }
  };

  const openFeedSession = (item: CronFeedItem) => {
    if (!item.session_id) return;
    router.push({ pathname: '/chat', params: { sessionId: item.session_id } });
  };

  const enabledJobs = jobs.filter((job) => job.enabled).length;
  const dueJobs = jobs.filter((job) => job.due).length;

  return (
    <SafeAreaView edges={['top', 'left', 'right']} style={styles.container}>
      <AppDrawer
        visible={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        initialTab={drawerTab}
        sessions={sessions}
        jobs={jobs}
        cronUnreadCount={cronUnreadCount}
        backendLabel={apiBaseUrl || 'Backend not configured'}
      />

      <View style={styles.topBar}>
        <Pressable
          style={styles.topButton}
          onPress={() => {
            setDrawerTab('cron');
            setDrawerOpen(true);
          }}
        >
          <Text style={styles.topButtonText}>Sidebar</Text>
        </Pressable>
        <View style={styles.titleBlock}>
          <Text style={styles.title}>Cron Center</Text>
          <Text style={styles.subtitle}>Background jobs, timing, and job output feed</Text>
        </View>
        <Pressable style={styles.topButton} onPress={() => void loadCronCenter()}>
          <Text style={styles.topButtonText}>Refresh</Text>
        </Pressable>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.summaryRow}>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Status</Text>
          <Text style={styles.summaryValue}>{status}</Text>
        </View>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Jobs</Text>
          <Text style={styles.summaryValue}>{jobs.length} total</Text>
        </View>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Enabled</Text>
          <Text style={styles.summaryValue}>{enabledJobs}</Text>
        </View>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>Due now</Text>
          <Text style={styles.summaryValue}>{dueJobs}</Text>
        </View>
      </ScrollView>

      <ScrollView style={styles.body} contentContainerStyle={styles.bodyContent}>
        <View style={styles.heroCard}>
          <Text style={styles.heroTitle}>Background, not session-bound</Text>
          <Text style={styles.heroText}>
            Cron jobs now run in the background regardless of whichever chat session is open. This screen is the app-side mailbox for their output plus the place to inspect timing and control runs.
          </Text>
        </View>

        <CollapsibleSection title="Create cron job" meta="Natural-language schedules supported" defaultExpanded={false}>
          <TextInput
            style={styles.input}
            value={name}
            onChangeText={setName}
            placeholder="Job name"
            placeholderTextColor="#7f8aa3"
          />
          <TextInput
            style={styles.input}
            value={schedule}
            onChangeText={setSchedule}
            placeholder="every 1 hour"
            placeholderTextColor="#7f8aa3"
          />
          <TextInput
            style={[styles.input, styles.textarea]}
            value={prompt}
            onChangeText={setPrompt}
            placeholder="What should this background job do?"
            placeholderTextColor="#7f8aa3"
            multiline
          />
          <Pressable style={styles.primaryButton} onPress={() => void createCronJob()}>
            <Text style={styles.primaryButtonText}>Create job</Text>
          </Pressable>
        </CollapsibleSection>

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Cron chat</Text>
            <Text style={styles.sectionHint}>Auto-refreshes every few seconds</Text>
          </View>
          {feed.length === 0 ? (
            <Text style={styles.empty}>No cron output yet. Background announcements and results will land here as a running transcript.</Text>
          ) : (
            [...feed].reverse().map((item) => (
              <Pressable
                key={item.id}
                style={[
                  styles.feedBubble,
                  item.kind === 'result' ? styles.feedBubbleResult : styles.feedBubbleAnnouncement,
                ]}
                onPress={() => openFeedSession(item)}
                disabled={!item.session_id}
              >
                <View style={styles.feedHeader}>
                  <Text style={styles.feedKind}>{item.job_name || 'Scheduled job'}</Text>
                  <Text style={styles.feedTime}>{item.timestamp ? formatAbsoluteTime(item.timestamp) : 'unknown'}</Text>
                </View>
                <Text style={styles.feedType}>{item.kind === 'announcement' ? 'Update' : 'Result'}</Text>
                <Text style={styles.feedBody}>{item.content}</Text>
                <Text style={styles.feedMeta}>
                  {item.session_name ? `Chat: ${item.session_name}` : 'No linked chat'}
                  {item.telegram_bot_label ? ` · Bot: ${item.telegram_bot_label}` : ''}
                  {item.status ? ` · ${item.status}` : ''}
                  {item.timestamp ? ` · ${formatRelativeTime(item.timestamp)}` : ''}
                </Text>
              </Pressable>
            ))
          )}
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Tracking</Text>
          {jobs.length === 0 ? (
            <Text style={styles.empty}>No scheduled jobs yet.</Text>
          ) : (
            jobs.map((job) => (
              <View key={job.id} style={styles.jobCard}>
                <View style={styles.jobHeader}>
                  <View style={styles.jobTitleBlock}>
                    <Text style={styles.jobTitle}>{job.name}</Text>
                    <Text style={styles.jobMeta}>
                      {job.enabled ? 'Enabled' : 'Paused'} · {job.schedule || 'No schedule'}
                    </Text>
                  </View>
                  <Text style={[styles.jobBadge, job.due ? styles.jobBadgeDue : null]}>
                    {job.due ? 'Due' : 'Scheduled'}
                  </Text>
                </View>
                <Text style={styles.jobPrompt}>{job.prompt}</Text>
                <Text style={styles.jobStats}>
                  Next: {job.next_run_at ? `${formatRelativeTime(job.next_run_at)} (${formatAbsoluteTime(job.next_run_at)})` : 'unknown'}
                </Text>
                <Text style={styles.jobStats}>
                  Last: {job.last_run_at ? formatRelativeTime(job.last_run_at) : 'never'} · Runs: {job.run_count ?? 0} · Errors: {job.error_count ?? 0}
                </Text>
                <Text style={styles.jobStats}>
                  Origin: {sessions.find((session) => session.id === job.origin_session_id)?.name || job.origin_session_id || 'unknown chat'}
                  {job.origin_workspace ? ` · ${job.origin_workspace}` : ''}
                </Text>
                <Text style={styles.jobStats}>
                  Bot: {job.origin_telegram_bot_config_id || 'default'} · Packs: {(job.origin_enabled_tool_packs || []).join(', ') || 'default'}
                </Text>
                <View style={styles.actionsRow}>
                  <Pressable style={styles.secondaryButton} onPress={() => void runAction(job.id, 'run')}>
                    <Text style={styles.secondaryButtonText}>Run now</Text>
                  </Pressable>
                  {job.enabled ? (
                    <Pressable style={styles.secondaryButton} onPress={() => void runAction(job.id, 'disable')}>
                      <Text style={styles.secondaryButtonText}>Pause</Text>
                    </Pressable>
                  ) : (
                    <Pressable style={styles.secondaryButton} onPress={() => void runAction(job.id, 'enable')}>
                      <Text style={styles.secondaryButtonText}>Resume</Text>
                    </Pressable>
                  )}
                  <Pressable style={styles.deleteButton} onPress={() => void runAction(job.id, 'delete')}>
                    <Text style={styles.deleteButtonText}>Delete</Text>
                  </Pressable>
                </View>
              </View>
            ))
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0b1020',
    paddingHorizontal: 16,
    paddingTop: 8,
    gap: 12,
  },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  topButton: {
    backgroundColor: '#182342',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  topButtonText: {
    color: '#dce8ff',
    fontWeight: '700',
    fontSize: 13,
  },
  titleBlock: {
    flex: 1,
    gap: 4,
  },
  title: {
    color: '#ffffff',
    fontSize: 24,
    fontWeight: '700',
  },
  subtitle: {
    color: '#8fa2c8',
    fontSize: 13,
  },
  summaryRow: {
    gap: 8,
    paddingRight: 20,
  },
  summaryCard: {
    backgroundColor: '#141c33',
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
    minWidth: 112,
    gap: 4,
  },
  summaryLabel: {
    color: '#7f93bc',
    fontSize: 11,
    textTransform: 'uppercase',
  },
  summaryValue: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '700',
  },
  body: {
    flex: 1,
  },
  bodyContent: {
    gap: 14,
    paddingBottom: 16,
  },
  heroCard: {
    backgroundColor: '#141c33',
    borderRadius: 20,
    padding: 16,
    gap: 8,
  },
  heroTitle: {
    color: '#ffffff',
    fontSize: 17,
    fontWeight: '700',
  },
  heroText: {
    color: '#d5e3fb',
    fontSize: 15,
    lineHeight: 22,
  },
  section: {
    gap: 10,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 10,
  },
  sectionTitle: {
    color: '#ffffff',
    fontSize: 17,
    fontWeight: '700',
  },
  sectionHint: {
    color: '#8fa2c8',
    fontSize: 12,
  },
  input: {
    backgroundColor: '#0f1730',
    color: '#ffffff',
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  textarea: {
    minHeight: 110,
    textAlignVertical: 'top',
  },
  primaryButton: {
    alignSelf: 'flex-start',
    backgroundColor: '#3b82f6',
    borderRadius: 14,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  primaryButtonText: {
    color: '#ffffff',
    fontWeight: '700',
  },
  feedBubble: {
    backgroundColor: '#141c33',
    borderRadius: 18,
    padding: 14,
    gap: 8,
  },
  feedBubbleAnnouncement: {
    borderLeftWidth: 3,
    borderLeftColor: '#7cc7ff',
  },
  feedBubbleResult: {
    borderLeftWidth: 3,
    borderLeftColor: '#4ade80',
  },
  feedHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 10,
  },
  feedKind: {
    color: '#ffffff',
    fontWeight: '700',
    fontSize: 13,
  },
  feedTime: {
    color: '#8194b9',
    fontSize: 11,
  },
  feedType: {
    color: '#7cc7ff',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  feedBody: {
    color: '#e8f0ff',
    fontSize: 14,
    lineHeight: 21,
  },
  feedMeta: {
    color: '#9db0d4',
    fontSize: 12,
  },
  empty: {
    color: '#9aa9c7',
    fontSize: 14,
  },
  jobCard: {
    backgroundColor: '#141c33',
    borderRadius: 18,
    padding: 14,
    gap: 8,
  },
  jobHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 10,
  },
  jobTitleBlock: {
    flex: 1,
    gap: 4,
  },
  jobTitle: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '700',
  },
  jobMeta: {
    color: '#9db0d4',
    fontSize: 12,
  },
  jobBadge: {
    color: '#cfe1ff',
    backgroundColor: '#223153',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    overflow: 'hidden',
    fontSize: 11,
    fontWeight: '700',
  },
  jobBadgeDue: {
    backgroundColor: '#73420d',
  },
  jobPrompt: {
    color: '#dce8ff',
    fontSize: 14,
    lineHeight: 20,
  },
  jobStats: {
    color: '#9db0d4',
    fontSize: 12,
  },
  actionsRow: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
    paddingTop: 4,
  },
  secondaryButton: {
    backgroundColor: '#223153',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  secondaryButtonText: {
    color: '#ffffff',
    fontWeight: '700',
    fontSize: 13,
  },
  deleteButton: {
    backgroundColor: '#6a2630',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  deleteButtonText: {
    color: '#ffffff',
    fontWeight: '700',
    fontSize: 13,
  },
});
