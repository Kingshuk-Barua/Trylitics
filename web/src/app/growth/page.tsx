'use client';
import { useMemo, useState } from 'react';
import { useData } from '@/components/DataProvider';
import { Scatter } from '@/components/charts';
import { DistrictDrawer } from '@/components/DistrictDrawer';
import { Section, Loading, Stat, Note, Table, Th } from '@/components/ui';
import { num, int, popShort } from '@/lib/format';

export default function GrowthPage() {
  const { bundle, loading } = useData();
  const [pick, setPick] = useState<string | null>(null);
  const d = useMemo(
    () => (bundle?.districts ?? []).filter((x) => x.current_vs_future),
    [bundle],
  );

  const movers = useMemo(
    () =>
      [...d]
        .map((x) => ({
          x,
          move: (x.current_vs_future!.current_rank - x.current_vs_future!.projected_rank),
        }))
        .sort((a, b) => b.move - a.move),
    [d],
  );

  const flagged = useMemo(
    () =>
      d
        .filter((x) => x.current_vs_future!.growth_flag)
        .sort(
          (a, b) =>
            b.current_vs_future!.growth_gap - a.current_vs_future!.growth_gap,
        ),
    [d],
  );

  if (loading) return <Loading what="districts" />;
  if (!d.length)
    return (
      <Section title="Current vs future" eyebrow="Deliverable 1 · forward view">
        <div className="panel px-4 py-4 text-[12px] text-dim">
          The loaded documents carry no <code>current_vs_future</code> block.
          That block is a v2 field — publish the v2 run to populate it.
        </div>
      </Section>
    );

  return (
    <>
      <Section
        eyebrow="Deliverable 1 · forward-looking view"
        title="Current standing versus projected opportunity"
        sub="The forward view is a momentum-adjusted projection, not a forecast, and the distinction is deliberate: NFHS deltas are differences of two survey estimates, so their sampling noise is large. Momentum therefore carries only 10% of quality weight and the projection shifts ranks rather than inventing a growth rate."
      >
        <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Districts with a projection" value={int(d.length)} />
          <Stat
            label="Invest-ahead flags"
            value={int(flagged.length)}
            tone="good"
            note="momentum in the top quartile while current rank is outside the top 100"
          />
          <Stat
            label="Largest projected climb"
            value={`+${int(movers[0]?.move ?? 0)}`}
            note={`${movers[0]?.x.district_name}, ${movers[0]?.x.state_name}`}
            tone="good"
          />
          <Stat
            label="Largest projected slide"
            value={int(movers[movers.length - 1]?.move ?? 0)}
            note={`${movers[movers.length - 1]?.x.district_name}, ${
              movers[movers.length - 1]?.x.state_name
            }`}
            tone="warn"
          />
        </div>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="panel px-4 py-4">
            <div className="h-eyebrow mb-3">Current rank against projected rank</div>
            <Scatter
              points={d.map((x) => ({
                x: x.current_vs_future!.current_rank,
                y: x.current_vs_future!.projected_rank,
                label: `${x.district_name}, ${x.state_name}`,
                sub: `#${x.current_vs_future!.current_rank} → #${
                  x.current_vs_future!.projected_rank
                } · gap ${num(x.current_vs_future!.growth_gap, 1)}`,
                code: x.code,
              }))}
              xLabel="current rank (1 = best)"
              yLabel="projected rank"
              diagonal
              onPick={setPick}
            />
            <Note>
              Points below the diagonal improve; points above slide. The
              interesting region is the lower-right — districts that are
              mediocre today and projected to climb. Those are the invest-ahead
              candidates, and they are the ones a population-sorted territory
              plan never surfaces.
            </Note>
          </div>
          <div className="hidden xl:block">
            {pick ? (
              <DistrictDrawer
                doc={bundle?.byCode.get(pick) ?? null}
                total={bundle?.districts.length ?? 0}
                allScores={(bundle?.districts ?? []).map((x) => x.overall_score)}
                onClose={() => setPick(null)}
              />
            ) : (
              <div className="panel px-4 py-4 text-[12px] leading-relaxed text-dim">
                Click a point to open the district record. The growth gap is the
                momentum percentile minus the current-index percentile — a
                continuous companion to the binary flag, so a district sitting
                just under the threshold is still visible.
              </div>
            )}
          </div>
        </div>
      </Section>

      <Section
        eyebrow="Business application"
        title="Invest-ahead shortlist"
        sub="Momentum in the top quartile while the current index sits outside the top 100. These are the districts to seed before the market arrives rather than after."
      >
        <Table
          head={
            <>
              <Th>District</Th>
              <Th>State</Th>
              <Th align="right">Current rank</Th>
              <Th align="right">Projected rank</Th>
              <Th align="right">Movement</Th>
              <Th align="right">Growth gap</Th>
              <Th align="right">Population</Th>
            </>
          }
        >
          {flagged.slice(0, 25).map((x) => {
            const c = x.current_vs_future!;
            const move = c.current_rank - c.projected_rank;
            return (
              <tr
                key={x.code}
                onClick={() => setPick(x.code)}
                className="cursor-pointer border-b border-line/60 transition-colors duration-[160ms] hover:bg-[#1F2A35]/40"
              >
                <td className="cell text-bright">{x.district_name}</td>
                <td className="cell text-dim">{x.state_name}</td>
                <td className="cell tnum text-right text-dim">#{c.current_rank}</td>
                <td className="cell tnum text-right text-dim">#{c.projected_rank}</td>
                <td
                  className={`cell tnum text-right ${
                    move > 0 ? 'text-accent' : 'text-ramp-6'
                  }`}
                >
                  {move > 0 ? '▲' : '▼'} {Math.abs(move)}
                </td>
                <td className="cell tnum text-right text-bright">
                  {num(c.growth_gap, 1)}
                </td>
                <td className="cell tnum text-right text-dim">
                  {popShort(x.population_2011)}
                </td>
              </tr>
            );
          })}
        </Table>
        <Note>
          {int(flagged.length)} districts carry the flag. The flag is a hard
          threshold on a continuous quantity, so the growth-gap column is shown
          alongside it — a district at 24.9 is not meaningfully different from
          one at 25.1, and the table should not pretend otherwise.
        </Note>
      </Section>
    </>
  );
}
