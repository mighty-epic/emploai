import { Pressable, Text, TextInput, View } from 'react-native';

import { styles } from './DesktopSetupPanel.styles';
import type { SharedSettingsDraft } from '@/lib/accountProfile';

const INTERRUPT_OPTIONS: Array<{ value: SharedSettingsDraft['interruptPolicy']; label: string }> = [
  { value: 'none', label: 'Queue' },
  { value: 'steer_now', label: 'Steer Now' },
  { value: 'after_tool', label: 'After Tool' },
];

type Props = {
  draft: SharedSettingsDraft;
  saving?: boolean;
  status?: string | null;
  standaloneMode?: boolean;
  onChange: (draft: SharedSettingsDraft) => void;
  onSave: () => void;
};

function ToggleRow({
  title,
  description,
  value,
  onPress,
}: {
  title: string;
  description?: string;
  value: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityLabel={title}
      accessibilityHint={description}
      accessibilityState={{ checked: value }}
      style={styles.settingRow}
      onPress={onPress}
    >
      <View style={styles.settingRowCopy}>
        <Text style={styles.settingRowTitle}>{title}</Text>
        {description ? <Text style={styles.settingRowDescription}>{description}</Text> : null}
      </View>
      <View style={[styles.toggleSwitch, value ? styles.toggleSwitchActive : null]}>
        <View style={[styles.toggleSwitchKnob, value ? styles.toggleSwitchKnobActive : null]} />
      </View>
    </Pressable>
  );
}

export function DesktopSetupSharedSettingsSection({ draft, saving = false, status, standaloneMode = false, onChange, onSave }: Props) {
  const update = (patch: Partial<SharedSettingsDraft>) => onChange({ ...draft, ...patch });

  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{standaloneMode ? 'Local Runtime Settings' : 'Shared Account Settings'}</Text>
      {!standaloneMode ? <Text style={styles.helperText}>Applies across desktop, mobile, and Telegram.</Text> : null}

      <View style={styles.settingStack}>
        <View style={styles.settingCard}>
          <Text style={styles.settingCardTitle}>Custom instructions</Text>
          <TextInput
            value={draft.customSystemPromptAppend}
            onChangeText={(value) => update({ customSystemPromptAppend: value })}
            style={[styles.input, styles.sharedPromptInput]}
            placeholder="Extra account instructions"
            placeholderTextColor="#7f93b5"
            multiline
            textAlignVertical="top"
          />
        </View>

        <View style={styles.settingCard}>
          <View style={styles.settingRow}>
            <View style={styles.settingRowCopy}>
              <Text style={styles.settingRowTitle}>Max turns</Text>
            </View>
            <TextInput
              value={draft.maxTurns}
              onChangeText={(value) => update({ maxTurns: value.replace(/[^\d]/g, '') })}
              style={[styles.input, styles.numberInput]}
              placeholder="100"
              placeholderTextColor="#7f93b5"
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>
          <ToggleRow title="Sleep mode" description="Allow the local runtime to continue approved background work while the app is not active." value={draft.sleepModeEnabled} onPress={() => update({ sleepModeEnabled: !draft.sleepModeEnabled })} />
          <ToggleRow title="Verbose feed" description="Show detailed tool and runtime activity in chat." value={draft.verboseMode} onPress={() => update({ verboseMode: !draft.verboseMode })} />
          {!standaloneMode ? (
            <ToggleRow
              title="Cloud chat backup"
              value={draft.cloudChatBackupEnabled}
              onPress={() => update({ cloudChatBackupEnabled: !draft.cloudChatBackupEnabled })}
            />
          ) : null}
        </View>

        <View style={styles.settingCard}>
          <Text style={styles.settingCardTitle}>Active-run messages</Text>
          <View style={styles.voiceModeRow}>
            {INTERRUPT_OPTIONS.map((option) => {
              const selected = draft.interruptPolicy === option.value;
              return (
                <Pressable
                  key={option.value}
                  style={[styles.voiceModeButton, selected ? styles.voiceModeButtonActive : null]}
                  onPress={() => update({ interruptPolicy: option.value })}
                >
                  <Text style={[styles.voiceModeButtonText, selected ? styles.voiceModeButtonTextActive : null]}>
                    {option.label}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        <View style={styles.settingCard}>
          <Text style={styles.settingCardTitle}>Memory controls</Text>
          <ToggleRow
            title="Prompt context"
            value={draft.memoryPromptContextEnabled}
            onPress={() => update({ memoryPromptContextEnabled: !draft.memoryPromptContextEnabled })}
          />
          <ToggleRow
            title="Search"
            value={draft.memorySearchEnabled}
            onPress={() => update({ memorySearchEnabled: !draft.memorySearchEnabled })}
          />
          <ToggleRow
            title="Writes"
            value={draft.memoryWriteEnabled}
            onPress={() => update({ memoryWriteEnabled: !draft.memoryWriteEnabled })}
          />
        </View>

        {!standaloneMode ? (
          <View style={styles.settingCard}>
            <Text style={styles.settingCardTitle}>Telegram user IDs</Text>
            <TextInput
              value={draft.telegramAllowedUserIds}
              onChangeText={(value) => update({ telegramAllowedUserIds: value })}
              style={styles.input}
              placeholder="123456789, 987654321"
              placeholderTextColor="#7f93b5"
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>
        ) : null}

        <View style={styles.pathActions}>
          <Pressable style={[styles.primaryButton, saving ? styles.primaryButtonDisabled : null]} onPress={onSave} disabled={saving}>
            <Text style={styles.primaryButtonText}>{saving ? 'Saving...' : standaloneMode ? 'Save Local Settings' : 'Save Shared Settings'}</Text>
          </Pressable>
          {status ? <Text accessibilityLiveRegion="polite" style={styles.helperText}>{status}</Text> : null}
        </View>
      </View>
    </View>
  );
}
