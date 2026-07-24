import { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  reviewCompanyJobReadiness,
  type CompanyJobContract,
} from '@/lib/appApi';
import { userFacingError } from '../../../lib/diagnostics';


const READINESS_CHECKS = [
  ['mission', 'Mission and boundaries'],
  ['objective_context', 'Relevant objectives'],
  ['approved_input', 'Approved input access'],
  ['representative_deliverable', 'Representative deliverable'],
  ['approval_boundary', 'Approval boundary'],
  ['handoff', 'Correct handoff'],
  ['uncertainty', 'Uncertainty and blockers'],
] as const;

type Props = {
  apiBaseUrl: string;
  token: string;
  companyId: string;
  contract: CompanyJobContract;
  employeeName: string;
  reviewerIdentityId?: string | null;
  onClose: () => void;
  onSaved: () => Promise<void>;
};

function requirementRecords(value: string) {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((label) => ({ kind: 'missing_requirement', label }));
}

export function CompanyReadinessReview({
  apiBaseUrl,
  token,
  companyId,
  contract,
  employeeName,
  reviewerIdentityId,
  onClose,
  onSaved,
}: Props) {
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  const [evidence, setEvidence] = useState('');
  const [missing, setMissing] = useState(
    (contract.missing_requirements || [])
      .map((item) => String(item.label || item.kind || '').trim())
      .filter(Boolean)
      .join('\n'),
  );
  const [limitedMode, setLimitedMode] = useState(false);
  const [limitations, setLimitations] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const missingRequirements = useMemo(
    () => requirementRecords(missing),
    [missing],
  );
  const allDemonstrated = READINESS_CHECKS.every(([id]) => checks[id]);
  const projectedStatus = allDemonstrated && evidence.trim()
    ? missingRequirements.length
      ? limitedMode && limitations.trim() ? 'limited ready' : 'blocked'
      : 'ready'
    : 'blocked';

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      await reviewCompanyJobReadiness(
        apiBaseUrl,
        token,
        companyId,
        contract.job_contract_id,
        {
          reviewer_identity_id: reviewerIdentityId || null,
          checks,
          evidence: evidence.trim()
            ? [{ kind: 'readiness_observation', summary: evidence.trim() }]
            : [],
          missing_requirements: missingRequirements,
          limited_mode: limitedMode,
          limitations: limitations.trim() || null,
        },
      );
      await onSaved();
      onClose();
    } catch (reason) {
      setError(userFacingError(reason, 'The readiness review could not be recorded.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.panel}>
      <View style={styles.header}>
        <View style={styles.headerCopy}>
          <Text style={styles.eyebrow}>READINESS REVIEW</Text>
          <Text style={styles.title}>{employeeName}</Text>
          <Text style={styles.meta}>
            Contract v{contract.version} · observed evidence, not a general intelligence claim
          </Text>
        </View>
        <Pressable accessibilityRole="button" style={styles.close} onPress={onClose}>
          <Text style={styles.closeText}>Close</Text>
        </Pressable>
      </View>

      <View style={styles.checkGrid}>
        {READINESS_CHECKS.map(([id, label]) => {
          const selected = Boolean(checks[id]);
          return (
            <Pressable
              key={id}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: selected }}
              style={[styles.check, selected ? styles.checkSelected : null]}
              onPress={() => setChecks((current) => ({
                ...current,
                [id]: !current[id],
              }))}
            >
              <View style={[styles.checkMark, selected ? styles.checkMarkSelected : null]}>
                <Text style={styles.checkMarkText}>{selected ? '✓' : ''}</Text>
              </View>
              <Text style={[styles.checkText, selected ? styles.checkTextSelected : null]}>
                {label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <Text style={styles.label}>OBSERVED TEST EVIDENCE</Text>
      <TextInput
        accessibilityLabel="Readiness test evidence"
        multiline
        style={[styles.input, styles.evidenceInput]}
        value={evidence}
        placeholder="What did the employee demonstrate, what was reviewed, and where is the result?"
        placeholderTextColor="#60768b"
        onChangeText={setEvidence}
      />

      <View style={styles.split}>
        <View style={styles.field}>
          <Text style={styles.label}>MISSING REQUIREMENTS</Text>
          <TextInput
            accessibilityLabel="Missing readiness requirements"
            multiline
            style={[styles.input, styles.smallInput]}
            value={missing}
            placeholder="One missing tool, credential, model, file, or capability per line"
            placeholderTextColor="#60768b"
            onChangeText={setMissing}
          />
        </View>
        <View style={styles.field}>
          <View style={styles.limitHeader}>
            <Text style={styles.label}>LIMITED MODE</Text>
            <Pressable
              accessibilityRole="switch"
              accessibilityState={{ checked: limitedMode }}
              style={[styles.switchTrack, limitedMode ? styles.switchTrackOn : null]}
              onPress={() => setLimitedMode((current) => !current)}
            >
              <View style={[styles.switchThumb, limitedMode ? styles.switchThumbOn : null]} />
            </Pressable>
          </View>
          <TextInput
            accessibilityLabel="Limited mode restrictions"
            multiline
            editable={limitedMode}
            style={[
              styles.input,
              styles.smallInput,
              !limitedMode ? styles.disabled : null,
            ]}
            value={limitations}
            placeholder="Exact work it may do and actions it still cannot take"
            placeholderTextColor="#60768b"
            onChangeText={setLimitations}
          />
        </View>
      </View>

      {error ? <Text style={styles.error}>{error}</Text> : null}
      <View style={styles.footer}>
        <Text style={styles.outcome}>
          Result: <Text style={projectedStatus === 'ready' ? styles.ready : projectedStatus === 'limited ready' ? styles.limited : styles.blocked}>{projectedStatus}</Text>
        </Text>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: saving }}
          disabled={saving}
          style={[styles.save, saving ? styles.disabled : null]}
          onPress={() => void submit()}
        >
          <Text style={styles.saveText}>{saving ? 'Recording…' : 'Record review'}</Text>
        </Pressable>
      </View>
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
  checkGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 5 },
  check: { width: 196, minHeight: 34, paddingHorizontal: 8, paddingVertical: 7, borderRadius: 7, backgroundColor: '#12222e', flexDirection: 'row', alignItems: 'center', gap: 7 },
  checkSelected: { backgroundColor: '#17343c' },
  checkMark: { width: 14, height: 14, borderRadius: 4, borderWidth: 1, borderColor: '#587185', alignItems: 'center', justifyContent: 'center' },
  checkMarkSelected: { borderColor: '#6edbe7', backgroundColor: '#6edbe7' },
  checkMarkText: { color: '#07141a', fontSize: 9, fontWeight: '900' },
  checkText: { color: '#8195a7', fontSize: 9, flex: 1 },
  checkTextSelected: { color: '#dce9f1' },
  label: { color: '#758ca0', fontSize: 8, fontWeight: '800', letterSpacing: 0.65 },
  input: { borderRadius: 7, backgroundColor: '#101f2b', color: '#e2edf5', paddingHorizontal: 10, paddingVertical: 8, fontSize: 10, outlineStyle: 'none' } as any,
  evidenceInput: { minHeight: 68, textAlignVertical: 'top' },
  smallInput: { minHeight: 58, textAlignVertical: 'top' },
  split: { flexDirection: 'row', flexWrap: 'wrap', gap: 9 },
  field: { flex: 1, minWidth: 250, gap: 5 },
  limitHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  switchTrack: { width: 30, height: 17, borderRadius: 999, padding: 2, backgroundColor: '#213446' },
  switchTrackOn: { backgroundColor: '#2a6670' },
  switchThumb: { width: 13, height: 13, borderRadius: 999, backgroundColor: '#91a4b4' },
  switchThumbOn: { marginLeft: 13, backgroundColor: '#79e0ea' },
  disabled: { opacity: 0.45 },
  error: { color: '#f0a0a6', fontSize: 9, lineHeight: 13 },
  footer: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  outcome: { color: '#8095a7', fontSize: 9, textTransform: 'capitalize' },
  ready: { color: '#61d3a0', fontWeight: '900' },
  limited: { color: '#e3bd68', fontWeight: '900' },
  blocked: { color: '#ef969c', fontWeight: '900' },
  save: { paddingHorizontal: 12, paddingVertical: 9, borderRadius: 7, backgroundColor: '#70d7e5' },
  saveText: { color: '#061219', fontSize: 9, fontWeight: '900' },
});
