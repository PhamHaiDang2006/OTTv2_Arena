# engine — Trọng tài OTTv2

## Implementation 1.0.0 — dev-v1

Đã có package Python không phụ thuộc runtime bên ngoài: Board/FEN, sinh và áp
nước, undo, phân định thắng/thua, clock, protocol, replay, local process adapter
và CLI. Profile vẫn **chưa được ban tổ chức xác nhận**. Checklist thiết kế ở
cuối tài liệu là mục tiêu tổng thể, không phải chứng nhận nghiệm thu production.

Từ repo root (Python 3.12+):

```sh
python -m pip install -e engine -e runner
python -m pip install --target contracts/.deps -r contracts/requirements.txt
python -m unittest discover -s engine/tests -v
python -m unittest discover -s runner/tests -v
python -m ottv2 play starter-kits/python starter-kits/python --replay engine/dist/local.json
python engine/scripts/generate_fixtures.py
python starter-kits/tests/check_kits.py
python starter-kits/tests/play_kits.py
python engine/scripts/stress.py --games 10000
```

Các script C++ nhận `--cxx /path/to/g++`. Local runner chỉ dành cho bot phát
triển đáng tin cậy, không giới hạn quyền/mạng/RAM như Docker. CLI `--games N`
đổi màu sau mỗi ván. Hai đường dẫn bot có thể là folder, file `.py` hoặc binary.

Public exports `run_game`, `GameConfig`, `GameResult`, `BotIO`,
`BotProtocolError`, `InfrastructureError` thực hiện `contracts/engine_api.py`.
`Board` được dùng trực tiếp bởi kit Python: `apply` trả bản sao; `push/pop`
sửa tại chỗ và hoàn tác LIFO. Không dùng engine để gọi Docker/DB/storage.

### Ghép với runner

`OTTv2_ENGINE_FACTORY=ottv2.adapter:make_engine` chuyển dict cấu hình của runner
thành `GameConfig`. `OTTv2_BUILD_VERIFIER=ottv2_runner.engine_verifier:make_build_verifier`
chạy cả ván với đối thủ random tin cậy; bot thua bình thường vẫn build thành
công, lỗi CRASH/TIMEOUT/ILLEGAL_MOVE của bot nộp thì build thất bại.

```sh
docker build -f runner/Dockerfile.engine -t ottv2-worker:local .
docker build -f engine/Dockerfile.bot -t ottv2-python:local .
```

Build từ repo root. Khi triển khai, publish image rồi cấu hình digest bất biến
trong VPS2, không dùng digest Python trần vì kit cần `ottv2` cài sẵn. Dockerfile
worker cũ vẫn dành cho adapter tự cung cấp; bản `.engine` đóng gói engine này.
Runner/backend giữ nguyên hợp đồng v1.0.0; bên chịu ảnh hưởng là B (image/adapter),
C (callback) và D/viewer (fixture). Không cần thay schema hoặc thứ tự merge khác
ngoài runner hiện có và engine này phải cùng có mặt trong image tích hợp.

Wire GameConfig vẫn theo giá trị cố định trong schema; engine cho phép giảm
clock/max_turns qua API trực tiếp để test cục bộ, không gửi các override đó vào
job backend. Seed của bot mẫu cố định riêng; protocol v1 không có trường seed
gửi tới bot, nên config.seed không được tự ý chèn vào INIT.

### Kiểm chứng và fixture

`fixtures/manifest.json` có replay thật từ engine và bàn cuối để viewer đối
chiếu; `fixtures/positions.json` có 1.000 thế trận cho hai kit. Nguồn/lệnh tái
sinh tại `fixtures/README.md`. Công cụ đã dùng: Python 3.12.14, g++ 16.1.0.
Test tích hợp runner dùng engine thật với Docker/storage giả lập; test kit
chạy subprocess Python/C++ thật. Chưa chứng nhận Docker sandbox, upload backend
thật hay cân bằng giải đấu. Xem `HANDOFF.md` cho kết quả chạy và phần còn mở.

## Hợp đồng tích hợp và hướng dẫn cho AI

Đọc [AGENTS.md](../AGENTS.md), [hợp đồng tích hợp](../integration.md) mục 2, 5, 6, 9 và README của runner/starter-kits/replay-viewer trước khi triển khai.

- **Sở hữu:** package `ottv2`, luật, protocol, clock, kiểu dữ liệu public và replay. Không nhúng Docker, HTTP, Redis hoặc storage vào engine.
- **Nhận:** hai BotIO do runner/local runner tạo; GameConfig đã chốt. **Trả:** GameResult và replay JSON-compatible, không tự upload.
- Export `run_game`, `GameConfig`, `GameResult`, `BotIO` theo mục 5. Công bố exception hạ tầng; lỗi bot phải có lý do kết thúc xác định.
- Bàn cờ, tọa độ và thao tác áp nước phải có fixture dùng chung với starter kits và viewer; mô tả rõ mutation/undo và bên đi.
- Triển khai độc lập theo [engine_api.py](../contracts/engine_api.py), [GameConfig schema](../contracts/schemas/game-config.schema.json) và [dev-v1](../contracts/rules.md). RULE-01..08 có giả định phát triển thống nhất; không tự sửa hoặc gọi đó là luật chính thức.
- Schema replay và fixture cấu trúc đã có trong contracts. A bổ sung replay thật xuất từ engine: ăn quân, 0 nước, timeout, crash, illegal move, move limit; kèm expected_final_fen để B/D kiểm tra. Không tạo schema cạnh tranh.
- Không dùng ví dụ replay rút gọn trong architecture làm golden test; số ply và moves phải khớp.

### Chạy độc lập và bàn giao

Implementation và lệnh chạy hiện hành nằm ở đầu tài liệu; các mục ngày bên dưới
giữ lại kế hoạch gốc. Dùng unittest và các script kiểm chứng đã công bố.

Trước merge: round-trip FEN; ca đúng/sai cho luật đã chốt; đồng hồ giả tại biên deadline; EOF/timeout khác lỗi hạ tầng; run_game với BotIO giả; fixture đọc được ở kit/viewer. Khi tích hợp, chạy với adapter pipe của B. B review API Python/clock; D đối chiếu replay. PR ghi engine_version và commit fixture.


**Phụ trách:** A · **Dự phòng:** B · **Ngôn ngữ:** Python 3.12, không phụ thuộc thư viện ngoài

Engine là nguồn sự thật duy nhất về luật chơi. Nó giữ trạng thái thật của ván, gửi thế trận cho bot, đo đồng hồ, kiểm tra nước đi, quyết định thắng thua và ghi replay. Engine không bao giờ tin dữ liệu từ bot.

Cùng một gói Python này được dùng ở ba nơi: match worker trên VPS 2, build worker (ván chạy thử), và starter kit cho thí sinh chạy cục bộ.

## Cấu trúc dự kiến

```
engine/
├── ottv2/
│   ├── board.py       # Bàn cờ, quân, đọc ghi FEN
│   ├── rules.py       # Sinh nước đi hợp lệ, áp nước đi, kiểm tra kết thúc
│   ├── tiebreak.py    # Phân định khi chạm trần lượt
│   ├── protocol.py    # Đọc ghi các dòng giao thức
│   ├── clock.py       # Đồng hồ cờ vua
│   ├── game.py        # Vòng lặp một ván với hai kênh bot
│   ├── replay.py      # Ghi replay theo định dạng trong architecture.md
│   └── cli.py         # ottv2 play bot1 bot2 --replay out.json
└── tests/
```

## Nhiệm vụ

### Ngày 1
- [ ] Chốt 8 điểm luật với ban tổ chức (danh sách trong `project_plan.md`, mục 9)
- [ ] Viết đặc tả giao thức và định dạng replay vào `architecture.md`, cả nhóm duyệt
- [ ] `board.py`: biểu diễn bàn 9x9, chuyển đổi tọa độ `a1`–`i9`, đọc và ghi FEN

### Ngày 2
- [ ] `rules.py`: sinh nước đi 8 hướng, chặn quân cùng bên, chặn quân cùng loại đối phương, cấm tự sát, cấm vào ô mục tiêu đối phương
- [ ] Luật ăn: Búa ăn Kéo, Kéo ăn Bao, Bao ăn Búa
- [ ] Kiểm tra kết thúc theo đúng thứ tự: `GOAL`, `WIPEOUT`, `STALEMATE`
- [ ] Unit test cho từng luật, mỗi luật ít nhất một ca đúng và một ca sai

### Ngày 3
- [ ] `clock.py`: ngân sách khởi động 10 s, ngân sách ván 60 s, ân hạn 50 ms mỗi nước, giới hạn cứng
- [ ] `game.py`: vòng lặp ván, xử lý `TIMEOUT`, `ILLEGAL_MOVE`, `CRASH`, `MOVE_LIMIT`
- [ ] `tiebreak.py`: loại quân mỏng nhất → tổng quân → khoảng cách tới đích → Đỏ thắng
- [ ] `replay.py`: ghi replay, gồm cả dòng gỡ lỗi `#` của bot
- [ ] Chạy 10.000 ván bot ngẫu nhiên với bot ngẫu nhiên: không lỗi, chạy lại cho kết quả giống hệt, tỷ lệ thắng của Xanh nằm trong 48–52%

### Ngày 4–5
- [ ] Chuyển sang làm `web/replay-viewer/`
- [ ] Hỗ trợ B ghép engine vào match worker

### Ngày 6
- [ ] Kiểm thử biên: bot không gửi `READY`, gửi dòng rỗng, gửi nước sai định dạng, in 10 MB ra stdout, treo vĩnh viễn, thoát giữa ván
- [ ] Đóng phiên bản `1.0.0`, ghi vào `engine_version`

### Ngày 7
- [ ] Viết tài liệu luật chơi và giao thức cho thí sinh, kèm ví dụ minh họa từng luật

## Giao diện với phần khác

| Cung cấp cho | Thứ được cung cấp |
| --- | --- |
| `runner/` | Hàm `run_game(blue_io, red_io, config) -> GameResult` và tệp replay |
| `starter-kits/` | Gói `ottv2` để thí sinh chạy cục bộ |
| `web/replay-viewer/` | Định dạng replay và bộ ván mẫu để kiểm thử |

## Tiêu chí hoàn thành

- Độ phủ kiểm thử của `rules.py` và `clock.py` đạt 95%.
- 10.000 ván ngẫu nhiên không lỗi và tất định.
- `ottv2 play` chạy được hai bot mẫu trên máy cá nhân, không cần Docker.

### API công khai cho Casual

Từ tích hợp HTTP contract 1.2.0, package export thêm `outcome(board, mover, plies, max_turns=300)` ở `ottv2`. Trả `(winner, reason)` hoặc None, dùng sau mỗi nước hợp lệ; cùng hàm run_game dùng nên thứ tự kết thúc/tiebreak không khác Arena. Backend chỉ gọi API công khai này với Board và INITIAL_FEN, không import implementation nội bộ. Engine version 1.0.0, luật dev-v1 và clock/protocol Arena không đổi. Consumer chịu trách nhiệm lượt, auth và lưu trạng thái; hàm không kiểm tra lịch sử hoặc quyền người chơi.
