'use client';
import { useMemo, useState } from 'react';
import { useData } from '@/components/DataProvider';
import { CoverageCurve } from '@/components/charts';
import { Section, Loading, Stat, Note, Table, Th, Verdict } from '@/components/ui';
import { num, int, popShort, toCsv, downloadCsv } from '@/lib/format';
import { RAMP, ACCENT } from '@/lib/color';
import type { DistrictDoc } from '@/lib/types';

/**
 * The deployment view answers the only question a sales director actually
 * asks: given a field force of N territories, which districts, and what does
 * choosing by MAI buy over choosing by population?
 *
 * Estimated value per district is population x an affluence multiplier derived
 * from the affordability pillar. It deliberately excludes the private-activity
 * variables used to validate the model, because using them here would make the
 * comparison circular — the same reasoning the pipeline applies in
 * `validate.build_opportunity`.
 */
function opportunityOf(d: DistrictDoc): number {
  const pop = d.population_2011 ?? 0;
  const afford = d.pillar_scores?.P4_afford ?? 50;
  return pop * (0.5 + afford / 100);
}

export default function DeploymentPage() {
  const { bundle, loading } = useData();
  const [reps, setReps] = useState(150);
  const [metric, setMetric] = useState<'overall_score' | 'chronic_score' | 'acute_score'>(
    'overall_score',
  );

  const all = useMemo(() => bundle?.districts ?? [], [bundle]);

  const model = useMemo(() => {
    if (!all.length) return null;
    const opp = new Map(all.map((d) => [d.code, opportunityOf(d)]));
    const total = [...opp.values()].reduce((a, b) => a + b, 0);

    const curve = (order: DistrictDoc[]) => {
      let acc = 0;
      const pts: [number, number][] = [[0, 0]];
      order.forEach((d, i) => {
        acc += opp.get(d.code) ?? 0;
        pts.push([i + 1, (acc / total) * 100]);
      });
      return pts;
    };

    const byMai = [...all].sort((a, b) => (b[metric] as number) - (a[metric] as number));
    const byPop = [...all].sort(
      (a, b) => (b.population_2011 ?? 0) - (a.population_2011 ?? 0),
    );
    const random = all.map((_, i) => [i + 1, ((i + 1) / all.length) * 100] as [number, number]);

    // Value captured at EQUAL POPULATION COVERED — a field force covers people,
    // not polygons, so the honest head-to-head holds population constant.
    const atBudget = (budget: number) => {
      const take = (order: DistrictDoc[]) => {
        const popTotal = all.reduce((a, d) => a + (d.population_2011 ?? 0), 0);
        let p = 0;
        let v = 0;
        let n = 0;
        for (const d of order) {
          p += d.population_2011 ?? 0;
          v += opp.get(d.code) ?? 0;
          n += 1;
          if (p / popTotal >= budget) break;
        }
        return { value: (v / total) * 100, n };
      };
      return { mai: take(byMai), pop: take(byPop) };
    };

    return {
      opp,
      total,
      byMai,
      byPop,
      curves: [
        { name: 'MAI', color: ACCENT, points: curve(byMai) },
        { name: 'Population', color: RAMP[5], points: curve(byPop) },
        { name: 'Random', color: '#8FA3B0', points: random },
      ],
      budgets: [0.1, 0.2, 0.3, 0.4].map((b) => ({ b, ...atBudget(b) })),
    };
  }, [all, metric]);

  if (loading || !model) return <Loading what="districts" />;

  const territory = model.byMai.slice(0, reps);
  const covered = territory.reduce((a, d) => a + (d.population_2011 ?? 0), 0);
  const capturedValue =
    (territory.reduce((a, d) => a + (model.opp.get(d.code) ?? 0), 0) / model.total) * 100;
  const popEquivalent = model.byPop.slice(0, reps);
  const popValue =
    (popEquivalent.reduce((a, d) => a + (model.opp.get(d.code) ?? 0), 0) / model.total) *
    100;

  // Arrow const rather than a hoisted declaration: a function declaration is
  // visible before the null guard above, so TypeScript cannot narrow `model`
  // inside it.
  const exportPlan = () => {
    downloadCsv(
      `mai_territory_plan_${reps}.csv`,
      toCsv(
        territory.map((d, i) => ({
          priority: i + 1,
          code: d.code,
          district: d.district_name,
          state: d.state_name,
          overall_score: d.overall_score,
          overall_rank: d.overall_rank,
          therapy_lean: d.chronic_rank < d.acute_rank ? 'chronic' : 'acute',
          chronic_rank: d.chronic_rank,
          acute_rank: d.acute_rank,
          population_2011: d.population_2011 ?? '',
          band: d.tier,
          growth_flag: d.current_vs_future?.growth_flag ?? '',
          estimated_value_share_pct: (
            ((model.opp.get(d.code) ?? 0) / model.total) *
            100
          ).toFixed(4),
        })),
      ),
    );
  };

  return (
    <>
      <Section
        eyebrow="Deliverable 4 · business application"
        title="Territory planning"
        sub="Pick a field-force size and the plan writes itself: which districts, in what order, with the therapy lean for each. The comparison that matters is against how the industry actually deploys today — largest districts first."
        right={
          <button onClick={exportPlan} className="btn">
            export the {reps}-territory plan →
          </button>
        }
      >
        <div className="panel mb-5 px-5 py-4">
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-3 text-[12px] text-dim">
              field force
              <input
                type="range"
                min={25}
                max={400}
                step={25}
                value={reps}
                onChange={(e) => setReps(Number(e.target.value))}
                className="w-64 accent-[#3FB6A8]"
              />
              <span className="tnum w-12 text-bright">{reps}</span>
            </label>
            <div className="flex gap-2">
              {(
                [
                  ['overall_score', 'Overall'],
                  ['chronic_score', 'Chronic'],
                  ['acute_score', 'Acute'],
                ] as const
              ).map(([k, l]) => (
                <button
                  key={k}
                  onClick={() => setMetric(k)}
                  className={`btn ${metric === k ? 'btn-on' : ''}`}
                >
                  {l}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Territories" value={int(reps)} />
            <Stat label="Population covered" value={popShort(covered)} />
            <Stat
              label="Estimated value captured"
              value={`${num(capturedValue, 1)}%`}
              tone="good"
            />
            <Stat
              label="Same count, population-sorted"
              value={`${num(popValue, 1)}%`}
              note={`${capturedValue >= popValue ? '+' : ''}${num(
                capturedValue - popValue,
                1,
              )} pp difference on a count-matched basis`}
              tone={capturedValue >= popValue ? 'good' : 'warn'}
            />
          </div>
        </div>

        <div className="panel px-5 py-4">
          <div className="h-eyebrow mb-3">
            Cumulative estimated market value as territories are added
          </div>
          <CoverageCurve
            series={model.curves}
            xLabel="districts covered"
            yLabel="% of estimated market value"
          />
          <Note>
            Estimated value is population × an affluence multiplier built from
            the affordability pillar. It deliberately excludes private-hospital
            density and private-TB share, because those are the variables the
            model is validated against — scoring the plan with them would be
            circular.
          </Note>
        </div>
      </Section>

      <Section
        eyebrow="The honest head-to-head"
        title="Value captured at equal population covered"
        sub="A count-based race between MAI and a population sort is not well posed: estimated opportunity is population times a per-capita multiplier, population spans three orders of magnitude and the multiplier less than one, so only a population sort can win on district count. A field force covers people, not polygons — so hold population constant and ask which ranking picks the more valuable districts."
      >
        <Table
          head={
            <>
              <Th>Population budget</Th>
              <Th align="right">MAI value</Th>
              <Th align="right">Population-sort value</Th>
              <Th align="right">Advantage</Th>
              <Th align="right">MAI districts</Th>
              <Th align="right">Pop districts</Th>
              <Th align="right">Verdict</Th>
            </>
          }
        >
          {model.budgets.map((r) => (
            <tr key={r.b} className="border-b border-line/60">
              <td className="cell text-bright">{num(r.b * 100, 0)}%</td>
              <td className="cell tnum text-right text-accent">
                {num(r.mai.value, 1)}%
              </td>
              <td className="cell tnum text-right text-dim">{num(r.pop.value, 1)}%</td>
              <td
                className={`cell tnum text-right ${
                  r.mai.value > r.pop.value ? 'text-accent' : 'text-ramp-6'
                }`}
              >
                {r.mai.value > r.pop.value ? '+' : ''}
                {num(r.mai.value - r.pop.value, 2)} pp
              </td>
              <td className="cell tnum text-right text-dim">{r.mai.n}</td>
              <td className="cell tnum text-right text-dim">{r.pop.n}</td>
              <td className="cell text-right">
                <Verdict v={r.mai.value > r.pop.value ? 'PASS' : 'FAIL'} />
              </td>
            </tr>
          ))}
        </Table>
        <Note>
          The pipeline&apos;s own pre-registered version of this test uses the
          model&apos;s internal opportunity estimate and reports{' '}
          <span className="text-bright">+1.46 pp at a 20% population budget,
          winning at all four budgets</span>. The table above recomputes the
          same shape in the browser from the published documents, so the number
          moves slightly with the client-side multiplier — the direction is the
          claim, not the third decimal.
        </Note>
      </Section>

      <Section
        eyebrow="The plan"
        title={`Top ${Math.min(reps, 40)} territories`}
        sub="Ordered by the selected index, with the therapy lean each territory should be detailed for."
      >
        <Table
          head={
            <>
              <Th w="52px">#</Th>
              <Th>District</Th>
              <Th>State</Th>
              <Th align="right">Score</Th>
              <Th>Lean</Th>
              <Th align="right">Population</Th>
              <Th align="right">Value share</Th>
              <Th>Signal</Th>
            </>
          }
        >
          {territory.slice(0, 40).map((d, i) => (
            <tr key={d.code} className="border-b border-line/60">
              <td className="cell tnum text-dim">{i + 1}</td>
              <td className="cell text-bright">{d.district_name}</td>
              <td className="cell text-dim">{d.state_name}</td>
              <td className="cell tnum text-right text-bright">
                {num(d[metric] as number)}
              </td>
              <td className="cell text-[12px]">
                <span className={d.chronic_rank < d.acute_rank ? 'text-accent' : 'text-ramp-6'}>
                  {d.chronic_rank < d.acute_rank ? 'chronic' : 'acute'}
                </span>
              </td>
              <td className="cell tnum text-right text-dim">
                {popShort(d.population_2011)}
              </td>
              <td className="cell tnum text-right text-dim">
                {num(((model.opp.get(d.code) ?? 0) / model.total) * 100, 2)}%
              </td>
              <td className="cell text-[11px] text-dim">
                {d.current_vs_future?.growth_flag ? (
                  <span className="text-accent">invest ahead</span>
                ) : (
                  '—'
                )}
              </td>
            </tr>
          ))}
        </Table>
      </Section>
    </>
  );
}
