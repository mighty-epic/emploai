export function playJarvisWakeTone() {
  const AudioContextConstructor = globalThis.AudioContext || (globalThis as any).webkitAudioContext;
  if (!AudioContextConstructor) return;
  const context = new AudioContextConstructor() as AudioContext;
  const oscillator = context.createOscillator();
  const gain = context.createGain();
  const now = context.currentTime;
  oscillator.type = 'sine';
  oscillator.frequency.setValueAtTime(760, now);
  oscillator.frequency.exponentialRampToValueAtTime(1040, now + 0.08);
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(0.12, now + 0.012);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.11);
  oscillator.connect(gain);
  gain.connect(context.destination);
  oscillator.start(now);
  oscillator.stop(now + 0.12);
  oscillator.onended = () => {
    oscillator.disconnect();
    gain.disconnect();
    void context.close().catch(() => undefined);
  };
}
