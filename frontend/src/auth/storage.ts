/**
 * Where the authentication token is kept.
 *
 * Two different mechanisms, because the platforms genuinely differ:
 *
 * - iOS / Android: `expo-secure-store`, which is the Keychain and the
 *   Keystore. The value is encrypted by the operating system and is not
 *   readable by other applications.
 * - Web: `localStorage`. SecureStore has NO web implementation, and there is
 *   no encrypted browser equivalent -- anything the page can read, a script
 *   on the page can read.
 *
 * SECURITY NOTE, to be stated in the thesis rather than hidden here: on the
 * web build the token is exposed to any script running in the page, so an
 * XSS flaw would leak it. That is acceptable for a local demonstration over
 * localhost, and it is the reason the backend keeps token lifetimes short and
 * invalidates a token the moment a person is demoted. It would NOT be
 * acceptable for a public deployment, where the token belongs in an
 * HttpOnly cookie that JavaScript cannot read at all.
 */

import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

/** SecureStore keys must be alphanumeric, with `.`, `-` and `_` only. */
const TOKEN_KEY = 'surveillance.auth.token';

const isWeb = Platform.OS === 'web';

function webStorage(): Storage | null {
  // Guarded rather than assumed: during server-side rendering of the web
  // build there is no `window`, and touching it would crash the bundle.
  if (typeof window === 'undefined' || !window.localStorage) {
    return null;
  }
  return window.localStorage;
}

export async function saveToken(token: string): Promise<void> {
  if (isWeb) {
    webStorage()?.setItem(TOKEN_KEY, token);
    return;
  }
  await SecureStore.setItemAsync(TOKEN_KEY, token, {
    // Require the device to be unlocked. A surveillance app's token should
    // not be readable from a locked phone.
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
}

export async function loadToken(): Promise<string | null> {
  if (isWeb) {
    return webStorage()?.getItem(TOKEN_KEY) ?? null;
  }
  try {
    return await SecureStore.getItemAsync(TOKEN_KEY);
  } catch {
    // A corrupted or unreadable entry must not block startup: the worst
    // outcome is that the user signs in again.
    return null;
  }
}

export async function clearToken(): Promise<void> {
  if (isWeb) {
    webStorage()?.removeItem(TOKEN_KEY);
    return;
  }
  try {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
  } catch {
    // Already absent; nothing to do.
  }
}
