#!/usr/bin/env python3
"""
ultimo_video.py — imprime la URL del ultimo video subido al canal de YouTube
de No Huddle (@nohuddleok), salteando los Shorts. Usa el feed RSS publico
del canal: no necesita API key.

    python3 ultimo_video.py          # URL del ultimo video
    python3 ultimo_video.py -v       # ultimos videos con fecha y titulo
"""
import json
import os
import re
import sys
import time
import urllib.request

CHANNEL_ID = 'UCZ4FPVtNO0n89VKzh_3F9ng'  # No Huddle (@nohuddleok)
FEED = f'https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}'
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.ultimo_video_cache.json')


def _feed(intentos=5):
    """El feed de YouTube da 404/500 pasajeros: se reintenta con espera creciente."""
    ultimo = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(FEED, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode('utf-8')
        except Exception as e:                       # noqa: BLE001
            ultimo = e
            time.sleep(1.5 * (i + 1))
    raise ultimo


def ultimo_cacheado():
    """Ultimo video bueno guardado (para cuando el feed no responde), o None."""
    try:
        with open(CACHE) as f:
            return json.load(f)['url']
    except (OSError, ValueError, KeyError):
        return None


def guardar_cache(url, fecha):
    try:
        with open(CACHE, 'w') as f:
            json.dump({'url': url, 'fecha': fecha}, f)
    except OSError:
        pass


def videos():
    xml = _feed()
    for entry in re.findall(r'<entry>(.*?)</entry>', xml, re.S):
        link = re.search(r'<link rel="alternate" href="([^"]+)"', entry).group(1)
        titulo = re.search(r'<title>(.*?)</title>', entry, re.S).group(1)
        fecha = re.search(r'<published>(.*?)</published>', entry).group(1)[:10]
        yield link, titulo, fecha


def main():
    lista = [v for v in videos() if '/shorts/' not in v[0]]
    if not lista:
        sys.exit('No encontre videos (sin contar Shorts) en el feed del canal.')
    guardar_cache(lista[0][0], lista[0][2])
    if '-v' in sys.argv:
        for link, titulo, fecha in lista[:5]:
            print(f'{fecha}  {link}  {titulo}')
    else:
        print(lista[0][0])


if __name__ == '__main__':
    main()
