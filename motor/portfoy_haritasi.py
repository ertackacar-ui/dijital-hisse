"""HEDGE FUND - Portfoy Yol Haritasi motoru.

Kullanim: .venv/bin/python .claude/scripts/portfoy_haritasi.py
Yalnizca ortak_veri.py'deki lot/maliyet ve kalkan verisini kullanir; nakit bakiyesi bilmez.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kar_kalkani import gostergeler, pct, satir, seans_acik_mi, veri_cek, vix_rejimi
from ortak_veri import ACTIVE_SHIELDS, KADRO, KARTOPU, LIG_1, LIG_2, PUSU

TAVAN = 3100.0  # tekil hisse referans tavani ($)
TAVAN_UYARI = 85  # doluluk % esigi


def fiyat(veri, t):
    return veri[t]["Close"].iloc[-1] if t in veri else None


def muhasebe(veri):
    """Lot ve maliyeti tanimli hisseler icin $ tablo. Doner: {ticker: dict}."""
    poz = {}
    for t, (lot, maliyet) in KADRO.items():
        f = fiyat(veri, t)
        if not lot or not maliyet or f is None:
            continue
        ana, deger = lot * maliyet, lot * f
        poz[t] = {"lot": lot, "maliyet": maliyet, "fiyat": f, "ana": ana, "deger": deger,
                  "kz": deger - ana, "kz_pct": pct(f, maliyet),
                  "doluluk": deger / TAVAN * 100, "bosluk": max(0.0, TAVAN - deger)}
    return poz


def tablo(poz, veri):
    print(f"{'Hisse':7}{'Lot':>8}{'Maliyet':>10}{'Fiyat':>10}{'Ana Para':>11}{'Değer':>11}"
          f"{'Net K/Z $':>11}{'K/Z %':>8}{'Tavan %':>9}{'Boşluk $':>10}  İşaret")
    ozet = {}
    for ad, lig in (("1. Lig", LIG_1), ("2. Lig", LIG_2)):
        ana = deger = 0.0
        for t in lig:
            if t not in poz:
                continue
            p = poz[t]
            ana, deger = ana + p["ana"], deger + p["deger"]
            isaret = "TAVANA YAKIN / ALIM KISITLI" if p["doluluk"] > TAVAN_UYARI else ""
            print(f"{t:7}{p['lot']:>8.4f}{p['maliyet']:>10.2f}{p['fiyat']:>10.2f}{p['ana']:>11.2f}"
                  f"{p['deger']:>11.2f}{p['kz']:>+11.2f}{p['kz_pct']:>+8.1f}{p['doluluk']:>8.1f}%"
                  f"{p['bosluk']:>10.2f}  {isaret}")
        ozet[ad] = (ana, deger)
        print(f"{'— ' + ad + ' toplam':30}{ana:>11.2f}{deger:>11.2f}{deger - ana:>+11.2f}"
              f"{pct(deger, ana) if ana else 0:>+8.1f}")
    ana = sum(a for a, _ in ozet.values())
    deger = sum(d for _, d in ozet.values())
    print(f"{'= TOPLAM HİSSE PORTFÖYÜ':30}{ana:>11.2f}{deger:>11.2f}{deger - ana:>+11.2f}"
          f"{pct(deger, ana) if ana else 0:>+8.1f}")
    izleme = [f"{t} ({fiyat(veri, t):.2f})" if fiyat(veri, t) else f"{t} (VERİ YOK)"
              for t, (lot, m) in KADRO.items() if not lot or not m]
    print("İzleme / Lot Tanımsız:", ", ".join(izleme))
    eksik = [t for t, (lot, m) in KADRO.items() if lot and m and t not in poz]
    if eksik:
        print("VERİ YOK (tabloya giremedi):", ", ".join(eksik))


def kalkan_ozeti(veri):
    print("\n--- KİLİTLENEN KÂR KALKANI ÖZETİ ---")
    for t, sh in ACTIVE_SHIELDS.items():
        pusu = sh.get("geri_alim_pusu") or sh.get("ana_pusu")
        nakit = sh["satilan_lot"] * sh["satis_fiyati"]
        geri_lot = nakit / pusu
        f = fiyat(veri, t)
        mesafe = f"{pct(f, pusu):+.1f}%" if f else "VERİ YOK"
        print(f"{t}: {sh['tarih']} @ ${sh['satis_fiyati']} × {sh['satilan_lot']} lot = ${nakit:,.2f} kilitlendi"
              f" | kalan {sh['kalan_lot']} lot | pusu {pusu} (fiyat mesafesi {mesafe})"
              f" | aynı $ ile geri alım ≈ {geri_lot:.4f} lot (+{geri_lot - sh['satilan_lot']:.4f} lot net artış)")
    print("NOT: Satış kârı, vergi ve FIFO maliyet etkisi hesaplanmadı; mali müşavir kontrolü gerekir.")


def yol_haritasi(veri, poz):
    vix = veri["^VIX"]["Close"].iloc[-1] if "^VIX" in veri else None
    rejim = vix_rejimi(vix) if vix is not None else "VIX: VERİ YOK"
    kilit = "TAM" if vix is None or vix >= 22.5 else ("LIG1" if vix >= 20 else "ACIK")
    print("\n--- STRATEJİK YOL HARİTASI ---")
    print("Rejim:", rejim)

    gos = {t: satir(gostergeler(veri[t])) for t in KADRO if t in veri and len(veri[t]) >= 60}

    print("\nA) Kâr Koruma / Üst Hedef (KARTOPU) sırası — hedefe en yakından:")
    a = sorted(((t, h, pct(h, gos[t]["fiyat"])) for t, h in KARTOPU.items() if t in gos), key=lambda x: x[2])
    for t, h, m in a:
        p = poz.get(t)
        kz = f"K/Z {p['kz_pct']:+.1f}%" if p else "pozisyon yok"
        kalkan = " | KALKAN İCRA EDİLDİ" if t in ACTIVE_SHIELDS else ""
        durum = "HEDEF AŞILDI" if m <= 0 else f"{m:.1f}% kaldı"
        print(f"  {t:6} hedef {h:<7} {durum:14} | {kz} | RSI {gos[t]['rsi']:.1f} | Dönüş {gos[t]['puan']}/4{kalkan}")

    print("\nB) Alt Pusu (PUSU) yakınlık ve hazırlık sırası — en yakın 5 aday:")
    b = []
    for t, seviyeler in PUSU.items():
        if t not in gos:
            continue
        f = gos[t]["fiyat"]
        lvl = min(seviyeler, key=lambda s: abs(pct(f, s)))
        b.append((t, lvl, pct(f, lvl)))
    for t, lvl, m in sorted(b, key=lambda x: abs(x[2]))[:5]:
        g, p = gos[t], poz.get(t)
        bosluk = f"boşluk ${p['bosluk']:,.0f}" if p else f"pozisyon yok, boşluk ${TAVAN:,.0f}"
        if kilit == "TAM":
            izin = "VIX KİLİT → alım yok, hazırlık"
        elif kilit == "LIG1" and t not in LIG_1:
            izin = "VIX → 2. Lig kilitli"
        else:
            izin = "alım penceresi açık"
        if p and p["doluluk"] > TAVAN_UYARI:
            izin += " | TAVANA YAKIN"
        neden = f"pusu {lvl} mesafe {m:+.1f}% | Dönüş {g['puan']}/4 | RSI {g['rsi']:.1f} | OBV {'ÜST' if g['obv_ust'] else 'ALT'}"
        print(f"  {t:6} {neden} | {bosluk} | {izin}")
    print("Not: Dönüş 0/4 = teyit yok, seviye izlenir; 3/4+ = teyit güçleniyor. Nakit bakiyesi bilinmiyor, alım tutarı yazılmaz.")


if __name__ == "__main__":
    veri = veri_cek()
    ref = next(iter(veri.values()))
    acik = seans_acik_mi(ref.index[-1].date())
    print("=" * 110)
    print("HEDGE FUND — PORTFÖY YOL HARİTASI ($ bazlı)")
    print("⚠ SEANS AÇIK — Rakamlar kesinleşmedi" if acik else f"Seans kapalı. Kesin kapanış: {ref.index[-1].date()}")
    print(f"Tekil hisse referans tavanı: ${TAVAN:,.0f} | Uyarı eşiği: %{TAVAN_UYARI} doluluk")
    print("=" * 110)
    poz = muhasebe(veri)
    tablo(poz, veri)
    kalkan_ozeti(veri)
    yol_haritasi(veri, poz)
