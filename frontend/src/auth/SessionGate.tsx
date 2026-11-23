/**
 * Session guard shared by every authenticated route group.
 *
 * Extracted rather than copied into each layout: a second hand-written copy
 * is how one group silently ends up with a weaker rule than the other.
 *
 * This is a convenience guard, not a security boundary. Nothing is trusted on
 * the client -- every route the screens call is enforced by the backend's own
 * role checks. Redirecting only avoids showing a signed-out visitor a screen
 * that would fail on every request.
 */

import { Redirect } from 'expo-router';
import React from 'react';

import { useAuth } from './AuthContext';

export function SessionGate({ children }: { children: React.ReactNode }) {
  const { initialising, isSignedIn } = useAuth();

  // Nothing is rendered while the stored token is still being verified.
  // Rendering the screen first would flash protected content before the
  // redirect, which looks like a leak even when no data was fetched.
  if (initialising) {
    return null;
  }
  if (!isSignedIn) {
    return <Redirect href="/login" />;
  }
  return <>{children}</>;
}
