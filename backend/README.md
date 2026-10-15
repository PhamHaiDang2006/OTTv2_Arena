# backend — API, dữ liệu, logic giải đấu

## Hợp đồng tích hợp và hướng dẫn cho AI

Đọc [AGENTS.md](../AGENTS.md), [hợp đồng tích hợp](../integration.md) mục 2–4, 7–9 và README runner/P1/P2. C là chủ schema DB, migration và hợp đồng HTTP.

### API trước giao diện

- [contracts/openapi.yaml](../contracts/openapi.yaml) đã có operationId, quyền, request/response/error, fixture và phân trang. C triển khai đúng hợp đồng này; không tạo lại API theo suy đoán. Nguồn sinh là contracts/build.mjs.
- OpenAPI đã review là hợp đồng consumer. Code FastAPI phải khớp; kiểm tra diff OpenAPI sinh từ code trong CI, không âm thầm lấy code mới ghi đè hợp đồng.
- D sinh TypeScript client từ bản này. Không bắt D tự khai báo DTO hoặc suy kiểu từ bảng SQL.
- API-01 đã được đặc tả: opponents/quota, auth/me, freeze/snapshot, nguồn/log, thông báo và queue. Dùng operationId và fixture trong contracts/operations.json để phối hợp D.
- Mọi tài nguyên submission/match/game phải có schema detail và list rõ ràng. Login/refresh, error envelope, response list theo integration mục 3.
- Thực hiện cookie/CSRF/Origin, đăng ký WS và hết hạn token theo contracts/behavior.md. WebSocket chỉ là thông báo refetch sau commit; không phát mã nguồn/debug lên public.

### Trạng thái và dữ liệu

- Submission queued → building → ready/failed; không cho đặt active bot chưa ready hoặc của đội khác.
- Snapshot bot theo vòng cần dữ liệu bền riêng (round và frozen submission mapping); bổ sung migration/architecture trước code, không chỉ đọc lại active_bots khi enqueue.
- Dùng enum trong schema và bảng chuyển trạng thái/điều kiện trong contracts/behavior.md; trả 409 khi không hợp lệ, frontend không tự điều hành tiến trình.
- Team hiện tại lấy từ user/token được kiểm tra với membership. Admin thao tác đội khác và opponent_team_id được phép là tham số nhưng phải validate quyền/nghiệp vụ; không diễn giải quy tắc team_id thành cấm mọi ID đội trong API.
- Callback tuân mục 4: xác thực job, transaction, dedup, attempt cũ và chống cộng điểm lặp. Chốt cơ chế enqueue sau commit và phục hồi khi DB thành công nhưng Redis lỗi.
- DB result dùng BLUE/RED khi finished; callback result là object, adapter phải map rõ. Không trộn kết quả game với điểm cặp đấu.
- Giữ lịch sử rerun/override, không xóa games. Tính lại đúng một lần; khóa thao tác khi downstream đã frozen hoặc giải finished theo contracts/behavior.md.

### Chạy độc lập và bàn giao

PR implementation đầu tiên bổ sung lệnh cài, migrate, seed 2 đội + admin, start API và test, cùng biến DATABASE_URL/REDIS_URL/S3/JWT/worker token theo mục 7. Các lệnh này chưa tồn tại trong baseline tài liệu.

Trước merge: response thật khớp OpenAPI/fixture, phân quyền chéo đội, refresh/logout, callback lặp và sai job, snapshot bất biến, retry attempt, bảng điểm và nhánh; WS reconnect refetch được với D. Migration kiểm tra từ DB trống và từ revision trước. Chỉ C tạo migration, ghi head/revision và thứ tự merge để tránh hai head. D review API, B review queue/callback.


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

- Đội sở hữu thao tác của thí sinh lấy từ phiên đăng nhập đã kiểm tra membership. ID đối thủ hoặc đội đích của thao tác admin nhận từ request phải được kiểm tra quyền/nghiệp vụ riêng.
- Mã nguồn chỉ đội sở hữu và admin đọc được.
- Không xóa, không ghi đè `games`; kết quả hiện hành là bản ghi có `attempt` lớn nhất.

## Tiêu chí hoàn thành

- Kiểm thử tự động cho phân quyền: mọi endpoint thử với 4 vai trò (khách, thành viên đội khác, thành viên, admin).
- Kiểm thử tự động cho tính bảng xếp hạng và dựng nhánh.
- Giải giả lập 8 đội chạy từ bốc thăm đến chung kết mà không phải sửa DB bằng tay.
