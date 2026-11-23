/**
 * The hub's people.
 *
 * As on the journal, the two empty states are told apart: "nobody matches
 * these filters" offers a way out, while "nobody is enrolled" explains what
 * that means for the system. Conflating them would read as an empty hub when
 * it is only an empty search.
 *
 * The screen holds no data logic. Loading, filtering and invalidation live in
 * `usePeople`, so adopting a server-state library later replaces that file
 * and leaves this layout untouched.
 */

import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React from 'react';
import { FlatList, RefreshControl, StyleSheet, View } from 'react-native';
import {
  ActivityIndicator,
  Button,
  Chip,
  Divider,
  FAB,
  Searchbar,
  Text,
  useTheme,
} from 'react-native-paper';

import type { UserRole } from '../../src/api/types';
import { PersonRow } from '../../src/people/PersonRow';
import { ROLES, ROLE_ORDER } from '../../src/people/roles';
import {
  EMPTY_PEOPLE_FILTERS,
  countActivePeopleFilters,
  usePeople,
} from '../../src/people/usePeople';
import type { AppTheme } from '../../src/theme/theme';

export default function PeopleScreen() {
  const theme = useTheme<AppTheme>();
  const router = useRouter();
  const people = usePeople();
  const filtered = countActivePeopleFilters(people.filters) > 0;

  const missingFace = people.visible.filter((person) => !person.has_embedding).length;

  const header = (
    <View style={styles.header}>
      <Searchbar
        placeholder="Search by name or email"
        value={people.filters.search}
        onChangeText={(search) => people.setFilters({ ...people.filters, search })}
        style={styles.search}
        inputStyle={styles.searchInput}
      />

      <View style={styles.chipRow}>
        {ROLE_ORDER.map((role: UserRole) => {
          const selected = people.filters.role === role;
          return (
            <Chip
              key={role}
              mode={selected ? 'flat' : 'outlined'}
              selected={selected}
              showSelectedCheck={false}
              icon={ROLES[role].icon}
              // Tapping the active chip clears it, so the filter never
              // becomes a one-way door that needs the reset button.
              onPress={() =>
                people.setFilters({ ...people.filters, role: selected ? null : role })
              }
            >
              {ROLES[role].label}
            </Chip>
          );
        })}
        <Chip
          mode={people.filters.enrolment === 'missing' ? 'flat' : 'outlined'}
          selected={people.filters.enrolment === 'missing'}
          showSelectedCheck={false}
          icon="alert-outline"
          onPress={() =>
            people.setFilters({
              ...people.filters,
              enrolment: people.filters.enrolment === 'missing' ? 'all' : 'missing',
            })
          }
        >
          No face enrolled
        </Chip>
      </View>

      {people.visible.length > 0 ? (
        <>
          <Text variant="bodySmall" style={styles.countLine}>
            {people.visible.length === people.total
              ? `${people.total} ${people.total === 1 ? 'person' : 'people'}`
              : `${people.visible.length} of ${people.total}`}
            {missingFace > 0
              ? ` · ${missingFace} without an enrolled face`
              : ''}
          </Text>
          <Divider style={styles.headerDivider} />
        </>
      ) : null}
    </View>
  );

  if (people.loading && people.total === 0) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" accessibilityLabel="Loading the people" />
      </View>
    );
  }

  if (people.error && people.total === 0) {
    return (
      <View style={styles.center}>
        <MaterialCommunityIcons
          name="cloud-off-outline"
          size={48}
          color={theme.colors.onSurfaceVariant}
        />
        <Text variant="titleMedium">The people could not be loaded</Text>
        <Text variant="bodyMedium" style={styles.centeredText}>
          {people.error}
        </Text>
        <Button mode="contained" onPress={people.refresh}>
          Try again
        </Button>
      </View>
    );
  }

  return (
    <View style={styles.screen}>
      <FlatList
        data={people.visible}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <PersonRow person={item} onPress={() => router.push(`/person/${item.id}`)} />
        )}
        contentContainerStyle={[
          styles.list,
          { maxWidth: theme.maxContentWidth, alignSelf: 'center', width: '100%' },
        ]}
        ItemSeparatorComponent={() => <View style={styles.separator} />}
        refreshControl={
          <RefreshControl refreshing={people.refreshing} onRefresh={people.refresh} />
        }
        ListHeaderComponent={header}
        ListEmptyComponent={
          filtered ? (
            <View style={styles.center}>
              <MaterialCommunityIcons
                name="filter-remove-outline"
                size={48}
                color={theme.colors.onSurfaceVariant}
              />
              <Text variant="titleMedium">Nobody matches these filters</Text>
              <Text variant="bodyMedium" style={styles.centeredText}>
                The hub has {people.total} {people.total === 1 ? 'person' : 'people'}, but none
                of them fall inside the current selection.
              </Text>
              <Button
                mode="contained"
                onPress={() => people.setFilters(EMPTY_PEOPLE_FILTERS)}
              >
                Clear filters
              </Button>
            </View>
          ) : (
            <View style={styles.center}>
              <MaterialCommunityIcons
                name="account-plus-outline"
                size={48}
                color={theme.colors.onSurfaceVariant}
              />
              <Text variant="titleMedium">Nobody is enrolled yet</Text>
              <Text variant="bodyMedium" style={styles.centeredText}>
                With an empty list the cameras have nobody to recognise, so every person they
                see is reported as unknown.
              </Text>
              <Button mode="contained" onPress={() => router.push('/person/new')}>
                Add the first person
              </Button>
            </View>
          )
        }
      />

      {people.total > 0 ? (
        <FAB
          icon="account-plus"
          label="Add person"
          onPress={() => router.push('/person/new')}
          style={styles.fab}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
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
    // Clears the floating button, which would otherwise cover the last row.
    paddingBottom: 96,
  },
  header: {
    gap: 10,
    paddingBottom: 4,
  },
  search: {
    borderRadius: 12,
  },
  searchInput: {
    minHeight: 0,
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  countLine: {
    opacity: 0.7,
    paddingTop: 2,
  },
  headerDivider: {
    marginTop: 6,
  },
  separator: {
    height: 10,
  },
  fab: {
    position: 'absolute',
    right: 16,
    bottom: 16,
  },
});
