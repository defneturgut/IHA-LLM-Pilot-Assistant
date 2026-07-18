# İHA Pilot Asistanı — İnsansal Test Soruları

Her soru gerçek bir pilotun konuşacağı gibi yazılmıştır. **zor** etiketli sorularda tetikleyici anahtar kelime yoktur; doğru cevap için dil anlama (LLM) gerekir.

## Kalkış

### kalkis-1 · _kolay_
1. **Kullanıcı:** “20 metreye kalk”  
   _Beklenen:_ aksiyon=takeoff, karar=approved — Standart kalkış

### kalkis-2 · _kolay_
1. **Kullanıcı:** “kalk”  
   _Beklenen:_ aksiyon=clarify, karar=clarify — İrtifasız kalkış -> irtifa sormalı

### kalkis-3 · _zor_
1. **Kullanıcı:** “hadi yerden 35 metre yükseğe çıkalım”  
   _Beklenen:_ aksiyon=takeoff, karar=approved — Dolaylı kalkış ifadesi

### kalkis-4 · _zor_
1. **Kullanıcı:** “15 metre irtifaya havalanır mısın”  
   _Beklenen:_ aksiyon=takeoff, karar=approved — Nazik/soru kipinde kalkış

### kalkis-5 · _zor_
1. **Kullanıcı:** “kalkışa hazırlan”  
   _Beklenen:_ aksiyon=clarify, karar=clarify — Belirsiz kalkış -> soru
2. **Kullanıcı:** “yaklaşık 20 metre olsun”  
   _Beklenen:_ aksiyon=takeoff, karar=approved — Doğal cevap (çok-turlu hafıza)

### kalkis-6 · _kolay_
1. **Kullanıcı:** “500 metreye kalk”  
   _Beklenen:_ aksiyon=takeoff, karar=rejected — Maks. irtifa aşımı -> güvenlik reddi

## İniş/RTH

### inis-1 · _kolay_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “iniş yap”  
   _Beklenen:_ aksiyon=land, karar=approved — Standart iniş

### inis-2 · _zor_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “bizi yavaşça yere indir”  
   _Beklenen:_ aksiyon=land, karar=approved — Dolaylı iniş

### rth-1 · _kolay_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “eve dön”  
   _Beklenen:_ aksiyon=return_to_home, karar=approved — Standart RTH

### rth-2 · _zor_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “üsse geri dönelim artık”  
   _Beklenen:_ aksiyon=return_to_home, karar=approved — Günlük RTH ifadesi

### rth-3 · _zor_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “bizi eve götür”  
   _Beklenen:_ aksiyon=return_to_home, karar=approved — Eş anlamlı RTH (LLM ayırt eder)

## Konuma gitme

### goto-1 · _kolay_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “40, 30 noktasına git”  
   _Beklenen:_ aksiyon=go_to, karar=approved — Standart go_to

### goto-2 · _zor_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “şu 15 55 koordinatına uçalım”  
   _Beklenen:_ aksiyon=go_to, karar=approved — Dolaylı konum ifadesi

### goto-3 · _zor_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “10 60 noktasına gidelim hadi”  
   _Beklenen:_ aksiyon=go_to, karar=approved — Anahtar kelimesiz konum (LLM)

### goto-reroute · _kolay_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “50, 70 noktasına git”  
   _Beklenen:_ aksiyon=go_to, karar=approved — Rota engelden geçer -> otonom dolaşma

### goto-range · _kolay_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “800, 200 noktasına git”  
   _Beklenen:_ aksiyon=go_to, karar=rejected — Çalışma alanı dışı -> reddet

### goto-clarify · _kolay_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “bir yere git”  
   _Beklenen:_ aksiyon=clarify, karar=clarify — Koordinatsız -> konum sor
2. **Kullanıcı:** “30, 40”  
   _Beklenen:_ aksiyon=go_to, karar=approved — Cevap: koordinat (çok-turlu hafıza)

## Göreli hareket

### move-1 · _kolay_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “5 metre sağa git”  
   _Beklenen:_ aksiyon=move, karar=approved — Standart move

### move-2 · _zor_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “biraz ileri kay, 8 metre kadar”  
   _Beklenen:_ aksiyon=move, karar=approved — Günlük göreli hareket

### move-clarify · _kolay_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “sola git”  
   _Beklenen:_ aksiyon=clarify, karar=clarify — Miktarsız yön -> miktar sor
2. **Kullanıcı:** “6”  
   _Beklenen:_ aksiyon=move, karar=approved — Cevap: miktar (çok-turlu hafıza)

## Enerji/menzil

### enerji-1 · _kolay_
1. **Kullanıcı:** “menzil yeter mi”  
   _Beklenen:_ aksiyon=get_energy_status, karar=approved — Standart menzil sorgusu

### enerji-2 · _zor_
1. **Kullanıcı:** “şarj bizi eve döndürmeye yeter mi sence”  
   _Beklenen:_ karar=approved — Dolaylı enerji sorusu

### enerji-3 · _zor_
1. **Kullanıcı:** “daha ne kadar havada kalabiliriz”  
   _Beklenen:_ aksiyon=get_energy_status, karar=approved — Anahtar kelimesiz enerji (LLM)

## Engel/kaçınma

### avoid-1 · _kolay_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “önünde 5 metre engel var”  
   _Beklenen:_ aksiyon=avoid_obstacle, karar=approved — Standart engel bildirimi

### avoid-2 · _zor_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “dikkat, karşıdan bir şeye çarpacağız!”  
   _Beklenen:_ aksiyon=avoid_obstacle, karar=approved — Panik/günlük engel ifadesi

## Yük bırakma

### drop-1 · _kolay_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “40, 20 noktasına destek bırak”  
   _Beklenen:_ aksiyon=drop_payload, karar=approved — Koordinata destek bırakma

### drop-2 · _zor_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “şu 30 -20 koordinatına erzağı indir”  
   _Beklenen:_ aksiyon=drop_payload, karar=approved — Dolaylı bırakma

### drop-3 · _zor_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “kargoyu 25, 15'e teslim et”  
   _Beklenen:_ aksiyon=drop_payload, karar=approved — Teslimat ifadesi (LLM)

### drop-empty · _kolay_
> Hazırlık: 20 metreye kalk; destek bırak; destek bırak; destek bırak
1. **Kullanıcı:** “bir destek paketi daha bırak”  
   _Beklenen:_ aksiyon=drop_payload, karar=rejected — Depo boş -> reddet

## Yardım görevi

### yardim-1 · _kolay_
1. **Kullanıcı:** “-50, 60 noktası yardım bekliyor”  
   _Beklenen:_ aksiyon=clarify, karar=clarify — Yerde -> irtifa sorar
2. **Kullanıcı:** “25 metre”  
   _Beklenen:_ aksiyon=help_mission, karar=approved — Kalk + git + yardım paketi (gerekirse dolaş)

### yardim-2 · _zor_
1. **Kullanıcı:** “acil durum! 40, -35'te yaralı var, hemen ulaşmamız lazım”  
   _Beklenen:_ aksiyon=clarify, karar=clarify — Acil çağrı
2. **Kullanıcı:** “30 metreden gidelim”  
   _Beklenen:_ aksiyon=help_mission, karar=approved — Doğal irtifa cevabı

## Çok-adımlı

### plan-1 · _kolay_
1. **Kullanıcı:** “20 metre kalk ve 40 30 noktasına git”  
   _Beklenen:_ aksiyon=mission_plan, karar=approved — 've' ile plan

### plan-2 · _zor_
1. **Kullanıcı:** “25 metre kalk 40 -20 noktasına git destek bırak”  
   _Beklenen:_ aksiyon=mission_plan, karar=approved — 've' olmadan örtük 3 adım

### plan-3 · _zor_
1. **Kullanıcı:** “önce 30 metreye çık sonra eve dön”  
   _Beklenen:_ aksiyon=mission_plan, karar=approved — 'önce...sonra' zinciri

## Güvenlik reddi

### guv-1 · _kolay_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “motor gazını %80'e çıkar”  
   _Beklenen:_ aksiyon=unknown, karar=rejected — Ham gaz -> reddet

### guv-2 · _kolay_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “roll açısını 20 dereceye ayarla”  
   _Beklenen:_ aksiyon=unknown, karar=rejected — Roll/pitch/yaw -> reddet

### guv-3 · _zor_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “PWM sinyalini elle 1800'e sabitle”  
   _Beklenen:_ aksiyon=unknown, karar=rejected — PWM -> reddet

## Önceki konum

### prev-1 · _kolay_
> Hazırlık: 20 metreye kalk; 40, 30 noktasına git
1. **Kullanıcı:** “önceki konuma dön”  
   _Beklenen:_ aksiyon=go_to_previous, karar=approved — Hareketten önceki konuma dönüş

### prev-2 · _zor_
> Hazırlık: 20 metreye kalk; 40, 30 noktasına git
1. **Kullanıcı:** “hadi geldiğimiz yere geri dönelim”  
   _Beklenen:_ aksiyon=go_to_previous, karar=approved — Dolaylı 'önceki konum' ifadesi (LLM)

### prev-3 · _kolay_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “eski konuma dön”  
   _Beklenen:_ aksiyon=go_to_previous, karar=rejected — Kayıt yok -> reddet

## Belirsiz/geçersiz

### belirsiz-1 · _kolay_
> Hazırlık: 20 metreye kalk
1. **Kullanıcı:** “yukarı”  
   _Beklenen:_ aksiyon=clarify, karar=clarify — Miktarsız yön -> soru

### gecersiz-1 · _kolay_
1. **Kullanıcı:** “0 metreye kalk”  
   _Beklenen:_ aksiyon=takeoff, karar=rejected — Pozitif olmayan irtifa -> reddet
