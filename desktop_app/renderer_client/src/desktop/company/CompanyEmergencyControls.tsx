import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import {
  applyCompanyEmergencyControl,
  type CompanyDetail,
  type CompanyOperatingModel,
} from '@/lib/appApi';
import type { LocalConfirm } from '@/lib/sharedConfirmations';
import { userFacingError } from '../../../lib/diagnostics';


type Props = {
  apiBaseUrl: string;
  token: string;
  companyId: string;
  company: CompanyDetail | null;
  operatingModel: CompanyOperatingModel | null;
  confirmAction: LocalConfirm;
  onChanged: () => Promise<void>;
};


export function CompanyEmergencyControls({
  apiBaseUrl,
  token,
  companyId,
  company,
  operatingModel,
  confirmAction,
  onChanged,
}: Props) {
  const [open, setOpen] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const companyPaused = String(company?.manifest?.operating_state || 'active') === 'paused';
  const employees = company?.employees || [];
  const departments = operatingModel?.departments || company?.departments || [];

  const change = async (
    scope: 'company' | 'employee' | 'department',
    targetId: string | null,
    label: string,
    paused: boolean,
  ) => {
    const action = paused ? 'resume' : 'pause';
    const confirmed = await confirmAction({
      title: `${action === 'pause' ? 'Pause' : 'Resume'} ${label}?`,
      message: scope === 'company'
        ? (
          action === 'pause'
            ? 'This blocks new Company assignments and delegation at the root boundary. Active work is not silently killed.'
            : 'This reopens new Company assignment and delegation after operator review.'
        )
        : `${action === 'pause' ? 'Block' : 'Allow'} new Company assignments for this ${scope}.`,
      confirmLabel: action === 'pause' ? 'Pause new work' : 'Resume new work',
      cancelLabel: 'Cancel',
      tone: action === 'pause' ? 'danger' : 'access',
      details: [
        'Running work keeps its explicit state; use the manager emergency overflow to stop active worker runs.',
        'The change is Company-scoped, root-authorized, and audit logged.',
      ],
    });
    if (!confirmed) return;

    const key = `${scope}:${targetId || companyId}`;
    setBusyKey(key);
    setError(null);
    try {
      await applyCompanyEmergencyControl(apiBaseUrl, token, companyId, {
        scope,
        target_id: targetId,
        action,
        reason: `${action === 'pause' ? 'Paused' : 'Resumed'} by the local human operator from Company Governance.`,
      });
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, `New work was not ${action}d.`));
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <View style={styles.section}>
      <View style={styles.header}>
        <View style={styles.copy}>
          <Text style={styles.title}>Emergency assignment controls</Text>
          <Text style={styles.meta}>
            {companyPaused
              ? 'New Company work is paused at the root boundary.'
              : 'New Company work is allowed under normal policy and approval checks.'}
          </Text>
        </View>
        <Text style={companyPaused ? styles.paused : styles.active}>
          {companyPaused ? 'PAUSED' : 'ACTIVE'}
        </Text>
        <Pressable accessibilityRole="button" style={styles.secondaryAction} onPress={() => setOpen((value) => !value)}>
          <Text style={styles.secondaryActionText}>{open ? 'Close' : 'Manage'}</Text>
        </Pressable>
      </View>
      {open ? (
        <View style={styles.controls}>
          <ControlRow
            label="All new Company work"
            meta="Root dispatch boundary"
            paused={companyPaused}
            busy={busyKey === `company:${companyId}`}
            onChange={() => void change('company', null, 'all new Company work', companyPaused)}
          />
          {employees.map((employee) => (
            <ControlRow
              key={employee.employee_id}
              label={employee.display_name}
              meta={`${employee.company_role} · employee assignments`}
              paused={Boolean(employee.assignment_paused)}
              busy={busyKey === `employee:${employee.identity_id}`}
              onChange={() => void change(
                'employee',
                employee.identity_id,
                employee.display_name,
                Boolean(employee.assignment_paused),
              )}
            />
          ))}
          {departments.map((department: any) => (
            <ControlRow
              key={String(department.department_id)}
              label={String(department.name || 'Department')}
              meta="Department assignments"
              paused={Boolean(department.assignment_paused)}
              busy={busyKey === `department:${String(department.department_id)}`}
              onChange={() => void change(
                'department',
                String(department.department_id),
                String(department.name || 'department'),
                Boolean(department.assignment_paused),
              )}
            />
          ))}
          {error ? <Text style={styles.error}>{error}</Text> : null}
        </View>
      ) : null}
    </View>
  );
}


function ControlRow({
  label,
  meta,
  paused,
  busy,
  onChange,
}: {
  label: string;
  meta: string;
  paused: boolean;
  busy: boolean;
  onChange: () => void;
}) {
  return (
    <View style={styles.controlRow}>
      <View style={styles.copy}>
        <Text style={styles.controlLabel}>{label}</Text>
        <Text style={styles.meta}>{meta}</Text>
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ disabled: busy }}
        disabled={busy}
        style={[paused ? styles.resumeAction : styles.pauseAction, busy ? styles.disabled : null]}
        onPress={onChange}
      >
        <Text style={paused ? styles.resumeActionText : styles.pauseActionText}>
          {busy ? 'Updating…' : paused ? 'Resume' : 'Pause'}
        </Text>
      </Pressable>
    </View>
  );
}


const styles = StyleSheet.create({
  section: { borderTopWidth: 1, borderTopColor: '#1b2a39', paddingTop: 12, gap: 8 },
  header: { minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: 10 },
  copy: { flex: 1, minWidth: 0 },
  title: { color: '#e1ebf3', fontSize: 11, fontWeight: '700' },
  meta: { color: '#71879a', fontSize: 9, lineHeight: 13, marginTop: 2 },
  active: { color: '#61d3a0', fontSize: 8, fontWeight: '900' },
  paused: { color: '#ef9ba3', fontSize: 8, fontWeight: '900' },
  controls: { padding: 10, borderRadius: 9, backgroundColor: '#0c1721' },
  controlRow: { minHeight: 46, flexDirection: 'row', alignItems: 'center', gap: 10, borderBottomWidth: 1, borderBottomColor: '#182837' },
  controlLabel: { color: '#dce8f1', fontSize: 10, fontWeight: '700' },
  secondaryAction: { paddingHorizontal: 11, paddingVertical: 7, borderRadius: 7, backgroundColor: '#132732' },
  secondaryActionText: { color: '#73d9e6', fontSize: 9, fontWeight: '800' },
  pauseAction: { paddingHorizontal: 10, paddingVertical: 7, borderRadius: 6, backgroundColor: '#2c1a20' },
  pauseActionText: { color: '#f0a8ae', fontSize: 9, fontWeight: '800' },
  resumeAction: { paddingHorizontal: 10, paddingVertical: 7, borderRadius: 6, backgroundColor: '#17342e' },
  resumeActionText: { color: '#83dcb4', fontSize: 9, fontWeight: '800' },
  disabled: { opacity: 0.45 },
  error: { color: '#f0a0a6', fontSize: 10, marginTop: 8 },
});
