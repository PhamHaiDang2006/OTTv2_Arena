# Casual UI/QOL — 2026-10-22

## Sửa test CI chờ khóa — 2026-10-23

`tests/casual.test.tsx` dùng fake timers và React `act` trong test chờ Web Lock:
5 giây giả lập chưa được cấp khóa vẫn không đi quân; sau cấp khóa lưu 2 ply nhưng
bàn vẫn khóa trong animation; chạy hết timer mới cho tương tác. Tránh timeout
1 giây mặc định bị sát thời gian animation 560 + 280 ms trên CI. Cleanup luôn
khôi phục real timers. Không thay code game hoặc hợp đồng 1.3.0.

Xác minh local: `npm.cmd test` đạt 127/127 tests (11 files),
`npm.cmd run typecheck` đạt. Chưa chạy lại GitHub Actions; chưa commit/push.

## Thiết kế bổ sung — 2026-10-23

- `src/casual-design.css`: bảng màu Casual riêng, huy hiệu quân có chiều sâu,
  khung bàn, navigation ngang trong trận, thẻ bot và bố cục responsive.
- `casual-presentation.tsx`: Crest SVG (bot/người/mục tiêu/cúp), MiniBoard cho
  lịch sử; `casual.tsx`: chọn bot bằng thẻ, bộ đếm từng loại quân, sảnh mới.
- `main.tsx`: gắn scope Casual; `tests/casual.test.tsx`: kiểm tra thẻ chọn bot
  đồng bộ form và tạo đúng ván. README mô tả các thành phần.
- Kiểm tra cuối: 127 tests đạt, TypeScript và build P1/P2 đạt, diff --check đạt.
- Trình duyệt thật: chọn thẻ greedy, bắt đầu ván, d3→d4 + lượt bot, đổi sáng/tối,
  đầu hàng có xác nhận, bảng kết quả và quay về sảnh hoạt động.
- Điện thoại: viewport yêu cầu 390×844, clientWidth/scrollWidth cùng 375 px;
  ảnh `evidence/design-mobile.png`, không tràn ngang; đã reset viewport.
- Ảnh bàn giao: `evidence/design-lobby-dark.png`, `design-board-dark.png`,
  `design-board-light.png`, `design-result.png`.
- Không đổi hợp đồng 1.3.0, luật hay engine. Không cần dependency hoặc migration
  mới. Các thay đổi khôi phục branch có sẵn được giữ nguyên; chưa commit/push.
- Không chạy lại backend/runner cho phần thiết kế. Màn thắng vẫn được kiểm tra
  qua unit test; kiểm tra trình duyệt lần này dùng kết quả đầu hàng.

## Phạm vi

- `src/casual.tsx`: bàn cờ, trình bày lượt người/máy, bố cục, lịch sử, xem lại và chơi lại.
- `src/casual-presentation.tsx`: SVG quân, dựng lại lịch sử, dialog kết quả và pháo giấy thắng.
- `src/preferences.tsx`: sáng/tối, giảm chuyển động, âm thanh Web Audio tùy chọn.
- `src/game.css`: giao diện sáng/tối, animation và responsive.
- `src/main.tsx`, `src/auth-page.tsx`: tích hợp công tắc giao diện.
- `tests/game-polish.test.tsx`: sáu test hành vi mới.
- `README.md`, tài liệu này và `evidence/casual-{light,dark}.png`: bàn giao và ảnh kiểm tra.

Contract giữ 1.3.0; không đổi schema/API, luật hoặc engine. Theme tác động giao diện
web chung, các hiệu ứng bàn cờ và kết quả thuộc Casual. Không cần backend migration
hay dependency mới. Dựa trên Casual client engine và replay-viewer có sẵn trong checkout.

## Kết quả thực tế

- `npm.cmd test`: 11 file, 127 test đạt (Vitest 4.1.11).
- `npm.cmd run build`: typecheck và cả build người chơi/quản trị đạt (Vite 6.4.4).
- `git diff --check`: đạt, chỉ cảnh báo chuyển đổi line endings.
- Trình duyệt localhost: tạo ván mới, đi d3→d4, thấy trạng thái máy đang đi và
  kết thúc lượt với 2 nước; chuyển sáng/tối, reload giữ theme và ván.
- Đầu hàng có xác nhận, hiện lý do/số nước; xem lại mở thanh điều khiển;
  chơi lại tạo ID mới với bàn cờ khởi đầu.
- Kiểm tra breakpoint điện thoại (viewport yêu cầu 390×844): DOM clientWidth
  và scrollWidth đều 375 px, bàn 323.6 px; không tràn ngang. Đã reset viewport.
- Test tự động kiểm tra lưu nguyên tử trước animation, reduced motion, replay
  không sửa storage, giữ tùy chọn khi rematch, confetti thắng và âm move/capture khác nhau.

Chưa kiểm tra bằng tai chất lượng âm thanh trên thiết bị thật, chưa chơi đến thắng
trong kiểm tra trình duyệt; nhánh thắng và âm thanh đã có test tự động. Không chạy lại
backend/runner vì đợt UI này không sửa chúng. Các thay đổi infra/runner có sẵn được giữ nguyên.
