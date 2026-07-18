"""
tools.py
========
Araç Fonksiyonları (Tool Layer).

LLM ajanının tetikleyebileceği TEK arayüz burasıdır. Her fonksiyon:
    1. Güvenlik katmanından (SafetyLayer) geçer,
    2. Onaylanırsa simülasyonun düşük seviyeli fonksiyonlarını çağırır,
    3. Standart bir sonuç sözlüğü döndürür.

LLM asla PWM, ham hız veya roll/pitch/yaw gibi düşük seviyeli kontrollere
erişemez; yalnızca bu güvenli fonksiyonları çağırabilir.
"""

from __future__ import annotations

import math
from typing import Any, Dict

from .simulation import DroneSimulator
from .safety import SafetyLayer, MAX_HORIZONTAL_RANGE


class ToolResult(dict):
    """Tool çağrılarının standart sonuç yapısı (dict alt sınıfı)."""

    @classmethod
    def make(cls, action: str, success: bool, message: str,
             telemetry: Dict[str, Any] | None = None) -> "ToolResult":
        return cls(
            action=action,
            success=success,
            message=message,
            telemetry=telemetry or {},
        )


class DroneTools:
    """
    Güvenli araç fonksiyonlarını barındıran sınıf.

    Ajan bu sınıfın metotlarını çağırır; her metot güvenlik katmanını
    otomatik olarak uygular.
    """

    def __init__(self, simulator: DroneSimulator):
        self.sim = simulator
        self.safety = SafetyLayer(simulator)

    def _prev_snapshot(self):
        """Hareketten ÖNCEKİ konumun anlık görüntüsü (x, y, irtifa)."""
        s = self.sim.state
        return (round(s.x, 2), round(s.y, 2), round(s.altitude, 2))

    # ------------------------------------------------------------------ #
    def _run(self, action: str, args: Dict[str, Any], executor) -> ToolResult:
        decision = self.safety.validate(action, args)
        if not decision.approved:
            return ToolResult.make(
                action, False, f"REDDEDİLDİ: {decision.reason}",
                self.sim.get_state().to_dict(),
            )
        safe_args = decision.sanitized_args or args
        executor(safe_args)
        return ToolResult.make(
            action, True, decision.reason, self.sim.get_state().to_dict()
        )

    # ------------------------------------------------------------------ #
    # Güvenli fonksiyonlar
    # ------------------------------------------------------------------ #
    def get_telemetry(self, **args) -> ToolResult:
        """Anlık telemetriyi döndürür (durum sorgulama)."""
        decision = self.safety.validate("get_telemetry", args)
        state = self.sim.get_state().to_dict()
        return ToolResult.make(
            "get_telemetry", decision.approved, decision.reason, state
        )

    def takeoff(self, altitude: float | None = None, **_) -> ToolResult:
        """Belirtilen irtifaya güvenli kalkış."""
        return self._run(
            "takeoff",
            {"altitude": altitude},
            lambda a: self.sim._takeoff(a["altitude"]),
        )

    def land(self, **_) -> ToolResult:
        """Güvenli iniş."""
        return self._run("land", {}, lambda a: self.sim._land())

    def return_to_home(self, **_) -> ToolResult:
        """Eve dönüş (Return-To-Home) ve güvenli iniş."""
        snap = self._prev_snapshot()
        res = self._run(
            "return_to_home", {}, lambda a: self.sim._return_to_home()
        )
        if res["success"]:
            self.sim.previous_position = snap
        return res

    def go_to(self, x=None, y=None, altitude=None, **_) -> ToolResult:
        """Belirtilen (x, y[, irtifa]) konumuna güvenli gidiş. Doğrudan yol bir
        engel/yasak bölgeden geçiyorsa OTONOM olarak ara noktalarla dolaşır."""
        args = {"x": x, "y": y, "altitude": altitude}
        decision = self.safety.validate("go_to", args)
        if not decision.approved:
            return ToolResult.make(
                "go_to", False, f"REDDEDİLDİ: {decision.reason}",
                self.sim.get_state().to_dict())
        a = decision.sanitized_args or args
        snap = self._prev_snapshot()
        route = a.get("route") or [(a["x"], a["y"])]
        for i, wp in enumerate(route):
            last = (i == len(route) - 1)
            self.sim._go_to(wp[0], wp[1], a.get("altitude") if last else None)
        self.sim.previous_position = snap
        res = ToolResult.make("go_to", True, decision.reason,
                              self.sim.get_state().to_dict())
        if len(route) > 1:
            res["detour"] = len(route) - 1
        return res

    def go_to_previous(self, **_) -> ToolResult:
        """Hareketten önceki konuma güvenle geri döner (engel varsa dolaşarak).
        Art arda çağrılırsa iki nokta arasında gidip gelir (toggle)."""
        st = self.sim.get_state()
        prev = getattr(self.sim, "previous_position", None)
        if not st.in_air:
            return ToolResult.make(
                "go_to_previous", False,
                "REDDEDİLDİ: Önceki konuma dönüş için drone havada olmalıdır.",
                st.to_dict())
        if prev is None:
            return ToolResult.make(
                "go_to_previous", False,
                "REDDEDİLDİ: Kayıtlı bir önceki konum yok (henüz hareket "
                "edilmedi).", st.to_dict())
        px, py, palt = prev
        # self.go_to, mevcut konumu yeni 'önceki konum' olarak kaydeder (toggle)
        nav = self.go_to(x=px, y=py, altitude=(palt if palt and palt > 0
                                               else None))
        out = ToolResult.make("go_to_previous", nav["success"], nav["message"],
                              nav["telemetry"])
        if nav.get("detour"):
            out["detour"] = nav["detour"]
        return out

    def move(self, dx=0.0, dy=0.0, dz=0.0, **_) -> ToolResult:
        """Göreli hareket: sağ/sol (dx), ileri/geri (dy), yukarı/aşağı (dz)."""
        snap = self._prev_snapshot()
        res = self._run(
            "move",
            {"dx": dx, "dy": dy, "dz": dz},
            lambda a: self.sim._move(a.get("dx", 0.0), a.get("dy", 0.0),
                                     a.get("dz", 0.0)),
        )
        if res["success"]:
            self.sim.previous_position = snap
        return res

    def observe(self, x=None, y=None, radius=5.0, laps=1, altitude=None,
                **_) -> ToolResult:
        """Bir noktanın etrafında dairesel GÖZLEM yörüngesi uçar. Önce (engelden
        dolaşarak) merkeze/irtifaya gider, sonra verilen yarıçapta 'laps' tur
        atarak alanı gözlemler. Özgün keşif/gözetleme yeteneği."""
        st = self.sim.get_state()
        if not st.in_air:
            return ToolResult.make(
                "observe", False,
                "REDDEDİLDİ: Gözlem için drone havada olmalıdır (kalkış yapın).",
                st.to_dict())
        try:
            cx, cy = float(x), float(y)
            r = abs(float(radius)) or 5.0
            n = max(1, int(round(float(laps))))
        except (TypeError, ValueError):
            return ToolResult.make(
                "observe", False,
                "REDDEDİLDİ: Geçersiz gözlem parametresi (merkez/yarıçap/tur).",
                st.to_dict())
        if abs(cx) > MAX_HORIZONTAL_RANGE or abs(cy) > MAX_HORIZONTAL_RANGE:
            return ToolResult.make(
                "observe", False,
                f"REDDEDİLDİ: Gözlem merkezi çalışma alanı sınırının "
                f"(±{MAX_HORIZONTAL_RANGE} m) dışında.", st.to_dict())
        alt = None
        if altitude is not None:
            try:
                alt = float(altitude)
            except (TypeError, ValueError):
                alt = None
            if alt is not None and (alt <= 0 or alt > self.sim.max_altitude):
                return ToolResult.make(
                    "observe", False,
                    f"REDDEDİLDİ: Gözlem irtifası 0 ile "
                    f"{self.sim.max_altitude} m arasında olmalıdır.",
                    st.to_dict())
        # Merkeze (engelden dolaşarak) git ve gözlem irtifasına in/çık.
        nav = self.go_to(x=cx, y=cy, altitude=alt)
        if not nav["success"]:
            return ToolResult.make(
                "observe", False,
                f"REDDEDİLDİ: Gözlem noktasına gidilemedi — {nav['message']}",
                self.sim.get_state().to_dict())
        self.sim._orbit(cx, cy, r, n)
        self.sim.observe_zone = (round(cx, 2), round(cy, 2), round(r, 2))
        tele = self.sim.get_state().to_dict()
        altmsg = f"{alt:.0f} m irtifada " if alt is not None else ""
        return ToolResult.make(
            "observe", True,
            f"🔭 Gözlem tamamlandı: ({cx:.0f}, {cy:.0f}) çevresinde "
            f"{r:.0f} m yarıçaplı yörüngede {altmsg}{n} tur atıldı "
            f"(batarya %{tele['battery']:.0f}).", tele)

    def recharge(self, amount=None, **_) -> ToolResult:
        """Bataryayı şarj eder. Yalnızca ev noktasında ve yerdeyken; amount
        verilirse o kadar (%) ekler, verilmezse tam doluma getirir."""
        dec = self.safety.validate("recharge", {"amount": amount})
        if not dec.approved:
            return ToolResult.make("recharge", False,
                                   f"REDDEDİLDİ: {dec.reason}",
                                   self.sim.get_state().to_dict())
        amt = None
        if amount is not None:
            try:
                amt = abs(float(amount))
            except (TypeError, ValueError):
                amt = None
        self.sim._recharge(amt)
        tele = self.sim.get_state().to_dict()
        return ToolResult.make(
            "recharge", True,
            f"🔋 Şarj tamamlandı; drone ev istasyonunda. "
            f"Batarya %{tele['battery']:.0f}.", tele)

    def get_energy_status(self, **_) -> ToolResult:
        """Enerji/menzil durumu: kalan menzil ve eve güvenli dönüş bilgisi."""
        es = self.safety.energy_status(self.sim.get_state())
        tele = self.sim.get_state().to_dict()
        tele = dict(tele)
        tele["energy"] = es
        return ToolResult.make("get_energy_status", True,
                               "Enerji durumu hesaplandı.", tele)

    def avoid_obstacle(self, distance=None, **_) -> ToolResult:
        """Otonom engel kaçınma. distance verilirse drone'un önüne (+y) dinamik
        bir engel ekler, sonra güvenli kaçınma kararı verir ve uygular."""
        dec = self.safety.validate("avoid_obstacle", {})
        if not dec.approved:
            return ToolResult.make("avoid_obstacle", False,
                                   f"REDDEDİLDİ: {dec.reason}",
                                   self.sim.get_state().to_dict())
        st = self.sim.get_state()
        if distance is not None:
            try:
                d = float(distance)
                self.sim.add_obstacle(round(st.x, 2), round(st.y + d, 2), 2.0,
                                      "algilanan engel")
            except (TypeError, ValueError):
                pass
        plan = self.safety.plan_avoidance(self.sim.get_state())
        if plan["decision"] == "avoid":
            dx, dy = plan["dx"], plan["dy"]
            tx, ty = st.x + dx, st.y + dy
            safe = all(math.hypot(tx - k.x, ty - k.y) > k.radius
                       for k in self.sim.keepouts)
            if safe:
                self.sim._move(dx, dy, 0.0)
                return ToolResult.make(
                    "avoid_obstacle", True,
                    f"OTONOM KAÇINMA: {plan['reason']} Yeni konum güvenli.",
                    self.sim.get_state().to_dict())
            return ToolResult.make(
                "avoid_obstacle", True,
                f"Güvenli kaçış yönü bulunamadı; pozisyon korunuyor (hover). "
                f"({plan['reason']})", self.sim.get_state().to_dict())
        return ToolResult.make("avoid_obstacle", True, plan["reason"],
                               self.sim.get_state().to_dict())

    def drop_payload(self, x=None, y=None, label=None, **_) -> ToolResult:
        """Destek/kargo paketi bırakma. Koordinat verilirse önce oraya güvenle
        gider (rota güvenlik denetiminden geçer), sonra paketi bırakır. Koordinat
        yoksa drone'un bulunduğu konuma bırakır. Özgün yetenek."""
        dec = self.safety.validate(
            "drop_payload", {"x": x, "y": y, "label": label})
        if not dec.approved:
            return ToolResult.make("drop_payload", False,
                                   f"REDDEDİLDİ: {dec.reason}",
                                   self.sim.get_state().to_dict())
        a = dec.sanitized_args or {}
        lbl = a.get("label") or "destek paketi"
        # Koordinat verildiyse ve farklıysa önce oraya git (engelden OTONOM
        # dolaşarak). go_to başarısız olursa bırakma iptal edilir.
        if a.get("x") is not None and a.get("y") is not None:
            cur = (round(self.sim.state.x, 2), round(self.sim.state.y, 2))
            if (round(a["x"], 2), round(a["y"], 2)) != cur:
                nav = self.go_to(x=a["x"], y=a["y"])
                if not nav["success"]:
                    return ToolResult.make(
                        "drop_payload", False,
                        f"REDDEDİLDİ: bırakma noktasına gidilemedi — "
                        f"{nav['message']}", self.sim.get_state().to_dict())
        self.sim._drop_payload(lbl)
        st = self.sim.get_state().to_dict()
        return ToolResult.make(
            "drop_payload", True,
            f"📦 Kargo bölmesi açıldı; '{lbl}' (x={st['x']} m, y={st['y']} m) "
            f"konumuna bırakıldı. Kalan yük: {st.get('payloads_remaining')} "
            f"paket.", st)

    # ------------------------------------------------------------------ #
    # Ajan/LLM için tool şeması (tool-calling formatı)
    # ------------------------------------------------------------------ #
    @staticmethod
    def get_tool_schema() -> list:
        """OpenAI/Anthropic tool-calling formatına uygun şema."""
        return [
            {
                "name": "get_telemetry",
                "description": "Drone'un anlık telemetrisini (konum, irtifa, "
                               "batarya, mod, havada mı) döndürür.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "takeoff",
                "description": "Drone'u belirtilen irtifaya kaldırır.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "altitude": {
                            "type": "number",
                            "description": "Hedef irtifa (metre). Zorunlu.",
                        }
                    },
                    "required": ["altitude"],
                },
            },
            {
                "name": "land",
                "description": "Drone'u bulunduğu konumda güvenle indirir.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "return_to_home",
                "description": "Drone'u kalkış (ev) noktasına döndürür ve "
                               "indirir.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "go_to",
                "description": "Drone'u belirtilen (x, y) konumuna, isteğe "
                               "bağlı bir irtifaya götürür. Havada olmalıdır.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number", "description": "Hedef x (m)."},
                        "y": {"type": "number", "description": "Hedef y (m)."},
                        "altitude": {
                            "type": "number",
                            "description": "İsteğe bağlı hedef irtifa (m).",
                        },
                    },
                    "required": ["x", "y"],
                },
            },
            {
                "name": "move",
                "description": "Drone'u göreli hareket ettirir: dx sağ(+)/sol(-), "
                               "dy ileri(+)/geri(-), dz yukarı(+)/aşağı(-) (metre). "
                               "Havada olmalıdır.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dx": {"type": "number", "description": "Sağ(+)/sol(-) m."},
                        "dy": {"type": "number", "description": "İleri(+)/geri(-) m."},
                        "dz": {"type": "number", "description": "Yukarı(+)/aşağı(-) m."},
                    },
                },
            },
            {
                "name": "get_energy_status",
                "description": "Kalan menzil, tahmini kullanılabilir mesafe ve "
                               "eve güvenle dönülüp dönülemeyeceğini döndürür.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "avoid_obstacle",
                "description": "Engel algılandığında otonom güvenli kaçınma "
                               "kararı verir (uzaklaş veya hover). Bir engel "
                               "mesafesi verilebilir.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "distance": {
                            "type": "number",
                            "description": "Algılanan engelin öndeki uzaklığı "
                                           "(m, opsiyonel).",
                        },
                    },
                },
            },
            {
                "name": "go_to_previous",
                "description": "Drone'u hareketten önceki konumuna geri "
                               "götürür ('önceki/eski konuma dön'). Havada "
                               "olmalıdır; parametre almaz.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "observe",
                "description": "Bir (x, y) noktasının etrafında dairesel gözlem "
                               "yörüngesi uçar. radius=yarıçap (m), laps=tur "
                               "sayısı, altitude=gözlem irtifası (m, opsiyonel). "
                               "Havada olmalıdır.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number", "description": "Merkez x (m)."},
                        "y": {"type": "number", "description": "Merkez y (m)."},
                        "radius": {"type": "number",
                                   "description": "Yörünge yarıçapı (m)."},
                        "laps": {"type": "number",
                                 "description": "Tur sayısı."},
                        "altitude": {"type": "number",
                                     "description": "Gözlem irtifası (m, ops.)."},
                    },
                    "required": ["x", "y"],
                },
            },
            {
                "name": "recharge",
                "description": "Bataryayı şarj eder. Yalnızca drone yerde ve "
                               "başlangıç (ev) noktasındayken çalışır. amount "
                               "verilmezse tam doluma (%100) getirir.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "amount": {"type": "number",
                                   "description": "Eklenecek şarj yüzdesi "
                                                  "(opsiyonel)."},
                    },
                },
            },
            {
                "name": "drop_payload",
                "description": "Destek/kargo paketi bırakır. İsteğe bağlı (x, y) "
                               "verilirse önce oraya güvenle gider, sonra bırakır; "
                               "verilmezse mevcut konuma bırakır. Havada olmalı ve "
                               "kargo bölmesinde yük bulunmalıdır.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number",
                              "description": "Bırakma x (m, opsiyonel)."},
                        "y": {"type": "number",
                              "description": "Bırakma y (m, opsiyonel)."},
                        "label": {"type": "string",
                                  "description": "Paket etiketi (opsiyonel)."},
                    },
                },
            },
        ]

    def dispatch(self, action: str, args: Dict[str, Any]) -> ToolResult:
        """Aksiyon adına göre ilgili tool fonksiyonunu çağırır."""
        args = args or {}
        if action == "get_telemetry":
            return self.get_telemetry(**args)
        if action == "takeoff":
            return self.takeoff(**args)
        if action == "land":
            return self.land(**args)
        if action == "return_to_home":
            return self.return_to_home(**args)
        if action == "go_to":
            return self.go_to(**args)
        if action == "go_to_previous":
            return self.go_to_previous(**args)
        if action == "observe":
            return self.observe(**args)
        if action == "recharge":
            return self.recharge(**args)
        if action == "move":
            return self.move(**args)
        if action == "get_energy_status":
            return self.get_energy_status(**args)
        if action == "avoid_obstacle":
            return self.avoid_obstacle(**args)
        if action == "drop_payload":
            return self.drop_payload(**args)
        return ToolResult.make(
            action, False, f"REDDEDİLDİ: Bilinmeyen aksiyon '{action}'.",
            self.sim.get_state().to_dict(),
        )
