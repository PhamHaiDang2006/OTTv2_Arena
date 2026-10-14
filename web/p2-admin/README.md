# web/p2-admin — Cổng quản trị

**Phụ trách:** D · **Dự phòng:** C · **Công nghệ:** dùng chung khung với P1, bảng dữ liệu bằng TanStack Table

P2 phục vụ hai việc: **điều hành giải** trong lúc thi và **kiểm tra code**. Giao diện chia hai khu rõ ràng. Ưu tiên đúng và nhanh hơn đẹp: dùng component bảng có sẵn, không tự thiết kế.

Chỉ tài khoản `admin` vào được. Mọi thao tác thay đổi dữ liệu phải có hộp xác nhận, và những thao tác ảnh hưởng kết quả bắt buộc nhập lý do.

## Màn hình

### Khu điều hành giải

| Đường dẫn | Màn hình | Thao tác |
| --- | --- | --- |
| `/admin/teams` | Đội | Tạo, duyệt, khóa, loại đội; nhập hạt giống; nhập đội hàng loạt từ CSV |
| `/admin/draw` | Bốc thăm | Xem 4 nhóm hạt giống, bốc thăm, bốc lại trước khi chốt, chốt |
| `/admin/rounds` | Vòng đấu | Đặt giờ đóng băng, đóng băng, chạy vòng, xem tiến độ |
| `/admin/matches` | Trận đấu | Lọc theo vòng, trạng thái; chạy lại ván; sửa kết quả kèm lý do |
| `/admin/queue` | Hàng đợi | Số việc chờ, đang chạy, lỗi; nhịp tim từng worker; tạm dừng hàng đợi |
| `/admin/announcements` | Thông báo | Soạn, xem trước, công bố |

### Khu kiểm tra code

| Đường dẫn | Màn hình | Thao tác |
| --- | --- | --- |
| `/admin/submissions` | Bản nộp | Lọc theo đội, ngôn ngữ, trạng thái |
| `/admin/submissions/:id` | Mã nguồn | Xem cây tệp, tô cú pháp, so sánh với bản nộp khác của cùng đội |
| `/admin/similarity` | Trùng lặp | Danh sách cặp sắp theo điểm, mở hai bản cạnh nhau |
| `/admin/games/:id` | Nhật ký ván | Replay, stderr hai bên, thời gian từng nước |
| `/admin/audit-log` | Nhật ký kiểm toán | Chỉ đọc, lọc theo người, thao tác, thời gian |

## Nhiệm vụ

### Ngày 5
- [ ] Khung P2, kiểm tra quyền admin ở tầng định tuyến
- [ ] Trang đội: danh sách, duyệt, khóa, nhập CSV
- [ ] Trang bản nộp và xem mã nguồn

### Ngày 6 — M3
- [ ] Bốc thăm, vòng đấu, đóng băng, chạy vòng
- [ ] Trang trận đấu: chạy lại, sửa kết quả kèm lý do
- [ ] Bảng hàng đợi cập nhật mỗi 5 giây

### Ngày 7
- [ ] Trang trùng lặp với chế độ xem hai bản cạnh nhau
- [ ] Trang thông báo
- [ ] Trang nhật ký kiểm toán

## Tiêu chí hoàn thành

- Một quản trị viên không viết code điều hành trọn giải giả lập 8 đội chỉ bằng P2.
- Không thao tác nào ảnh hưởng kết quả mà không có hộp xác nhận và lý do.
- Mọi thao tác hiện ra trong nhật ký kiểm toán.
