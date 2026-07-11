import { useEffect, useState } from 'react';
import { Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  JARVIS_WAKE_REQUIRED_SAMPLES,
  buildJarvisWakeProfile,
  createJarvisWakeSignature,
  normalizeJarvisWakePhrase,
  recordJarvisWakeSample,
  type JarvisWakeProfile,
  type JarvisWakeSignature,
} from './desktopJarvisWakeProfile';
import { DESKTOP_UI as UI } from './desktopUiTokens';

type Props = {
  visible: boolean;
  profile: JarvisWakeProfile | null;
  required?: boolean;
  onSave: (profile: JarvisWakeProfile) => void;
  onCancel?: () => void;
  onUsePushToTalk?: () => void;
};

const SAMPLE_SLOTS = Array.from({ length: JARVIS_WAKE_REQUIRED_SAMPLES }, (_, index) => index);
const MONO_FONT = Platform.OS === 'web' ? UI.type.mono : undefined;
const BODY_FONT = Platform.OS === 'web' ? UI.type.sans : undefined;

export function DesktopJarvisWakeEnrollmentPanel({
  visible,
  profile,
  required,
  onSave,
  onCancel,
  onUsePushToTalk,
}: Props) {
  const [phrase, setPhrase] = useState(profile?.phrase || 'Jarvis');
  const [samples, setSamples] = useState<Array<JarvisWakeSignature | null>>(
    SAMPLE_SLOTS.map(() => null),
  );
  const [recordingIndex, setRecordingIndex] = useState<number | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!visible) {
      return;
    }
    setPhrase(profile?.phrase || 'Jarvis');
    setSamples(SAMPLE_SLOTS.map(() => null));
    setMessage(profile ? 'Record new samples to replace the current wake phrase profile.' : '');
    setError('');
  }, [profile, visible]);

  if (!visible) {
    return null;
  }

  const capturedCount = samples.filter(Boolean).length;
  const saveDisabled = recordingIndex !== null || capturedCount < JARVIS_WAKE_REQUIRED_SAMPLES;
  const normalizedPhrase = normalizeJarvisWakePhrase(phrase);

  const recordSample = async (index: number) => {
    setRecordingIndex(index);
    setError('');
    setMessage(`Recording sample ${index + 1}. Say "${normalizedPhrase}" now.`);
    try {
      const audio = await recordJarvisWakeSample();
      const signature = createJarvisWakeSignature(audio.samples, audio.sampleRate);
      setSamples((current) => {
        const next = [...current];
        next[index] = signature;
        return next;
      });
      setMessage(`Sample ${index + 1} captured: ${Math.round(signature.durationMs)} ms.`);
    } catch (recordError) {
      setError(recordError instanceof Error ? recordError.message : 'Wake phrase sample failed.');
      setMessage('');
    } finally {
      setRecordingIndex(null);
    }
  };

  const saveProfile = () => {
    setError('');
    try {
      const nextProfile = buildJarvisWakeProfile(normalizedPhrase, samples.filter(Boolean) as JarvisWakeSignature[]);
      onSave(nextProfile);
      setMessage(`Wake phrase "${nextProfile.phrase}" saved locally.`);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Wake phrase profile could not be saved.');
    }
  };

  return (
    <View style={panelStyles.backdrop}>
      <View style={panelStyles.panel}>
        <View style={panelStyles.header}>
          <View style={panelStyles.headerCopy}>
            <Text style={panelStyles.eyebrow}>LOCAL WAKE TRAINING</Text>
            <Text style={panelStyles.title}>
              {profile ? 'Redo Jarvis wake phrase' : 'Train Jarvis before always-on listening'}
            </Text>
            <Text style={panelStyles.subtitle}>
              EmploAI stores a small audio fingerprint on this computer and checks it before any always-on audio is sent to transcription.
            </Text>
          </View>
          {profile ? (
            <View style={panelStyles.statusBadge}>
              <Text style={panelStyles.statusBadgeText}>CURRENT: {profile.phrase.toUpperCase()}</Text>
            </View>
          ) : null}
        </View>

        <View style={panelStyles.fieldBlock}>
          <Text style={panelStyles.label}>Wake phrase</Text>
          <TextInput
            value={phrase}
            onChangeText={(nextPhrase) => {
              setPhrase(nextPhrase);
              setSamples(SAMPLE_SLOTS.map(() => null));
              setMessage('Record fresh samples after changing the phrase.');
              setError('');
            }}
            editable={recordingIndex === null}
            placeholder="Jarvis"
            placeholderTextColor="#686b72"
            style={panelStyles.input}
          />
        </View>

        <View style={panelStyles.samplesGrid}>
          {SAMPLE_SLOTS.map((index) => {
            const sample = samples[index];
            const recording = recordingIndex === index;
            return (
              <Pressable
                key={`jarvis-wake-sample-${index}`}
                disabled={recordingIndex !== null}
                style={({ hovered, pressed }: any) => [
                  panelStyles.sampleButton,
                  sample ? panelStyles.sampleButtonDone : null,
                  hovered && recordingIndex === null ? panelStyles.sampleButtonHover : null,
                  pressed && recordingIndex === null ? panelStyles.sampleButtonPressed : null,
                  recordingIndex !== null && !recording ? panelStyles.disabled : null,
                ]}
                onPress={() => {
                  void recordSample(index);
                }}
              >
                <Text style={panelStyles.sampleLabel}>Sample {index + 1}</Text>
                <Text style={panelStyles.sampleState}>
                  {recording
                    ? 'Listening...'
                    : sample
                      ? `${Math.round(sample.durationMs)} ms captured`
                      : `Say "${normalizedPhrase}"`}
                </Text>
              </Pressable>
            );
          })}
        </View>

        {message ? <Text style={panelStyles.message}>{message}</Text> : null}
        {error ? <Text style={panelStyles.error}>{error}</Text> : null}

        <View style={panelStyles.actions}>
          {onUsePushToTalk ? (
            <Pressable
              disabled={recordingIndex !== null}
              style={[panelStyles.secondaryButton, recordingIndex !== null ? panelStyles.disabled : null]}
              onPress={onUsePushToTalk}
            >
              <Text style={panelStyles.secondaryButtonText}>Use Push To Talk</Text>
            </Pressable>
          ) : null}
          {!required && onCancel ? (
            <Pressable
              disabled={recordingIndex !== null}
              style={[panelStyles.secondaryButton, recordingIndex !== null ? panelStyles.disabled : null]}
              onPress={onCancel}
            >
              <Text style={panelStyles.secondaryButtonText}>Cancel</Text>
            </Pressable>
          ) : null}
          <Pressable
            disabled={saveDisabled}
            style={[panelStyles.primaryButton, saveDisabled ? panelStyles.disabled : null]}
            onPress={saveProfile}
          >
            <Text style={panelStyles.primaryButtonText}>
              {capturedCount >= JARVIS_WAKE_REQUIRED_SAMPLES ? 'Save Wake Phrase' : `${capturedCount}/${JARVIS_WAKE_REQUIRED_SAMPLES} Samples`}
            </Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const panelStyles = StyleSheet.create({
  backdrop: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    zIndex: 24,
    backgroundColor: UI.color.overlay,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 28,
  },
  panel: {
    width: '100%',
    maxWidth: 680,
    borderRadius: UI.radius.large,
    borderWidth: 1,
    borderColor: UI.color.borderStrong,
    backgroundColor: UI.color.surfaceRaised,
    padding: 22,
    gap: 18,
    ...UI.elevation.high,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 18,
  },
  headerCopy: {
    flex: 1,
    gap: 8,
  },
  eyebrow: {
    color: UI.color.accentStrong,
    fontFamily: MONO_FONT,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.55,
  },
  title: {
    color: UI.color.text,
    fontFamily: BODY_FONT,
    fontSize: 24,
    fontWeight: '700',
    letterSpacing: -0.35,
  },
  subtitle: {
    color: UI.color.textMuted,
    fontFamily: BODY_FONT,
    fontSize: 13,
    lineHeight: 19,
    maxWidth: 560,
  },
  statusBadge: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: UI.color.borderStrong,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  statusBadgeText: {
    color: UI.color.textMuted,
    fontFamily: MONO_FONT,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.8,
  },
  fieldBlock: {
    gap: 8,
  },
  label: {
    color: UI.color.textSubtle,
    fontFamily: MONO_FONT,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  input: {
    minHeight: 44,
    borderRadius: UI.radius.control,
    borderWidth: 1,
    borderColor: UI.color.borderStrong,
    backgroundColor: UI.color.surfaceMuted,
    color: UI.color.text,
    paddingHorizontal: 13,
    fontFamily: BODY_FONT,
    fontSize: 16,
    fontWeight: '700',
  },
  samplesGrid: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  sampleButton: {
    flex: 1,
    minWidth: 150,
    borderRadius: UI.radius.control,
    borderWidth: 1,
    borderColor: UI.color.border,
    backgroundColor: UI.color.surfaceMuted,
    padding: 14,
    gap: 8,
  },
  sampleButtonDone: {
    borderColor: 'rgba(117, 198, 154, 0.36)',
    backgroundColor: UI.color.successSoft,
  },
  sampleButtonHover: {
    borderColor: UI.color.borderStrong,
    backgroundColor: UI.color.surfaceHover,
  },
  sampleButtonPressed: {
    transform: [{ translateY: 1 }],
  },
  sampleLabel: {
    color: UI.color.text,
    fontFamily: MONO_FONT,
    fontSize: 12,
    fontWeight: '800',
  },
  sampleState: {
    color: UI.color.textMuted,
    fontFamily: BODY_FONT,
    fontSize: 12,
    lineHeight: 16,
  },
  message: {
    color: UI.color.success,
    fontFamily: BODY_FONT,
    fontSize: 12,
  },
  error: {
    color: UI.color.danger,
    fontFamily: BODY_FONT,
    fontSize: 12,
  },
  actions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 10,
  },
  primaryButton: {
    minHeight: 40,
    borderRadius: UI.radius.control,
    backgroundColor: UI.color.accent,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 16,
  },
  primaryButtonText: {
    color: UI.color.accentInk,
    fontFamily: BODY_FONT,
    fontSize: 13,
    fontWeight: '700',
  },
  secondaryButton: {
    minHeight: 40,
    borderRadius: UI.radius.control,
    borderWidth: 1,
    borderColor: UI.color.borderStrong,
    backgroundColor: UI.color.surfaceMuted,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 14,
  },
  secondaryButtonText: {
    color: UI.color.textMuted,
    fontFamily: BODY_FONT,
    fontSize: 13,
    fontWeight: '600',
  },
  disabled: {
    opacity: 0.48,
  },
});
