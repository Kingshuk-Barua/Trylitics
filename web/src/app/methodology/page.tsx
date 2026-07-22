'use client';
import { useEffect, useMemo, useState } from 'react';
import { loadMethodology } from '@/lib/data';
import { BarList } from '@/components/charts';
import { Section, Loading, Note, Table, Th, Stat } from '@/components/ui';
import { num, int, PILLAR_LABEL } from '@/lib/format';
import { RAMP } from '@/lib/color';
import type { Methodology } from '@/lib/types';

const PILLAR_RATIONALE: Record<string, string> = {
  P2_chronic:
    'Chronic disease burden and the treatment-seeking that follows it — blood sugar, blood pressure, obesity, waist-hip ratio, tobacco and alcohol, plus the share already medicating. Age enters inverted: an older population is more chronic-attractive, not less.',
  P2_acute:
    'Acute and infectious burden — anaemia, ARI, diarrhoea, stunting, underweight, TB notification rate — with water and sanitation entering negatively, and the 0–6 share carrying the paediatric segment.',
  P3_access:
    'Whether a prescription can physically be filled: institutional births, skilled attendance, vaccination coverage, antenatal care, private-facility vaccination and empanelled hospital density.',
  P4_afford:
    'Ability to pay. Health insurance, female literacy, electrification, clean cooking fuel, and the SECC income, deprivation and vehicle-ownership variables — the only genuine ability-to-pay data in the model. Out-of-pocket spend enters as wallet size.',
  P5_mom_chronic: 'Rising metabolic burden and procedure intensity — the leading edge of chronic demand.',
  P5_mom_acute: 'Direction of travel on anaemia and diarrhoea burden.',
  P5_mom_adoption: 'Whether formal care is being adopted faster than the base rate.',
};

export default function MethodologyPage() {
  const [m, setM] = useState<Methodology | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    loadMethodology()
      .then(setM)
      .catch((e: unknown) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  const weights = useMemo(
    () =>
      m
        ? Object.entries(m.quality_weights).map(([k, v]) => ({
            label: PILLAR_LABEL[k] ?? k,
            value: v * 100,
          }))
        : [],
    [m],
  );

  if (err) return <div className="panel px-4 py-4 text-[12px] text-ramp-6">{err}</div>;
  if (!m) return <Loading what="the run record" />;

  return (
    <>
      <Section
        eyebrow="Deliverable 3 · methodology"
        title="How a score is built"
        sub="Ten steps of the OECD/JRC composite-indicator handbook, with the choices that differ from the default stated and defended rather than assumed."
      >
        <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Districts" value={int(m.n_districts)} />
          <Stat label="Indicators retained" value={int(m.n_indicators)} />
          <Stat label="Pillars" value={int(Object.keys(m.pillar_composition).length)} />
          <Stat label="Seed" value={int(m.seed)} note={m.git_sha?.slice(0, 10) ?? ''} />
        </div>

        <div className="panel px-5 py-4">
          <div className="h-eyebrow mb-3">The formula</div>
          <p className="tnum text-[15px] text-bright">
            MAI = 100 · Size<sup>{num(m.alpha, 2)}</sup> · Quality
            <sup>{num(1 - m.alpha, 2)}</sup>
          </p>
          <p className="mt-3 text-[13px] leading-relaxed text-dim">{m.method}</p>
          <div className="mt-4 grid gap-4 md:grid-cols-3">
            <div>
              <div className="h-eyebrow mb-1">Why geometric</div>
              <p className="text-[12px] leading-relaxed text-dim">
                A geometric mean is only partially compensatory: a district
                cannot offset a near-zero on ability-to-pay with sheer
                headcount. An arithmetic mean would let population buy the top
                of the table, which is exactly the industry practice the brief
                asks us to improve on.
              </p>
            </div>
            <div>
              <div className="h-eyebrow mb-1">Why rank normalisation</div>
              <p className="text-[12px] leading-relaxed text-dim">
                Inputs span Census 2011, SECC 2011, NFHS-5 2019–21 and
                current-year TB notifications. Absolute levels are not
                comparable across that span, but district ORDERING is stable —
                so ranks are the vintage-robust choice, and they are invariant
                to any monotone transform, which removes winsorisation from the
                pipeline entirely.
              </p>
            </div>
            <div>
              <div className="h-eyebrow mb-1">Why size is not a pillar</div>
              <p className="text-[12px] leading-relaxed text-dim">
                Treating population, urbanisation and age as a reflective scale
                gives Cronbach α = −0.432 — they do not measure a common latent
                construct. They are formative drivers of market size and enter
                through a separate multiplicative term.
              </p>
            </div>
          </div>
        </div>
      </Section>

      <Section
        eyebrow="Deliverable 2 · variable selection"
        title="Pillars and weights"
        sub="Weights are stated, not discovered. The broken PCA and entropy schemes from v1 were removed rather than repaired — taking the absolute value of the first component is not a PCA weighting, and entropy applied to pre-aggregated composites inverts the method."
      >
        <div className="grid gap-5 lg:grid-cols-[380px_minmax(0,1fr)]">
          <div className="panel px-5 py-4">
            <div className="h-eyebrow mb-3">Quality weights (%)</div>
            <BarList
              rows={weights}
              max={30}
              colorOf={(_, i) => RAMP[Math.min(5, i + 1)]}
              format={(v) => `${num(v, 1)}%`}
            />
            <Note>
              Momentum carries 10% in total precisely because it is the least
              reliable content in the model: NFHS deltas are differences of two
              survey estimates and sampling noise dominates. Weighting it like
              the level pillars would import that noise into the ranking.
            </Note>
          </div>
          <div className="space-y-3">
            {Object.entries(m.pillar_composition).map(([p, fields]) => (
              <div key={p} className="panel px-4 py-3">
                <div className="flex items-baseline justify-between">
                  <span className="font-display text-[14px] text-bright">
                    {PILLAR_LABEL[p] ?? p}
                  </span>
                  <span className="tnum text-[11px] text-dim">
                    {fields.length} indicators ·{' '}
                    {num((m.quality_weights[p] ?? 0) * 100, 1)}% weight
                  </span>
                </div>
                <p className="mt-1.5 text-[12px] leading-relaxed text-dim">
                  {PILLAR_RATIONALE[p]}
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {fields.map((f) => (
                    <span
                      key={f}
                      className="tnum rounded border border-line px-1.5 py-0.5 text-[10px] text-dim"
                      title={
                        m.indicator_directions[f] === 1
                          ? 'higher is more attractive'
                          : 'lower is more attractive'
                      }
                    >
                      {f}
                      <span
                        className={
                          m.indicator_directions[f] === 1 ? 'text-accent' : 'text-ramp-6'
                        }
                      >
                        {m.indicator_directions[f] === 1 ? ' +' : ' −'}
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </Section>

      <Section
        eyebrow="Index construction"
        title="Which pillars enter which index"
        sub="The therapy indices are not re-weightings of the same pillar set — each drops the burden pillar that does not belong to it, and each is multiplied by a therapy-specific patient pool rather than by raw headcount."
      >
        <Table
          head={
            <>
              <Th>Index</Th>
              <Th>Pillars included</Th>
            </>
          }
        >
          {Object.entries(m.index_pillars).map(([idx, ps]) => (
            <tr key={idx} className="border-b border-line/60">
              <td className="cell text-bright">{idx}</td>
              <td className="cell text-[12px] text-dim">
                {ps.map((p) => PILLAR_LABEL[p] ?? p).join(' · ')}
              </td>
            </tr>
          ))}
        </Table>
        <Note>
          Patient pool = population × prevalence × relevant age share, computed
          separately for chronic and acute. Without it the two therapy indices
          would share an identical size term and their correlation would rise to
          0.963; with it, 0.851.
        </Note>
      </Section>

      <Section
        eyebrow="Data"
        title="Vintage and provenance"
        sub="Levels are fused across vintages, which is a real limitation and the reason rank normalisation was chosen rather than a convenience."
      >
        <Table
          head={
            <>
              <Th>Source</Th>
              <Th>Vintage</Th>
            </>
          }
        >
          {Object.entries(m.data_vintage).map(([k, v]) => (
            <tr key={k} className="border-b border-line/60">
              <td className="cell text-bright">{k}</td>
              <td className="cell text-[12px] text-dim">{v}</td>
            </tr>
          ))}
        </Table>
        <Note>
          {m.nfhs4_sentinel_fields.length} NFHS-4 sentinel fields were detected
          by measurement rather than hard-coded — v1 hard-coded two, which
          silently corrupted the momentum deltas for every field it missed.
        </Note>
      </Section>
    </>
  );
}
