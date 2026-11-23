/**
 * The hub's registered cameras.
 *
 * Needed by the people screens before a cameras screen exists: a person's
 * allowed zones are camera ids, and the backend validates every one of them
 * against the registry (`CameraService.validate_allowed_cameras`). Offering a
 * free-text field would let a typo create a permission that never matches --
 * the person would keep raising alerts in a zone they were supposed to be
 * expected in, with no error anywhere. Selecting from the real list makes
 * that impossible rather than merely unlikely.
 *
 * Reading cameras requires only a signed-in user (`require_app_access`), not
 * ADMIN, so this hook is safe to use from any authenticated screen.
 */

import { useCallback, useEffect, useState } from 'react';

import { ApiError, cameras as camerasApi } from '../api/client';
import type { Camera } from '../api/types';

export interface CamerasState {
  cameras: Camera[];
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export function useCameras(): CamerasState {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setCameras(await camerasApi.list());
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : 'The cameras could not be loaded.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return { cameras, loading, error, reload: () => void load() };
}

/**
 * Human label for a camera id.
 *
 * Falls back to the raw id rather than to "Unknown camera": an id that is no
 * longer in the registry still identifies where an event happened, and
 * hiding it would make a journal entry unreadable precisely when a camera has
 * been removed.
 */
export function cameraLabel(cameras: Camera[], cameraId: string): string {
  const match = cameras.find((camera) => camera.camera_id === cameraId);
  return match ? match.name : cameraId;
}
