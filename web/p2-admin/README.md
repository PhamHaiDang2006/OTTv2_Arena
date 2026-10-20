# web/p2-admin — Cổng quản trị

## Implementation 1.0.0

Mã P2 ở `../src/admin.tsx`, dùng routing/layout/auth/API client chung. Đã có đội/CSV,
tạo giải/bốc thăm/chốt, vòng/snapshot/freeze/run, attempt/rerun/override, queue,
source có tô cú pháp và xem hai bên, similarity, draft/publish thông báo và audit.
Mọi mutation P2 đi qua form xác nhận; nghiệp vụ cần reason đều có trường bắt buộc.

Chạy `npm run dev:admin` từ `web/`, mở `/admin/` trên port 5174.
Xem [README workspace](../README.md) và [CHECKS.md](../CHECKS.md).
Checklist ngày công bên dưới là kế hoạch gốc, không thay thế nghiệm thu giải trọn luồng.
Audit API 1.0.0 chỉ có filter actor/action và pagination, chưa có query lọc khoảng ngày;
UI không giả vờ lọc toàn bộ dữ liệu bằng các dòng của một trang.

## Hợp đồng tích hợp và hướng dẫn cho AI

Đọc [AGENTS.md](../../AGENTS.md), [hợp đồng tích hợp](../../integration.md) mục 2–4, 6–9 và README backend/P1/replay-viewer.

- D sở hữu P2, dùng shared API client/auth/UI và lockfile của web; không tạo implementation auth thứ hai.
- UI ở /admin; Vite base và Router basename phải khớp Caddy cùng deep link /admin/games/:id. API vẫn dùng /api/v1/admin/..., không suy ra API từ URL trang.
- Guard admin chỉ phục vụ UX; backend kiểm tra quyền ở mọi request, kể cả signed URL source/stderr.
- Dùng schema enum/trạng thái và khả năng thao tác do C đặc tả. Không tự cho phép freeze/run/rerun chỉ vì nút đang hiển thị.
- API-01 và quy tắc vận hành TOUR-02 đã có trong [OpenAPI](../../contracts/openapi.yaml) và [behavior](../../contracts/behavior.md): freeze, queue pause, source tree, stderr, publish và khóa rerun downstream. Dùng [mock API](../../contracts/README.md) khi backend chưa có.
- Mutation phải hiển thị xác nhận; thay đổi kết quả có reason bắt buộc. Disable khi đang gửi; không tự retry POST. Backend trả 409 thì refetch và giải thích trạng thái mới.
- Rerun tạo game attempt mới; UI giữ lịch sử và đánh dấu attempt hiện hành, không sửa kết quả cũ trong cache như thể cùng bản ghi.
- Dữ liệu mã nguồn/stderr chỉ tải sau quyền admin; truyền stderr cho viewer mode admin theo props chung.
- Sự kiện WS dùng invalidate/refetch; queue polling mỗi 5 giây theo kế hoạch và dừng khi trang không hoạt động. Không suy ra server đã hoàn thành từ việc request được nhận.

### Phụ thuộc theo nhóm màn hình

Đội/source dùng API admin và phân quyền của C; bốc thăm/vòng đấu dùng trạng thái tournament/round và snapshot đã chốt; trận dùng attempt/result hiện hành; queue dùng heartbeat/job schema B+C; audit là dữ liệu chỉ đọc. Với mỗi màn hình, D ghi operationId + fixture + trạng thái lỗi trong test khi tạo implementation.

### Chạy độc lập và bàn giao

Lệnh dev thật, typecheck/test/build đã có trong workspace web chung. Mock HTTP chuẩn trả captain khi login; P2 dùng backend dev để kiểm tra admin và member bị từ chối. Test bổ sung cho 409, xác nhận mutation, errors trong kết quả import và WS nằm trong web/tests.

Trước merge: member không truy cập nguồn/log; thao tác nguy hiểm có reason và backend audit; double click không tạo hai vòng; 409 không làm UI báo thành công; xem attempt cũ/mới rõ ràng; chạy giải giả lập qua API thật. C review nghiệp vụ, A đối chiếu replay, B đối chiếu routing.


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
