import { router } from "expo-router";
import { useState } from "react";
import { ScrollView } from "react-native";

import { Btn, Card, Field, H1, P, Screen } from "../components/ui";
import { api, saveServer } from "../lib/api";

export default function Setup() {
  const [url, setUrl] = useState("http://192.168.1.10:8000");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const srv = { url: url.trim().replace(/\/+$/, ""), token: token.trim() };
      await api.ping(srv);
      await saveServer(srv.url, srv.token);
      try {
        await api.plan();
        router.replace("/");
      } catch {
        router.replace("/onboarding");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: 16 }}>
        <H1>Runners</H1>
        <P muted>App giáo án chạy bộ cá nhân. Nhập địa chỉ backend bạn tự chạy (Docker) và APP_TOKEN trong file .env.</P>
        <Card style={{ marginTop: 16 }}>
          <Field label="Địa chỉ máy chủ" value={url} onChangeText={setUrl} autoCapitalize="none" autoCorrect={false} keyboardType="url" />
          <Field label="APP_TOKEN" value={token} onChangeText={setToken} autoCapitalize="none" autoCorrect={false} secureTextEntry />
          {error ? <P style={{ color: "#DC2626", marginBottom: 8 }}>{error}</P> : null}
          <Btn title="Kết nối" onPress={save} loading={busy} disabled={!url || !token} />
        </Card>
      </ScrollView>
    </Screen>
  );
}
