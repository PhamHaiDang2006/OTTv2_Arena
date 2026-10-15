# Profile phát triển dev-v1 — chưa phải luật chính thức

Đây là lựa chọn tạm rõ ràng để bốn implementation không suy diễn khác nhau khi làm thử. Không có xác nhận của ban tổ chức trong repository. Profile có ID và status riêng; khi có luật chính thức tạo profile mới cùng fixture, không âm thầm đổi nghĩa dev-v1.

| Điểm mở | Quy ước dev-v1 |
| --- | --- |
| RULE-01 | Mọi quân đi đúng 1 ô theo 8 hướng, không nhảy; không đứng yên; không đi ra bàn |
| RULE-02 | Xanh đi trước, đích Xanh i9, đích Đỏ a1; Xanh cấm vào a1, Đỏ cấm vào i9 |
| RULE-03 | Búa B ăn Kéo K, K ăn Bao P, P ăn B; quân cùng bên/cùng loại đối thủ hoặc quân khắc mình đều chặn. WIPEOUT là đối thủ hết toàn bộ quân. Sau nước hợp lệ: GOAL → WIPEOUT → STALEMATE (bên sắp đi không có nước) → MOVE_LIMIT |
| RULE-04 | max_turns=300 nghĩa tối đa 300 ply, một MOVE được chấp nhận là một ply. Không có nước thứ 301 |
| RULE-05 | MOVE_LIMIT so lần lượt min(số B,P,K) lớn hơn, tổng quân lớn hơn, khoảng cách Chebyshev nhỏ nhất của một quân đến đích nhỏ hơn; cuối cùng Đỏ thắng |
| RULE-06 | think_ms là thời gian đo thực, trừ ngân sách max(0,think_ms-50); chỉ timeout khi mức trừ lớn hơn ngân sách. Bằng ngân sách là được chấp nhận với clock 0; các lượt sau vẫn phải đáp trong grace. Hard timeout = remaining+1000ms |
| RULE-07 | Tên bot 1..64 ký tự UTF-8; dòng protocol <=4096 bytes bao gồm LF. Bỏ dòng rỗng, dòng # là debug. UTF-8 sai/dòng quá dài/sai handshake là CRASH; MOVE sai cú pháp hoặc không hợp lệ là ILLEGAL_MOVE; không trả lời đúng hạn TIMEOUT. Tổng debug lưu <=64KiB/bot/ván, cắt bớt nhưng đọc/discard trong deadline; stderr lưu <=1MiB/bot |
| RULE-08 | Init độc lập từng bot; một bot lỗi thì bên kia thắng nếu ready. Nếu cả hai lỗi thì dùng lỗi của Xanh làm reason và Đỏ thắng theo quy ước dev. Lỗi hệ thống/engine không biến thành bot thua |
| TOUR-01 | Bản 20 đội: 5 pot ×4 đội theo seed tăng dần (seed nhỏ mạnh hơn), mỗi bảng lấy 1 đội/pot. Dev 8 đội: 2 pot ×4. Dùng thuật toán và test vector ở dưới để chạy lại cùng kết quả |
| TOUR-02 | Bằng điểm: game_diff → games_won → điểm đối đầu trong nhóm đang bằng nhau → tổng ply của các ván thắng ít hơn → thứ tự xổ seed lưu audit. Nếu nhóm con còn bằng, không lặp lại đối đầu. Loại trực tiếp ván lẻ đầu A Xanh, ván chẵn B Xanh; ván quyết định cuối số tối đa bên seed mạnh hơn được Xanh (dev default) |

Ban đầu kiểm tra bàn/FEN hợp lệ trước chạy. Nếu bàn custom đã kết thúc, runner chỉ nhận map standard nên không xảy ra ở production; test rules riêng chỉ assert điều kiện được nêu, không gọi đầy đủ game trên bàn đã kết thúc nếu không có fixture tương ứng.

## Thuật toán bốc thăm phát triển

`xorshift32-fisher-yates-rejection-v1`: seed là uint32 khác 0, ghi audit trước bốc; mỗi lần lấy số thực hiện x ^= x << 13, x ^= x >>> 17, x ^= x << 5 với wrap 32 bit, trả uint32. Lấy số trong [0,bound): limit=floor(2^32/bound)*bound, bỏ số >=limit, trả số mod bound. Không dùng random mặc định của ngôn ngữ.

Danh sách đội phải có seed duy nhất 1..N (N=20 hoặc 8 trong dev). Chia danh sách tăng dần thành từng pot 4; Fisher–Yates i=3 xuống 1 với bounded(i+1), dùng một PRNG state liên tục qua mọi pot. Gán vị trí 0..3 sau shuffle vào A..D. Dùng [draw-cases.json](fixtures/draw-cases.json) để đối chiếu. Khi xổ thứ tự nhóm bằng điểm, sort team UUID tăng dần trước shuffle bằng cùng thuật toán và một seed khác được ghi audit.

Các fixture board là dữ liệu kiểm tra tọa độ/áp nước, có thể dùng bàn ít quân để cô lập trường hợp. Các replay `shape-only` chỉ phục vụ UI/schema, không dùng đánh giá luật hoặc cân bằng. A cần tạo bộ replay từ engine thật và 1.000 thế trận luật theo kế hoạch, kiểm thử chính thức sau khi luật được xác nhận.
