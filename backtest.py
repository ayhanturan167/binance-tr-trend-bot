"""
SMA kesişim stratejisi için basit backtest.
- API anahtarı GEREKTİRMEZ (sadece herkese açık fiyat verisi çeker).
- Veriyi bir kez indirir, btc_1h.csv dosyasına kaydeder.
Kurulum: pip install python-binance pandas
"""
import os
import pandas as pd

SEMBOL = "BTCUSDT"
ARALIK = "1h"
GECMIS = "6 years ago UTC"
CSV = "btc_1h_6yil.csv"

KOMISYON = 0.001   # %0.1 (tek yön). Binance spot standart komisyonu
KAYMA = 0.0005     # %0.05 kayma (slippage) tahmini
TEST_ORANI = 0.30  # Verinin son %30'u "görülmemiş dönem" olarak ayrı raporlanır

# (kısa, uzun) ortalama çiftleri
KOMBINASYONLAR = [(7, 25), (10, 50), (20, 50), (20, 100), (50, 200)]


def veri_al():
    if os.path.exists(CSV):
        df = pd.read_csv(CSV, parse_dates=["zaman"])
        print(f"Veri dosyadan okundu: {len(df)} mum")
        return df

    from binance.client import Client
    print("Veri Binance'ten indiriliyor (birkaç dakika sürebilir)...")
    client = Client("", "")  # anahtar gerekmez, sadece açık veri
    klines = client.get_historical_klines(SEMBOL, ARALIK, GECMIS)
    df = pd.DataFrame(klines, columns=[
        "zaman", "acilis", "yuksek", "dusuk", "kapanis", "hacim",
        "kapanis_zamani", "qav", "num_trades", "tbv", "tqv", "ignore"
    ])
    df["zaman"] = pd.to_datetime(df["zaman"], unit="ms")
    df["kapanis"] = df["kapanis"].astype(float)
    df = df[["zaman", "kapanis"]]
    df.to_csv(CSV, index=False)
    print(f"{len(df)} mum indirildi ve {CSV} dosyasına kaydedildi.")
    return df


def backtest(df, kisa, uzun):
    d = df.copy().reset_index(drop=True)
    d["kisa"] = d["kapanis"].rolling(kisa).mean()
    d["uzun"] = d["kapanis"].rolling(uzun).mean()
    d = d.dropna().reset_index(drop=True)

    # Sinyal mum kapanışında hesaplanır, pozisyon bir SONRAKİ mumun getirisine uygulanır
    # (geleceği görme hatasını önlemek için shift(1))
    sinyal = (d["kisa"] > d["uzun"]).astype(int)
    poz = sinyal.shift(1).fillna(0)

    getiri = d["kapanis"].pct_change().fillna(0)
    islem = poz.diff().abs().fillna(0)          # pozisyon değişti mi (alım veya satım)
    maliyet = islem * (KOMISYON + KAYMA)
    strateji = poz * getiri - maliyet

    d["poz"] = poz
    d["strateji_getiri"] = strateji
    d["equity"] = (1 + strateji).cumprod()
    d["bh_equity"] = d["kapanis"] / d["kapanis"].iloc[0]
    return d


def islem_listesi(d):
    """Her alım-satım turunun getirisini hesaplar."""
    c = KOMISYON + KAYMA
    sonuclar = []
    giris = None
    for i in range(1, len(d)):
        if d["poz"].iloc[i] == 1 and d["poz"].iloc[i - 1] == 0:
            giris = d["kapanis"].iloc[i - 1]
        elif d["poz"].iloc[i] == 0 and d["poz"].iloc[i - 1] == 1 and giris:
            cikis = d["kapanis"].iloc[i - 1]
            sonuclar.append(cikis / giris * (1 - c) ** 2 - 1)
            giris = None
    return sonuclar


def max_dusus(equity):
    tepe = equity.cummax()
    return ((equity - tepe) / tepe).min()


def rapor_satiri(d):
    tk = d["equity"].iloc[-1] / d["equity"].iloc[0] - 1
    bh = d["kapanis"].iloc[-1] / d["kapanis"].iloc[0] - 1
    # equity'yi bu dilimin başına göre normalize et
    eq = d["equity"] / d["equity"].iloc[0]
    islemler = islem_listesi(d)
    kazanma = (sum(1 for x in islemler if x > 0) / len(islemler) * 100) if islemler else 0
    return tk * 100, bh * 100, len(islemler), kazanma, max_dusus(eq) * 100


def main():
    df = veri_al()
    print(f"Dönem: {df['zaman'].iloc[0]} -> {df['zaman'].iloc[-1]}\n")

    baslik = f"{'Strateji':<10}{'Getiri%':>10}{'Al-Tut%':>10}{'İşlem':>8}{'Kazanma%':>10}{'MaxDüşüş%':>11}"
    print("=== TÜM DÖNEM ===")
    print(baslik)
    for k, u in KOMBINASYONLAR:
        d = backtest(df, k, u)
        r = rapor_satiri(d)
        print(f"SMA {k}/{u:<4}{r[0]:>10.1f}{r[1]:>10.1f}{r[2]:>8}{r[3]:>10.1f}{r[4]:>11.1f}")

    print("\n=== SADECE SON %30 (stratejinin 'görmediği' dönem) ===")
    print(baslik)
    for k, u in KOMBINASYONLAR:
        d = backtest(df, k, u)
        kesim = int(len(d) * (1 - TEST_ORANI))
        dt = d.iloc[kesim:].reset_index(drop=True)
        r = rapor_satiri(dt)
        print(f"SMA {k}/{u:<4}{r[0]:>10.1f}{r[1]:>10.1f}{r[2]:>8}{r[3]:>10.1f}{r[4]:>11.1f}")

    print("\nNot: 'Al-Tut' = hiçbir şey yapmadan BTC'yi elde tutsaydın oluşacak getiri.")
    print("Strateji Al-Tut'u geçemiyorsa ve düşüşü de belirgin azaltmıyorsa bot işe yaramıyor demektir.")


if __name__ == "__main__":
    main()
