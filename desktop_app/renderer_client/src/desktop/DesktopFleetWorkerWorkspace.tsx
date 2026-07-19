import { Pressable, StyleSheet, Text, View } from 'react-native';

import type {
  DesktopFleetIdentity,
  DesktopFleetReport,
  DesktopFleetSnapshot,
  DesktopFleetTask,
} from '@/lib/desktopBridge';
import { DESKTOP_UI as UI } from './desktopUiTokens';
import { FLEET_TYPE as TYPE } from './desktopFleetUi';

const ACTIVE_TASK_STATES = new Set(['running', 'paused', 'blocked', 'needs_review']);

function displayToken(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function taskTime(task: DesktopFleetTask) {
  const value = task.updated_at || task.created_at;
  if (!value) return null;
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime()) ? null : timestamp.toLocaleString();
}

function reportForTask(reports: DesktopFleetReport[], taskId: string) {
  return reports.find((report) => report.task_id === taskId) || null;
}

export function DesktopFleetWorkerWorkspace({
  snapshot,
  identity,
  onSwitchToManager,
}: {
  snapshot: DesktopFleetSnapshot;
  identity: DesktopFleetIdentity;
  onSwitchToManager?: () => void;
}) {
  const worker = (snapshot.workers || []).find((item) => (
    item.worker_id === identity.worker_id || item.instance_id === identity.instance_id
  )) || null;
  const workerId = String(worker?.worker_id || identity.worker_id || '');
  const tasks = (snapshot.tasks || [])
    .filter((task) => task.worker_id === workerId)
    .sort((left, right) => String(right.updated_at || right.created_at || '').localeCompare(String(left.updated_at || left.created_at || '')));
  const reports = (snapshot.reports || [])
    .filter((report) => report.worker_id === workerId)
    .sort((left, right) => String(right.created_at || '').localeCompare(String(left.created_at || '')));
  const activeTask = tasks.find((task) => (
    task.task_id === worker?.active_task_id || ACTIVE_TASK_STATES.has(task.status)
  )) || null;
  const queuedTasks = tasks.filter((task) => task.status === 'queued');
  const recentTasks = tasks.filter((task) => task.task_id !== activeTask?.task_id).slice(0, 8);
  const toolPacks = worker?.enabled_tool_packs || identity.enabled_tool_packs || [];
  const profile = worker?.tool_profile || identity.tool_profile || 'custom_execution';
  const status = worker?.status || identity.status || 'idle';

  return (
    <View style={styles.workspace}>
      <View style={styles.hero}>
        <View style={styles.heroCopy}>
          <View style={styles.titleRow}>
            <Text style={styles.title}>{identity.display_name}</Text>
            <View style={styles.executionBadge}>
              <Text style={styles.executionBadgeText}>WORKER</Text>
            </View>
          </View>
          <Text style={styles.detail}>Direct execution on this computer.</Text>
        </View>
        <View style={styles.heroActions}>
          {onSwitchToManager ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Switch to the manager console"
              onPress={onSwitchToManager}
              style={({ hovered }: any) => [styles.switchButton, hovered ? styles.switchButtonHovered : null]}
            >
              <Text style={styles.switchButtonText}>Switch to Manager Console</Text>
            </Pressable>
          ) : null}
        </View>
      </View>

      <Text style={styles.boundaryText}>Connected-computer controls are unavailable in Worker view.</Text>

      <View style={styles.summaryGrid}>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>STATUS</Text>
          <Text style={styles.summaryValue}>{displayToken(status)}</Text>
          <Text style={styles.summaryMeta}>{worker?.detail || (activeTask ? 'Task in progress' : 'Ready')}</Text>
        </View>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>TOOL PROFILE</Text>
          <Text style={styles.summaryValue}>{displayToken(profile)}</Text>
          <Text style={styles.summaryMeta}>{toolPacks.length} execution pack{toolPacks.length === 1 ? '' : 's'}</Text>
        </View>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryLabel}>QUEUE</Text>
          <Text style={styles.summaryValue}>{queuedTasks.length}</Text>
          <Text style={styles.summaryMeta}>{queuedTasks.length ? 'Waiting' : 'Clear'}</Text>
        </View>
      </View>

      <View style={styles.profileCard}>
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Tools</Text>
          <Text style={styles.sectionMeta}>{toolPacks.length} enabled</Text>
        </View>
        <View style={styles.packList}>
          {toolPacks.length ? toolPacks.map((pack) => (
            <View key={pack} style={styles.packRow}>
              <View style={styles.packDot} />
              <Text style={styles.packName}>{displayToken(pack)}</Text>
            </View>
          )) : <Text style={styles.emptyText}>No execution packs are configured for this worker.</Text>}
        </View>
      </View>

      <View style={styles.taskGrid}>
        <View style={styles.taskColumn}>
          <Text style={styles.sectionTitle}>Current task</Text>
          {activeTask ? (
            <View style={styles.taskCard}>
              <View style={styles.taskHeader}>
                <Text style={styles.taskStatus}>{displayToken(activeTask.status)}</Text>
                {taskTime(activeTask) ? <Text style={styles.taskTime}>{taskTime(activeTask)}</Text> : null}
              </View>
              <Text style={styles.taskPrompt}>{activeTask.prompt}</Text>
              {reportForTask(reports, activeTask.task_id)?.summary ? (
                <Text style={styles.taskReport}>{reportForTask(reports, activeTask.task_id)?.summary}</Text>
              ) : null}
            </View>
          ) : (
            <View style={styles.emptyCard}>
              <Text style={styles.emptyTitle}>No active task</Text>
              <Text style={styles.emptyText}>Use Worker Chat to start work.</Text>
            </View>
          )}
        </View>

        <View style={styles.taskColumn}>
          <Text style={styles.sectionTitle}>Recent tasks</Text>
          {recentTasks.length ? recentTasks.map((task) => {
            const report = reportForTask(reports, task.task_id);
            return (
              <View key={task.task_id} style={styles.historyRow}>
                <View style={styles.historyHeader}>
                  <Text style={styles.historyStatus}>{displayToken(task.status)}</Text>
                  {taskTime(task) ? <Text style={styles.taskTime}>{taskTime(task)}</Text> : null}
                </View>
                <Text style={styles.historyPrompt} numberOfLines={3}>{task.prompt}</Text>
                {report?.summary ? <Text style={styles.historyReport} numberOfLines={3}>{report.summary}</Text> : null}
              </View>
            );
          }) : (
            <View style={styles.emptyCard}>
              <Text style={styles.emptyTitle}>No recent tasks</Text>
              <Text style={styles.emptyText}>Completed work will appear here.</Text>
            </View>
          )}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  workspace: { gap: 18 },
  hero: { paddingVertical: 4, gap: 16, flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center' },
  heroCopy: { flex: 1, minWidth: 300, maxWidth: 760 },
  titleRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 9 },
  heroActions: { alignItems: 'flex-end' },
  title: { color: UI.color.text, fontSize: TYPE.heroTitle, fontWeight: '700' },
  detail: { marginTop: 5, color: UI.color.textMuted, fontSize: TYPE.body, lineHeight: TYPE.bodyLine },
  executionBadge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: UI.radius.pill, backgroundColor: UI.color.successSoft },
  executionBadgeText: { color: UI.color.success, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '700', letterSpacing: 0.5 },
  switchButton: { minHeight: 38, paddingHorizontal: 12, borderRadius: UI.radius.control, backgroundColor: UI.color.surfaceRaised, alignItems: 'center', justifyContent: 'center' },
  switchButtonHovered: { backgroundColor: UI.color.surfaceHover },
  switchButtonText: { color: UI.color.text, fontSize: TYPE.body, fontWeight: '600' },
  boundaryText: { marginTop: -10, color: UI.color.textSubtle, fontSize: TYPE.body, lineHeight: TYPE.bodyLine },
  summaryGrid: { flexDirection: 'row', flexWrap: 'wrap', borderTopWidth: 1, borderBottomWidth: 1, borderColor: UI.color.border },
  summaryCard: { flexGrow: 1, flexBasis: 170, minWidth: 150, paddingVertical: 12, paddingRight: 18, gap: 3 },
  summaryLabel: { color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '600', letterSpacing: 0.5 },
  summaryValue: { color: UI.color.text, fontSize: TYPE.sectionTitle, fontWeight: '700' },
  summaryMeta: { color: UI.color.textMuted, fontSize: TYPE.micro, lineHeight: 15 },
  profileCard: { gap: 10 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  sectionTitle: { color: UI.color.text, fontSize: TYPE.sectionTitle, fontWeight: '700' },
  sectionMeta: { color: UI.color.textSubtle, fontSize: TYPE.micro },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  capabilityChip: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: UI.radius.pill, backgroundColor: UI.color.successSoft },
  capabilityChipText: { color: UI.color.success, fontSize: TYPE.micro, fontWeight: '600' },
  packList: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  packRow: { minHeight: 32, paddingHorizontal: 9, borderRadius: UI.radius.control, backgroundColor: UI.color.surfaceMuted, flexDirection: 'row', alignItems: 'center', gap: 7 },
  packDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#6ce2ae' },
  packName: { color: UI.color.textMuted, fontSize: TYPE.body, fontWeight: '600' },
  taskGrid: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-start', gap: 28 },
  taskColumn: { flexGrow: 1, flexBasis: 360, minWidth: 290, paddingTop: 14, gap: 9, borderTopWidth: 1, borderTopColor: UI.color.border },
  taskCard: { padding: 13, gap: 8, borderRadius: UI.radius.control, backgroundColor: UI.color.successSoft },
  taskHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 },
  taskStatus: { color: '#6ce2ae', fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '700', letterSpacing: 0.5 },
  taskTime: { color: UI.color.textSubtle, fontFamily: UI.type.mono, fontSize: TYPE.micro },
  taskPrompt: { color: UI.color.text, fontSize: TYPE.body, fontWeight: '600', lineHeight: TYPE.bodyLine },
  taskReport: { paddingTop: 8, borderTopWidth: 1, borderTopColor: '#315046', color: '#a8c6bb', fontSize: TYPE.body, lineHeight: TYPE.bodyLine },
  historyRow: { paddingVertical: 11, gap: 5, borderBottomWidth: 1, borderBottomColor: UI.color.border },
  historyHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 },
  historyStatus: { color: UI.color.accentStrong, fontFamily: UI.type.mono, fontSize: TYPE.micro, fontWeight: '700' },
  historyPrompt: { color: UI.color.text, fontSize: TYPE.body, fontWeight: '600', lineHeight: TYPE.bodyLine },
  historyReport: { color: UI.color.textMuted, fontSize: TYPE.body, lineHeight: TYPE.bodyLine },
  emptyCard: { paddingVertical: 12, gap: 4 },
  emptyTitle: { color: UI.color.textMuted, fontSize: TYPE.body, fontWeight: '600' },
  emptyText: { color: UI.color.textMuted, fontSize: TYPE.body, lineHeight: TYPE.bodyLine },
});
