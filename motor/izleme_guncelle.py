"""HEDGE FUND - Canli Izleme veri motoru.

Kullanim:
  .venv/bin/python .claude/scripts/izleme_guncelle.py            # veri.json uret: SIFIR dolar/lot/maliyet (varsayilan, yayina uygun)
  .venv/bin/python .claude/scripts/izleme_guncelle.py --tam      # YALNIZ YEREL: veri_tam.json (lot/K-Z + Midas aynasi); yayinla.sh kopyalamaz
  .venv/bin/python .claude/scripts/izleme_guncelle.py --sunucu   # yerel sunucu (port 8765); veri_tam.json'u 15 dk'da bir arka planda yeniler
Turkce haber ozeti: .claude/izleme_uygulamasi/ozet_tr.json (haber-istihbarat ajani yazar; script oldugu gibi gomer).
"""
import contextlib
import io
import json
import os
import socket
import sys
import time
from datetime import date, datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bilanco_takvimi import ETF, bilanco_tarihleri
from haber_istihbarat import MAKRO_SORGULAR, analist, birlestir, hisse_haberleri, rss, yf_haber
from kar_kalkani import gostergeler, pct, satir, seans_acik_mi, veri_cek, vix_rejimi
from makro_likidite_takvim import FOMC
from makro_para_akisi import CIP, DEFANSIF, DXY_YEDEK, MAKRO as MAKRO_T, SEKTOR, makro_baski, sektor_tablosu
from ortak_veri import ACTIVE_SHIELDS, EMA21_GUARD, KADRO, KARTOPU, LIG_1, LIG_2, PUSU, SHIELD_EXEMPT
from portfoy_haritasi import TAVAN, muhasebe

KLASOR = Path(os.environ.get("IZLEME_KLASOR") or (Path(__file__).resolve().parents[1] / "izleme_uygulamasi")).resolve()
PORT = 8765


def canli_fiyat(t):
    """Seans oncesi/sonrasi dahil son 5 dk bari (prepost=True). Doner: (fiyat, utc zaman) veya (None, None)."""
    import yfinance as yf
    for deneme in range(3):
        try:
            d = yf.Ticker(t).history(period="1d", interval="5m", prepost=True)
            if len(d):
                return float(d["Close"].iloc[-1]), d.index[-1].tz_convert("UTC")
        except Exception:
            pass
        time.sleep(1 + deneme)
    return None, None


def seans_etiketi():
    """NY saatine gore: Seans Oncesi / Seans Ici / Seans Sonrasi / Kapali."""
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo
    ny = _dt.now(ZoneInfo("America/New_York"))
    dk = ny.hour * 60 + ny.minute
    if ny.weekday() >= 5:
        return "Kapalı (hafta sonu)"
    if 240 <= dk < 570:
        return "Seans Öncesi"
    if 570 <= dk < 960:
        return "Seans İçi"
    if 960 <= dk < 1200:
        return "Seans Sonrası"
    return "Kapalı"


def lig(t):
    return 1 if t in LIG_1 else (2 if t in LIG_2 else 3)


def ud(a, b):
    return "ÜST" if a > b else "ALT"


def topla(tam=False):
    sessiz = io.StringIO()
    veri = veri_cek(list(KADRO) + list(MAKRO_T) + [DXY_YEDEK, "^VIX9D", "^VIX3M"] + list(SEKTOR), period="1y")
    ref = next(iter(veri.values()))
    acik = seans_acik_mi(ref.index[-1].date())
    poz = muhasebe(veri)
    vix = veri["^VIX"]["Close"].iloc[-1] if "^VIX" in veri else None

    hisseler, haber_adaylari = [], set()
    for t in KADRO:
        if t not in veri or len(veri[t]) < 60:
            hisseler.append({"t": t, "lig": lig(t), "veri_yok": True})
            continue
        g = gostergeler(veri[t])
        s, c = satir(g), g["close"]
        d1 = pct(c.iloc[-1], c.iloc[-2])
        p = poz.get(t)
        pusu = PUSU.get(t, [])
        en_yakin = min(pusu, key=lambda l: abs(pct(s["fiyat"], l))) if pusu else None
        cf, cz = canli_fiyat(t)
        h = {"t": t, "lig": lig(t), "fiyat": round(s["fiyat"], 2), "d1": round(d1, 2),
             "canli": round(cf, 2) if cf else None, "canli_zaman": cz.isoformat() if cz is not None else None,
             "canli_degisim": round(pct(cf, s["fiyat"]), 2) if cf else None,
             "d5": round(pct(c.iloc[-1], c.iloc[-6]), 2),
             "ema21": ud(s["fiyat"], s["ema21"]), "ema50": ud(s["fiyat"], s["ema50"]), "sma200": ud(s["fiyat"], s["sma200"]),
             "ema21_deger": round(s["ema21"], 2), "rsi": round(s["rsi"], 1), "obv_ust": bool(s["obv_ust"]), "puan": int(s["puan"]),
             "pusu": pusu, "pusu_yakin": en_yakin, "pusu_mesafe": round(pct(s["fiyat"], en_yakin), 2) if en_yakin else None,
             "kartopu": KARTOPU.get(t), "kartopu_mesafe": round(pct(KARTOPU[t], s["fiyat"]), 2) if t in KARTOPU else None,
             "kalkan": t in ACTIVE_SHIELDS, "muaf": t in SHIELD_EXEMPT, "guard": t in EMA21_GUARD}
        if p:
            h.update({"lot": p["lot"], "maliyet": p["maliyet"], "ana": round(p["ana"], 2), "deger": round(p["deger"], 2),
                      "kz": round(p["kz"], 2), "kz_pct": round(p["kz_pct"], 2), "doluluk": round(p["doluluk"], 1), "bosluk": round(p["bosluk"], 2)})
        hisseler.append(h)
        if abs(d1) >= 3 or (en_yakin and abs(h["pusu_mesafe"]) <= 3):
            haber_adaylari.add(t)

    def ozet(ts):
        ana = sum(poz[t]["ana"] for t in ts if t in poz)
        deger = sum(poz[t]["deger"] for t in ts if t in poz)
        return {"ana": round(ana, 2), "deger": round(deger, 2), "kz": round(deger - ana, 2), "kz_pct": round(pct(deger, ana), 2) if ana else 0}
    toplam = {"lig1": ozet(LIG_1), "lig2": ozet(LIG_2), "tum": ozet(KADRO)}

    with contextlib.redirect_stdout(sessiz):
        rejim_para = makro_baski(veri)
        sekt = sektor_tablosu(veri)
    sektorler = [{"etf": t, "ad": SEKTOR[t], "d5": round(r["d5"], 1), "d20": round(r["d20"], 1), "rs": round(r["rs"], 1),
                  "rsi": round(r["rsi"], 1), "obv_ust": bool(r["obv_ust"]), "ema21": bool(r["ema21"])}
                 for t, r in sorted(sekt.items(), key=lambda x: -x[1]["rs"])]
    def ort(ets):
        v = [sekt[t]["rs"] for t in ets if t in sekt]
        return sum(v) / len(v) if v else 0
    fark = ort(DEFANSIF) - ort(CIP)
    taraf = "DEFANSİF" if fark > 1 else ("ÇİP/TEKNOLOJİ" if fark < -1 else "BELİRSİZ")

    bilanco = []
    for t in [t for t in KADRO if t not in ETF]:
        ed, cal = bilanco_tarihleri(t)
        if ed is None:
            bilanco.append({"t": t, "veri_yok": True}); continue
        gelecek = [ts for ts in ed.index if ts.date() >= date.today()]
        if not gelecek:
            continue
        kalan = (min(gelecek).date() - date.today()).days
        bilanco.append({"t": t, "tarih": str(min(gelecek).date()), "kalan": kalan, "mayin": kalan <= 14, "lig": lig(t)})
        if kalan <= 14:
            haber_adaylari.add(t)
    bilanco.sort(key=lambda b: b.get("kalan", 9999))

    makro_h = birlestir([yf_haber("SPY"), yf_haber("QQQ")] +
                        [rss(f"https://news.google.com/rss/search?q={q.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en") for q in MAKRO_SORGULAR], 48)
    def h2j(h):
        return {"z": h["zaman"].isoformat() if h["zaman"] else None, "etiket": h["etiket"], "baslik": h["baslik"], "kaynak": h["kaynak"]}
    haber_hisse = {}
    for t in sorted(haber_adaylari)[:6]:
        a = analist(t) or {}
        hs = hisse_haberleri(t, 48, a.get("ad", ""))
        haber_hisse[t] = {"basliklar": [h2j(h) for h in hs[:5]], "hedef": a.get("hedef"), "tavsiye": a.get("tavsiye"),
                          "potansiyel": round(pct(a["hedef"], a["fiyat"]), 1) if a.get("hedef") and a.get("fiyat") else None}

    ozet_tr = None
    yol = KLASOR / "ozet_tr.json"
    if yol.exists():
        try:
            ozet_tr = json.loads(yol.read_text())
        except Exception:
            ozet_tr = None

    v9 = veri["^VIX9D"]["Close"].iloc[-1] if "^VIX9D" in veri else None
    v3 = veri["^VIX3M"]["Close"].iloc[-1] if "^VIX3M" in veri else None
    if vix is None or v9 is None or v3 is None: egri = "VERİ YOK"
    elif v9 > vix > v3: egri = "TAM BACKWARDATION"
    elif v9 > vix or vix > v3: egri = "KISMİ BACKWARDATION"
    else: egri = "CONTANGO"
    makro_mayin = [{"tarih": d, "ad": "FOMC karar günü", "kalan": (date.fromisoformat(d) - date.today()).days}
                   for d in FOMC if 0 <= (date.fromisoformat(d) - date.today()).days <= 14]
    midas = None
    if tam:
        from midas_ayna import uret
        midas = uret(veri, {h["t"]: (h["canli"], None) for h in hisseler if h.get("canli")})
    return {
        "guncelleme": datetime.now(timezone.utc).isoformat(), "midas": midas,
        "vix_egri": {"vix9d": round(v9, 2) if v9 is not None else None, "vix3m": round(v3, 2) if v3 is not None else None, "yapi": egri},
        "makro_mayin": makro_mayin, "seans_acik": acik, "seans_etiketi": seans_etiketi(), "kesin_kapanis": str(ref.index[-2 if acik else -1].date()),
        "vix": {"deger": round(vix, 2) if vix is not None else None, "metin": vix_rejimi(vix) if vix is not None else "VERİ YOK",
                "rejim": "TAM KİLİT" if vix is None or vix >= 22.5 else ("YALNIZ 1. LİG" if vix >= 20 else "AÇIK")},
        "tnx": round(veri["^TNX"]["Close"].iloc[-1], 2) if "^TNX" in veri else None,
        "dxy": round(veri["DX-Y.NYB"]["Close"].iloc[-1], 2) if "DX-Y.NYB" in veri else None,
        "para_akisi": {"rejim": rejim_para, "taraf": taraf, "fark": round(fark, 1), "sektorler": sektorler},
        "tavan": TAVAN, "hisseler": hisseler, "toplam": toplam, "bilanco": bilanco,
        "haber": {"makro": [h2j(h) for h in makro_h[:10]], "hisse": haber_hisse}, "ozet_tr": ozet_tr,
    }


def gizle(d):
    """Dolar tutarlarini cikarir; fiyat ve yuzdeler kalir (internete yayin icin)."""
    for h in d["hisseler"]:
        for k in ("lot", "maliyet", "ana", "deger", "kz", "kz_pct", "bosluk", "doluluk"):
            h.pop(k, None)
    d["toplam"] = None
    d.pop("midas", None)
    d["gizli"] = True
    return d


def yerel_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close(); return ip
    except Exception:
        return "127.0.0.1"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(KLASOR), **k)
    def end_headers(self):
        self.send_header("Cache-Control", "no-store"); super().end_headers()
    def log_message(self, *a):
        pass


def tam_yaz():
    """YALNIZ YEREL veri_tam.json: lot/K-Z ve Midas aynasi dahil. yayinla.sh bu dosyayi kopyalamaz."""
    d = topla(tam=True)
    gecici = KLASOR / "veri_tam.json.tmp"
    gecici.write_text(json.dumps(d, ensure_ascii=False, indent=1)); json.loads(gecici.read_text()); os.replace(gecici, KLASOR / "veri_tam.json")
    print(f"veri_tam.json yazıldı (YEREL, lot/K-Z + Midas aynası): {len(d['hisseler'])} hisse")


def tam_dongu():
    import threading
    def tur():
        try: tam_yaz()
        except Exception as e: print("veri_tam yenilenemedi:", e)
        threading.Timer(900, tur).start()
    threading.Thread(target=tur, daemon=True).start()


if __name__ == "__main__":
    if "--tam" in sys.argv:
        tam_yaz(); sys.exit()
    if "--sunucu" in sys.argv:
        tam_dongu()
        ip = yerel_ip()
        print(f"HEDGE FUND Canlı İzleme sunucusu çalışıyor (Ctrl+C ile durdur)")
        print(f"  Bu bilgisayar : http://localhost:{PORT}/")
        print(f"  Telefon (aynı Wi-Fi): http://{ip}:{PORT}/")
        ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    else:
        d = gizle(topla())  # yayina giden veri.json her zaman gizli
        KLASOR.mkdir(exist_ok=True)
        # Sema dogrulama: eksik/bozuk veri eski dosyayi ezmesin
        hata = []
        if len(d.get("hisseler") or []) != len(KADRO): hata.append(f"hisse sayısı {len(d.get('hisseler') or [])} != {len(KADRO)}")
        if sum(1 for h in d["hisseler"] if not h.get("veri_yok")) < len(KADRO) * 0.8: hata.append("hisselerin %20'sinden fazlası VERİ YOK")
        if d["vix"].get("deger") is None: hata.append("VIX yok")
        for k in ("guncelleme", "para_akisi", "bilanco", "haber"):
            if d.get(k) is None: hata.append(f"{k} yok")
        if d.get("gizli"):
            yasak = {"lot", "maliyet", "ana", "deger", "kz", "kz_pct", "bosluk", "doluluk"}
            if any(yasak & set(h) for h in d["hisseler"]) or d.get("toplam") is not None or d.get("midas") is not None: hata.append("gizli modda yasak alan var")
        if hata:
            sys.exit("veri.json YAZILMADI (eski dosya korundu): " + "; ".join(hata))
        # Atomik yazim: once gecici dosya, JSON geri okunur, sonra tek adimda yerine konur
        gecici = KLASOR / "veri.json.tmp"
        gecici.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        json.loads(gecici.read_text())
        os.replace(gecici, KLASOR / "veri.json")
        print(f"veri.json yazıldı: {len(d['hisseler'])} hisse, {len(d['bilanco'])} bilanço, {len(d['haber']['hisse'])} hisse haberi"
              f"{' (GİZLİ: dolar tutarları yok)' if d.get('gizli') else ''} | VIX {d['vix']['deger']} {d['vix']['rejim']}")
