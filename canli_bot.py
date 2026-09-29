"""
Binance TR için canlı bot: yavaş trend stratejisi (SMA kesişim), risk limitli, Telegram bildirimli.
(Binance TR'nin kendi API'sini kullanır: https://www.binance.tr/apidocs)

MOD:
  DRY_RUN=1 (varsayılan)  -> SANAL para ile çalışır, borsaya emir GİTMEZ. Anahtar gerekmez.
  DRY_RUN=0               -> GERÇEK emir gönderir. API anahtarı gerekir.

Kurulum: pip install requests pandas
Ortam değişkenleri (PowerShell):
  $env:BINANCE_KEY="..."            (sadece gerçek mod)
  $env:BINANCE_SECRET="..."         (sadece gerçek mod)
  $env:TELEGRAM_TOKEN="..."         (bildirim için, isteğe bağlı)
  $env:TELEGRAM_CHAT_ID="..."       (bildirim için, isteğe bağlı)
  $env:DRY_RUN="0"                  (gerçek mod için)
"""
import os
import sys
import json
import time
import hmac
import hashlib
import logging
from decimal import Decimal, ROUND_DOWN

import requests
import pandas as pd

# ---------------- AYARLAR ----------------
DRY_RUN = os.getenv("DRY_RUN", "1") != "0"
API_ANA = "https://www.binance.tr"          # /open/v1/... uçları
API_PIYASA = "https://api.binance.me"       # klines uçları
SEMBOL = "BTC_TRY"                          # Binance TR biçimi (alt çizgili)
SEMBOL_PIYASA = SEMBOL.replace("_", "")     # klines için: BTCTRY
BASE_ASSET = "BTC"
QUOTE_ASSET = "TRY"

ARALIK = "4h"
KISA, UZUN = 50, 200
STOP_LOSS = 0.05              # %5 zarar durdurma
YATIRIM = float(os.getenv("YATIRIM", "1800"))  # TL, tek pozisyonda kullanılacak en çok tutar
MAKS_TOPLAM_ZARAR = 0.25      # Sermayenin %25'i kaybedilirse bot KENDİNİ KAPATIR
KONTROL_SANIYE = 300          # 5 dakikada bir kontrol
SANAL_BASLANGIC_TL = 2000.0
KOMISYON = 0.001
OZET_SAATI = 9                # günlük özet mesajı saati (yerel saat)

TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")

STATE = "bot_durum_sanal.json"   # moda göre main() içinde değişir
AYAR = "bot_ayarlar.json"        # Telegram bilgileri burada saklanır
LOG = "bot.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler(LOG, encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("bot")


# ---------------- TELEGRAM ----------------
def bildir(mesaj):
    """Telegram'a mesaj yollar. Hata olursa botu asla durdurmaz."""
    log.info(f"[BİLDİRİM] {mesaj}")
    if not TG_TOKEN or not TG_CHAT:
        log.warning("Telegram KAPALI: TELEGRAM_TOKEN / TELEGRAM_CHAT_ID bu terminalde tanımlı değil.")
        return
    try:
        etiket = "SANAL" if DRY_RUN else "GERÇEK"
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={"chat_id": TG_CHAT, "text": f"[{etiket}] {mesaj}"},
            timeout=10,
        )
        if r.status_code != 200:
            log.error(f"Telegram reddetti ({r.status_code}): {r.text}")
    except Exception as e:
        log.error(f"Telegram gönderilemedi: {e}")


# ---------------- DURUM DOSYASI ----------------
def durum_yukle():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {
        "giris_fiyati": None,
        "stop_sonrasi_bekle": False,
        "baslangic_ozkaynak": None,
        "sanal_try": SANAL_BASLANGIC_TL,
        "sanal_base": 0.0,
        "durdu": False,
        "son_ozet_gun": None,
    }


def durum_kaydet(d):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)


# ---------------- BINANCE TR İSTEMCİSİ ----------------
class TRClient:
    def __init__(self, key=None, secret=None):
        self.key = key
        self.secret = secret
        self.s = requests.Session()
        if key:
            self.s.headers.update({"X-MBX-APIKEY": key})

    @staticmethod
    def _kontrol(r):
        r.raise_for_status()
        j = r.json()
        if isinstance(j, dict) and j.get("code", 0) != 0:
            raise RuntimeError(f"Binance TR hata kodu={j.get('code')} mesaj={j.get('msg') or j.get('message')}")
        return j

    def _imzali(self, yontem, yol, params):
        if not (self.key and self.secret):
            raise RuntimeError("Bu işlem için API anahtarı gerekli")
        params = dict(params)
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 5000
        sorgu = "&".join(f"{k}={v}" for k, v in params.items())
        imza = hmac.new(self.secret.encode(), sorgu.encode(), hashlib.sha256).hexdigest()
        url = f"{API_ANA}{yol}"
        if yontem == "GET":
            r = self.s.get(f"{url}?{sorgu}&signature={imza}", timeout=15)
        else:
            r = self.s.post(url, data=f"{sorgu}&signature={imza}",
                            headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
        return self._kontrol(r)

    # -- herkese açık
    def sembol_bilgisi(self, sembol):
        j = self._kontrol(self.s.get(f"{API_ANA}/open/v1/common/symbols", timeout=15))
        for x in j["data"]["list"]:
            if x["symbol"] == sembol:
                return x
        return None

    def mumlar(self, sembol_piyasa, aralik, limit):
        r = self.s.get(f"{API_PIYASA}/api/v1/klines",
                       params={"symbol": sembol_piyasa, "interval": aralik, "limit": limit}, timeout=15)
        j = self._kontrol(r)
        return j["data"] if isinstance(j, dict) else j

    def son_fiyat(self, sembol_piyasa):
        m = self.mumlar(sembol_piyasa, "1m", 2)
        return float(m[-1][4])

    # -- imzalı
    def bakiyeler(self):
        j = self._imzali("GET", "/open/v1/account/spot", {})
        return {a["asset"]: float(a["free"]) for a in j["data"]["accountAssets"]}

    def piyasa_emri(self, sembol, yon, miktar=None, tl_tutar=None):
        p = {"symbol": sembol, "side": 0 if yon == "BUY" else 1, "type": 2}
        if yon == "BUY":
            p["quoteOrderQty"] = f"{tl_tutar:.2f}"
        else:
            p["quantity"] = f"{miktar:.8f}".rstrip("0").rstrip(".")
        return self._imzali("POST", "/open/v1/orders", p)


def adim_yuvarla(miktar, step):
    step = Decimal(str(step))
    return float((Decimal(str(miktar)) / step).to_integral_value(rounding=ROUND_DOWN) * step)


class Borsa:
    def __init__(self, client, durum):
        self.c = client
        self.d = durum
        info = self.c.sembol_bilgisi(SEMBOL)
        if not info:
            raise RuntimeError(f"{SEMBOL} çifti bulunamadı.")
        self.step = 0.00001
        self.min_notional = 0.0
        for f in info.get("filters", []):
            if f["filterType"] == "LOT_SIZE":
                self.step = float(f["stepSize"])
            if f["filterType"] in ("MIN_NOTIONAL", "NOTIONAL"):
                self.min_notional = float(f.get("minNotional", 0))

    def fiyat(self):
        return self.c.son_fiyat(SEMBOL_PIYASA)

    def bakiye(self):
        if DRY_RUN:
            return self.d["sanal_try"], self.d["sanal_base"]
        b = self.c.bakiyeler()
        return b.get(QUOTE_ASSET, 0.0), b.get(BASE_ASSET, 0.0)

    def al(self, tl_tutar, fiyat):
        if DRY_RUN:
            coin = tl_tutar / fiyat * (1 - KOMISYON)
            self.d["sanal_try"] -= tl_tutar
            self.d["sanal_base"] += coin
        else:
            self.c.piyasa_emri(SEMBOL, "BUY", tl_tutar=tl_tutar)
        bildir(f"ALIM: {tl_tutar:.2f} TL ile {BASE_ASSET} alındı, fiyat ≈ {fiyat:,.0f} TL")

    def sat(self, coin, fiyat, sebep):
        miktar = adim_yuvarla(coin, self.step)
        if miktar <= 0:
            return
        if DRY_RUN:
            tl = miktar * fiyat * (1 - KOMISYON)
            self.d["sanal_base"] -= miktar
            self.d["sanal_try"] += tl
        else:
            self.c.piyasa_emri(SEMBOL, "SELL", miktar=miktar)
        bildir(f"SATIŞ ({sebep}): {miktar} {BASE_ASSET} satıldı, fiyat ≈ {fiyat:,.0f} TL")


# ---------------- SİNYAL ----------------
def sinyal_al(client):
    """Son KAPANMIŞ mumlara göre kısa>uzun ise 1, değilse 0."""
    kl = client.mumlar(SEMBOL_PIYASA, ARALIK, UZUN + 60)
    kapanis = pd.Series([float(k[4]) for k in kl]).iloc[:-1]   # son (kapanmamış) mumu at
    if len(kapanis) < UZUN + 1:
        raise RuntimeError("Yeterli mum verisi yok")
    kisa = kapanis.rolling(KISA).mean().iloc[-1]
    uzun = kapanis.rolling(UZUN).mean().iloc[-1]
    return int(kisa > uzun), kisa, uzun


# ---------------- ANA DÖNGÜ ----------------
def gunluk_ozet(d, ozkaynak, pozisyonda):
    simdi = time.localtime()
    bugun = time.strftime("%Y-%m-%d", simdi)
    if simdi.tm_hour >= OZET_SAATI and d.get("son_ozet_gun") != bugun:
        d["son_ozet_gun"] = bugun
        bas = d["baslangic_ozkaynak"] or ozkaynak
        degisim = (ozkaynak / bas - 1) * 100
        bildir(f"Günlük özet: özkaynak {ozkaynak:.0f} TL ({degisim:+.1f}% başlangıca göre), "
               f"pozisyon: {'VAR' if pozisyonda else 'YOK'}. Bot çalışıyor.")


def tur(borsa, client, d):
    fiyat = borsa.fiyat()
    tl, coin = borsa.bakiye()
    ozkaynak = tl + coin * fiyat
    if d["baslangic_ozkaynak"] is None:
        d["baslangic_ozkaynak"] = ozkaynak
        bildir(f"Bot başladı. Başlangıç özkaynak: {ozkaynak:.0f} TL. Strateji: {ARALIK} SMA{KISA}/{UZUN}, stop %{STOP_LOSS*100:.0f}.")

    if ozkaynak < d["baslangic_ozkaynak"] * (1 - MAKS_TOPLAM_ZARAR):
        bildir(f"⚠️ TOPLAM ZARAR LİMİTİ AŞILDI (özkaynak {ozkaynak:.0f} TL). Pozisyon kapatılıp bot DURDURULUYOR.")
        if coin * fiyat > max(borsa.min_notional, 1):
            borsa.sat(coin, fiyat, "zarar limiti")
        d["durdu"] = True
        return

    pozisyonda = coin * fiyat >= max(borsa.min_notional, 1) and coin > 0
    sinyal, kisa, uzun = sinyal_al(client)
    if sinyal == 0:
        d["stop_sonrasi_bekle"] = False

    log.info(f"Fiyat={fiyat:.2f} | SMA{KISA}={kisa:.2f} SMA{UZUN}={uzun:.2f} | sinyal={sinyal} "
             f"| pozisyon={pozisyonda} | özkaynak={ozkaynak:.2f} TL")

    if pozisyonda:
        if d["giris_fiyati"] is None:
            d["giris_fiyati"] = fiyat
        if fiyat <= d["giris_fiyati"] * (1 - STOP_LOSS):
            borsa.sat(coin, fiyat, "STOP-LOSS")
            d["giris_fiyati"] = None
            d["stop_sonrasi_bekle"] = bool(sinyal == 1)
        elif sinyal == 0:
            borsa.sat(coin, fiyat, "trend bitti")
            d["giris_fiyati"] = None
    else:
        if sinyal == 1 and not d["stop_sonrasi_bekle"]:
            tutar = min(YATIRIM, tl * 0.98)
            if tutar < max(borsa.min_notional, 10):
                log.warning(f"Alım için yeterli TL yok ({tl:.2f}). Min emir: {borsa.min_notional}")
            else:
                borsa.al(tutar, fiyat)
                d["giris_fiyati"] = fiyat

    gunluk_ozet(d, ozkaynak, pozisyonda or d['giris_fiyati'] is not None)


def _temiz(x):
    return (x or "").strip().strip('"').strip("'")


def telegram_dogrula(token, chat):
    """Token ve chat id'yi dener; (basarili, aciklama) döndürür."""
    if token.lower().startswith("bot"):
        token = token[3:]
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15)
        if r.status_code != 200:
            return False, "Token yanlış görünüyor (BotFather'dan tekrar kopyala).", token
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          data={"chat_id": chat, "text": "Bot kurulumu tamam, bildirimler bu sohbete gelecek."}, timeout=15)
        if r.status_code != 200:
            return False, "Chat id yanlış ya da kendi botunda Başlat'a basmadın.", token
    except Exception as e:
        return False, f"Telegram'a bağlanılamadı: {e}", token
    return True, "ok", token


def ayarlari_hazirla():
    """Telegram bilgilerini ve çalışma modunu (sanal/gerçek) ister. Dosya düzenlemek gerekmez."""
    global TG_TOKEN, TG_CHAT, DRY_RUN, STATE
    cfg = {}
    if os.path.exists(AYAR):
        with open(AYAR, encoding="utf-8") as f:
            cfg = json.load(f)
    TG_TOKEN = _temiz(TG_TOKEN) or cfg.get("telegram_token")
    TG_CHAT = _temiz(TG_CHAT) or cfg.get("telegram_chat_id")

    # Telegram
    if not TG_TOKEN or not TG_CHAT:
        print("\n--- TELEGRAM KURULUMU (telefona bildirim için) ---")
        print("Atlamak istersen iki soruda da sadece Enter'a bas.")
        for _ in range(3):
            t = _temiz(input("Token (BotFather'dan, içinde : olan uzun yazı): "))
            if not t:
                TG_TOKEN = TG_CHAT = None
                print("Telegram atlandı, bildirim gelmeyecek.")
                break
            c = _temiz(input("Chat id (userinfobot'tan, sadece rakamlar): "))
            ok, aciklama, t = telegram_dogrula(t, c)
            if ok:
                TG_TOKEN, TG_CHAT = t, c
                with open(AYAR, "w", encoding="utf-8") as f:
                    json.dump({"telegram_token": t, "telegram_chat_id": c}, f)
                print("Telegram bağlandı, telefonuna test mesajı gitti. Bilgiler kaydedildi.\n")
                break
            print("HATA:", aciklama, "Tekrar dene.\n")
        else:
            TG_TOKEN = TG_CHAT = None
            print("Telegram 3 denemede bağlanamadı, atlanıyor.\n")

    # Mod
    if os.getenv("DRY_RUN") is None:
        print("\n--- MOD SEÇİMİ ---")
        print("Sadece Enter = SANAL mod (gerçek para kullanılmaz, önerilen).")
        secim = input("Gerçek para ile işlem için  GERCEK  yaz: ").strip().upper()
        DRY_RUN = secim != "GERCEK"
    STATE = "bot_durum_sanal.json" if DRY_RUN else "bot_durum_gercek.json"


def main():
    ayarlari_hazirla()
    d = durum_yukle()
    if d.get("durdu"):
        log.error(f"Bot daha önce güvenlik limiti nedeniyle durdu. Nedenini incele, sonra {STATE} dosyasını silip yeniden başlat.")
        return

    if DRY_RUN:
        log.info("=== SANAL MOD (gerçek emir gitmez) ===")
        client = TRClient()
    else:
        key, sec = _temiz(os.getenv("BINANCE_KEY")), _temiz(os.getenv("BINANCE_SECRET"))
        if not key or not sec:
            print("\n--- GERÇEK MOD: Binance TR API anahtarları (kaydedilmez, her açılışta sorulur) ---")
            key = _temiz(input("API Key: "))
            sec = _temiz(input("Secret Key: "))
            if input(f"{YATIRIM:.0f} TL'ye kadar GERÇEK alım-satım yapılacak. Onaylıyorsan EVET yaz: ").strip().upper() != "EVET":
                sys.exit("Onaylanmadı, bot kapatıldı.")
        if not key or not sec:
            sys.exit("API anahtarı girilmedi.")
        log.warning("=== GERÇEK MOD: gerçek para ile emir gönderilecek ===")
        client = TRClient(key, sec)

    borsa = Borsa(client, d)
    log.info(f"Sembol={SEMBOL} aralık={ARALIK} SMA {KISA}/{UZUN} stop=%{STOP_LOSS*100:.0f} "
             f"yatırım<={YATIRIM} TL. Durdurmak için Ctrl+C.")

    hata_sayac = 0
    while True:
        try:
            tur(borsa, client, d)
            durum_kaydet(d)
            hata_sayac = 0
            if d.get("durdu"):
                return
        except KeyboardInterrupt:
            durum_kaydet(d)
            bildir("Bot elle durduruldu.")
            return
        except Exception as e:
            hata_sayac += 1
            log.error(f"Hata ({hata_sayac}/10): {e}")
            if hata_sayac == 3:
                bildir(f"⚠️ Bot art arda 3 hata aldı: {e}")
        if hata_sayac >= 10:
            bildir("🛑 Art arda 10 hata. Bot güvenlik için DURDU. Log dosyasına bak.")
            return
        try:
            time.sleep(KONTROL_SANIYE)
        except KeyboardInterrupt:
            durum_kaydet(d)
            bildir("Bot elle durduruldu.")
            return


if __name__ == "__main__":
    main()
