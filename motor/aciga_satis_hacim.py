"""HEDGE FUND - Aciga Satis & Hacim Radari (12. ajan).

Kullanim: .venv/bin/python .claude/scripts/aciga_satis_hacim.py [HISSE ...]   (varsayilan: 27 hisse)
20G RVOL (goreli hacim), UDVR (yukari/asagi gun hacim orani), shortPercentOfFloat, shortRatio ve dipte Kurumsal Emilim Mumu.
"""
import sys
import time
from datetime import date
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from kar_kalkani import seans_acik_mi, veri_cek
from ortak_veri import KADRO

EMILIM_HACIM, EMILIM_DIP_PCT, EMILIM_KAPANIS = 1.8, 3.0, 0.6  # hacim >= 1.8x, 20G dibe <=%3, kapanis gun araliginin ust %40'inda


def kisa_bilgi(t):
    for deneme in range(3):
        try:
            i = yf.Ticker(t).get_info()
            return i.get("shortPercentOfFloat"), i.get("shortRatio")
        except Exception:
            time.sleep(2 * (deneme + 1))
    return None, None


def hacim_analizi(d, acik):
    """Son kesin bar uzerinden RVOL/UDVR; emilim mumu son 5 kesin barda aranir."""
    d = d.iloc[:-1] if acik else d
    v, c = d["Volume"], d["Close"]
    ort20 = v.iloc[-21:-1].mean()
    rvol = v.iloc[-1] / ort20 if ort20 else None
    son20 = d.iloc[-20:]
    yon = son20["Close"].diff()
    yukari, asagi = son20["Volume"][yon > 0].sum(), son20["Volume"][yon < 0].sum()
    udvr = yukari / asagi if asagi else None
    dip20 = c.iloc[-20:].min()
    mumlar = []
    for i in range(-5, 0):
        b = d.iloc[i]
        aralik = b["High"] - b["Low"]
        konum = (b["Close"] - b["Low"]) / aralik if aralik else 0
        if (b["Volume"] >= EMILIM_HACIM * ort20 and b["Low"] <= dip20 * (1 + EMILIM_DIP_PCT / 100) and konum >= EMILIM_KAPANIS):
            mumlar.append(d.index[i].date().isoformat())
    return rvol, udvr, mumlar


def main(argv):
    hisseler = [h.upper() for h in argv] or list(KADRO)
    veri = veri_cek(hisseler, period="6mo")
    ornek = next(iter(veri.values()), None)
    acik = seans_acik_mi(ornek.index[-1].date()) if ornek is not None else False
    print("=" * 100)
    print(f"HEDGE FUND — AÇIĞA SATIŞ & HACİM RADARI | {date.today()} | {'SEANS AÇIK: kesin bar = dün' if acik else 'kesin kapanış'}")
    print("=" * 100)
    print(f"{'Hisse':7}{'RVOL20':>8}{'UDVR':>7}{'Short%Float':>13}{'ShortRatio':>12}  Not")
    for t in hisseler:
        if t not in veri or len(veri[t]) < 25:
            print(f"{t:7} VERİ YOK")
            continue
        rvol, udvr, mumlar = hacim_analizi(veri[t], acik)
        spf, sr = kisa_bilgi(t)
        notlar = []
        if rvol and rvol >= 2:
            notlar.append("HACİM PATLAMASI")
        if udvr is not None and udvr >= 1.5:
            notlar.append("alıcı hacmi baskın")
        elif udvr is not None and udvr <= 0.67:
            notlar.append("satıcı hacmi baskın")
        if spf and spf >= 0.10:
            notlar.append(f"yüksek açık pozisyon (%{spf*100:.0f}) → sıkışma potansiyeli")
        if mumlar:
            notlar.append("KURUMSAL EMİLİM MUMU " + ", ".join(mumlar))
        f = lambda x, p=2: "—" if x is None else f"{x:.{p}f}"
        print(f"{t:7}{f(rvol):>8}{f(udvr):>7}{('—' if spf is None else f'%{spf*100:.1f}'):>13}{f(sr,1):>12}  {' | '.join(notlar)}")
    print("\nRVOL20 = son kesin gün hacmi / 20G ortalama · UDVR = 20G yükseliş günü hacmi / düşüş günü hacmi · Emilim mumu = 20G dibinde ≥1.8x hacim ve üst %40'ta kapanış.")
    print("ETF'lerde açığa satış verisi genelde yoktur (—). Bilgi amaçlıdır; alım kararı VIX kilidine tabidir.")


if __name__ == "__main__":
    main(sys.argv[1:])
