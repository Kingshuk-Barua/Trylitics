'use client';
/**
 * Loads the district collection once for the whole session and hands it to
 * every view. One fetch, one cache, many derived views — hovering the map or
 * sorting a 698-row table must not touch the network.
 */
import {
  createContext, useContext, useEffect, useMemo, useState, type ReactNode,
} from 'react';
import { loadBundle, type Bundle } from '@/lib/data';
import type { DistrictDoc } from '@/lib/types';

interface Ctx {
  bundle: Bundle | null;
  loading: boolean;
  error: string | null;
  /** every state present in the data, sorted, with district counts */
  states: { name: string; count: number }[];
}

const DataCtx = createContext<Ctx>({
  bundle: null, loading: true, error: null, states: [],
});

export function DataProvider({ children }: { children: ReactNode }) {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    loadBundle()
      .then((b) => {
        if (!alive) return;
        setBundle(b);
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setError(e instanceof Error ? e.message : String(e));
        setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const states = useMemo(() => {
    if (!bundle) return [];
    const m = new Map<string, number>();
    for (const d of bundle.districts) m.set(d.state_name, (m.get(d.state_name) ?? 0) + 1);
    return [...m.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [bundle]);

  return (
    <DataCtx.Provider value={{ bundle, loading, error, states }}>
      {children}
    </DataCtx.Provider>
  );
}

export function useData(): Ctx {
  return useContext(DataCtx);
}

/** Districts, or an empty array while loading — saves a null check per view. */
export function useDistricts(): DistrictDoc[] {
  return useData().bundle?.districts ?? [];
}
