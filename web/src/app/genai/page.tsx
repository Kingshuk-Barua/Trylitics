'use client';
import { useEffect, useState } from 'react';
import { loadGenAi } from '@/lib/data';
import { Section, Loading, Note, Table, Th, Stat, Verdict } from '@/components/ui';
import { num, int, pct } from '@/lib/format';
import type { GenAiBundle } from '@/lib/types';

export default function GenAiPage() {
  const [g, setG] = useState<GenAiBundle | null>(null);

  useEffect(() => {
    loadGenAi().then(setG).catch(() => setG(null));
  }, []);

  if (!g) return <Loading what="the GenAI evaluations" />;

  const g1 = g.g1_summary;
  const g2Llm = g.g2_llm ?? 0;
  const g2All = g.g2_count ?? 0;

  return (
    <>
      <Section
        eyebrow="Evaluation · innovation"
        title="Where a language model earns its place — and where it does not"
        sub="Two uses, both with a graded evaluation attached. An LLM is used only where a deterministic method genuinely cannot reach: resolving district names no string metric can match, and writing prose. It is never allowed near a number."
      >
        <div className="grid gap-3 md:grid-cols-4">
          <Stat
            label="G1 · crosswalk precision"
            value={g1 ? num(g1.precision_auto_accept, 3) : '—'}
            tone={g1 && g1.precision_auto_accept >= 0.95 ? 'good' : 'warn'}
            note="bar: ≥ 0.95 on auto-accepted mappings"
          />
          <Stat
            label="G1 · two-family agreement"
            value={g1 ? pct(g1.two_family_agreement_rate) : '—'}
            note="proposer and verifier are different model families"
          />
          <Stat
            label="G2 · numeric fidelity"
            value={g2All ? pct((g2Llm / g2All) * 100) : '—'}
            note="narratives that stated only numbers they were given"
          />
          <Stat
            label="G2 · published fidelity"
            value="100%"
            tone="good"
            note="by construction — a failing narrative is replaced, never shipped"
          />
        </div>
      </Section>

      {g1 && (
        <Section
          eyebrow="G1"
          title="LLM-assisted district crosswalk"
          sub="Source feeds name districts in spellings no alias table anticipates. The resolver is given a CLOSED vocabulary — only the districts that exist in the target state — so it selects rather than generates, which removes the hallucination surface instead of asking the model to avoid it."
        >
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div>
              <Table
                head={
                  <>
                    <Th>Measure</Th>
                    <Th align="right">Value</Th>
                    <Th align="right">Verdict</Th>
                  </>
                }
              >
                <tr className="border-b border-line/60">
                  <td className="cell text-bright">
                    Precision on auto-accepted mappings
                  </td>
                  <td className="cell tnum text-right text-bright">
                    {num(g1.precision_auto_accept, 4)}
                  </td>
                  <td className="cell text-right">
                    <Verdict v={g1.verdict} />
                  </td>
                </tr>
                <tr className="border-b border-line/60">
                  <td className="cell text-bright">Labels auto-accepted</td>
                  <td className="cell tnum text-right text-bright">
                    {int(g1.auto_accepted)} of {int(g1.n)}
                  </td>
                  <td className="cell" />
                </tr>
                <tr className="border-b border-line/60">
                  <td className="cell text-bright">
                    Agreement between the two model families
                  </td>
                  <td className="cell tnum text-right text-bright">
                    {pct(g1.two_family_agreement_rate)}
                  </td>
                  <td className="cell" />
                </tr>
                <tr className="border-b border-line/60">
                  <td className="cell text-bright">Sent to human review</td>
                  <td className="cell tnum text-right text-bright">
                    {int(g1.review_queue)}
                  </td>
                  <td className="cell" />
                </tr>
                <tr>
                  <td className="cell text-bright">Recall across all labels</td>
                  <td className="cell tnum text-right text-bright">
                    {num(g1.recall_all, 3)}
                  </td>
                  <td className="cell" />
                </tr>
              </Table>
              <Note>
                Precision is 1.000 on the subset where the two families agreed
                independently. Agreement between two runs of the same model at
                temperature zero would be worth nothing — it is agreement across
                different families that carries information, which is why the
                roles are split across model families on purpose rather than for
                variety.
              </Note>
            </div>
            <div className="panel px-4 py-4">
              <div className="h-eyebrow mb-3">Role assignment</div>
              <div className="space-y-3 text-[12px]">
                {Object.entries(g1.models).map(([role, model]) => (
                  <div key={role}>
                    <div className="text-dim">{role}</div>
                    <div className="tnum text-bright">{model}</div>
                  </div>
                ))}
              </div>
              <Note>
                The tiebreak model is a third family and is called only on
                disagreement. Every model id is validated against the live
                endpoint at startup, so a deprecation fails loudly instead of
                silently falling back.
              </Note>
              <div className="tnum mt-4 space-y-1 border-t border-line pt-3 text-[11px] text-dim">
                <div className="flex justify-between">
                  <span>API calls</span>
                  <span className="text-bright">{int(g1.groq_usage.calls)}</span>
                </div>
                <div className="flex justify-between">
                  <span>prompt tokens</span>
                  <span className="text-bright">
                    {int(g1.groq_usage.prompt_tokens)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>completion tokens</span>
                  <span className="text-bright">
                    {int(g1.groq_usage.completion_tokens)}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </Section>
      )}

      <Section
        eyebrow="G2"
        title="District field briefs"
        sub="A deterministic template already produces a grounded brief for all 698 districts with zero numeric-fidelity failures. The LLM layer sits on top of that, never instead of it — every number is placed by code and the model composes prose around them."
      >
        <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Briefs generated" value={int(g2All)} />
          <Stat label="Passed the numeric check" value={int(g2Llm)} tone="good" />
          <Stat
            label="Rejected and replaced"
            value={int(g.g2_rejected?.length ?? 0)}
            tone="warn"
          />
          <Stat
            label="Judge evaluation"
            value={g.g2_judge ? 'complete' : 'pending'}
            note={
              g.g2_judge
                ? undefined
                : "blocked on the daily token allowance of the judge model — the run is written, not run"
            }
          />
        </div>

        <div className="panel px-5 py-4">
          <div className="h-eyebrow mb-3">How fidelity is enforced</div>
          <ol className="space-y-2 text-[12.5px] leading-relaxed text-dim">
            <li>
              <span className="text-bright">1.</span> The prompt carries only
              that district&apos;s own pre-computed values — no retrieval, no
              world knowledge, no peer data.
            </li>
            <li>
              <span className="text-bright">2.</span> Every fact is passed
              pre-formatted, so the model composes and never calculates.
            </li>
            <li>
              <span className="text-bright">3.</span> After generation, every
              integer is re-extracted from the prose and checked against the set
              the model was given. Zero tolerance.
            </li>
            <li>
              <span className="text-bright">4.</span> A narrative that states a
              number it was not given is rejected outright and the deterministic
              template ships instead. Published fidelity is therefore 100% by
              construction, not by hope.
            </li>
          </ol>
        </div>

        {g.g2_samples && g.g2_samples.length > 0 && (
          <div className="mt-5">
            <div className="h-eyebrow mb-2">Accepted briefs</div>
            <div className="grid gap-3 md:grid-cols-2">
              {g.g2_samples.slice(0, 4).map((s) => (
                <div key={s.code} className="panel px-4 py-3">
                  <div className="tnum mb-2 text-[11px] text-dim">
                    district {s.code} · {s.model}
                  </div>
                  <p className="text-[12.5px] leading-relaxed text-bright">
                    {s.narrative}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {g.g2_rejected && g.g2_rejected.length > 0 && (
          <div className="mt-5">
            <div className="h-eyebrow mb-2">
              Rejected drafts — the check catching real failures
            </div>
            <div className="space-y-3">
              {g.g2_rejected.map((r) => (
                <div key={r.code} className="panel px-4 py-3">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="tnum text-[11px] text-dim">
                      district {r.code}
                    </span>
                    <span className="tnum text-[11px] text-ramp-6">
                      ungrounded numbers: {(r.rejected_numbers ?? []).join(', ')}
                    </span>
                  </div>
                  <p className="text-[12px] leading-relaxed text-dim">{r.draft}</p>
                </div>
              ))}
            </div>
            <Note>
              These are shown because they are the evidence that the check does
              something. A verifier that never rejects anything is
              indistinguishable from no verifier at all.
            </Note>
          </div>
        )}
      </Section>

      <Section
        eyebrow="Scope"
        title="Where the model is deliberately not used"
        sub="The brief invites ML, DL and GenAI. The honest answer is that most of the obvious framings do not survive contact with the data."
      >
        <div className="grid gap-3 md:grid-cols-3">
          {[
            [
              'Tier classification',
              'Rejected. The tier is a deterministic quartile cut of a score published in the same document. A classifier trained on it recovers three thresholds and nothing else; a two-line lookup achieves 100%.',
            ],
            [
              'Archetype classification',
              'Kept only as a utility. Silhouette is 0.224 at the chosen k — the clusters barely separate, and training a classifier on unstable labels propagates the instability.',
            ],
            [
              'Score generation by LLM',
              'Never. Scores come from a specified, reproducible composite. The model writes prose about numbers it is handed, and is checked afterwards.',
            ],
          ].map(([t, body]) => (
            <div key={t} className="panel px-4 py-3">
              <div className="mb-1.5 font-display text-[13px] text-bright">{t}</div>
              <p className="text-[12px] leading-relaxed text-dim">{body}</p>
            </div>
          ))}
        </div>
      </Section>
    </>
  );
}
