# web/p2-admin — Cổng quản trị

P2 phục vụ hai việc: **điều hành giải** và **kiểm tra code**. Mã nằm ở `../src/admin.tsx`, dùng chung routing, đăng nhập và API client với P1. Chỉ tài khoản `admin` vào được; guard ở frontend chỉ là trải nghiệm, backend kiểm tra quyền ở mọi request.

Chạy `npm run dev:admin` từ `web/` rồi mở `http://127.0.0.1:5174/admin/`; xem [README workspace](../README.md). Vite base và Router basename là `/admin`, khớp định tuyến của Caddy; API vẫn là `/api/v1/admin/...`.

## Màn hình

### Điều hành giải

| Đường dẫn | Màn hình | Thao tác |
| --- | --- | --- |
| `/admin/teams` | Đội | Tạo, duyệt, khóa, loại đội; nhập hạt giống; nhập đội hàng loạt từ CSV |
| `/admin/draw` | Bốc thăm | Tạo giải, bốc thăm, bốc lại trước khi chốt, chốt |
| `/admin/rounds` | Vòng đấu | Đặt giờ đóng băng, đóng băng (snapshot bot), chạy vòng, xem tiến độ |
| `/admin/matches` | Trận đấu | Lọc theo vòng, trạng thái; chạy lại ván; sửa kết quả kèm lý do |
| `/admin/queue` | Hàng đợi | Việc chờ, đang chạy, lỗi; nhịp tim worker; tạm dừng hàng đợi; trạng thái nhận đánh tập. Tự làm mới 5 giây khi trang đang mở |
| `/admin/announcements` | Thông báo | Soạn nháp, xem trước, công bố |

### Kiểm tra code

| Đường dẫn | Màn hình | Thao tác |
| --- | --- | --- |
| `/admin/submissions`, `/admin/submissions/:id` | Bản nộp | Lọc; xem cây tệp có tô cú pháp, so sánh hai bản |
| `/admin/similarity` | Trùng lặp | Cặp bản nộp sắp theo điểm, mở hai bản cạnh nhau |
| `/admin/games/:id` | Nhật ký ván | Replay, stderr hai bên, thời gian từng nước |
| `/admin/audit-log` | Nhật ký kiểm toán | Chỉ đọc, lọc theo người và thao tác |

## Quy tắc

- Mọi thao tác thay đổi dữ liệu có hộp xác nhận; thao tác ảnh hưởng kết quả bắt buộc nhập lý do. Nút bị khóa khi đang gửi, không tự gửi lại POST.
- Backend trả 409 thì tải lại và giải thích trạng thái mới, không báo thành công. Chạy lại ván hoặc sửa kết quả bị khóa khi vòng sau đã đóng băng hoặc giải đã kết thúc.
- Chạy lại ván tạo attempt mới: UI giữ lịch sử và đánh dấu attempt hiện hành.
- Mã nguồn và stderr chỉ tải qua API admin.
- API audit chỉ có lọc theo người, thao tác và phân trang, chưa lọc theo khoảng ngày; UI không giả vờ lọc toàn bộ dữ liệu bằng các dòng của một trang.
- Tạo giải với ruleset `dev-v1` cần backend bật `ALLOW_DEVELOPMENT_TOURNAMENTS=true`.
