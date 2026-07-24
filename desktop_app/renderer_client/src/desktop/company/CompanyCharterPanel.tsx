import { useEffect, useState, type Dispatch, type SetStateAction } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { updateCompany, type CompanyDetail } from '@/lib/appApi';
import { userFacingError } from '../../../lib/diagnostics';


type Props = {
  apiBaseUrl: string;
  token: string;
  companyId: string;
  company: CompanyDetail | null;
  onChanged: () => Promise<void>;
};

const STEPS = [
  'Starting point',
  'Owner authority',
  'Identity & purpose',
  'Current reality',
  'Goals',
  'Organization',
  'Operating model',
  'Tools & placement',
  'Readiness',
];

function text(value: unknown) {
  return String(value ?? '').trim();
}

function lines(value: unknown) {
  return Array.isArray(value) ? value.map(text).filter(Boolean).join('\n') : text(value);
}

function lineList(value: string) {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
}

export function CompanyCharterPanel({
  apiBaseUrl,
  token,
  companyId,
  company,
  onChanged,
}: Props) {
  const manifest = company?.manifest || {};
  const [editing, setEditing] = useState(false);
  const [step, setStep] = useState(Number(manifest.onboarding_step || 1));
  const [form, setForm] = useState(() => formFromManifest(manifest));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm(formFromManifest(company?.manifest || {}));
    setStep(Math.max(1, Math.min(9, Number(company?.manifest?.onboarding_step || 1))));
  }, [company?.company_id, company?.revision]);

  const saveStep = async (nextStep: number, finish = false) => {
    setSaving(true);
    setError(null);
    try {
      const manifestUpdate = manifestFromForm(form, finish ? 9 : nextStep);
      await updateCompany(apiBaseUrl, token, companyId, {
        display_name: form.displayName.trim() || 'My Company',
        onboarding_status: finish ? 'complete' : 'in_progress',
        manifest: manifestUpdate,
      });
      setStep(nextStep);
      if (finish) setEditing(false);
      await onChanged();
    } catch (reason) {
      setError(userFacingError(reason, 'Company onboarding could not be saved.'));
    } finally {
      setSaving(false);
    }
  };

  const hasCharter = ['purpose', 'offer', 'customers', 'business_model'].some((key) => text(manifest[key]));
  const complete = text(manifest.onboarding_status) === 'complete';

  if (!editing) {
    return (
      <View style={styles.content}>
        <View style={styles.header}>
          <View>
            <Text style={styles.eyebrow}>DURABLE DIRECTION</Text>
            <Text style={styles.title}>Company charter</Text>
          </View>
          <Pressable accessibilityRole="button" style={styles.primaryAction} onPress={() => setEditing(true)}>
            <Text style={styles.primaryActionText}>{complete ? 'Edit setup' : 'Begin setup'}</Text>
          </Pressable>
        </View>
        {hasCharter ? (
          <View style={styles.definitionList}>
            <Definition label="Purpose" value={text(manifest.purpose)} />
            <Definition label="Offer" value={text(manifest.offer)} />
            <Definition label="Customers" value={text(manifest.customers)} />
            <Definition label="Business model" value={text(manifest.business_model)} />
          </View>
        ) : (
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>Business onboarding is optional</Text>
            <Text style={styles.emptyBody}>
              This company already works as a general assistant. Add business direction only when you want it to pursue durable outcomes.
            </Text>
          </View>
        )}
        <View style={styles.facts}>
          <Fact label="Root" value={text(manifest.root_computer_id) || 'This computer'} />
          <Fact label="Onboarding" value={(text(manifest.onboarding_status) || 'not started').replace(/_/g, ' ')} />
          <Fact label="Storage" value="Encrypted locally" />
          <Fact label="Cloud account" value="Not required" />
        </View>
      </View>
    );
  }

  return (
    <View style={styles.content}>
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>OPTIONAL BUSINESS ONBOARDING</Text>
          <Text style={styles.title}>{STEPS[step - 1]}</Text>
          <Text style={styles.stepText}>Step {step} of 9 · saved locally to this company</Text>
        </View>
        <Pressable accessibilityRole="button" style={styles.closeAction} onPress={() => setEditing(false)}>
          <Text style={styles.closeActionText}>Close</Text>
        </Pressable>
      </View>
      <View style={styles.progress}>
        {STEPS.map((label, index) => (
          <Pressable
            key={label}
            accessibilityRole="button"
            accessibilityLabel={`Step ${index + 1}: ${label}`}
            style={[styles.progressStep, index + 1 <= step ? styles.progressStepActive : null]}
            onPress={() => setStep(index + 1)}
          />
        ))}
      </View>

      <View style={styles.editor}>
        {step === 1 ? <StartingPoint form={form} setForm={setForm} /> : null}
        {step === 2 ? <OwnerAuthority form={form} setForm={setForm} /> : null}
        {step === 3 ? <IdentityPurpose form={form} setForm={setForm} /> : null}
        {step === 4 ? <CurrentReality form={form} setForm={setForm} /> : null}
        {step === 5 ? <Goals form={form} setForm={setForm} /> : null}
        {step === 6 ? <Organization form={form} setForm={setForm} /> : null}
        {step === 7 ? <OperatingModel form={form} setForm={setForm} /> : null}
        {step === 8 ? <ToolsPlacement form={form} setForm={setForm} /> : null}
        {step === 9 ? <Readiness form={form} /> : null}
      </View>

      {error ? <Text style={styles.error}>{error}</Text> : null}
      <View style={styles.footer}>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: saving || step === 1 }}
          disabled={saving || step === 1}
          style={[styles.secondaryAction, step === 1 ? styles.disabled : null]}
          onPress={() => setStep((value) => Math.max(1, value - 1))}
        >
          <Text style={styles.secondaryActionText}>Back</Text>
        </Pressable>
        <Text style={styles.footerHint}>Unknown facts may stay blank. EmploAI will not invent them.</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: saving }}
          disabled={saving}
          style={[styles.saveAction, saving ? styles.disabled : null]}
          onPress={() => void saveStep(Math.min(9, step + 1), step === 9)}
        >
          <Text style={styles.saveActionText}>{saving ? 'Saving…' : step === 9 ? 'Launch operating cycle' : 'Save and continue'}</Text>
        </Pressable>
      </View>
    </View>
  );
}

type Form = ReturnType<typeof formFromManifest>;
type FormSetter = Dispatch<SetStateAction<Form>>;

function formFromManifest(manifest: Record<string, unknown>) {
  return {
    startingPoint: text(manifest.starting_point) || 'existing_business',
    operatorRole: text(manifest.operator_role) || 'Owner',
    reservedDecisions: lines(manifest.reserved_decisions),
    autonomousDecisions: lines(manifest.autonomous_decisions),
    reviewCadence: text(manifest.review_cadence) || 'Weekly',
    displayName: text(manifest.display_name) || 'My Company',
    purpose: text(manifest.purpose),
    offer: text(manifest.offer),
    customers: text(manifest.customers),
    customerProblem: text(manifest.customer_problem),
    promisedOutcome: text(manifest.promised_outcome),
    businessModel: text(manifest.business_model),
    stage: text(manifest.stage) || 'idea',
    operatingCurrency: text(manifest.operating_currency),
    timeZone: text(manifest.time_zone),
    jurisdictionNotes: text(manifest.jurisdiction_notes),
    currentReality: text(manifest.current_reality),
    knownConstraints: lines(manifest.hard_constraints),
    primaryOutcome: text(manifest.primary_outcome),
    successCriteria: text(manifest.primary_success_criteria),
    deadline: text(manifest.primary_deadline),
    maxRiskSpend: text(manifest.maximum_risk_or_spend),
    unacceptableOutcomes: lines(manifest.unacceptable_outcomes),
    organizationNotes: text(manifest.organization_notes),
    deferredPositions: lines(manifest.deferred_positions),
    operatingCadence: text(manifest.operating_cadence),
    approvalDefaults: text(manifest.external_action_default) || 'draft_only',
    toolsAndData: text(manifest.tools_and_data),
    placementNotes: text(manifest.fleet_placement_notes),
    setupGaps: lines(manifest.setup_gaps),
  };
}

function manifestFromForm(form: Form, onboardingStep: number) {
  return {
    starting_point: form.startingPoint,
    operator_role: form.operatorRole,
    reserved_decisions: lineList(form.reservedDecisions),
    autonomous_decisions: lineList(form.autonomousDecisions),
    review_cadence: form.reviewCadence,
    purpose: form.purpose,
    offer: form.offer,
    customers: form.customers,
    customer_problem: form.customerProblem,
    promised_outcome: form.promisedOutcome,
    business_model: form.businessModel,
    stage: form.stage,
    operating_currency: form.operatingCurrency || null,
    time_zone: form.timeZone || null,
    jurisdiction_notes: form.jurisdictionNotes || null,
    current_reality: form.currentReality,
    hard_constraints: lineList(form.knownConstraints),
    primary_outcome: form.primaryOutcome,
    primary_success_criteria: form.successCriteria,
    primary_deadline: form.deadline || null,
    maximum_risk_or_spend: form.maxRiskSpend,
    unacceptable_outcomes: lineList(form.unacceptableOutcomes),
    organization_notes: form.organizationNotes,
    deferred_positions: lineList(form.deferredPositions),
    operating_cadence: form.operatingCadence,
    external_action_default: form.approvalDefaults,
    tools_and_data: form.toolsAndData,
    fleet_placement_notes: form.placementNotes,
    setup_gaps: lineList(form.setupGaps),
    onboarding_step: onboardingStep,
  };
}

function StartingPoint({ form, setForm }: { form: Form; setForm: FormSetter }) {
  return (
    <>
      <Prompt title="Where are you starting?" body="Dismissing this setup keeps the default assistant company. No cloud login or hosted account is involved." />
      <Choice
        label="I already have a business"
        meta="Record verified existing operations and goals."
        selected={form.startingPoint === 'existing_business'}
        onPress={() => setForm((value) => ({ ...value, startingPoint: 'existing_business' }))}
      />
      <Choice
        label="Help me create a new business"
        meta="Start with idea selection and demand validation—not an invented organization."
        selected={form.startingPoint === 'new_business'}
        onPress={() => setForm((value) => ({ ...value, startingPoint: 'new_business' }))}
      />
    </>
  );
}

function OwnerAuthority({ form, setForm }: { form: Form; setForm: FormSetter }) {
  return (
    <>
      <Prompt title="The human operator retains ultimate authority" body="The CEO is an agent. The operator is the person controlling this root computer and may override, pause, or change anything." />
      <Field label="Your role" value={form.operatorRole} onChange={(operatorRole) => setForm((value) => ({ ...value, operatorRole }))} placeholder="Owner, founder, director…" />
      <Field multiline label="Decisions that must always come to you" value={form.reservedDecisions} onChange={(reservedDecisions) => setForm((value) => ({ ...value, reservedDecisions }))} placeholder="One decision per line" />
      <Field multiline label="Decisions the company may make without asking" value={form.autonomousDecisions} onChange={(autonomousDecisions) => setForm((value) => ({ ...value, autonomousDecisions }))} placeholder="One bounded decision per line" />
      <Field label="Preferred review cadence" value={form.reviewCadence} onChange={(reviewCadence) => setForm((value) => ({ ...value, reviewCadence }))} placeholder="Weekly" />
    </>
  );
}

function IdentityPurpose({ form, setForm }: { form: Form; setForm: FormSetter }) {
  return (
    <>
      <Prompt title="Name the company and its durable purpose" body="Unknown commercial details may stay blank." />
      <Field label="Company name" value={form.displayName} onChange={(displayName) => setForm((value) => ({ ...value, displayName }))} placeholder="My Company" />
      <Field label="One-sentence purpose" value={form.purpose} onChange={(purpose) => setForm((value) => ({ ...value, purpose }))} placeholder="Why this company exists" />
      <Field label="Products or services" value={form.offer} onChange={(offer) => setForm((value) => ({ ...value, offer }))} placeholder="What it offers" />
      <Field label="Target customers" value={form.customers} onChange={(customers) => setForm((value) => ({ ...value, customers }))} placeholder="Who it serves" />
      <Field label="Customer problem" value={form.customerProblem} onChange={(customerProblem) => setForm((value) => ({ ...value, customerProblem }))} placeholder="The verified problem, if known" />
      <Field label="Promised outcome" value={form.promisedOutcome} onChange={(promisedOutcome) => setForm((value) => ({ ...value, promisedOutcome }))} placeholder="What changes for the customer" />
      <Field label="Business model" value={form.businessModel} onChange={(businessModel) => setForm((value) => ({ ...value, businessModel }))} placeholder="How value and revenue work" />
      <ChoiceRow
        label="Stage"
        values={['idea', 'validation', 'pre-revenue', 'operating', 'scaling']}
        selected={form.stage}
        onSelect={(stage) => setForm((value) => ({ ...value, stage }))}
      />
    </>
  );
}

function CurrentReality({ form, setForm }: { form: Form; setForm: FormSetter }) {
  return (
    <>
      <Prompt title="Describe what already exists" body="Include customers, revenue, products, repositories, commitments, channels, available computers, and known limits. Unknown remains unknown." />
      <Field multiline label="Current reality" value={form.currentReality} onChange={(currentReality) => setForm((value) => ({ ...value, currentReality }))} placeholder="Verified facts only" />
      <Field multiline label="Hard constraints" value={form.knownConstraints} onChange={(knownConstraints) => setForm((value) => ({ ...value, knownConstraints }))} placeholder="One constraint per line" />
      <View style={styles.split}>
        <Field label="Operating currency" value={form.operatingCurrency} onChange={(operatingCurrency) => setForm((value) => ({ ...value, operatingCurrency }))} placeholder="Optional" compact />
        <Field label="Time zone" value={form.timeZone} onChange={(timeZone) => setForm((value) => ({ ...value, timeZone }))} placeholder="Optional" compact />
      </View>
      <Field label="Jurisdiction notes" value={form.jurisdictionNotes} onChange={(jurisdictionNotes) => setForm((value) => ({ ...value, jurisdictionNotes }))} placeholder="Relevant legal context; not legal advice" />
    </>
  );
}

function Goals({ form, setForm }: { form: Form; setForm: FormSetter }) {
  return (
    <>
      <Prompt title="Set the next outcome and its evidence gate" body="For an unvalidated idea, the first objective should normally validate a painful problem, a reachable buyer, and willingness to pay before product investment." />
      <Field label="Primary outcome" value={form.primaryOutcome} onChange={(primaryOutcome) => setForm((value) => ({ ...value, primaryOutcome }))} placeholder="The exact outcome requested by the operator" />
      <Field multiline label="Success or failure evidence" value={form.successCriteria} onChange={(successCriteria) => setForm((value) => ({ ...value, successCriteria }))} placeholder="Observable evidence and pass/fail threshold" />
      <Field label="Deadline" value={form.deadline} onChange={(deadline) => setForm((value) => ({ ...value, deadline }))} placeholder="Optional ISO date or plain-language deadline" />
      <Field label="Maximum risk or spend" value={form.maxRiskSpend} onChange={(maxRiskSpend) => setForm((value) => ({ ...value, maxRiskSpend }))} placeholder="A hard bound, if any" />
      <Field multiline label="Unacceptable outcomes" value={form.unacceptableOutcomes} onChange={(unacceptableOutcomes) => setForm((value) => ({ ...value, unacceptableOutcomes }))} placeholder="One outcome per line" />
    </>
  );
}

function Organization({ form, setForm }: { form: Form; setForm: FormSetter }) {
  return (
    <>
      <Prompt title="Keep the organization as small as the objective allows" body="Departments are optional and there are none by default. Hire positions only for work that is required now." />
      <Field multiline label="Organization notes" value={form.organizationNotes} onChange={(organizationNotes) => setForm((value) => ({ ...value, organizationNotes }))} placeholder="Needed positions, reporting lines, and independent review" />
      <Field multiline label="Positions intentionally deferred" value={form.deferredPositions} onChange={(deferredPositions) => setForm((value) => ({ ...value, deferredPositions }))} placeholder="One deferred position per line" />
    </>
  );
}

function OperatingModel({ form, setForm }: { form: Form; setForm: FormSetter }) {
  return (
    <>
      <Prompt title="Choose the working and review rhythm" body="Automations and schedules remain proposals until the operator activates them." />
      <Field multiline label="Operating cadence" value={form.operatingCadence} onChange={(operatingCadence) => setForm((value) => ({ ...value, operatingCadence }))} placeholder="Daily, weekly, monthly, incident, and reporting expectations" />
      <ChoiceRow
        label="External actions"
        values={['disabled', 'draft_only', 'approval_required', 'bounded_autonomous']}
        selected={form.approvalDefaults}
        onSelect={(approvalDefaults) => setForm((value) => ({ ...value, approvalDefaults }))}
      />
    </>
  );
}

function ToolsPlacement({ form, setForm }: { form: Form; setForm: FormSetter }) {
  return (
    <>
      <Prompt title="Record required tools, data, and computers" body="Requirements are not grants. Credentials need explicit local setup, and Fleet placement must respect the destination computer's owner and capability boundaries." />
      <Field multiline label="Tools, data, models, and credentials" value={form.toolsAndData} onChange={(toolsAndData) => setForm((value) => ({ ...value, toolsAndData }))} placeholder="Available and missing requirements" />
      <Field multiline label="Fleet placement notes" value={form.placementNotes} onChange={(placementNotes) => setForm((value) => ({ ...value, placementNotes }))} placeholder="Privacy, hardware, capacity, and preferred computer" />
      <Field multiline label="Setup gaps" value={form.setupGaps} onChange={(setupGaps) => setForm((value) => ({ ...value, setupGaps }))} placeholder="One blocker per line" />
    </>
  );
}

function Readiness({ form }: { form: Form }) {
  const gaps = lineList(form.setupGaps);
  return (
    <>
      <Prompt title="Review before the first operating cycle" body="Completing setup does not prove business validation or make every employee operationally ready." />
      <ReviewRow label="Company" value={form.displayName || 'My Company'} />
      <ReviewRow label="Operator" value={form.operatorRole || 'Owner'} />
      <ReviewRow label="Primary outcome" value={form.primaryOutcome || 'Not yet defined'} />
      <ReviewRow label="External actions" value={form.approvalDefaults.replace(/_/g, ' ')} />
      <ReviewRow label="Setup gaps" value={gaps.length ? `${gaps.length} unresolved` : 'None recorded'} tone={gaps.length ? 'warning' : 'success'} />
      <Text style={styles.readinessNote}>The CEO and default worker already remain available. Employees with incomplete job contracts cannot accept ordinary assignments.</Text>
    </>
  );
}

function Prompt({ title, body }: { title: string; body: string }) {
  return (
    <View style={styles.prompt}>
      <Text style={styles.promptTitle}>{title}</Text>
      <Text style={styles.promptBody}>{body}</Text>
    </View>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  multiline,
  compact,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  multiline?: boolean;
  compact?: boolean;
}) {
  return (
    <View style={compact ? styles.compactField : undefined}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        multiline={multiline}
        style={[styles.input, multiline ? styles.multiline : null]}
        value={value}
        placeholder={placeholder}
        placeholderTextColor="#60768b"
        onChangeText={onChange}
      />
    </View>
  );
}

function Choice({ label, meta, selected, onPress }: { label: string; meta: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="radio" accessibilityState={{ selected }} style={[styles.choice, selected ? styles.choiceSelected : null]} onPress={onPress}>
      <View style={[styles.radio, selected ? styles.radioSelected : null]} />
      <View style={styles.choiceCopy}>
        <Text style={styles.choiceTitle}>{label}</Text>
        <Text style={styles.choiceMeta}>{meta}</Text>
      </View>
    </Pressable>
  );
}

function ChoiceRow({ label, values, selected, onSelect }: { label: string; values: string[]; selected: string; onSelect: (value: string) => void }) {
  return (
    <View>
      <Text style={styles.fieldLabel}>{label}</Text>
      <View style={styles.choiceRow}>
        {values.map((value) => (
          <Pressable key={value} accessibilityRole="radio" accessibilityState={{ selected: selected === value }} style={[styles.pill, selected === value ? styles.pillSelected : null]} onPress={() => onSelect(value)}>
            <Text style={[styles.pillText, selected === value ? styles.pillTextSelected : null]}>{value.replace(/_/g, ' ')}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

function Definition({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <View style={styles.definitionRow}>
      <Text style={styles.definitionLabel}>{label}</Text>
      <Text style={styles.definitionValue}>{value}</Text>
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

function ReviewRow({ label, value, tone }: { label: string; value: string; tone?: 'warning' | 'success' }) {
  return (
    <View style={styles.reviewRow}>
      <Text style={styles.reviewLabel}>{label}</Text>
      <Text style={[styles.reviewValue, tone === 'warning' ? styles.warning : null, tone === 'success' ? styles.success : null]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 20, paddingTop: 18, gap: 14 },
  header: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12 },
  eyebrow: { color: '#5fd3e5', fontSize: 8, fontWeight: '800', letterSpacing: 1.05 },
  title: { color: '#edf5fb', fontSize: 17, fontWeight: '800', marginTop: 3 },
  stepText: { color: '#71879b', fontSize: 9, marginTop: 3 },
  primaryAction: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 7, backgroundColor: '#17313b' },
  primaryActionText: { color: '#79ddea', fontSize: 10, fontWeight: '800' },
  closeAction: { paddingHorizontal: 10, paddingVertical: 7 },
  closeActionText: { color: '#8399ac', fontSize: 10, fontWeight: '700' },
  progress: { flexDirection: 'row', gap: 3 },
  progressStep: { height: 3, flex: 1, borderRadius: 999, backgroundColor: '#172735' },
  progressStepActive: { backgroundColor: '#5ed2e3' },
  editor: { borderRadius: 10, backgroundColor: '#0c1721', padding: 14, gap: 10 },
  prompt: { marginBottom: 2 },
  promptTitle: { color: '#e7f0f7', fontSize: 13, fontWeight: '800' },
  promptBody: { color: '#7d93a6', fontSize: 10, lineHeight: 15, marginTop: 4, maxWidth: 760 },
  fieldLabel: { color: '#758ca0', fontSize: 8, fontWeight: '800', letterSpacing: 0.7, marginBottom: 4, marginTop: 2 },
  input: { minHeight: 38, borderRadius: 7, backgroundColor: '#101f2b', color: '#e2edf5', paddingHorizontal: 11, paddingVertical: 8, fontSize: 11, outlineStyle: 'none' } as any,
  multiline: { minHeight: 76, textAlignVertical: 'top' },
  split: { flexDirection: 'row', gap: 8 },
  compactField: { flex: 1 },
  choice: { minHeight: 58, padding: 10, flexDirection: 'row', alignItems: 'center', gap: 10, borderRadius: 8, backgroundColor: '#101e29' },
  choiceSelected: { backgroundColor: '#18343e' },
  radio: { width: 9, height: 9, borderRadius: 999, borderWidth: 1, borderColor: '#5d788d' },
  radioSelected: { borderColor: '#70dce9', backgroundColor: '#70dce9' },
  choiceCopy: { flex: 1 },
  choiceTitle: { color: '#dfeaf2', fontSize: 11, fontWeight: '800' },
  choiceMeta: { color: '#71879a', fontSize: 9, lineHeight: 13, marginTop: 2 },
  choiceRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 5 },
  pill: { paddingHorizontal: 10, paddingVertical: 7, borderRadius: 999, backgroundColor: '#101f2b' },
  pillSelected: { backgroundColor: '#1b3a44' },
  pillText: { color: '#758b9e', fontSize: 9, textTransform: 'capitalize' },
  pillTextSelected: { color: '#73dbe7', fontWeight: '800' },
  footer: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  footerHint: { flex: 1, color: '#687f93', fontSize: 9, textAlign: 'center' },
  secondaryAction: { paddingHorizontal: 12, paddingVertical: 9, borderRadius: 7, backgroundColor: '#101e29' },
  secondaryActionText: { color: '#92a5b5', fontSize: 10, fontWeight: '800' },
  saveAction: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: 7, backgroundColor: '#70d7e5' },
  saveActionText: { color: '#061219', fontSize: 10, fontWeight: '900' },
  disabled: { opacity: 0.45 },
  error: { color: '#f0a0a6', fontSize: 10, lineHeight: 14 },
  definitionList: { borderTopWidth: 1, borderTopColor: '#1b2a39' },
  definitionRow: { minHeight: 56, borderBottomWidth: 1, borderBottomColor: '#172635', paddingVertical: 10, flexDirection: 'row', gap: 20 },
  definitionLabel: { width: 120, color: '#71879c', fontSize: 10, fontWeight: '700' },
  definitionValue: { flex: 1, color: '#dfeaf3', fontSize: 11, lineHeight: 16 },
  empty: { minHeight: 72, paddingVertical: 13, paddingHorizontal: 14, borderRadius: 9, backgroundColor: '#0c1721' },
  emptyTitle: { color: '#d9e5ef', fontSize: 12, fontWeight: '800' },
  emptyBody: { color: '#758a9d', fontSize: 10, lineHeight: 15, marginTop: 4, maxWidth: 720 },
  facts: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  fact: { minWidth: 150, paddingVertical: 10, paddingHorizontal: 12, borderRadius: 8, backgroundColor: '#0d1923' },
  factLabel: { color: '#6f8498', fontSize: 8, fontWeight: '800', letterSpacing: 0.7, textTransform: 'uppercase' },
  factValue: { color: '#dae6ef', fontSize: 11, fontWeight: '700', marginTop: 4, textTransform: 'capitalize' },
  reviewRow: { minHeight: 42, flexDirection: 'row', alignItems: 'center', gap: 14, borderBottomWidth: 1, borderBottomColor: '#172635' },
  reviewLabel: { width: 130, color: '#72889b', fontSize: 9, fontWeight: '700' },
  reviewValue: { flex: 1, color: '#dce8f0', fontSize: 10 },
  warning: { color: '#dda85b' },
  success: { color: '#61d3a0' },
  readinessNote: { color: '#73899c', fontSize: 10, lineHeight: 15, marginTop: 4 },
});
