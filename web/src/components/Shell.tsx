'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useData } from './DataProvider';
import { shortDate } from '@/lib/format';

const NAV = [
  { href: '/', label: 'Overview' },
  { href: '/map/', label: 'Map' },
  { href: '/districts/', label: 'Districts' },
  { href: '/states/', label: 'States' },
  { href: '/therapy/', label: 'Therapy split' },
  { href: '/growth/', label: 'Current vs future' },
  { href: '/deployment/', label: 'Deployment' },
  { href: '/methodology/', label: 'Methodology' },
  { href: '/validation/', label: 'Validation' },
  { href: '/genai/', label: 'GenAI layer' },
  { href: '/data-quality/', label: 'Data quality' },
];

function StatusBar() {
  const { bundle, loading } = useData();
  const live = bundle?.source === 'firestore';
  return (
    <div className="border-b border-line bg-page/80 backdrop-blur">
      <div className="mx-auto flex max-w-shell flex-wrap items-center gap-x-6 gap-y-1 px-6 py-1.5 text-[11px] text-dim">
        <span className="flex items-center gap-2">
          <span
            className="inline-block h-1.5 w-1.5 rounded-full"
            style={{
              background: loading ? '#8FA3B0' : live ? '#3FB6A8' : '#F2C14E',
            }}
          />
          {loading
            ? 'reading…'
            : live
              ? 'live · Firestore mai_scores'
              : 'bundled snapshot'}
        </span>
        {bundle && (
          <>
            <span className="tnum">{bundle.districts.length} districts</span>
            <span className="tnum">{bundle.run?.model_version ?? 'no run record'}</span>
            <span className="tnum">
              vintage {shortDate(bundle.run?.created_at)}
            </span>
            {!bundle.isV2 && (
              <span className="text-ramp-6">
                v1 documents — pillar detail and narratives arrive with{' '}
                <code>mai.publish --confirm</code>
              </span>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const isActive = (href: string) =>
    href === '/' ? path === '/' : path.startsWith(href.replace(/\/$/, ''));

  return (
    <div className="min-h-screen bg-page">
      <StatusBar />
      <header className="sticky top-0 z-40 border-b border-line bg-page/95 backdrop-blur">
        <div className="mx-auto flex max-w-shell items-center justify-between gap-6 px-6 py-3">
          <Link href="/" className="group flex items-baseline gap-3">
            <span className="font-display text-[15px] font-medium tracking-[0.14em] text-bright">
              MAI
            </span>
            <span className="hidden text-[11px] tracking-[0.16em] text-dim sm:block">
              DISTRICT MARKET ATTRACTIVENESS INDEX · v2
            </span>
          </Link>
          <nav className="flex flex-wrap items-center justify-end gap-x-4 gap-y-1">
            {NAV.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className={`text-[12px] tracking-wide transition-colors duration-[160ms] ease-out ${
                  isActive(n.href)
                    ? 'text-accent'
                    : 'text-dim hover:text-bright'
                }`}
              >
                {n.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-shell px-6 py-10">{children}</main>
      <footer className="mt-16 border-t border-line">
        <div className="mx-auto max-w-shell px-6 py-8 text-[11px] leading-relaxed text-dim">
          <p>
            Built for the Trilytics 2026 challenge (Sun Pharma). Scores are read
            from Firestore at runtime; the analysis artefacts behind the
            validation, benchmark and GenAI pages are read from the build
            output of the Python pipeline in this repository.
          </p>
          <p className="mt-2">
            Every failing test is shown as failing. Nothing on this site is
            asserted that the pipeline did not compute.
          </p>
        </div>
      </footer>
    </div>
  );
}
