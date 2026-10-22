# Hợp đồng tích hợp cho bốn người làm bằng AI

Baseline hiện hành **contract v1.2.0** ngày 2026-10-22. Bộ artifact thực tế đã có trong [contracts/README.md](contracts/README.md): OpenAPI, JSON Schema, fixture, type Python/TypeScript, mock HTTP và validator. Engine/backend/worker/web đã có implementation; xem mục bàn giao Casual và README từng phần để chạy.

## 1. Nguồn sự thật

Đọc [AGENTS.md](AGENTS.md), [architecture.md](architecture.md), tài liệu này và README folder mình phụ trách. Với wire format, dùng [contracts/openapi.yaml](contracts/openapi.yaml), các schema trong contracts và [behavior.md](contracts/behavior.md), không suy schema từ bảng DB hoặc ví dụ rút gọn cũ.

| Giao diện | Artifact | Chủ trì / đối chiếu |
| --- | --- | --- |
| HTTP | OpenAPI, generated types/operations, client.ts | C / D |
| Build/match job và callback | schemas, examples, behavior mục worker | B + C / A |
| Engine Python API | engine_api.py, game-config/engine-result schema | A / B |
| Replay và viewer | replay schema, viewer-api.ts, board/replay fixtures | A / D |
| WS | websocket-client/server/event schema và fixture | C / D |
| Luật phát triển | rules.md, rules/dev-v1.json | A + C / cả nhóm |
| Môi trường | infra/.env.example, behavior, CI contracts | B / A,C,D |

Nguồn sinh machine contract là contracts/build.mjs. Sửa nguồn → tái sinh → kiểm tra → cập nhật consumer; không sửa file generated/OpenAPI/schema bằng tay. Schema đóng nên thêm field cũng phải đồng bộ các validator liên quan. Mỗi PR ghi version/commit hợp đồng, không chỉ ghi “đã đọc tài liệu”.

## 2. Quy ước dữ liệu

JSON snake_case; UUID string; timestamp UTC Z; duration integer ms; BLUE/RED; language python/cpp/java/node. Nullable khác trường vắng mặt. Key MinIO là object key, không phải URL. Replay result.plies bằng số nước hợp lệ trong moves. Callback result.plies ánh xạ DB total_plies; DB không phải DTO trả trực tiếp.

Job v1 có job_id; MatchJob có game_id, attempt, image references, players và config đầy đủ. map_id/engine_version/players ngoài config phải khớp bên trong. Config có ruleset_id và seed để A/B không tự chọn khác. Callback lỗi hạ tầng không có winner.

## 3. Backend ↔ frontend

Base /api/v1, WS /ws. OpenAPI đã đặc tả endpoint của P1/P2, gồm auth/me, opponents/quota, freeze/snapshot, source/logs, queue, announcements và thao tác giải. D dùng generated types/client hoặc generator tương đương từ chính OpenAPI, mock chạy trên localhost:4010.

Response tài nguyên trực tiếp; danh sách items/page/page_size/total; lỗi error.code/message/details + request_id. Auth/refresh/cookie/Origin và quyền tài nguyên theo behavior. Mutation bắt buộc Idempotency-Key ở operation đã khai báo; giữ nguyên key khi gửi lại cùng ý định, không tái dùng cho body khác.

WS có auth/subscribe/unsubscribe/ping, server ack/error/event. Token hết hạn/reconnect phải refetch HTTP; event không phải nguồn tính điểm. Mock HTTP không giả lập socket: C/D test transport bằng fixture trước khi nối socket thật. Không đưa dữ liệu private lên public.

## 4. Backend ↔ runner

Public RQ entrypoints: `ottv2_runner.jobs.build_submission(payload)` và `ottv2_runner.jobs.run_match(payload)`. C enqueue string import + dict, B thực hiện. Nhận job_id bất biến, claim lease theo behavior; callback cần token worker và X-Worker-Lease, ID trong URL/payload/job phải khớp.

Backend sở hữu state/attempt/outbox/dedup. Worker chỉ build/chạy/upload/báo kết quả. Retry callback không chạy lại bot; infra_error mới khiến backend tạo game_id/attempt/job mới, tối đa 3 retry sau lần đầu. Terminal receipt cho phép retry giống hệt sau giải phóng lease; payload khác bị 409. Không sửa kết quả hiện hành bằng callback attempt cũ.

Rerun/override bị khóa nếu downstream đã frozen hoặc giải finished. Khi còn cho phép, backend tính lại standings/bracket có audit, không sửa replay cũ. Chi tiết lease/fencing/staging/heartbeat trong behavior là bắt buộc khi có nhiều worker.

## 5. Engine ↔ runner/kit

A implement và public export run_game, GameConfig, GameResult, BotIO, BotProtocolError, InfrastructureError trong package ottv2 theo [engine_api.py](contracts/engine_api.py). Runner/local runner cung cấp pipe/process; engine không gọi Docker/HTTP/Redis/storage.

run_game async, nhận hai BotIO và GameConfig; runner ghi started_at_ns bằng monotonic clock cùng host; engine giữ deadline khởi động riêng. GameResult có replay object, lỗi bot là kết quả thi đấu, lỗi hạ tầng raise InfrastructureError. Invalid UTF-8/line overflow qua adapter là BotProtocolError để engine phân loại bot CRASH.

Python kit dùng package ottv2; kit khác kiểm tra cùng fixtures/ruleset. Tên file chính/lệnh build/run đã chốt trong behavior, không tự thêm Dockerfile hoặc build script do thí sinh cung cấp.

## 6. Replay ↔ viewer

Replay format 1 có ruleset_id dev-v1 trong baseline máy đọc được. Viewer nhận object đã tải/validate, không biết auth/router/storage. Package @ottv2/replay-viewer export ReplayViewer/parseFen/applyMove và Replay type; props trong viewer-api.ts.

Board 81 ô, a1=0, i1=8, a9=72; applyMove trả mảng mới. A/D dùng fixtures/board-cases.json và replay examples; replay shape-only không chứng nhận luật. A bổ sung replay xuất từ engine thật khi có implementation.

API replay trả url/expires_at; parent page tải JSON rồi truyền viewer. Storage gzip phục vụ application/json + Content-Encoding gzip; browser giải nén đúng một lần. Admin stderr phải được backend cấp quyền, không tải ở participant rồi giấu bằng UI.

## 7. Môi trường và package

Python 3.12. Mỗi package có pyproject; C sở hữu migration; B sở hữu Compose/CI. Web dùng npm workspace và một lockfile dưới web; D sở hữu shared API/auth/root scripts, A đối chiếu khi thêm viewer. Lockfile trong contracts chỉ cho công cụ hợp đồng, không phải workspace web thứ hai.

[infra/.env.example](infra/.env.example) đã có biến chuẩn và giá trị dev placeholder. Compose còn cần triển khai; hostname/port trong mẫu là mục tiêu phải giữ hoặc đổi có phối hợp. Proxy route /api/v1, /ws; P2 ở /admin, P1 ở /; chặn /api/v1/internal/* ngoài VPN. Không cấp DATABASE_URL/JWT_SECRET cho runner hoặc bí mật cho VITE_*.

## 8. Chạy và kiểm tra

```bash
python -m pip install --target contracts/.deps -r contracts/requirements.txt
node contracts/build.mjs --check
python contracts/validate.py
python contracts/test_mock.py
python contracts/mock_server.py --port 4010
```

Đọc contracts/README.md để dùng token mock, fixture, client và typecheck. Đây là kiểm tra nền tảng hợp đồng; test sản phẩm và smoke thật nằm ở [acceptance.md](contracts/acceptance.md). Không báo đã tích hợp thật chỉ vì mock pass.

## 9. Trạng thái quyết định từng còn mở

| Nhóm | Trạng thái |
| --- | --- |
| API-01 | Đã đặc tả endpoint/request/response trong OpenAPI; triển khai theo đó |
| OPS-01 | Đã chọn giới hạn upload/build/log, lease/retry/heartbeat trong behavior |
| TOUR-02 phần vận hành | Đã chốt state machine, rerun/override/downstream locking trong behavior |
| RULE-01..08, TOUR-01..02 phần luật | Có profile đề xuất dev-v1 để làm thử nhất quán; chưa phải quyết định ban tổ chức |

AI được dùng dev-v1 cho implementation/test phát triển, phải giữ nhãn development. Không tự tuyên bố luật chính thức hoặc bỏ khóa production tournament. Khi có luật thật, tạo profile/version mới, fixture và thay consumer cùng đợt. Việc chưa xác nhận luật chính thức không cản tạo API, UI, worker hoặc engine theo profile phát triển đã ghi rõ.

## Cập nhật đăng ký 1.1.0

Backend + web + contracts phải đi cùng nhau: POST /auth/register trả Auth + cookie, tạo đội pending có quyền đấu tập. Mock đã có operation/fixture. Không thay job/callback, engine hay replay. Tái sinh bằng node contracts/build.mjs; không cần migration.

## Bàn giao Casual 1.2.0 — 2026-10-22

A cung cấp public `ottv2.outcome` dùng chung quy tắc kết thúc; C sở hữu bảng/migration `0002`, 5 endpoint `/casual/games` và bot tích hợp; D sở hữu màn chọn chế độ, lobby và bàn cờ. Phân công A/B/C/D không đổi. B không cần sửa worker/job; image backend thêm engine từ local path theo uv.lock.

Merge contract/build + artifacts, public engine export, backend migration và web cùng nhau. Chạy `uv sync --project backend --frozen` rồi migrate trước khi khởi động API mới. HTTP contract 1.2.0 có 91 definitions, 71 operations, 149 fixtures; engine version 1.0.0, dev-v1, job/callback/replay không đổi. Arena URL chức năng cũ giữ nguyên, dashboard P1 chuyển `/` → `/arena`. Kiểm thử ở backend/tests/test_casual.py và web/tests/casual.test.tsx; cần chạy toàn bộ suite để đối chiếu producer/consumer.
