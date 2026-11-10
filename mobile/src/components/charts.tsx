import { Text, View } from "react-native";
import Svg, { Circle, G, Line, Polyline, Rect } from "react-native-svg";

import { useTheme } from "../lib/theme";

export function ReadinessRing({ score, size = 88 }: { score: number; size?: number }) {
  const t = useTheme();
  const stroke = 9;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const color = score >= 70 ? t.good : score >= 50 ? t.warn : t.bad;
  return (
    <View style={{ width: size, height: size, alignItems: "center", justifyContent: "center" }}>
      <Svg width={size} height={size} style={{ position: "absolute" }}>
        <Circle cx={size / 2} cy={size / 2} r={r} stroke={t.chip} strokeWidth={stroke} fill="none" />
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={color}
          strokeWidth={stroke}
          fill="none"
          strokeDasharray={`${(c * score) / 100} ${c}`}
          strokeLinecap="round"
          rotation={-90}
          originX={size / 2}
          originY={size / 2}
        />
      </Svg>
      <Text style={{ color: t.text, fontSize: 24, fontWeight: "800" }}>{score}</Text>
    </View>
  );
}

/** Weekly volume: actual (solid) vs planned (outline). */
export function VolumeBars({ data, height = 140 }: { data: { label: string; actual: number; planned: number | null }[]; height?: number }) {
  const t = useTheme();
  const max = Math.max(10, ...data.map((d) => Math.max(d.actual, d.planned ?? 0)));
  const barW = 18;
  const gap = 8;
  const width = data.length * (barW + gap);
  return (
    <View>
      <Svg width={width} height={height}>
        {data.map((d, i) => {
          const x = i * (barW + gap);
          const ph = ((d.planned ?? 0) / max) * (height - 4);
          const ah = (d.actual / max) * (height - 4);
          return (
            <G key={i}>
              {d.planned ? <Rect x={x} y={height - ph} width={barW} height={ph} fill="none" stroke={t.muted} strokeDasharray="3 3" rx={4} /> : null}
              <Rect x={x + 3} y={height - ah} width={barW - 6} height={ah} fill={t.primary} rx={3} />
            </G>
          );
        })}
      </Svg>
      <View style={{ flexDirection: "row", width }}>
        {data.map((d, i) => (
          <Text key={i} style={{ width: barW + gap, color: t.muted, fontSize: 9 }}>
            {d.label}
          </Text>
        ))}
      </View>
    </View>
  );
}

/** Fitness (CTL), fatigue (ATL) lines. */
export function LoadChart({ series, width = 320, height = 140 }: { series: { ctl: number; atl: number }[]; width?: number; height?: number }) {
  const t = useTheme();
  if (series.length < 2) return <Text style={{ color: t.muted }}>Chưa đủ dữ liệu</Text>;
  const max = Math.max(10, ...series.map((p) => Math.max(p.ctl, p.atl)));
  const pts = (key: "ctl" | "atl") =>
    series.map((p, i) => `${(i / (series.length - 1)) * width},${height - (p[key] / max) * (height - 6) - 3}`).join(" ");
  return (
    <Svg width={width} height={height}>
      <Line x1={0} y1={height - 1} x2={width} y2={height - 1} stroke={t.border} />
      <Polyline points={pts("atl")} fill="none" stroke="#EC4899" strokeWidth={1.5} />
      <Polyline points={pts("ctl")} fill="none" stroke="#3B82F6" strokeWidth={2.5} />
    </Svg>
  );
}
