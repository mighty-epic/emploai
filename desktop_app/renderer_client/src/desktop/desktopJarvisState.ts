export type JarvisPhase =
  | 'unavailable'
  | 'armed'
  | 'listening'
  | 'processing'
  | 'speaking'
  | 'muted'
  | 'error';

export type DesktopVoiceMachineState = {
  voiceState: string;
  jarvisPhase: JarvisPhase;
};

export type DesktopVoiceMachineAction =
  | { type: 'voice_state'; value: string }
  | { type: 'muted'; value: boolean };

export const initialDesktopVoiceMachineState: DesktopVoiceMachineState = {
  voiceState: 'idle',
  jarvisPhase: 'unavailable',
};

function phaseForVoiceState(value: string): JarvisPhase {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'unavailable' || normalized === 'authentication required') return 'unavailable';
  if (normalized === 'error') return 'error';
  if (normalized === 'listening') return 'listening';
  if (normalized === 'speaking') return 'speaking';
  if (['finalizing', 'generating', 'synthesizing', 'processing'].includes(normalized)) return 'processing';
  return 'armed';
}

export function desktopVoiceMachineReducer(
  state: DesktopVoiceMachineState,
  action: DesktopVoiceMachineAction,
): DesktopVoiceMachineState {
  if (action.type === 'muted') {
    return {
      ...state,
      jarvisPhase: action.value ? 'muted' : phaseForVoiceState(state.voiceState),
    };
  }
  return {
    voiceState: action.value,
    jarvisPhase: state.jarvisPhase === 'muted' ? 'muted' : phaseForVoiceState(action.value),
  };
}
