/**
 * Role guard for screens whose every request requires a specific role.
 *
 * Like `SessionGate`, this is UX rather than security. The backend enforces
 * the roles itself: every `/api/whitelist/` route depends on `require_admin`
 * and answers 403 regardless of what the client renders. Nothing here grants
 * access -- removing this component would only make an unauthorised screen
 * fail on each request instead of explaining itself.
 *
 * It exists because the alternative is worse than a missing screen: an
 * APP_USER who reaches an administration screen sees controls that all fail,
 * which reads as a broken application rather than as a permission they do not
 * have. Hiding a tab is not enough on its own, because on the web the route
 * is still reachable by typing its URL -- so the check lives in the route as
 * well as in the tab bar.
 */

import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { Button, Text, useTheme } from 'react-native-paper';

import type { UserRole } from '../api/types';
import { roleLabel } from '../people/roles';
import type { AppTheme } from '../theme/theme';
import { useAuth } from './AuthContext';

export function RoleGate({
  allow,
  children,
}: {
  allow: readonly UserRole[];
  children: React.ReactNode;
}) {
  const { role } = useAuth();
  const theme = useTheme<AppTheme>();
  const router = useRouter();

  if (role && allow.includes(role)) {
    return <>{children}</>;
  }

  const required = allow.map(roleLabel).join(' or ');

  return (
    <View style={[styles.container, { backgroundColor: theme.colors.background }]}>
      <MaterialCommunityIcons
        name="lock-outline"
        size={48}
        color={theme.colors.onSurfaceVariant}
      />
      <Text variant="titleMedium" style={styles.title}>
        {required} access required
      </Text>
      <Text variant="bodyMedium" style={styles.body}>
        {role
          ? `You are signed in as ${roleLabel(role)}. This screen administers the hub, ` +
            'so it is restricted to administrators.'
          : 'Your role could not be determined. Sign in again.'}
      </Text>
      <Button mode="contained" onPress={() => router.replace('/(tabs)/journal')}>
        Back to the journal
      </Button>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    padding: 32,
  },
  title: {
    fontWeight: '700',
    textAlign: 'center',
  },
  body: {
    textAlign: 'center',
    opacity: 0.75,
    maxWidth: 420,
    marginBottom: 8,
  },
});
