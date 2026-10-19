# starter-kits — Bộ khởi động cho thí sinh

## Các kit hiện có — 1.0.0

Đã triển khai [Python](python/README.md) và [C++20](cpp/README.md), mỗi kit có
random/greedy, giao thức tự flush, FEN, sinh nước, apply/undo và debug.
Kit dùng contract v1.0.0, protocol OTTV2 1, luật phát triển dev-v1.
Java/Node chưa triển khai/bật vì chưa có pipeline image được kiểm chứng.

Từ repo root:

```sh
python -m pip install -e engine
python -m pip install --target contracts/.deps -r contracts/requirements.txt
python engine/scripts/generate_fixtures.py
python starter-kits/tests/check_kits.py
python starter-kits/tests/play_kits.py
python starter-kits/tools/package.py
```

Hai script test nhận `--cxx /path/to/g++`. `check_kits.py` so 1.000 thế trận
cả hai màu và kiểm tra apply/undo; `play_kits.py` kiểm tra ZIP bằng runner,
compile C++ rồi chạy tám cặp Python/C++ với random/greedy và đổi màu.

`dist/` chứa bốn ZIP chỉ có source, tên file gốc đúng hợp đồng, cùng manifest
version/SHA-256. Sinh bằng `tools/package.py` (Python 3.12.14); không sửa ZIP
bằng tay. Kết quả này là artifact local, chưa publish link tải lên P1.

Local runner dùng chính `ottv2.run_game`, không có vòng lặp luật riêng:

```sh
python starter-kits/tools/local_runner.py starter-kits/python starter-kits/cpp --games 10 --replay starter-kits/dist/game.json
```

Compile C++ theo README con trước. Local runner chạy code với quyền người dùng,
chỉ dùng cho bot phát triển đáng tin cậy. Image Python trên runner cần cài sẵn
ottv2 1.0.0; xem `engine/Dockerfile.bot`. ZIP đã qua giải nén/build/play cục bộ,
nhưng chưa được upload qua backend và chạy trong Docker ở lượt triển khai này.

## Hợp đồng tích hợp và hướng dẫn cho AI

Đọc [AGENTS.md](../AGENTS.md), [hợp đồng tích hợp](../integration.md) mục 2, 5, 9 và README engine/runner. Phân công hiện hành: B sở hữu kit, A đối chiếu luật.

- **Nhận:** giao thức OTTV2 1, FEN, engine_version và fixture luật do A cung cấp.
- **Cung cấp:** ZIP chạy được nguyên trạng qua build worker, bot mẫu và local runner dùng public API engine.
- Python dùng cùng package ottv2; C++/Java/Node phải kiểm tra chéo với engine, không dựa vào bản luật AI tự nhớ.
- Dùng bảng tên file chính/lệnh build/run trong [behavior.md](../contracts/behavior.md), public engine API và fixture tại [contracts](../contracts/README.md); runner chọn image digest, kit không có quy ước đóng gói thứ hai.
- Bot đọc OTTV2 trước READY, INIT trước OK, chỉ trả MOVE khi GO; flush mỗi dòng. Log dùng # hoặc stderr, không lẫn vào MOVE.
- Dùng seed cố định cho bot random trong fixture; cùng thế trận trả cùng tập nước (so sánh sau sort, không phụ thuộc thứ tự container).
- Local runner tạo và thu hồi tiến trình, cung cấp BotIO cho run_game như runner Docker. Không sao chép vòng lặp hoặc cách tính giờ của engine.
- Version kit phải ghi engine_version và protocol version; cập nhật engine phải chạy lại kiểm thử chéo trước phát hành.

### Chạy độc lập và bàn giao

Khi tạo mỗi kit, README con phải có yêu cầu runtime/compiler, lệnh build/run chính xác, cấu trúc ZIP minh họa và một ví dụ giao thức hoàn chỉnh. Các lệnh local_runner trong kế hoạch hiện là giao diện dự kiến, chưa phải công cụ đã có.

Trước merge: apply/undo trở lại đúng FEN; 1.000 fixture thế trận khớp engine; đấu bot Python/C++ với nhau cục bộ; upload chính ZIP mẫu vào pipeline và nhận replay. Không đánh dấu Java/Node hoàn thành nếu chỉ chạy local mà chưa có image tương ứng. B bàn giao link/version kit cho D để hiển thị ở P1.


**Phụ trách:** B · **Dự phòng:** A

Bộ khởi động giúp thí sinh tập trung vào thuật toán thay vì tự viết bộ đọc giao thức. Mỗi ngôn ngữ có cùng một bộ chức năng, để đội nào chọn ngôn ngữ nào cũng không bị thiệt.

## Cấu trúc dự kiến

```
starter-kits/
├── python/
├── cpp/
├── java/
├── node/
└── tools/
    └── local-runner/   # Chạy 2 bot đấu nhau trên máy cá nhân (dùng gói engine)
```

## Mỗi bộ khởi động phải có

| Thành phần | Mô tả |
| --- | --- |
| Lớp giao thức | Đọc `INIT`, `STATE`, `GO`, `END`; ghi `READY`, `OK`, `MOVE`; tự flush sau mỗi dòng |
| Cấu trúc bàn cờ | Đọc FEN, truy vấn quân tại ô, liệt kê quân theo bên và loại |
| Sinh nước đi | Trả về toàn bộ nước hợp lệ, đúng y luật của engine |
| Áp và hoàn tác nước đi | Để thí sinh viết tìm kiếm minimax, alpha–beta, MCTS |
| Hàm gỡ lỗi | `debug("...")` in ra dòng bắt đầu bằng `#` |
| Bot ngẫu nhiên | Mốc thấp nhất |
| Bot tham lam | Ưu tiên ăn quân và tiến về ô mục tiêu, mốc để thí sinh so sánh |
| Hướng dẫn | Cách build, cách chạy cục bộ, cách đóng gói zip để nộp |

Thí sinh chỉ cần viết một hàm, ví dụ với Python:

```python
def chon_nuoc_di(ban_co, ms_con_lai):
    ...
    return nuoc_di
```

## Nhiệm vụ

### Ngày 5
- [ ] Bộ khởi động Python: dùng trực tiếp gói `ottv2` của engine
- [ ] Bộ khởi động C++: viết lại sinh nước đi, kiểm thử chéo với engine
- [ ] Bot ngẫu nhiên và bot tham lam cho cả hai ngôn ngữ
- [ ] `tools/local-runner`: `python -m local_runner bot_a/ bot_b/ --games 10`

### Ngày 6
- [ ] Java và Node nếu image đã sẵn
- [ ] **Kiểm thử chéo bắt buộc**: với 1.000 thế trận ngẫu nhiên, danh sách nước hợp lệ của mỗi bộ khởi động phải trùng khớp tuyệt đối với engine

### Ngày 8
- [ ] Đóng gói từng bộ thành zip, đặt link tải trên trang tài liệu của P1
- [ ] Ghi số phiên bản khớp với `engine_version`

## Tiêu chí hoàn thành

- Bot mẫu của mỗi ngôn ngữ build và chạy được trên hệ thống thật, không sửa gì.
- Kiểm thử chéo sinh nước đi đạt 100%.
- Một người chưa biết dự án, theo hướng dẫn, nộp được bot đầu tiên trong vòng 15 phút.
