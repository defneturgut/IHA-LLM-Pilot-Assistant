"""
visualize.py
============
Özgün geliştirme: Görsel harita / uçuş izi.

Simülasyonun uçuş izini (trail), engelleri, uçuşa yasak bölgeleri, başlangıç
(ev) noktasını ve güncel drone konumunu tek dosyalık, bağımsız bir HTML (SVG)
haritası olarak çizer. Harici bağımlılık yoktur (yalnızca stdlib).

Kullanım:
    from uav_assistant import DroneSimulator, DronePilotAgent
    from uav_assistant.visualize import save_map
    ...
    save_map(agent.sim, "mission_map.html")
"""

from __future__ import annotations

from typing import List, Tuple

W, H, PAD = 820, 620, 60


def _bounds(sim):
    xs = [p[0] for p in sim.trail] + [0.0]
    ys = [p[1] for p in sim.trail] + [0.0]
    for k in sim.keepouts:
        xs += [k.x - k.radius, k.x + k.radius]
        ys += [k.y - k.radius, k.y + k.radius]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    if maxx - minx < 20:
        minx -= 10; maxx += 10
    if maxy - miny < 20:
        miny -= 10; maxy += 10
    return minx, maxx, miny, maxy


def _make_transform(sim):
    minx, maxx, miny, maxy = _bounds(sim)
    sx = (W - 2 * PAD) / (maxx - minx)
    sy = (H - 2 * PAD) / (maxy - miny)
    s = min(sx, sy)

    def tx(x):
        return PAD + (x - minx) * s

    def ty(y):
        # dünya y'si yukarı; SVG y'si aşağı -> ters çevir
        return H - PAD - (y - miny) * s

    return tx, ty, s


def _svg(sim, title: str) -> str:
    tx, ty, s = _make_transform(sim)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'viewBox="0 0 {W} {H}" font-family="sans-serif">']
    parts.append(f'<rect width="{W}" height="{H}" fill="#0f1420"/>')
    parts.append(f'<text x="{W/2}" y="30" fill="#e6edf3" font-size="18" '
                 f'text-anchor="middle">{title}</text>')

    # yasak bölgeler ve engeller
    for k in sim.keepouts:
        cx, cy, r = tx(k.x), ty(k.y), k.radius * s
        if k.kind == "nofly":
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
                         f'fill="#ff453a" fill-opacity="0.18" stroke="#ff453a" '
                         f'stroke-dasharray="6 4"/>')
        else:
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
                         f'fill="#ff9f0a" fill-opacity="0.28" stroke="#ff9f0a"/>')
        parts.append(f'<text x="{cx:.1f}" y="{cy - r - 4:.1f}" fill="#c9d1d9" '
                     f'font-size="11" text-anchor="middle">{k.name}</text>')

    # uçuş izi (polyline)
    pts = " ".join(f"{tx(x):.1f},{ty(y):.1f}" for x, y, _ in sim.trail)
    parts.append(f'<polyline points="{pts}" fill="none" stroke="#2f81f7" '
                 f'stroke-width="2.5"/>')
    # ara noktalar
    for x, y, alt in sim.trail:
        parts.append(f'<circle cx="{tx(x):.1f}" cy="{ty(y):.1f}" r="3" '
                     f'fill="#58a6ff"/>')

    # ev (başlangıç)
    hx, hy = tx(sim.state.home_x), ty(sim.state.home_y)
    parts.append(f'<rect x="{hx-6:.1f}" y="{hy-6:.1f}" width="12" height="12" '
                 f'fill="#3fb950"/>')
    parts.append(f'<text x="{hx:.1f}" y="{hy+20:.1f}" fill="#3fb950" '
                 f'font-size="11" text-anchor="middle">EV</text>')

    # güncel drone konumu
    dx, dy = tx(sim.state.x), ty(sim.state.y)
    parts.append(f'<circle cx="{dx:.1f}" cy="{dy:.1f}" r="7" fill="#f0f6fc" '
                 f'stroke="#2f81f7" stroke-width="3"/>')
    parts.append(f'<text x="{dx:.1f}" y="{dy-12:.1f}" fill="#f0f6fc" '
                 f'font-size="11" text-anchor="middle">'
                 f'DRONE ({sim.state.x:.0f},{sim.state.y:.0f},'
                 f'{sim.state.altitude:.0f}m)</text>')

    # açıklama (legend) ve ölçek
    parts.append(f'<text x="12" y="{H-16}" fill="#8b949e" font-size="12">'
                 f'Ölçek: 1 kare ~ {50} m  |  Batarya %{sim.state.battery:.0f}  '
                 f'|  Mavi: uçuş izi, Turuncu: engel, Kırmızı: yasak bölge</text>')
    parts.append('</svg>')
    return "\n".join(parts)


def save_map(sim, path: str = "mission_map.html",
             title: str = "İHA Görev Haritası") -> str:
    """Simülasyonu bir HTML/SVG haritası olarak kaydeder; dosya yolunu döndürür."""
    svg = _svg(sim, title)
    html = (
        "<!doctype html><html lang='tr'><head><meta charset='utf-8'>"
        f"<title>{title}</title></head>"
        "<body style='margin:0;background:#0f1420;display:flex;"
        "justify-content:center;padding:16px'>"
        f"{svg}</body></html>"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
