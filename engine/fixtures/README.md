# Engine fixtures 1.0.0 / dev-v1

File sinh bằng `engine/scripts/generate_fixtures.py` (riêng `stress-report.json` sinh bằng `engine/scripts/stress.py`); không sửa JSON bằng tay. Sinh lại từ repo root sau khi cài `engine`:

```sh
python engine/scripts/generate_fixtures.py
python -m unittest discover -s engine/tests -v
python starter-kits/tests/check_kits.py
```

| File | Nội dung |
| --- | --- |
| `manifest.json` + `capture.json`, `goal.json`, `crash-zero-ply.json`, `timeout.json`, `illegal-move.json`, `move-limit.json` | Sáu replay do `run_game` thật xuất qua BotIO tất định, mỗi mục có `expected_final_fen` để viewer đối chiếu. Bàn thưa dùng để cô lập luật, không phải ván từ bot Docker |
| `positions.json` | 1.000 bàn tổng hợp (seed 20261016) kèm tập nước hợp lệ của BLUE/RED; engine, kit Python và kit C++ dùng chung để kiểm tra luật và undo. Không khẳng định mọi bàn đều đạt được trong thi đấu |
| `outcomes.json` | 600 ca kết thúc (GOAL, WIPEOUT, STALEMATE, MOVE_LIMIT) để web kiểm chéo bản luật TypeScript |
| `stress-report.json` | 10.000 seed, mỗi ván chạy hai lần và so toàn bộ chuỗi nước, kết quả, bàn cuối. Không phải benchmark đồng hồ hay chứng nhận cân bằng luật |
