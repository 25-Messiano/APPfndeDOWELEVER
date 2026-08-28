from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    linha = f"{datetime.now().isoformat(timespec='seconds')} | {msg}\n"
    with (LOG_DIR / "appfnde.log").open("a", encoding="utf-8") as f:
        f.write(linha)
