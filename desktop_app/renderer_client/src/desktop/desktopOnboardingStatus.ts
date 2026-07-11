import type { ProjectOnboardingProfile } from '@/lib/appApi';

export type OnboardingSuggestion = {
  title: string;
  message: string;
  missingLabels: string[];
  actionLabel: string;
};

type RequiredField = {
  key: keyof Pick<
    ProjectOnboardingProfile,
    'role_identity' | 'job_mission' | 'required_tools' | 'workflows' | 'constraints' | 'communication_style'
  >;
  label: string;
};

const REQUIRED_FIELDS: RequiredField[] = [
  { key: 'role_identity', label: 'agent identity' },
  { key: 'job_mission', label: 'job' },
  { key: 'required_tools', label: 'tools' },
  { key: 'workflows', label: 'workflows' },
  { key: 'constraints', label: 'boundaries' },
  { key: 'communication_style', label: 'communication style' },
];

function hasValue(value: unknown) {
  if (Array.isArray(value)) {
    return value.some((item) => String(item || '').trim());
  }
  return Boolean(String(value || '').trim());
}

function workspaceLabel(workspace: string) {
  const clean = String(workspace || '').trim();
  if (!clean) {
    return 'this project';
  }
  const parts = clean.replace(/\\/g, '/').split('/').filter(Boolean);
  return parts[parts.length - 1] || clean;
}

export function onboardingMissingLabels(profile: ProjectOnboardingProfile | null | undefined) {
  if (!profile?.updated_at) {
    return REQUIRED_FIELDS.map((field) => field.label);
  }
  const missing = REQUIRED_FIELDS
    .filter((field) => !hasValue(profile[field.key]))
    .map((field) => field.label);
  if (!profile.enabled) {
    missing.unshift('enable profile');
  }
  if ((profile.missing_requirements || []).length > 0) {
    missing.push('tool setup details');
  }
  return Array.from(new Set(missing));
}

export function buildOnboardingSuggestion(
  profile: ProjectOnboardingProfile | null | undefined,
  workspace: string,
): OnboardingSuggestion | null {
  const missingLabels = onboardingMissingLabels(profile);
  if (!missingLabels.length) {
    return null;
  }

  const project = workspaceLabel(profile?.workspace || workspace);
  if (!profile?.updated_at) {
    return {
      title: 'Project onboarding is still empty',
      message: `Optional, but useful: tell EmploAI what its job is for ${project} so future chats inherit the right role, tools, and workflows.`,
      missingLabels,
      actionLabel: 'Start onboarding',
    };
  }

  return {
    title: 'Project onboarding could use a quick pass',
    message: `The saved profile for ${project} is usable, but a few sections are still missing. Finishing them gives the agent steadier project context.`,
    missingLabels,
    actionLabel: 'Review onboarding',
  };
}
