/**
 * One person in the list.
 *
 * The row carries one piece of information that is easy to leave out and
 * expensive to miss: whether a FACE is enrolled.
 *
 * A person can exist in the hub with `has_embedding = false`. The matching
 * step has nothing to compare against for them, so the cameras cannot
 * recognise them and every appearance is classified as INTRUDER. From the
 * administrator's point of view the person "is in the system" and the alerts
 * look like a malfunction. Saying it on the row turns an unexplained stream
 * of alerts into a visible, fixable state.
 *
 * As everywhere else in this app, meaning never depends on colour alone:
 * every indicator carries an icon and a word, so the screen survives colour
 * blindness and the grayscale figures printed in the thesis.
 */

import { MaterialCommunityIcons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { Card, Text, TouchableRipple, useTheme } from 'react-native-paper';

import type { Person } from '../api/types';
import type { AppTheme } from '../theme/theme';
import { ROLES, roleLabel } from './roles';

/** Up to two initials, which is enough to tell rows apart at a glance. */
function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) {
    return '?';
  }
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
}

export function PersonRow({ person, onPress }: { person: Person; onPress?: () => void }) {
  const theme = useTheme<AppTheme>();
  const role = ROLES[person.role];
  const zones = person.allowed_cameras.length;

  return (
    <Card mode="contained" style={[styles.row, { backgroundColor: theme.colors.surface }]}>
      <TouchableRipple
        onPress={onPress}
        disabled={!onPress}
        accessibilityRole="button"
        accessibilityLabel={
          `${person.name}, ${roleLabel(person.role)}, ` +
          `${zones} ${zones === 1 ? 'zone' : 'zones'}, ` +
          `${person.has_embedding ? 'face enrolled' : 'no face enrolled'}`
        }
        borderless
      >
        <View style={styles.inner}>
          <View style={[styles.avatar, { backgroundColor: theme.colors.secondaryContainer }]}>
            <Text
              variant="titleMedium"
              style={{ color: theme.colors.onSecondaryContainer, fontWeight: '700' }}
            >
              {initials(person.name)}
            </Text>
          </View>

          <View style={styles.body}>
            <Text variant="titleSmall" style={styles.name} numberOfLines={1}>
              {person.name}
            </Text>

            <View style={styles.metaLine}>
              <MaterialCommunityIcons
                name={role?.icon as never}
                size={14}
                color={theme.colors.onSurfaceVariant}
              />
              <Text variant="bodySmall" style={styles.meta}>
                {roleLabel(person.role)}
              </Text>
              <Text variant="bodySmall" style={styles.separator}>
                ·
              </Text>
              <MaterialCommunityIcons
                name="video-outline"
                size={14}
                color={theme.colors.onSurfaceVariant}
              />
              <Text variant="bodySmall" style={styles.meta}>
                {zones === 0 ? 'No zone' : `${zones} ${zones === 1 ? 'zone' : 'zones'}`}
              </Text>
            </View>

            <View style={styles.metaLine}>
              {person.has_embedding ? (
                <>
                  <MaterialCommunityIcons
                    name="face-recognition"
                    size={14}
                    color={theme.outcomes.KNOWN.accent}
                  />
                  <Text variant="bodySmall" style={{ color: theme.outcomes.KNOWN.accent }}>
                    Face enrolled
                  </Text>
                </>
              ) : (
                <>
                  <MaterialCommunityIcons
                    name="alert-outline"
                    size={14}
                    color={theme.outcomes.FAULT.accent}
                  />
                  <Text variant="bodySmall" style={{ color: theme.outcomes.FAULT.accent }}>
                    No face enrolled — cannot be recognised
                  </Text>
                </>
              )}
            </View>

            {person.email ? (
              <Text variant="bodySmall" style={styles.meta} numberOfLines={1}>
                {person.email}
              </Text>
            ) : null}
          </View>

          {onPress ? (
            <MaterialCommunityIcons
              name="chevron-right"
              size={22}
              color={theme.colors.onSurfaceVariant}
              style={styles.chevron}
            />
          ) : null}
        </View>
      </TouchableRipple>
    </Card>
  );
}

const styles = StyleSheet.create({
  row: {
    borderRadius: 14,
    overflow: 'hidden',
  },
  inner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 12,
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  body: {
    flex: 1,
    gap: 2,
  },
  name: {
    fontWeight: '700',
  },
  metaLine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    flexWrap: 'wrap',
  },
  meta: {
    opacity: 0.7,
  },
  separator: {
    opacity: 0.4,
  },
  chevron: {
    opacity: 0.5,
  },
});
