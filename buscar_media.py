#!/usr/bin/env python3
"""
buscar_media.py — busca fotos ya subidas a la biblioteca de medios de
WordPress, para reusarlas en una nota como ![pie](media:ID).

    python3 buscar_media.py "Bo Nix" "Denver Broncos"
"""
import html
import re
import sys
import urllib.parse

from publicar_nota import WP


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    wp = WP()
    vistos = set()
    for termino in sys.argv[1:]:
        q = urllib.parse.quote(termino)
        res = wp.get(f'media?search={q}&media_type=image&per_page=20&orderby=date&order=desc')
        print(f'== "{termino}": {len(res)} resultado(s)')
        for m in res:
            if m['id'] in vistos:
                continue
            vistos.add(m['id'])
            d = m.get('media_details', {})
            pie = html.unescape(re.sub(r'<[^>]+>', '', m['caption']['rendered'])).strip()
            titulo = html.unescape(m['title']['rendered'])
            print(f"  media:{m['id']}  {m['date'][:10]}  {d.get('width')}x{d.get('height')}  "
                  f"{titulo}\n      pie: {pie or '(sin pie)'}\n      {m['source_url']}")


if __name__ == '__main__':
    main()
