import { Stack } from 'expo-router';
import type { ReactNode } from 'react';
import { Component } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { userFacingError } from '../lib/diagnostics';

type RootErrorBoundaryProps = {
  children: ReactNode;
};

type RootErrorBoundaryState = {
  error: string | null;
};

class RootErrorBoundary extends Component<RootErrorBoundaryProps, RootErrorBoundaryState> {
  state: RootErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: unknown): RootErrorBoundaryState {
    return { error: userFacingError(error, 'The app hit a startup problem.') };
  }

  componentDidCatch(error: unknown) {
    console.error('[emploai:root] startup render failed', error);
  }

  render() {
    if (this.state.error) {
      return (
        <View style={styles.errorScreen}>
          <Text style={styles.errorTitle}>Kraitos could not start</Text>
          <Text style={styles.errorText}>{this.state.error}</Text>
        </View>
      );
    }

    return this.props.children;
  }
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <RootErrorBoundary>
        <Stack screenOptions={{ headerShown: false }} />
      </RootErrorBoundary>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  errorScreen: {
    flex: 1,
    justifyContent: 'center',
    gap: 12,
    padding: 24,
    backgroundColor: '#0b1020',
  },
  errorTitle: {
    color: '#ffffff',
    fontSize: 22,
    fontWeight: '800',
  },
  errorText: {
    color: '#ffb4b4',
    fontSize: 14,
    lineHeight: 20,
  },
});
