export function fmtPace(sPerKm?: number | null): string {
  if (!sPerKm || !isFinite(sPerKm)) return "–";
  const s = Math.round(sPerKm);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function fmtDuration(totalS: number): string {
  const s = Math.max(0, Math.round(totalS));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
}

export function parseDuration(text: string): number | null {
  const parts = text.trim().split(":").map((p) => Number(p));
  if (!parts.length || parts.some((p) => isNaN(p))) return null;
  return parts.reduce((acc, p) => acc * 60 + p, 0);
}

const WEEKDAYS = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
export const WEEKDAY_LABELS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]; // index 0 = Monday

export function parseDate(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function fmtDay(iso: string): string {
  const d = parseDate(iso);
  return `${WEEKDAYS[d.getDay()]} ${d.getDate()}/${d.getMonth() + 1}`;
}

export function addDays(iso: string, n: number): string {
  const d = parseDate(iso);
  d.setDate(d.getDate() + n);
  return isoDate(d);
}

export const TYPE_LABELS: Record<string, string> = {
  easy: "Chạy nhẹ",
  recovery: "Hồi phục",
  long: "Chạy dài",
  tempo: "Tempo",
  intervals: "Interval",
  fartlek: "Fartlek",
  hills: "Chạy dốc",
  progression: "Progression",
  race_pace: "Pace thi đấu",
  shakeout: "Shakeout",
  race: "Thi đấu",
  strength: "Sức mạnh",
  rest: "Nghỉ",
};

export const PHASE_LABELS: Record<string, string> = {
  base: "Nền tảng",
  build: "Phát triển",
  peak: "Cao điểm",
  taper: "Giảm tải",
  maintain: "Duy trì",
};

export const DISTANCE_LABELS: Record<string, string> = {
  "5k": "5K",
  "10k": "10K",
  half: "Half marathon",
  marathon: "Marathon",
  general: "Chạy đều / khỏe",
};

export const STATUS_LABELS: Record<string, string> = {
  planned: "Kế hoạch",
  completed: "Hoàn thành",
  partial: "Một phần",
  missed: "Bỏ lỡ",
  skipped: "Bỏ qua",
};
