'use client';
/**
 * The choropleth.
 *
 * Rendered as inline SVG with d3-geo rather than a tile library, because every
 * requirement here is per-feature: fill by score, stroke on selection, hover
 * without a network call, and an animated fit-to-bounds on drill-down. A tile
 * map would fight all four.
 *
 * Projection is fixed to the national extent and never recomputed. Drilling
 * into a state applies an SVG transform instead, so the zoom is one CSS
 * transition on one group rather than 735 re-projected path strings — which is
 * also why it stays smooth on a laptop.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { geoMercator, geoPath, type GeoPermissibleObjects } from 'd3-geo';
import type { Feature, FeatureCollection, Geometry } from 'geojson';
import { percentileScale, ACCENT, NO_DATA } from '@/lib/color';
import { geoKey } from '@/lib/names';
import type { DistrictDoc, GeoNameMap } from '@/lib/types';

const W = 900;
const H = 1000;

export type ScoreKey = 'overall_score' | 'chronic_score' | 'acute_score';

interface Props {
  districts: DistrictDoc[];
  byCode: Map<string, DistrictDoc>;
  nameMap: GeoNameMap | null;
  adm2: FeatureCollection | null;
  states: FeatureCollection | null;
  crown: FeatureCollection | null;
  metric: ScoreKey;
  selectedCode: string | null;
  selectedState: string | null;
  onSelectDistrict: (code: string | null) => void;
  onSelectState: (state: string | null) => void;
}

interface HoverInfo {
  x: number; y: number;
  name: string; state: string;
  doc: DistrictDoc | null;
}

export function IndiaMap({
  districts, byCode, nameMap, adm2, states, crown, metric,
  selectedCode, selectedState, onSelectDistrict, onSelectState,
}: Props) {
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const projection = useMemo(() => {
    const p = geoMercator();
    if (states) {
      p.fitExtent(
        [
          [12, 12],
          [W - 12, H - 12],
        ],
        states as unknown as GeoPermissibleObjects,
      );
    }
    return p;
  }, [states]);

  const path = useMemo(() => geoPath(projection), [projection]);

  const scale = useMemo(
    () => percentileScale(districts.map((d) => d[metric] as number)),
    [districts, metric],
  );

  /** shapeName|state -> district code, from the curated name map */
  const codeOf = useMemo(() => {
    const m = new Map<string, string>();
    if (!nameMap) return m;
    for (const [k, code] of Object.entries(nameMap.exact)) {
      const [name, state] = k.split('|');
      m.set(geoKey(name, state ?? ''), code);
    }
    return m;
  }, [nameMap]);

  function docFor(f: Feature<Geometry>): DistrictDoc | null {
    const p = f.properties as { shapeName?: string; state?: string } | null;
    if (!p?.shapeName) return null;
    const code = codeOf.get(geoKey(p.shapeName, p.state ?? ''));
    return code ? (byCode.get(code) ?? null) : null;
  }

  /** Zoom transform for the selected state, computed from projected bounds. */
  const transform = useMemo(() => {
    if (!selectedState || !states) return { k: 1, x: 0, y: 0 };
    const f = states.features.find(
      (s) =>
        String((s.properties as Record<string, unknown>)?.NAME_1 ?? '')
          .toLowerCase() === selectedState.toLowerCase(),
    );
    if (!f) return { k: 1, x: 0, y: 0 };
    const [[x0, y0], [x1, y1]] = path.bounds(f as unknown as GeoPermissibleObjects);
    const dx = x1 - x0;
    const dy = y1 - y0;
    // Capped: a small UT would otherwise zoom to a scale where the
    // simplified geometry's own vertices become visible as facets.
    const k = Math.min(6, 0.82 / Math.max(dx / W, dy / H));
    const cx = (x0 + x1) / 2;
    const cy = (y0 + y1) / 2;
    return { k, x: W / 2 - k * cx, y: H / 2 - k * cy };
  }, [selectedState, states, path]);

  // Escape leaves the state view — the same affordance as the back control.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        if (selectedCode) onSelectDistrict(null);
        else if (selectedState) onSelectState(null);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectedCode, selectedState, onSelectDistrict, onSelectState]);

  const stateNameOf = (f: Feature<Geometry>) =>
    String((f.properties as Record<string, unknown>)?.NAME_1 ?? '');

  const inSelectedState = (f: Feature<Geometry>) => {
    if (!selectedState) return true;
    const s = String((f.properties as Record<string, unknown>)?.state ?? '');
    return s.toLowerCase() === selectedState.toLowerCase();
  };

  function handleMove(e: React.MouseEvent, f: Feature<Geometry>) {
    const rect = wrapRef.current?.getBoundingClientRect();
    const p = f.properties as { shapeName?: string; state?: string };
    setHover({
      x: e.clientX - (rect?.left ?? 0),
      y: e.clientY - (rect?.top ?? 0),
      name: p.shapeName ?? '—',
      state: p.state ?? '—',
      doc: docFor(f),
    });
  }

  return (
    <div ref={wrapRef} className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-auto w-full select-none"
        role="img"
        aria-label="Choropleth of Indian districts by market attractiveness"
        onMouseLeave={() => setHover(null)}
      >
        <g
          className="map-zoom"
          style={{
            transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.k})`,
            transformOrigin: '0 0',
          }}
        >
          {/* districts */}
          <g>
            {adm2?.features.map((f, i) => {
              const doc = docFor(f);
              const dim = selectedState && !inSelectedState(f);
              const isSel = doc && doc.code === selectedCode;
              const fill = doc ? scale.color(doc[metric] as number) : NO_DATA;
              return (
                <path
                  key={`d${i}`}
                  d={path(f as unknown as GeoPermissibleObjects) ?? undefined}
                  fill={fill}
                  fillOpacity={dim ? 0.18 : 1}
                  stroke={isSel ? ACCENT : '#0B0F14'}
                  strokeWidth={isSel ? 2.4 / transform.k : 0.3 / transform.k}
                  className="cursor-pointer transition-[fill-opacity,stroke] duration-[160ms] ease-out hover:fill-opacity-100"
                  style={{ vectorEffect: 'non-scaling-stroke' }}
                  onMouseMove={(e) => handleMove(e, f)}
                  onClick={() => {
                    const p = f.properties as { state?: string };
                    if (!selectedState && p.state) onSelectState(p.state);
                    onSelectDistrict(doc ? doc.code : null);
                  }}
                />
              );
            })}
          </g>

          {/* state boundaries, heavier so states read as units */}
          <g fill="none" pointerEvents="none">
            {states?.features.map((f, i) => (
              <path
                key={`s${i}`}
                d={path(f as unknown as GeoPermissibleObjects) ?? undefined}
                // Lighter and heavier than the district hairlines: states have
                // to read as units against 734 individually filled polygons,
                // and #1F2A35 disappears against a mid-ramp fill.
                stroke="#0B0F14"
                strokeOpacity={0.85}
                strokeWidth={selectedState ? 1.2 : 1.8}
                strokeLinejoin="round"
                style={{ vectorEffect: 'non-scaling-stroke' }}
              />
            ))}
          </g>

          {/* disputed-territory outline, dashed and unfilled */}
          <g fill="none" pointerEvents="none">
            {crown?.features.map((f, i) => (
              <path
                key={`c${i}`}
                d={path(f as unknown as GeoPermissibleObjects) ?? undefined}
                stroke="#8FA3B0"
                strokeWidth={0.6}
                strokeDasharray="3 3"
                strokeOpacity={0.5}
                style={{ vectorEffect: 'non-scaling-stroke' }}
              />
            ))}
          </g>

          {/* clickable state hit-areas, national view only */}
          {!selectedState && (
            <g fill="transparent">
              {states?.features.map((f, i) => (
                <path
                  key={`h${i}`}
                  d={path(f as unknown as GeoPermissibleObjects) ?? undefined}
                  className="cursor-pointer"
                  onClick={() => onSelectState(stateNameOf(f))}
                  onMouseMove={(e) => {
                    // a state hit-area must not swallow the district tooltip
                    e.stopPropagation();
                  }}
                  pointerEvents="none"
                />
              ))}
            </g>
          )}
        </g>
      </svg>

      {hover && (
        <div
          className="pointer-events-none absolute z-30 min-w-[180px] rounded border border-line bg-panel px-3 py-2"
          style={{
            left: Math.min(hover.x + 14, (wrapRef.current?.clientWidth ?? 600) - 210),
            top: hover.y + 14,
          }}
        >
          <div className="font-display text-[13px] text-bright">{hover.name}</div>
          <div className="text-[11px] text-dim">{hover.state}</div>
          {hover.doc ? (
            <div className="mt-2 space-y-0.5 text-[11px]">
              <div className="flex justify-between gap-6">
                <span className="text-dim">MAI</span>
                <span className="tnum text-bright">
                  {(hover.doc[metric] as number).toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between gap-6">
                <span className="text-dim">rank</span>
                <span className="tnum text-bright">
                  {metric === 'chronic_score'
                    ? hover.doc.chronic_rank
                    : metric === 'acute_score'
                      ? hover.doc.acute_rank
                      : hover.doc.overall_rank}{' '}
                  <span className="text-dim">/ {districts.length}</span>
                </span>
              </div>
              <div className="flex justify-between gap-6">
                <span className="text-dim">band</span>
                <span className="tnum text-bright">{hover.doc.tier}</span>
              </div>
            </div>
          ) : (
            <div className="mt-2 text-[11px] leading-snug text-dim">
              No data — this polygon did not match a scored district.
              <br />
              Listed on the data-quality page.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
