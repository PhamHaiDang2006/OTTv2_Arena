# contracts — Hợp đồng dùng chung v1.3.0

Định nghĩa giao tiếp giữa engine, runner, backend và web: OpenAPI, JSON Schema, fixture, kiểu TypeScript sinh tự động, mock HTTP và validator. Implementation nằm ở các thư mục khác; mọi phần dùng chung một phiên bản hợp đồng. Profile luật `dev-v1` chưa được ban tổ chức xác nhận, không dùng mở giải chính thức.

## File

| File | Vai trò |
| --- | --- |
| [build.mjs](build.mjs) | Nguồn duy nhất của DTO, operation và fixture; sửa ở đây rồi tái sinh |
| [openapi.yaml](openapi.yaml) | OpenAPI 3.1 (cú pháp JSON, hợp lệ YAML 1.2) |
| [schemas/](schemas/) | JSON Schema 2020-12 của mọi DTO |
| [operations.json](operations.json), [examples/](examples/manifest.json) | operationId → method/path → fixture; ca hợp lệ và không hợp lệ |
| [generated/](generated/) | `types.ts`, `operations.ts` cho TypeScript |
| [fixtures/](fixtures/) | `board-cases.json` (áp nước/FEN), `draw-cases.json` (test vector bốc thăm) |
| [client.ts](client.ts) | HTTP helper có type, hỗ trợ JSON và multipart |
| [engine_api.py](engine_api.py) | API Python mà engine phải export, Protocol `BotIO` |
| [viewer-api.ts](viewer-api.ts) | Props và hàm public của replay viewer |
| [behavior.md](behavior.md) | Quyền, chuyển trạng thái, lease, retry, idempotency |
| [acceptance.md](acceptance.md) | Kiểm thử bắt buộc ở từng ranh giới |
| [rules.md](rules.md), [rules/dev-v1.json](rules/dev-v1.json) | Luật phát triển dev-v1 và thuật toán bốc thăm |
| [rooms.md](rooms.md), [profiles.md](profiles.md) | Phòng hai người và hồ sơ người chơi |
| [mock_server.py](mock_server.py), [validate.py](validate.py), [test_mock.py](test_mock.py) | Mock HTTP, validator, test của mock |

`openapi.yaml`, `schemas/`, `operations.json`, `examples/`, `generated/`, `fixtures/` và `version.json` là file sinh, không sửa tay.

## Chạy

Từ repo root, cần Node.js 22+ và Python 3.12+. Không cần Docker hay backend.

```bash
python -m pip install --target contracts/.deps -r contracts/requirements.txt
npm ci --prefix contracts
node contracts/build.mjs            # tái sinh mọi artifact
node contracts/build.mjs --check    # chỉ kiểm tra lệch, không ghi file
npm run typecheck --prefix contracts
python contracts/validate.py
python contracts/test_mock.py
python contracts/mock_server.py --port 4010
```

`.deps` bị gitignore; nếu dùng virtualenv thì cài requirements vào đó thay cho `--target`. CI (`.github/workflows/contracts.yml`) chạy cùng chuỗi lệnh, trừ mock server. Lockfile npm ở đây chỉ phục vụ công cụ hợp đồng; web có lockfile riêng.

## Mock server

- Phục vụ `/api/v1/*`, `/openapi.json`, `/fixtures/replay.json`. Web dev proxy `/api/v1` tới `http://127.0.0.1:4010`.
- Token theo role: `mock-member-token`, `mock-captain-token`, `mock-admin-token`, `mock-worker-token`. Login trả cookie refresh và token captain.
- **Stateless**: POST không làm đổi GET, không build, thi đấu hay tính điểm thật. Không kiểm JWT, Origin/CSRF, membership hay lease thật.
- Header `X-Mock-Status: <mã>` để thử trạng thái lỗi; header này chỉ có ở mock.
- Mutation cần `Idempotency-Key` UUID, callback cần `X-Worker-Lease` UUID; mock chỉ kiểm dạng.
- Không giả lập WebSocket; dùng fixture event trong `examples/`.

Mock pass không chứng minh tích hợp được với backend thật.

## Đổi hợp đồng

1. Sửa `build.mjs`, chạy `node contracts/build.mjs`.
2. Chạy typecheck, `validate.py`, `test_mock.py`.
3. Cập nhật `behavior.md` hoặc `rules.md` nếu đổi nghĩa; thêm fixture hợp lệ và ca lỗi.
4. Đổi wire format thì tăng version: `info.version` của OpenAPI và `version.json` (cùng nằm trong `build.mjs`) phải khớp.
5. Ghi rõ producer và consumer bị ảnh hưởng.

`obj()` mặc định mọi field required và `additionalProperties: false`, nên thêm cả field tùy chọn cũng làm validator phía consumer từ chối payload: producer và consumer phải nâng cùng lúc. Schema không chứng minh được transaction, quyền theo từng tài nguyên, thời gian hay luật; các ca đó nằm trong [acceptance.md](acceptance.md). `examples/replay-move_limit.json` chỉ là fixture hình dạng cho UI, không phải ván 300 ply hợp lệ.
