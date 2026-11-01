/**
 * Sign-in screen.
 *
 * Two deliberate choices about error handling:
 *
 * 1. The backend answers identically for a wrong password and an unknown
 *    email, so accounts cannot be enumerated. The screen must not undo that
 *    by guessing which one it was -- it shows exactly what the server said.
 *
 * 2. A network failure (status 0) is shown differently from a rejected
 *    login, together with the address that was tried. On a phone the most
 *    common cause is that `EXPO_PUBLIC_API_URL` still points at localhost,
 *    which on the phone means the phone itself.
 */

import { useRouter } from 'expo-router';
import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import { Button, Card, HelperText, Text, TextInput, useTheme } from 'react-native-paper';

import { ApiError, getApiBaseUrl } from '../src/api/client';
import { useAuth } from '../src/auth/AuthContext';
import type { AppTheme } from '../src/theme/theme';

export default function LoginScreen() {
  const theme = useTheme<AppTheme>();
  const router = useRouter();
  const { signIn } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<{ message: string; isNetwork: boolean } | null>(null);

  const canSubmit = email.trim().length > 0 && password.length > 0 && !submitting;

  async function handleSubmit() {
    if (!canSubmit) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await signIn(email.trim(), password);
      router.replace('/journal');
    } catch (caught) {
      const isNetwork = caught instanceof ApiError && caught.status === 0;
      setError({
        message:
          caught instanceof Error ? caught.message : 'Sign-in failed for an unknown reason.',
        isNetwork,
      });
      // Cleared on failure so a wrong password is not resubmitted by accident.
      setPassword('');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={[styles.flex, { backgroundColor: theme.colors.background }]}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
      >
        <View style={[styles.wrapper, { maxWidth: 440 }]}>
          <View style={styles.header}>
            <Text variant="headlineMedium" style={styles.title}>
              Edge AI Surveillance
            </Text>
            <Text variant="bodyMedium" style={{ opacity: 0.7 }}>
              Sign in to review detections and manage monitored people.
            </Text>
          </View>

          <Card mode="elevated" style={styles.card}>
            <Card.Content style={styles.cardContent}>
              <TextInput
                label="Email"
                value={email}
                onChangeText={setEmail}
                mode="outlined"
                autoCapitalize="none"
                autoComplete="email"
                keyboardType="email-address"
                autoCorrect={false}
                textContentType="emailAddress"
                disabled={submitting}
                left={<TextInput.Icon icon="email-outline" />}
                accessibilityLabel="Email address"
              />

              <TextInput
                label="Password"
                value={password}
                onChangeText={setPassword}
                mode="outlined"
                secureTextEntry={!passwordVisible}
                autoCapitalize="none"
                autoComplete="current-password"
                textContentType="password"
                disabled={submitting}
                onSubmitEditing={handleSubmit}
                returnKeyType="go"
                left={<TextInput.Icon icon="lock-outline" />}
                right={
                  <TextInput.Icon
                    icon={passwordVisible ? 'eye-off' : 'eye'}
                    onPress={() => setPasswordVisible((visible) => !visible)}
                    accessibilityLabel={passwordVisible ? 'Hide password' : 'Show password'}
                  />
                }
                accessibilityLabel="Password"
              />

              {error ? (
                <HelperText type="error" visible padding="none">
                  {error.message}
                  {error.isNetwork ? `\n\nAddress tried: ${getApiBaseUrl() || '(not set)'}` : ''}
                </HelperText>
              ) : null}

              <Button
                mode="contained"
                onPress={handleSubmit}
                disabled={!canSubmit}
                loading={submitting}
                style={styles.submit}
                contentStyle={styles.submitContent}
              >
                {submitting ? 'Signing in…' : 'Sign in'}
              </Button>
            </Card.Content>
          </Card>

          <Text variant="bodySmall" style={styles.footer}>
            Only people granted application access can sign in. Monitored
            people have no password and no account.
          </Text>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  scroll: {
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  wrapper: {
    width: '100%',
    gap: 24,
  },
  header: {
    gap: 8,
  },
  title: {
    fontWeight: '700',
  },
  card: {
    borderRadius: 16,
  },
  cardContent: {
    gap: 16,
    paddingVertical: 8,
  },
  submit: {
    marginTop: 8,
    borderRadius: 12,
  },
  submitContent: {
    paddingVertical: 6,
  },
  footer: {
    opacity: 0.6,
    textAlign: 'center',
  },
});
