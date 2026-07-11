import { useEffect, useState } from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';

import { styles } from './DesktopSetupPanel.styles';
import {
  fetchAgentSkillDetail,
  fetchAgentSkills,
  learnAgentSkill,
  type SkillDetail,
  type SkillSummary,
} from '@/lib/appApi';
import { userFacingError } from '../../lib/diagnostics';

type Props = {
  apiBaseUrl?: string | null;
  token?: string | null;
  sessionId?: string | null;
  onOpenPath?: (targetPath: string) => void;
  embedded?: boolean;
};

function trimPreview(value: string, maxLength = 260) {
  const text = String(value || '').trim();
  return text.length > maxLength ? `${text.slice(0, maxLength - 18).trim()} ... (truncated)` : text;
}

export function DesktopSetupLocalIntelligenceSection({ apiBaseUrl, token, sessionId, onOpenPath, embedded = false }: Props) {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [selectedSkill, setSelectedSkill] = useState<SkillDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [learnName, setLearnName] = useState('');
  const [learnWorkflow, setLearnWorkflow] = useState('');
  const canUseLocalRuntime = Boolean(apiBaseUrl && token);
  const canMutateSession = Boolean(canUseLocalRuntime && sessionId);
  const rootStyle = embedded ? styles.localEmbeddedSection : styles.section;
  const titleStyle = embedded ? styles.settingCardTitle : styles.sectionTitle;
  const helperStyle = embedded ? styles.settingCardDescription : styles.helperText;
  const titleText = embedded ? 'Local skills' : 'Local intelligence';
  const helperText = embedded
    ? 'Skills live beside MEMORY.md on this computer and load only when needed.'
    : 'Local skills live on this computer and load only when needed.';

  const refresh = async () => {
    if (!apiBaseUrl || !token) {
      return;
    }
    setBusy(true);
    setMessage('Refreshing local intelligence...');
    try {
      const skillResult = await fetchAgentSkills(apiBaseUrl, token, sessionId || undefined);
      setSkills(skillResult.items);
      setMessage(`Loaded ${skillResult.items.length} skills.`);
    } catch (error) {
      setMessage(userFacingError(error, 'Local intelligence could not be loaded.'));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (canUseLocalRuntime) {
      void refresh();
    }
  }, [apiBaseUrl, token, sessionId]);

  const viewSkill = async (name: string) => {
    if (!apiBaseUrl || !token) return;
    setBusy(true);
    setMessage(`Loading ${name}...`);
    try {
      const detail = await fetchAgentSkillDetail(apiBaseUrl, token, name, sessionId || undefined);
      setSelectedSkill(detail);
      setMessage(`Loaded ${name}.`);
    } catch (error) {
      setMessage(userFacingError(error, `Skill ${name} could not be loaded.`));
    } finally {
      setBusy(false);
    }
  };

  const learnSkill = async () => {
    if (!apiBaseUrl || !token || !sessionId || !learnName.trim()) {
      return;
    }
    setBusy(true);
    setMessage('Saving local skill...');
    try {
      const result = await learnAgentSkill(
        apiBaseUrl,
        token,
        {
          name: learnName.trim(),
          workflow: learnWorkflow.trim() || undefined,
          activate: true,
        },
        sessionId
      );
      setSelectedSkill(result.skill);
      setLearnName('');
      setLearnWorkflow('');
      await refresh();
      setMessage(result.message || `Learned ${result.skill.name}.`);
    } catch (error) {
      setMessage(userFacingError(error, 'Local skill was not saved.'));
    } finally {
      setBusy(false);
    }
  };

  if (!canUseLocalRuntime) {
    return (
      <View style={rootStyle}>
        <Text style={titleStyle}>{titleText}</Text>
        <Text style={helperStyle}>
          Start the local runtime to inspect local skills.
        </Text>
      </View>
    );
  }

  return (
    <View style={rootStyle}>
      <Text style={titleStyle}>{titleText}</Text>
      <Text style={helperStyle}>{helperText}</Text>

      <View style={styles.pathActions}>
        <Pressable style={[styles.pathButton, busy ? styles.buttonDisabled : null]} onPress={() => void refresh()} disabled={busy}>
          <Text style={styles.pathButtonText}>{busy ? 'Working...' : 'Refresh'}</Text>
        </Pressable>
      </View>
      {message ? <Text style={styles.localStatusText}>{message}</Text> : null}

      <View style={styles.settingCard}>
        <Text style={styles.settingCardTitle}>Local skills</Text>
        <Text style={styles.settingCardDescription}>Skill bodies load on demand, keeping normal prompts lighter.</Text>
        <View style={styles.localList}>
          {skills.length ? skills.slice(0, 8).map((skill) => (
            <View key={skill.name} style={styles.localRow}>
              <View style={styles.localRowMain}>
                <Text style={styles.localRowTitle}>{skill.name}</Text>
                <Text style={styles.localRowBody}>{trimPreview(skill.description, 150)}</Text>
              </View>
              <Pressable style={[styles.localActionButton, busy ? styles.buttonDisabled : null]} onPress={() => void viewSkill(skill.name)} disabled={busy}>
                <Text style={styles.localActionButtonText}>View</Text>
              </Pressable>
            </View>
          )) : (
            <Text style={styles.localEmptyText}>No local skills are available.</Text>
          )}
        </View>
      </View>

      {selectedSkill ? (
        <View style={styles.settingCard}>
          <View style={styles.localSectionHeaderRow}>
            <View style={styles.localRowMain}>
              <Text style={styles.settingCardTitle}>{selectedSkill.name}</Text>
              <Text style={styles.settingCardDescription}>{selectedSkill.description}</Text>
            </View>
            {selectedSkill.path ? (
              <Pressable style={styles.localActionButton} onPress={() => onOpenPath?.(selectedSkill.path || '')}>
                <Text style={styles.localActionButtonText}>Open</Text>
              </Pressable>
            ) : null}
          </View>
          <Text style={styles.localCodePreview}>{trimPreview(selectedSkill.body, 1800)}</Text>
        </View>
      ) : null}

      <View style={styles.settingCard}>
        <Text style={styles.settingCardTitle}>Learn a local skill</Text>
        <Text style={styles.settingCardDescription}>
          Name a workflow, then optionally paste steps. Leave steps blank to draft from recent chat history.
        </Text>
        <TextInput
          value={learnName}
          onChangeText={setLearnName}
          style={styles.input}
          placeholder="skill-name"
          placeholderTextColor="#7f93b5"
          autoCapitalize="none"
          autoCorrect={false}
        />
        <TextInput
          value={learnWorkflow}
          onChangeText={setLearnWorkflow}
          style={[styles.input, styles.localWorkflowInput]}
          placeholder="Optional workflow steps"
          placeholderTextColor="#7f93b5"
          autoCapitalize="none"
          autoCorrect={false}
          multiline
          textAlignVertical="top"
        />
        <Pressable
          style={[styles.pathButton, (!canMutateSession || !learnName.trim() || busy) ? styles.buttonDisabled : null]}
          onPress={() => void learnSkill()}
          disabled={!canMutateSession || !learnName.trim() || busy}
        >
          <Text style={styles.pathButtonText}>Save Local Skill</Text>
        </Pressable>
      </View>
    </View>
  );
}
