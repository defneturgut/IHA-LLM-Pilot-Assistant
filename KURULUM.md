# Kurulum ve Çalıştırma Kılavuzu

İHA Pilot Asistanı — projeyi sıfırdan çalıştırmak için gereken adımlar.

## Gereksinimler

- **Python 3.10+** (çekirdek sistem yalnızca standart kütüphaneyi kullanır — ek
  kurulum GEREKMEZ).
- LLM modu **isteğe bağlıdır**; kurulmazsa sistem otomatik olarak offline
  **kural tabanlı** ayrıştırıcıya düşer.

## 1. Komut satırı asistanı (REPL)

```bash
cd "MTA-IHA LLM-Defne Turgut"
python main.py            # kural tabanlı (offline) mod — kurulum gerekmez
python main.py --llm      # LLM modu (bkz. 4. adım)
```

Doğal dilde komut yazın: `20 metreye kalk`, `12,23 noktasını 10 m çapında
dolaşıp gözlemle`, `eve dön`, `şarj et`. Harita için `harita`, çıkış için `exit`.

## 2. Canlı web panosu (harita + animasyon + ses)

```bash
python web_app.py                 # http://127.0.0.1:8000
python web_app.py --port 8080     # farklı port
python web_app.py --llm           # LLM ile
```

Tarayıcıda **Chrome/Edge** ile `http://127.0.0.1:8000` açın. Solda canlı taktik
radar (adım adım animasyon), sağda telemetri + komut konsolu ve sohbet geçmişi.
🎙 ile **sesli komut**, 🔊 ile **sesli yanıt** (mikrofon izni gerekir).

## 3. Testler ve gösterim

```bash
python test_scenarios.py             # 23 senaryo + 8 özgün özellik testi
python test_llm_scenarios.py         # 42 insansal senaryoyu puanlar (kural tabanlı)
python test_llm_scenarios.py --llm   # aynı seti LLM ile ölçer (karşılaştırma)
python demo_showcase.py              # 8 blokluk yetenek gösterimi
python demo_showcase.py --pause      # sunum modu (her komutta Enter bekler)
```

Tüm görev kayıtları `logs/mission_log.csv` ve `.json` dosyalarına yazılır.

## 4. (İsteğe bağlı) Gerçek LLM'i bağlama

`--llm` bayrağı erişilebilir olan ilk sağlayıcıyı kullanır; hiçbiri yoksa kural
tabanlı moda döner.

| Sağlayıcı | Kurulum | Ortam değişkeni |
|-----------|---------|-----------------|
| **Ollama** (yerel, ücretsiz) | `ollama serve` + `ollama pull qwen2.5` | `OLLAMA_HOST` |
| **Anthropic** | `pip install anthropic` | `ANTHROPIC_API_KEY` |
| **OpenAI** | `pip install openai` | `OPENAI_API_KEY` |

Sağlayıcı: `UAV_LLM_PROVIDER=auto|ollama|anthropic|openai`, model: `UAV_LLM_MODEL`.
Güvenlik katmanı LLM modundan bağımsız çalışır; LLM güvenilmez çıktı üretirse
sistem otomatik olarak kural tabanlı ayrıştırıcıya düşer.

## Proje yapısı

```
├── README.md                # proje özeti ve yapı
├── KURULUM.md               # bu dosya
├── main.py                  # komut satırı REPL
├── web_app.py               # canlı web panosu (harita + animasyon + ses)
├── test_scenarios.py        # senaryo + özgün özellik testleri
├── test_llm_scenarios.py    # insansal ölçüm seti (kural tabanlı vs LLM)
├── demo_showcase.py         # yetenek gösterimi
├── uav_assistant/           # çekirdek paket
│   ├── simulation.py        # 3B drone simülasyonu, ortam, gözlem yörüngesi
│   ├── safety.py            # güvenlik katmanı, rota planlama, enerji, fail-safe
│   ├── tools.py             # güvenli araç fonksiyonları (tek erişim arayüzü)
│   ├── agent.py             # NLU (kural tabanlı + LLM), görev planlama
│   ├── logger.py            # CSV/JSON loglama
│   └── visualize.py         # statik harita (opsiyonel)
├── belgeler/                # teslim dokümanları
│   ├── IHA_Teknik_Rapor.docx
│   ├── OZGUN_OZELLIKLER.md
│   ├── TEST_LOGLARI.md
│   ├── LLM_Demo_Promptlari.md
│   ├── DEMO_VIDEO_SENARYO.md
│   └── gorseller/
├── logs/                    # mission_log.csv / .json
└── arsiv/                   # eski/opsiyonel dosyalar
```
