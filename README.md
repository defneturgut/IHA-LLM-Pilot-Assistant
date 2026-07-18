# İHA (Drone) LLM Pilot Asistanı — Prototip

Büyük dil modeli (LLM) tabanlı bir İHA pilot asistanı prototipi. Amaç gerçek bir uçuş kontrol yazılımı **değil**; LLM/agent mantığını, telemetri farkındalığını, komut doğrulamayı ve güvenlik katmanını gösteren, uçtan uca çalışan küçük bir sistemdir.

**Temel güvenlik ilkesi:** LLM hiçbir zaman düşük seviyeli kontrol kodlarına (PWM, ham hız, roll/pitch/yaw) erişmez. Yalnızca önceden tanımlı güvenli fonksiyonları (`get_telemetry`, `takeoff`, `land`, `return_to_home`, `go_to`, `move`, `get_energy_status`, `avoid_obstacle`) tetikleyebilir ve her komut uygulanmadan önce bir güvenlik katmanından geçer.

## Mimari

```
Doğal dil komutu
      │
      ▼
┌─────────────────┐   Hibrit NLU (kural tabanlı veya opsiyonel gerçek LLM)
│  agent.py       │──▶ komutu tool call'a çevirir + çok-adımlı planlama
└─────────────────┘
      │
      ▼
┌─────────────────┐   8 güvenli fonksiyon
│  tools.py       │
└─────────────────┘
      │
      ▼
┌─────────────────┐   Kural tabanlı doğrulama (maks. irtifa, batarya, durum...)
│  safety.py      │──▶ güvensiz/eksik komutları REDDEDER
└─────────────────┘
      │
      ▼
┌─────────────────┐   3B durum: x, y, altitude, mode, battery, in_air
│  simulation.py  │
└─────────────────┘
      │
      ▼
┌─────────────────┐   Her etkileşimi JSON + CSV olarak kaydeder
│  logger.py      │
└─────────────────┘
```

## Modüller

| Dosya | Görev |
|-------|-------|
| `uav_assistant/simulation.py` | Sınıf tabanlı basit 3B drone simülasyonu ve durum yönetimi. |
| `uav_assistant/safety.py` | Güvenlik katmanı: tool call'ları uygulanmadan önce kurallarla doğrular. |
| `uav_assistant/tools.py` | 8 güvenli araç fonksiyonu + LLM tool-calling şeması. |
| `uav_assistant/agent.py` | Doğal dil arayüzü (hibrit NLU) + çok-adımlı görev planlama. |
| `uav_assistant/logger.py` | JSON/CSV loglama sistemi. |
| `uav_assistant/scenario_generator.py` | Özgün özellik: rastgele senaryo üreticisi. |
| `uav_assistant/visualize.py` | Özgün özellik: uçuş izi/engel/yasak bölge HTML haritası. |
| `demo_mission.py` | Engelli ortamda uçtan uca demo + harita üretimi. |
| `web_app.py` | Özgün özellik: canlı 2B web panosu (tarayıcıda görsel ortam). |
| `main.py` | İnteraktif komut satırı arayüzü (REPL). |
| `test_scenarios.py` | 23 doğal dil komutu + 8 özgün özellik testi. |
| `IHA_Pilot_Asistani_Teknik_Rapor.docx` | Kısa teknik rapor (mimari, gerekçe, güvenlik, test, sınırlılıklar). |

## Kurulum

Python 3.9+ yeterlidir. **Varsayılan (offline) mod hiçbir harici bağımlılık gerektirmez** — yalnızca standart kütüphane kullanır.

```bash
cd "MTA-IHA LLM-Defne Turgut"
python -m venv .venv            # (isteğe bağlı)
source .venv/bin/activate       # Windows: .venv\Scripts\activate
```

### Gerçek LLM modu (opsiyonel)

Sistem üç sağlayıcıyı destekler; `UAV_LLM_PROVIDER` ile seçilir (`auto` varsayılan). Sağlayıcıdan bağımsız olarak LLM yalnızca güvenli fonksiyonları çağırır; güvenlik katmanı her koşulda uygulanır. Erişilebilir sağlayıcı yoksa otomatik olarak kural tabanlı moda düşer.

**Ollama (yerel, ücretsiz, önerilen):** API anahtarı gerekmez.

```bash
# 1) Ollama'yı kur (https://ollama.com) ve tool-calling destekleyen bir model çek
ollama pull llama3.1            # veya: qwen2.5, mistral
# 2) Asistanı Ollama ile çalıştır
export UAV_LLM_PROVIDER=ollama  # $env:UAV_LLM_PROVIDER = "ollama"
export UAV_LLM_MODEL=llama3.1   # $env:UAV_LLM_MODEL = "llama3.1"
python main.py --llm
```

**Bulut (opsiyonel):**

```bash
pip install anthropic              # veya: pip install openai
export ANTHROPIC_API_KEY="..."     # veya OPENAI_API_KEY
python main.py --llm
```

İlgili ortam değişkenleri: `UAV_LLM_PROVIDER` (auto/ollama/anthropic/openai), `UAV_LLM_MODEL`, `OLLAMA_HOST` (varsayılan http://localhost:11434).

## Çalıştırma

```bash
python test_scenarios.py                              # 23 senaryo + 8 özgün (31 test)
python main.py                                        # interaktif (offline)
python main.py --llm                                  # gerçek LLM (API anahtarı ile)
python -m uav_assistant.scenario_generator --n 15     # rastgele senaryolar
python demo_mission.py                                # engelli demo + mission_map.html
python web_app.py                                     # canlı 2B web panosu -> http://127.0.0.1:8000
```

## Örnek komutlar

| Komut | Sonuç |
|-------|-------|
| `durum nedir?` | ✅ Telemetriyi doğal dille açıklar |
| `20 metreye kalk` | ✅ Güvenli kalkış |
| `30, 40 noktasına git` | ✅ Belirtilen konuma gidiş (go_to) |
| `iniş yap` | ✅ İniş (havadaysa) |
| `eve dön` | ✅ Return-to-home + iniş |
| `kalk, 30 40 noktasına git, durum bildir ve eve dön` | ✅ Çok-adımlı görev planı |
| `500 metreye kalk` | ⛔ Maks. irtifa aşımı → reddedilir |
| `kalkış yap` | ❓ İrtifa belirsiz → açıklama ister |
| `4 sağa git`, `20 yukarı çık` | ✅ Yönlü/göreli hareket (move) |
| `menzil ne kadar, eve dönebilir miyim` | ✅ Enerji/menzil tahmini |
| `30 30 noktasına git` (engel) | ⛔ Rota engelden geçiyor → reddedilir |
| `önünde 1 metre engel var` | 🛟 Otonom kaçınma (uzaklaş) veya hover |
| `roll açısını 30'a ayarla` | ⛔ Düşük seviyeli kontrol → reddedilir |

## Güvenlik kuralları (safety.py)

- Maksimum irtifa sınırı (varsayılan **120 m**) aşılamaz.
- Kalkış için batarya **%20**'nin altındaysa reddedilir.
- `go_to` ve `move` için yatay çalışma alanı sınırı **±500 m**.
- Hareket rotası bir **engel** veya **uçuşa yasak bölgeden** geçiyorsa reddedilir.
- Havadayken tekrar kalkış, yerdeyken iniş gibi mantıksız komutlar reddedilir.
- Belirsiz komutta (irtifa/koordinat yoksa) **varsayım yapılmaz**, açıklama istenir.
- Düşük seviyeli kontrol denemeleri (PWM/roll/pitch/yaw/motor) her koşulda reddedilir.

## Özgün özellikler

- **Çok-adımlı görev planlama:** tek cümlede birden çok görev ("kalk, git, durum bildir, eve dön") sırayla ve her biri güvenlik katmanından geçirilerek çalıştırılır.
- **Batarya bazlı otomatik eve dönüş önerisi:** batarya %30 altına inince ajan, eylem uygulamadan güvenli eve dönüş önerir.
- **Rastgele senaryo üreticisi:** farklı ifade varyasyonlarıyla sistemi otomatik sınar.
- **Aksan-duyarsız NLU:** "çık/cik", "iniş/inis", "dön/don" gibi Türkçe varyasyonlar aynı tanınır.
- **Yönlü/göreli hareket (move):** "20 yukarı çık", "4 sağa git", "8 aşağı in" gibi komutlar konumu doğru günceller.
- **Engel + uçuşa yasak bölge (geofence):** simülasyondaki engel/yasak bölgeler; güvenlik katmanı hareket rotasını kontrol eder, çarpışan/yasak rotaları reddeder.
- **Enerji/menzil tahmini:** kalan menzil, eve dönüş maliyeti ve "eve güvenle dönebilir miyim?" hesabı (`get_energy_status`).
- **Görsel harita:** uçuş izini, engelleri, yasak bölgeleri ve güncel konumu gösteren tek dosyalık HTML/SVG harita (REPL'de `harita` komutu veya `demo_mission.py`).
- **Otonom engel kaçınma (avoid_obstacle):** "önünde engel var / engel çıktı" komutunda drone güvenli otonom karar verir — engele yakınsa uzaklaşır, uzaksa hover; kararını gerekçesiyle açıklar. "1 metre engel var" gibi ifadelerde dinamik engel ekler.
- **LLM "uydurma" koruması + kural tabanlı geri düşüş:** LLM geçersiz/uydurma çıktı verirse sistem deterministik kural tabanlı ayrıştırıcıya düşer.
- **Gelişmiş LLM entegrasyonu:** en iyi kurulu Ollama modelini otomatik seçme, temperature=0, canlı durum bağlamı, argüman normalizasyonu.
- **Canlı 2B web panosu (`web_app.py`):** tarayıcıda çalışan görsel ortam; komut yazdıkça drone, engeller, yasak bölgeler ve uçuş izi canlı güncellenir, telemetri + karar gösterilir. Sadece stdlib.

## Loglama

Her etkileşim `logs/mission_log.json` ve `logs/mission_log.csv` dosyalarına kaydedilir: zaman damgası, gelen komut, yorumlanan aksiyon, argümanlar, güvenlik kararı, başarı durumu, mesaj ve o anki telemetri.

## Test kapsamı

`test_scenarios.py`: 23 senaryo + 6 özgün özellik testi (çok-adımlı planlama, batarya önerisi, yönlü hareket, geofence, enerji/menzil, görsel h