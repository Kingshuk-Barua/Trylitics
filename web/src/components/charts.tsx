'use client';
/**
 * Charts, hand-rolled in SVG.
 *
 * A charting library would bring its own type scale, its own default palette
 * and its own idea of a tooltip, and the whole point of this shell is that one
 * palette and one type system hold across map, tables and charts. These are
 * small enough that owning them is cheaper than overriding a library.
 */
import { useMemo, useState } from 'react';
import { scaleLinear } from 'd3-scale';
import { RAMP, ACCENT, percentileScale } from '@/lib/color';
import { num } from '@/lib/format';

const AXIS = '#1F2A35';
const TEXT = '#8FA3B0';

/** Histogram with an optional marker for one district. */
export function Histogram({
  values, bins = 40, height = 180, marker, label,
}: {
  values: number[]; bins?: number; height?: number; marker?: number; label?: string;
}) {
  const { bars, max, lo, hi } = useMemo(() => {
    const v = values.filter(Number.isFinite);
    if (!v.length) return { bars: [], max: 0, lo: 0, hi: 1 };
    const lo = Math.min(...v);
    const hi = Math.max(...v);
    const w = (hi - lo) / bins || 1;
    const counts = new Array(bins).fill(0);
    for (const x of v) counts[Math.min(bins - 1, Math.floor((x - lo) / w))]++;
    return { bars: counts, max: Math.max(...counts), lo, hi };
  }, [values, bins]);

  const W = 640;
  const H = height;
  const pad = { l: 34, r: 8, t: 8, b: 22 };
  const x = scaleLinear().domain([lo, hi]).range([pad.l, W - pad.r]);
  const y = scaleLinear().domain([0, max]).range([H - pad.b, pad.t]);
  const scale = percentileScale(values);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {y.ticks(4).map((t) => (
        <g key={t}>
          <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke={AXIS} strokeWidth={1} />
          <text x={4} y={y(t) + 3} fill={TEXT} fontSize={9} className="tnum">
            {t}
          </text>
        </g>
      ))}
      {bars.map((c, i) => {
        const bw = (W - pad.l - pad.r) / bins;
        const v = lo + ((hi - lo) * (i + 0.5)) / bins;
        return (
          <rect
            key={i}
            x={pad.l + i * bw}
            y={y(c)}
            width={Math.max(1, bw - 1)}
            height={H - pad.b - y(c)}
            fill={scale.color(v)}
            opacity={0.9}
          />
        );
      })}
      {marker !== undefined && Number.isFinite(marker) && (
        <line x1={x(marker)} x2={x(marker)} y1={pad.t} y2={H - pad.b} stroke={ACCENT} strokeWidth={2} />
      )}
      {x.ticks(6).map((t) => (
        <text key={t} x={x(t)} y={H - 6} fill={TEXT} fontSize={9} textAnchor="middle" className="tnum">
          {num(t, 0)}
        </text>
      ))}
      {label && (
        <text x={W - pad.r} y={pad.t + 10} fill={TEXT} fontSize={10} textAnchor="end">
          {label}
        </text>
      )}
    </svg>
  );
}

/** Horizontal bar list — league tables, weight breakdowns, coefficient plots. */
export function BarList({
  rows, max, height = 14, colorOf, format = (v: number) => num(v),
}: {
  rows: { label: string; value: number; note?: string }[];
  max?: number; height?: number;
  colorOf?: (v: number, i: number) => string;
  format?: (v: number) => string;
}) {
  const hi = max ?? Math.max(...rows.map((r) => Math.abs(r.value)), 1);
  const hasNeg = rows.some((r) => r.value < 0);
  return (
    <div className="space-y-2">
      {rows.map((r, i) => {
        const w = (Math.abs(r.value) / hi) * (hasNeg ? 50 : 100);
        const color = colorOf?.(r.value, i) ?? RAMP[3];
        return (
          <div key={r.label} className="grid grid-cols-[minmax(120px,1.4fr)_3fr_auto] items-center gap-3">
            <span className="truncate text-[11.5px] text-dim" title={r.label}>
              {r.label}
            </span>
            <div className="relative rounded bg-[#1F2A35]" style={{ height }}>
              {hasNeg && (
                <div className="absolute left-1/2 top-0 h-full w-px bg-[#2b3946]" />
              )}
              <div
                className="absolute top-0 h-full rounded transition-all duration-[160ms] ease-out"
                style={{
                  width: `${w}%`,
                  left: hasNeg ? (r.value >= 0 ? '50%' : `${50 - w}%`) : 0,
                  background: color,
                }}
              />
            </div>
            <span className="tnum w-16 text-right text-[11.5px] text-bright">
              {format(r.value)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** Scatter with hover readout — used for therapy comparison and growth gap. */
export function Scatter({
  points, xLabel, yLabel, height = 380, diagonal = false, onPick,
}: {
  points: { x: number; y: number; label: string; sub?: string; code: string }[];
  xLabel: string; yLabel: string; height?: number; diagonal?: boolean;
  onPick?: (code: string) => void;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 720;
  const H = height;
  const pad = { l: 44, r: 14, t: 14, b: 36 };
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const x = scaleLinear()
    .domain([Math.min(...xs), Math.max(...xs)])
    .nice()
    .range([pad.l, W - pad.r]);
  const y = scaleLinear()
    .domain([Math.min(...ys), Math.max(...ys)])
    .nice()
    .range([H - pad.b, pad.t]);

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {x.ticks(6).map((t) => (
          <g key={`x${t}`}>
            <line x1={x(t)} x2={x(t)} y1={pad.t} y2={H - pad.b} stroke={AXIS} />
            <text x={x(t)} y={H - 18} fill={TEXT} fontSize={9} textAnchor="middle" className="tnum">
              {num(t, 0)}
            </text>
          </g>
        ))}
        {y.ticks(5).map((t) => (
          <g key={`y${t}`}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke={AXIS} />
            <text x={pad.l - 6} y={y(t) + 3} fill={TEXT} fontSize={9} textAnchor="end" className="tnum">
              {num(t, 0)}
            </text>
          </g>
        ))}
        {diagonal && (
          <line
            x1={x(x.domain()[0])}
            y1={y(x.domain()[0])}
            x2={x(x.domain()[1])}
            y2={y(x.domain()[1])}
            stroke={TEXT}
            strokeDasharray="4 4"
            strokeOpacity={0.5}
          />
        )}
        {points.map((p, i) => (
          <circle
            key={p.code}
            cx={x(p.x)}
            cy={y(p.y)}
            r={hover === i ? 4.5 : 2.2}
            fill={hover === i ? ACCENT : RAMP[3]}
            fillOpacity={hover === i ? 1 : 0.65}
            className="cursor-pointer transition-all duration-[160ms] ease-out"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            onClick={() => onPick?.(p.code)}
          />
        ))}
        <text x={W / 2} y={H - 3} fill={TEXT} fontSize={10} textAnchor="middle">
          {xLabel}
        </text>
        <text
          x={-H / 2}
          y={11}
          fill={TEXT}
          fontSize={10}
          textAnchor="middle"
          transform="rotate(-90)"
        >
          {yLabel}
        </text>
      </svg>
      {hover !== null && (
        <div className="pointer-events-none absolute left-3 top-3 rounded border border-line bg-panel px-3 py-2">
          <div className="text-[12px] text-bright">{points[hover].label}</div>
          {points[hover].sub && (
            <div className="tnum text-[11px] text-dim">{points[hover].sub}</div>
          )}
        </div>
      )}
    </div>
  );
}

/** Cumulative coverage curve — value captured as territories are added. */
export function CoverageCurve({
  series, height = 300, xLabel, yLabel,
}: {
  series: { name: string; color: string; points: [number, number][] }[];
  height?: number; xLabel: string; yLabel: string;
}) {
  const W = 720;
  const H = height;
  const pad = { l: 44, r: 120, t: 14, b: 36 };
  const allX = series.flatMap((s) => s.points.map((p) => p[0]));
  const x = scaleLinear().domain([0, Math.max(...allX)]).range([pad.l, W - pad.r]);
  const y = scaleLinear().domain([0, 100]).range([H - pad.b, pad.t]);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {y.ticks(5).map((t) => (
        <g key={t}>
          <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke={AXIS} />
          <text x={pad.l - 6} y={y(t) + 3} fill={TEXT} fontSize={9} textAnchor="end" className="tnum">
            {t}
          </text>
        </g>
      ))}
      {x.ticks(6).map((t) => (
        <text key={t} x={x(t)} y={H - 18} fill={TEXT} fontSize={9} textAnchor="middle" className="tnum">
          {t}
        </text>
      ))}
      {(() => {
        // Curves that converge (all three end at 100%) would stack their end
        // labels on top of each other, so labels are pushed apart vertically
        // while keeping their series order.
        const ends = series
          .map((s, i) => ({ i, y: y(s.points[s.points.length - 1][1]) }))
          .sort((a, b) => a.y - b.y);
        const placed: Record<number, number> = {};
        let prev = -Infinity;
        for (const e of ends) {
          const yy = Math.max(e.y, prev + 13);
          placed[e.i] = yy;
          prev = yy;
        }
        return series.map((s, i) => (
          <g key={s.name}>
            <path
              d={s.points
                .map((p, j) => `${j ? 'L' : 'M'}${x(p[0])},${y(p[1])}`)
                .join(' ')}
              fill="none"
              stroke={s.color}
              strokeWidth={1.8}
            />
            <line
              x1={W - pad.r}
              x2={W - pad.r + 6}
              y1={y(s.points[s.points.length - 1][1])}
              y2={placed[i]}
              stroke={s.color}
              strokeWidth={0.8}
              strokeOpacity={0.6}
            />
            <text x={W - pad.r + 9} y={placed[i] + 3} fill={s.color} fontSize={10}>
              {s.name}
            </text>
          </g>
        ));
      })()}
      <text x={(W - pad.r) / 2} y={H - 3} fill={TEXT} fontSize={10} textAnchor="middle">
        {xLabel}
      </text>
      <text x={-H / 2} y={11} fill={TEXT} fontSize={10} textAnchor="middle" transform="rotate(-90)">
        {yLabel}
      </text>
    </svg>
  );
}
