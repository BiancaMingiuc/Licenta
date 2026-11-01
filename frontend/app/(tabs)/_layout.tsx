/**
 * Authenticated area.
 *
 * The guard lives here rather than in each screen: a route added to this
 * group is protected by being in the group, so a new screen cannot be
 * forgotten and left reachable without a session.
 *
 * This is a convenience guard, not a security boundary. Nothing is trusted on
 * the client -- every route the screens call is enforced by the backend's own
 * role checks. Hiding a tab only avoids showing a user buttons that would
 * return 403.
 */

import { MaterialCommunityIcons } from '@expo/vector-icons';
import { Redirect, Tabs } from 'expo-router';
import React from 'react';
import { useTheme } from 'react-native-paper';

import { useAuth } from '../../src/auth/AuthContext';
import type { AppTheme } from '../../src/theme/theme';

export default function TabsLayout() {
  const { initialising, isSignedIn } = useAuth();
  const theme = useTheme<AppTheme>();

  if (initialising) {
    return null;
  }
  if (!isSignedIn) {
    return <Redirect href="/login" />;
  }

  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: theme.colors.surface },
        headerTitleStyle: { fontWeight: '700' },
        tabBarActiveTintColor: theme.colors.primary,
        tabBarStyle: {
          backgroundColor: theme.colors.surface,
          borderTopColor: theme.colors.outlineVariant,
        },
      }}
    >
      <Tabs.Screen
        name="journal"
        options={{
          title: 'Journal',
          tabBarIcon: ({ color, size }) => (
            <MaterialCommunityIcons name="clipboard-text-clock" color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: 'Profile',
          tabBarIcon: ({ color, size }) => (
            <MaterialCommunityIcons name="account-circle" color={color} size={size} />
          ),
        }}
      />
    </Tabs>
  );
}
