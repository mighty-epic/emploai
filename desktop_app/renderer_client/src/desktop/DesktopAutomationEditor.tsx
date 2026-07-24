import { useMemo, useRef, useState } from 'react';
import { Pressable, ScrollView, Text, TextInput, View } from 'react-native';

import type { FleetGroup, FleetIdentity, ModelProviderGroup, SessionSummary } from '@/lib/appApi';
import type { DesktopPressableState } from '@/lib/pressableState';
import { automationStyles as styles } from './DesktopAutomations.styles';
import {
  AUTOMATION_SCHEDULE_UNITS,
  buildAutomationSchedule,
  previewAutomationNextRun,
  validateAutomationDraft,
  type AutomationEditorDraft,
  type AutomationFieldErrors,
  type AutomationPermissionMode,
  type AutomationScheduleMode,
} from './desktopAutomations';

type Props = {
  mode: 'create' | 'edit';
  initialDraft: AutomationEditorDraft;
  identities: FleetIdentity[];
  groups?: FleetGroup[];
  sessions: SessionSummary[];
  modelGroups: ModelProviderGroup[];
  variants: string[];
  busy: boolean;
  onSave: (draft: AutomationEditorDraft) => void | Promise<void>;
  onRequestClose: (dirty: boolean) => void | Promise<void>;
};

type SelectOption = { value: string; label: string; detail?: string };

const REPEAT_OPTIONS: SelectOption[] = [
  { value: 'daily', label: 'Daily', detail: 'At a local time each day' },
  { value: 'interval', label: 'Repeating', detail: 'After a fixed interval' },
  { value: 'delay', label: 'One time', detail: 'Run once after a delay' },
  { value: 'advanced', label: 'Advanced', detail: 'Use a schedule phrase' },
];

const CHAT_OPTIONS: SelectOption[] = [
  { value: 'new', label: 'New chat', detail: 'Create a dedicated chat for this automation' },
  { value: 'existing', label: 'Existing chat', detail: 'Use that chat’s complete configuration' },
];

const PERMISSION_OPTIONS: SelectOption[] = [
  { value: 'standard', label: 'Confirm risky actions' },
  { value: 'low', label: 'Ask before acting' },
  { value: 'full_permissions', label: 'Full access' },
];

function buttonStyle({ hovered, pressed }: DesktopPressableState) {
  return [styles.button, hovered ? styles.buttonHover : null, pressed ? styles.buttonPressed : null];
}

function selectedLabel(options: SelectOption[], value: string, fallback: string) {
  return options.find((option) => option.value === value)?.label || fallback;
}

function SelectRow({
  id,
  label,
  value,
  hint,
  options,
  open,
  error,
  onToggle,
  onSelect,
  last = false,
}: {
  id: string;
  label: string;
  value: string;
  hint?: string;
  options: SelectOption[];
  open: boolean;
  error?: string;
  onToggle: () => void;
  onSelect: (value: string) => void;
  last?: boolean;
}) {
  return (
    <View style={[styles.settingsRowWrap, last ? styles.settingsRowWrapLast : null]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${label}: ${value}`}
        accessibilityState={{ expanded: open }}
        style={({ hovered, pressed }: DesktopPressableState) => [
          styles.settingsRow,
          last ? styles.settingsRowLast : null,
          hovered ? styles.settingsRowHover : null,
          pressed ? styles.buttonPressed : null,
        ]}
        onPress={onToggle}
      >
        <View style={styles.settingsLabelGroup}>
          <Text style={styles.settingsLabel}>{label}</Text>
          {hint ? <Text numberOfLines={1} style={styles.settingsHint}>{hint}</Text> : null}
        </View>
        <View style={styles.settingsValueGroup}>
          <Text numberOfLines={1} style={styles.settingsValue}>{value}</Text>
          <Text style={styles.chevron}>{open ? '⌃' : '⌄'}</Text>
        </View>
      </Pressable>
      {open ? (
        <View accessibilityRole="radiogroup" accessibilityLabel={`${label} options`} style={styles.selectMenu}>
          <ScrollView style={styles.selectMenuScroll} nestedScrollEnabled keyboardShouldPersistTaps="handled">
            {options.map((option) => {
              const selected = option.value === id;
              return (
                <Pressable
                  key={option.value}
                  accessibilityRole="radio"
                  accessibilityState={{ checked: selected }}
                  style={({ hovered, pressed }: DesktopPressableState) => [
                    styles.selectOption,
                    selected ? styles.selectOptionSelected : null,
                    hovered ? styles.selectOptionHover : null,
                    pressed ? styles.buttonPressed : null,
                  ]}
                  onPress={() => onSelect(option.value)}
                >
                  <View style={styles.selectOptionCopy}>
                    <Text style={styles.selectOptionLabel}>{option.label}</Text>
                    {option.detail ? <Text style={styles.selectOptionDetail}>{option.detail}</Text> : null}
                  </View>
                  {selected ? <Text style={styles.selectCheck}>✓</Text> : null}
                </Pressable>
              );
            })}
          </ScrollView>
        </View>
      ) : null}
      {error ? <Text accessibilityLiveRegion="polite" style={styles.rowError}>{error}</Text> : null}
    </View>
  );
}

function ReadOnlyRow({ label, value, hint, last = false }: { label: string; value: string; hint?: string; last?: boolean }) {
  return (
    <View style={[styles.settingsRow, styles.settingsRowReadOnly, last ? styles.settingsRowLast : null]}>
      <View style={styles.settingsLabelGroup}>
        <Text style={styles.settingsLabel}>{label}</Text>
        {hint ? <Text numberOfLines={1} style={styles.settingsHint}>{hint}</Text> : null}
      </View>
      <Text numberOfLines={1} style={styles.settingsValue}>{value}</Text>
    </View>
  );
}

export function DesktopAutomationEditor({
  mode,
  initialDraft,
  identities,
  sessions,
  modelGroups,
  variants,
  busy,
  onSave,
  onRequestClose,
}: Props) {
  const [draft, setDraft] = useState(initialDraft);
  const [errors, setErrors] = useState<AutomationFieldErrors>({});
  const [openSelect, setOpenSelect] = useState<string | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const baselineRef = useRef(JSON.stringify(initialDraft));
  const nameRef = useRef<TextInput | null>(null);
  const promptRef = useRef<TextInput | null>(null);

  const dirty = JSON.stringify(draft) !== baselineRef.current;
  const identityOptions = useMemo<SelectOption[]>(() => identities.map((identity) => ({
    value: identity.identity_id,
    label: identity.display_name,
    detail: `${identity.role === 'manager' ? 'Manager' : identity.is_default ? 'Default worker' : 'Worker'} · ${identity.status || 'available'}`,
  })), [identities]);
  const selectedIdentity = identities.find((identity) => identity.identity_id === draft.targetIdentityId) || null;
  const entitySessions = useMemo(() => sessions.filter((session) => (
    session.fleet_identity_id === draft.targetIdentityId
    || (!session.fleet_identity_id && selectedIdentity?.role === 'manager')
  )), [draft.targetIdentityId, selectedIdentity?.role, sessions]);
  const sessionOptions = useMemo<SelectOption[]>(() => entitySessions.map((session) => ({
    value: session.id,
    label: session.name || 'Untitled chat',
    detail: `${session.model}${session.workspace ? ` · ${session.workspace}` : ''}`,
  })), [entitySessions]);
  const selectedSession = entitySessions.find((session) => session.id === draft.targetChatId) || null;
  const modelOptions = useMemo<SelectOption[]>(() => {
    const seen = new Set<string>();
    return modelGroups.flatMap((group) => group.models.map((model) => ({
      value: model,
      label: model,
      detail: group.provider,
    }))).filter((option) => {
      if (seen.has(option.value)) return false;
      seen.add(option.value);
      return true;
    });
  }, [modelGroups]);
  const variantOptions = useMemo<SelectOption[]>(() => (variants.length ? variants : ['low', 'medium', 'high', 'xhigh']).map((variant) => ({
    value: variant,
    label: variant.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()),
  })), [variants]);
  const schedule = buildAutomationSchedule(draft);
  const nextRun = useMemo(() => previewAutomationNextRun(draft), [draft]);
  const nextRunLabel = nextRun
    ? new Intl.DateTimeFormat(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(nextRun)
    : 'Complete the schedule to preview the next run';

  const update = <K extends keyof AutomationEditorDraft>(key: K, value: AutomationEditorDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined, schedule: undefined }));
  };

  const choose = <K extends keyof AutomationEditorDraft>(key: K, value: AutomationEditorDraft[K]) => {
    update(key, value);
    setOpenSelect(null);
  };

  const chooseIdentity = (identityId: string) => {
    const currentChat = sessions.find((session) => session.id === draft.targetChatId);
    setDraft((current) => ({
      ...current,
      targetKind: 'identity',
      targetIdentityId: identityId,
      targetChatId: currentChat?.fleet_identity_id === identityId ? current.targetChatId : '',
    }));
    setErrors((current) => ({ ...current, targetIdentityId: undefined, targetChatId: undefined }));
    setOpenSelect(null);
  };

  const submit = () => {
    const nextErrors = validateAutomationDraft(draft);
    setErrors(nextErrors);
    if (nextErrors.name) nameRef.current?.focus();
    else if (nextErrors.prompt) promptRef.current?.focus();
    if (Object.keys(nextErrors).length) return;
    void onSave(draft);
  };

  return (
    <View style={styles.editor}>
      <View style={styles.editorTopbar}>
        <View style={styles.editorTopbarCopy}>
          <Text style={styles.editorKicker}>{mode === 'edit' ? 'Edit automation' : 'New automation'}</Text>
          <Text numberOfLines={1} style={styles.editorStatus}>{dirty ? 'Unsaved changes' : 'Ready to schedule'}</Text>
        </View>
        <Pressable accessibilityRole="button" accessibilityLabel="Close automation editor" style={buttonStyle} onPress={() => void onRequestClose(dirty)}>
          <Text style={styles.buttonText}>Close</Text>
        </Pressable>
      </View>

      <ScrollView style={styles.detailScroll} contentContainerStyle={styles.formContent} keyboardShouldPersistTaps="handled">
        <View style={styles.titleField}>
          <Text style={styles.formSectionLabel}>Scheduled task title</Text>
          <TextInput
            ref={nameRef}
            accessibilityLabel="Automation name"
            autoComplete="off"
            value={draft.name}
            onChangeText={(value) => update('name', value)}
            placeholder="Name this automation"
            placeholderTextColor="#697586"
            style={[styles.titleInput, errors.name ? styles.inputError : null]}
          />
          {errors.name ? <Text accessibilityLiveRegion="polite" style={styles.fieldError}>{errors.name}</Text> : null}
        </View>

        <View style={styles.field}>
          <TextInput
            ref={promptRef}
            accessibilityLabel="Automation task"
            autoComplete="off"
            value={draft.prompt}
            onChangeText={(value) => update('prompt', value)}
            multiline
            placeholder="Describe what EmploAI should do"
            placeholderTextColor="#697586"
            style={[styles.taskInput, errors.prompt ? styles.inputError : null]}
          />
          {errors.prompt ? <Text accessibilityLiveRegion="polite" style={styles.fieldError}>{errors.prompt}</Text> : null}
        </View>

        <View style={styles.formSection}>
          <Text style={styles.formSectionLabel}>Details</Text>
          <View style={styles.settingsCard}>
            <SelectRow
              id={draft.targetIdentityId}
              label="Entity"
              value={selectedLabel(identityOptions, draft.targetIdentityId, 'Choose entity')}
              hint="The manager or worker that owns this automation"
              options={identityOptions}
              open={openSelect === 'entity'}
              error={errors.targetIdentityId}
              onToggle={() => setOpenSelect((value) => value === 'entity' ? null : 'entity')}
              onSelect={chooseIdentity}
            />
            <SelectRow
              id={draft.chatMode}
              label="Runs in"
              value={selectedLabel(CHAT_OPTIONS, draft.chatMode, 'Choose chat mode')}
              options={CHAT_OPTIONS}
              open={openSelect === 'chatMode'}
              onToggle={() => setOpenSelect((value) => value === 'chatMode' ? null : 'chatMode')}
              onSelect={(value) => {
                setDraft((current) => {
                  const canReuseManagedChat = mode === 'edit'
                    && initialDraft.chatMode === 'new'
                    && current.targetChatId === initialDraft.targetChatId;
                  return {
                    ...current,
                    chatMode: value as AutomationEditorDraft['chatMode'],
                    targetChatId: value === 'existing' || canReuseManagedChat ? current.targetChatId : '',
                  };
                });
                setErrors((current) => ({ ...current, targetChatId: undefined, model: undefined }));
                setOpenSelect(null);
              }}
            />
            {draft.chatMode === 'existing' ? (
              <>
                <SelectRow
                  id={draft.targetChatId}
                  label="Chat"
                  value={selectedLabel(sessionOptions, draft.targetChatId, entitySessions.length ? 'Choose an existing chat' : 'No chats for this entity')}
                  hint="Only chats owned by the selected entity are shown"
                  options={sessionOptions}
                  open={openSelect === 'chat'}
                  error={errors.targetChatId}
                  onToggle={() => setOpenSelect((value) => value === 'chat' ? null : 'chat')}
                  onSelect={(value) => choose('targetChatId', value)}
                />
                <ReadOnlyRow label="Model" value={selectedSession?.model || 'Inherited from chat'} hint="Uses the chat’s live configuration" />
                <ReadOnlyRow label="Reasoning" value={selectedSession?.variant || 'Inherited from chat'} />
                <ReadOnlyRow
                  label="Tools & approvals"
                  value={selectedSession ? `${selectedSession.enabled_tool_packs.length} packs · ${selectedSession.security_permission_mode || 'standard'}` : 'Inherited from chat'}
                  last
                />
              </>
            ) : (
              <>
                <SelectRow
                  id={draft.model}
                  label="Model"
                  value={selectedLabel(modelOptions, draft.model, draft.model || 'Choose model')}
                  options={modelOptions}
                  open={openSelect === 'model'}
                  error={errors.model}
                  onToggle={() => setOpenSelect((value) => value === 'model' ? null : 'model')}
                  onSelect={(value) => choose('model', value)}
                />
                <SelectRow
                  id={draft.variant}
                  label="Reasoning"
                  value={selectedLabel(variantOptions, draft.variant, draft.variant || 'Default')}
                  options={variantOptions}
                  open={openSelect === 'variant'}
                  onToggle={() => setOpenSelect((value) => value === 'variant' ? null : 'variant')}
                  onSelect={(value) => choose('variant', value)}
                  last
                />
              </>
            )}
          </View>
          {draft.chatMode === 'existing' ? (
            <View style={styles.inheritanceNote}>
              <Text style={styles.inheritanceMark}>↳</Text>
              <Text style={styles.inheritanceText}>This automation will use the selected chat’s model, reasoning, workspace, tools, and approval mode.</Text>
            </View>
          ) : null}
        </View>

        <View style={styles.formSection}>
          <Text style={styles.formSectionLabel}>Frequency</Text>
          <View style={styles.settingsCard}>
            <SelectRow
              id={draft.scheduleMode}
              label="Repeat"
              value={selectedLabel(REPEAT_OPTIONS, draft.scheduleMode, 'Choose frequency')}
              options={REPEAT_OPTIONS}
              open={openSelect === 'repeat'}
              onToggle={() => setOpenSelect((value) => value === 'repeat' ? null : 'repeat')}
              onSelect={(value) => choose('scheduleMode', value as AutomationScheduleMode)}
            />
            {draft.scheduleMode === 'daily' ? (
              <View style={[styles.settingsRow, styles.settingsRowLast]}>
                <Text style={styles.settingsLabel}>At</Text>
                <TextInput
                  accessibilityLabel="Daily run time"
                  value={draft.dailyTime}
                  onChangeText={(value) => update('dailyTime', value)}
                  placeholder="09:00"
                  placeholderTextColor="#697586"
                  style={[styles.compactInput, errors.dailyTime ? styles.inputError : null]}
                />
              </View>
            ) : null}
            {draft.scheduleMode === 'interval' || draft.scheduleMode === 'delay' ? (
              <View style={[styles.settingsRow, styles.settingsRowLast]}>
                <Text style={styles.settingsLabel}>{draft.scheduleMode === 'delay' ? 'After' : 'Every'}</Text>
                <View style={styles.frequencyControls}>
                  <TextInput
                    accessibilityLabel={`${draft.scheduleMode === 'delay' ? 'Delay' : 'Interval'} amount`}
                    inputMode="numeric"
                    value={draft.scheduleMode === 'delay' ? draft.delayAmount : draft.intervalAmount}
                    onChangeText={(value) => update(draft.scheduleMode === 'delay' ? 'delayAmount' : 'intervalAmount', value)}
                    style={[styles.compactInput, styles.amountInput]}
                  />
                  <View style={styles.unitChoices}>
                    {AUTOMATION_SCHEDULE_UNITS.map((unit) => {
                      const current = draft.scheduleMode === 'delay' ? draft.delayUnit : draft.intervalUnit;
                      return (
                        <Pressable
                          key={unit}
                          accessibilityRole="radio"
                          accessibilityState={{ checked: current === unit }}
                          style={({ hovered, pressed }: DesktopPressableState) => [styles.unitChoice, current === unit ? styles.unitChoiceSelected : null, hovered ? styles.buttonHover : null, pressed ? styles.buttonPressed : null]}
                          onPress={() => update(draft.scheduleMode === 'delay' ? 'delayUnit' : 'intervalUnit', unit)}
                        >
                          <Text style={[styles.unitChoiceText, current === unit ? styles.unitChoiceTextSelected : null]}>{unit}</Text>
                        </Pressable>
                      );
                    })}
                  </View>
                </View>
              </View>
            ) : null}
            {draft.scheduleMode === 'advanced' ? (
              <View style={[styles.settingsRow, styles.settingsRowLast]}>
                <Text style={styles.settingsLabel}>Schedule</Text>
                <TextInput
                  accessibilityLabel="Advanced schedule phrase"
                  value={draft.advancedSchedule}
                  onChangeText={(value) => update('advancedSchedule', value)}
                  placeholder="every day at 09:00"
                  placeholderTextColor="#697586"
                  style={[styles.compactInput, styles.advancedInput]}
                />
              </View>
            ) : null}
          </View>
          {errors.dailyTime || errors.intervalAmount || errors.delayAmount || errors.advancedSchedule ? (
            <Text accessibilityLiveRegion="polite" style={styles.fieldError}>{errors.dailyTime || errors.intervalAmount || errors.delayAmount || errors.advancedSchedule}</Text>
          ) : null}
          <Text style={styles.nextRunText}>{schedule} · Next run {nextRunLabel}</Text>
        </View>

        <View style={styles.formSection}>
          <Pressable accessibilityRole="button" accessibilityState={{ expanded: advancedOpen }} style={styles.advancedToggle} onPress={() => setAdvancedOpen((value) => !value)}>
            <Text style={styles.advancedToggleText}>{advancedOpen ? 'Hide advanced settings' : 'Advanced settings'}</Text>
            <Text style={styles.chevron}>{advancedOpen ? '⌃' : '⌄'}</Text>
          </Pressable>
          {advancedOpen ? (
            <View style={styles.settingsCard}>
              {draft.chatMode === 'new' ? (
                <SelectRow
                  id={draft.permissionMode}
                  label="Approvals"
                  value={selectedLabel(PERMISSION_OPTIONS, draft.permissionMode, 'Confirm risky actions')}
                  options={PERMISSION_OPTIONS}
                  open={openSelect === 'permissions'}
                  onToggle={() => setOpenSelect((value) => value === 'permissions' ? null : 'permissions')}
                  onSelect={(value) => choose('permissionMode', value as AutomationPermissionMode)}
                  last
                />
              ) : (
                <ReadOnlyRow label="Approvals" value={selectedSession?.security_permission_mode || 'Inherited from chat'} last />
              )}
            </View>
          ) : null}
        </View>

        <View style={styles.saveBar}>
          <View style={styles.saveSummary}>
            <Text style={styles.saveSummaryTitle}>{draft.name.trim() || 'Untitled automation'}</Text>
            <Text numberOfLines={1} style={styles.saveSummaryCopy}>{selectedIdentity?.display_name || 'No entity'} · {draft.chatMode === 'existing' ? selectedSession?.name || 'Choose chat' : draft.model || 'Choose model'}</Text>
          </View>
          <View style={styles.editorFooterActions}>
            <Pressable accessibilityRole="button" disabled={busy} style={buttonStyle} onPress={() => { setDraft(initialDraft); setErrors({}); }}>
              <Text style={styles.buttonText}>Reset</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={mode === 'edit' ? 'Save automation changes' : 'Create automation'}
              disabled={busy}
              style={(state: DesktopPressableState) => [...buttonStyle(state), styles.primaryButton, busy ? styles.disabled : null]}
              onPress={submit}
            >
              <Text style={[styles.buttonText, styles.primaryButtonText]}>{busy ? 'Saving…' : mode === 'edit' ? 'Save changes' : 'Create automation'}</Text>
            </Pressable>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}
