import { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Link, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  approvePendingConfirmation,
  configureHeadlessRuntime,
  createPendingConfirmation,
  deleteRemoteAccountData,
  denyPendingConfirmation,
  fetchAgentOverview,
  fetchPendingConfirmations,
  fetchRemoteAccountProfile,
  fetchRecoveryItems,
  permanentlyDeleteRecoveryItem,
  remoteLogout,
  restoreRecoveryItem,
  restoreWorkspaceFiles,
  updateRemoteAccountCloudProfile,
  type PendingConfirmation,
  type RecoveryArchiveItem,
  type RemoteAccountProfile,
} from '../src/lib/appApi';
import { clearRemoteAccountConfig, loadAppConfig, MOBILE_RELEASE } from '../lib/appConfig';
import { reconcileRemoteAccountConfig } from '../lib/accountSession';
import { useConfirmation } from '../src/components/ConfirmationDialog';
import { PageHeader } from '../src/components/PageHeader';
import { shortStatusText, userFacingError } from '../lib/diagnostics';
import { createApprovedConfirmation } from '../src/lib/sharedConfirmations';
import { InfoHint } from '../src/components/InfoHint';
import {
  applySharedSettingsDraftToProfile,
  profileToSharedSettingsDraft,
  validateSharedSettingsDraft,
  type SharedSettingsDraft,
} from '../src/lib/accountProfile';

const INTERRUPT_OPTIONS: Array<{ value: SharedSettingsDraft['interruptPolicy']; label: string }> = [
  { value: 'none', label: 'Queue' },
  { value: 'steer_now', label: 'Steer now' },
  { value: 'after_tool', label: 'After tool' },
];

export default function SettingsScreen() {
  const router = useRouter();
  const [apiBaseUrl, setApiBaseUrl] = useState('');
  const [token, setToken] = useState('');
  const [profile, setProfile] = useState<RemoteAccountProfile | null>(null);
  const [profileDraft, setProfileDraft] = useState<SharedSettingsDraft>(() => profileToSharedSettingsDraft(null));
  const [pendingConfirmations, setPendingConfirmations] = useState<PendingConfirmation[]>([]);
  const [recoveryItems, setRecoveryItems] = useState<RecoveryArchiveItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [dataDeleting, setDataDeleting] = useState(false);
  const [recoveryBusyId, setRecoveryBusyId] = useState<string | null>(null);
  const [status, setStatus] = useState('loading account');
  const { confirm, confirmationDialog } = useConfirmation();

  const refresh = async () => {
    setBusy(true);
    setStatus('checking account');
    try {
      const { config, profile: reconciledProfile } = await reconcileRemoteAccountConfig(await loadAppConfig());
      setApiBaseUrl(config.apiBaseUrl);
      setToken(config.accountToken || config.accessToken);
      if (!config.accountToken && !config.accessToken) {
        setProfile(null);
        setStatus('not signed in');
        router.replace('/auth');
        return;
      }
      const nextProfile = reconciledProfile || await fetchRemoteAccountProfile(config.apiBaseUrl, config.accountToken || config.accessToken);
      const [recovery, confirmations] = await Promise.all([
        fetchRecoveryItems(config.apiBaseUrl, config.accountToken || config.accessToken).catch(() => ({ items: [] })),
        fetchPendingConfirmations(config.apiBaseUrl, config.accountToken || config.accessToken).catch(() => ({ items: [] })),
      ]);
      setProfile(nextProfile);
      setProfileDraft(profileToSharedSettingsDraft(nextProfile.profile));
      setRecoveryItems(Array.isArray(recovery.items) ? recovery.items : []);
      setPendingConfirmations(Array.isArray(confirmations.items) ? confirmations.items : []);
      setStatus(nextProfile.mobile?.paired_desktop_id ? 'account ready' : 'signed in, not paired');
    } catch (error) {
      setStatus(userFacingError(error, 'Settings could not load.'));
    } finally {
      setBusy(false);
    }
  };

  const saveProfile = async () => {
    if (!apiBaseUrl || !token) {
      setStatus('sign in before saving profile');
      return;
    }
    const validationError = validateSharedSettingsDraft(profileDraft);
    if (validationError) {
      setStatus(validationError);
      return;
    }
    setProfileSaving(true);
    setStatus('saving profile');
    try {
      const nextCloudProfile = applySharedSettingsDraftToProfile(profile?.profile, profileDraft);
      const result = await updateRemoteAccountCloudProfile(apiBaseUrl, token, nextCloudProfile);
      setProfile((current) => current ? { ...current, profile: result.profile } : current);
      setProfileDraft(profileToSharedSettingsDraft(result.profile));
      await Promise.all([
        fetchAgentOverview(apiBaseUrl, token).catch(() => null),
        configureHeadlessRuntime(apiBaseUrl, token, { enabled: profileDraft.sleepModeEnabled }).catch(() => null),
      ]);
      setStatus('profile saved');
    } catch (error) {
      setStatus(userFacingError(error, 'Profile was not saved.'));
    } finally {
      setProfileSaving(false);
    }
  };

  const logout = async () => {
    setBusy(true);
    setStatus('logging out');
    try {
      if (apiBaseUrl && token) {
        await remoteLogout(apiBaseUrl, token).catch(() => null);
      }
      await clearRemoteAccountConfig();
      setProfile(null);
      setProfileDraft(profileToSharedSettingsDraft(null));
      setToken('');
      setStatus('logged out');
      router.replace('/auth');
    } catch (error) {
      setStatus(userFacingError(error, 'Logout did not finish.'));
    } finally {
      setBusy(false);
    }
  };

  const deleteCloudDataNow = async (confirmationId?: string | null) => {
    if (!apiBaseUrl || !token) {
      setStatus('sign in before deleting saved data');
      return;
    }
    setDataDeleting(true);
    setStatus('deleting saved data');
    try {
      const result = await deleteRemoteAccountData(apiBaseUrl, token, confirmationId);
      const nextProfile = await fetchRemoteAccountProfile(apiBaseUrl, token);
      setProfile(nextProfile);
      setProfileDraft(profileToSharedSettingsDraft(nextProfile.profile));
      setStatus(result.deleted_secrets ? 'Saved data deleted.' : 'Preferences reset.');
    } catch (error) {
      setStatus(userFacingError(error, 'Saved data was not deleted.'));
    } finally {
      setDataDeleting(false);
    }
  };

  const confirmDeleteCloudData = async () => {
    if (!apiBaseUrl || !token) {
      setStatus('sign in before deleting saved data');
      return;
    }
    const confirmationId = await createApprovedConfirmation(apiBaseUrl, token, confirm, {
      action_kind: 'remote_account_data_delete',
      title: 'Delete saved account data?',
      message: 'This deletes saved preferences, connected-device state, and saved access for this account. Your login account remains active.',
      risk_tier: 'danger',
      origin_surface: 'mobile',
      payload: {},
    }, {
      confirmLabel: 'Delete',
      tone: 'danger',
      details: ['This cannot be undone from the phone settings screen.', 'Use Recovery for archived chats and workers where available.'],
    });
    if (confirmationId) {
      await deleteCloudDataNow(confirmationId);
    }
  };

  const refreshRecovery = async () => {
    if (!apiBaseUrl || !token) return;
    setRecoveryBusyId('refresh');
    setStatus('refreshing recovery');
    try {
      const [recovery, confirmations] = await Promise.all([
        fetchRecoveryItems(apiBaseUrl, token),
        fetchPendingConfirmations(apiBaseUrl, token).catch(() => ({ items: [] })),
      ]);
      setRecoveryItems(Array.isArray(recovery.items) ? recovery.items : []);
      setPendingConfirmations(Array.isArray(confirmations.items) ? confirmations.items : []);
      setStatus('recovery ready');
    } catch (error) {
      setStatus(userFacingError(error, 'Recovery could not refresh.'));
    } finally {
      setRecoveryBusyId(null);
    }
  };

  const approveSharedConfirmation = async (confirmationId: string) => {
    if (!apiBaseUrl || !token) return;
    setRecoveryBusyId(confirmationId);
    setStatus('approving confirmation');
    try {
      await approvePendingConfirmation(apiBaseUrl, token, confirmationId, 'mobile');
      await refreshRecovery();
      setStatus('confirmation approved');
    } catch (error) {
      setStatus(userFacingError(error, 'Approval did not finish.'));
    } finally {
      setRecoveryBusyId(null);
    }
  };

  const denySharedConfirmation = async (confirmationId: string) => {
    if (!apiBaseUrl || !token) return;
    setRecoveryBusyId(confirmationId);
    setStatus('denying confirmation');
    try {
      await denyPendingConfirmation(apiBaseUrl, token, confirmationId, 'mobile');
      await refreshRecovery();
      setStatus('confirmation denied');
    } catch (error) {
      setStatus(userFacingError(error, 'Decision was not saved.'));
    } finally {
      setRecoveryBusyId(null);
    }
  };

  const restoreArchivedItem = async (archiveId: string) => {
    if (!apiBaseUrl || !token) return;
    setRecoveryBusyId(archiveId);
    setStatus('restoring archived item');
    try {
      await restoreRecoveryItem(apiBaseUrl, token, archiveId);
      await refreshRecovery();
      setStatus('archived item restored');
    } catch (error) {
      setStatus(userFacingError(error, 'Item was not restored.'));
    } finally {
      setRecoveryBusyId(null);
    }
  };

  const permanentlyDeleteArchivedItem = async (archiveId: string) => {
    if (!apiBaseUrl || !token) return;
    const ok = await confirm({
      title: 'Permanently delete this archived item?',
      message: 'This removes the recovery copy. You will not be able to restore it later.',
      confirmLabel: 'Delete Forever',
      tone: 'danger',
      details: ['Normal deletes are recoverable for 30 days.', 'Use this only when you intentionally want to remove the recovery copy.'],
    });
    if (!ok) return;
    setRecoveryBusyId(archiveId);
    setStatus('deleting archived item');
    try {
      const confirmation = await createPendingConfirmation(apiBaseUrl, token, {
        action_kind: 'recovery_permanent_delete',
        title: 'Permanently delete recovery item',
        message: 'This removes the archived recovery copy permanently.',
        risk_tier: 'danger',
        origin_surface: 'mobile',
        payload: { archive_id: archiveId },
        ttl_seconds: 300,
      });
      const approved = await approvePendingConfirmation(apiBaseUrl, token, confirmation.confirmation_id, 'mobile');
      await permanentlyDeleteRecoveryItem(apiBaseUrl, token, archiveId, approved.confirmation_id);
      await refreshRecovery();
      setStatus('archived item permanently deleted');
    } catch (error) {
      setStatus(userFacingError(error, 'Item was not deleted.'));
    } finally {
      setRecoveryBusyId(null);
    }
  };

  const restoreManagedWorkspace = async () => {
    if (!apiBaseUrl || !token) return;
    setRecoveryBusyId('workspace_restore');
    setStatus('restoring workspace files');
    try {
      const result = await restoreWorkspaceFiles(apiBaseUrl, token, {});
      setStatus(result.restored_files.length ? 'Workspace files restored.' : 'No files to restore.');
    } catch (error) {
      setStatus(userFacingError(error, 'Workspace files were not restored.'));
    } finally {
      setRecoveryBusyId(null);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const pairedDesktopId = profile?.mobile?.paired_desktop_id || '';

  return (
    <SafeAreaView style={styles.container}>
      {confirmationDialog}
      <ScrollView contentContainerStyle={styles.content}>
        <PageHeader
          eyebrow="Settings"
          title="Settings"
          subtitle="General app behavior, mobile connection, account, Recovery, and data controls."
        />

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>General</Text>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Mobile version</Text>
            <Text style={styles.infoValue}>{MOBILE_RELEASE.version}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Desktop compatibility</Text>
            <Text style={styles.infoValue}>{MOBILE_RELEASE.desktopCompatibility}</Text>
          </View>
          <Link href="/diagnostics" style={styles.link}>Diagnostics</Link>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Account</Text>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Email</Text>
            <Text style={styles.infoValue}>{profile?.user.email || 'not signed in'}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Name</Text>
            <Text style={styles.infoValue}>{profile?.user.display_name || 'not set'}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Phone</Text>
            <Text style={styles.infoValue}>{profile?.mobile?.device_name || 'this device'}</Text>
          </View>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Mobile Connection</Text>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Status</Text>
            <Text style={styles.infoValue}>{pairedDesktopId ? 'paired' : 'not paired'}</Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Desktop</Text>
            <View style={styles.valueWithInfo}>
              <Text style={styles.infoValue}>{pairedDesktopId ? 'Paired' : 'Pair from desktop setup'}</Text>
              {pairedDesktopId ? <InfoHint text={pairedDesktopId} /> : null}
            </View>
          </View>
          <Link href="/pair" style={styles.link}>Open pairing</Link>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Mobile Chat</Text>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Busy-run messages</Text>
            <View style={styles.segmentRow}>
              {INTERRUPT_OPTIONS.map((option) => (
                <Pressable
                  key={option.value}
                  style={[
                    styles.segmentButton,
                    profileDraft.interruptPolicy === option.value ? styles.segmentButtonActive : null,
                  ]}
                  onPress={() => setProfileDraft((current) => ({ ...current, interruptPolicy: option.value }))}
                >
                  <Text
                    style={[
                      styles.segmentText,
                      profileDraft.interruptPolicy === option.value ? styles.segmentTextActive : null,
                    ]}
                  >
                    {option.label}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
          <Pressable
            style={styles.toggleRow}
            onPress={() => setProfileDraft((current) => ({ ...current, verboseMode: !current.verboseMode }))}
          >
            <View style={[styles.toggleTrack, profileDraft.verboseMode ? styles.toggleTrackActive : null]}>
              <View style={[styles.toggleKnob, profileDraft.verboseMode ? styles.toggleKnobActive : null]} />
            </View>
            <Text style={styles.toggleText}>{profileDraft.verboseMode ? 'Verbose feed preferred' : 'Quiet feed preferred'}</Text>
          </Pressable>
          <Pressable
            style={styles.toggleRow}
            onPress={() => setProfileDraft((current) => ({ ...current, cloudChatBackupEnabled: !current.cloudChatBackupEnabled }))}
          >
            <View style={[styles.toggleTrack, profileDraft.cloudChatBackupEnabled ? styles.toggleTrackActive : null]}>
              <View style={[styles.toggleKnob, profileDraft.cloudChatBackupEnabled ? styles.toggleKnobActive : null]} />
            </View>
            <Text style={styles.toggleText}>{profileDraft.cloudChatBackupEnabled ? 'Cloud chat backup on' : 'Cloud chat backup off'}</Text>
          </Pressable>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Personalization</Text>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Custom instructions</Text>
            <TextInput
              value={profileDraft.customSystemPromptAppend}
              onChangeText={(value) => setProfileDraft((current) => ({ ...current, customSystemPromptAppend: value }))}
              style={[styles.input, styles.multilineInput]}
              autoCapitalize="sentences"
              autoCorrect
              multiline
              textAlignVertical="top"
              placeholder="Extra account instructions"
              placeholderTextColor="#7f8aa3"
            />
          </View>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Max turns</Text>
            <TextInput
              value={profileDraft.maxTurns}
              onChangeText={(value) => setProfileDraft((current) => ({ ...current, maxTurns: value.replace(/[^\d]/g, '') }))}
              style={styles.input}
              keyboardType="number-pad"
              placeholder="100"
              placeholderTextColor="#7f8aa3"
            />
          </View>
          <Pressable
            style={styles.toggleRow}
            onPress={() => setProfileDraft((current) => ({ ...current, sleepModeEnabled: !current.sleepModeEnabled }))}
          >
            <View style={[styles.toggleTrack, profileDraft.sleepModeEnabled ? styles.toggleTrackActive : null]}>
              <View style={[styles.toggleKnob, profileDraft.sleepModeEnabled ? styles.toggleKnobActive : null]} />
            </View>
            <Text style={styles.toggleText}>{profileDraft.sleepModeEnabled ? 'Sleep mode on' : 'Sleep mode off'}</Text>
          </Pressable>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Memory</Text>
          <Pressable
            style={styles.toggleRow}
            onPress={() => setProfileDraft((current) => ({ ...current, memoryPromptContextEnabled: !current.memoryPromptContextEnabled }))}
          >
            <View style={[styles.toggleTrack, profileDraft.memoryPromptContextEnabled ? styles.toggleTrackActive : null]}>
              <View style={[styles.toggleKnob, profileDraft.memoryPromptContextEnabled ? styles.toggleKnobActive : null]} />
            </View>
            <Text style={styles.toggleText}>{profileDraft.memoryPromptContextEnabled ? 'Prompt context on' : 'Prompt context off'}</Text>
          </Pressable>
          <Pressable
            style={styles.toggleRow}
            onPress={() => setProfileDraft((current) => ({ ...current, memorySearchEnabled: !current.memorySearchEnabled }))}
          >
            <View style={[styles.toggleTrack, profileDraft.memorySearchEnabled ? styles.toggleTrackActive : null]}>
              <View style={[styles.toggleKnob, profileDraft.memorySearchEnabled ? styles.toggleKnobActive : null]} />
            </View>
            <Text style={styles.toggleText}>{profileDraft.memorySearchEnabled ? 'Search on' : 'Search off'}</Text>
          </Pressable>
          <Pressable
            style={styles.toggleRow}
            onPress={() => setProfileDraft((current) => ({ ...current, memoryWriteEnabled: !current.memoryWriteEnabled }))}
          >
            <View style={[styles.toggleTrack, profileDraft.memoryWriteEnabled ? styles.toggleTrackActive : null]}>
              <View style={[styles.toggleKnob, profileDraft.memoryWriteEnabled ? styles.toggleKnobActive : null]} />
            </View>
            <Text style={styles.toggleText}>{profileDraft.memoryWriteEnabled ? 'Writes on' : 'Writes off'}</Text>
          </Pressable>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Telegram</Text>
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>User IDs</Text>
            <TextInput
              value={profileDraft.telegramAllowedUserIds}
              onChangeText={(value) => setProfileDraft((current) => ({ ...current, telegramAllowedUserIds: value }))}
              style={styles.input}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="numbers-and-punctuation"
              placeholder="123456789, 987654321"
              placeholderTextColor="#7f8aa3"
            />
          </View>
          <Pressable
            style={[styles.secondaryButton, (busy || profileSaving) ? styles.disabled : null]}
            onPress={saveProfile}
            disabled={busy || profileSaving}
          >
            <Text style={styles.secondaryText}>{profileSaving ? 'Saving...' : 'Save shared settings'}</Text>
          </Pressable>
        </View>

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Recovery</Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Refresh recovery"
              style={[styles.miniButton, recoveryBusyId === 'refresh' ? styles.disabled : null]}
              onPress={refreshRecovery}
              disabled={recoveryBusyId === 'refresh'}
            >
              <Text style={styles.miniButtonText}>{recoveryBusyId === 'refresh' ? 'Refreshing...' : 'Refresh'}</Text>
            </Pressable>
          </View>
          <Text style={styles.helperText}>Restore archived chats, workers, automations, reports, and app-created files for 30 days.</Text>
          {pendingConfirmations.length ? (
            <View style={styles.recoveryCard}>
              <View style={styles.cardHeader}>
                <Text style={styles.recoveryTitle}>Pending confirmations</Text>
                <InfoHint text="Sensitive actions wait here until you approve or deny them. Requests can come from desktop, mobile, Telegram, or Agent." />
              </View>
              {pendingConfirmations.slice(0, 8).map((item) => {
                const itemBusy = recoveryBusyId === item.confirmation_id;
                return (
                  <View key={item.confirmation_id} style={styles.confirmationItem}>
                    <Text style={styles.recoveryTitle}>{item.title}</Text>
                    <Text style={styles.recoveryMeta}>{item.message}</Text>
                    <View style={styles.recoveryActions}>
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel="Approve pending confirmation"
                        style={[styles.secondaryButton, itemBusy ? styles.disabled : null]}
                        onPress={() => void approveSharedConfirmation(item.confirmation_id)}
                        disabled={itemBusy}
                      >
                        <Text style={styles.secondaryText}>Approve</Text>
                      </Pressable>
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel="Deny pending confirmation"
                        style={[styles.dangerButton, itemBusy ? styles.disabled : null]}
                        onPress={() => void denySharedConfirmation(item.confirmation_id)}
                        disabled={itemBusy}
                      >
                        <Text style={styles.dangerText}>Deny</Text>
                      </Pressable>
                    </View>
                  </View>
                );
              })}
            </View>
          ) : (
            <Text style={styles.empty}>No sensitive actions are waiting for approval.</Text>
          )}
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Restore workspace files"
            style={[styles.secondaryButton, recoveryBusyId === 'workspace_restore' ? styles.disabled : null]}
            onPress={restoreManagedWorkspace}
            disabled={recoveryBusyId === 'workspace_restore'}
          >
            <Text style={styles.secondaryText}>{recoveryBusyId === 'workspace_restore' ? 'Restoring...' : 'Restore workspace files'}</Text>
          </Pressable>
          {recoveryItems.length === 0 ? (
            <Text style={styles.empty}>No archived items are waiting to be restored.</Text>
          ) : (
            recoveryItems.slice(0, 12).map((item) => {
              const itemBusy = recoveryBusyId === item.archive_id;
              return (
                <View key={item.archive_id} style={styles.recoveryCard}>
                  <Text style={styles.recoveryTitle}>{item.display_name || item.object_id}</Text>
                  <Text style={styles.recoveryMeta}>{item.object_kind} · {item.status}</Text>
                  <Text style={styles.recoveryMeta}>Expires {item.expires_at || 'unknown'}</Text>
                  <View style={styles.recoveryActions}>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel="Restore archived item"
                      style={[styles.secondaryButton, itemBusy || item.status === 'restored' ? styles.disabled : null]}
                      onPress={() => void restoreArchivedItem(item.archive_id)}
                      disabled={itemBusy || item.status === 'restored'}
                    >
                      <Text style={styles.secondaryText}>{itemBusy ? 'Working...' : 'Restore'}</Text>
                    </Pressable>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel="Permanently delete archived item"
                      style={[styles.dangerButton, itemBusy ? styles.disabled : null]}
                      onPress={() => void permanentlyDeleteArchivedItem(item.archive_id)}
                      disabled={itemBusy}
                    >
                      <Text style={styles.dangerText}>Delete Forever</Text>
                    </Pressable>
                  </View>
                </View>
              );
            })
          )}
        </View>

        <Text style={styles.status}>{shortStatusText(status)}</Text>

        <View style={styles.section}>
          <View style={styles.cardHeader}>
            <Text style={styles.sectionTitle}>Danger Zone</Text>
            <InfoHint text="Deletes saved preferences, connected-device state, and saved account access. Your login account remains active." />
          </View>
          <Pressable
            style={[styles.dangerButton, (busy || dataDeleting) ? styles.disabled : null]}
            onPress={confirmDeleteCloudData}
            disabled={busy || dataDeleting}
          >
            <Text style={styles.dangerText}>{dataDeleting ? 'Deleting...' : 'Delete saved account data'}</Text>
          </Pressable>
        </View>

        <View style={styles.actions}>
          <Pressable style={[styles.secondaryButton, busy ? styles.disabled : null]} onPress={refresh} disabled={busy}>
            <Text style={styles.secondaryText}>{busy ? 'Working...' : 'Refresh'}</Text>
          </Pressable>
          <Pressable style={[styles.dangerButton, busy ? styles.disabled : null]} onPress={logout} disabled={busy}>
            <Text style={styles.dangerText}>Log out</Text>
          </Pressable>
        </View>

        <Link href="/chat" style={styles.backLink}>Back to chat</Link>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0b1020',
  },
  content: {
    padding: 20,
    gap: 16,
  },
  header: {
    gap: 7,
  },
  eyebrow: {
    color: '#7cc7ff',
    fontSize: 13,
    fontWeight: '800',
  },
  title: {
    color: '#ffffff',
    fontSize: 26,
    fontWeight: '800',
  },
  subtitle: {
    color: '#b8c7e6',
    fontSize: 15,
    lineHeight: 22,
  },
  section: {
    backgroundColor: '#111a31',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#223252',
    padding: 14,
    gap: 10,
  },
  sectionTitle: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '800',
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  helperText: {
    color: '#b8c7e6',
    fontSize: 13,
    lineHeight: 20,
  },
  empty: {
    color: '#8fa3c8',
    fontSize: 13,
    lineHeight: 20,
  },
  miniButton: {
    minHeight: 36,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#2a3b61',
    paddingHorizontal: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  miniButtonText: {
    color: '#7cc7ff',
    fontWeight: '800',
    fontSize: 12,
  },
  recoveryCard: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#27385c',
    backgroundColor: '#0f1730',
    padding: 12,
    gap: 7,
  },
  recoveryTitle: {
    color: '#ffffff',
    fontWeight: '800',
    fontSize: 14,
  },
  recoveryMeta: {
    color: '#91a6c9',
    fontSize: 12,
    lineHeight: 17,
  },
  recoveryActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  confirmationItem: {
    borderTopWidth: 1,
    borderTopColor: '#27385c',
    paddingTop: 10,
    gap: 7,
  },
  infoRow: {
    gap: 4,
  },
  infoLabel: {
    color: '#8fa3c8',
    fontSize: 12,
    fontWeight: '700',
  },
  infoValue: {
    color: '#e8f0ff',
    fontSize: 15,
    lineHeight: 20,
  },
  valueWithInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  input: {
    minHeight: 46,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#2a3b61',
    backgroundColor: '#0f1730',
    color: '#ffffff',
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
  },
  multilineInput: {
    minHeight: 112,
  },
  segmentRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  segmentButton: {
    minHeight: 40,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#2a3b61',
    backgroundColor: '#0f1730',
    paddingHorizontal: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  segmentButtonActive: {
    backgroundColor: '#7cc7ff',
    borderColor: '#7cc7ff',
  },
  segmentText: {
    color: '#dce8ff',
    fontSize: 13,
    fontWeight: '800',
  },
  segmentTextActive: {
    color: '#07111f',
  },
  toggleRow: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  toggleTrack: {
    width: 50,
    height: 28,
    borderRadius: 999,
    backgroundColor: '#223252',
    padding: 4,
    justifyContent: 'center',
  },
  toggleTrackActive: {
    backgroundColor: '#7cc7ff',
  },
  toggleKnob: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: '#e8f0ff',
  },
  toggleKnobActive: {
    alignSelf: 'flex-end',
    backgroundColor: '#07111f',
  },
  toggleText: {
    color: '#dce8ff',
    fontSize: 14,
    fontWeight: '700',
  },
  link: {
    color: '#7cc7ff',
    fontWeight: '800',
    minHeight: 44,
    paddingTop: 12,
  },
  status: {
    color: '#b8c7e6',
    fontSize: 13,
    lineHeight: 20,
  },
  dangerCopy: {
    color: '#fecaca',
    fontSize: 13,
    lineHeight: 20,
  },
  actions: {
    gap: 10,
  },
  secondaryButton: {
    minHeight: 48,
    borderRadius: 8,
    backgroundColor: '#1b2745',
    alignItems: 'center',
    justifyContent: 'center',
  },
  secondaryText: {
    color: '#dce8ff',
    fontWeight: '800',
  },
  dangerButton: {
    minHeight: 48,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#ef4444',
    alignItems: 'center',
    justifyContent: 'center',
  },
  dangerText: {
    color: '#fecaca',
    fontWeight: '800',
  },
  disabled: {
    opacity: 0.55,
  },
  backLink: {
    color: '#7cc7ff',
    fontWeight: '800',
    alignSelf: 'center',
    minHeight: 44,
  },
});
