"""HEDGE FUND - Kar Kalkani Bekcisi motoru.

Kullanim:
  .venv/bin/python .claude/scripts/kar_kalkani.py            # tam gosterge raporu
  .venv/bin/python .claude/scripts/kar_kalkani.py --kapanis  # kesinlesmis 1G kapanis tablosu
"""
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from ortak_veri import (ACTIVE_SHIELDS, EMA21_GUARD, KADRO, KARTOPU, MAKRO,
                        PUSU, SHIELD_EXEMPT)

KRITIK_PUSU = ["QQQ", "VOO", "MU", "TSM", "ASML", "NOW", "AVGO", "AMZN", "PLTR"]


def seans_acik_mi(son_bar_tarihi):
    ny = datetime.now(ZoneInfo("America/New_York"))
    hafta_ici = ny.weekday() < 5
    saat = ny.hour * 60 + ny.minute
    return hafta_ici and 570 <= saat < 960 and son_bar_tarihi == ny.date()


def veri_cek(tickers=None, period="1y"):
    # shortcut: toplu yf.download oran siniriyla rastgele hisse dusuruyor; tek tek + 5 deneme
    out = {}
    for t in tickers or list(KADRO) + MAKRO:
        for deneme in range(5):
            try:
                d = yf.Ticker(t).history(period=period, interval="1d", auto_adjust=False)
                if len(d):
                    out[t] = d.dropna(subset=["Close"])
                    break
            except Exception:
                pass
            time.sleep(2 * (deneme + 1))
    return out


def gostergeler(d):
    """Tum seriyi hesaplar; son satir = canli, bir onceki = kesin (seans aciksa)."""
    c, v = d["Close"], d["Volume"]
    out = pd.DataFrame({"close": c})
    out["ema21"] = c.ewm(span=21, adjust=False).mean()
    out["ema50"] = c.ewm(span=50, adjust=False).mean()
    out["sma200"] = c.rolling(200).mean()
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    out["rsi"] = 100 - 100 / (1 + gain / loss)
    obv = (v * delta.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))).cumsum()
    out["obv"] = obv
    out["obv_sma21"] = obv.rolling(21).mean()
    return out


def satir(g, i=-1):
    """Verilen bar icin okunur gostergeler ve donus puani."""
    r, onceki, bes = g.iloc[i], g.iloc[i - 1], g.iloc[i - 5]
    ema21_up = r.ema21 > onceki.ema21
    rsi_up = r.rsi > onceki.rsi
    obv_ust = r.obv > r.obv_sma21
    puan = sum([r.close > r.ema21, ema21_up, obv_ust, r.rsi > 50 and rsi_up])
    return {
        "fiyat": r.close, "ema21": r.ema21, "ema50": r.ema50, "sma200": r.sma200,
        "rsi": r.rsi, "rsi_up": rsi_up, "obv_ust": obv_ust,
        "obv5": "↑" if r.obv > bes.obv else "↓", "puan": puan,
        "ema21_up": ema21_up,
    }


def pct(a, b):
    return (a / b - 1) * 100


def kz(t, fiyat):
    lot, maliyet = KADRO[t]
    return pct(fiyat, maliyet) if lot and maliyet else None


def vix_rejimi(vix):
    if vix >= 22.5:
        return f"VIX {vix:.2f} → TAM KİLİT (alım yok)"
    if vix >= 20:
        return f"VIX {vix:.2f} → YALNIZ 1. LİG alımı"
    return f"VIX {vix:.2f} → AÇIK"


def baslik(veri):
    ref = next(veri[t] for t in list(KADRO) + MAKRO if t in veri)
    son_tarih = ref.index[-1].date()
    acik = seans_acik_mi(son_tarih)
    print("=" * 100)
    print("HEDGE FUND — KÂR KALKANI BEKÇİSİ")
    if acik:
        print("⚠ SEANS AÇIK — Rakamlar kesinleşmedi (son bar canlı). Kesin kapanış: "
              f"{ref.index[-2].date()}")
    else:
        print(f"Seans kapalı. Kesin 1G kapanış: {son_tarih}")
    if "^VIX" in veri:
        vix = veri["^VIX"]["Close"]
        print(vix_rejimi(vix.iloc[-1]) + f" | Kesin VIX: {vix.iloc[-2 if acik else -1]:.2f}")
    else:
        print("VIX: VERİ YOK — alım rejimi belirlenemedi")
    son = lambda t: f"{veri[t]['Close'].iloc[-1]:.2f}" if t in veri else "VERİ YOK"
    print(f"10Y: {son('^TNX')}% | DXY: {son('DX-Y.NYB')}")
    print("=" * 100)
    return acik


def ud(f, ref):
    return "ÜST" if f > ref else "ALT"


def tam_rapor(veri):
    acik = baslik(veri)
    hesap = {}
    adaylar, uyarilar, pusu_yakin, kartopu_yakin = [], [], [], []
    print(f"{'Hisse':7}{'Fiyat':>9}{'K/Z%':>8}{'EMA21':>6}{'EMA50':>6}{'SMA200':>7}"
          f"{'RSI':>7}{'OBV/S21':>10}{'Dönüş':>7}  Not")
    for t in KADRO:
        if t not in veri or len(veri[t]) < 60:
            print(f"{t:7} VERİ YOK")
            continue
        g = gostergeler(veri[t])
        s = satir(g)
        kesin = satir(g, -2) if acik else s
        hesap[t] = (s, kesin)
        k = kz(t, s["fiyat"])
        obv_txt = ("ÜST ↑" if s["obv_ust"] else "ALT ↓") + f"({s['obv5']})"
        not_ = []
        if t in ACTIVE_SHIELDS:
            sh = ACTIVE_SHIELDS[t]
            pusu = sh.get("geri_alim_pusu") or sh.get("ana_pusu")
            not_.append(f"KALKAN İCRA EDİLDİ (sat {sh['satis_fiyati']}) → pusu {pusu}: "
                        f"{pct(s['fiyat'], pusu):+.1f}%")
        elif t in SHIELD_EXEMPT:
            not_.append("Kale Muafiyeti")
        else:
            if t in EMA21_GUARD:
                if kesin["fiyat"] < kesin["ema21"]:
                    uyarilar.append(f"🔴 KIRMIZI UYARI {t}: kesin kapanış {kesin['fiyat']:.2f} < EMA21 "
                                    f"{kesin['ema21']:.2f}")
                    not_.append("🔴 EMA21 ALTI")
                not_.append(f"EMA21 kırılım eşiği (bugün): {s['ema21']:.2f}")
            if k is not None and k > 3 and s["fiyat"] < s["ema21"] and not s["obv_ust"]:
                adaylar.append(t)
                not_.append("⚠ ÜSTTEN KÂR KALKANI ADAYI")
        for lvl in PUSU.get(t, []):
            if pct(s["fiyat"], lvl) <= 3:
                pusu_yakin.append((t, lvl, pct(s["fiyat"], lvl), s))
        if t in KARTOPU:
            kartopu_yakin.append((t, KARTOPU[t], pct(KARTOPU[t], s["fiyat"]), s))
        k_txt = f"{k:+.1f}" if k is not None else "-"
        print(f"{t:7}{s['fiyat']:>9.2f}{k_txt:>8}{ud(s['fiyat'], s['ema21']):>6}"
              f"{ud(s['fiyat'], s['ema50']):>6}{ud(s['fiyat'], s['sma200']):>7}"
              f"{s['rsi']:>7.1f}{obv_txt:>10}{s['puan']:>5}/4  {' | '.join(not_)}")

    print("\n--- UYARILAR ---")
    for u in uyarilar:
        print(u)
    if not uyarilar:
        print("EMA21 Guard (LLY, V): kesin kapanış EMA21 üstünde.")
    print("Üstten kâr kalkanı adayları:", ", ".join(adaylar) or "yok")

    print("\n--- PUSU (alt seviyeye %3'ten yakın veya altında) ---")
    for t, lvl, m, s in sorted(pusu_yakin, key=lambda x: x[2]):
        print(f"{t:7} fiyat {s['fiyat']:.2f} | pusu {lvl} | mesafe {m:+.1f}% | "
              f"RSI {s['rsi']:.1f} | OBV {'ÜST' if s['obv_ust'] else 'ALT'} | Dönüş {s['puan']}/4")
    if not pusu_yakin:
        print("yok")

    print("\n--- KARTOPU (üst satış hedefine mesafe, en yakından) ---")
    for t, hedef, m, s in sorted(kartopu_yakin, key=lambda x: x[2]):
        durum = "HEDEF AŞILDI" if m <= 0 else f"{m:.1f}% kaldı"
        print(f"{t:7} fiyat {s['fiyat']:.2f} | hedef {hedef} | {durum} | "
              f"RSI {s['rsi']:.1f} | OBV {'ÜST' if s['obv_ust'] else 'ALT'}")
    if acik:
        print("\n⚠ SEANS AÇIK — yukarıdaki rakamlar kesinleşmedi.")


def kapanis_raporu(veri):
    acik = baslik(veri)
    print(f"{'Hisse':7}{'Kesin Kap.':>11}{'Seans İçi':>11}{'Pusu eşikleri':>16}{'Durum':>10}"
          f"{'RSI':>7}{'OBV/S21':>9}{'Dönüş':>7}  Not")
    for t in KADRO:
        if t not in veri or len(veri[t]) < 60:
            print(f"{t:7} VERİ YOK")
            continue
        g = gostergeler(veri[t])
        canli = satir(g)
        kesin = satir(g, -2) if acik else canli
        seans = f"{canli['fiyat']:.2f}" if acik else "-"
        esikler = "/".join(str(x) for x in PUSU.get(t, [])) or "-"
        durum = "-"
        if t in PUSU:
            en_ust = max(PUSU[t])
            durum = "KIRILDI" if kesin["fiyat"] < min(PUSU[t]) else (
                "EŞİK ALTI" if kesin["fiyat"] < en_ust else f"{pct(kesin['fiyat'], en_ust):+.1f}%")
        not_ = "KRİTİK" if t in KRITIK_PUSU else ""
        if t in EMA21_GUARD:
            not_ = ("🔴 EMA21 ALTI " if kesin["fiyat"] < kesin["ema21"] else "EMA21 üstü ") + \
                   f"(EMA21 {kesin['ema21']:.2f})"
        print(f"{t:7}{kesin['fiyat']:>11.2f}{seans:>11}{esikler:>16}{durum:>10}"
              f"{kesin['rsi']:>7.1f}{('ÜST' if kesin['obv_ust'] else 'ALT'):>9}{kesin['puan']:>5}/4  {not_}")
    print("\nDurum sütunu: en üst pusuya mesafe; EŞİK ALTI = üst pusu altında; KIRILDI = en alt pusu altında.")


if __name__ == "__main__":
    veri = veri_cek()
    eksik = [t for t in list(KADRO) + MAKRO if t not in veri]
    if eksik:
        print("VERİ YOK:", ", ".join(eksik))
    if "--kapanis" in sys.argv:
        kapanis_raporu(veri)
    else:
        tam_rapor(veri)
