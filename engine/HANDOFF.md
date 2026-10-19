# Bàn giao engine và starter kits — 2026-10-16

Contract **v1.0.0**, engine **1.0.0**, protocol **OTTV2 1**, profile **dev-v1**.
Không thay OpenAPI, schema, behavior hay generated artifacts trong contracts.
Luật chỉ dùng phát triển, chưa được ban tổ chức xác nhận.

## File và giao diện

- `engine/ottv2/`: public API, Board/FEN, luật, clock/protocol/game/replay,
  bot helper, local process adapter, CLI và adapter dict cho runner.
- `engine/pyproject.toml`: package cài được và entrypoint `ottv2`.
- `engine/tests/`, `scripts/`, `fixtures/`: kiểm thử và dữ liệu tái sinh.
- `starter-kits/python/`, `cpp/`: bot mẫu random/greedy và hướng dẫn riêng.
- `starter-kits/tools/`: đóng ZIP tất định và wrapper local runner.
- `starter-kits/tests/`: đối chiếu hai ngôn ngữ và đấu từ ZIP đã giải nén bằng runner.
- `runner/ottv2_runner/engine_verifier.py`: smoke game dùng engine thật và
  đối thủ random tin cậy, nhận interface verifier hiện hành.
- `runner/Dockerfile.engine`, `engine/Dockerfile.bot`: image worker có engine
  và Python bot base có ottv2/numpy. Chưa build Docker trong lượt này.
- `.github/workflows/engine-kits.yml`: CI engine/runner, coverage rules/clock,
  kiểm tra fixture, C++ cross-check và tám trận kit. Workflow chưa chạy trên GitHub.
- README engine, starter-kits và runner: lệnh cài, ghép adapter, giới hạn kiểm chứng.

Các thay đổi runner/infra sửa bốn lỗi review ở lượt trước vẫn giữ nguyên local;
không gộp chúng thành công việc của engine hoặc ghi đè thay đổi teammate.

## Lệnh và kết quả đã chạy

Máy kiểm tra: Windows, Python 3.12.14, g++ 16.1.0, coverage 7.10.7.
Đã dùng PYTHONPATH trỏ `engine;runner` khi chạy source trực tiếp.

| Lệnh từ repo root | Kết quả |
| --- | --- |
| `python -m unittest discover -s engine/tests -v` (qua coverage) | 18 test đạt: luật/clock, protocol lỗi, replay, runner adapter, smoke verifier, subprocess lỗi/treo/stderr và cleanup |
| `python -m coverage report --include='*/ottv2/rules.py,*/ottv2/clock.py' --fail-under=95` | rules.py 100%, clock.py 100%; board.py 95% trong báo cáo đầy đủ |
| `python -m unittest discover -s runner/tests -v` | 23 test đạt với engine hiện diện |
| `python engine/scripts/generate_fixtures.py` | 6 replay engine và 1.000 thế trận |
| `python starter-kits/tests/check_kits.py --cxx C:/msys64/mingw64/bin/g++.exe` | 1.000 bàn × hai màu: tập nước Python/C++ trùng, undo phục hồi FEN |
| `python starter-kits/tests/play_kits.py --cxx C:/msys64/mingw64/bin/g++.exe` | 8 trận từ ZIP mẫu, random/greedy, đổi màu; không CRASH/TIMEOUT/ILLEGAL_MOVE |
| `python engine/scripts/stress.py --games 10000` | 10.000 ván rule-level, mỗi seed chạy hai lần, cùng chuỗi nước/kết quả/bàn cuối |
| `python starter-kits/tools/package.py` | 4 ZIP source và manifest SHA-256 trong starter-kits/dist |
| `python -m pip wheel --no-deps --no-build-isolation --no-index ./engine -w engine/dist` | Build wheel ottv2-1.0.0 thành công |
| Cài wheel vào `engine/dist/installed`, chạy `python -m ottv2 play starter-kits/python starter-kits/python --games 2 --replay engine/dist/cli.json` | 2 trận CLI từ package đã đóng gói, đều kết thúc GOAL ở ply 240 |
| `node contracts/build.mjs --check` | Đạt, không thay generated artifacts |
| `python contracts/validate.py` | 85 định nghĩa, 65 operation, 133 ca hợp lệ/lỗi đạt |
| `python contracts/test_mock.py` | 5 test đạt |

Stress seed 0..9999: BLUE 4.875, RED 5.125; BLUE thắng 48,75%; 9.217 ván
MOVE_LIMIT, 783 GOAL. Hash chuỗi kết quả tại `fixtures/stress-report.json`.
Đây là tự đấu random ở mức luật, không phải 10.000 lần chạy Docker hoặc kiểm
chứng công bằng đồng hồ trên VPS. Tỷ lệ thắng không chứng nhận cân bằng luật.

## Ghép và phần còn mở

1. Image worker cần chứa engine này và runner hiện có. Đặt
   `OTTv2_ENGINE_FACTORY=ottv2.adapter:make_engine` và
   `OTTv2_BUILD_VERIFIER=ottv2_runner.engine_verifier:make_build_verifier`.
2. Python bot runtime cần ottv2 1.0.0 và numpy. Build `engine/Dockerfile.bot`
   từ repo root, publish rồi pin digest trong RUNNER_IMAGE_PYTHON. Không dùng
   lại image Python trần của thử nghiệm devkit cho Python kit mới.
3. B review Docker/CPU/clock adapter; C review callback thật; D/viewer dùng
   `engine/fixtures/manifest.json` cùng expected_final_fen. Backend vẫn sở hữu
   lease/finalize/retry; engine không tự gọi API hoặc thay trạng thái DB.
4. Docker Linux daemon trên máy hiện không chạy (`dockerDesktopLinuxEngine`
   không tồn tại), nên chưa build/run hai Dockerfile mới hoặc upload ZIP qua
   Redis/MinIO/backend thật. Cần diễn tập lại với Docker và backend khi sẵn sàng.
5. Java/Node là phần tùy chọn, chưa triển khai hoặc bật. Chưa publish ZIP lên
   web/P1, chưa triển khai viewer, chưa benchmark đồng hồ trên VPS.
6. Local runner chỉ dành cho bot đáng tin cậy, không phải sandbox. Các kiểm
   thử subprocess chỉ xác nhận cleanup/giới hạn đọc trên máy kiểm tra hiện tại.

Không có commit/push/merge tự động. Artifact `dist/` được gitignore và có thể
tái sinh bằng các lệnh trên; source, fixture và script được lưu để AI khác tiếp tục.
