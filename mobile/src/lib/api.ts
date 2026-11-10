import { getItem, removeItem, setItem } from "./storage";
import type {
  Activity,
  Adjustment,
  AppSettings,
  IntegrationStatus,
  PlanResponse,
  StatsResponse,
  TodayResponse,
  Workout,
} from "./types";

const SERVER_KEY = "server_url";
const TOKEN_KEY = "app_token";

let cached: { url: string; token: string } | null = null;

export async function getServer(): Promise<{ url: string; token: string } | null> {
  if (cached) return cached;
  const url = await getItem(SERVER_KEY);
  const token = await getItem(TOKEN_KEY);
  if (!url || !token) return null;
  cached = { url: url.replace(/\/+$/, ""), token };
  return cached;
}

export async function saveServer(url: string, token: string): Promise<void> {
  await setItem(SERVER_KEY, url.trim().replace(/\/+$/, ""));
  await setItem(TOKEN_KEY, token.trim());
  cached = null;
}

export async function clearServer(): Promise<void> {
  await removeItem(SERVER_KEY);
  await removeItem(TOKEN_KEY);
  cached = null;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown, server?: { url: string; token: string }): Promise<T> {
  const srv = server ?? (await getServer());
  if (!srv) throw new ApiError(0, "Chưa cấu hình máy chủ");
  const res = await fetch(`${srv.url}${path}`, {
    method,
    headers: { Authorization: `Bearer ${srv.token}`, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(res.status, typeof detail === "string" ? detail : `Lỗi ${res.status}`);
  }
  return data as T;
}

export type CreatePlanBody = {
  goal: { distance: string; race_date?: string | null; target_time_s?: number | null; start_date: string; name?: string };
  profile: {
    level: string;
    current_weekly_km: number;
    longest_recent_run_km?: number | null;
    days_per_week: number;
    available_days: number[];
    long_run_day: number;
    recent_race?: { distance_m: number; time_s: number } | null;
    easy_pace_s_per_km?: number | null;
    age?: number | null;
    max_hr?: number | null;
    resting_hr?: number | null;
    include_strength: boolean;
    strides: boolean;
  };
};

export type HealthWorkout = {
  source: "apple_health" | "health_connect";
  external_id: string;
  start_time: string;
  end_time?: string;
  distance_m: number;
  duration_s: number;
  sport: string;
  avg_hr?: number | null;
  max_hr?: number | null;
  calories?: number | null;
  name?: string;
  laps?: { distance_m: number; duration_s: number; avg_hr?: number | null }[];
};

export type HealthDaily = {
  day: string;
  resting_hr?: number | null;
  hrv_ms?: number | null;
  sleep_hours?: number | null;
  source: string;
};

export const api = {
  ping: (server: { url: string; token: string }) => request<{ ok: boolean }>("GET", "/api/settings", undefined, server),
  today: () => request<TodayResponse>("GET", "/api/today"),
  plan: () => request<PlanResponse>("GET", "/api/plan"),
  createPlan: (body: CreatePlanBody) => request<PlanResponse>("POST", "/api/plan", body),
  previewPlan: (body: CreatePlanBody) => request<{ start_vdot: number; goal_vdot: number; warnings: string[]; weeks: { target_km: number; phase: string }[] }>("POST", "/api/plan/preview", body),
  regenerate: () => request<PlanResponse>("POST", "/api/plan/regenerate"),
  updateGoal: (body: { target_time_s?: number; race_date?: string }) => request<PlanResponse>("PATCH", "/api/plan/goal", body),
  workout: (id: number) => request<Workout>("GET", `/api/workouts/${id}`),
  patchWorkout: (id: number, body: { date?: string; status?: string; rpe?: number; notes?: string }) => request<Workout>("PATCH", `/api/workouts/${id}`, body),
  pushWorkout: (id: number) => request<Record<string, unknown>>("POST", `/api/workouts/${id}/push`),
  adjustments: (status?: string) => request<Adjustment[]>("GET", `/api/adjustments${status ? `?status=${status}` : ""}`),
  applyAdjustment: (id: number) => request<Adjustment>("POST", `/api/adjustments/${id}/apply`),
  dismissAdjustment: (id: number) => request<Adjustment>("POST", `/api/adjustments/${id}/dismiss`),
  notFeeling100: (reason: string, days: number) => request<{ reason: string }>("POST", "/api/not-feeling-100", { reason, days }),
  activities: (limit = 50) => request<Activity[]>("GET", `/api/activities?limit=${limit}`),
  addActivity: (body: {
    start_time: string;
    distance_m: number;
    duration_s: number;
    avg_hr?: number;
    rpe?: number;
    workout_id?: number;
    laps?: { distance_m: number; duration_s: number }[];
    source?: "manual" | "phone";
    name?: string;
  }) => request<Activity>("POST", "/api/activities", body),
  healthBatch: (workouts: HealthWorkout[], daily: HealthDaily[]) => request<{ workouts: number }>("POST", "/api/health/batch", { workouts, daily }),
  stats: () => request<StatsResponse>("GET", "/api/stats"),
  weekly: () => request<{ text: string }>("GET", "/api/coach/weekly"),
  chat: (messages: { role: "user" | "assistant"; content: string }[]) => request<{ reply: string }>("POST", "/api/coach/chat", { messages }),
  settings: () => request<AppSettings>("GET", "/api/settings"),
  putSettings: (body: Partial<AppSettings>) => request<AppSettings>("PUT", "/api/settings", body),
  integrations: () => request<IntegrationStatus>("GET", "/api/integrations"),
  syncAll: () => request<Record<string, unknown>>("POST", "/api/integrations/sync"),
  stravaConnect: () => request<{ authorize_url: string }>("GET", "/api/integrations/strava/connect"),
  stravaSubscribe: () => request<Record<string, unknown>>("POST", "/api/integrations/strava/webhook/subscribe"),
  stravaDisconnect: () => request("DELETE", "/api/integrations/strava"),
  garminLogin: (email?: string, password?: string) => request<{ status: "connected" | "needs_mfa" }>("POST", "/api/integrations/garmin/login", { email, password }),
  garminMfa: (code: string) => request<{ status: string }>("POST", "/api/integrations/garmin/mfa", { code }),
  garminDisconnect: () => request("DELETE", "/api/integrations/garmin"),
  corosConnect: () => request<{ authorize_url?: string; status?: string }>("POST", "/api/integrations/coros/connect"),
  corosDisconnect: () => request("DELETE", "/api/integrations/coros"),
};
