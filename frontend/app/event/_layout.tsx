/**
 * Event detail route group.
 *
 * Lives outside the tab group on purpose: a detail view is a push, not a tab.
 * Because it is a separate group it does not inherit the tabs' guard, so it
 * applies the SAME shared guard rather than a second hand-written copy.
 */

import { Stack } from 'expo-router';
import React from 'react';
import { useTheme } from 'react-native-paper';

import { SessionGate } from '../../src/auth/SessionGate';
import type { AppTheme } from '../../src/theme/theme';

export default function EventLayout() {
  const theme = useTheme<AppTheme>();

  return (
    <SessionGate>
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: theme.colors.surface },
          headerTitleStyle: { fontWeight: '700' },
          headerTintColor: theme.colors.onSurface,
          contentStyle: { backgroundColor: theme.colors.background },
          title: 'Event',
        }}
      />
    </SessionGate>
  );
}
