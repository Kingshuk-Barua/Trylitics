'use client';
import { useMemo, useState } from 'react';
import { useData } from '@/components/DataProvider';
import { Section, Loading, Table, Th, Note, Stat } from '@/components/ui';
import { num, int, popShort } from '@/lib/format';
import { percentileScale } from '@/lib/color';

interface Roll {
  state: string;
  n: number;
  mean: number;
  best: { name: string; score: number; rank: number };
  worst: { name: string; score: number };
  spread: number;
  pop: number;
  top100: number;
}

export default function StatesPage() {
  const { bundle, loading } = useData();
  const [sort, setSort] = useState<keyof Roll>('mean');
  const [asc, setAsc] = useState(false);

  const rolls = useMemo<Roll[]>(() => {
    const d = bundle?.districts ?? [];
    const by = new Map<string, typeof d>();
    for (const x of d) {
      const arr = by.get(x.state_name) ?? [];
      arr.push(x);
      by.set(x.state_name, arr);
    }
    return [...by.entries()].map(([state, arr]) => {
      const sorted = [...arr].sort((a, b) => b.overall_score - a.overall_score);
      const scores = arr.map((x) => x.overall_score);
      return {
        state,
        n: arr.length,
        mean: scores.reduce((a, b) => a + b, 0) / arr.length,
        best: {
          name: sorted[0].district_name,
          score: sorted[0].overall_score,
          rank: sorted[0].overall_rank,
        },
        worst: {
          name: sorted[sorted.length - 1].district_name,
          score: sorted[sorted.length - 1].overall_score,
        },
        spread: sorted[0].overall_score - sorted[sorted.length - 1].overall_score,
        pop: arr.reduce((a, x) => a + (x.population_2011 ?? 0), 0),
        top100: arr.filter((x) => x.overall_rank <= 100).length,
      };
    });
  }, [bundle]);

  const rows = useMemo(() => {
    return [...rolls].sort((a, b) => {
      const av = a[sort];
      const bv = b[sort];
      const c =
        typeof av === 'number' && typeof bv === 'number'
          ? av - bv
          : String(av).localeCompare(String(bv));
      return asc ? c : -c;
    });
  }, [rolls, sort, asc]);

  const scale = useMemo(
    () => percentileScale(rolls.map((r) => r.mean)),
    [rolls],
  );

  const widest = useMemo(
    () => [...rolls].sort((a, b) => b.spread - a.spread).slice(0, 5),
    [rolls],
  );

  function head(key: keyof Roll, label: string, align: 'left' | 'right' = 'right') {
    return (
      <Th
        align={align}
        active={sort === key}
        onClick={() => {
          if (sort === key) setAsc(!asc);
          else {
            setSort(key);
            setAsc(false);
          }
        }}
      >
        {label}
        {sort === key ? (asc ? ' ↑' : ' ↓') : ''}
      </Th>
    );
  }

  if (loading) return <Loading what="districts" />;

  return (
    <>
      <Section
        eyebrow="Rollup"
        title="State league table"
        sub="State means exist to be argued with. A state-level plan built on these averages would miss the point of the framework: the within-state spread is larger than the between-state spread for most of the country, which is precisely why territory planning belongs at district level."
      >
        <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="States / UTs" value={int(rolls.length)} />
          <Stat
            label="Widest internal spread"
            value={num(widest[0]?.spread ?? 0, 1)}
            note={widest[0]?.state}
            tone="warn"
          />
          <Stat
            label="Median state spread"
            value={num(
              [...rolls].sort((a, b) => a.spread - b.spread)[
                Math.floor(rolls.length / 2)
              ]?.spread ?? 0,
              1,
            )}
            note="index points between a state's best and worst district"
          />
          <Stat
            label="States with a top-100 district"
            value={int(rolls.filter((r) => r.top100 > 0).length)}
          />
        </div>

        <Table
          head={
            <>
              {head('state', 'State', 'left')}
              {head('n', 'Districts')}
              {head('mean', 'Mean MAI')}
              {head('spread', 'Internal spread')}
              {head('top100', 'In top 100')}
              {head('pop', 'Population')}
              <Th>Best district</Th>
              <Th>Weakest district</Th>
            </>
          }
        >
          {rows.map((r) => (
            <tr
              key={r.state}
              className="border-b border-line/60 transition-colors duration-[160ms] hover:bg-[#1F2A35]/40"
            >
              <td className="cell text-bright">{r.state}</td>
              <td className="cell tnum text-right text-dim">{r.n}</td>
              <td className="cell tnum text-right">
                <span
                  className="mr-1.5 inline-block h-2 w-2 rounded-sm align-middle"
                  style={{ background: scale.color(r.mean) }}
                />
                <span className="text-bright">{num(r.mean)}</span>
              </td>
              <td className="cell tnum text-right text-dim">{num(r.spread, 1)}</td>
              <td className="cell tnum text-right text-dim">{r.top100 || '—'}</td>
              <td className="cell tnum text-right text-dim">{popShort(r.pop)}</td>
              <td className="cell text-[12px] text-dim">
                {r.best.name}{' '}
                <span className="tnum text-[11px]">
                  {num(r.best.score)} · #{r.best.rank}
                </span>
              </td>
              <td className="cell text-[12px] text-dim">
                {r.worst.name}{' '}
                <span className="tnum text-[11px]">{num(r.worst.score)}</span>
              </td>
            </tr>
          ))}
        </Table>
        <Note>
          State identity explains 53.6% of the variance in the index, which is
          why the ML validation is cross-validated with a state-blocked
          GroupKFold rather than a random split — a random split would let a
          model memorise the state and report that as skill.
        </Note>
      </Section>

      <Section
        eyebrow="Why district level"
        title="The states that hide the most"
        sub="These five states contain the widest gap between their best and weakest district. Any plan that treats them as a single unit is averaging away the decision."
      >
        <div className="grid gap-3 md:grid-cols-5">
          {widest.map((r) => (
            <div key={r.state} className="panel px-4 py-3">
              <div className="h-eyebrow mb-2 truncate">{r.state}</div>
              <div className="tnum text-[22px] text-ramp-6">{num(r.spread, 1)}</div>
              <div className="mt-2 text-[11px] leading-snug text-dim">
                <div className="text-bright">{r.best.name}</div>
                <div className="tnum">{num(r.best.score)} — best</div>
                <div className="mt-1 text-bright">{r.worst.name}</div>
                <div className="tnum">{num(r.worst.score)} — weakest</div>
              </div>
            </div>
          ))}
        </div>
      </Section>
    </>
  );
}
