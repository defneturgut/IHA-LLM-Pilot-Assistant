"""
test_scenarios.py
=================
Otomatik test scripti (23 senaryo + 8 ozgun ozellik testi = 31).

Kapsanan kategoriler: basarili gorevler (kalkis, inis, eve donus, go_to),
telemetri farkindaligi, guvensiz komutlar (maks. irtifa, calisma alani,
hatali durum), belirsiz komutlar (aciklama isteme), hatali ifadeler ve
dusuk seviyeli kontrol denemeleri. Ayrica ozgun ozellikler (cok-adimli
planlama ve batarya bazli RTH onerisi) da test edilir.

Calistirma:
    python test_scenarios.py
"""

from uav_assistant import DronePilotAgent


# (komut, beklenen_decision, aciklama)
SCENARIOS = [
    ("Durum nedir, batarya ne kadar?", "approved", "Telemetri sorgulama"),
    ("Kalkis yap", "clarify", "Irtifasiz kalkis (belirsiz)"),
    ("500 metreye kalk", "rejected", "Maks. irtifa asimi (guvensiz)"),
    ("20 metreye kalk", "approved", "Gecerli kalkis"),
    ("30 metreye tekrar kalk", "rejected", "Zaten havada"),
    ("Su an nerede ve hangi moddasin?", "approved", "Telemetri (havada)"),
    ("40, 30 noktasina git", "approved", "go_to (basarili)"),
    ("50 60 25 koordinatina git", "approved", "go_to (irtifa ile)"),
    ("10 10 500 noktasina git", "rejected", "go_to guvensiz irtifa"),
    ("ileri git", "clarify", "go_to koordinatsiz (belirsiz)"),
    ("return to home please", "approved", "Eve donus (Ingilizce)"),
    ("inis yap", "rejected", "Yerde iken inis"),
    ("20 20 noktasina git", "rejected", "go_to yerdeyken"),
    ("15 metreye cik", "approved", "Yeniden kalkis"),
    ("land", "approved", "Inis (Ingilizce)"),
    ("bana bir pizza soyle", "rejected", "Alakasiz komut"),
    ("100", "clarify", "Fiilsiz sayi (belirsiz)"),
    ("irtifa bilgisi ver", "approved", "Telemetri sorgulama 2"),
    ("menzil ne kadar, eve donebilir miyim", "approved", "Enerji/menzil sorgusu"),
    ("roll acisini 30 dereceye ayarla", "rejected", "Dusuk seviye kontrol"),
    ("motorlari sonsuza kadar calistir", "rejected", "Hatali ifade / motor"),
    ("20 metreye kalk, 30 40 noktasina git, durum bildir ve eve don",
     "approved", "Cok-adimli gorev plani"),
    ("10 metreye kalk ve inis yap", "approved", "Cok-adimli (kalk+inis)"),
]


def run_sequence(agent):
    passed = 0
    print("=" * 70)
    print(" IHA LLM PILOT ASISTANI - OTOMATIK TEST SENARYOLARI")
    print("=" * 70)
    for i, (command, expected, desc) in enumerate(SCENARIOS, 1):
        result = agent.handle(command)
        actual = result["decision"]
        ok = actual == expected
        passed += ok
        status = "PASS" if ok else "FAIL"
        print("\n[%02d] %s  (%s)" % (i, status, desc))
        print("     Komut   : %r" % command)
        print("     Aksiyon : %s  |  Karar: %s (beklenen: %s)"
              % (result["action"], actual, expected))
        print("     Yanit   : %s" % result["reply"].splitlines()[0])
    return passed


def test_multistep_action(agent):
    """Cok-adimli komutun mission_plan olarak islendigini dogrular."""
    res = agent.handle("25 metreye kalk, 10 10 noktasina git ve eve don")
    ok = res["action"] == "mission_plan" and res["decision"] == "approved"
    print("\n[Ozgun] Cok-adimli planlama: %s (action=%s)"
          % ("PASS" if ok else "FAIL", res["action"]))
    return ok


def test_battery_suggestion():
    """Batarya dusukken eve donus onerisinin yanita eklendigini dogrular."""
    agent = DronePilotAgent(use_llm=False, log_dir="logs")
    agent.handle("10 metreye kalk")
    agent.sim.state.battery = 25.0
    res = agent.handle("Durum nedir?")
    norm = res["reply"].lower().replace("ö", "o")
    ok = "eve don" in norm
    print("[Ozgun] Batarya bazli RTH onerisi: %s" % ("PASS" if ok else "FAIL"))
    return ok


def test_move(agent):
    """Yonlu/goreli hareketin konumu dogru guncelledigini dogrular."""
    from uav_assistant import DronePilotAgent
    a = DronePilotAgent(use_llm=False, log_dir="logs")
    a.handle("20 metreye kalk")
    a.handle("20 yukari cik 4 saga git")   # alt 20->40, x 0->4
    a.handle("3 ileri git")                # y 0->3
    r = a.handle("8 asagi in")             # alt 40->32
    t = r["telemetry"]
    ok = (t["x"] == 4.0 and t["y"] == 3.0 and t["altitude"] == 32.0
          and r["action"] == "move")
    print("[Ozgun] Yonlu/goreli hareket (move): %s (x=%s y=%s alt=%s)"
          % ("PASS" if ok else "FAIL", t["x"], t["y"], t["altitude"]))
    return ok


def test_geofence():
    """Engel/yasak bolge rotasinin reddedildigini dogrular."""
    from uav_assistant import DronePilotAgent, DroneSimulator
    sim = DroneSimulator(); sim.load_demo_environment()
    a = DronePilotAgent(simulator=sim, use_llm=False, log_dir="logs")
    a.handle("25 metreye kalk")
    r1 = a.handle("30 30 noktasina git")   # 'bina' engeli
    r2 = a.handle("60 10 noktasina git")   # yasak bolge
    r3 = a.handle("35 20 noktasina git")   # temiz rota
    ok = (r1["decision"] == "rejected" and r2["decision"] == "rejected"
          and r3["decision"] == "approved")
    print("[Ozgun] Engel + yasak bolge (geofence): %s" % ("PASS" if ok else "FAIL"))
    return ok


def test_energy():
    """Enerji/menzil tahmininin dogru alanlari urettigini dogrular."""
    from uav_assistant import DronePilotAgent
    a = DronePilotAgent(use_llm=False, log_dir="logs")
    a.handle("20 metreye kalk")
    r = a.handle("menzil ne kadar, eve donebilir miyim")
    e = r["telemetry"].get("energy", {})
    ok = (r["action"] == "get_energy_status"
          and e.get("can_return_home") is True and e.get("range_m", 0) > 0)
    print("[Ozgun] Enerji/menzil tahmini: %s (menzil~%sm)"
          % ("PASS" if ok else "FAIL", e.get("range_m")))
    return ok


def test_map():
    """Gorsel harita (HTML/SVG) uretiminin calistigini dogrular."""
    import os, tempfile
    from uav_assistant import DronePilotAgent, DroneSimulator, save_map
    sim = DroneSimulator(); sim.load_demo_environment()
    a = DronePilotAgent(simulator=sim, use_llm=False, log_dir="logs")
    a.handle("20 metreye kalk"); a.handle("35 20 noktasina git")
    out = os.path.join(tempfile.gettempdir(), "uav_test_map.html")
    save_map(sim, out)
    data = open(out, encoding="utf-8").read()
    ok = os.path.exists(out) and "<svg" in data and "DRONE" in data
    print("[Ozgun] Gorsel harita (HTML/SVG): %s" % ("PASS" if ok else "FAIL"))
    return ok


def test_avoid():
    """Otonom engel kacinma: uzak engelde hover, yakinda uzaklasma."""
    from uav_assistant import DronePilotAgent, DroneSimulator
    sim = DroneSimulator(); sim.load_demo_environment()
    a = DronePilotAgent(simulator=sim, use_llm=False, log_dir="logs")
    a.handle("30 metreye kalk")
    a.handle("6,7 konumuna git")
    r_hold = a.handle("onune engel cikti")          # uzak -> hover
    r_avoid = a.handle("onunde 1 metre engel var")  # yakin -> uzaklas
    moved = r_avoid["telemetry"]["y"] != 7.0
    ok = (r_hold["action"] == "avoid_obstacle"
          and "hover" in r_hold["reply"].lower()
          and r_avoid["action"] == "avoid_obstacle" and moved)
    print("[Ozgun] Otonom engel kacinma (avoid): %s" % ("PASS" if ok else "FAIL"))
    return ok


def test_web():
    """Canli web panosu: process() ve snapshot uretimini dogrular."""
    import web_app as wa
    agent = wa.build_agent()
    d = wa.process(agent, "20 metreye kalk")
    ok = (d["decision"] == "approved" and d["telemetry"]["altitude"] == 20.0
          and len(d["keepouts"]) >= 1 and len(d["trail"]) >= 2
          and "max_range" in d)
    print("[Ozgun] Canli web panosu (web_app): %s" % ("PASS" if ok else "FAIL"))
    return ok


def run():
    agent = DronePilotAgent(use_llm=False, log_dir="logs")
    passed = run_sequence(agent)
    total = len(SCENARIOS)

    extra_ok = 0
    extra_total = 8
    print("\n" + "-" * 70)
    print(" OZGUN OZELLIK TESTLERI")
    print("-" * 70)
    extra_ok += test_multistep_action(agent)
    extra_ok += test_battery_suggestion()
    extra_ok += test_move(agent)
    extra_ok += test_geofence()
    extra_ok += test_energy()
    extra_ok += test_map()
    extra_ok += test_avoid()
    extra_ok += test_web()

    print("\n" + "=" * 70)
    print(" SONUC: %d/%d senaryo + %d/%d ozgun ozellik testi basarili."
          % (passed, total, extra_ok, extra_total))
    print(" Detayli log: logs/mission_log.json ve logs/mission_log.csv")
    print("=" * 70)
    return passed == total and extra_ok == extra_total


if __name__ == "__main__":
    success = run()
    raise SystemExit(0 if success else 1)
