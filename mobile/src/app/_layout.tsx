import { Stack, router, useSegments } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";

import { Loading } from "../components/ui";
import { getServer } from "../lib/api";
import { useTheme } from "../lib/theme";

export default function RootLayout() {
  const t = useTheme();
  const segments = useSegments();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    getServer().then((srv) => {
      setReady(true);
      if (!srv && segments[0] !== "setup") router.replace("/setup");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!ready) return <Loading />;
  return (
    <>
      <StatusBar style="auto" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: t.card },
          headerTintColor: t.text,
          contentStyle: { backgroundColor: t.bg },
          headerBackTitle: "Quay lại",
        }}
      >
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="setup" options={{ title: "Kết nối máy chủ" }} />
        <Stack.Screen name="onboarding" options={{ title: "Tạo giáo án" }} />
        <Stack.Screen name="workout/[id]" options={{ title: "Buổi tập" }} />
        <Stack.Screen name="coach" options={{ title: "Coach" }} />
        <Stack.Screen name="not-feeling" options={{ title: "Không khỏe 100%", presentation: "modal" }} />
      </Stack>
    </>
  );
}
