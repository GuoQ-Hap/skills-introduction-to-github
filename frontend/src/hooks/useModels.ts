import { useState, useEffect, useRef } from 'react';
import { adminApi, parsePoolModelsPayload, type AvailableModel } from '../api';

/** 仅在「已拿到一次完整池状态」后缓存，避免把「验证前空列表」缓存死 */
let settledCache: { models: AvailableModel[] } | null = null;

const POLL_MS = 3000;
const MAX_POLLS = 40;

export function useModels() {
  const [models, setModels] = useState<AvailableModel[]>(() => settledCache?.models ?? []);
  const [loading, setLoading] = useState(!settledCache);
  const [verifying, setVerifying] = useState(false);
  const pollCount = useRef(0);

  useEffect(() => {
    if (settledCache) {
      setModels(settledCache.models);
      setLoading(false);
      setVerifying(false);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const finish = (list: AvailableModel[]) => {
      settledCache = { models: list };
      setModels(list);
      setLoading(false);
      setVerifying(false);
    };

    const fetchOnce = (): void => {
      adminApi
        .availableModels()
        .then((res) => {
          if (cancelled) return;
          const { models: list, last_full_test } = parsePoolModelsPayload(res.data);
          const poolReady = last_full_test != null || list.length > 0;

          if (poolReady) {
            finish(list);
            return;
          }

          setModels([]);
          setVerifying(true);
          setLoading(true);
          if (pollCount.current >= MAX_POLLS) {
            finish([]);
            return;
          }
          pollCount.current += 1;
          timer = setTimeout(fetchOnce, POLL_MS);
        })
        .catch(() => {
          if (cancelled) return;
          finish([]);
        });
    };

    pollCount.current = 0;
    fetchOnce();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  return { models, loading, verifying };
}
