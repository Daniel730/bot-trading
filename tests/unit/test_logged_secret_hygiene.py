import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_local_recovery_log_does_not_expose_telegram_bot_token():
    log_path = ROOT / "logs" / "recovery_window.log"
    if not log_path.exists():
        return

    raw = log_path.read_bytes()
    encoding = "utf-16" if raw.count(b"\x00") > len(raw) // 4 else "utf-8"
    text = raw.decode(encoding, errors="ignore")
    compact_text = re.sub(r"\s+", "", text)

    offenders = []
    if re.search(r"api\.telegram\.org/bot\d{6,}", text):
        offenders.append("direct Telegram bot API URL")
    if re.search(r"bot\d{6,}:[A-Za-z0-9_-]{20,}", compact_text):
        offenders.append("wrapped Telegram bot token")

    assert offenders == [], (
        f"{log_path} still exposes Telegram credentials: " + ", ".join(offenders)
    )
