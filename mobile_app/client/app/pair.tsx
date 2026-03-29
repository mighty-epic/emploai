import { SafeAreaView, StyleSheet, Text, View } from 'react-native';

export default function PairScreen() {
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.title}>Secure pairing</Text>
        <Text style={styles.text}>
          QR pairing will exchange a short-lived token for a revocable device token.
        </Text>
        <Text style={styles.text}>
          Backend endpoints scaffolded: POST /api/app/pair/start and POST /api/app/pair/complete.
        </Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0b1020', padding: 20 },
  card: { backgroundColor: '#141c33', borderRadius: 16, padding: 16, gap: 12 },
  title: { color: '#fff', fontSize: 24, fontWeight: '700' },
  text: { color: '#d7def0', fontSize: 16 },
});
