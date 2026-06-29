import { Redirect } from 'expo-router';

export default function DesktopSettingsRedirect() {
  return <Redirect href={{ pathname: '/desktop', params: { setup: '1' } }} />;
}
