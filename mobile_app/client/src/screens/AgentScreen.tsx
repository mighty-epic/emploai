import { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { loadAppConfig } from '../../lib/appConfig';
import { describeError } from '../../lib/diagnostics';
import { AppDrawer, type DrawerTab } from '@/components/AppDrawer';
import { CollapsibleSection } from '@/components/CollapsibleSection';
import {
  appendAgentMemoryNote,
  clearAgentPendingFiles,
  configureAgent,
  fetchAgentConfig,
  fetchAgentOverview,
  fetchJobs,
  fetchSessions,
  forgetLastAgentMessage,
  resetAgentContext,
  searchAgentMemory,
  type AgentOverview,
  type ConfigEntry,
  type MemorySearchResult,
  type ScheduledJob,
  type SessionSummary,
  updateAgentConfig,
} from '@/lib/appApi';
import { formatAbsoluteTime, formatRelativeTime } from '@/lib/time';

const MAX_TURN_OPTIONS = [50, 100, 200, 500];

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
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [overview, setOverview] = useState<AgentOverview | null>(null);
  const [configEntries, setConfigEntries] = useState<ConfigEntry[]>([]);
  const [memoryResults, setMemoryResults] = useState<MemorySearchResult[]>([]);
  const [status, setStatus] = useState('idle');
  const [apiBaseUrl, setApiBaseUrl] = useState('');
  const [token, setToken] = useState('');
  const [configLoaded, setConfigLoaded] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>('system');
  const [workspaceDraft, setWorkspaceDraft] = useState('');
  const [heartbeatDraft, setHeartbeatDraft] = useState('1800');
  const [memoryQuery, setMemoryQuery] = useState('');
  const [memoryNote, setMemoryNote] = useState('');
  const [configKey, setConfigKey] = useState('');
  const [configValue, setConfigValue] = useState('');

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

  const loadControlCenter = async () => {
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
      const [sessionList, jobList, nextOverview, configList] = await Promise.all([
        fetchSessions(apiBaseUrl, token),
        fetchJobs(apiBaseUrl, token),
        fetchAgentOverview(apiBaseUrl, token),
        fetchAgentConfig(apiBaseUrl, token),
      ]);

      setSessions(Array.isArray(sessionList) ? sessionList : []);
      setJobs(Array.isArray(jobList) ? jobList : []);
      setOverview(nextOverview);
      setConfigEntries(Array.isArray(configList.items) ? configList.items : []);
      setWorkspaceDraft(nextOverview.workspace || '');
      setHeartbeatDraft(String(nextOverview.heartbeat.interval_seconds || 1800));
      setStatus('ready');
    } catch (error) {
      setStatus(describeError(error));
    }
  };

  useEffect(() => {
    if (!configLoaded) return;
    void loadControlCenter();
  }, [apiBaseUrl, configLoaded, token]);

  const applyConfig = async (payload: Parameters<typeof configureAgent>[2]) => {
    if (!apiBaseUrl || !token) return;
    setStatus('saving changes');
    try {
      const sessionId = overview?.session_id || undefined;
      await configureAgent(apiBaseUrl, token, payload, sessionId);
      await loadControlCenter();
    } catch (error) {
      setStatus(describeError(error));
    }
  };

  const runAction = async (action: () => Promise<unknown>, successStatus: string) => {
    setStatus(successStatus);
    try {
      await action();
      await loadControlCenter();
    } catch (error) {
      setStatus(describeError(error));
    }
  };

  const activeSession = overview?.session_id
    ? sessions.find((session) => session.id === overview.session_id)
    : undefined;

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
      />

      <View style={styles.topBar}>
        <Pressable
          style={styles.topButton}
          onPress={() => {
            setDrawerTab('system');
            setDrawerOpen(true);
          }}
        >
          <Text style={styles.topButtonText}>Sidebar</Text>
        </Pressable>
        <View style={styles.titleBlock}>
          <Text style={styles.title}>Agent controls</Text>
          <Text style={styles.subtitle}>Model, runtime, memory, context, and system controls migrated from Telegram.</Text>
        </View>
        <Pressable style={styles.topButton} onPress={() => void loadControlCenter()}>
          <Text style={styles.topButtonText}>Refresh</Text>
        </Pressable>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.summaryRow}>
        <MetricCard label="Status" value={status} />
        <MetricCard label="Model" value={overview?.current_model || 'Unknown'} />
        <MetricCard label="Variant" value={overview?.current_variant || 'Unknown'} />
        <MetricCard label="Planner" value={overview?.planner_model || 'Automatic'} />
        <MetricCard label="Turns" value={overview ? String(overview.max_turns) : '-'} />
        <MetricCard label="Session" value={activeSession?.name || 'No session'} />
      </ScrollView>

      <ScrollView style={styles.body} contentContainerStyle={styles.bodyContent}>
        <View style={styles.heroCard}>
          <Text style={styles.heroTitle}>Advanced controls stay off the chat surface</Text>
          <Text style={styles.heroText}>
            The chat remains clean while this page carries the Telegram-style model, runtime, memory, config, history, and inspection controls.
          </Text>
          {activeSession ? (
            <Text style={styles.heroMeta}>
              Active session: {activeSession.name} · {activeSession.message_count} messages · updated{' '}
              {formatRelativeTime(activeSession.updated_at)}
            </Text>
          ) : null}
        </View>

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

        <CollapsibleSection
          title="Runtime toggles"
          meta={overview ? `${overview.bridge_enabled ? 'Bridge on' : 'Bridge off'} · ${overview.headless_mode} browser · heartbeat ${overview.heartbeat.enabled ? 'on' : 'off'}` : 'Bridge, browser mode, heartbeat, workspace'}
          defaultExpanded={false}
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
              onPress={() =>
                void runAction(
                  () => resetAgentContext(apiBaseUrl, token, overview?.session_id || undefined),
                  'resetting context'
                )
              }
            >
              <Text style={styles.deleteButtonText}>Reset chat context</Text>
            </Pressable>
          </View>
        </CollapsibleSection>

        <CollapsibleSection
          title="Memory"
          meta={overview ? `${overview.memory_summary.daily_log_count} daily logs` : 'Search long-term memory and append notes'}
          defaultExpanded={false}
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

        <CollapsibleSection
          title="Config, analytics, and security"
          meta="Equivalent to /config, /analytics, and /security"
          defaultExpanded={false}
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
            <Text style={styles.subsectionTitle}>Top commands</Text>
            {overview && Object.keys(overview.analytics.top_commands).length ? (
              Object.entries(overview.analytics.top_commands).map(([command, count]) => (
                <Text key={command} style={styles.inlineHelp}>
                  /{command}: {count}
                </Text>
              ))
            ) : (
              <Text style={styles.empty}>No command analytics yet.</Text>
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
