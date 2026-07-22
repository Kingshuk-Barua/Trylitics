'use client';
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { FeatureCollection } from 'geojson';
import { useData } from './DataProvider';
import { IndiaMap, type ScoreKey } from './IndiaMap';
import { DistrictDrawer } from './DistrictDrawer';
import { Loading } from './ui';
import { loadGeoNameMap } from '@/lib/data';
import { percentileScale } from '@/lib/color';
import { num } from '@/lib/format';
import type { GeoNameMap } from '@/lib/types';

const METRICS: { key: ScoreKey; label: string }[] = [
  { key: 'overall_score', label: 'Overall' },
  { key: 'chronic_score', label: 'Chronic' },
  { key: 'acute_score', label: 'Acute' },
];

export function MapView({ compact = false }: { compact?: boolean }) {
  const { bundle, loading } = useData();
  const [adm2, setAdm2] = useState<FeatureCollection | null>(null);
  const [states, setStates] = useState<FeatureCollection | null>(null);
  const [crown, setCrown] = useState<FeatureCollection | null>(null);
  const [nameMap, setNameMap] = useState<GeoNameMap | null>(null);
  const [metric, setMetric] = useState<ScoreKey>('overall_score');
  const [selectedState, setSelectedState] = useState<string | null>(null);
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [geoError, setGeoError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([
      fetch('/india_adm2.geojson').then((r) => r.json()),
      fetch('/india_states.geojson').then((r) => r.json()),
      fetch('/india_crown.geojson').then((r) => r.json()),
      loadGeoNameMap(),
    ])
      .then(([d, s, c, n]) => {
        if (!alive) return;
        setAdm2(d as FeatureCollection);
        setStates(s as FeatureCollection);
        setCrown(c as FeatureCollection);
        setNameMap(n);
        if (n.unmatched_geo?.length) {
          // eslint-disable-next-line no-console
          console.warn(
            `[mai] ${n.unmatched_geo.length} district polygons did not match a scored record ` +
              `and render white. Full list on /data-quality.`,
            n.unmatched_geo,
          );
        }
      })
      .catch((e: unknown) => {
        if (alive) setGeoError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      alive = false;
    };
  }, []);

  // Browser back leaves the state view instead of leaving the site.
  useEffect(() => {
    function onPop() {
      setSelectedCode(null);
      setSelectedState(null);
    }
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const selectState = useCallback((s: string | null) => {
    setSelectedState(s);
    if (s) window.history.pushState({ state: s }, '', `#${s.toLowerCase().replace(/\s+/g, '-')}`);
    else if (window.location.hash) window.history.pushState({}, '', window.location.pathname);
  }, []);

  /** State names as the MAP knows them — the drill-down keys off NAME_1. */
  const geoStates = useMemo(() => {
    if (!states) return [];
    return [
      ...new Set(
        states.features.map((f) =>
          String((f.properties as Record<string, unknown>)?.NAME_1 ?? ''),
        ),
      ),
    ]
      .filter(Boolean)
      .sort();
  }, [states]);

  const districts = bundle?.districts ?? [];
  const scale = useMemo(
    () => percentileScale(districts.map((d) => d[metric] as number)),
    [districts, metric],
  );
  const doc = selectedCode ? (bundle?.byCode.get(selectedCode) ?? null) : null;

  const stateRows = useMemo(() => {
    if (!selectedState) return [];
    const key = selectedState.toLowerCase();
    return districts
      .filter((d) => d.state_name.toLowerCase().replace(/ and /g, ' and ') === key
        || d.state_name.toLowerCase().startsWith(key.slice(0, 6)))
      .sort((a, b) => (b[metric] as number) - (a[metric] as number));
  }, [districts, selectedState, metric]);

  if (loading) return <Loading what="districts" />;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {METRICS.map((m) => (
            <button
              key={m.key}
              onClick={() => setMetric(m.key)}
              className={`btn ${metric === m.key ? 'btn-on' : ''}`}
            >
              {m.label}
            </button>
          ))}
          {/* Not a convenience: at national scale the Andaman and Nicobar
              islands and Lakshadweep are a few pixels across and cannot be
              clicked at all. Without this control those territories are
              unreachable on the map. */}
          <select
            value={selectedState ?? ''}
            onChange={(e) => {
              selectState(e.target.value || null);
              setSelectedCode(null);
            }}
            className="rounded border border-line bg-panel px-3 py-1.5 text-[12px] text-dim outline-none transition-colors duration-[160ms] focus:border-accent"
            aria-label="Jump to a state"
          >
            <option value="">jump to a state…</option>
            {geoStates.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-3">
          {selectedState && (
            <button onClick={() => { selectState(null); setSelectedCode(null); }} className="btn btn-on">
              ← back to India
            </button>
          )}
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] tracking-[0.14em] text-dim">LOW</span>
            {scale.legend.map((l) => (
              <span
                key={l.color}
                title={`≈ ${num(l.value)}`}
                className="inline-block h-3 w-7 border border-line"
                style={{ background: l.color }}
              />
            ))}
            <span className="text-[10px] tracking-[0.14em] text-dim">HIGH</span>
            <span
              className="ml-2 inline-block h-3 w-7 border border-line"
              style={{ background: '#FFFFFF' }}
              title="no matching district record"
            />
            <span className="text-[10px] tracking-[0.14em] text-dim">NO DATA</span>
          </div>
        </div>
      </div>

      {geoError && (
        <div className="panel mb-4 px-4 py-3 text-[12px] text-ramp-6">
          Map layers failed to load ({geoError}). Run{' '}
          <code>python3 web/scripts/build_geo.py</code> to regenerate them.
        </div>
      )}

      <div className={`grid gap-5 ${compact ? '' : 'lg:grid-cols-[minmax(0,1fr)_380px]'}`}>
        <div className="panel overflow-hidden p-2">
          {adm2 ? (
            <IndiaMap
              districts={districts}
              byCode={bundle?.byCode ?? new Map()}
              nameMap={nameMap}
              adm2={adm2}
              states={states}
              crown={crown}
              metric={metric}
              selectedCode={selectedCode}
              selectedState={selectedState}
              onSelectDistrict={setSelectedCode}
              onSelectState={selectState}
            />
          ) : (
            <Loading what="map layers" />
          )}
        </div>

        {!compact && (
          // h-full so the record panel stretches to the row height set by the
          // map instead of ending in a short box partway down the page.
          <div className="h-full space-y-4">
            {doc ? (
              <DistrictDrawer
                doc={doc}
                total={districts.length}
                allScores={districts.map((d) => d[metric] as number)}
                onClose={() => setSelectedCode(null)}
              />
            ) : (
              <div className="panel px-4 py-4">
                <div className="h-eyebrow mb-2">
                  {selectedState ? selectedState : 'National view'}
                </div>
                <p className="text-[12px] leading-relaxed text-dim">
                  {selectedState
                    ? 'Click any district for its full record — pillar decomposition, rank interval, projected movement, imputation flags and provenance.'
                    : 'Click a state to zoom in. Hover any district for its score; click for the full record. Districts that did not match a scored record render white.'}
                </p>
                {selectedState && stateRows.length > 0 && (
                  <div className="mt-4 max-h-[520px] overflow-y-auto">
                    <table className="w-full">
                      <tbody>
                        {stateRows.map((d) => (
                          <tr
                            key={d.code}
                            onClick={() => setSelectedCode(d.code)}
                            className="cursor-pointer border-b border-line/60 transition-colors duration-[160ms] hover:bg-[#1F2A35]/40"
                          >
                            <td className="cell text-[12px] text-bright">
                              {d.district_name}
                            </td>
                            <td className="cell tnum text-right text-[12px] text-dim">
                              {num(d[metric] as number)}
                            </td>
                            <td className="cell tnum w-10 text-right text-[11px] text-dim">
                              {d.tier}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Below tablet the map is unusable at this density, so the same data is
          offered as a list rather than as a pinch-zoom puzzle. */}
      <div className="mt-4 text-[11px] text-dim lg:hidden">
        On a small screen, use the{' '}
        <a href="/districts/" className="text-accent underline">
          district table
        </a>{' '}
        — it carries the same records with search and sort.
      </div>
    </div>
  );
}
