import { Tabs } from "expo-router/js-tabs";
import { Text, type ColorValue } from "react-native";

import { useTheme } from "../../lib/theme";

const icon = (glyph: string) =>
  function TabIcon({ color }: { color: ColorValue }) {
    return <Text style={{ fontSize: 20, color }}>{glyph}</Text>;
  };

export default function TabsLayout() {
  const t = useTheme();
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: t.primary,
        tabBarInactiveTintColor: t.muted,
        tabBarStyle: { backgroundColor: t.card, borderTopColor: t.border },
        headerStyle: { backgroundColor: t.card },
        headerTintColor: t.text,
      }}
    >
      <Tabs.Screen name="index" options={{ title: "Hôm nay", tabBarIcon: icon("◉") }} />
      <Tabs.Screen name="plan" options={{ title: "Giáo án", tabBarIcon: icon("▦") }} />
      <Tabs.Screen name="run" options={{ title: "Chạy", tabBarIcon: icon("▶") }} />
      <Tabs.Screen name="stats" options={{ title: "Thống kê", tabBarIcon: icon("▲") }} />
      <Tabs.Screen name="settings" options={{ title: "Kết nối", tabBarIcon: icon("⚙") }} />
    </Tabs>
  );
}
