Temel veri dosyası veya HTTPS endpoint'i aynı sözleşmeyi kullanır:

```json
{
  "BIST:SEMBOL": {
    "source": "https://kaynak.example/rapor",
    "as_of": "2026-10-01T00:00:00Z",
    "pe": 12,
    "roe": 20,
    "revenue_growth": 15,
    "debt_to_equity": 60,
    "rsi_14": 55
  }
}
```

Bu sayılar yalnızca şema örneğidir, gerçek hisse verisi değildir. ROE ve büyüme yüzde puanı, borç/özsermaye yüzde (60 = 0,6 kat) olarak gönderilir. Kaynak ve tarih zorunludur. Varsayılan olarak 180 günden eski veri kullanılmaz; teknik metrikleri yalnız güncel olduklarında gönderin. API anahtarı yalnız sunucuda tutulur. Sağlayıcı kullanım hakkı kullanıcı tarafından sağlanır. Eksik temel veriyle skor veya AI seçimi yayınlanmaz.
