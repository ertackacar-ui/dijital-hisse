"""HEDGE FUND - Makro Likidite & Takvim (14. ajan).

Kullanim: .venv/bin/python .claude/scripts/makro_likidite_takvim.py
VIX vade egrisi (^VIX9D/^VIX/^VIX3M -> contango/backwardation), HYG/IEF kredi istahi, SOXX/QQQ cip liderligi,
FOMC (resmi 2026-2027 takvimi gomulu) ve NYSE tatil/yarim gun takvimi; NFP/CPI/PCE icin kural tabanli pencere (resmi tarih degil).
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kar_kalkani import pct, veri_cek

# Fed'in yayimladigi FOMC toplanti ikinci gunleri (karar gunu)
# federalreserve.gov/monetarypolicy/fomccalendars.htm ile 25 Kasim 2026'da dogrulandi (2027 tarihleri bir onceki toplantida kesinlesir)
FOMC = ["2026-12-09", "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09", "2027-07-28", "2027-09-15", "2027-10-27", "2027-11-17"]
# NYSE resmi tatilleri ve 13:00 erken kapanislar
NYSE_TATIL = {"2026-11-26": "Şükran Günü", "2026-12-25": "Noel", "2027-01-01": "Yılbaşı", "2027-01-18": "MLK Günü",
              "2027-02-15": "Başkanlar Günü", "2027-03-26": "Kutsal Cuma", "2027-05-31": "Anma Günü", "2027-06-18": "Juneteenth (gözlem)",
              "2027-07-05": "Bağımsızlık Günü (gözlem)", "2027-09-06": "İşçi Bayramı", "2027-11-25": "Şükran Günü", "2027-12-24": "Noel (gözlem)"}
NYSE_YARIM = {"2026-11-27": "Şükran ertesi 13:00 kapanış", "2026-12-24": "Noel arifesi 13:00 kapanış", "2027-11-26": "Şükran ertesi 13:00 kapanış"}
UFUK = 45


def ilk_cuma(y, m):
    d = date(y, m, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def kural_takvimi(bugun):
    """Resmi tarih degil: NFP genelde ayin ilk Cumasi, CPI 10-15 arasi, PCE ayin son haftasi. BLS/BEA ile dogrulanmali."""
    out = []
    for k in range(3):
        y, m = (bugun.year + (bugun.month - 1 + k) // 12, (bugun.month - 1 + k) % 12 + 1)
        out.append((ilk_cuma(y, m), "NFP (tarım dışı istihdam) — kural: ayın ilk Cuması"))
        out.append((date(y, m, 10), "CPI penceresi 10-15 — kural, BLS ile doğrula"))
        out.append((date(y, m, 26), "PCE penceresi ayın son haftası — kural, BEA ile doğrula"))
    return out


def oran_degisim(veri, a, b, n=20):
    if a not in veri or b not in veri:
        return None, None
    r = (veri[a]["Close"] / veri[b]["Close"]).dropna()
    return float(r.iloc[-1]), pct(r.iloc[-1], r.iloc[-1 - n])


def main():
    bugun = date.today()
    veri = veri_cek(["^VIX9D", "^VIX", "^VIX3M", "HYG", "IEF", "SOXX", "QQQ"], period="3mo")
    son = lambda t: float(veri[t]["Close"].iloc[-1]) if t in veri else None
    v9, v, v3 = son("^VIX9D"), son("^VIX"), son("^VIX3M")
    print("=" * 100)
    print(f"HEDGE FUND — MAKRO LİKİDİTE & TAKVİM | {bugun}")
    print("=" * 100)
    print("(1) VIX VADE EĞRİSİ")
    if None in (v9, v, v3):
        print("    VERİ YOK (VIX9D/VIX/VIX3M alınamadı)")
    else:
        if v9 > v > v3: yapi = "TAM BACKWARDATION — akut stres, kısa vade korku uzun vadeyi aştı"
        elif v9 > v or v > v3: yapi = "KISMİ BACKWARDATION — stres yükseliyor"
        else: yapi = "CONTANGO — normal yapı, panik yok"
        print(f"    VIX9D {v9:.2f} | VIX {v:.2f} | VIX3M {v3:.2f} → {yapi}")
        print(f"    VIX/VIX3M oranı {v/v3:.2f} ({'>1 stres' if v/v3 > 1 else '<1 sakin'})")
    print("(2) KREDİ İŞTAHI ve ÇİP LİDERLİĞİ (20 günlük)")
    for a, b, ad in (("HYG", "IEF", "HYG/IEF (riskli tahvil / güvenli tahvil)"), ("SOXX", "QQQ", "SOXX/QQQ (çipler / teknoloji)")):
        oran, d = oran_degisim(veri, a, b)
        if oran is None:
            print(f"    {ad}: VERİ YOK")
        else:
            yon = "RİSK İŞTAHI ARTIYOR" if d > 1 else "RİSKTEN KAÇIŞ" if d < -1 else "yatay"
            if a == "SOXX": yon = "çipler önder" if d > 1 else "çipler geride kalıyor" if d < -1 else "yatay"
            print(f"    {ad}: {oran:.3f} | 20G {d:+.1f}% → {yon}")
    print(f"(3) OLAY TAKVİMİ (önümüzdeki {UFUK} gün)")
    olaylar = [(date.fromisoformat(d), "FOMC KARAR GÜNÜ (resmi)") for d in FOMC]
    olaylar += [(date.fromisoformat(d), f"NYSE KAPALI: {ad}") for d, ad in NYSE_TATIL.items()]
    olaylar += [(date.fromisoformat(d), f"NYSE YARIM GÜN: {ad}") for d, ad in NYSE_YARIM.items()]
    olaylar += kural_takvimi(bugun)
    for d, ad in sorted(olaylar):
        kalan = (d - bugun).days
        if 0 <= kalan <= UFUK:
            uyari = "  ← 3 GÜN İÇİNDE" if kalan <= 3 else ""
            print(f"    {d} ({kalan:>2} gün)  {ad}{uyari}")
    print("\nFOMC ve NYSE tarihleri resmi takvimden gömülüdür; NFP/CPI/PCE satırları kural tabanlı penceredir, resmi tarih değildir.")
    print("Bilgi amaçlıdır; saat tahmini yapılmaz, alım kararı VIX kilidine tabidir.")


if __name__ == "__main__":
    main()
