"""
Backtest 2: farklı zaman dilimleri (1s, 4s, 1g), trend filtresi ve stop-loss karşılaştırması.
Önce backtest.py'nin indirdiği btc_1h.csv dosyasını kullanır (aynı klasörde olmalı).
Kurulum: pip install python-binance pandas numpy
"""
import numpy as np
import pandas as pd
from backtest import veri_al

KOMISYON = 0.001
KAYMA = 0.0005
MALIYET = KOMISYON + KAYMA
TEST_ORANI = 0.30

STRATEJILER = [
    ("Kesişim 10/50", "cross", 10, 50),
    ("Kesişim 20/50", "cross", 20, 50),
    ("Kesişim 50/200", "cross", 50, 200),
    ("Fiyat>SMA50", "trend", 50, None),
    ("Fiyat>SMA100", "trend", 100, None),
    ("Fiyat>SMA200", "trend", 200, None),
]
STOPLAR = [0, 0.05, 0.10]  # 0 = stop-loss yok


def zaman_dilimi(df, kural):
    if kural == "1h":
        return df[["zaman", "kapanis"]].copy()
    d = df.set_index("zaman")["kapanis"].resample(kural).last().dropna().reset_index()
    return d


def sinyal_uret(close, tip, a, b):
    s = pd.Series(close)
    if tip == "cross":
        sig = (s.rolling(a).mean() > s.rolling(b).mean())
        ilk = b
    else:
        sig = (s > s.rolling(a).mean())
        ilk = a
    return sig.astype(int).values, ilk


def simule_et(close, sinyal, baslangic, stop):
    n = len(close)
    eq = np.ones(n)
    poz, entry, blocked = False, 0.0, False
    islemler = []  # (cikis_indeksi, getiri)
    e = 1.0
    for i in range(baslangic + 1, n):
        if poz:
            e *= close[i] / close[i - 1]
            stop_oldu = stop > 0 and close[i] <= entry * (1 - stop)
            if sinyal[i] == 0 or stop_oldu:
                e *= (1 - MALIYET)
                islemler.append((i, close[i] / entry * (1 - MALIYET) ** 2 - 1))
                poz = False
                if sinyal[i] == 1:
                    blocked = True  # stop sonrası sinyal sıfırlanana kadar tekrar girme
        else:
            if sinyal[i] == 0:
                blocked = False
            if sinyal[i] == 1 and not blocked:
                poz, entry = True, close[i]
                e *= (1 - MALIYET)
        eq[i] = e
    eq[:baslangic + 1] = 1.0
    return eq, islemler


def max_dusus(x):
    x = np.asarray(x, dtype=float)
    tepe = np.maximum.accumulate(x)
    return ((x - tepe) / tepe).min() * 100


def calistir(df, ad_dilim):
    close = df["kapanis"].values
    n = len(close)
    print(f"\n===== {ad_dilim}  ({n} mum) =====")
    print(f"{'Strateji':<18}{'Stop':>6}{'Getiri%':>9}{'AlTut%':>8}{'İşlem':>7}{'Kaz%':>6}{'MaxDüş%':>9}{'Son30%':>8}{'SonAT%':>8}  Aday")
    adaylar = []
    for ad, tip, a, b in STRATEJILER:
        sig, ilk = sinyal_uret(close, tip, a, b)
        if n - ilk < 100:
            continue
        for stop in STOPLAR:
            eq, isl = simule_et(close, sig, ilk, stop)
            e = eq[ilk:]
            c = close[ilk:]
            tum = (e[-1] / e[0] - 1) * 100
            at = (c[-1] / c[0] - 1) * 100
            kes = int(len(e) * (1 - TEST_ORANI))
            son = (e[-1] / e[kes] - 1) * 100
            son_at = (c[-1] / c[kes] - 1) * 100
            rets = [r for _, r in isl]
            kaz = (sum(1 for r in rets if r > 0) / len(rets) * 100) if rets else 0
            md = max_dusus(e)
            md_at = max_dusus(c / c[0])
            aday = tum > 0 and son > 0 and md > md_at and len(rets) >= 10  # md negatif; büyük = daha küçük düşüş
            stop_txt = f"%{int(stop*100)}" if stop else "yok"
            print(f"{ad:<18}{stop_txt:>6}{tum:>9.1f}{at:>8.1f}{len(rets):>7}{kaz:>6.0f}{md:>9.1f}{son:>8.1f}{son_at:>8.1f}  {'✓' if aday else ''}")
            if aday:
                adaylar.append((ad, stop_txt))
    return adaylar


def main():
    df = veri_al()
    print(f"Dönem: {df['zaman'].iloc[0]} -> {df['zaman'].iloc[-1]}")
    tum_adaylar = {}
    for kural, ad in [("1h", "1 SAATLİK"), ("4h", "4 SAATLİK"), ("1D", "GÜNLÜK")]:
        d = zaman_dilimi(df, kural)
        tum_adaylar[ad] = calistir(d, ad)

    print("\n===== ÖZET =====")
    print("Sütunlar: Getiri%=tüm dönem | AlTut%=elde tutma | Kaz%=kazanan işlem oranı |")
    print("MaxDüş%=en büyük düşüş | Son30%=son %30'daki getiri | SonAT%=aynı dönemde al-tut")
    print("Aday (✓) = tüm dönemde VE son %30'da kârlı, üstelik en büyük düşüşü Al-Tut'tan küçük ve en az 10 işlem.")
    toplam = sum(len(v) for v in tum_adaylar.values())
    print(f"Toplam aday sayısı: {toplam}")
    print("Not: Stop-loss kapanış fiyatına göre simüle edilir; gerçekte ani düşüşlerde daha kötü fiyattan tetiklenebilir.")


if __name__ == "__main__":
    main()
