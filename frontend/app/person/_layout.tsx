/**
 * Person detail and enrolment route group.
 *
 * Outside the tab group, because a detail view is a push rather than a tab,
 * and therefore it does not inherit the tabs' guard. It applies the SAME
 * shared guards instead of a second hand-written copy.
 *
 * Both guards are needed, for different reasons. `SessionGate` keeps a
 * signed-out visitor out. `RoleGate` matters specifically on the web: hiding
 * the tab from an APP_USER does not stop them typing `/person/<id>` in the
 * address bar, and every route these screens call requires ADMIN. Without the
 * gate they would see a form whose every button returns 403, which reads as a
 * broken application rather than as a permission they do not have.
 */

import { Stack } from 'expo-router';
import React from 'react';
import { useTheme } from 'react-native-paper';

import { RoleGate } from '../../src/auth/RoleGate';
import { SessionGate } from '../../src/auth/SessionGate';
import type { AppTheme } from '../../src/theme/theme';

export default function PersonLayout() {
  const theme = useTheme<AppTheme>();

  return (
    <SessionGate>
      <RoleGate allow={['ADMIN']}>
        <Stack
          screenOptions={{
            headerStyle: { backgroundColor: theme.colors.surface },
            headerTitleStyle: { fontWeight: '700' },
            headerTintColor: theme.colors.onSurface,
            contentStyle: { backgroundColor: theme.colors.background },
            title: 'Person',
          }}
        />
      </RoleGate>
    </SessionGate>
  );
}
