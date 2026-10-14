# Kế hoạch dự án OTTv2 Arena

> Phiên bản 1.0 · 4 người · 8 ngày làm việc · Tài liệu thiết kế gốc: "Hệ thống thi đấu lập trình OTTv2 — Tài liệu thiết kế"

## 1. Mục tiêu

Sau 8 ngày, hệ thống phải tổ chức được trọn vẹn một giải 20 đội, từ lúc đội nộp bot đến lúc công bố nhà vô địch, mà ban tổ chức không phải can thiệp tay vào kết quả.

Tiêu chí đo được:

| # | Tiêu chí | Ngưỡng đạt |
| --- | --- | --- |
| 1 | Thí sinh nộp bot và biết kết quả build | Dưới 60 giây với bot Python |
| 2 | Một trận đánh tập chạy xong và có replay | Dưới 3 phút kể từ khi bấm |
| 3 | Engine không có lỗi luật | 10.000 ván bot ngẫu nhiên không lỗi, khớp kết quả khi chạy lại |
| 4 | Đồng hồ cờ vua công bằng | Cùng một cặp bot chạy 100 lần, thời gian tiêu thụ lệch nhau dưới 2% |
| 5 | Sandbox an toàn | Bộ 10 bot phá hoại (fork bomb, mở mạng, ghi đĩa, đọc file hệ thống...) đều bị chặn |
| 6 | Cả giải chạy tự động | 108 ván của giải giả lập chạy xong trong dưới 90 phút, không trận nào phải sửa tay |

## 2. Phạm vi

### Làm trong 8 ngày

- Engine OTTv2 theo luật đã chốt, ghi replay, chạy lại được y hệt.
- Sandbox Docker cho **Python và C++** (bắt buộc), **Java và JavaScript** (nếu kịp ngày 6).
- P1: đăng nhập, quản lý đội, nộp bot, xem nhật ký build, đánh tập với đội chọn, xem replay, xem bảng đấu và nhánh.
- P2: quản lý đội, xem mã nguồn, rà trùng lặp mức cơ bản, bốc thăm, chạy vòng bảng, chạy vòng loại trực tiếp, chạy lại trận, sửa kết quả có lý do, nhật ký kiểm toán, thông báo.
- Bộ khởi động cho thí sinh và tài liệu luật chơi, giao thức.
- Triển khai trên 2 VPS, có sao lưu và giám sát cơ bản.

### Cắt so với tài liệu thiết kế gốc

| Hạng mục | Lý do cắt | Thay bằng |
| --- | --- | --- |
| Xếp hạng Elo cho sân đánh tập | Không ảnh hưởng thứ hạng giải | Bốc thăm hạt giống theo danh sách ban tổ chức nhập |
| Ghép đối thủ tự động | Phụ thuộc Elo | Thí sinh tự chọn đối thủ |
| Màn hình chiếu cho khán giả | Không cần để chạy giải | Chiếu trang nhánh đấu của P1 |
| Chấm điểm kỹ thuật theo phiếu | Chưa chốt có dùng không | P2 chỉ kiểm tra tính hợp lệ của code |
| Khiếu nại qua P1 | Ít dùng với 20 đội | Khiếu nại qua nhóm chat, xử lý bằng P2 |
| Nhiều thế trận ban đầu | Thêm công cân bằng | Một thế trận cố định, giữ sẵn trường `map_id` |

## 3. Nhóm và vai trò

| Người | Vai trò | Thư mục phụ trách | Dự phòng cho |
| --- | --- | --- | --- |
| **A** | Trưởng kỹ thuật, engine và replay | `engine/`, `web/replay-viewer/` | B |
| **B** | Sandbox và hạ tầng | `runner/`, `starter-kits/`, `infra/` | A |
| **C** | Backend và logic giải đấu | `backend/` | D |
| **D** | Giao diện P1 và P2 | `web/p1-participant/`, `web/p2-admin/` | C |

Người dự phòng duyệt Pull Request của người kia và phải đủ hiểu phần đó để sửa lỗi nếu người chính vắng mặt.

## 4. Các mốc

| Mốc | Cuối ngày | Điều kiện đạt | Ai xác nhận |
| --- | --- | --- | --- |
| **M1 – Chốt đặc tả** | 1 | Luật chơi, giao thức bot, định dạng replay, lược đồ DB, danh sách API được cả nhóm duyệt và đóng băng | A |
| **M2 – Thông luồng đầu cuối** | 4 | Một bot Python nộp qua P1, build xong, đấu với bot mẫu, replay xem được trên web | Cả nhóm |
| **M3 – Đủ chức năng** | 6 | Chạy được một giải giả lập 8 đội từ bốc thăm đến chung kết qua P2 | C |
| **M4 – Sẵn sàng thi** | 8 | Diễn tập 20 đội trên máy chủ thật đạt cả 6 tiêu chí ở mục 1 | A |

Không qua được M2 vào cuối ngày 4 là tín hiệu đỏ: ngày 5 cả nhóm dồn vào sửa luồng chính, hoãn mọi chức năng mới.

## 5. Kế hoạch theo ngày

| Ngày | A – Engine, replay | B – Sandbox, hạ tầng | C – Backend | D – Giao diện |
| --- | --- | --- | --- | --- |
| **1** | Chốt 8 điểm luật với ban tổ chức; viết đặc tả giao thức và định dạng replay; khung bàn cờ, đọc ghi FEN | Khởi tạo repo, CI; Docker Compose dev (PostgreSQL, Redis, MinIO); thuê và cấu hình 2 VPS | Lược đồ DB và migration đầu tiên; đăng nhập JWT; danh sách endpoint | Khung React + Vite; bố cục chung; trang đăng nhập; gọi API giả |
| **2** | Sinh nước đi hợp lệ, luật ăn quân, điều kiện thắng; unit test toàn bộ luật | Image bot Python; chạy một bot trong container và nói chuyện qua stdin/stdout | API đội, thành viên; tải mã nguồn lên MinIO; đẩy việc build vào hàng đợi | Trang chủ đội; trang nộp bài kéo thả |
| **3** | Vòng lặp ván đấu, đồng hồ cờ vua, xử lý lỗi bot, ghi replay; chạy 10.000 ván ngẫu nhiên kiểm tra cân bằng | Build worker: biên dịch, chạy thử, đẩy image vào registry, trả nhật ký | Bảng match, game; API đánh tập; nhận kết quả từ worker | Lịch sử nộp bài; nhật ký build trực tiếp qua WebSocket |
| **4** | Trình phát replay: bàn cờ, tua, đi từng nước | Match worker: ghép engine với 2 container bot, áp giới hạn tài nguyên, ghim CPU | Sự kiện WebSocket; API trận, ván, replay | Trang đánh tập; danh sách trận; nhúng trình phát replay — **M2** |
| **5** | Khung gỡ lỗi trong replay (dòng `#`, stderr), đồng hồ hai bên, lý do kết thúc | Bộ khởi động và image C++; bot mẫu ngẫu nhiên và tham lam | Bốc thăm có hạt giống; xếp lịch vòng bảng; tính bảng xếp hạng và tiêu chí phụ | P2: quản lý đội, danh sách bản nộp, xem mã nguồn |
| **6** | Kiểm thử biên của engine: hết giờ, nước sai, bot treo, chạm trần lượt | Image Java và JavaScript nếu kịp; benchmark độ lệch đồng hồ | Nhánh loại trực tiếp; chạy lại trận; sửa kết quả; nhật ký kiểm toán; đóng băng nộp bài | P2: điều hành giải, bảng hàng đợi, chạy lại trận — **M3** |
| **7** | Cùng B viết và chạy bộ 10 bot phá hoại; viết tài liệu luật và giao thức cho thí sinh | Gia cố sandbox; triển khai lên VPS thật; sao lưu, giám sát, cảnh báo | Giới hạn tần suất; rà trùng lặp mã; thông báo | P1: bảng đấu, nhánh đấu, thông báo; hoàn thiện giao diện |
| **8** | Diễn tập: tạo 20 đội giả, chạy trọn giải, sửa lỗi, phát hành bộ khởi động — **M4** | Diễn tập: theo dõi máy chủ, thử khôi phục từ bản sao lưu | Diễn tập: kiểm tra số liệu bảng xếp hạng và nhánh đấu | Diễn tập: kiểm thử trên điện thoại và trình duyệt khác |

## 6. Hợp đồng giữa các phần

Đây là những thứ phải chốt sớm vì người khác đang chờ. Trễ một mục ở đây kéo trễ cả người nhận.

| Hợp đồng | Người viết | Người dùng | Hạn chót |
| --- | --- | --- | --- |
| Giao thức bot (stdin/stdout) | A | B, thí sinh | Cuối ngày 1 |
| Định dạng tệp replay | A | B, C, D | Cuối ngày 1 |
| Lược đồ DB | C | B, D | Cuối ngày 1 |
| Danh sách API và kiểu dữ liệu trả về | C | D | Cuối ngày 1 |
| Định dạng việc trong hàng đợi (build job, match job) | C | B | Giữa ngày 2 |
| Kết quả worker trả về backend | B | C | Cuối ngày 2 |
| Sự kiện WebSocket | C | D | Cuối ngày 3 |

## 7. Rủi ro

| Rủi ro | Khả năng | Ảnh hưởng | Cách xử lý |
| --- | --- | --- | --- |
| Ban tổ chức chưa chốt luật trong ngày 1 | Trung bình | Cao | Dùng toàn bộ phương án đề xuất trong tài liệu thiết kế làm mặc định, chỉ đổi nếu có quyết định bằng văn bản |
| Sandbox tốn thời gian hơn dự kiến | Cao | Cao | A hỗ trợ B từ ngày 5; Java và JavaScript là phần đầu tiên bị cắt |
| Đồng hồ lệch quá 2% | Trung bình | Cao | Tăng ân hạn mỗi nước, giảm số trận song song từ 4 xuống 2 |
| D quá tải với cả P1 và P2 | Cao | Trung bình | P2 dùng thư viện bảng sẵn có, không tự thiết kế; C nhận phần P2 nếu cần |
| Thế trận ban đầu mất cân bằng | Thấp | Cao | Kiểm tra bằng 10.000 ván ngẫu nhiên ngày 3, tỷ lệ thắng của Xanh phải trong khoảng 48–52% |
| Một người nghỉ ốm | Thấp | Cao | Cơ chế người dự phòng ở mục 3 |

## 8. Định nghĩa "xong"

Một việc chỉ được tính là xong khi:

1. Code đã vào `main` qua Pull Request có người duyệt.
2. Có kiểm thử tự động cho phần logic (engine, tính điểm, phân quyền).
3. README của thư mục được cập nhật nếu cách chạy thay đổi.
4. Chạy được trên môi trường dev bằng Docker Compose, không chỉ trên máy người viết.

## 9. Việc cần ban tổ chức quyết định trong ngày 1

- [ ] Duyệt 8 điểm luật đề xuất: thế trận ban đầu, cấm tự sát, cấm vào ô mục tiêu đối phương, trần 300 lượt, tiêu chí phân định, 60 giây mỗi bên, nước sai xử thua.
- [ ] "Chấm code" chỉ là kiểm tra tính hợp lệ, hay có điểm kỹ thuật cộng vào thứ hạng.
- [ ] Danh sách hạt giống để bốc thăm.
- [ ] Ngày giờ đóng băng nộp bài cho từng vòng.
