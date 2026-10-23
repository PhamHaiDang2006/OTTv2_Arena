# Bàn giao Bản đồ đặc biệt

Kết quả ngày 2026-10-23 sau sửa Vành khuyên theo ảnh: `npm test` đạt 148/148; `npm run build` đạt typecheck và
hai bản build P1/P2. `node contracts/build.mjs --check`,
`backend/.venv/Scripts/python.exe contracts/validate.py` và
`backend/.venv/Scripts/python.exe contracts/test_mock.py` đều đạt (5 mock tests).
`git diff --check` đạt. Chưa chạy lại backend/runner suite vì không sửa các phần đó.

- Nguồn luật local: `special-v1` trong `src/special-engine.ts`, đặc tả ở README.
- UI: `src/special.tsx`, `src/special.css`; route và shell ở `main.tsx`, thẻ chế độ ở `casual.tsx`.
- `src/circular-board.tsx`: SVG 4 vòng đồng tâm × 24 ô hình quạt, map `circular`.
  Test kiểm tra nối sector 23↔0, 8 hướng, chặn mép trong/ngoài, ăn quân qua ranh giới,
  về đích, quân số đối xứng, ván đầy đủ và điều khiển bàn bằng bàn phím.
  Map `ring` cũ vẫn đọc được nhưng không còn trong sảnh tạo ván mới.
- Không thay API/WS/Replay contract 1.3.0, Casual engine, backend, runner, starter kits.
- Không cần producer mới hoặc bước migration DB. Ván đặc biệt lưu riêng theo account/game.
- Test: `tests/special.test.tsx` kiểm tra kết nối/đối xứng map, quân số, RPS, sáu hướng,
  lỗ giữa/biên, kết thúc, bot, ván hoàn chỉnh, dữ liệu hỏng, ghi stale, lựa chọn map,
  lưu/đọc, replay, đầu hàng và rematch. Bộ test Casual/Arena hiện có cũng chạy cùng.
- Kiểm tra trực quan bằng harness local tạm (đã gỡ): sảnh sáng/tối, Vành khuyên đi
  một lượt và bot đáp trả, viewport 390px (clientWidth/scrollWidth đều 375, không tràn ngang).
  Ảnh: `evidence/special-maps-light.png`, `evidence/special-ring-dark.png`.
- Hai ảnh trên ghi nhận phiên bản hex khoét giữa cũ. Ảnh hiện hành:
  `evidence/circular-board-dark.png`; đã kiểm tra một nước người và bot đáp trả
  trên bàn tròn mới qua harness tạm (đã gỡ). Chưa kiểm tra lại mobile của bàn tròn.
- Phiên browser không còn đăng nhập nên chưa kiểm tra lại luồng đăng nhập thật đến
  `/special`; test UI sử dụng user fixture. Không sửa xác thực để phục vụ preview.
- Còn mở: cân bằng map và hiệu năng bot Khó trên điện thoại yếu; chưa có multiplayer,
  đồng bộ đa thiết bị hoặc xuất Replay Arena cho chế độ này.
