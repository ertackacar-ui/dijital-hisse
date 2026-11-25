"""HEDGE FUND - Bilanco Istihbarat motoru.

Kullanim: .venv/bin/python .claude/scripts/bilanco_takvimi.py [--gun 45] [HISSE ...]
Yaklasan bilanco takvimi + son 8 bilancoda ertesi gun sok analizi. ETF'ler ayrilir.
"""
import sys
import time
from datetime import date

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from kar_kalkani import pct, veri_cek
from ortak_veri import KADRO, LIG_1, LIG_2

ETF = ["VOO", "SCHD", "QQQ"]
YAKIN_GUN, SON_N = 14, 8


def lig(t):
    return "1. Lig" if t in LIG_1 else ("2. Lig" if t in LIG_2 else "3. Lig")


def bilanco_tarihleri(t):
    """Doner: (earnings_dates DataFrame, calendar 'Earnings Date' listesi). Oran sinirina karsi 3 deneme."""
    for deneme in range(3):
        try:
            tk = yf.Ticker(t)
            ed = tk.get_earnings_dates(limit=16)
            cal = (tk.calendar or {}).get("Earnings Date", [])
            if ed is not None and len(ed):
                return ed, cal
        except Exception:
            pass
        time.sleep(2 * (deneme + 1))
    return None, []


def durum(cal, tarih):
    # Yahoo takvim tarihi UTC'ye kayabilir (16:00 NY = ertesi gun UTC); 1 gun fark eslesme sayilir
    if len(cal) == 1:
        return "Tek tarih (onaylı görünüm)" if abs((cal[0] - tarih).days) <= 1 else f"Takvim {cal[0]} ile uyuşmuyor"
    if len(cal) >= 2:
        return f"TAHMİN aralık {cal[0]}–{cal[-1]}"
    return "TAHMİN (takvim yok)"


def sok_analizi(t, ed, fiyat):
    """Son SON_N gerceklesmis bilancoda ertesi gun kapanis-kapanis hareket ve 5G on egilim."""
    gecmis = ed[ed["Reported EPS"].notna()]
    gecmis = gecmis[gecmis.index.date <= date.today()].sort_index(ascending=False).head(SON_N)
    c = fiyat["Close"]
    gunler = c.index.date
    hareket, egilim = [], []
    for ts in gecmis.index:
        amc = ts.hour >= 16
        gun = ts.date()
        idx = [i for i, g in enumerate(gunler) if g >= gun]
        if not idx:
            continue
        i = idx[0]
        oncesi, sonrasi = (i, i + 1) if amc and gunler[i] == gun else (i - 1, i)
        if sonrasi >= len(c) or oncesi < 5:
            continue
        hareket.append(pct(c.iloc[sonrasi], c.iloc[oncesi]))
        egilim.append(pct(c.iloc[oncesi], c.iloc[oncesi - 5]))
    if not hareket:
        return None
    s = pd.Series(hareket)
    ort = s.abs().mean()
    risk = "🔴 YÜKSEK" if ort >= 10 else ("🟡 ORTA" if ort >= 5 else "🟢 DÜŞÜK")
    return {"n": len(s), "ort": ort, "maks": s.abs().max(), "maks_isaret": s[s.abs().idxmax()],
            "yukari": int((s > 0).sum()), "asagi": int((s < 0).sum()),
            "on_egilim": sum(egilim) / len(egilim), "risk": risk}


def main(argv):
    gun = int(argv[argv.index("--gun") + 1]) if "--gun" in argv else 45
    ozel = [a.upper() for a in argv if a.isalpha() and a.upper() in KADRO]
    sirketler = [t for t in KADRO if t not in ETF]
    bugun = date.today()
    print("=" * 100)
    print(f"HEDGE FUND — BİLANÇO İSTİHBARAT | pencere {gun} gün | bugün {bugun}")
    print("ETF — Bilanço Yok:", ", ".join(ETF))
    print("=" * 100)

    ed_map, yaklasan, veri_yok = {}, [], []
    for t in sirketler:
        ed, cal = bilanco_tarihleri(t)
        if ed is None:
            veri_yok.append(t)
            continue
        ed_map[t] = ed
        gelecek = [ts for ts in ed.index if ts.date() >= bugun]
        if not gelecek:
            continue
        ts = min(gelecek)
        kalan = (ts.date() - bugun).days
        if kalan <= gun:
            yaklasan.append((ts.date(), t, kalan, durum(cal, ts.date())))

    print(f"\n--- YAKLAŞAN BİLANÇOLAR ({gun} gün) ---")
    print(f"{'Tarih':12}{'Hisse':7}{'Lig':8}{'Kalan':>6}  Onay/Tahmin")
    for tarih, t, kalan, d in sorted(yaklasan):
        uyari = "  🔴 YAKIN MAYIN" if kalan <= YAKIN_GUN else ""
        print(f"{str(tarih):12}{t:7}{lig(t):8}{kalan:>6}  {d}{uyari}")
    if not yaklasan:
        print("Pencerede bilanço yok.")
    if veri_yok:
        print("VERİ YOK (bilanço tarihi çekilemedi):", ", ".join(veri_yok))

    hedef = sorted(set([t for _, t, _, _ in yaklasan] + [t for t in ozel if t in ed_map]))
    if not hedef:
        return
    print(f"\n--- GEÇMİŞ ŞOK ANALİZİ (son {SON_N} bilanço, ertesi gün kapanış→kapanış) ---")
    fiyatlar = veri_cek(hedef, period="3y")
    print(f"{'Hisse':7}{'N':>3}{'Ort ±%':>8}{'Maks %':>9}{'↑/↓':>6}{'5G ön eğilim':>14}  Risk")
    for t in hedef:
        if t not in fiyatlar:
            print(f"{t:7} VERİ YOK (fiyat)")
            continue
        r = sok_analizi(t, ed_map[t], fiyatlar[t])
        if r is None:
            print(f"{t:7} gerçekleşmiş bilanço verisi yok")
            continue
        not_ = f"  (yalnız {r['n']} bilanço var)" if r["n"] < SON_N else ""
        yon = f"{r['yukari']}/{r['asagi']}"
        print(f"{t:7}{r['n']:>3}{r['ort']:>8.1f}{r['maks_isaret']:>+9.1f}{yon:>6}"
              f"{r['on_egilim']:>+13.1f}%  {r['risk']}{not_}")
    print("Ort ±% = mutlak hareket ortalaması; 5G ön eğilim = bilanço öncesi 5 işlem günü getirisi ortalaması.")
    print("Tarihler Yahoo Finance kaynaklı; şirket onayı yerine takvimin tek tarih/aralık verdiği gösterilir.")


if __name__ == "__main__":
    main(sys.argv[1:])
