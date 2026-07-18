"""
demo_showcase.py
================
LLM / Ajan YETENEK GÖSTERİM (demo) betiği.

Bu betik, asistanın doğal dil anlama ve güvenli araç-çağırma yeteneğini
GÖSTERMEK için tasarlanmış, ZİNCİRLEME ve gerçekçi promptları sırayla çalıştırır
ve her komutun ürettiği anlatımlı yanıtı + telemetriyi ekrana basar.

Amaç: değerlendirme sırasında "sistem doğru, güvenli ve açıklanabilir çalışıyor"
iddiasını canlı olarak kanıtlamak. Her DEMO bloğu bir yeteneği vurgular:

    1. Bayrak gösterisi  : tek cümlede çok aşamalı GÖZLEM görevi (orbit)
    2. Zincirleme görev   : kalk + git + yük bırak + eve dön (tek komut)
    3. Otonom kaçınma     : engelden dolaşarak hedefe ulaşma
    4. Sohbet / belirsizlik: eksik bilgiyi kendi sorup tamamlama (çok-turlu)
    5. Hafıza             : 'önceki konuma dön'
    6. Enerji + fail-safe : kritik bataryada otomatik eve dönüş
    7. Güvenlik reddi     : maks. irtifa / düşük seviye / yasak bölge / geçersiz
    8. Doğal varyasyonlar : anahtar kelimesiz, günlük ifadeler (LLM'i öne çıkarır)

Çalıştırma:
    python demo_showcase.py             # kural tabanlı NLU
    python demo_showcase.py --llm       # gerçek LLM (Ollama/Anthropic/OpenAI)
    python demo_showcase.py --pause     # her komuttan sonra Enter bekle (sunum)
"""

from __future__ import annotations

import argparse

from uav_assistant import DronePilotAgent, DroneSimulator


def new_agent(use_llm: bool) -> DronePilotAgent:
    sim = DroneSimulator()
    sim.load_demo_environment()
    return DronePilotAgent(simulator=sim, use_llm=use_llm, log_dir="logs")


class Demo:
    def __init__(self, use_llm: bool, pause: bool):
        self.use_llm = use_llm
        self.pause = pause

    def _say(self, agent, prompt):
        res = agent.handle(prompt)
        icon = {"approved": "✅", "rejected": "⛔", "clarify": "💬",
                "error": "⚠️"}.get(res["decision"], "•")
        print(f"\n🧑 PILOT   : {prompt}")
        print(f"🤖 ASİSTAN [{icon} {res['decision']}] ({res['action']})")
        for line in res["reply"].splitlines():
            print(f"           {line}")
        if self.pause:
            try:
                input("           — devam için Enter —")
            except EOFError:
                pass

    def block(self, title, subtitle):
        print("\n" + "=" * 74)
        print(f" {title}")
        print(f"   → {subtitle}")
        print("=" * 74)

    # ------------------------------------------------------------------ #
    def run(self):
        mode = new_agent(self.use_llm).active_mode
        print("#" * 74)
        print(f"#  İHA PİLOT ASİSTANI — YETENEK GÖSTERİMİ   |  NLU modu: {mode}")
        print("#" * 74)

        # 1) BAYRAK: tek cümlede çok aşamalı gözlem görevi ----------------- #
        self.block("DEMO 1 — Karmaşık bileşik GÖZLEM görevi (tek cümle)",
                   "Kalkış + seyir + alçalma + dairesel gözlem (2 tur) + "
                   "yükselme + eve dönüşü tek komuttan planlar.")
        a = new_agent(self.use_llm)
        self._say(a, "50 metre yükseklikten 12,23 konumuna git o noktayı 10 "
                     "metre çapında dolaşıp gözlemle 5 metre yükseklikte o "
                     "çapta 2 tur attıktan sonra tekrar aynı yüksekliğe gelip "
                     "başlangıç noktasına dön")

        # 2) ZİNCİRLEME görev --------------------------------------------- #
        self.block("DEMO 2 — Zincirleme çok-adımlı görev",
                   "Tek komutta kalkış → konuma gidiş → yük bırakma → eve "
                   "dönüş; adımlar ayrı ayrı doğrulanır.")
        a = new_agent(self.use_llm)
        self._say(a, "45 metreye kalk, -30 20 noktasına git ve oraya bir "
                     "destek paketi bırak sonra başlangıç noktasına dön")

        # 3) OTONOM engelden kaçınma -------------------------------------- #
        self.block("DEMO 3 — Otonom engelden kaçınma",
                   "Doğrudan rota bir binadan geçtiği için ajan güvenli ara "
                   "nokta üretip engelin etrafından dolaşır.")
        a = new_agent(self.use_llm)
        self._say(a, "20 metreye kalk ve 50 70 noktasına git")

        # 4) SOHBET / belirsizlik çözümü (çok-turlu) ---------------------- #
        self.block("DEMO 4 — Belirsizliği kendi sorup tamamlama (çok-turlu)",
                   "Eksik bilgi olduğunda varsayım YAPMAZ; sorar ve cevabı "
                   "bağlamda hatırlayarak görevi tamamlar.")
        a = new_agent(self.use_llm)
        self._say(a, "kalkışa geç")             # irtifa sorar
        self._say(a, "25 metre olsun")          # tamamlar
        self._say(a, "bir koordinata gidelim")  # koordinat sorar
        self._say(a, "40, -30")                 # tamamlar

        # 5) HAFIZA: önceki konuma dönüş ---------------------------------- #
        self.block("DEMO 5 — Konum hafızası",
                   "Hareketten önceki konumu hatırlar; 'önceki konuma dön' "
                   "ile geri gider (art arda: gidip-gelir).")
        a = new_agent(self.use_llm)
        self._say(a, "20 metreye kalk")
        self._say(a, "35, 15 noktasına git")
        self._say(a, "önceki konuma dön")

        # 6) ENERJİ farkındalığı + FAIL-SAFE ------------------------------ #
        self.block("DEMO 6 — Enerji farkındalığı + otomatik fail-safe RTH",
                   "Menzil/enerji tahmini; batarya kritik eşiğe inince görev "
                   "durdurulup OTOMATİK eve dönülür (zorunlu güvenlik).")
        a = new_agent(self.use_llm)
        self._say(a, "30 metreye kalk")
        self._say(a, "menzilimiz uzağa gidip dönmeye yeter mi")
        a.sim.state.battery = 19.0              # kritik seviyeyi simüle et
        print("\n   [simülasyon: batarya %19'a düşürüldü]")
        self._say(a, "-45, -45 noktasına git")  # fail-safe devreye girer

        # 7) GÜVENLİK reddi (başarısız/güvensiz senaryolar) --------------- #
        self.block("DEMO 7 — Güvenlik katmanı: reddedilen komutlar",
                   "Maksimum irtifa aşımı, düşük seviye kontrol, yasak bölge "
                   "ve geçersiz parametre GEREKÇELİ olarak reddedilir.")
        a = new_agent(self.use_llm)
        self._say(a, "900 metreye kalk")             # maks irtifa (yerde)
        a.handle("20 metreye kalk")
        self._say(a, "motor gazını %90'a getir")     # düşük seviye kontrol
        self._say(a, "60 10 noktasına git")          # yasak bölge merkezi
        self._say(a, "20 20 noktasına 900 metrede git")  # geçersiz irtifa

        # 8) DOĞAL varyasyonlar (LLM'i öne çıkaran) ----------------------- #
        self.block("DEMO 8 — Doğal dil varyasyonları (aynı niyet, farklı ifade)",
                   "Anahtar kelime olmadan, günlük/dolaylı ifadeler. İyi bir "
                   "LLM bunları doğru araca eşler.")
        a = new_agent(self.use_llm)
        a.handle("20 metreye kalk")
        self._say(a, "şu 15, 55 koordinatına doğru süzül")   # go_to
        self._say(a, "kargoyu tam buraya bırakıver")          # drop_payload
        self._say(a, "hadi üsse geri dönelim artık")          # return_to_home

        print("\n" + "#" * 74)
        print("#  GÖSTERİM TAMAMLANDI. Ayrıntılı kayıt: logs/mission_log.json")
        print("#  Ölçümlü test seti için: python test_llm_scenarios.py [--llm]")
        print("#" * 74)


def main():
    ap = argparse.ArgumentParser(description="İHA asistanı yetenek gösterimi")
    ap.add_argument("--llm", action="store_true", help="Gerçek LLM kullan")
    ap.add_argument("--pause", action="store_true",
                    help="Her komuttan sonra Enter bekle (canlı sunum)")
    args = ap.parse_args()
    Demo(use_llm=args.llm, pause=args.pause).run()


if __name__ == "__main__":
    main()
