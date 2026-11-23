/**
 * One person: their state, their editable fields, their surveillance history,
 * and the two destructive actions.
 *
 * Loaded from its own id rather than from data handed over by the list, so
 * reloading the page on web -- or opening a link someone sent -- works. That
 * is the capability expo-router was chosen for, and it only holds if the
 * screen fetches for itself.
 *
 * Three refusals are left to the backend rather than reimplemented here:
 *
 * - **The last administrator** cannot be deleted or demoted. Deciding that
 *   client-side would need a count this screen does not reliably have, since
 *   another administrator may have been removed a second ago. The 409 and its
 *   message are shown as-is.
 * - **Email uniqueness** is a database index; a pre-check would be a race.
 * - **Role consequences** (clearing a password hash on demotion, deriving
 *   `has_app_access`) belong to the service layer and have one home.
 *
 * What IS warned about here is the case the backend cannot see as a problem:
 * editing your OWN account. Demoting yourself while another administrator
 * exists is a legal request, and it immediately invalidates your token --
 * every subsequent request answers 401 and the app signs you out. Legal, and
 * worth saying before the tap rather than after.
 */

import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import {
  ActivityIndicator,
  Banner,
  Button,
  Card,
  Dialog,
  Divider,
  Portal,
  Snackbar,
  Text,
  useTheme,
} from 'react-native-paper';

import { ApiError, people as peopleApi } from '../../src/api/client';
import type { PersonDetail } from '../../src/api/types';
import { useAuth } from '../../src/auth/AuthContext';
import { useCameras } from '../../src/cameras/useCameras';
import { EventRow } from '../../src/journal/EventRow';
import {
  PersonForm,
  diffPerson,
  personToFormValues,
  type PersonFormValues,
} from '../../src/people/PersonForm';
import { ROLES, demotionClearsPassword, roleLabel } from '../../src/people/roles';
import { deletePerson, updatePerson } from '../../src/people/usePeople';
import type { AppTheme } from '../../src/theme/theme';

/** Which destructive action the confirmation dialog is asking about. */
type Confirming = 'none' | 'delete' | 'clearFace';

export default function PersonDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const theme = useTheme<AppTheme>();
  const router = useRouter();
  const { user } = useAuth();
  const cameras = useCameras();

  const [person, setPerson] = useState<PersonDetail | null>(null);
  const [values, setValues] = useState<PersonFormValues | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirming, setConfirming] = useState<Confirming>('none');
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) {
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      const loaded = await peopleApi.get(id);
      setPerson(loaded);
      setValues(personToFormValues(loaded));
    } catch (caught) {
      setLoadError(
        caught instanceof ApiError ? caught.message : 'This person could not be loaded.',
      );
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const changes = useMemo(
    () => (person && values ? diffPerson(person, values) : {}),
    [person, values],
  );
  const unchanged = Object.keys(changes).length === 0;

  const isSelf = Boolean(person && user && person.id === user.id);
  const selfDemotion =
    isSelf && values ? demotionClearsPassword(person!.role, values.role) : false;
  const selfRoleChange = isSelf && values ? values.role !== person!.role : false;

  const save = async () => {
    if (!person || !values || unchanged) {
      return;
    }
    setSubmitting(true);
    setSaveError(null);
    try {
      await updatePerson(person.id, changes);
      // Reloaded rather than patched from the response: the backend derives
      // `has_app_access` and may clear the password hash, so the authoritative
      // state after a role change is the one it returns on a fresh read.
      await load();
      setNotice('Changes saved.');
    } catch (caught) {
      setSaveError(caught instanceof ApiError ? caught.message : 'The changes were not saved.');
    } finally {
      setSubmitting(false);
    }
  };

  const clearFace = async () => {
    if (!person) {
      return;
    }
    setConfirming('none');
    setSubmitting(true);
    setSaveError(null);
    try {
      // null, not an empty array: the backend distinguishes "not sent" from
      // "sent as null", and only null erases the stored vector.
      await updatePerson(person.id, { embedding: null });
      await load();
      setNotice('The enrolled face was deleted. The recorded events are unchanged.');
    } catch (caught) {
      setSaveError(
        caught instanceof ApiError ? caught.message : 'The face could not be deleted.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async () => {
    if (!person) {
      return;
    }
    setConfirming('none');
    setSubmitting(true);
    setSaveError(null);
    try {
      await deletePerson(person.id);
      router.replace('/(tabs)/people');
    } catch (caught) {
      setSaveError(
        caught instanceof ApiError ? caught.message : 'The person could not be deleted.',
      );
      setSubmitting(false);
    }
  };

  if (loading && !person) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" accessibilityLabel="Loading the person" />
      </View>
    );
  }

  if (loadError || !person || !values) {
    return (
      <View style={styles.center}>
        <MaterialCommunityIcons
          name="account-question-outline"
          size={48}
          color={theme.colors.onSurfaceVariant}
        />
        <Text variant="titleMedium">This person could not be loaded</Text>
        <Text variant="bodyMedium" style={styles.centeredText}>
          {loadError ?? 'No data was returned for this id.'}
        </Text>
        <Button mode="contained" onPress={() => void load()}>
          Try again
        </Button>
        <Button onPress={() => router.replace('/(tabs)/people')}>Back to the list</Button>
      </View>
    );
  }

  const role = ROLES[person.role];
  const enrolled = person.has_embedding;
  const enrolmentStyle = enrolled ? theme.outcomes.KNOWN : theme.outcomes.FAULT;

  return (
    <>
      <ScrollView
        contentContainerStyle={[
          styles.content,
          { maxWidth: theme.maxContentWidth, alignSelf: 'center', width: '100%' },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        <Card mode="contained" style={{ backgroundColor: theme.colors.surface }}>
          <Card.Content style={styles.headerCard}>
            <Text variant="headlineSmall" style={styles.name}>
              {person.name}
            </Text>

            <View style={styles.headerLine}>
              <MaterialCommunityIcons
                name={role?.icon as never}
                size={18}
                color={theme.colors.onSurfaceVariant}
              />
              <Text variant="bodyMedium" style={styles.headerMeta}>
                {roleLabel(person.role)}
              </Text>
              <Text style={styles.separator}>·</Text>
              <Text variant="bodyMedium" style={styles.headerMeta}>
                {person.has_app_access ? 'Can sign in' : 'No application access'}
              </Text>
            </View>

            <View style={[styles.enrolment, { backgroundColor: enrolmentStyle.container }]}>
              <MaterialCommunityIcons
                name="face-recognition"
                size={20}
                color={enrolmentStyle.onContainer}
              />
              <Text
                variant="bodySmall"
                style={{ color: enrolmentStyle.onContainer, flex: 1 }}
              >
                {enrolled
                  ? 'A face is enrolled, so the cameras can recognise this person.'
                  : 'No face is enrolled. The cameras have nothing to match against, so this ' +
                    'person is recorded as an intruder when they appear.'}
              </Text>
            </View>

            {isSelf ? (
              <Text variant="bodySmall" style={styles.selfNote}>
                This is your own account.
              </Text>
            ) : null}
          </Card.Content>
        </Card>

        {selfRoleChange ? (
          <Banner visible icon="account-alert" style={styles.banner}>
            {selfDemotion
              ? 'You are removing your own application access. Saving this signs you out ' +
                'immediately and you will not be able to sign back in.'
              : 'You are changing your own role. Saving this re-evaluates your permissions ' +
                'on the next request.'}
          </Banner>
        ) : null}

        <Text variant="titleMedium" style={styles.sectionHeading}>
          Details
        </Text>
        <Card mode="contained" style={{ backgroundColor: theme.colors.surface }}>
          <Card.Content>
            <PersonForm
              mode="edit"
              values={values}
              onChange={setValues}
              originalRole={person.role}
              cameras={cameras.cameras}
              camerasLoading={cameras.loading}
              camerasError={cameras.error}
              submitting={submitting}
              error={saveError}
              submitLabel="Save changes"
              onSubmit={() => void save()}
              unchanged={unchanged}
            />
          </Card.Content>
        </Card>

        <Text variant="titleMedium" style={styles.sectionHeading}>
          Surveillance history
        </Text>
        {person.logs.length === 0 ? (
          <Card mode="contained" style={{ backgroundColor: theme.colors.surface }}>
            <Card.Content>
              <Text variant="bodyMedium" style={styles.quiet}>
                This person has not been recorded by any camera yet.
                {enrolled
                  ? ''
                  : ' That is expected while no face is enrolled: a detection cannot be ' +
                    'attributed to them.'}
              </Text>
            </Card.Content>
          </Card>
        ) : (
          <View style={styles.history}>
            <Text variant="bodySmall" style={styles.quiet}>
              {person.logs.length === 1 ? '1 event' : `${person.logs.length} events`} attributed
              to this person.
            </Text>
            {person.logs.map((entry) => (
              <EventRow
                key={entry.id}
                entry={entry}
                onPress={() => router.push(`/event/${entry.id}`)}
              />
            ))}
          </View>
        )}

        <Divider style={styles.dangerDivider} />

        <Text variant="titleMedium" style={[styles.sectionHeading, { color: theme.colors.error }]}>
          Irreversible actions
        </Text>

        {enrolled ? (
          <Button
            mode="outlined"
            icon="face-recognition"
            textColor={theme.colors.error}
            disabled={submitting}
            onPress={() => setConfirming('clearFace')}
            style={styles.dangerButton}
          >
            Delete the enrolled face
          </Button>
        ) : null}

        <Button
          mode="outlined"
          icon="account-remove"
          textColor={theme.colors.error}
          disabled={submitting}
          onPress={() => setConfirming('delete')}
          style={styles.dangerButton}
        >
          Delete this person
        </Button>

        <Text variant="bodySmall" style={styles.dangerNote}>
          Deleting a person removes them from the hub immediately: the cameras stop recognising
          them on the next frame. Their recorded events stay in the journal, because removing
          them would destroy the audit trail.
        </Text>
      </ScrollView>

      <Portal>
        <Dialog visible={confirming !== 'none'} onDismiss={() => setConfirming('none')}>
          <Dialog.Title>
            {confirming === 'delete' ? 'Delete this person?' : 'Delete the enrolled face?'}
          </Dialog.Title>
          <Dialog.Content>
            <Text variant="bodyMedium">
              {confirming === 'delete'
                ? `${person.name} will be removed from the hub and will no longer be ` +
                  'recognised by any camera. Their events stay in the journal. This cannot ' +
                  'be undone.'
                : `The face vector stored for ${person.name} will be erased. They stay in ` +
                  'the hub, but the cameras will report them as an intruder until a face is ' +
                  'enrolled again. This cannot be undone.'}
            </Text>
            {confirming === 'delete' && isSelf ? (
              <Text variant="bodyMedium" style={[styles.dialogWarning, { color: theme.colors.error }]}>
                This is your own account. You will be signed out and will not be able to sign
                back in.
              </Text>
            ) : null}
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setConfirming('none')}>Cancel</Button>
            <Button
              textColor={theme.colors.error}
              onPress={() => void (confirming === 'delete' ? remove() : clearFace())}
            >
              {confirming === 'delete' ? 'Delete person' : 'Delete face'}
            </Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>

      <Snackbar visible={notice !== null} onDismiss={() => setNotice(null)} duration={4000}>
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
  content: {
    padding: 16,
    paddingBottom: 56,
    gap: 12,
  },
  headerCard: {
    gap: 8,
  },
  name: {
    fontWeight: '700',
  },
  headerLine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    flexWrap: 'wrap',
  },
  headerMeta: {
    opacity: 0.75,
  },
  separator: {
    opacity: 0.4,
  },
  enrolment: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    padding: 12,
    borderRadius: 12,
    marginTop: 4,
  },
  selfNote: {
    opacity: 0.6,
    fontStyle: 'italic',
  },
  banner: {
    borderRadius: 12,
  },
  sectionHeading: {
    fontWeight: '700',
    marginTop: 8,
  },
  history: {
    gap: 10,
  },
  quiet: {
    opacity: 0.7,
  },
  dangerDivider: {
    marginTop: 16,
  },
  dangerButton: {
    borderRadius: 12,
  },
  dangerNote: {
    opacity: 0.7,
  },
  dialogWarning: {
    marginTop: 12,
    fontWeight: '700',
  },
});
