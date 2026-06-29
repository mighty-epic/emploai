import { Pressable, Text, View } from 'react-native';

import { styles } from './DesktopSetupPanel.styles';
import { VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW, VOICE_ENGINE_NONE } from './desktopVoicePolicy';

import type {
  DesktopSetupValues,
  DesktopVoicePackInstallProgress,
  DesktopVoicePackSummary,
} from '@/lib/desktopBridge';

type Props = {
  values: DesktopSetupValues;
  selectedVoiceEngine: string;
  selectedVoicePack: DesktopVoicePackSummary | null;
  voiceModel: string;
  voiceDraftModel?: string | null;
  voiceSelectionSource: string;
  sttVoicePacks: DesktopVoicePackSummary[];
  ttsVoicePacks: DesktopVoicePackSummary[];
  selectedTtsBackend: string;
  voicePackBusyId?: string | null;
  voicePackProgress?: DesktopVoicePackInstallProgress | null;
  onSetVoiceDefaultEngine: (nextEngine: string) => void;
  onToggleVoicePackRequest: (pack: DesktopVoicePackSummary) => void;
  onInstallVoicePack?: (packId: string) => void;
  onRemoveVoicePack?: (packId: string) => void;
};

function voiceSelectionSourceLabel(source: string) {
  if (source === 'settings') {
    return 'Manual settings';
  }
  if (source === 'installer') {
    return 'Installer selection';
  }
  return source;
}

function VoicePackProgress({ progress }: { progress: DesktopVoicePackInstallProgress }) {
  const progressPercent = progress.percent ?? 0;
  return (
    <View style={styles.voicePackProgressCard}>
      <Text style={styles.voicePackProgressTitle}>{progress.message}</Text>
      <View style={styles.voicePackProgressTrack}>
        <View style={[styles.voicePackProgressFill, { width: `${progressPercent}%` }]} />
      </View>
      <Text style={styles.voicePackProgressMeta}>
        {progress.phase.replace(/_/g, ' ')}
        {typeof progress.percent === 'number' ? ` · ${Math.round(progress.percent)}%` : ''}
      </Text>
    </View>
  );
}

function VoicePackStatusBadge({ label, ready }: { label: string; ready: boolean }) {
  return (
    <View
      style={[
        styles.voicePackStatusBadge,
        ready ? styles.voicePackStatusReady : styles.voicePackStatusPlaceholder,
      ]}
    >
      <Text style={styles.voicePackStatusText}>{label}</Text>
    </View>
  );
}

export function DesktopSetupVoiceSection({
  values,
  selectedVoiceEngine,
  selectedVoicePack,
  voiceModel,
  voiceDraftModel,
  voiceSelectionSource,
  sttVoicePacks,
  ttsVoicePacks,
  selectedTtsBackend,
  voicePackBusyId,
  voicePackProgress,
  onSetVoiceDefaultEngine,
  onToggleVoicePackRequest,
  onInstallVoicePack,
  onRemoveVoicePack,
}: Props) {
  const isVoicePackBusy = (packId: string) => voicePackBusyId === packId;

  return (
    <>
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Voice</Text>
        <Text style={styles.helperText}>
          Choose speech input and voices for Jarvis and desktop voice features.
        </Text>
        <View style={styles.metaRow}>
          <View style={styles.metaCard}>
            <Text style={styles.metaLabel}>Selected path</Text>
            <Text style={styles.metaValue}>
              {selectedVoiceEngine === VOICE_ENGINE_NONE ? 'Off' : selectedVoicePack?.title || selectedVoiceEngine}
            </Text>
            {selectedVoicePack ? <Text style={styles.metaIssue}>{selectedVoicePack.description}</Text> : null}
          </View>
          <View style={styles.metaCard}>
            <Text style={styles.metaLabel}>Speech input</Text>
            <Text style={styles.metaValue}>{voiceModel}</Text>
            {voiceDraftModel ? <Text style={styles.metaIssue}>Live drafts: {voiceDraftModel}</Text> : null}
          </View>
          <View style={styles.metaCard}>
            <Text style={styles.metaLabel}>Selection source</Text>
            <Text style={styles.metaValue}>{voiceSelectionSourceLabel(voiceSelectionSource)}</Text>
          </View>
        </View>

        <View style={styles.voiceModeRow}>
          <Pressable
            style={[styles.voiceModeButton, selectedVoiceEngine === VOICE_ENGINE_NONE ? styles.voiceModeButtonActive : null]}
            onPress={() => onSetVoiceDefaultEngine(VOICE_ENGINE_NONE)}
          >
            <Text style={[styles.voiceModeButtonText, selectedVoiceEngine === VOICE_ENGINE_NONE ? styles.voiceModeButtonTextActive : null]}>
              No voice
            </Text>
          </Pressable>
          <Pressable
            style={[
              styles.voiceModeButton,
              selectedVoiceEngine === VOICE_ENGINE_ENGLISH ? styles.voiceModeButtonActive : null,
              values.VOICE_ENGLISH_REQUESTED === '0' ? styles.voiceModeButtonDisabled : null,
            ]}
            onPress={() => onSetVoiceDefaultEngine(VOICE_ENGINE_ENGLISH)}
            disabled={values.VOICE_ENGLISH_REQUESTED === '0'}
          >
            <Text style={[styles.voiceModeButtonText, selectedVoiceEngine === VOICE_ENGINE_ENGLISH ? styles.voiceModeButtonTextActive : null]}>
              English
            </Text>
          </Pressable>
          <Pressable
            style={[
              styles.voiceModeButton,
              selectedVoiceEngine === VOICE_ENGINE_HEBREW ? styles.voiceModeButtonActive : null,
              values.VOICE_HEBREW_REQUESTED !== '1' ? styles.voiceModeButtonDisabled : null,
            ]}
            onPress={() => onSetVoiceDefaultEngine(VOICE_ENGINE_HEBREW)}
            disabled={values.VOICE_HEBREW_REQUESTED !== '1'}
          >
            <Text style={[styles.voiceModeButtonText, selectedVoiceEngine === VOICE_ENGINE_HEBREW ? styles.voiceModeButtonTextActive : null]}>
              Hebrew
            </Text>
          </Pressable>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Voice input packs</Text>
        <View style={styles.voicePackList}>
          {sttVoicePacks.map((pack) => {
            const activeProgress = isVoicePackBusy(pack.id) ? voicePackProgress : null;
            const busy = isVoicePackBusy(pack.id);
            return (
              <View key={pack.id} style={styles.voicePackCard}>
                <View style={styles.voicePackHeader}>
                  <View style={styles.voicePackCopy}>
                    <Text style={styles.voicePackTitle}>{pack.title}</Text>
                    <Text style={styles.voicePackDescription}>{pack.description}</Text>
                  </View>
                  <VoicePackStatusBadge
                    label={pack.available ? 'Ready' : pack.installed ? 'Installed' : 'Optional'}
                    ready={pack.available}
                  />
                </View>
                <Text style={styles.voicePackMeta}>
                  Installed: {pack.installed ? 'yes' : 'no'}
                  {pack.source ? ` · Source: ${pack.source}` : ''}
                  {pack.supportsAlwaysOn ? ' · Always-on target included' : ''}
                </Text>
                {pack.issues?.length ? <Text style={styles.metaIssue}>{pack.issues[0]}</Text> : null}
                {activeProgress ? <VoicePackProgress progress={activeProgress} /> : null}
                <View style={styles.voicePackActionRow}>
                  <Pressable
                    style={[styles.voicePackActionButton, busy ? styles.voiceModeButtonDisabled : null]}
                    onPress={() => onToggleVoicePackRequest(pack)}
                    disabled={busy}
                  >
                    <Text style={styles.voicePackActionText}>
                      {pack.id === VOICE_ENGINE_ENGLISH
                        ? values.VOICE_ENGLISH_REQUESTED === '0'
                          ? 'Enable English pack'
                          : 'Disable English pack'
                        : values.VOICE_HEBREW_REQUESTED === '1'
                          ? 'Disable Hebrew pack'
                          : 'Enable Hebrew pack'}
                    </Text>
                  </Pressable>
                  {pack.installed ? (
                    <Pressable
                      style={[
                        styles.voicePackActionButtonSecondary,
                        !pack.removable || busy ? styles.voiceModeButtonDisabled : null,
                      ]}
                      onPress={() => onRemoveVoicePack?.(pack.id)}
                      disabled={!pack.removable || busy}
                    >
                      <Text style={styles.voicePackActionTextSecondary}>{busy ? 'Removing...' : 'Delete Pack'}</Text>
                    </Pressable>
                  ) : (
                    <Pressable
                      style={[styles.voicePackActionButtonSecondary, busy ? styles.voiceModeButtonDisabled : null]}
                      onPress={() => onInstallVoicePack?.(pack.id)}
                      disabled={busy}
                    >
                      <Text style={styles.voicePackActionTextSecondary}>{busy ? 'Installing...' : 'Install and Use'}</Text>
                    </Pressable>
                  )}
                  {pack.id === VOICE_ENGINE_ENGLISH ? (
                    <Pressable
                      style={[
                        styles.voicePackActionButtonSecondary,
                        values.VOICE_ENGLISH_REQUESTED === '0' || !pack.available || busy ? styles.voiceModeButtonDisabled : null,
                      ]}
                      onPress={() => onSetVoiceDefaultEngine(VOICE_ENGINE_ENGLISH)}
                      disabled={values.VOICE_ENGLISH_REQUESTED === '0' || !pack.available || busy}
                    >
                      <Text style={styles.voicePackActionTextSecondary}>Use English</Text>
                    </Pressable>
                  ) : (
                    <Pressable
                      style={[
                        styles.voicePackActionButtonSecondary,
                        values.VOICE_HEBREW_REQUESTED !== '1' || !pack.available || busy ? styles.voiceModeButtonDisabled : null,
                      ]}
                      onPress={() => onSetVoiceDefaultEngine(VOICE_ENGINE_HEBREW)}
                      disabled={values.VOICE_HEBREW_REQUESTED !== '1' || !pack.available || busy}
                    >
                      <Text style={styles.voicePackActionTextSecondary}>Use Hebrew</Text>
                    </Pressable>
                  )}
                </View>
              </View>
            );
          })}
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Jarvis speech packs</Text>
        <Text style={styles.helperText}>
          Install local voices for Jarvis mode. Online speech remains the fallback when no local voice is selected.
        </Text>
        <View style={styles.voicePackList}>
          {ttsVoicePacks.map((pack) => {
            const activeProgress = isVoicePackBusy(pack.id) ? voicePackProgress : null;
            const busy = isVoicePackBusy(pack.id);
            const packBackend = String(pack.backend || '').trim();
            const active = Boolean(packBackend && selectedTtsBackend === packBackend);
            return (
              <View key={pack.id} style={styles.voicePackCard}>
                <View style={styles.voicePackHeader}>
                  <View style={styles.voicePackCopy}>
                    <Text style={styles.voicePackTitle}>{pack.title}</Text>
                    <Text style={styles.voicePackDescription}>{pack.description}</Text>
                  </View>
                  <VoicePackStatusBadge
                    label={active ? 'Active' : pack.available ? 'Ready' : pack.installed ? 'Installed' : 'Optional'}
                    ready={active || pack.available}
                  />
                </View>
                <Text style={styles.voicePackMeta}>
                  Installed: {pack.installed ? 'yes' : 'no'}
                  {pack.source ? ` · Source: ${pack.source}` : ''}
                  {packBackend ? ` · Backend: ${packBackend}` : ''}
                </Text>
                {pack.issues?.length ? <Text style={styles.metaIssue}>{pack.issues[0]}</Text> : null}
                {activeProgress ? <VoicePackProgress progress={activeProgress} /> : null}
                <View style={styles.voicePackActionRow}>
                  <Pressable
                    style={[
                      styles.voicePackActionButton,
                      active || busy ? styles.voiceModeButtonDisabled : null,
                    ]}
                    onPress={() => onInstallVoicePack?.(pack.id)}
                    disabled={active || busy}
                  >
                    <Text style={styles.voicePackActionText}>
                      {busy ? 'Working...' : pack.installed ? 'Use Pack' : 'Install and Use'}
                    </Text>
                  </Pressable>
                  {pack.installed ? (
                    <Pressable
                      style={[
                        styles.voicePackActionButtonSecondary,
                        !pack.removable || busy ? styles.voiceModeButtonDisabled : null,
                      ]}
                      onPress={() => onRemoveVoicePack?.(pack.id)}
                      disabled={!pack.removable || busy}
                    >
                      <Text style={styles.voicePackActionTextSecondary}>{busy ? 'Removing...' : 'Delete Pack'}</Text>
                    </Pressable>
                  ) : null}
                </View>
              </View>
            );
          })}
        </View>
      </View>
    </>
  );
}
