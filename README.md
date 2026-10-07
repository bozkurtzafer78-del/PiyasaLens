# PiyasaLens Research Console

Türkçe, responsive bir piyasa araştırma uygulamasıdır. Günlük kapanış/tarama verisi kullanır; sessizce gerçek zamanlı veri iddiasında bulunmaz ve otomatik emir göndermez.

## Çalıştırma

```bash
npm test
npm start
```

Ardından `http://localhost:4173` adresini açın.

## Mevcut kapsam

- Enstrüman detay görünümü, demo fiyat, veri zamanı ve veri durumu.
- Net potansiyel hesabı: alış/satış maliyetleriyle birlikte; yuvarlanmamış eşik kontrolü.
- Yeni alım ve mevcut pozisyon kararlarının ayrılması.
- Alım bandı aşımı, %5 altı net getiri, minimum 2:1 risk/getiri, eksik veri ve tez kırılması kuralları.
- JavaScript ve Python katmanlarında toplam 22 otomatik test: %4,99 engeli, %5 tek başına yeterli değil, band aşımı, maliyet etkisi, eksik/veri bayatlığı, birleşik şema, tarama normalizasyonu, karar ayrıştırması ve günlük kota politikası.
- Demo katalog dışı semboller için kesin karar yerine açıkça “Veri yetersiz” gösterilir; arama sonucu sessizce THYAO verisine düşmez.
- [data-provider.js](data-provider.js) değiştirilebilir sağlayıcı sınırını ve BIST/ABD/ETF varlık sınıflandırmasını içerir.
- Oturum açılmadığında pozisyon/takip/alarm bilgileri `localStorage` ile korunur; Firebase hesabı açıldığında kullanıcıya özel Firestore profilinde senkronize edilir. Emir gönderimi yoktur.
- Gerçek sağlayıcı için [provider-adapter.js](provider-adapter.js) ve [.env.example](.env.example) hazırdır. Güncel veri hattı Twelve Data EOD kullanır; gerçek zamanlı veri iddiasında bulunmaz.
- Python veri servisi [data_service.py](data_service.py) ile `/api/status`, `/api/instruments?q=`, `/api/quote?symbol=` ve ortak sözleşmeli `/api/analysis?symbol=` endpoint’lerini sağlar. Proje kökündeki `.env` dosyasını otomatik okur. Çalıştırma: `python3 data_service.py`; test: `python3 -m unittest discover -v`.
- Twelve Data EOD seçildi. `.env.example` Twelve Data `/eod` endpoint’ini kullanır; yanıt `values[0].close`, `values[0].datetime` ve `meta.currency` alanlarına normalize edilir. BIST XIST erişimi için uygun plan ve harici gösterim/ticari kullanım lisansı doğrulanmalıdır.
- Birleşik backend çekirdeği `backend/normalized_schema.py` ve `backend/divergence_engine.py` içinde kuruldu. Bu katman HisseRadar KAP, USStockRadar SEC, zfinace quant ve PiyasaLens karar motorunun ortak veri sözleşmesidir.
- Günlük piyasa pipeline'ı [twelve_data_batch.py](twelve_data_batch.py) ile [data/universe.json](data/universe.json) içindeki seçilmiş evrenden EOD fiyatlarını batch çağrısıyla alır. Varsayılan kota dağılımı 60 BIST + 60 ABD sembolüdür; çalıştırma: `python3 collect_and_analyze.py --market all --analyze`. Çıktılar `data/latest_market.json` ve Gemini etkinse `data/latest_strategy.json` içine yazılır.
- Gemini katmanı [gemini_analysis.py](gemini_analysis.py) yalnızca yerel puanlamadan geçen normalize adayları tek yapılandırılmış JSON isteğiyle analiz eder. `GEMINI_API_KEY`, `GEMINI_MODEL` ve `GEMINI_TOP_N` değerleri `.env` içinde tutulur; anahtar tarayıcıya gönderilmez.

## Ürün sınırları

Güncel sürüm günlük kapanış/tarama verisi kullanır; gerçek zamanlı fiyat akışı ve otomatik emir gönderimi yoktur. Manuel veri yenileme kapalıdır. Kullanıcı hesapları ve kalıcı saklama Firebase Authentication/Firestore ile hazırlanmıştır; zamanlanmış piyasa görevinin canlı çalışması için Firebase Functions dağıtımı gereklidir.

TradingView tarama endpoint'i üretim veri hattından çıkarılmıştır. Twelve Data kişisel/kurumsal kullanım ve gösterim lisansının seçilen planla uyumlu olduğu ayrıca doğrulanmalıdır.

## Üretime geçiş planı

1. **Temel kalite ve görsel sonlandırma — tamamlandı**
   - Türkçe arayüz, okunabilir yazı ölçekleri, mobil düzen, erişilebilir metin tablosu ve yerel alarm/takip listesi.
   - JavaScript ve Python testleri çalıştırılıyor; günlük veri tazeliği arayüzde kontrol ediliyor.
2. **Günlük veri hattı — büyük ölçüde hazır**
   - Twelve Data EOD batch adaptörü, açık 60 BIST + 60 ABD kotası, sembol evreni dosyası ve ortak normalize şema.
   - Ücretsiz planın 800/gün sınırı aşılmadan genişletilebilir; daha geniş evren için plan ve BIST kapsamı doğrulanmalı.
3. **Kaynak API katmanı — kod hazır, yayın için Blaze gerekli**
   - KAP ve SEC Functions endpoint'leri hazır; Firebase Functions deploy'u için proje Blaze plana geçirilmelidir.
   - Günlük piyasa snapshot'ı için iki toplu tarama isteği hafta içi 19:15 (Europe/Istanbul) zamanlanmıştır. İstemcide manuel yenileme kapalıdır; aynı gün içinde sağlayıcıya tekrar tekrar istek gönderilmez.
   - Hazır backend yayını için `bash deploy_backend.sh` kullanılabilir.
4. **Kullanıcı hesabı ve kalıcı saklama — istemci ve güvenlik kodu hazır**
   - Firebase Web App kaydı, e-posta/şifre hesap ekranı, kullanıcıya özel Firestore şeması ve güvenlik kuralları eklendi.
   - Firebase Console/Google Cloud tarafında Authentication sağlayıcısı ve Firestore API etkinleştirildiğinde hesap senkronizasyonu aktif olacaktır.
5. **Otomatik günlük tarama ve bildirimler**
   - Render `piyasalens-daily-refresh` Cron görevi Twelve Data EOD pipeline'ını çalıştırır; çıktı Firestore `marketSnapshots` kayıtlarına sayfalanarak yazılır.
   - Zamanlanmış Functions/Cloud Scheduler yayını için Firebase projesinin Blaze planında olması gerekir; ücretsiz kotayı korumak için görev yalnızca hafta içi bir kez çalışır.
6. **Son üretim QA ve yayın**
   - Mobil/masaüstü tarayıcı kontrolü, hata senaryoları, kaynak bağlantıları, veri tazeliği ve Firebase güvenlik kuralları doğrulanıp son sürüm deploy edilecek.
