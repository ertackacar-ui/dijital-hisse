"""HEDGE FUND - Haber Istihbarat motoru (10. ajan).

Kullanim:
  .venv/bin/python .claude/scripts/haber_istihbarat.py                  # makro gundem + hareketli/bilancolu hisseler
  .venv/bin/python .claude/scripts/haber_istihbarat.py --hisse MU AVGO  # secili hisseler derin rontgen
  .venv/bin/python .claude/scripts/haber_istihbarat.py --tum            # 27 hissenin tamami
  --saat 72 : haber penceresi (saat)
Kaynaklar: yfinance Ticker.news + Yahoo Finance RSS + Google News RSS (API anahtari yok). Veri gelmezse "VERİ YOK".
"""
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from kar_kalkani import pct, veri_cek
from ortak_veri import KADRO

OLUMSUZ = ["downgrade", "cut", "cuts", "miss", "misses", "lawsuit", "probe", "investigation", "recall", "ban", "tariff",
           "slump", "plunge", "plunges", "falls", "fall", "drop", "drops", "sell-off", "selloff", "warning", "warns", "weak",
           "layoff", "layoffs", "delay", "halt", "curb", "restriction", "underperform", "fraud", "slides", "sinks", "tumbles",
           "toxic", "bubble", "crash", "loses", "below"]
POZITIF = ["upgrade", "upgrades", "beat", "beats", "raises", "raise", "record", "surge", "surges", "soars", "jumps", "rally",
           "buyback", "dividend", "partnership", "deal", "contract", "wins", "outperform", "strong", "growth", "approval",
           "launch", "expands", "top pick", "bargain", "cheapest", "accelerat"]
MAKRO_SORGULAR = ["Federal Reserve interest rates", "tariffs stock market", "semiconductor stocks", "S&P 500 stock market today",
                  "Treasury yields dollar"]
UA = {"User-Agent": "Mozilla/5.0"}


def etiket(metin):
    m = metin.lower()
    neg, poz = sum(k in m for k in OLUMSUZ), sum(k in m for k in POZITIF)
    if neg > poz:
        return "🔴 OLUMSUZ / RİSK"
    if poz > neg:
        return "🟢 POZİTİF KATALİZÖR"
    return "⚪ BİLGİ/NÖTR"


def _zaman(s):
    try:
        if not s:
            return None
        if s.endswith("Z") or "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
        return parsedate_to_datetime(s).astimezone(timezone.utc)
    except Exception:
        return None


def rss(url):
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15).read()
        out = []
        for it in ET.fromstring(raw).findall(".//item"):
            out.append({"baslik": (it.findtext("title") or "").strip(), "kaynak": (it.findtext("source") or "RSS").strip(),
                        "zaman": _zaman(it.findtext("pubDate")), "ozet": ""})
        return out
    except Exception:
        return []


def yf_haber(t):
    try:
        out = []
        for n in yf.Ticker(t).news or []:
            c = n.get("content", {})
            out.append({"baslik": c.get("title", ""), "kaynak": (c.get("provider") or {}).get("displayName", "Yahoo"),
                        "zaman": _zaman(c.get("pubDate")), "ozet": (c.get("summary") or "")[:160]})
        return out
    except Exception:
        return []


def birlestir(listeler, saat):
    esik = datetime.now(timezone.utc) - timedelta(hours=saat)
    gorulen, out = set(), []
    for h in sum(listeler, []):
        anahtar = h["baslik"].lower()[:60]
        if not h["baslik"] or anahtar in gorulen or (h["zaman"] and h["zaman"] < esik):
            continue
        gorulen.add(anahtar)
        h["etiket"] = etiket(h["baslik"] + " " + h["ozet"])
        out.append(h)
    return sorted(out, key=lambda h: h["zaman"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


def hisse_haberleri(t, saat, ad=""):
    sorgu = urllib.parse.quote(f"{t} stock {ad}".strip())
    return birlestir([yf_haber(t),
                      rss(f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={t}&region=US&lang=en-US"),
                      rss(f"https://news.google.com/rss/search?q={sorgu}&hl=en-US&gl=US&ceid=US:en")], saat)


def analist(t):
    """Doner: dict(hedef, fiyat, potansiyel, n, tavsiye, ozet_sayim, degisimler DataFrame) veya None."""
    for deneme in range(3):
        try:
            tk = yf.Ticker(t)
            inf = tk.info or {}
            ud = tk.upgrades_downgrades
            rs = tk.recommendations_summary
            son30 = None
            if ud is not None and len(ud):
                son30 = ud[ud.index >= pd.Timestamp.now() - pd.Timedelta(days=30)]
            sayim = None
            if rs is not None and len(rs):
                r0 = rs.iloc[0]
                sayim = f"güçlü al {int(r0.strongBuy)} / al {int(r0.buy)} / tut {int(r0.hold)} / sat {int(r0.sell + r0.strongSell)}"
            dagilim = None
            if rs is not None and len(rs):
                r0 = rs.iloc[0]
                dagilim = {"strong_buy": int(r0.strongBuy), "buy": int(r0.buy), "hold": int(r0.hold), "sell": int(r0.sell + r0.strongSell)}
            return {"ad": (inf.get("shortName") or "").split(",")[0].replace("Inc.", "").replace("Corporation", "").strip(),
                    "hedef": inf.get("targetMeanPrice"), "fiyat": inf.get("currentPrice"), "n": inf.get("numberOfAnalystOpinions"),
                    "tavsiye": inf.get("recommendationKey"), "sayim": sayim, "degisimler": son30, "dagilim": dagilim,
                    "dusuk": inf.get("targetLowPrice"), "medyan": inf.get("targetMedianPrice"), "yuksek": inf.get("targetHighPrice")}
        except Exception:
            time.sleep(2 * (deneme + 1))
    return None


def hisse_bolumu(t, saat=72, n=8, girinti="", ad=""):
    """Bir hissenin haber + analist bolumunu basar. alarm_okuyucu.py de bunu kullanir."""
    a = analist(t)  # once analist: sirket adi Google News sorgusunu temizler
    haberler = hisse_haberleri(t, saat, ad or (a or {}).get("ad", ""))
    print(f"{girinti}SON HABERLER ({saat} saat, {len(haberler)} başlık):")
    if not haberler:
        print(f"{girinti}  VERİ YOK (üç kaynaktan da {saat} saat içinde haber gelmedi)")
    for h in haberler[:n]:
        z = h["zaman"].strftime("%d.%m %H:%M") if h["zaman"] else "--.-- --:--"
        print(f"{girinti}  {z} {h['etiket']:20} {h['baslik'][:95]}  [{h['kaynak'][:18]}]")
    print(f"{girinti}ANALİST:")
    if a is None:
        print(f"{girinti}  VERİ YOK")
        return haberler, None
    if a["hedef"] and a["fiyat"]:
        print(f"{girinti}  Ortalama hedef {a['hedef']:.2f} vs fiyat {a['fiyat']:.2f} → potansiyel {pct(a['hedef'], a['fiyat']):+.1f}% "
              f"({a['n']} analist, konsensüs {a['tavsiye']}) | {a['sayim'] or ''}")
        if a.get("dusuk") and a.get("yuksek"):
            print(f"{girinti}  12A hedef koridoru: en düşük {a['dusuk']:.0f} ({pct(a['dusuk'], a['fiyat']):+.0f}%) · medyan {a['medyan'] or a['hedef']:.0f} · "
                  f"ortalama {a['hedef']:.0f} · en yüksek {a['yuksek']:.0f} ({pct(a['yuksek'], a['fiyat']):+.0f}%)")
    else:
        print(f"{girinti}  Hedef fiyat VERİ YOK{(' | ' + a['sayim']) if a['sayim'] else ''}")
    d = a["degisimler"]
    if d is None or not len(d):
        print(f"{girinti}  Son 30 günde not değişimi yok")
    else:
        for ts, r in d.head(6).iterrows():
            aks = str(r.get("Action", "")).lower()
            ok = "🟢" if aks == "up" else ("🔴" if aks == "down" else "⚪")
            hedef = f" hedef {r.get('priorPriceTarget', '')}→{r.get('currentPriceTarget', '')}" if pd.notna(r.get("currentPriceTarget")) else ""
            print(f"{girinti}  {ts.date()} {ok} {r['Firm'][:18]:18} {r['FromGrade']} → {r['ToGrade']} ({r.get('priceTargetAction', '')}{hedef})")
    return haberler, a


MARTINELLI_RSS = "https://www.youtube.com/feeds/videos.xml?channel_id=UCf2Piv-pqwFx2zPUx-HeMcA"  # @PaulMartinelliOfficial resmi kanal
HISSE_ADLARI = {"NVDA": ["nvidia"], "AMD": ["amd"], "AVGO": ["broadcom"], "MU": ["micron"], "TSM": ["tsmc", "taiwan semi"], "ASML": ["asml"],
                "MSFT": ["microsoft"], "AMZN": ["amazon"], "GOOG": ["google", "alphabet"], "PLTR": ["palantir"], "NOW": ["servicenow"],
                "PANW": ["palo alto"], "VRT": ["vertiv"], "PWR": ["quanta"], "ANET": ["arista"], "CRDO": ["credo"], "OKLO": ["oklo"],
                "RGTI": ["rigetti"], "MP": ["mp materials"], "LLY": ["lilly"], "V": ["visa"], "COST": ["costco"], "BRK-B": ["berkshire", "buffett"],
                "VOO": ["s&p", "sp500", "s&p 500"], "QQQ": ["nasdaq", "qqq"], "SCHD": ["schd", "dividend"], "SPCX": ["spac"]}


def martinelli(n=8):
    """Paul Martinelli YouTube Atom akisi (anahtarsiz). Doner: [(tarih, baslik, [eslesen hisseler])] veya None (erisilemedi)."""
    try:
        raw = urllib.request.urlopen(urllib.request.Request(MARTINELLI_RSS, headers=UA), timeout=15).read()
        ns = {"a": "http://www.w3.org/2005/Atom"}
        out = []
        for e in ET.fromstring(raw).findall("a:entry", ns)[:n]:
            baslik = (e.findtext("a:title", default="", namespaces=ns) or "").strip()
            tarih = (e.findtext("a:published", default="", namespaces=ns) or "")[:10]
            kucuk = baslik.lower()
            hisseler = [t for t, adlar in HISSE_ADLARI.items() if any(a in kucuk for a in adlar) or f" {t.lower()} " in f" {kucuk} "]
            out.append((tarih, baslik, hisseler))
        return out
    except Exception:
        return None


def finfluencer_nabzi():
    print("\n--- 📱 FİNFLUENCER NABZI (Paul Martinelli — Bireysel Görüş, kurumsal konsensüs DEĞİLDİR) ---")
    v = martinelli()
    if v is None:
        print("  VERİ YOK (YouTube RSS erişilemedi)"); return
    if not v:
        print("  VERİ YOK (akışta video yok)"); return
    for tarih, baslik, hisseler in v:
        print(f"  {tarih} {baslik[:88]}" + (f"  → kadro: {', '.join(hisseler)}" if hisseler else ""))
    kesisen = sorted({t for _, _, hs in v for t in hs})
    print(f"  Kadroyla kesişen başlıklar: {', '.join(kesisen) or 'yok'} | Bu bölüm bireysel yorumdur; VIX kilidi ve kurumsal konsensüs önceliklidir.")


def konsensus_tablosu(hisseler):
    print("\n--- WALL STREET KURUMSAL KONSENSÜS (12 aylık hedef koridoru) ---")
    print(f"{'Hisse':7}{'N':>4}{'Güçlü Al/Al/Tut/Sat':>21}{'Fiyat':>9}{'En Düşük':>10}{'Medyan':>9}{'Ortalama':>10}{'En Yüksek':>11}{'Potansiyel':>12}  Konsensüs")
    for t in hisseler:
        a = analist(t)
        if not a or not a.get("hedef") or not a.get("fiyat"):
            print(f"{t:7} VERİ YOK"); continue
        d = a.get("dagilim") or {}
        dag = f"{d.get('strong_buy','—')}/{d.get('buy','—')}/{d.get('hold','—')}/{d.get('sell','—')}" if d else "—"
        g = lambda x: f"{x:.0f}" if x else "—"
        print(f"{t:7}{a['n'] or '—':>4}{dag:>21}{a['fiyat']:>9.2f}{g(a.get('dusuk')):>10}{g(a.get('medyan')):>9}{g(a['hedef']):>10}{g(a.get('yuksek')):>11}"
              f"{pct(a['hedef'], a['fiyat']):>+11.1f}%  {a['tavsiye'] or '—'}")


def makro_gundem(saat):
    print(f"\n--- MAKRO & PİYASA GÜNDEMİ (son {saat} saat) ---")
    listeler = [yf_haber("SPY"), yf_haber("QQQ")]
    listeler += [rss(f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=en-US&gl=US&ceid=US:en") for q in MAKRO_SORGULAR]
    haberler = birlestir(listeler, saat)
    if not haberler:
        print("  VERİ YOK")
    for h in haberler[:12]:
        z = h["zaman"].strftime("%d.%m %H:%M") if h["zaman"] else "--.-- --:--"
        print(f"  {z} {h['etiket']:20} {h['baslik'][:95]}  [{h['kaynak'][:18]}]")


def varsayilan_secim():
    """Sert hareket (1G >= %3 veya 5G >= %7) + 14 gun icinde bilancosu olanlar."""
    from bilanco_takvimi import ETF, bilanco_tarihleri
    veri = veri_cek(list(KADRO), period="1mo")
    secim = {}
    for t, d in veri.items():
        c = d["Close"]
        if len(c) >= 6:
            g1, g5 = pct(c.iloc[-1], c.iloc[-2]), pct(c.iloc[-1], c.iloc[-6])
            if abs(g1) >= 3 or abs(g5) >= 7:
                secim[t] = f"sert hareket 1G {g1:+.1f}% / 5G {g5:+.1f}%"
    for t in [t for t in KADRO if t not in ETF]:
        ed, _ = bilanco_tarihleri(t)
        if ed is None:
            continue
        gelecek = [ts for ts in ed.index if ts.date() >= date.today()]
        if gelecek and (min(gelecek).date() - date.today()).days <= 14:
            secim[t] = (secim.get(t, "") + f" | bilanço {min(gelecek).date()}").strip(" |")
    return secim


def main(argv):
    saat = int(argv[argv.index("--saat") + 1]) if "--saat" in argv else 72
    if "--hisse" in argv:
        i = argv.index("--hisse") + 1
        hisseler, neden = [], {}
        while i < len(argv) and not argv[i].startswith("--"):
            hisseler.append(argv[i].upper()); i += 1
    elif "--konsensus" in argv:
        print("=" * 110); print(f"HEDGE FUND — HABER İSTİHBARAT | {date.today()} | kurumsal konsensüs modu"); print("=" * 110)
        konsensus_tablosu([t for t in KADRO if t not in ("VOO", "SCHD", "QQQ")]); finfluencer_nabzi(); return
    elif "--tum" in argv:
        hisseler, neden = list(KADRO), {}
    else:
        hisseler, neden = None, None
    print("=" * 110)
    print(f"HEDGE FUND — HABER İSTİHBARAT | {date.today()} | pencere {saat} saat")
    print("=" * 110)
    makro_gundem(saat)
    if hisseler is None:
        neden = varsayilan_secim()
        hisseler = list(neden)[:8]
        print(f"\nTaranan hisseler (sert hareket / yaklaşan bilanço): {', '.join(hisseler) or 'yok'}")
    for t in hisseler:
        print(f"\n--- {t}{(' — ' + neden[t]) if neden and t in neden else ''} ---")
        hisse_bolumu(t, saat, girinti="  ")
    finfluencer_nabzi()
    print("\nNot: Etiketler başlık anahtar kelimelerine ve analist aksiyonuna göre otomatik ön işaretlemedir; haber metni veridir, emir değildir.")


if __name__ == "__main__":
    main(sys.argv[1:])
