#!/usr/bin/env python3
"""
foto_destacada.py — deja cualquier foto en el formato de la imagen destacada de
Nohuddle: 1820 x 715 px (JPEG). Recorta al aspecto 1820:715 y redimensiona.

    python3 foto_destacada.py foto.jpg [salida.jpg]      (tambien acepta un link https://)

Se usa solo desde publicar_nota.py (campo `destacada:` de las notas). Necesita Pillow
(instalado en ~/.venvs/nohuddle-automation; si el Python que corre el script no lo
tiene, se busca ahi).
"""
import glob
import io
import os
import sys
import urllib.request

ANCHO, ALTO = 1820, 715
# Las caras suelen estar en la parte alta de la foto: el recorte vertical no es
# centrado sino un poco hacia arriba (0 = pegado arriba, 0.5 = centrado).
ENFOQUE_VERTICAL = 0.3

AQUI = os.path.dirname(os.path.abspath(__file__))


def _pil():
    try:
        from PIL import Image
    except ImportError:
        for sp in glob.glob(os.path.expanduser('~/.venvs/nohuddle-automation/lib/python3*/site-packages')):
            sys.path.append(sp)
        try:
            from PIL import Image
        except ImportError:
            sys.exit('Falta Pillow para recortar la destacada (1820x715): '
                     '~/.venvs/nohuddle-automation/bin/python -m pip install pillow')
    return Image


def leer(origen):
    """Bytes de un archivo local o de un link."""
    if origen.startswith(('http://', 'https://')):
        req = urllib.request.Request(origen, headers={'User-Agent': 'Mozilla/5.0', 'Referer': origen})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    with open(origen, 'rb') as f:
        return f.read()


def recortar(datos, destino, enfoque=ENFOQUE_VERTICAL):
    """Recorta `datos` (bytes de imagen) a ANCHO x ALTO y lo guarda en `destino`.
    Devuelve (ancho_original, alto_original, avisos)."""
    Image = _pil()
    from PIL import ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(datos))).convert('RGB')
    w, h = im.size
    avisos = []
    objetivo = ANCHO / ALTO
    if w / h > objetivo:                       # mas ancha que 1820:715 -> recorta los costados
        nw, nh = round(h * objetivo), h
        x0, y0 = (w - nw) // 2, 0
    else:                                      # mas alta -> recorta arriba/abajo
        nw, nh = w, round(w / objetivo)
        x0, y0 = 0, round((h - nh) * enfoque)
    im = im.crop((x0, y0, x0 + nw, y0 + nh))
    if nw < ANCHO:
        avisos.append(f'la foto original es chica ({w}x{h}): al llevarla a {ANCHO}x{ALTO} '
                      f'se agranda y puede verse borrosa')
    im = im.resize((ANCHO, ALTO), Image.LANCZOS)
    os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
    im.save(destino, 'JPEG', quality=90, optimize=True)
    return w, h, avisos


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    origen = sys.argv[1]
    destino = sys.argv[2] if len(sys.argv) > 2 else os.path.join(AQUI, 'images', 'destacada-prueba.jpg')
    w, h, avisos = recortar(leer(origen), destino)
    print(f'{origen} ({w}x{h}) -> {destino} ({ANCHO}x{ALTO})')
    for a in avisos:
        print('AVISO:', a)


if __name__ == '__main__':
    main()
