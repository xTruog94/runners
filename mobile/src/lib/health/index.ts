// Fallback for platforms without a health store (web). Metro picks
// index.ios.ts / index.android.ts on devices.
export async function syncHealth(_days?: number): Promise<{ workouts: number; daily: number }> {
  throw new Error("Nền tảng này không có Apple Health / Health Connect");
}
export const healthName = "Health";
