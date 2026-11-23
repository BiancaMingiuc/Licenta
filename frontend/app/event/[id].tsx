/**
 * One surveillance event, in full.
 *
 * Loaded from the backend BY ID rather than from data handed over by the
 * list. That is what makes the address work on its own: reloading the page on
 * web, or opening a shared link, still shows the event. Passing the row
 * through navigation would have been less code and would break on both.
 *
 * The screen also states the PHOTO POLICY (decision D2) per event, in words.
 * A privacy guarantee nobody can see is a guarantee nobody trusts, and "was a
 * photo of me kept?" is the question a monitored person actually has.
 */

import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useCallback, useEffect, useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import {
  ActivityIndicator,
  Button,
  Card,
  Dialog,
  Divider,
  Portal,
  Snackbar,
  Text,
  useTheme,
} from 'react-native-paper';

import { ApiError, logs as logsApi } from '../../src/api/client';
import { OUTCOME_BY_REASON, type LogEntry } from '../../src/api/types';
import { useAuth } from '../../src/auth/AuthContext';
import { formatRelative, formatTimestampLong } from '../../src/journal/format';
import { announceDeletedEntry } from '../../src/journal/journalSignals';
import { REASON_TEXT, type AppTheme } from '../../src/theme/theme';

/** Reasons that name an identified person. Mirrors the backend invariant. */
const REASONS_WITH_IDENTITY = ['KNOWN', 'UNEXPECTED_ZONE'];
/** Reasons for which decision D2 allows a photo to be retained. */
const REASONS_KEEPING_SNAPSHOT = ['INTRUDER', 'EMPTY_WHITELIST'];

/**
 * Explain, for this event, what happened to the photo and why.
 *
 * The reason is derived from the event's own status rather than stored as
 * text, so the explanation cannot drift away from the policy the backend
 * actually applies.
 */
function describePhotoPolicy(entry: LogEntry): { title: string; detail: string } {
  if (entry.has_snapshot) {
    return {
      title: 'A photo was kept',
      detail:
        'The person was not identified, so the image is the only record of who was ' +
        'present. It is stored on the hub and is readable by an administrator only.',
    };
  }
  if (REASONS_WITH_IDENTITY.includes(entry.status)) {
    return {
      title: 'No photo was kept',
      detail:
        'The person was identified, so their name is already in this entry. An extra ' +
        'image would be biometric data with no purpose, and is discarded even when the ' +
        'camera loop supplies one.',
    };
  }
  if (REASONS_KEEPING_SNAPSHOT.includes(entry.status)) {
    return {
      title: 'No photo available',
      detail:
        'This kind of event may retain a photo, but none was recorded for it — the ' +
        'entry was created without an image.',
    };
  }
  return {
    title: 'No photo was kept',
    detail: 'This is an equipment fault. No person was involved, so there is nothing to show.',
  };
}

function DetailRow({
  icon,
  label,
  value,
  hint,
}: {
  icon: string;
  label: string;
  value: string;
  hint?: string | null;
}) {
  const theme = useTheme<AppTheme>();
  return (
    <View style={styles.detailRow}>
      <MaterialCommunityIcons
        name={icon as never}
        size={20}
        color={theme.colors.onSurfaceVariant}
        style={styles.detailIcon}
      />
      <View style={styles.detailBody}>
        <Text variant="labelMedium" style={{ opacity: 0.6 }}>
          {label}
        </Text>
        <Text variant="bodyLarge" selectable>
          {value}
        </Text>
        {hint ? (
          <Text variant="bodySmall" style={{ opacity: 0.6 }}>
            {hint}
          </Text>
        ) : null}
      </View>
    </View>
  );
}

export default function EventDetailScreen() {
  const theme = useTheme<AppTheme>();
  const router = useRouter();
  const { role } = useAuth();
  const { id } = useLocalSearchParams<{ id: string }>();

  const [entry, setEntry] = useState<LogEntry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [confirmVisible, setConfirmVisible] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotFound(false);
    try {
      setEntry(await logsApi.get(id));
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) {
        setNotFound(true);
      } else {
        setError(
          caught instanceof ApiError ? caught.message : 'The event could not be loaded.',
        );
      }
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const goBack = useCallback(() => {
    // Opened directly from a URL there is no history to go back to, so the
    // journal is pushed instead of leaving the user on a dead screen.
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace('/(tabs)/journal');
    }
  }, [router]);

  const remove = useCallback(async () => {
    if (!id) {
      return;
    }
    setDeleting(true);
    try {
      await logsApi.remove(id);
      // Announced only AFTER the backend confirmed it: removing the row from
      // the list on an optimistic assumption would hide an entry that is
      // still in the journal.
      announceDeletedEntry(id);
      setConfirmVisible(false);
      goBack();
    } catch (caught) {
      setConfirmVisible(false);
      setNotice(
        caught instanceof ApiError ? caught.message : 'The event could not be deleted.',
      );
    } finally {
      setDeleting(false);
    }
  }, [goBack, id]);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" accessibilityLabel="Loading the event" />
      </View>
    );
  }

  if (notFound) {
    return (
      <View style={styles.center}>
        <MaterialCommunityIcons
          name="file-remove-outline"
          size={48}
          color={theme.colors.onSurfaceVariant}
        />
        <Text variant="titleMedium">This event is not available</Text>
        <Text variant="bodyMedium" style={styles.centeredText}>
          It was deleted, belongs to another hub, or is not one you are allowed to read.
        </Text>
        <Button mode="contained" onPress={goBack}>
          Back to the journal
        </Button>
      </View>
    );
  }

  if (error || !entry) {
    return (
      <View style={styles.center}>
        <MaterialCommunityIcons
          name="cloud-off-outline"
          size={48}
          color={theme.colors.onSurfaceVariant}
        />
        <Text variant="titleMedium">The event could not be loaded</Text>
        <Text variant="bodyMedium" style={styles.centeredText}>
          {error ?? 'Unknown error.'}
        </Text>
        <Button mode="contained" onPress={() => void load()}>
          Try again
        </Button>
      </View>
    );
  }

  const outcome = OUTCOME_BY_REASON[entry.status] ?? 'FAULT';
  const style = theme.outcomes[outcome];
  const text = REASON_TEXT[entry.status] ?? {
    title: entry.status,
    description: 'Unrecognised status reported by the backend.',
  };
  const photo = describePhotoPolicy(entry);
  const relative = formatRelative(entry.timestamp);

  return (
    <>
      <ScrollView
        contentContainerStyle={[
          styles.page,
          { maxWidth: theme.maxContentWidth, alignSelf: 'center', width: '100%' },
        ]}
      >
        <Card
          mode="contained"
          style={[styles.banner, { backgroundColor: style.container }]}
        >
          <View style={styles.bannerInner}>
            <MaterialCommunityIcons
              name={style.icon as never}
              size={34}
              color={style.onContainer}
            />
            <View style={styles.bannerText}>
              <Text
                variant="labelLarge"
                style={{ color: style.onContainer, fontWeight: '800' }}
              >
                {style.label.toUpperCase()}
              </Text>
              <Text
                variant="titleMedium"
                style={{ color: style.onContainer, fontWeight: '700' }}
              >
                {text.title}
              </Text>
              <Text variant="bodySmall" style={{ color: style.onContainer }}>
                {text.description}
              </Text>
            </View>
          </View>
        </Card>

        <Card mode="contained" style={[styles.card, { backgroundColor: theme.colors.surface }]}>
          <View style={styles.cardInner}>
            <DetailRow
              icon="clock-outline"
              label="When"
              value={formatTimestampLong(entry.timestamp)}
              hint={relative}
            />
            <Divider />
            <DetailRow icon="video-outline" label="Camera" value={entry.camera_id} />
            <Divider />
            <DetailRow
              icon="account-outline"
              label="Person"
              value={entry.user_name ?? 'No person involved'}
              hint={
                entry.user_id
                  ? null
                  : REASONS_WITH_IDENTITY.includes(entry.status)
                    ? null
                    : 'This kind of event never names a person.'
              }
            />
          </View>
        </Card>

        <Card mode="contained" style={[styles.card, { backgroundColor: theme.colors.surface }]}>
          <View style={styles.cardInner}>
            <DetailRow
              icon={entry.has_snapshot ? 'camera' : 'camera-off-outline'}
              label="Photo"
              value={photo.title}
              hint={photo.detail}
            />
          </View>
        </Card>

        <Card mode="contained" style={[styles.card, { backgroundColor: theme.colors.surface }]}>
          <View style={styles.cardInner}>
            <DetailRow
              icon="identifier"
              label="Event reference"
              value={entry.id}
              hint={`Recorded reason: ${entry.status} · Hub: ${entry.hub_id}`}
            />
          </View>
        </Card>

        {role === 'ADMIN' ? (
          <Button
            mode="outlined"
            icon="trash-can-outline"
            textColor={theme.outcomes.ALERT.accent}
            onPress={() => setConfirmVisible(true)}
            style={styles.deleteButton}
          >
            Delete this event
          </Button>
        ) : null}

        <Text variant="bodySmall" style={styles.footnote}>
          Entries are evidence: they are written by the hub and never edited. Deleting one
          is permanent.
        </Text>
      </ScrollView>

      <Portal>
        <Dialog visible={confirmVisible} onDismiss={() => setConfirmVisible(false)}>
          <Dialog.Title>Delete this event?</Dialog.Title>
          <Dialog.Content>
            <Text variant="bodyMedium">
              This removes one entry from the surveillance journal and cannot be undone.
              {entry.has_snapshot
                ? ' The photo file stays on the hub: deleting the entry does not delete the image.'
                : ''}
            </Text>
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setConfirmVisible(false)} disabled={deleting}>
              Keep it
            </Button>
            <Button
              onPress={() => void remove()}
              loading={deleting}
              disabled={deleting}
              textColor={theme.outcomes.ALERT.accent}
            >
              Delete
            </Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>

      <Snackbar visible={notice !== null} onDismiss={() => setNotice(null)} duration={6000}>
        {notice ?? ''}
      </Snackbar>
    </>
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
  page: {
    padding: 16,
    gap: 12,
  },
  banner: {
    borderRadius: 16,
  },
  bannerInner: {
    flexDirection: 'row',
    gap: 14,
    padding: 16,
    alignItems: 'center',
  },
  bannerText: {
    flex: 1,
    gap: 2,
  },
  card: {
    borderRadius: 16,
  },
  cardInner: {
    paddingVertical: 4,
  },
  detailRow: {
    flexDirection: 'row',
    gap: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  detailIcon: {
    marginTop: 2,
  },
  detailBody: {
    flex: 1,
    gap: 2,
  },
  deleteButton: {
    marginTop: 4,
  },
  footnote: {
    opacity: 0.55,
    textAlign: 'center',
    paddingHorizontal: 16,
    paddingTop: 4,
  },
});
