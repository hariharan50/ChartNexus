/** Wire types for HUGIN — the autonomous market-memory agent (read-only). */

export type HuginAvailability = {
  available: boolean;
};

export type HuginEnrollment = {
  enabled: boolean;
};

export type HuginGradeEvidence = {
  expected_move?: string;
  actual_move?: string;
  wall_status?: string;
  level_status?: string;
  note?: string;
} & Record<string, unknown>;

export type HuginObservation = {
  tick_at: string;
  instrument: string;
  bias: string;
  expectation: string;
  call_wall: number | null;
  put_wall: number | null;
  key_level: number | null;
  grade: string | null;
  score: number | null;
  grade_evidence: HuginGradeEvidence | null;
};

export type HuginLesson = {
  text: string;
  instrument: string | null;
  hits: number;
  misses: number;
  reliability: number;
  last_seen_at: string | null;
};

export type HuginMemoryToday = {
  instrument: string;
  observations: HuginObservation[];
  lessons: HuginLesson[];
  hit_rate: number | null;
  graded_count: number;
  hit_count: number;
};

export type HuginDay = {
  trading_day: string;
  observations: HuginObservation[];
  hit_rate: number | null;
  graded_count: number;
  hit_count: number;
};

export type HuginHistory = {
  instrument: string;
  days: HuginDay[];
  overall_hit_rate: number | null;
  overall_graded: number;
  overall_hits: number;
};

export type HuginCall = {
  created_at: string | null;
  instrument: string;
  bias: string;
  target_zone: string;
  conviction: number;
  track_hit_rate: number | null;
  rationale: string;
  entry: string | null;
  stop: string | null;
  target1: string | null;
  target2: string | null;
};

export type HuginCalls = {
  calls: HuginCall[];
};
