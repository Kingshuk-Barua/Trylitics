'use client';
import { useEffect, useMemo, useState } from 'react';
import { loadValidation, loadBenchmarks, loadMl } from '@/lib/data';
import { BarList } from '@/components/charts';
import { Section, Loading, Note, Table, Th, Stat, Verdict } from '@/components/ui';
import { num, int } from '@/lib/format';
import { RAMP } from '@/lib/color';
import type { ValidationRow, BenchmarkRow, MlValidation } from '@/lib/types';

/** Group the flat metric list into the four layers of the validation plan. */
function layerOf(metric: string): string {
  const m = metric.toLowerCase();
  if (m.includes('cronbach') || m.includes('kmo') || m.includes('bartlett'))
    return 'Layer 1 · statistical validity';
  if (
    m.includes('income') ||
    m.includes('development') ||
    m.includes('revealed activity') ||
    m.includes('spearman(mai')
  )
    return 'Layer 2 · construct validity';
  if (
    m.includes('lift') ||
    m.includes('population covered') ||
    m.includes('c-01') ||
    m.includes('budget') ||
    m.includes('demand') ||
    m.includes('discriminant')
  )
    return 'Layer 3 · business outcomes';
  return 'Layer 4 · stability and reproducibility';
}

export default function ValidationPage() {
  const [val, setVal] = useState<{ rows: ValidationRow[]; pass: number; fail: number } | null>(
    null,
  );
  const [bench, setBench] = useState<{ rows: BenchmarkRow[]; niti_states_used?: string[] } | null>(
    null,
  );
  const [ml, setMl] = useState<MlValidation | null>(null);
  const [only, setOnly] = useState<'all' | 'FAIL'>('all');

  useEffect(() => {
    loadValidation().then(setVal).catch(() => setVal(null));
    loadBenchmarks().then(setBench).catch(() => setBench(null));
    loadMl().then(setMl).catch(() => setMl(null));
  }, []);

  const grouped = useMemo(() => {
    if (!val) return [];
    const g = new Map<string, ValidationRow[]>();
    for (const r of val.rows) {
      if (only === 'FAIL' && r.verdict !== 'FAIL') continue;
      const k = layerOf(r.metric);
      g.set(k, [...(g.get(k) ?? []), r]);
    }
    return [...g.entries()].sort();
  }, [val, only]);

  if (!val) return <Loading what="the validation table" />;

  return (
    <>
      <Section
        eyebrow="Evaluation · model design and validation"
        title="Every test, with its threshold fixed before the value was computed"
        sub="Each metric declares its pass band in code before the number exists, and a mechanical comparison decides the verdict. That is what makes the failures below meaningful — none of them could be talked away after the fact, and none has been removed."
        right={
          <div className="flex gap-2">
            <button
              onClick={() => setOnly('all')}
              className={`btn ${only === 'all' ? 'btn-on' : ''}`}
            >
              all {val.rows.length}
            </button>
            <button
              onClick={() => setOnly('FAIL')}
              className={`btn ${only === 'FAIL' ? 'btn-on' : ''}`}
            >
              failures only ({val.fail})
            </button>
          </div>
        }
      >
        <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Passing" value={int(val.pass)} tone="good" />
          <Stat label="Failing" value={int(val.fail)} tone="warn" />
          <Stat
            label="Top-50 stability"
            value="98.2%"
            note="weights-only Monte Carlo, the test v1 reported at 95.2%"
            tone="good"
          />
          <Stat
            label="Four-axis stability"
            value="78.8%"
            note="weights × normalisation × aggregation × leave-one-out — a strictly harder test, below its 80% bar"
            tone="warn"
          />
        </div>

        {grouped.map(([layer, rows]) => (
          <div key={layer} className="mb-6">
            <div className="h-eyebrow mb-2">{layer}</div>
            <Table
              dense
              head={
                <>
                  <Th>Metric</Th>
                  <Th align="right">Value</Th>
                  <Th align="right">Verdict</Th>
                  <Th>Reading</Th>
                </>
              }
            >
              {rows.map((r) => (
                <tr key={r.metric} className="border-b border-line/60">
                  <td
                    className={`cell ${
                      r.metric.startsWith(' ') ? 'pl-8 text-dim' : 'text-bright'
                    }`}
                  >
                    {r.metric.trim()}
                  </td>
                  <td className="cell tnum text-right text-bright">
                    {r.value === null ? '—' : num(r.value, 4)}
                  </td>
                  <td className="cell text-right">
                    <Verdict v={r.verdict} />
                  </td>
                  <td className="cell text-[11px] leading-snug text-dim">{r.note}</td>
                </tr>
              ))}
            </Table>
          </div>
        ))}

        <Note>
          Two failures are structural rather than defects. The wealth-proxy test
          at composite level fails because MAI = size × quality and size is
          negatively rank-correlated with income (India&apos;s largest districts
          are poorer), so the two factors cancel; decomposed, quality vs income
          is +0.41 and the affordability pillar vs income is +0.69, both inside
          band. The legacy top-100 count test is ill-posed — opportunity is
          near-collinear with population, so only a population sort can win a
          count-based race. Both are left standing as FAIL because the
          thresholds were fixed first.
        </Note>
      </Section>

      {bench && (
        <Section
          eyebrow="Layer 2 · external benchmarks"
          title="Convergent validity against sources the model never saw"
          sub="None of these is a model input. What could not be obtained is counted in the tally rather than quietly dropped."
        >
          <Table
            head={
              <>
                <Th>Benchmark</Th>
                <Th align="right">Spearman</Th>
                <Th align="right">n</Th>
                <Th align="right">Band</Th>
                <Th align="right">Verdict</Th>
                <Th>Note</Th>
              </>
            }
          >
            {bench.rows.map((r) => (
              <tr key={r.benchmark} className="border-b border-line/60">
                <td className="cell text-bright">{r.benchmark}</td>
                <td className="cell tnum text-right text-bright">
                  {r.spearman === null ? '—' : num(r.spearman, 4)}
                </td>
                <td className="cell tnum text-right text-dim">{r.n ?? '—'}</td>
                <td className="cell tnum text-right text-dim">{r.band}</td>
                <td className="cell text-right">
                  <Verdict v={r.verdict} />
                </td>
                <td className="cell text-[11px] leading-snug text-dim">{r.note}</td>
              </tr>
            ))}
          </Table>
          <Note>
            The two UNAVAILABLE rows are genuinely blocked, not skipped.
            District NSDP is not published district-wise on the India Data
            Portal or data.gov.in; SHRUG night lights require a human to select
            tables on devdatalab.org, the S3 bucket refuses listing and guessed
            object paths return 403. Both wire in automatically if a file is
            ever supplied.
          </Note>
        </Section>
      )}

      {ml && (
        <Section
          eyebrow="Falsification"
          title="The machine-learning test, and why it partly fails"
          sub="A supervised model predicting revealed private-sector activity from the pillar scores. This is a falsification test, not a headline model — if the pillars carry real signal about where private pharma demand actually shows up, a model should find it."
        >
          <div className="grid gap-5 lg:grid-cols-2">
            <div className="panel px-5 py-4">
              <div className="h-eyebrow mb-3">
                State-blocked cross-validated R² by model
              </div>
              <BarList
                rows={Object.entries(ml.results.blocked_cv_R2).map(([k, v]) => ({
                  label: k,
                  value: v,
                }))}
                colorOf={(v) => (v > 0 ? RAMP[3] : RAMP[5])}
                format={(v) => num(v, 4)}
              />
              <Note>
                Cross-validation is <code>GroupKFold</code> blocked by state.
                State identity explains 53.6% of index variance, so a random
                split would let the model memorise the state and report that as
                skill. Blocking removes the shortcut, and the R² collapses to
                near zero — which is the honest result.
              </Note>
            </div>
            <div className="panel px-5 py-4">
              <div className="h-eyebrow mb-3">Pillar coefficients</div>
              <BarList
                rows={Object.entries(ml.coefficients).map(([k, v]) => ({
                  label: k,
                  value: v,
                }))}
                colorOf={(v) => (v >= 0 ? RAMP[3] : RAMP[5])}
                format={(v) => num(v, 4)}
              />
              <div className="mt-4 rounded border border-ramp-6/40 px-3 py-2">
                <div className="h-eyebrow mb-1 text-ramp-6">Verdict</div>
                <p className="text-[12px] leading-relaxed text-bright">{ml.verdict}</p>
                <p className="mt-2 text-[11px] leading-relaxed text-dim">
                  Two momentum pillars carry negative coefficients against
                  revealed demand. A model that produced only confirmations
                  would be a model that could not fail; this one can, and here
                  it partly does.
                </p>
              </div>
              <div className="tnum mt-3 space-y-1 text-[11px] text-dim">
                <div className="flex justify-between">
                  <span>baseline — population alone</span>
                  <span className="text-bright">
                    {num(ml.baseline_spearman_population, 3)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>baseline — quality alone</span>
                  <span className="text-bright">
                    {num(ml.baseline_spearman_quality, 3)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>districts in the test</span>
                  <span className="text-bright">{int(ml.n)}</span>
                </div>
              </div>
            </div>
          </div>
        </Section>
      )}
    </>
  );
}
