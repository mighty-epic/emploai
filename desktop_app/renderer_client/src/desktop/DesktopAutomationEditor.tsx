import { useMemo, useRef, useState } from 'react';
import { Pressable, ScrollView, Text, TextInput, View } from 'react-native';

import type { FleetGroup, FleetIdentity, SessionSummary } from '@/lib/appApi';
import type { DesktopPressableState } from '@/lib/pressableState';
import { automationStyles as styles } from './DesktopAutomations.styles';
import {
  AUTOMATION_SCHEDULE_UNITS,
  automationPermissionLabel,
  buildAutomationSchedule,
  emptyAutomationDraft,
  previewAutomationNextRun,
  validateAutomationDraft,
  type AutomationFieldErrors,
  type AutomationEditorDraft,
  type AutomationPermissionMode,
  type AutomationScheduleMode,
  type AutomationTargetKind,
} from './desktopAutomations';

type Props = {
  mode: 'create' | 'edit';
  initialDraft: AutomationEditorDraft;
  identities: FleetIdentity[];
  groups: FleetGroup[];
  sessions: SessionSummary[];
  busy: boolean;
  onSave: (draft: AutomationEditorDraft) => void | Promise<void>;
  onRequestClose: (dirty: boolean) => void | Promise<void>;
};

const SCHEDULE_OPTIONS: Array<{ key: AutomationScheduleMode; label: string; description: string }> = [
  { key: 'interval', label: 'Repeating', description: 'Run after the same amount of time.' },
  { key: 'daily', label: 'Daily', description: 'Run at a specific local time every day.' },
  { key: 'delay', label: 'One Time', description: 'Run once after a short delay.' },
  { key: 'advanced', label: 'Advanced', description: 'Use a supported schedule phrase.' },
];

const TARGET_OPTIONS: Array<{ key: AutomationTargetKind; label: string; description: string }> = [
  { key: 'active_identity', label: 'Current Identity', description: 'Use whichever local identity is active when the automation runs.' },
  { key: 'manager', label: 'Manager', description: 'Always route this automation through the local manager.' },
  { key: 'identity', label: 'Specific Identity', description: 'Choose one manager or Fleet worker.' },
  { key: 'group', label: 'Fleet Group', description: 'Route the work to a saved Fleet group.' },
];

const PERMISSION_OPTIONS: Array<{ key: AutomationPermissionMode; label: string; description: string }> = [
  { key: 'standard', label: 'Confirm Risky Actions', description: 'Runs normally but pauses for destructive or sensitive actions. Recommended.' },
  { key: 'low', label: 'Ask Before Acting', description: 'Pauses before tools make changes. Best for new automations.' },
  { key: 'full_permissions', label: 'Full Access', description: 'Allows configured tools to act without an additional approval prompt.' },
];

function controlStyle({ hovered, pressed }: DesktopPressableState) {
  return [styles.button, hovered ? styles.buttonHover : null, pressed ? styles.buttonPressed : null];
}

function ChoiceButton({
  label,
  selected,
  onPress,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ checked: selected }}
      style={({ hovered, pressed }: DesktopPressableState) => [
        styles.choice,
        selected ? styles.choiceSelected : null,
        hovered ? styles.buttonHover : null,
        pressed ? styles.buttonPressed : null,
      ]}
      onPress={onPress}
    >
      <Text style={[styles.choiceText, selected ? styles.choiceTextSelected : null]}>{label}</Text>
    </Pressable>
  );
}

function OptionCard({
  label,
  description,
  selected,
  onPress,
}: {
  label: string;
  description: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityLabel={`${label}. ${description}`}
      accessibilityState={{ checked: selected }}
      style={({ hovered, pressed }: DesktopPressableState) => [
        styles.optionCard,
        selected ? styles.optionCardSelected : null,
        hovered ? styles.buttonHover : null,
        pressed ? styles.buttonPressed : null,
      ]}
      onPress={onPress}
    >
      <Text style={styles.optionTitle}>{label}</Text>
      <Text style={styles.optionCopy}>{description}</Text>
    </Pressable>
  );
}

export function DesktopAutomationEditor({ mode, initialDraft, identities, groups, sessions, busy, onSave, onRequestClose }: Props) {
  const [draft, setDraft] = useState(initialDraft);
  const [errors, setErrors] = useState<AutomationFieldErrors>({});
  const [advancedOpen, setAdvancedOpen] = useState(Boolean(initialDraft.targetChatId || initialDraft.toolPacksText));
  const baselineRef = useRef(JSON.stringify(initialDraft));
  const nameRef = useRef<TextInput | null>(null);
  const promptRef = useRef<TextInput | null>(null);
  const scheduleRef = useRef<TextInput | null>(null);

  const dirty = JSON.stringify(draft) !== baselineRef.current;
  const schedule = buildAutomationSchedule(draft);
  const nextRun = useMemo(() => previewAutomationNextRun(draft), [draft]);
  const timezone = useMemo(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || 'local time';
    } catch {
      return 'local time';
    }
  }, []);
  const nextRunLabel = nextRun
    ? new Intl.DateTimeFormat(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(nextRun)
    : 'Fix the schedule to preview the next run';

  const update = <K extends keyof AutomationEditorDraft>(key: K, value: AutomationEditorDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined, schedule: undefined }));
  };

  const submit = () => {
    const nextErrors = validateAutomationDraft(draft);
    setErrors(nextErrors);
    const firstError = Object.keys(nextErrors)[0];
    if (firstError) {
      if (firstError === 'name') nameRef.current?.focus();
      else if (firstError === 'prompt') promptRef.current?.focus();
      else scheduleRef.current?.focus();
      return;
    }
    void onSave(draft);
  };

  const reset = () => {
    const next = mode === 'edit' ? initialDraft : emptyAutomationDraft();
    setDraft(next);
    setErrors({});
  };

  return (
    <View style={styles.editor}>
      <View style={styles.editorHeader}>
        <Text style={styles.eyebrow}>{mode === 'edit' ? 'Edit Automation' : 'New Automation'}</Text>
        <Text style={styles.detailTitle}>{mode === 'edit' ? `Update ${initialDraft.name}` : 'Schedule work with a clear safety boundary'}</Text>
        <Text style={styles.detailSubtitle}>Define the task first. Routing and tool controls stay optional until you need them.</Text>
      </View>
      <ScrollView style={styles.detailScroll} contentContainerStyle={styles.editorBody} keyboardShouldPersistTaps="handled">
        <View style={styles.editorSection}>
          <Text style={styles.editorSectionTitle}>1. What Should Happen?</Text>
          <Text style={styles.editorSectionCopy}>Use a short name and give the agent enough detail to know when the work is complete.</Text>
          <View style={styles.field}>
            <Text style={styles.fieldLabel}>Name <Text style={styles.required}>*</Text></Text>
            <TextInput
              ref={nameRef}
              accessibilityLabel="Automation name"
              autoComplete="off"
              value={draft.name}
              onChangeText={(value) => update('name', value)}
              placeholder="Example: Morning project brief…"
              placeholderTextColor="#748194"
              style={[styles.input, errors.name ? styles.inputError : null]}
            />
            {errors.name ? <Text accessibilityLiveRegion="polite" style={styles.fieldError}>{errors.name}</Text> : null}
          </View>
          <View style={styles.field}>
            <Text style={styles.fieldLabel}>Task <Text style={styles.required}>*</Text></Text>
            <TextInput
              ref={promptRef}
              accessibilityLabel="Automation task"
              autoComplete="off"
              value={draft.prompt}
              onChangeText={(value) => update('prompt', value)}
              multiline
              placeholder="Describe the result you want and what should be checked…"
              placeholderTextColor="#748194"
              style={[styles.input, styles.textArea, errors.prompt ? styles.inputError : null]}
            />
            {errors.prompt ? <Text accessibilityLiveRegion="polite" style={styles.fieldError}>{errors.prompt}</Text> : null}
          </View>
        </View>

        <View style={styles.editorSection}>
          <Text style={styles.editorSectionTitle}>2. When Should It Run?</Text>
          <Text style={styles.editorSectionCopy}>Daily schedules use this computer’s timezone: {timezone}.</Text>
          <View accessibilityRole="radiogroup" accessibilityLabel="Schedule type" style={styles.optionStack}>
            {SCHEDULE_OPTIONS.map((option) => (
              <OptionCard
                key={option.key}
                label={option.label}
                description={option.description}
                selected={draft.scheduleMode === option.key}
                onPress={() => update('scheduleMode', option.key)}
              />
            ))}
          </View>
          {draft.scheduleMode === 'interval' || draft.scheduleMode === 'delay' ? (
            <View style={styles.fieldRow}>
              <View style={styles.fieldHalf}>
                <Text style={styles.fieldLabel}>Amount</Text>
                <TextInput
                  ref={scheduleRef}
                  accessibilityLabel={`${draft.scheduleMode === 'delay' ? 'Delay' : 'Interval'} amount`}
                  autoComplete="off"
                  inputMode="numeric"
                  value={draft.scheduleMode === 'delay' ? draft.delayAmount : draft.intervalAmount}
                  onChangeText={(value) => update(draft.scheduleMode === 'delay' ? 'delayAmount' : 'intervalAmount', value)}
                  placeholder="1…"
                  placeholderTextColor="#748194"
                  style={[styles.input, errors.delayAmount || errors.intervalAmount ? styles.inputError : null]}
                />
                {errors.delayAmount || errors.intervalAmount ? <Text accessibilityLiveRegion="polite" style={styles.fieldError}>{errors.delayAmount || errors.intervalAmount}</Text> : null}
              </View>
              <View style={styles.fieldHalf}>
                <Text style={styles.fieldLabel}>Unit</Text>
                <View accessibilityRole="radiogroup" accessibilityLabel="Schedule unit" style={styles.choiceRow}>
                  {AUTOMATION_SCHEDULE_UNITS.map((unit) => {
                    const current = draft.scheduleMode === 'delay' ? draft.delayUnit : draft.intervalUnit;
                    return <ChoiceButton key={unit} label={unit} selected={current === unit} onPress={() => update(draft.scheduleMode === 'delay' ? 'delayUnit' : 'intervalUnit', unit)} />;
                  })}
                </View>
              </View>
            </View>
          ) : null}
          {draft.scheduleMode === 'daily' ? (
            <View style={styles.field}>
              <Text style={styles.fieldLabel}>Local Time</Text>
              <TextInput
                ref={scheduleRef}
                accessibilityLabel="Daily run time"
                autoComplete="off"
                value={draft.dailyTime}
                onChangeText={(value) => update('dailyTime', value)}
                placeholder="08:00…"
                placeholderTextColor="#748194"
                style={[styles.input, errors.dailyTime ? styles.inputError : null]}
              />
              {errors.dailyTime ? <Text accessibilityLiveRegion="polite" style={styles.fieldError}>{errors.dailyTime}</Text> : null}
            </View>
          ) : null}
          {draft.scheduleMode === 'advanced' ? (
            <View style={styles.field}>
              <Text style={styles.fieldLabel}>Schedule Phrase</Text>
              <TextInput
                ref={scheduleRef}
                accessibilityLabel="Advanced schedule phrase"
                autoComplete="off"
                value={draft.advancedSchedule}
                onChangeText={(value) => update('advancedSchedule', value)}
                placeholder="Example: every day at 08:00…"
                placeholderTextColor="#748194"
                style={[styles.input, errors.advancedSchedule ? styles.inputError : null]}
              />
              {errors.advancedSchedule ? <Text accessibilityLiveRegion="polite" style={styles.fieldError}>{errors.advancedSchedule}</Text> : null}
            </View>
          ) : null}
          <View style={styles.reviewStrip}>
            <Text style={styles.reviewTitle}>{schedule || 'Add a schedule'}</Text>
            <Text style={styles.reviewCopy}>Next run: {nextRunLabel}</Text>
          </View>
        </View>

        <View style={styles.editorSection}>
          <Text style={styles.editorSectionTitle}>3. Where Should It Work?</Text>
          <Text style={styles.editorSectionCopy}>Most automations can follow the current identity. Choose a fixed destination only when routing must never change.</Text>
          <View accessibilityRole="radiogroup" accessibilityLabel="Automation target" style={styles.optionStack}>
            {TARGET_OPTIONS.map((option) => (
              <OptionCard key={option.key} label={option.label} description={option.description} selected={draft.targetKind === option.key} onPress={() => update('targetKind', option.key)} />
            ))}
          </View>
          {draft.targetKind === 'identity' ? (
            <View style={styles.field}>
              <Text style={styles.fieldLabel}>Identity</Text>
              {identities.length ? (
                <View accessibilityRole="radiogroup" accessibilityLabel="Fleet identity" style={styles.choiceRow}>
                  {identities.map((identity) => <ChoiceButton key={identity.identity_id} label={identity.display_name} selected={draft.targetIdentityId === identity.identity_id} onPress={() => update('targetIdentityId', identity.identity_id)} />)}
                </View>
              ) : <Text style={styles.fieldError}>Create or enroll a Fleet identity before using this destination.</Text>}
              {errors.targetIdentityId ? <Text accessibilityLiveRegion="polite" style={styles.fieldError}>{errors.targetIdentityId}</Text> : null}
            </View>
          ) : null}
          {draft.targetKind === 'group' ? (
            <View style={styles.field}>
              <Text style={styles.fieldLabel}>Fleet Group</Text>
              {groups.length ? (
                <View accessibilityRole="radiogroup" accessibilityLabel="Fleet group" style={styles.choiceRow}>
                  {groups.map((group) => <ChoiceButton key={group.group_id} label={group.display_name} selected={draft.targetGroupId === group.group_id} onPress={() => update('targetGroupId', group.group_id)} />)}
                </View>
              ) : <Text style={styles.fieldError}>Create a Fleet group before using this destination.</Text>}
              {errors.targetGroupId ? <Text accessibilityLiveRegion="polite" style={styles.fieldError}>{errors.targetGroupId}</Text> : null}
            </View>
          ) : null}
        </View>

        <View style={styles.editorSection}>
          <Text style={styles.editorSectionTitle}>4. Safety</Text>
          <Text style={styles.editorSectionCopy}>Choose how the automation should behave when tools could change files, processes, or external systems.</Text>
          <View accessibilityRole="radiogroup" accessibilityLabel="Automation permission level" style={styles.optionStack}>
            {PERMISSION_OPTIONS.map((option) => (
              <OptionCard key={option.key} label={option.label} description={option.description} selected={draft.permissionMode === option.key} onPress={() => update('permissionMode', option.key)} />
            ))}
          </View>
          {draft.permissionMode === 'full_permissions' ? (
            <View accessibilityRole="alert" style={styles.warningPanel}>
              <Text style={styles.warningTitle}>Full Access removes an important pause.</Text>
              <Text style={styles.warningCopy}>Use it only for a narrow, trusted task with tools you have already reviewed.</Text>
            </View>
          ) : null}
        </View>

        <View style={styles.editorSection}>
          <Pressable accessibilityRole="button" accessibilityState={{ expanded: advancedOpen }} style={controlStyle} onPress={() => setAdvancedOpen((value) => !value)}>
            <Text style={styles.buttonText}>{advancedOpen ? 'Hide Advanced Routing' : 'Show Advanced Routing'}</Text>
          </Pressable>
          {advancedOpen ? (
            <>
              <View style={styles.field}>
                <Text style={styles.fieldLabel}>Specific Chat</Text>
                <View accessibilityRole="radiogroup" accessibilityLabel="Specific chat" style={styles.choiceRow}>
                  <ChoiceButton label="Choose Automatically" selected={!draft.targetChatId} onPress={() => update('targetChatId', '')} />
                  {sessions.slice(0, 20).map((session) => <ChoiceButton key={session.id} label={session.name || session.id} selected={draft.targetChatId === session.id} onPress={() => update('targetChatId', session.id)} />)}
                </View>
              </View>
              <View style={styles.field}>
                <Text style={styles.fieldLabel}>Additional Tool Packs</Text>
                <TextInput
                  accessibilityLabel="Additional tool packs"
                  autoComplete="off"
                  value={draft.toolPacksText}
                  onChangeText={(value) => update('toolPacksText', value)}
                  placeholder="Example: browser_isolated, scheduler…"
                  placeholderTextColor="#748194"
                  style={styles.input}
                />
                <Text style={styles.editorSectionCopy}>Optional local tool-pack IDs, separated with commas.</Text>
              </View>
            </>
          ) : null}
        </View>

        <View style={styles.reviewStrip}>
          <Text style={styles.reviewTitle}>Review</Text>
          <Text style={styles.reviewCopy}>{draft.name.trim() || 'Untitled automation'} · {schedule || 'No schedule'} · {automationPermissionLabel(draft.permissionMode)}</Text>
          <Text style={styles.reviewCopy}>Next run: {nextRunLabel}</Text>
        </View>

        <View style={styles.editorFooter}>
          <Text style={styles.editorSectionCopy}>{dirty ? 'Unsaved changes' : 'No unsaved changes'}</Text>
          <View style={styles.editorFooterActions}>
            <Pressable accessibilityRole="button" disabled={busy} style={controlStyle} onPress={reset}>
              <Text style={styles.buttonText}>{mode === 'edit' ? 'Revert Changes' : 'Clear Form'}</Text>
            </Pressable>
            <Pressable accessibilityRole="button" disabled={busy} style={controlStyle} onPress={() => void onRequestClose(dirty)}>
              <Text style={styles.buttonText}>Cancel</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={mode === 'edit' ? 'Save automation changes' : 'Create automation'}
              disabled={busy}
              style={(state: DesktopPressableState) => [
                ...controlStyle(state),
                styles.primaryButton,
                busy ? styles.disabled : null,
              ]}
              onPress={submit}
            >
              <Text style={[styles.buttonText, styles.primaryButtonText]}>{busy ? 'Saving…' : mode === 'edit' ? 'Save Changes' : 'Create Automation'}</Text>
            </Pressable>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}
