import { useEffect, useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { usePathname, useRouter } from 'expo-router';
import { SafeAreaView as SafeAreaFrame } from 'react-native-safe-area-context';

import type { ScheduledJob, SessionSummary } from '@/lib/appApi';
import { formatRelativeTime } from '@/lib/time';

export type DrawerTab = 'chats' | 'cron' | 'system';

type Props = {
  visible: boolean;
  onClose: () => void;
  initialTab?: DrawerTab;
  sessions: SessionSummary[];
  jobs: ScheduledJob[];
  activeSessionId?: string;
  backendLabel?: string;
  onSelectSession?: (sessionId: string) => void;
  onCreateSession?: () => void;
};

export function AppDrawer({
  visible,
  onClose,
  initialTab = 'chats',
  sessions,
  jobs,
  activeSessionId,
  backendLabel,
  onSelectSession,
  onCreateSession,
}: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const [tab, setTab] = useState<DrawerTab>(initialTab);

  useEffect(() => {
    if (visible) {
      setTab(initialTab);
    }
  }, [initialTab, visible]);

  const navigate = (path: '/chat' | '/cron' | '/pair' | '/settings' | '/diagnostics') => {
    router.push(path);
    onClose();
  };

  const selectSession = (sessionId: string) => {
    onSelectSession?.(sessionId);
    router.push({ pathname: '/chat', params: { sessionId } });
    onClose();
  };

  const openNewSession = () => {
    if (onCreateSession) {
      onCreateSession();
    } else {
      router.push({ pathname: '/chat', params: { newSession: '1' } });
    }
    onClose();
  };

  return (
    <Modal transparent visible={visible} animationType="fade" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <SafeAreaFrame edges={['top', 'bottom']} style={styles.panel}>
          <View style={styles.panelHeader}>
            <View style={styles.headerCopy}>
              <Text style={styles.brand}>EmploAI</Text>
              <Text style={styles.subhead}>{backendLabel || 'Backend not configured'}</Text>
            </View>
            <Pressable onPress={onClose}>
              <Text style={styles.close}>Close</Text>
            </Pressable>
          </View>

          <View style={styles.tabRow}>
            {(['chats', 'cron', 'system'] as DrawerTab[]).map((value) => (
              <Pressable
                key={value}
                style={[styles.tabButton, tab === value ? styles.tabButtonActive : null]}
                onPress={() => setTab(value)}
              >
                <Text style={styles.tabText}>{value === 'chats' ? 'Chats' : value === 'cron' ? 'Cron' : 'System'}</Text>
              </Pressable>
            ))}
          </View>

          <ScrollView contentContainerStyle={styles.content}>
            {tab === 'chats' ? (
              <View style={styles.section}>
                <View style={styles.sectionHeader}>
                  <Text style={styles.sectionTitle}>Conversations</Text>
                  <Pressable style={styles.ghostButton} onPress={() => navigate('/chat')}>
                    <Text style={styles.ghostText}>{pathname === '/chat' ? 'Open' : 'Go'}</Text>
                  </Pressable>
                </View>
                <Pressable style={styles.primaryButton} onPress={openNewSession}>
                  <Text style={styles.primaryText}>+ New chat</Text>
                </Pressable>
                {sessions.length === 0 ? (
                  <Text style={styles.empty}>No sessions yet.</Text>
                ) : (
                  sessions.map((session) => (
                    <Pressable
                      key={session.id}
                      style={[styles.listCard, activeSessionId === session.id ? styles.listCardActive : null]}
                      onPress={() => selectSession(session.id)}
                    >
                      <Text style={styles.cardTitle}>{session.name}</Text>
                      <Text style={styles.cardMeta}>
                        {session.message_count} msgs · {formatRelativeTime(session.updated_at)}
                      </Text>
                      <Text style={styles.cardBody}>{session.latest_preview || 'No messages yet'}</Text>
                    </Pressable>
                  ))
                )}
              </View>
            ) : null}

            {tab === 'cron' ? (
              <View style={styles.section}>
                <View style={styles.sectionHeader}>
                  <Text style={styles.sectionTitle}>Background jobs</Text>
                  <Pressable style={styles.ghostButton} onPress={() => navigate('/cron')}>
                    <Text style={styles.ghostText}>{pathname === '/cron' ? 'Open' : 'Go'}</Text>
                  </Pressable>
                </View>
                <Text style={styles.hint}>
                  Cron jobs run in the background and are not tied to whichever chat you currently have open.
                </Text>
                {jobs.length === 0 ? (
                  <Text style={styles.empty}>No jobs yet.</Text>
                ) : (
                  jobs.slice(0, 8).map((job) => (
                    <Pressable key={job.id} style={styles.listCard} onPress={() => navigate('/cron')}>
                      <Text style={styles.cardTitle}>{job.name}</Text>
                      <Text style={styles.cardMeta}>
                        {job.enabled ? 'Enabled' : 'Paused'} · {job.schedule || 'No schedule'}
                      </Text>
                      <Text style={styles.cardBody}>
                        Next run {job.next_run_at ? formatRelativeTime(job.next_run_at) : 'unscheduled'}
                      </Text>
                    </Pressable>
                  ))
                )}
              </View>
            ) : null}

            {tab === 'system' ? (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>System</Text>
                <Pressable style={styles.navCard} onPress={() => navigate('/pair')}>
                  <Text style={styles.cardTitle}>Pair device</Text>
                  <Text style={styles.cardBody}>Finish trusted-device pairing or re-pair this phone.</Text>
                </Pressable>
                <Pressable style={styles.navCard} onPress={() => navigate('/settings')}>
                  <Text style={styles.cardTitle}>Settings</Text>
                  <Text style={styles.cardBody}>Backend URL, token state, and device verification.</Text>
                </Pressable>
                <Pressable style={styles.navCard} onPress={() => navigate('/diagnostics')}>
                  <Text style={styles.cardTitle}>Diagnostics</Text>
                  <Text style={styles.cardBody}>Request logs, socket events, and connectivity failures.</Text>
                </Pressable>
              </View>
            ) : null}
          </ScrollView>
        </SafeAreaFrame>
        <Pressable style={styles.backdrop} onPress={onClose} />
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(5, 8, 18, 0.55)',
    flexDirection: 'row',
  },
  backdrop: {
    flex: 1,
  },
  panel: {
    width: 320,
    backgroundColor: '#0e1630',
    borderRightWidth: 1,
    borderRightColor: '#1e294b',
    paddingHorizontal: 16,
    paddingBottom: 18,
    paddingTop: 10,
    gap: 14,
  },
  panelHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    paddingTop: 10,
    gap: 12,
  },
  headerCopy: {
    flex: 1,
    gap: 4,
  },
  brand: {
    color: '#ffffff',
    fontSize: 22,
    fontWeight: '700',
  },
  subhead: {
    color: '#8ca1c8',
    fontSize: 12,
  },
  close: {
    color: '#7cc7ff',
    fontWeight: '700',
  },
  tabRow: {
    flexDirection: 'row',
    gap: 8,
  },
  tabButton: {
    flex: 1,
    borderRadius: 12,
    paddingVertical: 10,
    alignItems: 'center',
    backgroundColor: '#16203d',
  },
  tabButtonActive: {
    backgroundColor: '#2d4674',
  },
  tabText: {
    color: '#ffffff',
    fontWeight: '700',
    fontSize: 13,
  },
  content: {
    gap: 16,
    paddingBottom: 22,
  },
  section: {
    gap: 12,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  sectionTitle: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '700',
  },
  hint: {
    color: '#b2c2e2',
    fontSize: 13,
    lineHeight: 19,
  },
  primaryButton: {
    backgroundColor: '#3b82f6',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  primaryText: {
    color: '#ffffff',
    fontWeight: '700',
  },
  ghostButton: {
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: '#172341',
  },
  ghostText: {
    color: '#dce8ff',
    fontWeight: '700',
  },
  listCard: {
    backgroundColor: '#141c33',
    borderRadius: 16,
    padding: 12,
    gap: 6,
  },
  listCardActive: {
    borderWidth: 1,
    borderColor: '#5da0ff',
    backgroundColor: '#1a2948',
  },
  navCard: {
    backgroundColor: '#141c33',
    borderRadius: 16,
    padding: 14,
    gap: 6,
  },
  cardTitle: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '700',
  },
  cardMeta: {
    color: '#8ca1c8',
    fontSize: 12,
  },
  cardBody: {
    color: '#d8e5fb',
    fontSize: 13,
    lineHeight: 18,
  },
  empty: {
    color: '#8ca1c8',
    fontSize: 13,
  },
});
