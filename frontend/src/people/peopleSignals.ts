/**
 * Cross-screen notification that the people list changed.
 *
 * This is the SECOND hand-written invalidation channel in the app, and it is
 * worth stating plainly why the two are not the same shape.
 *
 * `journalSignals.ts` carries the deleted IDS, because the journal is
 * paginated: refetching it would throw away every page already scrolled
 * through, so the list removes exactly the rows that went. Here the backend
 * route is `GET /api/whitelist/` and returns the hub's people in ONE
 * unpaginated response, so a refetch costs a single small request and loses
 * nothing. A version counter is therefore enough, and reproducing the
 * journal's surgical bookkeeping would be complexity with no benefit.
 *
 * The version is monotonic rather than a boolean flag so a screen can tell
 * "nothing changed while I was away" from "something changed twice": a
 * mounted list compares the version it last loaded against the current one,
 * which a flag cleared by the first reader could not do.
 *
 * This remains the cost of the still-open server-state decision. Two
 * channels, two shapes, written by hand. The cameras screen and face
 * enrolment would each add a third and a fourth.
 */

let version = 0;
const listeners = new Set<() => void>();

/**
 * Record that a person was created, updated or deleted.
 *
 * Call this only AFTER the backend confirmed the write. Announcing first
 * would make every screen reload to the same state it already had, while
 * reporting a change that never happened.
 */
export function announcePeopleChanged(): void {
  version += 1;
  listeners.forEach((listener) => listener());
}

/** The current version, to be compared against the one a screen loaded. */
export function peopleVersion(): number {
  return version;
}

export function subscribeToPeopleChanges(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
