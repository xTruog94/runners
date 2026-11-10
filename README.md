# Runners — app giáo án chạy bộ cá nhân

App tự tạo và tự điều chỉnh giáo án chạy bộ (lấy cảm hứng từ Miles, Runna, Garmin Coach), dùng cho cá nhân.
Kết nối **Strava**, **Apple Health / Health Connect**, **Garmin** và **COROS**.

- Research & lý do chọn tính năng: [`docs/research.md`](docs/research.md)
- Backend: `backend/` (Python FastAPI + SQLite, tự host bằng Docker)
- App: `mobile/` (Expo / React Native, iOS + Android)

```
┌───────────── iPhone / Android ─────────────┐        ┌──────────── backend (Docker) ────────────┐
│ Expo app                                   │  HTTPS │ FastAPI                                  │
│  • Hôm nay / Giáo án / Chạy / Thống kê     │ ─────▶ │  engine/  giáo án, thích ứng, tải tập    │
│  • HealthKit / Health Connect → /health    │        │  services/ ghép trùng, phân tích, thời   │
│  • Chạy theo hướng dẫn (GPS + giọng nói)   │        │            tiết, lịch .ics, AI coach     │
└────────────────────────────────────────────┘        │  integrations/ Strava · Garmin · COROS   │
                                                      │  SQLite (./data)                         │
         Strava webhook / OAuth, COROS OAuth  ──────▶ │  đồng bộ nền mỗi 30 phút                 │
                                                      └──────────────────────────────────────────┘
```

## Tính năng

**Giáo án**
- Mục tiêu 5K / 10K / Half / Marathon (có ngày thi, thời gian mục tiêu) hoặc "chạy đều" 12 tuần.
- Tính VDOT từ thành tích gần nhất (hoặc pace chạy nhẹ). Vùng pace: hồi phục, E, M, HM, T, I, R.
- Chia pha base → build → peak → taper. Km/tuần tăng ≤ 10%, tuần hồi phục mỗi 4 tuần, long run có giới hạn theo cự ly. Tối đa 2 bài nặng mỗi tuần, không bao giờ 2 ngày liền nhau. Giới hạn khối lượng T/I/R theo Daniels.
- Thư viện bài: tempo, cruise intervals, VO2max, tốc độ, fartlek, dốc, progression, pace thi đấu, long run có đoạn cuối ở pace mục tiêu, strides, shakeout. Có thêm 2 buổi sức mạnh mỗi tuần.
- Mục tiêu quá tham vọng thì app cảnh báo; VDOT tăng dần theo tuần.

**Tự điều chỉnh**
- Bỏ lỡ bài quan trọng → dời sang ngày trống phù hợp. Bỏ lỡ bài nhẹ → bỏ qua.
- Nghỉ ≥ 7 ngày → đề xuất tính lại giáo án với khối lượng 50–80%.
- **Pace Insights**: liên tục nhanh hơn mục tiêu mà vẫn nhẹ (hoặc chậm hơn và rất nặng) → đề xuất ±1 VDOT.
- **Không khỏe 100%**: ốm / đau nhẹ / mệt / bận.
- Readiness thấp hoặc ACWR > 1.5 → đề xuất giảm tải.
- **Nóng ẩm**: pace tự chậm lại theo nhiệt độ và độ ẩm (Open-Meteo), kèm gợi ý giờ mát nhất trong ngày.

**Dữ liệu & phân tích**
- Nhập từ Strava (webhook realtime), Garmin, COROS, Apple Health / Health Connect. Một buổi chạy đến từ nhiều nguồn được tự gộp.
- Tự khớp buổi chạy với bài trong giáo án. Phân tích: % hoàn thành, pace so với mục tiêu, pace từng rep, trôi nhịp tim, điểm 0–100, lời khuyên.
- Tải tập (rTSS / TRIMP), CTL / ATL / TSB, ACWR, readiness (form + nhịp tim nghỉ + HRV + giấc ngủ + RPE).
- Dự đoán thành tích 5K → marathon. Biểu đồ km/tuần (thực tế so với kế hoạch).

**Trên tay & trên cổ tay**
- **Chạy với hướng dẫn**: GPS điện thoại, đọc từng bước bằng tiếng Việt, nhắc "chậm lại / nhanh lên", báo mỗi km. Lưu buổi chạy kèm RPE.
- **Đẩy bài lên đồng hồ**: Garmin (bài có cấu trúc + pace, lên lịch Garmin Connect) và COROS. Tự đồng bộ 7 ngày tới.
- Feed **lịch .ics** để giáo án hiện trong app Lịch.
- **AI coach** (tùy chọn, cần `ANTHROPIC_API_KEY`): hỏi đáp dựa trên dữ liệu thật. Có thêm tóm tắt tuần theo quy tắc (không cần AI).

## Cài đặt

### 1. Backend

```bash
cp backend/.env.example backend/.env     # sửa APP_TOKEN, PUBLIC_URL, ...
docker compose up -d --build             # http://localhost:8000/health
```

Chạy không cần Docker:

```bash
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]" && pytest        # 44 test
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`PUBLIC_URL` phải truy cập được từ Internet để Strava/COROS redirect về và để Strava gửi webhook. Có thể dùng Cloudflare Tunnel, Tailscale Funnel hoặc ngrok trỏ tới cổng 8000.

### 2. Strava
1. Tạo app tại <https://www.strava.com/settings/api>. Đặt *Authorization Callback Domain* = domain của `PUBLIC_URL`.
2. Điền `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET` vào `.env`.
3. Trong app: tab **Kết nối → Kết nối Strava**, rồi bấm **Bật webhook** để nhận hoạt động ngay khi upload.
4. Lưu ý: từ 06/2026 Strava yêu cầu người phát triển app Standard tier có gói Strava trả phí.

### 3. Apple Health / Health Connect
Không cần cấu hình backend. App xin quyền đọc trên điện thoại, rồi đồng bộ khi kéo để làm mới ở tab **Hôm nay** hoặc khi bấm **Đồng bộ ngay**.

### 4. Garmin (không chính thức)
Đăng nhập trong tab **Kết nối** (có hỗ trợ MFA), hoặc đặt `GARMIN_EMAIL` / `GARMIN_PASSWORD` trong `.env`. Token được lưu ở `data/garmin_tokens`.
Thư viện `garminconnect` dùng endpoint riêng của Garmin Connect web, nên có thể hỏng khi Garmin thay đổi. Mọi lỗi đều được ghi vào nhật ký đồng bộ, không làm hỏng app.

### 5. COROS (thử nghiệm)
Bấm **Kết nối COROS**. Backend tự dò máy chủ OAuth của `COROS_MCP_URL`, đăng ký client, rồi mở trang đăng nhập COROS.
Tên tool trên server COROS được dò tự động. Nếu dò sai: xem `GET /api/integrations/coros/tools`, rồi đặt `COROS_TOOL_LIST_ACTIVITIES` / `COROS_TOOL_CREATE_WORKOUT` trong `.env`.

### 6. App mobile
App dùng native module (HealthKit, Health Connect) nên **không chạy được trong Expo Go**. Cần build bản dev hoặc bản cá nhân:

```bash
cd mobile && npm install
npx eas-cli@latest build --profile development --platform ios        # hoặc android
# Android APK dùng riêng:    npx eas-cli@latest build --profile personal --platform android
# Có Xcode/Android Studio:   npx expo run:ios  /  npx expo run:android
npx expo start --dev-client
```

Mở app → nhập địa chỉ backend + `APP_TOKEN` → tạo giáo án.
iOS: cài lên iPhone của bạn cần tài khoản Apple Developer (HealthKit là capability cần ký app).

## API chính

| Method | Path | Mô tả |
|---|---|---|
| POST | `/api/plan` · `/api/plan/preview` | Tạo / xem trước giáo án |
| GET | `/api/plan` · `/api/today` | Giáo án đầy đủ / hôm nay (pace đã chỉnh theo nóng ẩm, readiness, đề xuất) |
| PATCH | `/api/workouts/{id}` | Dời ngày, RPE, ghi chú, trạng thái |
| POST | `/api/workouts/{id}/push` | Đẩy bài lên Garmin/COROS |
| GET/POST | `/api/adjustments` · `/{id}/apply` · `/{id}/dismiss` | Đề xuất điều chỉnh |
| POST | `/api/not-feeling-100` | Ốm / đau / mệt / bận |
| POST | `/api/health/batch` | App gửi dữ liệu HealthKit / Health Connect |
| GET | `/api/stats` · `/api/coach/weekly` · POST `/api/coach/chat` | Thống kê, tóm tắt tuần, AI coach |
| POST | `/api/integrations/sync` | Đồng bộ tất cả nguồn + chạy bước tự điều chỉnh |
| GET | `/calendar.ics?token=…` | Feed lịch |

Mọi endpoint `/api/*` cần header `Authorization: Bearer <APP_TOKEN>`, trừ OAuth callback và Strava webhook.

## Giới hạn hiện tại
- Chưa kiểm thử với tài khoản Strava / Garmin / COROS thật. Phần COROS dựa trên tài liệu "Build on COROS MCP", tên tool phải dò khi chạy.
- Chạy bằng GPS điện thoại hoạt động ở foreground (giữ màn hình sáng). Chưa ghi vị trí khi app chạy nền và chưa lưu ngược vào Apple Health.
- Giáo án tạo theo quy tắc, không thay thế huấn luyện viên hay bác sĩ. Đau tăng dần, đau ngực, chóng mặt → dừng tập.
