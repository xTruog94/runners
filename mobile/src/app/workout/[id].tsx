import { router, Stack, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Alert, ScrollView, Text, View } from "react-native";

import { Btn, Card, Chip, ErrorBox, Field, H2, Loading, P, Row, Screen, Stat } from "../../components/ui";
import { StatusBadge, StepList } from "../../components/workout";
import { api } from "../../lib/api";
import { addDays, fmtDay, fmtDuration, fmtPace, TYPE_LABELS } from "../../lib/format";
import { useTheme } from "../../lib/theme";
import { useAsync } from "../../lib/useAsync";

export default function WorkoutDetail() {
  const t = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { data: w, error, loading, reload, setData } = useAsync(() => api.workout(Number(id)), [id]);
  const [busy, setBusy] = useState<string | null>(null);
  const [notes, setNotes] = useState<string | null>(null);

  if (loading && !w) return <Loading />;
  if (!w) return <ErrorBox message={error ?? "Không tìm thấy"} onRetry={reload} />;

  const patch = async (body: Parameters<typeof api.patchWorkout>[1], label: string) => {
    setBusy(label);
    try {
      setData(await api.patchWorkout(w.id, body));
    } catch (e) {
      Alert.alert("Lỗi", e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const a = w.analysis;
  const act = w.activity;

  return (
    <Screen>
      <Stack.Screen options={{ title: TYPE_LABELS[w.type] ?? "Buổi tập" }} />
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40 }}>
        <Card>
          <Text style={{ color: t.muted }}>{fmtDay(w.date)}</Text>
          <H2>{w.title}</H2>
          <StatusBadge status={w.status} />
          <P muted style={{ marginTop: 6 }}>{w.description}</P>
          <Row style={{ marginTop: 10 }}>
            {w.distance_km ? <Stat label="Quãng đường" value={`${w.distance_km} km`} /> : null}
            {w.duration_min ? <Stat label="Thời gian ước tính" value={`${Math.round(w.duration_min)} phút`} /> : null}
          </Row>
        </Card>

        {w.steps.length ? (
          <Card>
            <H2>Cấu trúc bài</H2>
            <StepList steps={w.heat_adjusted_steps ?? w.steps} />
            {w.heat ? <P style={{ color: t.warn, fontSize: 13, marginTop: 8 }}>Pace đã điều chỉnh {w.heat.slowdown_pct}% do nóng ẩm.</P> : null}
          </Card>
        ) : null}

        {w.exercises?.length ? (
          <Card>
            <H2>Bài tập</H2>
            {w.exercises.map((e, i) => (
              <Row key={i} style={{ justifyContent: "space-between", paddingVertical: 4 }}>
                <Text style={{ color: t.text, flex: 1 }}>{e.name}</Text>
                <Text style={{ color: t.muted }}>
                  {e.sets} x {e.reps}
                </Text>
              </Row>
            ))}
          </Card>
        ) : null}

        {a ? (
          <Card style={{ borderColor: a.pace_vs_target === "on" ? t.good : t.warn }}>
            <H2>Phân tích · {a.score}/100</H2>
            <P>{a.summary}</P>
            {a.tips.map((tip, i) => (
              <P key={i} muted style={{ marginTop: 4 }}>
                • {tip}
              </P>
            ))}
            {act ? (
              <Row style={{ marginTop: 10 }}>
                <Stat label="Thực tế" value={`${(act.distance_m / 1000).toFixed(2)} km`} sub={fmtDuration(act.duration_s)} />
                <Stat label="Pace" value={fmtPace(act.duration_s / (act.distance_m / 1000))} sub={act.avg_hr ? `${Math.round(act.avg_hr)} bpm` : undefined} />
                <Stat label="Nguồn" value={act.source.replace("_", " ")} />
              </Row>
            ) : null}
          </Card>
        ) : null}

        {w.status !== "planned" && w.type !== "strength" ? (
          <Card>
            <H2>Cảm giác (RPE)</H2>
            <Row style={{ flexWrap: "wrap" }}>
              {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
                <Chip key={n} label={String(n)} active={w.rpe === n} onPress={() => patch({ rpe: n }, "rpe")} />
              ))}
            </Row>
            <P muted style={{ fontSize: 12, marginTop: 6 }}>1–3 rất nhẹ · 4–6 vừa · 7–8 nặng · 9–10 hết sức</P>
          </Card>
        ) : null}

        <Card>
          <H2>Ghi chú</H2>
          <Field label="" value={notes ?? w.notes ?? ""} onChangeText={setNotes} multiline placeholder="Đau chân trái nhẹ, trời nóng…" />
          {notes !== null && notes !== (w.notes ?? "") ? <Btn small title="Lưu ghi chú" onPress={() => patch({ notes }, "notes")} loading={busy === "notes"} /> : null}
        </Card>

        {w.status === "planned" ? (
          <View style={{ gap: 8 }}>
            {w.type !== "strength" ? <Btn title="▶ Chạy với hướng dẫn" onPress={() => router.push({ pathname: "/run", params: { workoutId: String(w.id) } })} /> : null}
            {w.type === "strength" ? <Btn title="✓ Đã tập xong" onPress={() => patch({ status: "completed" }, "done")} loading={busy === "done"} /> : null}
            <Row>
              <View style={{ flex: 1 }}>
                <Btn kind="secondary" title="← Lùi 1 ngày" onPress={() => patch({ date: addDays(w.date, -1) }, "move")} />
              </View>
              <View style={{ flex: 1 }}>
                <Btn kind="secondary" title="Dời 1 ngày →" onPress={() => patch({ date: addDays(w.date, 1) }, "move")} />
              </View>
            </Row>
            {w.type !== "strength" ? (
              <Btn
                kind="secondary"
                title="⌚ Gửi lên đồng hồ"
                loading={busy === "push"}
                onPress={async () => {
                  setBusy("push");
                  try {
                    const r = await api.pushWorkout(w.id);
                    Alert.alert("Đồng hồ", Object.entries(r).map(([k, v]) => `${k}: ${String(v)}`).join("\n") || "Chưa kết nối Garmin/COROS");
                    reload();
                  } finally {
                    setBusy(null);
                  }
                }}
              />
            ) : null}
            <Btn kind="danger" title="Bỏ buổi này" onPress={() => patch({ status: "skipped" }, "skip")} />
          </View>
        ) : null}
      </ScrollView>
    </Screen>
  );
}
