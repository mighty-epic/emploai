import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { loadAppConfig, type AppConnectionMode } from '../../lib/appConfig';
import { reconcileRemoteAccountConfig } from '../../lib/accountSession';
import { describeError, shortStatusText, userFacingError } from '../../lib/diagnostics';
import { AppDrawer, type DrawerTab } from '@/components/AppDrawer';
import { CollapsibleSection } from '@/components/CollapsibleSection';
import { InfoHint } from '@/components/InfoHint';
import { PageHeader } from '@/components/PageHeader';
import { useConfirmation } from '@/components/ConfirmationDialog';
import { SectionTabs } from '@/components/ParityUI';
import {
  appendAgentMemoryNote,
  clearAgentPendingFiles,
  configureAgent,
  deleteSession,
  fetchAgentConfig,
  fetchAgentOverview,
  fetchJobs,
  fetchSessions,
  fetchSidebarState,
  fetchSubAgents,
  forgetLastAgentMessage,
  resetAgentContext,
  searchAgentMemory,
  spawnSubAgent,
  type AgentOverview,
  type ConfigEntry,
  type MemorySearchResult,
  type ScheduledJob,
  type SidebarState,
  type SessionSummary,
  type SubAgentStatus,
  updateAgentConfig,
  updateSidebarState,
} from '@/lib/appApi';
import { formatAbsoluteTime, formatRelativeTime } from '@/lib/time';

const MAX_TURN_OPTIONS = [50, 100, 200, 500];
const AGENT_NO_ACTIVE_SESSION_STATUS = 'Open or select a chat before starting an agent task.';
type AgentSection = 'model' | 'runtime' | 'tasks' | 'tools' | 'memory' | 'analytics' | 'config' | 'diagnostics';

function formatConfigValue(value: unknown) {
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metricCard}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

function ActionChip({
  label,
  active = false,
  onPress,
}: {
  label: string;
  active?: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable style={[styles.chip, active ? styles.chipActive : null]} onPress={onPress}>
      <Text style={[styles.chipText, active ? styles.chipTextActive : null]}>{label}</Text>
    </Pressable>
  );
}

export default function AgentScreen() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [overview, setOverview] = useState<AgentOverview | null>(null);
  const [subAgents, setSubAgents] = useState<SubAgentStatus | null>(null);
  const [configEntries, setConfigEntries] = useState<ConfigEntry[]>([]);
  const [memoryResults, setMemoryResults] = useState<MemorySearchResult[]>([]);
  const [sidebarState, setSidebarState] = useState<SidebarState | null>(null);
  const [status, setStatus] = useState('idle');
  const [apiBaseUrl, setApiBaseUrl] = useState('');
  const [token, setToken] = useState('');
  const [connectionMode, setConnectionMode] = useState<AppConnectionMode>('direct_backend');
  const [pairedDesktopId, setPairedDesktopId] = useState('');
  const [configLoaded, setConfigLoaded] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>('system');
  const [workspaceDraft, setWorkspaceDraft] = useState('');
  const [heartbeatDraft, setHeartbeatDraft] = useState('1800');
  const { confirm, confirmationDialog } = useConfirmation();
  const [memoryQuery, setMemoryQuery] = useState('');
  const [memoryNote, setMemoryNote] = useState('');
  const [configKey, setConfigKey] = useState('');
  const [configValue, setConfigValue] = useState('');
  const [subAgentPrompt, setSubAgentPrompt] = useState('');
  const [subAgentHeadless, setSubAgentHeadless] = useState(true);
  const [subAgentTurns, setSubAgentTurns] = useState(50);
  const [activeSection, setActiveSection] = useState<AgentSection>('model');

  useEffect(() => {
    loadAppConfig()
      .then(async (loadedConfig) => {
        const { config } = await reconcileRemoteAccountConfig(loadedConfig);
        setApiBaseUrl(config.apiBaseUrl);
        setToken(config.accountToken || config.accessToken);
        setConnectionMode(config.connectionMode);
        setPairedDesktopId(config.pairedDesktopId);
        setConfigLoaded(true);
      })
      .catch(() => {
        setStatus('Setup needs attention.');
        setConfigLoaded(true);
      });
  }, []);

  const agentConnected = Boolean(apiBaseUrl && token && !(connectionMode === 'remote_cloud' && !pairedDesktopId));
  const agentSetupStatus = !configLoaded
    ? 'loading agent setup'
    : !apiBaseUrl
      ? 'Connect agent: add the backend URL first'
      : !token
        ? 'Connect agent: sign in and pair this phone first'
        : connectionMode === 'remote_cloud' && !pairedDesktopId
          ? 'Connect agent: pair this phone with a desktop first'
        : 'Agent controls ready';
  const ensureAgentConnection = () => {
    if (!agentConnected) {
      setStatus(agentSetupStatus);
      return false;
    }
    return true;
  };
  const ensureAgentActiveSession = () => {
    if (!ensureAgentConnection()) return false;
    if (!overview?.session_id) {
      setStatus(AGENT_NO_ACTIVE_SESSION_STATUS);
      return false;
    }
    return true;
  };

  const loadControlCenter = async () => {
    if (!agentConnected) {
      setStatus(agentSetupStatus);
      return;
    }

    setStatus('loading');
    try {
      const [sessionList, jobList, nextSidebarState] = await Promise.all([
        fetchSessions(apiBaseUrl, token),
        fetchJobs(apiBaseUrl, token),
        fetchSidebarState(apiBaseUrl, token).catch(() => null),
      ]);
      let nextOverview: AgentOverview | null = null;
      let overviewError: unknown = null;
      let configList: { items: ConfigEntry[] } = { items: [] };
      let subAgentStatus: SubAgentStatus | null = null;
      try {
        nextOverview = await fetchAgentOverview(apiBaseUrl, token);
      } catch (error) {
        overviewError = error;
      }
      if (nextOverview?.session_id) {
        [configList, subAgentStatus] = await Promise.all([
          fetchAgentConfig(apiBaseUrl, token, undefined, nextOverview.session_id).catch(() => ({ items: [] })),
          fetchSubAgents(apiBaseUrl, token, nextOverview.session_id).catch(() => null),
        ]);
      }

      setSessions(Array.isArray(sessionList) ? sessionList : []);
      setJobs(Array.isArray(jobList) ? jobList : []);
      setOverview(nextOverview);
      setConfigEntries(Array.isArray(configList.items) ? configList.items : []);
      setSubAgents(subAgentStatus);
      if (nextSidebarState?.state) {
        setSidebarState(nextSidebarState.state);
      }
      setWorkspaceDraft(nextOverview?.workspace || '');
      setHeartbeatDraft(String(nextOverview?.heartbeat.interval_seconds || 1800));
      if (nextOverview?.session_id) {
        setStatus('ready');
      } else if (overviewError && !describeError(overviewError).toLowerCase().includes('no current session')) {
        setStatus(userFacingError(overviewError, 'Agent is not ready.'));
      } else {
        setStatus(AGENT_NO_ACTIVE_SESSION_STATUS);
      }
    } catch (error) {
      setStatus(userFacingError(error, 'Agent is not ready.'));
    }
  };

  useEffect(() => {
    if (!configLoaded) return;
    void loadControlCenter();
  }, [apiBaseUrl, configLoaded, connectionMode, pairedDesktopId, token]);

  const applyConfig = async (payload: Parameters<typeof configureAgent>[2]) => {
    if (!ensureAgentActiveSession()) return;
    const activeSessionId = overview?.session_id || undefined;
    if (!activeSessionId) {
      setStatus(AGENT_NO_ACTIVE_SESSION_STATUS);
      return;
    }
    setStatus('saving changes');
    try {
      await configureAgent(apiBaseUrl, token, payload, activeSessionId);
      await loadControlCenter();
    } catch (error) {
      setStatus(userFacingError(error, 'Changes were not saved.'));
    }
  };

  const runAction = async (action: () => Promise<unknown>, successStatus: string) => {
    if (!ensureAgentActiveSession()) return;
    setStatus(successStatus);
    try {
      await action();
      await loadControlCenter();
    } catch (error) {
      setStatus(userFacingError(error, 'Action did not finish.'));
    }
  };

  const resetCurrentContext = async () => {
    if (!ensureAgentActiveSession()) return;
    const ok = await confirm({
      title: 'Reset chat context?',
      message: 'This clears the active agent context for this chat. The visible history stays, but the runtime will start fresh.',
      confirmLabel: 'Reset',
      tone: 'danger',
    });
    if (!ok) return;
    await runAction(
      () => resetAgentContext(apiBaseUrl, token, overview?.session_id || undefined),
      'resetting context'
    );
  };

  const persistSidebarState = async (nextState: SidebarState) => {
    setSidebarState(nextState);
    if (!agentConnected) return;
    try {
      const result = await updateSidebarState(apiBaseUrl, token, nextState);
      if (result.state) {
        setSidebarState(result.state);
      }
      setStatus('sidebar updated');
    } catch (error) {
      setStatus(userFacingError(error, 'Sidebar was not saved.'));
    }
  };

  const deleteConversation = async (sessionId: string) => {
    if (!sessionId) {
      setStatus('missing chat');
      return;
    }
    if (!ensureAgentConnection()) return;
    setStatus('deleting chat');
    try {
      await deleteSession(apiBaseUrl, token, sessionId);
      setSessions((current) => current.filter((session) => session.id !== sessionId));
      if (overview?.session_id === sessionId) {
        setOverview(null);
        router.push('/chat' as never);
      } else {
        await loadControlCenter();
      }
      setStatus('chat deleted');
    } catch (error) {
      setStatus(userFacingError(error, 'Chat was not deleted.'));
    }
  };

  const startAgentTask = async () => {
    const prompt = subAgentPrompt.trim();
    if (!prompt) {
      setStatus('enter an agent task first');
      return;
    }
    const activeSessionId = overview?.session_id || '';
    if (!activeSessionId) {
      setStatus(AGENT_NO_ACTIVE_SESSION_STATUS);
      return;
    }
    await runAction(
      async () => {
        await spawnSubAgent(
          apiBaseUrl,
          token,
          { prompt, headless: subAgentHeadless, max_turns: subAgentTurns },
          activeSessionId
        );
        setSubAgentPrompt('');
      },
      'starting agent task'
    );
  };

  const activeSession = overview?.session_id
    ? sessions.find((session) => session.id === overview.session_id)
    : undefined;
  const agentRestriction = !agentConnected
    ? 'Connect this phone first.'
    : !overview?.session_id
      ? AGENT_NO_ACTIVE_SESSION_STATUS
    : 'Focused agent tools are ready.';
  const agentRestrictionDetail = !agentConnected
    ? 'Chat, Fleet, and Agent controls need a signed-in mobile account paired to a trusted desktop.'
    : !overview?.session_id
      ? 'Open a chat first so the agent knows which runtime session to control.'
      : 'Use Chat for text turns, Fleet for worker queues, and this page for focused agent tasks.';
  const agentTaskStartDisabled = !agentConnected || !overview?.session_id || !subAgentPrompt.trim();
  const agentTaskRefreshDisabled = !agentConnected || !overview?.session_id;
  const agentTabs = [
    { key: 'model' as const, label: 'Model' },
    { key: 'runtime' as const, label: 'Runtime' },
    { key: 'tasks' as const, label: 'Tasks', badge: subAgents?.running || null },
    { key: 'tools' as const, label: 'Tools', badge: overview?.enabled_tool_packs?.length || null },
    { key: 'memory' as const, label: 'Memory' },
    { key: 'analytics' as const, label: 'Analytics' },
    { key: 'config' as const, label: 'Config' },
    { key: 'diagnostics' as const, label: 'Diagnostics' },
  ];

  return (
    <SafeAreaView edges={['top', 'left', 'right']} style={styles.container}>
      <AppDrawer
        visible={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        initialTab={drawerTab}
        sessions={sessions}
        jobs={jobs}
        activeSessionId={overview?.session_id || undefined}
        backendLabel={apiBaseUrl || 'Backend not configured'}
        sidebarState={sidebarState}
        onCreateSession={(workspace) => {
          setDrawerOpen(false);
          router.push({ pathname: '/chat', params: { newSession: '1', workspace } });
        }}
        onSelectSession={(sessionId) => {
          setDrawerOpen(false);
          router.push({ pathname: '/chat', params: { sessionId } });
        }}
        onDeleteSession={(sessionId) => {
          void deleteConversation(sessionId);
        }}
        onSidebarStateChange={(nextState) => {
          void persistSidebarState(nextState);
        }}
      />
      {confirmationDialog}

      <View style={styles.modeTabs}>
        <Pressable accessibilityRole="button" accessibilityLabel="Open Chat" style={styles.modeTab} onPress={() => router.push('/chat' as never)}>
          <Text style={styles.modeTabText}>Chat</Text>
        </Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel="Open Fleet" style={styles.modeTab} onPress={() => router.push('/fleet' as never)}>
          <Text style={styles.modeTabText}>Fleet</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Agent selected"
          accessibilityState={{ selected: true }}
          style={[styles.modeTab, styles.modeTabActive]}
        >
          <Text style={[styles.modeTabText, styles.modeTabTextActive]}>Agent</Text>
        </Pressable>
      </View>

      <PageHeader
        title="Agent controls"
        subtitle="Model, runtime, tools, memory, analytics, config, and diagnostics."
        right={(
          <View style={styles.actionsRow}>
            <Pressable
              style={styles.topButton}
              onPress={() => {
                setDrawerTab('system');
                setDrawerOpen(true);
              }}
            >
              <Text style={styles.topButtonText}>Sidebar</Text>
            </Pressable>
            <Pressable style={styles.topButton} onPress={() => void loadControlCenter()}>
              <Text style={styles.topButtonText}>Refresh</Text>
            </Pressable>
          </View>
        )}
      />

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.summaryRow}>
        <MetricCard label="Status" value={shortStatusText(status)} />
        <MetricCard label="Model" value={overview?.current_model || 'Unknown'} />
        <MetricCard label="Variant" value={overview?.current_variant || 'Unknown'} />
        <MetricCard label="Planner" value={overview?.planner_model || 'Automatic'} />
        <MetricCard label="Turns" value={overview ? String(overview.max_turns) : '-'} />
        <MetricCard label="Session" value={activeSession?.name || 'No session'} />
      </ScrollView>

      <SectionTabs tabs={agentTabs} active={activeSection} onChange={setActiveSection} />

      <ScrollView style={styles.body} contentContainerStyle={styles.bodyContent}>
        <View style={styles.heroCard}>
          <Text style={styles.heroTitle}>Advanced controls</Text>
          <Text style={styles.heroText}>
            Use this page for controls that should not crowd the chat composer.
          </Text>
          {activeSession ? (
            <Text style={styles.heroMeta}>
              Active session: {activeSession.name} · {activeSession.message_count} messages · updated{' '}
              {formatRelativeTime(activeSession.updated_at)}
            </Text>
          ) : null}
        </View>

        <View style={styles.warningCard}>
          <View style={styles.warningHeader}>
            <Text style={styles.warningTitle}>Agent availability</Text>
            <InfoHint text={agentRestrictionDetail} />
          </View>
          <Text style={styles.warningText}>{agentRestriction}</Text>
          <View style={styles.actionsRow}>
            <Pressable accessibilityRole="button" accessibilityLabel="Open Chat from Agent" style={styles.secondaryButton} onPress={() => router.push('/chat' as never)}>
              <Text style={styles.secondaryButtonText}>Open Chat</Text>
            </Pressable>
            <Pressable accessibilityRole="button" accessibilityLabel="Open Fleet from Agent" style={styles.secondaryButton} onPress={() => router.push('/fleet' as never)}>
              <Text style={styles.secondaryButtonText}>Open Fleet</Text>
            </Pressable>
          </View>
        </View>

        <View pointerEvents={agentConnected && overview?.session_id ? 'auto' : 'none'} style={(!agentConnected || !overview?.session_id) ? styles.disabledControlsGroup : null}>
        {activeSection === 'model' ? (
        <CollapsibleSection
          title="Model and execution"
          meta={overview ? `${overview.current_model} · ${overview.current_variant} · ${overview.max_turns} turns` : 'Choose model, variant, and task limits'}
          defaultExpanded
        >
          {overview?.model_groups.map((group) => (
            <View key={group.provider} style={styles.groupBlock}>
              <Text style={styles.groupTitle}>{group.provider.toUpperCase()}</Text>
              <View style={styles.chipRow}>
                {group.models.map((model) => (
                  <ActionChip
                    key={model}
                    label={model}
                    active={model === overview.current_model}
                    onPress={() => void applyConfig({ model })}
                  />
                ))}
              </View>
            </View>
          ))}

          <View style={styles.groupBlock}>
            <Text style={styles.groupTitle}>Variant</Text>
            <View style={styles.chipRow}>
              {(overview?.available_variants || []).map((variant) => (
                <ActionChip
                  key={variant}
                  label={variant}
                  active={variant === overview?.current_variant}
                  onPress={() => void applyConfig({ variant })}
                />
              ))}
            </View>
          </View>

          <View style={styles.groupBlock}>
            <Text style={styles.groupTitle}>Planner model</Text>
            <View style={styles.chipRow}>
              <ActionChip
                label="Automatic"
                active={!overview?.planner_model}
                onPress={() => void applyConfig({ planner_model: null })}
              />
              {(overview?.available_planner_models || []).map((model) => (
                <ActionChip
                  key={`planner-${model}`}
                  label={model}
                  active={model === overview?.planner_model}
                  onPress={() => void applyConfig({ planner_model: model })}
                />
              ))}
            </View>
          </View>

          <View style={styles.groupBlock}>
            <Text style={styles.groupTitle}>Max turns</Text>
            <View style={styles.chipRow}>
              {MAX_TURN_OPTIONS.map((turns) => (
                <ActionChip
                  key={turns}
                  label={String(turns)}
                  active={turns === overview?.max_turns}
                  onPress={() => void applyConfig({ max_turns: turns })}
                />
              ))}
            </View>
          </View>
        </CollapsibleSection>
        ) : null}

        {activeSection === 'runtime' ? (
        <CollapsibleSection
          title="Runtime toggles"
          meta={overview ? `${overview.bridge_enabled ? 'Bridge on' : 'Bridge off'} · ${overview.headless_mode} browser · heartbeat ${overview.heartbeat.enabled ? 'on' : 'off'}` : 'Bridge, browser mode, heartbeat, workspace'}
          defaultExpanded
        >
          <View style={styles.toggleRow}>
            <Text style={styles.toggleLabel}>Auto-reply monitor</Text>
            <View style={styles.inlineActions}>
              <ActionChip
                label="On"
                active={Boolean(overview?.auto_reply_enabled)}
                onPress={() => void applyConfig({ auto_reply_enabled: true })}
              />
              <ActionChip
                label="Off"
                active={overview ? !overview.auto_reply_enabled : false}
                onPress={() => void applyConfig({ auto_reply_enabled: false })}
              />
            </View>
          </View>

          <View style={styles.toggleRow}>
            <Text style={styles.toggleLabel}>Verbose tool feed</Text>
            <View style={styles.inlineActions}>
              <ActionChip
                label="On"
                active={Boolean(overview?.verbose_mode)}
                onPress={() => void applyConfig({ verbose_mode: true })}
              />
              <ActionChip
                label="Off"
                active={overview ? !overview.verbose_mode : false}
                onPress={() => void applyConfig({ verbose_mode: false })}
              />
            </View>
          </View>

          <View style={styles.toggleRow}>
            <Text style={styles.toggleLabel}>Browser extension bridge</Text>
            <View style={styles.inlineActions}>
              <ActionChip
                label="Real Chrome"
                active={Boolean(overview?.bridge_enabled)}
                onPress={() => void applyConfig({ bridge_enabled: true })}
              />
              <ActionChip
                label="Selenium"
                active={overview ? !overview.bridge_enabled : false}
                onPress={() => void applyConfig({ bridge_enabled: false })}
              />
            </View>
          </View>

          <View style={styles.toggleRow}>
            <Text style={styles.toggleLabel}>Browser mode</Text>
            <View style={styles.inlineActions}>
              <ActionChip
                label="Headless"
                active={overview?.headless_mode === 'headless'}
                onPress={() => void applyConfig({ headless_mode: 'headless' })}
              />
              <ActionChip
                label="Headed"
                active={overview?.headless_mode === 'headed'}
                onPress={() => void applyConfig({ headless_mode: 'headed' })}
              />
            </View>
          </View>

          <View style={styles.toggleRow}>
            <Text style={styles.toggleLabel}>Heartbeat</Text>
            <View style={styles.inlineActions}>
              <ActionChip
                label="On"
                active={Boolean(overview?.heartbeat.enabled)}
                onPress={() => void applyConfig({ heartbeat_enabled: true })}
              />
              <ActionChip
                label="Off"
                active={overview ? !overview.heartbeat.enabled : false}
                onPress={() => void applyConfig({ heartbeat_enabled: false })}
              />
            </View>
          </View>

          <View style={styles.formBlock}>
            <Text style={styles.inputLabel}>Heartbeat interval (seconds)</Text>
            <View style={styles.inlineForm}>
              <TextInput
                style={[styles.input, styles.compactInput]}
                value={heartbeatDraft}
                onChangeText={setHeartbeatDraft}
                placeholder="1800"
                placeholderTextColor="#7f8aa3"
                keyboardType="number-pad"
              />
              <Pressable
                style={styles.secondaryButton}
                onPress={() => void applyConfig({ heartbeat_interval_seconds: Number(heartbeatDraft) || 1800 })}
              >
                <Text style={styles.secondaryButtonText}>Save</Text>
              </Pressable>
            </View>
            <Text style={styles.inlineHelp}>
              Running: {overview?.heartbeat.running ? 'yes' : 'no'} · checks: {overview?.heartbeat.check_count ?? 0}
              {overview?.heartbeat.last_heartbeat ? ` · last ${formatRelativeTime(overview.heartbeat.last_heartbeat)}` : ''}
            </Text>
          </View>

          <View style={styles.formBlock}>
            <Text style={styles.inputLabel}>Workspace</Text>
            <View style={styles.inlineForm}>
              <TextInput
                style={styles.input}
                value={workspaceDraft}
                onChangeText={setWorkspaceDraft}
                placeholder="Workspace path"
                placeholderTextColor="#7f8aa3"
                autoCapitalize="none"
                autoCorrect={false}
              />
              <Pressable style={styles.secondaryButton} onPress={() => void applyConfig({ workspace: workspaceDraft })}>
                <Text style={styles.secondaryButtonText}>Apply</Text>
              </Pressable>
            </View>
          </View>
        </CollapsibleSection>
        ) : null}

        {activeSection === 'tasks' ? (
        <CollapsibleSection
          title="Agent tasks"
          meta={subAgents ? `${subAgents.running} running · ${subAgents.completed} completed · ${subAgents.failed} failed` : 'Subagent task runner'}
          defaultExpanded
        >
          <View style={styles.formBlock}>
            <Text style={styles.inputLabel}>Task</Text>
            <TextInput
              style={[styles.input, styles.textarea]}
              value={subAgentPrompt}
              onChangeText={setSubAgentPrompt}
              placeholder="Ask the agent to run a focused task"
              placeholderTextColor="#7f8aa3"
              multiline
            />
            <View style={styles.toggleRow}>
              <Text style={styles.toggleLabel}>Browser mode</Text>
              <View style={styles.inlineActions}>
                <ActionChip label="Headless" active={subAgentHeadless} onPress={() => setSubAgentHeadless(true)} />
                <ActionChip label="Headed" active={!subAgentHeadless} onPress={() => setSubAgentHeadless(false)} />
              </View>
            </View>
            <View style={styles.toggleRow}>
              <Text style={styles.toggleLabel}>Max turns</Text>
              <View style={styles.inlineActions}>
                {MAX_TURN_OPTIONS.map((turns) => (
                  <ActionChip
                    key={`subagent-turns-${turns}`}
                    label={String(turns)}
                    active={subAgentTurns === turns}
                    onPress={() => setSubAgentTurns(turns)}
                  />
                ))}
              </View>
            </View>
            <View style={styles.actionsRow}>
              <Pressable
                style={[styles.primaryButton, agentTaskStartDisabled ? styles.disabledButton : null]}
                disabled={agentTaskStartDisabled}
                accessibilityRole="button"
                accessibilityLabel="Start Agent task"
                accessibilityState={{ disabled: agentTaskStartDisabled }}
                onPress={() => void startAgentTask()}
              >
                <Text style={styles.primaryButtonText}>Start task</Text>
              </Pressable>
              <Pressable
                style={[styles.secondaryButton, agentTaskRefreshDisabled ? styles.disabledButton : null]}
                disabled={agentTaskRefreshDisabled}
                accessibilityRole="button"
                accessibilityLabel="Refresh Agent tasks"
                accessibilityState={{ disabled: agentTaskRefreshDisabled }}
                onPress={() =>
                  void runAction(
                    async () => {
                      const next = await fetchSubAgents(apiBaseUrl, token, overview?.session_id || undefined);
                      setSubAgents(next);
                    },
                    'refreshing agent tasks'
                  )
                }
              >
                <Text style={styles.secondaryButtonText}>Refresh tasks</Text>
              </Pressable>
            </View>
          </View>

          <View style={styles.metricsGrid}>
            <MetricCard label="Total" value={subAgents ? String(subAgents.total_tasks) : '0'} />
            <MetricCard label="Running" value={subAgents ? String(subAgents.running) : '0'} />
            <MetricCard label="Failed" value={subAgents ? String(subAgents.failed) : '0'} />
          </View>

          <View style={styles.subsection}>
            <Text style={styles.subsectionTitle}>Recent tasks</Text>
            {subAgents?.tasks.length ? (
              subAgents.tasks.slice(0, 8).map((task) => (
                <View key={task.id} style={styles.resultCard}>
                  <Text style={styles.resultMeta}>
                    {task.status} · {task.turns_used}/{task.max_turns} turns · {task.created_at ? formatRelativeTime(task.created_at) : 'new'}
                  </Text>
                  <Text style={styles.resultBody}>{task.prompt}</Text>
                  {task.result ? <Text style={styles.configValue}>{task.result}</Text> : null}
                  {task.error ? <Text style={styles.errorText}>{userFacingError(task.error, 'Task stopped.')}</Text> : null}
                </View>
              ))
            ) : (
              <Text style={styles.empty}>No Agent tasks yet.</Text>
            )}
          </View>
        </CollapsibleSection>
        ) : null}

        {activeSection === 'tools' ? (
        <CollapsibleSection
          title="Tool packs"
          meta={overview ? `${overview.enabled_tool_packs.length} enabled · ${overview.available_tool_packs.length} available` : 'Enabled and available tools'}
          defaultExpanded
        >
          <View style={styles.metricsGrid}>
            <MetricCard label="Enabled" value={(overview?.enabled_tool_packs || []).join(', ') || 'None'} />
            <MetricCard label="Available" value={(overview?.available_tool_packs || []).join(', ') || 'None'} />
            <MetricCard label="Run state" value={overview?.run_state || 'idle'} />
          </View>
          {overview?.lock_status && Object.keys(overview.lock_status).length ? (
            <View style={styles.configCard}>
              <View style={styles.configHeader}>
                <Text style={styles.configKey}>Runtime lock</Text>
                <InfoHint text={formatConfigValue(overview.lock_status)} />
              </View>
              <Text style={styles.configValue}>Active</Text>
            </View>
          ) : null}
        </CollapsibleSection>
        ) : null}

        {activeSection === 'tools' ? (
        <CollapsibleSection
          title="Context and files"
          meta={overview ? `${overview.context_usage.message_count} messages · ${overview.pending_files.length} pending files` : 'History preview, context usage, and pending uploads'}
          defaultExpanded={false}
        >
          <View style={styles.metricsGrid}>
            <MetricCard label="Estimated tokens" value={overview ? String(overview.context_usage.estimated_tokens) : '0'} />
            <MetricCard label="Context limit" value={overview ? String(overview.context_usage.max_tokens) : '0'} />
            <MetricCard label="Usage" value={overview ? `${overview.context_usage.usage_percent}%` : '0%'} />
          </View>

          <View style={styles.subsection}>
            <Text style={styles.subsectionTitle}>Recent history</Text>
            {overview?.history.length ? (
              overview.history.map((item, index) => (
                <View key={`${item.timestamp || index}-${item.preview}`} style={styles.historyCard}>
                  <Text style={styles.historyRole}>
                    {item.display_label || item.role} {item.timestamp ? `· ${formatRelativeTime(item.timestamp)}` : ''}
                  </Text>
                  <Text style={styles.historyPreview}>{item.preview || '[empty]'}</Text>
                </View>
              ))
            ) : (
              <Text style={styles.empty}>No history yet.</Text>
            )}
          </View>

          <View style={styles.subsection}>
            <View style={styles.subsectionHeader}>
              <Text style={styles.subsectionTitle}>Pending files</Text>
              <Pressable
                style={styles.ghostButton}
                onPress={() =>
                  void runAction(
                    () => clearAgentPendingFiles(apiBaseUrl, token, overview?.session_id || undefined),
                    'clearing files'
                  )
                }
              >
                <Text style={styles.ghostButtonText}>Clear</Text>
              </Pressable>
            </View>
            {overview?.pending_files.length ? (
              overview.pending_files.map((file) => (
                <View key={`${file.filename}-${file.uploaded_at || file.source_format || 'file'}`} style={styles.fileCard}>
                  <Text style={styles.fileName}>{file.filename}</Text>
                  <Text style={styles.fileMeta}>
                    {file.mime_type || 'unknown type'}
                    {file.size ? ` · ${file.size} bytes` : ''}
                    {file.uploaded_at ? ` · ${formatRelativeTime(file.uploaded_at)}` : ''}
                  </Text>
                </View>
              ))
            ) : (
              <Text style={styles.empty}>No pending files.</Text>
            )}
          </View>

          <View style={styles.actionsRow}>
            <Pressable
              style={styles.secondaryButton}
              onPress={() =>
                void runAction(
                  () => forgetLastAgentMessage(apiBaseUrl, token, overview?.session_id || undefined),
                  'removing last message'
                )
              }
            >
              <Text style={styles.secondaryButtonText}>Forget last user message</Text>
            </Pressable>
            <Pressable
              style={styles.deleteButton}
              onPress={() => void resetCurrentContext()}
            >
              <Text style={styles.deleteButtonText}>Reset chat context</Text>
            </Pressable>
          </View>
        </CollapsibleSection>
        ) : null}

        {activeSection === 'memory' ? (
        <CollapsibleSection
          title="Memory"
          meta={overview ? `${overview.memory_summary.daily_log_count} daily logs` : 'Search long-term memory and append notes'}
          defaultExpanded
        >
          <View style={styles.metricsGrid}>
            <MetricCard label="Memory file" value={overview?.memory_summary.memory_file_exists ? 'Present' : 'Missing'} />
            <MetricCard label="Daily logs" value={overview ? String(overview.memory_summary.daily_log_count) : '0'} />
            <MetricCard label="Newest" value={overview?.memory_summary.newest_log ? formatRelativeTime(overview.memory_summary.newest_log) : 'None'} />
          </View>

          <View style={styles.formBlock}>
            <Text style={styles.inputLabel}>Search memory</Text>
            <View style={styles.inlineForm}>
              <TextInput
                style={styles.input}
                value={memoryQuery}
                onChangeText={setMemoryQuery}
                placeholder="Search notes, facts, or logs"
                placeholderTextColor="#7f8aa3"
              />
              <Pressable
                style={styles.secondaryButton}
                onPress={() =>
                  void runAction(
                    async () => {
                      const result = await searchAgentMemory(apiBaseUrl, token, memoryQuery, overview?.session_id || undefined);
                      setMemoryResults(result.results || []);
                    },
                    'searching memory'
                  )
                }
              >
                <Text style={styles.secondaryButtonText}>Search</Text>
              </Pressable>
            </View>
          </View>

          {memoryResults.length ? (
            <View style={styles.subsection}>
              {memoryResults.map((result, index) => (
                <View key={`${result.source}-${result.line || index}`} style={styles.resultCard}>
                  <Text style={styles.resultMeta}>
                    {result.source}
                    {result.line ? `:${result.line}` : ''}
                  </Text>
                  <Text style={styles.resultBody}>{result.content}</Text>
                </View>
              ))}
            </View>
          ) : null}

          <View style={styles.formBlock}>
            <Text style={styles.inputLabel}>Append note to memory</Text>
            <TextInput
              style={[styles.input, styles.textarea]}
              value={memoryNote}
              onChangeText={setMemoryNote}
              placeholder="Save a durable fact, preference, or working note"
              placeholderTextColor="#7f8aa3"
              multiline
            />
            <Pressable
              style={styles.primaryButton}
              onPress={() =>
                void runAction(
                  async () => {
                    await appendAgentMemoryNote(apiBaseUrl, token, memoryNote, overview?.session_id || undefined);
                    setMemoryNote('');
                  },
                  'saving memory note'
                )
              }
            >
              <Text style={styles.primaryButtonText}>Save note</Text>
            </Pressable>
          </View>
        </CollapsibleSection>
        ) : null}

        {activeSection === 'analytics' || activeSection === 'config' || activeSection === 'diagnostics' ? (
        <CollapsibleSection
          title={activeSection === 'analytics' ? 'Analytics' : activeSection === 'config' ? 'Config' : 'Diagnostics'}
          meta="Metrics, settings, and safety state"
          defaultExpanded
        >
          <View style={styles.metricsGrid}>
            <MetricCard label="Messages" value={overview ? String(overview.analytics.total_messages) : '0'} />
            <MetricCard label="Commands" value={overview ? String(overview.analytics.total_commands) : '0'} />
            <MetricCard label="Tokens" value={overview ? String(overview.analytics.total_tokens) : '0'} />
          </View>

          <View style={styles.metricsGrid}>
            <MetricCard label="Allowed users" value={overview ? String(overview.security.allowed_users_count) : '0'} />
            <MetricCard label="Rate limits" value={overview ? `${overview.security.max_requests_per_minute}/min` : '0/min'} />
            <MetricCard label="24h alerts" value={overview ? String(overview.security.security_events_24h) : '0'} />
          </View>

          <View style={styles.subsection}>
            <Text style={styles.subsectionTitle}>Top actions</Text>
            {overview && Object.keys(overview.analytics.top_commands).length ? (
              Object.entries(overview.analytics.top_commands).map(([command, count]) => (
                <Text key={command} style={styles.inlineHelp}>
                  {command}: {count}
                </Text>
              ))
            ) : (
              <Text style={styles.empty}>No action analytics yet.</Text>
            )}
          </View>

          <View style={styles.subsection}>
            <Text style={styles.subsectionTitle}>Config editor</Text>
            <View style={styles.inlineForm}>
              <TextInput
                style={[styles.input, styles.compactInput]}
                value={configKey}
                onChangeText={setConfigKey}
                placeholder="config.key"
                placeholderTextColor="#7f8aa3"
                autoCapitalize="none"
                autoCorrect={false}
              />
              <TextInput
                style={styles.input}
                value={configValue}
                onChangeText={setConfigValue}
                placeholder="value"
                placeholderTextColor="#7f8aa3"
                autoCapitalize="none"
                autoCorrect={false}
              />
            </View>
            <View style={styles.actionsRow}>
              <Pressable
                style={styles.secondaryButton}
                onPress={() =>
                  void runAction(
                    async () => {
                      const result = await fetchAgentConfig(apiBaseUrl, token, configKey || undefined, overview?.session_id || undefined);
                      setConfigEntries(result.items || []);
                    },
                    'loading config'
                  )
                }
              >
                <Text style={styles.secondaryButtonText}>Load key</Text>
              </Pressable>
              <Pressable
                style={styles.primaryButton}
                onPress={() =>
                  void runAction(
                    async () => {
                      await updateAgentConfig(
                        apiBaseUrl,
                        token,
                        { key: configKey, value: configValue },
                        overview?.session_id || undefined
                      );
                      setConfigValue('');
                    },
                    'saving config'
                  )
                }
              >
                <Text style={styles.primaryButtonText}>Set value</Text>
              </Pressable>
            </View>
            <Text style={styles.inlineHelp}>Booleans, numbers, arrays, and objects can be entered as JSON-like text.</Text>
          </View>

          <View style={styles.subsection}>
            <Text style={styles.subsectionTitle}>Config values</Text>
            {(configEntries.length ? configEntries : overview?.config_preview || []).map((entry) => (
              <View key={entry.key} style={styles.configCard}>
                <Text style={styles.configKey}>{entry.key}</Text>
                <Text style={styles.configValue}>{formatConfigValue(entry.value)}</Text>
              </View>
            ))}
          </View>
        </CollapsibleSection>
        ) : null}
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
  modeTabs: {
    flexDirection: 'row',
    gap: 8,
  },
  modeTab: {
    flex: 1,
    minHeight: 40,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#15213c',
  },
  modeTabActive: {
    backgroundColor: '#2dd4bf',
  },
  modeTabText: {
    color: '#dce8ff',
    fontWeight: '800',
  },
  modeTabTextActive: {
    color: '#05131e',
  },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    flexWrap: 'wrap',
    gap: 8,
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
    lineHeight: 18,
  },
  summaryRow: {
    gap: 10,
    paddingRight: 12,
  },
  metricCard: {
    minWidth: 120,
    backgroundColor: '#141c33',
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 12,
    gap: 4,
  },
  metricLabel: {
    color: '#8fa2c8',
    fontSize: 12,
  },
  metricValue: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '700',
  },
  body: {
    flex: 1,
  },
  bodyContent: {
    gap: 14,
    paddingBottom: 28,
  },
  disabledControlsGroup: {
    opacity: 0.45,
  },
  heroCard: {
    backgroundColor: '#141c33',
    borderRadius: 20,
    padding: 16,
    gap: 8,
  },
  heroTitle: {
    color: '#ffffff',
    fontSize: 18,
    fontWeight: '700',
  },
  heroText: {
    color: '#b8c7e4',
    fontSize: 14,
    lineHeight: 20,
  },
  heroMeta: {
    color: '#8fa2c8',
    fontSize: 12,
  },
  warningCard: {
    borderWidth: 1,
    borderColor: '#7c5d1f',
    backgroundColor: '#1c180d',
    borderRadius: 12,
    padding: 14,
    gap: 10,
  },
  warningTitle: {
    color: '#ffe0a3',
    fontSize: 14,
    fontWeight: '800',
  },
  warningHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  warningText: {
    color: '#f7e8c1',
    fontSize: 13,
    lineHeight: 19,
  },
  groupBlock: {
    gap: 8,
  },
  groupTitle: {
    color: '#dce8ff',
    fontSize: 13,
    fontWeight: '700',
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  chip: {
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: '#182342',
  },
  chipActive: {
    backgroundColor: '#315ba3',
  },
  chipText: {
    color: '#dce8ff',
    fontSize: 12,
    fontWeight: '600',
  },
  chipTextActive: {
    color: '#ffffff',
  },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  toggleLabel: {
    flex: 1,
    color: '#eef4ff',
    fontSize: 14,
    fontWeight: '600',
  },
  inlineActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'flex-end',
    gap: 8,
  },
  formBlock: {
    gap: 8,
  },
  inputLabel: {
    color: '#dce8ff',
    fontSize: 13,
    fontWeight: '700',
  },
  inlineForm: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  input: {
    flex: 1,
    backgroundColor: '#0f1730',
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 11,
    color: '#ffffff',
    minHeight: 44,
  },
  compactInput: {
    flexBasis: 120,
    flexGrow: 0,
  },
  inlineHelp: {
    color: '#93a7cf',
    fontSize: 12,
    lineHeight: 18,
  },
  subsection: {
    gap: 8,
  },
  subsectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  subsectionTitle: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '700',
  },
  historyCard: {
    backgroundColor: '#101933',
    borderRadius: 14,
    padding: 12,
    gap: 4,
  },
  historyRole: {
    color: '#8fa2c8',
    fontSize: 12,
    fontWeight: '700',
  },
  historyPreview: {
    color: '#eef4ff',
    fontSize: 13,
    lineHeight: 19,
  },
  fileCard: {
    backgroundColor: '#101933',
    borderRadius: 14,
    padding: 12,
    gap: 4,
  },
  fileName: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: '700',
  },
  fileMeta: {
    color: '#8fa2c8',
    fontSize: 12,
  },
  resultCard: {
    backgroundColor: '#101933',
    borderRadius: 14,
    padding: 12,
    gap: 6,
  },
  resultMeta: {
    color: '#8fa2c8',
    fontSize: 12,
    fontWeight: '700',
  },
  resultBody: {
    color: '#eef4ff',
    fontSize: 13,
    lineHeight: 19,
  },
  configCard: {
    backgroundColor: '#101933',
    borderRadius: 14,
    padding: 12,
    gap: 6,
  },
  configHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  configKey: {
    color: '#dce8ff',
    fontSize: 12,
    fontWeight: '700',
  },
  configValue: {
    color: '#b8c7e4',
    fontSize: 12,
    lineHeight: 18,
  },
  errorText: {
    color: '#ffb4c0',
    fontSize: 12,
    lineHeight: 18,
  },
  textarea: {
    minHeight: 92,
    textAlignVertical: 'top',
  },
  actionsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  primaryButton: {
    alignSelf: 'flex-start',
    backgroundColor: '#3b82f6',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 11,
  },
  primaryButtonText: {
    color: '#ffffff',
    fontWeight: '700',
  },
  disabledButton: {
    opacity: 0.45,
  },
  secondaryButton: {
    alignSelf: 'flex-start',
    backgroundColor: '#223153',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 11,
  },
  secondaryButtonText: {
    color: '#dce8ff',
    fontWeight: '700',
  },
  ghostButton: {
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: '#172341',
  },
  ghostButtonText: {
    color: '#dce8ff',
    fontWeight: '700',
  },
  deleteButton: {
    alignSelf: 'flex-start',
    backgroundColor: '#6a2630',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 11,
  },
  deleteButtonText: {
    color: '#ffffff',
    fontWeight: '700',
  },
  metricsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  empty: {
    color: '#8fa2c8',
    fontSize: 13,
  },
});
