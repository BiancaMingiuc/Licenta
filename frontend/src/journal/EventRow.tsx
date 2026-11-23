/**
 * One journal row.
 *
 * Presentation rules that follow from decision D3:
 *
 * - The row shows the ACTION level (expected / alert / fault) prominently and
 *   the precise reason as readable text. The backend stores the fine-grained
 *   reason because the thesis evaluation chapter needs to count categories; a
 *   person needs to know what happened.
 * - Alerts and faults are visually distinct. A broken camera must not look
 *   like a break-in attempt, or the operator learns to dismiss both.
 * - Meaning never depends on colour alone: every row carries an icon and a
 *   word, so the screen survives colour blindness and the grayscale figures
 *   printed in the thesis.
 */

import { MaterialCommunityIcons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { Card, Text, TouchableRipple, useTheme } from 'react-native-paper';

import { OUTCOME_BY_REASON, type LogEntry } from '../api/types';
import { REASON_TEXT, type AppTheme } from '../theme/theme';
import { formatTimestamp } from './format';

export function EventRow({
  entry,
  onPress,
}: {
  entry: LogEntry;
  onPress?: () => void;
}) {
  const theme = useTheme<AppTheme>();
  // An unrecognised status falls back to FAULT rather than to "expected": if
  // the backend reports something this build does not know, the honest
  // reading is that the system could not be interpreted, not that all is well.
  const outcome = OUTCOME_BY_REASON[entry.status] ?? 'FAULT';
  const style = theme.outcomes[outcome];
  const text = REASON_TEXT[entry.status] ?? {
    title: entry.status,
    description: 'Unrecognised status reported by the backend.',
  };

  return (
    <Card mode="contained" style={[styles.row, { backgroundColor: theme.colors.surface }]}>
      <TouchableRipple
        onPress={onPress}
        disabled={!onPress}
        accessibilityRole="button"
        accessibilityLabel={`${style.label}: ${text.title}, ${entry.camera_id}, ${formatTimestamp(
          entry.timestamp,
        )}`}
        borderless
      >
        <View style={styles.rowInner}>
          <View style={[styles.badge, { backgroundColor: style.container }]}>
            <MaterialCommunityIcons
              name={style.icon as never}
              size={22}
              color={style.onContainer}
            />
            <Text variant="labelSmall" style={{ color: style.onContainer, fontWeight: '700' }}>
              {style.label}
            </Text>
          </View>

          <View style={styles.rowBody}>
            <Text variant="titleSmall" style={styles.rowTitle}>
              {text.title}
            </Text>
            <Text variant="bodySmall" style={styles.rowDescription}>
              {text.description}
            </Text>

            <View style={styles.metaLine}>
              <MaterialCommunityIcons
                name="video-outline"
                size={14}
                color={theme.colors.onSurfaceVariant}
              />
              <Text variant="bodySmall" style={styles.meta}>
                {entry.camera_id}
              </Text>
              <Text variant="bodySmall" style={styles.metaSeparator}>
                ·
              </Text>
              <Text variant="bodySmall" style={styles.meta}>
                {formatTimestamp(entry.timestamp)}
              </Text>
            </View>

            <View style={styles.metaLine}>
              <MaterialCommunityIcons
                name="account-outline"
                size={14}
                color={theme.colors.onSurfaceVariant}
              />
              <Text variant="bodySmall" style={styles.meta}>
                {entry.user_name ?? 'No person involved'}
              </Text>
              {entry.has_snapshot ? (
                <>
                  <Text variant="bodySmall" style={styles.metaSeparator}>
                    ·
                  </Text>
                  <MaterialCommunityIcons name="camera" size={14} color={style.accent} />
                  <Text variant="bodySmall" style={{ color: style.accent }}>
                    Photo kept
                  </Text>
                </>
              ) : null}
            </View>
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
  rowInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 12,
  },
  badge: {
    width: 68,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    gap: 4,
  },
  rowBody: {
    flex: 1,
    gap: 2,
  },
  rowTitle: {
    fontWeight: '700',
  },
  rowDescription: {
    opacity: 0.75,
    marginBottom: 4,
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
  metaSeparator: {
    opacity: 0.4,
  },
  chevron: {
    opacity: 0.5,
  },
});
