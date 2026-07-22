'use client';
import { useMemo, useState } from 'react';
import { useData } from '@/components/DataProvider';
import { Scatter, BarList } from '@/components/charts';
import { DistrictDrawer } from '@/components/DistrictDrawer';
import { Section, Loading, Stat, Note, Table, Th, Verdict } from '@/components/ui';
import { num, int, PILLAR_LABEL } from '@/lib/format';
import { RAMP } from '@/lib/color';

/** Spearman on ranks — the same statistic the pipeline reports. */
function spearman(a: number[], b: number[]): number {
  const rank = (xs: number[]) => {
    const idx = xs.map((v, i) => [v, i] as const).sort((p, q) => p[0] - q[0]);
    const r = new Array(xs.length).fill(0);
    idx.forEach(([, i], k) => (r[i] = k + 1));
    return r;
  };
  const ra = rank(a);
  const rb = rank(b);
  const n = a.length;
  const ma = ra.reduce((x, y) => x + y, 0) / n;
  const mb = rb.reduce((x, y) => x + y, 0) / n;
  let num2 = 0;
  let da = 0;
  let db = 0;
  for (let i = 0; i < n; i++) {
    num2 += (ra[i] - ma) * (rb[i] - mb);
    da += (ra[i] - ma) ** 2;
    db += (rb[i] - mb) ** 2;
  }
  return num2 / Math.sqrt(da * db);
}

export default function TherapyPage() {
  const { bundle, loading } = useData();
  const [pick, setPick] = useState<string | null>(null);
  const d = useMemo(() => bundle?.districts ?? [], [bundle]);

  const rho = useMemo(
    () =>
      d.length
        ? spearman(d.map((x) => x.chronic_score), d.map((x) => x.acute_score))
        : NaN,
    [d],
  );

  const divergent = useMemo(
    () =>
      [...d]
        .map((x) => ({ ...x, gap: x.acute_rank - x.chronic_rank }))
        .sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap))
        .slice(0, 14),
    [d],
  );

  const pillarMeans = useMemo(() => {
    if (!d.length || !d[0].pillar_scores) return [];
    const keys = Object.keys(d[0].pillar_scores);
    return keys.map((k) => ({
      label: PILLAR_LABEL[k] ?? k,
      value:
        d.reduce((a, x) => a + (x.pillar_scores?.[k as never] ?? 0), 0) / d.length,
    }));
  }, [d]);

  if (loading) return <Loading what="districts" />;

  return (
    <>
      <Section
        eyebrow="Deliverable 1 · three indices"
        title="Chronic versus acute"
        sub="The brief asks for three indices, which is only worth doing if the therapy indices actually disagree. They share a size term by construction — the same people live in both markets — so the question is whether the per-capita content differs, and where."
      >
        <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat
            label="Spearman(chronic, acute)"
            value={num(rho, 3)}
            note="v1 was 0.676; v2 is higher because the size repair added a shared component"
            tone={rho < 0.95 ? 'normal' : 'warn'}
          />
          <Stat
            label="Districts ranking 100+ places apart"
            value={int(
              d.filter((x) => Math.abs(x.acute_rank - x.chronic_rank) >= 100).length,
            )}
            tone="good"
            note="where the therapy call actually changes the plan"
          />
          <Stat
            label="Chronic-leaning districts"
            value={int(d.filter((x) => x.chronic_rank < x.acute_rank).length)}
          />
          <Stat
            label="Acute-leaning districts"
            value={int(d.filter((x) => x.acute_rank < x.chronic_rank).length)}
          />
        </div>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="panel px-4 py-4">
            <div className="h-eyebrow mb-3">
              Every district — chronic index against acute index
            </div>
            <Scatter
              points={d.map((x) => ({
                x: x.chronic_score,
                y: x.acute_score,
                label: `${x.district_name}, ${x.state_name}`,
                sub: `chronic ${num(x.chronic_score)} (#${x.chronic_rank}) · acute ${num(
                  x.acute_score,
                )} (#${x.acute_rank})`,
                code: x.code,
              }))}
              xLabel="chronic therapy index"
              yLabel="acute therapy index"
              diagonal
              onPick={setPick}
            />
            <Note>
              Points above the dashed line are acute-leaning, below it
              chronic-leaning. The spread around the diagonal is the entire
              commercial content of the therapy split — a perfectly diagonal
              cloud would mean two indices carrying one signal.
            </Note>
          </div>
          <div className="hidden xl:block">
            {pick ? (
              <DistrictDrawer
                doc={bundle?.byCode.get(pick) ?? null}
                total={d.length}
                allScores={d.map((x) => x.overall_score)}
                onClose={() => setPick(null)}
              />
            ) : (
              <div className="panel px-4 py-4 text-[12px] leading-relaxed text-dim">
                Click any point for the district record.
                <div className="mt-4 h-eyebrow mb-2">Mean pillar level</div>
                <BarList
                  rows={pillarMeans}
                  max={100}
                  colorOf={(_, i) => RAMP[(i % 4) + 2]}
                />
              </div>
            )}
          </div>
        </div>
      </Section>

      <Section
        eyebrow="Where it matters"
        title="Districts whose therapy call flips the plan"
        sub="Ranked by the gap between chronic and acute rank. These are the territories where a single overall score would send the wrong detailing mix."
      >
        <Table
          head={
            <>
              <Th>District</Th>
              <Th>State</Th>
              <Th align="right">Chronic rank</Th>
              <Th align="right">Acute rank</Th>
              <Th align="right">Gap</Th>
              <Th>Lean</Th>
            </>
          }
        >
          {divergent.map((x) => (
            <tr
              key={x.code}
              onClick={() => setPick(x.code)}
              className="cursor-pointer border-b border-line/60 transition-colors duration-[160ms] hover:bg-[#1F2A35]/40"
            >
              <td className="cell text-bright">{x.district_name}</td>
              <td className="cell text-dim">{x.state_name}</td>
              <td className="cell tnum text-right text-dim">#{x.chronic_rank}</td>
              <td className="cell tnum text-right text-dim">#{x.acute_rank}</td>
              <td className="cell tnum text-right text-bright">
                {Math.abs(x.gap)}
              </td>
              <td className="cell text-[12px]">
                <span className={x.gap > 0 ? 'text-accent' : 'text-ramp-6'}>
                  {x.gap > 0 ? 'chronic' : 'acute'}
                </span>
              </td>
            </tr>
          ))}
        </Table>
      </Section>

      <Section
        eyebrow="Does the split survive testing?"
        title="Discriminant validity"
        sub="The test the three-index design had never faced: each therapy index is rebuilt with every proxy-contaminating indicator removed, then correlated against an external treatment-seeking measure. The diagonal must dominate, or the split is decoration."
      >
        <Table
          head={
            <>
              <Th>Index (quality leg)</Th>
              <Th align="right">vs chronic demand proxy</Th>
              <Th align="right">vs acute demand proxy</Th>
            </>
          }
        >
          <tr className="border-b border-line/60">
            <td className="cell text-bright">quality_chronic</td>
            <td className="cell tnum text-right text-accent">+0.533</td>
            <td className="cell tnum text-right text-dim">+0.091</td>
          </tr>
          <tr>
            <td className="cell text-bright">quality_acute</td>
            <td className="cell tnum text-right text-dim">+0.300</td>
            <td className="cell tnum text-right text-accent">+0.205</td>
          </tr>
        </Table>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <div className="panel px-4 py-3">
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-dim">
                chronic proxy prefers the chronic index
              </span>
              <Verdict v="PASS" />
            </div>
            <div className="tnum mt-2 text-[18px] text-accent">+0.233 gap</div>
          </div>
          <div className="panel px-4 py-3">
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-dim">
                acute proxy prefers the acute index
              </span>
              <Verdict v="PASS" />
            </div>
            <div className="tnum mt-2 text-[18px] text-accent">+0.114 gap</div>
          </div>
          <div className="panel px-4 py-3">
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-dim">
                acute convergent level ≥ 0.40
              </span>
              <Verdict v="FAIL" />
            </div>
            <div className="tnum mt-2 text-[18px] text-ramp-6">+0.205</div>
          </div>
        </div>
        <Note>
          Reported on the quality leg deliberately. MAI = size<sup>0.5</sup> ×
          quality<sup>0.5</sup>, and size is a headcount common to both therapy
          indices, so a discriminant test at composite level would be close to
          vacuous. The acute row fails its convergent bar because private-sector
          TB share is the only district-level acute treatment-seeking measure
          available — the direction is right, the level is weak, and that is
          stated rather than smoothed over.
        </Note>
      </Section>
    </>
  );
}
