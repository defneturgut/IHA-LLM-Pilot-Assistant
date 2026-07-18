"""
main.py
=======
İnteraktif komut satırı arayüzü (REPL).

Kullanım:
    python main.py            # kural tabanlı (offline) mod
    python main.py --llm      # API anahtarı varsa gerçek LLM modu

Doğal dilde komut yazın (Türkçe/İngilizce). Harita: 'harita'. Çıkış: 'exit'.
"""

import argparse

from uav_assistant import DronePilotAgent, DroneSimulator, save_map


BANNER = """
=======================================================
   İHA (Drone) LLM Pilot Asistanı - Prototip v1.0
=======================================================
Örnek komutlar:
  - "durum nedir?"            (telemetri)
  - "20 metreye kalk"         (kalkış)
  - "iniş yap"                (iniş)
  - "eve dön"                 (return-to-home)
  - "200 metreye çık"         (güvensiz -> reddedilir)
  - "kalkış yap"              (belirsiz -> açıklama ister)
Harita: "harita"  |  Çıkış: exit
=======================================================
"""


def main():
    parser = argparse.ArgumentParser(description="İHA LLM Pilot Asistanı")
    parser.add_argument("--llm", action="store_true",
                        help="Gerçek LLM backend'ini dene (API anahtarı gerekir)")
    parser.add_argument("--no-env", action="store_true",
                        help="Demo engel/yasak bölge ortamını yükleme")
    args = parser.parse_args()

    sim = DroneSimulator()
    if not args.no_env:
        sim.load_demo_environment()
    agent = DronePilotAgent(simulator=sim, use_llm=args.llm)
    print(BANNER)
    print(f"[Aktif NLU modu: {agent.active_mode}]\n")

    while True:
        try:
            command = input("pilot> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGüle güle.")
            break
        if command.lower() in ("exit", "quit"):
            print("Güle güle.")
            break
        if command.lower() in ("harita", "map"):
            out = save_map(agent.sim, "mission_map.html")
            print(f"[HARİTA] Görsel harita kaydedildi: {out}\n")
            continue
        if not command:
            continue
        result = agent.handle(command)
        tag = {
            "approved": "✅ ONAY",
            "rejected": "⛔ RED",
            "clarify": "❓ AÇIKLAMA",
            "error": "⚠️ HATA",
        }.get(result["decision"], result["decision"])
        print(f"[{tag}] {result['reply']}\n")


if __name__ == "__main__":
    main()
