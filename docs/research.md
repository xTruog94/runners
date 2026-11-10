# Research: các app giáo án chạy bộ tương tự & khả năng kết nối

Tài liệu tổng hợp (11/2026) để chọn tính năng cho app cá nhân. Thông tin từ store listing, bài review và tài liệu nhà phát triển — một số nguồn do đối thủ viết nên cần kiểm chứng lại.

## 1. Các app tham khảo

| App | Điểm chính | Ghi chú |
|---|---|---|
| **Miles: AI Running Coach** (iOS) | Giáo án tạo từ thể lực hiện tại, **hướng dẫn pace bằng giọng nói theo thời gian thực**, phân tích sau buổi chạy, theo dõi readiness & training load, Apple Health, cảm biến nhịp tim Bluetooth. Tự điều chỉnh khi bỏ buổi / cần hồi phục. | Pro ~$14.99/tháng hoặc $99.99/năm |
| **Runna** (Strava mua 2025) | Giáo án 5K → ultra; pace mục tiêu từ thời gian dự kiến; **Pace Insights** đề xuất đổi pace khi liên tục nhanh/chậm hơn mục tiêu (người dùng chấp nhận); **"Not feeling 100%"** khi ốm/đau/bận; **Adapt for Heat** theo nhiệt độ cảm nhận; khởi động/thả lỏng, sức mạnh, mobility; dự đoán thành tích; đẩy bài lên Garmin/COROS/Apple Watch… | ~$120/năm |
| **Garmin Coach** | Miễn phí, giáo án dựng sẵn 5K–marathon, tự đẩy lên đồng hồ, thích ứng theo dữ liệu đồng hồ | Chỉ đồng hồ Garmin, ít tùy biến |
| **Final Surge / TrainingPeaks** | Biểu đồ training load (CTL/ATL), km tuần/tháng, xu hướng pace & nhịp tim | Thiên về HLV & phân tích |
| **TrainAsONE, Coopah…** | AI/HLV người; ít nguồn tin cậy | — |

### Tính năng đã đưa vào app này

| Tính năng (lấy cảm hứng từ) | Trong app |
|---|---|
| Giáo án theo mục tiêu, ngày thi, số buổi/tuần, ngày chạy dài (tất cả) | `engine/generator.py`: VDOT, chia pha base/build/peak/taper, tăng ≤10%/tuần, tuần hồi phục mỗi 4 tuần, 80/20, giới hạn long run |
| Pace mục tiêu theo thể lực (Runna, Miles) | Vùng pace Daniels (E/M/HM/T/I/R) từ thành tích gần nhất hoặc pace chạy nhẹ |
| Mục tiêu tham vọng → cảnh báo (Runna) | VDOT tăng tối đa ~1 điểm/4 tuần, gợi ý thời gian thực tế hơn |
| Pace Insights (Runna) | `adapt.pace_insight`: 3/4 bài chất lượng nhanh hơn mà RPE ≤ 7 → đề xuất +1 VDOT, ngược lại −1 (người dùng xác nhận) |
| Not feeling 100% (Runna) | Ốm / đau nhẹ / mệt / bận → sửa các ngày tới |
| Tự điều chỉnh khi bỏ buổi (Miles, Runna) | Bài quan trọng dời sang ngày trống phù hợp, bài nhẹ bỏ qua; nghỉ ≥ 7 ngày → tính lại giáo án với khối lượng thấp hơn |
| Adapt for Heat (Runna) | Thời tiết Open-Meteo + bảng "nhiệt độ + điểm sương" → làm chậm pace, gợi ý giờ mát nhất (rất cần ở VN) |
| Readiness & training load (Miles, Final Surge) | CTL/ATL/TSB, ACWR, readiness từ form + nhịp tim nghỉ + HRV + giấc ngủ + RPE |
| Phân tích sau buổi chạy (Miles) | Độ hoàn thành, pace so với mục tiêu, pace từng rep (từ laps), trôi nhịp tim, điểm 0–100, lời khuyên |
| Hướng dẫn giọng nói khi chạy (Miles) | Tab **Chạy**: GPS điện thoại, đọc từng bước, nhắc nhanh/chậm, báo mỗi km (tiếng Việt) |
| Đẩy bài lên đồng hồ (Runna, Garmin Coach) | Garmin Connect calendar (bài có cấu trúc + pace) và COROS (thử nghiệm) |
| Sức mạnh, strides, khởi động (Runna) | 2 buổi sức mạnh/tuần (1 ở peak, 0 ở taper), strides sau chạy nhẹ |
| Dự đoán thành tích (Runna) | Từ VDOT giáo án + ước tính VDOT từ nhịp tim các buổi chạy đều |
| AI coach (Miles) | Tuỳ chọn: chat với Claude dựa trên dữ liệu thật; engine quy tắc vẫn quyết định khối lượng/pace |
| Lịch | Feed iCalendar để giáo án hiện trong app Lịch |

## 2. Khả năng kết nối cho app cá nhân

| Nguồn | Cách kết nối | Đọc | Ghi bài tập | Rủi ro |
|---|---|---|---|---|
| **Strava** | API chính thức, OAuth, webhook | Hoạt động, laps, HR | (ghi mô tả hoạt động – tùy chọn) | Từ 01/06/2026 (06/30 với dev cũ) app Standard tier yêu cầu **người phát triển có gói Strava trả phí**; giới hạn 400 req/15 phút, 4.000/ngày; webhook không ký nên backend lọc theo `owner_id` |
| **Apple Health** | HealthKit trên iPhone (`@kingstinct/react-native-healthkit`) | Workout chạy, HR, HR nghỉ, HRV, giấc ngủ | — | Cần build native (không chạy trong Expo Go) |
| **Health Connect** (Android) | `react-native-health-connect` | ExerciseSession, quãng đường, HR, HR nghỉ, HRV, giấc ngủ | — | minSdk 26, cần cài Health Connect |
| **Garmin** | Thư viện cộng đồng `garminconnect` (endpoint riêng của Garmin Connect web) | Hoạt động + splits, HR nghỉ, HRV, giấc ngủ | **Có**: upload workout + lên lịch | API chính thức chỉ cho đối tác doanh nghiệp. Đăng nhập không chính thức đã từng hỏng (3/2026); `garth` đã ngừng duy trì; dùng `garminconnect >= 0.3.5` (vá CVE-2026-54447 về file token) |
| **COROS** | "Build on COROS" MCP (`https://mcp.coros.com/mcp`), OAuth 2.0 tự phục vụ, **1 người dùng**, không cần xin duyệt | Dữ liệu tập luyện | **Có** (theo tài liệu COROS: ghi workout plan) | Mới ra mắt (5/2026), tên tool phải dò khi chạy; Partner API (nhiều user) cần đơn xin. API Training Hub không chính thức dễ hỏng |

Dữ liệu từ Garmin/COROS thường cũng chảy sang Strava và Apple Health/Health Connect, nên backend **gộp trùng** (cùng giờ bắt đầu ± 5 phút, quãng đường lệch < 10%) và ưu tiên nguồn có laps tốt nhất: Garmin > COROS > Strava > Apple Health > Health Connect > điện thoại > nhập tay.

## Nguồn

- Miles: [App Store](https://apps.apple.com/app/id6763786354), [iTechGuides](https://www.itechguides.com/products/miles/), [Marlvel](https://marlvel.ai/apps/miles-ai-running-coach)
- Runna: [Tom's Guide](https://www.tomsguide.com/reviews/runna-app), [the5krunner – Is Runna AI?](https://the5krunner.com/2026/09/28/is-runna-ai/), [the5krunner – Runna](https://the5krunner.com/runna/), [TechRadar](https://www.techradar.com/health-fitness/fitness-apps/runna-review), [Runna support](https://support.runna.com/en/collections/3431949-app-features-subscriptions-faqs)
- So sánh: [RunnersPicks – Garmin Coach vs TrainingPeaks vs Runna](https://www.runnerspicks.com/blog/garmin-coach-vs-trainingpeaks-vs-runna/), [RunnersPicks – TrainingPeaks vs Garmin Coach vs Final Surge](https://www.runnerspicks.com/blog/trainingpeaks-vs-garmin-coach-vs-final-surge/)
- Strava: [Rate limits](https://developers.strava.com/docs/rate-limits/), [API policy](https://www.strava.com/legal/api_policy), [intervals.icu forum – API update](https://forum.intervals.icu/t/strava-api-update-new-terms-subs-required-for-api-access/130240), [heise](https://heise.de/-11315017)
- Garmin: [python-garminconnect issue #332](https://github.com/cyberjunky/python-garminconnect/issues/332), [garth docs](https://garth.readthedocs.io/)
- COROS: [COROS support – developer/MCP](https://support.coros.com/hc/en-us/articles/53181619102996), [Partner API](https://support.coros.com/hc/en-us/articles/53181766856724), [RunnersPicks – COROS MCP](https://www.runnerspicks.com/blog/coros-mcp-connect-chatgpt-claude/), [the5krunner – COROS MCP](https://the5krunner.com/2026/05/13/coros-mcp-ai-data/), [intervals.icu – COROS structured workouts](https://forum.intervals.icu/t/coros-and-structured-workouts/16859/33)
