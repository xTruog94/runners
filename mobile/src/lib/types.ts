export type Target = { zone?: string; fast_s_per_km?: number; slow_s_per_km?: number };
export type Step = {
  kind: "warmup" | "run" | "recovery" | "cooldown" | "repeat";
  distance_m?: number;
  duration_s?: number;
  target?: Target;
  repeats?: number;
  steps?: Step[];
  note?: string;
};

export type Analysis = {
  compliance: number;
  pace_s_per_km: number;
  pace_vs_target: "on" | "fast" | "slow" | "n/a";
  rep_paces: number[];
  hr_drift_pct?: number | null;
  score: number;
  summary: string;
  tips: string[];
};

export type Heat = {
  hour: number;
  temp_c: number;
  humidity: number;
  slowdown_pct: number;
  factor: number;
  advice: string;
  best_hour?: number | null;
  best_hour_slowdown_pct?: number | null;
};

export type Workout = {
  id: number;
  plan_id: number;
  week_id: number | null;
  date: string;
  type: string;
  title: string;
  description: string;
  distance_km: number;
  duration_min: number;
  steps: Step[];
  heat_adjusted_steps?: Step[];
  heat?: Heat;
  steps_text: string;
  exercises?: { name: string; sets: number; reps: string }[] | null;
  key: boolean;
  status: "planned" | "completed" | "partial" | "missed" | "skipped";
  rpe?: number | null;
  notes?: string | null;
  activity_id?: number | null;
  analysis?: Analysis | null;
  synced: { garmin: boolean; coros: boolean };
  activity?: Activity | null;
};

export type Week = {
  id: number;
  index: number;
  start_date: string;
  phase: string;
  target_km: number;
  planned_km: number;
  is_cutback: boolean;
  vdot: number;
  workouts: Workout[];
};

export type Zone = { label: string; fast: string; slow: string; fast_s?: number; slow_s?: number };

export type Goal = {
  distance: "5k" | "10k" | "half" | "marathon" | "general";
  race_date?: string | null;
  target_time_s?: number | null;
  start_date: string;
  name?: string | null;
};

export type PlanResponse = {
  plan: { id: number; goal: Goal; profile: Record<string, unknown>; start_vdot: number; goal_vdot: number; current_vdot: number; warnings: string[] };
  zones: Record<string, Zone>;
  weeks: Week[];
};

export type Readiness = { score: number; label: string; factors: string[] };

export type Adjustment = {
  id: number;
  kind: string;
  reason: string;
  status: string;
  requires_confirmation: boolean;
  created_at: string;
};

export type TodayResponse = {
  date: string;
  heat: Heat | null;
  workouts: Workout[];
  next: Workout | null;
  pending_adjustments?: Adjustment[];
  week?: Omit<Week, "workouts" | "planned_km"> | null;
  goal?: Goal;
  days_to_race?: number | null;
  readiness: Readiness;
  load: { ctl: number; atl: number; tsb: number; acwr: number | null };
};

export type Activity = {
  id: number;
  source: string;
  start_time: string;
  local_date: string;
  name: string;
  sport: string;
  distance_m: number;
  duration_s: number;
  avg_hr?: number | null;
  max_hr?: number | null;
  load?: number | null;
  pace?: string | null;
  workout_id?: number | null;
};

export type LoadPoint = { day: string; load: number; ctl: number; atl: number; tsb: number };

export type StatsResponse = {
  load: { ctl: number; atl: number; tsb: number; acwr: number | null; readiness: Readiness; series: LoadPoint[] };
  weekly: { week_start: string; actual_km: number; planned_km: number | null }[];
  fitness: {
    plan_vdot: number | null;
    hr_estimated_vdot: number | null;
    predictions: { distance: string; time_s: number; pace_s_per_km: number }[];
    completion_rate: number | null;
    runs_last_6_weeks: number;
  };
};

export type IntegrationStatus = {
  strava: { configured: boolean; connected: boolean; last?: SyncLog | null };
  garmin: { connected: boolean; last?: SyncLog | null; push?: SyncLog | null };
  coros: { connected: boolean; last?: SyncLog | null; push?: SyncLog | null; tools: string[] };
  apple_health: { last_sync?: string | null };
  health_connect: { last_sync?: string | null };
};

export type SyncLog = { at: string; provider: string; ok: boolean; message: string };

export type AppSettings = {
  latitude: number;
  longitude: number;
  preferred_run_hour: number;
  heat_adjust: boolean;
  timezone: string;
  calendar_url: string;
  ai_coach: boolean;
};
