/**
 * Typed HTTP client for the surveillance backend.
 *
 * Scope of this file: transport only. It performs no caching, holds no React
 * state and decides nothing about navigation or storage -- those are open
 * decisions. Token retrieval is INJECTED (`getToken`), so choosing where the
 * token lives (SecureStore, AsyncStorage, memory) does not require touching
 * this file.
 *
 * Base URL
 * --------
 * Set `EXPO_PUBLIC_API_URL` in `frontend/.env`. Expo inlines variables with
 * the `EXPO_PUBLIC_` prefix at build time on every platform.
 *
 * The default differs per platform for a reason that costs beginners hours:
 * on a physical iPhone running Expo Go, `127.0.0.1` is the PHONE itself, not
 * the laptop, so the request fails with a network error that looks like a
 * dead server. On a phone the laptop's LAN address must be used.
 */

import { Platform } from 'react-native';

import type {
  Camera,
  CameraCreate,
  CameraUpdate,
  CurrentUser,
  DetectionResult,
  LoginResponse,
  LogPage,
  LogQuery,
  Person,
  PersonCreate,
  PersonUpdate,
  PurgeQuery,
  PurgeResult,
} from './types';

const DEFAULT_PORT = 8000;

function defaultBaseUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_API_URL;
  if (fromEnv) {
    return fromEnv.replace(/\/+$/, '');
  }
  // In a browser the backend is reachable at the same host that served the
  // page, which is the laptop. On a device it is not, and there is no way to
  // guess the laptop's address -- hence the explicit error below rather than
  // a silent failure.
  if (Platform.OS === 'web') {
    return `http://127.0.0.1:${DEFAULT_PORT}`;
  }
  return '';
}

export interface ApiConfig {
  baseUrl: string;
  /** Returns the bearer token, or null when not signed in. */
  getToken: () => string | null | Promise<string | null>;
  /**
   * Called when the backend answers 401 on an authenticated request.
   *
   * This is not merely about expiry: the backend invalidates a token the
   * moment a person is demoted, so a 401 can arrive mid-session on a token
   * that has not expired. The app must sign out rather than retry.
   */
  onUnauthorized?: () => void;
}

let config: ApiConfig = {
  baseUrl: defaultBaseUrl(),
  getToken: () => null,
};

export function configureApi(partial: Partial<ApiConfig>): void {
  config = { ...config, ...partial };
}

export function getApiBaseUrl(): string {
  return config.baseUrl;
}

/** An error carrying the HTTP status, so callers can branch on it. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }

  /** 422 from Pydantic validation, as opposed to a business-rule refusal. */
  get isValidation(): boolean {
    return this.status === 422;
  }
}

/**
 * Turn a FastAPI error body into one readable line.
 *
 * FastAPI uses `detail` for two different shapes: a plain string for errors
 * raised by the services, and an array of objects for schema validation.
 * Rendering the array naively produces "[object Object]" on screen, which is
 * why this is handled here once instead of at every call site.
 */
function formatDetail(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) {
          const location = Array.isArray((item as { loc?: unknown[] }).loc)
            ? (item as { loc: unknown[] }).loc.filter((p) => p !== 'body').join('.')
            : '';
          const message = String((item as { msg: unknown }).msg);
          return location ? `${location}: ${message}` : message;
        }
        return null;
      })
      .filter((m): m is string => Boolean(m));
    if (messages.length > 0) {
      return messages.join('\n');
    }
  }
  return fallback;
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
  /** Public routes (login) must not send an Authorization header. */
  authenticated?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, authenticated = true } = options;

  if (!config.baseUrl) {
    throw new ApiError(
      0,
      'API address not configured. Set EXPO_PUBLIC_API_URL to the laptop address, ' +
        'for example http://192.168.1.10:8000',
      null,
    );
  }

  const url = new URL(config.baseUrl + path);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) {
        url.searchParams.set(key, String(value));
      }
    }
  }

  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }
  if (authenticated) {
    const token = await config.getToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  }

  let response: Response;
  try {
    response = await fetch(url.toString(), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (cause) {
    // A failed fetch here is almost always "wrong address" or "server not
    // running", not a backend error. Saying so saves a long debugging detour.
    throw new ApiError(
      0,
      `Could not reach the server at ${config.baseUrl}. Check that it is running ` +
        'and that the address is reachable from this device.',
      cause,
    );
  }

  if (response.status === 401 && authenticated) {
    config.onUnauthorized?.();
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }

  if (!response.ok) {
    const detail =
      parsed && typeof parsed === 'object' && 'detail' in parsed
        ? (parsed as { detail: unknown }).detail
        : parsed;
    throw new ApiError(
      response.status,
      formatDetail(detail, `Request failed with status ${response.status}.`),
      detail,
    );
  }

  return parsed as T;
}

// -- authentication ---------------------------------------------------------

export const auth = {
  login: (email: string, password: string) =>
    request<LoginResponse>('/api/auth/login', {
      method: 'POST',
      body: { email, password },
      authenticated: false,
    }),

  me: () => request<CurrentUser>('/api/auth/me'),
};

// -- monitored people -------------------------------------------------------

export const people = {
  list: () => request<Person[]>('/api/whitelist/'),

  get: (id: string) => request<Person>(`/api/whitelist/${id}`),

  create: (person: PersonCreate) =>
    request<Person>('/api/whitelist/', { method: 'POST', body: person }),

  update: (id: string, changes: PersonUpdate) =>
    request<Person>(`/api/whitelist/${id}`, { method: 'PUT', body: changes }),

  remove: (id: string) =>
    request<{ message: string }>(`/api/whitelist/${id}`, { method: 'DELETE' }),
};

// -- cameras ----------------------------------------------------------------

export const cameras = {
  list: () => request<Camera[]>('/api/cameras/'),

  create: (camera: CameraCreate) =>
    request<Camera>('/api/cameras/', { method: 'POST', body: camera }),

  update: (cameraId: string, changes: CameraUpdate) =>
    request<Camera>(`/api/cameras/${cameraId}`, { method: 'PUT', body: changes }),

  remove: (cameraId: string) =>
    request<{ message: string }>(`/api/cameras/${cameraId}`, { method: 'DELETE' }),
};

// -- journal ----------------------------------------------------------------

export const logs = {
  list: (query: LogQuery = {}) =>
    request<LogPage>('/api/logs/', { query: { ...query } }),

  /** Bulk delete. Irreversible; the backend refuses it without confirm=true. */
  purge: (query: PurgeQuery) =>
    request<PurgeResult>('/api/logs/', { method: 'DELETE', query: { ...query } }),

  remove: (id: string) =>
    request<{ message: string }>(`/api/logs/${id}`, { method: 'DELETE' }),
};

// -- detection --------------------------------------------------------------

export const detection = {
  /** Evaluate one frame. ADMIN only; used for the demonstration. */
  evaluate: (cameraId: string, embedding: number[], snapshotPath?: string) =>
    request<DetectionResult>('/api/detection/evaluate', {
      method: 'POST',
      body: { camera_id: cameraId, embedding, snapshot_path: snapshotPath ?? null },
    }),

  /**
   * Generate a simulated event. ADMIN only.
   *
   * This is NOT recognition: the backend believes the `expected` flag. It
   * exists so the app can be built before any camera or model is available.
   */
  simulate: (expected: boolean, userId?: string, cameraId?: string) =>
    request<{ simulated: boolean; reason: string; event: unknown }>(
      '/api/simulation/detection',
      {
        method: 'POST',
        body: { expected, user_id: userId ?? null, camera_id: cameraId ?? 'cam_entrance' },
      },
    ),
};
