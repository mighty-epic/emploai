import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  createCompanyHandoff,
  createCompanyInitiative,
  createCompanyRecurringOperation,
  createCompanyRunbook,
  fetchJobs,
  updateCompanyInitiativeStatus,
  updateCompanyRecurringOperationStatus,
  updateCompanyRunbookStatus,
  type CompanyDetail,
  type CompanyOperatingModel,
  type ScheduledJob,
} from '@/lib/appApi';
import { userFacingError } from '../../../lib/diagnostics';


type Section = 'initiatives' | 'runbooks' | 'operations' | 'handoffs';

type Props = {
  apiBaseUrl: string;
  token: string;
  companyId: string;
  company: CompanyDetail | null;
  operatingModel: CompanyOperatingModel | null;
  onChanged: () => Promise<void>;
};

function lines(value: string) {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function CompanyOperatingRecordsPanel({
  apiBaseUrl,
  token,
  companyId,
  company,
  operatingModel,
  onChanged,
}: Props) {
  const [section, setSection] = useState<Section>('initiatives');
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState('');
  const [outcomeOrTrigger, setOutcomeOrTrigger] = useState('');
  const [details, setDetails] = useState('');
  const [secondary, setSecondary] = useState('');
  const [fromIdentityId, setFromIdentityId] = useState('');
  const [toIdentityId, setToIdentityId] = useState('');
  const [objectiveId, setObjectiveId] = useState<string | null>(null);
  const [runbookId, setRunbookId] = useState<string | null>(null);
  const [automationId, setAutomationId] = useState<string | null>(null);
  const [operationSchedule, setOperationSchedule] = useState('');
  const [operationOutput, setOperationOutput] = useState('');
  const [operationEscalation, setOperationEscalation] = useState('60');
  const [automations, setAutomations] = useState<ScheduledJob[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const initiatives = operatingModel?.initiatives || company?.initiatives || [];
  const runbooks = operatingModel?.runbooks || company?.runbooks || [];
  const operations = operatingModel?.recurring_operations || company?.recurring_operations || [];
  const handoffs = operatingModel?.handoffs || company?.handoffs || [];
  const objectives = operatingModel?.objectives || company?.objectives || [];
  const employees = company?.employees.filter((item) => item.status === 'active') || [];

  useEffect(() => {
    let disposed = false;
    void fetchJobs(apiBaseUrl, token)
      .then((items) => {
        if (!disposed) setAutomations(items);
      })
      .catch(() => {
        if (!disposed) setAutomations([]);
      });
    return () => {
      disposed = true;
    };
  }, [apiBaseUrl, token]);

  const reset = () => {
    setTitle('');
    setOutcomeOrTrigger('');
    setDetails('');
    setSecondary('');
    setFromIdentityId('');
    setToIdentityId('');
    setObjectiveId(null);
    setRunbookId(null);
    setAutomationId(null);
    setOperationSchedule('');
    setOperationOutput('');
    setOperationEscalation('60');
  };

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      if (section === 'initiatives') {
        await createCompanyInitiative(apiBaseUrl, token, companyId, {
          title: title.trim(),
          outcome: outcomeOrTrigger.trim(),
          owner_identity_id: employees.find((item) => item.system_role === 'manager')?.identity_id || null,
          objective_ids: [],
          plan: lines(details),
          risks: lines(secondary),
        });
      } else if (section === 'runbooks') {
        await createCompanyRunbook(apiBaseUrl, token, companyId, {
          title: title.trim(),
          trigger: outcomeOrTrigger.trim(),
          steps: lines(details).map((action, index) => ({
            order: index + 1,
            action,
          })),
          required_roles: [],
          approval_gates: lines(secondary).map((rule) => ({
            rule,
            authority: 'human_operator',
          })),
          evidence_requirements: [],
        });
      } else if (section === 'operations') {
        await createCompanyRecurringOperation(
          apiBaseUrl,
          token,
          companyId,
          {
            title: title.trim(),
            trigger: outcomeOrTrigger.trim(),
            owner_identity_id: employees.find((item) => item.system_role === 'manager')?.identity_id || null,
            runbook_id: runbookId || '',
            automation_id: automationId,
            schedule: operationSchedule.trim(),
            inputs: lines(details),
            expected_output: operationOutput.trim(),
            quality_gate: secondary.trim(),
            escalation_minutes: Math.max(1, Number(operationEscalation) || 60),
          },
        );
      } else {
        await createCompanyHandoff(apiBaseUrl, token, companyId, {
          from_identity_id: fromIdentityId,
          to_identity_id: toIdentityId,
          deliverable: details.trim(),
          acceptance_criteria: secondary.trim(),
          objective_id: objectiveId,
          evidence: [],
          open_questions: [],
        });
      }
      reset();
      setCreating(false);
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, `The ${section.slice(0, -1)} could not be saved.`));
    } finally {
      setSaving(false);
    }
  };

  const canSave = section === 'handoffs'
    ? Boolean(fromIdentityId && toIdentityId && details.trim() && secondary.trim())
    : section === 'operations'
      ? Boolean(
        title.trim()
        && outcomeOrTrigger.trim()
        && runbookId
        && operationSchedule.trim()
        && operationOutput.trim()
        && secondary.trim()
      )
      : Boolean(title.trim() && outcomeOrTrigger.trim() && details.trim());

  return (
    <View style={styles.section}>
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>OPERATING RECORDS</Text>
          <Text style={styles.title}>Plans, playbooks, and handoffs</Text>
        </View>
        <Pressable accessibilityRole="button" style={styles.newAction} onPress={() => setCreating((current) => !current)}>
          <Text style={styles.newActionText}>{creating ? 'Close' : 'New'}</Text>
        </Pressable>
      </View>

      <View accessibilityRole="tablist" style={styles.tabs}>
        {([
          ['initiatives', initiatives.length],
          ['runbooks', runbooks.length],
          ['operations', operations.length],
          ['handoffs', handoffs.length],
        ] as Array<[Section, number]>).map(([id, count]) => (
          <Pressable
            key={id}
            accessibilityRole="tab"
            accessibilityState={{ selected: section === id }}
            style={[styles.tab, section === id ? styles.tabSelected : null]}
            onPress={() => {
              setSection(id);
              setCreating(false);
              reset();
            }}
          >
            <Text style={[styles.tabText, section === id ? styles.tabTextSelected : null]}>
              {id} · {count}
            </Text>
          </Pressable>
        ))}
      </View>

      {creating ? (
        <View style={styles.editor}>
          {section !== 'handoffs' ? (
            <>
              <TextInput
                accessibilityLabel={`${section} title`}
                style={styles.input}
                value={title}
                placeholder={section === 'initiatives'
                  ? 'Initiative title'
                  : section === 'operations'
                    ? 'Recurring operation title'
                    : 'Runbook title'}
                placeholderTextColor="#60768b"
                onChangeText={setTitle}
              />
              <TextInput
                accessibilityLabel={section === 'initiatives' ? 'Initiative outcome' : `${section} trigger`}
                style={styles.input}
                value={outcomeOrTrigger}
                placeholder={section === 'initiatives' ? 'Measurable initiative outcome' : 'Exact condition that starts this runbook'}
                placeholderTextColor="#60768b"
                onChangeText={setOutcomeOrTrigger}
              />
              {section === 'operations' ? (
                <>
                  <Text style={styles.label}>REVIEWED RUNBOOK</Text>
                  <View style={styles.choiceWrap}>
                    {runbooks.map((runbook) => (
                      <Pressable
                        key={runbook.runbook_id}
                        accessibilityRole="radio"
                        accessibilityState={{ selected: runbookId === runbook.runbook_id }}
                        style={[styles.choice, runbookId === runbook.runbook_id ? styles.choiceSelected : null]}
                        onPress={() => setRunbookId(runbook.runbook_id)}
                      >
                        <Text style={styles.choiceText}>{runbook.title} · {runbook.status}</Text>
                      </Pressable>
                    ))}
                  </View>
                  {!runbooks.length ? (
                    <Text style={styles.hint}>Create a runbook before defining a recurring operation.</Text>
                  ) : null}
                  <Text style={styles.label}>AUTOMATION · OPTIONAL UNTIL ACTIVATION</Text>
                  <View style={styles.choiceWrap}>
                    <Pressable
                      accessibilityRole="radio"
                      accessibilityState={{ selected: !automationId }}
                      style={[styles.choice, !automationId ? styles.choiceSelected : null]}
                      onPress={() => setAutomationId(null)}
                    >
                      <Text style={styles.choiceText}>Link later</Text>
                    </Pressable>
                    {automations.map((automation) => (
                      <Pressable
                        key={automation.id}
                        accessibilityRole="radio"
                        accessibilityState={{ selected: automationId === automation.id }}
                        style={[styles.choice, automationId === automation.id ? styles.choiceSelected : null]}
                        onPress={() => setAutomationId(automation.id)}
                      >
                        <Text style={styles.choiceText}>{automation.name} · {automation.enabled ? 'enabled' : 'paused'}</Text>
                      </Pressable>
                    ))}
                  </View>
                  <TextInput
                    accessibilityLabel="Recurring operation schedule"
                    style={styles.input}
                    value={operationSchedule}
                    placeholder="Human-readable schedule, for example Weekdays at 09:00"
                    placeholderTextColor="#60768b"
                    onChangeText={setOperationSchedule}
                  />
                </>
              ) : null}
            </>
          ) : (
            <>
              <View style={styles.identityGrid}>
                <IdentityChoices
                  label="FROM"
                  employees={employees}
                  selected={fromIdentityId}
                  onSelect={setFromIdentityId}
                />
                <IdentityChoices
                  label="TO"
                  employees={employees}
                  selected={toIdentityId}
                  onSelect={setToIdentityId}
                />
              </View>
              {objectives.length ? (
                <View>
                  <Text style={styles.label}>OBJECTIVE · OPTIONAL</Text>
                  <View style={styles.choiceWrap}>
                    <Pressable
                      accessibilityRole="radio"
                      accessibilityState={{ selected: !objectiveId }}
                      style={[styles.choice, !objectiveId ? styles.choiceSelected : null]}
                      onPress={() => setObjectiveId(null)}
                    >
                      <Text style={styles.choiceText}>No objective</Text>
                    </Pressable>
                    {objectives.map((objective) => (
                      <Pressable
                        key={objective.objective_id}
                        accessibilityRole="radio"
                        accessibilityState={{ selected: objectiveId === objective.objective_id }}
                        style={[styles.choice, objectiveId === objective.objective_id ? styles.choiceSelected : null]}
                        onPress={() => setObjectiveId(objective.objective_id)}
                      >
                        <Text style={styles.choiceText}>{objective.outcome}</Text>
                      </Pressable>
                    ))}
                  </View>
                </View>
              ) : null}
            </>
          )}
          <TextInput
            accessibilityLabel={`${section} primary details`}
            multiline
            style={[styles.input, styles.multiline]}
            value={details}
            placeholder={section === 'initiatives'
              ? 'Plan · one step per line'
              : section === 'runbooks'
                ? 'Ordered actions · one step per line'
                : section === 'operations'
                  ? 'Required inputs · one per line'
                : 'Deliverable being handed over'}
            placeholderTextColor="#60768b"
            onChangeText={setDetails}
          />
          <TextInput
            accessibilityLabel={`${section} secondary details`}
            multiline
            style={[styles.input, styles.multiline]}
            value={secondary}
            placeholder={section === 'initiatives'
              ? 'Known risks · one per line'
              : section === 'runbooks'
                ? 'Human approval gates · one per line'
                : section === 'operations'
                  ? 'Quality gate for every run'
                : 'Acceptance criteria'}
            placeholderTextColor="#60768b"
            onChangeText={setSecondary}
          />
          {section === 'operations' ? (
            <View style={styles.operationFields}>
              <TextInput
                accessibilityLabel="Recurring operation expected output"
                multiline
                style={[styles.input, styles.multiline, styles.operationOutput]}
                value={operationOutput}
                placeholder="Report or deliverable produced by every run"
                placeholderTextColor="#60768b"
                onChangeText={setOperationOutput}
              />
              <TextInput
                accessibilityLabel="Recurring operation escalation minutes"
                keyboardType="number-pad"
                style={[styles.input, styles.escalationInput]}
                value={operationEscalation}
                placeholder="Escalate after minutes"
                placeholderTextColor="#60768b"
                onChangeText={setOperationEscalation}
              />
            </View>
          ) : null}
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <View style={styles.editorFooter}>
            <Text style={styles.hint}>
              {section === 'runbooks'
                ? 'New runbooks stay draft until activation is separately approved.'
                : section === 'operations'
                  ? 'Operations stay proposed. Activation requires an active runbook and a linked company-scoped automation.'
                : section === 'handoffs'
                  ? 'The recipient or owning manager must accept the handoff.'
                  : 'Initiatives coordinate objectives; they do not replace them.'}
            </Text>
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: saving || !canSave }}
              disabled={saving || !canSave}
              style={[styles.save, saving || !canSave ? styles.disabled : null]}
              onPress={() => void submit()}
            >
              <Text style={styles.saveText}>{saving ? 'Saving…' : 'Save'}</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      {section === 'initiatives' ? (
        initiatives.length ? initiatives.map((item) => (
          <RecordRow
            key={item.initiative_id}
            title={item.title}
            meta={`${item.outcome} · ${item.plan.length} steps`}
            status={item.status}
            action={initiativeAction(item.status)?.label}
            onAction={initiativeAction(item.status) ? async () => {
              await updateCompanyInitiativeStatus(
                apiBaseUrl,
                token,
                companyId,
                item.initiative_id,
                initiativeAction(item.status)!.status,
              );
              await onChanged();
            } : undefined}
          />
        )) : <Empty text="No initiatives. Use one when several objectives need a coordinated plan." />
      ) : null}
      {section === 'runbooks' ? (
        runbooks.length ? runbooks.map((item) => (
          <RecordRow
            key={item.runbook_id}
            title={item.title}
            meta={`${item.trigger} · ${item.steps.length} steps`}
            status={item.status}
            action={item.status === 'draft' ? 'Activate' : undefined}
            onAction={item.status === 'draft' ? async () => {
              await updateCompanyRunbookStatus(
                apiBaseUrl,
                token,
                companyId,
                item.runbook_id,
                'active',
                'The local root operator reviewed and activated this runbook.',
              );
              await onChanged();
            } : undefined}
          />
        )) : <Empty text="No runbooks. Ordinary work can continue without them." />
      ) : null}
      {section === 'operations' ? (
        operations.length ? operations.map((item) => {
          const linkedAutomation = automations.find((automation) => automation.id === item.automation_id);
          const canActivate = Boolean(
            item.status !== 'active'
            && item.status !== 'archived'
            && item.automation_id
            && linkedAutomation?.enabled
            && runbooks.find((runbook) => runbook.runbook_id === item.runbook_id)?.status === 'active',
          );
          const nextStatus = item.status === 'active' ? 'paused' : canActivate ? 'active' : null;
          return (
            <RecordRow
              key={item.operation_id}
              title={item.title}
              meta={`${item.schedule} · ${linkedAutomation?.name || 'automation not linked'} · output: ${item.expected_output}`}
              status={item.status}
              action={nextStatus === 'paused' ? 'Pause' : nextStatus === 'active' ? 'Activate' : undefined}
              onAction={nextStatus ? async () => {
                await updateCompanyRecurringOperationStatus(
                  apiBaseUrl,
                  token,
                  companyId,
                  item.operation_id,
                  nextStatus,
                  nextStatus === 'active'
                    ? 'The root operator reviewed the runbook and enabled automation.'
                    : 'The root operator paused this recurring operation.',
                );
                await onChanged();
              } : undefined}
            />
          );
        }) : <Empty text="No recurring operations. They are optional and stay proposed until deliberately activated." />
      ) : null}
      {section === 'handoffs' ? (
        handoffs.length ? handoffs.map((item: any) => (
          <RecordRow
            key={String(item.handoff_id)}
            title={String(item.deliverable || 'Handoff')}
            meta={`${identityName(employees, item.from_identity_id)} → ${identityName(employees, item.to_identity_id)}`}
            status={String(item.status || 'pending')}
          />
        )) : <Empty text="No handoffs. Add one when responsibility and acceptance move between employees." />
      ) : null}
    </View>
  );
}

function initiativeAction(status: string): { label: string; status: string } | null {
  if (status === 'proposed' || status === 'planned') return { label: 'Scope', status: 'scoped' };
  if (status === 'scoped') return { label: 'Approve', status: 'approved' };
  if (status === 'approved') return { label: 'Start', status: 'active' };
  if (status === 'completed') return { label: 'Review', status: 'reviewed' };
  return null;
}

function identityName(employees: CompanyDetail['employees'], identityId: unknown) {
  return employees.find((item) => item.identity_id === String(identityId || ''))?.display_name || 'Employee';
}

function IdentityChoices({
  label,
  employees,
  selected,
  onSelect,
}: {
  label: string;
  employees: CompanyDetail['employees'];
  selected: string;
  onSelect: (identityId: string) => void;
}) {
  return (
    <View style={styles.identityColumn}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.choiceWrap}>
        {employees.map((employee) => (
          <Pressable
            key={employee.identity_id}
            accessibilityRole="radio"
            accessibilityState={{ selected: employee.identity_id === selected }}
            style={[styles.choice, employee.identity_id === selected ? styles.choiceSelected : null]}
            onPress={() => onSelect(employee.identity_id)}
          >
            <Text style={styles.choiceText}>{employee.display_name}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

function RecordRow({
  title,
  meta,
  status,
  action,
  onAction,
}: {
  title: string;
  meta: string;
  status: string;
  action?: string;
  onAction?: () => Promise<void>;
}) {
  return (
    <View style={styles.row}>
      <View style={styles.rowCopy}>
        <Text style={styles.rowTitle}>{title}</Text>
        <Text style={styles.rowMeta} numberOfLines={2}>{meta}</Text>
      </View>
      {action && onAction ? (
        <Pressable accessibilityRole="button" style={styles.rowAction} onPress={() => void onAction()}>
          <Text style={styles.rowActionText}>{action}</Text>
        </Pressable>
      ) : null}
      <Text style={styles.status}>{status.replace(/_/g, ' ')}</Text>
    </View>
  );
}

function Empty({ text }: { text: string }) {
  return <Text style={styles.empty}>{text}</Text>;
}


const styles = StyleSheet.create({
  section: { marginTop: 8, paddingTop: 15, borderTopWidth: 1, borderTopColor: '#1b2a39', gap: 9 },
  header: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', gap: 10 },
  eyebrow: { color: '#5fd3e5', fontSize: 8, fontWeight: '900', letterSpacing: 0.8 },
  title: { color: '#e4edf5', fontSize: 13, fontWeight: '800', marginTop: 3 },
  newAction: { paddingHorizontal: 10, paddingVertical: 7, borderRadius: 7, backgroundColor: '#17313b' },
  newActionText: { color: '#79ddea', fontSize: 9, fontWeight: '800' },
  tabs: { flexDirection: 'row', gap: 4 },
  tab: { paddingHorizontal: 10, paddingVertical: 7, borderRadius: 7, backgroundColor: '#101e29' },
  tabSelected: { backgroundColor: '#183640' },
  tabText: { color: '#72889b', fontSize: 8, fontWeight: '800', textTransform: 'capitalize' },
  tabTextSelected: { color: '#73dbe7' },
  editor: { padding: 11, borderRadius: 8, backgroundColor: '#0d1a25', gap: 7 },
  input: { minHeight: 36, borderRadius: 7, backgroundColor: '#101f2b', color: '#e2edf5', paddingHorizontal: 10, paddingVertical: 8, fontSize: 10, outlineStyle: 'none' } as any,
  multiline: { minHeight: 58, textAlignVertical: 'top' },
  operationFields: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  operationOutput: { flex: 1, minWidth: 260 },
  escalationInput: { width: 180, alignSelf: 'stretch' },
  identityGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  identityColumn: { flex: 1, minWidth: 250, gap: 5 },
  label: { color: '#758ca0', fontSize: 8, fontWeight: '800', letterSpacing: 0.65 },
  choiceWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 4 },
  choice: { paddingHorizontal: 8, paddingVertical: 6, borderRadius: 6, backgroundColor: '#13232f' },
  choiceSelected: { backgroundColor: '#1b3a44' },
  choiceText: { color: '#94a8b8', fontSize: 8 },
  editorFooter: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  hint: { flex: 1, color: '#708599', fontSize: 9, lineHeight: 13 },
  save: { paddingHorizontal: 12, paddingVertical: 9, borderRadius: 7, backgroundColor: '#70d7e5' },
  saveText: { color: '#061219', fontSize: 9, fontWeight: '900' },
  disabled: { opacity: 0.45 },
  error: { color: '#f0a0a6', fontSize: 9 },
  row: { minHeight: 52, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#172635', flexDirection: 'row', alignItems: 'center', gap: 10 },
  rowCopy: { flex: 1, minWidth: 0 },
  rowTitle: { color: '#e0ebf3', fontSize: 10, fontWeight: '800' },
  rowMeta: { color: '#71879a', fontSize: 9, lineHeight: 13, marginTop: 2 },
  rowAction: { paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6, backgroundColor: '#132a35' },
  rowActionText: { color: '#70d7e5', fontSize: 8, fontWeight: '800' },
  status: { color: '#6fd8e6', fontSize: 8, fontWeight: '900', textTransform: 'uppercase' },
  empty: { color: '#708599', fontSize: 9, lineHeight: 14, paddingVertical: 8 },
});
