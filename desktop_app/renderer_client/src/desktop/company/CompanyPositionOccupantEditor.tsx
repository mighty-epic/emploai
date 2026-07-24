import { useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  changeCompanyPositionOccupant,
  fetchCompanyEligibleIdentities,
  type CompanyEmployee,
  type CompanyPosition,
} from '@/lib/appApi';
import type { DesktopFleetIdentity } from '@/lib/desktopBridge';
import type { LocalConfirm } from '@/lib/sharedConfirmations';
import { userFacingError } from '../../../lib/diagnostics';


type Props = {
  apiBaseUrl: string;
  token: string;
  companyId: string;
  position: CompanyPosition;
  currentEmployee: CompanyEmployee | null;
  employees: CompanyEmployee[];
  positions: CompanyPosition[];
  confirmAction: LocalConfirm;
  onClose: () => void;
  onChanged: () => Promise<void>;
};


export function CompanyPositionOccupantEditor({
  apiBaseUrl,
  token,
  companyId,
  position,
  currentEmployee,
  employees,
  positions,
  confirmAction,
  onClose,
  onChanged,
}: Props) {
  const [eligible, setEligible] = useState<DesktopFleetIdentity[]>([]);
  const [selectedIdentityId, setSelectedIdentityId] = useState<string | null>(
    currentEmployee?.identity_id || null,
  );
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    setLoading(true);
    void fetchCompanyEligibleIdentities(apiBaseUrl, token, companyId)
      .then((payload) => {
        if (!disposed) setEligible(payload.items);
      })
      .catch((reasonValue) => {
        if (!disposed) {
          setError(userFacingError(reasonValue, 'Eligible Company identities could not be loaded.'));
        }
      })
      .finally(() => {
        if (!disposed) setLoading(false);
      });
    return () => {
      disposed = true;
    };
  }, [apiBaseUrl, companyId, token]);

  const selectedEmployee = employees.find(
    (item) => item.identity_id === selectedIdentityId,
  );
  const sourcePosition = positions.find(
    (item) => (
      item.position_id !== position.position_id
      && item.occupant_identity_id === selectedIdentityId
      && !['archived', 'closed'].includes(item.status)
    ),
  );
  const identityById = useMemo(
    () => new Map(eligible.map((item) => [item.identity_id, item])),
    [eligible],
  );
  const choices = useMemo(() => {
    const all = new Map<string, { identity_id: string; display_name: string; role: string }>();
    eligible.forEach((identity) => all.set(identity.identity_id, {
      identity_id: identity.identity_id,
      display_name: identity.display_name,
      role: identity.role,
    }));
    employees.forEach((employee) => all.set(employee.identity_id, {
      identity_id: employee.identity_id,
      display_name: employee.display_name,
      role: employee.system_role,
    }));
    return [...all.values()].sort((left, right) => (
      left.display_name.localeCompare(right.display_name)
    ));
  }, [eligible, employees]);

  const submit = async () => {
    if (!reason.trim() || saving) return;
    const nextIdentity = selectedIdentityId
      ? identityById.get(selectedIdentityId)
        || {
          display_name: selectedEmployee?.display_name || 'Selected employee',
          role: selectedEmployee?.system_role || 'worker',
        }
      : null;
    const confirmed = await confirmAction({
      title: selectedIdentityId ? `Change occupant of ${position.title}?` : `Vacate ${position.title}?`,
      message: selectedIdentityId
        ? `${nextIdentity?.display_name || 'The selected identity'} will receive this position's job contract and must pass readiness again.`
        : 'The current employee remains in the Company but this position becomes open.',
      confirmLabel: selectedIdentityId ? 'Change occupant' : 'Vacate position',
      cancelLabel: 'Cancel',
      tone: 'access',
      details: [
        currentEmployee
          ? `${currentEmployee.display_name} remains an unassigned Company identity.`
          : 'This position is currently open.',
        sourcePosition
          ? `${nextIdentity?.display_name || 'The identity'} moves from ${sourcePosition.title}, which becomes open.`
          : 'No other position will be changed.',
        'Private identity memory is never transferred between occupants.',
      ],
    });
    if (!confirmed) return;

    setSaving(true);
    setError(null);
    try {
      await changeCompanyPositionOccupant(
        apiBaseUrl,
        token,
        companyId,
        position.position_id,
        {
          identity_id: selectedIdentityId,
          move_from_position_id: sourcePosition?.position_id || null,
          reason: reason.trim(),
        },
      );
      await onChanged();
      onClose();
    } catch (reasonValue) {
      setError(userFacingError(reasonValue, 'The position occupant was not changed.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.editor}>
      <View style={styles.header}>
        <View style={styles.copy}>
          <Text style={styles.eyebrow}>CONTROLLED JOB CHANGE</Text>
          <Text style={styles.title}>{position.title}</Text>
          <Text style={styles.meta}>Change the position assignment without merging identity memory or history.</Text>
        </View>
        <Pressable style={styles.secondaryAction} onPress={onClose}>
          <Text style={styles.secondaryActionText}>Close</Text>
        </Pressable>
      </View>

      {loading ? <Text style={styles.meta}>Reading eligible Company identities…</Text> : null}
      <View style={styles.choices}>
        <Pressable
          accessibilityRole="radio"
          accessibilityState={{ selected: selectedIdentityId === null }}
          style={[styles.choice, selectedIdentityId === null ? styles.choiceSelected : null]}
          onPress={() => setSelectedIdentityId(null)}
        >
          <Text style={styles.choiceTitle}>Leave position open</Text>
          <Text style={styles.meta}>The current employee stays in the Company as unassigned.</Text>
        </Pressable>
        {choices.map((identity) => {
          const selected = identity.identity_id === selectedIdentityId;
          const occupied = positions.find(
            (item) => item.occupant_identity_id === identity.identity_id,
          );
          return (
            <Pressable
              key={identity.identity_id}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
              style={[styles.choice, selected ? styles.choiceSelected : null]}
              onPress={() => setSelectedIdentityId(identity.identity_id)}
            >
              <Text style={styles.choiceTitle}>{identity.display_name}</Text>
              <Text style={styles.meta}>
                {identity.role}
                {occupied ? ` · currently ${occupied.title}` : ' · unassigned'}
              </Text>
            </Pressable>
          );
        })}
      </View>
      <TextInput
        accessibilityLabel="Reason for position occupant change"
        style={styles.input}
        value={reason}
        placeholder="Why this job change is being made"
        placeholderTextColor="#60768b"
        onChangeText={setReason}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Pressable
        disabled={!reason.trim() || saving || selectedIdentityId === currentEmployee?.identity_id}
        style={[
          styles.primaryAction,
          !reason.trim() || saving || selectedIdentityId === currentEmployee?.identity_id
            ? styles.disabled
            : null,
        ]}
        onPress={() => void submit()}
      >
        <Text style={styles.primaryActionText}>
          {saving ? 'Applying…' : selectedIdentityId ? 'Review occupant change…' : 'Review vacancy…'}
        </Text>
      </Pressable>
    </View>
  );
}


const styles = StyleSheet.create({
  editor: { marginHorizontal: 12, marginBottom: 10, padding: 12, borderRadius: 9, backgroundColor: '#0c1721', gap: 9 },
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  copy: { flex: 1, minWidth: 0 },
  eyebrow: { color: '#66d7e6', fontSize: 8, fontWeight: '900', letterSpacing: 0.8 },
  title: { color: '#e8f1f7', fontSize: 12, fontWeight: '800', marginTop: 3 },
  meta: { color: '#71879a', fontSize: 9, lineHeight: 13, marginTop: 2 },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  choice: { minWidth: 180, flexGrow: 1, padding: 9, borderRadius: 7, backgroundColor: '#101f2b' },
  choiceSelected: { backgroundColor: '#18343d' },
  choiceTitle: { color: '#dce8f1', fontSize: 10, fontWeight: '700' },
  input: { minHeight: 38, borderRadius: 7, backgroundColor: '#101f2b', color: '#e2edf5', paddingHorizontal: 11, paddingVertical: 8, fontSize: 11, outlineStyle: 'none' } as any,
  primaryAction: { alignSelf: 'flex-start', paddingHorizontal: 13, paddingVertical: 9, borderRadius: 7, backgroundColor: '#70d7e5' },
  primaryActionText: { color: '#061219', fontSize: 10, fontWeight: '900' },
  secondaryAction: { paddingHorizontal: 10, paddingVertical: 7, borderRadius: 7, backgroundColor: '#132732' },
  secondaryActionText: { color: '#73d9e6', fontSize: 9, fontWeight: '800' },
  error: { color: '#f0a0a6', fontSize: 10 },
  disabled: { opacity: 0.45 },
});
