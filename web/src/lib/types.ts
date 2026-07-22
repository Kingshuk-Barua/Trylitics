/**
 * Document contracts.
 *
 * `DistrictDoc` is transcribed from `mai/publish.py::build_documents()`, which
 * is the authoritative definition of what lands in the `mai_scores` collection.
 * Everything the v1 documents lacked is optional here, because the collection
 * currently in Firestore is still v1 (14 fields, no pillar detail, no
 * narrative, no imputation flags) until `python3 -m mai.publish --confirm` is
 * run. The app renders whichever it is given and says which it got.
 */

export type PillarKey =
  | 'P2_chronic' | 'P2_acute' | 'P3_access' | 'P4_afford'
  | 'P5_mom_chronic' | 'P5_mom_acute' | 'P5_mom_adoption';

export interface CurrentVsFuture {
  current_score: number;
  current_rank: number;
  projected_score: number;
  projected_rank: number;
  growth_flag: boolean;
  growth_gap: number;
}

export interface DistrictDoc {
  /** always zero-padded to 3 chars by `normaliseCode`, never trusted raw */
  code: string;
  district_name: string;
  state_name: string;
  population_2011: number | null;

  overall_score: number;
  overall_rank: number;
  chronic_score: number;
  chronic_rank: number;
  acute_score: number;
  acute_rank: number;
  tier: string;

  current_vs_future?: CurrentVsFuture;
  rank_interval_p5_p95?: [number, number];
  pillar_scores?: Partial<Record<PillarKey, number>>;
  size_score?: number;
  quality_score?: number;

  narrative?: string;
  narrative_source?: string;
  narrative_numeric_check?: string;

  run_id?: string;
  updated_at?: string;
  is_imputed?: Record<string, number>;
  imputation_method?: string;
  data_vintage?: Record<string, string>;
  data_snapshot_id?: string;

  /** v1 only — kept so a v1 read still renders rather than throwing */
  cluster?: number | string;
  model_version?: string;
}

export interface RunDoc {
  model_version: string;
  created_at?: string;
  git_sha?: string | null;
  seed?: number;
  method?: string;
  alpha?: number;
  alpha_future?: number;
  quality_weights?: Record<string, number>;
  index_pillars?: Record<string, string[]>;
  indicators_kept?: string[];
  indicators_dropped_below_coverage?: string[];
  indicator_directions?: Record<string, number>;
  pillar_composition?: Record<string, string[]>;
  n_districts?: number;
  n_indicators?: number;
  imputation?: {
    observed: number; state_median: number; national_median: number;
    imputed_pct: number;
    per_pillar_imputed_pct: Record<string, number>;
  };
  data_vintage?: Record<string, string>;
  input_snapshot_sha256?: Record<string, string>;
  nfhs4_sentinel_fields?: string[];
  n_nfhs4_sentinel_fields?: number;
  secc_joined_districts?: number;
  pca_repaired?: boolean;
  /** v1 shape */
  weights?: Record<string, number>;
  top50_stability_pct?: number;
}

export interface ValidationRow {
  metric: string;
  value: number | null;
  verdict: 'PASS' | 'FAIL' | 'N/A' | '—' | string;
  note: string | null;
}

export interface BenchmarkRow {
  benchmark: string;
  spearman: number | null;
  n: number | null;
  verdict: 'PASS' | 'FAIL' | 'UNAVAILABLE' | string;
  band: string;
  note: string;
}

export interface MlValidation {
  n: number;
  features: string[];
  results: {
    blocked_cv_R2: Record<string, number>;
    blocked_cv_spearman: Record<string, number>;
  };
  coefficients: Record<string, number>;
  baseline_spearman_population: number;
  baseline_spearman_quality: number;
  negative_coefficient_pillars: string[];
  verdict: string;
  cv: string;
  target?: string;
  note?: string;
}

export interface CoverageRow {
  Unnamed_0?: string;
  coverage: number;
  kept: boolean;
  [k: string]: unknown;
}

export interface CrosswalkRow {
  label?: string;
  source_state?: string;
  category?: string;
  targets?: string;
  source?: string;
  [k: string]: unknown;
}

export interface DataQuality {
  coverage: Record<string, unknown>[];
  crosswalk_summary: Record<string, number>;
  crosswalk_rows: CrosswalkRow[];
  imputation: RunDoc['imputation'];
  reproducibility: {
    reproduces_at_2dp?: boolean | null;
    inputs_fresh?: boolean | null;
    detector_fires_on_perturbation?: boolean | null;
  };
  reproducibility_detail: Record<string, unknown>[];
  staleness: Record<string, unknown>[];
  imputation_spearman: Record<string, Record<string, number>>;
}

export interface GenAiBundle {
  g1_summary?: {
    n: number; auto_accepted: number; precision_auto_accept: number;
    recall_all: number; review_queue: number;
    two_family_agreement_rate: number;
    models: Record<string, string>; bar: string; verdict: string;
    groq_usage: Record<string, number>;
  };
  g1_rows?: Record<string, unknown>[];
  g1_resolutions?: Record<string, unknown>[];
  g2_count?: number;
  g2_llm?: number;
  g2_rejected?: { code: string; rejected_numbers: number[]; draft: string }[];
  g2_samples?: { code: string; narrative: string; model?: string }[];
  g2_judge?: Record<string, unknown>;
}

export interface Methodology {
  method: string;
  alpha: number;
  alpha_future: number;
  quality_weights: Record<string, number>;
  index_pillars: Record<string, string[]>;
  pillar_composition: Record<string, string[]>;
  indicator_directions: Record<string, number>;
  indicators_kept: string[];
  indicators_dropped: string[];
  data_vintage: Record<string, string>;
  seed: number;
  git_sha: string | null;
  nfhs4_sentinel_fields: string[];
  n_districts: number;
  n_indicators: number;
}

/** Where the district records in this session actually came from. */
export type DataSource = 'firestore' | 'local-fallback' | 'local-forced';

export interface GeoNameMap {
  generated_at: string;
  method?: string;
  counts?: {
    features: number; records: number; matched: number; fuzzy: number;
    dropped: number; unmatched_geo: number; unmatched_records: number;
  };
  dropped?: { shape_name: string; state: string; reason: string }[];
  exact: Record<string, string>;
  fuzzy: { shape_name: string; state: string; matched_name: string; code: string; score: number }[];
  unmatched_geo: { shape_name: string; state: string }[];
  unmatched_records: { code: string; district_name: string; state_name: string }[];
}
