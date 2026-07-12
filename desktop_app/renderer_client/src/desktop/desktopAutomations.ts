import type {
  AutomationEventRun,
  CronFeedItem,
  JobCreatePayload,
  PlannerContract,
  ProcessWait,
  ScheduledJob,
} from '@/lib/appApi';

export type AutomationScheduleMode = 'interval' | 'daily' | 'delay' | 'advanced';
export type AutomationTargetKind = 'active_identity' | 'manager' | 'identity' | 'group';
export type AutomationPermissionMode = 'standard' | 'low' | 'full_permissions';
export type AutomationDetailTab = 'overview' | 'activity' | 'advanced';
export type AutomationListFilter = 'all' | 'active' | 'paused' | 'attention';

export type AutomationEditorDraft = {
  name: string;
  prompt: string;
  scheduleMode: AutomationScheduleMode;
  intervalAmount: string;
  intervalUnit: string;
  dailyTime: string;
  delayAmount: string;
  delayUnit: string;
  advancedSchedule: string;
  targetKind: AutomationTargetKind;
  targetIdentityId: string;
  targetGroupId: string;
  targetChatId: string;
  permissionMode: AutomationPermissionMode;
  toolPacksText: string;
};

export type AutomationFieldErrors = Partial<Record<keyof AutomationEditorDraft | 'schedule', string>>;

export const AUTOMATION_SCHEDULE_UNITS = ['minutes', 'hours', 'days'] as const;

export function emptyAutomationDraft(): AutomationEditorDraft {
  return {
    name: '',
    prompt: '',
    scheduleMode: 'interval',
    intervalAmount: '1',
    intervalUnit: 'hours',
    dailyTime: '08:00',
    delayAmount: '20',
    delayUnit: 'minutes',
    advancedSchedule: 'every 1 hour',
    targetKind: 'active_identity',
    targetIdentityId: '',
    targetGroupId: '',
    targetChatId: '',
    permissionMode: 'standard',
    toolPacksText: '',
  };
}

function singularUnit(value: string) {
  return String(value || '').trim().toLowerCase().replace(/s$/, '');
}

function pluralUnit(value: string, amount: number) {
  const unit = singularUnit(value) || 'hour';
  return amount === 1 ? unit : `${unit}s`;
}

export function buildAutomationSchedule(draft: AutomationEditorDraft) {
  if (draft.scheduleMode === 'daily') {
    return `every day at ${draft.dailyTime.trim()}`;
  }
  if (draft.scheduleMode === 'delay') {
    const amount = Number.parseInt(draft.delayAmount, 10);
    return `in ${Number.isFinite(amount) ? amount : draft.delayAmount.trim()} ${pluralUnit(draft.delayUnit, amount)}`.trim();
  }
  if (draft.scheduleMode === 'advanced') {
    return draft.advancedSchedule.trim();
  }
  const amount = Number.parseInt(draft.intervalAmount, 10);
  return `every ${Number.isFinite(amount) ? amount : draft.intervalAmount.trim()} ${pluralUnit(draft.intervalUnit, amount)}`.trim();
}

function validPositiveInteger(value: string) {
  return /^\d+$/.test(value.trim()) && Number.parseInt(value, 10) > 0;
}

export function validateAutomationDraft(draft: AutomationEditorDraft): AutomationFieldErrors {
  const errors: AutomationFieldErrors = {};
  if (!draft.name.trim()) errors.name = 'Give this automation a recognizable name.';
  if (draft.name.trim().length > 160) errors.name = 'Keep the name under 160 characters.';
  if (!draft.prompt.trim()) errors.prompt = 'Describe what EmploAI should do when this automation runs.';

  if (draft.scheduleMode === 'interval' && !validPositiveInteger(draft.intervalAmount)) {
    errors.intervalAmount = 'Enter a whole number greater than 0.';
  } else if (draft.scheduleMode === 'delay' && !validPositiveInteger(draft.delayAmount)) {
    errors.delayAmount = 'Enter a whole number greater than 0.';
  } else if (draft.scheduleMode === 'daily') {
    const match = /^(\d{2}):(\d{2})$/.exec(draft.dailyTime.trim());
    if (!match || Number(match[1]) > 23 || Number(match[2]) > 59) {
      errors.dailyTime = 'Use a 24-hour time such as 08:00.';
    }
  } else if (draft.scheduleMode === 'advanced') {
    const schedule = draft.advancedSchedule.trim().toLowerCase();
    if (!schedule) {
      errors.advancedSchedule = 'Enter a supported schedule.';
    } else if (!/^(in \d+ (second|minute|hour|day)s?|every \d+ (second|minute|hour|day)s?|every day at \d{2}:\d{2})$/.test(schedule)) {
      errors.advancedSchedule = 'Use “every 30 minutes,” “every day at 08:00,” or “in 2 hours.”';
    }
  }

  if (draft.targetKind === 'identity' && !draft.targetIdentityId) {
    errors.targetIdentityId = 'Choose a worker or manager identity.';
  }
  if (draft.targetKind === 'group' && !draft.targetGroupId) {
    errors.targetGroupId = 'Choose a Fleet group.';
  }
  return errors;
}

export function splitAutomationToolPacks(value: string) {
  const seen = new Set<string>();
  return value
    .split(',')
    .map((item) => item.trim())
    .filter((item) => {
      if (!item || seen.has(item)) return false;
      seen.add(item);
      return true;
    });
}

export function automationPayloadFromDraft(draft: AutomationEditorDraft): JobCreatePayload {
  return {
    name: draft.name.trim(),
    prompt: draft.prompt.trim(),
    schedule: buildAutomationSchedule(draft),
    target_kind: draft.targetKind,
    target_identity_id: draft.targetKind === 'identity' ? draft.targetIdentityId : null,
    target_group_id: draft.targetKind === 'group' ? draft.targetGroupId : null,
    target_chat_id: draft.targetChatId || null,
    chat_target: draft.targetChatId ? 'existing' : 'existing_or_new',
    permission_mode: draft.permissionMode,
    tool_packs: splitAutomationToolPacks(draft.toolPacksText),
    metadata: {
      created_from: 'desktop_automations',
      schedule_mode: draft.scheduleMode,
      catch_up_policy: 'latest_only',
    },
  };
}

export function draftFromAutomation(job: ScheduledJob): AutomationEditorDraft {
  const draft = emptyAutomationDraft();
  const schedule = String(job.schedule || '').trim();
  let match = /^every day at (\d{2}:\d{2})$/i.exec(schedule);
  if (match) {
    draft.scheduleMode = 'daily';
    draft.dailyTime = match[1];
  } else {
    match = /^in (\d+) (second|minute|hour|day)s?$/i.exec(schedule);
    if (match) {
      draft.scheduleMode = 'delay';
      draft.delayAmount = match[1];
      draft.delayUnit = pluralUnit(match[2], Number(match[1]));
    } else {
      match = /^every (\d+) (second|minute|hour|day)s?$/i.exec(schedule);
      if (match) {
        draft.scheduleMode = 'interval';
        draft.intervalAmount = match[1];
        draft.intervalUnit = pluralUnit(match[2], Number(match[1]));
      } else {
        draft.scheduleMode = 'advanced';
        draft.advancedSchedule = schedule;
      }
    }
  }
  return {
    ...draft,
    name: job.name || '',
    prompt: job.prompt || '',
    targetKind: (job.target_kind as AutomationTargetKind) || 'active_identity',
    targetIdentityId: job.target_identity_id || '',
    targetGroupId: job.target_group_id || '',
    targetChatId: job.target_chat_id || '',
    permissionMode: (job.permission_mode as AutomationPermissionMode) || 'standard',
    toolPacksText: (job.tool_packs || []).join(', '),
  };
}

function secondsFor(value: string, unitValue: string) {
  const amount = Number.parseInt(value, 10);
  if (!Number.isFinite(amount) || amount <= 0) return null;
  const unit = singularUnit(unitValue);
  if (unit === 'second') return amount;
  if (unit === 'minute') return amount * 60;
  if (unit === 'hour') return amount * 3600;
  if (unit === 'day') return amount * 86400;
  return null;
}

export function previewAutomationNextRun(draft: AutomationEditorDraft, now = new Date()) {
  if (Object.keys(validateAutomationDraft({ ...draft, name: draft.name || 'Preview', prompt: draft.prompt || 'Preview' })).some((key) => (
    !['name', 'prompt', 'targetIdentityId', 'targetGroupId'].includes(key)
  ))) return null;

  if (draft.scheduleMode === 'daily') {
    const [hour, minute] = draft.dailyTime.split(':').map(Number);
    const next = new Date(now);
    next.setHours(hour, minute, 0, 0);
    if (next.getTime() <= now.getTime()) next.setDate(next.getDate() + 1);
    return next;
  }
  if (draft.scheduleMode === 'delay') {
    const seconds = secondsFor(draft.delayAmount, draft.delayUnit);
    return seconds ? new Date(now.getTime() + seconds * 1000) : null;
  }
  if (draft.scheduleMode === 'interval') {
    const seconds = secondsFor(draft.intervalAmount, draft.intervalUnit);
    return seconds ? new Date(now.getTime() + seconds * 1000) : null;
  }
  const delayMatch = /^in (\d+) (second|minute|hour|day)s?$/i.exec(draft.advancedSchedule.trim());
  if (delayMatch) {
    const seconds = secondsFor(delayMatch[1], delayMatch[2]);
    return seconds ? new Date(now.getTime() + seconds * 1000) : null;
  }
  const intervalMatch = /^every (\d+) (second|minute|hour|day)s?$/i.exec(draft.advancedSchedule.trim());
  if (intervalMatch) {
    const seconds = secondsFor(intervalMatch[1], intervalMatch[2]);
    return seconds ? new Date(now.getTime() + seconds * 1000) : null;
  }
  const dailyMatch = /^every day at (\d{2}):(\d{2})$/i.exec(draft.advancedSchedule.trim());
  if (dailyMatch) {
    const next = new Date(now);
    next.setHours(Number(dailyMatch[1]), Number(dailyMatch[2]), 0, 0);
    if (next.getTime() <= now.getTime()) next.setDate(next.getDate() + 1);
    return next;
  }
  return null;
}

export function automationPermissionLabel(value?: string | null) {
  if (value === 'low') return 'Ask Before Acting';
  if (value === 'full_permissions') return 'Full Access';
  return 'Confirm Risky Actions';
}

export function automationTargetLabel(job: ScheduledJob) {
  if (job.target_kind === 'manager') return 'Manager';
  if (job.target_kind === 'identity') return 'Specific Fleet Identity';
  if (job.target_kind === 'group') return 'Fleet Group';
  return 'Current Active Identity';
}

export function automationNeedsAttention(job: ScheduledJob) {
  const status = String(job.status || '').toLowerCase();
  return Boolean((job.error_count || 0) > 0 || ['failed', 'blocked', 'needs_review', 'needs_confirmation'].includes(status));
}

export function automationMatchesFilter(job: ScheduledJob, filter: AutomationListFilter, query: string) {
  const normalizedQuery = query.trim().toLowerCase();
  if (normalizedQuery && !`${job.name} ${job.prompt} ${job.schedule || ''}`.toLowerCase().includes(normalizedQuery)) return false;
  if (filter === 'active') return job.enabled && !automationNeedsAttention(job);
  if (filter === 'paused') return !job.enabled;
  if (filter === 'attention') return automationNeedsAttention(job);
  return true;
}

function automationReferenceIds(job: ScheduledJob) {
  return new Set([job.id, job.automation_id].filter(Boolean).map(String));
}

function automationSessionIds(job: ScheduledJob) {
  return new Set([job.target_chat_id, job.origin_session_id].filter(Boolean).map(String));
}

function metadataMatchesJob(metadata: Record<string, unknown> | undefined, ids: Set<string>) {
  if (!metadata) return false;
  return ['automation_id', 'job_id', 'scheduled_job_id'].some((key) => ids.has(String(metadata[key] || '')));
}

export function processWaitMatchesAutomation(item: ProcessWait, job: ScheduledJob) {
  return automationSessionIds(job).has(String(item.session_id || '')) || metadataMatchesJob(item.metadata, automationReferenceIds(job));
}

export function plannerContractMatchesAutomation(item: PlannerContract, job: ScheduledJob) {
  return automationSessionIds(job).has(String(item.session_id || '')) || metadataMatchesJob(item.contract, automationReferenceIds(job));
}

export function eventRunMatchesAutomation(run: AutomationEventRun, job: ScheduledJob) {
  return automationReferenceIds(job).has(String(run.automation_id || '')) || metadataMatchesJob(run.metadata, automationReferenceIds(job));
}

export function cronFeedMatchesAutomation(item: CronFeedItem, job: ScheduledJob) {
  const ids = automationReferenceIds(job);
  return ids.has(String(item.automation_id || ''))
    || ids.has(String(item.job_id || ''))
    || metadataMatchesJob(item.metadata, ids);
}
