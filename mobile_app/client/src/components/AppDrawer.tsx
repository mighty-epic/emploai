import { useEffect, useMemo, useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView as SafeAreaFrame } from 'react-native-safe-area-context';

import type { ScheduledJob, SessionSummary, SidebarState } from '@/lib/appApi';
import { formatRelativeTime } from '@/lib/time';

export type DrawerTab = 'chats' | 'fleet' | 'cron' | 'system';

type Props = {
  visible: boolean;
  onClose: () => void;
  initialTab?: DrawerTab;
  sessions: SessionSummary[];
  jobs: ScheduledJob[];
  cronUnreadCount?: number;
  activeSessionId?: string;
  backendLabel?: string;
  sidebarState?: SidebarState | null;
  onSelectSession?: (sessionId: string) => void;
  onCreateSession?: (workspace?: string) => void;
  onDeleteSession?: (sessionId: string) => void;
  onFolderRemoved?: (workspace: string) => void;
  onSidebarStateChange?: (state: SidebarState) => void;
};

type ProjectGroup = {
  path: string;
  label: string;
  sessions: SessionSummary[];
  pinned: boolean;
  collapsed: boolean;
};

function emptySidebarState(): SidebarState {
  return {
    version: 1,
    projectOrder: [],
    projects: {},
    sessionMeta: {},
    selectedProjectPath: null,
    lastSelectedProjectPath: null,
  };
}

function normalizeWorkspacePath(value?: string | null) {
  return String(value || '').trim() || 'workspace://default';
}

function projectBasename(path: string) {
  const normalized = path.replace(/\\/g, '/').replace(/\/+$/, '');
  const parts = normalized.split('/').filter(Boolean);
  return parts[parts.length - 1] || normalized || 'Workspace';
}

function coerceSidebarState(value?: SidebarState | null): SidebarState {
  const state = value || emptySidebarState();
  return {
    version: Number(state.version || 1),
    projectOrder: Array.isArray(state.projectOrder) ? state.projectOrder.map(normalizeWorkspacePath) : [],
    projects: state.projects && typeof state.projects === 'object' ? state.projects : {},
    sessionMeta: state.sessionMeta && typeof state.sessionMeta === 'object' ? state.sessionMeta : {},
    selectedProjectPath: state.selectedProjectPath || null,
    lastSelectedProjectPath: state.lastSelectedProjectPath || null,
  };
}

function sessionSort(state: SidebarState, left: SessionSummary, right: SessionSummary) {
  const leftPinned = Boolean(state.sessionMeta[left.id]?.pinned);
  const rightPinned = Boolean(state.sessionMeta[right.id]?.pinned);
  if (leftPinned !== rightPinned) return leftPinned ? -1 : 1;
  const leftOrder = state.sessionMeta[left.id]?.order;
  const rightOrder = state.sessionMeta[right.id]?.order;
  if (typeof leftOrder === 'number' && typeof rightOrder === 'number' && leftOrder !== rightOrder) {
    return leftOrder - rightOrder;
  }
  return String(right.updated_at || '').localeCompare(String(left.updated_at || ''));
}

function buildProjectGroups(sessions: SessionSummary[], state: SidebarState): ProjectGroup[] {
  const paths = new Set<string>();
  state.projectOrder.forEach((path) => paths.add(normalizeWorkspacePath(path)));
  Object.keys(state.projects || {}).forEach((path) => paths.add(normalizeWorkspacePath(path)));
  sessions.forEach((session) => paths.add(normalizeWorkspacePath(session.workspace)));

  const order = new Map(state.projectOrder.map((path, index) => [normalizeWorkspacePath(path), index]));
  return Array.from(paths)
    .filter((path) => !state.projects[path]?.hidden)
    .map((path) => {
      const projectState = state.projects[path] || {};
      const label = String(projectState.displayName || '').trim() || projectBasename(path);
      const groupedSessions = sessions
        .filter((session) => normalizeWorkspacePath(session.workspace) === path)
        .sort((left, right) => sessionSort(state, left, right));
      return {
        path,
        label,
        sessions: groupedSessions,
        pinned: Boolean(projectState.pinned),
        collapsed: Boolean(projectState.collapsed),
      };
    })
    .sort((left, right) => {
      const leftPinned = left.pinned ? 0 : 1;
      const rightPinned = right.pinned ? 0 : 1;
      if (leftPinned !== rightPinned) return leftPinned - rightPinned;
      const leftOrder = order.has(left.path) ? order.get(left.path)! : Number.MAX_SAFE_INTEGER;
      const rightOrder = order.has(right.path) ? order.get(right.path)! : Number.MAX_SAFE_INTEGER;
      if (leftOrder !== rightOrder) return leftOrder - rightOrder;
      return left.label.localeCompare(right.label);
    });
}

function sessionMatchesQuery(session: SessionSummary, query: string) {
  if (!query) return true;
  const haystack = [
    session.name,
    session.workspace,
    session.latest_preview,
    session.model,
  ].join(' ').toLowerCase();
  return haystack.includes(query);
}

export function AppDrawer({
  visible,
  onClose,
  initialTab = 'chats',
  sessions,
  jobs,
  cronUnreadCount = 0,
  activeSessionId,
  backendLabel,
  sidebarState,
  onSelectSession,
  onCreateSession,
  onDeleteSession,
  onFolderRemoved,
  onSidebarStateChange,
}: Props) {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [renamePath, setRenamePath] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [renameSessionId, setRenameSessionId] = useState<string | null>(null);
  const [renameSessionValue, setRenameSessionValue] = useState('');
  const [menuTarget, setMenuTarget] = useState<{ kind: 'session'; session: SessionSummary } | { kind: 'project'; group: ProjectGroup } | null>(null);
  const state = useMemo(() => coerceSidebarState(sidebarState), [sidebarState]);
  const groups = useMemo(() => buildProjectGroups(sessions, state), [sessions, state]);
  const normalizedSearch = search.trim().toLowerCase();
  const filteredGroups = useMemo(
    () => groups
      .map((group) => {
        const projectMatches = `${group.label} ${group.path}`.toLowerCase().includes(normalizedSearch);
        return {
          ...group,
          sessions: projectMatches
            ? group.sessions
            : group.sessions.filter((session) => sessionMatchesQuery(session, normalizedSearch)),
        };
      })
      .filter((group) => !normalizedSearch || group.sessions.length > 0 || `${group.label} ${group.path}`.toLowerCase().includes(normalizedSearch)),
    [groups, normalizedSearch],
  );
  const pinnedSessions = useMemo(
    () => sessions
      .filter((session) => Boolean(state.sessionMeta[session.id]?.pinned))
      .filter((session) => sessionMatchesQuery(session, normalizedSearch))
      .sort((left, right) => sessionSort(state, left, right)),
    [normalizedSearch, sessions, state],
  );

  useEffect(() => {
    if (visible) {
      setRenamePath(null);
      setRenameValue('');
      setRenameSessionId(null);
      setRenameSessionValue('');
      setMenuTarget(null);
      setSearch('');
    }
  }, [initialTab, visible]);

  const navigate = (path: '/chat' | '/fleet' | '/cron' | '/pair' | '/settings' | '/diagnostics' | '/agent') => {
    router.push(path as any);
    onClose();
  };

  const writeState = (next: SidebarState) => {
    onSidebarStateChange?.(next);
  };

  const updateProject = (projectPath: string, updates: Record<string, unknown>) => {
    const normalized = normalizeWorkspacePath(projectPath);
    writeState({
      ...state,
      projectOrder: state.projectOrder.includes(normalized) ? state.projectOrder : [...state.projectOrder, normalized],
      projects: {
        ...state.projects,
        [normalized]: {
          ...(state.projects[normalized] || {}),
          ...updates,
        },
      },
      selectedProjectPath: normalized,
      lastSelectedProjectPath: normalized,
    });
  };

  const toggleSessionPin = (sessionId: string) => {
    writeState({
      ...state,
      sessionMeta: {
        ...state.sessionMeta,
        [sessionId]: {
          ...(state.sessionMeta[sessionId] || {}),
          pinned: !Boolean(state.sessionMeta[sessionId]?.pinned),
        },
      },
    });
  };

  const displaySessionName = (session: SessionSummary) => {
    return String(state.sessionMeta[session.id]?.displayName || '').trim() || session.name;
  };

  const startRenameSession = (session: SessionSummary) => {
    setRenameSessionId(session.id);
    setRenameSessionValue(displaySessionName(session));
    setMenuTarget(null);
  };

  const commitSessionRename = () => {
    if (!renameSessionId) return;
    writeState({
      ...state,
      sessionMeta: {
        ...state.sessionMeta,
        [renameSessionId]: {
          ...(state.sessionMeta[renameSessionId] || {}),
          displayName: renameSessionValue.trim() || null,
        },
      },
    });
    setRenameSessionId(null);
    setRenameSessionValue('');
  };

  const hideProject = (projectPath: string) => {
    updateProject(projectPath, { hidden: true });
    onFolderRemoved?.(normalizeWorkspacePath(projectPath));
    setMenuTarget(null);
  };

  const selectSession = (sessionId: string) => {
    onSelectSession?.(sessionId);
    router.push({ pathname: '/chat', params: { sessionId } });
    onClose();
  };

  const openNewSession = (workspace?: string) => {
    if (onCreateSession) {
      onCreateSession(workspace);
    } else {
      router.push({ pathname: '/chat', params: { newSession: '1' } });
    }
    onClose();
  };

  const startRename = (group: ProjectGroup) => {
    setRenamePath(group.path);
    setRenameValue(group.label);
  };

  const commitRename = () => {
    if (!renamePath) return;
    updateProject(renamePath, { displayName: renameValue.trim() || null });
    setRenamePath(null);
    setRenameValue('');
  };

  return (
    <Modal transparent visible={visible} animationType="fade" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <SafeAreaFrame edges={['top', 'bottom']} style={styles.panel}>
          <View style={styles.panelHeader}>
            <View style={styles.headerCopy}>
              <Text style={styles.brand}>Kraitos</Text>
              <Text style={styles.subhead}>{backendLabel || 'Sign-in required'}</Text>
            </View>
            <Pressable onPress={onClose} style={styles.closeButton}>
              <Text style={styles.close}>Close</Text>
            </Pressable>
          </View>

          <ScrollView contentContainerStyle={styles.content}>
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Navigation</Text>
              <View style={styles.navGrid}>
                <Pressable style={styles.navButton} onPress={() => navigate('/chat')}>
                  <Text style={styles.navButtonTitle}>Chat</Text>
                </Pressable>
                <Pressable style={styles.navButton} onPress={() => navigate('/fleet')}>
                  <Text style={styles.navButtonTitle}>Fleet</Text>
                </Pressable>
                <Pressable style={styles.navButton} onPress={() => navigate('/agent')}>
                  <Text style={styles.navButtonTitle}>Agent</Text>
                </Pressable>
                <Pressable style={styles.navButton} onPress={() => navigate('/cron')}>
                  <Text style={styles.navButtonTitle}>Automations</Text>
                  {cronUnreadCount > 0 ? (
                    <View style={styles.navBadge}>
                      <Text style={styles.navBadgeText}>{cronUnreadCount > 9 ? '9+' : String(cronUnreadCount)}</Text>
                    </View>
                  ) : null}
                </Pressable>
                <Pressable style={styles.navButton} onPress={() => navigate('/settings')}>
                  <Text style={styles.navButtonTitle}>Settings</Text>
                </Pressable>
                <Pressable style={styles.navButton} onPress={() => navigate('/pair')}>
                  <Text style={styles.navButtonTitle}>Pair</Text>
                </Pressable>
                <Pressable style={styles.navButton} onPress={() => navigate('/diagnostics')}>
                  <Text style={styles.navButtonTitle}>Diagnostics</Text>
                </Pressable>
              </View>
            </View>

            <View style={styles.section}>
              <View style={styles.sectionHeader}>
                <Text style={styles.sectionTitle}>Conversations</Text>
                <Pressable style={styles.primaryButtonCompact} onPress={() => openNewSession(state.selectedProjectPath || undefined)}>
                  <Text style={styles.primaryText}>New</Text>
                </Pressable>
              </View>
              <TextInput
                style={styles.searchInput}
                value={search}
                onChangeText={setSearch}
                placeholder="Search chats and folders"
                placeholderTextColor="#7f93b5"
                autoCapitalize="none"
                autoCorrect={false}
              />

              {pinnedSessions.length ? (
                <View style={styles.subsection}>
                  <Text style={styles.subsectionTitle}>Pinned</Text>
                  {pinnedSessions.map((session) => (
                    <SessionRow
                      key={session.id}
                      session={session}
                      displayName={displaySessionName(session)}
                      active={activeSessionId === session.id}
                      renameOpen={renameSessionId === session.id}
                      renameValue={renameSessionValue}
                      onRenameChange={setRenameSessionValue}
                      onRenameSave={commitSessionRename}
                      onSelect={() => selectSession(session.id)}
                      onOpenMenu={() => setMenuTarget({ kind: 'session', session })}
                    />
                  ))}
                </View>
              ) : null}

              {filteredGroups.length === 0 ? (
                <Text style={styles.empty}>No sessions yet.</Text>
              ) : (
                filteredGroups.map((group) => (
                  <View key={group.path} style={styles.projectBlock}>
                    <View style={styles.projectHeader}>
                      <Pressable
                        style={styles.projectTitleButton}
                        onPress={() => updateProject(group.path, { collapsed: !group.collapsed })}
                        onLongPress={() => setMenuTarget({ kind: 'project', group })}
                      >
                        <Text style={styles.projectTitle}>{group.collapsed ? '>' : 'v'} {group.label}</Text>
                        <Text style={styles.projectMeta} numberOfLines={1}>{group.path}</Text>
                      </Pressable>
                      <Pressable style={styles.overflowButton} onPress={() => setMenuTarget({ kind: 'project', group })}>
                        <Text style={styles.overflowText}>...</Text>
                      </Pressable>
                    </View>

                    {renamePath === group.path ? (
                      <View style={styles.renameRow}>
                        <TextInput
                          style={styles.renameInput}
                          value={renameValue}
                          onChangeText={setRenameValue}
                          placeholder="Folder name"
                          placeholderTextColor="#7f93b5"
                        />
                        <Pressable style={styles.smallAction} onPress={commitRename}>
                          <Text style={styles.smallActionText}>Save</Text>
                        </Pressable>
                      </View>
                    ) : null}

                    {!group.collapsed ? (
                      group.sessions.length ? (
                        group.sessions.map((session) => (
                          <SessionRow
                            key={session.id}
                            session={session}
                            displayName={displaySessionName(session)}
                            active={activeSessionId === session.id}
                            renameOpen={renameSessionId === session.id}
                            renameValue={renameSessionValue}
                            onRenameChange={setRenameSessionValue}
                            onRenameSave={commitSessionRename}
                            onSelect={() => selectSession(session.id)}
                            onOpenMenu={() => setMenuTarget({ kind: 'session', session })}
                          />
                        ))
                      ) : (
                        <Text style={styles.empty}>No chats in this folder yet.</Text>
                      )
                    ) : null}
                  </View>
                ))
              )}

              {jobs.length ? (
                <View style={styles.automationPreview}>
                  <Text style={styles.subsectionTitle}>Automations</Text>
                  {jobs.slice(0, 2).map((job) => (
                    <Pressable key={job.id} style={styles.listCard} onPress={() => navigate('/cron')}>
                      <Text style={styles.cardTitle}>{job.name}</Text>
                      <Text style={styles.cardMeta}>
                        {job.enabled ? 'Enabled' : 'Paused'} · {job.next_run_at ? formatRelativeTime(job.next_run_at) : 'unscheduled'}
                      </Text>
                    </Pressable>
                  ))}
                </View>
              ) : null}
            </View>
          </ScrollView>
          {menuTarget ? (
            <View style={styles.actionMenu}>
              <View style={styles.actionMenuHeader}>
                <Text style={styles.actionMenuTitle}>
                  {menuTarget.kind === 'session' ? displaySessionName(menuTarget.session) : menuTarget.group.label}
                </Text>
                <Pressable style={styles.actionMenuClose} onPress={() => setMenuTarget(null)}>
                  <Text style={styles.close}>Close</Text>
                </Pressable>
              </View>
              {menuTarget.kind === 'session' ? (
                <>
                  <Pressable style={styles.actionMenuItem} onPress={() => { toggleSessionPin(menuTarget.session.id); setMenuTarget(null); }}>
                    <Text style={styles.actionMenuText}>{state.sessionMeta[menuTarget.session.id]?.pinned ? 'Unpin' : 'Pin'}</Text>
                  </Pressable>
                  <Pressable style={styles.actionMenuItem} onPress={() => startRenameSession(menuTarget.session)}>
                    <Text style={styles.actionMenuText}>Rename</Text>
                  </Pressable>
                  <Pressable style={styles.actionMenuItemDanger} onPress={() => { onDeleteSession?.(menuTarget.session.id); setMenuTarget(null); onClose(); }}>
                    <Text style={styles.actionMenuDangerText}>Delete</Text>
                  </Pressable>
                </>
              ) : (
                <>
                  <Pressable style={styles.actionMenuItem} onPress={() => { updateProject(menuTarget.group.path, { pinned: !menuTarget.group.pinned }); setMenuTarget(null); }}>
                    <Text style={styles.actionMenuText}>{menuTarget.group.pinned ? 'Unpin folder' : 'Pin folder'}</Text>
                  </Pressable>
                  <Pressable style={styles.actionMenuItem} onPress={() => { startRename(menuTarget.group); setMenuTarget(null); }}>
                    <Text style={styles.actionMenuText}>Rename</Text>
                  </Pressable>
                  <Pressable style={styles.actionMenuItem} onPress={() => { openNewSession(menuTarget.group.path); setMenuTarget(null); }}>
                    <Text style={styles.actionMenuText}>New chat here</Text>
                  </Pressable>
                  <Pressable style={styles.actionMenuItemDanger} onPress={() => hideProject(menuTarget.group.path)}>
                    <Text style={styles.actionMenuDangerText}>Remove</Text>
                  </Pressable>
                </>
              )}
            </View>
          ) : null}
        </SafeAreaFrame>
        <Pressable style={styles.backdrop} onPress={onClose} />
      </View>
    </Modal>
  );
}

function SessionRow({
  session,
  displayName,
  active,
  renameOpen,
  renameValue,
  onRenameChange,
  onRenameSave,
  onSelect,
  onOpenMenu,
}: {
  session: SessionSummary;
  displayName: string;
  active: boolean;
  renameOpen: boolean;
  renameValue: string;
  onRenameChange: (value: string) => void;
  onRenameSave: () => void;
  onSelect: () => void;
  onOpenMenu: () => void;
}) {
  return (
    <Pressable style={[styles.listCard, active ? styles.listCardActive : null]} onPress={onSelect} onLongPress={onOpenMenu}>
      <View style={styles.sessionTopRow}>
        <View style={styles.sessionCopy}>
          {renameOpen ? (
            <View style={styles.renameRow}>
              <TextInput
                style={styles.renameInput}
                value={renameValue}
                onChangeText={onRenameChange}
                placeholder="Chat name"
                placeholderTextColor="#7f93b5"
              />
              <Pressable style={styles.smallAction} onPress={onRenameSave}>
                <Text style={styles.smallActionText}>Save</Text>
              </Pressable>
            </View>
          ) : (
            <Text style={styles.cardTitle} numberOfLines={1}>{displayName}</Text>
          )}
          <Text style={styles.cardMeta}>
            {session.is_running ? 'Running' : formatRelativeTime(session.updated_at)} · {session.message_count} msgs
          </Text>
        </View>
        <Pressable style={styles.overflowButton} onPress={onOpenMenu}>
          <Text style={styles.overflowText}>...</Text>
        </Pressable>
      </View>
      <Text style={styles.cardBody} numberOfLines={2}>{session.latest_preview || 'No messages yet'}</Text>
    </Pressable>
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
    width: 336,
    maxWidth: '88%',
    backgroundColor: '#0e1630',
    borderRightWidth: 1,
    borderRightColor: '#1e294b',
    paddingHorizontal: 14,
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
    fontWeight: '800',
  },
  subhead: {
    color: '#8ca1c8',
    fontSize: 12,
  },
  closeButton: {
    minHeight: 44,
    minWidth: 56,
    alignItems: 'flex-end',
    justifyContent: 'center',
  },
  close: {
    color: '#7cc7ff',
    fontWeight: '800',
  },
  tabRow: {
    flexDirection: 'row',
    gap: 8,
  },
  tabButton: {
    flex: 1,
    borderRadius: 8,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#16203d',
  },
  tabLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  tabButtonActive: {
    backgroundColor: '#2d4674',
  },
  tabText: {
    color: '#ffffff',
    fontWeight: '800',
    fontSize: 13,
  },
  tabBadge: {
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    paddingHorizontal: 5,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#f97316',
  },
  tabBadgeText: {
    color: '#ffffff',
    fontSize: 10,
    fontWeight: '800',
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
    fontWeight: '800',
  },
  subsection: {
    gap: 8,
  },
  subsectionTitle: {
    color: '#8ca1c8',
    fontSize: 12,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  primaryButton: {
    backgroundColor: '#3b82f6',
    borderRadius: 8,
    minHeight: 44,
    paddingHorizontal: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryText: {
    color: '#ffffff',
    fontWeight: '800',
  },
  primaryButtonCompact: {
    backgroundColor: '#3b82f6',
    borderRadius: 8,
    minHeight: 36,
    paddingHorizontal: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  navGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  navButton: {
    minHeight: 42,
    minWidth: 118,
    flexGrow: 1,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#273656',
    backgroundColor: '#141c33',
    paddingHorizontal: 12,
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  navButtonTitle: {
    color: '#dce8ff',
    fontSize: 13,
    fontWeight: '800',
  },
  navBadge: {
    position: 'absolute',
    top: -6,
    right: -6,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    paddingHorizontal: 5,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#f97316',
  },
  navBadgeText: {
    color: '#ffffff',
    fontSize: 10,
    fontWeight: '800',
  },
  searchInput: {
    minHeight: 44,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#273656',
    backgroundColor: '#0f1730',
    color: '#ffffff',
    paddingHorizontal: 12,
    fontSize: 14,
  },
  ghostButton: {
    borderRadius: 8,
    minHeight: 44,
    paddingHorizontal: 12,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#172341',
  },
  ghostText: {
    color: '#dce8ff',
    fontWeight: '800',
  },
  projectBlock: {
    gap: 8,
    borderTopWidth: 1,
    borderTopColor: '#223252',
    paddingTop: 10,
  },
  projectHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  projectTitleButton: {
    flex: 1,
    minHeight: 44,
    justifyContent: 'center',
  },
  projectTitle: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '800',
  },
  projectMeta: {
    color: '#7f93b5',
    fontSize: 11,
  },
  projectActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  textAction: {
    minHeight: 36,
    justifyContent: 'center',
  },
  textActionText: {
    color: '#9bd1ff',
    fontSize: 12,
    fontWeight: '800',
  },
  textActionDanger: {
    color: '#fca5a5',
    fontSize: 12,
    fontWeight: '800',
  },
  smallAction: {
    minHeight: 40,
    borderRadius: 8,
    paddingHorizontal: 12,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#1b2745',
  },
  smallActionText: {
    color: '#dce8ff',
    fontWeight: '800',
    fontSize: 12,
  },
  overflowButton: {
    minWidth: 38,
    minHeight: 38,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#273656',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#101933',
  },
  overflowText: {
    color: '#dce8ff',
    fontSize: 18,
    lineHeight: 18,
    fontWeight: '900',
  },
  renameRow: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'center',
  },
  renameInput: {
    flex: 1,
    minHeight: 44,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#263659',
    backgroundColor: '#0b1020',
    color: '#ffffff',
    paddingHorizontal: 12,
    fontSize: 15,
  },
  listCard: {
    backgroundColor: '#141c33',
    borderRadius: 8,
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
    borderRadius: 8,
    padding: 14,
    gap: 6,
  },
  sessionTopRow: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'center',
  },
  sessionCopy: {
    flex: 1,
  },
  cardTitle: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '800',
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
  pinButton: {
    minHeight: 36,
    paddingHorizontal: 8,
    justifyContent: 'center',
  },
  pinText: {
    color: '#9bd1ff',
    fontSize: 12,
    fontWeight: '800',
  },
  empty: {
    color: '#8ca1c8',
    fontSize: 13,
    lineHeight: 19,
  },
  automationPreview: {
    gap: 8,
    borderTopWidth: 1,
    borderTopColor: '#223252',
    paddingTop: 10,
  },
  actionMenu: {
    borderTopWidth: 1,
    borderTopColor: '#223252',
    backgroundColor: '#0b1327',
    paddingTop: 10,
    gap: 8,
  },
  actionMenuHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  actionMenuTitle: {
    flex: 1,
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '800',
  },
  actionMenuClose: {
    minHeight: 34,
    justifyContent: 'center',
  },
  actionMenuItem: {
    minHeight: 42,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#273656',
    backgroundColor: '#111a31',
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionMenuItemDanger: {
    minHeight: 42,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#7f2342',
    backgroundColor: '#321223',
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionMenuText: {
    color: '#dce8ff',
    fontSize: 13,
    fontWeight: '800',
  },
  actionMenuDangerText: {
    color: '#fecaca',
    fontSize: 13,
    fontWeight: '800',
  },
});
