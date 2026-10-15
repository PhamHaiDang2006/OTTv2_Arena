# Nền tảng hợp đồng dùng chung — v1.0.0

Bốn AI triển khai cùng một phiên bản trong repository. Bộ này định nghĩa giao tiếp và cung cấp mock/fixture; chưa có backend, engine, sandbox hay giao diện sản phẩm. Profile luật `dev-v1` là đề xuất phát triển, **chưa được ban tổ chức xác nhận**. Có thể làm độc lập và chạy thử; không mở giải chính thức với profile này.

## Nguồn sự thật

| File | Vai trò |
| --- | --- |
| [build.mjs](build.mjs) | Nguồn định nghĩa DTO, operation, fixture và sinh artifact; chỉnh ở đây rồi tái sinh |
| [openapi.yaml](openapi.yaml) | OpenAPI 3.1 đầy đủ; dùng JSON syntax hợp lệ trong YAML 1.2 để tránh cần thêm parser khi sinh |
| [schemas/common.schema.json](schemas/common.schema.json) | JSON Schema 2020-12 của toàn bộ DTO; các schema nhỏ tham chiếu file này |
| [operations.json](operations.json) | Danh mục operationId → method/path → request/response fixture |
| [examples/manifest.json](examples/manifest.json) | Ca hợp lệ/không hợp lệ và schema tương ứng |
| [generated/types.ts](generated/types.ts), [generated/operations.ts](generated/operations.ts) | TypeScript wire types và typed operation map được sinh từ cùng nguồn |
| [client.ts](client.ts) | HTTP helper có type, hỗ trợ JSON/multipart; auth refresh do shared app quản lý |
| [engine_api.py](engine_api.py) | Kiểu Python công khai, Protocol BotIO và chữ ký engine phải thực hiện |
| [viewer-api.ts](viewer-api.ts) | Props, board và chữ ký hàm public viewer |
| [behavior.md](behavior.md) | Quyền, chuyển trạng thái, retry/lease/idempotency và quy tắc nghiệp vụ |
| [rules.md](rules.md), [rules/dev-v1.json](rules/dev-v1.json) | Luật tạm phát triển và cấu hình dùng chung |
| [fixtures/board-cases.json](fixtures/board-cases.json) | Fixture áp nước/FEN cho engine, kit và viewer; không phải test chứng nhận đầy đủ luật |
| [fixtures/draw-cases.json](fixtures/draw-cases.json) | Test vector bốc thăm có seed, đối chiếu giữa các ngôn ngữ |
| [mock_server.py](mock_server.py) | HTTP mock có kiểm tra request và role, trả response fixture cho mọi operation |

Schema và fixture phân biệt **cấu trúc** với **luật**. `replay-move_limit.json` là shape fixture cho UI kết thúc ván, không phải một ván hợp lệ 300 ply. Replay do engine thật xuất vẫn phải được kiểm thử chéo trước phát hành.

## Chạy từ repo root

Yêu cầu Node.js 22+ và Python 3.12. Dùng `python` là interpreter Python thực tế, không phải Windows Store alias. Không cần Docker/backend để chạy bộ hợp đồng.

```bash
python -m pip install --target contracts/.deps -r contracts/requirements.txt
npm ci --prefix contracts
node contracts/build.mjs
node contracts/build.mjs --check
npm run typecheck --prefix contracts
python contracts/validate.py
python contracts/test_mock.py
python contracts/mock_server.py --port 4010
```

`--check` không sửa file, trả lỗi nếu artifact sinh ra khác nguồn. `.deps` là thư viện cục bộ bị gitignore. CI chạy cùng lệnh, trừ server tương tác. Nếu dùng virtualenv, có thể cài requirements vào virtualenv thay vì --target.

Lockfile npm trong contracts chỉ quản lý TypeScript của công cụ hợp đồng; workspace web vẫn do D tạo và sở hữu lockfile riêng tại web.

Mock có `/api/v1/*`, `/openapi.json`, `/fixtures/replay.json`. D cấu hình dev proxy `/api/v1` tới `http://127.0.0.1:4010`; không nhúng URL mock trong production. Request dùng token `mock-member-token`, `mock-captain-token`, `mock-admin-token`, `mock-worker-token` theo role. Login trả cookie refresh và captain token; các token còn lại dùng trực tiếp để thử phân quyền.

- Mock **stateless**: POST không làm thay đổi GET, không thực hiện build/thi đấu/tính điểm/idempotency thật. Kết quả thành công chỉ là hình dạng response.
- Mock không kiểm chứng JWT, Origin/CSRF, membership tài nguyên, Redis lease hay chữ ký URL thật. Fixture từng operation là ví dụ cấu trúc độc lập, không phải database chung của một giải.
- Header `X-Mock-Status: 409` (hoặc mã lỗi được OpenAPI liệt kê) thử trạng thái lỗi UI. Header này chỉ dành cho mock, không thuộc production API.
- Mutation yêu cầu `Idempotency-Key` UUID. Callback yêu cầu `X-Worker-Lease` UUID; mock chỉ kiểm tra dạng, backend thật kiểm tra lease.
- Mock kiểm tra multipart ZIP cơ bản, không thay thế kiểm tra archive/sandbox. Không dùng với mã thí sinh thật.
- WebSocket dùng fixture client/server/event trong examples; mock HTTP không giả lập socket. Shared frontend transport cần nhận event fixture qua adapter để test reconnect/refetch; backend thật phải chạy kiểm tra socket trong checklist.

## Bốn người bắt đầu độc lập

| Người | Dùng ngay | Phần cần thực hiện |
| --- | --- | --- |
| A | engine_api.py, game-config/replay schema, rules/dev-v1, board fixtures, viewer-api.ts | Implement package ottv2 và viewer theo public interface; tạo replay thật để thay fixture cấu trúc trong test liên thông |
| B | build/match job, callback, engine interface, luật/profile, env mẫu và behavior | Build/worker/kit/infra; adapter BotIO giả trước rồi thay bằng pipe Docker; giữ DTO |
| C | OpenAPI, DTO, callback/WS, state machine, job fixtures | Backend + migration + enqueue adapter; kiểm tra response thật bằng schema; không tự sinh hợp đồng khác |
| D | Mock HTTP, generated TS, client helper, viewer props, event fixtures | P1/P2/shared web; dùng viewer stub đúng props đến khi A bàn giao |

Ví dụ prompt: “Đọc AGENTS.md và contracts/README.md, làm folder được giao theo contract v1.0.0 và dev-v1. Dùng fixture/mock cho phụ thuộc chưa có. Không sửa hợp đồng để hợp thức hóa implementation lệch. Chạy validator, kiểm thử phần mình và ghi việc chưa nối thật.”

## Thay đổi và nghiệm thu

Thay `build.mjs` → tái sinh → chạy validate/test → cập nhật behavior/rules khi thay nghĩa. Không sửa file generated, schema hoặc openapi bằng tay. Với schema đóng (`additionalProperties:false`), ngay cả thêm field tùy chọn cũng cần tái sinh/triển khai các consumer validator liên quan; không giả định tự tương thích. Tăng contract version khi thay wire contract; version trong mọi artifact phải khớp.

Schema không chứng minh được transaction, quyền trên từng tài nguyên, thời gian hay luật. Các ca bắt buộc của implementation được ghi trong [acceptance.md](acceptance.md). Mỗi PR nêu contract version/commit và kiểm tra thực sự đã chạy. Giữ phạm vi folder, trừ thay đổi hợp đồng có phối hợp producer/consumer.
