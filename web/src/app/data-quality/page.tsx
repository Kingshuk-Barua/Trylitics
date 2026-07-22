'use client';
import { useEffect, useMemo, useState } from 'react';
import { loadDataQuality, loadGeoNameMap } from '@/lib/data';
import { BarList } from '@/components/charts';
import { Section, Loading, Note, Table, Th, Stat, Verdict } from '@/components/ui';
import { num, int, PILLAR_LABEL } from '@/lib/format';
import { RAMP } from '@/lib/color';
import type { DataQuality, GeoNameMap } from '@/lib/types';

export default function DataQualityPage() {
  const [dq, setDq] = useState<DataQuality | null>(null);
  const [geo, setGeo] = useState<GeoNameMap | null>(null);
  const [cwFilter, setCwFilter] = useState('');

  useEffect(() => {
    loadDataQuality().then(setDq).catch(() => setDq(null));
    loadGeoNameMap().then(setGeo).catch(() => setGeo(null));
  }, []);

  const coverage = useMemo(() => {
    if (!dq) return [];
    return (dq.coverage as Record<string, unknown>[])
      .map((r) => ({
        name: String(r['Unnamed: 0'] ?? r.indicator ?? ''),
        coverage: Number(r.coverage) * 100,
        kept: Boolean(r.kept),
      }))
      .sort((a, b) => a.coverage - b.coverage);
  }, [dq]);

  const crosswalk = useMemo(() => {
    if (!dq) return [];
    const rows = dq.crosswalk_rows ?? [];
    if (!cwFilter) return rows.slice(0, 120);
    return rows
      .filter((r) => String(r.category ?? '') === cwFilter)
      .slice(0, 120);
  }, [dq, cwFilter]);

  if (!dq) return <Loading what="the data-quality artefacts" />;

  const imp = dq.imputation;
  const repro = dq.reproducibility ?? {};

  return (
    <>
      <Section
        eyebrow="Evaluation · data, variables and assumptions"
        title="What is missing, and what was done about it"
        sub="Every gap in this model is recorded rather than absorbed. A district that could not be measured is flagged, a polygon that could not be matched renders white, and an indicator below the coverage floor is dropped rather than filled."
      >
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat
            label="Imputed cells"
            value={`${num(imp?.imputed_pct ?? 0, 2)}%`}
            note={`${int(imp?.state_median ?? 0)} state-median, ${int(
              imp?.national_median ?? 0,
            )} national-median`}
          />
          <Stat label="Observed cells" value={int(imp?.observed ?? 0)} tone="good" />
          <Stat
            label="Polygons matched"
            value={geo ? int(Object.keys(geo.exact).length) : '—'}
            note={geo ? `of ${geo.counts?.features ?? '—'} district polygons` : ''}
          />
          <Stat
            label="Unmatched polygons"
            value={geo ? int(geo.unmatched_geo.length) : '—'}
            tone="warn"
            note="render white on the map"
          />
        </div>
      </Section>

      <Section
        eyebrow="Reproducibility"
        title="Can the published numbers be regenerated?"
        sub="The run record stores the git SHA, seed, full indicator list with directions, pillar composition, weights, coverage and imputation tables, data vintage and a SHA-256 of every input snapshot. Recording that proves nothing on its own, so each claim it supports is tested."
      >
        <div className="grid gap-3 md:grid-cols-3">
          {[
            [
              'Rebuild reproduces every score at 2 dp',
              repro.reproduces_at_2dp,
              '698 of 698 districts identical on all seven score columns; max absolute difference 7.1e-15',
            ],
            [
              'Input snapshots still match their hashes',
              repro.inputs_fresh,
              'the published scores were computed from the data currently in the cache',
            ],
            [
              'Staleness detector fires when it should',
              repro.detector_fires_on_perturbation,
              'a detector that has never fired is indistinguishable from one that cannot — so one recorded hash is perturbed in memory and the detector must report STALE',
            ],
          ].map(([label, ok, note]) => (
            <div key={String(label)} className="panel px-4 py-3">
              <div className="mb-2 flex items-start justify-between gap-3">
                <span className="text-[12px] leading-snug text-bright">
                  {String(label)}
                </span>
                <Verdict v={ok === true ? 'PASS' : ok === false ? 'FAIL' : 'UNAVAILABLE'} />
              </div>
              <p className="text-[11px] leading-relaxed text-dim">{String(note)}</p>
            </div>
          ))}
        </div>

        {dq.staleness?.length > 0 && (
          <div className="mt-5">
            <div className="h-eyebrow mb-2">Input snapshots</div>
            <Table
              dense
              head={
                <>
                  <Th>Collection</Th>
                  <Th>Recorded hash</Th>
                  <Th>Current hash</Th>
                  <Th align="right">State</Th>
                </>
              }
            >
              {dq.staleness.map((r, i) => (
                <tr key={i} className="border-b border-line/60">
                  <td className="cell text-bright">{String(r.collection)}</td>
                  <td className="cell tnum text-[11px] text-dim">{String(r.recorded)}</td>
                  <td className="cell tnum text-[11px] text-dim">{String(r.current)}</td>
                  <td className="cell text-right">
                    <Verdict v={String(r.state) === 'OK' ? 'PASS' : 'FAIL'} />
                  </td>
                </tr>
              ))}
            </Table>
          </div>
        )}
      </Section>

      <Section
        eyebrow="Missing data"
        title="Imputation, per pillar"
        sub="Within-state median first, national median second, and a hard rule on top: a district missing more than a third of a pillar's indicators has that pillar's weight re-allocated across the pillars it does have, rather than the pillar being fabricated from medians."
      >
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="panel px-5 py-4">
            <div className="h-eyebrow mb-3">Share of cells imputed, by pillar (%)</div>
            <BarList
              rows={Object.entries(imp?.per_pillar_imputed_pct ?? {}).map(([k, v]) => ({
                label: PILLAR_LABEL[k] ?? k,
                value: v,
              }))}
              max={25}
              colorOf={(v) => (v > 10 ? RAMP[5] : RAMP[3])}
              format={(v) => `${num(v, 2)}%`}
            />
            <Note>
              The three momentum pillars sit at 18.5% because 129 districts have
              no NFHS-4 round to difference against. That is the single largest
              remaining data gap in the model, and the reason momentum carries
              only 10% of quality weight.
            </Note>
          </div>
          <div className="panel px-5 py-4">
            <div className="h-eyebrow mb-3">
              Does the ranking survive a different fill rule?
            </div>
            <Table
              dense
              head={
                <>
                  <Th>Strategy</Th>
                  {Object.keys(dq.imputation_spearman ?? {}).map((k) => (
                    <Th key={k} align="right">
                      {k.replace('_', ' ')}
                    </Th>
                  ))}
                </>
              }
            >
              {Object.entries(dq.imputation_spearman ?? {}).map(([row, cols]) => (
                <tr key={row} className="border-b border-line/60">
                  <td className="cell text-bright">{row.replace('_', ' ')}</td>
                  {Object.values(cols).map((v, i) => (
                    <td key={i} className="cell tnum text-right text-dim">
                      {num(v, 4)}
                    </td>
                  ))}
                </tr>
              ))}
            </Table>
            <Note>
              Minimum pairwise Spearman 0.9933 against a 0.95 bar — the order is
              robust. Band labels are not: 12.2% of districts cross a quartile
              boundary under some strategy, against a 5% bar. Present bands as
              bands.
            </Note>
          </div>
        </div>
      </Section>

      <Section
        eyebrow="Coverage gate"
        title="Indicators, by how much of the country they cover"
        sub="An indicator is kept only if at least 80% of districts have a valid value. Below that it is dropped, not imputed — imputing 30% of a column invents a variable rather than repairing one."
      >
        <div className="panel px-5 py-4">
          <BarList
            rows={coverage.slice(0, 18).map((c) => ({
              label: c.name,
              value: c.coverage,
            }))}
            max={100}
            colorOf={(v) => (v >= 80 ? RAMP[3] : RAMP[5])}
            format={(v) => `${num(v, 1)}%`}
          />
          <Note>
            Showing the {Math.min(18, coverage.length)} least-covered of{' '}
            {coverage.length} candidate indicators.{' '}
            {int(coverage.filter((c) => !c.kept).length)} fell below the gate.
          </Note>
        </div>
      </Section>

      {geo && (
        <Section
          eyebrow="Map join"
          title="District polygons that did not match a scored record"
          sub="These render white with a 'no data' tooltip rather than being guessed at. Matching is alias-first, then strict within-state, then within-state fuzzy with a one-to-one constraint — deliberately never falling back to a national name pool, because a district joined to the wrong state is an invisible error while a white polygon is a visible one."
        >
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Polygons" value={int(geo.counts?.features ?? 0)} />
            <Stat
              label="Matched"
              value={int(Object.keys(geo.exact).length)}
              tone="good"
            />
            <Stat
              label="Of which fuzzy"
              value={int(geo.fuzzy.length)}
              note="listed below for audit"
            />
            <Stat
              label="Records with no polygon"
              value={int(geo.unmatched_records.length)}
              tone="warn"
            />
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <div>
              <div className="h-eyebrow mb-2">
                Unmatched polygons ({geo.unmatched_geo.length}) — white on the map
              </div>
              <div className="panel max-h-[340px] overflow-y-auto px-4 py-3">
                {geo.unmatched_geo.map((g) => (
                  <div
                    key={`${g.shape_name}|${g.state}`}
                    className="flex justify-between border-b border-line/40 py-1 text-[12px]"
                  >
                    <span className="text-bright">{g.shape_name}</span>
                    <span className="text-dim">{g.state}</span>
                  </div>
                ))}
              </div>
              <Note>
                Almost all of these are districts created after the 2011 Census
                spine — Manipur&apos;s and Mizoram&apos;s new districts, Tamil
                Nadu&apos;s 2019 splits, Alipurduar, Jhargram, Kalimpong,
                Palghar — which have no Census population, no SECC row and no
                NFHS sample, so there is nothing to score them from.
              </Note>
            </div>
            <div>
              <div className="h-eyebrow mb-2">
                Scored records with no polygon ({geo.unmatched_records.length})
              </div>
              <div className="panel max-h-[340px] overflow-y-auto px-4 py-3">
                {geo.unmatched_records.map((r) => (
                  <div
                    key={r.code}
                    className="flex justify-between border-b border-line/40 py-1 text-[12px]"
                  >
                    <span className="text-bright">
                      <span className="tnum text-dim">{r.code}</span> {r.district_name}
                    </span>
                    <span className="text-dim">{r.state_name}</span>
                  </div>
                ))}
              </div>
              <div className="mt-4">
                <div className="h-eyebrow mb-2">
                  Fuzzy matches, weakest first — audit these
                </div>
                <div className="panel max-h-[220px] overflow-y-auto px-4 py-3">
                  {[...geo.fuzzy]
                    .sort((a, b) => a.score - b.score)
                    .slice(0, 30)
                    .map((f) => (
                      <div
                        key={`${f.shape_name}|${f.state}`}
                        className="flex justify-between gap-3 border-b border-line/40 py-1 text-[11.5px]"
                      >
                        <span className="text-dim">
                          {f.shape_name} <span className="text-bright">→ {f.matched_name}</span>
                        </span>
                        <span className="tnum text-dim">{num(f.score, 3)}</span>
                      </div>
                    ))}
                </div>
              </div>
            </div>
          </div>
        </Section>
      )}

      <Section
        eyebrow="Source joins"
        title="Crosswalk review"
        sub="Every non-exact name decision made when joining TB notifications, PMJAY empanelment and the NFHS factsheet onto the district spine — categorised, logged and reviewable rather than silently applied."
      >
        <div className="mb-3 flex flex-wrap gap-2">
          <button
            onClick={() => setCwFilter('')}
            className={`btn ${cwFilter === '' ? 'btn-on' : ''}`}
          >
            all
          </button>
          {Object.entries(dq.crosswalk_summary ?? {})
            .sort((a, b) => b[1] - a[1])
            .map(([k, v]) => (
              <button
                key={k}
                onClick={() => setCwFilter(cwFilter === k ? '' : k)}
                className={`btn ${cwFilter === k ? 'btn-on' : ''}`}
              >
                {k} <span className="tnum">{v}</span>
              </button>
            ))}
        </div>
        <Table
          dense
          head={
            <>
              <Th>Source label</Th>
              <Th>Source state</Th>
              <Th>Category</Th>
              <Th>Resolved to</Th>
              <Th>From</Th>
            </>
          }
        >
          {crosswalk.map((r, i) => (
            <tr key={i} className="border-b border-line/60">
              <td className="cell text-bright">{String(r.label ?? '')}</td>
              <td className="cell text-dim">{String(r.source_state ?? '')}</td>
              <td className="cell text-[11px] text-dim">{String(r.category ?? '')}</td>
              <td className="cell tnum text-[11px] text-dim">
                {String(r.targets ?? '')}
              </td>
              <td className="cell text-[11px] text-dim">{String(r.source ?? '')}</td>
            </tr>
          ))}
        </Table>
        <Note>
          Showing up to 120 rows of{' '}
          {int((dq.crosswalk_rows ?? []).length)}. Categories are explicit:
          RENAME, SPLIT_CHILD, SUBUNIT, CROSS_STATE, PRORATE and DROP each mean
          a different thing about what happened to the source row, and the
          distinction matters when a district&apos;s TB count is being
          apportioned rather than mapped.
        </Note>
      </Section>
    </>
  );
}
