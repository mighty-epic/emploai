import { Link } from 'expo-router';
import { SafeAreaView, ScrollView, StyleSheet, Text, View } from 'react-native';

const features = [
  'Live chat with streamed responses',
  'Realtime tool log feed',
  'Voice draft transcript lane',
  'Shared sessions with Telegram labels',
  'Jobs and scheduler controls',
  'Camera, gallery, and document upload hooks',
];

export default function HomeScreen() {
  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>EmploAI App</Text>
        <Text style={styles.subtitle}>
          Android-first mobile shell for the additive app channel.
        </Text>

        <View style={styles.card}>
          <Text style={styles.sectionTitle}>V1 scope locked</Text>
          {features.map((feature) => (
            <Text key={feature} style={styles.bullet}>• {feature}</Text>
          ))}
        </View>

        <View style={styles.card}>
          <Text style={styles.sectionTitle}>Primary screens</Text>
          <Link href="/pair" style={styles.link}>Pair / Login</Link>
          <Link href="/chat" style={styles.link}>Chat</Link>
          <Link href="/sessions" style={styles.link}>Sessions</Link>
          <Link href="/jobs" style={styles.link}>Jobs</Link>
          <Link href="/settings" style={styles.link}>Settings</Link>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0b1020' },
  content: { padding: 20, gap: 16 },
  title: { color: '#ffffff', fontSize: 30, fontWeight: '700' },
  subtitle: { color: '#b6c0d4', fontSize: 16 },
  card: {
    backgroundColor: '#141c33',
    borderRadius: 16,
    padding: 16,
    gap: 10,
  },
  sectionTitle: { color: '#ffffff', fontSize: 18, fontWeight: '600' },
  bullet: { color: '#d7def0', fontSize: 15 },
  link: { color: '#7cc7ff', fontSize: 16 },
});
