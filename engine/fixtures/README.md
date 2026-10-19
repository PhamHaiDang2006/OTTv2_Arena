# Engine fixtures 1.0.0 / dev-v1

Nguồn sinh: `engine/scripts/generate_fixtures.py`; không sửa JSON bằng tay.
Sinh lại từ repo root sau khi cài `engine`:

```sh
python engine/scripts/generate_fixtures.py
python -m unittest discover -s engine/tests -v
python starter-kits/tests/check_kits.py
```

Đã sinh với Python 3.12.14. `manifest.json` trỏ tới sáu replay do `run_game`
thực sự xuất qua BotIO tất định: capture/WIPEOUT, GOAL, CRASH 0 ply, TIMEOUT,
ILLEGAL_MOVE, MOVE_LIMIT đủ 300 ply. Mỗi mục có `expected_final_fen` cho viewer.
Các bàn thưa dùng để cô lập luật; không phải ván từ bot Docker hay giải chính thức.

`positions.json`: 1.000 bàn sinh với seed 20261016, hai tập nước BLUE/RED.
Đây là bàn tổng hợp, không khẳng định mọi bàn có thể đạt được trong thi đấu.
Python kit, C++ kit và engine dùng chung dữ liệu này để kiểm tra luật và undo.

`stress-report.json` do `python engine/scripts/stress.py` sinh: 10.000 seed,
mỗi ván rule-level được chạy hai lần và so toàn bộ chuỗi nước/kết quả/bàn cuối.
Không phải benchmark đồng hồ hoặc chứng nhận cân bằng luật.
