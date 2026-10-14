# backend — API, dữ liệu, logic giải đấu

**Phụ trách:** C · **Dự phòng:** D · **Công nghệ:** FastAPI, SQLAlchemy 2, Alembic, RQ, PostgreSQL 16, MinIO

Backend là trung tâm điều phối: xác thực người dùng, giữ dữ liệu đội và bản nộp, đẩy việc cho worker, nhận kết quả, tính bảng xếp hạng và dựng nhánh đấu.

## Cấu trúc dự kiến

```
backend/
├── app/
│   ├── main.py
│   ├── auth/           # JWT, refresh token, phân quyền
│   ├── teams/
│   ├── submissions/
│   ├── matches/        # match, game, đánh tập
│   ├── tournament/     # bốc thăm, vòng bảng, loại trực tiếp, tiêu chí phụ
│   ├── admin/          # endpoint quản trị, nhật ký kiểm toán
│   ├── internal/       # endpoint cho worker
│   ├── ws/             # WebSocket
│   ├── storage.py      # MinIO
│   └── queue.py        # RQ
├── migrations/
└── tests/
```

## Nhiệm vụ

### Ngày 1
- [ ] Lược đồ DB theo `architecture.md` mục 5.1, migration đầu tiên
- [ ] Đăng nhập, refresh, đăng xuất; ba vai trò `member`, `captain`, `admin`
- [ ] Liệt kê endpoint và kiểu dữ liệu trả về, xuất OpenAPI để D gọi API giả

### Ngày 2
- [ ] API đội và thành viên; script tạo sẵn 20 đội và tài khoản từ tệp CSV
- [ ] `POST /submissions`: kiểm tra zip (tối đa 1 MB, 50 tệp, không tệp nhị phân), lưu MinIO, tính `sha256`, đẩy build job
- [ ] Chốt định dạng build job và match job với B

### Ngày 3
- [ ] `POST /internal/builds/{id}`, `POST /internal/games/{id}`, xác thực bằng token worker
- [ ] `PUT /teams/me/active-bot`, tách `scrimmage` và `tournament`
- [ ] API đánh tập: mỗi lần tạo 1 cặp 2 ván đổi bên; hạn mức 60 trận mỗi đội mỗi ngày

### Ngày 4
- [ ] WebSocket với kênh `team:{id}` và `public`; phát `build.updated`, `game.finished`, `match.finished`
- [ ] API trận, ván; `GET /games/{id}/replay` trả URL ký sẵn từ MinIO

### Ngày 5 — Vòng bảng
- [ ] Bốc thăm 4 bảng × 5 đội theo 4 nhóm hạt giống; seed ghi vào `audit_log` trước khi bốc
- [ ] Đóng băng: chụp `active_bots` phạm vi `tournament` của mọi đội
- [ ] Sinh 10 cặp mỗi bảng, mỗi cặp 2 ván đổi bên
- [ ] Tính điểm 3–1–0 theo cặp; tiêu chí phụ: hiệu số ván → số ván thắng → đối đầu → tổng nước đi trong ván thắng → bốc thăm
- [ ] Kiểm thử tính bảng xếp hạng với ít nhất 10 kịch bản, kể cả 3 đội bằng điểm

### Ngày 6 — Loại trực tiếp và quản trị
- [ ] Điền nhánh: Nhất A–Nhì B, Nhất B–Nhì A, Nhất C–Nhì D, Nhất D–Nhì C
- [ ] Tứ kết, bán kết chạm 2 (3 ván); tranh ba, chung kết chạm 3 (5 ván); chỉ đẩy ván tiếp khi cặp chưa phân thắng bại
- [ ] Quy tắc chọn bên ở ván quyết định cho đội hạt giống cao hơn
- [ ] Chạy lại ván (`attempt + 1`), sửa kết quả bắt buộc có lý do
- [ ] Ghi mọi thao tác quản trị vào `audit_log`
- [ ] `GET /admin/queue`: số việc chờ, đang chạy, nhịp tim worker

### Ngày 7
- [ ] Giới hạn tần suất ở tầng ứng dụng bổ sung cho Caddy
- [ ] Rà trùng lặp mã: so khớp token giữa mọi cặp bản nộp chính thức (thư viện `copydetect` hoặc tương đương), lưu `code_similarity`
- [ ] Thông báo: tạo, công bố, phát qua WebSocket

## Quy tắc bắt buộc

- `team_id` luôn lấy từ token, không bao giờ từ tham số người dùng gửi lên.
- Mã nguồn chỉ đội sở hữu và admin đọc được.
- Không xóa, không ghi đè `games`; kết quả hiện hành là bản ghi có `attempt` lớn nhất.

## Tiêu chí hoàn thành

- Kiểm thử tự động cho phân quyền: mọi endpoint thử với 4 vai trò (khách, thành viên đội khác, thành viên, admin).
- Kiểm thử tự động cho tính bảng xếp hạng và dựng nhánh.
- Giải giả lập 8 đội chạy từ bốc thăm đến chung kết mà không phải sửa DB bằng tay.
