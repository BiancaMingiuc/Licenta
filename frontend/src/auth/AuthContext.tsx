/**
 * Authentication state for the whole application.
 *
 * This is the only place that knows the user is signed in. It wires the token
 * storage into the API client (`configureApi`), so no screen ever touches a
 * token directly.
 *
 * One behaviour worth understanding: the backend invalidates a token the
 * moment a person loses application access, so a 401 can arrive on a token
 * that has NOT expired. `onUnauthorized` therefore signs the user out rather
 * than retrying -- a retry would loop forever against a permission that was
 * deliberately revoked.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { ApiError, auth as authApi, configureApi } from '../api/client';
import type { CurrentUser, UserRole } from '../api/types';
import { clearToken, loadToken, saveToken } from './storage';

interface AuthState {
  /** True until the stored token has been read from disk. */
  initialising: boolean;
  user: CurrentUser | null;
  role: UserRole | null;
  isSignedIn: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [initialising, setInitialising] = useState(true);
  const [user, setUser] = useState<CurrentUser | null>(null);
  // Held in a ref as well as state: the API client reads the token
  // synchronously on every request, and state updates are not immediate.
  const tokenRef = useRef<string | null>(null);

  const signOut = useCallback(async () => {
    tokenRef.current = null;
    setUser(null);
    await clearToken();
  }, []);

  // Configured once, before any request can be issued.
  useMemo(() => {
    configureApi({
      getToken: () => tokenRef.current,
      onUnauthorized: () => {
        void signOut();
      },
    });
  }, [signOut]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const stored = await loadToken();
      if (stored) {
        tokenRef.current = stored;
        try {
          // The stored token is verified against the backend rather than
          // trusted: it may have expired, or the account may have been
          // demoted while the app was closed. Showing the dashboard first and
          // failing afterwards would be worse than one short check here.
          const me = await authApi.me();
          if (!cancelled) {
            setUser(me);
          }
        } catch {
          await clearToken();
          tokenRef.current = null;
        }
      }
      if (!cancelled) {
        setInitialising(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const response = await authApi.login(email, password);
    tokenRef.current = response.access_token;
    await saveToken(response.access_token);
    try {
      setUser(await authApi.me());
    } catch (error) {
      // The token was issued but the identity could not be read. Leaving the
      // token behind would put the app in a half-signed-in state.
      tokenRef.current = null;
      await clearToken();
      throw error instanceof ApiError
        ? error
        : new Error('Signed in, but the profile could not be loaded.');
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      initialising,
      user,
      role: user?.role ?? null,
      isSignedIn: user !== null,
      signIn,
      signOut,
    }),
    [initialising, user, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider.');
  }
  return context;
}
