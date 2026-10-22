# Hành vi chuẩn v1.3.0

Đây là quy ước kỹ thuật được chọn cho việc triển khai độc lập. Schema quyết định tên/kiểu trường; tài liệu này quyết định quyền, trạng thái và các ràng buộc nhiều trường. Không coi mock HTTP là implementation của các quy tắc dưới đây.

## HTTP, auth và dữ liệu riêng

- HTTP base `/api/v1`, WS `/ws`. JSON UTF-8, UUID dạng string, timestamp UTC Z, duration ms. Danh sách page bắt đầu 1, mặc định 20, tối đa 100; response items/page/page_size/total. Filter tùy chọn trừ tham số được ghi required trong OpenAPI. Sort mặc định timestamp tạo giảm dần, tie id tăng dần; standings sort group label/rank, bracket sort round thứ tự thi đấu/slot_index, queue theo tên. Không tự thêm query `sort`.
- `x-role=member` chấp nhận member/captain/admin ở mức route, nhưng endpoint `/teams/me` và tài nguyên đội vẫn đòi membership tương ứng. Admin không có đội nhận 404 ở `/teams/me`, không được tạo scrimmage hoặc upload thay đội qua endpoint member. Admin dùng các endpoint admin để xem đội khác.
- `/matches` và `/games`: người đã đăng nhập xem trận giải; trận scrimmage chỉ hai đội tham gia và admin. Replay có debug nên áp quyền tương tự; source/build-log chỉ đội sở hữu và admin. `/teams/opponents` chỉ đội pending hoặc approved, không locked/disqualified, có bot scrimmage ready, loại đội hiện tại. Backend không lấy actor team từ payload.
- JWT 15 phút. Refresh token opaque được lưu hash server-side, xoay sau refresh, thu hồi khi logout; refresh token bị tái sử dụng thì thu hồi family. Cookie production: `ottv2_refresh`, HttpOnly, Secure, SameSite=Strict, Path=/api/v1/auth; tuổi thọ 7 ngày. Dev loopback có thể bỏ Secure trong cấu hình dev rõ ràng.
- Register/login/refresh/logout yêu cầu Origin đúng danh sách frontend cấu hình; thiếu/sai Origin bị 403 đối với browser session API. Không dùng CORS wildcard với credentials. Chỉ nhận JSON cho login, không nhận form URL encoded. Refresh/logout dùng cookie, không cần JWT còn hạn. Logout xóa cookie cùng path và thu hồi token; token đã bị thu hồi trả 204 khi cookie có mặt (idempotent), không lộ giá trị token.
- Frontend giữ access token trong memory, refresh một lần cho 401, gom các refresh đồng thời. Refresh lỗi thì xóa phiên và về login. Không tự retry mutation trừ giữ nguyên Idempotency-Key.
- Idempotency-Key UUID bắt buộc cho mutation được OpenAPI đánh dấu. Backend lưu actor + method + normalized path + key + hash request + response trong 24h. Cùng key/cùng body trả nguyên status/body, khác body trả 409 IDEMPOTENCY_CONFLICT, đang xử lý trả 409 REQUEST_IN_PROGRESS. Với ZIP hash cả bytes và language. Commit thay đổi và record idempotency cùng transaction. Outbox giao job Redis sau commit, retry delivery giữ job_id.
- Không ghi token/password/source vào log lỗi; error.code ổn định, message tiếng Việt. Mã chung: INVALID_REQUEST, UNAUTHORIZED, FORBIDDEN, NOT_FOUND, STATE_CONFLICT, IDEMPOTENCY_CONFLICT, REQUEST_IN_PROGRESS, PAYLOAD_TOO_LARGE, RATE_LIMITED, SERVICE_UNAVAILABLE. Nghiệp vụ: SUBMISSION_NOT_READY, SELF_SCRIMMAGE, QUOTA_EXCEEDED, SCRIMMAGE_LIMIT, SCRIMMAGE_PAUSED, ROUND_NOT_FROZEN, DOWNSTREAM_STARTED, RULESET_UNCONFIRMED. details là map thông tin không bí mật.

## Submission, build và giới hạn

- queued → building → ready/failed, hoặc queued → failed. Không sửa source/language/hash/image sau terminal; nộp mới tạo submission_id mới. Active bot chỉ ready thuộc đội; team locked/disqualified không nộp/đánh tập.
- Upload ZIP <= 1 MiB, <= 50 file, tổng giải nén <= 5 MiB, mỗi file <= 1 MiB. Cấm absolute path, `..`, symlink, archive lồng, file nhị phân và đường dẫn trùng sau normalize. Allowlist source UTF-8/extensions do bảng build dưới đây quy định; không thực thi script build người dùng cung cấp.
- Build tối đa 60s, smoke game tối đa 150s, không network, log build <= 1 MiB. Build lỗi bot/protocol/compiler là failed. Build lỗi hạ tầng cũng failed với error.code INFRA_ERROR, không tự sửa submission terminal; người dùng có thể nộp lại. Retry tự động ba lần chỉ áp game infra_error.
- `POST /scrimmages` tạo cặp 2 ván đổi màu và chụp hai active bot tại thời điểm request. Không tự đấu. Hạn mức 60 cặp/ngày/đội tạo, reset 00:00 Asia/Saigon; duplicate idempotency không trừ lần hai. 429 QUOTA_EXCEEDED khi hết; response quota resets_at vẫn UTC. Từ 1.3.0 còn có giới hạn trận chưa xong của đội và tạm dừng nhận khi tải cao, xem mục Phân bổ tài nguyên.

| language | File chính ở gốc ZIP | Compile / run | Nền bắt buộc |
| --- | --- | --- | --- |
| python | main.py | không compile; `python -u /bot/main.py` | Python 3.12 + ottv2 cùng engine_version + numpy |
| cpp | main.cpp | `g++ -std=c++20 -O2 -pipe main.cpp -o /bot/main`; `/bot/main` | C++20, include header trong ZIP bằng include tương đối |
| java | Main.java | `javac Main.java`; `java -cp /bot Main` | Java 21, chỉ bật sau test sandbox |
| node | main.js | không install package; `node /bot/main.js` | Node 22, chỉ bật sau test sandbox |

B phải chọn image digest cụ thể khi tạo Dockerfile; không tải package từ code thí sinh. Nguồn hỗ trợ .py/.cpp/.h/.hpp/.java/.js/.json/.txt/.md; file chính phải đúng ngôn ngữ. image_tag callback là registry reference bất biến, ưu tiên digest.

## Worker, lease và callback

- Public RQ import: `ottv2_runner.jobs.build_submission(payload)` và `ottv2_runner.jobs.run_match(payload)`; C enqueue tên import dạng string với một dict duy nhất, B implement trong package worker. Không yêu cầu backend import Docker code. RQ job ID bằng payload.job_id.
- Worker claim Redis `ottv2:lease:{job_id}` bằng SET NX, value token UUID, TTL 90s; gia hạn mỗi 15s bằng compare-token atomic script. Callback có X-Worker-Lease; backend kiểm tra khớp lease hiện hành, job và tài nguyên trước cập nhật. Không gia hạn/mất lease thì worker dừng bot và không upload/callback thêm.
- Heartbeat gửi endpoint nội bộ mỗi 30s, worker offline khi quá 90s. Backend watchdog mỗi 15s phát hiện lease hết hạn của job đang chạy, đánh dấu infra_error và tạo attempt mới. Job queued chưa được claim không bị watchdog coi là bot thua.
- Callback finished phải upload replay/stderr xong. Để tránh stale worker ghi đè artifact, upload key có ownership token ở vùng staging, backend xác minh lease khi finalize/copy tới key chuẩn; key chuẩn bất biến, không overwrite. B/C thực hiện finalize có fencing/conditional write, kiểm tra key tồn tại trước commit.
- Prefix ownership bắt buộc là `staging/{job_id}/{lease_token}/`. Runner đặt file tại `staging/{job_id}/{lease_token}/builds/{submission_id}/build.log` hoặc `staging/{job_id}/{lease_token}/games/{game_id}/...`. Backend kiểm tra prefix theo job và lease đã xác thực, không nhận key chuẩn từ worker. `log_key` là prefix thư mục game có dấu `/` cuối, chứa `blue.stderr.log` và `red.stderr.log`; dùng cùng tên cho finished và infra_error. Finished cần đủ hai stderr (có thể rỗng) và `replay.json.gz`; infra_error cho phép thiếu log. Replay upload với Content-Type `application/json`, Content-Encoding `gzip`, backend copy giữ metadata.
- Callback terminal đã lưu: retry payload giống hệt + đúng token của receipt trả 200 dù lease đã được giải phóng; payload khác trả 409. Token receipt được lưu với kết quả, không dùng nó để nhận payload mới. Callback cũ running sau terminal trả 409, không phát event hoặc làm lùi trạng thái.
- Khi nhận infra_error hoặc watchdog phát hiện mất worker: backend tạo game_id mới, attempt+1, job_id mới, tối đa attempts 1..4. Worker không tự enqueue attempt. Callback attempt cũ không thay current attempt. RQ redelivery cùng job chỉ được claim nếu chưa terminal; kết quả đã có chỉ gửi callback lưu sẵn.
- Worker persist callback pending vào volume trước khi gửi, retry transport backoff 1/2/4/8/16/30s (tối đa 30s giữa các lần) đến khi được xác nhận hoặc 409 terminal conflict. Không chạy lại bot để giải quyết HTTP timeout; báo admin khi backlog callback >5 phút. Lease được giữ cho đến khi backend nhận terminal callback hoặc worker xác nhận kết quả đã lưu.
- Game queued → running → finished/infra_error; queued → infra_error khi không khởi động được. finished/infra_error bất biến. `result` và replay chỉ xuất hiện khi finished; duration_ms null khi queued, running có thể 0; infra_error không có winner. GameConfig trong MatchJob phải khớp engine_version/map_id/players ngoài config.
- Build không có attempt: duplicate job cùng submission đã terminal không build lại. Worker heartbeat không thể gia hạn lease thay owner token.
- Submission dùng trong game hoặc snapshot vòng phải được build với cùng `engine_version` của game/giải. Backend từ chối bot khác version bằng `409 SUBMISSION_NOT_READY` trước enqueue/freeze; không để worker chạy luật mới trên bot dùng package engine cũ.

## Giải đấu và thao tác quản trị

Các thuật toán chia bảng/tiebreak dưới đây dùng profile phát triển trong rules.md; giải chính thức bị chặn bằng RULESET_UNCONFIRMED khi ruleset_status=development. Để test flow admin có thể dùng mock hoặc môi trường dev với `ALLOW_DEVELOPMENT_TOURNAMENTS=true`; flag này không được bật ở production. API capabilities.tournament_enabled phản ánh flag thực tế, không hardcode false trong implementation.

- Tournament draft → drawn sau bốc thăm; bốc lại chỉ khi chưa locked, không có round frozen. Lock draw chỉ một lần; khi round đầu chạy chuyển running; sau final/third_place hoàn tất chuyển finished. Engine version/ruleset không đổi sau draw lock.
- Round draft → frozen → running → finished. Freeze cần mọi đội hợp lệ có bot tournament ready; chụp snapshot và timestamp trong transaction, không đổi snapshot sau đó. Scheduled freeze chạy cùng code path như thao tác admin, có audit actor null. Đổi freeze_at chỉ khi draft. Run cần snapshot + vòng trước hoàn thành, tạo match/outbox một lần.
- Scrimmage match queued → running → finished khi cả hai ván current attempt finished; điểm cặp 2–0 thắng, 1–1 hòa. Group match tương tự, points=3/1/0. best_of wire là `two_games`, `first_to_2`, `first_to_3`; database có thể dùng số nhưng adapter không trả số lên API.
- Loại trực tiếp tạo ván tiếp theo sau ván trước finished, dừng khi đủ 2/3 thắng. Match blocked nếu một current game hết retry; admin rerun mới cho tiếp tục. Không âm thầm dùng kết quả attempt cũ.
- Rerun chỉ game đã finished/infra_error, không cho running/queued. Nếu round sau đã frozen/running/finished hoặc giải finished, trả 409 DOWNSTREAM_STARTED. Nếu chưa có downstream, mở lại match/round và tính lại standings từ current attempts. Không xóa lịch sử. Override match cũng áp khóa downstream, bắt buộc reason, audit lưu trước/sau; override là kết quả cặp hành chính, không sửa game/replay.
- Đóng băng một round là ranh giới khóa kết quả round trước. Tính standings/bracket từ dữ liệu hiện hành trong transaction; phát WS sau commit. Audit mọi mutation admin, kể cả lý do thất bại 409 ở mức vận hành phù hợp.
- CSV import header `name,slug,captain_email,seed`; kiểm tra toàn bộ trước, có bất kỳ dòng lỗi thì không tạo đội nào, response ImportResult.created=[] và errors chỉ rõ row (header là 1). 201 là request import được xử lý; UI phải kiểm tra errors. API quản trị đội/CSV không nhận mật khẩu; tự đăng ký dùng endpoint riêng dưới đây.
- Announcements draft (published_at=null), publish idempotent và phát event một lần; chỉ sửa draft. Queue pause dừng lấy job mới của queue được chọn, không kill trận đang chạy. Source file path phải nằm trong source ZIP đã validate; không cho file system path tùy ý.

## WebSocket

- Server kiểm tra Origin allowlist ngay handshake. Public subscribe được không auth; team subscribe cần auth frame trong 10s trước đó. Token hết hạn gửi error TOKEN_EXPIRED rồi close 4401, client refresh HTTP và reconnect. Role không cho kênh đội trả FORBIDDEN, không subscribe ngầm.
- Frame <=16 KiB, <=30 message/phút/client; ping/pong ứng dụng dùng `{type:"ping"}`/`{type:"pong"}`, idle 60s thì server đóng 4408. Invalid message gửi INVALID_MESSAGE, vượt hạn RATE_LIMITED và close 4429. Không truyền JWT trong query string/subprotocol/log.
- subscribe/unsubscribe có ack đúng channel, không đăng ký trùng. Sự kiện event_id UUID, timestamp UTC, payload theo schema. Không bảo đảm replay hoặc thứ tự toàn cục; refetch HTTP sau reconnect, không suy winner/score từ event.
- build.updated chỉ kênh đội. Game/match scrimmage chỉ hai kênh đội; trận giải có thể public nhưng payload chỉ ID. announcement và standings public. stderr/source/debug không bao giờ nằm trong WS event.

## Dữ liệu DB cần triển khai

C sở hữu migration, cần thêm vào phác thảo architecture: rounds, round_snapshots + frozen_bots, worker_jobs (job/lease/status), callback_receipts (hash/token), idempotency_records, outbox, refresh_token_families và match_overrides. Giữ unique (match_id,game_index,attempt); standings lấy current attempt. Schema HTTP không phải schema SQL và không được tự expose cột nhạy cảm.

## Tự đăng ký — bổ sung HTTP contract 1.1.0

- `POST /auth/register` công khai, JSON `{email,password,team_name}`, trả 201 `Auth` và refresh cookie như login. Không cần Idempotency-Key, không tự retry. Nếu mất response, thử đăng nhập bằng thông tin vừa đăng ký.
- Email hợp lệ tối đa 320 ký tự, lưu lowercase; mật khẩu 8–256 ký tự được hash Argon2id; tên đội 1–100 ký tự sau trim, không chỉ khoảng trắng. Không nhận role, status, team_id hoặc seed từ client.
- Tạo trong một transaction: user captain, đội pending với slug tự sinh, membership, audit không chứa mật khẩu và refresh session. Email đã tồn tại (kể cả tài khoản chưa đặt mật khẩu) trả 409 STATE_CONFLICT/reason=email_taken; không chiếm tài khoản cũ. Unique index xử lý cả đăng ký đồng thời.
- Origin bắt buộc theo allowlist. Giới hạn mặc định 5 yêu cầu hợp lệ schema/IP/giờ (`REGISTRATION_RATE_PER_HOUR`); Redis lỗi thì trả 503. Không tin X-Forwarded-For do client tự gửi; cấu hình proxy tin cậy khi triển khai.
- Đội pending được upload, chọn bot ready và đánh tập với đội pending/approved có bot ready. Locked/disqualified vẫn bị chặn. Bốc thăm giải chỉ chọn đội approved như trước.
- Đăng ký chưa xác minh email; chưa có quên mật khẩu hoặc gia nhập đội bằng mã mời. Mỗi lần đăng ký tạo đội riêng.
- Backend và web phải cập nhật cùng contract 1.1.0 (86 definitions, 66 operations, 138 fixtures); engine, job/callback schema_version=1, replay format=1 và luật dev-v1 không đổi.

## Casual — chạy trên trình duyệt từ contract 1.3.0

- Contract 1.2.0 có 5 operation `/casual/games` chạy luật và bot trên backend. Contract 1.3.0 **gỡ cả 5 operation**: backend trả 404 cho các đường dẫn này, không còn import engine khi chạy. Bảng `casual_games` (migration 0002) được giữ nguyên để không xóa ván cũ; không code nào đọc/ghi bảng. Muốn xóa bảng cần quyết định riêng và migration mới.
- Bàn cờ, luật dev-v1 (nước hợp lệ, thứ tự GOAL → WIPEOUT → STALEMATE → MOVE_LIMIT, tiebreak RULE-05) và bot mẫu random/greedy chạy trong trình duyệt. Luật nằm ở `@ottv2/replay-viewer` (`legalMoves`, `isLegal`, `outcome`, `tiebreak`, chữ ký trong viewer-api.ts), kiểm chéo với engine qua `engine/fixtures/positions.json`, `engine/fixtures/outcomes.json` và replay engine thật. Đổi luật phải đổi engine, bản TypeScript và fixture cùng đợt.
- Vẫn bắt đăng nhập để vào Casual, nhưng không gửi nước đi lên server. Ván lưu trong localStorage của trình duyệt theo user id (50 ván gần nhất); trình duyệt hoặc máy khác không thấy. Hai tab cùng ván: tab đi nước giữ Web Lock của tài khoản, đọc lại ply/trạng thái đã lưu và từ chối nếu tab kia đã đổi, không ghi đè. Không đồng hồ, tối đa 300 ply, RESIGNED chỉ thuộc Casual. Kết quả Casual không phải nguồn tin cậy và không ảnh hưởng Arena.

## Phân bổ tài nguyên — contract 1.3.0

| Chế độ | Chạy ở | Tài nguyên server |
| --- | --- | --- |
| Casual | Trình duyệt | Chỉ xác thực, không lưu ván |
| Tự luyện | Máy thí sinh: `python -m ottv2 practice <bot> --vs random\|greedy\|<bot khác>` | Không; P1 `/practice` chỉ hướng dẫn và mở replay cục bộ trong trình duyệt |
| Đánh tập | Worker riêng của `match:scrimmage` | Giới hạn số ván đồng thời bằng số worker đánh tập |
| Giải chính thức | Worker riêng của `match:tournament` | Không bao giờ chạy job đánh tập |

- Worker giải chỉ nghe `match:tournament`; worker đánh tập chỉ nghe `match:scrimmage`. Số worker đánh tập là trần số ván đánh tập chạy cùng lúc. Một tiến trình nghe cả hai hàng đợi chỉ dùng cho môi trường dev. Job, callback, lease và attempt không đổi.
- `POST /scrimmages` kiểm tra theo thứ tự hiện có (đội, đối thủ, bot, hạn mức ngày), rồi: 503 `SCRIMMAGE_PAUSED` với `details.reason` và header `Retry-After` khi hệ thống tạm dừng nhận; 429 `SCRIMMAGE_LIMIT` với `details.active/active_limit` khi đội đã có `SCRIMMAGE_MAX_ACTIVE_PER_TEAM` (mặc định 2) trận do mình tạo ở trạng thái queued/running. Trận blocked không giữ chỗ. Yêu cầu bị từ chối không trừ hạn mức ngày.
- Lý do tạm dừng, xét theo thứ tự: `queue_paused` khi admin tạm dừng `match:scrimmage`; `tournament_load` khi số job `match:tournament` queued/running ≥ `SCRIMMAGE_PAUSE_TOURNAMENT_JOBS` (mặc định 1, 0 là tắt); `scrimmage_backlog` khi số job `match:scrimmage` queued (chưa worker nào nhận) ≥ `SCRIMMAGE_MAX_PENDING_GAMES` (mặc định 12). Ngưỡng tồn đọng là ngưỡng mềm: hai đội được nhận cùng lúc có thể vượt một chút.
- Trận đánh tập đã nhận trước khi tạm dừng không bị hủy, không tạo attempt mới, không chuyển sang worker giải và không trừ hạn mức lần nữa; ván đang chạy chạy hết, ván đang chờ vẫn chạy trên worker đánh tập. Muốn giữ cả ván chưa chạy, admin tạm dừng `match:scrimmage` như trước (ván đang chạy vẫn chạy hết, ván chờ được rút khỏi RQ và trả lại khi tiếp tục).
- `GET /scrimmages/quota` trả thêm `active`, `active_limit` và `admission {accepting, paused_reason}`; `GET/PUT /admin/queue` trả `scrimmage_admission` cùng dạng. `accepting=true` khi và chỉ khi `paused_reason=null`. P1 khóa nút tạo trận và giải thích lý do; P2 hiển thị trạng thái nhận trận.
- 1.3.0: 88 definitions, 66 operations, 141 fixture cases. Engine 1.0.0, job/callback schema_version=1, replay format=1 và dev-v1 không đổi.
