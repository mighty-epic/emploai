import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  createCompanyPolicy,
  recordCompanyDecision,
  updateCompany,
  type CompanyDetail,
  type CompanyOperatingModel,
} from '@/lib/appApi';
import type { LocalConfirm } from '@/lib/sharedConfirmations';
import { userFacingError } from '../../../lib/diagnostics';
import { CompanyEmergencyControls } from './CompanyEmergencyControls';
import { CompanyLifecyclePanel } from './CompanyLifecyclePanel';


type ExternalActionLevel =
  | 'disabled'
  | 'draft_only'
  | 'approval_required'
  | 'autonomous_within_scope'
  | 'broadly_autonomous';

const EXTERNAL_LEVELS: ExternalActionLevel[] = [
  'disabled',
  'draft_only',
  'approval_required',
  'autonomous_within_scope',
  'broadly_autonomous',
];
const EXTERNAL_CATEGORIES = [
  ['customer_communication', 'Customer communication'],
  ['publishing', 'Publishing'],
  ['spending', 'Spending'],
  ['deploying', 'Deploying'],
  ['external_account_changes', 'External account changes'],
] as const;
const NOTIFICATION_CATEGORIES = [
  ['approvals', 'Approvals'],
  ['risks', 'Material risks'],
  ['incidents', 'Incidents'],
  ['deadlines', 'Deadlines'],
  ['blockers', 'Blockers'],
] as const;

type Props = {
  apiBaseUrl: string;
  token: string;
  companyId: string;
  company: CompanyDetail | null;
  operatingModel: CompanyOperatingModel | null;
  openRequestCount: number;
  confirmAction: LocalConfirm;
  onChanged: () => Promise<void>;
};

export function CompanyGovernancePanel({
  apiBaseUrl,
  token,
  companyId,
  company,
  operatingModel,
  openRequestCount,
  confirmAction,
  onChanged,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [decisionOpen, setDecisionOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [rule, setRule] = useState('');
  const [decisionQuestion, setDecisionQuestion] = useState('');
  const [decisionText, setDecisionText] = useState('');
  const [decisionRationale, setDecisionRationale] = useState('');
  const [saving, setSaving] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [externalPolicies, setExternalPolicies] = useState<Record<string, ExternalActionLevel>>({});
  const [notificationPolicy, setNotificationPolicy] = useState<Record<string, boolean>>({});
  const [quietHours, setQuietHours] = useState('');
  const [error, setError] = useState<string | null>(null);
  const policies = operatingModel?.policies || company?.policies || [];
  const decisions = company?.decisions || [];

  useEffect(() => {
    const manifest = company?.manifest || {};
    const storedExternal = (manifest.external_action_policies || {}) as Record<string, ExternalActionLevel>;
    const storedNotifications = (manifest.notification_policy || {}) as Record<string, unknown>;
    setExternalPolicies(Object.fromEntries(
      EXTERNAL_CATEGORIES.map(([id]) => [
        id,
        EXTERNAL_LEVELS.includes(storedExternal[id])
          ? storedExternal[id]
          : 'draft_only',
      ]),
    ));
    setNotificationPolicy(Object.fromEntries(
      NOTIFICATION_CATEGORIES.map(([id]) => [
        id,
        storedNotifications[id] !== false,
      ]),
    ));
    setQuietHours(String(storedNotifications.quiet_hours || ''));
  }, [company?.company_id, company?.updated_at]);

  const submit = async () => {
    if (!title.trim() || !rule.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createCompanyPolicy(apiBaseUrl, token, companyId, {
        title: title.trim(),
        rule: rule.trim(),
        scope: 'company',
        enforcement: 'manager',
      });
      setTitle('');
      setRule('');
      setEditing(false);
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, 'The policy could not be created.'));
    } finally {
      setSaving(false);
    }
  };

  const submitDecision = async () => {
    if (!decisionQuestion.trim() || !decisionText.trim() || !decisionRationale.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await recordCompanyDecision(apiBaseUrl, token, companyId, {
        question: decisionQuestion.trim(),
        decision: decisionText.trim(),
        rationale: decisionRationale.trim(),
        scope: 'company',
        related_record_ids: [],
      });
      setDecisionQuestion('');
      setDecisionText('');
      setDecisionRationale('');
      setDecisionOpen(false);
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, 'The operator decision could not be recorded.'));
    } finally {
      setSaving(false);
    }
  };

  const saveOperatingBoundaries = async () => {
    setSaving(true);
    setError(null);
    try {
      await updateCompany(apiBaseUrl, token, companyId, {
        manifest: {
          external_action_default: 'draft_only',
          external_action_policies: externalPolicies,
          notification_policy: {
            ...notificationPolicy,
            quiet_hours: quietHours.trim() || null,
          },
        },
      });
      setSettingsOpen(false);
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, 'The operating boundaries could not be saved.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.content}>
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>AUTHORITY AND AUDIT</Text>
          <Text style={styles.title}>Governance</Text>
        </View>
        <View style={styles.headerActions}>
          <Pressable accessibilityRole="button" style={styles.secondaryAction} onPress={() => {
            setSettingsOpen((value) => !value);
            setDecisionOpen(false);
            setEditing(false);
          }}>
            <Text style={styles.secondaryActionText}>{settingsOpen ? 'Close' : 'Boundaries'}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" style={styles.secondaryAction} onPress={() => {
            setDecisionOpen((value) => !value);
            setEditing(false);
            setSettingsOpen(false);
          }}>
            <Text style={styles.secondaryActionText}>{decisionOpen ? 'Close' : 'Record decision'}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" style={styles.primaryAction} onPress={() => {
            setEditing((value) => !value);
            setDecisionOpen(false);
            setSettingsOpen(false);
          }}>
            <Text style={styles.primaryActionText}>{editing ? 'Close' : 'Add policy'}</Text>
          </Pressable>
        </View>
      </View>

      <View style={styles.facts}>
        <Fact label="Policies" value={String(policies.length)} />
        <Fact label="Decisions" value={String(decisions.length)} />
        <Fact label="Open requests" value={String(openRequestCount)} />
        <Fact label="Ultimate authority" value="Local OS operator" />
      </View>

      {settingsOpen ? (
        <View style={styles.editor}>
          <Text style={styles.editorTitle}>External actions and human notifications</Text>
          <Text style={styles.editorBody}>
            These are Company ceilings. A lower-level job, assignment, recipient, budget, tool grant, Fleet permission, or safety rule may still require stricter handling.
          </Text>
          <View style={styles.boundaryList}>
            {EXTERNAL_CATEGORIES.map(([id, label]) => (
              <View key={id} style={styles.boundaryRow}>
                <Text style={styles.boundaryLabel}>{label}</Text>
                <View style={styles.levelChoices}>
                  {EXTERNAL_LEVELS.map((level) => (
                    <Pressable
                      key={level}
                      accessibilityRole="radio"
                      accessibilityState={{ selected: externalPolicies[id] === level }}
                      style={[
                        styles.levelChoice,
                        externalPolicies[id] === level ? styles.levelChoiceSelected : null,
                      ]}
                      onPress={() => setExternalPolicies((current) => ({
                        ...current,
                        [id]: level,
                      }))}
                    >
                      <Text style={[
                        styles.levelChoiceText,
                        externalPolicies[id] === level ? styles.levelChoiceTextSelected : null,
                      ]}>
                        {level.replace(/_/g, ' ')}
                      </Text>
                    </Pressable>
                  ))}
                </View>
              </View>
            ))}
          </View>
          <Text style={styles.listLabel}>PING THE HUMAN FOR</Text>
          <View style={styles.notificationChoices}>
            {NOTIFICATION_CATEGORIES.map(([id, label]) => {
              const selected = notificationPolicy[id] !== false;
              return (
                <Pressable
                  key={id}
                  accessibilityRole="checkbox"
                  accessibilityState={{ checked: selected }}
                  style={[styles.notificationChoice, selected ? styles.notificationChoiceSelected : null]}
                  onPress={() => setNotificationPolicy((current) => ({
                    ...current,
                    [id]: !selected,
                  }))}
                >
                  <Text style={styles.notificationMark}>{selected ? '✓' : ''}</Text>
                  <Text style={styles.notificationText}>{label}</Text>
                </Pressable>
              );
            })}
          </View>
          <TextInput
            accessibilityLabel="Notification quiet hours"
            style={styles.input}
            value={quietHours}
            placeholder="Optional quiet hours, for example 22:00–07:00 local"
            placeholderTextColor="#60768b"
            onChangeText={setQuietHours}
          />
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <View style={styles.footer}>
            <Text style={styles.hint}>Draft only remains the default for any new or unspecified external-action category.</Text>
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: saving }}
              disabled={saving}
              style={[styles.saveAction, saving ? styles.disabled : null]}
              onPress={() => void saveOperatingBoundaries()}
            >
              <Text style={styles.saveActionText}>{saving ? 'Saving…' : 'Save boundaries'}</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      {editing ? (
        <View style={styles.editor}>
          <Text style={styles.editorTitle}>Publish a company policy</Text>
          <Text style={styles.editorBody}>
            A company policy guides managers and employees. It never overrides Fleet pairing, local tool grants, resource locks, or safety enforcement.
          </Text>
          <TextInput
            accessibilityLabel="Policy title"
            style={styles.input}
            value={title}
            placeholder="Policy title"
            placeholderTextColor="#60768b"
            onChangeText={setTitle}
          />
          <TextInput
            accessibilityLabel="Policy rule"
            multiline
            style={[styles.input, styles.multiline]}
            value={rule}
            placeholder="State the rule clearly"
            placeholderTextColor="#60768b"
            onChangeText={setRule}
          />
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <View style={styles.footer}>
            <Text style={styles.hint}>Version 1 · company scope · manager enforced</Text>
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: saving || !title.trim() || !rule.trim() }}
              disabled={saving || !title.trim() || !rule.trim()}
              style={[styles.saveAction, saving || !title.trim() || !rule.trim() ? styles.disabled : null]}
              onPress={() => void submit()}
            >
              <Text style={styles.saveActionText}>{saving ? 'Publishing…' : 'Publish policy'}</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      {decisionOpen ? (
        <View style={styles.editor}>
          <Text style={styles.editorTitle}>Record an operator decision</Text>
          <Text style={styles.editorBody}>Use this for a material choice the company must be able to explain later. Recording it does not grant new Fleet or tool access.</Text>
          <TextInput
            accessibilityLabel="Decision question"
            style={styles.input}
            value={decisionQuestion}
            placeholder="Question that was decided"
            placeholderTextColor="#60768b"
            onChangeText={setDecisionQuestion}
          />
          <TextInput
            accessibilityLabel="Operator decision"
            multiline
            style={[styles.input, styles.multiline]}
            value={decisionText}
            placeholder="The decision"
            placeholderTextColor="#60768b"
            onChangeText={setDecisionText}
          />
          <TextInput
            accessibilityLabel="Decision rationale"
            multiline
            style={[styles.input, styles.multiline]}
            value={decisionRationale}
            placeholder="Why this decision was made"
            placeholderTextColor="#60768b"
            onChangeText={setDecisionRationale}
          />
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: saving || !decisionQuestion.trim() || !decisionText.trim() || !decisionRationale.trim() }}
            disabled={saving || !decisionQuestion.trim() || !decisionText.trim() || !decisionRationale.trim()}
            style={[styles.saveAction, saving || !decisionQuestion.trim() || !decisionText.trim() || !decisionRationale.trim() ? styles.disabled : null]}
            onPress={() => void submitDecision()}
          >
            <Text style={styles.saveActionText}>{saving ? 'Recording…' : 'Record decision'}</Text>
          </Pressable>
        </View>
      ) : null}

      {error && !editing && !decisionOpen && !settingsOpen ? <Text style={styles.error}>{error}</Text> : null}
      {policies.length ? (
        <View style={styles.list}>
          {policies.map((policy) => (
            <View key={policy.policy_id} style={styles.policyRow}>
              <View style={styles.rowCopy}>
                <Text style={styles.rowTitle}>{policy.title}</Text>
                <Text style={styles.rowMeta}>{policy.rule}</Text>
              </View>
              <Text style={styles.status}>{policy.status}</Text>
            </View>
          ))}
        </View>
      ) : (
        <Text style={styles.hint}>No additional policies. The charter, Fleet permissions, tool grants, safety rules, and resource locks still apply.</Text>
      )}

      {decisions.length ? (
        <View style={styles.list}>
          <Text style={styles.listLabel}>DECISION REGISTER</Text>
          {[...decisions].reverse().map((decision: any) => (
            <View key={String(decision.decision_id || decision.id)} style={styles.policyRow}>
              <View style={styles.rowCopy}>
                <Text style={styles.rowTitle}>{String(decision.question || 'Operator decision')}</Text>
                <Text style={styles.rowMeta}>{String(decision.decision || '')}</Text>
                <Text style={styles.decisionRationale}>{String(decision.rationale || '')}</Text>
              </View>
              <Text style={styles.status}>RECORDED</Text>
            </View>
          ))}
        </View>
      ) : null}

      <CompanyEmergencyControls
        apiBaseUrl={apiBaseUrl}
        token={token}
        companyId={companyId}
        company={company}
        operatingModel={operatingModel}
        confirmAction={confirmAction}
        onChanged={onChanged}
      />

      <CompanyLifecyclePanel
        apiBaseUrl={apiBaseUrl}
        token={token}
        companyId={companyId}
        company={company}
        companyName={String(company?.manifest?.display_name || 'My Company')}
        confirmAction={confirmAction}
        onChanged={onChanged}
      />
    </View>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.fact}>
      <Text style={styles.factLabel}>{label}</Text>
      <Text style={styles.factValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 20, paddingTop: 18, gap: 14 },
  header: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12 },
  headerActions: { flexDirection: 'row', gap: 6 },
  eyebrow: { color: '#5fd3e5', fontSize: 8, fontWeight: '800', letterSpacing: 1.05 },
  title: { color: '#edf5fb', fontSize: 17, fontWeight: '800', marginTop: 3 },
  primaryAction: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 7, backgroundColor: '#17313b' },
  primaryActionText: { color: '#79ddea', fontSize: 10, fontWeight: '800' },
  facts: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  fact: { minWidth: 150, paddingVertical: 10, paddingHorizontal: 12, borderRadius: 8, backgroundColor: '#0d1923' },
  factLabel: { color: '#6f8498', fontSize: 8, fontWeight: '800', letterSpacing: 0.7, textTransform: 'uppercase' },
  factValue: { color: '#dae6ef', fontSize: 11, fontWeight: '700', marginTop: 4 },
  editor: { borderRadius: 10, backgroundColor: '#0c1721', padding: 14, gap: 9 },
  editorTitle: { color: '#e7f0f7', fontSize: 13, fontWeight: '800' },
  editorBody: { color: '#7d93a6', fontSize: 10, lineHeight: 15, maxWidth: 720 },
  input: { minHeight: 38, borderRadius: 7, backgroundColor: '#101f2b', color: '#e2edf5', paddingHorizontal: 11, paddingVertical: 8, fontSize: 11, outlineStyle: 'none' } as any,
  multiline: { minHeight: 82, textAlignVertical: 'top' },
  boundaryList: { gap: 5 },
  boundaryRow: { minHeight: 42, flexDirection: 'row', alignItems: 'center', gap: 10 },
  boundaryLabel: { width: 142, color: '#9aabba', fontSize: 9, fontWeight: '700' },
  levelChoices: { flex: 1, flexDirection: 'row', flexWrap: 'wrap', gap: 4 },
  levelChoice: { paddingHorizontal: 8, paddingVertical: 6, borderRadius: 6, backgroundColor: '#101f2b' },
  levelChoiceSelected: { backgroundColor: '#1a3943' },
  levelChoiceText: { color: '#71889b', fontSize: 8, textTransform: 'capitalize' },
  levelChoiceTextSelected: { color: '#75dce7', fontWeight: '800' },
  notificationChoices: { flexDirection: 'row', flexWrap: 'wrap', gap: 5 },
  notificationChoice: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 9, paddingVertical: 7, borderRadius: 7, backgroundColor: '#101f2b' },
  notificationChoiceSelected: { backgroundColor: '#17343c' },
  notificationMark: { width: 10, color: '#70dbe6', fontSize: 9, fontWeight: '900' },
  notificationText: { color: '#9babb9', fontSize: 8, fontWeight: '700' },
  footer: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  hint: { color: '#708599', fontSize: 10, lineHeight: 15 },
  saveAction: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: 7, backgroundColor: '#70d7e5' },
  saveActionText: { color: '#061219', fontSize: 10, fontWeight: '900' },
  disabled: { opacity: 0.45 },
  error: { color: '#f0a0a6', fontSize: 10, lineHeight: 14 },
  list: { borderTopWidth: 1, borderTopColor: '#1b2a39' },
  listLabel: { color: '#657d91', fontSize: 8, fontWeight: '900', letterSpacing: 0.75, paddingTop: 8, paddingBottom: 2 },
  policyRow: { minHeight: 60, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#172635', flexDirection: 'row', alignItems: 'center', gap: 12 },
  rowCopy: { flex: 1, minWidth: 0 },
  rowTitle: { color: '#e1ebf3', fontSize: 11, fontWeight: '700' },
  rowMeta: { color: '#71879a', fontSize: 9, lineHeight: 14, marginTop: 3 },
  decisionRationale: { color: '#667e92', fontSize: 8, lineHeight: 12, marginTop: 4 },
  status: { color: '#61d3a0', fontSize: 8, fontWeight: '900', textTransform: 'uppercase' },
  secondaryAction: { paddingHorizontal: 11, paddingVertical: 7, borderRadius: 7, backgroundColor: '#132732' },
  secondaryActionText: { color: '#73d9e6', fontSize: 9, fontWeight: '800' },
});
