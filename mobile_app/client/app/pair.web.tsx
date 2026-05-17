import { Link } from 'expo-router';
import { SafeAreaView, StyleSheet, Text, View } from 'react-native';

export default function DesktopPairDisabledScreen() {
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.title}>Pairing is disabled on desktop</Text>
        <Text style={styles.text}>
          The Electron app boots directly into the local runtime and uses the shared desktop token path. Pairing remains a mobile-only flow.
        </Text>
        <Link href="/desktop" style={styles.link}>
          Return to desktop app
        </Link>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0b1020', padding: 24 },
  card: { backgroundColor: '#141c33', borderRadius: 18, padding: 20, gap: 10 },
  title: { color: '#fff', fontSize: 24, fontWeight: '700' },
  text: { color: '#cbd6ee', lineHeight: 22 },
  link: { color: '#7cc7ff', fontWeight: '700' },
});
