/**
 * Cross-screen notification that journal entries were deleted.
 *
 * The problem this solves: the detail screen can delete an event, but the
 * list screen holds its own loaded pages. Without a signal, going back would
 * show a row that no longer exists -- and refetching the whole list instead
 * would discard every page the user had scrolled through.
 *
 * So the signal carries the deleted IDS rather than "something changed": the
 * list removes exactly those rows and keeps its position.
 *
 * Worth naming plainly: this is a hand-written invalidation channel, and it
 * covers precisely one mutation. The screens still to be built (people,
 * cameras, enrolment) each invalidate different lists after create, update
 * and delete, so hand-writing this per screen is the cost that a server-state
 * library removes. That decision is still open; this file is the minimum
 * needed to keep the journal honest in the meantime.
 */

const deletedIds = new Set<string>();
const listeners = new Set<() => void>();

/** Record that an entry was deleted, after the backend confirmed it. */
export function announceDeletedEntry(id: string): void {
  deletedIds.add(id);
  listeners.forEach((listener) => listener());
}

/**
 * Take the pending deletions, clearing them.
 *
 * Draining rather than reading keeps a late-mounting list from applying the
 * same removal twice, and keeps the set from growing for the life of the app.
 */
export function drainDeletedEntries(): string[] {
  const ids = [...deletedIds];
  deletedIds.clear();
  return ids;
}

export function subscribeToDeletions(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
