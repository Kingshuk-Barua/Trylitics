'use client';
/** The full record for one district. Everything `publish.py` writes appears here. */
import { PILLAR_LABEL, PILLAR_ORDER, int, num, popShort } from '@/lib/format';
import { percentileScale } from '@/lib/color';
import { Bar } from './ui';
import type { DistrictDoc } from '@/lib/types';

export function DistrictDrawer({
  doc, total, allScores, onClose,
}: {
  doc: DistrictDoc | null; total: number; allScores: number[];
  onClose: () => void;
}) {
  if (!doc) return null;
  const scale = percentileScale(allScores);
  const cvf = doc.current_vs_future;
  const interval = doc.rank_interval_p5_p95;
  const pillars = doc.pillar_scores ?? {};

  const Row = ({ k, v }: { k: string; v: React.ReactNode }) => (
    <div className="flex items-baseline justify-between gap-4 py-1">
      <span className="text-[11px] text-dim">{k}</span>
      <span className="tnum text-[12px] text-bright">{v}</span>
    </div>
  );

  return (
    // No max-height and no overflow of its own: the panel grows to its content
    // and the PAGE scrolls it, so the record never sits in a short box with an
    // inner scrollbar next to a tall map.
    <aside className="panel flex h-full flex-col">
      <div className="flex items-start justify-between gap-4 border-b border-line bg-panel px-4 py-3">
        <div>
          <div className="h-eyebrow">{doc.state_name}</div>
          <h3 className="font-display text-[18px] tracking-[0.02em] text-bright">
            {doc.district_name}
          </h3>
          <div className="tnum mt-1 text-[11px] text-dim">
            code {doc.code} · population {popShort(doc.population_2011)}
          </div>
        </div>
        <button onClick={onClose} className="btn" aria-label="Close district panel">
          close
        </button>
      </div>

      <div className="space-y-5 px-4 py-4">
        {/* headline indices */}
        <div className="grid grid-cols-3 gap-2">
          {([
            ['Overall', doc.overall_score, doc.overall_rank],
            ['Chronic', doc.chronic_score, doc.chronic_rank],
            ['Acute', doc.acute_score, doc.acute_rank],
          ] as const).map(([label, score, rank]) => (
            <div key={label} className="rounded border border-line px-3 py-2">
              <div className="h-eyebrow">{label}</div>
              <div className="tnum mt-1 text-[19px] text-bright">{num(score)}</div>
              <div className="tnum text-[11px] text-dim">
                #{int(rank)} / {total}
              </div>
              <div className="mt-2">
                <Bar
                  value={score}
                  max={100}
                  color={scale.color(score)}
                />
              </div>
            </div>
          ))}
        </div>

        {/* rank interval — the honest precision of a rank */}
        {interval && (
          <div>
            <div className="h-eyebrow mb-2">Rank interval (5th–95th percentile)</div>
            <div className="relative h-6 rounded border border-line">
              <div
                className="absolute top-0 h-full bg-[#24506B]/50"
                style={{
                  left: `${(interval[0] / total) * 100}%`,
                  width: `${((interval[1] - interval[0]) / total) * 100}%`,
                }}
              />
              <div
                className="absolute top-0 h-full w-[2px] bg-accent"
                style={{ left: `${(doc.overall_rank / total) * 100}%` }}
              />
            </div>
            <div className="tnum mt-1 flex justify-between text-[11px] text-dim">
              <span>#{interval[0]}</span>
              <span>
                point estimate #{doc.overall_rank}
              </span>
              <span>#{interval[1]}</span>
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-dim">
              The band is where this district lands across 400 Monte-Carlo runs
              that vary weights, normalisation, aggregation and one
              leave-one-indicator-out draw. A rank is a point on a distribution,
              not a fact.
            </p>
          </div>
        )}

        {/* pillars */}
        {Object.keys(pillars).length > 0 && (
          <div>
            <div className="h-eyebrow mb-2">Pillar scores (0–100)</div>
            <div className="space-y-2">
              {PILLAR_ORDER.filter((p) => pillars[p] !== undefined).map((p) => (
                <div key={p}>
                  <div className="flex items-baseline justify-between text-[11px]">
                    <span className="text-dim">{PILLAR_LABEL[p]}</span>
                    <span className="tnum text-bright">{num(pillars[p])}</span>
                  </div>
                  <div className="mt-1">
                    <Bar value={pillars[p] ?? 0} color={scale.color(pillars[p] ?? 0)} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* size vs quality */}
        {(doc.size_score !== undefined || doc.quality_score !== undefined) && (
          <div className="rounded border border-line px-3 py-2">
            <div className="h-eyebrow mb-1">Decomposition</div>
            <Row k="Size factor (patient pool × urbanisation)" v={num(doc.size_score)} />
            <Row k="Quality factor (per-capita attractiveness)" v={num(doc.quality_score)} />
            <p className="mt-2 text-[11px] leading-relaxed text-dim">
              MAI = 100 · size<sup>0.5</sup> · quality<sup>0.5</sup>. The
              geometric form means a district cannot buy its way to the top on
              headcount alone — a zero on either factor cannot be compensated.
            </p>
          </div>
        )}

        {/* current vs future */}
        {cvf && (
          <div className="rounded border border-line px-3 py-2">
            <div className="h-eyebrow mb-1">Current vs projected</div>
            <Row k="Current score / rank" v={`${num(cvf.current_score)} · #${int(cvf.current_rank)}`} />
            <Row k="Projected score / rank" v={`${num(cvf.projected_score)} · #${int(cvf.projected_rank)}`} />
            <Row
              k="Rank movement"
              v={
                <span
                  className={
                    cvf.current_rank - cvf.projected_rank > 0 ? 'text-accent' : 'text-dim'
                  }
                >
                  {cvf.current_rank - cvf.projected_rank > 0 ? '▲' : '▼'}{' '}
                  {Math.abs(cvf.current_rank - cvf.projected_rank)}
                </span>
              }
            />
            <Row k="Growth gap" v={num(cvf.growth_gap)} />
            {cvf.growth_flag && (
              <div className="mt-2 rounded border border-accent/40 px-2 py-1 text-[11px] text-accent">
                Invest-ahead candidate — momentum in the top quartile while the
                current index sits outside the top 100.
              </div>
            )}
          </div>
        )}

        {/* narrative */}
        {doc.narrative && (
          <div>
            <div className="h-eyebrow mb-2">Field brief</div>
            <p className="text-[12.5px] leading-relaxed text-bright">{doc.narrative}</p>
            <p className="mt-2 text-[11px] leading-relaxed text-dim">
              source: {doc.narrative_source ?? 'unknown'}
              {doc.narrative_numeric_check
                ? ` · numeric check: ${doc.narrative_numeric_check}`
                : ''}
            </p>
          </div>
        )}

      </div>
    </aside>
  );
}
