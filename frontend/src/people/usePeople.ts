/**
 * People data: the hub's list, its filters, and the three writes.
 *
 * Why the filters here are applied on the DEVICE, while the journal's are
 * applied by the database -- the inconsistency is deliberate and the reason
 * matters:
 *
 * `GET /api/logs/` is paginated, so filtering already-loaded rows would
 * describe only those rows while `total` still counted the rest; the screen
 * would claim "3 events" out of hundreds. `GET /api/whitelist/` is NOT
 * paginated -- it returns every person in the hub in one response -- so the
 * loaded list IS the whole set. Filtering it locally is exact, and it is also
 * instant, which matters for a search box.
 *
 * That holds because a hub has tens of people, not thousands. If the route
 * ever gains pagination, this filtering must move to the server for the same
 * reason the journal's did.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError, people as peopleApi } from '../api/client';
import type { Person, PersonCreate, PersonUpdate, UserRole } from '../api/types';
import { announcePeopleChanged, peopleVersion, subscribeToPeopleChanges } from './peopleSignals';

export interface PeopleFilters {
  /** Matched against name and email, case-insensitively. */
  search: string;
  role: UserRole | null;
  /** Narrow to people whose face is enrolled, or who still need enrolling. */
  enrolment: 'all' | 'enrolled' | 'missing';
}

export const EMPTY_PEOPLE_FILTERS: PeopleFilters = {
  search: '',
  role: null,
  enrolment: 'all',
};

export function countActivePeopleFilters(filters: PeopleFilters): number {
  let active = 0;
  if (filters.search.trim()) active += 1;
  if (filters.role) active += 1;
  if (filters.enrolment !== 'all') active += 1;
  return active;
}

function matches(person: Person, filters: PeopleFilters): boolean {
  if (filters.role && person.role !== filters.role) {
    return false;
  }
  if (filters.enrolment === 'enrolled' && !person.has_embedding) {
    return false;
  }
  if (filters.enrolment === 'missing' && person.has_embedding) {
    return false;
  }
  const needle = filters.search.trim().toLowerCase();
  if (!needle) {
    return true;
  }
  return (
    person.name.toLowerCase().includes(needle) ||
    (person.email ?? '').toLowerCase().includes(needle)
  );
}

export interface PeopleState {
  /** The people that pass the filters, ready to render. */
  visible: Person[];
  /** How many people the hub has in total, regardless of filters. */
  total: number;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  filters: PeopleFilters;
  setFilters: (next: PeopleFilters) => void;
  refresh: () => void;
}

export function usePeople(): PeopleState {
  const [all, setAll] = useState<Person[]>([]);
  const [filters, setFilters] = useState<PeopleFilters>(EMPTY_PEOPLE_FILTERS);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Identifies the most recent request, so a slow earlier response cannot
  // overwrite a newer one. Cheaper than cancellation and enough here.
  const requestId = useRef(0);
  // The invalidation version this list last loaded. Compared on mount as
  // well, because a change may have been announced while this screen was
  // unmounted -- for instance a person deleted from the detail screen.
  const loadedVersion = useRef(-1);

  const load = useCallback(async (mode: 'replace' | 'refresh') => {
    const ticket = ++requestId.current;
    const version = peopleVersion();

    if (mode === 'refresh') {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const list = await peopleApi.list();
      if (ticket !== requestId.current) {
        return;
      }
      // Sorted by name so the order does not depend on insertion order in
      // the database, which would make the list appear to shuffle itself
      // after every edit.
      setAll([...list].sort((a, b) => a.name.localeCompare(b.name)));
      loadedVersion.current = version;
    } catch (caught) {
      if (ticket !== requestId.current) {
        return;
      }
      setError(caught instanceof ApiError ? caught.message : 'The people could not be loaded.');
    } finally {
      if (ticket === requestId.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    void load('replace');
  }, [load]);

  useEffect(() => {
    const apply = () => {
      if (peopleVersion() !== loadedVersion.current) {
        void load('refresh');
      }
    };
    apply();
    return subscribeToPeopleChanges(apply);
  }, [load]);

  return {
    visible: all.filter((person) => matches(person, filters)),
    total: all.length,
    loading,
    refreshing,
    error,
    filters,
    setFilters,
    refresh: () => void load('refresh'),
  };
}

// -- writes -----------------------------------------------------------------
//
// Thin wrappers whose only job is to announce the change AFTER the backend
// confirmed it. Announcing before would make every screen reload to the state
// it already had while reporting a change that never happened.

export async function createPerson(person: PersonCreate): Promise<Person> {
  const created = await peopleApi.create(person);
  announcePeopleChanged();
  return created;
}

export async function updatePerson(id: string, changes: PersonUpdate): Promise<Person> {
  const updated = await peopleApi.update(id, changes);
  announcePeopleChanged();
  return updated;
}

export async function deletePerson(id: string): Promise<void> {
  await peopleApi.remove(id);
  announcePeopleChanged();
}
