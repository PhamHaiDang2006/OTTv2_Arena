# Hồ sơ người chơi — mở rộng additive baseline 1.3.0

Producer C (backend), consumer D (web). Nguồn schema: `build.mjs`; tái sinh bằng
`node contracts/build.mjs`. Không thay User/Auth, luật, job, callback hoặc replay.

- `GET /profiles/me` (`myProfile`): tài khoản đăng nhập, kể cả chưa thuộc đội.
- `PUT /profiles/me` (`updateMyProfile`): bearer + Idempotency-Key; chỉ sửa chính mình.
  Gửi đủ display_name (1–40 ký tự, không toàn khoảng trắng), bio (0–240), avatar,
  frame, color. Enum cố định trong schema; không nhận URL ảnh, HTML hoặc thống kê.
  Tên không yêu cầu duy nhất; server trim tên/bio, từ chối control character trong tên.
- `GET /profiles/{user_id}` (`publicProfile`): công khai cho tài khoản đang hoạt động.
  Chỉ trả user_id, tên/giới thiệu/diện mạo và số liệu; tuyệt đối không trả email,
  role, team_id, credential. Chưa chỉnh hồ sơ: tên mặc định Người chơi + 8 ký tự UUID.

Các trường văn bản hiển thị bằng React text, không render HTML/Markdown.
Avatar là SVG có sẵn, không tải file bên ngoài. Bản này chưa có upload ảnh, achievement,
đường dẫn tùy chỉnh hoặc tìm kiếm danh sách người chơi.

## Thống kê

`stats`: played, wins, losses và by_map (standard/hexagon/circular, mỗi map cùng ba số).
Tỷ lệ thắng UI = wins/played × 100, làm tròn; chưa chơi hiển thị dấu gạch.
Nguồn duy nhất là bảng `room_results`, khóa (room_id, round), ghi cùng transaction
kết thúc ván. ON CONFLICT DO NOTHING ngăn cộng trùng khi retry, join lại hoặc đóng phòng.
Hai người đồng ý chơi lại đổi bên nhưng không xóa các kết quả trước. Rời phòng đang
chơi tính thua; đóng phòng chưa bắt đầu không tính. Không có hòa trong luật hiện tại.
Không cộng kết quả client Casual/Special, không cộng thành tích đội/bot Arena.

Migration 0004 sau 0003 tạo `player_profiles` và `room_results`; khôi phục vòng cuối
đang còn trong phòng finished/closed. Vòng cũ bị ghi đè trước migration không thể phục hồi;
phòng đang chơi được ghi khi kết thúc. Không suy đoán hoặc tạo số liệu cho các vòng đã mất.
Deploy migration + backend + contracts trước web. `python -m app.cli migrate` dùng DB
môi trường thật đã cấu hình; không reset DB. Không cần runner mới.
