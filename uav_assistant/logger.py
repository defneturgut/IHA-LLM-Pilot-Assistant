"""
logger.py
=========
Loglama Sistemi.

Her etkileşimi (gelen komut, yorumlanan görev/action, güvenlik kararı,
sonuç ve hata durumları) hem JSON hem de CSV dosyasına kaydeder. Bu, denetim
(audit) ve hata ayıklama için kritik bir güvenlik/izlenebilirlik bileşenidir.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List


class MissionLogger:
    """Uçuş görev günlüğünü JSON ve CSV olarak tutar."""

    CSV_FIELDS = [
        "timestamp",
        "user_command",
        "action",
        "args",
        "decision",       # approved / rejected / clarify / error
        "success",
        "message",
        "telemetry",
    ]

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.json_path = os.path.join(log_dir, "mission_log.json")
        self.csv_path = os.path.join(log_dir, "mission_log.csv")
        self.records: List[Dict[str, Any]] = []
        self._load_existing()

    def _load_existing(self) -> None:
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    self.records = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.records = []

    def log(
        self,
        user_command: str,
        action: str,
        args: Dict[str, Any] | None,
        decision: str,
        success: bool,
        message: str,
        telemetry: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Tek bir etkileşimi kaydeder ve kayıt sözlüğünü döndürür."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_command": user_command,
            "action": action,
            "args": args or {},
            "decision": decision,
            "success": success,
            "message": message,
            "telemetry": telemetry or {},
        }
        self.records.append(record)
        self._flush(record)
        return record

    def _flush(self, record: Dict[str, Any]) -> None:
        # JSON: tüm kayıtları yeniden yaz (küçük prototip için yeterli)
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(self.records, f, ensure_ascii=False, indent=2)

        # CSV: başlık yoksa yaz, sonra satırı ekle
        write_header = not os.path.exists(self.csv_path) or \
            os.path.getsize(self.csv_path) == 0
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_FIELDS)
            if write_header:
                writer.writeheader()
            row = dict(record)
            # Karmaşık alanları CSV için stringle
            row["args"] = json.dumps(record["args"], ensure_ascii=False)
            row["telemetry"] = json.dumps(record["telemetry"],
                                          ensure_ascii=False)
            writer.writerow(row)
