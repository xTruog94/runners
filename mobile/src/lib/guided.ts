import type { Step } from "./types";

export type FlatStep = {
  index: number;
  kind: Step["kind"];
  distance_m?: number;
  duration_s?: number;
  fast?: number;
  slow?: number;
  label: string;
  rep?: string; // "3/6"
};

const KIND: Record<string, string> = { warmup: "Khởi động", run: "Chạy", recovery: "Hồi phục", cooldown: "Thả lỏng" };

function spokenDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const r = Math.round(sec % 60);
  if (!m) return `${r} giây`;
  return r ? `${m} phút ${r} giây` : `${m} phút`;
}

/** Expands repeat groups into a linear list of steps. */
export function flatten(steps: Step[]): FlatStep[] {
  const out: FlatStep[] = [];
  const push = (s: Step, rep?: string) => {
    const amount = s.distance_m ? (s.distance_m >= 1000 ? `${+(s.distance_m / 1000).toFixed(2)} km` : `${Math.round(s.distance_m)} mét`) : s.duration_s ? spokenDuration(s.duration_s) : "";
    out.push({
      index: out.length,
      kind: s.kind,
      distance_m: s.distance_m,
      duration_s: s.duration_s,
      fast: s.target?.fast_s_per_km,
      slow: s.target?.slow_s_per_km,
      label: `${KIND[s.kind] ?? s.kind} ${amount}`.trim(),
      rep,
    });
  };
  for (const s of steps) {
    if (s.kind === "repeat") {
      const n = s.repeats ?? 1;
      for (let i = 0; i < n; i++) for (const c of s.steps ?? []) push(c, `${i + 1}/${n}`);
    } else push(s);
  }
  return out;
}

export function haversine(a: { latitude: number; longitude: number }, b: { latitude: number; longitude: number }): number {
  const R = 6371000;
  const toRad = (x: number) => (x * Math.PI) / 180;
  const dLat = toRad(b.latitude - a.latitude);
  const dLon = toRad(b.longitude - a.longitude);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.latitude)) * Math.cos(toRad(b.latitude)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

/** Is the current step finished, given distance/time done inside it? */
export function stepDone(step: FlatStep, dist_m: number, time_s: number): boolean {
  if (step.distance_m) return dist_m >= step.distance_m;
  if (step.duration_s) return time_s >= step.duration_s;
  return false; // open step: user taps "next"
}

export function paceCue(pace: number, step: FlatStep): "fast" | "slow" | "ok" | null {
  if (!step.fast || !step.slow || !isFinite(pace) || pace <= 0) return null;
  if (pace < step.fast - 5) return "fast";
  if (pace > step.slow + 5) return "slow";
  return "ok";
}

export function spokenPace(sPerKm: number): string {
  const s = Math.round(sPerKm);
  return `${Math.floor(s / 60)} phút ${s % 60} giây một cây số`;
}
