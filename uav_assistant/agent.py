"""
agent.py
========
LLM Ajanı (Doğal Dil Arayüzü) + çok-adımlı görev planlama.

Kullanıcının doğal dilde verdiği komutları alıp yapılandırılmış bir görev
isteğine (tool call) dönüştürür ve `DroneTools` üzerinden güvenle çalıştırır.

HİBRİT tasarım:
    * Varsayılan: API anahtarı gerektirmeyen, offline çalışan KURAL TABANLI
      NLU parser.
    * use_llm=True verilirse gerçek bir LLM tool-calling backend'ine geçer.
      Desteklenen sağlayıcılar:
        - ollama    : yerel/offline model (llama3.1, qwen2.5, mistral ...),
                      http://localhost:11434, ÜCRETSİZ, API anahtarı gerekmez
        - anthropic : bulut (claude-sonnet-5)  -> ANTHROPIC_API_KEY
        - openai    : bulut (gpt-4o-mini)      -> OPENAI_API_KEY
      Hangi sağlayıcı UAV_LLM_PROVIDER ile seçilir ("auto"/"ollama"/
      "anthropic"/"openai"). Sağlayıcıdan bağımsız olarak LLM yalnızca güvenli
      tool'ları çağırabilir; güvenlik katmanı her koşulda uygulanır.

Yetenekler:
    - Durum sorgulama (telemetriyi doğal dille açıklama)
    - Kalkış / iniş / eve dönüş / bir konuma gitme (go_to)
    - Çok-adımlı görev ("kalk, git, durum bildir, eve dön")
    - Geçersiz/güvensiz komutu reddetme (nedenini açıklayarak)
    - Belirsiz komutta VARSAYIM YAPMADAN açıklama isteme
    - Batarya bazlı otomatik eve dönüş önerisi (özgün özellik)
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .simulation import DroneSimulator
from .tools import DroneTools
from .logger import MissionLogger
from .safety import FAILSAFE_RTH_BATTERY


@dataclass
class Intent:
    """Doğal dil komutundan çıkarılan yapılandırılmış niyet."""

    action: str
    args: Dict[str, Any]
    kind: str = "tool_call"        # "tool_call" | "clarify" | "unknown"
    note: str = ""
    await_kind: str = ""           # clarify ise beklenen yanıt türü (sohbet)


# --------------------------------------------------------------------------- #
# Kural tabanlı doğal dil ayrıştırıcı (offline, deterministik)
# --------------------------------------------------------------------------- #
class RuleBasedNLU:
    """
    Anahtar kelime ve regex tabanlı basit bir niyet çözümleyici.

    Türkçe ve İngilizce temel komutları destekler; aksan-duyarsızdır. Belirsizlik
    durumunda ASLA varsayım yapmaz, `clarify` niyeti döndürür.
    """

    TELEMETRY_KW = [
        "telemetri", "durum", "batarya", "irtifa", "yukseklik", "nerede",
        "konum", "ne kadar", "status", "telemetry", "battery", "altitude",
        "where", "state", "rapor", "bilgi", "bildir",
    ]
    TAKEOFF_KW = ["kalk", "havalan", "yuksel", "cik", "takeoff", "take off",
                  "take-off", "launch", "ascend"]
    LAND_KW = ["inis", "indir", "yere in", "land", "alcal", "descend",
               "touch down"]
    RTH_KW = ["eve don", "eve gel", "eve git", "geri don", "usse don",
              "return to home", "return home", "rth", "come back", "go home",
              "return", "baslangica", "baslangic noktas", "baslangic konum",
              "kalkis noktas", "basladigimiz yer", "usse geri"]
    GOTO_KW = ["noktasina git", "konumuna git", "koordinat", "git ", "gel ",
               "go to", "goto", "move to", "point", "noktaya git"]
    # Göreli/yönlü hareket: yön kelimesi -> (eksen, işaret)
    DIR_MAP = {
        "sag": ("x", 1), "saga": ("x", 1), "right": ("x", 1),
        "sol": ("x", -1), "sola": ("x", -1), "left": ("x", -1),
        "ileri": ("y", 1), "on": ("y", 1), "forward": ("y", 1),
        "geri": ("y", -1), "arka": ("y", -1), "back": ("y", -1),
        "yukari": ("z", 1), "up": ("z", 1),
        "asagi": ("z", -1), "down": ("z", -1),
    }
    LOWLEVEL_KW = ["roll", "pitch", "yaw", "pwm", "throttle", "gaz", "motor",
                   "ham hiz", "raw speed", "servo", "esc"]
    # Otonom kaçınma / engel tepkisi (en yüksek öncelik)
    AVOID_KW = ["engel", "tehlike", "carpacak", "carpma", "carpar", "kacin",
                "engelden", "onunde engel", "avoid", "collision"]
    # Enerji/menzil sorgusu (RTH/telemetriden ÖNCE denetlenir)
    ENERGY_KW = ["menzil", "gidebilir", "donebilir mi", "ucabilir", "enerji",
                 "yeter mi", "kalan menzil", "ne kadar gidebilir",
                 "eve donebilir", "sarj yeter"]
    # Yük/destek/kargo bırakma (özgün yetenek). GOTO'dan ÖNCE denetlenir
    DROP_KW = ["destek birak", "yuk birak", "yuku birak", "kargo birak",
               "paket birak", "malzeme birak", "yardim birak", "destek indir",
               "kargo indir", "teslim et", "teslimat", "yuk teslim",
               "destek at", "paket at", "payload", "drop", "deliver", "birak"]
    # Yardım/kurtarma görevi (sohbet tarzı, özgün): bir koordinata yardıma gitme
    HELP_KW = ["yardim", "yardima", "imdat", "acil", "kurtar", "kurtarma",
               "yaral", "mahsur", "enkaz", "sos", "help", "rescue",
               "emergency", "medet"]
    # Batarya şarjı (evde/yerde). ENERGY/TELEMETRY'den ÖNCE denetlenir
    CHARGE_KW = ["sarj et", "sarj ol", "sarj yap", "sarjet", "sarj olsun",
                 "batarya doldur", "bataryayi doldur", "pili doldur",
                 "enerji doldur", "sarja tak", "doldur", "charge", "recharge"]
    # Gözlem/keşif yörüngesi (özgün): bir noktanın etrafında daire çizip gözleme
    OBSERVE_KW = ["gozlem", "gozetle", "gozle", "dolas", "orbit", "tur at",
                  "cevresinde don", "etrafinda don", "daire ciz", "kesif",
                  "izle", "tara", "cember"]
    # Önceki konuma dönüş (hafıza). RTH/GOTO'dan ÖNCE denetlenir
    PREV_KW = ["onceki konum", "onceki konuma", "onceki noktaya",
               "onceki noktatan", "onceki yere", "bir onceki", "eski konuma",
               "eski konum", "eski noktaya", "eksi konuma", "eksi konum",
               "geldigim yere", "son konuma", "onceki pozisyon",
               "previous position", "go back", "onceki yerine"]
    # Örtük çok-adımlı ayırma için FİİL çıpaları (Türkçe komutlar fiil-son'dur:
    # '... kalk', '... git', 'eve dön', '... bırak'). Bir cümlede >=2 çıpa varsa
    # her çıpadan SONRA yeni bir adım başlatılır (ör. '20 metre kalk 17,67 git').
    STEP_ANCHORS = {
        "kalk", "kalkis", "havalan", "cik", "yuksel",
        "git", "gel", "ilerle", "var",
        "in", "inis", "indir", "alcal", "alcalt",
        "don", "kacin",
        "birak", "birakin", "indirin", "teslim", "at",
        "bildir", "raporla",
    }

    ALTITUDE_RE = re.compile(
        r"(\d+(?:[.,]\d+)?)\s*(m|metre|meter|meters|metreye|metrede)?",
        re.IGNORECASE,
    )
    NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")
    STEP_SEPARATORS = re.compile(
        # Virgül yalnızca RAKAM-RAKAM arasında DEĞİLKEN adım ayracıdır;
        # "4,5" / "40, 30" gibi koordinat çiftleri bölünmez.
        r"\s*(?:(?<!\d)\s*,|;| ve | sonra | ardindan | daha sonra | then )\s*",
        re.IGNORECASE,
    )

    @staticmethod
    def _norm(s: str) -> str:
        """Türkçe karakterleri sadeleştirip küçük harfe çevirir (aksan-duyarsız
        eşleştirme): 'çık'/'cik', 'iniş'/'inis', 'dön'/'don' hepsi aynı tanınır.
        """
        s = s.lower()
        for a, b in (("ç", "c"), ("ğ", "g"), ("ı", "i"), ("ö", "o"),
                     ("ş", "s"), ("ü", "u"), ("â", "a"), ("î", "i"),
                     ("û", "u"), ("i̇", "i")):
            s = s.replace(a, b)
        return s

    def parse(self, text: str) -> Intent:
        t = f" {self._norm(text.strip())} "

        if self._has(t, self.LOWLEVEL_KW):
            return Intent(
                "unknown", {}, "unknown",
                note="Düşük seviyeli kontrol komutları (roll/pitch/yaw/PWM/gaz "
                     "vb.) güvenlik gereği DESTEKLENMEZ ve reddedilir. Yalnızca "
                     "güvenli işlemler kullanılabilir: telemetri, kalkış, iniş, "
                     "eve dönüş, go_to.",
            )
        if self._has(t, self.AVOID_KW):
            dist = self._extract_altitude(text)  # varsa engel uzakligi
            args = {} if dist is None else {"distance": dist}
            return Intent("avoid_obstacle", args, "tool_call")
        if self._has(t, self.CHARGE_KW):
            amount = self._extract_altitude(text)
            args = {"amount": amount} if amount is not None else {}
            return Intent("recharge", args, "tool_call")
        if self._has(t, self.PREV_KW):
            return Intent("go_to_previous", {}, "tool_call")
        if self._has(t, self.DROP_KW):
            coords = self._extract_coords(text)
            args = {}
            if coords:
                args = {k: v for k, v in coords.items() if k in ("x", "y")}
            return Intent("drop_payload", args, "tool_call")
        if self._has(t, self.ENERGY_KW):
            return Intent("get_energy_status", {}, "tool_call")
        if self._has(t, self.RTH_KW):
            return Intent("return_to_home", {}, "tool_call")
        move = self._extract_move(text)
        if move is not None:
            if move.get("_no_amount"):
                return Intent(
                    "clarify", {}, "clarify",
                    note="Yön belirtildi ancak miktar yok. Örn: '4 sağa git', "
                         "'20 yukarı çık', '8 aşağı in'. Varsayım yapılmadı.",
                    await_kind="move_amount",
                )
            return Intent("move", move, "tool_call")
        if self._has(t, self.GOTO_KW):
            coords = self._extract_coords(text)
            if coords is None:
                return Intent(
                    "clarify", {}, "clarify",
                    note="Gidilecek konum için en az x ve y koordinatı gerekli "
                         "(ör. '30, 40 noktasına git' veya 'x=30 y=40 25 metrede "
                         "git'). Varsayım yapılmadı.",
                    await_kind="goto_coords",
                )
            return Intent("go_to", coords, "tool_call")
        if self._has(t, self.TELEMETRY_KW):
            return Intent("get_telemetry", {}, "tool_call")
        if self._has(t, self.TAKEOFF_KW):
            altitude = self._extract_altitude(text)
            if altitude is None:
                return Intent(
                    "clarify", {}, "clarify",
                    note="Kalkış komutu için hedef irtifa belirtilmedi. Lütfen "
                         "kaç metreye kalkış yapılacağını belirtin (ör. '20 "
                         "metreye kalk').",
                    await_kind="takeoff_altitude",
                )
            return Intent("takeoff", {"altitude": altitude}, "tool_call")
        if self._has(t, self.LAND_KW):
            return Intent("land", {}, "tool_call")
        if self.ALTITUDE_RE.search(text) and not self._has(
            t, self.TAKEOFF_KW + self.LAND_KW + self.RTH_KW
        ):
            return Intent(
                "clarify", {}, "clarify",
                note="Bir irtifa/sayı algılandı ancak ne yapılacağı belirsiz. "
                     "Kalkış mı, alçalma mı istiyorsunuz?",
            )
        return Intent(
            "unknown", {}, "unknown",
            note="Komut anlaşılamadı. Desteklenen işlemler: telemetri "
                 "sorgulama, kalkış, iniş, eve dönüş, bir konuma gitme.",
        )

    def _has(self, padded_text: str, keywords) -> bool:
        return any(self._norm(kw) in padded_text for kw in keywords)

    def _extract_altitude(self, text: str) -> Optional[float]:
        m = self.ALTITUDE_RE.search(text)
        if not m:
            return None
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None

    def _extract_coords(self, text: str) -> Optional[Dict[str, float]]:
        # Once "7,18" / "40, 30" gibi virgulle ayrilmis KOORDINAT ciftini dene
        # (virgul ayrac kabul edilir; ondalik icin nokta kullanin).
        pair = re.search(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", text)
        if pair:
            coords: Dict[str, float] = {"x": float(pair.group(1)),
                                        "y": float(pair.group(2))}
            after = re.search(r"-?\d+(?:\.\d+)?", text[pair.end():])
            if after:
                coords["altitude"] = float(after.group())
            return coords
        nums = [float(n.replace(",", ".")) for n in self.NUMBER_RE.findall(text)]
        if len(nums) < 2:
            return None
        coords = {"x": nums[0], "y": nums[1]}
        if len(nums) >= 3:
            coords["altitude"] = nums[2]
        return coords

    def _extract_move(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Yönlü/göreli hareket komutlarını çözer: 'sağa/sola/ileri/geri/yukarı/
        aşağı' + miktar. Örn: '20 yukarı çık 4 sağa git' -> dz=+20, dx=+4.
        Yön yoksa None döner; yön var ama miktar yoksa {'_no_amount': True}.
        """
        toks = re.findall(r"-?\d+(?:[.,]\d+)?|[a-z]+", self._norm(text))

        def _num(tok):
            try:
                return float(tok.replace(",", "."))
            except ValueError:
                return None

        deltas = {"x": 0.0, "y": 0.0, "z": 0.0}
        found_dir = False
        pending = None
        for idx, tok in enumerate(toks):
            n = _num(tok)
            if n is not None:
                pending = n
                continue
            if tok in self.DIR_MAP:
                found_dir = True
                axis, sign = self.DIR_MAP[tok]
                amt = pending
                if amt is None:  # yön kelimesinden sonra sayı ara
                    for j in range(idx + 1, len(toks)):
                        nj = _num(toks[j])
                        if nj is not None:
                            amt = nj
                            break
                if amt is not None:
                    deltas[axis] += sign * amt
                    pending = None
        if not found_dir:
            return None
        if deltas["x"] == 0 and deltas["y"] == 0 and deltas["z"] == 0:
            return {"_no_amount": True}
        return {"dx": deltas["x"], "dy": deltas["y"], "dz": deltas["z"]}


# --------------------------------------------------------------------------- #
# Opsiyonel gerçek LLM backend'i (Ollama / Anthropic / OpenAI)
# --------------------------------------------------------------------------- #
class LLMBackend:
    """
    Gerçek bir LLM tool-calling backend'i için ince sarmalayıcı.

    Sağlayıcı sırası UAV_LLM_PROVIDER ile belirlenir:
        "auto" (varsayılan) -> anthropic, openai, ollama (ilk erişilebilir olan)
        "ollama" / "anthropic" / "openai" -> yalnızca o sağlayıcı.

    Hiçbiri erişilebilir değilse `available` False olur ve ajan otomatik olarak
    kural tabanlı parser'a düşer. Güvenlik yine ayrı katmanda uygulanır.
    """

    SYSTEM_PROMPT = (
        "Sen bir İHA (drone) pilot asistanısın. Görevin, kullanıcının doğal dil "
        "komutunu YALNIZCA şu güvenli araçlardan birine çevirmektir: "
        "get_telemetry, takeoff(altitude), land, return_to_home, "
        "go_to(x,y[,altitude]), move(dx,dy,dz), get_energy_status, avoid_obstacle(distance), "
        "drop_payload(x?,y?,label?), go_to_previous, observe(x,y,radius,laps,altitude?), "
        "recharge(amount?).\n"
        "KURALLAR:\n"
        "1) Düşük seviyeli kontrol (PWM, ham hız, roll/pitch/yaw, motor) ASLA "
        "üretme.\n"
        "2) Gerekli sayı/koordinat komutta yoksa DEĞER UYDURMA; araç çağırma, "
        "kullanıcıdan iste.\n"
        "3) 'Mevcut durum'u dikkate al: drone zaten havadaysa takeoff çağırma; "
        "yerdeyse hareketten önce takeoff gerekir.\n"
        "4) Göreli yön: sağ=+dx, sol=-dx, ileri=+dy, geri=-dy, yukarı=+dz, "
        "aşağı=-dz. Mutlak konum için go_to kullan.\n"
        "5) Yalnızca TEK bir araç çağrısı üret; açıklama metni yazma.\n"
        "ÖRNEKLER:\n"
        "'durum nedir' -> get_telemetry\n"
        "'20 metreye kalk' -> takeoff(altitude=20)\n"
        "'4, 5 konumuna git' -> go_to(x=4, y=5)\n"
        "'10 sağa 5 yukarı' -> move(dx=10, dz=5)\n"
        "'menzilim yeter mi' -> get_energy_status\n"
        "'eve dön' -> return_to_home\n"
        "'17, 67 konumuna destek bırak' -> drop_payload(x=17, y=67)\n"
        "'destek paketini bırak' -> drop_payload()\n"
        "'önceki konuma dön' / 'eski konuma geri dön' -> go_to_previous\n"
        "'12,23 noktasını 10 m çapında dolaşıp gözlemle' -> observe(x=12,y=23,radius=5,laps=1)\n"
        "'bataryayı şarj et' / 'şarj ol' -> recharge (yalnızca evde/yerde)\n"
        "'yukarı çık' (miktar yok) -> araç çağırma, miktar iste."
    )

    # Ollama'da tercih edilen (tool-calling'i güvenilir) modeller
    PREFERRED_OLLAMA = ["qwen2.5", "llama3.1", "mistral-nemo", "llama3.2",
                        "firefunction", "command-r", "mistral"]
    # Geçerli araç adları (LLM bunların dışında bir şey üretirse güvenilmez)
    VALID_ACTIONS = {"get_telemetry", "takeoff", "land", "return_to_home",
                     "go_to", "move", "get_energy_status", "avoid_obstacle",
                     "drop_payload", "go_to_previous", "observe", "recharge"}

    def __init__(self):
        self.provider: Optional[str] = None
        self.available = False
        self._client = None
        self.model: Optional[str] = None
        self.ollama_host = os.getenv(
            "OLLAMA_HOST", "http://localhost:11434"
        ).rstrip("/")
        self._init_client()

    # -- sağlayıcı seçimi ------------------------------------------------ #
    def _init_client(self) -> None:
        pref = os.getenv("UAV_LLM_PROVIDER", "auto").lower()
        order = (["anthropic", "openai", "ollama"] if pref == "auto"
                 else [pref])
        for p in order:
            if p == "anthropic" and self._try_anthropic():
                return
            if p == "openai" and self._try_openai():
                return
            if p == "ollama" and self._try_ollama():
                return

    def _try_anthropic(self) -> bool:
        if not os.getenv("ANTHROPIC_API_KEY"):
            return False
        try:
            import anthropic
            self._client = anthropic.Anthropic()
            self.provider = "anthropic"
            self.model = os.getenv("UAV_LLM_MODEL", "claude-sonnet-5")
            self.available = True
            return True
        except Exception:
            return False

    def _try_openai(self) -> bool:
        if not os.getenv("OPENAI_API_KEY"):
            return False
        try:
            from openai import OpenAI
            self._client = OpenAI()
            self.provider = "openai"
            self.model = os.getenv("UAV_LLM_MODEL", "gpt-4o-mini")
            self.available = True
            return True
        except Exception:
            return False

    def _try_ollama(self) -> bool:
        """Ollama çalışıyorsa, kurulu modeller arasından tool-calling'e en
        uygun olanı otomatik seçer (UAV_LLM_MODEL verilirse o kullanılır)."""
        try:
            with urllib.request.urlopen(
                self.ollama_host + "/api/tags", timeout=1.5
            ) as resp:
                if resp.status != 200:
                    return False
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return False
        installed = [m.get("name", "") for m in data.get("models", [])]
        forced = os.getenv("UAV_LLM_MODEL")
        chosen = forced
        if not chosen:
            for pref in self.PREFERRED_OLLAMA:
                match = next((n for n in installed if n.startswith(pref)
                              or pref in n), None)
                if match:
                    chosen = match
                    break
            if not chosen and installed:
                chosen = installed[0]
        self.provider = "ollama"
        self.model = chosen or "llama3.1"
        self.available = True
        return True

    # -- yardımcılar ----------------------------------------------------- #
    @staticmethod
    def _context_line(context) -> str:
        """Modele verilecek 'Mevcut durum' satırı (daha isabetli karar için)."""
        if not context:
            return ""
        c = context
        return ("Mevcut durum: konum=(%s, %s), irtifa=%s m, mod=%s, "
                "batarya=%%%s, havada=%s." % (
                    c.get("x"), c.get("y"), c.get("altitude"), c.get("mode"),
                    c.get("battery"), "evet" if c.get("in_air") else "hayir"))

    @staticmethod
    def _coerce_args(args) -> Dict[str, Any]:
        """LLM argümanlarını normalize eder (sayı stringlerini float'a çevirir)."""
        out: Dict[str, Any] = {}
        for k, v in (args or {}).items():
            if isinstance(v, str):
                vs = v.strip().replace(",", ".")
                try:
                    v = float(vs)
                except ValueError:
                    pass
            out[k] = v
        return out

    # -- çözümleme ------------------------------------------------------- #
    def to_intent(self, text, tools_schema, context=None) -> Optional[Intent]:
        if not self.available:
            return None
        try:
            if self.provider == "ollama":
                return self._ollama_call(text, tools_schema, context)
            if self.provider == "anthropic":
                return self._anthropic_call(text, tools_schema, context)
            if self.provider == "openai":
                return self._openai_call(text, tools_schema, context)
        except Exception:
            return None
        return None

    def _ollama_call(self, text, tools_schema, context=None) -> Optional[Intent]:
        """Ollama /api/chat (stdlib urllib; ek bağımlılık yok, temperature=0)."""
        tools = [{"type": "function", "function": t} for t in tools_schema]
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        ctx = self._context_line(context)
        if ctx:
            messages.append({"role": "system", "content": ctx})
        messages.append({"role": "user", "content": text})
        payload = {
            "model": self.model,
            "stream": False,
            "messages": messages,
            "tools": tools,
            "options": {"temperature": 0, "top_p": 0.9},
        }
        req = urllib.request.Request(
            self.ollama_host + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read().decode("utf-8"))
        msg = resp.get("message", {}) or {}
        tcs = msg.get("tool_calls") or []
        if tcs:
            fn = tcs[0].get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args or "{}")
                except Exception:
                    args = {}
            return Intent(fn.get("name", ""), self._coerce_args(args),
                          "tool_call")
        return Intent("clarify", {}, "clarify",
                      note=msg.get("content") or "Açıklama gerekli.")

    def _anthropic_call(self, text, tools_schema, context=None) -> Optional[Intent]:
        tools = [
            {"name": t["name"], "description": t["description"],
             "input_schema": t["parameters"]}
            for t in tools_schema
        ]
        system = self.SYSTEM_PROMPT
        ctx = self._context_line(context)
        if ctx:
            system = system + "\n" + ctx
        resp = self._client.messages.create(
            model=self.model, max_tokens=512, temperature=0, system=system,
            tools=tools, messages=[{"role": "user", "content": text}],
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return Intent(block.name,
                              self._coerce_args(dict(block.input or {})),
                              "tool_call")
        txt = " ".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        )
        return Intent("clarify", {}, "clarify", note=txt or "Açıklama gerekli.")

    def _openai_call(self, text, tools_schema, context=None) -> Optional[Intent]:
        tools = [{"type": "function", "function": t} for t in tools_schema]
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        ctx = self._context_line(context)
        if ctx:
            messages.append({"role": "system", "content": ctx})
        messages.append({"role": "user", "content": text})
        resp = self._client.chat.completions.create(
            model=self.model, tools=tools, temperature=0, messages=messages,
        )
        msg = resp.choices[0].message
        if msg.tool_calls:
            call = msg.tool_calls[0]
            args = json.loads(call.function.arguments or "{}")
            return Intent(call.function.name, self._coerce_args(args),
                          "tool_call")
        return Intent("clarify", {}, "clarify",
                      note=msg.content or "Açıklama gerekli.")


# --------------------------------------------------------------------------- #
# Ana ajan
# --------------------------------------------------------------------------- #
class DronePilotAgent:
    """
    Doğal dil komutlarını güvenle yürüten üst düzey ajan.

    Akış: komut -> (LLM veya kural tabanlı) niyet -> güvenlik katmanı ->
    simülasyon -> loglama -> doğal dil yanıtı.
    """

    def __init__(self, simulator: Optional[DroneSimulator] = None,
                 use_llm: bool = False, log_dir: str = "logs"):
        self.sim = simulator or DroneSimulator()
        self.tools = DroneTools(self.sim)
        self.logger = MissionLogger(log_dir=log_dir)
        self.nlu = RuleBasedNLU()
        self.llm = LLMBackend() if use_llm else None
        self.use_llm = bool(self.llm and self.llm.available)
        # Sohbet hafızası: yanıt bekleyen bir soru (ör. kalkış irtifası)
        self.pending: Optional[Dict[str, Any]] = None

    @property
    def active_mode(self) -> str:
        """İnsan-okur aktif NLU modu (ör. 'LLM:ollama' veya 'kural-tabanli')."""
        if self.use_llm:
            return f"LLM:{self.llm.provider}:{self.llm.model}"
        return "kural-tabanli"

    # ------------------------------------------------------------------ #
    def _interpret(self, command: str) -> Intent:
        if self.use_llm:
            # Modele canli durumu (telemetri) baglam olarak veriyoruz ki daha
            # isabetli karar versin (or. zaten havadaysa takeoff cagirmasin).
            ctx = self.sim.get_state().to_dict()
            intent = self.llm.to_intent(command, DroneTools.get_tool_schema(),
                                        ctx)
            if intent is not None:
                # Guvenilirlik korumasi: LLM (a) gecersiz bir arac adi urettiyse
                # veya (b) komutta OLMAYAN bir sayisal deger uydurduysa ona
                # guvenme; DETERMINISTIK kural tabanli parser'a dus. Boylece
                # zayif yerel modellerin hatalari otomatik telafi edilir.
                if intent.kind == "tool_call" and (
                    intent.action not in LLMBackend.VALID_ACTIONS
                    or self._has_invented_number(command, intent)
                ):
                    return self.nlu.parse(command)
                return intent
        return self.nlu.parse(command)

    @staticmethod
    def _has_invented_number(command: str, intent: Intent) -> bool:
        """LLM ciktisindaki zorunlu sayisal argumanlarin komut metninde gercekten
        gecip gecmedigini denetler. Hicbiri metinde yoksa deger uydurulmustur."""
        text_nums = set()
        for tok in re.findall(r"\d+(?:\.\d+)?", command.replace(",", " ")):
            try:
                text_nums.add(float(tok))
            except ValueError:
                pass
        a = intent.args or {}
        if intent.action == "takeoff":
            need = [a.get("altitude")]
        elif intent.action == "go_to":
            need = [a.get("x"), a.get("y")]
        elif intent.action == "move":
            need = [v for v in (a.get("dx"), a.get("dy"), a.get("dz")) if v]
        elif intent.action == "drop_payload":
            need = [v for v in (a.get("x"), a.get("y")) if v is not None]
        else:
            return False
        need = [float(v) for v in need if v is not None]
        if not need:
            return False
        return not any(v in text_nums for v in need)

    def handle(self, command: str) -> Dict[str, Any]:
        # 0) Bekleyen bir soru (ör. kalkış irtifası) varsa ve bu mesaj onu
        #    yanıtlıyorsa görevi tamamla (çok-turlu sohbet).
        if self.pending is not None:
            resolved = self._try_resolve_pending(command)
            if resolved is not None:
                return resolved
            self.pending = None  # yanıt değilse bekleyeni bırak, normal işle

        # 1) Yardım/kurtarma görevi mi? ("(3,4) yardım bekliyor" gibi) — sohbet
        #    tarzı: gerekiyorsa irtifayı sorar, sonra kalkıp yardıma gider.
        mission = self._detect_help_mission(command)
        if mission is not None:
            return self._handle_help(command, mission)

        # 2) Gözlem/yörünge görevi mi? ("... noktasını 10 m çapında dolaşıp
        #    gözlemle, 2 tur at, başlangıca dön" gibi bileşik komut).
        obs = self._detect_observe_mission(command)
        if obs is not None:
            return self._execute_observe(command, obs)

        parts = self._split_steps(command)
        if len(parts) > 1:
            return self._handle_plan(command, parts)
        return self._handle_single(command)

    # ------------------------------------------------------------------ #
    # Sohbet tarzı yardım/kurtarma görevi (özgün özellik)
    # ------------------------------------------------------------------ #
    def _detect_help_mission(self, command: str):
        """Komut bir 'yardıma git' talebiyse {x, y} veya {'no_coords': True}
        döndürür; değilse None. Açık 'bırak' komutları drop olarak bırakılır."""
        t = f" {self.nlu._norm(command)} "
        if not self.nlu._has(t, self.nlu.HELP_KW):
            return None
        if self.nlu._has(t, self.nlu.DROP_KW):
            return None  # 'yardım paketi bırak' -> normal drop_payload
        coords = self.nlu._extract_coords(command)
        if not coords:
            return {"no_coords": True}
        m = {"x": coords["x"], "y": coords["y"]}
        if "altitude" in coords:
            m["altitude"] = coords["altitude"]
        return m

    def _handle_help(self, command: str, mission) -> Dict[str, Any]:
        state = self.sim.get_state()
        if mission.get("no_coords"):
            # Koordinat bekle: sonraki mesajı bu görevin cevabı say.
            self.pending = {"kind": "help_coords"}
            msg = ("Yardım çağrısını aldım. Hangi koordinata gideyim? "
                   "(ör. '30, 40' veya 'x 30 y 40')")
            self.logger.log(command, "help_mission", {}, "clarify", False, msg,
                            state.to_dict())
            return self._reply(command, "clarify", "clarify", False, msg,
                               state.to_dict())
        x, y = mission["x"], mission["y"]
        alt = mission.get("altitude")
        if not state.in_air and alt is None:
            # Sohbet gibi irtifayı sor, görevi hatırla.
            self.pending = {"kind": "help_altitude", "x": x, "y": y}
            msg = (f"🆘 Yardım çağrısı alındı — ({x}, {y}) noktasına yardıma "
                   f"gidiyorum. Kaç metre irtifaya kalkayım? (ör. '20 metre')")
            self.logger.log(command, "help_mission", {"x": x, "y": y},
                            "clarify", False, msg, state.to_dict())
            return self._reply(command, "clarify", "clarify", False, msg,
                               state.to_dict())
        return self._execute_help(command, x, y, altitude=alt)

    def _try_resolve_pending(self, command: str):
        p = self.pending or {}
        low = self.nlu._norm(command)
        if any(w in low for w in ("iptal", "vazgec", "cancel", "bosver",
                                  "birak gitsin")):
            self.pending = None
            msg = "İşlem iptal edildi."
            return self._reply(command, "clarify", "clarify", False, msg,
                               self.sim.get_state().to_dict())
        # Basit sayı/konum yanıtı bekleyen soruların (kalkış irtifası, hedef
        # konumu, hareket miktarı) çözümü — sohbet gibi.
        parsed = self._safe_interpret(command)
        answers_only = parsed.kind != "tool_call"
        if p.get("kind") == "takeoff_altitude":
            alt = self.nlu._extract_altitude(command)
            if alt is not None and answers_only:
                self.pending = None
                return self._handle_single(f"{alt} metreye kalk")
            return None
        if p.get("kind") == "goto_coords":
            coords = self.nlu._extract_coords(command)
            if coords and answers_only:
                self.pending = None
                cmd = f"{coords['x']}, {coords['y']} noktasına git"
                if "altitude" in coords:
                    cmd += f" {coords['altitude']} metrede"
                return self._handle_single(cmd)
            return None
        if p.get("kind") == "move_amount":
            amt = self.nlu._extract_altitude(command)
            if amt is not None and answers_only:
                self.pending = None
                return self._handle_single(f"{p.get('orig', '')} {command}")
            return None
        if p.get("kind") == "help_coords":
            coords = self.nlu._extract_coords(command)
            if coords:
                self.pending = None
                mission = {"x": coords["x"], "y": coords["y"]}
                if "altitude" in coords:
                    mission["altitude"] = coords["altitude"]
                return self._handle_help(command, mission)
            return None  # koordinat değilse bekleyeni bırak, normal işle
        if p.get("kind") == "help_altitude":
            alt = self.nlu._extract_altitude(command)
            parsed = self._safe_interpret(command)
            # Sadece 'sayı/irtifa' içeren, başka bir aksiyon fiili OLMAYAN yanıt
            # (ör. '20', '20 metre') irtifa cevabı sayılır.
            if alt is not None and parsed.kind != "tool_call":
                self.pending = None
                return self._execute_help(command, p["x"], p["y"], alt)
        return None

    def _execute_help(self, command: str, x, y, altitude) -> Dict[str, Any]:
        """Yardım görevini yürütür: (gerekirse) kalkış -> hedefe git -> yardım
        paketi bırak. Sohbet tarzı, tek bir anlatımlı yanıt döndürür."""
        steps = []
        st = self.sim.get_state()
        if not st.in_air:
            res = self.tools.dispatch("takeoff", {"altitude": altitude})
            steps.append(("takeoff", res))
            if not res["success"]:
                return self._finish_help(command, x, y, steps)
        res = self.tools.dispatch("go_to", {"x": x, "y": y})
        steps.append(("go_to", res))
        if res["success"]:
            res2 = self.tools.dispatch("drop_payload", {"label": "yardım paketi"})
            steps.append(("drop_payload", res2))
        return self._finish_help(command, x, y, steps)

    def _finish_help(self, command, x, y, steps) -> Dict[str, Any]:
        ok = all(r["success"] for _, r in steps)
        head = (f"🚁 Anlaşıldı — ({x}, {y}) noktasına yardıma gidiyorum."
                if ok else
                f"⚠️ ({x}, {y}) yardım görevi tamamlanamadı:")
        body = []
        for action, res in steps:
            mark = "✅" if res["success"] else "⛔"
            text = (self._humanize(action, res) if res["success"]
                    else res["message"])
            body.append(f"  {mark} {text}")
        last_tele = steps[-1][1]["telemetry"] if steps else \
            self.sim.get_state().to_dict()
        reply = head + "\n" + "\n".join(body)
        failsafe = self._failsafe_rth_note()
        if failsafe:
            reply += "\n" + failsafe
            last_tele = self.sim.get_state().to_dict()
        else:
            suggestion = self.tools.safety.rth_suggestion(self.sim.get_state())
            if suggestion:
                reply += "\n" + suggestion
        decision = "approved" if ok else "rejected"
        self.logger.log(command, "help_mission", {"x": x, "y": y}, decision,
                        ok, reply.replace("\n", " | "), last_tele)
        return self._reply(command, "help_mission", decision, ok, reply,
                           last_tele)

    # ------------------------------------------------------------------ #
    # Gözlem/yörünge görevi (özgün, bileşik komut)
    # ------------------------------------------------------------------ #
    def _detect_observe_mission(self, command: str):
        """Komut bir 'gözlem/dolaş/tur at' görevi mi? Öyleyse merkez, yarıçap,
        tur, seyir irtifası, gözlem irtifası ve eve-dönüş bilgisini çıkarır."""
        import re as _re
        t = self.nlu._norm(command)
        if not self.nlu._has(f" {t} ", self.nlu.OBSERVE_KW):
            return None
        # Bir daire/tur ipucu (çap/yarıçap/tur/etraf) olsun ki yanlış tetiklemesin
        if not _re.search(r"\bcap|yaricap|\btur\b|etraf|cevre|daire|cember", t):
            if "gozlem" not in t and "orbit" not in t and "kesif" not in t:
                return None
        coords = self.nlu._extract_coords(command)
        if not coords:
            return {"no_coords": True}
        # Çap -> yarıçap (öncelik çap; yoksa yarıçap; yoksa varsayılan 5)
        radius = None
        m = _re.search(r"(\d+(?:[.,]\d+)?)\s*(?:m|metre)?\s*(?:lik\s*)?cap", t)
        if m:
            radius = float(m.group(1).replace(",", ".")) / 2.0
        else:
            m = _re.search(r"yaricap\D{0,8}(\d+(?:[.,]\d+)?)"
                           r"|(\d+(?:[.,]\d+)?)\s*(?:m|metre)?\s*yaricap", t)
            if m:
                radius = float((m.group(1) or m.group(2)).replace(",", "."))
        if radius is None:
            radius = 5.0
        # Tur sayısı
        laps = 1
        m = _re.search(r"(\d+)\s*tur", t)
        if m:
            laps = int(m.group(1))
        # İrtifalar: 'N metre yüksek...' geçenleri topla -> seyir=max, gözlem=min
        alts = [float(a.replace(",", ".")) for a in
                _re.findall(r"(\d+(?:[.,]\d+)?)\s*(?:m|metre)\s*yuksek", t)]
        cruise = max(alts) if alts else None
        observe_alt = min(alts) if alts else None
        return_home = bool(_re.search(r"baslangic|eve don|geri don|kalkis "
                                      r"noktas|basladigi", t))
        return {"x": coords["x"], "y": coords["y"], "radius": round(radius, 2),
                "laps": laps, "cruise": cruise, "observe_alt": observe_alt,
                "return_home": return_home}

    def _execute_observe(self, command: str, m) -> Dict[str, Any]:
        if m.get("no_coords"):
            msg = ("Gözlem için merkez koordinatı gerekli (ör. '12, 23 "
                   "noktasını 10 metre çapında dolaşıp gözlemle').")
            self.logger.log(command, "observe_mission", {}, "clarify", False,
                            msg, self.sim.get_state().to_dict())
            return self._reply(command, "clarify", "clarify", False, msg,
                               self.sim.get_state().to_dict())
        x, y = m["x"], m["y"]
        cruise = m.get("cruise")
        observe_alt = m.get("observe_alt")
        radius, laps = m["radius"], m["laps"]
        steps = []
        st = self.sim.get_state()
        # 0) Gerekliyse seyir irtifasına kalkış
        if not st.in_air:
            alt = cruise or observe_alt or 30.0
            cruise = cruise or alt
            steps.append(("takeoff",
                          self.tools.dispatch("takeoff", {"altitude": alt})))
            if not steps[-1][1]["success"]:
                return self._finish_observe(command, x, y, radius, laps, steps)
        if cruise is None:
            cruise = round(self.sim.get_state().altitude, 2) or 30.0
        # 1) Seyir irtifasında merkeze git (engelden dolaşarak)
        steps.append(("go_to",
                      self.tools.dispatch("go_to", {"x": x, "y": y,
                                                    "altitude": cruise})))
        if steps[-1][1]["success"]:
            # 2) Gözlem: (gerekliyse) alçal + daire çiz
            steps.append(("observe",
                          self.tools.dispatch("observe",
                                              {"x": x, "y": y, "radius": radius,
                                               "laps": laps,
                                               "altitude": observe_alt})))
        if steps[-1][1]["success"] and observe_alt is not None \
                and cruise is not None and cruise != observe_alt:
            # 3) Tekrar seyir irtifasına yüksel (merkez üstünde)
            steps.append(("go_to",
                          self.tools.dispatch("go_to", {"x": x, "y": y,
                                                        "altitude": cruise})))
        if steps[-1][1]["success"] and m.get("return_home"):
            # 4) Başlangıç noktasına dön
            steps.append(("return_to_home",
                          self.tools.dispatch("return_to_home", {})))
        return self._finish_observe(command, x, y, radius, laps, steps)

    def _finish_observe(self, command, x, y, radius, laps, steps):
        ok = all(r["success"] for _, r in steps)
        head = (f"🔭 Gözlem görevi — ({x}, {y}) çevresinde {radius} m yarıçapla "
                f"{laps} tur." if ok else
                f"⚠️ ({x}, {y}) gözlem görevi tamamlanamadı:")
        body = []
        for action, res in steps:
            mark = "✅" if res["success"] else "⛔"
            text = (self._humanize(action, res) if res["success"]
                    else res["message"])
            body.append(f"  {mark} {text}")
        last_tele = steps[-1][1]["telemetry"] if steps else \
            self.sim.get_state().to_dict()
        reply = head + "\n" + "\n".join(body)
        failsafe = self._failsafe_rth_note()
        if failsafe:
            reply += "\n" + failsafe
            last_tele = self.sim.get_state().to_dict()
        decision = "approved" if ok else "rejected"
        self.logger.log(command, "observe_mission",
                        {"x": x, "y": y, "radius": radius, "laps": laps},
                        decision, ok, reply.replace("\n", " | "), last_tele)
        return self._reply(command, "observe_mission", decision, ok, reply,
                           last_tele)

    def _split_steps(self, command: str):
        # 1) Açık ayraçlar: virgül (koordinat hariç), noktalı virgül, 've',
        #    'sonra', 'ardından', 'then'...
        raw = [p.strip() for p in self.nlu.STEP_SEPARATORS.split(command)
               if p.strip()]
        # 2) Her parçayı ÖRTÜK fiil sınırlarından ayrıca böl ('ve' olmasa da):
        #    'X kalk Y git' -> ['X kalk', 'Y git'].
        segments = []
        for piece in raw:
            segments.extend(self._implicit_segments(piece))
        segments = [s.strip() for s in segments if s.strip()]
        if len(segments) < 2:
            return [command]
        intents = [self._safe_interpret(p) for p in segments]
        tool_calls = [i for i in intents if i.kind == "tool_call"]
        distinct = {i.action for i in tool_calls}
        if len(tool_calls) >= 2 and len(distinct) >= 2:
            return segments
        return [command]

    def _implicit_segments(self, piece: str):
        """Tek bir cümleyi, fiil çıpalarından (kalk/git/dön/bırak...) ardışık
        adımlara böler — açık ayraç ('ve', virgül) olmasa da. Türkçe komutlar
        fiil-son olduğundan, çıpa TOKEN'INDAN SONRA yeni adım başlar. Bir çıpadan
        az varsa parça olduğu gibi döner (yanlış bölmeyi önler)."""
        toks = piece.split()
        if len(toks) < 3:
            return [piece]
        norm = [self.nlu._norm(tok.strip(".,!?;:")) for tok in toks]
        anchors = [i for i, n in enumerate(norm)
                   if n in self.nlu.STEP_ANCHORS]
        if len(anchors) < 2:
            return [piece]
        segs, start = [], 0
        for a in anchors:
            segs.append(" ".join(toks[start:a + 1]))
            start = a + 1
        # Son çıpadan sonra kalan (fiilsiz) artık atılır; geçerli komut fiille
        # biter. Böylece 'git 35,20' gibi tek-adımlar bozulmaz.
        return [s for s in segs if s.strip()]

    def _safe_interpret(self, command: str) -> Intent:
        try:
            return self._interpret(command)
        except Exception:
            return Intent("unknown", {}, "unknown", note="Ayrıştırılamadı.")

    def _handle_plan(self, command: str, parts) -> Dict[str, Any]:
        lines = [f"Çok-adımlı görev planı ({len(parts)} adım):"]
        all_ok = True
        last_telemetry = self.sim.get_state().to_dict()
        failsafe_hit = False
        for idx, part in enumerate(parts, 1):
            step = self._handle_single(part, plan_step=True)
            last_telemetry = step["telemetry"]
            mark = {"approved": "OK", "rejected": "RED",
                    "clarify": "?", "error": "!"}.get(step["decision"], "-")
            lines.append(f"  {idx}. [{mark}] {part} -> {step['reply']}")
            if step["decision"] != "approved":
                all_ok = False
            # Her adımdan sonra FAIL-SAFE denetimi: batarya kritikse kalan
            # adımları iptal edip otomatik eve dön.
            failsafe = self._failsafe_rth_note()
            if failsafe:
                lines.append(f"  {failsafe} Kalan adımlar iptal edildi.")
                last_telemetry = self.sim.get_state().to_dict()
                failsafe_hit = True
                break
        if not failsafe_hit:
            suggestion = self.tools.safety.rth_suggestion(self.sim.get_state())
            if suggestion:
                lines.append(suggestion)
        decision = "approved" if all_ok else "rejected"
        self.logger.log(command, "mission_plan", {"steps": parts}, decision,
                        all_ok, "; ".join(parts), last_telemetry)
        return self._reply(command, "mission_plan", decision, all_ok,
                           "\n".join(lines), last_telemetry)

    def _failsafe_rth_note(self) -> Optional[str]:
        """FAIL-SAFE: batarya kritik eşiğe indiyse ve drone havadaysa OTOMATİK
        eve dönüşü UYGULAR ve açıklayıcı bir not döndürür (yoksa None). Bu bir
        öneri değil, zorunlu güvenlik davranışıdır."""
        st = self.sim.get_state()
        if not (st.in_air and 0 < st.battery <= FAILSAFE_RTH_BATTERY):
            return None
        at_home = (abs(st.x - st.home_x) < 1e-6
                   and abs(st.y - st.home_y) < 1e-6)
        if at_home:
            return None
        bat = st.battery
        res = self.tools.dispatch("return_to_home", {})
        if res["success"]:
            return (f"🔋 FAIL-SAFE: Batarya kritik seviyede (%{bat:.0f}); "
                    f"güvenlik protokolü devreye girdi, görev durduruldu ve "
                    f"OTOMATİK EVE DÖNÜŞ yapıldı.")
        return (f"🔋 FAIL-SAFE UYARISI: Batarya kritik (%{bat:.0f}) fakat "
                f"otomatik eve dönüş uygulanamadı: {res['message']}")

    def _handle_single(self, command: str,
                       plan_step: bool = False) -> Dict[str, Any]:
        try:
            intent = self._interpret(command)
        except Exception as exc:
            self.logger.log(command, "error", {}, "error", False, str(exc))
            return self._reply(command, "error", "error", False,
                               f"Komut işlenirken hata oluştu: {exc}", {})

        if intent.kind == "clarify":
            # Sohbet hafızası: belirli bir yanıt bekleyen soruysa (irtifa/konum/
            # miktar), sonraki mesajı bunun cevabı sayabilmek için hatırla.
            if not plan_step and intent.await_kind:
                self.pending = {"kind": intent.await_kind, "orig": command}
            self.logger.log(command, "clarify", intent.args, "clarify", False,
                            intent.note, self.sim.get_state().to_dict())
            return self._reply(command, "clarify", "clarify", False,
                               intent.note, self.sim.get_state().to_dict())
        if intent.kind == "unknown":
            self.logger.log(command, "unknown", intent.args, "rejected", False,
                            intent.note, self.sim.get_state().to_dict())
            return self._reply(command, "unknown", "rejected", False,
                               intent.note, self.sim.get_state().to_dict())

        result = self.tools.dispatch(intent.action, intent.args)
        decision = "approved" if result["success"] else "rejected"
        reply_text = self._humanize(intent.action, result)

        telemetry = result["telemetry"]
        if not plan_step:
            failsafe = self._failsafe_rth_note()
            if failsafe:
                reply_text = f"{reply_text}\n{failsafe}"
                telemetry = self.sim.get_state().to_dict()
            else:
                suggestion = self.tools.safety.rth_suggestion(
                    self.sim.get_state())
                if suggestion:
                    reply_text = f"{reply_text}\n{suggestion}"

        self.logger.log(command, intent.action, intent.args, decision,
                        result["success"], result["message"], telemetry)
        return self._reply(command, intent.action, decision,
                           result["success"], reply_text, telemetry)

    # ------------------------------------------------------------------ #
    def _humanize(self, action: str, result: Dict[str, Any]) -> str:
        tele = result.get("telemetry", {})
        if not result["success"]:
            return result["message"]
        if action == "get_telemetry":
            return (
                f"Telemetri — Konum: (x={tele['x']} m, y={tele['y']} m), "
                f"İrtifa: {tele['altitude']} m, Mod: {tele['mode']}, "
                f"Batarya: %{tele['battery']:.0f}, "
                f"Havada: {'Evet' if tele['in_air'] else 'Hayır'}."
            )
        if action == "takeoff":
            return (f"Kalkış tamamlandı. Drone {tele['altitude']} m irtifada "
                    f"havada bekliyor (batarya %{tele['battery']:.0f}).")
        if action == "land":
            return (f"İniş tamamlandı. Drone yerde ({tele['mode']}), "
                    f"batarya %{tele['battery']:.0f}.")
        if action == "return_to_home":
            hint = (" '🔋 şarj et' diyerek bataryayı doldurabilirsiniz."
                    if tele['battery'] < 99.5 else "")
            return (f"Eve dönüş tamamlandı; drone başlangıç noktasına inip "
                    f"durdu (batarya %{tele['battery']:.0f}).{hint}")
        if action == "go_to":
            detour = result.get("detour")
            prefix = ""
            if detour:
                prefix = (f"Rota üzerindeki engel(ler) {detour} ara nokta ile "
                          f"otonom olarak aşıldı. ")
            return (f"{prefix}Hedefe ulaşıldı. Konum: (x={tele['x']} m, "
                    f"y={tele['y']} m), İrtifa: {tele['altitude']} m "
                    f"(batarya %{tele['battery']:.0f}).")
        if action == "go_to_previous":
            detour = result.get("detour")
            prefix = ""
            if detour:
                prefix = (f"Rota üzerindeki engel(ler) {detour} ara nokta ile "
                          f"otonom olarak aşıldı. ")
            return (f"{prefix}Önceki konuma geri dönüldü. Konum: "
                    f"(x={tele['x']} m, y={tele['y']} m), İrtifa: "
                    f"{tele['altitude']} m (batarya %{tele['battery']:.0f}).")
        if action == "move":
            return (f"Hareket tamamlandı. Yeni konum: (x={tele['x']} m, "
                    f"y={tele['y']} m), İrtifa: {tele['altitude']} m "
                    f"(batarya %{tele['battery']:.0f}).")
        if action == "get_energy_status":
            e = tele.get("energy", {})
            rth = ("Evet, eve güvenle dönebilir."
                   if e.get("can_return_home") else
                   "HAYIR — eve güvenli dönüş için batarya riskli!")
            return (f"Enerji durumu — Batarya %{e.get('battery')}, "
                    f"tahmini kalan menzil ~{e.get('range_m')} m "
                    f"(%{e.get('reserve')} rezerv ayrıldı). Eve uzaklık "
                    f"{e.get('dist_home')} m, dönüş maliyeti ~%{e.get('rth_cost_pct')}. "
                    f"{rth}")
        return result["message"]

    def _reply(self, command, action, decision, success, reply, telemetry):
        return {
            "command": command,
            "action": action,
            "decision": decision,
            "success": success,
            "reply": reply,
            "telemetry": telemetry,
        }
