# engine — Trọng tài OTTv2

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

Hiện chưa có implementation/lệnh chạy đã xác nhận. PR đầu tiên phải thêm pyproject, entrypoint CLI và lệnh cài/chạy/test chính xác từ repo root. Khung dự kiến: cài editable package engine, chạy pytest trong engine, dùng CLI đấu hai bot mẫu; không ghi “đã chạy” trước khi thực sự có kết quả.

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
