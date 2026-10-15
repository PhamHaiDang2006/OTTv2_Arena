# Hướng dẫn cho AI làm việc trong OTTv2 Arena

## Đọc trước khi thực hiện

Đọc `README.md`, `architecture.md`, `integration.md`, `project_plan.md`, `contracts/README.md`, `contracts/behavior.md` và README folder đang sửa. Đọc schema/fixture của bên cung cấp/tiêu thụ giao diện liên quan. Các phiên AI không chia sẻ trí nhớ: chỉ coi nội dung đã lưu trong repository và yêu cầu hiện tại của người dùng là ngữ cảnh chung.

## Phạm vi và nguồn sự thật

- Phân công A/B/C/D trong `project_plan.md` là phân công hiện hành. Không tự đổi phân công theo suy đoán.
- `architecture.md` giữ kiến trúc; machine contract v1.0.0 trong `contracts/` và `contracts/behavior.md` cụ thể hóa wire format/hành vi. Các ví dụ kiến trúc rút gọn không thay schema. Nguồn sinh là `contracts/build.mjs`; không sửa generated artifacts bằng tay.
- README từng phần dẫn tới hợp đồng chung; không tạo bản sao schema khác tên trường.
- Chỉ sửa phần thuộc nhiệm vụ. Có thể sửa hợp đồng chung cần thiết cho nhiệm vụ nhưng phải chỉ ra các bên bị ảnh hưởng trong bàn giao/PR.
- Không truy cập DB của backend từ runner hoặc frontend; không import implementation nội bộ của folder khác. Dùng giao diện công khai đã chốt.
- Dùng profile phát triển `contracts/rules/dev-v1.json` theo `contracts/rules.md` để triển khai độc lập; không tự đoán luật/enum/endpoint khác. Profile chưa được ban tổ chức xác nhận, không dùng như luật chính thức. Thay luật cần profile/version/fixture mới.

## Phát triển và bàn giao

- Repository đã có nền tảng hợp đồng, mock và validator; chưa có engine/backend/worker/web sản phẩm. Chạy `node contracts/build.mjs --check`, `python contracts/validate.py`, `python contracts/test_mock.py`; cài dependencies theo contracts/README.md. Không tạo bộ hợp đồng riêng ở folder mình.
- Trước khi viết consumer, kiểm tra producer và phiên bản hợp đồng hiện có. Mock phải theo hợp đồng, không dùng mock làm nguồn định nghĩa API.
- Không sửa file sinh tự động bằng tay. Ghi phiên bản công cụ và lệnh tái sinh trong README sở hữu file đó.
- Tác giả tự giải quyết conflict phần mình, giữ thay đổi của người khác và chạy kiểm tra liên quan sau khi cập nhật từ `main`.
- Thay đổi hợp đồng phải có fixture hợp lệ, ca lỗi và kiểm tra cả producer lẫn consumer. Không tuyên bố tương thích khi chỉ chạy unit test riêng.
- Bàn giao nêu: file thay đổi; hợp đồng và phiên bản; lệnh đã chạy/kết quả thật; phần chưa chạy và lý do; phụ thuộc cần merge trước; điểm còn mở.
- Không tự push, merge hay liên hệ thành viên khác khi người dùng chỉ yêu cầu sửa local. Quy trình PR bên dưới là quy trình nhóm, không tự cấp quyền xuất bản.

## Quy trình nhóm

PR nhỏ theo một luồng hoặc một hợp đồng; CI đạt và có một người khác review. Review A ↔ B cho engine/runner/starter kits, C ↔ D cho backend/web; replay cần A và D đối chiếu. B điều phối môi trường tích hợp, mỗi chủ phần chịu lỗi phần mình. PR thay đổi ranh giới cần người phụ trách bên tiêu thụ review trước khi merge.
