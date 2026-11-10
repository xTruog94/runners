import * as Location from "expo-location";
import { useKeepAwake } from "expo-keep-awake";
import { router, useLocalSearchParams } from "expo-router";
import * as Speech from "expo-speech";
import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, ScrollView, Text, View } from "react-native";

import { Btn, Card, Chip, H2, P, Row, Screen, Stat } from "../../components/ui";
import { api } from "../../lib/api";
import { fmtDuration, fmtPace } from "../../lib/format";
import { flatten, haversine, paceCue, spokenPace, stepDone, type FlatStep } from "../../lib/guided";
import { useTheme } from "../../lib/theme";
import type { Workout } from "../../lib/types";

type Lap = { distance_m: number; duration_s: number };

function say(text: string) {
  Speech.speak(text, { language: "vi-VN", rate: 1.0 });
}

function KeepAwake() {
  useKeepAwake();
  return null;
}

export default function Run() {
  const t = useTheme();
  const params = useLocalSearchParams<{ workoutId?: string }>();
  const [workout, setWorkout] = useState<Workout | null>(null);
  const [state, setState] = useState<"idle" | "running" | "paused" | "done">("idle");
  const [dist, setDist] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [stepIdx, setStepIdx] = useState(0);
  const [stepDist, setStepDist] = useState(0);
  const [stepTime, setStepTime] = useState(0);
  const [curPace, setCurPace] = useState(0);
  const [laps, setLaps] = useState<Lap[]>([]);
  const [rpe, setRpe] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const sub = useRef<Location.LocationSubscription | null>(null);
  const last = useRef<Location.LocationObject | null>(null);
  const recent = useRef<{ t: number; d: number }[]>([]);
  const startedAt = useRef<Date | null>(null);
  const lastKm = useRef(0);
  const lastCue = useRef(0);
  const s = useRef({ dist: 0, stepDist: 0, stepTime: 0, stepIdx: 0, elapsed: 0 });

  useEffect(() => {
    (async () => {
      try {
        if (params.workoutId) setWorkout(await api.workout(Number(params.workoutId)));
        else {
          const today = await api.today();
          setWorkout(today.workouts.find((w) => w.type !== "strength" && w.status === "planned") ?? null);
        }
      } catch {
        setWorkout(null);
      }
    })();
  }, [params.workoutId]);

  const steps: FlatStep[] = useMemo(() => flatten(workout?.heat_adjusted_steps ?? workout?.steps ?? []), [workout]);
  const step = steps[stepIdx];

  // 1 Hz clock
  useEffect(() => {
    if (state !== "running") return;
    const id = setInterval(() => {
      s.current.elapsed += 1;
      s.current.stepTime += 1;
      setElapsed(s.current.elapsed);
      setStepTime(s.current.stepTime);
      checkStep();
      // pace cue every 60 s inside a paced step
      const st = steps[s.current.stepIdx];
      if (st && s.current.elapsed - lastCue.current >= 60 && s.current.stepTime > 30) {
        lastCue.current = s.current.elapsed;
        const cue = paceCue(currentPace(), st);
        if (cue === "fast") say("Chậm lại một chút");
        else if (cue === "slow") say("Tăng tốc một chút");
      }
    }, 1000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, steps]);

  function currentPace(): number {
    const r = recent.current;
    if (r.length < 2) return 0;
    const dt = r[r.length - 1].t - r[0].t;
    const dd = r[r.length - 1].d - r[0].d;
    return dd > 5 ? dt / 1000 / (dd / 1000) : 0;
  }

  function announceStep(st: FlatStep | undefined) {
    if (!st) return;
    let text = `${st.rep ? `Lần ${st.rep.replace("/", " trên ")}. ` : ""}${st.label}`;
    if (st.fast && st.slow) text += `. Pace từ ${spokenPace(st.fast)} đến ${spokenPace(st.slow)}`;
    say(text);
  }

  function checkStep() {
    const st = steps[s.current.stepIdx];
    if (!st) return;
    if (stepDone(st, s.current.stepDist, s.current.stepTime)) nextStep();
  }

  function nextStep() {
    setLaps((prev) => [...prev, { distance_m: s.current.stepDist, duration_s: s.current.stepTime }]);
    s.current.stepIdx += 1;
    s.current.stepDist = 0;
    s.current.stepTime = 0;
    setStepIdx(s.current.stepIdx);
    setStepDist(0);
    setStepTime(0);
    if (s.current.stepIdx >= steps.length) {
      say("Hoàn thành bài tập. Bạn có thể tiếp tục chạy nhẹ hoặc kết thúc.");
    } else announceStep(steps[s.current.stepIdx]);
  }

  async function start() {
    const perm = await Location.requestForegroundPermissionsAsync();
    if (perm.status !== "granted") {
      Alert.alert("Cần quyền vị trí để đo quãng đường");
      return;
    }
    startedAt.current = new Date();
    setState("running");
    announceStep(steps[0] ?? { index: 0, kind: "run", label: "Bắt đầu chạy" });
    sub.current = await watch();
  }

  function onLocation(loc: Location.LocationObject) {
    if (loc.coords.accuracy != null && loc.coords.accuracy > 30) return;
    if (last.current) {
      const d = haversine(last.current.coords, loc.coords);
      if (d < 100) {
        s.current.dist += d;
        s.current.stepDist += d;
        setDist(s.current.dist);
        setStepDist(s.current.stepDist);
        recent.current = [...recent.current, { t: loc.timestamp, d: s.current.dist }].filter((p) => loc.timestamp - p.t <= 30000);
        setCurPace(currentPace());
        const km = Math.floor(s.current.dist / 1000);
        if (km > lastKm.current) {
          lastKm.current = km;
          const avg = s.current.elapsed / (s.current.dist / 1000);
          say(`${km} cây số. Pace trung bình ${spokenPace(avg)}`);
        }
        checkStep();
      }
    }
    last.current = loc;
  }

  function watch() {
    return Location.watchPositionAsync({ accuracy: Location.Accuracy.BestForNavigation, distanceInterval: 5, timeInterval: 2000 }, onLocation);
  }

  function pause() {
    sub.current?.remove();
    sub.current = null;
    last.current = null;
    setState("paused");
    say("Tạm dừng");
  }

  async function resume() {
    setState("running");
    say("Tiếp tục");
    sub.current = await watch();
  }

  function finish() {
    sub.current?.remove();
    sub.current = null;
    if (s.current.stepDist > 50) setLaps((prev) => [...prev, { distance_m: s.current.stepDist, duration_s: s.current.stepTime }]);
    setState("done");
    Speech.stop();
  }

  async function save() {
    if (!startedAt.current) return;
    setSaving(true);
    try {
      await api.addActivity({
        start_time: startedAt.current.toISOString(),
        distance_m: Math.round(s.current.dist),
        duration_s: s.current.elapsed,
        workout_id: workout?.id,
        rpe: rpe ?? undefined,
        laps,
        source: "phone",
        name: workout?.title ?? "Chạy bằng điện thoại",
      });
      router.replace(workout ? `/workout/${workout.id}` : "/");
    } catch (e) {
      Alert.alert("Lỗi lưu buổi chạy", e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  const avgPace = dist > 50 ? elapsed / (dist / 1000) : 0;
  const cue = step ? paceCue(curPace, step) : null;

  return (
    <Screen>
      {state === "running" ? <KeepAwake /> : null}
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40 }}>
        <Card>
          <H2>{workout?.title ?? "Chạy tự do"}</H2>
          {workout ? <P muted>{workout.description}</P> : <P muted>Không có bài tập hôm nay — app sẽ ghi lại buổi chạy tự do.</P>}
          <P muted style={{ fontSize: 12, marginTop: 6 }}>
            Đeo đồng hồ Garmin/COROS? Bài tập đã được đẩy lên đồng hồ — dùng đồng hồ sẽ chính xác hơn GPS điện thoại. Giữ màn hình mở khi chạy bằng điện thoại.
          </P>
        </Card>

        <Card>
          <Row>
            <Stat label="Quãng đường" value={`${(dist / 1000).toFixed(2)} km`} />
            <Stat label="Thời gian" value={fmtDuration(elapsed)} />
          </Row>
          <Row style={{ marginTop: 12 }}>
            <Stat label="Pace hiện tại" value={fmtPace(curPace)} />
            <Stat label="Pace TB" value={fmtPace(avgPace)} />
          </Row>
        </Card>

        {step && state !== "idle" ? (
          <Card style={{ borderColor: cue === "fast" ? t.warn : cue === "slow" ? t.bad : cue === "ok" ? t.good : t.border, borderWidth: 2 }}>
            <Text style={{ color: t.muted, fontSize: 12 }}>
              BƯỚC {stepIdx + 1}/{steps.length} {step.rep ? `· lần ${step.rep}` : ""}
            </Text>
            <Text style={{ color: t.text, fontSize: 22, fontWeight: "800" }}>{step.label}</Text>
            {step.fast && step.slow ? (
              <Text style={{ color: t.text, fontSize: 16 }}>
                Mục tiêu {fmtPace(step.fast)}–{fmtPace(step.slow)}/km {cue === "fast" ? "· chậm lại" : cue === "slow" ? "· nhanh lên" : cue === "ok" ? "· tốt" : ""}
              </Text>
            ) : null}
            <Text style={{ color: t.muted, marginTop: 4 }}>
              {step.distance_m ? `Còn ${Math.max(0, step.distance_m - stepDist).toFixed(0)} m` : step.duration_s ? `Còn ${fmtDuration(Math.max(0, step.duration_s - stepTime))}` : "Bước tự do"}
            </Text>
            {steps[stepIdx + 1] ? <Text style={{ color: t.muted, fontSize: 12, marginTop: 4 }}>Tiếp: {steps[stepIdx + 1].label}</Text> : null}
          </Card>
        ) : null}

        {state === "idle" ? <Btn title="▶ Bắt đầu" onPress={start} /> : null}
        {state === "running" ? (
          <Row>
            <View style={{ flex: 1 }}>
              <Btn kind="secondary" title="Bước tiếp" onPress={nextStep} />
            </View>
            <View style={{ flex: 1 }}>
              <Btn kind="secondary" title="⏸ Tạm dừng" onPress={pause} />
            </View>
          </Row>
        ) : null}
        {state === "paused" ? (
          <Row>
            <View style={{ flex: 1 }}>
              <Btn title="▶ Tiếp tục" onPress={resume} />
            </View>
            <View style={{ flex: 1 }}>
              <Btn kind="danger" title="■ Kết thúc" onPress={finish} />
            </View>
          </Row>
        ) : null}
        {state === "done" ? (
          <Card>
            <H2>Cảm giác buổi tập (RPE 1–10)</H2>
            <Row style={{ flexWrap: "wrap" }}>
              {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
                <Chip key={n} label={String(n)} active={rpe === n} onPress={() => setRpe(n)} />
              ))}
            </Row>
            <View style={{ marginTop: 12 }}>
              <Btn title="Lưu buổi chạy" onPress={save} loading={saving} />
            </View>
          </Card>
        ) : null}
      </ScrollView>
    </Screen>
  );
}
