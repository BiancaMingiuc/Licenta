/**
 * Types mirroring the backend contract.
 *
 * These are NOT design choices: every type here is dictated by a Pydantic
 * schema in `backend/app/schemas`. They are written out by hand so the app
 * fails at compile time when the backend contract changes, instead of
 * failing at runtime on the demonstration machine.
 *
 * When a backend schema changes, this file is the single place to update.
 */

// -- roles and vocabulary ---------------------------------------------------

/** From `user_schema.UserRole`. */
export type UserRole = 'ADMIN' | 'APP_USER' | 'MONITORED';

/**
 * From `access_schema.DetectionReason`: the precise reason recorded in the
 * journal. Seven values, deliberately finer-grained than the action.
 */
export type DetectionReason =
  | 'KNOWN'
  | 'INTRUDER'
  | 'UNEXPECTED_ZONE'
  | 'EMPTY_WHITELIST'
  | 'CAMERA_UNKNOWN'
  | 'CAMERA_DISABLED'
  | 'DEGRADED';

/**
 * From `access_schema.DetectionOutcome`: what the system must DO.
 *
 * The UI reacts to this level, not to the reason. Keeping ALERT and FAULT
 * apart is a requirement, not a detail: a security alert and a broken camera
 * must not look the same, or the user learns to ignore both.
 */
export type DetectionOutcome = 'KNOWN' | 'ALERT' | 'FAULT';

/** From `camera_schema.CameraKind`. */
export type CameraKind = 'USB' | 'CSI' | 'RTSP';

// -- authentication ---------------------------------------------------------

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: 'bearer';
  role: UserRole;
  expires_in: number;
}

/** From `GET /api/auth/me`. Never contains the password hash or embedding. */
export interface CurrentUser {
  id: string;
  hub_id: string;
  name: string;
  role: UserRole;
  email: string | null;
}

// -- monitored people -------------------------------------------------------

/**
 * A person as returned by the API.
 *
 * `embedding` is absent by design: the biometric vector never leaves the
 * backend. The client only learns WHETHER a face is enrolled.
 */
export interface Person {
  id: string;
  hub_id: string;
  name: string;
  role: UserRole;
  has_app_access: boolean;
  email: string | null;
  allowed_cameras: string[];
  has_embedding: boolean;
}

export interface PersonCreate {
  name: string;
  role: UserRole;
  email?: string | null;
  /** Required for ADMIN and APP_USER; rejected for MONITORED. */
  password?: string;
  allowed_cameras?: string[];
  embedding?: number[];
}

export type PersonUpdate = Partial<PersonCreate>;

// -- cameras ----------------------------------------------------------------

export interface Camera {
  hub_id: string;
  camera_id: string;
  name: string;
  kind: CameraKind;
  source: string | null;
  enabled: boolean;
  created_at: string | null;
}

export interface CameraCreate {
  /** Lowercase ASCII, digits and underscores only, 2-40 characters. */
  camera_id: string;
  name: string;
  kind?: CameraKind;
  source?: string | null;
}

export type CameraUpdate = Partial<Omit<CameraCreate, 'camera_id'>>;

// -- journal ----------------------------------------------------------------

/**
 * One surveillance event.
 *
 * `snapshot_path` is deliberately absent from the API: the photo of an
 * unidentified person is biometric data and is served on a separate
 * ADMIN-only route. The client only needs `has_snapshot` to show an
 * indicator.
 */
export interface LogEntry {
  id: string;
  hub_id: string;
  camera_id: string;
  user_id: string | null;
  user_name: string | null;
  status: DetectionReason;
  timestamp: string | null;
  has_snapshot: boolean;
}

export interface LogPage {
  items: LogEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface LogQuery {
  camera_id?: string;
  limit?: number;
  offset?: number;
}

/** Filters of `DELETE /api/logs/`. `confirm` is mandatory server-side. */
export interface PurgeQuery {
  confirm: true;
  camera_id?: string;
  status?: DetectionReason;
  /** A date (2026-10-20) or an ISO-8601 timestamp. */
  before?: string;
}

export interface PurgeResult {
  deleted: number;
  /** How many deleted entries referenced a snapshot file still on disk. */
  with_snapshot: number;
  filters: {
    camera_id: string | null;
    status: string | null;
    before: string | null;
  };
}

// -- detection --------------------------------------------------------------

export interface DetectionResult {
  outcome: DetectionOutcome;
  reason: DetectionReason;
  camera_id: string;
  user_id: string | null;
  user_name: string | null;
  score: number | null;
  threshold: number;
  log_id: string | null;
  candidates_compared: number;
}

// -- presentation helpers ---------------------------------------------------

/**
 * Which action level a journal status implies.
 *
 * Mirrors `access_schema.OUTCOME_BY_REASON`. The journal stores the reason,
 * so the UI needs this to decide how to present a row. Kept as a lookup
 * rather than an if-chain so a new reason cannot silently fall through
 * without a classification.
 */
export const OUTCOME_BY_REASON: Record<DetectionReason, DetectionOutcome> = {
  KNOWN: 'KNOWN',
  INTRUDER: 'ALERT',
  UNEXPECTED_ZONE: 'ALERT',
  EMPTY_WHITELIST: 'ALERT',
  CAMERA_UNKNOWN: 'FAULT',
  CAMERA_DISABLED: 'FAULT',
  DEGRADED: 'FAULT',
};
