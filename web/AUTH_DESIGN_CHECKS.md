# Auth và màu chế độ — 2026-10-23

## Thay đổi

- `src/auth-page.tsx`: thiết kế lại đăng nhập/đăng ký với artwork SVG, header
  chuyển sáng/tối, form và footer; giữ labels, validation, API và quyền admin.
- `src/identity.css`: bỏ phụ thuộc nền trắng cố định của `.login`; token auth
  cho khung/input/placeholder/autofill/error. Màu riêng Tự luyện tím chàm và
  Arena hổ phách ở cả sáng/tối, bao gồm sidebar và thẻ chọn chế độ.
- `src/main.tsx`: scope practice/arena/modes; `src/casual.tsx`: class thẻ Arena.
- README và ảnh `evidence/auth-*.png`, `practice-dark.png`, `arena-dark.png`.

Contract 1.3.0 không đổi; không đổi backend, schema, luật hay dependency.

## Kiểm tra

- `npm.cmd test`: 127/127 tests, gồm 4 test đăng ký (payload, mismatch,
  email trùng, không cho đăng ký admin).
- `npm.cmd run build`: TypeScript, build P1 và P2 đều đạt.
- `git diff --check`: đạt (có cảnh báo line endings).
- Trình duyệt: đăng nhập tối, chuyển đăng ký tối rồi sáng; form/placeholder,
  CTA và panel không còn vùng trắng thừa ở nền tối. Chuyển lại đăng nhập và
  theme hoạt động. Dùng hostname localhost riêng, không đăng xuất phiên 127.0.0.1.
- Xem trực tiếp trang Tự luyện và tổng quan Arena nền tối, sửa sidebar bị CSS
  cũ ưu tiên màu xanh; ảnh lưu sau sửa sidebar.
- Kiểm tra đăng ký ở viewport 390×844: clientWidth/scrollWidth đều 375 px;
  đã reset viewport. Chụp ảnh full-page mobile không thành công qua công cụ.

Chưa kiểm tra autofill bằng kho mật khẩu thực hoặc gửi đăng ký thật trong browser;
luồng gửi form được kiểm tra bằng tests. Không chạy lại backend vì không đổi API.
Thay đổi local, chưa commit/push.
