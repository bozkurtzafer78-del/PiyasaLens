# PiyasaLens Research Console

Türkçe BIST/ABD piyasa araştırma ekranı. BIST gecikmeli, ABD günlük kapanış verisi kullanılır. Takip listesi, yerel tarayıcı alarmları ve isteğe bağlı Firebase hesabı vardır. Otomatik emir gönderilmez.

## Yerel çalıştırma

Node.js 22 ve Python 3.10+ gerekir.

```bash
npm ci
npm ci --prefix functions
python3 -m pip install -r requirements.txt
cp .env.example .env
npm test
python3 -m unittest discover -v
npm start
```

Arayüz: http://localhost:4173. Anahtarlar `.env` içine veya sunucu ortamına girilir. Node ve Python bu dosyayı okur. Fiyat verisi yokken açık bir veri hatası gösterilir; gerçek veri yerine sessizce demo kullanılmaz. İlk snapshot için:

```bash
python3 collect_and_analyze.py --market all --analyze
```

BIST için `BIST_DATA_SERVICE_URL` ve gerekiyorsa `BIST_DATA_SERVICE_API_KEY`; ABD için `MARKET_DATA_API_KEY` gerekir. BIST toplama ABD anahtarına bağlı değildir. ABD evreni `data/universe.json` ile yönetilir; varsayılan sekiz semboldür. Çoklu istekler arasında 60 saniye beklenir. Günlük görevin aynı gün yeniden çağrılması başarılı snapshot varsa sağlayıcıyı tekrar çağırmaz. Başarısız yenileme önceki başarılı dosyayı korur. Kısmi sağlayıcı hataları açıkça raporlanır.

## Puanlama ve yapay zekâ

Fiyat sağlayıcıları tek başına temel finansal metrik sağlamaz. `FUNDAMENTALS_PATH` ile yerel dosya veya `FUNDAMENTALS_URL` ile HTTPS JSON kaynağı bağlanır. İsteğe bağlı anahtar `FUNDAMENTALS_API_KEY` ile sunucuda tutulur. [Veri sözleşmesi](data/README.md) kaynak, tarih ve metrik birimlerini açıklar. Başlangıç dosyası boştur; gerçek finansal veri içermez.

Ağırlıklar: F/K %30, ROE %20, gelir büyümesi %20, RSI %15, borç/özsermaye %15. En az üç kullanılabilir bileşen ve %65 veri kapsamı gerekir. Eksik bileşenlerin ağırlığı kalanlara aktarılmaz. Tek bir ucuz F/K yüksek toplam skor üretemez. Temel veri en fazla 180 günlük, teknik veri en fazla dört günlük olabilir. Skor bir yatırım tavsiyesi değildir.

Gemini için `GEMINI_API_KEY` ve hesabınızın erişebildiği `GEMINI_MODEL` gerekir. Model ismi varsayılmaz. Yeterli metrik yoksa Gemini çağrısı yapılmaz. Çıktıdaki semboller, kararlar ve güven aralığı doğrulanır. Analiz piyasa snapshot'ıyla birlikte saklanır; farklı tarihli analiz güncel verilere bağlanmaz. Arayüz, kaynak fiyatlarının en eskisinin yaşını gösterir; 96 saatten eski veya zamanı eksik veri için AI seçimi göstermez. Bu eşik hafta sonuna tolerans sağlar; borsa tatil takvimiyle otomatik uyarlama içermez.

## API ve güvenlik

- `GET /api/health`, `/api/providers`: yapılandırma durumu.
- `GET /api/market`, `/api/strategy`: aynı snapshot'ın fiyatları ve analizi.
- `GET /api/kap?symbol=THYAO`, `/api/sec?symbol=AAPL`: birincil kaynak bağlantıları.
- `POST /api/refresh`: yalnız `Authorization: Bearer <REFRESH_TOKEN>` ile çalışır.

Sunucu yalnız açıkça izin verilen web dosyalarını sunar. `.env`, kaynak kod, paketler ve cache dosyaları sunulmaz. Cloud snapshot sayfaları önce yazılır, aktif snapshot işaretçisi en son güncellenir; daha küçük yeni evrende eski sayfalar karışmaz. Eski sürüm sayfalarının saklama/temizleme politikası yayın ortamında ayrıca belirlenmelidir.

Kullanıcı profilleri Firestore `users/{uid}/profile/main` altında tutulur. Güvenlik kuralları yalnız hesap sahibinin erişimine izin verir. Hesaptan çıkışta o hesabın yerel takip ve alarm verileri temizlenir. Alarmlar uygulama açıkken veri yükleme/seçim sırasında değerlendirilir; arka planda push servisi yoktur.

İsteğe bağlı ayrı Python sözleşme/demo servisi `python3 data_service.py` ile 4180 portunda çalışır. Eksik `backend` modülleri tamamlanmıştır. Ana ekran Node API'sini kullanır. Ayrı Python servisindeki yalnız fiyat içeren analiz kesin karar üretmez.

## Render yayını

`render-bist.yaml` ayrı BIST servisini, `render.yaml` ana uygulama ve cron görevini tanımlar. BIST URL'si, sağlayıcı anahtarları, Gemini modeli ve Firebase servis hesabı yayın ortamında ayarlanmalıdır. Ana ekran Render Node servisiyle doğrudan kullanılabilir. Firestore olmadan dosya snapshot'ları geçicidir; kalıcılık için `FIREBASE_SERVICE_ACCOUNT_JSON` gerekir.

Cron hafta içi 16:15 UTC / 19:15 Türkiye saatinde çalışır. Bu saat ABD seansı kapanmadan öncedir; ABD EOD çıktısı önceki tamamlanan seansa ait olabilir. Sağlayıcı veri zamanları arayüzde korunur. Aynı gün ABD kapanışı istenirse görev zamanı ayrıca değiştirilmelidir.

## Firebase Hosting yayını

```bash
npm ci --prefix functions
npm run build
bash deploy_backend.sh
firebase deploy --project piyasalens --only hosting,firestore
```

Yayın komutları Firebase CLI kurulumu ve giriş yapılmış hesap gerektirir. Functions parametresi `PIYASALENS_API_URL` mevcut Render backend'inin HTTPS adresi olmalıdır; CLI yayın sırasında ister. `functions/index.js` yalnız okuma API'lerini bu backend'e taşır, yenileme token'ını taşımaz. Functions yayını Blaze planı ve Firebase yetkisi gerektirir. Hosting yalnız `dist/` dosyalarını yayınlar. Authentication e-posta/şifre sağlayıcısı ve Firestore ayrıca etkinleştirilmelidir.

## Doğrulama

JavaScript karar, kota, cloud snapshot, HTTP güvenliği ve UI veri hesaplama testleri; Python normalizasyon, bağımsız BIST toplama, hata koruması, kaynaklı temel veri ve AI kapsam kontrolleri vardır. GitHub Actions iki test grubunu ve web build'ini çalıştırır. Canlı sağlayıcılar ve Firebase/Render yayını anahtar ve hesap erişimi gerektirir; yerel testler bu erişimi doğrulamaz.
