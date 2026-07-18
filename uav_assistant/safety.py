"""
safety.py
=========
Güvenlik Katmanı (Safety Layer).

LLM / ajan tarafından üretilen yapılandırılmış görev isteklerini (tool call),
GERÇEK simülasyona uygulanmadan ÖNCE kurallarla doğrular. Amaç; güvensiz,
eksik veya mantıksız komutların dronu etkilemesini engellemektir.

Bu katman "son savunma hattıdır": ajan hatalı bir komut üretse bile
simülasyon burada korunur.
"""

from __future__ import annotations

import math

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .simulation import DroneSimulator, FlightMode


# Bataryanın altına düşünce kalkışa izin verilmeyen eşik (%)
MIN_TAKEOFF_BATTERY = 20.0
# Bu değerin altında yalnızca iniş / eve dönüş gibi güvenli manevralara izin
CRITICAL_BATTERY = 10.0
# Kalkışta izin verilen mutlak minimum irtifa (m)
MIN_TAKEOFF_ALTITUDE = 1.0
# Bu değerin altına inince ajan otomatik eve dönüş ÖNERİR (uygulamaz)
LOW_BATTERY_RTH_SUGGEST = 30.0
# Bu değerin altına inince FAIL-SAFE devreye girer: görev durdurulur ve
# otomatik eve dönüş UYGULANIR (öneri değil, zorunlu güvenlik davranışı)
FAILSAFE_RTH_BATTERY = 20.0
# go_to için izin verilen yatay çalışma alanı yarıçapı (m)
MAX_HORIZONTAL_RANGE = 500.0
# Enerji/menzil: güvenli rezerv (%) ve metre başına yaklaşık tüketim (%)
ENERGY_RESERVE = 10.0
BATTERY_PER_METER = 0.05
# Otonom kaçınmada engel etrafında korunacak güvenli tampon (m)
SAFE_BUFFER = 8.0


@dataclass
class SafetyDecision:
    """Güvenlik katmanının bir tool call için verdiği karar."""

    approved: bool
    reason: str
    sanitized_args: Optional[Dict[str, Any]] = None


class SafetyLayer:
    """
    Tool call'ları doğrulayan kural motoru.

    Her `validate` çağrısı bir `SafetyDecision` döndürür; asla doğrudan
    simülasyonu değiştirmez.
    """

    def __init__(self, simulator: DroneSimulator):
        self.sim = simulator

    def validate(self, action: str, args: Dict[str, Any]) -> SafetyDecision:
        args = dict(args or {})
        state = self.sim.get_state()

        handler = {
            "get_telemetry": self._validate_get_telemetry,
            "takeoff": self._validate_takeoff,
            "land": self._validate_land,
            "return_to_home": self._validate_return_to_home,
            "go_to": self._validate_go_to,
            "move": self._validate_move,
            "get_energy_status": self._validate_get_telemetry,
            "avoid_obstacle": self._validate_avoid,
            "drop_payload": self._validate_drop,
            "recharge": self._validate_recharge,
        }.get(action)

        if handler is None:
            return SafetyDecision(
                approved=False,
                reason=f"Bilinmeyen veya desteklenmeyen aksiyon: '{action}'.",
            )
        return handler(args, state)

    # ------------------------------------------------------------------ #
    # Geometri: rota (segment) engel/yasak bölge kesişim denetimi
    # ------------------------------------------------------------------ #
    @staticmethod
    def _seg_point_min_dist(ax, ay, bx, by, cx, cy) -> float:
        """C noktasının AB doğru parçasına en kısa uzaklığı."""
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(cx - ax, cy - ay)
        t = ((cx - ax) * dx + (cy - ay) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        px, py = ax + t * dx, ay + t * dy
        return math.hypot(cx - px, cy - py)

    def _path_blocked(self, x0, y0, x1, y1):
        """Rota bir engel/yasak bölgeden geçiyorsa (KeepOut, mesafe) döner."""
        for k in self.sim.keepouts:
            if self._seg_point_min_dist(x0, y0, x1, y1, k.x, k.y) <= k.radius:
                return k
        return None

    # ------------------------------------------------------------------ #
    # Otonom rota planlama: dairesel engel/yasak bölgeleri etrafından dolaşma
    # ------------------------------------------------------------------ #
    def plan_route(self, x0, y0, x1, y1, depth: int = 0):
        """(x0,y0)'dan (x1,y1)'e, TÜM engel/yasak bölgeleri dışından geçen bir
        ara-nokta listesi üretir (hedef HARİÇ başlangıç, hedef DAHİL). Doğrudan
        yol açıksa [(x1,y1)] döner. Güvenli yol yoksa None döner.

        Yöntem: yolu ilk kesen dairenin merkezine dik yönde (yarıçap+tampon)
        kaydırılmış bir ara nokta seçilir; iki taraf denenir, kısa ve güvenli
        olan özyinelemeli olarak alt-parçalara bölünür (böl-yönet)."""
        if depth > 8:
            return None
        blocker = self._path_blocked(x0, y0, x1, y1)
        if blocker is None:
            return [(round(x1, 2), round(y1, 2))]
        # Hedefin kendisi bir bölgenin içindeyse dolaşmak anlamsız.
        for k in self.sim.keepouts:
            if math.hypot(x1 - k.x, y1 - k.y) <= k.radius + 1e-6:
                return None
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy) or 1e-9
        ux, uy = dx / length, dy / length
        nx, ny = -uy, ux                      # yola dik birim vektör
        clr = blocker.radius + SAFE_BUFFER + 1.0
        best = None
        for sign in (1.0, -1.0):
            wx = round(blocker.x + nx * sign * clr, 2)
            wy = round(blocker.y + ny * sign * clr, 2)
            if abs(wx) > MAX_HORIZONTAL_RANGE or abs(wy) > MAX_HORIZONTAL_RANGE:
                continue
            first = self.plan_route(x0, y0, wx, wy, depth + 1)
            if first is None:
                continue
            second = self.plan_route(wx, wy, x1, y1, depth + 1)
            if second is None:
                continue
            route = first + second
            cost = self._route_length(x0, y0, route)
            if best is None or cost < best[0]:
                best = (cost, route)
        return best[1] if best else None

    @staticmethod
    def _route_length(x0, y0, route) -> float:
        total, px, py = 0.0, x0, y0
        for wx, wy in route:
            total += math.hypot(wx - px, wy - py)
            px, py = wx, wy
        return total

    # ------------------------------------------------------------------ #
    def _validate_get_telemetry(self, args, state) -> SafetyDecision:
        return SafetyDecision(True, "Telemetri okuma güvenli.", args)

    def _validate_takeoff(self, args, state) -> SafetyDecision:
        if state.in_air:
            return SafetyDecision(
                False, "Drone zaten havada; tekrar kalkış reddedildi."
            )
        if state.battery < MIN_TAKEOFF_BATTERY:
            return SafetyDecision(
                False,
                f"Batarya çok düşük (%{state.battery:.0f}). Güvenli kalkış "
                f"için en az %{MIN_TAKEOFF_BATTERY:.0f} gerekir.",
            )
        altitude = args.get("altitude")
        if altitude is None:
            return SafetyDecision(
                False,
                "Kalkış irtifası belirtilmemiş. Varsayım yapılmadı; hedef "
                "irtifa gerekli.",
            )
        try:
            altitude = float(altitude)
        except (TypeError, ValueError):
            return SafetyDecision(False, f"Geçersiz irtifa değeri: {altitude!r}.")
        if altitude <= 0:
            return SafetyDecision(False, "İrtifa pozitif bir değer olmalıdır.")
        if altitude < MIN_TAKEOFF_ALTITUDE:
            return SafetyDecision(
                False,
                f"İrtifa çok düşük ({altitude} m). Minimum "
                f"{MIN_TAKEOFF_ALTITUDE} m olmalıdır.",
            )
        if altitude > self.sim.max_altitude:
            return SafetyDecision(
                False,
                f"İstenen irtifa ({altitude} m) maksimum güvenli sınırı "
                f"({self.sim.max_altitude} m) aşıyor. Komut reddedildi.",
            )
        return SafetyDecision(
            True,
            f"{altitude} m irtifaya güvenli kalkış onaylandı.",
            {"altitude": altitude},
        )

    def _validate_land(self, args, state) -> SafetyDecision:
        if not state.in_air:
            return SafetyDecision(
                False, "Drone zaten yerde; iniş komutu gereksiz."
            )
        return SafetyDecision(True, "İniş onaylandı.", args)

    def _validate_return_to_home(self, args, state) -> SafetyDecision:
        if not state.in_air:
            return SafetyDecision(
                False, "Drone yerde. Eve dönüş için önce havada olması gerekir."
            )
        return SafetyDecision(True, "Eve dönüş (RTH) onaylandı.", args)

    def _validate_go_to(self, args, state) -> SafetyDecision:
        if not state.in_air:
            return SafetyDecision(
                False, "go_to için drone önce havada olmalıdır (kalkış yapın)."
            )
        try:
            x = float(args.get("x"))
            y = float(args.get("y"))
        except (TypeError, ValueError):
            return SafetyDecision(
                False, "Geçersiz veya eksik koordinat (x, y gerekli)."
            )
        altitude = args.get("altitude")
        if altitude is not None:
            try:
                altitude = float(altitude)
            except (TypeError, ValueError):
                return SafetyDecision(False, f"Geçersiz irtifa: {altitude!r}.")
            if altitude <= 0:
                return SafetyDecision(False, "İrtifa pozitif olmalıdır.")
            if altitude > self.sim.max_altitude:
                return SafetyDecision(
                    False,
                    f"Hedef irtifa ({altitude} m) maksimum sınırı "
                    f"({self.sim.max_altitude} m) aşıyor.",
                )
        if abs(x) > MAX_HORIZONTAL_RANGE or abs(y) > MAX_HORIZONTAL_RANGE:
            return SafetyDecision(
                False,
                f"Hedef konum çalışma alanı sınırının "
                f"(±{MAX_HORIZONTAL_RANGE} m) dışında.",
            )
        sanitized = {"x": x, "y": y}
        if altitude is not None:
            sanitized["altitude"] = altitude
        blocker = self._path_blocked(state.x, state.y, x, y)
        if blocker is not None:
            # Reddetmek yerine engelin/yasak bölgenin etrafından OTONOM dolaş.
            route = self.plan_route(state.x, state.y, x, y)
            if route is None:
                tur = ("uçuşa yasak bölge" if blocker.kind == "nofly"
                       else "engel")
                return SafetyDecision(
                    False,
                    f"Rota bir {tur} ('{blocker.name}') içinden geçiyor ve "
                    f"güvenli bir dolaşma yolu bulunamadı. Reddedildi.",
                )
            sanitized["route"] = route
            return SafetyDecision(
                True,
                f"({x}, {y}) konumuna engelden dolaşarak gidiş onaylandı "
                f"({len(route) - 1} ara nokta).",
                sanitized,
            )
        return SafetyDecision(True, f"({x}, {y}) konumuna gidiş onaylandı.",
                              sanitized)

    def _validate_move(self, args, state) -> SafetyDecision:
        if not state.in_air:
            return SafetyDecision(
                False, "Göreli hareket için drone havada olmalıdır (kalkış yapın)."
            )
        try:
            dx = float(args.get("dx", 0.0) or 0.0)
            dy = float(args.get("dy", 0.0) or 0.0)
            dz = float(args.get("dz", 0.0) or 0.0)
        except (TypeError, ValueError):
            return SafetyDecision(False, "Geçersiz hareket miktarı (dx, dy, dz).")
        if dx == 0 and dy == 0 and dz == 0:
            return SafetyDecision(False, "Hareket miktarı belirtilmedi.")
        new_x, new_y = state.x + dx, state.y + dy
        new_alt = state.altitude + dz
        if new_alt > self.sim.max_altitude:
            return SafetyDecision(
                False,
                f"Hedef irtifa ({new_alt} m) maksimum sınırı "
                f"({self.sim.max_altitude} m) aşıyor.",
            )
        if new_alt < 0:
            return SafetyDecision(
                False,
                "Aşağı hareket irtifayı 0'ın altına indirir. Tamamen inmek için "
                "'iniş yap' komutunu kullanın.",
            )
        if abs(new_x) > MAX_HORIZONTAL_RANGE or abs(new_y) > MAX_HORIZONTAL_RANGE:
            return SafetyDecision(
                False,
                f"Hedef konum çalışma alanı sınırının "
                f"(±{MAX_HORIZONTAL_RANGE} m) dışında.",
            )
        blocker = self._path_blocked(state.x, state.y, new_x, new_y)
        if blocker is not None:
            tur = "uçuşa yasak bölge" if blocker.kind == "nofly" else "engel"
            return SafetyDecision(
                False,
                f"Rota bir {tur} ('{blocker.name}') içinden geçiyor. Komut "
                f"güvenlik gereği reddedildi.",
            )
        return SafetyDecision(
            True,
            f"Göreli hareket onaylandı (dx={dx}, dy={dy}, dz={dz}).",
            {"dx": dx, "dy": dy, "dz": dz},
        )

    # ------------------------------------------------------------------ #
    # Özgün özellik: batarya bazlı otomatik eve dönüş ÖNERİSİ
    # ------------------------------------------------------------------ #
    def _validate_avoid(self, args, state) -> SafetyDecision:
        if not state.in_air:
            return SafetyDecision(
                False, "Kaçınma için drone havada olmalıdır (kalkış yapın)."
            )
        return SafetyDecision(True, "Kaçınma değerlendirmesi onaylandı.", args)

    def _validate_drop(self, args, state) -> SafetyDecision:
        """Yük/destek bırakma güvenlik denetimi. Havada olma, dolu kargo bölmesi,
        (varsa) hedef koordinatın menzil/rota/yasak-bölge uygunluğu denetlenir."""
        if not state.in_air:
            return SafetyDecision(
                False, "Yük bırakma için drone havada olmalıdır (kalkış yapın)."
            )
        if getattr(state, "payloads_remaining", 0) <= 0:
            return SafetyDecision(
                False, "Kargo bölmesi boş; bırakılacak destek paketi kalmadı."
            )
        label = args.get("label")
        x, y = args.get("x"), args.get("y")

        def _in_nofly(px, py):
            for k in self.sim.keepouts:
                if k.kind == "nofly" and math.hypot(px - k.x, py - k.y) <= k.radius:
                    return k
            return None

        if x is not None and y is not None:
            try:
                x, y = float(x), float(y)
            except (TypeError, ValueError):
                return SafetyDecision(False, "Geçersiz bırakma koordinatı (x, y).")
            if abs(x) > MAX_HORIZONTAL_RANGE or abs(y) > MAX_HORIZONTAL_RANGE:
                return SafetyDecision(
                    False,
                    f"Bırakma konumu çalışma alanı sınırının "
                    f"(±{MAX_HORIZONTAL_RANGE} m) dışında.",
                )
            # Rota engelden geçse bile go_to otonom olarak dolaşacağı için
            # burada yalnızca "hiç güvenli yol yok" durumunu reddederiz.
            if self._path_blocked(state.x, state.y, x, y) is not None:
                if self.plan_route(state.x, state.y, x, y) is None:
                    return SafetyDecision(
                        False,
                        "Bırakma noktasına güvenli bir rota bulunamadı. "
                        "Reddedildi.",
                    )
            nf = _in_nofly(x, y)
            if nf is not None:
                return SafetyDecision(
                    False,
                    f"Bırakma noktası uçuşa yasak bölge ('{nf.name}') içinde. "
                    f"Reddedildi.",
                )
            return SafetyDecision(
                True, f"({x}, {y}) konumuna yük bırakma onaylandı.",
                {"x": x, "y": y, "label": label},
            )

        nf = _in_nofly(state.x, state.y)
        if nf is not None:
            return SafetyDecision(
                False,
                f"Mevcut konum uçuşa yasak bölge ('{nf.name}') içinde; "
                f"yük bırakılamaz.",
            )
        return SafetyDecision(True, "Mevcut konuma yük bırakma onaylandı.",
                              {"label": label})

    def _validate_recharge(self, args, state) -> SafetyDecision:
        """Şarj güvenlik denetimi: drone YERDE ve BAŞLANGIÇ (ev) noktasında
        olmalı; batarya zaten doluysa reddedilir."""
        if state.in_air:
            return SafetyDecision(
                False, "Şarj için drone yerde olmalıdır. Önce 'eve dön' "
                       "(veya 'iniş yap')."
            )
        dist_home = math.hypot(state.x - state.home_x, state.y - state.home_y)
        if dist_home > 2.0:
            return SafetyDecision(
                False, "Şarj yalnızca başlangıç (ev) noktasında yapılabilir. "
                       "Önce 'eve dön'."
            )
        if state.battery >= 99.5:
            return SafetyDecision(False, "Batarya zaten dolu (%100).")
        return SafetyDecision(True, "Şarj onaylandı.", args)

    def plan_avoidance(self, state) -> Dict[str, Any]:
        """En yakın engele göre otonom kaçınma kararı üretir (uygulamaz).
        'hold' = güvenli mesafe, pozisyon korunur; 'avoid' = uzaklaşma vektörü."""
        if not self.sim.keepouts:
            return {"decision": "hold",
                    "reason": "Tanımlı engel yok; pozisyon korunuyor (hover)."}
        nearest = min(self.sim.keepouts,
                      key=lambda k: math.hypot(state.x - k.x, state.y - k.y)
                      - k.radius)
        d = math.hypot(state.x - nearest.x, state.y - nearest.y)
        needed = nearest.radius + SAFE_BUFFER
        if d >= needed:
            return {"decision": "hold", "obstacle": nearest.name,
                    "reason": f"En yakın engel '{nearest.name}' "
                              f"{max(0.0, d - nearest.radius):.1f} m uzakta "
                              f"(güvenli). Pozisyon korunuyor (hover)."}
        if d < 1e-6:
            ux, uy = 1.0, 0.0
        else:
            ux, uy = (state.x - nearest.x) / d, (state.y - nearest.y) / d
        step = needed - d
        return {"decision": "avoid", "dx": round(ux * step, 2),
                "dy": round(uy * step, 2), "obstacle": nearest.name,
                "reason": f"'{nearest.name}' engeli "
                          f"{max(0.0, d - nearest.radius):.1f} m yakında; "
                          f"güvenli mesafeye {step:.1f} m uzaklaşılıyor."}

    def energy_status(self, state) -> Dict[str, Any]:
        """Kalan menzil, eve dönüş maliyeti ve güvenli dönüş bilgisini hesaplar."""
        usable = max(0.0, state.battery - ENERGY_RESERVE)
        range_m = usable / BATTERY_PER_METER if BATTERY_PER_METER else 0.0
        dist_home = math.hypot(state.x - state.home_x, state.y - state.home_y)
        rth_cost = 2.0 + dist_home * BATTERY_PER_METER + 3.0  # gidiş + iniş
        can_rth = rth_cost <= state.battery
        return {
            "battery": round(state.battery, 1),
            "reserve": ENERGY_RESERVE,
            "range_m": round(range_m, 1),
            "dist_home": round(dist_home, 1),
            "rth_cost_pct": round(rth_cost, 1),
            "can_return_home": can_rth,
        }

    def rth_suggestion(self, state) -> Optional[str]:
        """
        Batarya düşük ve drone havadaysa bir öneri metni döndürür.
        Bu yalnızca bir ÖNERİDİR; hiçbir eylemi otomatik uygulamaz.
        """
        if state.in_air and 0 < state.battery <= LOW_BATTERY_RTH_SUGGEST:
            return (
                f"⚠️ Batarya %{state.battery:.0f} seviyesinde. Güvenlik için "
                f"'eve dön' komutunu vermenizi öneririm."
            )
        return None
