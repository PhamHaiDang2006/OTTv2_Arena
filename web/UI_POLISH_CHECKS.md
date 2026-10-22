# Casual UI/QOL — 2026-10-22

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
