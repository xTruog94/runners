import { useColorScheme } from "react-native";

const light = {
  bg: "#F5F6F8",
  card: "#FFFFFF",
  text: "#111827",
  muted: "#6B7280",
  border: "#E5E7EB",
  primary: "#FF5A1F",
  primaryText: "#FFFFFF",
  good: "#16A34A",
  warn: "#D97706",
  bad: "#DC2626",
  chip: "#F3F4F6",
};

const dark: typeof light = {
  bg: "#0B0D10",
  card: "#16191E",
  text: "#F3F4F6",
  muted: "#9CA3AF",
  border: "#2A2F36",
  primary: "#FF6B35",
  primaryText: "#FFFFFF",
  good: "#22C55E",
  warn: "#F59E0B",
  bad: "#F87171",
  chip: "#21252B",
};

export type Theme = typeof light;

export function useTheme(): Theme {
  return useColorScheme() === "dark" ? dark : light;
}

export const TYPE_COLORS: Record<string, string> = {
  easy: "#22C55E",
  recovery: "#86EFAC",
  long: "#3B82F6",
  tempo: "#F59E0B",
  intervals: "#EF4444",
  fartlek: "#F97316",
  hills: "#A855F7",
  progression: "#EAB308",
  race_pace: "#EC4899",
  shakeout: "#14B8A6",
  race: "#FF5A1F",
  strength: "#64748B",
  rest: "#9CA3AF",
};
