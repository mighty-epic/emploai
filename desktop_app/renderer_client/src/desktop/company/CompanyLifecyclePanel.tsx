import { useEffect, useMemo, useState } from 'react';
import { Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  completeCompanyMigration,
  deleteCompany,
  exportCompanyBackup,
  fetchCompanyDeletionPreview,
  fetchCompanyMigrationPreview,
  type CompanyDeletionPreview,
  type CompanyDetail,
  type CompanyMigrationPreview,
} from '@/lib/appApi';
import { rememberActiveCompanyId } from '@/lib/activeCompanyContext';
import {
  createApprovedConfirmation,
  type LocalConfirm,
} from '@/lib/sharedConfirmations';
import { userFacingError } from '../../../lib/diagnostics';


type Props = {
  apiBaseUrl: string;
  token: string;
  companyId: string;
  company: CompanyDetail | null;
  companyName: string;
  confirmAction: LocalConfirm;
  onChanged: () => Promise<void>;
};


function downloadBackup(companyName: string, backup: Record<string, unknown>) {
  if (Platform.OS !== 'web' || typeof document === 'undefined') return;
  const safeName = companyName
    .replace(/[^a-z0-9_-]+/gi, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase() || 'company';
  const blob = new Blob([JSON.stringify(backup, null, 2)], {
    type: 'application/json',
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${safeName}-${String(backup.backup_id || 'backup')}.emploai-company-backup.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}


export function CompanyLifecyclePanel({
  apiBaseUrl,
  token,
  companyId,
  company,
  companyName,
  confirmAction,
  onChanged,
}: Props) {
  const [backupOpen, setBackupOpen] = useState(false);
  const [migrationOpen, setMigrationOpen] = useState(false);
  const [deletionOpen, setDeletionOpen] = useState(false);
  const [backupPassphrase, setBackupPassphrase] = useState('');
  const [backupConfirmation, setBackupConfirmation] = useState('');
  const [recoveryKey, setRecoveryKey] = useState<string | null>(null);
  const [migrationPreview, setMigrationPreview] = useState<CompanyMigrationPreview | null>(null);
  const [deletionPreview, setDeletionPreview] = useState<CompanyDeletionPreview | null>(null);
  const [deletePhrase, setDeletePhrase] = useState('');
  const [useFinalBackup, setUseFinalBackup] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessionBackupId, setSessionBackupId] = useState('');

  const migrationState = String(company?.migration?.state || 'legacy_compatibility');
  const backupHistory = company?.backup_history || [];
  const latestStoredBackupId = String(
    backupHistory[backupHistory.length - 1]?.backup_id || '',
  );
  const verifiedBackupId = sessionBackupId || latestStoredBackupId;
  const backupReady = (
    backupPassphrase.length >= 12
    && backupPassphrase === backupConfirmation
  );

  useEffect(() => {
    setMigrationPreview(null);
    setDeletionPreview(null);
    setDeletePhrase('');
    setSessionBackupId('');
    setRecoveryKey(null);
    setError(null);
  }, [companyId]);

  const openMigration = async () => {
    const nextOpen = !migrationOpen;
    setMigrationOpen(nextOpen);
    setDeletionOpen(false);
    setError(null);
    if (!nextOpen || migrationPreview) return;
    setBusy('migration-preview');
    try {
      setMigrationPreview(
        await fetchCompanyMigrationPreview(apiBaseUrl, token, companyId),
      );
    } catch (reason) {
      setError(userFacingError(reason, 'The migration preview could not be loaded.'));
    } finally {
      setBusy(null);
    }
  };

  const openDeletion = async () => {
    const nextOpen = !deletionOpen;
    setDeletionOpen(nextOpen);
    setMigrationOpen(false);
    setError(null);
    if (!nextOpen || deletionPreview) return;
    setBusy('deletion-preview');
    try {
      setDeletionPreview(
        await fetchCompanyDeletionPreview(apiBaseUrl, token, companyId),
      );
    } catch (reason) {
      setError(userFacingError(reason, 'The deletion impact preview could not be loaded.'));
    } finally {
      setBusy(null);
    }
  };

  const exportBackup = async () => {
    if (!backupReady || busy) return;
    setBusy('backup');
    setError(null);
    try {
      const result = await exportCompanyBackup(
        apiBaseUrl,
        token,
        companyId,
        backupPassphrase,
      );
      downloadBackup(companyName, result.backup);
      setSessionBackupId(String(result.backup.backup_id || ''));
      setRecoveryKey(result.recovery_key);
      setBackupPassphrase('');
      setBackupConfirmation('');
      await onChanged();
      if (migrationOpen) {
        setMigrationPreview(
          await fetchCompanyMigrationPreview(apiBaseUrl, token, companyId),
        );
      }
      if (deletionOpen) {
        setDeletionPreview(
          await fetchCompanyDeletionPreview(apiBaseUrl, token, companyId),
        );
      }
    } catch (reason) {
      setError(userFacingError(reason, 'The encrypted company backup could not be exported.'));
    } finally {
      setBusy(null);
    }
  };

  const finishMigration = async () => {
    if (!verifiedBackupId || busy) return;
    setBusy('migration');
    setError(null);
    try {
      await completeCompanyMigration(
        apiBaseUrl,
        token,
        companyId,
        verifiedBackupId,
      );
      setMigrationOpen(false);
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, 'The legacy migration could not be completed.'));
    } finally {
      setBusy(null);
    }
  };

  const deleteRootCompany = async () => {
    if (
      !deletionPreview
      || deletePhrase !== deletionPreview.confirmation_text
      || busy
    ) return;
    const confirmationId = await createApprovedConfirmation(
      apiBaseUrl,
      token,
      confirmAction,
      {
        action_kind: 'company_delete',
        title: `Delete ${deletionPreview.company_name}?`,
        message: (
          'This permanently removes the Company from its fixed root, revokes every membership, '
          + 'and cancels its active Company work. A portable backup cannot be activated elsewhere in version one.'
        ),
        risk_tier: 'danger',
        origin_surface: 'desktop_company_governance',
        payload: {
          company_id: companyId,
          active_assignments: deletionPreview.active_assignment_count,
          active_objectives: deletionPreview.active_objective_count,
          memberships: deletionPreview.membership_count,
        },
      },
      {
        confirmLabel: 'Delete Company',
        tone: 'danger',
        details: [
          `${deletionPreview.active_assignment_count} active assignment(s) and ${deletionPreview.active_objective_count} active objective(s) will be cancelled.`,
          `${deletionPreview.membership_count} computer membership(s) will be revoked.`,
          useFinalBackup && verifiedBackupId
            ? `Verified backup ${verifiedBackupId} will be recorded as the final backup.`
            : 'No final backup is attached to this deletion.',
        ],
      },
    );
    if (!confirmationId) return;

    setBusy('delete');
    setError(null);
    try {
      await deleteCompany(
        apiBaseUrl,
        token,
        companyId,
        {
          company_name_confirmation: deletePhrase,
          active_work_action: 'cancel',
          final_backup_id: useFinalBackup && verifiedBackupId
            ? verifiedBackupId
            : null,
        },
        confirmationId,
      );
      rememberActiveCompanyId(null);
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        window.location.reload();
        return;
      }
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, 'The Company was not deleted.'));
    } finally {
      setBusy(null);
    }
  };

  const migrationCounts = useMemo(
    () => Object.entries(migrationPreview?.counts || {}),
    [migrationPreview],
  );

  return (
    <View style={styles.section}>
      <View style={styles.row}>
        <View style={styles.copy}>
          <Text style={styles.title}>Encrypted company backup</Text>
          <Text style={styles.meta}>
            Verified portable safekeeping. Secrets, pairing keys, and absolute workspace paths are excluded.
          </Text>
        </View>
        <Pressable
          accessibilityRole="button"
          style={styles.secondaryAction}
          onPress={() => {
            setBackupOpen((value) => !value);
            setRecoveryKey(null);
            setError(null);
          }}
        >
          <Text style={styles.secondaryActionText}>{backupOpen ? 'Close' : 'Export'}</Text>
        </Pressable>
      </View>

      {backupOpen ? (
        <View style={styles.editor}>
          <TextInput
            accessibilityLabel="Backup passphrase"
            secureTextEntry
            style={styles.input}
            value={backupPassphrase}
            placeholder="Create a passphrase of at least 12 characters"
            placeholderTextColor="#60768b"
            onChangeText={setBackupPassphrase}
          />
          <TextInput
            accessibilityLabel="Confirm backup passphrase"
            secureTextEntry
            style={styles.input}
            value={backupConfirmation}
            placeholder="Confirm the passphrase"
            placeholderTextColor="#60768b"
            onChangeText={setBackupConfirmation}
          />
          {backupConfirmation && backupPassphrase !== backupConfirmation ? (
            <Text style={styles.error}>The passphrases do not match.</Text>
          ) : null}
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: !backupReady || Boolean(busy) }}
            disabled={!backupReady || Boolean(busy)}
            style={[styles.primaryAction, !backupReady || busy ? styles.disabled : null]}
            onPress={() => void exportBackup()}
          >
            <Text style={styles.primaryActionText}>
              {busy === 'backup' ? 'Encrypting…' : 'Download verified backup'}
            </Text>
          </Pressable>
          {recoveryKey ? (
            <View style={styles.recovery}>
              <Text style={styles.recoveryTitle}>Save this separate recovery key now</Text>
              <Text selectable style={styles.recoveryKey}>{recoveryKey}</Text>
              <Text style={styles.meta}>It is shown only for this export and is never stored in Company data.</Text>
            </View>
          ) : null}
        </View>
      ) : null}

      <View style={styles.divider} />
      <View style={styles.row}>
        <View style={styles.copy}>
          <Text style={styles.title}>Legacy data migration</Text>
          <Text style={styles.meta}>
            {migrationState === 'completed'
              ? 'Mapped into this Company with a verified backup and audit report.'
              : 'Compatibility remains temporary until you review the mapping and preserve a verified backup.'}
          </Text>
        </View>
        {migrationState !== 'completed' ? (
          <Pressable accessibilityRole="button" style={styles.secondaryAction} onPress={() => void openMigration()}>
            <Text style={styles.secondaryActionText}>{migrationOpen ? 'Close' : 'Review'}</Text>
          </Pressable>
        ) : (
          <Text style={styles.success}>COMPLETE</Text>
        )}
      </View>

      {migrationOpen ? (
        <View style={styles.editor}>
          {busy === 'migration-preview' ? <Text style={styles.meta}>Building mapping report…</Text> : null}
          {migrationPreview ? (
            <>
              <View style={styles.counts}>
                {migrationCounts.map(([label, value]) => (
                  <View key={label} style={styles.count}>
                    <Text style={styles.countValue}>{value}</Text>
                    <Text style={styles.countLabel}>{label.replace(/_/g, ' ')}</Text>
                  </View>
                ))}
              </View>
              {Object.entries(migrationPreview.mappings).map(([source, destination]) => (
                <Text key={source} style={styles.mapping}>
                  {source.replace(/_/g, ' ')} → {destination}
                </Text>
              ))}
              {migrationPreview.warnings.map((warning) => (
                <Text key={warning} style={styles.warning}>• {warning}</Text>
              ))}
              <Text style={styles.meta}>{migrationPreview.recovery_note}</Text>
              <Pressable
                accessibilityRole="button"
                accessibilityState={{ disabled: !verifiedBackupId || Boolean(busy) }}
                disabled={!verifiedBackupId || Boolean(busy)}
                style={[styles.primaryAction, !verifiedBackupId || busy ? styles.disabled : null]}
                onPress={() => void finishMigration()}
              >
                <Text style={styles.primaryActionText}>
                  {busy === 'migration'
                    ? 'Completing…'
                    : verifiedBackupId
                      ? 'Confirm mapping and complete migration'
                      : 'Export a verified backup first'}
                </Text>
              </Pressable>
            </>
          ) : null}
        </View>
      ) : null}

      <View style={styles.divider} />
      <View style={styles.row}>
        <View style={styles.copy}>
          <Text style={styles.dangerTitle}>Delete this Company</Text>
          <Text style={styles.meta}>
            Root-only. Review active work and memberships before permanent removal.
          </Text>
        </View>
        <Pressable accessibilityRole="button" style={styles.dangerAction} onPress={() => void openDeletion()}>
          <Text style={styles.dangerActionText}>{deletionOpen ? 'Close' : 'Review deletion'}</Text>
        </Pressable>
      </View>

      {deletionOpen ? (
        <View style={styles.dangerEditor}>
          {busy === 'deletion-preview' ? <Text style={styles.meta}>Calculating impact…</Text> : null}
          {deletionPreview ? (
            <>
              <View style={styles.counts}>
                <View style={styles.count}>
                  <Text style={styles.countValue}>{deletionPreview.active_objective_count}</Text>
                  <Text style={styles.countLabel}>active objectives</Text>
                </View>
                <View style={styles.count}>
                  <Text style={styles.countValue}>{deletionPreview.active_assignment_count}</Text>
                  <Text style={styles.countLabel}>active assignments</Text>
                </View>
                <View style={styles.count}>
                  <Text style={styles.countValue}>{deletionPreview.membership_count}</Text>
                  <Text style={styles.countLabel}>memberships revoked</Text>
                </View>
              </View>
              <Text style={styles.warning}>{deletionPreview.version_one_result}</Text>
              {verifiedBackupId ? (
                <Pressable
                  accessibilityRole="checkbox"
                  accessibilityState={{ checked: useFinalBackup }}
                  style={styles.checkRow}
                  onPress={() => setUseFinalBackup((value) => !value)}
                >
                  <Text style={styles.checkMark}>{useFinalBackup ? '✓' : ''}</Text>
                  <Text style={styles.checkText}>
                    Record {verifiedBackupId} as the final verified backup
                  </Text>
                </Pressable>
              ) : (
                <Text style={styles.warning}>
                  No verified backup is available. You may export one above before continuing.
                </Text>
              )}
              <Text style={styles.meta}>
                Type <Text style={styles.exactText}>{deletionPreview.confirmation_text}</Text> exactly.
              </Text>
              <TextInput
                accessibilityLabel="Exact Company name confirmation"
                style={styles.input}
                value={deletePhrase}
                placeholder={deletionPreview.confirmation_text}
                placeholderTextColor="#60768b"
                onChangeText={setDeletePhrase}
              />
              <Pressable
                accessibilityRole="button"
                accessibilityState={{
                  disabled: deletePhrase !== deletionPreview.confirmation_text || Boolean(busy),
                }}
                disabled={
                  deletePhrase !== deletionPreview.confirmation_text
                  || Boolean(busy)
                }
                style={[
                  styles.deleteAction,
                  deletePhrase !== deletionPreview.confirmation_text || busy
                    ? styles.disabled
                    : null,
                ]}
                onPress={() => void deleteRootCompany()}
              >
                <Text style={styles.deleteActionText}>
                  {busy === 'delete' ? 'Deleting…' : 'Delete Company…'}
                </Text>
              </Pressable>
            </>
          ) : null}
        </View>
      ) : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}


const styles = StyleSheet.create({
  section: { borderTopWidth: 1, borderTopColor: '#1b2a39', paddingTop: 12, marginTop: 2, gap: 8 },
  row: { minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: 12 },
  copy: { flex: 1, minWidth: 0 },
  title: { color: '#e1ebf3', fontSize: 11, fontWeight: '700' },
  dangerTitle: { color: '#f2b0b5', fontSize: 11, fontWeight: '800' },
  meta: { color: '#71879a', fontSize: 9, lineHeight: 14, marginTop: 3 },
  exactText: { color: '#f0c2c5', fontWeight: '800' },
  divider: { height: 1, backgroundColor: '#182837' },
  editor: { padding: 12, borderRadius: 9, backgroundColor: '#0c1721', gap: 8 },
  dangerEditor: { padding: 12, borderRadius: 9, backgroundColor: '#21151a', gap: 8 },
  input: { minHeight: 38, borderRadius: 7, backgroundColor: '#101f2b', color: '#e2edf5', paddingHorizontal: 11, paddingVertical: 8, fontSize: 11, outlineStyle: 'none' } as any,
  primaryAction: { alignSelf: 'flex-start', paddingHorizontal: 14, paddingVertical: 9, borderRadius: 7, backgroundColor: '#70d7e5' },
  primaryActionText: { color: '#061219', fontSize: 10, fontWeight: '900' },
  secondaryAction: { paddingHorizontal: 11, paddingVertical: 7, borderRadius: 7, backgroundColor: '#132732' },
  secondaryActionText: { color: '#73d9e6', fontSize: 9, fontWeight: '800' },
  dangerAction: { paddingHorizontal: 11, paddingVertical: 7, borderRadius: 7, backgroundColor: '#2c1a20' },
  dangerActionText: { color: '#f0a8ae', fontSize: 9, fontWeight: '800' },
  deleteAction: { alignSelf: 'flex-start', paddingHorizontal: 14, paddingVertical: 10, borderRadius: 7, backgroundColor: '#aa3948' },
  deleteActionText: { color: '#fff4f5', fontSize: 10, fontWeight: '900' },
  disabled: { opacity: 0.45 },
  error: { color: '#f0a0a6', fontSize: 10, lineHeight: 14 },
  warning: { color: '#d8a26d', fontSize: 9, lineHeight: 14 },
  success: { color: '#61d3a0', fontSize: 8, fontWeight: '900' },
  recovery: { padding: 11, borderRadius: 8, backgroundColor: '#16251f', gap: 5 },
  recoveryTitle: { color: '#8ee0b9', fontSize: 10, fontWeight: '800' },
  recoveryKey: { color: '#e5f4eb', fontSize: 11, lineHeight: 16, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined },
  counts: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  count: { minWidth: 108, padding: 8, borderRadius: 7, backgroundColor: '#101f2b' },
  countValue: { color: '#e6f0f6', fontSize: 12, fontWeight: '800' },
  countLabel: { color: '#70869a', fontSize: 8, marginTop: 2, textTransform: 'capitalize' },
  mapping: { color: '#8fa4b6', fontSize: 9, lineHeight: 14, textTransform: 'capitalize' },
  checkRow: { minHeight: 38, flexDirection: 'row', alignItems: 'center', gap: 8 },
  checkMark: { width: 16, height: 16, borderRadius: 4, backgroundColor: '#19343d', color: '#70dbe6', fontSize: 10, fontWeight: '900', textAlign: 'center', lineHeight: 16 },
  checkText: { flex: 1, color: '#9aabb9', fontSize: 9 },
});
