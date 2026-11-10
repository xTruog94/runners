import { router } from "expo-router";
import { useMemo, useState } from "react";
import { ScrollView, Switch, Text, View } from "react-native";

import { Btn, Card, Chip, Field, H2, P, Row, Screen } from "../components/ui";
import { api, type CreatePlanBody } from "../lib/api";
import { DISTANCE_LABELS, isoDate, parseDuration, WEEKDAY_LABELS } from "../lib/format";
import { useTheme } from "../lib/theme";

const RACE_DIST: Record<string, number> = { "5k": 5000, "10k": 10000, half: 21097.5, marathon: 42195 };

export default function Onboarding() {
  const t = useTheme();
  const [distance, setDistance] = useState<"5k" | "10k" | "half" | "marathon" | "general">("half");
  const [raceDate, setRaceDate] = useState(isoDate(new Date(Date.now() + 16 * 7 * 86400_000)));
  const [goalTime, setGoalTime] = useState("");
  const [level, setLevel] = useState<"beginner" | "intermediate" | "advanced">("intermediate");
  const [weeklyKm, setWeeklyKm] = useState("20");
  const [longest, setLongest] = useState("");
  const [days, setDays] = useState<number[]>([1, 3, 5, 6]);
  const [longDay, setLongDay] = useState(6);
  const [raceKind, setRaceKind] = useState<string>("5k");
  const [raceTime, setRaceTime] = useState("");
  const [easyPace, setEasyPace] = useState("");
  const [maxHr, setMaxHr] = useState("");
  const [restHr, setRestHr] = useState("");
  const [strength, setStrength] = useState(true);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<{ start_vdot: number; goal_vdot: number; warnings: string[]; weeks: { target_km: number }[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const body = useMemo((): CreatePlanBody | null => {
    const rt = parseDuration(raceTime);
    const gt = parseDuration(goalTime);
    const ep = parseDuration(easyPace);
    if (!days.length) return null;
    return {
      goal: {
        distance,
        race_date: distance === "general" ? null : raceDate,
        target_time_s: distance === "general" ? null : gt,
        start_date: isoDate(new Date()),
      },
      profile: {
        level,
        current_weekly_km: Number(weeklyKm) || 0,
        longest_recent_run_km: longest ? Number(longest) : null,
        days_per_week: days.length,
        available_days: days,
        long_run_day: days.includes(longDay) ? longDay : days[days.length - 1],
        recent_race: rt ? { distance_m: RACE_DIST[raceKind], time_s: rt } : null,
        easy_pace_s_per_km: !rt && ep ? ep : null,
        max_hr: maxHr ? Number(maxHr) : null,
        resting_hr: restHr ? Number(restHr) : null,
        include_strength: strength,
        strides: true,
      },
    };
  }, [distance, raceDate, goalTime, level, weeklyKm, longest, days, longDay, raceKind, raceTime, easyPace, maxHr, restHr, strength]);

  const toggleDay = (d: number) => setDays((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort()));

  const doPreview = async () => {
    if (!body) return;
    setError(null);
    try {
      setPreview(await api.previewPlan(body));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const create = async () => {
    if (!body) return;
    setBusy(true);
    setError(null);
    try {
      await api.createPlan(body);
      router.replace("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 60 }}>
        <Card>
          <H2>1. Mục tiêu</H2>
          <Row style={{ flexWrap: "wrap", marginBottom: 12 }}>
            {(Object.keys(DISTANCE_LABELS) as (keyof typeof DISTANCE_LABELS)[]).map((k) => (
              <Chip key={k} label={DISTANCE_LABELS[k]} active={distance === k} onPress={() => setDistance(k as typeof distance)} />
            ))}
          </Row>
          {distance !== "general" ? (
            <>
              <Field label="Ngày thi (YYYY-MM-DD)" value={raceDate} onChangeText={setRaceDate} autoCapitalize="none" />
              <Field label="Thời gian mục tiêu (h:mm:ss, bỏ trống = theo thể lực)" value={goalTime} onChangeText={setGoalTime} placeholder="1:55:00" />
            </>
          ) : (
            <P muted>Chu kỳ 12 tuần giúp chạy đều, khỏe hơn, không cần ngày thi.</P>
          )}
        </Card>

        <Card>
          <H2>2. Thể lực hiện tại</H2>
          <Row style={{ marginBottom: 12 }}>
            <Chip label="Mới chạy" active={level === "beginner"} onPress={() => setLevel("beginner")} />
            <Chip label="Trung bình" active={level === "intermediate"} onPress={() => setLevel("intermediate")} />
            <Chip label="Nâng cao" active={level === "advanced"} onPress={() => setLevel("advanced")} />
          </Row>
          <Field label="Km/tuần trung bình 4 tuần qua" value={weeklyKm} onChangeText={setWeeklyKm} keyboardType="numeric" />
          <Field label="Buổi chạy dài nhất gần đây (km)" value={longest} onChangeText={setLongest} keyboardType="numeric" />
          <P muted>Thành tích gần đây (chính xác nhất để tính pace):</P>
          <Row style={{ marginVertical: 8 }}>
            {["5k", "10k", "half", "marathon"].map((k) => (
              <Chip key={k} label={DISTANCE_LABELS[k]} active={raceKind === k} onPress={() => setRaceKind(k)} />
            ))}
          </Row>
          <Field label="Thời gian (h:mm:ss hoặc mm:ss)" value={raceTime} onChangeText={setRaceTime} placeholder="27:30" />
          {!raceTime ? <Field label="…hoặc pace chạy nhẹ thoải mái (mm:ss /km)" value={easyPace} onChangeText={setEasyPace} placeholder="7:00" /> : null}
          <Row>
            <View style={{ flex: 1 }}>
              <Field label="Nhịp tim tối đa" value={maxHr} onChangeText={setMaxHr} keyboardType="numeric" />
            </View>
            <View style={{ flex: 1 }}>
              <Field label="Nhịp tim nghỉ" value={restHr} onChangeText={setRestHr} keyboardType="numeric" />
            </View>
          </Row>
        </Card>

        <Card>
          <H2>3. Lịch tập</H2>
          <P muted>Chọn các ngày có thể chạy ({days.length} ngày/tuần):</P>
          <Row style={{ flexWrap: "wrap", marginVertical: 8 }}>
            {WEEKDAY_LABELS.map((l, i) => (
              <Chip key={i} label={l} active={days.includes(i)} onPress={() => toggleDay(i)} />
            ))}
          </Row>
          <P muted>Ngày chạy dài:</P>
          <Row style={{ flexWrap: "wrap", marginVertical: 8 }}>
            {days.map((i) => (
              <Chip key={i} label={WEEKDAY_LABELS[i]} active={longDay === i} onPress={() => setLongDay(i)} color="#3B82F6" />
            ))}
          </Row>
          <Row style={{ justifyContent: "space-between" }}>
            <Text style={{ color: t.text }}>Bài tập sức mạnh (2 buổi/tuần)</Text>
            <Switch value={strength} onValueChange={setStrength} />
          </Row>
        </Card>

        {preview ? (
          <Card>
            <H2>Xem trước</H2>
            <P>
              VDOT {preview.start_vdot} → {preview.goal_vdot} · {preview.weeks.length} tuần · đỉnh {Math.max(...preview.weeks.map((w) => w.target_km))} km/tuần
            </P>
            {preview.warnings.map((w, i) => (
              <P key={i} style={{ color: t.warn, marginTop: 6 }}>
                ⚠ {w}
              </P>
            ))}
          </Card>
        ) : null}
        {error ? <P style={{ color: t.bad, marginBottom: 8 }}>{error}</P> : null}
        <View style={{ gap: 8 }}>
          <Btn kind="secondary" title="Xem trước" onPress={doPreview} disabled={!body} />
          <Btn title="Tạo giáo án" onPress={create} loading={busy} disabled={!body} />
        </View>
      </ScrollView>
    </Screen>
  );
}
