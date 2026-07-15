import {
  approvePendingConfirmation,
  configureAgent,
  configureHeadlessRuntime,
  controlAgentRun,
  createPendingConfirmation,
  createTelegramBotConfig,
  deleteTelegramBotConfig,
  denyPendingConfirmation,
  configureVoiceTtsBackend,
  fetchAgentOverview,
  fetchPendingConfirmations,
  fetchRecoveryItems,
  fetchRuntimeOrchestratorStatus,
  fetchSessions,
  fetchTelegramBotConfigs,
  permanentlyDeleteRecoveryItem,
  reloadProviderKeys,
  restoreRecoveryItem,
  restoreWorkspaceFiles,
  updateTelegramBotConfig,
  warmVoiceRuntime,
} from '@/lib/appApi';
import { describeError, userFacingError } from '../../lib/diagnostics';
import { createApprovedConfirmation } from '@/lib/sharedConfirmations';
import {
  applySharedSettingsDraftToProfile,
  profileToSharedSettingsDraft,
  sharedMaxTurnsFromDraft,
  validateSharedSettingsDraft,
} from '@/lib/accountProfile';
import {
  LIVE_APPLY_SETUP_FIELDS,
  RESTART_REQUIRED_SETUP_FIELDS,
  SETUP_PROVIDER_SECRET_LABELS,
  changedSetupFields,
  hasFilledLiveApplySetupSecret,
  hasFilledRestartRequiredSetupSecret,
  hasFilledSetupSecret,
  sanitizeLocalSetupValues,
  setupValuesForRuntimeSave,
} from './setupValues';
import {
  applyDesktopAccountData,
  createDesktopRemotePairingToken,
  deleteDesktopRemoteAccountData,
  deleteDesktopRemoteSecret,
  hideDesktopWindowForSleepMode,
  installDesktopUpdate,
  installDesktopVoicePack,
  loadDesktopBootstrap,
  loadDesktopMemory,
  loadDesktopRuntimeStatus,
  logoutDesktopRemoteAuth,
  listDesktopRemoteSecrets,
  removeDesktopVoicePack,
  saveDesktopMemory,
  saveDesktopRemoteSecrets,
  saveDesktopSetup,
  saveDesktopSetupSecrets,
  setDesktopVoiceDefaultEngine,
  startDesktopRuntime,
  stopDesktopRuntime,
  updateDesktopRemoteAccountProfile,
  type DesktopBootstrap,
  type DesktopSetupValues,
} from '@/lib/desktopBridge';

type DesktopAppShellActionsContext = Record<string, any>;

export function createDesktopAppShellActions(context: DesktopAppShellActionsContext) {
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
    accountMenuOpen,
    setAccountMenuOpen,
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
    setSharedSettingsSaving,
    setSharedSettingsStatus,
    remoteAuthStatus,
    setRemoteAuthStatus,
    remoteAuthLoading,
    setRemoteAuthLoading,
    remoteAuthBusy,
    setRemoteAuthBusy,
    setRemoteAuthLoggingOut,
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
    effectiveRuntimeStatus,
    localRuntimeReady,
    runtimeProcessDetected,
    setupBlocksRuntime,
    chatSkeletonVisible,
    handleConversationStartupState,
    refreshSetupRuntimeControls,
    retryStartup,
    DESKTOP_RUNTIME_RESTART_WAIT_MS,
    delay,
    desktopVoicePackLabel,
  } = context;

  const startLocalRuntime = async () => {
    setStartingRuntime(true);
    setError(null);
    setNotice(null);
    setLoadingState('starting local runtime');
    try {
      const payload = await startDesktopRuntime();
      if (!payload) {
        setError('Desktop runtime controls are unavailable in this shell.');
        setLoadingState('runtime controls unavailable');
        return;
      }
      applyBootstrap(payload);
      if (!payload.runtimeStatus?.ok || !payload.accessToken) {
        const recovered = await recoverReadyRuntimeFromStatus();
        if (!recovered) {
          setError(
            payload.runtimeStatus?.detail ||
            'Local runtime did not become ready. Check the desktop runtime logs and try again.'
          );
        }
        return;
      }
      await recoverReadyRuntimeFromStatus();
    } catch (runtimeError) {
      setError(String(runtimeError));
      setLoadingState('runtime start failed');
    } finally {
      setStartingRuntime(false);
    }
  };

  const stopLocalRuntimeNow = async () => {
    setStoppingRuntime(true);
    setError(null);
    setNotice(null);
    try {
      const payload = await stopDesktopRuntime();
      if (!payload) {
        setError('Desktop runtime stop controls are unavailable in this shell.');
        return;
      }
      applyBootstrap(payload);
    } catch (runtimeError) {
      setError(String(runtimeError));
    } finally {
      setStoppingRuntime(false);
    }
  };

  const logoutRemoteAccount = async () => {
    setRemoteAuthLoggingOut(true);
    setRemoteAuthBusy(true);
    setError(null);
    setNotice(null);
    setRemoteAuthMessage('Signing out…');
    try {
      if (runtimeProcessDetected || localRuntimeReady) {
        await stopDesktopRuntime().catch(() => null);
      }
      const status = await logoutDesktopRemoteAuth();
      setRemoteAuthStatus(status || { signedIn: false, cloudDisabled: true, standalone: true, apiBaseUrl: 'http://127.0.0.1:8787' });
      setRemoteAuthPassword('');
      setRemoteAuthMessage('Signed out.');
      resetAccountStartupState();
      setStartupPhase('bootstrapping');
      setBootstrap(null);
      setRuntimeStatus(null);
      setLoadingState('Sign-in required');
    } catch (logoutError) {
      setError(userFacingError(logoutError, 'Logout did not finish.'));
    } finally {
      setRemoteAuthBusy(false);
      setRemoteAuthLoggingOut(false);
    }
  };

  const deleteRemoteAccountData = async () => {
    if (!remoteAuthStatus?.signedIn) {
      setRemoteSecretsMessage('Sign in before deleting account data.');
      return;
    }
    if (!bootstrap?.apiBaseUrl || !bootstrap?.accessToken) {
      setRemoteSecretsMessage('App account session is not ready yet.');
      return;
    }
    const confirmationId = await createApprovedConfirmation(bootstrap.apiBaseUrl, bootstrap.accessToken, confirmAction, {
      action_kind: 'remote_account_data_delete',
      title: 'Delete account data?',
      message: 'This removes saved setup, connected-device state, and saved access for this account while keeping the login account.',
      risk_tier: 'danger',
      origin_surface: 'desktop',
      payload: {},
    }, {
      confirmLabel: 'Delete Data',
      tone: 'danger',
      details: ['Archived app data is recoverable only where the account service supports it.', 'This action cannot be undone from this computer.'],
    });
    if (!confirmationId) {
      return;
    }
    setRemoteSecretsBusy(true);
    setRemoteSecretsMessage('Deleting saved account data…');
    try {
      const result = await deleteDesktopRemoteAccountData(confirmationId);
      if (!result) {
        throw new Error('Desktop account data controls are unavailable in this shell.');
      }
      remoteAccountHydratedKeyRef.current = null;
      setRemoteSecretItems([]);
      const status = await refreshRemoteAuthStatus();
      if (status?.profile) {
        setRemoteAuthStatus(status);
      }
      setRemoteSecretsMessage('Saved account data deleted.');
    } catch (deleteError) {
      setRemoteSecretsMessage(userFacingError(deleteError, 'Saved account data was not deleted.'));
    } finally {
      setRemoteSecretsBusy(false);
    }
  };

  const refreshRecovery = async () => {
    if (!bootstrap?.apiBaseUrl || !bootstrap?.accessToken) {
      setRecoveryItems([]);
      setPendingConfirmations([]);
      return;
    }
    try {
      const [response, confirmations] = await Promise.all([
        fetchRecoveryItems(bootstrap.apiBaseUrl, bootstrap.accessToken),
        fetchPendingConfirmations(bootstrap.apiBaseUrl, bootstrap.accessToken).catch(() => ({ items: [] })),
      ]);
      setRecoveryItems(Array.isArray(response.items) ? response.items : []);
      setPendingConfirmations(Array.isArray(confirmations.items) ? confirmations.items : []);
    } catch (recoveryError) {
      setRecoveryMessage(userFacingError(recoveryError, 'Recovery did not load.'));
    }
  };

  const setCloudChatBackupEnabled = async (enabled: boolean) => {
    if (remoteAuthStatus?.cloudDisabled) {
      setRecoveryMessage('Cloud chat backup is disabled in standalone desktop mode.');
      return;
    }
    if (!remoteAuthStatus?.signedIn) {
      setRecoveryMessage('Sign in before changing cloud chat backup.');
      return;
    }
    const currentProfile: Record<string, unknown> = remoteAuthStatus.profile && typeof remoteAuthStatus.profile === 'object'
      ? remoteAuthStatus.profile
      : {};
    const currentPreferences = currentProfile.preferences && typeof currentProfile.preferences === 'object'
      ? currentProfile.preferences as Record<string, unknown>
      : {};
    const nextProfile = {
      ...currentProfile,
      preferences: {
        ...currentPreferences,
        cloud_chat_backup_enabled: Boolean(enabled),
      },
    };
    setRecoveryBusyId('cloud_chat_backup');
    setRecoveryMessage(enabled ? 'Enabling cloud chat backup…' : 'Disabling cloud chat backup…');
    try {
      const result = await updateDesktopRemoteAccountProfile(nextProfile);
      if (!result) {
        throw new Error('Desktop account profile controls are unavailable in this shell.');
      }
      const profile = result.profile && typeof result.profile === 'object' ? result.profile : nextProfile;
      setRemoteAuthStatus((current: any) => current ? { ...current, profile } : current);
      setRecoveryMessage(
        enabled
          ? 'Cloud chat backup enabled.'
          : 'Cloud chat backup disabled. Chats stay local unless you enable it again.',
      );
    } catch (profileError) {
      setRecoveryMessage(userFacingError(profileError, 'Cloud chat backup setting was not saved.'));
    } finally {
      setRecoveryBusyId(null);
    }
  };

  const saveSharedSettings = async () => {
    const validationError = validateSharedSettingsDraft(sharedSettingsDraft);
    if (validationError) {
      setSharedSettingsStatus(validationError);
      return false;
    }
    const cloudAccountEnabled = Boolean(remoteAuthStatus?.signedIn && !remoteAuthStatus?.cloudDisabled);
    const standaloneMode = Boolean(remoteAuthStatus?.cloudDisabled || remoteAuthStatus?.standalone);
    if (!cloudAccountEnabled && !standaloneMode) {
      setSharedSettingsStatus('Sign in before saving shared settings.');
      return false;
    }
    setSharedSettingsSaving(true);
    setSharedSettingsStatus(standaloneMode ? 'Saving local settings…' : 'Saving shared settings…');
    try {
      const maxTurns = sharedMaxTurnsFromDraft(sharedSettingsDraft);
      const runtimePayload = {
        ...(maxTurns ? { max_turns: maxTurns } : {}),
        verbose_mode: sharedSettingsDraft.verboseMode,
        custom_system_prompt_append: sharedSettingsDraft.customSystemPromptAppend.trim(),
        memory_controls: {
          prompt_context_enabled: sharedSettingsDraft.memoryPromptContextEnabled,
          search_enabled: sharedSettingsDraft.memorySearchEnabled,
          write_enabled: sharedSettingsDraft.memoryWriteEnabled,
        },
      };
      const runtimeReady = Boolean(bootstrap?.apiBaseUrl && bootstrap?.accessToken);

      if (cloudAccountEnabled) {
        const nextProfile = applySharedSettingsDraftToProfile(remoteAuthStatus.profile as any, sharedSettingsDraft);
        const result = await updateDesktopRemoteAccountProfile(nextProfile);
        if (!result) {
          throw new Error('Desktop account profile controls are unavailable in this shell.');
        }
        const profile = result.profile && typeof result.profile === 'object' ? result.profile : nextProfile;
        setRemoteAuthStatus((current: any) => current ? { ...current, profile } : current);
        setSharedSettingsDraft(profileToSharedSettingsDraft(profile as any));
      } else if (!runtimeReady) {
        throw new Error('Start the local desktop runtime before saving local settings.');
      }

      const setupPayload = await saveDesktopSetup(
        { INTERRUPT_POLICY_DEFAULT: sharedSettingsDraft.interruptPolicy } as Partial<DesktopSetupValues>,
        { restartPolicy: 'never' },
      );
      if (!setupPayload) {
        throw new Error('Desktop setup controls are unavailable in this shell.');
      }
      applyBootstrap(setupPayload, { preserveLoadingState: true });

      const runtimeApiBaseUrl = setupPayload.apiBaseUrl || bootstrap?.apiBaseUrl;
      const runtimeAccessToken = setupPayload.accessToken || bootstrap?.accessToken;
      const runtimeSessionId = setupPayload.currentSessionId ?? bootstrap?.currentSessionId;
      if (runtimeApiBaseUrl && runtimeAccessToken) {
        const runtimeTasks = [
          configureAgent(
            runtimeApiBaseUrl,
            runtimeAccessToken,
            runtimePayload,
            runtimeSessionId,
          ),
          configureHeadlessRuntime(runtimeApiBaseUrl, runtimeAccessToken, {
            enabled: sharedSettingsDraft.sleepModeEnabled,
          }).then((next) => setOrchestratorStatus(next)),
        ];
        if (cloudAccountEnabled) {
          await Promise.all(runtimeTasks.map((task) => task.catch(() => null)));
        } else {
          await Promise.all(runtimeTasks);
        }
        if (maxTurns) {
          setSetupMaxTurns(maxTurns);
        }
      }
      if (standaloneMode) {
        setSharedSettingsDraft((current: any) => current ? { ...current, cloudChatBackupEnabled: false } : current);
      }
      setSharedSettingsStatus(standaloneMode ? 'Local settings saved on this computer.' : 'Shared settings saved.');
      return true;
    } catch (profileError) {
      setSharedSettingsStatus(userFacingError(profileError, standaloneMode ? 'Local settings were not saved.' : 'Shared settings were not saved.'));
      return false;
    } finally {
      setSharedSettingsSaving(false);
    }
  };

  const approveSharedConfirmation = async (confirmationId: string) => {
    if (!bootstrap?.apiBaseUrl || !bootstrap?.accessToken) return;
    setRecoveryBusyId(confirmationId);
    setRecoveryMessage('Approving confirmation…');
    try {
      await approvePendingConfirmation(bootstrap.apiBaseUrl, bootstrap.accessToken, confirmationId, 'desktop');
      await refreshRecovery();
      setRecoveryMessage('Confirmation approved.');
    } catch (error) {
      setRecoveryMessage(userFacingError(error, 'Approval did not finish.'));
    } finally {
      setRecoveryBusyId(null);
    }
  };

  const denySharedConfirmation = async (confirmationId: string) => {
    if (!bootstrap?.apiBaseUrl || !bootstrap?.accessToken) return;
    setRecoveryBusyId(confirmationId);
    setRecoveryMessage('Denying confirmation…');
    try {
      await denyPendingConfirmation(bootstrap.apiBaseUrl, bootstrap.accessToken, confirmationId, 'desktop');
      await refreshRecovery();
      setRecoveryMessage('Confirmation denied.');
    } catch (error) {
      setRecoveryMessage(userFacingError(error, 'Decision was not saved.'));
    } finally {
      setRecoveryBusyId(null);
    }
  };

  const restoreArchivedItem = async (archiveId: string) => {
    if (!bootstrap?.apiBaseUrl || !bootstrap?.accessToken) return;
    setRecoveryBusyId(archiveId);
    setRecoveryMessage('Restoring archived item…');
    try {
      await restoreRecoveryItem(bootstrap.apiBaseUrl, bootstrap.accessToken, archiveId);
      await refreshRecovery();
      setRecoveryMessage('Archived item restored.');
    } catch (restoreError) {
      setRecoveryMessage(userFacingError(restoreError, 'Archived item was not restored.'));
    } finally {
      setRecoveryBusyId(null);
    }
  };

  const permanentlyDeleteArchivedItem = async (archiveId: string) => {
    if (!bootstrap?.apiBaseUrl || !bootstrap?.accessToken) return;
    const confirmed = await confirmAction({
      title: 'Permanently delete this archived item?',
      message: 'This removes the recovery copy. You will not be able to restore it later.',
      confirmLabel: 'Delete Forever',
      tone: 'danger',
      details: ['Normal deletes are recoverable for 30 days.', 'Use this only when you intentionally want to remove the recovery copy.'],
    });
    if (!confirmed) return;
    setRecoveryBusyId(archiveId);
    setRecoveryMessage('Deleting archived item…');
    try {
      const confirmation = await createPendingConfirmation(bootstrap.apiBaseUrl, bootstrap.accessToken, {
        action_kind: 'recovery_permanent_delete',
        title: 'Permanently delete recovery item',
        message: 'This removes the archived recovery copy permanently.',
        risk_tier: 'danger',
        origin_surface: 'desktop',
        payload: { archive_id: archiveId },
        ttl_seconds: 300,
      });
      const approved = await approvePendingConfirmation(bootstrap.apiBaseUrl, bootstrap.accessToken, confirmation.confirmation_id, 'desktop');
      await permanentlyDeleteRecoveryItem(bootstrap.apiBaseUrl, bootstrap.accessToken, archiveId, approved.confirmation_id);
      await refreshRecovery();
      setRecoveryMessage('Archived item permanently deleted.');
    } catch (deleteError) {
      setRecoveryMessage(userFacingError(deleteError, 'Archived item was not deleted.'));
    } finally {
      setRecoveryBusyId(null);
    }
  };

  const restoreManagedWorkspace = async () => {
    if (!bootstrap?.apiBaseUrl || !bootstrap?.accessToken) return;
    setRecoveryBusyId('workspace_restore');
    setRecoveryMessage('Restoring cloud-known workspace files…');
    try {
      const response = await restoreWorkspaceFiles(bootstrap.apiBaseUrl, bootstrap.accessToken, {});
      setRecoveryMessage(response.restored_files.length ? 'Workspace files restored.' : 'No files to restore.');
    } catch (restoreError) {
      setRecoveryMessage(userFacingError(restoreError, 'Workspace files were not restored.'));
    } finally {
      setRecoveryBusyId(null);
    }
  };

  const deleteRemoteSecretFromCloud = async (namespace: string, name: string) => {
    if (!remoteAuthStatus?.signedIn) {
      setRemoteSecretsMessage('Sign in before deleting saved keys.');
      return;
    }
    if (!bootstrap?.apiBaseUrl || !bootstrap?.accessToken) {
      setRemoteSecretsMessage('App account session is not ready yet.');
      return;
    }
    const cleanNamespace = String(namespace || '').trim();
    const cleanName = String(name || '').trim();
    if (!cleanNamespace || !cleanName) {
      setRemoteSecretsMessage('Missing saved key name.');
      return;
    }
    const secretLabel = cleanNamespace === 'setup'
      ? (SETUP_PROVIDER_SECRET_LABELS[cleanName] || cleanName)
      : cleanName;
    const confirmationId = await createApprovedConfirmation(bootstrap.apiBaseUrl, bootstrap.accessToken, confirmAction, {
      action_kind: 'remote_secret_delete',
      title: `Remove saved ${secretLabel}?`,
      message: 'You can paste a replacement after it is removed.',
      risk_tier: 'danger',
      origin_surface: 'desktop',
      payload: { namespace: cleanNamespace, name: cleanName },
    }, {
      confirmLabel: 'Remove',
      tone: 'danger',
    });
    if (!confirmationId) {
      return;
    }
    setRemoteSecretsBusy(true);
    setRemoteSecretsMessage(`Deleting saved ${secretLabel}…`);
    try {
      await deleteDesktopRemoteSecret(cleanNamespace, cleanName, confirmationId);
      remoteAccountHydratedKeyRef.current = null;
      setRemoteSecretItems((items: any[]) => items.filter((item: any) => !(item.namespace === cleanNamespace && item.name === cleanName)));
      await refreshRemoteSecretItems();
      setRemoteSecretsMessage(`Deleted saved ${secretLabel}.`);
    } catch (deleteError) {
      setRemoteSecretsMessage(userFacingError(deleteError, 'Saved key was not deleted.'));
    } finally {
      setRemoteSecretsBusy(false);
    }
  };

  const removeLocalRuntimeSecret = async (name: keyof DesktopSetupValues) => {
    const cleanName = String(name || '').trim();
    if (!cleanName) {
      return;
    }
    const secretLabel = SETUP_PROVIDER_SECRET_LABELS[cleanName] || cleanName;
    const confirmed = await confirmAction({
      title: `Remove local ${secretLabel}?`,
      message: 'You can paste a replacement after it is removed.',
      confirmLabel: 'Remove',
      tone: 'danger',
    });
    if (!confirmed) {
      return;
    }

    const removalValues = { [cleanName]: '' } as Partial<DesktopSetupValues>;
    const runtimeWasRunning = Boolean(runtimeProcessDetected || localRuntimeReady);
    setSavingSetup(true);
    setError(null);
    setNotice(null);
    try {
      const payload = await saveDesktopSetup(removalValues, { restartPolicy: 'never' });
      if (!payload) {
        throw new Error('Desktop setup controls are unavailable in this shell.');
      }
      applyBootstrap(payload, { keepSetupClosed: true });

      const apiBaseUrl = payload.apiBaseUrl || bootstrap?.apiBaseUrl;
      const accessToken = payload.accessToken || bootstrap?.accessToken;
      if (runtimeWasRunning && apiBaseUrl && accessToken) {
        await reloadProviderKeys(apiBaseUrl, accessToken, removalValues as Record<string, string | undefined>);
      }

      const refreshed = await loadDesktopBootstrap({ force: true });
      if (refreshed) {
        applyBootstrap(refreshed, { keepSetupClosed: true });
      }
      setNotice(`${secretLabel} removed locally.`);
    } catch (removeError) {
      setError(userFacingError(removeError, `${secretLabel} was not removed.`));
    } finally {
      setSavingSetup(false);
    }
  };

  const createRemotePairingTokenFromAccount = async () => {
    const pairing = await createDesktopRemotePairingToken();
    if (!pairing) {
      throw new Error('Desktop remote account controls are unavailable in this shell.');
    }
    return pairing;
  };

  const refreshRemoteSecretItems = async () => {
    if (!remoteAuthStatus?.signedIn) {
      setRemoteSecretItems([]);
      return;
    }
    setRemoteSecretsBusy(true);
    setRemoteSecretsMessage(null);
    try {
      const results = await Promise.all([
        listDesktopRemoteSecrets('setup'),
        listDesktopRemoteSecrets('telegram_bots'),
        listDesktopRemoteSecrets('login_credentials'),
      ]);
      const items = results.flatMap((result) => result?.items || []);
      setRemoteSecretItems(items);
      setRemoteSecretsMessage(items.length ? 'Saved items refreshed.' : 'No saved access yet.');
    } catch (secretError) {
      setRemoteSecretsMessage(userFacingError(secretError, 'Saved access did not refresh.'));
    } finally {
      setRemoteSecretsBusy(false);
    }
  };

  const saveCurrentSetupSecretsToCloud = async (values: Partial<DesktopSetupValues>) => {
    if (!remoteAuthStatus?.signedIn) {
      setRemoteSecretsMessage('Sign in before saving setup values.');
      return;
    }
    setRemoteSecretsBusy(true);
    setRemoteSecretsMessage('Saving setup values…');
    try {
      const result = await saveDesktopSetupSecrets(values);
      const primaryTelegramToken = String(values.TELEGRAM_BOT_TOKEN || '').trim();
      const defaultBot = telegramBotConfigs.find((item: any) => item.is_default) || telegramBotConfigs[0] || null;
      if (primaryTelegramToken && defaultBot?.id) {
        await saveTelegramBotSecretToCloud(
          defaultBot.id,
          defaultBot.label || 'Telegram bot token',
          primaryTelegramToken,
          Boolean(defaultBot.is_default),
        );
      }
      await refreshRemoteSecretItems();
      setRemoteSecretsMessage(result?.items?.length ? 'Setup values saved.' : 'No filled key fields to save.');
    } catch (secretError) {
      setRemoteSecretsMessage(userFacingError(secretError, 'Setup values were not saved.'));
    } finally {
      setRemoteSecretsBusy(false);
    }
  };

  const saveLoginCredentialSecretsToCloud = async (payload: { email?: string; password?: string }) => {
    if (!remoteAuthStatus?.signedIn) {
      setRemoteSecretsMessage('Sign in before saving login credentials.');
      return;
    }
    const secrets: Record<string, string> = {};
    const email = String(payload.email || '').trim();
    const password = String(payload.password || '').trim();
    if (email) {
      secrets.GMAIL_EMAIL = email;
    }
    if (password) {
      secrets.GMAIL_PASSWORD = password;
    }
    if (!Object.keys(secrets).length) {
      setRemoteSecretsMessage('Enter a Gmail address or password before saving.');
      return;
    }
    setRemoteSecretsBusy(true);
    setRemoteSecretsMessage('Saving Gmail login…');
    try {
      await saveDesktopRemoteSecrets('login_credentials', secrets, {
        GMAIL_EMAIL: { label: 'Gmail address', kind: 'login_email', service: 'gmail' },
        GMAIL_PASSWORD: { label: 'Gmail password', kind: 'login_password', service: 'gmail' },
      });
      await refreshRemoteSecretItems();
      setRemoteSecretsMessage('Gmail login saved.');
    } catch (secretError) {
      setRemoteSecretsMessage(userFacingError(secretError, 'Gmail login was not saved.'));
    } finally {
      setRemoteSecretsBusy(false);
    }
  };

  const saveTelegramBotSecretToCloud = async (botConfigId: string, label: string, botToken: string, isDefault = false) => {
    if (!remoteAuthStatus?.signedIn) {
      return false;
    }
    const cleanId = String(botConfigId || '').trim();
    const cleanToken = String(botToken || '').trim();
    if (!cleanId || !cleanToken) {
      return false;
    }
    try {
      await saveDesktopRemoteSecrets('telegram_bots', { [cleanId]: cleanToken }, {
        [cleanId]: {
          label: label || 'Telegram bot token',
          kind: 'telegram_bot_token',
          bot_config_id: cleanId,
          is_default: Boolean(isDefault),
        },
      });
      return true;
    } catch (secretError) {
      setRemoteSecretsMessage('Telegram bot saved locally. Saved copy failed.');
      return false;
    }
  };

  const applyCloudSetupSecrets = async () => {
    if (!remoteAuthStatus?.signedIn) {
      setRemoteSecretsMessage('Sign in before filling saved setup values.');
      return;
    }
    const confirmed = await confirmAction({
      title: 'Fill this desktop with saved setup?',
      message: 'Saved setup values will be applied to this desktop. The agent may restart if key settings change.',
      confirmLabel: 'Fill Setup',
      tone: 'access',
    });
    if (!confirmed) {
      return;
    }
    setRemoteSecretsBusy(true);
    setRemoteSecretsMessage('Filling saved setup values…');
    try {
      const result = await applyDesktopAccountData();
      if (!result) {
        throw new Error('Saved setup controls are unavailable in this shell.');
      }
      if (result.bootstrap) {
        applyBootstrap(result.bootstrap, { keepSetupClosed: false });
      }
      setRemoteSecretsMessage(result.applied ? 'Saved setup filled.' : 'No saved setup found.');
      await refreshRemoteSecretItems();
    } catch (secretError) {
      setRemoteSecretsMessage(userFacingError(secretError, 'Saved setup was not applied.'));
    } finally {
      setRemoteSecretsBusy(false);
    }
  };

  const saveSetup = async (values: Partial<DesktopSetupValues>) => {
    const localValues = sanitizeLocalSetupValues(values);
    const runtimeSaveValues = setupValuesForRuntimeSave(values);
    const hasSecretValues = hasFilledSetupSecret(values);
    const hasLiveApplySecretValues = hasFilledLiveApplySetupSecret(values);
    const hasRestartRequiredSecretValues = hasFilledRestartRequiredSetupSecret(values);
    const baselineValues = bootstrap?.setupState?.values
      ? sanitizeLocalSetupValues(bootstrap.setupState.values)
      : bootstrap?.setupState?.values;
    const changedFields = changedSetupFields(localValues, baselineValues);
    const localValuesChanged = changedFields.length > 0;
    const hasRestartRequiredLocalChanges = !baselineValues
      ? localValuesChanged
      : changedFields.some((field) => RESTART_REQUIRED_SETUP_FIELDS.has(field) || !LIVE_APPLY_SETUP_FIELDS.has(field));
    const restartRequired = hasRestartRequiredSecretValues || hasRestartRequiredLocalChanges;
    const changed = localValuesChanged || hasSecretValues;
    if (!changed) {
      setError(null);
      setNotice(null);
      setShowSetup(false);
      if (startupPhaseRef.current !== 'ready') {
        try {
          const refreshed = await loadDesktopBootstrap({ force: true });
          if (refreshed) {
            applyBootstrap(refreshed, { keepSetupClosed: true });
            if (!refreshed.setupState?.required) {
              setNotice('Setup is complete. Continuing startup…');
              await beginStartup({ forceBootstrap: true });
            } else {
              setShowSetup(true);
              setStartupPhase('setup_required');
              setLoadingState('Setup required');
            }
          }
        } catch (setupRefreshError) {
          setShowSetup(true);
          setStartupPhase('setup_required');
          setLoadingState('Setup required');
          setError(userFacingError(setupRefreshError, 'Setup did not reload.'));
        }
      }
      return;
    }

    const runtimeWasRunning = Boolean(runtimeProcessDetected || localRuntimeReady);
    if (runtimeWasRunning && restartRequired) {
      const confirmed = await confirmAction({
        title: 'Restart the agent?',
        message: 'Saving these settings will restart the local agent on this computer.',
        confirmLabel: 'Save and Restart',
        tone: 'access',
      });
      if (!confirmed) {
        return;
      }
    }

    setSavingSetup(true);
    setError(null);
    setNotice(null);
    if (runtimeWasRunning && restartRequired) {
      setLoadingState('restarting local runtime');
    }
    try {
      const cloudSecretIssues: string[] = [];
      if (hasSecretValues && remoteAuthStatus?.signedIn) {
        try {
          const secretResult = await saveDesktopSetupSecrets(values);
          if (!secretResult) {
            throw new Error('Saved setup controls are unavailable in this shell.');
          }
          const primaryTelegramToken = String(values.TELEGRAM_BOT_TOKEN || '').trim();
          const defaultBot = telegramBotConfigs.find((item: any) => item.is_default) || telegramBotConfigs[0] || null;
          if (primaryTelegramToken && defaultBot?.id) {
            await saveTelegramBotSecretToCloud(
              defaultBot.id,
              defaultBot.label || 'Telegram bot token',
              primaryTelegramToken,
              Boolean(defaultBot.is_default),
            );
          }
          await refreshRemoteSecretItems().catch(() => null);
        } catch (secretError) {
          cloudSecretIssues.push('Saved access was not updated.');
          setRemoteSecretsMessage(userFacingError(secretError, 'Saved access was not updated.'));
        }
      }

      let finalPayload: DesktopBootstrap | null = null;
      if (localValuesChanged || hasSecretValues || restartRequired) {
        const payload = await saveDesktopSetup(
          (localValuesChanged || hasSecretValues) ? runtimeSaveValues : {},
          { restartPolicy: restartRequired ? 'auto' : 'never' },
        );
        if (!payload) {
          setError('Desktop setup controls are unavailable in this shell.');
          return;
        }
        finalPayload = payload;
      }

      const liveApplyIssues: string[] = [...cloudSecretIssues];
      if (!restartRequired && localValuesChanged && runtimeWasRunning && bootstrap?.apiBaseUrl && bootstrap?.accessToken) {
        const effectiveSetupValues = finalPayload?.setupState?.values || localValues;
        const agentPayload: { workspace?: string; planner_model?: string | null } = {};
        if (changedFields.includes('DEFAULT_WORKSPACE')) {
          agentPayload.workspace = String(effectiveSetupValues.DEFAULT_WORKSPACE || localValues.DEFAULT_WORKSPACE || '').trim();
        }
        if (changedFields.includes('PLANNER_MODEL')) {
          agentPayload.planner_model = String(effectiveSetupValues.PLANNER_MODEL || localValues.PLANNER_MODEL || '').trim() || null;
        }
        if (Object.keys(agentPayload).length) {
          try {
            await configureAgent(
              bootstrap.apiBaseUrl,
              bootstrap.accessToken,
              agentPayload,
              bootstrap.currentSessionId || undefined,
            );
          } catch (agentConfigError) {
            liveApplyIssues.push('Live agent defaults were not applied.');
          }
        }
        if (changedFields.includes('VOICE_DEFAULT_ENGINE')) {
          try {
            const voicePayload = await setDesktopVoiceDefaultEngine(String(effectiveSetupValues.VOICE_DEFAULT_ENGINE || localValues.VOICE_DEFAULT_ENGINE || 'none').trim() || 'none');
            if (voicePayload) {
              finalPayload = voicePayload;
            }
          } catch (voiceError) {
            liveApplyIssues.push('Voice path was not switched.');
          }
        }
      }
      if (!restartRequired && hasLiveApplySecretValues && runtimeWasRunning) {
        const apiBaseUrl = finalPayload?.apiBaseUrl || bootstrap?.apiBaseUrl;
        const accessToken = finalPayload?.accessToken || bootstrap?.accessToken;
        if (apiBaseUrl && accessToken) {
          try {
            await reloadProviderKeys(apiBaseUrl, accessToken, runtimeSaveValues as Record<string, string | undefined>);
            const refreshed = await loadDesktopBootstrap({ force: true });
            if (refreshed) {
              finalPayload = refreshed;
            }
          } catch (providerReloadError) {
            liveApplyIssues.push('Provider keys were saved for the next runtime start, but the running agent did not reload them.');
          }
        } else {
          liveApplyIssues.push('Provider keys were saved for the next runtime start, but the running agent did not reload them.');
        }
      }

      if (!finalPayload) {
        finalPayload = await loadDesktopBootstrap({ force: true });
      }
      if (!finalPayload) {
        setError('Desktop setup controls are unavailable in this shell.');
        return;
      }

      if (runtimeWasRunning && restartRequired && (!finalPayload.runtimeStatus?.ok || !finalPayload.accessToken)) {
        const deadline = Date.now() + DESKTOP_RUNTIME_RESTART_WAIT_MS;
        while (Date.now() < deadline) {
          await delay(600);
          const refreshed = await loadDesktopBootstrap({ force: true });
          if (refreshed) {
            finalPayload = refreshed;
          }
          const refreshedStatus = await loadDesktopRuntimeStatus().catch(() => null);
          if (refreshedStatus) {
            if (shouldPreserveReadyRuntimeStatus(refreshedStatus)) {
              scheduleReadyRuntimeDowngradeRecheck(refreshedStatus);
            } else {
              setRuntimeStatusWithRef(refreshedStatus);
            }
            if (finalPayload) {
              finalPayload = {
                ...finalPayload,
                runtimeStatus: refreshedStatus,
              };
            }
          }
          if (finalPayload?.accessToken && finalPayload.runtimeStatus?.ok) {
            break;
          }
        }
      }

      applyBootstrap(finalPayload, { keepSetupClosed: true });
      const reconnected = Boolean(finalPayload.accessToken && finalPayload.runtimeStatus?.ok);
      const shouldResumeStartup = startupPhaseRef.current !== 'ready' && !finalPayload.setupState?.required;
      if (shouldResumeStartup) {
        setNotice(hasSecretValues ? 'Settings and API keys saved. Continuing startup…' : 'Settings saved. Continuing startup…');
        await beginStartup({ forceBootstrap: true });
        return true;
      }
      const liveIssueSuffix = liveApplyIssues.length ? ` ${liveApplyIssues.join(' ')}` : '';
      if (runtimeWasRunning && restartRequired) {
        setNotice(
          reconnected
            ? (hasSecretValues ? 'Settings and API keys saved. Local runtime restarted and reconnected.' : 'Settings saved. Local runtime restarted and reconnected.')
            : (hasSecretValues ? 'Settings and API keys saved. Local runtime is still restarting.' : 'Settings saved. Local runtime is still restarting.')
        );
      } else if (runtimeWasRunning) {
        setNotice(
          hasSecretValues
            ? `Settings and API keys saved without restarting.${liveIssueSuffix}`
            : `Settings saved and applied without restarting.${liveIssueSuffix}`
        );
      } else {
        setNotice(
          reconnected
            ? (hasSecretValues ? 'Settings and API keys saved. Local runtime connected.' : 'Settings saved. Local runtime connected.')
            : (hasSecretValues ? 'Settings and API keys saved. Start the local runtime when ready.' : 'Settings saved. Start the local runtime when ready.')
        );
      }
      await refreshUpdateStatus(true);
      return true;
    } catch (saveError) {
      const detail = userFacingError(saveError, 'Settings were not saved.');
      setError(detail);
      if (startupPhaseRef.current !== 'ready') {
        setStartupPhase('setup_required');
        setLoadingState('Setup required');
      }
      return false;
    } finally {
      setSavingSetup(false);
    }
  };

  const refreshMemory = async () => {
    setMemoryLoading(true);
    try {
      const next = await loadDesktopMemory();
      if (next) {
        setMemoryState(next);
      }
    } catch (memoryError) {
      setError(userFacingError(memoryError, 'Memory did not load.'));
    } finally {
      setMemoryLoading(false);
    }
  };

  const saveMemory = async (content: string) => {
    setMemorySaving(true);
    setError(null);
    setNotice(null);
    try {
      const next = await saveDesktopMemory(content);
      if (!next) {
        setError('Desktop memory controls are unavailable in this shell.');
        return false;
      }
      setMemoryState(next);
      setNotice('Memory saved.');
      return true;
    } catch (memoryError) {
      setError(userFacingError(memoryError, 'Memory was not saved.'));
      return false;
    } finally {
      setMemorySaving(false);
    }
  };

  const installVoicePack = async (packId: string) => {
    const packLabel = desktopVoicePackLabel(packId);
    setVoicePackBusyId(packId);
    setVoicePackProgress({
      packId,
      state: 'starting',
      phase: 'prepare',
      message: `Preparing ${packLabel} voice pack install…`,
      percent: 0,
    });
    setError(null);
    setNotice(`Preparing ${packLabel} voice pack install…`);
    try {
      let payload = await installDesktopVoicePack(packId);
      if (!payload) {
        setError('Voice pack controls are unavailable in this shell.');
        return;
      }
      if (
        packId === 'hebrew_local'
        && payload.apiBaseUrl
        && payload.accessToken
        && payload.setupState?.voicePacks?.defaultEngine === 'hebrew_local'
      ) {
        setVoicePackProgress({
          packId,
          state: 'warming',
          phase: 'warmup',
          message: 'Warming Hebrew voice path so first capture is ready immediately…',
          percent: 96,
        });
        setNotice('Warming Hebrew voice path so first capture is ready immediately…');
        const warmedVoiceStatus = await warmVoiceRuntime(payload.apiBaseUrl, payload.accessToken);
        const warmupError = String(
          warmedVoiceStatus?.warmup?.['error']
          || warmedVoiceStatus?.issues?.[0]
          || '',
        ).trim();
        payload = {
          ...payload,
          setupState: payload.setupState
            ? {
                ...payload.setupState,
                voiceStatus: warmedVoiceStatus as any,
              }
            : payload.setupState,
        };
        if (warmupError) {
          throw new Error(warmupError);
        }
      }
      applyBootstrap(payload, { keepSetupClosed: false });
      setVoicePackProgress({
        packId,
        state: 'ready',
        phase: 'complete',
        message: `${packLabel} voice pack is ready.`,
        percent: 100,
      });
      setNotice(`${packLabel} voice pack is ready.`);
    } catch (installError) {
      const message = userFacingError(installError, 'Voice pack was not installed.');
      setError(message);
      setVoicePackProgress({
        packId,
        state: 'error',
        phase: 'error',
        message,
      });
    } finally {
      setVoicePackBusyId(null);
    }
  };

  const selectTtsVoicePack = async (pack: { id?: string; backend?: string | null; title?: string | null }) => {
    const packId = String(pack?.id || '').trim();
    const backend = String(pack?.backend || '').trim();
    const packLabel = String(pack?.title || desktopVoicePackLabel(packId)).trim() || 'voice pack';
    if (!packId || !backend) {
      setError('This voice pack does not declare a TTS backend.');
      return false;
    }
    if (!bootstrap?.apiBaseUrl || !bootstrap?.accessToken) {
      setError('Voice controls are unavailable until the local runtime is ready.');
      return false;
    }
    setVoicePackBusyId(packId);
    setVoicePackProgress(null);
    setError(null);
    setNotice(`Switching Jarvis voice to ${packLabel}…`);
    try {
      const nextStatus = await configureVoiceTtsBackend(bootstrap.apiBaseUrl, bootstrap.accessToken, backend);
      const switchError = nextStatus.tts_switch?.ok === false
        ? nextStatus.tts_switch.issues?.[0] || `${packLabel} is not ready.`
        : nextStatus.tts_ready === false
          ? nextStatus.tts_issues?.[0] || `${packLabel} is not ready.`
          : '';
      if (switchError) {
        throw new Error(switchError);
      }
      const selectedBackend = String(nextStatus.tts_backend || backend).trim();
      const nextVoicePacks = bootstrap.setupState?.voicePacks
        ? {
            ...bootstrap.setupState.voicePacks,
            packs: (bootstrap.setupState.voicePacks.packs || []).map((item: any) => {
              if (item?.kind !== 'tts') {
                return item;
              }
              const itemBackend = String(item.backend || '').trim();
              return {
                ...item,
                enabled: Boolean(itemBackend && itemBackend === selectedBackend),
                requested: item.id === packId ? true : item.requested,
              };
            }),
          }
        : bootstrap.setupState?.voicePacks;
      applyBootstrap(
        {
          ...bootstrap,
          setupState: bootstrap.setupState
            ? {
                ...bootstrap.setupState,
                voiceStatus: nextStatus as any,
                voicePacks: nextVoicePacks,
              }
            : bootstrap.setupState,
        },
        { keepSetupClosed: false, preserveLoadingState: true },
      );
      setNotice(`${packLabel} is active for Jarvis speech.`);
      return true;
    } catch (selectionError) {
      setError(userFacingError(selectionError, `${packLabel} was not enabled.`));
      return false;
    } finally {
      setVoicePackBusyId(null);
    }
  };

  const removeVoicePack = async (packId: string) => {
    const packLabel = desktopVoicePackLabel(packId);
    const confirmed = await confirmAction({
      title: `Remove ${packLabel} voice pack?`,
      message: 'Voice input for this pack will stop working until it is installed again.',
      confirmLabel: 'Remove',
      tone: 'danger',
      details: ['Installed packs can be downloaded again from Voice settings.', 'This only removes the local pack files for this app.'],
    });
    if (!confirmed) {
      return;
    }
    setVoicePackBusyId(packId);
    setVoicePackProgress(null);
    setError(null);
    setNotice(`Removing ${packLabel} voice pack…`);
    try {
      const payload = await removeDesktopVoicePack(packId);
      if (!payload) {
        setError('Voice pack controls are unavailable in this shell.');
        return;
      }
      applyBootstrap(payload, { keepSetupClosed: false });
      setNotice(`${packLabel} voice pack removed.`);
    } catch (removeError) {
      setError(userFacingError(removeError, 'Voice pack was not removed.'));
    } finally {
      setVoicePackBusyId(null);
    }
  };

  const selectVoiceEngine = async (engine: string) => {
    setError(null);
    setNotice(`Switching voice path to ${engine === 'hebrew_local' ? 'Hebrew' : engine === 'english_local' ? 'English' : 'off'}…`);
    try {
      const payload = await setDesktopVoiceDefaultEngine(engine);
      if (!payload) {
        setError('Voice engine controls are unavailable in this shell.');
        return false;
      }
      applyBootstrap(payload, { keepSetupClosed: false });
      setNotice(
        engine === 'hebrew_local'
          ? 'Voice path switched to Hebrew.'
          : engine === 'english_local'
            ? 'Voice path switched to English.'
            : 'Voice input turned off.'
      );
      return true;
    } catch (selectionError) {
      setError(userFacingError(selectionError, 'Voice path was not switched.'));
      return false;
    }
  };

  const installUpdateNow = async () => {
    setInstallingUpdate(true);
    setError(null);
    setNotice(
      updateStatus?.dirty
        ? `Backing up ${updateStatus.dirtyCount || 'local'} project changes before updating…`
        : 'Preparing desktop update…'
    );
    try {
      if (bootstrap?.apiBaseUrl && bootstrap?.accessToken) {
        setNotice('Stopping local agent work before updating…');
        try {
          await controlAgentRun(
            bootstrap.apiBaseUrl,
            bootstrap.accessToken,
            'stop',
            bootstrap.currentSessionId || undefined
          );
        } catch (stopError) {
          const stopMessage = describeError(stopError);
          if (!/no active run|no task is currently running|session not found|not found/i.test(stopMessage)) {
            throw new Error(`Could not stop local agent work before updating: ${stopMessage}`);
          }
        }
      }
      setNotice(
        updateStatus?.dirty
          ? 'Local project changes are being preserved. EmploAI will close and reopen on the new commit.'
          : 'Pulling the desktop update. EmploAI will close and reopen when the new commit is ready.'
      );
      const result = await installDesktopUpdate();
      if (result && result.message && !result.launched) {
        if (result.ok) {
          setNotice(result.message);
        } else {
          setError(userFacingError(result.message, 'Desktop update did not start.'));
        }
      }
    } catch (installError) {
      setError(userFacingError(installError, 'Desktop update did not start.'));
    } finally {
      setInstallingUpdate(false);
    }
  };

  const createSetupTelegramBot = async (payload: { label: string; bot_token: string }) => {
    if (!bootstrap?.apiBaseUrl || !bootstrap?.accessToken) {
      setError('Runtime API is not ready yet.');
      return;
    }
    try {
      const created = await createTelegramBotConfig(bootstrap.apiBaseUrl, bootstrap.accessToken, payload);
      const mirroredToVault = await saveTelegramBotSecretToCloud(created.id, created.label || payload.label, payload.bot_token, Boolean(created.is_default));
      await refreshSetupRuntimeControls();
      setNotice(`Telegram bot "${payload.label}" added.`);
      if (remoteAuthStatus?.signedIn && mirroredToVault) {
        await refreshRemoteSecretItems();
      }
    } catch (createError) {
      setError(userFacingError(createError, 'Telegram bot was not added.'));
    }
  };

  const updateSetupTelegramBot = async (
    botConfigId: string,
    payload: { label?: string; bot_token?: string; is_default?: boolean },
  ) => {
    if (!bootstrap?.apiBaseUrl || !bootstrap?.accessToken) {
      setError('Runtime API is not ready yet.');
      return;
    }
    try {
      const updated = await updateTelegramBotConfig(bootstrap.apiBaseUrl, bootstrap.accessToken, botConfigId, payload);
      let mirroredToVault = false;
      if (payload.bot_token) {
        mirroredToVault = await saveTelegramBotSecretToCloud(updated.id, updated.label || payload.label || 'Telegram bot token', payload.bot_token, Boolean(updated.is_default));
      }
      await refreshSetupRuntimeControls();
      setNotice('Telegram bot settings updated.');
      if (remoteAuthStatus?.signedIn && mirroredToVault) {
        await refreshRemoteSecretItems();
      }
    } catch (updateError) {
      setError(userFacingError(updateError, 'Telegram bot was not updated.'));
    }
  };

  const deleteSetupTelegramBot = async (botConfigId: string) => {
    if (!bootstrap?.apiBaseUrl || !bootstrap?.accessToken) {
      setError('Runtime API is not ready yet.');
      return;
    }
    const bot = telegramBotConfigs.find((item: any) => item.id === botConfigId);
    const label = bot?.label || 'this Telegram bot';
    const confirmed = await confirmAction({
      title: `Remove ${label}?`,
      message: 'Messages sent to this bot will stop syncing with EmploAI after it is removed.',
      confirmLabel: 'Remove Bot',
      tone: 'danger',
      details: ['The saved bot token will also be removed from this account where possible.', 'You can add the bot again later from Telegram settings.'],
    });
    if (!confirmed) {
      return;
    }
    try {
      await deleteTelegramBotConfig(bootstrap.apiBaseUrl, bootstrap.accessToken, botConfigId);
      let cloudCleanupError: string | null = null;
      const remainingBots = await fetchTelegramBotConfigs(bootstrap.apiBaseUrl, bootstrap.accessToken).catch(() => []);
      if (remoteAuthStatus?.signedIn) {
        try {
          const botSecretConfirmation = await createPendingConfirmation(bootstrap.apiBaseUrl, bootstrap.accessToken, {
            action_kind: 'remote_secret_delete',
            title: `Remove saved ${label} token?`,
            message: 'The saved Telegram bot token will be removed from this account.',
            risk_tier: 'danger',
            origin_surface: 'desktop',
            payload: { namespace: 'telegram_bots', name: botConfigId },
          });
          const approvedBotSecret = await approvePendingConfirmation(bootstrap.apiBaseUrl, bootstrap.accessToken, botSecretConfirmation.confirmation_id, 'desktop');
          await deleteDesktopRemoteSecret('telegram_bots', botConfigId, approvedBotSecret.confirmation_id);
          if (!remainingBots.length) {
            const setupTokenConfirmation = await createPendingConfirmation(bootstrap.apiBaseUrl, bootstrap.accessToken, {
              action_kind: 'remote_secret_delete',
              title: 'Remove saved Telegram setup token?',
              message: 'No Telegram bots remain, so the legacy setup token will also be removed.',
              risk_tier: 'danger',
              origin_surface: 'desktop',
              payload: { namespace: 'setup', name: 'TELEGRAM_BOT_TOKEN' },
            });
            const approvedSetupToken = await approvePendingConfirmation(bootstrap.apiBaseUrl, bootstrap.accessToken, setupTokenConfirmation.confirmation_id, 'desktop');
            await deleteDesktopRemoteSecret('setup', 'TELEGRAM_BOT_TOKEN', approvedSetupToken.confirmation_id).catch(() => null);
          }
        } catch (secretError) {
          cloudCleanupError = 'Saved bot token was not removed.';
        }
      }
      await refreshSetupRuntimeControls();
      if (remoteAuthStatus?.signedIn) {
        await refreshRemoteSecretItems();
      }
      if (cloudCleanupError) {
        setRemoteSecretsMessage('Telegram bot removed locally. Saved copy was not removed.');
      }
      setNotice('Telegram bot removed.');
    } catch (deleteError) {
      setError(userFacingError(deleteError, 'Telegram bot was not removed.'));
    }
  };

  const configureRuntimeOrchestratorFromSetup = async (
    payload: { enabled?: boolean; default_max_concurrent_chats?: number | null },
  ) => {
    if (!bootstrap?.apiBaseUrl || !bootstrap?.accessToken) {
      setError('Runtime API is not ready yet.');
      return;
    }
    try {
      const next = await configureHeadlessRuntime(bootstrap.apiBaseUrl, bootstrap.accessToken, {
        enabled: payload.enabled,
        default_max_concurrent_chats: payload.default_max_concurrent_chats ?? undefined,
      });
      setOrchestratorStatus(next);
      if (payload.enabled === true) {
        setNotice('Sleep mode enabled. Desktop UI is hiding; use Telegram or local automations to continue.');
        try {
          await hideDesktopWindowForSleepMode();
        } catch (hideError) {
          setError('Sleep mode enabled. Desktop UI did not hide.');
        }
        return;
      }
      setNotice(payload.enabled === false ? 'Sleep mode disabled.' : 'Runtime concurrency settings updated.');
    } catch (runtimeError) {
      setError(userFacingError(runtimeError, 'Sleep mode settings were not saved.'));
    }
  };

  const updateSetupGeneralAgentConfig = async (
    payload: { max_turns?: number },
  ) => {
    if (!bootstrap?.apiBaseUrl || !bootstrap?.accessToken) {
      setError('Runtime API is not ready yet.');
      return;
    }
    try {
      await configureAgent(
        bootstrap.apiBaseUrl,
        bootstrap.accessToken,
        { max_turns: payload.max_turns },
        bootstrap.currentSessionId || undefined,
      );
      if (typeof payload.max_turns === 'number') {
        setSetupMaxTurns(payload.max_turns);
        setNotice(`Max turns updated to ${payload.max_turns}.`);
      }
    } catch (agentConfigError) {
      setError(userFacingError(agentConfigError, 'Agent settings were not saved.'));
    }
  };

  return {
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
    selectTtsVoicePack,
    removeVoicePack,
    selectVoiceEngine,
    installUpdateNow,
    createSetupTelegramBot,
    updateSetupTelegramBot,
    deleteSetupTelegramBot,
    configureRuntimeOrchestratorFromSetup,
    updateSetupGeneralAgentConfig,
  };
}
