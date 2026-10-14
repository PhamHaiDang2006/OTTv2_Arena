# web/p1-participant — Cổng thí sinh

**Phụ trách:** D · **Dự phòng:** C · **Công nghệ:** React 18, Vite, TypeScript, TanStack Query, React Router

Mục tiêu của P1 là rút ngắn vòng lặp *sửa code → biết bot mạnh hơn hay yếu đi*. Mọi màn hình khác là phụ.

## Màn hình

| Đường dẫn | Màn hình | Nội dung chính |
| --- | --- | --- |
| `/login` | Đăng nhập | Email, mật khẩu |
| `/` | Trang chủ đội | Bot đang dùng, trận sắp đấu, kết quả gần nhất, thông báo mới |
| `/submit` | Nộp bài | Kéo thả zip, chọn ngôn ngữ, nhật ký build chạy trực tiếp |
| `/submissions` | Lịch sử nộp | Danh sách bản nộp, trạng thái, đặt làm bot đánh tập hoặc bot thi đấu |
| `/scrimmage` | Đánh tập | Chọn đội đối thủ, hạn mức còn lại, danh sách trận đã đánh |
| `/games/:id` | Xem replay | Nhúng `replay-viewer` |
| `/standings` | Bảng đấu | 4 bảng, điểm, hiệu số |
| `/bracket` | Nhánh đấu | Sơ đồ tứ kết đến chung kết |
| `/docs` | Tài liệu | Luật, giao thức, tải bộ khởi động, câu hỏi thường gặp |

## Nhiệm vụ

### Ngày 1
- [ ] Khung Vite + React + TypeScript, cấu trúc dùng chung với P2 (thư viện component, client API)
- [ ] Bố cục chung, thanh điều hướng, trang đăng nhập
- [ ] Client API sinh từ OpenAPI của backend; dùng dữ liệu giả khi backend chưa sẵn

### Ngày 2
- [ ] Trang chủ đội
- [ ] Trang nộp bài: kéo thả, kiểm tra kích thước phía trình duyệt, thanh tiến trình tải lên

### Ngày 3
- [ ] Lịch sử nộp, nút đặt làm bot đang dùng (chỉ đội trưởng thấy)
- [ ] Nhật ký build cập nhật trực tiếp qua WebSocket `build.updated`

### Ngày 4 — M2
- [ ] Trang đánh tập: chọn đối thủ, tạo trận, danh sách trận cập nhật trực tiếp
- [ ] Trang replay nhúng `replay-viewer`

### Ngày 7
- [ ] Bảng đấu và nhánh đấu, cập nhật qua kênh `public`
- [ ] Hiển thị thông báo, có huy hiệu khi có thông báo mới
- [ ] Trang tài liệu
- [ ] Hiển thị tốt trên điện thoại, đủ để xem kết quả và replay

## Yêu cầu trải nghiệm

- Mọi lỗi từ backend hiện bằng tiếng Việt rõ ràng, không hiện mã lỗi thô.
- Trạng thái build có 4 màu cố định: chờ, đang build, sẵn sàng, lỗi.
- Khi bản nộp lỗi, hiện ngay dòng nhật ký gây lỗi, không bắt thí sinh cuộn tìm.
- Thời gian đóng băng nộp bài hiện đếm ngược trên trang chủ.

## Tiêu chí hoàn thành

- Một đội đi trọn luồng: đăng nhập → nộp → xem build → đặt bot → đánh tập → xem replay, không cần tải lại trang.
- Chạy được trên Chrome, Firefox, Safari và trình duyệt điện thoại.
