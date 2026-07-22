'use client';
import Link from 'next/link';
import { useMemo } from 'react';
import { useData } from '@/components/DataProvider';
import { MapView } from '@/components/MapView';
import { Histogram, BarList } from '@/components/charts';
import { Section, Stat, Loading, Note, Table, Th } from '@/components/ui';
import { num, int, popShort } from '@/lib/format';
import { percentileScale, RAMP } from '@/lib/color';

export default function Home() {
  const { bundle, loading, states } = useData();
  const d = useMemo(() => bundle?.districts ?? [], [bundle]);

  const stats = useMemo(() => {
    if (!d.length) return null;
    const scores = d.map((x) => x.overall_score);
    const pop = d.reduce((a, x) => a + (x.population_2011 ?? 0), 0);
    const tiers = new Map<string, number>();
    for (const x of d) tiers.set(x.tier, (tiers.get(x.tier) ?? 0) + 1);
    const flagged = d.filter((x) => x.current_vs_future?.growth_flag).length;
    return {
      scores,
      pop,
      min: Math.min(...scores),
      max: Math.max(...scores),
      tiers: [...tiers.entries()].sort(),
      flagged,
    };
  }, [d]);

  const top = d.slice(0, 12);
  const scale = useMemo(() => percentileScale(d.map((x) => x.overall_score)), [d]);

  if (loading || !stats) return <Loading what="the index" />;

  return (
    <>
      <section className="mb-14">
        <div className="h-eyebrow mb-3">Sun Pharma · Trilytics 2026</div>
        <h1 className="max-w-4xl font-display text-[38px] leading-[1.12] tracking-[-0.01em] text-bright">
          A district-level market attractiveness index for Indian pharma —
          <span className="text-accent">
            {' '}
            built, stress-tested, and reported with its failures intact.
          </span>
        </h1>
        <p className="mt-5 max-w-3xl text-[14px] leading-relaxed text-dim">
          {d.length} districts scored on three indices — overall, chronic
          therapy and acute therapy — from {bundle?.run?.n_indicators ?? 42}{' '}
          indicators across disease burden, access, affordability and momentum.
          Every score carries a rank interval, an imputation flag and the run
          that produced it. The validation pages show the tests that failed as
          prominently as the ones that passed.
        </p>

        <div className="mt-8 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          <Stat label="Districts scored" value={int(d.length)} />
          <Stat
            label="Population covered"
            value={popShort(stats.pop)}
            note="Census 2011 base"
          />
          <Stat label="Indicators" value={int(bundle?.run?.n_indicators ?? 42)} />
          <Stat
            label="Index range"
            value={`${num(stats.min, 1)}–${num(stats.max, 1)}`}
            note="of 100"
          />
          <Stat
            label="Imputed cells"
            value={`${num(bundle?.run?.imputation?.imputed_pct ?? 0, 1)}%`}
            note="flagged per district"
          />
          <Stat
            label="Invest-ahead flags"
            value={int(stats.flagged)}
            tone="good"
            note="momentum top quartile, current rank > 100"
          />
        </div>
      </section>

      <Section
        eyebrow="Deliverable 5 · visualisation"
        title="Where the opportunity is"
        sub="Each district is shaded by its own index percentile. Click a state to drill in, a district for its full record."
        right={
          <Link href="/map/" className="btn">
            full map →
          </Link>
        }
      >
        <MapView compact />
      </Section>

      <div className="mb-16 grid gap-5 lg:grid-cols-2">
        <div className="panel px-5 py-4">
          <div className="h-eyebrow mb-3">Score distribution</div>
          <Histogram values={stats.scores} label="overall MAI" />
          <Note>
            v1 compressed 698 districts into a 28.5-point range; v2 spreads them
            across {num(stats.max - stats.min, 1)} points. A composite that
            cannot separate its units cannot rank them, so range is a
            correctness property here, not a cosmetic one.
          </Note>
        </div>
        <div className="panel px-5 py-4">
          <div className="h-eyebrow mb-3">Band distribution</div>
          <BarList
            rows={stats.tiers.map(([t, n]) => ({ label: `Band ${t}`, value: n }))}
            colorOf={(_, i) => RAMP[Math.min(RAMP.length - 1, 5 - i)]}
            format={(v) => int(v)}
          />
          <Note>
            Bands are quartiles of the index and are presented as bands, never
            as categories. Under a change of imputation rule 12.2% of districts
            cross a band boundary while the ranking itself holds at ρ ≥ 0.993 —
            so the order is robust and the label is not.
          </Note>
        </div>
      </div>

      <Section
        eyebrow="Deliverable 1 · index output"
        title="Top districts by overall attractiveness"
        right={
          <Link href="/districts/" className="btn">
            all {d.length} districts →
          </Link>
        }
      >
        <Table
          head={
            <>
              <Th w="52px">#</Th>
              <Th>District</Th>
              <Th>State</Th>
              <Th align="right">Overall</Th>
              <Th align="right">Chronic</Th>
              <Th align="right">Acute</Th>
              <Th align="right">Population</Th>
              <Th align="right">Interval</Th>
            </>
          }
        >
          {top.map((x) => (
            <tr
              key={x.code}
              className="border-b border-line/60 transition-colors duration-[160ms] hover:bg-[#1F2A35]/40"
            >
              <td className="cell tnum text-dim">{x.overall_rank}</td>
              <td className="cell text-bright">{x.district_name}</td>
              <td className="cell text-dim">{x.state_name}</td>
              <td className="cell tnum text-right">
                <span
                  className="inline-block h-2 w-2 rounded-sm align-middle"
                  style={{ background: scale.color(x.overall_score) }}
                />{' '}
                <span className="text-bright">{num(x.overall_score)}</span>
              </td>
              <td className="cell tnum text-right text-dim">
                {num(x.chronic_score)}{' '}
                <span className="text-[10px]">#{x.chronic_rank}</span>
              </td>
              <td className="cell tnum text-right text-dim">
                {num(x.acute_score)}{' '}
                <span className="text-[10px]">#{x.acute_rank}</span>
              </td>
              <td className="cell tnum text-right text-dim">
                {popShort(x.population_2011)}
              </td>
              <td className="cell tnum text-right text-dim">
                {x.rank_interval_p5_p95
                  ? `${x.rank_interval_p5_p95[0]}–${x.rank_interval_p5_p95[1]}`
                  : '—'}
              </td>
            </tr>
          ))}
        </Table>
      </Section>

      <Section
        eyebrow="Coverage"
        title={`${states.length} states and union territories`}
        sub="State means are a rollup of district scores, never a substitute for them — the whole point of the framework is that opportunity varies inside a state more than between states."
        right={
          <Link href="/states/" className="btn">
            state league table →
          </Link>
        }
      >
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-[12px] md:grid-cols-4">
          {states.map((s) => (
            <div
              key={s.name}
              className="flex justify-between border-b border-line/40 py-1"
            >
              <span className="truncate text-dim">{s.name}</span>
              <span className="tnum text-bright">{s.count}</span>
            </div>
          ))}
        </div>
      </Section>
    </>
  );
}
