/**
 * Profile: who is signed in, and how to sign out.
 *
 * The role is shown explicitly because it determines what the rest of the app
 * will allow. An APP_USER seeing only their own events is correct behaviour,
 * not a bug, and stating the role is what makes that visible rather than
 * confusing.
 */

import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React, { useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { Button, Card, Chip, Divider, List, Text, useTheme } from 'react-native-paper';

import { getApiBaseUrl } from '../../src/api/client';
import type { UserRole } from '../../src/api/types';
import { useAuth } from '../../src/auth/AuthContext';
import type { AppTheme } from '../../src/theme/theme';

const ROLE_TEXT: Record<UserRole, { label: string; description: string; icon: string }> = {
  ADMIN: {
    label: 'Administrator',
    description:
      'Full control of this hub: enrol faces, manage cameras and expected zones, read every event.',
    icon: 'shield-crown',
  },
  APP_USER: {
    label: 'Application user',
    description:
      'Can sign in and review their own events. Cannot manage people or cameras.',
    icon: 'account-check',
  },
  MONITORED: {
    label: 'Monitored person',
    description:
      'Enrolled for recognition only, with no application access. This role cannot sign in.',
    icon: 'account-eye',
  },
};

export default function ProfileScreen() {
  const theme = useTheme<AppTheme>();
  const router = useRouter();
  const { user, signOut } = useAuth();
  const [signingOut, setSigningOut] = useState(false);

  if (!user) {
    return null;
  }

  const role = ROLE_TEXT[user.role];

  async function handleSignOut() {
    setSigningOut(true);
    await signOut();
    router.replace('/login');
  }

  return (
    <ScrollView
      contentContainerStyle={[
        styles.content,
        { maxWidth: theme.maxContentWidth, alignSelf: 'center', width: '100%' },
      ]}
    >
      <Card mode="elevated" style={styles.card}>
        <Card.Content style={styles.identity}>
          <View style={[styles.avatar, { backgroundColor: theme.colors.primaryContainer }]}>
            <MaterialCommunityIcons
              name={role.icon as never}
              size={34}
              color={theme.colors.onPrimaryContainer}
            />
          </View>
          <View style={styles.identityText}>
            <Text variant="titleLarge" style={styles.name}>
              {user.name}
            </Text>
            {user.email ? (
              <Text variant="bodyMedium" style={{ opacity: 0.7 }}>
                {user.email}
              </Text>
            ) : null}
            <Chip
              icon={role.icon as never}
              compact
              style={styles.chip}
              textStyle={styles.chipText}
            >
              {role.label}
            </Chip>
          </View>
        </Card.Content>
        <Divider />
        <Card.Content style={styles.roleBlock}>
          <Text variant="bodySmall" style={{ opacity: 0.75 }}>
            {role.description}
          </Text>
        </Card.Content>
      </Card>

      <Card mode="elevated" style={styles.card}>
        <List.Section>
          <List.Subheader>Connection</List.Subheader>
          <List.Item
            title="Hub"
            description={user.hub_id}
            left={(props) => <List.Icon {...props} icon="router-wireless" />}
          />
          <List.Item
            title="Backend address"
            description={getApiBaseUrl() || 'Not configured'}
            left={(props) => <List.Icon {...props} icon="server-network" />}
          />
        </List.Section>
      </Card>

      <Button
        mode="outlined"
        icon="logout"
        onPress={handleSignOut}
        loading={signingOut}
        disabled={signingOut}
        style={styles.signOut}
        contentStyle={styles.signOutContent}
      >
        Sign out
      </Button>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: 16,
    gap: 16,
  },
  card: {
    borderRadius: 16,
  },
  identity: {
    flexDirection: 'row',
    gap: 16,
    alignItems: 'center',
    paddingVertical: 8,
  },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },
  identityText: {
    flex: 1,
    gap: 4,
  },
  name: {
    fontWeight: '700',
  },
  chip: {
    alignSelf: 'flex-start',
    marginTop: 4,
  },
  chipText: {
    fontSize: 12,
  },
  roleBlock: {
    paddingTop: 12,
  },
  signOut: {
    borderRadius: 12,
  },
  signOutContent: {
    paddingVertical: 6,
  },
});
