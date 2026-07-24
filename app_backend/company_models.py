from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


CompanyOwnership = Literal["root", "member"]
CompanyMembershipRole = Literal["root_controller", "worker_node"]
CompanyStatus = Literal["active", "unavailable", "revoked", "deleting"]


class CompanySummaryView(BaseModel):
    company_id: str
    display_name: str
    ownership: CompanyOwnership
    membership_role: CompanyMembershipRole
    local_computer_id: str
    status: CompanyStatus = "active"
    onboarding_status: str = "not_started"
    created_at: str
    updated_at: str


class CompanyEmployeeView(BaseModel):
    employee_id: str
    identity_id: str
    display_name: str
    system_role: Literal["manager", "worker"]
    company_role: str
    protected: bool = False
    is_default: bool = False
    home_membership_id: str
    status: str = "active"
    job_contract_status: str = "setup_incomplete"
    position_id: Optional[str] = None
    job_contract_id: Optional[str] = None
    published_upstream: Optional[bool] = None
    assignment_paused: bool = False
    assignment_pause_reason: Optional[str] = None


class CompanyMembershipView(BaseModel):
    membership_id: str
    company_id: str
    computer_id: str
    computer_name: Optional[str] = None
    upstream_computer_id: Optional[str] = None
    membership_role: CompanyMembershipRole
    parent_membership_id: Optional[str] = None
    manager_identity_id: Optional[str] = None
    default_worker_identity_id: Optional[str] = None
    published_identity_ids: List[str] = Field(default_factory=list)
    status: str = "active"
    created_at: str
    updated_at: str


class CompanyDetailView(BaseModel):
    company_id: str
    schema_version: int = 1
    revision: int = 1
    manifest: Dict[str, Any] = Field(default_factory=dict)
    memberships: List[CompanyMembershipView] = Field(default_factory=list)
    employees: List[CompanyEmployeeView] = Field(default_factory=list)
    departments: List[Dict[str, Any]] = Field(default_factory=list)
    positions: List[Dict[str, Any]] = Field(default_factory=list)
    job_contracts: List[Dict[str, Any]] = Field(default_factory=list)
    objectives: List[Dict[str, Any]] = Field(default_factory=list)
    initiatives: List[Dict[str, Any]] = Field(default_factory=list)
    runbooks: List[Dict[str, Any]] = Field(default_factory=list)
    recurring_operations: List[Dict[str, Any]] = Field(default_factory=list)
    assignments: List[Dict[str, Any]] = Field(default_factory=list)
    handoffs: List[Dict[str, Any]] = Field(default_factory=list)
    approvals: List[Dict[str, Any]] = Field(default_factory=list)
    reports: List[Dict[str, Any]] = Field(default_factory=list)
    objective_reviews: List[Dict[str, Any]] = Field(default_factory=list)
    policies: List[Dict[str, Any]] = Field(default_factory=list)
    decisions: List[Dict[str, Any]] = Field(default_factory=list)
    knowledge: List[Dict[str, Any]] = Field(default_factory=list)
    metrics: List[Dict[str, Any]] = Field(default_factory=list)
    financial_entries: List[Dict[str, Any]] = Field(default_factory=list)
    backup_history: List[Dict[str, Any]] = Field(default_factory=list)
    company_audit_events: List[Dict[str, Any]] = Field(default_factory=list)
    migration: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class CompanyContextView(BaseModel):
    schema_version: int = 1
    active_company_id: Optional[str] = None
    active_company: Optional[CompanyDetailView] = None
    companies: List[CompanySummaryView] = Field(default_factory=list)
    chooser_required: bool = False
    selection_reason: Optional[str] = None
    local_computer_id: str
    local_computer_name: str


class CompanyCreateRequest(BaseModel):
    display_name: str = Field(default="My Company", min_length=1, max_length=120)


class CompanySelectRequest(BaseModel):
    company_id: str = Field(min_length=1, max_length=128)


class CompanyUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    onboarding_status: Optional[str] = Field(default=None, max_length=80)
    manifest: Dict[str, Any] = Field(default_factory=dict)


class CompanyMigrationCompleteRequest(BaseModel):
    verified_backup_id: str = Field(min_length=1, max_length=160)


class CompanyDeleteRequest(BaseModel):
    company_name_confirmation: str = Field(min_length=1, max_length=120)
    active_work_action: Literal["cancel"] = "cancel"
    final_backup_id: Optional[str] = Field(default=None, max_length=160)


class CompanyDepartmentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    mandate: str = Field(min_length=1, max_length=4000)
    manager_identity_id: Optional[str] = Field(default=None, max_length=240)


class CompanyPositionCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    template_id: Optional[str] = Field(default=None, max_length=240)
    manager_identity_id: Optional[str] = Field(default=None, max_length=240)
    department_id: Optional[str] = Field(default=None, max_length=240)
    identity_id: Optional[str] = Field(default=None, max_length=240)
    overlay: Dict[str, Any] = Field(default_factory=dict)


class CompanyPositionOccupantChangeRequest(BaseModel):
    identity_id: Optional[str] = Field(default=None, max_length=240)
    move_from_position_id: Optional[str] = Field(default=None, max_length=240)
    reason: str = Field(min_length=1, max_length=2000)


class CompanyJobContractUpdateRequest(BaseModel):
    mission: Optional[str] = Field(default=None, max_length=4000)
    responsibilities: Optional[List[str]] = None
    non_responsibilities: Optional[List[str]] = None
    deliverables: Optional[List[str]] = None
    inputs: Optional[List[str]] = None
    quality_gates: Optional[List[str]] = None
    success_measures: Optional[List[str]] = None
    reporting_cadence: Optional[str] = Field(default=None, max_length=1000)
    escalation_route: Optional[str] = Field(default=None, max_length=240)
    approved_tool_packs: Optional[List[str]] = None
    approved_workspace_ids: Optional[List[str]] = None
    authority: Optional[Dict[str, Any]] = None
    memory_policy: Optional[Dict[str, Any]] = None
    resource_policy: Optional[Dict[str, Any]] = None
    missing_requirements: Optional[List[Dict[str, Any]]] = None


class CompanyReadinessReviewRequest(BaseModel):
    reviewer_identity_id: Optional[str] = Field(default=None, max_length=240)
    checks: Dict[str, bool] = Field(default_factory=dict)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    missing_requirements: List[Dict[str, Any]] = Field(default_factory=list)
    limited_mode: bool = False
    limitations: Optional[str] = Field(default=None, max_length=4000)


class CompanyDecisionCreateRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    decision: str = Field(min_length=1, max_length=4000)
    rationale: str = Field(min_length=1, max_length=4000)
    scope: str = Field(default="company", max_length=160)
    related_record_ids: List[str] = Field(default_factory=list)


class CompanyInitiativeCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    outcome: str = Field(min_length=1, max_length=2000)
    owner_identity_id: Optional[str] = Field(default=None, max_length=240)
    objective_ids: List[str] = Field(default_factory=list)
    plan: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    due_at: Optional[str] = Field(default=None, max_length=80)


class CompanyInitiativeStatusRequest(BaseModel):
    status: str = Field(min_length=1, max_length=80)
    reason: Optional[str] = Field(default=None, max_length=2000)


class CompanyRunbookCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    trigger: str = Field(min_length=1, max_length=2000)
    steps: List[Dict[str, Any]] = Field(min_length=1)
    required_roles: List[str] = Field(default_factory=list)
    approval_gates: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_requirements: List[str] = Field(default_factory=list)


class CompanyRunbookStatusRequest(BaseModel):
    status: Literal["active", "archived"]
    review_note: str = Field(min_length=1, max_length=4000)


class CompanyRecurringOperationCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    trigger: str = Field(min_length=1, max_length=2000)
    owner_identity_id: Optional[str] = Field(default=None, max_length=240)
    runbook_id: str = Field(min_length=1, max_length=240)
    automation_id: Optional[str] = Field(default=None, max_length=240)
    schedule: str = Field(min_length=1, max_length=500)
    inputs: List[str] = Field(default_factory=list)
    expected_output: str = Field(min_length=1, max_length=4000)
    quality_gate: str = Field(min_length=1, max_length=4000)
    escalation_minutes: int = Field(default=60, ge=1, le=525600)


class CompanyRecurringOperationStatusRequest(BaseModel):
    status: Literal["active", "paused", "archived"]
    reason: str = Field(min_length=1, max_length=4000)


class CompanyEmergencyControlRequest(BaseModel):
    scope: Literal[
        "company",
        "assignment",
        "employee",
        "department",
        "runbook",
        "recurring_operation",
    ]
    target_id: Optional[str] = Field(default=None, max_length=240)
    action: Literal["pause", "resume"]
    reason: str = Field(min_length=1, max_length=4000)


class CompanyHandoffCreateRequest(BaseModel):
    from_identity_id: str = Field(min_length=1, max_length=240)
    to_identity_id: str = Field(min_length=1, max_length=240)
    deliverable: str = Field(min_length=1, max_length=8000)
    acceptance_criteria: str = Field(min_length=1, max_length=4000)
    objective_id: Optional[str] = Field(default=None, max_length=160)
    assignment_id: Optional[str] = Field(default=None, max_length=160)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)


class CompanyHandoffReviewRequest(BaseModel):
    reviewer_identity_id: Optional[str] = Field(default=None, max_length=240)
    decision: Literal["accepted", "rework_requested"]
    rationale: str = Field(min_length=1, max_length=4000)
    rework_instructions: Optional[str] = Field(default=None, max_length=4000)


class CompanyKnowledgeCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=40000)
    provenance: Dict[str, Any]
    sensitivity: str = Field(default="company", max_length=80)
    review_due_at: Optional[str] = Field(default=None, max_length=80)


class CompanyKnowledgeReviewRequest(BaseModel):
    next_review_due_at: Optional[str] = Field(default=None, max_length=80)
    review_note: str = Field(min_length=1, max_length=4000)


class CompanyMetricCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    definition: str = Field(min_length=1, max_length=4000)
    formula: str = Field(min_length=1, max_length=2000)
    unit: str = Field(min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=2000)
    cadence: str = Field(default="monthly", max_length=120)
    owner_identity_id: Optional[str] = Field(default=None, max_length=240)
    guardrails: List[str] = Field(default_factory=list)


class CompanyMetricObservationRequest(BaseModel):
    value: Any
    period_start: Optional[str] = Field(default=None, max_length=80)
    period_end: Optional[str] = Field(default=None, max_length=80)
    confidence: str = Field(default="unknown", max_length=80)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    note: Optional[str] = Field(default=None, max_length=4000)


class CompanyFinancialEntryCreateRequest(BaseModel):
    entry_type: Literal["revenue", "cost"]
    amount: float = Field(ge=0)
    currency: str = Field(min_length=3, max_length=12)
    description: str = Field(min_length=1, max_length=2000)
    recognized_at: str = Field(min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=2000)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)


class CompanyObjectiveCreateRequest(BaseModel):
    outcome: str = Field(min_length=1, max_length=2000)
    success_criteria: str = Field(min_length=1, max_length=4000)
    owner_identity_id: Optional[str] = Field(default=None, max_length=240)
    priority: str = Field(default="normal", max_length=40)
    due_at: Optional[str] = Field(default=None, max_length=80)
    low_risk_auto_accept: bool = False
    optional_proposals: List[Dict[str, Any]] = Field(default_factory=list)


class CompanyObjectiveStatusRequest(BaseModel):
    status: str = Field(min_length=1, max_length=80)
    reason: Optional[str] = Field(default=None, max_length=2000)


class CompanyObjectiveAssignmentLinkRequest(BaseModel):
    assignee_identity_id: str = Field(min_length=1, max_length=240)
    prompt: str = Field(min_length=1, max_length=20000)
    task_id: Optional[str] = Field(default=None, max_length=160)
    delegation_id: Optional[str] = Field(default=None, max_length=160)
    route: Dict[str, Any] = Field(default_factory=dict)
    state: str = Field(default="queued", max_length=80)


class CompanyReportReviewRequest(BaseModel):
    report_id: str = Field(min_length=1, max_length=160)
    objective_id: Optional[str] = Field(default=None, max_length=160)
    reviewer_identity_id: Optional[str] = Field(default=None, max_length=240)
    decision: str = Field(min_length=1, max_length=80)
    rationale: str = Field(min_length=1, max_length=4000)
    rework_instructions: Optional[str] = Field(default=None, max_length=4000)


class CompanyPolicyCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    rule: str = Field(min_length=1, max_length=6000)
    scope: str = Field(default="company", max_length=120)
    enforcement: str = Field(default="manager", max_length=120)


class CompanyBackupExportRequest(BaseModel):
    passphrase: str = Field(min_length=12, max_length=1024)


class CompanyBackupExportResponse(BaseModel):
    backup: Dict[str, Any]
    recovery_key: str
