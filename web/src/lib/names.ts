/**
 * Name and code normalisation.
 *
 * Two joins have to hold for the map to be correct, and both are string joins
 * across sources that disagree about spelling:
 *
 *   geojson shapeName  ->  Firestore district_name
 *   district code      ->  document id
 *
 * The code join is the one that silently breaks. District codes travel as both
 * `"007"` and `"7"` depending on which writer produced the file — the Python
 * side has the same hazard and handles it by trying both forms. Every lookup
 * here goes through `normaliseCode` so a padded and an unpadded key can never
 * address different records.
 */

/** Zero-pad to the 3-char form used as the Firestore document id. */
export function normaliseCode(code: string | number | null | undefined): string {
  if (code === null || code === undefined) return '';
  const s = String(code).trim();
  if (!s) return '';
  const digits = s.replace(/[^0-9]/g, '');
  return digits ? digits.padStart(3, '0') : s;
}

const SUFFIXES = [
  'district', 'dist', 'zilla', 'zila', 'jila', 'division', 'urban', 'rural',
];

/**
 * Aggressive normalisation for name matching: lowercase, strip diacritics,
 * fold "&" to "and", drop punctuation, collapse whitespace, remove a trailing
 * administrative noun. Deliberately lossy — it is only ever used as a join
 * key, never displayed.
 */
export function normaliseName(name: string | null | undefined): string {
  if (!name) return '';
  let s = name
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
  for (const suf of SUFFIXES) {
    if (s.endsWith(' ' + suf)) s = s.slice(0, -(suf.length + 1)).trim();
  }
  return s.replace(/\s+/g, ' ');
}

/**
 * Spelling variants that normalisation alone will not reconcile, because they
 * are different words rather than different punctuation. Every entry here is a
 * case observed in the data — the `maharastra` misspelling, for instance,
 * orphaned 36 districts in v1 until the pipeline crosswalk fixed it.
 */
const STATE_ALIASES: Record<string, string> = {
  'maharastra': 'maharashtra',
  'orissa': 'odisha',
  'pondicherry': 'puducherry',
  'uttaranchal': 'uttarakhand',
  'nct of delhi': 'delhi',
  'national capital territory of delhi': 'delhi',
  'delhi nct': 'delhi',
  'jammu kashmir': 'jammu and kashmir',
  'andaman nicobar': 'andaman and nicobar islands',
  'andaman and nicobar': 'andaman and nicobar islands',
  'dadra and nagar haveli and daman and diu': 'dadra and nagar haveli',
  'daman and diu': 'dadra and nagar haveli',
  'chattisgarh': 'chhattisgarh',
  'chhatisgarh': 'chhattisgarh',
  'telengana': 'telangana',
  'tamilnadu': 'tamil nadu',
};

export function normaliseState(name: string | null | undefined): string {
  const s = normaliseName(name);
  return STATE_ALIASES[s] ?? s;
}

/** URL-safe state slug, matching the per-state geojson filenames. */
export function stateSlug(name: string | null | undefined): string {
  return normaliseState(name).replace(/\s+/g, '-');
}

/** Title-case for display of a normalised name. */
export function titleCase(s: string): string {
  return s.replace(/\w\S*/g, (t) => t[0].toUpperCase() + t.slice(1));
}

/** Composite join key used by the geo name map: "<name>|<state>". */
export function geoKey(shapeName: string, state: string): string {
  return `${normaliseName(shapeName)}|${normaliseState(state)}`;
}
