import { aggregateRecord, getSdkStatus, initialize, readRecords, requestPermission, SdkAvailabilityStatus } from "react-native-health-connect";

import type { HealthDaily, HealthWorkout } from "../api";
import { dayKey, syncWith, type HealthReader } from "./common";

const RUN_TYPES = new Set([56, 57]); // RUNNING, RUNNING_TREADMILL

const PERMS = [
  { accessType: "read", recordType: "ExerciseSession" },
  { accessType: "read", recordType: "Distance" },
  { accessType: "read", recordType: "HeartRate" },
  { accessType: "read", recordType: "RestingHeartRate" },
  { accessType: "read", recordType: "HeartRateVariabilityRmssd" },
  { accessType: "read", recordType: "SleepSession" },
] as const;

function range(since: Date) {
  return { operator: "between" as const, startTime: since.toISOString(), endTime: new Date().toISOString() };
}

export const reader: HealthReader = {
  name: "health_connect",
  available: async () => {
    const status = await getSdkStatus();
    if (status !== SdkAvailabilityStatus.SDK_AVAILABLE) return false;
    return initialize();
  },
  requestPermissions: async () => {
    const granted = await requestPermission([...PERMS]);
    return granted.some((p) => "recordType" in p && p.recordType === "ExerciseSession");
  },
  readWorkouts: async (since: Date): Promise<HealthWorkout[]> => {
    const { records } = await readRecords("ExerciseSession", { timeRangeFilter: range(since) });
    const out: HealthWorkout[] = [];
    for (const r of records) {
      if (!RUN_TYPES.has(r.exerciseType)) continue;
      const tr = { operator: "between" as const, startTime: r.startTime, endTime: r.endTime };
      let distance = 0;
      let avg: number | null = null;
      let max: number | null = null;
      try {
        const d = await aggregateRecord({ recordType: "Distance", timeRangeFilter: tr });
        distance = d.DISTANCE?.inMeters ?? 0;
      } catch {
        // optional
      }
      try {
        const hr = await aggregateRecord({ recordType: "HeartRate", timeRangeFilter: tr });
        avg = hr.BPM_AVG || null;
        max = hr.BPM_MAX || null;
      } catch {
        // optional
      }
      out.push({
        source: "health_connect",
        external_id: r.metadata?.id ?? `${r.startTime}`,
        start_time: r.startTime,
        end_time: r.endTime,
        distance_m: distance,
        duration_s: (new Date(r.endTime).getTime() - new Date(r.startTime).getTime()) / 1000,
        sport: "run",
        avg_hr: avg,
        max_hr: max,
        name: r.title ?? "Health Connect",
      });
    }
    return out;
  },
  readDaily: async (since: Date): Promise<HealthDaily[]> => {
    const days = new Map<string, HealthDaily>();
    const get = (d: Date) => {
      const k = dayKey(d);
      if (!days.has(k)) days.set(k, { day: k, source: "health_connect" });
      return days.get(k)!;
    };
    const rhr = await readRecords("RestingHeartRate", { timeRangeFilter: range(since) });
    for (const r of rhr.records) get(new Date(r.time)).resting_hr = r.beatsPerMinute;
    const hrv = await readRecords("HeartRateVariabilityRmssd", { timeRangeFilter: range(since) });
    for (const r of hrv.records) get(new Date(r.time)).hrv_ms = r.heartRateVariabilityMillis;
    const sleep = await readRecords("SleepSession", { timeRangeFilter: range(since) });
    const byDay = new Map<string, number>();
    for (const r of sleep.records) {
      const end = new Date(r.endTime);
      const k = dayKey(end);
      byDay.set(k, (byDay.get(k) ?? 0) + (end.getTime() - new Date(r.startTime).getTime()) / 3600_000);
    }
    for (const [k, h] of byDay) get(new Date(`${k}T12:00:00`)).sleep_hours = Math.round(h * 100) / 100;
    return [...days.values()];
  },
};

export const syncHealth = (days?: number) => syncWith(reader, days);
export const healthName = "Health Connect";
