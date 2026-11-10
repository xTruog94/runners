"""Coach: rule-based weekly summary (always available) and an optional
Claude-powered chat that explains the plan using the runner's real data."""

from __future__ import annotations

import datetime as dt
import json

from sqlmodel import select

from ..config import get_settings
from ..db import ActivityRow, WorkoutRow, session
from ..engine.generator import monday
from ..engine.zones import fmt_pace, pace_zones
from . import metrics
from . import plans as plan_svc

SYSTEM_PROMPT = """Bạn là huấn luyện viên chạy bộ cá nhân, trả lời bằng tiếng Việt, ngắn gọn và thực tế.
Bạn được cung cấp dữ liệu JSON về giáo án, các buổi tập gần đây và chỉ số thể lực của runner.
Dựa vào dữ liệu đó để giải thích vì sao giáo án như vậy, đánh giá buổi tập và đưa lời khuyên.
Giáo án do một engine theo quy tắc khoa học tạo ra; bạn không tự ý thay đổi khối lượng hay pace,
chỉ gợi ý runner dùng các chức năng trong app (dời buổi, "Không khỏe 100%", chấp nhận đề xuất pace).
Nếu runner mô tả đau nhói, đau tăng dần, đau ngực, chóng mặt hay khó thở: khuyên dừng tập và gặp bác sĩ."""


def context(today: dt.date) -> dict:
    plan = plan_svc.active_plan()
    wk = monday(today)
    data: dict = {"today": today.isoformat()}
    if plan:
        zones = pace_zones(plan.current_vdot)
        data["goal"] = plan.goal
        data["vdot"] = {"start": plan.start_vdot, "current": plan.current_vdot, "goal": plan.goal_vdot}
        data["zones"] = {k: f"{fmt_pace(z.fast_s_per_km)}–{fmt_pace(z.slow_s_per_km)}" for k, z in zones.items()}
        with session() as s:
            rows = s.exec(
                select(WorkoutRow).where(WorkoutRow.plan_id == plan.id, WorkoutRow.date >= wk - dt.timedelta(days=7), WorkoutRow.date < wk + dt.timedelta(days=14)).order_by(WorkoutRow.date)
            ).all()
        data["workouts"] = [
            {"date": r.date.isoformat(), "type": r.type, "title": r.title, "km": r.distance_km, "status": r.status, "rpe": r.rpe, "analysis": (r.analysis or {}).get("summary")}
            for r in rows
        ]
    with session() as s:
        acts = s.exec(select(ActivityRow).where(ActivityRow.local_date >= today - dt.timedelta(days=14), ActivityRow.duplicate_of == None).order_by(ActivityRow.start_time)).all()  # noqa: E711
    data["activities"] = [
        {"date": a.local_date.isoformat(), "km": round(a.distance_m / 1000, 2), "pace": fmt_pace(a.duration_s / max(0.1, a.distance_m / 1000)), "avg_hr": a.avg_hr, "source": a.source}
        for a in acts
        if a.sport == "run"
    ]
    snap = metrics.snapshot(today)
    data["load"] = {k: snap[k] for k in ("ctl", "atl", "tsb", "acwr", "readiness")}
    data["fitness"] = metrics.fitness(today)
    return data


def weekly_summary(today: dt.date) -> dict:
    plan = plan_svc.active_plan()
    if not plan:
        return {"text": "Chưa có giáo án."}
    wk = monday(today) - dt.timedelta(days=7) if today.weekday() < 6 else monday(today)
    with session() as s:
        rows = s.exec(select(WorkoutRow).where(WorkoutRow.plan_id == plan.id, WorkoutRow.date >= wk, WorkoutRow.date < wk + dt.timedelta(days=7))).all()
    runs = [r for r in rows if r.type not in ("strength", "rest")]
    done = [r for r in runs if r.status in ("completed", "partial")]
    planned_km = sum(r.distance_km for r in runs)
    vols = {v["week_start"]: v["actual_km"] for v in metrics.weekly_volumes(today, 3)}
    actual_km = vols.get(wk.isoformat(), 0.0)
    key_done = [r for r in done if r.key]
    lines = [f"Tuần {wk.strftime('%d/%m')}: hoàn thành {len(done)}/{len(runs)} buổi, {actual_km:.1f}/{planned_km:.1f} km."]
    fast = sum(1 for r in done if (r.analysis or {}).get("pace_vs_target") == "fast" and r.type in ("easy", "recovery"))
    if fast >= 2:
        lines.append(f"{fast} buổi chạy nhẹ bị nhanh hơn vùng easy — hãy chạy chậm lại để hồi phục tốt hơn.")
    if key_done:
        lines.append("Bài quan trọng: " + "; ".join(f"{r.title} ({(r.analysis or {}).get('score', '?')} điểm)" for r in key_done))
    missed = [r for r in runs if r.status in ("missed", "skipped")]
    if missed:
        lines.append(f"Bỏ lỡ {len(missed)} buổi. Không sao — giáo án đã tự điều chỉnh.")
    snap = metrics.snapshot(today)
    lines.append(f"Thể lực (CTL) {snap['ctl']:.0f}, mệt mỏi (ATL) {snap['atl']:.0f}, sẵn sàng {snap['readiness']['score']}/100.")
    return {"week_start": wk.isoformat(), "text": " ".join(lines)}


async def chat(messages: list[dict], today: dt.date) -> str:
    cfg = get_settings()
    if not cfg.anthropic_api_key:
        raise RuntimeError("Chưa cấu hình ANTHROPIC_API_KEY — AI coach đang tắt.")
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key)
    ctx = json.dumps(context(today), ensure_ascii=False, default=str)
    system = [
        {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": f"Dữ liệu runner (JSON):\n{ctx}"},
    ]
    msgs = [{"role": m["role"], "content": m["content"]} for m in messages if m.get("role") in ("user", "assistant") and m.get("content")]
    try:
        resp = await client.beta.messages.create(
            model=cfg.coach_model,
            max_tokens=4000,
            system=system,
            messages=msgs,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.RateLimitError as e:
        raise RuntimeError("AI coach đang quá tải, thử lại sau.") from e
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Lỗi Claude API ({e.status_code}).") from e
    except anthropic.APIConnectionError as e:
        raise RuntimeError("Không kết nối được Claude API.") from e
    if resp.stop_reason == "refusal":
        return "Xin lỗi, mình không thể trả lời câu hỏi này."
    return "".join(b.text for b in resp.content if b.type == "text").strip()
