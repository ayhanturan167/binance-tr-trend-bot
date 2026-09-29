# Backtest sonuçları

Veri: Binance BTCUSDT saatlik mumlar. Komisyon %0,1 (tek yön) + %0,05 kayma. Sinyal mum kapanışında hesaplanır, pozisyon bir sonraki mumdan itibaren uygulanır.
"Al-Tut" = hiçbir şey yapmadan elde tutma getirisi. Geçmiş sonuçlar geleceği garanti etmez.

## 1) Yaklaşık 6 yıl, 1 saatlik mum (`backtest.py`)

### Tüm dönem

| Strateji | Getiri % | Al-Tut % | İşlem | Kazanma % | Max düşüş % |
|---|---:|---:|---:|---:|---:|
| SMA 7/25 | -88,3 | 674,8 | 1340 | 27,0 | -96,9 |
| SMA 10/50 | -56,6 | 683,1 | 731 | 28,2 | -88,9 |
| SMA 20/50 | -27,4 | 683,1 | 620 | 31,8 | -80,2 |
| SMA 20/100 | 102,7 | 686,8 | 359 | 28,7 | -67,5 |
| SMA 50/200 | 331,0 | 681,4 | 175 | 30,9 | -58,6 |

### Son %30 (stratejinin "görmediği" dönem)

| Strateji | Getiri % | Al-Tut % | İşlem | Kazanma % | Max düşüş % |
|---|---:|---:|---:|---:|---:|
| SMA 7/25 | -67,2 | -17,5 | 400 | 28,0 | -75,9 |
| SMA 10/50 | -59,0 | -17,3 | 215 | 27,4 | -68,1 |
| SMA 20/50 | -53,0 | -17,3 | 175 | 29,7 | -63,0 |
| SMA 20/100 | -44,3 | -17,2 | 108 | 24,1 | -56,2 |
| SMA 50/200 | -13,4 | -18,2 | 56 | 30,4 | -36,1 |

**Yorum:** Hiçbir ayar al-tut'u geçemedi. Hızlı ortalamalar çok sayıda sahte sinyal ve komisyon yüzünden ağır zarar etti. Yavaş ayar (50/200) en az kötüsü oldu ve düşen dönemde al-tut'a yakın sonuç verdi, ama kazandırmadı.

## 2) Yaklaşık 2 yıl: zaman dilimi, trend filtresi ve stop-loss karşılaştırması (`backtest2.py`)

Denenenler: 1 saatlik / 4 saatlik / günlük mum, ortalama kesişimleri, "fiyat > SMA" trend filtresi, stop-loss (yok / %5 / %10).

- 1 saatlik hızlı ayarlar yine zararda; yavaş ve büyük zaman dilimlerinde bazı ayarlar kârlı göründü.
- "Aday" kriteri: tüm dönemde ve son %30'da kârlı, en büyük düşüş al-tut'tan küçük, en az 10 işlem. Bu kriteri 23 satır geçti.
- Stop-loss'un etkisi tutarsızdı: bazı ayarlarda iyileştirdi, bazılarında kötüleştirdi.

**Yorum ve sınırlar:**
- Toplam 54 kombinasyon denendi. Bu kadar seçenek arasından bazılarının rastgele iyi çıkması beklenir (aşırı uydurma riski).
- Yalnızca 2 yıllık, tek bir piyasa dönemi test edildi. 6 yıllık veride aynı ayarlar al-tut'u geçemedi.
- Bazı adaylar sadece 8-14 işleme dayanıyor; bu sayı istatistiksel olarak zayıf.

## Çıkarılan ders

1. Kısa veriyle bulunan "iyi" strateji, uzun veride çöktü. Birden çok piyasa dönemiyle test şart.
2. Komisyon ve kayma, sık işlem yapan stratejilerin ana düşmanı.
3. Basit ortalama kesişimleri BTC'de elde tutmayı geçemedi; asıl değer, riski (max düşüşü) yönetmekte.
4. Gerçek paraya geçmeden önce geçmiş testin yanında sanal (paper) çalıştırma yapılmalı.
