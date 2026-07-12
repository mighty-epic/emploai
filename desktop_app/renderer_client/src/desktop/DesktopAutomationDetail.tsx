import { Pressable, ScrollView, Text, View } from 'react-native';

import type { AutomationEventRun, CronFeedItem, PlannerContract, ProcessWait, ScheduledJob } from '@/lib/appApi';
import type { DesktopPressableState } from '@/lib/pressableState';
import { formatAbsoluteTime, formatRelativeTime } from '@/lib/time';
import { userFacingError } from '../../lib/diagnostics';
import { automationStyles as styles } from './DesktopAutomations.styles';
import {
  automationNeedsAttention,
  automationPermissionLabel,
  automationTargetLabel,
  type AutomationDetailTab,
} from './desktopAutomations';

type Props = {
  job: ScheduledJob;
  tab: AutomationDetailTab;
  feed: CronFeedItem[];
  runs: AutomationEventRun[];
  processWaits: ProcessWait[];
  plannerContracts: PlannerContract[];
  busyAction: string | null;
  onTabChange: (tab: AutomationDetailTab) => void;
  onEdit: () => void;
  onRun: () => void;
  onToggleEnabled: () => void;
  onArchive: () => void;
  onOpenChat: (sessionId: string) => void;
  onAcknowledge: (item: CronFeedItem) => void;
  onRunAction: (run: AutomationEventRun, action: 'cancel' | 'retry') => void;
  onProcessAction: (item: ProcessWait, action: 'cancel' | 'stop' | 'persist' | 'unpersist') => void;
  onPlannerSatisfied: (item: PlannerContract) => void;
};

const TABS: Array<{ key: AutomationDetailTab; label: string }> = [
  { key: 'overview', label: 'Overview' },
  { key: 'activity', label: 'Activity' },
  { key: 'advanced', label: 'Advanced' },
];

function buttonStyle(primary = false, danger = false) {
  return ({ hovered, pressed }: DesktopPressableState) => [
    styles.button,
    primary ? styles.primaryButton : null,
    danger ? styles.dangerButton : null,
    hovered ? styles.buttonHover : null,
    pressed ? styles.buttonPressed : null,
  ];
}

function displayTime(value?: string | null) {
  if (!value) return 'Not yet';
  return `${formatRelativeTime(value)} · ${formatAbsoluteTime(value)}`;
}

function InfoBlock({ label, value, wide = false }: { label: string; value: string; wide?: boolean }) {
  return (
    <View style={[styles.infoBlock, wide ? styles.infoBlockWide : null]}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text selectable style={styles.infoValue}>{value}</Text>
    </View>
  );
}

function EmptySection({ title, copy }: { title: string; copy: string }) {
  return (
    <View style={styles.listEmpty}>
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.emptyCopy}>{copy}</Text>
    </View>
  );
}

export function DesktopAutomationDetail({
  job,
  tab,
  feed,
  runs,
  processWaits,
  plannerContracts,
  busyAction,
  onTabChange,
  onEdit,
  onRun,
  onToggleEnabled,
  onArchive,
  onOpenChat,
  onAcknowledge,
  onRunAction,
  onProcessAction,
  onPlannerSatisfied,
}: Props) {
  const attention = automationNeedsAttention(job);
  const statusLabel = attention ? 'Needs Attention' : job.enabled ? 'Active' : 'Paused';
  const busy = Boolean(busyAction);
  const timezone = (() => {
    try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Local Time'; } catch { return 'Local Time'; }
  })();

  return (
    <ScrollView style={styles.detailScroll} contentContainerStyle={styles.detailContent}>
      <View style={styles.detailHeader}>
        <View style={styles.detailHeaderCopy}>
          <Text style={styles.eyebrow}>{statusLabel}</Text>
          <Text style={styles.detailTitle}>{job.name}</Text>
          <Text style={styles.detailSubtitle}>{job.schedule || 'No schedule'} · {automationPermissionLabel(job.permission_mode)}</Text>
        </View>
        <View accessibilityRole="toolbar" accessibilityLabel="Automation actions" style={styles.detailActions}>
          <Pressable accessibilityRole="button" disabled={busy} style={buttonStyle(true)} onPress={onRun}>
            <Text style={[styles.buttonText, styles.primaryButtonText]}>{busyAction === 'run' ? 'Queueing…' : 'Run Now'}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" disabled={busy} style={buttonStyle()} onPress={onEdit}>
            <Text style={styles.buttonText}>Edit</Text>
          </Pressable>
          <Pressable accessibilityRole="button" disabled={busy} style={buttonStyle()} onPress={onToggleEnabled}>
            <Text style={styles.buttonText}>{busyAction === 'toggle' ? 'Updating…' : job.enabled ? 'Pause' : 'Resume'}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" disabled={busy} style={buttonStyle(false, true)} onPress={onArchive}>
            <Text style={[styles.buttonText, styles.dangerText]}>{busyAction === 'archive' ? 'Archiving…' : 'Archive'}</Text>
          </Pressable>
        </View>
      </View>

      <View accessibilityRole="tablist" style={styles.tabRow}>
        {TABS.map((item) => {
          const selected = tab === item.key;
          return (
            <Pressable
              key={item.key}
              accessibilityRole="tab"
              accessibilityState={{ selected }}
              style={({ pressed }: DesktopPressableState) => [styles.tab, selected ? styles.tabActive : null, pressed ? styles.buttonPressed : null]}
              onPress={() => onTabChange(item.key)}
            >
              <Text style={[styles.tabText, selected ? styles.tabTextActive : null]}>{item.label}</Text>
            </Pressable>
          );
        })}
      </View>

      {tab === 'overview' ? (
        <>
          <View style={styles.runway}>
            <View pointerEvents="none" style={styles.runwayGlow} />
            <Text style={styles.runwayKicker}>Next Scheduled Run</Text>
            <Text style={styles.runwayTime}>{displayTime(job.next_run_at)}</Text>
            <Text style={styles.runwaySchedule}>{job.schedule || 'No schedule configured'}</Text>
            <View style={styles.runwayLine} />
            <View style={styles.runwayMarkers}>
              <View style={styles.runwayMarker} />
              <View style={[styles.runwayMarker, styles.runwayMarkerMuted]} />
              <View style={[styles.runwayMarker, styles.runwayMarkerMuted]} />
            </View>
            <Text style={styles.runwayMeta}>{timezone} · Missed recurring runs resume at the next future occurrence.</Text>
          </View>
          {attention ? (
            <View accessibilityRole="alert" style={styles.warningPanel}>
              <Text style={styles.warningTitle}>This automation needs review.</Text>
              <Text style={styles.warningCopy}>Open Activity to inspect failed or blocked runs before resuming unattended work.</Text>
            </View>
          ) : null}
          <View style={styles.contentGrid}>
            <InfoBlock label="Task" value={job.prompt || 'No task description'} wide />
            <InfoBlock label="Destination" value={automationTargetLabel(job)} />
            <InfoBlock label="Chat" value={job.target_chat_id ? 'Specific Chat' : 'Choose Automatically'} />
            <InfoBlock label="Safety" value={automationPermissionLabel(job.permission_mode)} />
            <InfoBlock label="Tool Packs" value={(job.tool_packs || []).join(', ') || 'Use the destination’s configured tools'} />
          </View>
          <View style={styles.statsRow}>
            <View style={styles.stat}><Text style={styles.statValue}>{job.run_count || 0}</Text><Text style={styles.statLabel}>Total Runs</Text></View>
            <View style={styles.stat}><Text style={styles.statValue}>{job.error_count || 0}</Text><Text style={styles.statLabel}>Errors</Text></View>
            <View style={styles.stat}><Text style={styles.statValue}>{job.enabled ? 'On' : 'Off'}</Text><Text style={styles.statLabel}>Scheduling</Text></View>
          </View>
        </>
      ) : null}

      {tab === 'activity' ? (
        <>
          <View style={styles.section}>
            <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Runs</Text><Text style={styles.sectionMeta}>{runs.length}</Text></View>
            {runs.length ? runs.map((run) => {
              const runStatus = String(run.status || 'unknown');
              return (
                <View key={run.event_run_id} style={styles.activityRow}>
                  <View style={styles.activityTop}>
                    <Text style={styles.activityTitle}>{runStatus.replace(/_/g, ' ')}</Text>
                    <Text style={styles.activityMeta}>Attempt {run.attempt}/{run.max_attempts} · {displayTime(run.created_at)}</Text>
                  </View>
                  {run.result ? <Text style={styles.activityCopy}>{run.result}</Text> : null}
                  {run.error ? <Text style={styles.warningCopy}>{userFacingError(run.error, 'The run failed. Review its destination and provider settings, then retry.')}</Text> : null}
                  <View style={styles.inlineActions}>
                    {['queued', 'running'].includes(runStatus.toLowerCase()) ? <Pressable accessibilityRole="button" style={styles.textAction} onPress={() => onRunAction(run, 'cancel')}><Text style={[styles.textActionText, styles.textActionDanger]}>Cancel Run</Text></Pressable> : null}
                    {['failed', 'blocked', 'canceled'].includes(runStatus.toLowerCase()) ? <Pressable accessibilityRole="button" style={styles.textAction} onPress={() => onRunAction(run, 'retry')}><Text style={styles.textActionText}>Retry Run</Text></Pressable> : null}
                  </View>
                </View>
              );
            }) : <EmptySection title="No runs yet" copy="Scheduled and manual runs will appear here with their result and recovery actions." />}
          </View>
          <View style={styles.section}>
            <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Output</Text><Text style={styles.sectionMeta}>{feed.length}</Text></View>
            {feed.length ? feed.map((item) => (
              <View key={item.id} style={styles.activityRow}>
                <View style={styles.activityTop}>
                  <Text style={styles.activityTitle}>{item.kind || 'Automation Update'}</Text>
                  <Text style={styles.activityMeta}>{displayTime(item.timestamp || item.scheduled_for)}</Text>
                </View>
                <Text style={styles.activityCopy}>{item.content}</Text>
                <View style={styles.inlineActions}>
                  {item.session_id ? <Pressable accessibilityRole="button" style={styles.textAction} onPress={() => onOpenChat(item.session_id!)}><Text style={styles.textActionText}>Open Chat</Text></Pressable> : null}
                  {!item.acknowledged_at ? <Pressable accessibilityRole="button" style={styles.textAction} onPress={() => onAcknowledge(item)}><Text style={styles.textActionText}>Mark Reviewed</Text></Pressable> : null}
                </View>
              </View>
            )) : <EmptySection title="No output yet" copy="Results and noteworthy updates from this automation will appear here." />}
          </View>
        </>
      ) : null}

      {tab === 'advanced' ? (
        <>
          <View style={styles.warningPanel}>
            <Text style={styles.warningTitle}>Scoped Diagnostics</Text>
            <Text style={styles.warningCopy}>Only process waits and planner checks connected to this automation or its target chat are shown here.</Text>
          </View>
          <View style={styles.section}>
            <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Background Processes</Text><Text style={styles.sectionMeta}>{processWaits.length}</Text></View>
            {processWaits.length ? processWaits.map((item) => (
              <View key={item.process_wait_id} style={styles.activityRow}>
                <Text style={styles.activityTitle}>{item.command_id}</Text>
                <Text style={styles.activityMeta}>{String(item.status || '').replace(/_/g, ' ')} · {item.persistent ? 'Persistent' : 'This Run Only'}</Text>
                {item.command ? <Text selectable style={styles.codeText}>{item.command}</Text> : null}
                <View style={styles.inlineActions}>
                  {!item.completed_at ? <Pressable accessibilityRole="button" style={styles.textAction} onPress={() => onProcessAction(item, 'cancel')}><Text style={[styles.textActionText, styles.textActionDanger]}>Cancel Wait</Text></Pressable> : null}
                  {!item.completed_at ? <Pressable accessibilityRole="button" style={styles.textAction} onPress={() => onProcessAction(item, 'stop')}><Text style={[styles.textActionText, styles.textActionDanger]}>Stop Process</Text></Pressable> : null}
                  <Pressable accessibilityRole="button" style={styles.textAction} onPress={() => onProcessAction(item, item.persistent ? 'unpersist' : 'persist')}><Text style={styles.textActionText}>{item.persistent ? 'Use This Run Only' : 'Keep Monitoring'}</Text></Pressable>
                </View>
              </View>
            )) : <EmptySection title="No linked background processes" copy="Long-running commands started by this automation will appear here." />}
          </View>
          <View style={styles.section}>
            <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Planner Checks</Text><Text style={styles.sectionMeta}>{plannerContracts.length}</Text></View>
            {plannerContracts.length ? plannerContracts.map((item) => (
              <View key={item.contract_id} style={styles.activityRow}>
                <Text style={styles.activityTitle}>{item.action || 'Completion Check'}</Text>
                <Text style={styles.activityMeta}>{String(item.status || '').replace(/_/g, ' ')}</Text>
                {Array.isArray(item.contract?.requirements) ? item.contract.requirements.slice(0, 4).map((requirement) => <Text key={String(requirement)} style={styles.activityCopy}>• {String(requirement)}</Text>) : null}
                {item.status !== 'satisfied' ? <Pressable accessibilityRole="button" style={styles.textAction} onPress={() => onPlannerSatisfied(item)}><Text style={styles.textActionText}>Mark Satisfied</Text></Pressable> : null}
              </View>
            )) : <EmptySection title="No linked planner checks" copy="Completion requirements for this automation will appear here." />}
          </View>
        </>
      ) : null}
    </ScrollView>
  );
}
