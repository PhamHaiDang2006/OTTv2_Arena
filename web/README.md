# Web OTTv2 Arena

Implementation React 18 + TypeScript cho cổng thí sinh **P1**, cổng quản trị **P2** và package
`@ottv2/replay-viewer`. Hai bản build dùng chung session, API client, schema validator và UI.
Contract **1.3.0**, engine **1.0.0**, profile **dev-v1** chưa phải luật giải chính thức.

## Chạy

Hồ sơ: `/profile` chỉnh sửa và xem trước tên, bio, 6 avatar SVG, 4 khung, 5 màu;
`/players/:id` mở công khai. Các tên/avatar ở header P1 và phòng dẫn tới hồ sơ.
`src/profile.tsx` dùng Profile DTO sinh từ contracts, không sao chép schema;
`src/profile.css` hỗ trợ sáng/tối/mobile. Cần backend migration 0004 và contracts
mới cùng checkout trước khi dùng. Thống kê chỉ phòng hai người; xem
[profiles.md](../contracts/profiles.md) cho giới hạn lịch sử và quy tắc đếm.

### Bộ bàn và quân gỗ

Thanh trên có **Bàn & quân → Gỗ / Nguyên bản**. Mặc định Gỗ; lựa chọn lưu tại
`ottv2.board-skin`, độc lập nền sáng/tối, đồng bộ giữa các tab. `src/wood.css`
vẽ vân gỗ bằng CSS; Annulus dùng SVG pattern với ID riêng cho từng bàn.
Áp dụng cho Casual, Hexagon, Annulus, phòng hai người và replay trong P1/P2.
Quân giữ biểu tượng/hình dạng và viền xanh/đỏ; nước hợp lệ, nước cuối và focus
có màu riêng ưu tiên trên chất liệu gỗ. Không thêm dependency hay ảnh tải từ mạng.

Các file sở hữu: `src/preferences.tsx`, `src/main.tsx`, `src/wood.css`,
`src/circular-board.tsx`; viewer chỉ thêm class trình bày trong
`replay-viewer/src/index.tsx`. HTTP/WS contract 1.3.0 và viewer props không đổi,
không cần migration hoặc backend mới. Kiểm tra: `npm test`, `npm run build`,
`node contracts/build.mjs --check`, validator và 5 mock test đã qua.
Ảnh `evidence/wood-boards-light.png`, `wood-boards-dark.png` từ harness ba bàn
tạm đã gỡ; đã kiểm tra đổi bộ, lưu sau reload và đánh dấu nước đi.

Yêu cầu Node 22+, npm. Từ `web/`:

```sh
npm ci
npm run dev          # http://127.0.0.1:5173/
npm run dev:admin    # terminal thứ hai: http://127.0.0.1:5174/admin/
npm run typecheck
npm test
npm run build        # dist/p1 và dist/p2
npm run format:check
```

Vite proxy HTTP `/api` và WebSocket `/ws` tới backend `127.0.0.1:8000`. Khởi động backend
theo README backend, đặt `FRONTEND_ORIGINS=http://127.0.0.1:5173,http://127.0.0.1:5174`.
Chỉ khi phát triển qua HTTP local, đặt backend `COOKIE_SECURE=false`. Production dùng HTTPS
và giữ cookie Secure. Dùng nhất quán `localhost` hoặc `127.0.0.1` giữa URL và allowlist.

Biến môi trường:

| Biến | Mặc định | Mục đích |
| --- | --- | --- |
| `API_PROXY_TARGET` | `http://127.0.0.1:8000` | Target HTTP của dev server; đặt trong shell trước npm |
| `WS_PROXY_TARGET` | `ws://127.0.0.1:8000` | Target WebSocket dev |
| `VITE_API_BASE_URL` | `/api/v1` | Base API được nhúng lúc build |
| `VITE_WS_URL` | `/ws` trên cùng host, ws/wss theo HTTP/HTTPS | URL socket nếu khác host |

Không đặt secret trong biến `VITE_*`. Production nên dùng cùng origin qua Caddy.
Signed URL storage cần trình duyệt truy cập được và CORS cho phép origin frontend.
Font có fallback system; không phụ thuộc font mạng để sử dụng giao diện.

## Chạy với mock

Từ repo root, chạy `python contracts/mock_server.py --port 4010` bằng interpreter đã cài
requirements hợp đồng. Trong PowerShell ở `web/`:

```powershell
$env:API_PROXY_TARGET = 'http://127.0.0.1:4010'
npm run dev
```

Login mock trả fixture captain và cookie, dùng email hợp lệ và mật khẩu đủ độ dài schema.
Mock **stateless**, mutation không thay đổi danh sách và không có WS. Vì vậy trạng thái
“đang kết nối lại” là bình thường. Mock login không hỗ trợ chọn admin; kiểm tra P2 với backend
dev đã `seed-dev`, không thêm backdoor/token nhập tay vào UI.

## Bố trí mã nguồn

- `src/participant.tsx`: P1, trang trận/replay và các màn hình public.
- `src/admin.tsx`: P2, điều hành đội/giải/vòng/trận/queue, source/similarity/audit/thông báo.
- `src/main.tsx`: routing, guard, layout và login dùng chung. P2 basename `/admin`.
- `src/api.ts`, `src/live.ts`, `src/upload.ts`: token trong memory, coalesced refresh, HTTP/WS/upload.
- `src/ui.tsx`: form mutation có xác nhận, bảng TanStack Table, pagination, lỗi/loading.
- `shared/schema.ts`: validate bằng chính JSON Schema generated trong `contracts/`.
- `replay-viewer/src`: package viewer độc lập với router/session/API.
- `tests`: fixture compatibility, transport, mutation, WS và kiểm thử engine/viewer.

Không sao chép DTO: tất cả dùng `contracts/generated/types.ts` và `contracts/client.ts`.
Không đổi API/schema. Khi cập nhật contract, chạy lại toàn bộ test web và generator contract.

## Quy tắc tích hợp

- Access token chỉ lưu trong memory; refresh cookie do backend quản lý. Một refresh dùng chung
  cho các request đồng thời. Sau 401 replay tối đa một lần và giữ nguyên Idempotency-Key.
- Mutation không retry do lỗi mạng. UI báo kết quả chưa xác định và refetch dữ liệu.
  CSV trả HTTP 201 kèm errors vẫn được hiển thị là thất bại.
- Đăng xuất/đổi người dùng xóa query cache. Admin guard chỉ là UX, quyền cuối cùng nằm ở backend.
- Socket gửi token bằng auth frame, chờ auth.ok trước khi subscribe team, ping 25s.
  Reconnect có backoff và refetch HTTP; sự kiện chỉ invalidate cache, không tính kết quả.
- Nộp ZIP dùng XHR adapter cho tiến trình tải lên nhưng vẫn dùng client chung cho request.
  Trình duyệt kiểm tra ZIP/1 MiB; backend chịu trách nhiệm kiểm tra archive đầy đủ.
- P2 giữ các attempt cũ, đánh dấu current; reason và xác nhận trước mutation.
  Queue poll 5s khi trang hoạt động. Nguồn/stderr chỉ lấy qua API được phân quyền.
- Replay tải signed URL qua API, tự xin URL mới một lần nếu storage trả 401/403.
  Browser giải mã Content-Encoding; không giải nén gzip hai lần. Viewer không nhận stderr ở P1.
- Tất cả Markdown không cho raw HTML. Mã nguồn được tokenize rồi render thành React text,
  không thực thi và không dùng `dangerouslySetInnerHTML`.

## Kiểm thử chéo engine

Từ repo root, với Python có package engine:

```sh
python -m pip install -e engine
python web/tests/generate_engine_replays.py
cd web
npm test
```

Generator dùng public `ottv2` API để tạo 100 ván, lưu dữ liệu tạm vào
`tests/generated/engine-replays.json` (gitignored). Test so sánh FEN cuối viewer với engine.
Nếu chưa chạy generator, chỉ test 100 ván được skip rõ ràng; 6 replay cố định và 1000 FEN vẫn chạy.
CI luôn sinh 100 replay trước test. Đây không phải bộ fixture hợp đồng mới.

## Container / infra

Từ repo root:

```sh
docker build --target p1 -f web/Dockerfile -t ottv2-web-p1:local .
docker build --target p2 -f web/Dockerfile -t ottv2-web-p2:local .
```

Hai target phục vụ port 8080 bằng nginx không root, hỗ trợ `read_only` + tmpfs `/tmp`.
P1 fallback `/index.html`, P2 fallback `/admin/index.html`; asset không tồn tại trả 404.
`/api/` và `/ws` không bị SPA nuốt. Các biến `VPS1_P1_IMAGE`/`VPS1_P2_IMAGE` của infra trỏ
tới digest image sau quy trình publish riêng. Không sửa Caddy vì routing hiện có đã khớp.

Xem [CHECKS.md](CHECKS.md) cho kết quả kiểm thử thực tế và các bước nghiệm thu còn lại.

## Đăng ký người chơi

`src/identity.css` sở hữu giao diện auth và màu chế độ: auth xanh slate,
Tự luyện tím chàm (`practice-shell`), Arena hổ phách (`arena-shell`). Các thẻ
chọn chế độ dùng cùng bảng màu. Token sáng/tối áp dụng cho cả khung, form,
placeholder, autofill và thông báo lỗi; tránh thêm nền trắng cố định vào auth.
`auth-page.tsx` giữ nguyên API/quy tắc đăng ký và không cho tự đăng ký admin.

Nếu web báo không thực hiện được yêu cầu, kiểm tra API đã chạy: từ repo root dùng
`powershell -ExecutionPolicy Bypass -File .\infra\start-local-api.ps1` (Docker Desktop
phải mở). Script giữ tài khoản trong database dev bền; chỉ chạy `npm run dev` chưa đủ.

Mở cổng thí sinh → **Chưa có tài khoản? Đăng ký** → nhập tên đội, email, mật khẩu (ít nhất 8 ký tự), nhập lại mật khẩu → **Đăng ký và vào đấu trường**. Hệ thống đăng nhập luôn và tạo đội riêng. Sau khi nộp bot và build thành công, chọn bot đánh tập để thi đấu. Đội chưa được duyệt vẫn được đánh tập; giải chính thức cần admin duyệt. Không có đăng ký admin, xác minh email, quên mật khẩu hoặc mã mời gia nhập đội trong đợt này.

Yêu cầu backend + contracts 1.1.0 cùng checkout. Form dùng `register` trong client generated, không lưu mật khẩu/token vào localStorage. Nếu mất kết nối sau đăng ký, thử đăng nhập bằng tài khoản vừa nhập.

## Casual, Tự luyện, Arena — 1.3.0

Thiết kế Casual dùng `src/casual-design.css`, scope `.casual-shell`: nền trắng ngà/sage
hoặc xanh than, quân huy hiệu SVG, thẻ đối thủ, bàn thu nhỏ trong lịch sử và thanh
điều hướng ngang khi vào trận. `Crest`/`MiniBoard` ở `casual-presentation.tsx` là
thành phần trình bày; không thay luật hoặc schema. Ảnh kiểm tra nằm trong
`evidence/design-*.png`. Bộ đếm quân được dựng từ FEN hiện tại, kể cả lúc xem lại.

Giao diện Casual có quân SVG búa/bao/kéo, chuyển động nước đi, dấu nước cuối,
hiệu ứng ăn quân, trạng thái lượt và bảng kết quả với chơi lại/xem lại/về sảnh.
Lịch sử và cách chơi có thể thu gọn. Nút sáng/tối ở thanh trên và trang đăng nhập
lưu lựa chọn trong `ottv2.theme`; âm thanh mặc định tắt, bật bằng nút trong bàn cờ
và lưu trong `ottv2.sound`. Chế độ giảm chuyển động của hệ điều hành được tôn trọng.
Hiệu ứng chỉ trình bày: toàn bộ lượt người + máy được lưu trước khi chạy animation;
xem lại không sửa ván đã lưu. Chi tiết kiểm tra: [UI_POLISH_CHECKS.md](UI_POLISH_CHECKS.md).

Trang `/` công khai cho chọn ba chế độ. `/arena` là tổng quan Arena; `/submit`, `/submissions`, `/scrimmage`, `/standings`, `/matches/:id`, `/games/:id` và P2 không đổi.

- `/casual`, `/casual/:id` (cần đăng nhập): `src/casual-engine.ts` tạo ván, áp nước, chạy bot random/greedy và lưu localStorage theo user id (khóa `ottv2.casual.v1:<user_id>`, 50 ván). Luật lấy từ `@ottv2/replay-viewer/src/rules.ts`; không gọi API ván. Đi nước, đầu hàng và tạo ván đọc lại, kiểm tra rồi ghi trong Web Lock cùng tên khóa lưu trữ, nên các tab của một tài khoản lần lượt ghi; tab khác đã đổi ván thì nước đi bị từ chối và bàn được tải lại. Trình duyệt không có Web Locks thì ghi trực tiếp. Nếu trình duyệt không cho lưu, ván vẫn chơi được trong phiên.
- `/practice` (công khai): hướng dẫn `python -m ottv2 practice` và mở file replay cục bộ bằng FileReader, validate schema Replay rồi phát bằng ReplayViewer; không upload.
- `/scrimmage`: hiển thị số trận chưa xong của đội và lý do tạm dừng từ `scrimmageQuota`, khóa nút tạo trận khi không nhận. P2 Hàng đợi hiển thị `scrimmage_admission`.

Kiểm tra: `tests/rules.test.ts` (luật TS so với engine: 1000 thế cờ, 600 kết quả, 100 ván thật khi đã chạy `python web/tests/generate_engine_replays.py`), `tests/casual.test.tsx`, `tests/resources.test.tsx`.

Casual có ba độ khó: Dễ (`random`) chọn nước ngẫu nhiên; Trung bình (`greedy`)
ưu tiên thắng ngay, ăn quân rồi tiến đến đích; Khó (`hard`) tìm kiếm hai ply
(nước bot và nước đáp trả), chấm quân số, cân bằng loại quân và khoảng cách đến đích.
Khó xét mọi nước đáp trả, cắt nhánh khi không thể tốt hơn lựa chọn hiện có;
đây là bot chiến thuật ngắn hạn, không phải mức sức mạnh Elo được kiểm chứng.
Tất cả chạy trên client; không đổi HTTP/schema contract 1.3.0 hay cần merge backend.
Khóa lưu ván giữ nguyên: ván random/greedy cũ vẫn mở được, hard được lưu cùng định dạng;
chơi lại giữ nguyên độ khó và màu quân. Không sửa generated artifacts.
Kiểm thử trong `tests/casual.test.tsx` bao gồm chặn đích ở cả hai màu,
giới hạn nước, chọn độ khó trên UI và đọc lại ván cũ/mới mà không gọi mạng.

## Bản đồ đặc biệt — special-v1

Giao diện người chơi dùng `src/tabletop.css` (scope `tabletop-shell` trên toàn bộ giao diện P1, gồm Casual,
Special, Arena, Tự luyện): menu bàn cờ CSS/SVG, điều hướng ngang, bảng màu gỗ/kem/đồng sáng-tối,
map preview có chiều sâu, huy hiệu chọn bot, lịch sử Special thu gọn và khung kết quả.
Chỉ admin P2 không nhận scope này. Tên hiển thị map tròn là **Annulus**;
map id `circular`, khóa lưu và luật không đổi nên ván cũ vẫn tương thích.
Ảnh kiểm tra: `evidence/tabletop-menu-dark.png`, `tabletop-menu-light.png`,
`tabletop-annulus-dark.png`. Menu kiểm tra trên app thật; trận Special kiểm tra
bằng harness user fixture tạm đã gỡ. Viewport Annulus 390px không tràn ngang.
Không thêm dependency hoặc thay HTTP/WS contract 1.3.0.

Chế độ riêng `/special`, `/special/:id`, cần đăng nhập, nằm ngoài Casual và Arena.
Chọn Hexagon (91 ô axial q,r bán kính 5, 6 hướng kề cạnh) hoặc Annulus
(`circular`: 4 vòng × 24 ô hình quạt = 96 ô). Annulus dùng q=sector 0..23,
r=vòng 0..3 từ trong ra ngoài: đi một ô theo vòng, theo bán kính hoặc chéo (8 hướng).
Sector 23 và 0 kề nhau; không nối vòng trong với vòng ngoài, không xuyên tâm.
Mỗi phe 12 quân, 4 mỗi loại, vị trí xuất phát đối xứng qua tâm; Xanh đi trước.
Giữ búa ăn kéo, kéo ăn bao, bao ăn búa. Đích Hexagon: Xanh `(0,-5)`, Đỏ `(0,5)`;
đích Annulus: Xanh `(0,3)`, Đỏ `(12,3)`;
không đi vào đích đối phương. Thứ tự kết thúc: về đích, ăn hết quân, đối phương
hết nước đi, 300 ply. Tiebreak: loại quân ít nhất, tổng quân, khoảng cách ngắn nhất
trên đồ thị đến đích (bỏ qua quân cản), Đỏ nếu vẫn hòa. Không có King of the Hill.

Luật và dữ liệu local thuộc `src/special-engine.ts`; giao diện `src/special.tsx`
và `src/special.css`; `src/circular-board.tsx` vẽ các ô hình quạt bằng SVG.
Ba độ khó random/greedy/hard, hard xét hai ply.
Map id cũ `ring` (hex khoét 7 ô, 84 ô) chỉ để đọc/chơi tiếp ván đã lưu và rematch,
không còn trong lựa chọn tạo ván mới. Không tự chuyển lịch sử cũ sang hình học mới.
Lưu riêng từng ván trong `ottv2.special.v1:<user_id>:<game_id>`, version `special-v1`;
đọc lại kiểm tra toàn bộ lịch sử hợp lệ. Ghi dùng Web Lock và so sánh bản cũ để
không ghi đè ván tab khác. Không có Web Lock thì kiểm tra/ghi đồng bộ trong tab,
không bảo đảm loại trừ tuyệt đối giữa nhiều tab. Lỗi lưu được báo, không chuyển
trang hoặc cập nhật bàn như thể đã lưu thành công. Xem lại không sửa lịch sử;
chơi lại giữ map, màu và độ khó. Dữ liệu chỉ ở trình duyệt hiện tại, không đồng bộ.

HTTP/WS/Replay contract 1.3.0, engine Python, runner, starter kits và Arena không
thay đổi; không xuất ván đặc biệt thành Replay/FEN Arena. Không cần merge producer
backend mới. Nếu cần online hoặc export replay sau này phải định nghĩa hợp đồng
version mới riêng, không đưa tọa độ hex vào schema bàn 9×9 hiện tại.

Kiểm tra: `npm test` (bao gồm `tests/special.test.tsx`), `npm run build`.
Thử cân bằng với người chơi và đo hiệu năng bot Khó trên điện thoại yếu vẫn cần
thực hiện trước khi coi hai map là chế độ thi đấu chính thức.

## Thành tích luyện tập (local v1)

Trang `/achievements` cần đăng nhập, mở từ menu hoặc hồ sơ cá nhân. Bảy huy hiệu:
đi đủ 81/91/96 ô của Casual/Hexagon/Annulus; thắng ba độ khó trên từng map;
và hoàn thành cả chín tổ hợp map × độ khó. Chỉ tính ô đích nước của người chơi,
cộng dồn qua nhiều ván và cả hai màu; không tính nước bot, vị trí xuất phát,
ván phòng online hoặc Arena. Đầu hàng không được tính thắng. Map `ring` cũ không tính.

`src/training-progress.ts` lưu marker độc lập `ottv2.training.v1:<user>:<map>:visit:<cell>`
và `:win:<difficulty>` (giá trị `1`), tối đa 277 marker mỗi tài khoản.
Ghi idempotent theo từng ô/mốc để hai tab không ghi đè tiến độ nhau. Hai engine
thu thập sau khi lưu ván; trang thành tích cũng đọc lại lịch sử hợp lệ còn trên máy.
Tính lại kết quả từ nước đi, không tin trường winner đã cache; replay không ghi tiến độ.
Lỗi lưu thành tích không làm mất ván đã lưu, có thể thử lại khi mở trang thành tích.

Đây là thành tích cá nhân chưa xác minh, chỉ ở trình duyệt hiện tại, không đồng bộ
server hoặc hiển thị trên hồ sơ công khai. Xóa dữ liệu trình duyệt sẽ mất tiến độ;
không thể khôi phục lịch sử đã xóa. Không thay API/schema hay cần migration backend.
Giao diện ở `src/achievements.tsx` và `src/achievements.css`; liên kết ở `main.tsx`
và `profile.tsx`. Kiểm tra: `npm test` đạt 183 test, `npm run build` đạt cả P1/P2;
`node contracts/build.mjs --check`, validator và 5 mock test đều đạt.
