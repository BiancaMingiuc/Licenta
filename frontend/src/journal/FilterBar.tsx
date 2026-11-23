/**
 * Journal filter bar.
 *
 * Three independent filters, each a chip that opens a menu: camera, detection
 * reason, time window. They combine, and all three are applied by the
 * backend.
 *
 * The reason menu lists the seven REASONS, grouped visually under the three
 * action levels. It deliberately does not offer "all alerts" as one choice:
 * the backend filters by a single reason, so such an option would have to be
 * faked on the client over an already-paginated page -- the exact dishonesty
 * these filters exist to avoid. The grouping gives the reader the action
 * level without promising a filter that does not exist.
 */

import { MaterialCommunityIcons } from '@expo/vector-icons';
import React, { useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { Chip, Divider, Menu, Text, useTheme } from 'react-native-paper';

import { OUTCOME_BY_REASON, type DetectionOutcome, type DetectionReason } from '../api/types';
import { REASON_TEXT, type AppTheme } from '../theme/theme';
import {
  DATE_PRESET_LABELS,
  EMPTY_FILTERS,
  countActiveFilters,
  type DatePreset,
  type JournalFilters,
} from './useJournal';

const DATE_PRESETS: DatePreset[] = ['all', 'today', '7d', '30d'];

/** Reasons in action order, so the menu reads alerts first. */
const REASONS_BY_OUTCOME: [DetectionOutcome, DetectionReason[]][] = [
  ['ALERT', ['INTRUDER', 'UNEXPECTED_ZONE', 'EMPTY_WHITELIST']],
  ['FAULT', ['CAMERA_UNKNOWN', 'CAMERA_DISABLED', 'DEGRADED']],
  ['KNOWN', ['KNOWN']],
];

export function FilterBar({
  filters,
  cameraOptions,
  onChange,
}: {
  filters: JournalFilters;
  cameraOptions: string[];
  onChange: (next: JournalFilters) => void;
}) {
  const theme = useTheme<AppTheme>();
  const [openMenu, setOpenMenu] = useState<'camera' | 'reason' | 'period' | null>(null);
  const activeCount = countActiveFilters(filters);

  const reasonChipLabel = filters.status
    ? REASON_TEXT[filters.status].title
    : 'Any outcome';
  const reasonChipColour = filters.status
    ? theme.outcomes[OUTCOME_BY_REASON[filters.status]].accent
    : undefined;

  return (
    <View style={styles.wrapper}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.row}
      >
        <Menu
          visible={openMenu === 'camera'}
          onDismiss={() => setOpenMenu(null)}
          anchor={
            <Chip
              icon="video-outline"
              selected={Boolean(filters.cameraId)}
              showSelectedCheck={false}
              onPress={() => setOpenMenu('camera')}
            >
              {filters.cameraId ?? 'All cameras'}
            </Chip>
          }
        >
          <Menu.Item
            title="All cameras"
            leadingIcon={filters.cameraId === null ? 'check' : undefined}
            onPress={() => {
              setOpenMenu(null);
              onChange({ ...filters, cameraId: null });
            }}
          />
          {cameraOptions.length > 0 ? <Divider /> : null}
          {cameraOptions.map((camera) => (
            <Menu.Item
              key={camera}
              title={camera}
              leadingIcon={filters.cameraId === camera ? 'check' : undefined}
              onPress={() => {
                setOpenMenu(null);
                onChange({ ...filters, cameraId: camera });
              }}
            />
          ))}
          {cameraOptions.length === 0 ? (
            <Text variant="bodySmall" style={styles.menuNote}>
              No camera has reported an event yet.
            </Text>
          ) : null}
        </Menu>

        <Menu
          visible={openMenu === 'reason'}
          onDismiss={() => setOpenMenu(null)}
          anchor={
            <Chip
              icon="filter-variant"
              selected={Boolean(filters.status)}
              showSelectedCheck={false}
              onPress={() => setOpenMenu('reason')}
              selectedColor={reasonChipColour}
            >
              {reasonChipLabel}
            </Chip>
          }
        >
          <Menu.Item
            title="Any outcome"
            leadingIcon={filters.status === null ? 'check' : undefined}
            onPress={() => {
              setOpenMenu(null);
              onChange({ ...filters, status: null });
            }}
          />
          {REASONS_BY_OUTCOME.map(([outcome, reasons]) => (
            <View key={outcome}>
              <Divider />
              <Text
                variant="labelSmall"
                style={[styles.groupHeading, { color: theme.outcomes[outcome].accent }]}
              >
                {theme.outcomes[outcome].label}
              </Text>
              {reasons.map((reason) => (
                <Menu.Item
                  key={reason}
                  title={REASON_TEXT[reason].title}
                  leadingIcon={
                    filters.status === reason ? 'check' : theme.outcomes[outcome].icon
                  }
                  onPress={() => {
                    setOpenMenu(null);
                    onChange({ ...filters, status: reason });
                  }}
                />
              ))}
            </View>
          ))}
        </Menu>

        <Menu
          visible={openMenu === 'period'}
          onDismiss={() => setOpenMenu(null)}
          anchor={
            <Chip
              icon="calendar-range"
              selected={filters.datePreset !== 'all'}
              showSelectedCheck={false}
              onPress={() => setOpenMenu('period')}
            >
              {DATE_PRESET_LABELS[filters.datePreset]}
            </Chip>
          }
        >
          {DATE_PRESETS.map((preset) => (
            <Menu.Item
              key={preset}
              title={DATE_PRESET_LABELS[preset]}
              leadingIcon={filters.datePreset === preset ? 'check' : undefined}
              onPress={() => {
                setOpenMenu(null);
                onChange({ ...filters, datePreset: preset });
              }}
            />
          ))}
        </Menu>

        {activeCount > 0 ? (
          <Chip
            icon="close"
            onPress={() => onChange(EMPTY_FILTERS)}
            accessibilityLabel="Clear all filters"
          >
            Clear
          </Chip>
        ) : null}
      </ScrollView>

      {activeCount > 0 ? (
        <View style={styles.activeNote}>
          <MaterialCommunityIcons
            name="information-outline"
            size={13}
            color={theme.colors.onSurfaceVariant}
          />
          <Text variant="bodySmall" style={{ opacity: 0.7 }}>
            {activeCount === 1 ? '1 filter active' : `${activeCount} filters active`} — the
            count below describes the filtered events only.
          </Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    gap: 6,
  },
  row: {
    flexDirection: 'row',
    gap: 8,
    paddingVertical: 4,
    paddingRight: 8,
  },
  groupHeading: {
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 2,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  menuNote: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    opacity: 0.7,
    maxWidth: 240,
  },
  activeNote: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingBottom: 2,
  },
});
