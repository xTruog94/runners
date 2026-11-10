import { router } from "expo-router";
import { useState } from "react";
import { Alert, ScrollView } from "react-native";

import { Btn, Card, Chip, H2, P, Row, Screen } from "../components/ui";
import { api } from "../lib/api";

const REASONS = [
  { key: "sick", label: "🤒 Ốm / sốt", hint: "Nghỉ hẳn, sau đó vài ngày chỉ chạy nhẹ." },
  { key: "niggle", label: "🦵 Đau nhẹ", hint: "Chỉ chạy hồi phục ngắn. Đau tăng khi chạy → dừng và đi khám." },
  { key: "tired", label: "😮‍💨 Mệt mỏi", hint: "Bỏ bài nặng, chạy nhẹ để hồi phục." },
  { key: "busy", label: "⏱ Bận rộn", hint: "Rút ngắn các buổi, giữ phần chính của bài quan trọng." },
] as const;

export default function NotFeeling() {
  const [reason, setReason] = useState<(typeof REASONS)[number]["key"]>("tired");
  const [days, setDays] = useState(3);
  const [busy, setBusy] = useState(false);
  const r = REASONS.find((x) => x.key === reason)!;

  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: 16 }}>
        <Card>
          <H2>Bạn đang thế nào?</H2>
          <Row style={{ flexWrap: "wrap" }}>
            {REASONS.map((x) => (
              <Chip key={x.key} label={x.label} active={reason === x.key} onPress={() => setReason(x.key)} />
            ))}
          </Row>
          <P muted style={{ marginTop: 10 }}>{r.hint}</P>
        </Card>
        <Card>
          <H2>Trong bao lâu?</H2>
          <Row style={{ flexWrap: "wrap" }}>
            {[1, 2, 3, 5, 7, 10].map((d) => (
              <Chip key={d} label={`${d} ngày`} active={days === d} onPress={() => setDays(d)} />
            ))}
          </Row>
        </Card>
        <Btn
          title="Điều chỉnh giáo án"
          loading={busy}
          onPress={async () => {
            setBusy(true);
            try {
              const res = await api.notFeeling100(reason, days);
              Alert.alert("Đã điều chỉnh", res.reason);
              router.back();
            } catch (e) {
              Alert.alert("Lỗi", e instanceof Error ? e.message : String(e));
            } finally {
              setBusy(false);
            }
          }}
        />
      </ScrollView>
    </Screen>
  );
}
