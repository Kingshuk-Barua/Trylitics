'use client';
import { useMemo, useState } from 'react';
import { useData } from '@/components/DataProvider';
import { DistrictDrawer } from '@/components/DistrictDrawer';
import { Section, Loading, Table, Th, Note } from '@/components/ui';
import { num, int, popShort, toCsv, downloadCsv, PILLAR_ORDER, PILLAR_LABEL } from '@/lib/format';
import { percentileScale } from '@/lib/color';
import type { DistrictDoc } from '@/lib/types';

type SortKey =
  | 'overall_rank' | 'overall_score' | 'chronic_score' | 'acute_score'
  | 'population_2011' | 'district_name' | 'state_name' | 'growth_gap';

export default function DistrictsPage() {
  const { bundle, loading, states } = useData();
  const [q, setQ] = useState('');
  const [state, setState] = useState('');
  const [tier, setTier] = useState('');
  const [sort, setSort] = useState<SortKey>('overall_rank');
  const [asc, setAsc] = useState(true);
  const [pick, setPick] = useState<string | null>(null);
  const [showPillars, setShowPillars] = useState(false);

  const all = useMemo(() => bundle?.districts ?? [], [bundle]);
  const scale = useMemo(
    () => percentileScale(all.map((d) => d.overall_score)),
    [all],
  );

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const filtered = all.filter((d) => {
      if (state && d.state_name !== state) return false;
      if (tier && d.tier !== tier) return false;
      if (!needle) return true;
      return (
        d.district_name.toLowerCase().includes(needle) ||
        d.state_name.toLowerCase().includes(needle) ||
        d.code.includes(needle)
      );
    });
    const val = (d: DistrictDoc): number | string => {
      if (sort === 'growth_gap') return d.current_vs_future?.growth_gap ?? 0;
      const v = d[sort as keyof DistrictDoc];
      return typeof v === 'number' ? v : String(v ?? '');
    };
    return [...filtered].sort((a, b) => {
      const av = val(a);
      const bv = val(b);
      const c =
        typeof av === 'number' && typeof bv === 'number'
          ? av - bv
          : String(av).localeCompare(String(bv));
      return asc ? c : -c;
    });
  }, [all, q, state, tier, sort, asc]);

  function head(key: SortKey, label: string, align: 'left' | 'right' = 'left') {
    return (
      <Th
        align={align}
        active={sort === key}
        onClick={() => {
          if (sort === key) setAsc(!asc);
          else {
            setSort(key);
            setAsc(key === 'overall_rank' || key === 'district_name' || key === 'state_name');
          }
        }}
      >
        {label}
        {sort === key ? (asc ? ' ↑' : ' ↓') : ''}
      </Th>
    );
  }

  function exportCsv() {
    const flat = rows.map((d) => ({
      code: d.code,
      district: d.district_name,
      state: d.state_name,
      population_2011: d.population_2011 ?? '',
      overall_score: d.overall_score,
      overall_rank: d.overall_rank,
      chronic_score: d.chronic_score,
      chronic_rank: d.chronic_rank,
      acute_score: d.acute_score,
      acute_rank: d.acute_rank,
      tier: d.tier,
      size_score: d.size_score ?? '',
      quality_score: d.quality_score ?? '',
      rank_p5: d.rank_interval_p5_p95?.[0] ?? '',
      rank_p95: d.rank_interval_p5_p95?.[1] ?? '',
      current_rank: d.current_vs_future?.current_rank ?? '',
      projected_rank: d.current_vs_future?.projected_rank ?? '',
      growth_gap: d.current_vs_future?.growth_gap ?? '',
      growth_flag: d.current_vs_future?.growth_flag ?? '',
      ...Object.fromEntries(
        PILLAR_ORDER.map((p) => [p, d.pillar_scores?.[p] ?? '']),
      ),
      run_id: d.run_id ?? '',
    }));
    downloadCsv(`mai_districts_${rows.length}.csv`, toCsv(flat));
  }

  if (loading) return <Loading what="districts" />;

  return (
    <Section
      eyebrow="Deliverable 1 · full index output"
      title="All districts"
      sub="Every scored district with its three indices, band, decomposition and projected movement. Sort any column, filter by state or band, search by name or code, export exactly what you are looking at."
      right={
        <button onClick={exportCsv} className="btn">
          export {rows.length} rows as CSV
        </button>
      }
    >
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="search district, state or code…"
          className="w-64 rounded border border-line bg-panel px-3 py-1.5 text-[12px] text-bright outline-none transition-colors duration-[160ms] placeholder:text-dim focus:border-accent"
        />
        <select
          value={state}
          onChange={(e) => setState(e.target.value)}
          className="rounded border border-line bg-panel px-3 py-1.5 text-[12px] text-dim outline-none focus:border-accent"
        >
          <option value="">all states</option>
          {states.map((s) => (
            <option key={s.name} value={s.name}>
              {s.name} ({s.count})
            </option>
          ))}
        </select>
        {['A', 'B', 'C', 'D'].map((t) => (
          <button
            key={t}
            onClick={() => setTier(tier === t ? '' : t)}
            className={`btn ${tier === t ? 'btn-on' : ''}`}
          >
            band {t}
          </button>
        ))}
        <button
          onClick={() => setShowPillars(!showPillars)}
          className={`btn ${showPillars ? 'btn-on' : ''}`}
        >
          pillar columns
        </button>
        <span className="tnum ml-auto text-[11px] text-dim">
          {rows.length} of {all.length}
        </span>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="max-h-[70vh] overflow-y-auto">
          <Table
            dense
            head={
              <>
                {head('overall_rank', '#', 'right')}
                {head('district_name', 'District')}
                {head('state_name', 'State')}
                {head('overall_score', 'Overall', 'right')}
                {head('chronic_score', 'Chronic', 'right')}
                {head('acute_score', 'Acute', 'right')}
                <Th align="right">Band</Th>
                {head('population_2011', 'Population', 'right')}
                {head('growth_gap', 'Growth gap', 'right')}
                {showPillars &&
                  PILLAR_ORDER.map((p) => (
                    <Th key={p} align="right">
                      {PILLAR_LABEL[p].split(' ')[0]}
                    </Th>
                  ))}
              </>
            }
          >
            {rows.map((d) => (
              <tr
                key={d.code}
                onClick={() => setPick(d.code)}
                className={`cursor-pointer border-b border-line/50 transition-colors duration-[160ms] hover:bg-[#1F2A35]/50 ${
                  pick === d.code ? 'bg-[#1F2A35]/60' : ''
                }`}
              >
                <td className="cell tnum text-right text-dim">{d.overall_rank}</td>
                <td className="cell text-bright">{d.district_name}</td>
                <td className="cell text-dim">{d.state_name}</td>
                <td className="cell tnum text-right">
                  <span
                    className="mr-1.5 inline-block h-2 w-2 rounded-sm align-middle"
                    style={{ background: scale.color(d.overall_score) }}
                  />
                  <span className="text-bright">{num(d.overall_score)}</span>
                </td>
                <td className="cell tnum text-right text-dim">{num(d.chronic_score)}</td>
                <td className="cell tnum text-right text-dim">{num(d.acute_score)}</td>
                <td className="cell tnum text-right text-dim">{d.tier}</td>
                <td className="cell tnum text-right text-dim">
                  {popShort(d.population_2011)}
                </td>
                <td
                  className={`cell tnum text-right ${
                    (d.current_vs_future?.growth_gap ?? 0) > 0 ? 'text-accent' : 'text-dim'
                  }`}
                >
                  {d.current_vs_future ? num(d.current_vs_future.growth_gap, 1) : '—'}
                </td>
                {showPillars &&
                  PILLAR_ORDER.map((p) => (
                    <td key={p} className="cell tnum text-right text-dim">
                      {d.pillar_scores?.[p] !== undefined
                        ? num(d.pillar_scores[p], 0)
                        : '—'}
                    </td>
                  ))}
              </tr>
            ))}
          </Table>
          <Note>
            {int(all.length)} districts are scored. The gap to India&apos;s
            ~800 present-day districts is the 2011 Census spine: districts
            created after it have no Census population, no SECC row and no NFHS
            sample, so they are absent rather than estimated.
          </Note>
        </div>

        <div className="hidden xl:block">
          {pick ? (
            <DistrictDrawer
              doc={bundle?.byCode.get(pick) ?? null}
              total={all.length}
              allScores={all.map((d) => d.overall_score)}
              onClose={() => setPick(null)}
            />
          ) : (
            <div className="panel px-4 py-4 text-[12px] leading-relaxed text-dim">
              Select a row to open its full record — pillar decomposition, rank
              interval, projected movement, field brief and provenance.
            </div>
          )}
        </div>
      </div>
    </Section>
  );
}
