"""
demo_mission.py
===============
Uçtan uca demo: engelli/yasak bölgeli bir ortamda çok-adımlı bir görev
çalıştırır, güvenlik kararlarını gösterir ve görsel haritayı üretir.

Çalıştırma:
    python demo_mission.py
Çıktı: mission_map.html (tarayıcıda açın)
"""

from uav_assistant import DronePilotAgent, DroneSimulator, save_map


def main():
    sim = DroneSimulator()
    sim.load_demo_environment()
    agent = DronePilotAgent(simulator=sim, use_llm=False, log_dir="logs")

    commands = [
        "25 metreye kalk",
        "30 30 noktasina git",       # engel 'bina' -> reddedilir
        "35 20 noktasina git",       # guvenli
        "10 ileri git",
        "menzil ne kadar, eve donebilir miyim",
        "-40 60 noktasina git",
        "eve don",
    ]
    print("=== DEMO GOREV (engel + yasak bolge + enerji) ===\n")
    for c in commands:
        r = agent.handle(c)
        tag = {"approved": "OK", "rejected": "RED",
               "clarify": "?", "error": "!"}.get(r["decision"], "-")
        print(f"[{tag}] {c}")
        print(f"     -> {r['reply'].splitlines()[0]}")

    out = save_map(sim, "mission_map.html", "İHA Demo Görev Haritası")
    print(f"\nGörsel harita kaydedildi: {out}")


if __name__ == "__main__":
    main()
