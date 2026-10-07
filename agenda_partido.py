#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agenda_partido.py — notas de partido de la NFL (temporada regular) para
nohuddle.com.ar: "A vs. B, por la Semana N: hora y cómo ver la NFL en vivo por
TV y streaming" (categoria Agenda).

Arma todo lo fijo de la plantilla (titulo, subtitulos, horarios en Argentina,
Mexico y España, parrafo de TV, tags, extracto, Yoast) con los datos del
calendario de ESPN, y deja que la parte redactada (enganche, un parrafo por
equipo y el cierre) venga de un archivo escrito aparte. Despues reusa
publicar_nota.py para dejar el BORRADOR en WordPress.

Solo usa la stdlib. Credenciales de WP en .env (como publicar_nota.py).

USO
    python3 agenda_partido.py --lista [--semana 5]
        Partidos de la semana (por defecto la actual): cuando, donde, cadena.

    python3 agenda_partido.py --ficha "Raiders Chiefs" [--semana 4]
        Datos duros del partido para redactar: horarios ya convertidos, estadio,
        TV, record y ultimos resultados de cada equipo.

    python3 agenda_partido.py notas/agenda/semana-04-raiders-chiefs.md
        Simula (genera salida/agenda-<slug>.md y el HTML; no sube nada).
    python3 agenda_partido.py notas/agenda/semana-04-raiders-chiefs.md --publicar
        Crea el borrador en WordPress.

ARCHIVO DE LA NOTA (lo redacta Claude; ver la skill armar-agenda-partido)
    ---
    semana: 4
    partido: Kansas City Chiefs @ Las Vegas Raiders     (visitante @ local, o palabras sueltas)
    tweet: https://twitter.com/Raiders/status/123...    (opcional: embed de X)
    destacada: media:8436                               (media:ID, URL o archivo; opcional)
    destacada_pie: Foto: Getty Images                   (opcional)
    linkear: Patrick Mahomes, Ashton Jeanty             (figuras con tag existente a linkear)
    relatos: Ian Eagle y Charles Davis                  (los relatores cambian por partido: buscarlos)
    latam: En **México** se podrá ver por …             (opcional: pisa el tramo de México/Sudamérica/España,
                                                         que cambia por partido; ver Infobae "Semana N NFL canales")
    titulo: ...                                         (pisa el título; ej. notas de Sunday Night Football)
    tv_confirmado: si                                   (el usuario aprobó el párrafo de TV de ESTA nota)
    video: ninguno                                      (opcional: por defecto va el ultimo video del canal
                                                         de No Huddle antes del 1er subtitulo; o una URL)
    cadena: CBS                                         (opcional: pisa la de ESPN)
    extracto: ...  metadesc: ...  focuskw: ...          (opcionales: sino, los de la plantilla)
    ---
    ## enganche
    Este duelo de la AFC Oeste, correspondiente a la Semana 4 de la NFL, ...

    ## local
    (parrafo del equipo local)

    ## visitante
    (parrafo del equipo visitante)

    ## cierre
    (rivalidad / serie historica)

REGLAS QUE YA ESTAN RESUELTAS
    - Titulo: VISITANTE vs. LOCAL (como en las notas publicadas).
    - Horarios: Este de EEUU, hora local del estadio, Argentina, Mexico y
      España, calculados con zonas horarias reales: en verano de EEUU Mexico
      es Este -2 h (no -1), en invierno Este -1 h; Argentina +1 / +2 y
      España +6. Los dias de la lista cambian solos si cruzan medianoche.
    - Cadena y relatos: de agenda_tv.json. Si el texto de esa cadena no esta
      'confirmado', avisa y no deja publicar sin --tv-sin-confirmar.
    - Tags del post: los dos equipos + NFL. "linkear" solo linkea figuras.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.request
from zoneinfo import ZoneInfo

import ultimo_video

AQUI = os.path.dirname(os.path.abspath(__file__))
ESPN = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl'
UA = {'User-Agent': 'Mozilla/5.0'}

DIAS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
         'septiembre', 'octubre', 'noviembre', 'diciembre']

ET = ZoneInfo('America/New_York')
PAISES = [('Argentina', ZoneInfo('America/Argentina/Buenos_Aires')),
          ('México', ZoneInfo('America/Mexico_City')),
          ('España', ZoneInfo('Europe/Madrid'))]

# Zona horaria del estadio segun el estado de EEUU (Arizona no tiene horario de verano).
TZ_ESTADO = {
    'AZ': 'America/Phoenix', 'CA': 'America/Los_Angeles', 'NV': 'America/Los_Angeles',
    'WA': 'America/Los_Angeles', 'CO': 'America/Denver', 'TX': 'America/Chicago',
    'IL': 'America/Chicago', 'MN': 'America/Chicago', 'MO': 'America/Chicago',
    'WI': 'America/Chicago', 'LA': 'America/Chicago', 'TN': 'America/Chicago',
    'GA': 'America/New_York', 'FL': 'America/New_York', 'NC': 'America/New_York',
    'OH': 'America/New_York', 'PA': 'America/New_York', 'NY': 'America/New_York',
    'NJ': 'America/New_York', 'MD': 'America/New_York', 'MA': 'America/New_York',
    'DC': 'America/New_York', 'VA': 'America/New_York', 'MI': 'America/Detroit',
    'IN': 'America/Indiana/Indianapolis',
}
ESTADOS = {
    'AZ': 'Arizona', 'CA': 'California', 'CO': 'Colorado', 'FL': 'Florida', 'GA': 'Georgia',
    'IL': 'Illinois', 'IN': 'Indiana', 'LA': 'Louisiana', 'MA': 'Massachusetts',
    'MD': 'Maryland', 'MI': 'Michigan', 'MN': 'Minnesota', 'MO': 'Missouri',
    'NC': 'North Carolina', 'NJ': 'New Jersey', 'NV': 'Nevada', 'NY': 'New York',
    'OH': 'Ohio', 'PA': 'Pennsylvania', 'TN': 'Tennessee', 'TX': 'Texas',
    'WA': 'Washington', 'WI': 'Wisconsin', 'DC': 'Washington D. C.', 'VA': 'Virginia',
}
# Partidos fuera de EEUU: ciudad (como la informa ESPN) -> (zona, ciudad en español, país)
INTERNACIONAL = {
    'London': ('Europe/London', 'Londres', 'Inglaterra'),
    'Dublin': ('Europe/Dublin', 'Dublín', 'Irlanda'),
    'Munich': ('Europe/Berlin', 'Múnich', 'Alemania'),
    'Frankfurt': ('Europe/Berlin', 'Fráncfort', 'Alemania'),
    'Berlin': ('Europe/Berlin', 'Berlín', 'Alemania'),
    'Madrid': ('Europe/Madrid', 'Madrid', 'España'),
    'Paris': ('Europe/Paris', 'París', 'Francia'),
    'Mexico City': ('America/Mexico_City', 'Ciudad de México', 'México'),
    'São Paulo': ('America/Sao_Paulo', 'São Paulo', 'Brasil'),
    'Sao Paulo': ('America/Sao_Paulo', 'São Paulo', 'Brasil'),
    'Rio de Janeiro': ('America/Sao_Paulo', 'Río de Janeiro', 'Brasil'),
    'Melbourne': ('Australia/Melbourne', 'Melbourne', 'Australia'),
    'Toronto': ('America/Toronto', 'Toronto', 'Canadá'),
}
# ESPN a veces trae nombres de estadio viejos: si pasa, mapear 'nombre de ESPN': 'nombre real'.
# Vacio a proposito: el estadio de Houston VUELVE a llamarse Reliant Stadium desde agosto de
# 2026 (era NRG), asi que ESPN esta bien. Antes de "corregir" un nombre, verificarlo en la prensa
# local; no confiar en memoria.
ESTADIO_CORREGIDO = {}


# ---------------------------------------------------------------------------
# ESPN
# ---------------------------------------------------------------------------

def espn(path):
    req = urllib.request.Request(f'{ESPN}/{path}', headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.load(r)
    except Exception as e:
        sys.exit(f'No pude consultar ESPN ({path}): {e}')


def semana_actual():
    return espn('scoreboard')['week']['number']


def partidos_de_la_semana(semana):
    d = espn(f'scoreboard?seasontype=2&week={semana}&dates={datetime.date.today().year}')
    if d.get('week', {}).get('number') != semana:
        sys.exit(f'ESPN no devolvio la semana {semana} de temporada regular (devolvio {d.get("week")}).')
    return [normalizar(e) for e in d['events']]


def normalizar(e):
    c = e['competitions'][0]
    eq = {t['homeAway']: t for t in c['competitors']}

    def team(t):
        rec = (t.get('records') or [{}])[0].get('summary')
        return dict(id=t['team']['id'], nombre=t['team']['displayName'],
                    corto=t['team']['shortDisplayName'], abrev=t['team']['abbreviation'], record=rec)
    v = c['venue']
    addr = v.get('address', {})
    redes = [n for b in c.get('broadcasts', []) for n in b.get('names', [])]
    return dict(
        id=e['id'], utc=datetime.datetime.fromisoformat(e['date'].replace('Z', '+00:00')),
        semana=e['week']['number'], estado=e['status']['type']['name'],
        neutral=bool(c.get('neutralSite')), local=team(eq['home']), visitante=team(eq['away']),
        estadio=ESTADIO_CORREGIDO.get(v['fullName'], v['fullName']), estadio_espn=v['fullName'],
        ciudad=addr.get('city', ''), estado_cod=addr.get('state', ''), pais=addr.get('country', ''),
        redes=redes)


def buscar_partido(partidos, texto):
    """Elige el partido por palabras sueltas ('raiders chiefs') o 'Visitante @ Local'."""
    toks = [t for t in re.split(r'[\s@,/]+|\bvs\.?\b', texto.lower()) if len(t) >= 3]
    hits = []
    for p in partidos:
        pajar = ' '.join([p['local']['nombre'], p['local']['abrev'], p['visitante']['nombre'],
                          p['visitante']['abrev']]).lower()
        if toks and all(t in pajar for t in toks):
            hits.append(p)
    if len(hits) != 1:
        cand = '\n'.join(f'   - {titulo_corto(p)}' for p in (hits or partidos))
        sys.exit(f'"{texto}" {"coincide con varios partidos" if hits else "no coincide con ninguno"} '
                 f'de la semana:\n{cand}')
    return hits[0]


def titulo_corto(p):
    return f'{p["visitante"]["nombre"]} @ {p["local"]["nombre"]}'


# ---------------------------------------------------------------------------
# Fechas y horarios
# ---------------------------------------------------------------------------

def sede(p):
    """(zona del estadio, 'Ciudad, Estado/Pais' para el texto)."""
    if p['pais'] in ('USA', 'United States', '') and p['estado_cod'] in TZ_ESTADO:
        return ZoneInfo(TZ_ESTADO[p['estado_cod']]), f'{p["ciudad"]}, {ESTADOS.get(p["estado_cod"], p["estado_cod"])}'
    if p['ciudad'] in INTERNACIONAL:
        tz, ciudad, pais = INTERNACIONAL[p['ciudad']]
        return ZoneInfo(tz), f'{ciudad}, {pais}'
    sys.exit(f'No sé la zona horaria de {p["ciudad"]}, {p["estado_cod"] or p["pais"]}: sumala a '
             'TZ_ESTADO o INTERNACIONAL en agenda_partido.py.')


def hhmm(dt, tz):
    return dt.astimezone(tz).strftime('%H:%M')


def dia_largo(dt, tz):
    d = dt.astimezone(tz)
    return f'{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}'


def mayus(s):
    """Primera letra en mayuscula sin tocar el resto (str.capitalize pasa todo a minuscula)."""
    return s[:1].upper() + s[1:]


def articulo(nombre, complemento=False):
    """'los Dallas Cowboys', pero 'Los Angeles Chargers' ya lleva el articulo. Como
    complemento ('recibiran a ...') 'Las Vegas Raiders' va sin articulo (asi la nota 8435);
    como sujeto va 'Los Las Vegas Raiders' (nota 8198)."""
    if nombre.startswith('Los ') or (complemento and nombre.startswith('Las ')):
        return nombre
    return 'los ' + nombre


def horarios(p):
    tz_est, lugar = sede(p)
    et = hhmm(p['utc'], ET)
    local = hhmm(p['utc'], tz_est)
    lista = [(pais, hhmm(p['utc'], tz), dia_largo(p['utc'], tz)) for pais, tz in PAISES]
    return dict(et=et, local=local, lugar=lugar, misma_zona=(tz_est.utcoffset(p['utc']) == ET.utcoffset(p['utc'])),
                dia_et=dia_largo(p['utc'], ET), anio=p['utc'].astimezone(ET).year,
                dia_semana_et=DIAS[p['utc'].astimezone(ET).weekday()], lista=lista)


# ---------------------------------------------------------------------------
# Televisión
# ---------------------------------------------------------------------------

def cargar_tv():
    with open(os.path.join(AQUI, 'agenda_tv.json'), encoding='utf-8') as fh:
        return json.load(fh)


def parrafo_tv(p, tv, cadena=None, relatos=None, latam=None):
    """-> (texto, clave de la cadena, confirmado, faltan_relatos)."""
    nombres = [cadena] if cadena else p['redes']
    clave = None
    for n in nombres:
        clave = tv['alias_cadenas'].get(n.upper())
        if clave:
            break
    if not clave:
        sys.exit(f'No tengo texto de TV para la cadena {nombres or "(ESPN no informa cadena)"}: '
                 'agregala en agenda_tv.json (alias_cadenas y redes) o pasa "cadena:" en la nota.')
    red = tv['redes'][clave]
    rel = relatos or red.get('relatos')
    texto = red['eeuu'].replace('{relatos}', f', con los relatos de {rel}' if rel else '')
    falta_relatos = '{relatos}' in red['eeuu'] and not rel
    return f'{texto} {latam or tv["latam_espana"]}', clave, bool(red['confirmado']), falta_relatos


# ---------------------------------------------------------------------------
# Plantilla de la nota
# ---------------------------------------------------------------------------

def partes_fijas(p, tv, cadena=None, relatos=None, latam=None):
    L, V, n = p['local'], p['visitante'], p['semana']
    h = horarios(p)
    vs = f'{V["nombre"]} vs. {L["nombre"]}'
    estadio = p['estadio']
    if p['neutral']:
        intro = (f'{mayus(articulo(V["nombre"]))} y {articulo(L["nombre"])} se enfrentarán este '
                 f'{h["dia_et"]} de {h["anio"]} en el {estadio} de {h["lugar"]}.')
    else:
        intro = (f'{mayus(articulo(L["nombre"]))} recibirán a {articulo(V["nombre"], True)} este '
                 f'{h["dia_et"]} de {h["anio"]} en el {estadio}.')
    if h['misma_zona']:
        cuando = (f'El puntapié inicial del encuentro está pactado para las **{h["et"]} horas del Este de los '
                  f'Estados Unidos**. El {estadio} será la sede.')
    else:
        cuando = (f'El puntapié inicial del encuentro está pactado para las **{h["et"]} horas del Este de los '
                  f'Estados Unidos** ({h["local"]} horas en el tiempo local de {h["lugar"]}). '
                  f'El {estadio} será la sede.')
    texto_tv, clave_tv, tv_ok, falta_relatos = parrafo_tv(p, tv, cadena, relatos, latam)
    gancho = f'se enfrentan en la Semana {n}: hora, TV y streaming para seguir la acción de la NFL en vivo.'
    return dict(
        titulo=f'{vs}, por la Semana {n}: hora y cómo ver la NFL en vivo por TV y streaming',
        intro=intro, h2_cuando=f'¿Cuándo juegan y cómo ver {vs}, por la Semana {n} de la NFL?', cuando=cuando,
        h2_horario=f'Horario para {vs} según país',
        lista=[f'{pais}: {hora} ({dia})' for pais, hora, dia in h['lista']],
        h2_tv=f'¿Por dónde ver {vs}?', tv=texto_tv, clave_tv=clave_tv, tv_confirmado=tv_ok, falta_relatos=falta_relatos,
        tags=f'{L["nombre"]}, {V["nombre"]}, NFL',
        extracto=f'{V["corto"]} y {L["corto"]} se cruzan en la Semana {n}: hora, TV y streaming para seguir la acción de la NFL en vivo.',
        metadesc=f'{V["corto"]} y {L["corto"]} {gancho}',
        focuskw=f'{V["corto"]} vs {L["corto"]} Semana {n} NFL en vivo', horarios=h)


def leer_nota(path):
    txt = open(path, encoding='utf-8').read()
    m = re.match(r'---\s*\n(.*?)\n---\s*\n', txt, re.S)
    if not m:
        sys.exit(f'{path}: falta el bloque de datos (--- ... ---) arriba.')
    meta = {}
    for line in m.group(1).splitlines():
        if ':' in line:
            k, _, v = line.partition(':')
            meta[k.strip().lower()] = v.strip()
    secciones, actual = {}, None
    for line in txt[m.end():].splitlines():
        if mm := re.match(r'^##\s+(\w+)\s*$', line):
            actual = mm.group(1).lower()
            secciones[actual] = []
        elif actual:
            secciones[actual].append(line)
    cuerpo = {k: '\n'.join(v).strip() for k, v in secciones.items()}
    faltan = [k for k in ('enganche', 'local', 'visitante', 'cierre') if not cuerpo.get(k)]
    if faltan:
        sys.exit(f'{path}: faltan las secciones: ## ' + ', ## '.join(faltan))
    return meta, cuerpo


def video_canal(valor):
    """(url, descripcion) del video para antes del primer subtitulo. Por defecto el ultimo
    del canal de No Huddle (sin Shorts); 'video:' en la nota pisa la URL, 'ninguno' lo saltea."""
    if valor and valor.lower() in ('ninguno', 'no', '-'):
        return None, None
    if valor:
        return valor, 'indicado en la nota'
    try:
        lista = [v for v in ultimo_video.videos() if '/shorts/' not in v[0]]
        if lista:
            ultimo_video.guardar_cache(lista[0][0], lista[0][2])
            return lista[0][0], f'{lista[0][2]} - {lista[0][1]}'
    except Exception as e:
        cacheado = ultimo_video.ultimo_cacheado()
        if cacheado:
            print(f'AVISO: el feed de YouTube no responde ({e}); uso el ultimo video guardado.')
            return cacheado, 'ultimo video guardado (el feed no respondio)'
        print(f'AVISO: no pude leer el feed de YouTube ({e}); la nota sale sin video.')
        return None, None
    print('AVISO: el feed de YouTube no trae videos (sin contar Shorts); la nota sale sin video.')
    return None, None


def armar_markdown(meta, cuerpo, f, base_dir, video=None):
    cab = [f'titulo: {meta.get("titulo") or f["titulo"]}', 'categoria: Agenda', f'tags: {f["tags"]}',
           f'extracto: {meta.get("extracto") or f["extracto"]}',
           f'metadesc: {meta.get("metadesc") or f["metadesc"]}',
           f'focuskw: {meta.get("focuskw") or f["focuskw"]}']
    dest = meta.get('destacada', '')
    if dest and not re.match(r'(media:|https?://)', dest):
        dest = dest if os.path.isabs(dest) else os.path.abspath(os.path.join(base_dir, dest))
    if dest:
        cab.append(f'destacada: {dest}')
    if meta.get('destacada_pie'):
        cab.append(f'destacada_pie: {meta["destacada_pie"]}')
    if meta.get('linkear'):
        cab.append(f'linkear: {meta["linkear"]}')
    bloques = [f'{f["intro"]} {cuerpo["enganche"]}', cuerpo['local'], cuerpo['visitante']]
    if meta.get('tweet'):
        bloques.append(meta['tweet'])
    bloques += [cuerpo['cierre']] + ([video] if video else [])
    bloques += [f'## {f["h2_cuando"]}', f['cuando'], f'## {f["h2_horario"]}',
                '\n'.join(f'- {x}' for x in f['lista']), f'## {f["h2_tv"]}', f['tv']]
    return '---\n' + '\n'.join(cab) + '\n---\n\n' + '\n\n'.join(bloques) + '\n'


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------

def modo_lista(semana):
    partidos = partidos_de_la_semana(semana)
    print(f'Semana {semana} de temporada regular ({len(partidos)} partidos), horarios del Este:\n')
    for p in sorted(partidos, key=lambda p: p['utc']):
        et = p['utc'].astimezone(ET)
        print(f'  {DIAS[et.weekday()][:3]} {et:%d/%m %H:%M} ET | {titulo_corto(p):<52} | {p["estadio"]} ({p["ciudad"]}) '
              f'| {"/".join(p["redes"]) or "sin cadena"}' + (' | SEDE NEUTRAL' if p['neutral'] else ''))


def ultimos(team_id):
    d = espn(f'teams/{team_id}/schedule?seasontype=2')
    out = []
    for e in d['events']:
        c = e['competitions'][0]
        if c['status']['type']['name'] != 'STATUS_FINAL':
            continue
        yo = [t for t in c['competitors'] if t['id'] == team_id][0]
        otro = [t for t in c['competitors'] if t['id'] != team_id][0]

        def pts(t):
            s = t.get('score')
            return int(float(s['value'])) if isinstance(s, dict) else int(float(s))
        out.append(f'Sem {e["week"]["number"]}: {"G" if yo.get("winner") else "P"} {pts(yo)}-{pts(otro)} '
                   f'{"vs" if yo["homeAway"] == "home" else "@"} {otro["team"]["displayName"]}')
    return out, d['team'].get('standingSummary')


def modo_ficha(texto, semana, tv, cadena=None, relatos=None):
    p = buscar_partido(partidos_de_la_semana(semana), texto)
    f = partes_fijas(p, tv, cadena, relatos)
    h = f['horarios']
    print(f'{f["titulo"]}\n')
    print(f'Semana {p["semana"]} | estado: {p["estado"]} | {"SEDE NEUTRAL | " if p["neutral"] else ""}'
          f'{p["estadio"]}' + (f' (ESPN: "{p["estadio_espn"]}", corregido)' if p['estadio'] != p['estadio_espn'] else '')
          + f', {h["lugar"]}')
    print(f'Puntapié: {h["et"]} ET | {h["local"]} hora local | ' + ' | '.join(f'{a} {hh}' for a, hh, _ in h['lista']))
    print(f'TV: {"/".join(p["redes"])} -> texto "{f["clave_tv"]}" ' + ('(confirmado)' if f['tv_confirmado'] else '(¡NO CONFIRMADO!)'))
    print('Relatos: ESPN no los informa y cambian por partido -> buscarlos (cuadro de asignaciones de la semana) y pasar "relatos:" en la nota.')
    for rol in ('local', 'visitante'):
        t = p[rol]
        res, pos = ultimos(t['id'])
        print(f'\n{rol.upper()}: {t["nombre"]} (récord {t["record"]}; {pos})')
        for r in res:
            print(f'   {r}')
    print('\nIntro fija:', f['intro'])
    print('Tags:', f['tags'])


def modo_nota(path, publicar, tv_sin_confirmar, actualizar=None):
    meta, cuerpo = leer_nota(path)
    semana = int(meta.get('semana') or semana_actual())
    if not meta.get('partido'):
        sys.exit(f'{path}: falta "partido:" (ej. Kansas City Chiefs @ Las Vegas Raiders).')
    p = buscar_partido(partidos_de_la_semana(semana), meta['partido'])
    f = partes_fijas(p, cargar_tv(), meta.get('cadena'), meta.get('relatos'), meta.get('latam'))
    if meta.get('tv_confirmado', '').lower() in ('si', 'sí', 'true', '1'):
        f['tv_confirmado'] = True  # el usuario aprobo ESTE parrafo de TV para ESTA nota
    video, video_desc = video_canal(meta.get('video'))
    md = armar_markdown(meta, cuerpo, f, os.path.dirname(os.path.abspath(path)), video)
    slug = re.sub(r'[^a-z0-9]+', '-', os.path.splitext(os.path.basename(path))[0].lower()).strip('-')
    os.makedirs(os.path.join(AQUI, 'salida'), exist_ok=True)
    destino = os.path.join(AQUI, 'salida', f'agenda-{slug}.md')
    open(destino, 'w', encoding='utf-8').write(md)

    h = f['horarios']
    print(f'Partido:  {titulo_corto(p)} | Semana {p["semana"]} | {p["estadio"]}, {h["lugar"]}')
    print(f'Horarios: {h["et"]} ET | {h["local"]} local | ' + ' | '.join(f'{a} {hh}' for a, hh, _ in h['lista']))
    print(f'TV:       {"/".join(p["redes"])} -> {f["clave_tv"]}' + ('' if f['tv_confirmado'] else '  ¡TEXTO NO CONFIRMADO!'))
    print(f'Video:    {video} ({video_desc})' if video else 'Video:    (ninguno)')
    if not meta.get('tweet'):
        print('AVISO: no hay "tweet:", la nota sale sin el embed de X.')
    if f['falta_relatos']:
        print('AVISO: no hay "relatos:"; la nota sale sin "con los relatos de …". Los relatores cambian por partido: '
              'buscalos en el cuadro de asignaciones de la semana (ej. awfulannouncing.com, "NFL Week N announcing schedule").')
    if p['estadio'] != p['estadio_espn']:
        print(f'AVISO: ESPN informa el estadio como "{p["estadio_espn"]}"; use "{p["estadio"]}".')
    print(f'Nota armada en {destino}\n')
    if not f['tv_confirmado'] and (publicar or actualizar) and not tv_sin_confirmar:
        sys.exit(f'No publico: el texto de TV de {f["clave_tv"]} no esta confirmado en agenda_tv.json. '
                 'Revisalo (y pone "confirmado": true) o usa --tv-sin-confirmar.')
    if publicar or actualizar:
        print('RECORDATORIO: en el editor de WordPress falta marcar a mano (la API del sitio no deja escribirlos): '
              'Post template = NFL y Categoria principal (Yoast) = Agenda.', flush=True)
    cmd = [sys.executable, os.path.join(AQUI, 'publicar_nota.py'), destino]
    if actualizar:
        cmd += ['--actualizar', str(actualizar)]
    elif publicar:
        cmd += ['--publicar']
    sys.exit(subprocess.call(cmd))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('nota', nargs='?', help='Archivo .md con la parte redactada (ver ayuda)')
    ap.add_argument('--lista', action='store_true', help='Lista los partidos de la semana')
    ap.add_argument('--ficha', metavar='PARTIDO', help='Datos duros de un partido para redactar')
    ap.add_argument('--semana', type=int, help='Semana de temporada regular (default: la actual)')
    ap.add_argument('--cadena', help='Pisa la cadena de EEUU que informa ESPN (en --ficha)')
    ap.add_argument('--publicar', action='store_true', help='Crea el borrador en WordPress')
    ap.add_argument('--actualizar', type=int, metavar='ID',
                    help='Reescribe un borrador ya creado (en vez de crear uno nuevo)')
    ap.add_argument('--tv-sin-confirmar', action='store_true',
                    help='Permite publicar con un texto de TV no confirmado')
    a = ap.parse_args()
    tv = cargar_tv()
    if a.lista:
        modo_lista(a.semana or semana_actual())
    elif a.ficha:
        modo_ficha(a.ficha, a.semana or semana_actual(), tv, a.cadena)
    elif a.nota:
        modo_nota(a.nota, a.publicar, a.tv_sin_confirmar, a.actualizar)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
