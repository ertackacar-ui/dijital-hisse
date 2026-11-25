"""HEDGE FUND - Temel Degerleme & Kalite (13. ajan).

Kullanim: .venv/bin/python .claude/scripts/temel_degerleme.py [HISSE ...]          (varsayilan: 24 sirket, ETF'ler haric)
          .venv/bin/python .claude/scripts/temel_degerleme.py --rota [HISSE ...]   "Bu hisse nereye gidiyor?" 30G / 12A / 24A rota
Fwd P/E, PEG, EV/EBITDA, FCF Yield %, 0-100 Kalite Puani; 3. Lig icin Cash Runway (nakit omru). Kaynak: yfinance info.
Rota: 30G Monte Carlo bandi + opsiyon duvarlari, 12A Wall Street hedef koridoru, 24A adil deger (forwardEps x tavanli buyume x Fwd P/E).
"""
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from bilanco_takvimi import ETF
from ortak_veri import KADRO, LIG_3


def bilgi(t):
    for deneme in range(3):
        try:
            i = yf.Ticker(t).get_info()
            if i.get("marketCap"):
                return i
        except Exception:
            time.sleep(2 * (deneme + 1))
    return None


def kalite(i):
    """0-100: ROE, faaliyet marji, gelir buyumesi, borc/ozkaynak, FCF verimi. Eksik alan 0 puan."""
    p = 0
    roe = i.get("returnOnEquity"); p += 25 if roe and roe >= .20 else 15 if roe and roe >= .10 else 0
    m = i.get("operatingMargins"); p += 25 if m and m >= .30 else 15 if m and m >= .15 else 5 if m and m > 0 else 0
    g = i.get("revenueGrowth"); p += 20 if g and g >= .20 else 12 if g and g >= .08 else 5 if g and g > 0 else 0
    de = i.get("debtToEquity"); p += 15 if de is not None and de <= 50 else 8 if de is not None and de <= 120 else 0
    fcf, mc = i.get("freeCashflow"), i.get("marketCap")
    p += 15 if fcf and mc and fcf / mc >= .03 else 8 if fcf and fcf > 0 else 0
    return p


def runway(i):
    nakit, fcf = i.get("totalCash"), i.get("freeCashflow")
    if nakit is None or fcf is None:
        return "VERİ YOK"
    if fcf >= 0:
        return "nakit üretiyor"
    return f"{nakit / -fcf * 12:.0f} ay ({nakit/1e6:,.0f}M nakit / {-fcf/1e6:,.0f}M yıllık yakım)"


BUYUME_TAVAN, BUYUME_TABAN = 0.25, 0.0  # 24A projeksiyonunda yillik EPS buyumesi bu banda kirpilir
ETF_GETIRI_YIL = 10


def rota(t, i=None, fiyatlar=None):
    """30G / 12A / 24A gelecek fiyat haritasi. Doner dict; hesaplanamayan katman None. Sadece fiyat/yuzde icerir."""
    from monte_carlo import simule
    from opsiyon_duvari import analiz as opsiyon
    from kar_kalkani import veri_cek
    i = i if i is not None else (bilgi(t) or {})
    if fiyatlar is None:
        v = veri_cek([t], period="5y"); fiyatlar = v[t]["Close"] if t in v else None
    out = {"t": t, "fiyat": float(fiyatlar.iloc[-1]) if fiyatlar is not None and len(fiyatlar) else i.get("currentPrice")}
    # 30G taktik bant
    if fiyatlar is not None and len(fiyatlar) > 60:
        yollar, df, uyari = simule(fiyatlar)
        g30 = yollar[:, 29]
        out["mc30"] = {"dip": float(np.percentile(g30, 5)), "medyan": float(np.median(g30)), "tavan": float(np.percentile(g30, 95)), "uyari": uyari}
    o = opsiyon(t)
    out["opsiyon"] = {"put": o["put_duvar"], "call": o["call_duvar"], "max_pain": o["max_pain"], "vade": o["vade"], "hareket": o["hareket"]} if o else None
    # 12A kurumsal rota
    if i.get("targetMeanPrice") and out["fiyat"]:
        out["ws12"] = {"dusuk": i.get("targetLowPrice"), "ortalama": i["targetMeanPrice"], "medyan": i.get("targetMedianPrice"), "yuksek": i.get("targetHighPrice"),
                       "n": i.get("numberOfAnalystOpinions"), "potansiyel": (i["targetMeanPrice"] / out["fiyat"] - 1) * 100}
    else:
        out["ws12"] = None
    # 24A adil deger
    if t in ETF and fiyatlar is not None and len(fiyatlar) > 500:
        yil = min(ETF_GETIRI_YIL, len(fiyatlar) / 252)
        cagr = (float(fiyatlar.iloc[-1]) / float(fiyatlar.iloc[0])) ** (1 / yil) - 1
        out["adil24"] = {"yontem": f"{yil:.0f}Y bileşik getiri %{cagr*100:.1f}/yıl", "muhafazakar": out["fiyat"] * (1 + cagr / 2) ** 2,
                         "baz": out["fiyat"] * (1 + cagr) ** 2, "boga": out["fiyat"] * (1 + cagr * 1.5) ** 2}
    elif i.get("forwardEps") and i.get("forwardEps") > 0 and i.get("forwardPE"):
        adaylar = [x for x in (i.get("earningsGrowth"), i.get("earningsQuarterlyGrowth"), i.get("revenueGrowth")) if x is not None]
        g = min(max(max(adaylar) if adaylar else 0.0, BUYUME_TABAN), BUYUME_TAVAN)
        eps24 = i["forwardEps"] * (1 + g)  # forwardEps 12A ileriyi gosterir; bir yil daha buyutulur
        pe = i["forwardPE"]
        out["adil24"] = {"yontem": f"EPS {i['forwardEps']:.2f}×(1+%{g*100:.0f}) × Fwd P/E {pe:.1f} (0.75× / 1× / 1.25×)",
                         "muhafazakar": eps24 * pe * 0.75, "baz": eps24 * pe, "boga": eps24 * pe * 1.25}
    else:
        out["adil24"] = None
    return out


def rota_yazdir(hisseler):
    print("=" * 110)
    print(f"HEDGE FUND — GELECEK ROTA MOTORU: BU HİSSE NEREYE GİDİYOR? | {date.today()}")
    print("=" * 110)
    print(f"{'Hisse':7}{'Fiyat':>9} | {'30G %5 Dip':>10} {'Medyan':>8} {'%95 Tavan':>9} {'Put/Call Duvar':>15} | {'12A Düşük':>9} {'Ort':>7} {'Yüksek':>7} {'Upside':>8} | {'24A Muhafazakâr':>15} {'Baz':>8} {'Boğa':>8}")
    g = lambda x: "—" if x is None else f"{x:,.0f}"
    for t in hisseler:
        r = rota(t)
        if not r.get("fiyat"):
            print(f"{t:7} VERİ YOK"); continue
        m, o, w, a = r.get("mc30"), r.get("opsiyon"), r.get("ws12"), r.get("adil24")
        print(f"{t:7}{r['fiyat']:>9.2f} | {g(m and m['dip']):>10} {g(m and m['medyan']):>8} {g(m and m['tavan']):>9} {(g(o and o['put'])+'/'+g(o and o['call'])) if o else '—':>15} | "
              f"{g(w and w['dusuk']):>9} {g(w and w['ortalama']):>7} {g(w and w['yuksek']):>7} {(f"{w['potansiyel']:+.0f}%" if w else '—'):>8} | "
              f"{g(a and a['muhafazakar']):>15} {g(a and a['baz']):>8} {g(a and a['boga']):>8}")
        if a: print(f"{'':7}  24A yöntem: {a['yontem']}" + (f" | MC uyarı: {'; '.join(m['uyari'])}" if m and m.get('uyari') else ""))
    print("\n30G = Student-t Monte Carlo 10.000 yol + en yakın vade opsiyon duvarları · 12A = Wall Street hedef koridoru · 24A = adil değer projeksiyonu (ETF: tarihsel bileşik getiri).")
    print("Rota bir tahmin değil, olasılık ve konsensüs haritasıdır; alım kararı VIX kilidine tabidir.")


def main(argv):
    if "--rota" in argv:
        rota_yazdir([h.upper() for h in argv if not h.startswith("--")] or list(KADRO)); return
    hisseler = [h.upper() for h in argv] or [t for t in KADRO if t not in ETF]
    print("=" * 100)
    print(f"HEDGE FUND — TEMEL DEĞERLEME & KALİTE | {date.today()} | kaynak: yfinance info")
    print("=" * 100)
    print(f"{'Hisse':7}{'Fwd P/E':>9}{'PEG':>7}{'EV/EBITDA':>11}{'FCF Verim%':>12}{'Kalite':>8}  Not")
    f = lambda x, p=1: "—" if x is None else f"{x:.{p}f}"
    for t in hisseler:
        if t in ETF:
            print(f"{t:7} ETF — temel değerleme uygulanmaz")
            continue
        i = bilgi(t)
        if not i:
            print(f"{t:7} VERİ YOK")
            continue
        fcf, mc = i.get("freeCashflow"), i.get("marketCap")
        fcfy = fcf / mc * 100 if fcf and mc else None
        peg = i.get("pegRatio") or i.get("trailingPegRatio")
        k = kalite(i)
        notlar = []
        fpe = i.get("forwardPE")
        if fpe and fpe > 45: notlar.append("pahalı çarpan")
        if peg and peg < 1: notlar.append("PEG<1 büyümeye göre ucuz")
        if fcfy is not None and fcfy < 0: notlar.append("negatif FCF")
        if k >= 75: notlar.append("KALİTE YÜKSEK")
        elif k < 40: notlar.append("kalite zayıf")
        if t in LIG_3: notlar.append("Cash Runway: " + runway(i))
        print(f"{t:7}{f(fpe):>9}{f(peg,2):>7}{f(i.get('enterpriseToEbitda')):>11}{f(fcfy):>12}{k:>8}  {' | '.join(notlar)}")
    print("\nKalite Puanı (0-100): ROE 25 + faaliyet marjı 25 + gelir büyümesi 20 + düşük borç 15 + FCF verimi 15. Eksik alan 0 sayılır.")
    print("Cash Runway = nakit / yıllık nakit yakımı (3. Lig). Bilgi amaçlıdır; alım kararı VIX kilidine tabidir.")


if __name__ == "__main__":
    main(sys.argv[1:])
