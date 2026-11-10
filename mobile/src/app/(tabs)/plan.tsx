import { router } from "expo-router";
import { useState } from "react";
import { Alert, RefreshControl, ScrollView, Text, View } from "react-native";

import { Btn, Card, ErrorBox, H2, Loading, P, Row, Screen } from "../../components/ui";
import { WorkoutRow } from "../../components/workout";
import { api } from "../../lib/api";
import { DISTANCE_LABELS, fmtDay, isoDate, PHASE_LABELS } from "../../lib/format";
import { useTheme } from "../../lib/theme";
import { useAsync } from "../../lib/useAsync";

export default function Plan() {
  const t = useTheme();
  const { data, error, loading, reload } = useAsync(() => api.plan());
  const [showPast, setShowPast] = useState(false);

  if (loading && !data) return <Loading />;
  if (!data)
    return (
      <Screen>
        <View style={{ padding: 16 }}>
          <ErrorBox message={error ?? "Không tải được giáo án"} onRetry={reload} />
          <Btn title="Tạo giáo án" onPress={() => router.push("/onboarding")} />
        </View>
      </Screen>
    );

  const today = isoDate(new Date());
  const weeks = data.weeks.filter((w) => showPast || isoDate(new Date(new Date(w.start_date).getTime() + 7 * 86400_000)) > today);
  const p = data.plan;

  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40 }} refreshControl={<RefreshControl refreshing={loading} onRefresh={reload} />}>
        <Card>
          <H2>
            {DISTANCE_LABELS[p.goal.distance]} {p.goal.race_date ? `· ${fmtDay(p.goal.race_date)}` : ""}
          </H2>
          <P muted>
            VDOT hiện tại {p.current_vdot} (mục tiêu {p.goal_vdot}) · {data.weeks.length} tuần
          </P>
          {p.warnings.map((w, i) => (
            <P key={i} style={{ color: t.warn, fontSize: 13, marginTop: 4 }}>
              ⚠ {w}
            </P>
          ))}
          <View style={{ marginTop: 10 }}>
            {Object.entries(data.zones).map(([k, z]) => (
              <Row key={k} style={{ justifyContent: "space-between" }}>
                <Text style={{ color: t.text }}>{z.label}</Text>
                <Text style={{ color: t.muted }}>
                  {z.fast}–{z.slow}
                </Text>
              </Row>
            ))}
          </View>
          <Row style={{ marginTop: 12, flexWrap: "wrap" }}>
            <Btn small kind="secondary" title={showPast ? "Ẩn tuần cũ" : "Hiện tuần cũ"} onPress={() => setShowPast(!showPast)} />
            <Btn
              small
              kind="secondary"
              title="Tính lại từ hôm nay"
              onPress={() =>
                Alert.alert("Tính lại giáo án?", "Các buổi chưa tập từ hôm nay sẽ được tạo lại theo khối lượng thực tế gần đây.", [
                  { text: "Huỷ", style: "cancel" },
                  { text: "Tính lại", onPress: async () => { await api.regenerate(); reload(); } },
                ])
              }
            />
            <Btn small kind="secondary" title="Mục tiêu mới" onPress={() => router.push("/onboarding")} />
          </Row>
        </Card>

        {weeks.map((wk) => {
          const done = wk.workouts.filter((w) => w.status === "completed" || w.status === "partial").reduce((a, w) => a + (w.analysis ? w.distance_km * w.analysis.compliance : w.distance_km), 0);
          const current = wk.start_date <= today && today < isoDate(new Date(new Date(wk.start_date).getTime() + 7 * 86400_000));
          return (
            <Card key={wk.id} style={current ? { borderColor: t.primary, borderWidth: 2 } : undefined}>
              <Row style={{ justifyContent: "space-between" }}>
                <Text style={{ color: t.text, fontWeight: "700", fontSize: 16 }}>
                  Tuần {wk.index + 1} · {PHASE_LABELS[wk.phase] ?? wk.phase}
                  {wk.is_cutback ? " · hồi phục" : ""}
                </Text>
                <Text style={{ color: t.muted }}>
                  {done ? `${done.toFixed(0)}/` : ""}
                  {wk.planned_km} km
                </Text>
              </Row>
              <Text style={{ color: t.muted, fontSize: 12 }}>Từ {fmtDay(wk.start_date)}</Text>
              {wk.workouts.map((w) => (
                <WorkoutRow key={w.id} w={w} />
              ))}
            </Card>
          );
        })}
      </ScrollView>
    </Screen>
  );
}
