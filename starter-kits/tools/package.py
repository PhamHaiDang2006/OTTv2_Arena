"""Create deterministic source-only submission ZIPs; output is not published."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    out = ROOT / "starter-kits/dist"
    out.mkdir(exist_ok=True)
    manifest = []
    for language, files in {"python": ["main.py"], "cpp": ["main.cpp", "ottv2.hpp"]}.items():
        for strategy in ("random", "greedy"):
            path = out / f"ottv2-{language}-{strategy}-1.0.0.zip"
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name in files:
                    text = (ROOT / "starter-kits" / language / name).read_text()
                    if strategy == "greedy":
                        if name == "main.py":
                            text = text.replace('STRATEGY = "random"', 'STRATEGY = "greedy"')
                        elif name == "main.cpp":
                            text = text.replace("GREEDY = false", "GREEDY = true")
                    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, text)
            manifest.append({"language": language, "strategy": strategy, "file": path.name,
                             "engine_version": "1.0.0", "protocol_version": 1, "ruleset_id": "dev-v1",
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Created {len(manifest)} source ZIPs and manifest in {out}")


if __name__ == "__main__":
    main()
