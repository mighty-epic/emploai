import './global.css';

import { Stack } from 'expo-router';
import type { ReactNode } from 'react';
import { Component } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
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
    return { error: userFacingError(error, 'The desktop renderer hit a startup problem.') };
  }

  componentDidCatch(error: unknown) {
    console.error('[kraitos:desktop-renderer] startup render failed', error);
  }

  render() {
    if (this.state.error) {
      return (
        <View style={styles.errorScreen}>
          <Text style={styles.errorTitle}>Kraitos desktop could not start</Text>
          <Text style={styles.errorText}>{this.state.error}</Text>
          <View style={styles.errorActions}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Try rendering the desktop again"
              onPress={() => this.setState({ error: null })}
              style={styles.errorButton}
            >
              <Text style={styles.errorButtonText}>Try again</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Reload the desktop application"
              onPress={() => {
                if (typeof window !== 'undefined') window.location.reload();
              }}
              style={styles.errorButtonSecondary}
            >
              <Text style={styles.errorButtonText}>Reload desktop</Text>
            </Pressable>
          </View>
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
  errorActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  errorButton: {
    minHeight: 44,
    justifyContent: 'center',
    borderRadius: 8,
    paddingHorizontal: 16,
    backgroundColor: '#17c9e5',
  },
  errorButtonSecondary: {
    minHeight: 44,
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#54627c',
    borderRadius: 8,
    paddingHorizontal: 16,
    backgroundColor: '#111a2c',
  },
  errorButtonText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '700',
  },
});
