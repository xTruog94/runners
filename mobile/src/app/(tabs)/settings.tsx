import * as WebBrowser from "expo-web-browser";
import { router } from "expo-router";
import { useState } from "react";
import { Alert, Linking, RefreshControl, ScrollView, Switch, Text, View } from "react-native";

import { Btn, Card, ErrorBox, Field, H2, Loading, P, Row, Screen } from "../../components/ui";
import { api, clearServer } from "../../lib/api";
import { healthName, syncHealth } from "../../lib/health";
import { useTheme } from "../../lib/theme";
import type { SyncLog } from "../../lib/types";
import { useAsync } from "../../lib/useAsync";

function LastSync({ log }: { log?: SyncLog | null }) {
  const t = useTheme();
  if (!log) return null;
  return (
    <Text style={{ color: log.ok ? t.muted : t.bad, fontSize: 12, marginTop: 4 }} numberOfLines={3}>
      {new Date(log.at).toLocaleString()} · {log.message}
    </Text>
  );
}

export default function Settings() {
  const t = useTheme();
  const { data, error, loading, reload } = useAsync(() => Promise.all([api.integrations(), api.settings()]));
  const [gEmail, setGEmail] = useState("");
  const [gPass, setGPass] = useState("");
  const [mfa, setMfa] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    try {
      await fn();
      await reload();
    } catch (e) {
      Alert.alert("Lỗi", e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  if (loading && !data) return <Loading />;
  if (!data) return <ErrorBox message={error ?? "Lỗi"} onRetry={reload} />;
  const [s, cfg] = data;

  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 60 }} refreshControl={<RefreshControl refreshing={loading} onRefresh={reload} />}>
        <Card>
          <H2>{healthName}</H2>
          <P muted>Đọc buổi chạy, nhịp tim nghỉ, HRV và giấc ngủ ngay trên điện thoại.</P>
          <View style={{ marginTop: 8 }}>
            <Btn
              title="Đồng bộ ngay"
              loading={busy === "health"}
              onPress={() =>
                run("health", async () => {
                  const r = await syncHealth(60);
                  Alert.alert(healthName, `Đã gửi ${r.workouts} buổi chạy, ${r.daily} ngày dữ liệu sức khỏe`);
                })
              }
            />
          </View>
          <Text style={{ color: t.muted, fontSize: 12, marginTop: 4 }}>
            Lần cuối: {s.apple_health.last_sync ?? s.health_connect.last_sync ?? "chưa"}
          </Text>
        </Card>

        <Card>
          <H2>Strava {s.strava.connected ? "✅" : ""}</H2>
          {!s.strava.configured ? <P style={{ color: t.warn }}>Backend chưa có STRAVA_CLIENT_ID/SECRET.</P> : null}
          {s.strava.connected ? (
            <Row style={{ flexWrap: "wrap" }}>
              <Btn small title="Đồng bộ" loading={busy === "strava"} onPress={() => run("strava", () => api.syncAll())} />
              <Btn small kind="secondary" title="Bật webhook" onPress={() => run("hook", async () => Alert.alert("Webhook", JSON.stringify(await api.stravaSubscribe())))} />
              <Btn small kind="danger" title="Ngắt" onPress={() => run("strava", () => api.stravaDisconnect())} />
            </Row>
          ) : (
            <Btn
              title="Kết nối Strava"
              disabled={!s.strava.configured}
              onPress={() =>
                run("strava", async () => {
                  const { authorize_url } = await api.stravaConnect();
                  await WebBrowser.openBrowserAsync(authorize_url);
                })
              }
            />
          )}
          <LastSync log={s.strava.last} />
        </Card>

        <Card>
          <H2>Garmin Connect {s.garmin.connected ? "✅" : ""}</H2>
          <P muted>Nhập hoạt động, HRV, giấc ngủ và đẩy bài tập có cấu trúc lên lịch đồng hồ. Dùng API không chính thức — có thể bị lỗi khi Garmin thay đổi.</P>
          {s.garmin.connected ? (
            <Row style={{ marginTop: 8 }}>
              <Btn small title="Đồng bộ" loading={busy === "garmin"} onPress={() => run("garmin", () => api.syncAll())} />
              <Btn small kind="danger" title="Ngắt" onPress={() => run("garmin", () => api.garminDisconnect())} />
            </Row>
          ) : mfa !== null ? (
            <View style={{ marginTop: 8 }}>
              <Field label="Mã MFA" value={mfa} onChangeText={setMfa} keyboardType="number-pad" />
              <Btn title="Xác nhận" loading={busy === "garmin"} onPress={() => run("garmin", async () => { await api.garminMfa(mfa); setMfa(null); })} />
            </View>
          ) : (
            <View style={{ marginTop: 8 }}>
              <Field label="Email (để trống nếu đã đặt trong .env)" value={gEmail} onChangeText={setGEmail} autoCapitalize="none" keyboardType="email-address" />
              <Field label="Mật khẩu" value={gPass} onChangeText={setGPass} secureTextEntry />
              <Btn
                title="Đăng nhập Garmin"
                loading={busy === "garmin"}
                onPress={() =>
                  run("garmin", async () => {
                    const r = await api.garminLogin(gEmail || undefined, gPass || undefined);
                    if (r.status === "needs_mfa") setMfa("");
                    setGPass("");
                  })
                }
              />
            </View>
          )}
          <LastSync log={s.garmin.last} />
          <LastSync log={s.garmin.push} />
        </Card>

        <Card>
          <H2>COROS {s.coros.connected ? "✅" : ""}</H2>
          <P muted>Qua cổng "Build on COROS" (MCP + OAuth, 1 người dùng). Đọc hoạt động và ghi bài tập. Tính năng thử nghiệm.</P>
          {s.coros.connected ? (
            <>
              <Row style={{ marginTop: 8 }}>
                <Btn small title="Đồng bộ" loading={busy === "coros"} onPress={() => run("coros", () => api.syncAll())} />
                <Btn small kind="danger" title="Ngắt" onPress={() => run("coros", () => api.corosDisconnect())} />
              </Row>
              {s.coros.tools.length ? <Text style={{ color: t.muted, fontSize: 12, marginTop: 4 }}>Tools: {s.coros.tools.join(", ")}</Text> : null}
            </>
          ) : (
            <View style={{ marginTop: 8 }}>
              <Btn
                title="Kết nối COROS"
                loading={busy === "coros"}
                onPress={() =>
                  run("coros", async () => {
                    const r = await api.corosConnect();
                    if (r.authorize_url) await WebBrowser.openBrowserAsync(r.authorize_url);
                  })
                }
              />
            </View>
          )}
          <LastSync log={s.coros.last} />
          <LastSync log={s.coros.push} />
        </Card>

        <Card>
          <H2>Cài đặt</H2>
          <Row style={{ justifyContent: "space-between", marginBottom: 8 }}>
            <Text style={{ color: t.text }}>Điều chỉnh pace theo nóng ẩm</Text>
            <Switch value={cfg.heat_adjust} onValueChange={(v) => run("heat", () => api.putSettings({ heat_adjust: v }))} />
          </Row>
          <P muted>Giờ chạy thường ngày: {cfg.preferred_run_hour}h</P>
          <Row style={{ marginTop: 6, flexWrap: "wrap" }}>
            {[5, 6, 17, 18, 19].map((h) => (
              <Btn key={h} small kind={cfg.preferred_run_hour === h ? "primary" : "secondary"} title={`${h}h`} onPress={() => run("hour", () => api.putSettings({ preferred_run_hour: h }))} />
            ))}
          </Row>
          <P muted style={{ marginTop: 10, fontSize: 12 }}>Vị trí thời tiết: {cfg.latitude.toFixed(3)}, {cfg.longitude.toFixed(3)} · AI coach: {cfg.ai_coach ? "bật" : "tắt"}</P>
          <View style={{ marginTop: 10, gap: 8 }}>
            <Btn kind="secondary" title="📅 Thêm giáo án vào Lịch" onPress={() => Linking.openURL(cfg.calendar_url.replace(/^https?:/, "webcal:"))} />
            <Btn
              kind="danger"
              title="Đổi máy chủ"
              onPress={async () => {
                await clearServer();
                router.replace("/setup");
              }}
            />
          </View>
        </Card>
      </ScrollView>
    </Screen>
  );
}
