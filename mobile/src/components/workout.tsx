import { router } from "expo-router";
import { Pressable, Text, View } from "react-native";

import { fmtDay, fmtPace, STATUS_LABELS, TYPE_LABELS } from "../lib/format";
import { TYPE_COLORS, useTheme } from "../lib/theme";
import type { Step, Workout } from "../lib/types";

function amount(s: Step): string {
  if (s.distance_m) return s.distance_m >= 1000 ? `${+(s.distance_m / 1000).toFixed(2)} km` : `${Math.round(s.distance_m)} m`;
  if (s.duration_s) return s.duration_s >= 60 ? `${Math.floor(s.duration_s / 60)}′${s.duration_s % 60 ? `${s.duration_s % 60}″` : ""}` : `${s.duration_s}″`;
  return "tự do";
}

const KIND: Record<string, string> = { warmup: "Khởi động", run: "Chạy", recovery: "Hồi phục", cooldown: "Thả lỏng" };

function StepRow({ s, indent = 0 }: { s: Step; indent?: number }) {
  const t = useTheme();
  if (s.kind === "repeat") {
    return (
      <View style={{ marginLeft: indent, borderLeftWidth: 3, borderLeftColor: t.primary, paddingLeft: 8, marginVertical: 4 }}>
        <Text style={{ color: t.primary, fontWeight: "700" }}>Lặp {s.repeats} lần</Text>
        {(s.steps ?? []).map((c, i) => (
          <StepRow key={i} s={c} indent={4} />
        ))}
      </View>
    );
  }
  const tgt = s.target;
  return (
    <View style={{ marginLeft: indent, paddingVertical: 4 }}>
      <Text style={{ color: t.text, fontSize: 15 }}>
        <Text style={{ fontWeight: "600" }}>{KIND[s.kind] ?? s.kind}</Text> {amount(s)}
        {tgt?.fast_s_per_km ? (
          <Text style={{ color: t.muted }}>
            {"  "}@ {fmtPace(tgt.fast_s_per_km)}–{fmtPace(tgt.slow_s_per_km)}/km
          </Text>
        ) : null}
      </Text>
      {s.note ? <Text style={{ color: t.muted, fontSize: 13 }}>{s.note}</Text> : null}
    </View>
  );
}

export function StepList({ steps }: { steps: Step[] }) {
  return (
    <View>
      {steps.map((s, i) => (
        <StepRow key={i} s={s} />
      ))}
    </View>
  );
}

export function StatusBadge({ status }: { status: Workout["status"] }) {
  const t = useTheme();
  const color = status === "completed" ? t.good : status === "partial" ? t.warn : status === "missed" ? t.bad : t.muted;
  return <Text style={{ color, fontSize: 12, fontWeight: "600" }}>{status === "completed" ? "✓ " : ""}{STATUS_LABELS[status] ?? status}</Text>;
}

export function WorkoutRow({ w, showDate = true }: { w: Workout; showDate?: boolean }) {
  const t = useTheme();
  const color = TYPE_COLORS[w.type] ?? t.muted;
  const done = w.status === "completed" || w.status === "partial";
  return (
    <Pressable onPress={() => router.push(`/workout/${w.id}`)} style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}>
      <View style={{ flexDirection: "row", alignItems: "center", paddingVertical: 10, gap: 10 }}>
        <View style={{ width: 6, alignSelf: "stretch", borderRadius: 3, backgroundColor: color, opacity: w.status === "skipped" || w.status === "missed" ? 0.3 : 1 }} />
        <View style={{ flex: 1 }}>
          {showDate ? <Text style={{ color: t.muted, fontSize: 12 }}>{fmtDay(w.date)} · {TYPE_LABELS[w.type] ?? w.type}</Text> : null}
          <Text style={{ color: t.text, fontSize: 16, fontWeight: w.key ? "700" : "500", textDecorationLine: w.status === "skipped" ? "line-through" : "none" }}>{w.title}</Text>
          <View style={{ flexDirection: "row", gap: 10, marginTop: 2 }}>
            {w.distance_km ? <Text style={{ color: t.muted, fontSize: 13 }}>{w.distance_km} km</Text> : null}
            {w.duration_min ? <Text style={{ color: t.muted, fontSize: 13 }}>~{Math.round(w.duration_min)} phút</Text> : null}
            {w.synced?.garmin ? <Text style={{ color: t.muted, fontSize: 13 }}>⌚G</Text> : null}
            {w.synced?.coros ? <Text style={{ color: t.muted, fontSize: 13 }}>⌚C</Text> : null}
          </View>
        </View>
        <View style={{ alignItems: "flex-end" }}>
          <StatusBadge status={w.status} />
          {done && w.analysis ? <Text style={{ color: t.muted, fontSize: 12 }}>{w.analysis.score} điểm</Text> : null}
        </View>
      </View>
    </Pressable>
  );
}
