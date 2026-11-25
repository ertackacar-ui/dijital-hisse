"""HEDGE FUND - Seans Ici Mikroyapi & VWAP (16. ajan).

Kullanim: .venv/bin/python .claude/scripts/seans_mikroyapi.py [HISSE ...]   (varsayilan: pusu/kartopu listesi)
5 dakikalik seans ici veriden: gun ici VWAP ve uzaklik, acilis boslugu (Gap %), ilk 30 dk araligi (ORB) kirilimi,
pre/post-market soku ve son 30 dk hacim yogunlugu (MOC baskisi). Seans yoksa son seans analiz edilir.
"""
import sys
import time
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from kar_kalkani import pct

VARSAYILAN = ["QQQ", "VOO", "NVDA", "AMD", "AVGO", "MU", "TSM", "ASML", "AMZN", "GOOG", "PLTR", "NOW"]
NY = ZoneInfo("America/New_York")


def bes_dk(t):
    for deneme in range(3):
        try:
            d = yf.Ticker(t).history(period="5d", interval="5m", prepost=True, auto_adjust=False, timeout=20)
            if len(d):
                return d.tz_convert(NY)
        except Exception:
            time.sleep(2 * (deneme + 1))
    return None


def analiz(d):
    gun = d.index[-1].date()
    g = d[d.index.date == gun]
    seans = g.between_time("09:30", "15:59")
    pre = g.between_time("04:00", "09:29")
    post = g.between_time("16:00", "19:59")
    onceki_gunler = d[d.index.date < gun].between_time("09:30", "15:59")
    if onceki_gunler.empty:
        return None
    onceki_kapanis = float(onceki_gunler["Close"].iloc[-1])
    out = {"gun": gun, "onceki_kapanis": onceki_kapanis, "seans_var": not seans.empty}
    if not pre.empty:
        out["pre"] = pct(float(pre["Close"].iloc[-1]), onceki_kapanis)
    if not seans.empty:
        tp = (seans["High"] + seans["Low"] + seans["Close"]) / 3
        vwap = float((tp * seans["Volume"]).cumsum().iloc[-1] / max(seans["Volume"].sum(), 1))
        son = float(seans["Close"].iloc[-1])
        orb = seans.iloc[:6]
        out.update({"acilis": float(seans["Open"].iloc[0]), "gap": pct(float(seans["Open"].iloc[0]), onceki_kapanis),
                    "vwap": vwap, "son": son, "vwap_uzak": pct(son, vwap),
                    "orb_h": float(orb["High"].max()), "orb_l": float(orb["Low"].min()), "bar": len(seans)})
        if len(seans) >= 72:  # son 30 dk (6 bar) hacmi / gun hacmi
            out["moc"] = float(seans["Volume"].iloc[-6:].sum() / max(seans["Volume"].sum(), 1) * 100)
    if not post.empty and not seans.empty:
        out["post"] = pct(float(post["Close"].iloc[-1]), out["son"])
    return out


def main(argv):
    hisseler = [h.upper() for h in argv] or VARSAYILAN
    print("=" * 100)
    print(f"HEDGE FUND — SEANS İÇİ MİKROYAPI & VWAP | {date.today()} | 5 dk barlar, NY saati")
    print("=" * 100)
    print(f"{'Hisse':7}{'Gün':>11}{'Gap%':>7}{'Son':>9}{'VWAP':>9}{'VWAP±%':>8}{'ORB':>12}{'Pre%':>7}{'Post%':>7}{'MOC%':>6}  Not")
    f = lambda x, p=1: "—" if x is None else f"{x:+.{p}f}" if p else f"{x:.0f}"
    for t in hisseler:
        d = bes_dk(t)
        a = analiz(d) if d is not None else None
        if not a:
            print(f"{t:7} VERİ YOK")
            continue
        if not a["seans_var"]:
            print(f"{t:7}{str(a['gun']):>11}  seans barı yok | pre-market {f(a.get('pre'))}% (önceki kapanış {a['onceki_kapanis']:.2f})")
            continue
        notlar = []
        if a["son"] > a["orb_h"]: notlar.append("ORB YUKARI KIRILIM")
        elif a["son"] < a["orb_l"]: notlar.append("ORB AŞAĞI KIRILIM")
        if abs(a["gap"]) >= 2: notlar.append(f"büyük {'yukarı' if a['gap'] > 0 else 'aşağı'} boşluk")
        if a["vwap_uzak"] >= 1.5: notlar.append("VWAP üstünde güçlü (alıcı kontrolü)")
        elif a["vwap_uzak"] <= -1.5: notlar.append("VWAP altında zayıf (satıcı kontrolü)")
        if a.get("moc") and a["moc"] >= 20: notlar.append("MOC BASKISI: kapanışta yoğun hacim")
        if a["bar"] < 78: notlar.append(f"seans sürüyor ({a['bar']} bar)")
        print(f"{t:7}{str(a['gun']):>11}{f(a['gap']):>7}{a['son']:>9.2f}{a['vwap']:>9.2f}{f(a['vwap_uzak']):>8}"
              f"{a['orb_l']:>6.0f}-{a['orb_h']:<5.0f}{f(a.get('pre')):>7}{f(a.get('post')):>7}{f(a.get('moc'),0):>6}  {' | '.join(notlar)}")
    print("\nVWAP = hacim ağırlıklı ortalama fiyat (kurumsal maliyet çizgisi) · ORB = ilk 30 dk aralığı · MOC% = son 30 dk hacminin gün hacmine payı.")
    print("Pre/Post = seans dışı son fiyatın kapanışa göre değişimi. Bilgi amaçlıdır; saat tahmini yapılmaz, alım kararı VIX kilidine tabidir.")


if __name__ == "__main__":
    main(sys.argv[1:])
