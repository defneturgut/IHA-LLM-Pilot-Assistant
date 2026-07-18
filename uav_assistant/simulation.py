"""
simulation.py
=============
Basit, düşük kurulum yüklü 3B drone simülasyonu + ortam (engel/yasak bölge).

Bu modül GERÇEK bir uçuş kontrol yazılımı DEĞİLDİR. Amaç; LLM tabanlı bir
pilot asistanının etkileşime gireceği, telemetri üreten güvenli bir "oyun
alanı" (sandbox) sağlamaktır.

Özgün geliştirme: ortamda dairesel ENGELLER ve UÇUŞA YASAK BÖLGELER
(no-fly zone) tutulur. Güvenlik katmanı hareket komutlarının rotasını bu
bölgelere göre denetler. Ayrıca uçuş izi (trail) görselleştirme için kaydedilir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple


class FlightMode(str, Enum):
    """Drone'un olası uçuş modları."""

    IDLE = "IDLE"
    TAKEOFF = "TAKEOFF"
    HOVER = "HOVER"
    RETURN = "RETURN"
    LANDING = "LANDING"


@dataclass
class KeepOut:
    """Dairesel yasak alan: engel (obstacle) veya uçuşa yasak bölge (nofly)."""

    x: float
    y: float
    radius: float
    name: str = ""
    kind: str = "obstacle"   # "obstacle" | "nofly"

    def to_dict(self) -> Dict[str, Any]:
        return {"x": self.x, "y": self.y, "radius": self.radius,
                "name": self.name, "kind": self.kind}


@dataclass
class DroneState:
    """
    Drone'un anlık durumu (State).

    x, y : Yatay konum (m). altitude: irtifa (m). mode: uçuş modu.
    battery: %0-100. in_air: havada mı.
    """

    x: float = 0.0
    y: float = 0.0
    altitude: float = 0.0
    mode: FlightMode = FlightMode.IDLE
    battery: float = 100.0
    in_air: bool = False
    home_x: float = 0.0
    home_y: float = 0.0
    payloads_remaining: int = 3      # kargo bölmesindeki kalan destek paketi

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["mode"] = self.mode.value
        for k in ("x", "y", "altitude", "battery"):
            d[k] = round(float(d[k]), 2)
        return d


class DroneSimulator:
    """Sınıf tabanlı basit 3B drone simülatörü (+ ortam ve uçuş izi)."""

    def __init__(self, max_altitude: float = 120.0):
        self.max_altitude = max_altitude
        self.state = DroneState()
        self.keepouts: List[KeepOut] = []
        self.trail: List[Tuple[float, float, float]] = [(0.0, 0.0, 0.0)]
        # Bırakılan destek/kargo paketleri: (x, y, etiket)
        self.drops: List[Tuple[float, float, str]] = []
        # Hareketten ÖNCEKİ konum (x, y, irtifa) — 'önceki konuma dön' için
        self.previous_position: Optional[Tuple[float, float, float]] = None
        # Aktif/son gözlem alanı (x, y, yarıçap) — radar ışıldağı için
        self.observe_zone: Optional[Tuple[float, float, float]] = None

    # -- ortam ----------------------------------------------------------- #
    def add_obstacle(self, x, y, radius, name="engel") -> None:
        self.keepouts.append(KeepOut(x, y, radius, name, "obstacle"))

    def add_no_fly_zone(self, x, y, radius, name="yasak bolge") -> None:
        self.keepouts.append(KeepOut(x, y, radius, name, "nofly"))

    def load_demo_environment(self) -> None:
        """Demo/görselleştirme için birkaç engel ve bir yasak bölge ekler."""
        self.add_obstacle(30, 30, 8, "bina")
        self.add_obstacle(-20, 40, 6, "vinç")
        self.add_no_fly_zone(60, 10, 15, "havaalani yaklasma")

    # -- iç fonksiyonlar (yalnızca tools.py çağırmalıdır) ---------------- #
    def _record(self) -> None:
        self.trail.append((round(self.state.x, 2), round(self.state.y, 2),
                           round(self.state.altitude, 2)))

    def _consume_battery(self, amount: float) -> None:
        self.state.battery = max(0.0, self.state.battery - amount)

    def _takeoff(self, altitude: float) -> None:
        self.state.mode = FlightMode.TAKEOFF
        self.state.altitude = altitude
        self.state.in_air = True
        self.state.mode = FlightMode.HOVER
        self._consume_battery(5.0)
        self._record()

    def _land(self) -> None:
        self.state.mode = FlightMode.LANDING
        self.state.altitude = 0.0
        self.state.in_air = False
        self.state.mode = FlightMode.IDLE
        self._consume_battery(3.0)
        self._record()

    def _go_to(self, x: float, y: float, altitude: float | None = None) -> None:
        dist = math.hypot(x - self.state.x, y - self.state.y)
        self.state.x = x
        self.state.y = y
        if altitude is not None:
            self.state.altitude = altitude
        self.state.mode = FlightMode.HOVER
        self.state.in_air = True
        self._consume_battery(1.0 + dist * 0.05)
        self._record()

    def _move(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
        self.state.x += dx
        self.state.y += dy
        self.state.altitude = max(0.0, self.state.altitude + dz)
        self.state.mode = FlightMode.HOVER
        self.state.in_air = True
        dist = math.hypot(dx, dy) + abs(dz)
        self._consume_battery(1.0 + dist * 0.05)
        self._record()

    def _drop_payload(self, label: str = "destek paketi") -> None:
        """Mevcut konuma bir destek/kargo paketi bırakır (kargo bölmesi açılır)."""
        self.drops.append((round(self.state.x, 2), round(self.state.y, 2),
                           label))
        self.state.payloads_remaining = max(
            0, self.state.payloads_remaining - 1)
        self.state.mode = FlightMode.HOVER
        self._consume_battery(0.5)
        self._record()

    def _orbit(self, cx: float, cy: float, radius: float, laps: float = 1.0,
               steps_per_lap: int = 24) -> None:
        """Bir merkez etrafında dairesel gözlem yörüngesi uçar; her adımı uçuş
        izine kaydeder (harita/animasyonda daire görünür)."""
        total = int(max(1, round(laps)) * steps_per_lap)
        for i in range(total + 1):
            ang = 2.0 * math.pi * (i % steps_per_lap) / steps_per_lap
            self.state.x = round(cx + radius * math.cos(ang), 2)
            self.state.y = round(cy + radius * math.sin(ang), 2)
            self.state.mode = FlightMode.HOVER
            self.state.in_air = True
            self._consume_battery(0.1)
            self._record()

    def _recharge(self, amount: float | None = None) -> None:
        """Bataryayı doldurur (yalnızca ev/yer koşulunda çağrılmalı — güvenlik
        katmanı denetler). amount verilmezse tam doluma (%100) getirir."""
        if amount is None:
            self.state.battery = 100.0
        else:
            self.state.battery = min(100.0, self.state.battery + amount)
        self.state.mode = FlightMode.IDLE

    def _return_to_home(self) -> None:
        self.state.mode = FlightMode.RETURN
        dist = math.hypot(self.state.x - self.state.home_x,
                          self.state.y - self.state.home_y)
        self.state.x = self.state.home_x
        self.state.y = self.state.home_y
        self._consume_battery(2.0 + dist * 0.05)
        self._record()
        self._land()

    def get_state(self) -> DroneState:
        return self.state
