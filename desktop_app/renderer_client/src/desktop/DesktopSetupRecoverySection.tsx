import { Pressable, Text, View } from 'react-native';

import { styles } from './DesktopSetupPanel.styles';

import type { PendingConfirmation, RecoveryArchiveItem } from '@/lib/appApi';

type Props = {
  pendingConfirmations: PendingConfirmation[];
  recoveryItems: RecoveryArchiveItem[];
  recoveryBusyId?: string | null;
  recoveryMessage?: string | null;
  remoteAccountSignedIn?: boolean;
  remoteSecretsBusy?: boolean;
  cloudChatBackupEnabled?: boolean;
  cloudBackupPreferenceBusy?: boolean;
  onRefreshRecovery?: () => void;
  onToggleCloudChatBackup?: (enabled: boolean) => void;
  onApprovePendingConfirmation?: (confirmationId: string) => void;
  onDenyPendingConfirmation?: (confirmationId: string) => void;
  onRestoreRecoveryItem?: (archiveId: string) => void;
  onPermanentDeleteRecoveryItem?: (archiveId: string) => void;
  onRestoreManagedWorkspace?: () => void;
  onDeleteRemoteAccountData?: () => void;
};

export function DesktopSetupRecoverySection({
  pendingConfirmations,
  recoveryItems,
  recoveryBusyId = null,
  recoveryMessage = null,
  remoteAccountSignedIn = false,
  remoteSecretsBusy = false,
  cloudChatBackupEnabled = true,
  cloudBackupPreferenceBusy = false,
  onRefreshRecovery,
  onToggleCloudChatBackup,
  onApprovePendingConfirmation,
  onDenyPendingConfirmation,
  onRestoreRecoveryItem,
  onPermanentDeleteRecoveryItem,
  onRestoreManagedWorkspace,
  onDeleteRemoteAccountData,
}: Props) {
  const accountCleanupDisabled = !remoteAccountSignedIn || remoteSecretsBusy || !onDeleteRemoteAccountData;
  const cloudBackupDisabled = !remoteAccountSignedIn || cloudBackupPreferenceBusy || !onToggleCloudChatBackup;
  const workspaceRestoreBusy = recoveryBusyId === 'workspace_restore';

  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>Recovery</Text>
      <Text style={styles.helperText}>
        EmploAI keeps chats, tool timelines, worker reports, automations, and generated artifacts recoverable where cloud backup is available.
      </Text>
      <View style={styles.settingStack}>
        <View style={styles.settingCard}>
          <View style={styles.settingRow}>
            <View style={styles.settingRowCopy}>
              <Text style={styles.settingCardTitle}>Cloud chat backup</Text>
              <Text style={styles.settingCardDescription}>
                {cloudChatBackupEnabled
                  ? 'Chats and tool timelines are saved as recoverable account snapshots.'
                  : 'Chats stay local to this signed-in desktop account.'}
              </Text>
            </View>
            <View style={styles.settingRowControls}>
              <Text style={styles.settingCardDescription}>{cloudChatBackupEnabled ? 'On' : 'Off'}</Text>
              <Pressable
                accessibilityRole="switch"
                accessibilityState={{ checked: cloudChatBackupEnabled, disabled: cloudBackupDisabled }}
                accessibilityLabel="Cloud chat backup"
                style={[
                  styles.toggleSwitch,
                  cloudChatBackupEnabled ? styles.toggleSwitchActive : null,
                  cloudBackupDisabled ? styles.voiceModeButtonDisabled : null,
                ]}
                onPress={() => onToggleCloudChatBackup?.(!cloudChatBackupEnabled)}
                disabled={cloudBackupDisabled}
              >
                <View style={[styles.toggleSwitchKnob, cloudChatBackupEnabled ? styles.toggleSwitchKnobActive : null]} />
              </Pressable>
            </View>
          </View>
        </View>
        <View style={styles.settingCard}>
          <Text style={styles.settingCardTitle}>Pending confirmations</Text>
          <Text style={styles.settingCardDescription}>
            Sensitive actions requested from desktop, mobile, Telegram, or Jarvis can be approved here before they continue.
          </Text>
          {pendingConfirmations.length ? (
            <View style={styles.settingStack}>
              {pendingConfirmations.slice(0, 8).map((item) => (
                <View key={item.confirmation_id} style={styles.settingCardInner}>
                  <Text style={styles.settingCardTitle}>{item.title}</Text>
                  <Text style={styles.settingCardDescription}>
                    {item.message}
                    {item.expires_at ? ` · expires ${item.expires_at}` : ''}
                  </Text>
                  <View style={styles.settingActionRow}>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel={`Approve ${item.title}`}
                      style={styles.voicePackActionButton}
                      onPress={() => onApprovePendingConfirmation?.(item.confirmation_id)}
                      disabled={!onApprovePendingConfirmation}
                    >
                      <Text style={styles.voicePackActionText}>Approve</Text>
                    </Pressable>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel={`Deny ${item.title}`}
                      style={styles.voicePackActionButtonSecondary}
                      onPress={() => onDenyPendingConfirmation?.(item.confirmation_id)}
                      disabled={!onDenyPendingConfirmation}
                    >
                      <Text style={styles.voicePackActionTextSecondary}>Deny</Text>
                    </Pressable>
                  </View>
                </View>
              ))}
            </View>
          ) : (
            <Text style={styles.helperText}>No sensitive actions are waiting for approval.</Text>
          )}
        </View>
        <View style={styles.settingCard}>
          <Text style={styles.settingCardTitle}>Archived items</Text>
          <Text style={styles.settingCardDescription}>
            Deleted chats, workers, automations, and reports are hidden first and kept for up to 30 days.
          </Text>
          <View style={styles.settingActionRow}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Refresh archived items"
              style={styles.voicePackActionButtonSecondary}
              onPress={() => onRefreshRecovery?.()}
              disabled={!onRefreshRecovery}
            >
              <Text style={styles.voicePackActionTextSecondary}>Refresh</Text>
            </Pressable>
          </View>
          {recoveryMessage ? <Text style={styles.helperText}>{recoveryMessage}</Text> : null}
          {recoveryItems.length ? (
            <View style={styles.settingStack}>
              {recoveryItems.slice(0, 12).map((item) => {
                const busy = recoveryBusyId === item.archive_id;
                const itemLabel = item.display_name || item.object_id;
                return (
                  <View key={item.archive_id} style={styles.settingCardInner}>
                    <Text style={styles.settingCardTitle}>{itemLabel}</Text>
                    <Text style={styles.settingCardDescription}>
                      {item.object_kind} · {item.status}
                      {item.expires_at ? ` · recoverable until ${item.expires_at}` : ''}
                    </Text>
                    <View style={styles.settingActionRow}>
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel={`Restore ${itemLabel}`}
                        style={[styles.voicePackActionButton, busy ? styles.voiceModeButtonDisabled : null]}
                        onPress={() => onRestoreRecoveryItem?.(item.archive_id)}
                        disabled={busy || !onRestoreRecoveryItem || item.status === 'restored'}
                      >
                        <Text style={styles.voicePackActionText}>{busy ? 'Working...' : 'Restore'}</Text>
                      </Pressable>
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel={`Permanently delete ${itemLabel}`}
                        style={[styles.voicePackActionButtonSecondary, busy ? styles.voiceModeButtonDisabled : null]}
                        onPress={() => onPermanentDeleteRecoveryItem?.(item.archive_id)}
                        disabled={busy || !onPermanentDeleteRecoveryItem}
                      >
                        <Text style={styles.voicePackActionTextSecondary}>Delete Forever</Text>
                      </Pressable>
                    </View>
                  </View>
                );
              })}
            </View>
          ) : (
            <Text style={styles.helperText}>No archived items are waiting to be restored.</Text>
          )}
        </View>
        <View style={styles.settingCard}>
          <Text style={styles.settingCardTitle}>Workspace restore</Text>
          <Text style={styles.settingCardDescription}>
            Restore generated files and captured evidence into a managed workspace on this computer. Local files you never uploaded will still need to be reconnected.
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Restore managed workspace"
            style={[
              styles.voicePackActionButtonSecondary,
              (workspaceRestoreBusy || !onRestoreManagedWorkspace) ? styles.voiceModeButtonDisabled : null,
            ]}
            onPress={() => onRestoreManagedWorkspace?.()}
            disabled={workspaceRestoreBusy || !onRestoreManagedWorkspace}
          >
            <Text style={styles.voicePackActionTextSecondary}>
              {workspaceRestoreBusy ? 'Restoring...' : 'Restore Workspace Files'}
            </Text>
          </Pressable>
        </View>
        <View style={styles.settingCard}>
          <Text style={styles.settingCardTitle}>Account cleanup</Text>
          <Text style={styles.settingCardDescription}>
            Use this only when you want to remove saved setup, synced app state, and recoverable account data from this account.
          </Text>
          <Pressable
            style={[
              styles.voicePackActionButtonSecondary,
              accountCleanupDisabled ? styles.voiceModeButtonDisabled : null,
            ]}
            onPress={() => onDeleteRemoteAccountData?.()}
            disabled={accountCleanupDisabled}
          >
            <Text style={styles.voicePackActionTextSecondary}>Delete Account Data</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}
