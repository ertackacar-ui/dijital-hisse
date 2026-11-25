"""HEDGE FUND - Makro Para Akisi motoru.

Kullanim: .venv/bin/python .claude/scripts/makro_para_akisi.py
Tahvil/dolar/VIX baski rejimi + sektor ETF rotasyonu (VOO'ya gore goreceli guc) + portfoy baglanti ozeti.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kar_kalkani import gostergeler, pct, satir, seans_acik_mi, veri_cek, vix_rejimi

MAKRO = {"^TNX": "ABD 10Y Tahvil", "DX-Y.NYB": "Dolar Endeksi", "^VIX": "VIX"}
DXY_YEDEK = "UUP"
SEKTOR = {"SMH": "Yarı İletken (NVDA/AVGO/TSM/ASML/MU/AMD)", "XLK": "Teknoloji (MSFT/NOW/PANW)",
          "XLI": "Sanayi/Altyapı (PWR/VRT)", "XLF": "Finans (BRK-B/V)", "XLV": "Sağlık (LLY)",
          "XLP": "Defansif Tüketim (COST)", "VOO": "S&P 500 (kıyas)"}
DEFANSIF, CIP = ["XLV", "XLF", "XLP"], ["SMH", "XLK"]


def degisim(c, n):
    return pct(c.iloc[-1], c.iloc[-1 - n])


def makro_baski(veri):
    print("\n--- MAKRO BASKI GÖSTERGELERİ ---")
    print(f"{'Gösterge':16}{'Seviye':>9}{'5G %':>8}{'20G %':>8}{'EMA21':>7}{'EMA50':>7}  Not")
    puan, notlar = 0, []
    for t, ad in MAKRO.items():
        kaynak = t
        if t not in veri and t == "DX-Y.NYB" and DXY_YEDEK in veri:
            kaynak, ad = DXY_YEDEK, f"Dolar (yedek {DXY_YEDEK})"
        if kaynak not in veri:
            print(f"{ad:16} VERİ YOK")
            continue
        g = gostergeler(veri[kaynak])
        c, r = g["close"], g.iloc[-1]
        d5, d20 = degisim(c, 5), degisim(c, 20)
        ust21, ust50 = r.close > r.ema21, r.close > r.ema50
        # baski puani: yukselen tahvil/dolar ve yuksek VIX teknolojiye baski
        if t == "^VIX":
            baski = r.close >= 22.5 or ust21
            not_ = vix_rejimi(r.close)
        else:
            baski = ust21 and d20 > 0
            not_ = "yükseliyor, baskı" if baski else "baskı yok"
        puan += baski
        print(f"{ad:16}{r.close:>9.2f}{d5:>+8.1f}{d20:>+8.1f}{'ÜST' if ust21 else 'ALT':>7}"
              f"{'ÜST' if ust50 else 'ALT':>7}  {not_}")
    rejim = ("RİSK-AÇIK" if puan == 0 else "NÖTR" if puan == 1 else "RİSK-KAPALI / TAHVİL-DOLAR BASKISI")
    print(f"Baskı puanı {puan}/3 → Teknoloji rejimi: {rejim}")
    return rejim


def sektor_tablosu(veri):
    print("\n--- SEKTÖR ROTASYONU VE KURUMSAL PARA AKIŞI (20G göreceli güce göre) ---")
    if "VOO" not in veri:
        print("VOO VERİ YOK — göreceli güç hesaplanamadı")
        return {}
    voo20 = degisim(veri["VOO"]["Close"], 20)
    satirlar = {}
    for t in SEKTOR:
        if t not in veri or len(veri[t]) < 70:
            print(f"{t:5} VERİ YOK")
            continue
        g = gostergeler(veri[t])
        s, c = satir(g), g["close"]
        satirlar[t] = {"fiyat": s["fiyat"], "d5": degisim(c, 5), "d20": degisim(c, 20), "d60": degisim(c, 60),
                       "rs": degisim(c, 20) - voo20, "rsi": s["rsi"], "obv_ust": s["obv_ust"],
                       "ema21": s["fiyat"] > s["ema21"]}
    print(f"{'ETF':5}{'Fiyat':>9}{'5G %':>8}{'20G %':>8}{'60G %':>8}{'RS20 %':>8}{'RSI':>7}{'OBV':>12}{'EMA21':>7}  Sektör")
    for t, r in sorted(satirlar.items(), key=lambda x: -x[1]["rs"]):
        obv = "Giriş ↑" if r["obv_ust"] else "Çıkış ↓"
        print(f"{t:5}{r['fiyat']:>9.2f}{r['d5']:>+8.1f}{r['d20']:>+8.1f}{r['d60']:>+8.1f}{r['rs']:>+8.1f}"
              f"{r['rsi']:>7.1f}{obv:>12}{'ÜST' if r['ema21'] else 'ALT':>7}  {SEKTOR[t]}")
    print("RS20 = sektörün 20G getirisi − VOO 20G getirisi. OBV = OBV, kendi SMA21'inin üstünde (giriş) / altında (çıkış).")
    return satirlar


def portfoy_ozeti(s, rejim):
    print("\n--- PORTFÖY BAĞLANTI ÖZETİ ---")
    def grup(etfler, ad):
        v = [s[t] for t in etfler if t in s]
        if not v:
            return None
        rs = sum(x["rs"] for x in v) / len(v)
        giris = sum(x["obv_ust"] for x in v)
        ema = sum(x["ema21"] for x in v)
        print(f"{ad}: ort. RS20 {rs:+.1f}% | OBV girişi {giris}/{len(v)} | EMA21 üstü {ema}/{len(v)} "
              f"({', '.join(f'{t} {s[t]['rs']:+.1f}%' for t in etfler if t in s)})")
        return rs, giris
    d = grup(DEFANSIF, "1. Lig defansif kaleler (LLY, BRK-B, V, SCHD, COST → XLV/XLF/XLP)")
    c = grup(CIP, "2. Lig çip/yazılım (NVDA, AVGO, TSM, ASML, MU, AMD, NOW → SMH/XLK)")
    if d and c:
        fark = d[0] - c[0]
        taraf = "DEFANSİF tarafta" if fark > 1 else ("ÇİP/TEKNOLOJİ tarafta" if fark < -1 else "belirgin bir tarafta değil")
        print(f"Sonuç: Kurumsal para şu an {taraf} (RS farkı {fark:+.1f} puan). Makro rejim: {rejim}.")
    print("Not: Sektör ETF'leri temsilidir; tek hisse kararı için 1. ajan (kar-kalkani-bekcisi) tablosuna bakılır.")


if __name__ == "__main__":
    tickers = list(MAKRO) + [DXY_YEDEK] + list(SEKTOR)
    veri = veri_cek(tickers, period="1y")
    ref = next(iter(veri.values()), None)
    if ref is None:
        sys.exit("VERİ YOK: hiçbir gösterge çekilemedi")
    acik = seans_acik_mi(ref.index[-1].date())
    print("=" * 110)
    print("HEDGE FUND — MAKRO PARA AKIŞI")
    print("⚠ SEANS AÇIK — Rakamlar kesinleşmedi" if acik else f"Seans kapalı. Kesin kapanış: {ref.index[-1].date()}")
    print("=" * 110)
    rejim = makro_baski(veri)
    s = sektor_tablosu(veri)
    portfoy_ozeti(s, rejim)
    if acik:
        print("\n⚠ SEANS AÇIK — yukarıdaki rakamlar kesinleşmedi.")
