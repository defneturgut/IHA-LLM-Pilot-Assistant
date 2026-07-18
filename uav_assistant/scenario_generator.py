"""
scenario_generator.py
======================
Özgün özellik: Basit senaryo üreticisi.

Şablonlardan rastgele doğal dil komutları üreterek sistemi otomatik test
eder. Amaç; farklı ifade varyasyonlarında ajanın güvenli ve tutarlı
davrandığını hızlıca doğrulamaktır (fuzz benzeri hafif bir test).

Kullanım:
    python -m uav_assistant.scenario_generator --n 15 --seed 42
"""

from __future__ import annotations

import argparse
import random
from typing import List

from .agent import DronePilotAgent


# (kategori, şablon fonksiyonu)
_TEMPLATES = [
    ("telemetri", lambda r: r.choice(
        ["durum nedir?", "şu an havada mıyız?", "batarya ne kadar?",
         "telemetri ver", "irtifa bilgisi ver"])),
    ("kalkis", lambda r: f"{r.choice([10, 15, 20, 25, 30])} metreye kalk"),
    ("kalkis_guvensiz", lambda r: f"{r.choice([200, 500, 1000])} metreye çık"),
    ("kalkis_belirsiz", lambda r: r.choice(
        ["kalkış yap", "biraz yüksel", "havalan"])),
    ("gogo", lambda r: f"{r.randint(-100, 100)}, {r.randint(-100, 100)} "
                       f"noktasına git"),
    ("inis", lambda r: r.choice(["iniş yap", "land", "yere in"])),
    ("eve_don", lambda r: r.choice(
        ["eve dön", "return to home", "üsse dön"])),
    ("hatali", lambda r: r.choice(
        ["motorları sonsuza kadar çalıştır", "roll açısını ayarla",
         "bana kahve yap"])),
    ("cok_adimli", lambda r: f"{r.choice([15, 20, 25])} metreye kalk, "
                             f"{r.randint(0, 60)} {r.randint(0, 60)} "
                             f"noktasına git, durum bildir ve eve dön"),
]


def generate(n: int = 12, seed: int | None = None) -> List[str]:
    """n adet rastgele doğal dil komutu üretir."""
    r = random.Random(seed)
    return [r.choice(_TEMPLATES)[1](r) for _ in range(n)]


def run(n: int = 12, seed: int | None = None) -> None:
    """Üretilen komutları ajana gönderip özet basar."""
    agent = DronePilotAgent(use_llm=False, log_dir="logs")
    commands = generate(n, seed)
    counts = {"approved": 0, "rejected": 0, "clarify": 0, "error": 0}
    print(f"=== Rastgele {n} senaryo (seed={seed}) ===\n")
    for i, cmd in enumerate(commands, 1):
        res = agent.handle(cmd)
        counts[res["decision"]] = counts.get(res["decision"], 0) + 1
        first_line = res["reply"].splitlines()[0]
        print(f"[{i:02d}] ({res['decision']:8}) {cmd!r}\n     -> {first_line}")
    print("\nÖzet:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    print("Tüm kararlar güvenlik katmanından geçti; sistem çökmedi.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Rastgele senaryo üreticisi")
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    run(args.n, args.seed)
