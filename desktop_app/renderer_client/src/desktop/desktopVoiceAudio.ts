export type VoiceGateState = {
  pendingFrames: Float32Array[];
  pendingSampleCount: number;
  prerollFrames: Float32Array[];
  aboveFrames: number;
  belowFrames: number;
  recording: boolean;
  activeFrames: number;
  voicedFrames: number;
};

export function createVoiceGateState(): VoiceGateState {
  return {
    pendingFrames: [],
    pendingSampleCount: 0,
    prerollFrames: [],
    aboveFrames: 0,
    belowFrames: 0,
    recording: false,
    activeFrames: 0,
    voicedFrames: 0,
  };
}

export function bytesToBase64(bytes: Uint8Array) {
  let binary = '';
  for (let index = 0; index < bytes.length; index += 1) {
    binary += String.fromCharCode(bytes[index]);
  }
  return globalThis.btoa(binary);
}

export function concatFloat32(chunks: Float32Array[], totalLength?: number) {
  const length = totalLength ?? chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const merged = new Float32Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged;
}

export function encodePcm16Wav(samples: Float32Array, sampleRate: number) {
  const dataSize = samples.length * 2;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  let offset = 0;
  const writeString = (value: string) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset, value.charCodeAt(index));
      offset += 1;
    }
  };

  writeString('RIFF');
  view.setUint32(offset, 36 + dataSize, true);
  offset += 4;
  writeString('WAVE');
  writeString('fmt ');
  view.setUint32(offset, 16, true);
  offset += 4;
  view.setUint16(offset, 1, true);
  offset += 2;
  view.setUint16(offset, 1, true);
  offset += 2;
  view.setUint32(offset, sampleRate, true);
  offset += 4;
  view.setUint32(offset, sampleRate * 2, true);
  offset += 4;
  view.setUint16(offset, 2, true);
  offset += 2;
  view.setUint16(offset, 16, true);
  offset += 2;
  writeString('data');
  view.setUint32(offset, dataSize, true);
  offset += 4;

  for (let index = 0; index < samples.length; index += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[index]));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }

  return buffer;
}

export function samplesDbfs(samples: Float32Array) {
  if (!samples.length) return -120;
  let sumSquares = 0;
  for (let index = 0; index < samples.length; index += 1) {
    sumSquares += samples[index] * samples[index];
  }
  if (sumSquares <= 0) return -120;
  const rms = Math.sqrt(sumSquares / samples.length);
  return 20 * Math.log10(Math.max(rms, 0.000001));
}

export function takeGateFrame(gate: VoiceGateState, frameSamples: number) {
  if (gate.pendingSampleCount < frameSamples) {
    return null;
  }

  const frame = new Float32Array(frameSamples);
  let written = 0;
  while (written < frameSamples && gate.pendingFrames.length > 0) {
    const head = gate.pendingFrames[0];
    const needed = frameSamples - written;
    if (head.length <= needed) {
      frame.set(head, written);
      written += head.length;
      gate.pendingFrames.shift();
    } else {
      frame.set(head.subarray(0, needed), written);
      gate.pendingFrames[0] = head.subarray(needed);
      written += needed;
    }
  }
  gate.pendingSampleCount -= frameSamples;
  return frame;
}

export function createAudioContext() {
  const AudioContextConstructor = globalThis.AudioContext || (globalThis as any).webkitAudioContext;
  if (!AudioContextConstructor) {
    throw new Error('Web Audio microphone capture is not available in this desktop renderer.');
  }
  return new AudioContextConstructor() as AudioContext;
}
