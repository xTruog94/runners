import { RefreshControl, ScrollView, Text, useWindowDimensions } from "react-native";

import { LoadChart, VolumeBars } from "../../components/charts";
import { Card, ErrorBox, H2, Loading, P, Row, Screen, Stat } from "../../components/ui";
import { api } from "../../lib/api";
import { DISTANCE_LABELS, fmtDuration, fmtPace, parseDate } from "../../lib/format";
import { useTheme } from "../../lib/theme";
import { useAsync } from "../../lib/useAsync";

export default function Stats() {
  const t = useTheme();
  const { width } = useWindowDimensions();
  const { data, error, loading, reload } = useAsync(() => Promise.all([api.stats(), api.weekly(), api.activities(15)]));
  if (loading && !data) return <Loading />;
  if (!data) return <ErrorBox message={error ?? "Lỗi"} onRetry={reload} />;
  const [stats, weekly, acts] = data;
  const f = stats.fitness;

  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40 }} refreshControl={<RefreshControl refreshing={loading} onRefresh={reload} />}>
        <Card>
          <H2>Tóm tắt tuần</H2>
          <P>{weekly.text}</P>
        </Card>

        <Card>
          <H2>Km mỗi tuần</H2>
          <VolumeBars
            data={stats.weekly.map((w) => {
              const d = parseDate(w.week_start);
              return { label: `${d.getDate()}/${d.getMonth() + 1}`, actual: w.actual_km, planned: w.planned_km };
            })}
          />
          <P muted style={{ fontSize: 12, marginTop: 6 }}>Cột cam: thực tế · khung nét đứt: kế hoạch</P>
        </Card>

        <Card>
          <H2>Thể lực & mệt mỏi (90 ngày)</H2>
          <LoadChart series={stats.load.series} width={width - 64} />
          <Row style={{ marginTop: 8 }}>
            <Stat label="CTL (thể lực)" value={stats.load.ctl.toFixed(0)} />
            <Stat label="ATL (mệt)" value={stats.load.atl.toFixed(0)} />
            <Stat label="ACWR" value={stats.load.acwr != null ? String(stats.load.acwr) : "–"} sub="0.8–1.3 an toàn" />
          </Row>
          <P muted style={{ fontSize: 12, marginTop: 6 }}>Xanh: CTL · Hồng: ATL</P>
        </Card>

        <Card>
          <H2>Dự đoán thành tích</H2>
          <P muted style={{ marginBottom: 6 }}>
            VDOT giáo án {f.plan_vdot ?? "–"}
            {f.hr_estimated_vdot ? ` · ước tính từ nhịp tim ${f.hr_estimated_vdot}` : ""}
            {f.completion_rate != null ? ` · hoàn thành ${Math.round(f.completion_rate * 100)}% buổi tập` : ""}
          </P>
          {f.predictions.map((p) => (
            <Row key={p.distance} style={{ justifyContent: "space-between", paddingVertical: 3 }}>
              <Text style={{ color: t.text }}>{DISTANCE_LABELS[p.distance]}</Text>
              <Text style={{ color: t.text, fontWeight: "700" }}>
                {fmtDuration(p.time_s)} <Text style={{ color: t.muted, fontWeight: "400" }}>({fmtPace(p.pace_s_per_km)}/km)</Text>
              </Text>
            </Row>
          ))}
        </Card>

        <Card>
          <H2>Hoạt động gần đây</H2>
          {acts.map((a) => (
            <Row key={a.id} style={{ justifyContent: "space-between", paddingVertical: 6 }}>
              <Text style={{ color: t.text, flex: 1 }} numberOfLines={1}>
                {a.local_date.slice(5)} · {a.name || a.sport}
              </Text>
              <Text style={{ color: t.muted }}>
                {(a.distance_m / 1000).toFixed(1)} km · {a.pace ?? "–"} · {a.source.split("_")[0]}
              </Text>
            </Row>
          ))}
          {!acts.length ? <P muted>Chưa có hoạt động. Kết nối Strava/Health trong tab Kết nối.</P> : null}
        </Card>
      </ScrollView>
    </Screen>
  );
}
