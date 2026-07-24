import { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  updateCompanyJobContract,
  type CompanyJobContract,
} from '@/lib/appApi';
import { userFacingError } from '../../../lib/diagnostics';


type Props = {
  apiBaseUrl: string;
  token: string;
  companyId: string;
  contract: CompanyJobContract;
  employeeName: string;
  onClose: () => void;
  onSaved: () => Promise<void>;
};

function joined(items?: string[]) {
  return (items || []).join('\n');
}

function lines(value: string) {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function CompanyJobContractEditor({
  apiBaseUrl,
  token,
  companyId,
  contract,
  employeeName,
  onClose,
  onSaved,
}: Props) {
  const [mission, setMission] = useState(contract.mission || '');
  const [responsibilities, setResponsibilities] = useState(joined(contract.responsibilities));
  const [outsideRole, setOutsideRole] = useState(joined(contract.non_responsibilities));
  const [deliverables, setDeliverables] = useState(joined(contract.deliverables));
  const [qualityGates, setQualityGates] = useState(joined(contract.quality_gates));
  const [successMeasures, setSuccessMeasures] = useState(joined(contract.success_measures));
  const [reportingCadence, setReportingCadence] = useState(contract.reporting_cadence || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await updateCompanyJobContract(
        apiBaseUrl,
        token,
        companyId,
        contract.job_contract_id,
        {
          mission: mission.trim(),
          responsibilities: lines(responsibilities),
          non_responsibilities: lines(outsideRole),
          deliverables: lines(deliverables),
          quality_gates: lines(qualityGates),
          success_measures: lines(successMeasures),
          reporting_cadence: reportingCadence.trim() || null,
        },
      );
      await onSaved();
      onClose();
    } catch (reason) {
      setError(userFacingError(reason, 'The job contract could not be updated.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.panel}>
      <View style={styles.header}>
        <View style={styles.headerCopy}>
          <Text style={styles.eyebrow}>CONTROLLED JOB CHANGE</Text>
          <Text style={styles.title}>{employeeName}</Text>
          <Text style={styles.meta}>
            Contract v{contract.version} · changing the contract resets readiness until it is reviewed again
          </Text>
        </View>
        <Pressable accessibilityRole="button" style={styles.close} onPress={onClose}>
          <Text style={styles.closeText}>Close</Text>
        </Pressable>
      </View>
      <TextInput
        accessibilityLabel="Job mission"
        multiline
        style={[styles.input, styles.mission]}
        value={mission}
        placeholder="Mission and authority boundary"
        placeholderTextColor="#60768b"
        onChangeText={setMission}
      />
      <View style={styles.grid}>
        <Field
          label="RESPONSIBILITIES"
          value={responsibilities}
          onChange={setResponsibilities}
          placeholder="One responsibility per line"
        />
        <Field
          label="OUTSIDE THIS JOB"
          value={outsideRole}
          onChange={setOutsideRole}
          placeholder="One exclusion per line"
        />
        <Field
          label="DELIVERABLES"
          value={deliverables}
          onChange={setDeliverables}
          placeholder="One deliverable per line"
        />
        <Field
          label="QUALITY GATES"
          value={qualityGates}
          onChange={setQualityGates}
          placeholder="One gate per line"
        />
        <Field
          label="SUCCESS MEASURES"
          value={successMeasures}
          onChange={setSuccessMeasures}
          placeholder="One measurable outcome per line"
        />
        <View style={styles.field}>
          <Text style={styles.label}>REPORTING CADENCE</Text>
          <TextInput
            accessibilityLabel="Job reporting cadence"
            style={styles.input}
            value={reportingCadence}
            placeholder="For example weekly and at blockers"
            placeholderTextColor="#60768b"
            onChangeText={setReportingCadence}
          />
        </View>
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <View style={styles.footer}>
        <Text style={styles.hint}>
          The identity and its private memory stay in this Company. This changes the job contract, not the employee’s Company membership.
        </Text>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: saving || !mission.trim() }}
          disabled={saving || !mission.trim()}
          style={[styles.save, saving || !mission.trim() ? styles.disabled : null]}
          onPress={() => void save()}
        >
          <Text style={styles.saveText}>{saving ? 'Saving…' : 'Save new contract version'}</Text>
        </Pressable>
      </View>
    </View>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        multiline
        style={[styles.input, styles.multiline]}
        value={value}
        placeholder={placeholder}
        placeholderTextColor="#60768b"
        onChangeText={onChange}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { padding: 13, marginBottom: 9, borderRadius: 9, backgroundColor: '#0d1a25', gap: 9 },
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  headerCopy: { flex: 1 },
  eyebrow: { color: '#5fd3e5', fontSize: 8, fontWeight: '900', letterSpacing: 0.8 },
  title: { color: '#e5eff6', fontSize: 13, fontWeight: '800', marginTop: 3 },
  meta: { color: '#72899c', fontSize: 9, marginTop: 2 },
  close: { paddingHorizontal: 9, paddingVertical: 6, borderRadius: 6, backgroundColor: '#142431' },
  closeText: { color: '#8fa4b6', fontSize: 8, fontWeight: '800' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  field: { flex: 1, minWidth: 245, gap: 4 },
  label: { color: '#758ca0', fontSize: 8, fontWeight: '800', letterSpacing: 0.65 },
  input: { minHeight: 36, borderRadius: 7, backgroundColor: '#101f2b', color: '#e2edf5', paddingHorizontal: 10, paddingVertical: 8, fontSize: 10, outlineStyle: 'none' } as any,
  mission: { minHeight: 58, textAlignVertical: 'top' },
  multiline: { minHeight: 64, textAlignVertical: 'top' },
  footer: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  hint: { flex: 1, color: '#71879a', fontSize: 9, lineHeight: 13 },
  save: { paddingHorizontal: 12, paddingVertical: 9, borderRadius: 7, backgroundColor: '#70d7e5' },
  saveText: { color: '#061219', fontSize: 9, fontWeight: '900' },
  disabled: { opacity: 0.45 },
  error: { color: '#f0a0a6', fontSize: 9, lineHeight: 13 },
});
