import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

/** Загрузка данных экрана: состояния Loading / Error / Default, повтор запроса.
 *  Пока данные не загружены для текущих deps, возвращается loading=true: экран не рендерится с данными от прежних параметров
 *  (например, вкладка D2 с ответом D1). */
export function useLoad<T>(fn: () => Promise<T>, deps: any[]) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<any>(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const key = useMemo(() => ({}), deps);
  const [loadedKey, setLoadedKey] = useState<object | null>(null);
  const seq = useRef(0);
  const reload = useCallback(async () => {
    const my = ++seq.current;
    setLoading(true);
    setError(null);
    try {
      const d = await fn();
      if (my === seq.current) setData(d);
    } catch (e) {
      if (my === seq.current) setError(e);
    } finally {
      if (my === seq.current) { setLoading(false); setLoadedKey(key); }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  useEffect(() => { reload(); }, [reload]);
  return { data, setData, loading: loading || loadedKey !== key, error: loadedKey === key ? error : null, reload };
}

/** Предупреждение об уходе со страницы при несохранённых изменениях (ТЗ, раздел 4). */
export function useUnsavedGuard(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return undefined;
    const h = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', h);
    return () => window.removeEventListener('beforeunload', h);
  }, [dirty]);
}
