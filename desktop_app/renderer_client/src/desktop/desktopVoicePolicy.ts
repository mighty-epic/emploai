export const JARVIS_BARGE_IN_MIN_VOICED_MS = 1500;
export const JARVIS_BARGE_IN_MIN_WORDS = 2;
export const JARVIS_BARGE_IN_MIN_CHARS = 6;
export const VOICE_ENGINE_NONE = 'none';
export const VOICE_ENGINE_ENGLISH = 'english_local';
export const VOICE_ENGINE_HEBREW = 'hebrew_local';
export const JARVIS_ENGLISH_VOICE_PATH_ERROR = 'Jarvis mode currently uses the English local voice path.';
export const STT_BACKEND_LOCAL_WHISPER = 'local_whisper';
export const STT_BACKEND_OPENAI_REALTIME = 'openai_realtime';
export const TTS_BACKEND_KOKORO = 'kokoro_onnx';
export const TTS_BACKEND_KYUTAI = 'pocket';
export const ALWAYS_ON_VOICE_AUTO_SEND = false;

export type JarvisSttBackend = typeof STT_BACKEND_LOCAL_WHISPER | typeof STT_BACKEND_OPENAI_REALTIME;
export type JarvisTtsBackend = typeof TTS_BACKEND_KOKORO | typeof TTS_BACKEND_KYUTAI;

export function composeVoiceDraftInput(baseInput: string, draftText: string) {
  const draft = String(draftText || '').trim();
  if (!draft) {
    return baseInput;
  }
  const baseWithoutTrailingWhitespace = baseInput.replace(/\s+$/, '');
  if (!baseWithoutTrailingWhitespace) {
    return draft;
  }
  return `${baseWithoutTrailingWhitespace} ${draft}`;
}

export function appendVoiceTranscriptSegment(baseInput: string, segmentText: string) {
  const segment = String(segmentText || '').trim();
  const base = String(baseInput || '').trim();
  if (!segment) {
    return base;
  }
  if (!base) {
    return segment;
  }
  if (base === segment || base.endsWith(` ${segment}`)) {
    return base;
  }
  return `${base} ${segment}`;
}

export function jarvisBargeInSpeechWordCount(text: string) {
  return String(text || '')
    .trim()
    .split(/\s+/)
    .filter((word) => /[A-Za-z0-9]/.test(word))
    .length;
}

export function isMeaningfulJarvisBargeInText(text: string) {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim();
  return (
    normalized.length >= JARVIS_BARGE_IN_MIN_CHARS
    && jarvisBargeInSpeechWordCount(normalized) >= JARVIS_BARGE_IN_MIN_WORDS
  );
}

export function normalizeJarvisSttBackend(value: string | null | undefined): JarvisSttBackend {
  const backend = String(value || '').trim().toLowerCase().replace(/-/g, '_');
  if (backend === 'openai' || backend === STT_BACKEND_OPENAI_REALTIME || backend === 'realtime' || backend === 'realtime_api') {
    return STT_BACKEND_OPENAI_REALTIME;
  }
  return STT_BACKEND_LOCAL_WHISPER;
}

export function jarvisSttBackendLabel(value: string | null | undefined) {
  const backend = normalizeJarvisSttBackend(value);
  if (backend === STT_BACKEND_OPENAI_REALTIME) {
    return 'Realtime API';
  }
  return 'Local Whisper';
}

export function normalizeJarvisTtsBackend(value: string | null | undefined): JarvisTtsBackend | string {
  const backend = String(value || '').trim().toLowerCase().replace(/-/g, '_');
  if (backend === 'kokoro' || backend === TTS_BACKEND_KOKORO) {
    return TTS_BACKEND_KOKORO;
  }
  if (backend === 'kyutai' || backend === 'kyutai_clone' || backend === 'pocket_tts' || backend === TTS_BACKEND_KYUTAI) {
    return TTS_BACKEND_KYUTAI;
  }
  return backend;
}

export function jarvisTtsBackendLabel(value: string | null | undefined) {
  const backend = normalizeJarvisTtsBackend(value);
  if (backend === TTS_BACKEND_KOKORO) {
    return 'Kokoro';
  }
  if (backend === TTS_BACKEND_KYUTAI) {
    return 'Kyutai clone';
  }
  return String(value || 'TTS').trim() || 'TTS';
}
