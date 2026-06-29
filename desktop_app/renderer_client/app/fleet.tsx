import { Redirect } from 'expo-router';

export default function DesktopFleetRedirect() {
  return <Redirect href={{ pathname: '/desktop', params: { tab: 'fleet' } }} />;
}
