/**
 * Root layout: everything every screen depends on.
 *
 * Order matters here. The theme must wrap the navigator so navigation
 * surfaces are themed too, and `AuthProvider` must wrap the navigator so a
 * screen can redirect on the very first render instead of flashing the
 * dashboard before the token is checked.
 */

import { MaterialCommunityIcons } from '@expo/vector-icons';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { useColorScheme } from 'react-native';
import { PaperProvider } from 'react-native-paper';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider } from '../src/auth/AuthContext';
import { darkTheme, lightTheme } from '../src/theme/theme';

export default function RootLayout() {
  const scheme = useColorScheme();
  const theme = scheme === 'dark' ? darkTheme : lightTheme;

  return (
    <SafeAreaProvider>
      <PaperProvider
        theme={theme}
        settings={{
          // Paper's default icon set comes from react-native-vector-icons,
          // whose fonts are not registered in an Expo app. Supplying the Expo
          // icon component instead avoids blank squares where icons belong.
          icon: (props) => <MaterialCommunityIcons {...props} />,
        }}
      >
        <AuthProvider>
          <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
          <Stack
            screenOptions={{
              headerShown: false,
              contentStyle: { backgroundColor: theme.colors.background },
              animation: 'fade',
            }}
          />
        </AuthProvider>
      </PaperProvider>
    </SafeAreaProvider>
  );
}
