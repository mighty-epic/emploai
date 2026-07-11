import { useEffect, useMemo, useState } from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';

import { styles } from './DesktopSetupPanel.styles';
import { normalizeWorkspacePath, projectPathBasename } from './desktopSidebarState';
import { toolPackLabel } from './desktopToolPacks';
import {
  fetchProjectOnboarding,
  saveProjectOnboarding,
  summarizeProjectOnboarding,
  type ProjectOnboardingGuideMessage,
  type ProjectOnboardingProfile,
  type ProjectOnboardingToolRequirement,
  type SessionSummary,
} from '@/lib/appApi';
import { userFacingError } from '../../lib/diagnostics';

type Props = {
  apiBaseUrl?: string | null;
  token?: string | null;
  sessions?: SessionSummary[];
  defaultWorkspace?: string | null;
  onProfileChange?: (profile: ProjectOnboardingProfile) => void;
};

type DraftState = {
  enabled: boolean;
  role_identity: string;
  job_mission: string;
  required_tools: string;
  workflows: string;
  constraints: string;
  communication_style: string;
  raw_notes: string;
  prompt_preview: string;
};

type Mode = 'guided' | 'structured';
type StatusTone = 'neutral' | 'success' | 'error';

const EMPTY_DRAFT: DraftState = {
  enabled: false,
  role_identity: '',
  job_mission: '',
  required_tools: '',
  workflows: '',
  constraints: '',
  communication_style: '',
  raw_notes: '',
  prompt_preview: '',
};

const GUIDED_QUESTIONS = [
  {
    key: 'role_identity',
    label: 'Agent identity',
    question: 'Who should the agent be for this project?',
    placeholder: 'Example: senior ops assistant for the trade_system repo',
  },
  {
    key: 'job_mission',
    label: 'Job',
    question: 'What is the agent responsible for delivering?',
    placeholder: 'Example: maintain workflows, debug issues, prepare releases',
  },
  {
    key: 'required_tools',
    label: 'Tools',
    question: 'Which tools, accounts, apps, or integrations does it need?',
    placeholder: 'Example: browser, Gmail, Telegram, repo file edits, scheduled checks',
  },
  {
    key: 'workflows',
    label: 'Workflows',
    question: 'Which repeatable workflows should it understand?',
    placeholder: 'Example: review tasks, run tests, summarize failures, update docs',
  },
  {
    key: 'constraints',
    label: 'Boundaries',
    question: 'What should the agent avoid or ask before doing?',
    placeholder: 'Example: ask before deleting data or changing production credentials',
  },
  {
    key: 'communication_style',
    label: 'Style',
    question: 'How should the agent communicate while working?',
    placeholder: 'Example: concise, direct, mention risks before acting',
  },
  {
    key: 'raw_notes',
    label: 'Notes',
    question: 'Add any extra project context.',
    placeholder: 'Paste notes, internal names, conventions, or edge cases',
  },
] as const;

function listToText(items: string[] | null | undefined) {
  return (items || []).map((item) => String(item || '').trim()).filter(Boolean).join('\n');
}

function textToList(value: string) {
  return String(value || '')
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function profileToDraft(profile: ProjectOnboardingProfile | null | undefined): DraftState {
  if (!profile) {
    return EMPTY_DRAFT;
  }
  return {
    enabled: Boolean(profile.enabled),
    role_identity: profile.role_identity || '',
    job_mission: profile.job_mission || '',
    required_tools: listToText(profile.required_tools),
    workflows: listToText(profile.workflows),
    constraints: profile.constraints || '',
    communication_style: profile.communication_style || '',
    raw_notes: profile.raw_notes || '',
    prompt_preview: profile.prompt_preview || '',
  };
}

function draftFromGuidedAnswers(answers: Record<string, string>): DraftState {
  return {
    ...EMPTY_DRAFT,
    enabled: true,
    role_identity: answers.role_identity || '',
    job_mission: answers.job_mission || '',
    required_tools: listToText(textToList(answers.required_tools || '')),
    workflows: listToText(textToList(answers.workflows || '')),
    constraints: answers.constraints || '',
    communication_style: answers.communication_style || '',
    raw_notes: answers.raw_notes || '',
  };
}

function buildGuidedTranscript(answers: Record<string, string>): ProjectOnboardingGuideMessage[] {
  const createdAt = new Date().toISOString();
  return GUIDED_QUESTIONS.flatMap((item) => {
    const answer = String(answers[item.key] || '').trim();
    if (!answer) {
      return [];
    }
    return [
      {
        role: 'assistant' as const,
        content: item.question,
        created_at: createdAt,
      },
      {
        role: 'user' as const,
        content: answer,
        created_at: createdAt,
      },
    ];
  });
}

function statusStyle(tone: StatusTone) {
  if (tone === 'success') {
    return styles.validationTextValid;
  }
  if (tone === 'error') {
    return styles.validationTextError;
  }
  return styles.validationTextChecking;
}

function requirementStatusStyle(status: ProjectOnboardingToolRequirement['status']) {
  if (status === 'missing') {
    return styles.validationTextError;
  }
  return styles.validationTextValid;
}

export function DesktopSetupOnboardingSection({
  apiBaseUrl,
  token,
  sessions = [],
  defaultWorkspace,
  onProfileChange,
}: Props) {
  const projectOptions = useMemo(() => {
    const items = new Map<string, { path: string; label: string; detail: string }>();
    const addProject = (pathValue: string | null | undefined, detail: string) => {
      const normalized = normalizeWorkspacePath(pathValue);
      if (!normalized || items.has(normalized.toLowerCase())) {
        return;
      }
      items.set(normalized.toLowerCase(), {
        path: normalized,
        label: projectPathBasename(normalized),
        detail,
      });
    };
    addProject(defaultWorkspace, 'Default workspace');
    sessions.forEach((session) => {
      addProject(session.workspace, session.name ? `Chat: ${session.name}` : 'Recent chat');
    });
    return Array.from(items.values());
  }, [defaultWorkspace, sessions]);

  const [mode, setMode] = useState<Mode>('guided');
  const [selectedWorkspace, setSelectedWorkspace] = useState('');
  const [activeWorkspace, setActiveWorkspace] = useState('');
  const [workspaceInput, setWorkspaceInput] = useState('');
  const [guidedAnswers, setGuidedAnswers] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT);
  const [toolRequirements, setToolRequirements] = useState<ProjectOnboardingToolRequirement[]>([]);
  const [updatedSessionIds, setUpdatedSessionIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState('');
  const [statusTone, setStatusTone] = useState<StatusTone>('neutral');

  const canUseApi = Boolean(apiBaseUrl && token);
  const resolvedWorkspace = normalizeWorkspacePath(activeWorkspace);
  const pendingWorkspaceInput = normalizeWorkspacePath(workspaceInput);
  const canLoadWorkspace = canUseApi && Boolean(resolvedWorkspace);

  useEffect(() => {
    if (selectedWorkspace || workspaceInput || !projectOptions[0]?.path) {
      return;
    }
    setSelectedWorkspace(projectOptions[0].path);
    setActiveWorkspace(projectOptions[0].path);
    setWorkspaceInput(projectOptions[0].path);
  }, [activeWorkspace, projectOptions, selectedWorkspace, workspaceInput]);

  useEffect(() => {
    if (!canLoadWorkspace) {
      setDraft(EMPTY_DRAFT);
      setToolRequirements([]);
      setUpdatedSessionIds([]);
      return;
    }

    let disposed = false;
    setLoading(true);
    setStatus('Loading project onboarding...');
    setStatusTone('neutral');
    void (async () => {
      try {
        const response = await fetchProjectOnboarding(apiBaseUrl!, token!, resolvedWorkspace);
        if (disposed) {
          return;
        }
        setDraft(profileToDraft(response.profile));
        setToolRequirements(response.tool_requirements || []);
        setUpdatedSessionIds([]);
        onProfileChange?.(response.profile);
        setStatus(response.profile.updated_at ? 'Loaded saved project onboarding.' : 'No onboarding saved for this project yet.');
        setStatusTone('neutral');
      } catch (error) {
        if (disposed) {
          return;
        }
        setDraft(EMPTY_DRAFT);
        setToolRequirements([]);
        setUpdatedSessionIds([]);
        setStatus(userFacingError(error, 'Could not load project onboarding.'));
        setStatusTone('error');
      } finally {
        if (!disposed) {
          setLoading(false);
        }
      }
    })();

    return () => {
      disposed = true;
    };
  }, [apiBaseUrl, token, canLoadWorkspace, resolvedWorkspace]);

  const updateGuidedAnswer = (key: string, value: string) => {
    setGuidedAnswers((current) => ({ ...current, [key]: value }));
  };

  const updateDraft = (patch: Partial<DraftState>) => {
    setDraft((current) => ({ ...current, ...patch }));
  };

  const selectWorkspace = (pathValue: string) => {
    setSelectedWorkspace(pathValue);
    setActiveWorkspace(pathValue);
    setWorkspaceInput(pathValue);
  };

  const useTypedWorkspace = () => {
    const nextWorkspace = normalizeWorkspacePath(workspaceInput);
    if (!nextWorkspace) {
      setStatus('Enter a project path before loading onboarding.');
      setStatusTone('error');
      return;
    }
    setSelectedWorkspace('');
    setActiveWorkspace(nextWorkspace);
  };

  const buildDraft = async () => {
    if (!canLoadWorkspace) {
      setStatus('Choose a project path before building onboarding.');
      setStatusTone('error');
      return;
    }
    setSaving(true);
    setStatus('Building onboarding draft...');
    setStatusTone('neutral');
    try {
      const transcript = buildGuidedTranscript(guidedAnswers);
      const response = await summarizeProjectOnboarding(apiBaseUrl!, token!, {
        workspace: resolvedWorkspace,
        answers: guidedAnswers,
        guided_transcript: transcript,
      });
      setDraft(profileToDraft(response.profile));
      setToolRequirements(response.tool_requirements || []);
      setUpdatedSessionIds([]);
      onProfileChange?.(response.profile);
      setMode('structured');
      setStatus(response.message || 'Draft created. Review it, then save.');
      setStatusTone('success');
    } catch (error) {
      setDraft(draftFromGuidedAnswers(guidedAnswers));
      setStatus(userFacingError(error, 'Could not build draft. Structured fields were filled from your answers.'));
      setStatusTone('error');
    } finally {
      setSaving(false);
    }
  };

  const saveDraft = async () => {
    if (!canLoadWorkspace) {
      setStatus('Choose a project path before saving onboarding.');
      setStatusTone('error');
      return;
    }
    setSaving(true);
    setStatus('Saving project onboarding...');
    setStatusTone('neutral');
    try {
      const response = await saveProjectOnboarding(apiBaseUrl!, token!, {
        workspace: resolvedWorkspace,
        enabled: draft.enabled,
        role_identity: draft.role_identity,
        job_mission: draft.job_mission,
        required_tools: textToList(draft.required_tools),
        workflows: textToList(draft.workflows),
        constraints: draft.constraints,
        communication_style: draft.communication_style,
        raw_notes: draft.raw_notes,
        desired_tool_packs: [],
        missing_requirements: [],
        guided_transcript: buildGuidedTranscript(guidedAnswers),
        apply_tool_packs: true,
      });
      setDraft(profileToDraft(response.profile));
      setToolRequirements(response.tool_requirements || []);
      setUpdatedSessionIds(response.updated_session_ids || []);
      onProfileChange?.(response.profile);
      setStatus(response.message || 'Project onboarding saved.');
      setStatusTone('success');
    } catch (error) {
      setStatus(userFacingError(error, 'Could not save project onboarding.'));
      setStatusTone('error');
    } finally {
      setSaving(false);
    }
  };

  const buttonDisabled = loading || saving || !canLoadWorkspace;
  const usePathDisabled = loading || saving || !pendingWorkspaceInput || pendingWorkspaceInput.toLowerCase() === resolvedWorkspace.toLowerCase();

  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>Project onboarding</Text>
      <Text style={styles.helperText}>
        Save a per-project job profile that becomes a managed system prompt section whenever a chat runs in that workspace.
      </Text>

      <View style={styles.settingStack}>
        <View style={styles.settingCard}>
          <Text style={styles.settingCardTitle}>Project</Text>
          <Text style={styles.settingCardDescription}>
            Pick an existing project or enter a path. Onboarding is matched by workspace path.
          </Text>
          {projectOptions.length ? (
            <View style={styles.voiceModeRow}>
              {projectOptions.slice(0, 8).map((item) => {
                const selected = normalizeWorkspacePath(item.path).toLowerCase() === resolvedWorkspace.toLowerCase();
                return (
                  <Pressable
                    key={item.path}
                    style={[styles.voiceModeButton, selected ? styles.voiceModeButtonActive : null]}
                    onPress={() => selectWorkspace(item.path)}
                  >
                    <Text style={[styles.voiceModeButtonText, selected ? styles.voiceModeButtonTextActive : null]}>
                      {item.label}
                    </Text>
                    <Text style={[styles.voiceModeHelper, selected ? styles.sleepModeActionButtonTextActive : null]}>
                      {item.detail}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          ) : null}
          <TextInput
            value={workspaceInput}
            onChangeText={(next) => {
              setWorkspaceInput(next);
              setSelectedWorkspace('');
            }}
            style={styles.input}
            placeholder="C:\\Users\\You\\Documents\\Project"
            placeholderTextColor="#7f93b5"
            autoCapitalize="none"
            autoCorrect={false}
          />
          <View style={styles.pathActions}>
            <Pressable
              style={[styles.compactActionButton, usePathDisabled ? styles.buttonDisabled : null]}
              onPress={useTypedWorkspace}
              disabled={usePathDisabled}
            >
              <Text style={styles.compactActionButtonText}>Use Path</Text>
            </Pressable>
          </View>
          {!canUseApi ? (
            <Text style={[styles.validationText, styles.validationTextError]}>
              Local runtime API is unavailable. Start the desktop app runtime before editing onboarding.
            </Text>
          ) : null}
        </View>

        <View style={styles.settingCard}>
          <View style={styles.settingRow}>
            <View style={styles.settingRowCopy}>
              <Text style={styles.settingRowTitle}>Use this onboarding profile</Text>
              <Text style={styles.settingRowDescription}>
                When enabled, the saved profile is appended after the core runtime prompt for chats in this project.
              </Text>
            </View>
            <Pressable
              style={[styles.toggleSwitch, draft.enabled ? styles.toggleSwitchActive : null]}
              onPress={() => updateDraft({ enabled: !draft.enabled })}
            >
              <View style={[styles.toggleSwitchKnob, draft.enabled ? styles.toggleSwitchKnobActive : null]} />
            </Pressable>
          </View>
        </View>

        <View style={styles.voiceModeRow}>
          {[
            { value: 'guided' as const, label: 'Guided' },
            { value: 'structured' as const, label: 'Structured' },
          ].map((item) => {
            const selected = mode === item.value;
            return (
              <Pressable
                key={item.value}
                style={[styles.voiceModeButton, selected ? styles.voiceModeButtonActive : null]}
                onPress={() => setMode(item.value)}
              >
                <Text style={[styles.voiceModeButtonText, selected ? styles.voiceModeButtonTextActive : null]}>
                  {item.label}
                </Text>
              </Pressable>
            );
          })}
        </View>

        {mode === 'guided' ? (
          <View style={styles.settingCard}>
            <Text style={styles.settingCardTitle}>Guided onboarding</Text>
            <Text style={styles.settingCardDescription}>
              Answer the questions, then build a structured profile you can review before saving.
            </Text>
            {GUIDED_QUESTIONS.map((item) => (
              <View key={item.key} style={styles.fieldBlock}>
                <Text style={styles.fieldLabel}>{item.label}</Text>
                <Text style={styles.settingCardDescription}>{item.question}</Text>
                <TextInput
                  value={guidedAnswers[item.key] || ''}
                  onChangeText={(next) => updateGuidedAnswer(item.key, next)}
                  style={[styles.input, styles.sharedPromptInput]}
                  placeholder={item.placeholder}
                  placeholderTextColor="#7f93b5"
                  multiline
                  autoCapitalize="sentences"
                />
              </View>
            ))}
            <View style={styles.pathActions}>
              <Pressable
                style={[styles.pathButton, buttonDisabled ? styles.buttonDisabled : null]}
                onPress={() => void buildDraft()}
                disabled={buttonDisabled}
              >
                <Text style={styles.pathButtonText}>{saving ? 'Working...' : 'Build Draft'}</Text>
              </Pressable>
            </View>
          </View>
        ) : (
          <View style={styles.settingCard}>
            <Text style={styles.settingCardTitle}>Structured profile</Text>
            <Text style={styles.settingCardDescription}>
              This is the exact project identity and workflow context that will be saved locally.
            </Text>
            <View style={styles.fieldBlock}>
              <Text style={styles.fieldLabel}>Agent identity</Text>
              <TextInput
                value={draft.role_identity}
                onChangeText={(next) => updateDraft({ role_identity: next })}
                style={styles.input}
                placeholder="Who the agent should be"
                placeholderTextColor="#7f93b5"
              />
            </View>
            <View style={styles.fieldBlock}>
              <Text style={styles.fieldLabel}>Job</Text>
              <TextInput
                value={draft.job_mission}
                onChangeText={(next) => updateDraft({ job_mission: next })}
                style={[styles.input, styles.sharedPromptInput]}
                placeholder="What the agent is responsible for"
                placeholderTextColor="#7f93b5"
                multiline
              />
            </View>
            <View style={styles.fieldBlock}>
              <Text style={styles.fieldLabel}>Required tools</Text>
              <TextInput
                value={draft.required_tools}
                onChangeText={(next) => updateDraft({ required_tools: next })}
                style={[styles.input, styles.localWorkflowInput]}
                placeholder={'One tool or integration per line'}
                placeholderTextColor="#7f93b5"
                multiline
              />
            </View>
            <View style={styles.fieldBlock}>
              <Text style={styles.fieldLabel}>Workflows</Text>
              <TextInput
                value={draft.workflows}
                onChangeText={(next) => updateDraft({ workflows: next })}
                style={[styles.input, styles.sharedPromptInput]}
                placeholder={'One workflow per line'}
                placeholderTextColor="#7f93b5"
                multiline
              />
            </View>
            <View style={styles.fieldBlock}>
              <Text style={styles.fieldLabel}>Boundaries</Text>
              <TextInput
                value={draft.constraints}
                onChangeText={(next) => updateDraft({ constraints: next })}
                style={[styles.input, styles.sharedPromptInput]}
                placeholder="Limits, approvals, and safety rules"
                placeholderTextColor="#7f93b5"
                multiline
              />
            </View>
            <View style={styles.fieldBlock}>
              <Text style={styles.fieldLabel}>Communication style</Text>
              <TextInput
                value={draft.communication_style}
                onChangeText={(next) => updateDraft({ communication_style: next })}
                style={styles.input}
                placeholder="How the agent should report progress"
                placeholderTextColor="#7f93b5"
              />
            </View>
            <View style={styles.fieldBlock}>
              <Text style={styles.fieldLabel}>Extra notes</Text>
              <TextInput
                value={draft.raw_notes}
                onChangeText={(next) => updateDraft({ raw_notes: next })}
                style={[styles.input, styles.sharedPromptInput]}
                placeholder="Additional project context"
                placeholderTextColor="#7f93b5"
                multiline
              />
            </View>
            <View style={styles.pathActions}>
              <Pressable
                style={[styles.pathButton, buttonDisabled ? styles.buttonDisabled : null]}
                onPress={() => void saveDraft()}
                disabled={buttonDisabled}
              >
                <Text style={styles.pathButtonText}>{saving ? 'Saving...' : 'Save Onboarding'}</Text>
              </Pressable>
            </View>
          </View>
        )}

        {toolRequirements.length ? (
          <View style={styles.settingCard}>
            <Text style={styles.settingCardTitle}>Tool readiness</Text>
            {toolRequirements.map((item) => (
              <View key={`${item.tool_pack_id}:${item.status}`} style={styles.settingCardInner}>
                <Text style={styles.settingCardTitle}>{item.label || toolPackLabel(item.tool_pack_id)}</Text>
                <Text style={[styles.validationText, requirementStatusStyle(item.status)]}>
                  {item.status === 'missing' ? 'Needs setup' : 'Enabled'}
                </Text>
                {item.reason ? (
                  <Text style={styles.settingCardDescription}>{item.reason}</Text>
                ) : null}
              </View>
            ))}
          </View>
        ) : null}

        {draft.prompt_preview ? (
          <View style={styles.settingCard}>
            <Text style={styles.settingCardTitle}>Prompt preview</Text>
            <TextInput
              value={draft.prompt_preview}
              style={[styles.input, styles.localCodePreview]}
              multiline
              editable={false}
            />
          </View>
        ) : null}

        {updatedSessionIds.length ? (
          <Text style={[styles.validationText, styles.validationTextValid]}>
            Applied tool packs to {updatedSessionIds.length} existing project chat{updatedSessionIds.length === 1 ? '' : 's'}.
          </Text>
        ) : null}
        {status ? (
          <Text style={[styles.validationText, statusStyle(statusTone)]}>{status}</Text>
        ) : null}
      </View>
    </View>
  );
}
