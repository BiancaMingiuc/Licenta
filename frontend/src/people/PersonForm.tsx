/**
 * The create/edit form for a person, shared by both screens.
 *
 * One form rather than two, because the rules are the same and a second copy
 * is how the edit screen ends up accepting something the create screen
 * refuses.
 *
 * The form mirrors four backend rules so the user sees them as fields and
 * warnings instead of discovering them as a 422 after submitting:
 *
 * 1. ADMIN and APP_USER authenticate, so they require an email and a password.
 * 2. MONITORED cannot have a password at all.
 * 3. Promoting out of MONITORED requires a NEW password: the person never had
 *    a hash, so there is nothing for the backend to keep.
 * 4. Demoting to MONITORED destroys the password: it cannot be restored by
 *    promoting the person again.
 *
 * Zones are selected from the hub's registered cameras rather than typed. The
 * backend rejects an unregistered id with 422, but the real reason is quieter
 * than a rejection: a typo that somehow passed would create a permission that
 * never matches, and the person would keep raising alerts in a zone they were
 * supposed to be expected in.
 *
 * Enrolling a FACE is not part of this form. It cannot be: the backend has no
 * route that accepts an image, because there is no model to turn one into an
 * embedding yet (phase 3). Offering a button that cannot work would be worse
 * than stating the gap, so the form states it.
 */

import { MaterialCommunityIcons } from '@expo/vector-icons';
import React, { useMemo, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import {
  Banner,
  Button,
  Chip,
  Divider,
  HelperText,
  SegmentedButtons,
  Text,
  TextInput,
  useTheme,
} from 'react-native-paper';

import type { Camera, Person, PersonUpdate, UserRole } from '../api/types';
import type { AppTheme } from '../theme/theme';
import {
  ROLES,
  ROLE_ORDER,
  demotionClearsPassword,
  promotionNeedsPassword,
  roleNeedsCredentials,
} from './roles';

export interface PersonFormValues {
  name: string;
  role: UserRole;
  email: string;
  /** Empty means "unchanged" when editing, and "not supplied" when creating. */
  password: string;
  allowedCameras: string[];
}

export function emptyPersonFormValues(defaultCamera?: string): PersonFormValues {
  return {
    name: '',
    role: 'MONITORED',
    email: '',
    password: '',
    allowedCameras: defaultCamera ? [defaultCamera] : [],
  };
}

export function personToFormValues(person: Person): PersonFormValues {
  return {
    name: person.name,
    role: person.role,
    email: person.email ?? '',
    password: '',
    allowedCameras: [...person.allowed_cameras],
  };
}

/** Short segment labels: three long ones do not fit a phone's width. */
const ROLE_SEGMENT_LABEL: Record<UserRole, string> = {
  ADMIN: 'Admin',
  APP_USER: 'App user',
  MONITORED: 'Monitored',
};

function sameSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) {
    return false;
  }
  const sortedA = [...a].sort();
  const sortedB = [...b].sort();
  return sortedA.every((value, index) => value === sortedB[index]);
}

/**
 * The fields that actually changed, as the update payload.
 *
 * Only changed fields are sent, which matches the backend's
 * `model_dump(exclude_unset=True)`: a field that is absent is left alone,
 * while a field sent as null is cleared deliberately. Sending everything
 * would work but would re-hash the password on every save and would make
 * "clear the email" indistinguishable from "leave the email".
 */
export function diffPerson(person: Person, values: PersonFormValues): PersonUpdate {
  const changes: PersonUpdate = {};

  const name = values.name.trim();
  if (name !== person.name) {
    changes.name = name;
  }
  if (values.role !== person.role) {
    changes.role = values.role;
  }

  const email = values.email.trim();
  const currentEmail = person.email ?? '';
  if (email !== currentEmail) {
    // An emptied field is sent as null, not as "": null is how the backend
    // clears a column, whereas "" would be stored as an empty email.
    changes.email = email === '' ? null : email;
  }

  if (!sameSet(values.allowedCameras, person.allowed_cameras)) {
    changes.allowed_cameras = [...values.allowedCameras];
  }

  if (values.password) {
    changes.password = values.password;
  }

  return changes;
}

export interface PersonFormProps {
  mode: 'create' | 'edit';
  values: PersonFormValues;
  onChange: (next: PersonFormValues) => void;
  /** The role the person had before any change. Equals `values.role` on create. */
  originalRole: UserRole;
  cameras: Camera[];
  camerasLoading: boolean;
  camerasError: string | null;
  submitting: boolean;
  /** Message from the backend, shown verbatim: it carries the real rule. */
  error: string | null;
  submitLabel: string;
  onSubmit: () => void;
  /** True when editing and nothing has been modified yet. */
  unchanged?: boolean;
}

export function PersonForm({
  mode,
  values,
  onChange,
  originalRole,
  cameras,
  camerasLoading,
  camerasError,
  submitting,
  error,
  submitLabel,
  onSubmit,
  unchanged = false,
}: PersonFormProps) {
  const theme = useTheme<AppTheme>();
  const [touched, setTouched] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const needsCredentials = roleNeedsCredentials(values.role);
  const passwordMandatory =
    needsCredentials && (mode === 'create' || promotionNeedsPassword(originalRole, values.role));
  const willClearPassword = mode === 'edit' && demotionClearsPassword(originalRole, values.role);

  const problems = useMemo(() => {
    const found: Partial<Record<keyof PersonFormValues, string>> = {};
    if (!values.name.trim()) {
      found.name = 'A name is required.';
    }
    if (needsCredentials && !values.email.trim()) {
      found.email = `${ROLES[values.role].label} signs in by email, so an email is required.`;
    }
    if (passwordMandatory && !values.password) {
      found.password =
        mode === 'create'
          ? 'This role signs in, so a password is required.'
          : 'This person had no application access, so promoting them needs a new password.';
    }
    if (!needsCredentials && values.password) {
      found.password = 'A monitored person cannot have a password. Clear this field.';
    }
    return found;
  }, [mode, needsCredentials, passwordMandatory, values]);

  const blocked = Object.keys(problems).length > 0;

  const toggleCamera = (cameraId: string) => {
    const selected = values.allowedCameras.includes(cameraId);
    onChange({
      ...values,
      allowedCameras: selected
        ? values.allowedCameras.filter((id) => id !== cameraId)
        : [...values.allowedCameras, cameraId],
    });
  };

  const handleSubmit = () => {
    setTouched(true);
    if (!blocked) {
      onSubmit();
    }
  };

  const show = (field: keyof PersonFormValues) => (touched ? problems[field] : undefined);

  return (
    <View style={styles.form}>
      {error ? (
        <Banner visible icon="alert-circle" style={styles.banner}>
          {error}
        </Banner>
      ) : null}

      <TextInput
        mode="outlined"
        label="Full name"
        value={values.name}
        onChangeText={(name) => onChange({ ...values, name })}
        autoCapitalize="words"
        error={Boolean(show('name'))}
        disabled={submitting}
      />
      {show('name') ? <HelperText type="error">{problems.name}</HelperText> : null}

      <Divider style={styles.divider} />

      <Text variant="labelLarge" style={styles.sectionTitle}>
        Role
      </Text>
      <SegmentedButtons
        value={values.role}
        onValueChange={(role) => onChange({ ...values, role: role as UserRole })}
        buttons={ROLE_ORDER.map((role) => ({
          value: role,
          label: ROLE_SEGMENT_LABEL[role],
          icon: ROLES[role].icon,
          disabled: submitting,
        }))}
      />

      <View
        style={[styles.roleCard, { backgroundColor: theme.colors.surfaceVariant }]}
        accessibilityLabel={`${ROLES[values.role].label}: ${ROLES[values.role].summary}`}
      >
        <Text variant="titleSmall" style={styles.roleTitle}>
          {ROLES[values.role].label}
        </Text>
        <Text variant="bodySmall" style={styles.roleSummary}>
          {ROLES[values.role].summary}
        </Text>
        {ROLES[values.role].capabilities.map((line) => (
          <View key={line} style={styles.capability}>
            <MaterialCommunityIcons
              name="circle-small"
              size={18}
              color={theme.colors.onSurfaceVariant}
            />
            <Text variant="bodySmall" style={styles.capabilityText}>
              {line}
            </Text>
          </View>
        ))}
      </View>

      {willClearPassword ? (
        <Banner visible icon="key-remove" style={styles.banner}>
          Demoting this person deletes their password. They will not be able to sign in, and
          promoting them again later will require setting a new one.
        </Banner>
      ) : null}

      <Divider style={styles.divider} />

      <TextInput
        mode="outlined"
        label={needsCredentials ? 'Email (required to sign in)' : 'Email (optional)'}
        value={values.email}
        onChangeText={(email) => onChange({ ...values, email })}
        autoCapitalize="none"
        keyboardType="email-address"
        error={Boolean(show('email'))}
        disabled={submitting}
      />
      {show('email') ? (
        <HelperText type="error">{problems.email}</HelperText>
      ) : (
        <HelperText type="info">
          {needsCredentials
            ? 'This is the identity used to authenticate.'
            : 'A monitored person does not sign in, so an email is only a contact detail.'}
        </HelperText>
      )}

      {needsCredentials ? (
        <>
          <TextInput
            mode="outlined"
            label={passwordMandatory ? 'Password' : 'New password (leave empty to keep)'}
            value={values.password}
            onChangeText={(password) => onChange({ ...values, password })}
            autoCapitalize="none"
            secureTextEntry={!showPassword}
            right={
              <TextInput.Icon
                icon={showPassword ? 'eye-off' : 'eye'}
                onPress={() => setShowPassword((current) => !current)}
                // The field is typed by an administrator for someone else, so
                // being able to read it back prevents handing over a password
                // that was mistyped and is now impossible to recover.
                accessibilityLabel={showPassword ? 'Hide password' : 'Show password'}
              />
            }
            error={Boolean(show('password'))}
            disabled={submitting}
          />
          {show('password') ? (
            <HelperText type="error">{problems.password}</HelperText>
          ) : (
            <HelperText type="info">
              At least 8 characters. Stored only as a bcrypt hash, never in readable form.
            </HelperText>
          )}
        </>
      ) : null}

      <Divider style={styles.divider} />

      <Text variant="labelLarge" style={styles.sectionTitle}>
        Allowed zones
      </Text>
      <Text variant="bodySmall" style={styles.sectionHint}>
        The cameras where this person is expected. Recognised on any other camera, they are
        recorded as “known person, unexpected zone” and raise an alert.
      </Text>

      {camerasError ? (
        <HelperText type="error">{camerasError}</HelperText>
      ) : camerasLoading ? (
        <HelperText type="info">Loading the hub&apos;s cameras…</HelperText>
      ) : cameras.length === 0 ? (
        <HelperText type="error">
          This hub has no registered camera, so no zone can be granted. Register one first.
        </HelperText>
      ) : (
        <View style={styles.chips}>
          {cameras.map((camera) => {
            const selected = values.allowedCameras.includes(camera.camera_id);
            return (
              <Chip
                key={camera.camera_id}
                mode={selected ? 'flat' : 'outlined'}
                selected={selected}
                showSelectedCheck
                onPress={() => toggleCamera(camera.camera_id)}
                disabled={submitting}
                icon={camera.enabled ? 'video' : 'video-off'}
                accessibilityLabel={`${camera.name}${selected ? ', allowed' : ', not allowed'}`}
              >
                {camera.name}
                {camera.enabled ? '' : ' (disabled)'}
              </Chip>
            );
          })}
        </View>
      )}

      {values.allowedCameras.length === 0 && cameras.length > 0 ? (
        <Banner visible icon="alert-outline" style={styles.banner}>
          With no zone allowed, this person raises an alert on every camera that recognises
          them. That is a valid configuration, but it is rarely what is intended.
        </Banner>
      ) : null}

      <Divider style={styles.divider} />

      <View style={[styles.enrolNote, { backgroundColor: theme.outcomes.FAULT.container }]}>
        <MaterialCommunityIcons
          name="face-recognition"
          size={20}
          color={theme.outcomes.FAULT.onContainer}
        />
        <Text variant="bodySmall" style={{ color: theme.outcomes.FAULT.onContainer, flex: 1 }}>
          A face cannot be enrolled from this screen yet. Until it is, the cameras have nothing
          to match this person against and will record them as an intruder.
        </Text>
      </View>

      <Button
        mode="contained"
        onPress={handleSubmit}
        loading={submitting}
        disabled={submitting || (mode === 'edit' && unchanged)}
        style={styles.submit}
      >
        {submitLabel}
      </Button>

      {mode === 'edit' && unchanged ? (
        <HelperText type="info">
          Nothing has been changed yet. The backend refuses an update with no fields.
        </HelperText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  form: {
    gap: 4,
  },
  banner: {
    marginVertical: 8,
    borderRadius: 12,
  },
  divider: {
    marginVertical: 12,
  },
  sectionTitle: {
    marginBottom: 4,
    fontWeight: '700',
  },
  sectionHint: {
    opacity: 0.7,
    marginBottom: 8,
  },
  roleCard: {
    borderRadius: 12,
    padding: 12,
    marginTop: 12,
    gap: 2,
  },
  roleTitle: {
    fontWeight: '700',
  },
  roleSummary: {
    opacity: 0.8,
    marginBottom: 4,
  },
  capability: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  capabilityText: {
    opacity: 0.8,
    flex: 1,
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  enrolNote: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    padding: 12,
    borderRadius: 12,
  },
  submit: {
    marginTop: 20,
  },
});
