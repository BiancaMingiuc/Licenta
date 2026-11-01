/**
 * Surveillance journal.
 *
 * Presentation rules that follow from decision D3:
 *
 * - The row shows the ACTION level (expected / alert / fault) prominently and
 *   the precise reason as readable text. The backend stores the fine-grained
 *   reason because the thesis evaluation needs to count categories; a user
 *   needs to know what happened.
 * - Alerts and faults are visually distinct. A broken camera must not look
 *   like a break-in attempt.
 * - Meaning never depends on colour alone: every row carries an icon and a
 *   word, so the screen survives colour blindness and grayscale printing.
 *
 * NOTE: the data loading below is written with a plain effect on purpose --
 * the caching library is still an open decision. Everything the screen needs
 * goes through `load()`, so swapping in a query library touches this one
 * function and nothing else.
 */

import { MaterialCommunityIcons } from '@expo/vector-icons';
import React, { useCallback, useEffect, useState } from 'react';
import { FlatList, RefreshControl, StyleSheet, View } from 'react-native';
import { ActivityIndicator, Button, Card, Divider, Text, useTheme } from 'react-native-paper';

import { ApiError, logs as logsApi } from '../../src/api/client';
import { OUTCOME_BY_REASON, type LogEntry } from '../../src/api/types';
import { REASON_TEXT, type AppTheme } from '../../src/theme/theme';

const PAGE_SIZE = 50;

function formatTimestamp(value: string | null): string {
  if (!value) {
    return 'Unknown time';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function EventRow({ entry }: { entry: LogEntry }) {
  const theme = useTheme<AppTheme>();
  const outcome = OUTCOME_BY_REASON[entry.status] ?? 'FAULT';
  const style = theme.outcomes[outcome];
  const text = REASON_TEXT[entry.status] ?? {
    title: entry.status,
    description: 'Unrecognised status reported by the backend.',
  };

  return (
    <Card mode="contained" style={[styles.row, { backgroundColor: theme.colors.surface }]}>
      <View style={styles.rowInner}>
        <View
          style={[styles.badge, { backgroundColor: style.container }]}
          accessibilityLabel={`${style.label}: ${text.title}`}
        >
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
                <MaterialCommunityIcons
                  name="camera"
                  size={14}
                  color={style.accent}
                />
                <Text variant="bodySmall" style={{ color: style.accent }}>
                  Photo kept
                </Text>
              </>
            ) : null}
          </View>
        </View>
      </View>
    </Card>
  );
}

export default function JournalScreen() {
  const theme = useTheme<AppTheme>();
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (mode: 'initial' | 'refresh') => {
    if (mode === 'refresh') {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);
    try {
      const page = await logsApi.list({ limit: PAGE_SIZE, offset: 0 });
      setEntries(page.items);
      setTotal(page.total);
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : 'The journal could not be loaded.',
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load('initial');
  }, [load]);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" accessibilityLabel="Loading the journal" />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.center}>
        <MaterialCommunityIcons
          name="cloud-off-outline"
          size={48}
          color={theme.colors.onSurfaceVariant}
        />
        <Text variant="titleMedium">The journal could not be loaded</Text>
        <Text variant="bodyMedium" style={styles.centeredText}>
          {error}
        </Text>
        <Button mode="contained" onPress={() => void load('initial')}>
          Try again
        </Button>
      </View>
    );
  }

  return (
    <FlatList
      data={entries}
      keyExtractor={(item) => item.id}
      renderItem={({ item }) => <EventRow entry={item} />}
      contentContainerStyle={[
        styles.list,
        { maxWidth: theme.maxContentWidth, alignSelf: 'center', width: '100%' },
      ]}
      ItemSeparatorComponent={() => <View style={styles.separator} />}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={() => void load('refresh')} />
      }
      ListHeaderComponent={
        entries.length > 0 ? (
          <View style={styles.listHeader}>
            <Text variant="bodySmall" style={{ opacity: 0.7 }}>
              {total === 1 ? '1 event recorded' : `${total} events recorded`}
              {total > entries.length ? `, showing the latest ${entries.length}` : ''}
            </Text>
            <Divider style={styles.headerDivider} />
          </View>
        ) : null
      }
      ListEmptyComponent={
        <View style={styles.center}>
          <MaterialCommunityIcons
            name="shield-check-outline"
            size={48}
            color={theme.colors.onSurfaceVariant}
          />
          <Text variant="titleMedium">No events yet</Text>
          <Text variant="bodyMedium" style={styles.centeredText}>
            Detections will appear here as soon as the surveillance loop starts
            reporting.
          </Text>
        </View>
      }
    />
  );
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    padding: 32,
  },
  centeredText: {
    textAlign: 'center',
    opacity: 0.7,
  },
  list: {
    padding: 16,
    flexGrow: 1,
  },
  listHeader: {
    gap: 8,
    paddingBottom: 4,
  },
  headerDivider: {
    marginBottom: 4,
  },
  separator: {
    height: 10,
  },
  row: {
    borderRadius: 14,
    overflow: 'hidden',
  },
  rowInner: {
    flexDirection: 'row',
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
});
