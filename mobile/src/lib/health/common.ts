import { api, type HealthDaily, type HealthWorkout } from "../api";
import { getItem, setItem } from "../storage";

export type HealthReader = {
  name: "apple_health" | "health_connect";
  available: () => Promise<boolean>;
  requestPermissions: () => Promise<boolean>;
  readWorkouts: (since: Date) => Promise<HealthWorkout[]>;
  readDaily: (since: Date) => Promise<HealthDaily[]>;
};

const LAST_KEY = "health_last_sync";

/** Reads new runs + daily health metrics and uploads them to the backend. */
export async function syncWith(reader: HealthReader, days = 30): Promise<{ workouts: number; daily: number }> {
  if (!(await reader.available())) throw new Error("Thiết bị không hỗ trợ dữ liệu sức khỏe");
  const ok = await reader.requestPermissions();
  if (!ok) throw new Error("Chưa được cấp quyền đọc dữ liệu sức khỏe");
  const last = await getItem(LAST_KEY);
  const sinceWorkouts = last ? new Date(new Date(last).getTime() - 2 * 86400_000) : new Date(Date.now() - days * 86400_000);
  const sinceDaily = new Date(Date.now() - 14 * 86400_000);
  const [workouts, daily] = await Promise.all([reader.readWorkouts(sinceWorkouts), reader.readDaily(sinceDaily)]);
  await api.healthBatch(workouts, daily);
  await setItem(LAST_KEY, new Date().toISOString());
  return { workouts: workouts.length, daily: daily.length };
}

export function dayKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function toMeters(q?: { quantity: number; unit: string } | null): number {
  if (!q) return 0;
  switch (q.unit) {
    case "km":
      return q.quantity * 1000;
    case "mi":
      return q.quantity * 1609.344;
    case "ft":
      return q.quantity * 0.3048;
    default:
      return q.quantity;
  }
}

export function toSeconds(q?: { quantity: number; unit: string } | null): number {
  if (!q) return 0;
  switch (q.unit) {
    case "min":
      return q.quantity * 60;
    case "hr":
    case "h":
      return q.quantity * 3600;
    case "ms":
      return q.quantity / 1000;
    default:
      return q.quantity;
  }
}
