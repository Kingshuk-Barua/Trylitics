'use client';
/** Small shared primitives. One 4px radius, 1px borders, no shadows. */
import type { ReactNode } from 'react';

export function Section({
  title, eyebrow, sub, children, right,
}: {
  title: string; eyebrow?: string; sub?: ReactNode;
  children: ReactNode; right?: ReactNode;
}) {
  return (
    <section className="mb-16">
      <div className="mb-5 flex items-end justify-between gap-6">
        <div>
          {eyebrow && <div className="h-eyebrow mb-2">{eyebrow}</div>}
          <h2 className="font-display text-[22px] font-medium tracking-[0.02em] text-bright">
            {title}
          </h2>
          {sub && (
            <p className="mt-2 max-w-3xl text-[13px] leading-relaxed text-dim">{sub}</p>
          )}
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}

export function Stat({
  label, value, unit, note, tone = 'normal',
}: {
  label: string; value: ReactNode; unit?: string; note?: string;
  tone?: 'normal' | 'good' | 'warn';
}) {
  const color =
    tone === 'good' ? 'text-accent' : tone === 'warn' ? 'text-ramp-6' : 'text-bright';
  return (
    <div className="panel px-4 py-3">
      <div className="h-eyebrow">{label}</div>
      <div className={`tnum mt-2 text-[26px] leading-none ${color}`}>
        {value}
        {unit && <span className="ml-1 text-[13px] text-dim">{unit}</span>}
      </div>
      {note && <div className="mt-2 text-[11px] leading-snug text-dim">{note}</div>}
    </div>
  );
}

export function Verdict({ v }: { v: string }) {
  const map: Record<string, string> = {
    PASS: 'border-accent/50 text-accent',
    FAIL: 'border-ramp-6/50 text-ramp-6',
    UNAVAILABLE: 'border-line text-dim',
  };
  return (
    <span
      className={`rounded border px-1.5 py-0.5 text-[10px] tracking-[0.12em] ${
        map[v] ?? 'border-line text-dim'
      }`}
    >
      {v}
    </span>
  );
}

export function Bar({
  value, max = 100, color = '#3FB6A8',
}: { value: number; max?: number; color?: string }) {
  const w = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="h-1.5 w-full rounded bg-[#1F2A35]">
      <div
        className="h-full rounded transition-all duration-[160ms] ease-out"
        style={{ width: `${w}%`, background: color }}
      />
    </div>
  );
}

export function Loading({ what = 'data' }: { what?: string }) {
  return (
    <div className="panel flex h-40 items-center justify-center text-[12px] text-dim">
      <span className="animate-pulse">reading {what}…</span>
    </div>
  );
}

export function Note({ children }: { children: ReactNode }) {
  return (
    <p className="mt-3 border-l border-line pl-3 text-[11px] leading-relaxed text-dim">
      {children}
    </p>
  );
}

export function Table({
  head, children, dense = false,
}: { head: ReactNode; children: ReactNode; dense?: boolean }) {
  return (
    <div className="panel overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse">
        <thead>
          <tr className="border-b border-line text-left">{head}</tr>
        </thead>
        <tbody className={dense ? 'text-[12px]' : ''}>{children}</tbody>
      </table>
    </div>
  );
}

export function Th({
  children, align = 'left', onClick, active, w,
}: {
  children: ReactNode; align?: 'left' | 'right'; onClick?: () => void;
  active?: boolean; w?: string;
}) {
  return (
    <th
      onClick={onClick}
      style={w ? { width: w } : undefined}
      className={`cell h-eyebrow whitespace-nowrap ${
        align === 'right' ? 'text-right' : 'text-left'
      } ${onClick ? 'cursor-pointer select-none hover:text-bright' : ''} ${
        active ? 'text-accent' : ''
      }`}
    >
      {children}
    </th>
  );
}
