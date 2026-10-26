# Python kit 1.0.0

Engine `ottv2==1.0.0`, protocol `OTTV2 1`, luật **dev-v1 (phát triển)**. Cần Python 3.12+.

## Bắt đầu

Từ repo root:

```sh
python -m pip install -e engine
python -m ottv2 play starter-kits/python starter-kits/python --replay starter-kits/dist/python-match.json
python starter-kits/tools/package.py
```

Sửa `choose_move(board, side, remaining_ms)` trong `main.py`. `STRATEGY = "random"` chọn ngẫu nhiên với seed 1; đổi thành `"greedy"` để ưu tiên đích, ăn quân rồi tiến tới đích.

## API

- `Board.from_fen(fen)`, `board.fen()`: đọc và ghi bàn; `cells[0]` là a1.
- `board.pieces(side, kind=None)`: chỉ số ô có quân theo `BLUE`/`RED` và loại `B`/`P`/`K`.
- `board.legal_moves(side)`: các nước dạng `c3d4`.
- `board.apply(move, side)`: trả bàn mới, không sửa bàn cũ.
- `undo = board.push(move, side)` rồi `board.pop(undo)`: sửa và hoàn tác tại chỗ theo LIFO, dùng cho tìm kiếm.
- `ottv2.bot.debug(text)`: ghi dòng bắt đầu bằng `#` và flush; xem lại được trong replay.

`serve()` lo handshake và flush, chỉ gọi hàm chọn nước khi nhận `GO`. Không in gì khác ra stdout ngoài giao thức và debug.

## Nộp bài

ZIP phải chứa `main.py` **ngay tại gốc**, không chứa thư mục `python/`, venv, package engine hay file thực thi. `package.py` tạo sẵn hai ZIP random/greedy trong `starter-kits/dist/`. Image chạy bot đã cài sẵn `ottv2` và numpy; không tự `pip install` khi bot chạy.

## Ví dụ giao thức

```text
E: OTTV2 1
B: READY PythonStarter
E: INIT side=BLUE budget_ms=60000 init_ms=10000 max_turns=300
B: OK
E: STATE 9/pbkpbkpbk/kpbkpbkpb/9/9/9/BPKBPKBPK/KBPKBPKBP/9 BLUE 0 60000 60000
E: GO
B: MOVE c3d4
... các lượt tiếp theo ...
E: END LOSS GOAL
```

Luật đầy đủ: [contracts/rules.md](../../contracts/rules.md).
