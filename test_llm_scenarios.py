"""
test_llm_scenarios.py
=====================
İNSANSAL (doğal dil) test seti + LLM/kural-tabanlı NLU ölçüm aracı.

Amaç
----
Asistanı GERÇEK bir pilotun konuşacağı gibi, günlük ve çeşitli ifadelerle
sınamak; böylece hem kural tabanlı parser'ı hem de bir LLM'i (Ollama/Anthropic/
OpenAI) AYNI sorularla ölçüp karşılaştırabilmek.

Her senaryonun bir "zorluk" etiketi vardır:
    * kolay : komutta tetikleyici anahtar kelime doğrudan geçer
              (kural tabanlı parser da çözebilir).
    * zor   : dolaylı / günlük / eş anlamlı ifade — anahtar kelime YOK.
              Kural tabanlı genelde ıskalar; iyi bir LLM anlamalıdır.
              => "zor" başarımı, LLM'in dil anlama katkısını ölçer.

Çalıştırma
----------
    python test_llm_scenarios.py                 # kural tabanlı NLU
    python test_llm_scenarios.py --llm           # gerçek LLM (varsa)
    python test_llm_scenarios.py --md sorular.md  # soruları Markdown'a dök
    python test_llm_scenarios.py --verbose       # her turu ayrıntılı yaz

LLM için ortam değişkenleri (opsiyonel):
    UAV_LLM_PROVIDER=ollama|anthropic|openai (auto)
    OLLAMA_HOST, ANTHROPIC_API_KEY, OPENAI_API_KEY, UAV_LLM_MODEL
"""

from __future__ import annotations

import argparse
from typing import Any, Dict, List, Optional

from uav_assistant import DronePilotAgent, DroneSimulator


# --------------------------------------------------------------------------- #
# Senaryo şeması:
#   id       : kısa kimlik
#   kat      : kategori (raporlama için)
#   zorluk   : "kolay" | "zor"
#   prep     : puanlanmadan önce sessizce çalıştırılacak hazırlık komutları
#   turns    : [ {"msg", "action"(set|None), "decision"(str|None), "not"} ]
#              action None ise yalnızca decision denetlenir.
# --------------------------------------------------------------------------- #
SCENARIOS: List[Dict[str, Any]] = [

    # ---- A. KALKIŞ --------------------------------------------------------- #
    {"id": "kalkis-1", "kat": "Kalkış", "zorluk": "kolay", "turns": [
        {"msg": "20 metreye kalk", "action": {"takeoff"}, "decision": "approved",
         "not": "Standart kalkış"}]},
    {"id": "kalkis-2", "kat": "Kalkış", "zorluk": "kolay", "turns": [
        {"msg": "kalk", "action": {"clarify"}, "decision": "clarify",
         "not": "İrtifasız kalkış -> irtifa sormalı"}]},
    {"id": "kalkis-3", "kat": "Kalkış", "zorluk": "zor", "turns": [
        {"msg": "hadi yerden 35 metre yükseğe çıkalım", "action": {"takeoff"},
         "decision": "approved", "not": "Dolaylı kalkış ifadesi"}]},
    {"id": "kalkis-4", "kat": "Kalkış", "zorluk": "zor", "turns": [
        {"msg": "15 metre irtifaya havalanır mısın", "action": {"takeoff"},
         "decision": "approved", "not": "Nazik/soru kipinde kalkış"}]},
    {"id": "kalkis-5", "kat": "Kalkış", "zorluk": "zor", "turns": [
        {"msg": "kalkışa hazırlan", "action": {"clarify"}, "decision": "clarify",
         "not": "Belirsiz kalkış -> soru"},
        {"msg": "yaklaşık 20 metre olsun", "action": {"takeoff"},
         "decision": "approved", "not": "Doğal cevap (çok-turlu hafıza)"}]},
    {"id": "kalkis-6", "kat": "Kalkış", "zorluk": "kolay", "turns": [
        {"msg": "500 metreye kalk", "action": {"takeoff"}, "decision": "rejected",
         "not": "Maks. irtifa aşımı -> güvenlik reddi"}]},

    # ---- B. İNİŞ / EVE DÖNÜŞ ---------------------------------------------- #
    {"id": "inis-1", "kat": "İniş/RTH", "zorluk": "kolay",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "iniş yap", "action": {"land"}, "decision": "approved",
         "not": "Standart iniş"}]},
    {"id": "inis-2", "kat": "İniş/RTH", "zorluk": "zor",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "bizi yavaşça yere indir", "action": {"land"},
         "decision": "approved", "not": "Dolaylı iniş"}]},
    {"id": "rth-1", "kat": "İniş/RTH", "zorluk": "kolay",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "eve dön", "action": {"return_to_home"}, "decision": "approved",
         "not": "Standart RTH"}]},
    {"id": "rth-2", "kat": "İniş/RTH", "zorluk": "zor",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "üsse geri dönelim artık", "action": {"return_to_home"},
         "decision": "approved", "not": "Günlük RTH ifadesi"}]},
    {"id": "rth-3", "kat": "İniş/RTH", "zorluk": "zor",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "bizi eve götür", "action": {"return_to_home"},
         "decision": "approved", "not": "Eş anlamlı RTH (LLM ayırt eder)"}]},

    # ---- C. KONUMA GİTME -------------------------------------------------- #
    {"id": "goto-1", "kat": "Konuma gitme", "zorluk": "kolay",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "40, 30 noktasına git", "action": {"go_to"},
         "decision": "approved", "not": "Standart go_to"}]},
    {"id": "goto-2", "kat": "Konuma gitme", "zorluk": "zor",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "şu 15 55 koordinatına uçalım", "action": {"go_to"},
         "decision": "approved", "not": "Dolaylı konum ifadesi"}]},
    {"id": "goto-3", "kat": "Konuma gitme", "zorluk": "zor",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "10 60 noktasına gidelim hadi", "action": {"go_to"},
         "decision": "approved", "not": "Anahtar kelimesiz konum (LLM)"}]},
    {"id": "goto-reroute", "kat": "Konuma gitme", "zorluk": "kolay",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "50, 70 noktasına git", "action": {"go_to"},
         "decision": "approved", "not": "Rota engelden geçer -> otonom dolaşma"}]},
    {"id": "goto-range", "kat": "Konuma gitme", "zorluk": "kolay",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "800, 200 noktasına git", "action": {"go_to"},
         "decision": "rejected", "not": "Çalışma alanı dışı -> reddet"}]},
    {"id": "goto-clarify", "kat": "Konuma gitme", "zorluk": "kolay",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "bir yere git", "action": {"clarify"}, "decision": "clarify",
         "not": "Koordinatsız -> konum sor"},
        {"msg": "30, 40", "action": {"go_to"}, "decision": "approved",
         "not": "Cevap: koordinat (çok-turlu hafıza)"}]},

    # ---- D. GÖRELİ HAREKET ------------------------------------------------ #
    {"id": "move-1", "kat": "Göreli hareket", "zorluk": "kolay",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "5 metre sağa git", "action": {"move"}, "decision": "approved",
         "not": "Standart move"}]},
    {"id": "move-2", "kat": "Göreli hareket", "zorluk": "zor",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "biraz ileri kay, 8 metre kadar", "action": {"move"},
         "decision": "approved", "not": "Günlük göreli hareket"}]},
    {"id": "move-clarify", "kat": "Göreli hareket", "zorluk": "kolay",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "sola git", "action": {"clarify"}, "decision": "clarify",
         "not": "Miktarsız yön -> miktar sor"},
        {"msg": "6", "action": {"move"}, "decision": "approved",
         "not": "Cevap: miktar (çok-turlu hafıza)"}]},

    # ---- E. ENERJİ / MENZİL ---------------------------------------------- #
    {"id": "enerji-1", "kat": "Enerji/menzil", "zorluk": "kolay", "turns": [
        {"msg": "menzil yeter mi", "action": {"get_energy_status"},
         "decision": "approved", "not": "Standart menzil sorgusu"}]},
    {"id": "enerji-2", "kat": "Enerji/menzil", "zorluk": "zor", "turns": [
        {"msg": "şarj bizi eve döndürmeye yeter mi sence", "action": None,
         "decision": "approved", "not": "Dolaylı enerji sorusu"}]},
    {"id": "enerji-3", "kat": "Enerji/menzil", "zorluk": "zor", "turns": [
        {"msg": "daha ne kadar havada kalabiliriz", "action":
         {"get_energy_status"}, "decision": "approved",
         "not": "Anahtar kelimesiz enerji (LLM)"}]},

    # ---- F. ENGEL / KAÇINMA ---------------------------------------------- #
    {"id": "avoid-1", "kat": "Engel/kaçınma", "zorluk": "kolay",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "önünde 5 metre engel var", "action": {"avoid_obstacle"},
         "decision": "approved", "not": "Standart engel bildirimi"}]},
    {"id": "avoid-2", "kat": "Engel/kaçınma", "zorluk": "zor",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "dikkat, karşıdan bir şeye çarpacağız!", "action":
         {"avoid_obstacle"}, "decision": "approved",
         "not": "Panik/günlük engel ifadesi"}]},

    # ---- G. YÜK / DESTEK BIRAKMA ----------------------------------------- #
    {"id": "drop-1", "kat": "Yük bırakma", "zorluk": "kolay",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "40, 20 noktasına destek bırak", "action": {"drop_payload"},
         "decision": "approved", "not": "Koordinata destek bırakma"}]},
    {"id": "drop-2", "kat": "Yük bırakma", "zorluk": "zor",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "şu 30 -20 koordinatına erzağı indir", "action":
         {"drop_payload"}, "decision": "approved", "not": "Dolaylı bırakma"}]},
    {"id": "drop-3", "kat": "Yük bırakma", "zorluk": "zor",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "kargoyu 25, 15'e teslim et", "action": {"drop_payload"},
         "decision": "approved", "not": "Teslimat ifadesi (LLM)"}]},
    {"id": "drop-empty", "kat": "Yük bırakma", "zorluk": "kolay",
     "prep": ["20 metreye kalk", "destek bırak", "destek bırak",
              "destek bırak"], "turns": [
        {"msg": "bir destek paketi daha bırak", "action": {"drop_payload"},
         "decision": "rejected", "not": "Depo boş -> reddet"}]},

    # ---- H. YARDIM GÖREVİ (çok-turlu, özgün) ----------------------------- #
    {"id": "yardim-1", "kat": "Yardım görevi", "zorluk": "kolay", "turns": [
        {"msg": "-50, 60 noktası yardım bekliyor", "action": {"clarify"},
         "decision": "clarify", "not": "Yerde -> irtifa sorar"},
        {"msg": "25 metre", "action": {"help_mission"}, "decision": "approved",
         "not": "Kalk + git + yardım paketi (gerekirse dolaş)"}]},
    {"id": "yardim-2", "kat": "Yardım görevi", "zorluk": "zor", "turns": [
        {"msg": "acil durum! 40, -35'te yaralı var, hemen ulaşmamız lazım",
         "action": {"clarify"}, "decision": "clarify", "not": "Acil çağrı"},
        {"msg": "30 metreden gidelim", "action": {"help_mission"},
         "decision": "approved", "not": "Doğal irtifa cevabı"}]},

    # ---- I. ÇOK-ADIMLI GÖREV --------------------------------------------- #
    {"id": "plan-1", "kat": "Çok-adımlı", "zorluk": "kolay", "turns": [
        {"msg": "20 metre kalk ve 40 30 noktasına git", "action":
         {"mission_plan"}, "decision": "approved", "not": "'ve' ile plan"}]},
    {"id": "plan-2", "kat": "Çok-adımlı", "zorluk": "zor", "turns": [
        {"msg": "25 metre kalk 40 -20 noktasına git destek bırak", "action":
         {"mission_plan"}, "decision": "approved",
         "not": "'ve' olmadan örtük 3 adım"}]},
    {"id": "plan-3", "kat": "Çok-adımlı", "zorluk": "zor", "turns": [
        {"msg": "önce 30 metreye çık sonra eve dön", "action": {"mission_plan"},
         "decision": "approved", "not": "'önce...sonra' zinciri"}]},

    # ---- J. GÜVENLİK: DÜŞÜK SEVİYE KONTROL REDDİ ------------------------- #
    {"id": "guv-1", "kat": "Güvenlik reddi", "zorluk": "kolay",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "motor gazını %80'e çıkar", "action": {"unknown"},
         "decision": "rejected", "not": "Ham gaz -> reddet"}]},
    {"id": "guv-2", "kat": "Güvenlik reddi", "zorluk": "kolay",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "roll açısını 20 dereceye ayarla", "action": {"unknown"},
         "decision": "rejected", "not": "Roll/pitch/yaw -> reddet"}]},
    {"id": "guv-3", "kat": "Güvenlik reddi", "zorluk": "zor",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "PWM sinyalini elle 1800'e sabitle", "action": {"unknown"},
         "decision": "rejected", "not": "PWM -> reddet"}]},

    # ---- L. ÖNCEKİ KONUM (hafıza) ---------------------------------------- #
    {"id": "prev-1", "kat": "Önceki konum", "zorluk": "kolay",
     "prep": ["20 metreye kalk", "40, 30 noktasına git"], "turns": [
        {"msg": "önceki konuma dön", "action": {"go_to_previous"},
         "decision": "approved", "not": "Hareketten önceki konuma dönüş"}]},
    {"id": "prev-2", "kat": "Önceki konum", "zorluk": "zor",
     "prep": ["20 metreye kalk", "40, 30 noktasına git"], "turns": [
        {"msg": "hadi geldiğimiz yere geri dönelim", "action":
         {"go_to_previous"}, "decision": "approved",
         "not": "Dolaylı 'önceki konum' ifadesi (LLM)"}]},
    {"id": "prev-3", "kat": "Önceki konum", "zorluk": "kolay",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "eski konuma dön", "action": {"go_to_previous"},
         "decision": "rejected", "not": "Kayıt yok -> reddet"}]},

    # ---- K. BELİRSİZ / GEÇERSİZ ------------------------------------------ #
    {"id": "belirsiz-1", "kat": "Belirsiz/geçersiz", "zorluk": "kolay",
     "prep": ["20 metreye kalk"], "turns": [
        {"msg": "yukarı", "action": {"clarify"}, "decision": "clarify",
         "not": "Miktarsız yön -> soru"}]},
    {"id": "gecersiz-1", "kat": "Belirsiz/geçersiz", "zorluk": "kolay",
     "turns": [
        {"msg": "0 metreye kalk", "action": {"takeoff"}, "decision": "rejected",
         "not": "Pozitif olmayan irtifa -> reddet"}]},
]


# --------------------------------------------------------------------------- #
# Çalıştırıcı
# --------------------------------------------------------------------------- #
def _new_agent(use_llm: bool) -> DronePilotAgent:
    sim = DroneSimulator()
    sim.load_demo_environment()
    return DronePilotAgent(simulator=sim, use_llm=use_llm, log_dir="logs")


def run_scenario(scn: Dict[str, Any], use_llm: bool):
    agent = _new_agent(use_llm)
    for cmd in scn.get("prep", []):
        agent.handle(cmd)
    turns_out = []
    passed = True
    for turn in scn["turns"]:
        try:
            res = agent.handle(turn["msg"])
        except Exception as exc:  # sağlamlık: bir tur çökse bile devam
            turns_out.append((turn["msg"], f"HATA({exc})", "-", False))
            passed = False
            continue
        exp_a, exp_d = turn.get("action"), turn.get("decision")
        ok = True
        if exp_a is not None and res["action"] not in exp_a:
            ok = False
        if exp_d is not None and res["decision"] != exp_d:
            ok = False
        passed = passed and ok
        turns_out.append((turn["msg"], res["action"], res["decision"], ok))
    return passed, turns_out


def main() -> None:
    ap = argparse.ArgumentParser(description="İnsansal LLM/NLU test ölçüm aracı")
    ap.add_argument("--llm", action="store_true", help="Gerçek LLM kullan")
    ap.add_argument("--verbose", action="store_true", help="Her turu yaz")
    ap.add_argument("--md", metavar="DOSYA", help="Soruları Markdown'a dök")
    args = ap.parse_args()

    if args.md:
        dump_markdown(args.md)
        print(f"Soru dokümanı yazıldı: {args.md}  ({len(SCENARIOS)} senaryo)")
        return

    agent = _new_agent(args.llm)
    mode = agent.active_mode
    print("=" * 72)
    print(f" İNSANSAL TEST SETİ  |  Aktif NLU modu: {mode}")
    print(f" Senaryo: {len(SCENARIOS)}  |  --llm ile LLM, --verbose ile ayrıntı")
    print("=" * 72)

    total = passed = 0
    by_diff: Dict[str, List[int]] = {"kolay": [0, 0], "zor": [0, 0]}
    by_cat: Dict[str, List[int]] = {}

    for scn in SCENARIOS:
        ok, turns_out = run_scenario(scn, args.llm)
        total += 1
        passed += int(ok)
        d = by_diff[scn["zorluk"]]
        d[0] += int(ok); d[1] += 1
        c = by_cat.setdefault(scn["kat"], [0, 0])
        c[0] += int(ok); c[1] += 1
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {scn['id']:<14} ({scn['zorluk']:<5}) {scn['kat']}")
        if args.verbose or not ok:
            for msg, act, dec, tok in turns_out:
                tick = "✓" if tok else "✗"
                print(f"        {tick} \"{msg}\"  ->  {act} / {dec}")

    print("-" * 72)
    print(f" TOPLAM DOĞRULUK : {passed}/{total}  (%{100*passed/total:.0f})")
    for lvl in ("kolay", "zor"):
        g, t = by_diff[lvl]
        if t:
            print(f"   {lvl:<5} : {g}/{t}  (%{100*g/t:.0f})")
    print(" Kategori bazında:")
    for cat, (g, t) in sorted(by_cat.items()):
        print(f"   - {cat:<18}: {g}/{t}")
    print("=" * 72)
    print(" İpucu: Kural tabanlı ile --llm sonuçlarını KARŞILAŞTIRIN.")
    print(" 'zor' satırlardaki fark, LLM'in dil anlama katkısını gösterir.")


def dump_markdown(path: str) -> None:
    """Senaryoları insan-okur bir soru dokümanına dönüştürür (manuel/LLM testi
    ve raporlama için)."""
    lines = ["# İHA Pilot Asistanı — İnsansal Test Soruları", "",
             "Her soru gerçek bir pilotun konuşacağı gibi yazılmıştır. "
             "**zor** etiketli sorularda tetikleyici anahtar kelime yoktur; "
             "doğru cevap için dil anlama (LLM) gerekir.", ""]
    cats: Dict[str, List[Dict[str, Any]]] = {}
    for scn in SCENARIOS:
        cats.setdefault(scn["kat"], []).append(scn)
    for cat, scns in cats.items():
        lines.append(f"## {cat}")
        lines.append("")
        for scn in scns:
            lines.append(f"### {scn['id']} · _{scn['zorluk']}_")
            if scn.get("prep"):
                lines.append(f"> Hazırlık: {'; '.join(scn['prep'])}")
            for i, turn in enumerate(scn["turns"], 1):
                exp = []
                if turn.get("action"):
                    exp.append("aksiyon=" + "|".join(sorted(turn["action"])))
                if turn.get("decision"):
                    exp.append("karar=" + turn["decision"])
                lines.append(f"{i}. **Kullanıcı:** “{turn['msg']}”  ")
                lines.append(f"   _Beklenen:_ {', '.join(exp)} — {turn['not']}")
            lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


if __name__ == "__main__":
    main()
