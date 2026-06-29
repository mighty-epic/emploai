import { Redirect, useLocalSearchParams } from 'expo-router';

function normalizeParam(value: string | string[] | undefined) {
  if (Array.isArray(value)) {
    return value[0];
  }
  return value;
}

export default function DesktopChatRedirect() {
  const params = useLocalSearchParams<{ sessionId?: string | string[] }>();
  const sessionId = normalizeParam(params.sessionId);

  return (
    <Redirect
      href={{
        pathname: '/desktop',
        params: sessionId ? { sessionId, tab: 'chat' } : { tab: 'chat' },
      }}
    />
  );
}
