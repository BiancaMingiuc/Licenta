/**
 * How the three RBAC roles are presented, and which of them can sign in.
 *
 * `canSignIn` mirrors `ROLES_WITH_LOGIN` in `backend/app/services/user_service.py`.
 * It is duplicated here on purpose, with one justification: the form needs to
 * know whether to ASK for a password before the request is sent. Without it
 * the only way to learn that a password is required would be a 422 after
 * submitting, which trains the user to guess.
 *
 * What is NOT duplicated is the enforcement. The backend remains the only
 * authority: it derives `has_app_access` from the role, refuses a password on
 * a MONITORED person, and clears the stored hash on demotion. This file makes
 * the form honest, not permissive.
 *
 * The "last administrator" rule is deliberately absent. Deciding whether this
 * person is the last ADMIN would need a count the client does not reliably
 * have -- another administrator may have been deleted a second ago -- so that
 * refusal is left to the backend's 409 and its message is shown as-is.
 */

import type { UserRole } from '../api/types';

export interface RolePresentation {
  label: string;
  /** Material icon name. Meaning must survive without colour. */
  icon: string;
  /** One line stating what the role is. */
  summary: string;
  /** Spelled out in the form, so the consequence of the choice is visible. */
  capabilities: string[];
  /** Can authenticate, and therefore needs an email and a password. */
  canSignIn: boolean;
}

/** Most privileged first, which is the order a reader expects. */
export const ROLE_ORDER: readonly UserRole[] = ['ADMIN', 'APP_USER', 'MONITORED'];

export const ROLES: Record<UserRole, RolePresentation> = {
  ADMIN: {
    label: 'Administrator',
    icon: 'shield-account',
    summary: 'Full control of the hub.',
    capabilities: [
      'Signs in to the application',
      'Enrols people and assigns zones',
      'Sees every event in the journal',
      'Registers and disables cameras',
    ],
    canSignIn: true,
  },
  APP_USER: {
    label: 'Application user',
    icon: 'account-check',
    summary: 'Signs in, and is recognised by the cameras.',
    capabilities: [
      'Signs in to the application',
      'Sees only their own events',
      'Recognised in their allowed zones',
      'Cannot administer people or cameras',
    ],
    canSignIn: true,
  },
  MONITORED: {
    label: 'Monitored person',
    icon: 'account-eye',
    summary: 'Known to the cameras, no application access.',
    capabilities: [
      'Recognised in their allowed zones',
      'Raises no intruder alert',
      'Has no password, so cannot sign in',
      'Cannot open the application at all',
    ],
    canSignIn: false,
  },
};

export function roleLabel(role: UserRole): string {
  return ROLES[role]?.label ?? role;
}

/** True when this role needs an email and a password to exist. */
export function roleNeedsCredentials(role: UserRole): boolean {
  return ROLES[role]?.canSignIn ?? false;
}

/**
 * Whether changing `from` to `to` forces a new password to be set.
 *
 * Promotion out of MONITORED does: the person never had a password hash, so
 * the backend has nothing to keep and refuses the change with 422 unless one
 * is supplied. Asking in the form turns that refusal into a visible field.
 */
export function promotionNeedsPassword(from: UserRole, to: UserRole): boolean {
  return !roleNeedsCredentials(from) && roleNeedsCredentials(to);
}

/**
 * Whether changing `from` to `to` destroys the person's credentials.
 *
 * Demotion does: the backend sets `password_hash` to NULL, so the old
 * password cannot be restored by promoting the person again. Worth warning
 * about before the change, not after.
 */
export function demotionClearsPassword(from: UserRole, to: UserRole): boolean {
  return roleNeedsCredentials(from) && !roleNeedsCredentials(to);
}
