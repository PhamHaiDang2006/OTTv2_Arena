# backend — quyết định triển khai và câu hỏi mở

Contract **v1.0.0** (`contracts/version.json`), profile **dev-v1** (`ruleset_status: development`). Mỗi mục ghi rõ chỗ hợp đồng chưa quy định và lựa chọn hiện tại. Mục "Câu hỏi mở" cần người phụ trách liên quan chốt; code hiện chạy theo lựa chọn tạm ghi kèm.

## Quyết định đã chọn (trong phạm vi hợp đồng cho phép)

### HTTP và dữ liệu

- Backend **không tự sinh OpenAPI** (`openapi_url=None`). Thay cho "diff OpenAPI sinh từ code" trong README, test kiểm tra tập (method, path) của app bằng đúng `contracts/operations.json`, và validate **mọi response** trong test (thành công theo schema operation, lỗi theo `Error`). Request body/param được validate bằng chính JSON Schema trong `contracts/schemas/common.schema.json`; không có bộ DTO thứ hai.
- `GET /matches` bắt buộc `tournament_id` theo OpenAPI, nên chỉ liệt kê trận giải. Trận đánh tập lấy qua `GET /scrimmages`.
- `Match.games` trả **mọi attempt** (lịch sử rerun/retry) kèm `is_current`, sắp theo `game_index`, `attempt`.
- Timestamp xuất dạng `2026-10-17T16:30:00.000Z` (có mili giây, vẫn kết thúc bằng `Z`).
- Sắp xếp: danh sách mặc định `created_at` giảm dần rồi `id` tăng dần (kể cả rounds); standings theo nhãn bảng/rank; bracket theo thứ tự vòng (QF → SF → tranh ba → chung kết) rồi `slot_index`; queue theo tên.
- Idempotency chỉ lưu response **thành công**. Request lỗi (4xx) không giữ khóa, gửi lại sẽ được xử lý lại. Đồng thời cùng khóa: advisory lock theo transaction → `409 REQUEST_IN_PROGRESS`. Record lưu cùng transaction với thay đổi nghiệp vụ.
- Admin gọi endpoint thành viên cần đội (`POST /submissions`, `POST /scrimmages`, `GET /scrimmages/quota`) nhận `403 FORBIDDEN`; `GET /teams/me` nhận `404` như behavior.md.
- Mỗi user thuộc tối đa một đội (`User.team_id` là một giá trị). Vai trò captain/member lưu ở `users.role`.
- Logout không có cookie → `401`; có cookie (kể cả đã thu hồi) → `204`.
- JWT HS256 ký bằng `JWT_SECRET`. Refresh token opaque, lưu SHA-256, xoay mỗi lần refresh, dùng lại token đã xoay → thu hồi cả family.

### Nộp bài

- Thứ tự kiểm tra upload: role → đọc multipart (đúng hai trường, `language` đã bật) → idempotency (hash bytes ZIP + language) → đội không bị khóa/loại → rate limit → kiểm tra ZIP. S3 được ghi trước khi commit DB; nếu DB lỗi sau đó chỉ để lại object mồ côi, không có submission.
- Tên tệp trong ZIP phải khớp pattern `key` của hợp đồng (chữ Latin không dấu, số, `_ . / -`) vì `SourceTree.files[].path` dùng pattern đó. Tệp tên có dấu bị từ chối với `reason=invalid_path`.
- Đường dẫn trùng được so sau NFC + casefold (`A.py` và `a.py` là trùng).
- Rate limit nộp 10/giờ/đội lấy theo con số Caddy trong infra/README; `429 RATE_LIMITED` kèm `Retry-After`.

### Worker, job, callback

- Outbox giao dịch: job RQ và event WS ghi cùng transaction, giao sau commit; scheduler giao lại bản ghi còn treo (Redis lỗi lúc commit) với cùng `job_id`. RQ job id = `payload.job_id`; func là chuỗi `ottv2_runner.jobs.build_submission` / `run_match`; `job_timeout` theo env.
- Callback không thuộc idempotency-key; khử trùng bằng `callback_receipts` (hash payload + lease token). Non-terminal callback yêu cầu `X-Worker-Lease` khớp `ottv2:lease:{job_id}` hiện hành; Redis lỗi → `503`.
- Artifact: backend kiểm tra object worker báo đã tồn tại rồi **copy sang key chuẩn bất biến** (`builds/{submission_id}/build.log`, `replays/{game_id}.json.gz`, `logs/{game_id}/{blue,red}.stderr.log`). Key chuẩn đã có với nội dung khác (ETag/size) → `409`. Thiếu artifact → `422 reason=artifact_missing`, trạng thái không đổi để worker gửi lại.
- `log_key` của game là **prefix** chứa `blue.stderr.log` và `red.stderr.log` (theo fixture `logs/{game_id}/` và architecture 5.3). Callback `finished` bắt buộc có đủ replay và hai stderr; `infra_error` không bắt buộc.
- Retry tự động: attempt 1..4, cùng cặp, cùng bên, cùng submission, **cùng seed**, game_id/job_id mới. Hết retry → match `blocked`; admin rerun tạo attempt tiếp theo (có thể > 4).
- Watchdog (15 s): job đã thấy lease mà lease biến mất trước terminal callback → `infra_error` + attempt mới (game) hoặc submission `failed` với `INFRA_ERROR` (build). Job chưa ai claim không bị coi là thua; nếu RQ báo job `failed/stopped/canceled` khi chưa từng có lease thì cũng xử lý như mất worker. Job queued mất khỏi Redis quá 5 phút được giao lại.
- Heartbeat: thời điểm `last_seen_at` lấy theo đồng hồ server; offline khi quá 90 s.
- Tạm dừng queue: không giao job mới từ outbox **và** gỡ khỏi RQ các job chưa có lease; tiếp tục thì giao lại cùng `job_id`. Không đụng job đang chạy.
- `Queue.failed` = số job kết thúc `infra_error` trong 24 giờ gần nhất của queue đó.
- Thứ tự khóa dòng ở mọi nơi: `worker_job → match → game → tournament → round → group`. Callback đồng thời được tuần tự hóa ở tournament/round khi cập nhật standings/bracket (có test tất định).

### Giải đấu

- Bốc thăm cần đúng 20 (hoặc 8 khi dev) đội `approved`, seed duy nhất 1..N. Seed PRNG ghi `audit_log` trước khi chia bảng. Bốc lại được đến khi khóa.
- Vòng do admin tạo trước (`group`, `quarterfinal`, `semifinal`, `third_place`, `final`), mỗi stage một vòng. Freeze cần: draw đã khóa, vòng trước `finished`, mọi đội tham gia có bot tournament `ready`. Đội `disqualified` bị loại khỏi danh sách tham gia vòng bảng khi freeze.
- Slot nhánh tạo sẵn khi tạo giải theo README backend: `A1–B2`, `B1–A2`, `C1–D2`, `D1–C2`; bán kết `W:QF1–W:QF2`, `W:QF3–W:QF4`; tranh ba `L:SF1–L:SF2`; chung kết `W:SF1–W:SF2`. Slot QF chỉ được điền khi cả vòng bảng xong.
- `best_of`: bảng/scrimmage `two_games`; QF/SF `first_to_2`; tranh ba/chung kết `first_to_3`. Bên chơi theo TOUR-02: ván lẻ đội A Xanh, ván chẵn đội B Xanh, ván cuối có thể (3 hoặc 5) đội seed nhỏ hơn Xanh.
- Bảng xếp hạng: rút thăm bằng `xorshift32-fisher-yates-rejection-v1` trên UUID đã sort, seed mới ghi audit trước khi dùng; thứ tự rút thăm lưu bền (`tiebreak_lots`) và dùng lại khi tính lại. Chỉ rút thăm khi bảng đã đấu xong; trước đó phần còn bằng nhau hiển thị theo seed (chỉ để xem, chưa phải quyết định).
- Freeze theo giờ (`freeze_at`) chạy cùng code path với admin, actor `null`; lần từ chối được audit một lần cho mỗi giá trị `freeze_at`.
- Thao tác admin bị từ chối `409` được audit bởi middleware với action `<operationId>.rejected`.
- Override chỉ cho trận giải, không còn ván đang chờ/chạy, winner phải là một trong hai đội và khớp tỉ số; hòa (`winner_team_id=null`, tỉ số bằng) chỉ ở vòng bảng.
- Similarity: tự tính sau mỗi lần freeze vòng cho các bản nộp trong snapshot (k-gram token chuẩn hóa + winnowing, Jaccard). Không dùng thư viện ngoài; chỉ để admin sàng lọc.

### Tài liệu và cấu hình

- `GET /docs`: `rules_markdown` = `contracts/rules.md`; `protocol_markdown` = mục 4 của `architecture.md`; `starter_kits` từ `STARTER_KITS_JSON`.
- `GET /capabilities.languages` = `ENABLED_LANGUAGES` (mặc định `python,cpp`); `tournament_enabled` phản ánh `ALLOW_DEVELOPMENT_TOURNAMENTS` thật.
- Tạo tài khoản: API không nhận mật khẩu; đặt bằng CLI `set-password`. Chưa có luồng email/kích hoạt.

## Câu hỏi mở

| # | Câu hỏi | Ai chốt | Đang làm tạm |
| --- | --- | --- | --- |
| Q1 | Quy ước key staging để fencing artifact. behavior.md yêu cầu "upload key có ownership token ở vùng staging" nhưng hợp đồng không có định dạng. Đề xuất `staging/{job_id}/{lease_token}/...`. | B + C | Backend chấp nhận mọi key hợp lệ, copy sang key chuẩn; **chưa** kiểm tra token trong path. |
| Q2 | Worker có được upload thẳng vào key chuẩn (như fixture `replays/{game_id}.json.gz`) không? Nếu có thì mất fencing với worker cũ. | B + C | Chấp nhận (source = target thì chỉ kiểm tra tồn tại). |
| Q3 | `log_key` là prefix chứa `blue.stderr.log`/`red.stderr.log`? Callback `finished` có bắt buộc đủ hai tệp không? | B | Prefix; bắt buộc đủ hai tệp khi `finished`. |
| Q4 | Heartbeat: runner/README ghi "gửi về Redis", behavior.md ghi endpoint nội bộ. | B | Theo behavior.md/OpenAPI: `POST /internal/workers/heartbeat`. Đề nghị B sửa runner/README. |
| Q5 | Rerun một ván sớm của trận loại trực tiếp khi các ván sau đã có: ván sau giữ nguyên hay bị hủy? | C + ban tổ chức | Giữ nguyên; tính lại theo thứ tự ván, ván sau điểm quyết định không được tính nhưng vẫn hiển thị. |
| Q6 | "Tổng ply của các ván thắng ít hơn" (TOUR-02) tính trên mọi ván trong bảng hay chỉ ván giữa các đội đang bằng nhau? | A + C (luật) | Mọi ván thắng trong bảng (cột `winning_plies` của Standing). |
| Q7 | WS: "team subscribe cần auth frame trong 10s trước đó" nghĩa là auth phải gửi trong 10 s đầu kết nối, hay auth phải mới hơn 10 s so với lúc subscribe? | C + D | Auth chỉ được nhận trong 10 s đầu kết nối. |
| Q8 | Đội `pending` (chưa duyệt) có được tạo scrimmage không? (Đội pending không xuất hiện trong danh sách đối thủ.) | C + ban tổ chức | Được, chỉ chặn đội bị khóa/loại. |
| Q9 | Freeze có cần kiểm tra submission được build với đúng `engine_version` của giải không? | A + C | Chưa kiểm tra. |
| Q10 | Đội bị loại giữa giải: trận chưa đấu, standings và slot nhánh xử lý thế nào? | Ban tổ chức | Chỉ loại khỏi danh sách freeze; không tự xử thua. |
| Q11 | Override vòng bảng có giới hạn tỉ số (tối đa 2 ván) không? | C | Chỉ kiểm tra winner khớp tỉ số. |
| Q12 | Scrimmage có được rerun/override không? | C + D | Rerun được (không có downstream); override bị từ chối `409`. |
| Q13 | Quy trình tạo/kích hoạt tài khoản thật (email mời, đặt mật khẩu lần đầu). | C + ban tổ chức | CLI `set-password`/`add-member`. |

## Ảnh hưởng tới bên khác (cần phối hợp, chưa sửa vì ngoài `backend/`)

- **B (infra):** image backend phải chứa `contracts/` và `architecture.md` (hoặc đặt `CONTRACTS_DIR`/`ARCHITECTURE_PATH`). Cần thêm vào Compose một tiến trình `python -m app.cli scheduler` bên cạnh API, chạy `app.cli migrate` một lần trước API. Các biến backend mới (bảng trong README) chưa có trong `infra/.env.example`.
- **B (CI):** test backend cần service PostgreSQL 16 + Redis 7 trong `.github/workflows`; chưa thêm.
- **B (runner):** upload replay với `Content-Type: application/json` + `Content-Encoding: gzip` (backend copy giữ metadata); key staging theo Q1; heartbeat theo Q4.
- **D (web):** trận đánh tập ở `/scrimmages`, không phải `/matches`; `Match.games` có nhiều attempt, dùng `is_current`; lỗi chi tiết nằm ở `error.details` (`reason`, `errors`, `team_ids`...).
