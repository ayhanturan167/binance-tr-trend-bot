# Telegram bağlantı testi. Dosyayı DÜZENLEMENE GEREK YOK. Çalıştır, sorulanları yapıştır.
import requests

print("Telegram bağlantı testi")
print("-" * 40)
TOKEN = input("1) Token'ı yapıştır (içinde : olan uzun yazı) ve Enter'a bas: ").strip().strip('"').strip("'")
CHAT_ID = input("2) Chat id'yi yapıştır (sadece rakamlar) ve Enter'a bas: ").strip().strip('"').strip("'")

if TOKEN.lower().startswith("bot"):
    print("UYARI: Token 'bot' ile başlıyor, baştaki 'bot' kısmı olmamalı.")
    TOKEN = TOKEN[3:]
if ":" not in TOKEN:
    print("UYARI: Token içinde ':' yok. Yanlış şey yapıştırılmış olabilir.")
if not CHAT_ID.lstrip("-").isdigit():
    print("UYARI: Chat id sadece rakamlardan oluşmalı (örnek: 987654321).")

try:
    r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getMe", timeout=15)
except Exception as e:
    raise SystemExit(f"\nTelegram'a bağlanılamadı: {e}\n(İnternet, VPN ya da güvenlik duvarı sorunu olabilir.)")

print("\n[1] Token testi ->", r.status_code)
if r.status_code != 200:
    raise SystemExit("SONUÇ: Token YANLIŞ. BotFather mesajından tekrar kopyala.\nAyrıntı: " + r.text[:200])
print("Token doğru. Bot adı:", r.json()["result"].get("username"))

r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": "Test mesajı: bot bağlantısı çalışıyor"}, timeout=15)
print("\n[2] Mesaj testi ->", r.status_code)
if r.status_code == 200:
    print("SONUÇ: BAŞARILI. Telegram'a mesaj gelmiş olmalı.")
elif "chat not found" in r.text:
    print("SONUÇ: Chat id yanlış YA DA kendi botunu açıp Başlat'a basmadın.")
elif "blocked" in r.text:
    print("SONUÇ: Botu engellemişsin, engeli kaldır.")
else:
    print("SONUÇ: Hata ->", r.text[:300])
