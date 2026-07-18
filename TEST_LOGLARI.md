# Test Logları

Sistem her komutu otomatik olarak `logs/mission_log.csv` (ve `.json`) dosyasına
kaydeder. Her kayıt şu alanları içerir:

`timestamp, user_command, action (yorumlanan araç), args, decision, success,
message (sonuç/gerekçe), telemetry`

Bu belge log yapısını özetler ve temsili kayıtları gösterir; **tam makine-okur
log** `logs/mission_log.csv` dosyasındadır.

## Özet istatistikler

Toplam kayıt: **2637**

| Karar | Adet |
|-------|------|
| approved (onaylı) | 1932 |
| rejected (reddedildi) | 476 |
| clarify (açıklama istendi) | 229 |

Aksiyon dağılımı (yorumlanan araçlar): `takeoff 784, go_to 458, get_telemetry
204, clarify 191, unknown 154, return_to_home 149, mission_plan 138, land 133,
move 117, get_energy_status 75, drop_payload 73, help_mission 68, avoid_obstacle
54, go_to_previous 21, observe_mission 12, recharge 6`.

## Otomatik test sonuçları

| Test paketi | Sonuç |
|-------------|-------|
| `test_scenarios.py` | **23/23 senaryo + 8/8 özgün özellik** başarılı |
| `test_llm_scenarios.py` (kural tabanlı) | **35/42** — kolay **23/23 (%100)**, zor **12/19 (%63)** |

"zor" satırlar anahtar kelime içermeyen doğal ifadelerdir; kural tabanlı bir
kısmını ıskalar, LLM modunda skorun yükselmesi beklenir. `--llm` ile aynı set
çalıştırılıp karşılaştırılabilir.

## Temsili log kayıtları

### Başarılı (approved)

| Komut | Action | Mesaj |
|-------|--------|-------|
| 20 metreye kalk | takeoff | 20.0 m irtifaya güvenli kalkış onaylandı. |
| 40, 30 noktasına git | go_to | (40.0, 30.0) konumuna gidiş onaylandı. |
| 20 metreye kalk ve 50 70 noktasına git | mission_plan | 2 adım; rota engelden 1 ara nokta ile dolaşıldı. |
| 12,23'ü 10 m çapında 2 tur gözlemle... | observe_mission | Kalkış→gözlem (2 tur)→eve dönüş, tümü onaylı. |
| bataryayı şarj et | recharge | 🔋 Şarj tamamlandı. Batarya %100. |

### Belirsiz — açıklama istendi (clarify)

| Komut | Action | Mesaj |
|-------|--------|-------|
| kalkış yap | clarify | Kalkış için hedef irtifa belirtilmedi... |
| yukarı | clarify | Yön belirtildi ancak miktar yok. Varsayım yapılmadı. |
| acil durum! 40,-35'te yaralı var... | help_mission→clarify | 🆘 Yardıma gidiyorum. Kaç metre irtifaya kalkayım? |

### Reddedildi (rejected) — güvenlik/geçersiz

| Komut | Action | Mesaj |
|-------|--------|-------|
| 500 metreye kalk | takeoff | REDDEDİLDİ: 500 m maksimum sınırı (120 m) aşıyor. |
| 0 metreye kalk | takeoff | REDDEDİLDİ: İrtifa pozitif bir değer olmalıdır. |
| motor gazını %90'a getir | unknown | REDDEDİLDİ: Düşük seviye kontrol (PWM/gaz/roll) yasak. |
| 60 10 noktasına git | go_to | REDDEDİLDİ: Hedef uçuşa yasak bölge içinde. |
| eski konuma dön (hareket yokken) | go_to_previous | REDDEDİLDİ: Kayıtlı önceki konum yok. |
| şarj et (havadayken) | recharge | REDDEDİLDİ: Şarj için drone yerde olmalı. |

## Logları yeniden üretme

```bash
python test_scenarios.py       # senaryoları çalıştırır ve loglar
python demo_showcase.py        # gösterim akışını loglar
# çıktı: logs/mission_log.csv ve logs/mission_log.json
```
