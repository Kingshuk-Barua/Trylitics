/**
 * The choropleth ramp.
 *
 * Deliberately not the accent colour: score must never read as selection.
 * Selection is a `#3FB6A8` stroke and nothing else, so a district can be
 * simultaneously high-scoring and selected without the two signals colliding.
 *
 * The scale is built on PERCENTILE, not on the raw score. MAI is bounded and
 * clustered — 698 districts inside a ~73-point range with most of the mass in
 * the middle — so a linear domain would render the whole country in two
 * indistinguishable shades. Ranking against the distribution is also the
 * honest reading of a composite index: what matters is where a district sits
 * relative to the others, which is exactly what the index measures.
 */
import { scaleLinear } from 'd3-scale';

export const RAMP = ['#1B2A38', '#24506B', '#2E7C93', '#63B39B', '#C8D98A', '#F2C14E'];
export const NO_DATA = '#FFFFFF';
export const ACCENT = '#3FB6A8';

const interp = scaleLinear<string>()
  .domain(RAMP.map((_, i) => i / (RAMP.length - 1)))
  .range(RAMP)
  .clamp(true);

/** t in [0,1] -> ramp colour. */
export function rampColor(t: number): string {
  if (!Number.isFinite(t)) return NO_DATA;
  return interp(t);
}

/**
 * Build a percentile lookup over a set of values. Returns a function mapping a
 * value to its colour, plus the legend breakpoints actually used.
 */
export function percentileScale(values: number[]) {
  const sorted = [...values].filter(Number.isFinite).sort((a, b) => a - b);
  const n = sorted.length;

  function pctOf(v: number): number {
    if (!n || !Number.isFinite(v)) return NaN;
    // binary search for the insertion point
    let lo = 0;
    let hi = n;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (sorted[mid] < v) lo = mid + 1;
      else hi = mid;
    }
    return n === 1 ? 0.5 : lo / (n - 1);
  }

  const legend = RAMP.map((color, i) => {
    const t = i / (RAMP.length - 1);
    const idx = Math.min(n - 1, Math.max(0, Math.round(t * (n - 1))));
    return { color, t, value: sorted[idx] ?? NaN };
  });

  return {
    color: (v: number | null | undefined) =>
      v === null || v === undefined || !Number.isFinite(v)
        ? NO_DATA
        : rampColor(pctOf(v)),
    percentile: pctOf,
    legend,
    min: sorted[0] ?? NaN,
    max: sorted[n - 1] ?? NaN,
  };
}

/** Diverging colour for a signed value such as the growth gap. */
export function divergingColor(v: number, cap = 40): string {
  if (!Number.isFinite(v)) return NO_DATA;
  const t = Math.max(-1, Math.min(1, v / cap));
  return t >= 0 ? rampColor(0.5 + t * 0.5) : rampColor(0.5 + t * 0.5);
}
