import { requestJson } from '../../lib/appHttp';
import { readActiveCompanyId } from './activeCompanyContext';

function isTransientSessionCreateError(error: unknown) {
  const message = error instanceof Error
    ? error.message.toLowerCase()
    : String(error).toLowerCase();
  return (
    message.includes('failed to fetch')
    || message.includes('network request failed')
    || message.includes('load failed')
    || message.includes('timed out')
  );
}

function wait(ms: number) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}
import type { AppProfile, CompanyContext, CompanyMigrationPreview, CompanyDeletionPreview, CompanyJobCatalog, CompanyJobTemplate, CompanyJobContract, CompanyObjective, CompanyObjectiveReview, CompanyOperatingModel, CompanyPolicy, CompanyPosition, CompanyInitiative, CompanyRunbook, CompanyRecurringOperation, SessionSummary, SessionMessage, SessionTimelineEvent, SessionDetail, FleetIdentity, FleetWorker, FleetTask, FleetReport, FleetGroup, FleetToolGrant, FleetWorkspaceBinding, FleetSnapshot, ArtifactSummary, ArtifactDetail, DeleteSessionResult, SessionSearchResult, ScheduledJob, JobCreatePayload, CronFeedItem, AutomationEventRun, ProcessWait, PlannerContract, RecoveryArchiveItem, RecoveryListResponse, PendingConfirmation, ConfirmationCreatePayload, WorkspaceRestoreResponse, ModelProviderGroup, AgentHistoryItem, PendingFile, UploadResponse, ContextCompaction, ContextUsage, TaskBoardSubGoal, TaskBoard, HeartbeatStatus, MemorySummary, AnalyticsSummary, SecuritySummary, ConfigEntry, AgentOverview, TelegramBotConfig, RuntimeWorkerStatus, RuntimeOrchestratorStatus, WorkspaceGitState, SidebarProjectState, SidebarSessionState, SidebarState, SidebarStateResult, VoiceRuntimeStatus, TaskBoardArmResult, AgentConfigurePayload, ToolPackUpdatePayload, SessionBotAssignmentPayload, SessionHeadlessEligibilityPayload, SessionSecurityPermissionPayload, HeadlessConfigurePayload, AgentAction, BridgeStatus, SkillSummary, SkillDetail, SkillLearnResult, SkillValidation, SubAgentTask, SubAgentStatus, MemorySearchResult, MemoryOperation, MemoryOperationResult, MemoryFact } from './appApiTypes';
export type { AppProfile, CompanyContext, CompanySummary, CompanyDetail, CompanyEmployee, CompanyMembership, CompanyMigrationPreview, CompanyDeletionPreview, CompanyJobCatalog, CompanyJobTemplate, CompanyPosition, CompanyJobContract, CompanyObjective, CompanyInitiative, CompanyRunbook, CompanyRecurringOperation, CompanyAssignment, CompanyReport, CompanyObjectiveReview, CompanyPolicy, CompanyOperatingModel, SessionSummary, SessionMessage, SessionTimelineEvent, SessionDetail, FleetIdentity, FleetWorker, FleetTask, FleetReport, FleetGroup, FleetToolGrant, FleetWorkspaceBinding, FleetSnapshot, ArtifactSummary, ArtifactDetail, DeleteSessionResult, SessionSearchResult, ScheduledJob, JobCreatePayload, CronFeedItem, AutomationEventRun, ProcessWait, PlannerContract, RecoveryArchiveItem, RecoveryListResponse, PendingConfirmation, ConfirmationCreatePayload, WorkspaceRestoreResponse, ModelProviderGroup, AgentHistoryItem, PendingFile, UploadResponse, ContextCompaction, ContextUsage, TaskBoardSubGoal, TaskBoard, HeartbeatStatus, MemorySummary, AnalyticsSummary, SecuritySummary, ConfigEntry, AgentOverview, TelegramBotConfig, RuntimeWorkerStatus, RuntimeOrchestratorStatus, WorkspaceGitState, SidebarProjectState, SidebarSessionState, SidebarState, SidebarStateResult, VoiceRuntimeStatus, TaskBoardArmResult, ToolPackUpdatePayload, AgentConfigurePayload, SessionBotAssignmentPayload, SessionHeadlessEligibilityPayload, SessionSecurityPermissionPayload, HeadlessConfigurePayload, AgentAction, BridgeStatus, SkillSummary, SkillDetail, SkillLearnResult, SkillValidation, SubAgentTask, SubAgentStatus, MemorySearchResult, MemoryOperation, MemoryOperationResult, MemoryFact } from './appApiTypes';
import type { ProjectOnboardingProfile, ProjectOnboardingGuideMessage, ProjectOnboardingToolRequirement, ProjectOnboardingSavePayload, ProjectOnboardingSummarizePayload, ProjectOnboardingResponse } from './appApiTypes';
export type { ProjectOnboardingProfile, ProjectOnboardingGuideMessage, ProjectOnboardingToolRequirement, ProjectOnboardingSavePayload, ProjectOnboardingSummarizePayload, ProjectOnboardingResponse } from './appApiTypes';


function authHeaders(token: string): Record<string, string> {
  const companyId = readActiveCompanyId();
  return {
    Authorization: `Bearer ${token}`,
    ...(companyId ? { 'X-EmploAI-Company-Id': companyId } : {}),
  };
}

function confirmationHeaders(confirmationId?: string | null): Record<string, string> {
  return confirmationId ? { 'X-EmploAI-Confirmation-Id': confirmationId } : {};
}

export async function fetchProfile(apiBaseUrl: string, token: string) {
  return requestJson<AppProfile>({
    scope: 'profile.me',
    url: `${apiBaseUrl}/api/app/me`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchCompanyContext(apiBaseUrl: string, token: string) {
  return requestJson<CompanyContext>({
    scope: 'company.context',
    url: `${apiBaseUrl}/api/companies/context`,
    init: { headers: authHeaders(token) },
  });
}

export async function selectCompanyContext(apiBaseUrl: string, token: string, companyId: string) {
  return requestJson<CompanyContext>({
    scope: 'company.select',
    url: `${apiBaseUrl}/api/companies/active`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ company_id: companyId }),
    },
  });
}

export async function updateCompany(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  payload: {
    display_name?: string;
    onboarding_status?: string;
    manifest?: Record<string, unknown>;
  },
) {
  return requestJson<CompanyContext['active_company']>({
    scope: 'company.update',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}`,
    init: {
      method: 'PATCH',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function fetchCompanyMigrationPreview(
  apiBaseUrl: string,
  token: string,
  companyId: string,
) {
  return requestJson<CompanyMigrationPreview>({
    scope: 'company.migration.preview',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/migration-preview`,
    init: { headers: authHeaders(token) },
  });
}

export async function completeCompanyMigration(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  verifiedBackupId: string,
) {
  return requestJson<Record<string, unknown>>({
    scope: 'company.migration.complete',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/migration-complete`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ verified_backup_id: verifiedBackupId }),
    },
  });
}

export async function fetchCompanyDeletionPreview(
  apiBaseUrl: string,
  token: string,
  companyId: string,
) {
  return requestJson<CompanyDeletionPreview>({
    scope: 'company.deletion.preview',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/deletion-preview`,
    init: { headers: authHeaders(token) },
  });
}

export async function deleteCompany(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  payload: {
    company_name_confirmation: string;
    active_work_action: 'cancel';
    final_backup_id?: string | null;
  },
  confirmationId: string,
) {
  return requestJson<Record<string, unknown>>({
    scope: 'company.delete',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}`,
    init: {
      method: 'DELETE',
      headers: {
        ...authHeaders(token),
        ...confirmationHeaders(confirmationId),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
  });
}

export async function fetchCompanyOperatingModel(apiBaseUrl: string, token: string, companyId: string) {
  return requestJson<CompanyOperatingModel>({
    scope: 'company.operating_model',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/operating-model`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchCompanyEligibleIdentities(
  apiBaseUrl: string,
  token: string,
  companyId: string,
) {
  return requestJson<{ company_id: string; items: FleetIdentity[] }>({
    scope: 'company.eligible_identities',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/eligible-identities`,
    init: { headers: authHeaders(token) },
  });
}

export async function changeCompanyPositionOccupant(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  positionId: string,
  payload: {
    identity_id?: string | null;
    move_from_position_id?: string | null;
    reason: string;
  },
) {
  return requestJson<Record<string, unknown>>({
    scope: 'company.position.occupant.change',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/positions/${encodeURIComponent(positionId)}/occupant`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function fetchCompanyJobCatalog(
  apiBaseUrl: string,
  token: string,
  options?: { query?: string; division?: string; limit?: number },
) {
  const params = new URLSearchParams();
  if (options?.query) params.set('query', options.query);
  if (options?.division) params.set('division', options.division);
  params.set('limit', String(options?.limit || 245));
  const query = params.toString();
  return requestJson<CompanyJobCatalog>({
    scope: 'company.job_catalog',
    url: `${apiBaseUrl}/api/company/job-catalog${query ? `?${query}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchCompanyJobTemplate(
  apiBaseUrl: string,
  token: string,
  templateId: string,
) {
  return requestJson<CompanyJobTemplate>({
    scope: 'company.job_template',
    url: `${apiBaseUrl}/api/company/job-catalog/${encodeURIComponent(templateId)}`,
    init: { headers: authHeaders(token) },
  });
}

export async function createCompanyPosition(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  payload: {
    title: string;
    template_id?: string | null;
    manager_identity_id?: string | null;
    department_id?: string | null;
    identity_id?: string | null;
    overlay?: Record<string, unknown>;
  },
) {
  return requestJson<{ position: CompanyPosition; job_contract: Record<string, unknown> }>({
    scope: 'company.position.create',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/positions`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function createCompanyDepartment(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  payload: {
    name: string;
    mandate: string;
    manager_identity_id?: string | null;
  },
) {
  return requestJson<Record<string, unknown>>({
    scope: 'company.department.create',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/departments`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function updateCompanyJobContract(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  jobContractId: string,
  payload: {
    mission?: string | null;
    responsibilities?: string[];
    non_responsibilities?: string[];
    deliverables?: string[];
    inputs?: string[];
    quality_gates?: string[];
    success_measures?: string[];
    reporting_cadence?: string | null;
    escalation_route?: string | null;
    approved_tool_packs?: string[];
    approved_workspace_ids?: string[];
    authority?: Record<string, unknown>;
    memory_policy?: Record<string, unknown>;
    resource_policy?: Record<string, unknown>;
    missing_requirements?: Array<Record<string, unknown>>;
  },
) {
  return requestJson<CompanyJobContract>({
    scope: 'company.job_contract.update',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/job-contracts/${encodeURIComponent(jobContractId)}`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function reviewCompanyJobReadiness(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  jobContractId: string,
  payload: {
    reviewer_identity_id?: string | null;
    checks: Record<string, boolean>;
    evidence: Array<Record<string, unknown>>;
    missing_requirements: Array<Record<string, unknown>>;
    limited_mode: boolean;
    limitations?: string | null;
  },
) {
  return requestJson<{
    readiness_review_id: string;
    status: string;
    checks: Record<string, boolean>;
    evidence: Array<Record<string, unknown>>;
    missing_requirements: Array<Record<string, unknown>>;
    limitations?: string | null;
  }>({
    scope: 'company.job_contract.readiness',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/job-contracts/${encodeURIComponent(jobContractId)}/readiness`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function createCompanyObjective(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  payload: {
    outcome: string;
    success_criteria: string;
    owner_identity_id?: string | null;
    priority?: string;
    due_at?: string | null;
    low_risk_auto_accept?: boolean;
    optional_proposals?: Array<Record<string, unknown>>;
  },
) {
  return requestJson<CompanyObjective>({
    scope: 'company.objective.create',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/objectives`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function updateCompanyObjectiveStatus(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  objectiveId: string,
  payload: { status: string; reason?: string | null },
) {
  return requestJson<CompanyObjective>({
    scope: 'company.objective.status',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/objectives/${encodeURIComponent(objectiveId)}/status`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function createCompanyInitiative(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  payload: {
    title: string;
    outcome: string;
    owner_identity_id?: string | null;
    objective_ids: string[];
    plan: string[];
    risks: string[];
    due_at?: string | null;
  },
) {
  return requestJson<CompanyInitiative>({
    scope: 'company.initiative.create',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/initiatives`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function updateCompanyInitiativeStatus(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  initiativeId: string,
  status: string,
) {
  return requestJson<CompanyInitiative>({
    scope: 'company.initiative.status',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/initiatives/${encodeURIComponent(initiativeId)}/status`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    },
  });
}

export async function createCompanyRunbook(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  payload: {
    title: string;
    trigger: string;
    steps: Array<Record<string, unknown>>;
    required_roles: string[];
    approval_gates: Array<Record<string, unknown>>;
    evidence_requirements: string[];
  },
) {
  return requestJson<CompanyRunbook>({
    scope: 'company.runbook.create',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/runbooks`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function updateCompanyRunbookStatus(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  runbookId: string,
  status: 'active' | 'archived',
  reviewNote: string,
) {
  return requestJson<CompanyRunbook>({
    scope: 'company.runbook.status',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/runbooks/${encodeURIComponent(runbookId)}/status`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, review_note: reviewNote }),
    },
  });
}

export async function createCompanyRecurringOperation(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  payload: {
    title: string;
    trigger: string;
    owner_identity_id?: string | null;
    runbook_id: string;
    automation_id?: string | null;
    schedule: string;
    inputs: string[];
    expected_output: string;
    quality_gate: string;
    escalation_minutes: number;
  },
) {
  return requestJson<CompanyRecurringOperation>({
    scope: 'company.recurring_operation.create',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/recurring-operations`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function applyCompanyEmergencyControl(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  payload: {
    scope: 'company' | 'assignment' | 'employee' | 'department' | 'runbook' | 'recurring_operation';
    target_id?: string | null;
    action: 'pause' | 'resume';
    reason: string;
  },
) {
  return requestJson<Record<string, unknown>>({
    scope: 'company.emergency_control',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/emergency-control`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function updateCompanyRecurringOperationStatus(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  operationId: string,
  status: 'active' | 'paused' | 'archived',
  reason: string,
) {
  return requestJson<CompanyRecurringOperation>({
    scope: 'company.recurring_operation.status',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/recurring-operations/${encodeURIComponent(operationId)}/status`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, reason }),
    },
  });
}

export async function createCompanyHandoff(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  payload: {
    from_identity_id: string;
    to_identity_id: string;
    deliverable: string;
    acceptance_criteria: string;
    objective_id?: string | null;
    assignment_id?: string | null;
    evidence?: Array<Record<string, unknown>>;
    open_questions?: string[];
  },
) {
  return requestJson<Record<string, unknown>>({
    scope: 'company.handoff.create',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/handoffs`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function reviewCompanyHandoff(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  handoffId: string,
  payload: {
    reviewer_identity_id?: string | null;
    decision: 'accepted' | 'rework_requested';
    rationale: string;
    rework_instructions?: string | null;
  },
) {
  return requestJson<Record<string, unknown>>({
    scope: 'company.handoff.review',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/handoffs/${encodeURIComponent(handoffId)}/review`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function publishCompanyKnowledge(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  payload: {
    title: string;
    content: string;
    provenance: Record<string, unknown>;
    sensitivity?: string;
    review_due_at?: string | null;
  },
) {
  return requestJson<Record<string, unknown>>({
    scope: 'company.knowledge.publish',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/knowledge`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function reviewCompanyKnowledge(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  knowledgeId: string,
  nextReviewDueAt?: string | null,
) {
  return requestJson<Record<string, unknown>>({
    scope: 'company.knowledge.review',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/knowledge/${encodeURIComponent(knowledgeId)}/review`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        next_review_due_at: nextReviewDueAt || null,
        review_note: 'The local root operator reviewed this published Company knowledge.',
      }),
    },
  });
}

export async function createCompanyMetric(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  payload: {
    name: string;
    definition: string;
    formula: string;
    unit: string;
    source: string;
    cadence?: string;
    owner_identity_id?: string | null;
    guardrails?: string[];
  },
) {
  return requestJson<Record<string, unknown>>({
    scope: 'company.metric.create',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/metrics`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function recordCompanyMetricObservation(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  metricId: string,
  payload: {
    value: unknown;
    period_start?: string | null;
    period_end?: string | null;
    confidence?: string;
    evidence?: Array<Record<string, unknown>>;
    note?: string | null;
  },
) {
  return requestJson<Record<string, unknown>>({
    scope: 'company.metric.observe',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/metrics/${encodeURIComponent(metricId)}/observations`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function recordCompanyFinancialEntry(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  payload: {
    entry_type: 'revenue' | 'cost';
    amount: number;
    currency: string;
    description: string;
    recognized_at: string;
    source: string;
    evidence?: Array<Record<string, unknown>>;
  },
) {
  return requestJson<Record<string, unknown>>({
    scope: 'company.financial_entry.create',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/financial-entries`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function routeCompanyObjectiveAssignment(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  objective: CompanyObjective,
  assigneeIdentityId: string,
  assignmentPrompt: string,
  options?: {
    continuationTaskId?: string | null;
    reworkForReportId?: string | null;
  },
) {
  const prompt = [
    `Company objective: ${objective.outcome}`,
    `Success criteria: ${objective.success_criteria}`,
    `Your assignment: ${assignmentPrompt}`,
    'Complete only the assigned scope. Treat any improvement beyond the operator objective as an optional proposal.',
    'Return a structured report with evidence, artifacts, blockers, and confidence for manager review.',
  ].join('\n\n');
  const routed = await requestJson<{
    route: Record<string, unknown>;
    state: string;
    task_id?: string | null;
    delegation_id?: string | null;
  }>({
    scope: 'company.objective.route_assignment',
    url: `${apiBaseUrl}/api/fleet/delegations/route`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scope: 'auto',
        identity: assigneeIdentityId,
        target_role: 'auto',
        prompt,
        continuation_task_id: options?.continuationTaskId || null,
        metadata: {
          company_id: companyId,
          objective_id: objective.objective_id,
          objective_outcome: objective.outcome,
          objective_success_criteria: objective.success_criteria,
          rework_for_report_id: options?.reworkForReportId || null,
        },
      }),
    },
  });
  const assignment = await requestJson<Record<string, unknown>>({
    scope: 'company.objective.link_assignment',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/objectives/${encodeURIComponent(objective.objective_id)}/assignments`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        assignee_identity_id: assigneeIdentityId,
        prompt: assignmentPrompt,
        task_id: routed.task_id || null,
        delegation_id: routed.delegation_id || null,
        route: routed.route || {},
        state: routed.state || 'queued',
      }),
    },
  });
  return { routed, assignment };
}

export async function reviewCompanyReport(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  payload: {
    report_id: string;
    objective_id?: string | null;
    reviewer_identity_id?: string | null;
    decision: string;
    rationale: string;
    rework_instructions?: string | null;
  },
) {
  return requestJson<CompanyObjectiveReview>({
    scope: 'company.report.review',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/report-reviews`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function createCompanyPolicy(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  payload: { title: string; rule: string; scope?: string; enforcement?: string },
) {
  return requestJson<CompanyPolicy>({
    scope: 'company.policy.create',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/policies`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function recordCompanyDecision(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  payload: {
    question: string;
    decision: string;
    rationale: string;
    scope?: string;
    related_record_ids?: string[];
  },
) {
  return requestJson<Record<string, unknown>>({
    scope: 'company.decision.record',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/decisions`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function exportCompanyBackup(
  apiBaseUrl: string,
  token: string,
  companyId: string,
  passphrase: string,
) {
  return requestJson<{
    backup: Record<string, unknown>;
    recovery_key: string;
  }>({
    scope: 'company.backup.export',
    url: `${apiBaseUrl}/api/companies/${encodeURIComponent(companyId)}/backup/export`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ passphrase }),
    },
  });
}

export async function fetchFleetSnapshot(apiBaseUrl: string, token: string) {
  return requestJson<FleetSnapshot>({
    scope: 'fleet.snapshot',
    url: `${apiBaseUrl}/api/fleet/snapshot`,
    init: { headers: authHeaders(token) },
  });
}

export async function setFleetActiveIdentity(
  apiBaseUrl: string,
  token: string,
  identityId: string,
  selectedChatId?: string | null,
  source = 'mobile',
) {
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.identity.active',
    url: `${apiBaseUrl}/api/fleet/active-identity`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        identity_id: identityId,
        selected_chat_id: selectedChatId || null,
        source,
      }),
    },
  });
}

export async function setFleetIdentityActiveChat(
  apiBaseUrl: string,
  token: string,
  identityId: string,
  chatId?: string | null,
  source = 'mobile',
) {
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.identity.chat',
    url: `${apiBaseUrl}/api/fleet/identities/${encodeURIComponent(identityId)}/active-chat`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chatId || null, source }),
    },
  });
}

export async function createFleetLocalWorker(
  apiBaseUrl: string,
  token: string,
  displayName: string,
  metadata?: Record<string, unknown>,
) {
  return requestJson<FleetWorker>({
    scope: 'fleet.worker.create_local',
    url: `${apiBaseUrl}/api/fleet/workers/local`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        display_name: displayName.trim(),
        metadata: { ...(metadata || {}), created_by: 'desktop_user_request' },
      }),
    },
  });
}

export async function createFleetEnrollment(
  apiBaseUrl: string,
  token: string,
  displayName?: string | null,
  expiresInSeconds?: number | null,
  metadata?: Record<string, unknown>,
) {
  return requestJson<{ enrollment_id: string; enrollment_token: string; expires_in_seconds: number; display_name?: string | null }>({
    scope: 'fleet.enrollment.create',
    url: `${apiBaseUrl}/api/fleet/enrollments`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        display_name: displayName || null,
        expires_in_seconds: expiresInSeconds || null,
        metadata: metadata || {},
      }),
    },
  });
}

export async function renameFleetWorker(
  apiBaseUrl: string,
  token: string,
  workerId: string,
  displayName: string,
  metadata?: Record<string, unknown>,
) {
  return requestJson<FleetWorker>({
    scope: 'fleet.worker.rename',
    url: `${apiBaseUrl}/api/fleet/workers/${encodeURIComponent(workerId)}`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name: displayName, metadata: metadata || {} }),
    },
  });
}

export async function resetFleetWorker(
  apiBaseUrl: string,
  token: string,
  workerId: string,
  reason?: string | null,
  metadata?: Record<string, unknown>,
  confirmationId?: string | null,
) {
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.worker.reset',
    url: `${apiBaseUrl}/api/fleet/workers/${encodeURIComponent(workerId)}/reset`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json', ...confirmationHeaders(confirmationId) },
      body: JSON.stringify({ reason: reason || null, metadata: metadata || {} }),
    },
  });
}

export async function deleteFleetWorker(
  apiBaseUrl: string,
  token: string,
  workerId: string,
  wipeState = true,
  confirmationId?: string | null,
) {
  const suffix = `?wipe_state=${wipeState ? 'true' : 'false'}`;
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.worker.delete',
    url: `${apiBaseUrl}/api/fleet/workers/${encodeURIComponent(workerId)}${suffix}`,
    init: { method: 'DELETE', headers: { ...authHeaders(token), ...confirmationHeaders(confirmationId) } },
  });
}

export async function stopFleetWorker(
  apiBaseUrl: string,
  token: string,
  workerId: string,
  reason?: string | null,
  metadata?: Record<string, unknown>,
) {
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.worker.stop',
    url: `${apiBaseUrl}/api/fleet/workers/${encodeURIComponent(workerId)}/stop`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason || null, metadata: metadata || {} }),
    },
  });
}

export async function stopAllFleetWorkers(
  apiBaseUrl: string,
  token: string,
  reason?: string | null,
  metadata?: Record<string, unknown>,
  confirmationId?: string | null,
) {
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.stop_all',
    url: `${apiBaseUrl}/api/fleet/stop-all`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json', ...confirmationHeaders(confirmationId) },
      body: JSON.stringify({ reason: reason || null, metadata: metadata || {} }),
    },
  });
}

export async function requestFleetWorkerPreview(apiBaseUrl: string, token: string, workerId: string) {
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.worker.preview',
    url: `${apiBaseUrl}/api/fleet/workers/${encodeURIComponent(workerId)}/preview`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    },
  });
}

export async function assignFleetWorkerTask(
  apiBaseUrl: string,
  token: string,
  workerId: string,
  prompt: string,
  metadata?: Record<string, unknown>,
  options?: { target_session_id?: string | null; target_mode?: string | null; workspace_id?: string | null; requires_workspace_write?: boolean },
) {
  return requestJson<FleetTask>({
    scope: 'fleet.task.assign',
    url: `${apiBaseUrl}/api/fleet/workers/${encodeURIComponent(workerId)}/tasks`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt,
        source: 'mobile',
        target_session_id: options?.target_session_id || null,
        target_mode: options?.target_mode || 'auto',
        metadata: metadata || {},
        workspace_id: options?.workspace_id || null,
        requires_workspace_write: Boolean(options?.requires_workspace_write),
      }),
    },
  });
}

export async function createFleetGroup(
  apiBaseUrl: string,
  token: string,
  displayName: string,
  workerIds: string[] = [],
  description?: string | null,
  metadata?: Record<string, unknown>,
) {
  return requestJson<FleetGroup>({
    scope: 'fleet.group.create',
    url: `${apiBaseUrl}/api/fleet/groups`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        display_name: displayName,
        description: description || null,
        worker_ids: workerIds,
        metadata: metadata || {},
      }),
    },
  });
}

export async function updateFleetGroup(
  apiBaseUrl: string,
  token: string,
  groupId: string,
  payload: { display_name: string; description?: string | null; worker_ids?: string[]; metadata?: Record<string, unknown> },
) {
  return requestJson<FleetGroup>({
    scope: 'fleet.group.update',
    url: `${apiBaseUrl}/api/fleet/groups/${encodeURIComponent(groupId)}`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        display_name: payload.display_name,
        description: payload.description || null,
        worker_ids: payload.worker_ids || [],
        metadata: payload.metadata || {},
      }),
    },
  });
}

export async function deleteFleetGroup(apiBaseUrl: string, token: string, groupId: string, confirmationId?: string | null) {
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.group.delete',
    url: `${apiBaseUrl}/api/fleet/groups/${encodeURIComponent(groupId)}`,
    init: { method: 'DELETE', headers: { ...authHeaders(token), ...confirmationHeaders(confirmationId) } },
  });
}

export async function assignFleetGroupTask(
  apiBaseUrl: string,
  token: string,
  groupId: string,
  prompt: string,
  metadata?: Record<string, unknown>,
  options?: { target_session_id?: string | null; target_mode?: string | null; workspace_id?: string | null; requires_workspace_write?: boolean },
  confirmationId?: string | null,
) {
  return requestJson<FleetTask[]>({
    scope: 'fleet.group.task.assign',
    url: `${apiBaseUrl}/api/fleet/groups/${encodeURIComponent(groupId)}/tasks`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json', ...confirmationHeaders(confirmationId) },
      body: JSON.stringify({
        prompt,
        source: 'mobile',
        target_session_id: options?.target_session_id || null,
        target_mode: options?.target_mode || 'auto',
        metadata: metadata || {},
        workspace_id: options?.workspace_id || null,
        requires_workspace_write: Boolean(options?.requires_workspace_write),
      }),
    },
  });
}

export async function continueFleetWorkerQueue(
  apiBaseUrl: string,
  token: string,
  workerId: string,
  reviewedReportId?: string | null,
  metadata?: Record<string, unknown>,
) {
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.worker.queue.continue',
    url: `${apiBaseUrl}/api/fleet/workers/${encodeURIComponent(workerId)}/queue/continue`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        reviewed_report_id: reviewedReportId || null,
        source: 'mobile',
        metadata: metadata || {},
      }),
    },
  });
}

export async function reorderFleetTasks(
  apiBaseUrl: string,
  token: string,
  workerId: string,
  taskIds: string[],
) {
  return requestJson<FleetTask[]>({
    scope: 'fleet.tasks.reorder',
    url: `${apiBaseUrl}/api/fleet/tasks/reorder`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ worker_id: workerId, task_ids: taskIds }),
    },
  });
}

export async function redirectFleetTask(
  apiBaseUrl: string,
  token: string,
  taskId: string,
  direction: string,
  metadata?: Record<string, unknown>,
) {
  return requestJson<FleetTask>({
    scope: 'fleet.task.redirect',
    url: `${apiBaseUrl}/api/fleet/tasks/${encodeURIComponent(taskId)}/redirect`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ direction, source: 'mobile', metadata: metadata || {} }),
    },
  });
}

export async function updateFleetTaskStatus(
  apiBaseUrl: string,
  token: string,
  taskId: string,
  status: string,
  metadata?: Record<string, unknown>,
) {
  return requestJson<FleetTask>({
    scope: 'fleet.task.status',
    url: `${apiBaseUrl}/api/fleet/tasks/${encodeURIComponent(taskId)}/status`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, metadata: metadata || {} }),
    },
  });
}

export async function decideFleetToolGrant(
  apiBaseUrl: string,
  token: string,
  grantId: string,
  approved: boolean,
  approvedTurns?: number | null,
) {
  return requestJson<FleetToolGrant>({
    scope: 'fleet.tool_grant.decide',
    url: `${apiBaseUrl}/api/fleet/tool-grants/${encodeURIComponent(grantId)}/decision`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        approved,
        approved_turns: approvedTurns || null,
        approved_by: 'mobile',
      }),
    },
  });
}

export async function searchFleetReports(
  apiBaseUrl: string,
  token: string,
  payload: { query?: string | null; worker?: string | null; status?: string | null; limit?: number },
) {
  return requestJson<{ reports: FleetReport[]; count: number }>({
    scope: 'fleet.reports.search',
    url: `${apiBaseUrl}/api/fleet/reports/search`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: payload.query || null,
        worker: payload.worker || null,
        status: payload.status || null,
        limit: payload.limit || 20,
      }),
    },
  });
}

export async function fetchSessions(apiBaseUrl: string, token: string) {
  return requestJson<SessionSummary[]>({
    scope: 'sessions.list',
    url: `${apiBaseUrl}/api/app/sessions`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchSessionDetail(apiBaseUrl: string, token: string, sessionId: string) {
  return requestJson<SessionDetail>({
    scope: 'sessions.detail',
    url: `${apiBaseUrl}/api/app/sessions/${sessionId}`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchSessionArtifacts(apiBaseUrl: string, token: string, sessionId: string) {
  return requestJson<ArtifactSummary[]>({
    scope: 'sessions.artifacts.list',
    url: `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}/artifacts`,
    init: { headers: authHeaders(token) },
  });
}

export async function uploadAppAttachment(
  apiBaseUrl: string,
  token: string,
  file: Blob,
  options?: { filename?: string | null; sessionId?: string | null },
) {
  const form = new FormData();
  const filename = String(options?.filename || (file as { name?: string }).name || 'upload').trim() || 'upload';
  form.append('file', file, filename);
  const sessionId = String(options?.sessionId || '').trim();
  const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
  return requestJson<UploadResponse>({
    scope: 'chat.upload',
    url: `${apiBaseUrl}/api/app/upload${query}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
      body: form,
    },
    timeoutMs: 60000,
  });
}

export async function fetchSessionArtifactDetail(apiBaseUrl: string, token: string, sessionId: string, artifactId: string) {
  return requestJson<ArtifactDetail>({
    scope: 'sessions.artifacts.detail',
    url: `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}/artifacts/${encodeURIComponent(artifactId)}`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchSessionArtifactBlob(apiBaseUrl: string, token: string, sessionId: string, artifactId: string) {
  const response = await fetch(
    `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}/artifacts/${encodeURIComponent(artifactId)}/download`,
    { headers: authHeaders(token) },
  );
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(text || `Artifact download failed (${response.status})`);
  }
  const disposition = response.headers.get('content-disposition') || '';
  const filenameMatch = disposition.match(/filename=\"?([^\";]+)\"?/i);
  return {
    blob: await response.blob(),
    filename: filenameMatch?.[1] || `${artifactId}.bin`,
    mimeType: response.headers.get('content-type') || 'application/octet-stream',
  };
}

export async function searchSessions(
  apiBaseUrl: string,
  token: string,
  query: string,
  limit = 40,
) {
  return requestJson<{ results: SessionSearchResult[] }>({
    scope: 'sessions.search',
    url: `${apiBaseUrl}/api/app/sessions/search`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query, limit }),
    },
  });
}

export async function appendSessionTimelineEvent(
  apiBaseUrl: string,
  token: string,
  sessionId: string,
  payload: {
    kind: string;
    title: string;
    content: string;
    tone?: 'neutral' | 'accent' | 'warn' | 'error';
    channel?: 'telegram' | 'app' | 'system';
    source_format?: string;
    metadata?: Record<string, unknown>;
    source_client_id?: string;
  }
) {
  return requestJson<{ event: SessionTimelineEvent }>({
    scope: 'session-timeline-append',
    url: `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}/timeline`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
  });
}

export async function createSession(
  apiBaseUrl: string,
  token: string,
  nameOrOptions?: string | {
    name?: string;
    workspace?: string;
    workspace_id?: string | null;
    workspace_binding_status?: string | null;
    telegram_bot_config_id?: string | null;
    enabled_tool_packs?: string[];
    security_permission_mode?: 'low' | 'standard' | 'full_permissions';
    headless_eligible?: boolean;
    fleet_identity_id?: string | null;
    fleet_identity_role?: string | null;
    fleet_worker_id?: string | null;
    fleet_task_id?: string | null;
  },
  workspaceArg?: string,
) {
  const payload = typeof nameOrOptions === 'string'
    ? { name: nameOrOptions, workspace: workspaceArg }
    : {
        name: nameOrOptions?.name,
        workspace: nameOrOptions?.workspace,
        workspace_id: nameOrOptions?.workspace_id,
        workspace_binding_status: nameOrOptions?.workspace_binding_status,
        telegram_bot_config_id: nameOrOptions?.telegram_bot_config_id,
        enabled_tool_packs: nameOrOptions?.enabled_tool_packs,
        security_permission_mode: nameOrOptions?.security_permission_mode,
        headless_eligible: nameOrOptions?.headless_eligible,
        fleet_identity_id: nameOrOptions?.fleet_identity_id,
        fleet_identity_role: nameOrOptions?.fleet_identity_role,
        fleet_worker_id: nameOrOptions?.fleet_worker_id,
        fleet_task_id: nameOrOptions?.fleet_task_id,
      };
  const request = () => requestJson<{ session: SessionDetail }>({
    scope: 'sessions.create',
    url: `${apiBaseUrl}/api/app/sessions`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
  });
  try {
    return await request();
  } catch (error) {
    if (!isTransientSessionCreateError(error)) {
      throw error;
    }
    await wait(900);
    return request();
  }
}

export async function activateSession(apiBaseUrl: string, token: string, sessionId: string) {
  return requestJson<SessionDetail>({
    scope: 'sessions.activate',
    url: `${apiBaseUrl}/api/app/sessions/${sessionId}/activate`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function deleteSession(apiBaseUrl: string, token: string, sessionId: string) {
  return requestJson<DeleteSessionResult>({
    scope: 'sessions.delete',
    url: `${apiBaseUrl}/api/app/sessions/${sessionId}`,
    init: {
      method: 'DELETE',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function renameSession(apiBaseUrl: string, token: string, sessionId: string, name: string) {
  return requestJson<SessionDetail>({
    scope: 'sessions.rename',
    url: `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    },
    timeoutMs: 30000,
  });
}

export async function updateSessionModeState(
  apiBaseUrl: string,
  token: string,
  sessionId: string,
  payload: { action: 'exit_plan' | 'dismiss_plan' | 'clear_goal'; reason?: string | null },
) {
  return requestJson<SessionDetail>({
    scope: 'sessions.mode',
    url: `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}/mode`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function fetchJobs(apiBaseUrl: string, token: string) {
  return requestJson<ScheduledJob[]>({
    scope: 'automations.list',
    url: `${apiBaseUrl}/api/app/automations`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchCronFeed(apiBaseUrl: string, token: string) {
  return requestJson<CronFeedItem[]>({
    scope: 'events.feed',
    url: `${apiBaseUrl}/api/app/events`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchAutomationEventRuns(apiBaseUrl: string, token: string) {
  return requestJson<AutomationEventRun[]>({
    scope: 'automations.runs',
    url: `${apiBaseUrl}/api/app/events/runs`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchProcessWaits(apiBaseUrl: string, token: string) {
  return requestJson<ProcessWait[]>({
    scope: 'automations.process_waits',
    url: `${apiBaseUrl}/api/app/events/process-waits`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchPlannerContracts(apiBaseUrl: string, token: string) {
  return requestJson<PlannerContract[]>({
    scope: 'automations.planner_contracts',
    url: `${apiBaseUrl}/api/app/events/planner-contracts`,
    init: { headers: authHeaders(token) },
  });
}

export async function cancelAutomationEventRun(apiBaseUrl: string, token: string, eventRunId: string, reason?: string, confirmationId?: string | null) {
  return requestJson<AutomationEventRun>({
    scope: 'automations.runs.cancel',
    url: `${apiBaseUrl}/api/app/events/runs/${encodeURIComponent(eventRunId)}/cancel`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json', ...confirmationHeaders(confirmationId) },
      body: JSON.stringify({ reason: reason || 'Canceled by user.' }),
    },
    timeoutMs: 30000,
  });
}

export async function retryAutomationEventRun(apiBaseUrl: string, token: string, eventRunId: string, reason?: string) {
  return requestJson<AutomationEventRun>({
    scope: 'automations.runs.retry',
    url: `${apiBaseUrl}/api/app/events/runs/${encodeURIComponent(eventRunId)}/retry`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason || 'Retry requested by user.' }),
    },
    timeoutMs: 30000,
  });
}

export async function cancelProcessWait(apiBaseUrl: string, token: string, processWaitId: string, reason?: string, confirmationId?: string | null) {
  return requestJson<ProcessWait>({
    scope: 'automations.process_waits.cancel',
    url: `${apiBaseUrl}/api/app/events/process-waits/${encodeURIComponent(processWaitId)}/cancel`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json', ...confirmationHeaders(confirmationId) },
      body: JSON.stringify({ reason: reason || 'Canceled by user.' }),
    },
    timeoutMs: 30000,
  });
}

export async function stopProcessWait(apiBaseUrl: string, token: string, processWaitId: string, reason?: string, confirmationId?: string | null) {
  return requestJson<ProcessWait>({
    scope: 'automations.process_waits.stop',
    url: `${apiBaseUrl}/api/app/events/process-waits/${encodeURIComponent(processWaitId)}/stop`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json', ...confirmationHeaders(confirmationId) },
      body: JSON.stringify({ reason: reason || 'Stopped by user.' }),
    },
    timeoutMs: 30000,
  });
}

export async function setProcessWaitPersistent(apiBaseUrl: string, token: string, processWaitId: string, persistent: boolean, reason?: string) {
  return requestJson<ProcessWait>({
    scope: 'automations.process_waits.persistent',
    url: `${apiBaseUrl}/api/app/events/process-waits/${encodeURIComponent(processWaitId)}/persistent`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ persistent, reason }),
    },
    timeoutMs: 30000,
  });
}

export async function updatePlannerContractStatus(apiBaseUrl: string, token: string, contractId: string, status: string) {
  return requestJson<PlannerContract>({
    scope: 'automations.planner_contracts.status',
    url: `${apiBaseUrl}/api/app/events/planner-contracts/${encodeURIComponent(contractId)}/status`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    },
    timeoutMs: 30000,
  });
}

export async function fetchRecoveryItems(apiBaseUrl: string, token: string) {
  return requestJson<RecoveryListResponse>({
    scope: 'recovery.list',
    url: `${apiBaseUrl}/api/app/recovery`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchPendingConfirmations(apiBaseUrl: string, token: string) {
  return requestJson<{ items: PendingConfirmation[] }>({
    scope: 'confirmations.list',
    url: `${apiBaseUrl}/api/app/confirmations`,
    init: { headers: authHeaders(token) },
  });
}

export async function createPendingConfirmation(apiBaseUrl: string, token: string, payload: ConfirmationCreatePayload) {
  return requestJson<PendingConfirmation>({
    scope: 'confirmations.create',
    url: `${apiBaseUrl}/api/app/confirmations`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function approvePendingConfirmation(apiBaseUrl: string, token: string, confirmationId: string, decidedBySurface = 'app') {
  return requestJson<PendingConfirmation>({
    scope: 'confirmations.approve',
    url: `${apiBaseUrl}/api/app/confirmations/${encodeURIComponent(confirmationId)}/approve`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ decided_by_surface: decidedBySurface }),
    },
    timeoutMs: 30000,
  });
}

export async function denyPendingConfirmation(apiBaseUrl: string, token: string, confirmationId: string, decidedBySurface = 'app') {
  return requestJson<PendingConfirmation>({
    scope: 'confirmations.deny',
    url: `${apiBaseUrl}/api/app/confirmations/${encodeURIComponent(confirmationId)}/deny`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ decided_by_surface: decidedBySurface }),
    },
    timeoutMs: 30000,
  });
}

export async function restoreRecoveryItem(apiBaseUrl: string, token: string, archiveId: string) {
  return requestJson<{ ok: boolean; action: string; item?: RecoveryArchiveItem; restored_session_id?: string | null }>({
    scope: 'recovery.restore',
    url: `${apiBaseUrl}/api/app/recovery/${encodeURIComponent(archiveId)}/restore`,
    init: { method: 'POST', headers: authHeaders(token) },
    timeoutMs: 30000,
  });
}

export async function permanentlyDeleteRecoveryItem(apiBaseUrl: string, token: string, archiveId: string, confirmationId?: string | null) {
  return requestJson<{ ok: boolean; action: string; item?: RecoveryArchiveItem }>({
    scope: 'recovery.permanent_delete',
    url: `${apiBaseUrl}/api/app/recovery/${encodeURIComponent(archiveId)}`,
    init: {
      method: 'DELETE',
      headers: {
        ...authHeaders(token),
        ...(confirmationId ? { 'X-EmploAI-Confirmation-Id': confirmationId } : {}),
      },
    },
    timeoutMs: 30000,
  });
}

export async function restoreWorkspaceFiles(apiBaseUrl: string, token: string, payload: { workspace_id?: string | null; machine_id?: string | null; local_path?: string | null }) {
  return requestJson<WorkspaceRestoreResponse>({
    scope: 'recovery.workspace.restore',
    url: `${apiBaseUrl}/api/app/workspace/restore`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    timeoutMs: 60000,
  });
}

export async function createJob(apiBaseUrl: string, token: string, payload: JobCreatePayload) {
  return requestJson<ScheduledJob>({
    scope: 'automations.create',
    url: `${apiBaseUrl}/api/app/automations`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function acknowledgeAutomationEvent(apiBaseUrl: string, token: string, eventId: string) {
  return requestJson<CronFeedItem>({
    scope: 'automations.events.ack',
    url: `${apiBaseUrl}/api/app/events/${encodeURIComponent(eventId)}/ack`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function fetchTelegramBotConfigs(apiBaseUrl: string, token: string) {
  return requestJson<TelegramBotConfig[]>({
    scope: 'telegram-bots.list',
    url: `${apiBaseUrl}/api/app/telegram-bots`,
    init: { headers: authHeaders(token) },
  });
}

export async function createTelegramBotConfig(apiBaseUrl: string, token: string, payload: { label: string; bot_token: string }) {
  return requestJson<TelegramBotConfig>({
    scope: 'telegram-bots.create',
    url: `${apiBaseUrl}/api/app/telegram-bots`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function updateTelegramBotConfig(apiBaseUrl: string, token: string, botConfigId: string, payload: { label?: string; bot_token?: string; is_default?: boolean }) {
  return requestJson<TelegramBotConfig>({
    scope: 'telegram-bots.update',
    url: `${apiBaseUrl}/api/app/telegram-bots/${encodeURIComponent(botConfigId)}`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function deleteTelegramBotConfig(apiBaseUrl: string, token: string, botConfigId: string) {
  return requestJson<{ ok: boolean; id: string }>({
    scope: 'telegram-bots.delete',
    url: `${apiBaseUrl}/api/app/telegram-bots/${encodeURIComponent(botConfigId)}`,
    init: {
      method: 'DELETE',
      headers: authHeaders(token),
    },
  });
}

export async function updateSessionToolPacks(apiBaseUrl: string, token: string, sessionId: string, payload: ToolPackUpdatePayload) {
  return requestJson<SessionDetail>({
    scope: 'sessions.toolpacks',
    url: `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}/tool-packs`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function fetchProjectOnboarding(apiBaseUrl: string, token: string, workspace: string) {
  const query = new URLSearchParams({ workspace });
  return requestJson<ProjectOnboardingResponse>({
    scope: 'onboarding.get',
    url: `${apiBaseUrl}/api/app/onboarding?${query.toString()}`,
    init: {
      headers: authHeaders(token),
    },
  });
}

export async function saveProjectOnboarding(apiBaseUrl: string, token: string, payload: ProjectOnboardingSavePayload) {
  return requestJson<ProjectOnboardingResponse>({
    scope: 'onboarding.save',
    url: `${apiBaseUrl}/api/app/onboarding`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function summarizeProjectOnboarding(apiBaseUrl: string, token: string, payload: ProjectOnboardingSummarizePayload) {
  return requestJson<ProjectOnboardingResponse>({
    scope: 'onboarding.summarize',
    url: `${apiBaseUrl}/api/app/onboarding/summarize`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function updateSessionTelegramBotAssignment(apiBaseUrl: string, token: string, sessionId: string, payload: SessionBotAssignmentPayload) {
  return requestJson<SessionDetail>({
    scope: 'sessions.telegram-bot',
    url: `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}/telegram-bot`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function updateSessionHeadlessEligibility(apiBaseUrl: string, token: string, sessionId: string, payload: SessionHeadlessEligibilityPayload) {
  return requestJson<SessionDetail>({
    scope: 'sessions.headless-eligibility',
    url: `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}/headless-eligibility`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function updateSessionSecurityPermissionMode(
  apiBaseUrl: string,
  token: string,
  sessionId: string,
  payload: SessionSecurityPermissionPayload,
  confirmationId?: string | null,
) {
  return requestJson<SessionDetail>({
    scope: 'sessions.security-permission-mode',
    url: `${apiBaseUrl}/api/app/sessions/${encodeURIComponent(sessionId)}/security-permission-mode`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json', ...confirmationHeaders(confirmationId) },
      body: JSON.stringify(payload),
    },
  });
}

export async function fetchRuntimeOrchestratorStatus(apiBaseUrl: string, token: string) {
  return requestJson<RuntimeOrchestratorStatus>({
    scope: 'runtime.orchestrator',
    url: `${apiBaseUrl}/api/app/runtime/orchestrator`,
    init: { headers: authHeaders(token) },
  });
}

export async function configureHeadlessRuntime(apiBaseUrl: string, token: string, payload: HeadlessConfigurePayload) {
  return requestJson<RuntimeOrchestratorStatus>({
    scope: 'runtime.headless.configure',
    url: `${apiBaseUrl}/api/app/runtime/headless`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
}

export async function fetchWorkspaceGitState(apiBaseUrl: string, token: string, path: string) {
  const params = new URLSearchParams();
  params.set('path', path);
  return requestJson<WorkspaceGitState>({
    scope: 'workspace.git.info',
    url: `${apiBaseUrl}/api/app/workspace/git?${params.toString()}`,
    init: { headers: authHeaders(token) },
  });
}

export async function checkoutWorkspaceGitBranch(apiBaseUrl: string, token: string, path: string, branch: string) {
  return requestJson<WorkspaceGitState>({
    scope: 'workspace.git.checkout',
    url: `${apiBaseUrl}/api/app/workspace/git/checkout`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, branch }),
    },
    timeoutMs: 30000,
  });
}

export async function actOnJob(apiBaseUrl: string, token: string, jobId: string, action: 'run' | 'enable' | 'disable' | 'delete', confirmationId?: string | null) {
  const method = action === 'delete' ? 'DELETE' : 'POST';
  const automationAction = action === 'enable' ? 'resume' : action === 'disable' ? 'pause' : action;
  const url = action === 'delete'
    ? `${apiBaseUrl}/api/app/automations/${jobId}`
    : `${apiBaseUrl}/api/app/automations/${jobId}/${automationAction}`;

  return requestJson({
    scope: `automations.${action}`,
    url,
    init: {
      method,
      headers: { ...authHeaders(token), ...confirmationHeaders(confirmationId) },
    },
    timeoutMs: 30000,
  });
}

export async function fetchAgentOverview(
  apiBaseUrl: string,
  token: string,
  params?: { sessionId?: string; historyCount?: number; analyticsDays?: number }
) {
  const query = new URLSearchParams();
  if (params?.sessionId) query.set('session_id', params.sessionId);
  if (params?.historyCount) query.set('history_count', String(params.historyCount));
  if (params?.analyticsDays) query.set('analytics_days', String(params.analyticsDays));

  return requestJson<AgentOverview>({
    scope: 'agent.overview',
    url: `${apiBaseUrl}/api/app/agent/overview${query.size ? `?${query.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchVoiceRuntimeStatus(apiBaseUrl: string, token: string) {
  return requestJson<VoiceRuntimeStatus>({
    scope: 'voice.status',
    url: `${apiBaseUrl}/api/app/voice/status`,
    init: { headers: authHeaders(token) },
  });
}

export async function warmVoiceRuntime(apiBaseUrl: string, token: string) {
  return requestJson<VoiceRuntimeStatus>({
    scope: 'voice.warm',
    url: `${apiBaseUrl}/api/app/voice/warm`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 120000,
  });
}

export async function configureVoiceTtsBackend(apiBaseUrl: string, token: string, backend: string) {
  return requestJson<VoiceRuntimeStatus>({
    scope: 'voice.tts.configure',
    url: `${apiBaseUrl}/api/app/voice/tts`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ backend }),
    },
    timeoutMs: 120000,
  });
}

export async function configureVoiceSttBackend(apiBaseUrl: string, token: string, backend: string) {
  return requestJson<VoiceRuntimeStatus>({
    scope: 'voice.stt.configure',
    url: `${apiBaseUrl}/api/app/voice/stt`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ backend }),
    },
    timeoutMs: 120000,
  });
}

export async function fetchTaskBoard(apiBaseUrl: string, token: string, sessionId?: string) {
  const query = new URLSearchParams();
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<{ task_board?: TaskBoard | null }>({
    scope: 'agent.taskboard.get',
    url: `${apiBaseUrl}/api/app/agent/task-board${query.size ? `?${query.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function forceTaskBoardReassess(apiBaseUrl: string, token: string, sessionId?: string) {
  const query = new URLSearchParams();
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.taskboard.reassess',
    url: `${apiBaseUrl}/api/app/agent/task-board/reassess${query.size ? `?${query.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function setTaskBoardArmedNextTurn(
  apiBaseUrl: string,
  token: string,
  armed: boolean,
  sessionId?: string,
) {
  const query = new URLSearchParams();
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<TaskBoardArmResult>({
    scope: 'agent.taskboard.arm',
    url: `${apiBaseUrl}/api/app/agent/task-board/arm${query.size ? `?${query.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ armed }),
    },
    timeoutMs: 30000,
  });
}

export async function configureAgent(
  apiBaseUrl: string,
  token: string,
  payload: AgentConfigurePayload,
  sessionId?: string
) {
  const query = new URLSearchParams();
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.configure',
    url: `${apiBaseUrl}/api/app/agent/configure${query.size ? `?${query.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function reloadProviderKeys(
  apiBaseUrl: string,
  token: string,
  values: Record<string, string | undefined>,
) {
  return requestJson<AgentAction>({
    scope: 'agent.provider_keys.reload',
    url: `${apiBaseUrl}/api/app/agent/provider-keys/reload`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ values }),
    },
    timeoutMs: 30000,
  });
}

export async function fetchBridgeStatus(apiBaseUrl: string, token: string, sessionId?: string) {
  const query = new URLSearchParams();
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<BridgeStatus>({
    scope: 'agent.bridge.status',
    url: `${apiBaseUrl}/api/app/agent/bridge-status${query.size ? `?${query.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchAgentConfig(apiBaseUrl: string, token: string, key?: string, sessionId?: string) {
  const query = new URLSearchParams();
  if (key) query.set('key', key);
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<{ items: ConfigEntry[] }>({
    scope: 'agent.config.list',
    url: `${apiBaseUrl}/api/app/agent/config${query.size ? `?${query.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function updateAgentConfig(
  apiBaseUrl: string,
  token: string,
  payload: { key: string; value: unknown },
  sessionId?: string
) {
  const query = new URLSearchParams();
  if (sessionId) query.set('session_id', sessionId);

  return requestJson<ConfigEntry>({
    scope: 'agent.config.update',
    url: `${apiBaseUrl}/api/app/agent/config${query.size ? `?${query.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function searchAgentMemory(apiBaseUrl: string, token: string, query: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<{ query: string; results: MemorySearchResult[] }>({
    scope: 'agent.memory.search',
    url: `${apiBaseUrl}/api/app/agent/memory/search${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query }),
    },
    timeoutMs: 30000,
  });
}

export async function appendAgentMemoryNote(apiBaseUrl: string, token: string, note: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.memory.note',
    url: `${apiBaseUrl}/api/app/agent/memory/note${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ note }),
    },
    timeoutMs: 30000,
  });
}

export async function applyAgentMemoryOperations(
  apiBaseUrl: string,
  token: string,
  operations: MemoryOperation[],
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<MemoryOperationResult>({
    scope: 'agent.memory.operations',
    url: `${apiBaseUrl}/api/app/agent/memory/operations${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ operations }),
    },
    timeoutMs: 30000,
  });
}

export async function addAgentMemoryFact(
  apiBaseUrl: string,
  token: string,
  payload: { content: string; category?: string; tags?: string[]; trust?: number },
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<MemoryFact>({
    scope: 'agent.memory.facts.add',
    url: `${apiBaseUrl}/api/app/agent/memory/facts${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function fetchAgentMemoryFacts(
  apiBaseUrl: string,
  token: string,
  sessionId?: string,
  options?: { category?: string; limit?: number }
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);
  if (options?.category) params.set('category', options.category);
  if (options?.limit) params.set('limit', String(options.limit));

  return requestJson<{ items: MemoryFact[] }>({
    scope: 'agent.memory.facts.list',
    url: `${apiBaseUrl}/api/app/agent/memory/facts${params.size ? `?${params.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
    timeoutMs: 30000,
  });
}

export async function deleteAgentMemoryFact(
  apiBaseUrl: string,
  token: string,
  factId: number,
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.memory.facts.delete',
    url: `${apiBaseUrl}/api/app/agent/memory/facts/${encodeURIComponent(String(factId))}${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'DELETE',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function rateAgentMemoryFact(
  apiBaseUrl: string,
  token: string,
  payload: { fact_id: number; helpful: boolean },
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<MemoryFact>({
    scope: 'agent.memory.facts.feedback',
    url: `${apiBaseUrl}/api/app/agent/memory/facts/feedback${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function clearAgentPendingFiles(apiBaseUrl: string, token: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.files.clear',
    url: `${apiBaseUrl}/api/app/agent/files/clear${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function forgetLastAgentMessage(apiBaseUrl: string, token: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.forget',
    url: `${apiBaseUrl}/api/app/agent/forget-last${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function resetAgentContext(apiBaseUrl: string, token: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.reset',
    url: `${apiBaseUrl}/api/app/agent/reset${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function compactAgentContext(apiBaseUrl: string, token: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.compact',
    url: `${apiBaseUrl}/api/app/agent/compact${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function fetchAgentSkills(apiBaseUrl: string, token: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<{ items: SkillSummary[] }>({
    scope: 'agent.skills.list',
    url: `${apiBaseUrl}/api/app/agent/skills${params.size ? `?${params.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchAgentSkillDetail(
  apiBaseUrl: string,
  token: string,
  name: string,
  sessionId?: string,
  options?: { includeResources?: boolean }
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);
  if (options?.includeResources) params.set('include_resources', 'true');

  return requestJson<SkillDetail>({
    scope: 'agent.skills.view',
    url: `${apiBaseUrl}/api/app/agent/skills/${encodeURIComponent(name)}${params.size ? `?${params.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
    timeoutMs: 30000,
  });
}

export async function learnAgentSkill(
  apiBaseUrl: string,
  token: string,
  payload: { name: string; description?: string | null; workflow?: string; activate?: boolean; overwrite?: boolean },
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<SkillLearnResult>({
    scope: 'agent.skills.learn',
    url: `${apiBaseUrl}/api/app/agent/skills/learn${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function activateAgentSkill(
  apiBaseUrl: string,
  token: string,
  payload: { name: string; active?: boolean },
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.skills.activate',
    url: `${apiBaseUrl}/api/app/agent/skills/activate${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function validateAgentSkill(apiBaseUrl: string, token: string, name: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<SkillValidation>({
    scope: 'agent.skills.validate',
    url: `${apiBaseUrl}/api/app/agent/skills/validate${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ name, active: true }),
    },
    timeoutMs: 30000,
  });
}

export async function fetchSubAgents(apiBaseUrl: string, token: string, sessionId?: string) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<SubAgentStatus>({
    scope: 'agent.subagents.list',
    url: `${apiBaseUrl}/api/app/agent/subagents${params.size ? `?${params.toString()}` : ''}`,
    init: { headers: authHeaders(token) },
  });
}

export async function spawnSubAgent(
  apiBaseUrl: string,
  token: string,
  payload: { prompt: string; headless?: boolean; max_turns?: number },
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: 'agent.subagents.spawn',
    url: `${apiBaseUrl}/api/app/agent/subagents${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function controlAgentRun(
  apiBaseUrl: string,
  token: string,
  action: 'pause' | 'stop' | 'restart',
  sessionId?: string
) {
  const params = new URLSearchParams();
  if (sessionId) params.set('session_id', sessionId);

  return requestJson<AgentAction>({
    scope: `agent.control.${action}`,
    url: `${apiBaseUrl}/api/app/agent/control/${action}${params.size ? `?${params.toString()}` : ''}`,
    init: {
      method: 'POST',
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function setFleetIdentityToolPacks(
  apiBaseUrl: string,
  token: string,
  identityId: string,
  enabledToolPacks: string[],
) {
  return requestJson<FleetIdentity>({
    scope: 'fleet.identity.tool_packs',
    url: `${apiBaseUrl}/api/fleet/identities/${encodeURIComponent(identityId)}/tool-packs`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled_tool_packs: enabledToolPacks }),
    },
  });
}

export async function fetchRuntimePacks(apiBaseUrl: string, token: string) {
  return requestJson<{ packs: Array<Record<string, any>>; count: number; installed_count: number }>({
    scope: 'runtime_packs.summary',
    url: `${apiBaseUrl}/api/runtime-packs`,
    init: { headers: authHeaders(token) },
  });
}

export async function installRuntimePack(apiBaseUrl: string, token: string, packId: string, force = false) {
  return requestJson<Record<string, any>>({
    scope: 'runtime_packs.install',
    url: `${apiBaseUrl}/api/runtime-packs/${encodeURIComponent(packId)}/install`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ force }),
    },
  });
}

export async function removeRuntimePack(apiBaseUrl: string, token: string, packId: string) {
  return requestJson<Record<string, any>>({
    scope: 'runtime_packs.remove',
    url: `${apiBaseUrl}/api/runtime-packs/${encodeURIComponent(packId)}`,
    init: { method: 'DELETE', headers: authHeaders(token) },
  });
}

export async function fetchRuntimePackProgress(apiBaseUrl: string, token: string, packId: string) {
  return requestJson<Record<string, any>>({
    scope: 'runtime_packs.progress',
    url: `${apiBaseUrl}/api/runtime-packs/${encodeURIComponent(packId)}/progress`,
    init: { headers: authHeaders(token) },
  });
}

export async function fetchManagerContextInspectionSetting(apiBaseUrl: string, token: string) {
  return requestJson<Record<string, any>>({
    scope: 'fleet.context_inspection.setting',
    url: `${apiBaseUrl}/api/fleet/context-inspection`,
    init: { headers: authHeaders(token) },
  });
}

export async function setManagerContextInspectionSetting(apiBaseUrl: string, token: string, enabled: boolean) {
  return requestJson<Record<string, any>>({
    scope: 'fleet.context_inspection.update',
    url: `${apiBaseUrl}/api/fleet/context-inspection`,
    init: {
      method: 'PUT',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    },
  });
}

export async function stopFleetComputerDelegation(
  apiBaseUrl: string,
  token: string,
  delegationId: string,
  reason?: string | null,
) {
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.delegation.stop',
    url: `${apiBaseUrl}/api/fleet/delegations/${encodeURIComponent(delegationId)}/stop`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason || null, metadata: { source: 'desktop_task_card' } }),
    },
  });
}

export async function redirectFleetComputerDelegation(
  apiBaseUrl: string,
  token: string,
  delegationId: string,
  direction: string,
) {
  return requestJson<Record<string, unknown>>({
    scope: 'fleet.delegation.redirect',
    url: `${apiBaseUrl}/api/fleet/delegations/${encodeURIComponent(delegationId)}/redirect`,
    init: {
      method: 'POST',
      headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
      body: JSON.stringify({ direction, source: 'desktop_task_card', metadata: {} }),
    },
  });
}

export async function updateJob(apiBaseUrl: string, token: string, jobId: string, payload: JobCreatePayload) {
  return requestJson<ScheduledJob>({
    scope: 'automations.update',
    url: `${apiBaseUrl}/api/app/automations/${encodeURIComponent(jobId)}`,
    init: {
      method: 'PUT',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function stopIdentityTree(
  apiBaseUrl: string,
  token: string,
  payload: {
    session_id?: string | null;
    identity_id?: string | null;
    identity_role?: string | null;
    worker_id?: string | null;
    reason?: string | null;
  }
) {
  return requestJson<{
    ok: boolean;
    action: 'identity_stop';
    message: string;
    counts?: Record<string, number>;
    fleet_results?: unknown[];
    session_id?: string | null;
  }>({
    scope: 'agent.control.identity_stop',
    url: `${apiBaseUrl}/api/app/agent/control/identity-stop`,
    init: {
      method: 'POST',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
    timeoutMs: 30000,
  });
}

export async function fetchSidebarState(apiBaseUrl: string, token: string) {
  return requestJson<SidebarStateResult>({
    scope: 'sidebar-state.get',
    url: `${apiBaseUrl}/api/app/sidebar-state`,
    init: {
      headers: authHeaders(token),
    },
    timeoutMs: 30000,
  });
}

export async function updateSidebarState(apiBaseUrl: string, token: string, state: SidebarState) {
  return requestJson<SidebarStateResult>({
    scope: 'sidebar-state.put',
    url: `${apiBaseUrl}/api/app/sidebar-state`,
    init: {
      method: 'PUT',
      headers: {
        ...authHeaders(token),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ state }),
    },
    timeoutMs: 30000,
  });
}
