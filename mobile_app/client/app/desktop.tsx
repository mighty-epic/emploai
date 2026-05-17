import { Redirect } from 'expo-router';

export default function DesktopRouteFallback() {
  return <Redirect href="/chat" />;
}
