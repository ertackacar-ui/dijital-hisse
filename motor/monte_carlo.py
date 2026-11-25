"""HEDGE FUND - Monte Carlo Kant motoru.

Kullanim: .venv/bin/python .claude/scripts/monte_carlo.py [HISSE ...]
Son 5Y gunluk log-getiriye Student-t oturtur, 10.000 yol simule eder; fiyat bantlari ve pusu degme olasiliklari.
"""
import sys
from pathlib import Path

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
from kar_kalkani import pct, seans_acik_mi, veri_cek
from ortak_veri import PUSU

VARSAYILAN = "QQQ VOO NVDA GOOG AVGO MU TSM ASML NOW PLTR AMZN".split()
N_YOL, GUNLER, DF_MIN, KISA_GECMIS = 10_000, (30, 60), 2.5, 252
RNG = np.random.default_rng(42)  # tekrarlanabilir sonuc icin sabit tohum


def simule(fiyatlar):
    """Doner: (yollar [N_YOL x 60], df, uyarilar)."""
    r = np.diff(np.log(fiyatlar.values))
    r = r[np.isfinite(r)]
    uyarilar = []
    if len(fiyatlar) < KISA_GECMIS:
        uyarilar.append(f"Kısa Geçmiş Uyarısı ({len(fiyatlar)} bar)")
    df, loc, scale = stats.t.fit(r)
    if df < DF_MIN:
        df, loc, scale = stats.t.fit(r, f0=DF_MIN)
        uyarilar.append(f"df alt sınıra çekildi ({DF_MIN}): düz/SPAC fiyat geçmişi, kuyruk güvenilmez")
    getiri = stats.t.rvs(df, loc=loc, scale=scale, size=(N_YOL, max(GUNLER)), random_state=RNG)
    yollar = fiyatlar.iloc[-1] * np.exp(np.cumsum(getiri, axis=1))
    return yollar, df, uyarilar


def main(hisseler):
    veri = veri_cek(hisseler, period="5y")
    ref = next(iter(veri.values()), None)
    if ref is None:
        sys.exit("VERİ YOK: hiçbir hisse çekilemedi")
    acik = seans_acik_mi(ref.index[-1].date())
    print("=" * 110)
    print(f"HEDGE FUND — MONTE CARLO KANT (Student-t, {N_YOL:,} yol, 5Y günlük log-getiri)")
    print("⚠ SEANS AÇIK — Başlangıç fiyatı canlı, kesinleşmedi" if acik else f"Seans kapalı. Kesin kapanış: {ref.index[-1].date()}")
    print("=" * 110)

    sonuc = {}
    for t in hisseler:
        if t not in veri or len(veri[t]) < 30:
            print(f"{t}: VERİ YOK")
            continue
        sonuc[t] = simule(veri[t]["Close"])

    print(f"\n--- TABLO 1: FİYAT BANTLARI ---")
    print(f"{'Hisse':7}{'Güncel':>9}{'df':>6} | {'30G %5 Dip':>11}{'30G Medyan':>12}{'30G %95':>10} | "
          f"{'60G %5 Dip':>11}{'60G Medyan':>12}{'60G %95':>10}  Not")
    for t, (y, df, uyar) in sonuc.items():
        p0 = veri[t]["Close"].iloc[-1]
        satir = f"{t:7}{p0:>9.2f}{df:>6.1f} |"
        for g in GUNLER:
            q = np.percentile(y[:, g - 1], [5, 50, 95])
            satir += f"{q[0]:>11.2f}{q[1]:>12.2f}{q[2]:>10.2f} |"
        print(satir + "  " + " | ".join(uyar))

    print(f"\n--- TABLO 2: PUSU DEĞME OLASILIĞI ---")
    print(f"{'Hisse':7}{'Pusu':>8}{'Mesafe%':>9} | {'30G Değme%':>11}{'30G Altında%':>13} | {'60G Değme%':>11}{'60G Altında%':>13}")
    var = False
    for t, (y, df, uyar) in sonuc.items():
        p0 = veri[t]["Close"].iloc[-1]
        for lvl in PUSU.get(t, []):
            var = True
            satir = f"{t:7}{lvl:>8}{pct(lvl, p0):>+9.1f} |"
            for g in GUNLER:
                degme = (y[:, :g].min(axis=1) <= lvl).mean() * 100
                altinda = (y[:, g - 1] < lvl).mean() * 100
                satir += f"{degme:>10.1f}%{altinda:>12.1f}% |"
            print(satir)
    if not var:
        print("Seçilen hisselerde PUSU seviyesi tanımlı değil.")
    print("\nDeğme = 60/30 gün içinde en az bir gün kapanışın seviyeye inmesi; Altında = sürenin son günü seviyenin altında bitme.")
    print("Not: Olasılıklar geçmiş dağılımdan türetilen istatistiktir, tahmin değildir; haber ve rejim kırılmalarını içermez.")
    if acik:
        print("⚠ SEANS AÇIK — başlangıç fiyatı kesinleşmedi.")


if __name__ == "__main__":
    main([a.upper() for a in sys.argv[1:]] or VARSAYILAN)
