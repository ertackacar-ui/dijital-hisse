"""HEDGE FUND ortak veri - TEMIZ KOPYA (yayin). Pozisyon ve tutar bilgisi YOKTUR; otomatik uretilir."""

LIG_1 = {'VOO': (None, None), 'SCHD': (None, None), 'BRK-B': (None, None), 'LLY': (None, None), 'V': (None, None), 'MSFT': (None, None), 'AMZN': (None, None), 'GOOG': (None, None), 'COST': (None, None)}
LIG_2 = {'QQQ': (None, None), 'NVDA': (None, None), 'AVGO': (None, None), 'VRT': (None, None), 'ASML': (None, None), 'MU': (None, None), 'AMD': (None, None), 'TSM': (None, None), 'ANET': (None, None), 'PANW': (None, None), 'NOW': (None, None), 'PWR': (None, None), 'PLTR': (None, None)}
LIG_3 = {'OKLO': (None, None), 'RGTI': (None, None), 'SPCX': (None, None), 'MP': (None, None), 'CRDO': (None, None)}
KADRO = {**LIG_1, **LIG_2, **LIG_3}
MAKRO = ['^VIX', '^TNX', 'DX-Y.NYB']
SHIELD_EXEMPT = ['SCHD', 'BRK-B']
ACTIVE_SHIELDS = {'PLTR': {'geri_alim_pusu': 134.0, 'tarih': '2026-11-24'}, 'AMZN': {'ana_pusu': 232.0, 'bilgi_seviyesi': 243.4, 'tarih': '2026-11-24'}}
EMA21_GUARD = ['LLY', 'V']
KARTOPU = {'AVGO': 372.5, 'TSM': 408.0, 'GOOG': 311.3, 'NVDA': 213.8, 'NOW': 128.0, 'AMD': 600.0, 'PANW': 382.0, 'PWR': 645.0, 'PLTR': 170.0}
PUSU = {'VOO': [645, 573], 'SCHD': [32.5], 'BRK-B': [538, 521], 'LLY': [1325, 1293], 'V': [400, 386], 'AMZN': [243.4, 232.0], 'GOOG': [265, 248], 'COST': [975], 'QQQ': [635, 600], 'NVDA': [129.8], 'AVGO': [285, 260], 'ASML': [1310, 1220], 'MU': [640, 580], 'AMD': [375], 'TSM': [340, 315], 'ANET': [142], 'NOW': [89.4], 'PLTR': [134.0]}
MIN_SHIELD_POS_USD = 200.0
MIN_SHIELD_PROFIT_USD = 25.0
MIKRO_LOT_NOTU = '(Mikro lot — komisyon eşiği altı)'


def mikro_lot(t, fiyat):
    return False  # yayin kopyasinda pozisyon yok


assert len(KADRO) == 27
