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
import { Tabs } from 'expo-router';
import React from 'react';
import { useTheme } from 'react-native-paper';

import { SessionGate } from '../../src/auth/SessionGate';
import { useAuth } from '../../src/auth/AuthContext';
import type { AppTheme } from '../../src/theme/theme';

export default function TabsLayout() {
  const theme = useTheme<AppTheme>();
  const { role } = useAuth();
  const isAdmin = role === 'ADMIN';

  return (
    <SessionGate>
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
          name="people"
          options={{
            title: 'People',
            tabBarIcon: ({ color, size }) => (
              <MaterialCommunityIcons name="account-group" color={color} size={size} />
            ),
            // Hidden from the bar for anyone who is not an administrator,
            // because every route the screen calls requires ADMIN. This only
            // removes the button: on the web the URL is still typeable, which
            // is why `app/person/_layout.tsx` and the screen itself apply the
            // role gate as well.
            href: isAdmin ? undefined : null,
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
    </SessionGate>
  );
}
