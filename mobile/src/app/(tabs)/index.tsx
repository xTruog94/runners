import { router } from "expo-router";
import { useState } from "react";
import { RefreshControl, ScrollView, Text, View } from "react-native";

import { ReadinessRing } from "../../components/charts";
import { Btn, Card, ErrorBox, H2, Loading, P, Row, Screen, Stat } from "../../components/ui";
import { StepList, WorkoutRow } from "../../components/workout";
import { api } from "../../lib/api";
import { DISTANCE_LABELS, fmtDay, PHASE_LABELS } from "../../lib/format";
import { healthName, syncHealth } from "../../lib/health";
import { useTheme } from "../../lib/theme";
import { useAsync } from "../../lib/useAsync";

export default function Today() {
  const t = useTheme();
  const { data, error, loading, reload } = useAsync(() => api.today());
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);

  const refresh = async () => {
    setSyncing(true);
    setSyncMsg(null);
    const msgs: string[] = [];
    try {
      const r = await syncHealth();
      msgs.push(`${healthName}: ${r.workouts} buổi`);
    } catch (e) {
      msgs.push(`${healthName}: ${e instanceof Error ? e.message : e}`);
    }
    try {
      await api.syncAll();
    } catch (e) {
      msgs.push(`Đồng bộ: ${e instanceof Error ? e.message : e}`);
    }
    setSyncMsg(msgs.join(" · "));
    await reload();
    setSyncing(false);
  };

  if (loading && !data) return <Loading />;
  if (error && !data) {
    return (
      <Screen>
        <View style={{ padding: 16 }}>
          {error.includes("Chưa có giáo án") ? (
            <Card>
              <H2>Chưa có giáo án</H2>
              <P muted>Tạo giáo án đầu tiên dựa trên mục tiêu và thể lực của bạn.</P>
              <View style={{ marginTop: 12 }}>
                <Btn title="Tạo giáo án" onPress={() => router.push("/onboarding")} />
              </View>
            </Card>
          ) : (
            <ErrorBox message={error} onRetry={reload} />
          )}
        </View>
      </Screen>
    );
  }
  if (!data) return <Loading />;

  const main = data.workouts.find((w) => w.type !== "strength");
  const extras = data.workouts.filter((w) => w !== main);
  const steps = main?.heat_adjusted_steps ?? main?.steps ?? [];

  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40 }} refreshControl={<RefreshControl refreshing={syncing} onRefresh={refresh} />}>
        <Row style={{ justifyContent: "space-between", marginBottom: 12 }}>
          <View>
            <Text style={{ color: t.muted }}>{fmtDay(data.date)}</Text>
            {data.goal ? (
              <Text style={{ color: t.text, fontSize: 16, fontWeight: "600" }}>
                {DISTANCE_LABELS[data.goal.distance]}
                {data.days_to_race != null ? ` · còn ${data.days_to_race} ngày` : ""}
              </Text>
            ) : null}
            {data.week ? (
              <Text style={{ color: t.muted, fontSize: 13 }}>
                Tuần {data.week.index + 1} · {PHASE_LABELS[data.week.phase] ?? data.week.phase}
                {data.week.is_cutback ? " · tuần hồi phục" : ""} · {data.week.target_km} km
              </Text>
            ) : null}
          </View>
          <ReadinessRing score={data.readiness.score} />
        </Row>
        {syncMsg ? <P muted style={{ marginBottom: 8, fontSize: 12 }}>{syncMsg}</P> : null}

        {(data.pending_adjustments ?? []).map((a) => (
          <Card key={a.id} style={{ borderColor: t.warn }}>
            <P>💡 {a.reason}</P>
            <Row style={{ marginTop: 10 }}>
              <Btn
                small
                title="Áp dụng"
                onPress={async () => {
                  await api.applyAdjustment(a.id);
                  reload();
                }}
              />
              <Btn
                small
                kind="secondary"
                title="Bỏ qua"
                onPress={async () => {
                  await api.dismissAdjustment(a.id);
                  reload();
                }}
              />
            </Row>
          </Card>
        ))}

        <Card>
          {main ? (
            <>
              <WorkoutRow w={main} showDate={false} />
              <P muted style={{ marginBottom: 8 }}>{main.description}</P>
              <StepList steps={steps} />
              {main.heat ? (
                <P style={{ color: t.warn, marginTop: 8, fontSize: 13 }}>
                  🌡 {main.heat.temp_c.toFixed(0)}°C, ẩm {main.heat.humidity}% lúc {main.heat.hour}h: pace đã chậm lại {main.heat.slowdown_pct}%. {main.heat.advice}
                  {main.heat.best_hour != null && main.heat.best_hour !== main.heat.hour ? ` Giờ mát nhất: ${main.heat.best_hour}h.` : ""}
                </P>
              ) : null}
              {main.status === "planned" ? (
                <Row style={{ marginTop: 12 }}>
                  <View style={{ flex: 1 }}>
                    <Btn title="▶ Chạy với hướng dẫn" onPress={() => router.push({ pathname: "/run", params: { workoutId: String(main.id) } })} />
                  </View>
                </Row>
              ) : null}
            </>
          ) : (
            <>
              <H2>Hôm nay nghỉ 😴</H2>
              <P muted>Nghỉ ngơi là một phần của tập luyện. Ngủ đủ, ăn uống tốt.</P>
            </>
          )}
        </Card>

        {extras.map((w) => (
          <Card key={w.id}>
            <WorkoutRow w={w} showDate={false} />
          </Card>
        ))}

        <Card>
          <Row>
            <Stat label="Thể lực (CTL)" value={data.load.ctl.toFixed(0)} />
            <Stat label="Mệt (ATL)" value={data.load.atl.toFixed(0)} />
            <Stat label="Form (TSB)" value={data.load.tsb.toFixed(0)} />
          </Row>
          {data.readiness.factors.length ? <P muted style={{ marginTop: 8, fontSize: 13 }}>{data.readiness.factors.join(" · ")}</P> : null}
        </Card>

        {data.next ? (
          <Card>
            <Text style={{ color: t.muted, fontSize: 12, marginBottom: 4 }}>BUỔI TIẾP THEO</Text>
            <WorkoutRow w={data.next} />
          </Card>
        ) : null}

        <Row style={{ marginTop: 4 }}>
          <View style={{ flex: 1 }}>
            <Btn kind="secondary" title="🤒 Không khỏe 100%" onPress={() => router.push("/not-feeling")} />
          </View>
          <View style={{ flex: 1 }}>
            <Btn kind="secondary" title="💬 Coach" onPress={() => router.push("/coach")} />
          </View>
        </Row>
      </ScrollView>
    </Screen>
  );
}
