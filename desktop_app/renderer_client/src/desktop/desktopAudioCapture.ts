export const DESKTOP_AUDIO_CAPTURE_PROCESSOR_NAME = 'emploai-desktop-audio-capture-v1';

export const DESKTOP_AUDIO_CAPTURE_WORKLET_SOURCE = `
class EmploAIDesktopAudioCaptureProcessor extends AudioWorkletProcessor {
  process(inputs, outputs) {
    const input = inputs[0] && inputs[0][0];
    if (input && input.length) {
      const copy = new Float32Array(input);
      this.port.postMessage(copy.buffer, [copy.buffer]);
    }
    const output = outputs[0];
    if (output) {
      for (const channel of output) channel.fill(0);
    }
    return true;
  }
}
registerProcessor('${DESKTOP_AUDIO_CAPTURE_PROCESSOR_NAME}', EmploAIDesktopAudioCaptureProcessor);
`;

export type DesktopAudioCaptureHandle = {
  stop: () => void;
};

export async function createDesktopAudioCapture(
  context: AudioContext,
  source: MediaStreamAudioSourceNode,
  onSamples: (samples: Float32Array) => void,
): Promise<DesktopAudioCaptureHandle> {
  if (!context.audioWorklet || typeof context.audioWorklet.addModule !== 'function') {
    throw new Error('This desktop runtime does not support AudioWorklet microphone capture.');
  }

  const moduleBlob = new Blob([DESKTOP_AUDIO_CAPTURE_WORKLET_SOURCE], { type: 'text/javascript' });
  const moduleUrl = URL.createObjectURL(moduleBlob);
  try {
    await context.audioWorklet.addModule(moduleUrl);
  } finally {
    URL.revokeObjectURL(moduleUrl);
  }

  const node = new AudioWorkletNode(context, DESKTOP_AUDIO_CAPTURE_PROCESSOR_NAME, {
    numberOfInputs: 1,
    numberOfOutputs: 1,
    outputChannelCount: [1],
    channelCount: 1,
    channelCountMode: 'explicit',
    channelInterpretation: 'speakers',
  });
  const silentGain = context.createGain();
  silentGain.gain.value = 0;
  node.port.onmessage = (event: MessageEvent<ArrayBuffer | Float32Array>) => {
    const value = event.data;
    const samples = value instanceof Float32Array ? value : new Float32Array(value);
    if (samples.length) onSamples(samples);
  };
  source.connect(node);
  node.connect(silentGain);
  silentGain.connect(context.destination);

  let stopped = false;
  return {
    stop() {
      if (stopped) return;
      stopped = true;
      node.port.onmessage = null;
      try { source.disconnect(node); } catch (_error) { /* already disconnected */ }
      try { node.disconnect(); } catch (_error) { /* already disconnected */ }
      try { silentGain.disconnect(); } catch (_error) { /* already disconnected */ }
    },
  };
}
