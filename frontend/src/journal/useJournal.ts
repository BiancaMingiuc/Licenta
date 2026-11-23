/**
 * Journal data: filters, paging and loading state.
 *
 * Why this is a separate file rather than code inside the screen: the caching
 * library is still an open architectural decision. Every request the journal
 * makes goes through here, so adopting one later replaces this file and
 * touches no screen.
 *
 * Two things in here are correctness, not convenience:
 *
 * 1. **Filters are sent to the server.** The list is paginated, so filtering
 *    the loaded rows would describe only those rows while `total` still
 *    counted the whole journal. The screen would report "3 events" out of
 *    hundreds, which on an audit journal is worse than no filter at all.
 *
 * 2. **Responses are matched to the request that asked for them.** Toggling
 *    filters quickly issues overlapping requests, and they do not necessarily
 *    come back in order. Without the sequence guard below, a slow response for
 *    an abandoned filter can overwrite the result of the current one, leaving
 *    the screen showing rows that contradict the selected filters.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError, logs as logsApi } from '../api/client';
import type { DetectionReason, LogEntry } from '../api/types';
import { drainDeletedEntries, subscribeToDeletions } from './journalSignals';

export const PAGE_SIZE = 25;

/** Relative time windows, which is how a person actually thinks about a log. */
export type DatePreset = 'all' | 'today' | '7d' | '30d';

export const DATE_PRESET_LABELS: Record<DatePreset, string> = {
  all: 'All time',
  today: 'Last 24 hours',
  '7d': 'Last 7 days',
  '30d': 'Last 30 days',
};

export interface JournalFilters {
  cameraId: string | null;
  status: DetectionReason | null;
  datePreset: DatePreset;
}

export const EMPTY_FILTERS: JournalFilters = {
  cameraId: null,
  status: null,
  datePreset: 'all',
};

export function countActiveFilters(filters: JournalFilters): number {
  let active = 0;
  if (filters.cameraId) active += 1;
  if (filters.status) active += 1;
  if (filters.datePreset !== 'all') active += 1;
  return active;
}

/**
 * Turn a preset into the `since` bound the backend expects.
 *
 * Computed on the device and sent as an absolute UTC instant rather than as
 * "7d", so the server never has to guess which clock the window refers to.
 */
function sinceFromPreset(preset: DatePreset): string | undefined {
  if (preset === 'all') {
    return undefined;
  }
  const days = preset === 'today' ? 1 : preset === '7d' ? 7 : 30;
  const from = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
  return from.toISOString();
}

export interface JournalState {
  entries: LogEntry[];
  total: number;
  /** First load, or a reload after the filters changed. */
  loading: boolean;
  /** Pull-to-refresh, which keeps the current rows on screen. */
  refreshing: boolean;
  /** Fetching the next page. */
  loadingMore: boolean;
  error: string | null;
  hasMore: boolean;
  filters: JournalFilters;
  cameraOptions: string[];
  setFilters: (next: JournalFilters) => void;
  refresh: () => void;
  loadMore: () => void;
  /** Drop one entry locally after the backend confirmed its deletion. */
  forget: (id: string) => void;
}

export function useJournal(): JournalState {
  const [filters, setFiltersState] = useState<JournalFilters>(EMPTY_FILTERS);
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cameraOptions, setCameraOptions] = useState<string[]>([]);

  // Identifies the most recent request. A response whose number is not the
  // current one belongs to an abandoned filter and is discarded.
  const requestId = useRef(0);
  // Kept in a ref as well as in state: `loadMore` must read the offset at the
  // moment it fires, and state updates are not immediate.
  const loadedCount = useRef(0);

  const fetchPage = useCallback(
    async (next: JournalFilters, mode: 'replace' | 'refresh' | 'append') => {
      const ticket = ++requestId.current;
      const offset = mode === 'append' ? loadedCount.current : 0;

      if (mode === 'append') {
        setLoadingMore(true);
      } else if (mode === 'refresh') {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setError(null);

      try {
        const page = await logsApi.list({
          camera_id: next.cameraId ?? undefined,
          status: next.status ?? undefined,
          since: sinceFromPreset(next.datePreset),
          limit: PAGE_SIZE,
          offset,
        });

        if (ticket !== requestId.current) {
          return;
        }

        setTotal(page.total);
        if (mode === 'append') {
          // Deduplicated by id: a new event written between two page requests
          // shifts every row by one, which would otherwise make the last row
          // of the previous page reappear as the first of this one.
          setEntries((current) => {
            const known = new Set(current.map((item) => item.id));
            const merged = [...current, ...page.items.filter((item) => !known.has(item.id))];
            loadedCount.current = merged.length;
            return merged;
          });
        } else {
          loadedCount.current = page.items.length;
          setEntries(page.items);
        }
      } catch (caught) {
        if (ticket !== requestId.current) {
          return;
        }
        setError(
          caught instanceof ApiError ? caught.message : 'The journal could not be loaded.',
        );
      } finally {
        if (ticket === requestId.current) {
          setLoading(false);
          setRefreshing(false);
          setLoadingMore(false);
        }
      }
    },
    [],
  );

  // Camera options are loaded once: they change only when a new camera starts
  // reporting, which pull-to-refresh picks up.
  const loadCameraOptions = useCallback(async () => {
    try {
      const options = await logsApi.filterOptions();
      setCameraOptions(options.cameras);
    } catch {
      // A filter control that cannot be populated must not break the journal
      // itself: the list is the screen's purpose, the filter is an aid.
      setCameraOptions([]);
    }
  }, []);

  useEffect(() => {
    void fetchPage(filters, 'replace');
  }, [fetchPage, filters]);

  useEffect(() => {
    void loadCameraOptions();
  }, [loadCameraOptions]);

  // A deletion performed on the detail screen removes exactly that row here,
  // rather than refetching -- a refetch would discard every page already
  // scrolled through.
  useEffect(() => {
    const apply = () => {
      const ids = drainDeletedEntries();
      if (ids.length === 0) {
        return;
      }
      setEntries((current) => {
        const remaining = current.filter((item) => !ids.includes(item.id));
        loadedCount.current = remaining.length;
        return remaining;
      });
      setTotal((current) => Math.max(0, current - ids.length));
    };
    // Applied once on mount as well: the deletion may have been announced
    // while this screen was unmounted.
    apply();
    return subscribeToDeletions(apply);
  }, []);

  const setFilters = useCallback((next: JournalFilters) => {
    // Resetting to the first page is required, not cosmetic: keeping the
    // offset would open the new filter part-way through its results and look
    // like missing data.
    loadedCount.current = 0;
    setFiltersState(next);
  }, []);

  const refresh = useCallback(() => {
    void loadCameraOptions();
    void fetchPage(filters, 'refresh');
  }, [fetchPage, filters, loadCameraOptions]);

  const loadMore = useCallback(() => {
    if (loading || loadingMore || refreshing) {
      return;
    }
    if (loadedCount.current >= total) {
      return;
    }
    void fetchPage(filters, 'append');
  }, [fetchPage, filters, loading, loadingMore, refreshing, total]);

  const forget = useCallback((id: string) => {
    setEntries((current) => {
      const remaining = current.filter((item) => item.id !== id);
      loadedCount.current = remaining.length;
      return remaining;
    });
    setTotal((current) => Math.max(0, current - 1));
  }, []);

  return {
    entries,
    total,
    loading,
    refreshing,
    loadingMore,
    error,
    hasMore: entries.length < total,
    filters,
    cameraOptions,
    setFilters,
    refresh,
    loadMore,
    forget,
  };
}
