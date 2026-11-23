/**
 * Surveillance journal.
 *
 * The screen itself holds no data logic: filters, paging and request ordering
 * live in `useJournal`, so adopting a caching library later replaces that one
 * file and leaves this layout untouched.
 *
 * Two states are deliberately told apart, because conflating them is how a
 * log screen misleads its reader:
 *
 * - **Empty under filters** -- events exist, none match. Offers a way out.
 * - **Genuinely empty** -- nothing has been recorded at all.
 *
 * Showing "no events" for the first case would read as "nothing happened",
 * which on a surveillance journal is a false statement.
 */

import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React from 'react';
import { FlatList, RefreshControl, StyleSheet, View } from 'react-native';
import { ActivityIndicator, Button, Divider, Text, useTheme } from 'react-native-paper';

import { EventRow } from '../../src/journal/EventRow';
import { FilterBar } from '../../src/journal/FilterBar';
import { EMPTY_FILTERS, countActiveFilters, useJournal } from '../../src/journal/useJournal';
import type { AppTheme } from '../../src/theme/theme';

export default function JournalScreen() {
  const theme = useTheme<AppTheme>();
  const router = useRouter();
  const journal = useJournal();
  const filtered = countActiveFilters(journal.filters) > 0;

  const header = (
    <View style={styles.header}>
      <FilterBar
        filters={journal.filters}
        cameraOptions={journal.cameraOptions}
        onChange={journal.setFilters}
      />
      {journal.entries.length > 0 ? (
        <>
          <Text variant="bodySmall" style={styles.countLine}>
            {journal.total === 1 ? '1 event' : `${journal.total} events`}
            {journal.total > journal.entries.length
              ? `, showing the latest ${journal.entries.length}`
              : ''}
          </Text>
          <Divider style={styles.headerDivider} />
        </>
      ) : null}
    </View>
  );

  const footer = (() => {
    if (journal.loadingMore) {
      return (
        <View style={styles.footer}>
          <ActivityIndicator accessibilityLabel="Loading more events" />
        </View>
      );
    }
    if (journal.entries.length === 0) {
      return null;
    }
    if (journal.hasMore) {
      // An explicit button beside the automatic scroll trigger: on the web
      // layout the list may not be tall enough to scroll at all, so
      // `onEndReached` would never fire and the remaining pages would be
      // unreachable.
      return (
        <View style={styles.footer}>
          <Button mode="outlined" onPress={journal.loadMore}>
            Load more
          </Button>
        </View>
      );
    }
    return (
      <View style={styles.footer}>
        <Text variant="bodySmall" style={{ opacity: 0.6 }}>
          End of the journal.
        </Text>
      </View>
    );
  })();

  if (journal.loading && journal.entries.length === 0) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" accessibilityLabel="Loading the journal" />
      </View>
    );
  }

  if (journal.error && journal.entries.length === 0) {
    return (
      <View style={styles.center}>
        <MaterialCommunityIcons
          name="cloud-off-outline"
          size={48}
          color={theme.colors.onSurfaceVariant}
        />
        <Text variant="titleMedium">The journal could not be loaded</Text>
        <Text variant="bodyMedium" style={styles.centeredText}>
          {journal.error}
        </Text>
        <Button mode="contained" onPress={journal.refresh}>
          Try again
        </Button>
      </View>
    );
  }

  return (
    <FlatList
      data={journal.entries}
      keyExtractor={(item) => item.id}
      renderItem={({ item }) => (
        <EventRow entry={item} onPress={() => router.push(`/event/${item.id}`)} />
      )}
      contentContainerStyle={[
        styles.list,
        { maxWidth: theme.maxContentWidth, alignSelf: 'center', width: '100%' },
      ]}
      ItemSeparatorComponent={() => <View style={styles.separator} />}
      refreshControl={
        <RefreshControl refreshing={journal.refreshing} onRefresh={journal.refresh} />
      }
      onEndReached={journal.loadMore}
      onEndReachedThreshold={0.4}
      ListHeaderComponent={header}
      ListFooterComponent={footer}
      ListEmptyComponent={
        filtered ? (
          <View style={styles.center}>
            <MaterialCommunityIcons
              name="filter-remove-outline"
              size={48}
              color={theme.colors.onSurfaceVariant}
            />
            <Text variant="titleMedium">No events match these filters</Text>
            <Text variant="bodyMedium" style={styles.centeredText}>
              Events exist in the journal, but none of them fall inside the current
              selection.
            </Text>
            <Button mode="contained" onPress={() => journal.setFilters(EMPTY_FILTERS)}>
              Clear filters
            </Button>
          </View>
        ) : (
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
        )
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
  header: {
    gap: 4,
    paddingBottom: 4,
  },
  countLine: {
    opacity: 0.7,
    paddingTop: 2,
  },
  headerDivider: {
    marginTop: 6,
  },
  footer: {
    paddingTop: 16,
    alignItems: 'center',
  },
  separator: {
    height: 10,
  },
});
