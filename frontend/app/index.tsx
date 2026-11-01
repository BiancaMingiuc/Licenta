/**
 * Entry route: decides where the user lands.
 *
 * The decision waits for `initialising` to finish. Redirecting earlier would
 * send a user who is already signed in to the login screen for a fraction of
 * a second, which looks like the session was lost.
 */

import { Redirect } from 'expo-router';
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { ActivityIndicator, Text, useTheme } from 'react-native-paper';

import { useAuth } from '../src/auth/AuthContext';
import type { AppTheme } from '../src/theme/theme';

export default function Index() {
  const { initialising, isSignedIn } = useAuth();
  const theme = useTheme<AppTheme>();

  if (initialising) {
    return (
      <View style={[styles.center, { backgroundColor: theme.colors.background }]}>
        <ActivityIndicator size="large" accessibilityLabel="Restoring your session" />
        <Text variant="bodyMedium" style={styles.label}>
          Restoring your session…
        </Text>
      </View>
    );
  }

  return <Redirect href={isSignedIn ? '/journal' : '/login'} />;
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
  },
  label: {
    opacity: 0.7,
  },
});
