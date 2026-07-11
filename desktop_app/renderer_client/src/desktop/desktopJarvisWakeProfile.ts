import { JARVIS_WAKE_PHRASE } from './desktopVoicePolicy';
import { createDesktopAudioCapture } from './desktopAudioCapture';
import type { DesktopAudioCaptureHandle } from './desktopAudioCapture';

export const JARVIS_WAKE_PROFILE_STORAGE_KEY = 'emploai.jarvisWakeProfile.v1';
export const JARVIS_WAKE_REQUIRED_SAMPLES = 3;
export const JARVIS_WAKE_ENROLLMENT_RECORD_MS = 1700;
export const JARVIS_WAKE_MATCH_MIN_MS = 520;
export const JARVIS_WAKE_MATCH_MAX_MS = 2200;
export const JARVIS_WAKE_MATCH_SCORE_EVERY_MS = 120;
export const JARVIS_WAKE_MATCH_RELEASE_MS = 520;

const TARGET_SAMPLE_RATE = 8000;
const FEATURE_FRAME_SIZE = 256;
const FEATURE_HOP_SIZE = 96;
const FEATURE_FREQUENCIES = [220, 360, 520, 760, 1100, 1600, 2300, 3200];
const DEFAULT_WAKE_DISTANCE_THRESHOLD = 0.68;

export type JarvisWakeSignature = {
  sampleRate: number;
  durationMs: number;
  rms: number;
  frames: number[][];
};

export type JarvisWakeProfile = {
  version: 1;
  phrase: string;
  createdAt: string;
  updatedAt: string;
  sampleCount: number;
  threshold: number;
  signatures: JarvisWakeSignature[];
};

export type JarvisWakeMatchState = {
  active: boolean;
  frames: Float32Array[];
  sampleCount: number;
  frameCount: number;
  voicedFrames: number;
  belowFrames: number;
  lastScoreFrame: number;
  matchedFrames: number;
  bestDistance: number | null;
};

export type JarvisWakeScore = {
  matched: boolean;
  distance: number;
  threshold: number;
  durationMs: number;
  reason?: string;
};

export type JarvisWakeAudioSample = {
  samples: Float32Array;
  sampleRate: number;
};

export function createJarvisWakeMatchState(): JarvisWakeMatchState {
  return {
    active: false,
    frames: [],
    sampleCount: 0,
    frameCount: 0,
    voicedFrames: 0,
    belowFrames: 0,
    lastScoreFrame: 0,
    matchedFrames: 0,
    bestDistance: null,
  };
}

export function normalizeJarvisWakePhrase(value: string | null | undefined) {
  const cleaned = String(value || '')
    .replace(/[^\p{L}\p{N}\s'-]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 40);
  return cleaned || JARVIS_WAKE_PHRASE;
}

export function isJarvisWakeProfileReady(profile: JarvisWakeProfile | null | undefined) {
  return Boolean(
    profile
    && profile.version === 1
    && normalizeJarvisWakePhrase(profile.phrase)
    && Array.isArray(profile.signatures)
    && profile.signatures.length >= JARVIS_WAKE_REQUIRED_SAMPLES
    && profile.signatures.every((signature) => Array.isArray(signature.frames) && signature.frames.length >= 4)
  );
}

export function loadJarvisWakeProfile(): JarvisWakeProfile | null {
  const storage = safeLocalStorage();
  if (!storage) {
    return null;
  }
  try {
    return normalizeStoredProfile(JSON.parse(storage.getItem(JARVIS_WAKE_PROFILE_STORAGE_KEY) || 'null'));
  } catch {
    return null;
  }
}

export function saveJarvisWakeProfile(profile: JarvisWakeProfile) {
  const storage = safeLocalStorage();
  if (!storage) {
    return;
  }
  storage.setItem(JARVIS_WAKE_PROFILE_STORAGE_KEY, JSON.stringify(profile));
}

export function clearJarvisWakeProfile() {
  const storage = safeLocalStorage();
  if (!storage) {
    return;
  }
  storage.removeItem(JARVIS_WAKE_PROFILE_STORAGE_KEY);
}

export function createJarvisWakeSignature(samples: Float32Array, sampleRate: number): JarvisWakeSignature {
  if (!samples.length || !Number.isFinite(sampleRate) || sampleRate <= 0) {
    throw new Error('No wake phrase audio was captured.');
  }

  const trimmed = trimSilence(samples, sampleRate);
  const durationMs = (trimmed.length / sampleRate) * 1000;
  if (durationMs < 250) {
    throw new Error('That sample was too short. Say the full wake phrase clearly.');
  }
  if (durationMs > 2400) {
    throw new Error('That sample was too long. Say only the wake phrase.');
  }

  const rms = rootMeanSquare(trimmed);
  if (rms < 0.006) {
    throw new Error('That sample was too quiet. Move closer to the microphone and try again.');
  }

  const normalized = normalizeRms(trimmed);
  const resampled = resampleLinear(normalized, sampleRate, TARGET_SAMPLE_RATE);
  const frames = extractFeatureFrames(resampled, TARGET_SAMPLE_RATE);
  if (frames.length < 5) {
    throw new Error('That sample did not contain enough clear speech.');
  }

  return {
    sampleRate: TARGET_SAMPLE_RATE,
    durationMs: roundNumber(durationMs, 1),
    rms: roundNumber(rms, 5),
    frames: frames.map((frame) => frame.map((value) => roundNumber(value, 4))),
  };
}

export function buildJarvisWakeProfile(phraseValue: string, signatures: JarvisWakeSignature[]): JarvisWakeProfile {
  const phrase = normalizeJarvisWakePhrase(phraseValue);
  const usableSignatures = signatures.filter((signature) => Array.isArray(signature.frames) && signature.frames.length >= 5);
  if (usableSignatures.length < JARVIS_WAKE_REQUIRED_SAMPLES) {
    throw new Error(`Record ${JARVIS_WAKE_REQUIRED_SAMPLES} wake phrase samples first.`);
  }

  const threshold = calibratedThreshold(usableSignatures);
  const now = new Date().toISOString();
  return {
    version: 1,
    phrase,
    createdAt: now,
    updatedAt: now,
    sampleCount: usableSignatures.length,
    threshold,
    signatures: usableSignatures,
  };
}

export function scoreJarvisWakeCandidate(
  samples: Float32Array,
  sampleRate: number,
  profile: JarvisWakeProfile | null | undefined,
): JarvisWakeScore {
  const threshold = clamp(Number(profile?.threshold) || DEFAULT_WAKE_DISTANCE_THRESHOLD, 0.45, 0.74);
  if (!isJarvisWakeProfileReady(profile)) {
    return { matched: false, distance: Number.POSITIVE_INFINITY, threshold, durationMs: 0, reason: 'missing_profile' };
  }
  const readyProfile = profile as JarvisWakeProfile;

  let candidate: JarvisWakeSignature;
  try {
    candidate = createJarvisWakeSignature(samples, sampleRate);
  } catch (error) {
    return {
      matched: false,
      distance: Number.POSITIVE_INFINITY,
      threshold,
      durationMs: samples.length && sampleRate > 0 ? (samples.length / sampleRate) * 1000 : 0,
      reason: error instanceof Error ? error.message : 'invalid_candidate',
    };
  }

  const profileDurations = readyProfile.signatures.map((signature) => signature.durationMs).filter((value) => value > 0);
  const averageDurationMs = mean(profileDurations);
  const shortestAllowedDurationMs = Math.max(420, averageDurationMs ? averageDurationMs * 0.52 : 420);
  if (candidate.durationMs < shortestAllowedDurationMs) {
    return {
      matched: false,
      distance: Number.POSITIVE_INFINITY,
      threshold,
      durationMs: candidate.durationMs,
      reason: 'too_short_for_wake_phrase',
    };
  }

  const profileRmsValues = readyProfile.signatures.map((signature) => signature.rms).filter((value) => value > 0);
  const averageProfileRms = mean(profileRmsValues);
  if (averageProfileRms > 0 && candidate.rms < Math.max(0.007, averageProfileRms * 0.18)) {
    return {
      matched: false,
      distance: Number.POSITIVE_INFINITY,
      threshold,
      durationMs: candidate.durationMs,
      reason: 'too_quiet_for_wake_phrase',
    };
  }

  const distances = readyProfile.signatures
    .map((signature) => prefixDtwDistance(candidate.frames, signature.frames))
    .filter((value) => Number.isFinite(value))
    .sort((left, right) => left - right);
  if (!distances.length) {
    return { matched: false, distance: Number.POSITIVE_INFINITY, threshold, durationMs: candidate.durationMs, reason: 'no_templates' };
  }

  const best = distances[0];
  const requiredVotes = Math.min(2, distances.length);
  const agreement = distances.slice(0, requiredVotes).reduce((sum, value) => sum + value, 0) / requiredVotes;
  const matched = best <= threshold && agreement <= threshold * 1.03;
  return {
    matched,
    distance: roundNumber(best, 4),
    threshold,
    durationMs: candidate.durationMs,
    reason: matched ? undefined : 'distance',
  };
}

export async function recordJarvisWakeSample(durationMs = JARVIS_WAKE_ENROLLMENT_RECORD_MS): Promise<JarvisWakeAudioSample> {
  if (!globalThis.navigator?.mediaDevices?.getUserMedia) {
    throw new Error('Microphone capture is not available in this desktop renderer.');
  }
  const AudioContextConstructor = globalThis.AudioContext || (globalThis as any).webkitAudioContext;
  if (!AudioContextConstructor) {
    throw new Error('Web Audio microphone capture is not available in this desktop renderer.');
  }

  const stream = await globalThis.navigator.mediaDevices.getUserMedia({ audio: true });
  const context = new AudioContextConstructor() as AudioContext;
  const chunks: Float32Array[] = [];
  let source: MediaStreamAudioSourceNode | null = null;
  let capture: DesktopAudioCaptureHandle | null = null;
  try {
    if (context.state === 'suspended') {
      await context.resume();
    }
    source = context.createMediaStreamSource(stream);
    capture = await createDesktopAudioCapture(context, source, (samples) => {
      chunks.push(new Float32Array(samples));
    });
    await new Promise((resolve) => setTimeout(resolve, Math.max(500, durationMs)));
  } finally {
    capture?.stop();
    try {
      source?.disconnect();
    } catch {
      // no-op
    }
    stream.getTracks().forEach((track) => track.stop());
    void context.close().catch(() => undefined);
  }

  return {
    samples: concatFloat32(chunks),
    sampleRate: context.sampleRate,
  };
}

function safeLocalStorage(): Storage | null {
  try {
    return (globalThis as any).localStorage || null;
  } catch {
    return null;
  }
}

function normalizeStoredProfile(value: unknown): JarvisWakeProfile | null {
  const profile = value as Partial<JarvisWakeProfile> | null;
  if (!profile || profile.version !== 1 || !Array.isArray(profile.signatures)) {
    return null;
  }
  const signatures = profile.signatures
    .map((signature) => ({
      sampleRate: Number(signature?.sampleRate) || TARGET_SAMPLE_RATE,
      durationMs: Number(signature?.durationMs) || 0,
      rms: Number(signature?.rms) || 0,
      frames: Array.isArray(signature?.frames)
        ? signature.frames
            .filter((frame) => Array.isArray(frame))
            .map((frame) => frame.map((item) => Number(item)).filter((item) => Number.isFinite(item)))
            .filter((frame) => frame.length >= 4)
        : [],
    }))
    .filter((signature) => signature.frames.length >= 5);
  const normalized: JarvisWakeProfile = {
    version: 1,
    phrase: normalizeJarvisWakePhrase(profile.phrase),
    createdAt: String(profile.createdAt || ''),
    updatedAt: String(profile.updatedAt || profile.createdAt || ''),
    sampleCount: signatures.length,
    threshold: clamp(Number(profile.threshold) || DEFAULT_WAKE_DISTANCE_THRESHOLD, 0.45, 1.25),
    signatures,
  };
  return isJarvisWakeProfileReady(normalized) ? normalized : null;
}

function trimSilence(samples: Float32Array, sampleRate: number) {
  const frameSize = Math.max(1, Math.round(sampleRate * 0.02));
  const frameCount = Math.max(1, Math.ceil(samples.length / frameSize));
  const rmsFrames: number[] = [];
  let maxRms = 0;
  for (let frameIndex = 0; frameIndex < frameCount; frameIndex += 1) {
    const start = frameIndex * frameSize;
    const end = Math.min(samples.length, start + frameSize);
    const rms = rootMeanSquare(samples.subarray(start, end));
    rmsFrames.push(rms);
    maxRms = Math.max(maxRms, rms);
  }
  const threshold = Math.max(0.006, maxRms * 0.18);
  let firstFrame = 0;
  while (firstFrame < rmsFrames.length && rmsFrames[firstFrame] < threshold) {
    firstFrame += 1;
  }
  let lastFrame = rmsFrames.length - 1;
  while (lastFrame > firstFrame && rmsFrames[lastFrame] < threshold) {
    lastFrame -= 1;
  }
  if (firstFrame >= rmsFrames.length) {
    return samples;
  }
  const padding = Math.round(sampleRate * 0.08);
  const start = Math.max(0, firstFrame * frameSize - padding);
  const end = Math.min(samples.length, (lastFrame + 1) * frameSize + padding);
  return samples.subarray(start, end);
}

function normalizeRms(samples: Float32Array) {
  const rms = rootMeanSquare(samples);
  if (rms <= 0) {
    return samples;
  }
  const gain = Math.min(24, 0.08 / rms);
  const normalized = new Float32Array(samples.length);
  for (let index = 0; index < samples.length; index += 1) {
    normalized[index] = clamp(samples[index] * gain, -1, 1);
  }
  return normalized;
}

function resampleLinear(samples: Float32Array, fromRate: number, toRate: number) {
  if (Math.abs(fromRate - toRate) < 1) {
    return samples;
  }
  const nextLength = Math.max(1, Math.round(samples.length * (toRate / fromRate)));
  const next = new Float32Array(nextLength);
  for (let index = 0; index < nextLength; index += 1) {
    const sourcePosition = index * (fromRate / toRate);
    const left = Math.floor(sourcePosition);
    const right = Math.min(samples.length - 1, left + 1);
    const mix = sourcePosition - left;
    next[index] = samples[left] * (1 - mix) + samples[right] * mix;
  }
  return next;
}

function extractFeatureFrames(samples: Float32Array, sampleRate: number) {
  const rawFrames: number[][] = [];
  for (let start = 0; start + FEATURE_FRAME_SIZE <= samples.length; start += FEATURE_HOP_SIZE) {
    const frame = samples.subarray(start, start + FEATURE_FRAME_SIZE);
    rawFrames.push(extractFeatureFrame(frame, sampleRate));
  }
  if (!rawFrames.length && samples.length > 0) {
    const padded = new Float32Array(FEATURE_FRAME_SIZE);
    padded.set(samples.subarray(0, Math.min(samples.length, FEATURE_FRAME_SIZE)));
    rawFrames.push(extractFeatureFrame(padded, sampleRate));
  }

  const energyValues = rawFrames.map((frame) => frame[0]);
  const energyMean = mean(energyValues);
  const energyStd = standardDeviation(energyValues, energyMean) || 1;
  return rawFrames.map((frame) => [
    clamp((frame[0] - energyMean) / (energyStd * 3), -1, 1),
    clamp(frame[1] * 2 - 1, -1, 1),
    ...frame.slice(2).map((value) => clamp(value / 3, -1, 1)),
  ]);
}

function extractFeatureFrame(frame: Float32Array, sampleRate: number) {
  const windowed = new Float32Array(frame.length);
  let sumSquares = 0;
  let zeroCrossings = 0;
  for (let index = 0; index < frame.length; index += 1) {
    const window = 0.5 - 0.5 * Math.cos((2 * Math.PI * index) / Math.max(1, frame.length - 1));
    const value = frame[index] * window;
    windowed[index] = value;
    sumSquares += value * value;
    if (index > 0 && Math.sign(frame[index]) !== Math.sign(frame[index - 1])) {
      zeroCrossings += 1;
    }
  }
  const logEnergy = Math.log(Math.sqrt(sumSquares / Math.max(1, frame.length)) + 1e-6);
  const zcr = zeroCrossings / Math.max(1, frame.length - 1);
  const bandLogs = FEATURE_FREQUENCIES.map((frequency) => Math.log(goertzelPower(windowed, sampleRate, frequency) + 1e-9));
  const bandMean = mean(bandLogs);
  const bandStd = standardDeviation(bandLogs, bandMean) || 1;
  return [
    logEnergy,
    zcr,
    ...bandLogs.map((value) => (value - bandMean) / bandStd),
  ];
}

function calibratedThreshold(signatures: JarvisWakeSignature[]) {
  const distances: number[] = [];
  for (let left = 0; left < signatures.length; left += 1) {
    for (let right = left + 1; right < signatures.length; right += 1) {
      distances.push(dtwDistance(signatures[left].frames, signatures[right].frames));
    }
  }
  if (!distances.length) {
    return DEFAULT_WAKE_DISTANCE_THRESHOLD;
  }
  const maxDistance = Math.max(...distances);
  const averageDistance = mean(distances);
  return roundNumber(clamp(Math.max(maxDistance * 1.35, averageDistance * 1.75) + 0.06, 0.5, 0.74), 4);
}

function prefixDtwDistance(candidateFrames: number[][], templateFrames: number[][]) {
  if (!candidateFrames.length || !templateFrames.length) {
    return Number.POSITIVE_INFINITY;
  }
  const minLength = Math.max(4, Math.round(templateFrames.length * 0.62));
  if (candidateFrames.length < minLength) {
    return dtwDistance(candidateFrames, templateFrames) + 0.16;
  }
  const desiredLengths = [
    Math.round(templateFrames.length * 0.82),
    templateFrames.length,
    Math.round(templateFrames.length * 1.18),
    Math.round(templateFrames.length * 1.42),
  ];
  let best = Number.POSITIVE_INFINITY;
  for (const desiredLength of desiredLengths) {
    const length = clamp(desiredLength, minLength, candidateFrames.length);
    const prefix = candidateFrames.slice(0, length);
    best = Math.min(best, dtwDistance(prefix, templateFrames));
  }
  if (candidateFrames.length <= templateFrames.length * 1.55) {
    best = Math.min(best, dtwDistance(candidateFrames, templateFrames));
  }
  return best;
}

function dtwDistance(leftFrames: number[][], rightFrames: number[][]) {
  const leftLength = leftFrames.length;
  const rightLength = rightFrames.length;
  if (!leftLength || !rightLength) {
    return Number.POSITIVE_INFINITY;
  }
  let previous = new Array(rightLength + 1).fill(Number.POSITIVE_INFINITY);
  let current = new Array(rightLength + 1).fill(Number.POSITIVE_INFINITY);
  previous[0] = 0;
  for (let left = 1; left <= leftLength; left += 1) {
    current[0] = Number.POSITIVE_INFINITY;
    for (let right = 1; right <= rightLength; right += 1) {
      const cost = vectorDistance(leftFrames[left - 1], rightFrames[right - 1]);
      current[right] = cost + Math.min(previous[right], current[right - 1], previous[right - 1]);
    }
    [previous, current] = [current, previous];
  }
  return previous[rightLength] / Math.max(leftLength, rightLength);
}

function vectorDistance(left: number[], right: number[]) {
  const weights = [0.7, 0.5, 1, 1, 1, 1, 1, 1, 1, 1];
  const length = Math.min(left.length, right.length);
  let weightedSum = 0;
  let weightTotal = 0;
  for (let index = 0; index < length; index += 1) {
    const weight = weights[index] ?? 1;
    const delta = (left[index] || 0) - (right[index] || 0);
    weightedSum += delta * delta * weight;
    weightTotal += weight;
  }
  return Math.sqrt(weightedSum / Math.max(1, weightTotal));
}

function goertzelPower(samples: Float32Array, sampleRate: number, frequency: number) {
  const omega = (2 * Math.PI * frequency) / sampleRate;
  const coefficient = 2 * Math.cos(omega);
  let previous = 0;
  let previous2 = 0;
  for (let index = 0; index < samples.length; index += 1) {
    const current = samples[index] + coefficient * previous - previous2;
    previous2 = previous;
    previous = current;
  }
  return previous2 * previous2 + previous * previous - coefficient * previous * previous2;
}

function rootMeanSquare(samples: Float32Array) {
  if (!samples.length) {
    return 0;
  }
  let sumSquares = 0;
  for (let index = 0; index < samples.length; index += 1) {
    sumSquares += samples[index] * samples[index];
  }
  return Math.sqrt(sumSquares / samples.length);
}

function concatFloat32(chunks: Float32Array[]) {
  const length = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const merged = new Float32Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged;
}

function mean(values: number[]) {
  if (!values.length) {
    return 0;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function standardDeviation(values: number[], valueMean = mean(values)) {
  if (values.length <= 1) {
    return 0;
  }
  const variance = values.reduce((sum, value) => sum + ((value - valueMean) ** 2), 0) / values.length;
  return Math.sqrt(variance);
}

function roundNumber(value: number, digits: number) {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}
