import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, Text, TextInput, View } from "react-native";

import { Btn, Card, P, Screen } from "../components/ui";
import { api } from "../lib/api";
import { useTheme } from "../lib/theme";
import { useAsync } from "../lib/useAsync";

type Msg = { role: "user" | "assistant"; content: string };

const SUGGESTIONS = ["Vì sao tuần này giảm km?", "Buổi interval hôm qua của mình thế nào?", "Mình có kịp mục tiêu không?", "Nên ăn gì trước long run?"];

export default function Coach() {
  const t = useTheme();
  const weekly = useAsync(() => api.weekly());
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = async (text: string) => {
    if (!text.trim()) return;
    const next: Msg[] = [...msgs, { role: "user", content: text.trim() }];
    setMsgs(next);
    setInput("");
    setBusy(true);
    setError(null);
    try {
      const { reply } = await api.chat(next);
      setMsgs([...next, { role: "assistant", content: reply }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined} keyboardVerticalOffset={90}>
        <ScrollView contentContainerStyle={{ padding: 16 }}>
          {weekly.data ? (
            <Card>
              <P>{weekly.data.text}</P>
            </Card>
          ) : null}
          {msgs.map((m, i) => (
            <View key={i} style={{ alignSelf: m.role === "user" ? "flex-end" : "flex-start", maxWidth: "85%", backgroundColor: m.role === "user" ? t.primary : t.card, borderRadius: 14, padding: 12, marginBottom: 8 }}>
              <Text style={{ color: m.role === "user" ? "#fff" : t.text, fontSize: 15, lineHeight: 21 }}>{m.content}</Text>
            </View>
          ))}
          {!msgs.length ? (
            <View style={{ gap: 8 }}>
              {SUGGESTIONS.map((s) => (
                <Btn key={s} kind="secondary" small title={s} onPress={() => send(s)} />
              ))}
            </View>
          ) : null}
          {error ? <P style={{ color: t.bad, marginTop: 8 }}>{error}</P> : null}
        </ScrollView>
        <View style={{ flexDirection: "row", padding: 12, gap: 8, borderTopWidth: 1, borderTopColor: t.border, backgroundColor: t.card }}>
          <TextInput
            value={input}
            onChangeText={setInput}
            placeholder="Hỏi coach…"
            placeholderTextColor={t.muted}
            style={{ flex: 1, color: t.text, borderWidth: 1, borderColor: t.border, borderRadius: 10, paddingHorizontal: 12 }}
            onSubmitEditing={() => send(input)}
          />
          <Btn small title="Gửi" onPress={() => send(input)} loading={busy} />
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}
