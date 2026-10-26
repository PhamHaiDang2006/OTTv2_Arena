# web/p1-participant — Cổng thí sinh

Mục tiêu của P1 là rút ngắn vòng lặp *sửa code → biết bot mạnh hơn hay yếu đi*. Mã nằm ở `../src/participant.tsx` (Arena) cùng các file chế độ chơi trong `../src/`; routing, layout và đăng nhập ở `../src/main.tsx`, API client dùng chung ở `../src/api.ts`. P1 không gọi API admin.

Chạy, build và test từ `web/` theo [README workspace](../README.md).

## Màn hình

| Đường dẫn | Màn hình | Nội dung chính |
| --- | --- | --- |
| `/` | Chọn chế độ | Casual, Bản đồ đặc biệt, Chơi với bạn, Tự luyện, Arena |
| `/casual`, `/special`, `/rooms`, `/practice` | Chế độ chơi | Xem [README workspace](../README.md#bố-trí-mã-nguồn) |
| `/arena` | Tổng quan Arena | Đội, bot đang dùng, lịch đóng băng, kết quả gần nhất, thông báo |
| `/submit` | Nộp bài | Kéo thả ZIP, chọn ngôn ngữ, tiến trình tải lên, nhật ký build |
| `/submissions`, `/submissions/:id` | Lịch sử nộp | Trạng thái build, mã nguồn của đội, đặt làm bot đánh tập hoặc bot thi đấu (đội trưởng) |
| `/scrimmage` | Đánh tập | Chọn đối thủ, số trận chưa xong, lý do tạm dừng nhận trận, danh sách trận |
| `/matches/:id`, `/games/:id` | Trận, replay | Kết quả từng ván, nhúng `ReplayViewer` |
| `/standings`, `/bracket` | Bảng, nhánh | Điểm, hiệu số, sơ đồ loại trực tiếp |
| `/docs` | Tài liệu | Luật, giao thức (lấy từ `GET /docs`), bộ khởi động |
| `/profile`, `/players/:id`, `/achievements` | Hồ sơ | Tên, giới thiệu, avatar/khung/màu, thống kê phòng hai người, thành tích luyện tập |

## Dữ liệu và làm mới

| Màn hình | Nguồn | Sự kiện WebSocket để tải lại |
| --- | --- | --- |
| Đội, bot đang dùng | `/teams/me`, `/teams/me/active-bot` | `build.updated` |
| Nộp bài, lịch sử | `/submissions`, `/submissions/{id}/build-log` | `build.updated` |
| Đánh tập, trận | `/scrimmages`, `/scrimmages/quota`, `/matches/{id}` | `game.finished`, `match.finished` |
| Replay | `/games/{id}/replay` | `game.finished` |
| Bảng, nhánh | `/standings`, `/bracket` | `standings.updated`, `match.finished` |
| Thông báo | `/announcements` | `announcement.published` |

Đường dẫn tương đối với `/api/v1`; method và response theo [OpenAPI](../../contracts/openapi.yaml). Frontend không tự cộng điểm hay suy ra người thắng.

## Đăng ký

Mở cổng thí sinh → **Chưa có tài khoản? Đăng ký** → nhập tên đội, email, mật khẩu (ít nhất 8 ký tự) → **Đăng ký và vào đấu trường**. Hệ thống đăng nhập luôn và tạo đội riêng ở trạng thái chờ duyệt. Đội chờ duyệt vẫn nộp bot và đánh tập được; giải chính thức cần admin duyệt. Chưa có xác minh email, quên mật khẩu hay mã mời vào đội.

## Yêu cầu trải nghiệm

- Lỗi từ backend hiện bằng tiếng Việt rõ ràng; đủ trạng thái loading, rỗng, 403, 409, 429 và URL replay hết hạn.
- Trạng thái build có màu cố định: chờ, đang build, sẵn sàng, lỗi. Build lỗi thì hiện ngay dòng nhật ký gây lỗi.
- Upload và tạo trận không tự gửi lại khi mất mạng; báo trạng thái chưa xác định và tải lại dữ liệu.
- Dùng tốt trên điện thoại, ít nhất để xem kết quả và replay.
