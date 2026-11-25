"""HEDGE FUND - Opsiyon Duvar Analisti (11. ajan).

Kullanim: .venv/bin/python .claude/scripts/opsiyon_duvari.py [HISSE ...]   (varsayilan: pusu/kartopu listesindeki hisseler)
Yakin vadeli (>=5 gun) zincirde Put/Call OI duvarlari, Max Pain, Put/Call orani, ATM beklenen hareket ve pusu/kartopu ortusmesi.
Ucretsiz yfinance zinciri; ETF'ler dahil. Veri gelmezse VERI YOK.
"""
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from kar_kalkani import pct
from ortak_veri import KARTOPU, PUSU

VARSAYILAN = ["QQQ", "VOO", "NVDA", "AMD", "AVGO", "MU", "TSM", "ASML", "AMZN", "GOOG", "PLTR", "NOW"]
ORTUSME_PCT = 2.0


def zincir(t):
    """En yakin >=5 gunluk vade; 3 deneme. Doner (vade, calls, puts, spot) veya None."""
    for deneme in range(3):
        try:
            tk = yf.Ticker(t)
            vadeler = [v for v in tk.options if (date.fromisoformat(v) - date.today()).days >= 5]
            if not vadeler:
                return None
            oc = tk.option_chain(vadeler[0])
            spot = tk.fast_info.get("lastPrice") or tk.history(period="1d")["Close"].iloc[-1]
            return vadeler[0], oc.calls, oc.puts, float(spot)
        except Exception:
            time.sleep(2 * (deneme + 1))
    return None


def max_pain(calls, puts):
    strikes = sorted(set(calls.strike) | set(puts.strike))
    def odeme(s):
        c = ((s - calls.strike).clip(lower=0) * calls.openInterest.fillna(0)).sum()
        p = ((puts.strike - s).clip(lower=0) * puts.openInterest.fillna(0)).sum()
        return c + p
    return min(strikes, key=odeme)


def analiz(t):
    z = zincir(t)
    if not z:
        return None
    vade, calls, puts, spot = z
    calls, puts = calls.fillna({"openInterest": 0}), puts.fillna({"openInterest": 0})
    call_duvar = float(calls.loc[calls.openInterest.idxmax(), "strike"])
    put_duvar = float(puts.loc[puts.openInterest.idxmax(), "strike"])
    pc_oran = puts.openInterest.sum() / max(calls.openInterest.sum(), 1)
    atm_c = calls.iloc[(calls.strike - spot).abs().argsort()[:1]]
    atm_p = puts.iloc[(puts.strike - spot).abs().argsort()[:1]]
    orta = lambda r: ((r.bid + r.ask) / 2 if r.bid > 0 and r.ask > 0 else r.lastPrice)
    straddle = float(orta(atm_c.iloc[0]) + orta(atm_p.iloc[0]))
    return {"vade": vade, "spot": spot, "call_duvar": call_duvar, "put_duvar": put_duvar,
            "pc": pc_oran, "max_pain": max_pain(calls, puts), "hareket": straddle / spot * 100,
            "call_oi": int(calls.openInterest.sum()), "put_oi": int(puts.openInterest.sum())}


def ortusme(t, a):
    notlar = []
    for lvl in PUSU.get(t, []):
        if abs(pct(a["put_duvar"], lvl)) <= ORTUSME_PCT:
            notlar.append(f"PUSU {lvl} = PUT DUVARI {a['put_duvar']:g} (destek örtüşmesi)")
    if t in KARTOPU and abs(pct(a["call_duvar"], KARTOPU[t])) <= ORTUSME_PCT:
        notlar.append(f"KARTOPU {KARTOPU[t]} = CALL DUVARI {a['call_duvar']:g} (direnç örtüşmesi)")
    if a["pc"] >= 1.3:
        notlar.append("P/C yüksek: korunma yoğun (kontrarian destek)")
    elif a["pc"] <= 0.6:
        notlar.append("P/C düşük: iyimserlik aşırı")
    return notlar


def main(argv):
    hisseler = [h.upper() for h in argv] or VARSAYILAN
    print("=" * 100)
    print(f"HEDGE FUND — OPSİYON DUVAR ANALİSTİ | {date.today()} | en yakın ≥5 günlük vade")
    print("=" * 100)
    print(f"{'Hisse':7}{'Spot':>9}{'Vade':>12}{'Put Duvar':>11}{'Call Duvar':>11}{'Max Pain':>10}{'P/C OI':>8}{'ATM ±%':>8}  Not")
    for t in hisseler:
        a = analiz(t)
        if not a:
            print(f"{t:7} VERİ YOK (opsiyon zinciri alınamadı)")
            continue
        print(f"{t:7}{a['spot']:>9.2f}{a['vade']:>12}{a['put_duvar']:>11g}{a['call_duvar']:>11g}{a['max_pain']:>10g}"
              f"{a['pc']:>8.2f}{a['hareket']:>8.1f}  {' | '.join(ortusme(t, a))}")
    print("\nPut Duvarı = en yüksek put OI (destek), Call Duvarı = en yüksek call OI (direnç), Max Pain = opsiyon yazıcılarının en az ödeyeceği fiyat.")
    print("ATM ±% = yakın vade straddle fiyatının spota oranı (piyasanın beklediği hareket). Bilgi amaçlıdır; alım kararı VIX kilidine tabidir.")


if __name__ == "__main__":
    main(sys.argv[1:])
