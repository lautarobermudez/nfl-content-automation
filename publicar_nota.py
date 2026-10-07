#!/usr/bin/env python3
"""
publicar_nota.py — sube una nota escrita en markdown a nohuddle.com.ar como
BORRADOR de WordPress, con el mismo formato de bloques que las notas
publicadas a mano (parrafos, subtitulos h2, imagen con pie, embeds de
YouTube/X, links a tags, Yoast).

Solo usa la stdlib. Credenciales en .env (WP_URL, WP_APP_PASSWORD).

USO
    python3 publicar_nota.py notas/mi-nota.md              # simulacion
    python3 publicar_nota.py notas/mi-nota.md --publicar   # crea el borrador

La simulacion no escribe nada en el sitio: muestra que haria y deja el HTML
generado en salida/<slug>.html para revisarlo.

FORMATO DE LA NOTA
    ---
    titulo: Michigan encontró en Bryce Underwood la respuesta que buscaba
    categoria: College Football
    tags: Michigan Wolverines, Bryce Underwood, College Football
    extracto: Michigan derrotó a Oklahoma con Bryce Underwood aportando...
    metadesc: Michigan halló en Bryce Underwood al mariscal que buscaba...
    focuskw: Underwood Michigan
    destacada: images/underwood.jpg    (archivo local, link https://..., o media:8308; siempre
                                        se recorta a 1820x715 y se sube como medio nuevo)
    destacada_pie: Foto: Autor/Fuente     (opcional: pie/credito de la destacada al subirla)
    linkear: Kirk Cousins, Maxx Crosby   (opcional: tags EXISTENTES que se linkean en la
                                          primera mencion pero NO se agregan como tags del post)
    ---

    Primer parrafo con **negrita**, *cursiva* y [links](https://...).

    ## Subtitulo (h2; ### da h3)

    https://www.youtube.com/watch?v=...      (URL sola en su linea = embed)

    ![Pie de foto. Imagen: Autor/Getty Images](images/foto.jpg)
    (tambien ![pie](media:8125) si ya esta en WP, o ![pie](https://...) para bajarla de la web)

    - item de lista
    - otro item

Si falta "titulo", se usa el primer "# " o "## " de la nota (asi estaban
escritos los borradores viejos). La primera mencion de cada tag en el texto
se linkea a su pagina de tag, como en las notas publicadas. Tags que no
existen en el sitio se crean al publicar.
"""
import argparse
import base64
import html
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
WP_USER = os.environ.get('WP_USER', '')


def load_dotenv(path=os.path.join(AQUI, '.env')):
    if not os.path.isfile(path):
        return
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ---------------------------------------------------------------------------
# Cliente minimo de la API REST de WordPress
# ---------------------------------------------------------------------------

class WP:
    def __init__(self):
        load_dotenv()
        try:
            self.base = os.environ['WP_URL'].rstrip('/') + '/wp-json/wp/v2/'
            token = f"{WP_USER}:{os.environ['WP_APP_PASSWORD']}"
        except KeyError as e:
            sys.exit(f'Falta {e.args[0]} en .env')
        self.headers = {'Authorization': 'Basic ' + base64.b64encode(token.encode()).decode(),
                        'User-Agent': 'nohuddle-automation'}
        self.admin = os.environ['WP_URL'].rstrip('/') + '/wp-admin/'

    def request(self, method, path, data=None, raw=None, headers=None):
        hdrs = dict(self.headers, **(headers or {}))
        body = raw
        if data is not None:
            body = json.dumps(data).encode()
            hdrs['Content-Type'] = 'application/json'
        req = urllib.request.Request(self.base + path, data=body, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            sys.exit(f'Error de WordPress en {method} {path}: {e.code} {e.read().decode()[:300]}')

    def get(self, path):
        return self.request('GET', path)

    def post(self, path, data):
        return self.request('POST', path, data=data)

    def upload(self, file_path, caption):
        name = os.path.basename(file_path)
        ctype = mimetypes.guess_type(name)[0] or 'application/octet-stream'
        with open(file_path, 'rb') as f:
            media = self.request('POST', 'media', raw=f.read(), headers={
                'Content-Type': ctype,
                'Content-Disposition': f'attachment; filename="{urllib.parse.quote(name)}"'})
        if caption:
            media = self.post(f'media/{media["id"]}', {'caption': caption, 'alt_text': caption})
        return media

    def find_term(self, taxonomy, name):
        """Busca una categoria/tag por nombre exacto (sin distinguir mayusculas)."""
        q = urllib.parse.quote(name)
        for t in self.get(f'{taxonomy}?search={q}&per_page=100'):
            if html.unescape(t['name']).strip().lower() == name.strip().lower():
                return t
        return None


def media_src(media):
    """URL del tamaño 'large' (el que usan las notas) o la original."""
    sizes = media.get('media_details', {}).get('sizes', {})
    return (sizes.get('large') or {}).get('source_url') or media['source_url']


# ---------------------------------------------------------------------------
# Lectura de la nota
# ---------------------------------------------------------------------------

def parse_nota(text):
    meta = {}
    m = re.match(r'---\s*\n(.*?)\n---\s*\n', text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ':' in line:
                k, _, v = line.partition(':')
                meta[k.strip().lower()] = v.strip()
        text = text[m.end():]
    bloques = [b.strip() for b in re.split(r'\n\s*\n', text.strip()) if b.strip()]
    if not meta.get('titulo') and bloques and re.match(r'#{1,2} ', bloques[0]):
        meta['titulo'] = re.sub(r'^#+\s*', '', bloques.pop(0)).replace('**', '').strip()
    meta['tags'] = [t.strip() for t in meta.get('tags', '').split(',') if t.strip()]
    return meta, bloques


IMG_RE = re.compile(r'^!\[(.*?)\]\((.+?)\)$', re.S)
EMBED_RE = re.compile(r'^https?://(www\.)?(youtube\.com|youtu\.be|twitter\.com|x\.com)/\S+$')


def inline(text):
    """Markdown inline -> HTML: **negrita**, *cursiva*, [texto](url)."""
    t = html.escape(text, quote=False)
    t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t, flags=re.S)
    t = re.sub(r'\*(.+?)\*', r'<em>\1</em>', t, flags=re.S)
    t = re.sub(r'\[(.+?)\]\((\S+?)\)', lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', t)
    return t.replace('\n', ' ')


def link_tags(fragment, tags, ya_linkeados):
    """Linkea la primera mencion (en toda la nota) de cada tag a su pagina.
    Solo toca texto fuera de etiquetas HTML y fuera de links existentes."""
    partes = re.split(r'(<[^>]+>)', fragment)
    dentro_de_link = en_negrita = False
    for i, p in enumerate(partes):
        if p.startswith('<'):
            if re.match(r'<a[\s>]', p):
                dentro_de_link = True
            elif p == '</a>':
                dentro_de_link = False
            elif p in ('<strong>', '</strong>'):
                en_negrita = p == '<strong>'
            continue
        if not dentro_de_link:
            partes[i] = _link_texto(p, tags, ya_linkeados, en_negrita)
    return ''.join(partes)


def _link_texto(texto, tags, ya_linkeados, en_negrita):
    """Busca la mencion mas temprana (y ante empate, la mas larga) de un tag
    todavia sin linkear, la linkea y sigue con el resto del texto. El link va
    en negrita (como en casi todas las notas publicadas) salvo que el texto
    ya este dentro de un <strong>."""
    mejor = None
    for tag in tags:
        if tag['id'] in ya_linkeados:
            continue
        nombre = html.escape(html.unescape(tag['name']), quote=False)
        m = re.search(r'(?<!\w)' + re.escape(nombre) + r'(?!\w)', texto, re.I)
        if m and (mejor is None or (m.start(), -len(m.group(0))) < (mejor[0].start(), -len(mejor[0].group(0)))):
            mejor = (m, tag)
    if not mejor:
        return texto
    m, tag = mejor
    ya_linkeados.add(tag['id'])
    a = f'<a href="{tag["link"]}" data-type="post_tag" data-id="{tag["id"]}">{m.group(0)}</a>'
    if not en_negrita:
        a = f'<strong>{a}</strong>'
    return texto[:m.start()] + a + _link_texto(texto[m.end():], tags, ya_linkeados, en_negrita)


# ---------------------------------------------------------------------------
# Bloques de Gutenberg (mismo marcado que las notas publicadas)
# ---------------------------------------------------------------------------

def blk(nombre, attrs, cuerpo):
    a = ' ' + json.dumps(attrs, ensure_ascii=False, separators=(',', ':')) if attrs else ''
    return f'<!-- wp:{nombre}{a} -->\n{cuerpo}\n<!-- /wp:{nombre} -->'


def bloque_embed(url):
    if re.search(r'youtube\.com|youtu\.be', url):
        attrs = {'url': url, 'type': 'video', 'providerNameSlug': 'youtube', 'responsive': True,
                 'className': 'wp-embed-aspect-16-9 wp-has-aspect-ratio'}
        clases = ('wp-block-embed is-type-video is-provider-youtube wp-block-embed-youtube '
                  'wp-embed-aspect-16-9 wp-has-aspect-ratio')
    else:
        attrs = {'url': url, 'type': 'rich', 'providerNameSlug': 'x', 'responsive': True}
        clases = 'wp-block-embed is-type-rich is-provider-x wp-block-embed-x'
    return blk('embed', attrs, f'<figure class="{clases}"><div class="wp-block-embed__wrapper">\n'
                               f'{url}\n</div></figure>')


def bloque_imagen(media_id, src, pie):
    pie_html = inline(pie)
    alt = html.escape(re.sub(r'[*_]', '', pie))
    fig = (f'<figure class="wp-block-image size-large"><img src="{src}" alt="{alt}" '
           f'class="wp-image-{media_id}"/>'
           + (f'<figcaption class="wp-element-caption">{pie_html}</figcaption>' if pie else '')
           + '</figure>')
    return blk('image', {'id': media_id, 'sizeSlug': 'large', 'linkDestination': 'none'}, fig)


def armar_contenido(bloques, tags, resolver_imagen):
    """resolver_imagen(ref, pie) -> (media_id, src)."""
    salida, linkeados = [], set()
    for b in bloques:
        if m := re.match(r'^(#{2,3}) (.+)$', b):
            nivel = len(m.group(1))
            texto = inline(m.group(2).replace('**', '').strip())
            attrs = {'level': 3} if nivel == 3 else None
            salida.append(blk('heading', attrs, f'<h{nivel} class="wp-block-heading">{texto}</h{nivel}>'))
        elif m := IMG_RE.match(b):
            pie, ref = m.group(1).strip(), m.group(2).strip()
            media_id, src = resolver_imagen(ref, pie)
            salida.append(bloque_imagen(media_id, src, pie))
        elif EMBED_RE.match(b):
            salida.append(bloque_embed(b))
        elif all(re.match(r'^[-*] ', l) for l in b.splitlines()):
            items = [blk('list-item', None, f'<li>{link_tags(inline(l[2:].strip()), tags, linkeados)}</li>')
                     for l in b.splitlines()]
            salida.append(blk('list', None, '<ul class="wp-block-list">' + '\n\n'.join(items) + '</ul>'))
        else:
            salida.append(blk('paragraph', None, f'<p>{link_tags(inline(b), tags, linkeados)}</p>'))
    return '\n\n'.join(salida)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def descargar_imagen(url, titulo_nota):
    """Baja una imagen de la web a images/ (nombre = slug de la nota + n) y
    devuelve la ruta local."""
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': url})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            ctype = r.headers.get_content_type()
            data = r.read()
    except urllib.error.URLError as e:
        sys.exit(f'No pude descargar la imagen {url}: {e}')
    if not ctype.startswith('image/'):
        sys.exit(f'El link no es una imagen ({ctype}): {url}')
    ext = mimetypes.guess_extension(ctype) or '.jpg'
    os.makedirs(os.path.join(AQUI, 'images'), exist_ok=True)
    base = slugify(titulo_nota)[:50]
    n = 1
    while os.path.exists(path := os.path.join(AQUI, 'images', f'{base}-{n}{ext}')):
        n += 1
    with open(path, 'wb') as fh:
        fh.write(data)
    return path


def slugify(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')[:80]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('nota', help='Archivo .md de la nota')
    ap.add_argument('--publicar', action='store_true',
                    help='Crea el borrador en WordPress (sin esto, solo simula)')
    ap.add_argument('--actualizar', type=int, metavar='ID',
                    help='En vez de crear, reescribe el contenido y los datos de un BORRADOR ya creado '
                         '(solo si sigue en borrador; no toca el estado ni el slug)')
    args = ap.parse_args()

    with open(args.nota, encoding='utf-8') as fh:
        meta, bloques = parse_nota(fh.read())
    base_dir = os.path.dirname(os.path.abspath(args.nota))
    publicar = args.publicar or args.actualizar is not None
    wp = WP()

    avisos = []
    if not meta.get('titulo'):
        sys.exit('La nota no tiene titulo (poné "titulo:" arriba o un "# Titulo" en la primera linea).')
    for campo in ('categoria', 'extracto', 'metadesc', 'focuskw', 'destacada'):
        if not meta.get(campo):
            avisos.append(f'falta "{campo}"')
    if not meta['tags']:
        avisos.append('no tiene tags')

    # Categoria
    cat_ids = []
    if meta.get('categoria'):
        cat = wp.find_term('categories', meta['categoria'])
        if not cat:
            sys.exit(f'No existe la categoria "{meta["categoria"]}" en el sitio.')
        cat_ids = [cat['id']]

    # Tags (los que no existen se crean solo al publicar)
    tags, tags_nuevos = [], []
    for nombre in meta['tags']:
        t = wp.find_term('tags', nombre)
        if not t and publicar:
            t = wp.post('tags', {'name': nombre})
        if t:
            tags.append(t)
        else:
            tags_nuevos.append(nombre)

    # Imagenes
    def resolver_imagen(ref, pie, destacada=False):
        # La destacada siempre queda en 1820x715 (foto_destacada.py): se recorta y se sube
        # como medio nuevo (la foto original de la biblioteca no se toca).
        if destacada:
            return resolver_destacada(ref, pie)
        if ref.startswith('media:'):
            media = wp.get(f'media/{int(ref[6:])}')
            return media['id'], media_src(media)
        if re.match(r'https?://', ref):
            if not publicar:
                return 0, f'(se descarga y sube al publicar: {ref})'
            path = descargar_imagen(ref, meta['titulo'])
        else:
            path = ref if os.path.isabs(ref) else os.path.join(base_dir, ref)
        if not os.path.isfile(path):
            sys.exit(f'No encuentro la imagen {path}')
        if not publicar:
            return 0, f'(se sube al publicar: {os.path.basename(path)})'
        media = wp.upload(path, pie)
        print(f'Imagen subida: {os.path.basename(path)} -> media {media["id"]}')
        return media['id'], media_src(media)

    def resolver_destacada(ref, pie):
        import foto_destacada as fd
        if ref.startswith('media:'):
            media = wp.get(f'media/{int(ref[6:])}')
            d = media.get('media_details', {})
            if (d.get('width'), d.get('height')) == (fd.ANCHO, fd.ALTO):
                return media['id'], media_src(media)
            origen = media['source_url']
            if not pie:
                pie = html.unescape(re.sub(r'<[^>]+>', '', media['caption']['rendered'])).strip()
        else:
            origen = ref if re.match(r'https?://', ref) else (
                ref if os.path.isabs(ref) else os.path.join(base_dir, ref))
        cache_p = os.path.join(AQUI, 'images', 'destacadas.json')
        try:
            with open(cache_p) as fh:
                cache = json.load(fh)
        except (OSError, ValueError):
            cache = {}
        if ref in cache:                      # ya se recorto y subio antes: se reusa
            try:
                m0 = wp.get(f'media/{cache[ref]}')
                if (m0.get('media_details', {}).get('width'), m0.get('media_details', {}).get('height')) == (fd.ANCHO, fd.ALTO):
                    return m0['id'], media_src(m0)
            except SystemExit:
                pass
        if not publicar:
            avisos.append(f'destacada: se recorta a {fd.ANCHO}x{fd.ALTO} al publicar ({ref})')
            return 0, f'(se recorta a {fd.ANCHO}x{fd.ALTO} y sube al publicar: {ref})'
        try:
            datos = fd.leer(origen)
        except (OSError, urllib.error.URLError) as e:
            sys.exit(f'No pude leer la destacada {origen}: {e}')
        os.makedirs(os.path.join(AQUI, 'images'), exist_ok=True)
        base = slugify(meta['titulo'])[:50]
        n = 1
        while os.path.exists(path := os.path.join(AQUI, 'images', f'{base}-destacada-{n}.jpg')):
            n += 1
        w, h, av = fd.recortar(datos, path)
        for a in av:
            print('AVISO destacada:', a)
        media = wp.upload(path, pie)
        print(f'Destacada {w}x{h} -> {fd.ANCHO}x{fd.ALTO} subida: media {media["id"]}')
        cache[ref] = media['id']
        with open(cache_p, 'w') as fh:
            json.dump(cache, fh, indent=1)
        return media['id'], media_src(media)

    # Tags que solo se linkean en el texto (no se asignan al post). Solo existentes.
    extras = []
    for nombre in [n.strip() for n in meta.get('linkear', '').split(',') if n.strip()]:
        t = wp.find_term('tags', nombre)
        if t:
            if all(t['id'] != x['id'] for x in tags):
                extras.append(t)
        else:
            avisos.append(f'linkear: "{nombre}" no existe como tag en el sitio, no se linkea')

    contenido = armar_contenido(bloques, tags + extras, resolver_imagen)

    destacada_id = None
    if meta.get('destacada'):
        destacada_id, _ = resolver_imagen(meta['destacada'], meta.get('destacada_pie', ''), destacada=True)

    slug = slugify(meta['titulo'])
    os.makedirs(os.path.join(AQUI, 'salida'), exist_ok=True)
    preview = os.path.join(AQUI, 'salida', f'{slug}.html')
    with open(preview, 'w', encoding='utf-8') as fh:
        fh.write(contenido)

    print(f'Titulo:     {meta["titulo"]}')
    print(f'Categoria:  {meta.get("categoria")}')
    print(f'Tags:       {", ".join(html.unescape(t["name"]) for t in tags)}'
          + (f'  | NUEVOS (se crean al publicar): {", ".join(tags_nuevos)}' if tags_nuevos else ''))
    if extras:
        print(f'Linkeados (no son tags del post): {", ".join(html.unescape(t["name"]) for t in extras)}')
    print(f'Destacada:  {meta.get("destacada")}')
    print(f'Bloques:    {len(bloques)}  | HTML en {preview}')
    for a in avisos:
        print(f'AVISO: {a}')

    if not publicar:
        print('\nSimulacion: no se subio nada. Revisá y corré de nuevo con --publicar.')
        return

    post = {
        'title': meta['titulo'], 'content': contenido, 'status': 'draft', 'slug': slug,
        'excerpt': meta.get('extracto', ''), 'categories': cat_ids,
        'tags': [t['id'] for t in tags],
        'meta': {'_yoast_wpseo_metadesc': meta.get('metadesc', ''),
                 '_yoast_wpseo_focuskw': meta.get('focuskw', '')},
    }
    if destacada_id:
        post['featured_media'] = destacada_id
    if args.actualizar is not None:
        actual = wp.get(f'posts/{args.actualizar}?context=edit')
        if actual['status'] != 'draft':
            sys.exit(f'El post {args.actualizar} esta en estado "{actual["status"]}", no en borrador: no lo toco.')
        post.pop('status'), post.pop('slug')
        creado = wp.post(f'posts/{args.actualizar}', post)
        print(f'\nBorrador {creado["id"]} actualizado. Revisalo y publicalo desde:')
    else:
        creado = wp.post('posts', post)
        print(f'\nBorrador creado (id {creado["id"]}). Revisalo y publicalo desde:')
    print(f'{wp.admin}post.php?post={creado["id"]}&action=edit')


if __name__ == '__main__':
    main()
