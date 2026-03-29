import { SafeAreaView, StyleSheet, Text, View } from 'react-native';

export default function SettingsScreen() {
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.title}>Settings</Text>
        <Text style={styles.text}>Reserved for backend URL, device trust, model summary, and future push settings.</Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0b1020', padding: 20 },
  card: { backgroundColor: '#141c33', borderRadius: 16, padding: 16, gap: 10 },
  title: { color: '#fff', fontSize: 24, fontWeight: '700' },
  text: { color: '#d7def0', fontSize: 16 },
});
