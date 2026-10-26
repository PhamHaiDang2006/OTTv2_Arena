# web — Giao diện OTTv2 Arena

Một npm workspace (React 18, TypeScript, Vite) gồm cổng thí sinh **P1** (`/`), cổng quản trị **P2** (`/admin/`) và package `@ottv2/replay-viewer`. Hai bản build dùng chung session, API client, schema validator và UI. Contract 1.3.0, engine 1.0.0, luật `dev-v1`.

| Phần | Tài liệu |
| --- | --- |
| Cổng thí sinh | [p1-participant/README.md](p1-participant/README.md) |
| Cổng quản trị | [p2-admin/README.md](p2-admin/README.md) |
| Trình phát replay | [replay-viewer/README.md](replay-viewer/README.md) |

## Chạy

Cần Node.js 22+. Từ `web/`:

```sh
npm ci
npm run dev          # P1: http://127.0.0.1:5173/
npm run dev:admin    # P2, terminal thứ hai: http://127.0.0.1:5174/admin/
npm run typecheck
npm test
npm run build        # dist/p1 và dist/p2
npm run format:check
```

Vite proxy `/api` và `/ws` tới backend ở `127.0.0.1:8000`; chỉ chạy `npm run dev` chưa đủ để đăng ký hay đăng nhập. Chạy backend theo [backend/README.md](../backend/README.md) với `FRONTEND_ORIGINS=http://127.0.0.1:5173,http://127.0.0.1:5174`, và `COOKIE_SECURE=false` khi dev qua HTTP. Dùng nhất quán `localhost` hoặc `127.0.0.1` giữa URL và allowlist.

| Biến | Mặc định | Mục đích |
| --- | --- | --- |
| `API_PROXY_TARGET` | `http://127.0.0.1:8000` | Target HTTP của dev server, đặt trong shell trước `npm` |
| `WS_PROXY_TARGET` | `ws://127.0.0.1:8000` | Target WebSocket của dev server |
| `VITE_API_BASE_URL` | `/api/v1` | Base API nhúng lúc build |
| `VITE_WS_URL` | `/ws` cùng host, ws/wss theo HTTP/HTTPS | URL socket nếu khác host |

Không đặt secret trong biến `VITE_*`. Production dùng cùng origin qua Caddy.

### Chạy với mock

Từ repo root chạy `python contracts/mock_server.py --port 4010`, rồi trong `web/` đặt `API_PROXY_TARGET=http://127.0.0.1:4010` trước `npm run dev`. Mock trả fixture captain khi login, **stateless** và không có WebSocket, nên trạng thái "đang kết nối lại" là bình thường. Mock không cho đăng nhập admin; kiểm tra P2 bằng backend dev đã `seed-dev`.

## Image

Từ repo root:

```sh
docker build --target p1 -f web/Dockerfile -t ottv2-web-p1:local .
docker build --target p2 -f web/Dockerfile -t ottv2-web-p2:local .
```

Hai target phục vụ port 8080 bằng nginx không chạy root, chạy được với `read_only` + tmpfs `/tmp`. P1 fallback về `/index.html`, P2 về `/admin/index.html`; asset không tồn tại trả 404, `/api/` và `/ws` không bị SPA nuốt.

## Bố trí mã nguồn

| Route | File | Ghi chú |
| --- | --- | --- |
| `/` | `src/main.tsx` | Chọn chế độ, công khai. `main.tsx` cũng chứa routing, guard, layout và login dùng chung |
| `/casual`, `/casual/:id` | `src/casual.tsx`, `src/casual-engine.ts` | Chơi với máy, cần đăng nhập |
| `/special`, `/special/:id` | `src/special.tsx`, `src/special-engine.ts`, `src/circular-board.tsx` | Bản đồ đặc biệt, cần đăng nhập |
| `/rooms`, `/rooms/:id` | `src/rooms.tsx` | Phòng hai người qua backend ([hướng dẫn](../ROOM_QUICKSTART.md)) |
| `/practice` | `src/practice.tsx` | Tự luyện, công khai |
| `/arena`, `/submit`, `/submissions`, `/scrimmage`, `/standings`, `/bracket`, `/matches/:id`, `/games/:id`, `/docs` | `src/participant.tsx` | Arena |
| `/profile`, `/players/:id` | `src/profile.tsx` | Hồ sơ; `/players/:id` công khai |
| `/achievements` | `src/achievements.tsx`, `src/training-progress.ts` | Thành tích luyện tập |
| `/admin/*` | `src/admin.tsx` | P2 |

Dùng chung: `src/api.ts`, `src/live.ts`, `src/upload.ts` (HTTP, WebSocket, upload), `src/ui.tsx` (form có xác nhận, bảng, phân trang), `src/preferences.tsx` (sáng/tối, bộ bàn gỗ/nguyên bản), `shared/schema.ts` (validate bằng JSON Schema sinh trong `contracts/`). DTO lấy từ `contracts/generated/types.ts` và `contracts/client.ts`, không định nghĩa lại.

Lựa chọn giao diện lưu trong localStorage: `ottv2.theme`, `ottv2.sound`, `ottv2.board-skin`.

## Quy tắc tích hợp

- Access token chỉ nằm trong bộ nhớ; refresh cookie do backend quản lý. Các request đồng thời dùng chung một lần refresh; sau 401 chỉ thử lại một lần với cùng `Idempotency-Key`.
- Mutation không tự retry khi lỗi mạng: UI báo kết quả chưa xác định rồi tải lại dữ liệu. Đăng xuất hoặc đổi người dùng thì xóa query cache.
- Socket gửi token bằng frame xác thực, chờ `auth.ok` rồi mới đăng ký kênh, ping 25 giây, reconnect có backoff. Sự kiện chỉ làm mới cache, không tính kết quả.
- Guard admin chỉ phục vụ trải nghiệm; quyền cuối cùng nằm ở backend.
- Nộp ZIP: trình duyệt kiểm tra đuôi và giới hạn 1 MiB, backend kiểm tra đầy đủ.
- Replay tải qua URL ký sẵn, tự xin URL mới một lần khi storage trả 401/403. P1 không nhận stderr.
- Markdown không cho raw HTML; mã nguồn hiển thị dạng text, không dùng `dangerouslySetInnerHTML`.

## Chế độ chơi trên trình duyệt

Casual, bản đồ đặc biệt và thành tích chạy hoàn toàn ở client, không gọi API ván và không cần runner.

- **Casual**: luật lấy từ `@ottv2/replay-viewer/src/rules.ts`. Ba độ khó: Dễ (`random`), Trung bình (`greedy`: thắng ngay, ăn quân, tiến tới đích), Khó (`hard`: tìm kiếm hai ply). Lưu tối đa 50 ván ở `ottv2.casual.v1:<user_id>`; ghi trong Web Lock để các tab của cùng tài khoản không ghi đè nhau.
- **Thành tích**: bảy huy hiệu (đi đủ ô từng map, thắng từng độ khó, hoàn thành chín tổ hợp map × độ khó), tính lại từ nước đi đã lưu ở `ottv2.training.v1:<user>:...`. Chỉ ở trình duyệt hiện tại, không đồng bộ server.

Dữ liệu chỉ nằm trong trình duyệt; xóa dữ liệu trình duyệt là mất.

## Bản đồ đặc biệt — special-v1

Luật thử nghiệm, chưa phải chế độ thi đấu chính thức. Chọn **Hexagon** hoặc **Annulus** (map id `circular`).

- **Hexagon**: 91 ô axial `(q, r)` bán kính 5, đi một ô theo 6 hướng kề cạnh. Đích Xanh `(0,-5)`, Đỏ `(0,5)`.
- **Annulus**: 4 vòng × 24 ô hình quạt = 96 ô; `q` là sector 0..23, `r` là vòng 0..3 từ trong ra. Đi một ô theo vòng, theo bán kính hoặc chéo (8 hướng); sector 23 kề sector 0, không xuyên tâm. Đích Xanh `(0,3)`, Đỏ `(12,3)`.
- Mỗi phe 12 quân, 4 mỗi loại, xuất phát đối xứng qua tâm; Xanh đi trước. Búa ăn Kéo, Kéo ăn Bao, Bao ăn Búa; không đi vào đích đối phương.
- Thứ tự kết thúc: về đích, ăn hết quân, đối phương hết nước, 300 ply. Tiebreak: loại quân còn ít nhất, tổng quân, khoảng cách ngắn nhất trên đồ thị tới đích (bỏ qua quân cản), cuối cùng Đỏ thắng.

Ba độ khó giống Casual. Mỗi ván lưu ở `ottv2.special.v1:<user_id>:<game_id>`, đọc lại thì kiểm tra toàn bộ lịch sử. Map cũ `ring` (84 ô) chỉ còn để mở ván đã lưu. Ván đặc biệt không xuất ra Replay/FEN của Arena; muốn chơi online hoặc xuất replay phải định nghĩa hợp đồng mới. Phòng hai người dùng cùng luật cho Hexagon và Annulus ([contracts/rooms.md](../contracts/rooms.md)).

## Kiểm thử

`npm test` chạy toàn bộ test trong `tests/`, gồm kiểm chéo luật TypeScript với engine (1.000 thế trận, 600 ca kết thúc, 6 replay cố định). Để chạy thêm 100 ván thật:

```sh
python -m pip install -e engine      # từ repo root
python web/tests/generate_engine_replays.py
cd web && npm test
```

Generator ghi `tests/generated/engine-replays.json` (gitignored); thiếu file này thì test 100 ván được skip rõ ràng. CI luôn sinh trước khi test. Khi cập nhật contract, chạy lại toàn bộ test web và `node contracts/build.mjs --check`.

Kết quả kiểm tra thực tế và việc còn lại: [CHECKS.md](CHECKS.md), [UI_POLISH_CHECKS.md](UI_POLISH_CHECKS.md), [SPECIAL_CHECKS.md](SPECIAL_CHECKS.md), [REGISTRATION_CHECKS.md](REGISTRATION_CHECKS.md), [AUTH_DESIGN_CHECKS.md](AUTH_DESIGN_CHECKS.md). Ảnh minh họa trong `evidence/`.
