import { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  createCompanyObjective,
  routeCompanyObjectiveAssignment,
  updateCompanyObjectiveStatus,
  type CompanyDetail,
  type CompanyObjective,
  type CompanyOperatingModel,
} from '@/lib/appApi';
import { userFacingError } from '../../../lib/diagnostics';
import type { CompanyAssignmentTarget } from './companyAssignmentTargets';
import { CompanyOperatingRecordsPanel } from './CompanyOperatingRecordsPanel';


type Props = {
  apiBaseUrl: string;
  token: string;
  companyId: string;
  company: CompanyDetail | null;
  operatingModel: CompanyOperatingModel | null;
  tasks: any[];
  reports: any[];
  assignmentTargets: CompanyAssignmentTarget[];
  onChanged: () => Promise<void>;
};

export function CompanyWorkPanel({
  apiBaseUrl,
  token,
  companyId,
  company,
  operatingModel,
  tasks,
  reports,
  assignmentTargets,
  onChanged,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [outcome, setOutcome] = useState('');
  const [successCriteria, setSuccessCriteria] = useState('');
  const [priority, setPriority] = useState('normal');
  const [saving, setSaving] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [assigningObjectiveId, setAssigningObjectiveId] = useState<string | null>(null);
  const [assigneeIdentityId, setAssigneeIdentityId] = useState<string | null>(null);
  const [assignmentPrompt, setAssignmentPrompt] = useState('');
  const [routing, setRouting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const objectives = operatingModel?.objectives || company?.objectives || [];
  const owner = company?.employees.find((employee) => employee.system_role === 'manager');
  const availableAssignees = assignmentTargets.filter(
    (target) => target.identityId !== owner?.identity_id,
  );

  const submit = async () => {
    if (!outcome.trim() || !successCriteria.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createCompanyObjective(apiBaseUrl, token, companyId, {
        outcome: outcome.trim(),
        success_criteria: successCriteria.trim(),
        owner_identity_id: owner?.identity_id || null,
        priority,
        low_risk_auto_accept: false,
        optional_proposals: [],
      });
      setOutcome('');
      setSuccessCriteria('');
      setPriority('normal');
      setEditing(false);
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, 'The objective could not be created.'));
    } finally {
      setSaving(false);
    }
  };

  const setStatus = async (objective: CompanyObjective, status: string) => {
    setUpdatingId(objective.objective_id);
    setError(null);
    try {
      await updateCompanyObjectiveStatus(apiBaseUrl, token, companyId, objective.objective_id, { status });
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, 'The objective could not be updated.'));
    } finally {
      setUpdatingId(null);
    }
  };

  const assignObjective = async (objective: CompanyObjective) => {
    if (!assigneeIdentityId || !assignmentPrompt.trim()) return;
    setRouting(true);
    setError(null);
    try {
      await routeCompanyObjectiveAssignment(
        apiBaseUrl,
        token,
        companyId,
        objective,
        assigneeIdentityId,
        assignmentPrompt.trim(),
      );
      setAssigningObjectiveId(null);
      setAssigneeIdentityId(null);
      setAssignmentPrompt('');
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, 'The objective assignment could not be routed.'));
    } finally {
      setRouting(false);
    }
  };

  return (
    <View style={styles.content}>
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>OUTCOMES AND EXECUTION</Text>
          <Text style={styles.title}>Work</Text>
        </View>
        <Pressable accessibilityRole="button" style={styles.primaryAction} onPress={() => setEditing((value) => !value)}>
          <Text style={styles.primaryActionText}>{editing ? 'Close' : 'New objective'}</Text>
        </Pressable>
      </View>

      {editing ? (
        <View style={styles.editor}>
          <Text style={styles.editorTitle}>What outcome did the operator ask for?</Text>
          <Text style={styles.editorBody}>
            Keep the requested outcome exact. A manager may later propose optional improvements, but they remain proposals until the operator accepts them.
          </Text>
          <TextInput
            accessibilityLabel="Objective outcome"
            style={styles.input}
            value={outcome}
            placeholder="Outcome"
            placeholderTextColor="#60768b"
            onChangeText={setOutcome}
          />
          <TextInput
            accessibilityLabel="Objective success criteria"
            multiline
            style={[styles.input, styles.multiline]}
            value={successCriteria}
            placeholder="How will the manager know the result is acceptable?"
            placeholderTextColor="#60768b"
            onChangeText={setSuccessCriteria}
          />
          <View style={styles.choiceWrap}>
            {['low', 'normal', 'high', 'urgent'].map((item) => (
              <Pressable
                key={item}
                accessibilityRole="radio"
                accessibilityState={{ selected: priority === item }}
                style={[styles.choice, priority === item ? styles.choiceSelected : null]}
                onPress={() => setPriority(item)}
              >
                <Text style={[styles.choiceText, priority === item ? styles.choiceTextSelected : null]}>{item}</Text>
              </Pressable>
            ))}
          </View>
          <Text style={styles.reviewNote}>
            Every employee or subordinate-manager report remains submitted until its assigning manager reviews it.
          </Text>
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <View style={styles.footer}>
            <Text style={styles.hint}>Owner: {owner?.display_name || 'local manager'}</Text>
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: saving || !outcome.trim() || !successCriteria.trim() }}
              disabled={saving || !outcome.trim() || !successCriteria.trim()}
              style={[styles.saveAction, saving || !outcome.trim() || !successCriteria.trim() ? styles.disabled : null]}
              onPress={() => void submit()}
            >
              <Text style={styles.saveActionText}>{saving ? 'Saving…' : 'Create objective'}</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      {error && !editing ? <Text style={styles.error}>{error}</Text> : null}

      {objectives.length ? (
        <View style={styles.list}>
          {objectives.map((objective) => (
            <View key={objective.objective_id} style={styles.objectiveRow}>
              <View style={styles.rowCopy}>
                <View style={styles.rowHeader}>
                  <Text style={styles.rowTitle}>{objective.outcome}</Text>
                  <Text style={styles.status}>{objective.status.replace(/_/g, ' ')}</Text>
                </View>
                <Text style={styles.rowMeta}>{objective.success_criteria}</Text>
                <View style={styles.rowFooter}>
                  <Text style={styles.tiny}>{objective.priority} priority · {objective.linked_task_ids.length} linked tasks</Text>
                  <View style={styles.actions}>
                    {objective.status === 'planned' ? (
                      <SmallAction
                        label={updatingId === objective.objective_id ? 'Starting…' : 'Start'}
                        disabled={Boolean(updatingId)}
                        onPress={() => void setStatus(objective, 'active')}
                      />
                    ) : null}
                    {!['completed', 'stopped', 'superseded'].includes(objective.status) ? (
                      <SmallAction
                        label={assigningObjectiveId === objective.objective_id ? 'Close assignment' : 'Assign work'}
                        disabled={routing}
                        onPress={() => {
                          setAssigningObjectiveId((current) => (
                            current === objective.objective_id ? null : objective.objective_id
                          ));
                          setAssigneeIdentityId(null);
                          setAssignmentPrompt('');
                        }}
                      />
                    ) : null}
                    {!['completed', 'stopped', 'superseded'].includes(objective.status) ? (
                      <SmallAction
                        label="Stop"
                        disabled={Boolean(updatingId)}
                        onPress={() => void setStatus(objective, 'stopped')}
                      />
                    ) : null}
                  </View>
                </View>
                {assigningObjectiveId === objective.objective_id ? (
                  <View style={styles.assignmentEditor}>
                    <Text style={styles.fieldLabel}>DESTINATION EMPLOYEE</Text>
                    <View style={styles.choiceWrap}>
                      {availableAssignees.map((target) => (
                        <Pressable
                          key={`${target.computerId}:${target.identityId}`}
                          accessibilityRole="radio"
                          accessibilityLabel={`${target.displayName}, ${target.role}, ${target.computerName}`}
                          accessibilityState={{ selected: assigneeIdentityId === target.identityId }}
                          style={[
                            styles.assigneeChoice,
                            assigneeIdentityId === target.identityId ? styles.choiceSelected : null,
                          ]}
                          onPress={() => setAssigneeIdentityId(target.identityId)}
                        >
                          <View style={styles.assigneeHeading}>
                            <Text style={styles.assigneeTitle}>{target.displayName}</Text>
                            <Text style={[
                              styles.scopeBadge,
                              target.scope === 'child' ? styles.scopeBadgeChild : null,
                            ]}>
                              {target.scope === 'child' ? 'CHILD' : 'LOCAL'}
                            </Text>
                          </View>
                          <Text style={styles.assigneeRoute} numberOfLines={1}>
                            {target.computerName} → {target.role}
                          </Text>
                          <Text style={styles.assigneeMeta}>
                            {target.status}{target.isDefault ? ' · default' : ''}
                          </Text>
                        </Pressable>
                      ))}
                    </View>
                    {!availableAssignees.length ? (
                      <Text style={styles.hint}>No ready employee identity is available on this company membership.</Text>
                    ) : null}
                    <TextInput
                      accessibilityLabel="Assignment scope"
                      multiline
                      style={[styles.input, styles.assignmentInput]}
                      value={assignmentPrompt}
                      placeholder="Describe this employee's exact part of the objective"
                      placeholderTextColor="#60768b"
                      onChangeText={setAssignmentPrompt}
                    />
                    <View style={styles.assignmentFooter}>
                      <Text style={styles.hint}>The route, objective, task, and resulting report stay linked.</Text>
                      <Pressable
                        accessibilityRole="button"
                        accessibilityState={{ disabled: routing || !assigneeIdentityId || !assignmentPrompt.trim() }}
                        disabled={routing || !assigneeIdentityId || !assignmentPrompt.trim()}
                        style={[
                          styles.saveAction,
                          routing || !assigneeIdentityId || !assignmentPrompt.trim() ? styles.disabled : null,
                        ]}
                        onPress={() => void assignObjective(objective)}
                      >
                        <Text style={styles.saveActionText}>{routing ? 'Routing…' : 'Send assignment'}</Text>
                      </Pressable>
                    </View>
                  </View>
                ) : null}
              </View>
            </View>
          ))}
        </View>
      ) : (
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>No durable objectives yet</Text>
          <Text style={styles.emptyBody}>Ordinary delegated tasks still work. Add an objective when several assignments should serve one measurable outcome.</Text>
        </View>
      )}

      <View style={styles.subheader}>
        <Text style={styles.eyebrow}>ASSIGNMENTS</Text>
        <Text style={styles.subheaderCount}>{tasks.length}</Text>
      </View>
      {tasks.length ? (
        <View style={styles.list}>
          {tasks.slice(0, 20).map((task) => (
            <View key={task.task_id} style={styles.compactRow}>
              <View style={styles.rowCopy}>
                <Text style={styles.rowTitle} numberOfLines={2}>{task.prompt}</Text>
                <Text style={styles.rowMeta}>{task.report_id ? `Report ${task.report_id.slice(-6)}` : 'No report yet'}</Text>
              </View>
              <Text style={styles.status}>{task.status}</Text>
            </View>
          ))}
        </View>
      ) : <Text style={styles.hint}>No assignments. Delegated work will appear here.</Text>}
      {reports.length ? <Text style={styles.hint}>{reports.length} structured report{reports.length === 1 ? '' : 's'} retained.</Text> : null}
      <CompanyOperatingRecordsPanel
        apiBaseUrl={apiBaseUrl}
        token={token}
        companyId={companyId}
        company={company}
        operatingModel={operatingModel}
        onChanged={onChanged}
      />
    </View>
  );
}

function SmallAction({ label, disabled, onPress }: { label: string; disabled: boolean; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} style={[styles.smallAction, disabled ? styles.disabled : null]} onPress={onPress}>
      <Text style={styles.smallActionText}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 20, paddingTop: 18, gap: 14 },
  header: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12 },
  eyebrow: { color: '#5fd3e5', fontSize: 8, fontWeight: '800', letterSpacing: 1.05 },
  title: { color: '#edf5fb', fontSize: 17, fontWeight: '800', marginTop: 3 },
  primaryAction: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 7, backgroundColor: '#17313b' },
  primaryActionText: { color: '#79ddea', fontSize: 10, fontWeight: '800' },
  editor: { borderRadius: 10, backgroundColor: '#0c1721', padding: 14, gap: 9 },
  editorTitle: { color: '#e7f0f7', fontSize: 13, fontWeight: '800' },
  editorBody: { color: '#7d93a6', fontSize: 10, lineHeight: 15, maxWidth: 720 },
  input: { minHeight: 38, borderRadius: 7, backgroundColor: '#101f2b', color: '#e2edf5', paddingHorizontal: 11, paddingVertical: 8, fontSize: 11, outlineStyle: 'none' } as any,
  multiline: { minHeight: 76, textAlignVertical: 'top' },
  choiceWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 5 },
  choice: { paddingHorizontal: 10, paddingVertical: 7, borderRadius: 999, backgroundColor: '#101f2b' },
  choiceSelected: { backgroundColor: '#1b3a44' },
  choiceText: { color: '#758b9e', fontSize: 9, textTransform: 'capitalize' },
  choiceTextSelected: { color: '#73dbe7', fontWeight: '800' },
  reviewNote: { color: '#8ea3b5', fontSize: 9, lineHeight: 14, paddingVertical: 3 },
  footer: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  hint: { color: '#708599', fontSize: 10, lineHeight: 15 },
  saveAction: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: 7, backgroundColor: '#70d7e5' },
  saveActionText: { color: '#061219', fontSize: 10, fontWeight: '900' },
  disabled: { opacity: 0.45 },
  error: { color: '#f0a0a6', fontSize: 10, lineHeight: 14 },
  list: { borderTopWidth: 1, borderTopColor: '#1b2a39' },
  objectiveRow: { paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#172635', flexDirection: 'row', gap: 12 },
  compactRow: { minHeight: 56, paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: '#172635', flexDirection: 'row', alignItems: 'center', gap: 12 },
  rowCopy: { flex: 1, minWidth: 0 },
  rowHeader: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 },
  rowTitle: { color: '#e1ebf3', fontSize: 11, lineHeight: 15, fontWeight: '700', flex: 1 },
  rowMeta: { color: '#71879a', fontSize: 9, lineHeight: 14, marginTop: 3 },
  rowFooter: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginTop: 8 },
  assignmentEditor: { marginTop: 10, padding: 10, borderRadius: 8, backgroundColor: '#0f1d28', gap: 7 },
  fieldLabel: { color: '#758ca0', fontSize: 8, fontWeight: '800', letterSpacing: 0.7 },
  assigneeChoice: { width: 208, paddingHorizontal: 10, paddingVertical: 8, borderRadius: 7, backgroundColor: '#13232f' },
  assigneeHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 7 },
  assigneeTitle: { color: '#dce8f0', fontSize: 10, fontWeight: '800', flex: 1 },
  assigneeRoute: { color: '#8da4b6', fontSize: 8, marginTop: 4 },
  assigneeMeta: { color: '#70879a', fontSize: 8, marginTop: 2, textTransform: 'capitalize' },
  scopeBadge: { color: '#72dce8', fontSize: 7, fontWeight: '900', letterSpacing: 0.5 },
  scopeBadgeChild: { color: '#f2c86f' },
  assignmentInput: { minHeight: 68, textAlignVertical: 'top' },
  assignmentFooter: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  tiny: { color: '#62798d', fontSize: 8, textTransform: 'capitalize' },
  status: { color: '#6fd8e6', fontSize: 8, fontWeight: '900', textTransform: 'uppercase' },
  actions: { flexDirection: 'row', gap: 5 },
  smallAction: { paddingHorizontal: 9, paddingVertical: 5, borderRadius: 6, backgroundColor: '#132a35' },
  smallActionText: { color: '#70d7e5', fontSize: 8, fontWeight: '800' },
  empty: { minHeight: 72, paddingVertical: 13, paddingHorizontal: 14, borderRadius: 9, backgroundColor: '#0c1721' },
  emptyTitle: { color: '#d9e5ef', fontSize: 12, fontWeight: '800' },
  emptyBody: { color: '#758a9d', fontSize: 10, lineHeight: 15, marginTop: 4, maxWidth: 720 },
  subheader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 3 },
  subheaderCount: { color: '#6fd8e6', fontSize: 12, fontWeight: '900' },
});
