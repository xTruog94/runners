import {
  isHealthDataAvailableAsync,
  queryCategorySamples,
  queryQuantitySamples,
  queryWorkoutSamples,
  requestAuthorization,
  WorkoutActivityType,
} from "@kingstinct/react-native-healthkit";

import type { HealthDaily, HealthWorkout } from "../api";
import { dayKey, syncWith, toMeters, toSeconds, type HealthReader } from "./common";

const READ = [
  "HKWorkoutTypeIdentifier",
  "HKQuantityTypeIdentifierDistanceWalkingRunning",
  "HKQuantityTypeIdentifierHeartRate",
  "HKQuantityTypeIdentifierRestingHeartRate",
  "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
  "HKCategoryTypeIdentifierSleepAnalysis",
] as const;

// HKCategoryValueSleepAnalysis: 1 asleepUnspecified, 3 core, 4 deep, 5 REM
const ASLEEP = new Set([1, 3, 4, 5]);

export const reader: HealthReader = {
  name: "apple_health",
  available: () => isHealthDataAvailableAsync(),
  requestPermissions: async () => requestAuthorization({ toRead: READ }),
  readWorkouts: async (since: Date): Promise<HealthWorkout[]> => {
    const workouts = await queryWorkoutSamples({
      limit: 0,
      filter: { date: { startDate: since }, workoutActivityType: WorkoutActivityType.running },
    });
    const out: HealthWorkout[] = [];
    for (const w of workouts) {
      let avg: number | null = null;
      let max: number | null = null;
      try {
        const hr = await w.getStatistic("HKQuantityTypeIdentifierHeartRate", "count/min");
        avg = hr?.averageQuantity?.quantity ?? null;
        max = hr?.maximumQuantity?.quantity ?? null;
      } catch {
        // heart rate is optional
      }
      out.push({
        source: "apple_health",
        external_id: w.uuid,
        start_time: new Date(w.startDate).toISOString(),
        end_time: new Date(w.endDate).toISOString(),
        distance_m: toMeters(w.totalDistance),
        duration_s: toSeconds(w.duration),
        sport: "run",
        avg_hr: avg,
        max_hr: max,
        calories: w.totalEnergyBurned?.quantity ?? null,
        name: "Apple Health",
      });
      w.dispose();
    }
    return out;
  },
  readDaily: async (since: Date): Promise<HealthDaily[]> => {
    const days = new Map<string, HealthDaily>();
    const get = (d: Date) => {
      const k = dayKey(d);
      if (!days.has(k)) days.set(k, { day: k, source: "apple_health" });
      return days.get(k)!;
    };
    const rhr = await queryQuantitySamples("HKQuantityTypeIdentifierRestingHeartRate", { limit: 0, unit: "count/min", filter: { date: { startDate: since } } });
    for (const s of rhr) get(new Date(s.startDate)).resting_hr = s.quantity;
    const hrv = await queryQuantitySamples("HKQuantityTypeIdentifierHeartRateVariabilitySDNN", { limit: 0, unit: "ms", filter: { date: { startDate: since } } });
    const hrvByDay = new Map<string, number[]>();
    for (const s of hrv) {
      const k = dayKey(new Date(s.startDate));
      hrvByDay.set(k, [...(hrvByDay.get(k) ?? []), s.quantity]);
    }
    for (const [k, vals] of hrvByDay) get(new Date(`${k}T12:00:00`)).hrv_ms = vals.reduce((a, b) => a + b, 0) / vals.length;
    const sleep = await queryCategorySamples("HKCategoryTypeIdentifierSleepAnalysis", { limit: 0, filter: { date: { startDate: since } } });
    const sleepByDay = new Map<string, number>();
    for (const s of sleep) {
      if (!ASLEEP.has(Number(s.value))) continue;
      const end = new Date(s.endDate);
      const hours = (end.getTime() - new Date(s.startDate).getTime()) / 3600_000;
      const k = dayKey(end); // attribute to the morning you wake up
      sleepByDay.set(k, (sleepByDay.get(k) ?? 0) + hours);
    }
    for (const [k, h] of sleepByDay) get(new Date(`${k}T12:00:00`)).sleep_hours = Math.round(h * 100) / 100;
    return [...days.values()];
  },
};

export const syncHealth = (days?: number) => syncWith(reader, days);
export const healthName = "Apple Health";
