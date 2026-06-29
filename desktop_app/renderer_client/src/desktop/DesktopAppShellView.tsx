import { useEffect, useState } from 'react';
import { Platform, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { InfoHint } from '@/components/InfoHint';
import { copyDesktopText, openDesktopChromeExtensions, openDesktopPath } from '@/lib/desktopBridge';
import { passwordRequirementStatus } from '@/lib/remoteAuthPasswordPolicy';
import { shortStatusText, userFacingError } from '../../lib/diagnostics';
import { DesktopConversationView } from './DesktopConversationView';
import { DesktopSetupPanel } from './DesktopSetupPanel';
import { DesktopConversationSkeleton, DesktopStatusBanner, StartupGlyph } from './DesktopAppShellStartup';
import { styles } from './DesktopAppShell.styles';

const webBackdropBlurStyle =
  Platform.OS === 'web'
    ? ({ backdropFilter: 'blur(18px)', WebkitBackdropFilter: 'blur(18px)' } as any)
    : null;
const webWindowDragStyle =
  Platform.OS === 'web'
    ? ({ WebkitAppRegion: 'drag', userSelect: 'none' } as any)
    : null;
const webWindowNoDragStyle =
  Platform.OS === 'web'
    ? ({ WebkitAppRegion: 'no-drag' } as any)
    : null;

type DesktopAppShellViewProps = {
  scope: Record<string, any>;
};

export function DesktopAppShellView({ scope }: DesktopAppShellViewProps) {
  const {
    confirmAction,
    confirmationDialog,
    params,
    requestedSessionId,
    requestedTab,
    requestedDesktopRoute,
    requestedDesktopMode,
    requestedSurfaceMode,
    activeTab,
    setActiveTab,
    bootstrap,
    setBootstrap,
    runtimeStatus,
    setRuntimeStatus,
    updateStatus,
    setUpdateStatus,
    loadingState,
    setLoadingState,
    error,
    setError,
    notice,
    setNotice,
    conversationSidebarToggleSignal,
    setConversationSidebarToggleSignal,
    startupPhase,
    setStartupPhase,
    startupErrorDetail,
    setStartupErrorDetail,
    startupCurrentTimeoutSeconds,
    setStartupCurrentTimeoutSeconds,
    showSetup,
    setShowSetup,
    startingRuntime,
    setStartingRuntime,
    stoppingRuntime,
    setStoppingRuntime,
    savingSetup,
    setSavingSetup,
    voicePackBusyId,
    setVoicePackBusyId,
    voicePackProgress,
    setVoicePackProgress,
    checkingUpdates,
    setCheckingUpdates,
    installingUpdate,
    setInstallingUpdate,
    memoryState,
    setMemoryState,
    memoryLoading,
    setMemoryLoading,
    memorySaving,
    setMemorySaving,
    telegramBotConfigs,
    setTelegramBotConfigs,
    orchestratorStatus,
    setOrchestratorStatus,
    setupSessions,
    setSetupSessions,
    setupMaxTurns,
    setSetupMaxTurns,
    recoveryItems,
    setRecoveryItems,
    pendingConfirmations,
    setPendingConfirmations,
    recoveryBusyId,
    setRecoveryBusyId,
    recoveryMessage,
    setRecoveryMessage,
    sharedSettingsDraft,
    setSharedSettingsDraft,
    sharedSettingsSaving,
    sharedSettingsStatus,
    remoteAuthStatus,
    setRemoteAuthStatus,
    remoteAuthLoading,
    setRemoteAuthLoading,
    remoteAuthBusy,
    setRemoteAuthBusy,
    remoteAuthLoggingOut,
    remoteAuthMode,
    setRemoteAuthMode,
    remoteAuthEmail,
    setRemoteAuthEmail,
    remoteAuthPassword,
    setRemoteAuthPassword,
    remoteAuthDisplayName,
    setRemoteAuthDisplayName,
    remoteAuthRememberMe,
    setRemoteAuthRememberMe,
    remoteAuthOtpChallenge,
    setRemoteAuthOtpChallenge,
    remoteAuthOtpCode,
    setRemoteAuthOtpCode,
    remoteAuthMessage,
    setRemoteAuthMessage,
    remoteSecretItems,
    setRemoteSecretItems,
    remoteSecretsBusy,
    setRemoteSecretsBusy,
    remoteSecretsMessage,
    setRemoteSecretsMessage,
    remoteAccountHydrating,
    setRemoteAccountHydrating,
    remoteAccountSetupCheckPending,
    startupPhaseRef,
    startupWatchdogTimerRef,
    startupFlowInFlightRef,
    startupInitializedRef,
    startupAutoRetryAttemptedRef,
    startupAutoRetryInFlightRef,
    startupDeferredRetryTimeoutRef,
    startupRecoveryInFlightRef,
    postStartupRefreshKeyRef,
    postStartupSetupNoticeSentRef,
    previousTelegramStateRef,
    bootstrapRef,
    runtimeStatusRef,
    startupSleepWakeAttemptedRef,
    startupVoiceWarmKeyRef,
    remoteAccountHydratedKeyRef,
    remoteAccountHydrationInFlightKeyRef,
    runtimeDowngradeRecheckInFlightRef,
    resetAccountStartupState,
    refreshRemoteAuthStatus,
    submitRemoteAuth,
    verifyRemoteAuthOtp,
    resendRemoteAuthOtp,
    submitRemoteGoogleAuth,
    currentStartupWatchdogMs,
    nextStartupRetryWindowSeconds,
    setRuntimeStatusWithRef,
    shouldPreserveReadyRuntimeStatus,
    scheduleReadyRuntimeDowngradeRecheck,
    applyBootstrap,
    remoteAccountHydrationKey,
    hydrateSignedInAccountData,
    failStartup,
    retryStartupSilently,
    handleStartupFailure,
    beginStartup,
    refreshUpdateStatus,
    wakeDesktopFromSleepMode,
    reconnectDesktopAfterWindowReopen,
    recoverReadyRuntimeFromStatus,
    remoteRuntimes,
    effectiveRuntimeStatus,
    localRuntimeReady,
    runtimeProcessDetected,
    setupBlocksRuntime,
    chatSkeletonVisible,
    handleConversationStartupState,
    refreshSetupRuntimeControls,
    retryStartup,
    startLocalRuntime,
    stopLocalRuntimeNow,
    logoutRemoteAccount,
    deleteRemoteAccountData,
    refreshRecovery,
    setCloudChatBackupEnabled,
    saveSharedSettings,
    approveSharedConfirmation,
    denySharedConfirmation,
    restoreArchivedItem,
    permanentlyDeleteArchivedItem,
    restoreManagedWorkspace,
    deleteRemoteSecretFromCloud,
    removeLocalRuntimeSecret,
    createRemotePairingTokenFromAccount,
    refreshRemoteSecretItems,
    saveCurrentSetupSecretsToCloud,
    saveLoginCredentialSecretsToCloud,
    saveTelegramBotSecretToCloud,
    applyCloudSetupSecrets,
    saveSetup,
    refreshMemory,
    saveMemory,
    installVoicePack,
    removeVoicePack,
    selectVoiceEngine,
    installUpdateNow,
    createSetupTelegramBot,
    updateSetupTelegramBot,
    deleteSetupTelegramBot,
    configureRuntimeOrchestratorFromSetup,
    updateSetupGeneralAgentConfig,
    runtimeSummary,
    showStartupRuntimeSummary,
    updateAvailable,
    accountEmail,
    telegramStatus,
    telegramSummary,
    telegramStatusTone,
    navigateWindowHistory,
  } = scope;
  const [remoteAuthConfirmPasswordDraft, setRemoteAuthConfirmPasswordDraft] = useState('');
  const [remoteAuthPasswordVisible, setRemoteAuthPasswordVisible] = useState(false);
  const [remoteAuthConfirmPasswordVisible, setRemoteAuthConfirmPasswordVisible] = useState(false);
  const [remoteAuthOtpResendAvailableAt, setRemoteAuthOtpResendAvailableAt] = useState(0);
  const [remoteAuthResendCooldownSeconds, setRemoteAuthResendCooldownSeconds] = useState(0);
  const remoteAuthPasswordRequirements = passwordRequirementStatus(String(remoteAuthPassword || ''));

  useEffect(() => {
    if (!remoteAuthOtpChallenge) {
      setRemoteAuthOtpResendAvailableAt(0);
      setRemoteAuthResendCooldownSeconds(0);
      return;
    }
    const cooldownSeconds = Math.max(0, Number(remoteAuthOtpChallenge.resend_available_in_seconds || 0));
    setRemoteAuthOtpResendAvailableAt(cooldownSeconds > 0 ? Date.now() + cooldownSeconds * 1000 : 0);
    setRemoteAuthResendCooldownSeconds(Math.ceil(cooldownSeconds));
  }, [remoteAuthOtpChallenge?.challenge_id, remoteAuthOtpChallenge?.resend_available_in_seconds]);

  useEffect(() => {
    if (!remoteAuthOtpChallenge || !remoteAuthOtpResendAvailableAt) {
      setRemoteAuthResendCooldownSeconds(0);
      return;
    }
    const updateCooldown = () => {
      setRemoteAuthResendCooldownSeconds(Math.max(0, Math.ceil((remoteAuthOtpResendAvailableAt - Date.now()) / 1000)));
    };
    updateCooldown();
    const timer = globalThis.setInterval(updateCooldown, 1000);
    return () => {
      globalThis.clearInterval(timer);
    };
  }, [remoteAuthOtpChallenge?.challenge_id, remoteAuthOtpResendAvailableAt]);

  const remoteProfile = remoteAuthStatus?.profile && typeof remoteAuthStatus.profile === 'object'
    ? remoteAuthStatus.profile
    : {};
  const remotePreferences = remoteProfile.preferences && typeof remoteProfile.preferences === 'object'
    ? remoteProfile.preferences
    : {};
  const cloudChatBackupEnabled = remotePreferences.cloud_chat_backup_enabled !== false;
  const cloudBackupPreferenceBusy = recoveryBusyId === 'cloud_chat_backup';

  if (remoteAuthLoggingOut) {
    return (
      <SafeAreaView edges={['top', 'left', 'right', 'bottom']} style={styles.startupPage}>
        {confirmationDialog}
        <View style={styles.startupGateCard}>
          <Text style={styles.startupGateTitle}>Signing out</Text>
          <Text style={styles.startupGateText}>
            Closing the local session and clearing this device. This will only take a moment.
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  if (remoteAuthLoading || !remoteAuthStatus?.signedIn) {
    return (
      <SafeAreaView edges={['top', 'left', 'right', 'bottom']} style={styles.startupPage}>
        {confirmationDialog}
        <View style={styles.startupGateCard}>
          <Text style={styles.startupGateTitle}>Sign in to EmploAI</Text>
          <Text style={styles.startupGateText}>
            Sign in once so your desktop, phone, Telegram, and saved settings stay connected.
          </Text>
          <View style={styles.accountModeRow}>
            <Pressable
              style={[styles.accountModeButton, remoteAuthMode === 'login' ? styles.accountModeButtonActive : null]}
              onPress={() => {
                setRemoteAuthMode('login');
                setRemoteAuthOtpChallenge(null);
                setRemoteAuthOtpCode('');
                setRemoteAuthConfirmPasswordDraft('');
              }}
              disabled={remoteAuthBusy}
            >
              <Text style={[styles.accountModeText, remoteAuthMode === 'login' ? styles.accountModeTextActive : null]}>Log In</Text>
            </Pressable>
            <Pressable
              style={[styles.accountModeButton, remoteAuthMode === 'signup' ? styles.accountModeButtonActive : null]}
              onPress={() => {
                setRemoteAuthMode('signup');
                setRemoteAuthOtpChallenge(null);
                setRemoteAuthOtpCode('');
                setRemoteAuthConfirmPasswordDraft('');
              }}
              disabled={remoteAuthBusy}
            >
              <Text style={[styles.accountModeText, remoteAuthMode === 'signup' ? styles.accountModeTextActive : null]}>Sign Up</Text>
            </Pressable>
          </View>
          {remoteAuthOtpChallenge ? (
            <>
              <View style={styles.startupIssueRow}>
                <Text style={styles.startupHintText}>Enter the 6-digit code.</Text>
                <InfoHint text={`Sent to ${remoteAuthOtpChallenge.email}.`} />
              </View>
              <TextInput
                value={remoteAuthOtpCode}
                onChangeText={setRemoteAuthOtpCode}
                style={styles.accountInput}
                placeholder="Verification code"
                placeholderTextColor="#7f97bc"
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="number-pad"
              />
              <Pressable
                style={[styles.startupPrimaryButton, (remoteAuthBusy || remoteAuthLoading) ? styles.startupPrimaryButtonDisabled : null]}
                onPress={() => void verifyRemoteAuthOtp()}
                disabled={remoteAuthBusy || remoteAuthLoading}
              >
                <Text style={styles.startupPrimaryButtonText}>{remoteAuthBusy ? 'Verifying...' : 'Verify Code'}</Text>
              </Pressable>
              <View style={styles.startupActionRow}>
                <Pressable
                  style={[
                    styles.startupSecondaryButton,
                    (remoteAuthBusy || remoteAuthResendCooldownSeconds > 0) ? styles.startupPrimaryButtonDisabled : null,
                  ]}
                  onPress={() => void resendRemoteAuthOtp()}
                  disabled={remoteAuthBusy || remoteAuthResendCooldownSeconds > 0}
                >
                  <Text style={styles.startupSecondaryButtonText}>
                    {remoteAuthResendCooldownSeconds > 0 ? `Resend in ${remoteAuthResendCooldownSeconds}s` : 'Resend Code'}
                  </Text>
                </Pressable>
                <Pressable
                  style={[styles.startupSecondaryButton, remoteAuthBusy ? styles.startupPrimaryButtonDisabled : null]}
                  onPress={() => {
                    setRemoteAuthOtpChallenge(null);
                    setRemoteAuthOtpCode('');
                    setRemoteAuthMessage('');
                  }}
                  disabled={remoteAuthBusy}
                >
                  <Text style={styles.startupSecondaryButtonText}>Use Another Email</Text>
                </Pressable>
              </View>
            </>
          ) : (
            <>
              {remoteAuthMode === 'signup' ? (
                <TextInput
                  value={remoteAuthDisplayName}
                  onChangeText={setRemoteAuthDisplayName}
                  style={styles.accountInput}
                  placeholder="Display name"
                  placeholderTextColor="#7f97bc"
                  autoCapitalize="words"
                />
              ) : null}
              <TextInput
                value={remoteAuthEmail}
                onChangeText={setRemoteAuthEmail}
                style={styles.accountInput}
                placeholder="Email"
                placeholderTextColor="#7f97bc"
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
              />
              <View style={styles.accountPasswordInputRow}>
                <TextInput
                  value={remoteAuthPassword}
                  onChangeText={setRemoteAuthPassword}
                  style={[styles.accountInput, styles.accountPasswordInput]}
                  placeholder={remoteAuthMode === 'signup' ? 'Strong password' : 'Password'}
                  placeholderTextColor="#7f97bc"
                  autoCapitalize="none"
                  autoCorrect={false}
                  secureTextEntry={!remoteAuthPasswordVisible}
                />
                <Pressable
                  style={styles.accountPeekButton}
                  onPress={() => setRemoteAuthPasswordVisible((current) => !current)}
                  disabled={remoteAuthBusy}
                >
                  <Text style={styles.accountPeekButtonText}>{remoteAuthPasswordVisible ? 'Hide' : 'Show'}</Text>
                </Pressable>
              </View>
              {remoteAuthMode === 'signup' ? (
                <>
                  <View style={styles.accountPasswordInputRow}>
                    <TextInput
                      value={remoteAuthConfirmPasswordDraft}
                      onChangeText={setRemoteAuthConfirmPasswordDraft}
                      style={[styles.accountInput, styles.accountPasswordInput]}
                      placeholder="Confirm password"
                      placeholderTextColor="#7f97bc"
                      autoCapitalize="none"
                      autoCorrect={false}
                      secureTextEntry={!remoteAuthConfirmPasswordVisible}
                    />
                    <Pressable
                      style={styles.accountPeekButton}
                      onPress={() => setRemoteAuthConfirmPasswordVisible((current) => !current)}
                      disabled={remoteAuthBusy}
                    >
                      <Text style={styles.accountPeekButtonText}>{remoteAuthConfirmPasswordVisible ? 'Hide' : 'Show'}</Text>
                    </Pressable>
                  </View>
                  <View style={styles.accountPasswordChecklist}>
                    {remoteAuthPasswordRequirements.map((requirement: any) => (
                      <Text
                        key={requirement.id}
                        style={[
                          styles.accountPasswordRequirement,
                          requirement.met ? styles.accountPasswordRequirementMet : null,
                        ]}
                      >
                        {requirement.met ? '✓' : '-'} {requirement.label}
                      </Text>
                    ))}
                    {remoteAuthConfirmPasswordDraft ? (
                      <Text
                        style={[
                          styles.accountPasswordRequirement,
                          remoteAuthPassword === remoteAuthConfirmPasswordDraft ? styles.accountPasswordRequirementMet : null,
                        ]}
                      >
                        {remoteAuthPassword === remoteAuthConfirmPasswordDraft ? '✓' : '-'} Passwords match
                      </Text>
                    ) : null}
                  </View>
                </>
              ) : null}
              <Pressable
                style={styles.rememberRow}
                onPress={() => setRemoteAuthRememberMe((current: any) => !current)}
                disabled={remoteAuthBusy}
              >
                <View style={[styles.rememberBox, remoteAuthRememberMe ? styles.rememberBoxActive : null]}>
                  <Text style={styles.rememberCheck}>{remoteAuthRememberMe ? '✓' : ''}</Text>
                </View>
                <Text style={styles.rememberText}>Remember me for 7 days</Text>
              </Pressable>
              <Pressable
                style={[styles.startupPrimaryButton, (remoteAuthBusy || remoteAuthLoading) ? styles.startupPrimaryButtonDisabled : null]}
                onPress={() => void submitRemoteAuth({ confirmPassword: remoteAuthConfirmPasswordDraft })}
                disabled={remoteAuthBusy || remoteAuthLoading}
              >
                <Text style={styles.startupPrimaryButtonText}>
                  {remoteAuthBusy || remoteAuthLoading
                    ? 'Working...'
                    : remoteAuthMode === 'signup' ? 'Create Account' : 'Log In'}
                </Text>
              </Pressable>
              <Pressable
                style={[styles.startupGoogleButton, (remoteAuthBusy || remoteAuthLoading) ? styles.startupPrimaryButtonDisabled : null]}
                onPress={() => void submitRemoteGoogleAuth()}
                disabled={remoteAuthBusy || remoteAuthLoading}
              >
                <Text style={styles.startupGoogleButtonText}>Continue with Google</Text>
              </Pressable>
            </>
          )}
          {remoteAuthMessage || remoteAuthStatus?.error ? (
            <Text style={styles.startupHintText}>
              {shortStatusText(remoteAuthMessage || (remoteAuthStatus?.error ? userFacingError(remoteAuthStatus.error, 'Sign-in needs attention.') : ''))}
            </Text>
          ) : null}
        </View>
      </SafeAreaView>
    );
  }

  if (remoteAccountSetupCheckPending) {
    return (
      <SafeAreaView edges={['top', 'left', 'right', 'bottom']} style={styles.startupPage}>
        {confirmationDialog}
        <View style={styles.startupGateCard}>
          <StartupGlyph />
          <Text style={styles.startupGateTitle}>Checking saved setup</Text>
          <Text style={styles.startupGateText}>
            Looking for saved provider keys on this account.
          </Text>
          {loadingState ? <Text style={styles.startupHintText}>{shortStatusText(loadingState)}</Text> : null}
        </View>
      </SafeAreaView>
    );
  }

  if (startupPhase === 'setup_required') {
    return (
      <SafeAreaView edges={['top', 'left', 'right', 'bottom']} style={styles.startupPage}>
        {showSetup && bootstrap?.setupState ? (
          <View style={styles.startupSetupShell}>
            <DesktopSetupPanel
              setupState={bootstrap.setupState}
              saving={savingSetup}
              voicePackBusyId={voicePackBusyId}
              voicePackProgress={voicePackProgress}
              onSave={(values) => void saveSetup(values)}
              onInstallVoicePack={(packId) => void installVoicePack(packId)}
              onRemoveVoicePack={(packId) => void removeVoicePack(packId)}
              onDismiss={undefined}
              onOpenPath={(targetPath) => void openDesktopPath(targetPath)}
              onOpenChromeExtensions={() => void openDesktopChromeExtensions()}
              onCopyText={(textValue) => void copyDesktopText(textValue)}
              memoryState={memoryState}
              memoryLoading={memoryLoading}
              memorySaving={memorySaving}
              onReloadMemory={() => void refreshMemory()}
              onSaveMemory={(content) => void saveMemory(content)}
              updateStatus={updateStatus}
              checkingUpdates={checkingUpdates}
              installingUpdate={installingUpdate}
              onCheckUpdates={() => void refreshUpdateStatus(true)}
              onInstallUpdate={() => void installUpdateNow()}
              telegramBotConfigs={telegramBotConfigs}
              sessions={setupSessions}
              runtimeOrchestratorStatus={orchestratorStatus}
              currentMaxTurns={setupMaxTurns}
              onCreateTelegramBotConfig={(payload) => void createSetupTelegramBot(payload)}
              onUpdateTelegramBotConfig={(botConfigId, payload) => void updateSetupTelegramBot(botConfigId, payload)}
              onDeleteTelegramBotConfig={(botConfigId) => void deleteSetupTelegramBot(botConfigId)}
              onConfigureRuntimeOrchestrator={(payload) => void configureRuntimeOrchestratorFromSetup(payload)}
              onUpdateGeneralAgentConfig={(payload) => void updateSetupGeneralAgentConfig(payload)}
              remoteAuthStatus={remoteAuthStatus}
              onRefreshRemoteAuth={() => refreshRemoteAuthStatus()}
              onCreateRemotePairingToken={() => createRemotePairingTokenFromAccount()}
              remoteSecretItems={remoteSecretItems}
              remoteSecretsBusy={remoteSecretsBusy}
              remoteSecretsMessage={remoteSecretsMessage}
              onRefreshRemoteSecrets={() => void refreshRemoteSecretItems()}
              onSaveSetupSecrets={(values) => void saveCurrentSetupSecretsToCloud(values)}
              onSaveLoginCredentials={(payload) => void saveLoginCredentialSecretsToCloud(payload)}
              onApplySetupSecrets={() => void applyCloudSetupSecrets()}
              onDeleteRemoteSecret={(namespace, name) => void deleteRemoteSecretFromCloud(namespace, name)}
              onRemoveLocalRuntimeSecret={(name) => void removeLocalRuntimeSecret(name)}
              onDeleteRemoteAccountData={() => void deleteRemoteAccountData()}
              cloudChatBackupEnabled={cloudChatBackupEnabled}
              cloudBackupPreferenceBusy={cloudBackupPreferenceBusy}
              onToggleCloudChatBackup={(enabled) => void setCloudChatBackupEnabled(enabled)}
              sharedSettingsDraft={sharedSettingsDraft}
              sharedSettingsSaving={sharedSettingsSaving}
              sharedSettingsStatus={sharedSettingsStatus}
              onSharedSettingsDraftChange={setSharedSettingsDraft}
              onSaveSharedSettings={() => void saveSharedSettings()}
              recoveryItems={recoveryItems}
              pendingConfirmations={pendingConfirmations}
              recoveryBusyId={recoveryBusyId}
              recoveryMessage={recoveryMessage}
              onRefreshRecovery={() => void refreshRecovery()}
              onApprovePendingConfirmation={(confirmationId) => void approveSharedConfirmation(confirmationId)}
              onDenyPendingConfirmation={(confirmationId) => void denySharedConfirmation(confirmationId)}
              onRestoreRecoveryItem={(archiveId) => void restoreArchivedItem(archiveId)}
              onPermanentDeleteRecoveryItem={(archiveId) => void permanentlyDeleteArchivedItem(archiveId)}
              onRestoreManagedWorkspace={() => void restoreManagedWorkspace()}
            />
          </View>
        ) : (
          <View style={styles.startupGateCard}>
            <StartupGlyph />
            <Text style={styles.startupGateTitle}>Finish setup to start EmploAI</Text>
            <Text style={styles.startupGateText}>
              EmploAI needs the required setup values before it can start on this computer.
            </Text>
            <Pressable style={styles.startupPrimaryButton} onPress={() => setShowSetup(true)}>
              <Text style={styles.startupPrimaryButtonText}>Open Setup</Text>
            </Pressable>
          </View>
        )}
      </SafeAreaView>
    );
  }

  if (startupPhase === 'startup_error') {
    return (
      <SafeAreaView edges={['top', 'left', 'right', 'bottom']} style={styles.startupPage}>
        {confirmationDialog}
        {showSetup && bootstrap?.setupState ? (
          <View style={styles.startupSetupShell}>
            <DesktopSetupPanel
              setupState={bootstrap.setupState}
              saving={savingSetup}
              voicePackBusyId={voicePackBusyId}
              voicePackProgress={voicePackProgress}
              onSave={(values) => void saveSetup(values)}
              onInstallVoicePack={(packId) => void installVoicePack(packId)}
              onRemoveVoicePack={(packId) => void removeVoicePack(packId)}
              onDismiss={() => setShowSetup(false)}
              onOpenPath={(targetPath) => void openDesktopPath(targetPath)}
              onOpenChromeExtensions={() => void openDesktopChromeExtensions()}
              onCopyText={(textValue) => void copyDesktopText(textValue)}
              memoryState={memoryState}
              memoryLoading={memoryLoading}
              memorySaving={memorySaving}
              onReloadMemory={() => void refreshMemory()}
              onSaveMemory={(content) => void saveMemory(content)}
              updateStatus={updateStatus}
              checkingUpdates={checkingUpdates}
              installingUpdate={installingUpdate}
              onCheckUpdates={() => void refreshUpdateStatus(true)}
              onInstallUpdate={() => void installUpdateNow()}
              telegramBotConfigs={telegramBotConfigs}
              sessions={setupSessions}
              runtimeOrchestratorStatus={orchestratorStatus}
              currentMaxTurns={setupMaxTurns}
              onCreateTelegramBotConfig={(payload) => void createSetupTelegramBot(payload)}
              onUpdateTelegramBotConfig={(botConfigId, payload) => void updateSetupTelegramBot(botConfigId, payload)}
              onDeleteTelegramBotConfig={(botConfigId) => void deleteSetupTelegramBot(botConfigId)}
              onConfigureRuntimeOrchestrator={(payload) => void configureRuntimeOrchestratorFromSetup(payload)}
              onUpdateGeneralAgentConfig={(payload) => void updateSetupGeneralAgentConfig(payload)}
              remoteAuthStatus={remoteAuthStatus}
              onRefreshRemoteAuth={() => refreshRemoteAuthStatus()}
              onCreateRemotePairingToken={() => createRemotePairingTokenFromAccount()}
              remoteSecretItems={remoteSecretItems}
              remoteSecretsBusy={remoteSecretsBusy}
              remoteSecretsMessage={remoteSecretsMessage}
              onRefreshRemoteSecrets={() => void refreshRemoteSecretItems()}
              onSaveSetupSecrets={(values) => void saveCurrentSetupSecretsToCloud(values)}
              onSaveLoginCredentials={(payload) => void saveLoginCredentialSecretsToCloud(payload)}
              onApplySetupSecrets={() => void applyCloudSetupSecrets()}
              onDeleteRemoteSecret={(namespace, name) => void deleteRemoteSecretFromCloud(namespace, name)}
              onRemoveLocalRuntimeSecret={(name) => void removeLocalRuntimeSecret(name)}
              onDeleteRemoteAccountData={() => void deleteRemoteAccountData()}
              cloudChatBackupEnabled={cloudChatBackupEnabled}
              cloudBackupPreferenceBusy={cloudBackupPreferenceBusy}
              onToggleCloudChatBackup={(enabled) => void setCloudChatBackupEnabled(enabled)}
              sharedSettingsDraft={sharedSettingsDraft}
              sharedSettingsSaving={sharedSettingsSaving}
              sharedSettingsStatus={sharedSettingsStatus}
              onSharedSettingsDraftChange={setSharedSettingsDraft}
              onSaveSharedSettings={() => void saveSharedSettings()}
              recoveryItems={recoveryItems}
              pendingConfirmations={pendingConfirmations}
              recoveryBusyId={recoveryBusyId}
              recoveryMessage={recoveryMessage}
              onRefreshRecovery={() => void refreshRecovery()}
              onApprovePendingConfirmation={(confirmationId) => void approveSharedConfirmation(confirmationId)}
              onDenyPendingConfirmation={(confirmationId) => void denySharedConfirmation(confirmationId)}
              onRestoreRecoveryItem={(archiveId) => void restoreArchivedItem(archiveId)}
              onPermanentDeleteRecoveryItem={(archiveId) => void permanentlyDeleteArchivedItem(archiveId)}
              onRestoreManagedWorkspace={() => void restoreManagedWorkspace()}
            />
          </View>
        ) : (
          <View style={styles.startupGateCard}>
            <StartupGlyph />
            <Text style={styles.startupGateTitle}>Startup needs attention</Text>
            <View style={styles.startupIssueRow}>
              <Text style={styles.startupGateText}>
                {startupErrorDetail || error ? 'Desktop startup did not finish.' : 'The desktop app could not finish becoming ready.'}
              </Text>
              {startupErrorDetail || error ? <InfoHint text={startupErrorDetail || error || ''} /> : null}
            </View>
            <Text style={styles.startupHintText}>
              Retry will use a {nextStartupRetryWindowSeconds}-second runtime window.
            </Text>
            <View style={styles.startupActionRow}>
              <Pressable
                style={[styles.startupPrimaryButton, startingRuntime ? styles.startupPrimaryButtonDisabled : null]}
                onPress={() => void retryStartup()}
                disabled={startingRuntime}
              >
                <Text style={styles.startupPrimaryButtonText}>{startingRuntime ? 'Retrying...' : 'Retry Startup'}</Text>
              </Pressable>
              {bootstrap?.setupState ? (
                <Pressable style={styles.startupSecondaryButton} onPress={() => setShowSetup(true)}>
                  <Text style={styles.startupSecondaryButtonText}>Open Setup</Text>
                </Pressable>
              ) : null}
            </View>
          </View>
        )}
      </SafeAreaView>
    );
  }

  if (startupPhase === 'bootstrapping' || startupPhase === 'starting_runtime') {
    return (
      <SafeAreaView edges={['top', 'left', 'right', 'bottom']} style={styles.startupPage}>
        {confirmationDialog}
        <View style={styles.startupGateCard}>
          <StartupGlyph />
          <Text style={styles.startupGateTitle}>Starting EmploAI</Text>
            <Text style={styles.startupGateText}>
              {loadingState || 'Preparing the local runtime.'}
            </Text>
          {showStartupRuntimeSummary ? (
            <Text style={styles.startupHintText}>{runtimeSummary}</Text>
          ) : null}
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView edges={['top', 'left', 'right', 'bottom']} style={styles.page}>
      {confirmationDialog}
      <View style={[styles.windowChromeBar, webWindowDragStyle]}>
        <View style={[styles.windowChromeLeft, webWindowNoDragStyle]}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Toggle sidebar"
            style={({ pressed, hovered }) => [
              styles.windowChromeIconButton,
              hovered ? styles.windowChromeButtonHovered : null,
              pressed ? styles.windowChromeButtonPressed : null,
            ]}
            onPress={() => setConversationSidebarToggleSignal((value: any) => value + 1)}
          >
            <Text style={styles.windowChromeIconText}>▯</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Back"
            onPress={() => navigateWindowHistory('back')}
            style={({ pressed, hovered }) => [
              styles.windowChromeIconButton,
              styles.windowChromeButtonSubtle,
              hovered ? styles.windowChromeButtonHovered : null,
              pressed ? styles.windowChromeButtonPressed : null,
            ]}
          >
            <Text style={styles.windowChromeIconText}>‹</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Forward"
            onPress={() => navigateWindowHistory('forward')}
            style={({ pressed, hovered }) => [
              styles.windowChromeIconButton,
              styles.windowChromeButtonSubtle,
              hovered ? styles.windowChromeButtonHovered : null,
              pressed ? styles.windowChromeButtonPressed : null,
            ]}
          >
            <Text style={styles.windowChromeIconText}>›</Text>
          </Pressable>
          {['File', 'Edit', 'View'].map((item) => (
            <Pressable
              key={`chrome-menu-${item}`}
              accessibilityRole="button"
              style={({ pressed, hovered }) => [
                styles.windowChromeMenuButton,
                hovered ? styles.windowChromeMenuButtonHovered : null,
                pressed ? styles.windowChromeButtonPressed : null,
              ]}
              onPress={() => {
                if (item === 'View') {
                  setConversationSidebarToggleSignal((value: any) => value + 1);
                }
              }}
            >
              <Text style={styles.windowChromeMenuText}>{item}</Text>
            </Pressable>
          ))}
          <Pressable
            accessibilityRole="button"
            style={({ pressed, hovered }) => [
              styles.windowChromeMenuButton,
              hovered ? styles.windowChromeMenuButtonHovered : null,
              pressed ? styles.windowChromeButtonPressed : null,
            ]}
            onPress={() => setNotice('Open Settings for setup, recovery, voice, updates, and account controls.')}
          >
            <Text style={styles.windowChromeMenuText}>Help</Text>
          </Pressable>
        </View>
        <View style={[styles.windowChromeRight, webWindowNoDragStyle]}>
          {updateAvailable ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Install available update"
              style={({ pressed, hovered }) => [
                styles.windowChromeIconButton,
                styles.windowChromeUpdateButton,
                hovered ? styles.windowChromeButtonHovered : null,
                pressed ? styles.windowChromeButtonPressed : null,
                installingUpdate ? styles.headerActionDisabled : null,
              ]}
              onPress={() => void installUpdateNow()}
              disabled={installingUpdate}
            >
              <Text style={styles.windowChromeUpdateText}>{installingUpdate ? '...' : '↑'}</Text>
            </Pressable>
          ) : checkingUpdates ? (
            <View style={[styles.windowChromeIconButton, styles.headerIconButtonMuted]}>
              <Text style={styles.windowChromeIconText}>↻</Text>
            </View>
          ) : null}
          <Pressable
            style={[
              styles.windowChromeStopButton,
              runtimeProcessDetected ? styles.windowChromeStopButtonActive : styles.windowChromeStartButton,
              (startingRuntime || stoppingRuntime || (setupBlocksRuntime && !runtimeProcessDetected)) ? styles.headerActionDisabled : null,
            ]}
            onPress={() => void (runtimeProcessDetected ? stopLocalRuntimeNow() : startLocalRuntime())}
            disabled={startingRuntime || stoppingRuntime || (setupBlocksRuntime && !runtimeProcessDetected)}
          >
            <Text style={[styles.windowChromeStopText, runtimeProcessDetected ? styles.windowChromeStopTextActive : null]}>
              {stoppingRuntime ? '■ Stopping' : runtimeProcessDetected ? '■ Stop' : startingRuntime ? '▶ Starting' : '▶ Start'}
            </Text>
          </Pressable>
        </View>
      </View>

      {/* ── Error banner ── */}
      {error ? (
        <DesktopStatusBanner tone="error" message={error} onDismiss={() => setError(null)} />
      ) : null}

      {notice && !error ? (
        <DesktopStatusBanner tone="notice" message={notice} onDismiss={() => setNotice(null)} />
      ) : null}

      {/* ── Main content: conversation fills all remaining space ── */}
      {setupBlocksRuntime ? (
        <View style={styles.tabBody}>
          <View style={styles.loadingCard}>
            <Text style={styles.loadingTitle}>Finish setup to start the local agent</Text>
            <Text style={styles.loadingText}>
              EmploAI needs the required setup values before the local agent can start on this computer.
            </Text>
            <Pressable style={styles.runtimeButton} onPress={() => setShowSetup(true)}>
              <Text style={styles.runtimeButtonText}>Open Setup</Text>
            </Pressable>
          </View>
        </View>
      ) : activeTab === 'local' ? (
        <View style={styles.tabBody}>
          {bootstrap && localRuntimeReady && startupPhase === 'ready' ? (
            <View style={styles.conversationBootShell}>
              <DesktopConversationView
                apiBaseUrl={bootstrap.apiBaseUrl}
                token={bootstrap.accessToken}
                initialSessionId={requestedSessionId || bootstrap.currentSessionId || undefined}
                initialSurfaceMode={requestedSurfaceMode}
                runtimeMode={bootstrap.runtimeMode}
                runtimeStatus={effectiveRuntimeStatus}
                envFilePath={bootstrap.envFilePath || undefined}
                defaultWorkspace={bootstrap.setupState?.values.DEFAULT_WORKSPACE || bootstrap.workspaceRoot || undefined}
                defaultInterruptPolicy={bootstrap.setupState?.values.INTERRUPT_POLICY_DEFAULT || 'none'}
                configuredModelGroups={bootstrap.setupState?.modelGroups || []}
                configuredPlannerModels={bootstrap.setupState?.plannerModels || []}
                voicePackState={bootstrap.setupState?.voicePacks || null}
                voiceStatus={bootstrap.setupState?.voiceStatus || null}
                onSelectVoiceEngine={(engine) => selectVoiceEngine(engine)}
                onStartupStateChange={handleConversationStartupState}
                onOpenSetup={() => setShowSetup(true)}
                accountEmail={accountEmail}
                updateAvailable={updateAvailable}
                remoteAuthBusy={remoteAuthBusy}
                remoteAuthLoggingOut={remoteAuthLoggingOut}
                onLogoutRemoteAccount={() => void logoutRemoteAccount()}
                onInviteUnavailable={() => setNotice('Invite flow is not available in this beta yet.')}
                setupOpen={showSetup}
                sidebarToggleSignal={conversationSidebarToggleSignal}
              />
            </View>
          ) : chatSkeletonVisible ? (
            <DesktopConversationSkeleton />
          ) : (
            <View style={styles.loadingCard}>
              <Text style={styles.loadingTitle}>Desktop shell is running</Text>
              <Text style={styles.loadingText}>
                Start the runtime to host the agent on this computer, or open setup to configure keys, updates, and local tools.
              </Text>
              <View style={styles.offlineMetaCard}>
                <Text style={styles.offlineMetaLabel}>Local runtime</Text>
                <Text style={styles.offlineMetaValue}>{runtimeSummary}</Text>
                <Text style={styles.offlineMetaText}>
                  {runtimeProcessDetected
                    ? 'Runtime process detected but unhealthy. Stop it, then start again.'
                    : effectiveRuntimeStatus?.detail || bootstrap?.runtimeStatus?.detail || 'No local runtime attached yet.'}
                </Text>
              </View>
              <View style={styles.offlineActionRow}>
                <Pressable
                  style={[
                    runtimeProcessDetected ? styles.secondaryRuntimeButton : styles.runtimeButton,
                    (runtimeProcessDetected ? stoppingRuntime : startingRuntime) ? styles.runtimeButtonDisabled : null,
                  ]}
                  onPress={() => void (runtimeProcessDetected ? stopLocalRuntimeNow() : startLocalRuntime())}
                  disabled={runtimeProcessDetected ? stoppingRuntime : startingRuntime}
                >
                  <Text style={runtimeProcessDetected ? styles.secondaryRuntimeButtonText : styles.runtimeButtonText}>
                    {runtimeProcessDetected
                      ? stoppingRuntime ? 'Stopping...' : 'Force Stop Runtime'
                      : startingRuntime ? 'Starting...' : 'Start Local Runtime'}
                  </Text>
                </Pressable>
              </View>
            </View>
          )}
        </View>
      ) : (
        <ScrollView style={styles.tabBody} contentContainerStyle={styles.remoteBody}>
          <View style={styles.remoteIntro}>
            <Text style={styles.remoteIntroTitle}>Remote runtime control is planned</Text>
            <Text style={styles.remoteIntroText}>
              This tab accounts for hosted agents and multi-computer orchestration. Only the local tab is functional in this beta.
            </Text>
          </View>
              {remoteRuntimes.map((runtime: any) => (
            <View key={runtime.id} style={styles.remoteCard}>
              <View style={styles.remoteHeader}>
                <View>
                  <Text style={styles.remoteTitle}>{runtime.name}</Text>
                  <Text style={styles.remoteMeta}>{runtime.hostLabel}</Text>
                </View>
                <View style={styles.remoteStatusBadge}>
                  <Text style={styles.remoteStatusText}>{runtime.status}</Text>
                </View>
              </View>
              <View style={styles.remoteDetailRow}>
                <Text style={styles.remoteDetail}>Details available</Text>
                <InfoHint text={runtime.detail} />
              </View>
            </View>
          ))}
        </ScrollView>
      )}
      {showSetup && bootstrap?.setupState ? (
        <View style={styles.setupOverlay} pointerEvents="box-none">
          <View style={[styles.setupOverlayBackdrop, webBackdropBlurStyle]} />
          <View style={styles.setupOverlayFrame} pointerEvents="box-none">
            <View style={styles.setupOverlaySurface}>
              <DesktopSetupPanel
                setupState={bootstrap.setupState}
                saving={savingSetup}
                voicePackBusyId={voicePackBusyId}
                voicePackProgress={voicePackProgress}
                onSave={(values) => void saveSetup(values)}
                onInstallVoicePack={(packId) => void installVoicePack(packId)}
                onRemoveVoicePack={(packId) => void removeVoicePack(packId)}
                onDismiss={bootstrap.setupState.required ? undefined : () => setShowSetup(false)}
                onOpenPath={(targetPath) => void openDesktopPath(targetPath)}
                onOpenChromeExtensions={() => void openDesktopChromeExtensions()}
                onCopyText={(textValue) => void copyDesktopText(textValue)}
                memoryState={memoryState}
                memoryLoading={memoryLoading}
                memorySaving={memorySaving}
                onReloadMemory={() => void refreshMemory()}
                onSaveMemory={(content) => void saveMemory(content)}
                updateStatus={updateStatus}
                checkingUpdates={checkingUpdates}
                installingUpdate={installingUpdate}
                onCheckUpdates={() => void refreshUpdateStatus(true)}
                onInstallUpdate={() => void installUpdateNow()}
                telegramBotConfigs={telegramBotConfigs}
                sessions={setupSessions}
                runtimeOrchestratorStatus={orchestratorStatus}
                currentMaxTurns={setupMaxTurns}
                onCreateTelegramBotConfig={(payload) => void createSetupTelegramBot(payload)}
                onUpdateTelegramBotConfig={(botConfigId, payload) => void updateSetupTelegramBot(botConfigId, payload)}
                onDeleteTelegramBotConfig={(botConfigId) => void deleteSetupTelegramBot(botConfigId)}
                onConfigureRuntimeOrchestrator={(payload) => void configureRuntimeOrchestratorFromSetup(payload)}
                onUpdateGeneralAgentConfig={(payload) => void updateSetupGeneralAgentConfig(payload)}
                remoteAuthStatus={remoteAuthStatus}
                onRefreshRemoteAuth={() => refreshRemoteAuthStatus()}
                onCreateRemotePairingToken={() => createRemotePairingTokenFromAccount()}
                remoteSecretItems={remoteSecretItems}
                remoteSecretsBusy={remoteSecretsBusy}
                remoteSecretsMessage={remoteSecretsMessage}
                onRefreshRemoteSecrets={() => void refreshRemoteSecretItems()}
                onSaveSetupSecrets={(values) => void saveCurrentSetupSecretsToCloud(values)}
                onSaveLoginCredentials={(payload) => void saveLoginCredentialSecretsToCloud(payload)}
                onApplySetupSecrets={() => void applyCloudSetupSecrets()}
                onDeleteRemoteSecret={(namespace, name) => void deleteRemoteSecretFromCloud(namespace, name)}
                onRemoveLocalRuntimeSecret={(name) => void removeLocalRuntimeSecret(name)}
                onDeleteRemoteAccountData={() => void deleteRemoteAccountData()}
                cloudChatBackupEnabled={cloudChatBackupEnabled}
                cloudBackupPreferenceBusy={cloudBackupPreferenceBusy}
                onToggleCloudChatBackup={(enabled) => void setCloudChatBackupEnabled(enabled)}
                sharedSettingsDraft={sharedSettingsDraft}
                sharedSettingsSaving={sharedSettingsSaving}
                sharedSettingsStatus={sharedSettingsStatus}
                onSharedSettingsDraftChange={setSharedSettingsDraft}
                onSaveSharedSettings={() => void saveSharedSettings()}
                recoveryItems={recoveryItems}
                pendingConfirmations={pendingConfirmations}
                recoveryBusyId={recoveryBusyId}
                recoveryMessage={recoveryMessage}
                onRefreshRecovery={() => void refreshRecovery()}
                onApprovePendingConfirmation={(confirmationId) => void approveSharedConfirmation(confirmationId)}
                onDenyPendingConfirmation={(confirmationId) => void denySharedConfirmation(confirmationId)}
                onRestoreRecoveryItem={(archiveId) => void restoreArchivedItem(archiveId)}
                onPermanentDeleteRecoveryItem={(archiveId) => void permanentlyDeleteArchivedItem(archiveId)}
                onRestoreManagedWorkspace={() => void restoreManagedWorkspace()}
              />
            </View>
          </View>
        </View>
      ) : null}
    </SafeAreaView>
  );
}
