import type { ReactNode } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View, type TextInputProps, type ViewStyle } from "react-native";

import { useTheme } from "../lib/theme";

export function Screen({ children }: { children: ReactNode }) {
  const t = useTheme();
  return <View style={{ flex: 1, backgroundColor: t.bg }}>{children}</View>;
}

export function Card({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  const t = useTheme();
  return <View style={[styles.card, { backgroundColor: t.card, borderColor: t.border }, style]}>{children}</View>;
}

export function H1({ children }: { children: ReactNode }) {
  const t = useTheme();
  return <Text style={[styles.h1, { color: t.text }]}>{children}</Text>;
}

export function H2({ children }: { children: ReactNode }) {
  const t = useTheme();
  return <Text style={[styles.h2, { color: t.text }]}>{children}</Text>;
}

export function P({ children, muted, style }: { children: ReactNode; muted?: boolean; style?: object }) {
  const t = useTheme();
  return <Text style={[{ color: muted ? t.muted : t.text, fontSize: 15, lineHeight: 21 }, style]}>{children}</Text>;
}

export function Btn({
  title,
  onPress,
  kind = "primary",
  disabled,
  loading,
  small,
}: {
  title: string;
  onPress: () => void;
  kind?: "primary" | "secondary" | "danger";
  disabled?: boolean;
  loading?: boolean;
  small?: boolean;
}) {
  const t = useTheme();
  const bg = kind === "primary" ? t.primary : kind === "danger" ? t.bad : t.chip;
  const fg = kind === "secondary" ? t.text : t.primaryText;
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [styles.btn, small && styles.btnSmall, { backgroundColor: bg, opacity: disabled ? 0.5 : pressed ? 0.8 : 1 }]}
    >
      {loading ? <ActivityIndicator color={fg} /> : <Text style={{ color: fg, fontWeight: "600", fontSize: small ? 13 : 16 }}>{title}</Text>}
    </Pressable>
  );
}

export function Chip({ label, active, onPress, color }: { label: string; active?: boolean; onPress?: () => void; color?: string }) {
  const t = useTheme();
  return (
    <Pressable
      onPress={onPress}
      style={[styles.chip, { backgroundColor: active ? (color ?? t.primary) : t.chip, borderColor: active ? (color ?? t.primary) : t.border }]}
    >
      <Text style={{ color: active ? "#fff" : t.text, fontSize: 13, fontWeight: "500" }}>{label}</Text>
    </Pressable>
  );
}

export function Field({ label, ...props }: TextInputProps & { label: string }) {
  const t = useTheme();
  return (
    <View style={{ marginBottom: 12 }}>
      <Text style={{ color: t.muted, fontSize: 13, marginBottom: 4 }}>{label}</Text>
      <TextInput
        placeholderTextColor={t.muted}
        {...props}
        style={[styles.input, { color: t.text, borderColor: t.border, backgroundColor: t.card }, props.style]}
      />
    </View>
  );
}

export function Row({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  return <View style={[{ flexDirection: "row", alignItems: "center", gap: 8 }, style]}>{children}</View>;
}

export function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  const t = useTheme();
  return (
    <View style={{ flex: 1 }}>
      <Text style={{ color: t.muted, fontSize: 12 }}>{label}</Text>
      <Text style={{ color: t.text, fontSize: 20, fontWeight: "700" }}>{value}</Text>
      {sub ? <Text style={{ color: t.muted, fontSize: 12 }}>{sub}</Text> : null}
    </View>
  );
}

export function Loading() {
  const t = useTheme();
  return (
    <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: t.bg }}>
      <ActivityIndicator color={t.primary} />
    </View>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const t = useTheme();
  return (
    <Card style={{ borderColor: t.bad }}>
      <P style={{ color: t.bad }}>{message}</P>
      {onRetry ? (
        <View style={{ marginTop: 8 }}>
          <Btn small kind="secondary" title="Thử lại" onPress={onRetry} />
        </View>
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: 14, padding: 16, borderWidth: StyleSheet.hairlineWidth, marginBottom: 12 },
  h1: { fontSize: 26, fontWeight: "800", marginBottom: 4 },
  h2: { fontSize: 18, fontWeight: "700", marginBottom: 8 },
  btn: { borderRadius: 12, paddingVertical: 14, paddingHorizontal: 16, alignItems: "center", justifyContent: "center" },
  btnSmall: { paddingVertical: 8, paddingHorizontal: 12, borderRadius: 10 },
  chip: { paddingVertical: 6, paddingHorizontal: 12, borderRadius: 999, borderWidth: StyleSheet.hairlineWidth },
  input: { borderWidth: StyleSheet.hairlineWidth, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 16 },
});
