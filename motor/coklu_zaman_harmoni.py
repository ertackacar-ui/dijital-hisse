"""HEDGE FUND - Coklu Zaman Harmoni (19. ajan).

Kullanim: .venv/bin/python .claude/scripts/coklu_zaman_harmoni.py [HISSE ...]   (varsayilan: 27 hisse)
4 zaman diliminde (15m, 1h, 1d, 1wk) EMA21 ustu + RSI(14)>50 uyumundan 0/4-4/4 MTF Harmoni Skoru;
1Y gunluk hacim profilinden VPOC (en yogun hacimli fiyat), 52H zirve-dip Fibonacci %50 / %61.8 seviyeleri
ve PUSU seviyeleriyle ±%2 kesisenler = CELIK DESTEK KESISIMI.
"""
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from kar_kalkani import gostergeler, pct, veri_cek
from ortak_veri import KADRO, PUSU

DILIMLER = [("15m", "10d"), ("1h", "3mo"), ("1d", "1y"), ("1wk", "5y")]
KESISIM_PCT = 2.0


def toplu(hisseler, interval, period):
    """Tek istekle cok hisse; eksik kalanlar tek tek 2 deneme."""
    out = {}
    try:
        d = yf.download(hisseler, period=period, interval=interval, group_by="ticker", auto_adjust=False, progress=False, threads=True, timeout=20)
        for t in hisseler:
            try:
                x = (d[t] if len(hisseler) > 1 else d).dropna(subset=["Close"])
                if len(x) > 30: out[t] = x
            except Exception:
                pass
    except Exception:
        pass
    for t in [t for t in hisseler if t not in out]:
        for deneme in range(2):
            try:
                x = yf.Ticker(t).history(period=period, interval=interval, auto_adjust=False, timeout=20).dropna(subset=["Close"])
                if len(x) > 30: out[t] = x; break
            except Exception:
                time.sleep(2)
    return out


def yon(d):
    g = gostergeler(d).iloc[-1]
    return int(g.close > g.ema21 and g.rsi > 50)


def vpoc(d, bins=50):
    tp = (d["High"] + d["Low"] + d["Close"]) / 3
    hist, kenar = np.histogram(tp, bins=bins, weights=d["Volume"])
    i = int(hist.argmax())
    return float((kenar[i] + kenar[i + 1]) / 2)


def hesapla(hisseler):
    """Doner: {hisse: dict(puanlar, skor, fiyat, vpoc, fib50, fib618, celik[list], notlar[list])}; veri yoksa hisse anahtari yok."""
    seriler = {iv: toplu(hisseler, iv, per) for iv, per in DILIMLER}
    gunluk, out = seriler["1d"], {}
    for t in hisseler:
        if t not in gunluk or len(gunluk[t]) < 60:
            continue
        puanlar = [yon(seriler[iv][t]) if t in seriler[iv] else None for iv, _ in DILIMLER]
        skor = sum(p for p in puanlar if p is not None)
        d = gunluk[t]; fiyat = float(d["Close"].iloc[-1])
        son52 = d.iloc[-252:]; zirve, dip = float(son52["High"].max()), float(son52["Low"].min())
        fib50, fib618 = zirve - .5 * (zirve - dip), zirve - .618 * (zirve - dip)
        vp = vpoc(d)
        celik, notlar = [], []
        for lvl in PUSU.get(t, []):
            kesisen = [ad for ad, sv in (("VPOC", vp), ("Fib50", fib50), ("Fib61.8", fib618)) if abs(pct(sv, lvl)) <= KESISIM_PCT]
            if kesisen:
                celik.append(f"pusu {lvl} ≈ {'+'.join(kesisen)}"); notlar.append(f"ÇELİK DESTEK: pusu {lvl} ≈ {'+'.join(kesisen)}")
        if skor == 4: notlar.append("tam uyum yukarı")
        elif skor == 0: notlar.append("tam uyum aşağı")
        if abs(pct(fiyat, vp)) <= 1: notlar.append("fiyat VPOC üzerinde (hacim mıknatısı)")
        out[t] = {"puanlar": puanlar, "skor": skor, "fiyat": fiyat, "vpoc": vp, "fib50": fib50, "fib618": fib618, "celik": celik, "notlar": notlar}
    return out


def main(argv):
    hisseler = [h.upper() for h in argv] or list(KADRO)
    H = hesapla(hisseler)
    print("=" * 100)
    print(f"HEDGE FUND — ÇOKLU ZAMAN HARMONİ | {date.today()} | 15m · 1h · 1d · 1wk")
    print("=" * 100)
    print(f"{'Hisse':7}{'15m':>4}{'1h':>4}{'1d':>4}{'1wk':>5}{'MTF':>5}{'Fiyat':>9}{'VPOC':>9}{'Fib50':>9}{'Fib61.8':>9}  Çelik Destek / Not")
    s = lambda p: "—" if p is None else ("↑" if p else "↓")
    for t in hisseler:
        if t not in H:
            print(f"{t:7} VERİ YOK"); continue
        h = H[t]; p = h["puanlar"]
        print(f"{t:7}{s(p[0]):>4}{s(p[1]):>4}{s(p[2]):>4}{s(p[3]):>5}{h['skor']:>4}/4{h['fiyat']:>9.2f}{h['vpoc']:>9.2f}{h['fib50']:>9.2f}{h['fib618']:>9.2f}  {' | '.join(h['notlar'])}")
    print("\n↑ = o dilimde fiyat EMA21 üstünde ve RSI>50. VPOC = 1Y en yoğun hacimli fiyat düğümü. Fib = 52H zirveden geri çekilme seviyeleri.")
    print("Çelik Destek = pusu seviyesinin VPOC/Fib ile ±%2 kesişmesi. Bilgi amaçlıdır; alım kararı VIX kilidine tabidir.")


if __name__ == "__main__":
    main(sys.argv[1:])
