"""HEDGE FUND - Derin Istatistik & Gelecek Rotasi veri motoru (PWA hisse cekmecesi icin derin.json).

Kullanim: .venv/bin/python .claude/scripts/derin_guncelle.py [HISSE ...]
Icerik (yalniz fiyat/yuzde, SIFIR lot/maliyet/dolar bakiye): donus puani, RVOL/UDVR, gun ici VWAP/gap/ORB, opsiyon put/call duvari,
MTF harmoni + VPOC/Fib celik destek, Monte Carlo 30G, 12A Wall Street koridoru + tavsiye dagilimi, 24A adil deger rotasi.
Yavas (27 hisse ~5-8 dk); yayinda gunde 2 kez yeterlidir.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from aciga_satis_hacim import hacim_analizi
from coklu_zaman_harmoni import hesapla as harmoni
from haber_istihbarat import analist
from kar_kalkani import gostergeler, satir, seans_acik_mi, veri_cek
from ortak_veri import KADRO
from seans_mikroyapi import analiz as mikro, bes_dk
from temel_degerleme import bilgi, rota

KLASOR = Path(os.environ.get("IZLEME_KLASOR") or (Path(__file__).resolve().parents[1] / "izleme_uygulamasi")).resolve()
YASAK = {"lot", "maliyet", "ana", "deger", "kz", "kz_pct", "bosluk", "doluluk", "kalan_lot", "satilan_lot", "satis_fiyati"}
r2 = lambda x: None if x is None else round(float(x), 2)


def hisse(t, veri5y, acik, H):
    d = veri5y.get(t)
    if d is None or len(d) < 60:
        return {"t": t, "veri_yok": True}
    s = satir(gostergeler(d))
    rvol, udvr, mumlar = hacim_analizi(d, acik)
    bd = bes_dk(t); m = mikro(bd) if bd is not None else None
    i = bilgi(t) or {}
    a = analist(t) or {}
    r = rota(t, i, d["Close"])
    h = H.get(t)
    return {
        "t": t, "fiyat": r2(s["fiyat"]), "puan": int(s["puan"]), "rsi": r2(s["rsi"]), "obv_ust": bool(s["obv_ust"]),
        "rvol": r2(rvol), "udvr": r2(udvr), "emilim": mumlar,
        "vwap": {"deger": r2(m["vwap"]), "uzak": r2(m["vwap_uzak"]), "gap": r2(m["gap"]), "orb": [r2(m["orb_l"]), r2(m["orb_h"])], "gun": str(m["gun"])} if m and m.get("seans_var") else None,
        "opsiyon": {k: r2(v) if isinstance(v, (int, float)) else v for k, v in r["opsiyon"].items()} if r.get("opsiyon") else None,
        "harmoni": {"skor": h["skor"], "puanlar": h["puanlar"], "vpoc": r2(h["vpoc"]), "fib50": r2(h["fib50"]), "fib618": r2(h["fib618"]), "celik": h["celik"]} if h else None,
        "mc30": {"dip": r2(r["mc30"]["dip"]), "medyan": r2(r["mc30"]["medyan"]), "tavan": r2(r["mc30"]["tavan"]), "uyari": r["mc30"]["uyari"]} if r.get("mc30") else None,
        "ws12": {**{k: r2(v) for k, v in r["ws12"].items() if k != "n"}, "n": r["ws12"].get("n"), "tavsiye": a.get("tavsiye"), "dagilim": a.get("dagilim")} if r.get("ws12") else None,
        "adil24": {"yontem": r["adil24"]["yontem"], "muhafazakar": r2(r["adil24"]["muhafazakar"]), "baz": r2(r["adil24"]["baz"]), "boga": r2(r["adil24"]["boga"])} if r.get("adil24") else None,
    }


def main(argv):
    hisseler = [x.upper() for x in argv] or list(KADRO)
    veri5y = veri_cek(hisseler, period="5y")
    ref = next(iter(veri5y.values()), None)
    acik = seans_acik_mi(ref.index[-1].date()) if ref is not None else False
    H = harmoni(hisseler)
    out = {"guncelleme": datetime.now(timezone.utc).isoformat(), "seans_acik": acik, "gizli": True, "hisseler": {}}
    for t in hisseler:
        try:
            out["hisseler"][t] = hisse(t, veri5y, acik, H)
        except Exception as e:
            out["hisseler"][t] = {"t": t, "veri_yok": True, "hata": str(e)[:80]}
        print(f"{t}: {'VERİ YOK ' + out['hisseler'][t].get('hata', '') if out['hisseler'][t].get('veri_yok') else 'ok'}", flush=True)
    metin = json.dumps(out, ensure_ascii=False)
    assert not any(k in YASAK for h in out["hisseler"].values() for k in h), "sızıntı: yasak alan"
    assert "satis_fiyati" not in metin and "kalan_lot" not in metin
    tam = sum(1 for h in out["hisseler"].values() if not h.get("veri_yok"))
    if len(hisseler) == len(KADRO) and tam < len(KADRO) * 0.8:
        sys.exit("derin.json YAZILMADI: hisselerin %20'sinden fazlası VERİ YOK")
    KLASOR.mkdir(exist_ok=True)
    gecici = KLASOR / "derin.json.tmp"; gecici.write_text(metin); json.loads(gecici.read_text()); os.replace(gecici, KLASOR / "derin.json")
    print(f"derin.json yazıldı: {tam}/{len(hisseler)} hisse (GİZLİ: lot/maliyet/dolar yok)")


if __name__ == "__main__":
    main(sys.argv[1:])
