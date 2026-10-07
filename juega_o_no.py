#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
juega_o_no.py — notas "¿Juega o no X HOY en A vs B, por la Semana N de la NFL?" de
nohuddle.com.ar (temporada regular, categoria Agenda).

La eleccion del jugador pasa por el REPORTE DE LESIONES de ESPN: el script lista a
los jugadores que figuran Questionable / Doubtful / Out en partidos que todavia no
se jugaron, arma lo fijo de la nota (titulo, categoria, tags, Yoast) y valida que
la respuesta de la nota (si / no / duda) no contradiga el estado oficial. La parte
redactada (primer parrafo con la respuesta en negrita, contexto, subtitulo y cierre)
viene de un archivo escrito aparte; despues reusa publicar_nota.py para dejar el
BORRADOR en WordPress.

Solo usa la stdlib. Credenciales de WP en .env (como publicar_nota.py).

USO
    python3 juega_o_no.py --candidatos [--semana 5] [--posiciones QB,RB,WR,TE] [--todos]
        Jugadores del reporte de lesiones (Questionable/Doubtful/Out) de los partidos
        que faltan jugar. Por defecto solo QB; --posiciones o --todos amplian.

    python3 juega_o_no.py --ficha "Patrick Mahomes" [--semana 5]
        Datos duros para redactar: estado oficial, tipo de lesion, comentarios del
        reporte, partido (dia, hora, estadio, cadena), HC y resultados recientes.

    python3 juega_o_no.py notas/juega/semana-04-mahomes.md
        Simula (genera salida/juega-<slug>.md y el HTML; no sube nada).
    python3 juega_o_no.py notas/juega/semana-04-mahomes.md --publicar
        Crea el borrador en WordPress  (--actualizar ID reescribe uno existente).

ARCHIVO DE LA NOTA (lo redacta Claude; ver la skill armar-juega-o-no)
    ---
    semana: 4
    jugador: Patrick Mahomes
    respuesta: si            (si | no | duda: lo que dice la nota; se chequea contra ESPN)
    extracto: ...            (1 linea que resume la noticia)
    metadesc: ...            (descripcion Yoast)
    focuskw: ...             (opcional; por defecto "juega hoy <jugador>")
    tweet: https://x.com/...  (opcional: embed de X)
    destacada: media:8436    (foto del JUGADOR: media:ID, URL o archivo; se recorta SIEMPRE a 1820x715)
    destacada_pie: Foto: Getty Images
    linkear: Andy Reid       (figuras con tag existente a linkear sin sumarlas como tags)
    hc: Andy Reid            (opcional: pisa el HC de ESPN; "ninguno" = sin tag de HC)
    titulo: ...              (opcional: pisa el titulo)
    video: URL | ninguno     (opcional: por defecto va el ultimo video del canal de No Huddle
                             antes del primer subtitulo, como en las notas de partido)
    ---
    Primer parrafo con la respuesta en **negrita** (jugara HOY / no jugara HOY / es duda)...

    Parrafos de contexto...

    ## Subtitulo con gancho

    Parrafos...

REGLAS QUE YA ESTAN RESUELTAS (sacadas de 8081/8109 de 2026 y las de 2025)
    - Titulo: "¿Juega o no JUGADOR HOY en VISITANTE vs LOCAL, por la Semana N de la NFL?"
    - Categoria Agenda; tags = jugador + ambos equipos + NFL + HC del jugador.
    - Se publica el dia del partido.
"""
import argparse
import os
import re
import subprocess
import sys

import agenda_partido as ap

AQUI = os.path.dirname(os.path.abspath(__file__))
ESTADOS_OK = ('Questionable', 'Doubtful', 'Out')
ORDEN_POS = {'QB': 0, 'RB': 1, 'WR': 2, 'TE': 3}
# Estado oficial -> respuestas de la nota que NO se contradicen con el
VEREDICTO = {
    'Out': {'no'},
    'Doubtful': {'no', 'duda'},
    'Questionable': {'si', 'no', 'duda'},
    'Active': {'si'},
}


def sin_tildes(s):
    return (s.lower().replace('á', 'a').replace('é', 'e').replace('í', 'i')
            .replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n'))


def lesiones():
    """[(team_id, team_name, injury)] de todo el reporte de ESPN."""
    d = ap.espn('injuries')
    return [(t['id'], t['displayName'], i) for t in d['injuries'] for i in t['injuries']]


def pos_de(i):
    return (i['athlete'].get('position') or {}).get('abbreviation', '?')


def partido_de_equipo(partidos, team_id):
    for p in partidos:
        if team_id in (p['local']['id'], p['visitante']['id']):
            return p
    return None


def cuando(p):
    et = p['utc'].astimezone(ap.ET)
    return f'{ap.DIAS[et.weekday()][:3]} {et:%d/%m %H:%M} ET'


def modo_candidatos(semana, posiciones, todos):
    partidos = ap.partidos_de_la_semana(semana)
    pendientes = [p for p in partidos if p['estado'] == 'STATUS_SCHEDULED']
    filas = []
    for tid, tname, i in lesiones():
        if i['status'] not in ESTADOS_OK:
            continue
        pos = pos_de(i)
        if not todos and pos not in posiciones:
            continue
        p = partido_de_equipo(pendientes, tid)
        if not p:
            continue
        filas.append((p['utc'], ORDEN_POS.get(pos, 9), tname, i, pos, p))
    filas.sort(key=lambda f: (f[1], f[0], f[2]))
    pend = len(pendientes)
    print(f'Semana {semana}: {pend} partidos por jugar. Reporte de lesiones de ESPN '
          f'(Questionable/Doubtful/Out; posiciones: {"todas" if todos else ",".join(posiciones)}):\n')
    if not filas:
        print('  (ninguno)')
    for _, _, tname, i, pos, p in filas:
        det = (i.get('details') or {}).get('type') or '-'
        print(f'  {pos:<3} {i["athlete"]["displayName"]:<24} {i["status"]:<12} {det:<14} | {tname} | '
              f'{ap.titulo_corto(p)} | {cuando(p)}')
        print(f'      {(i.get("shortComment") or "")[:150]}')
    print('\nOrden: QB, RB, WR, TE, resto; dentro de cada grupo por horario del partido. '
          'ESPN no marca titulares: elegir a mano a quien importe. Out = No juega (nota "No, X no jugara HOY").')


def buscar_jugador(texto, partidos):
    """(injury|None, athlete_dict, team_id, team_name) por nombre, solo en equipos de partidos pendientes."""
    toks = [t for t in re.split(r'\s+', sin_tildes(texto)) if t]
    equipos = {}
    for p in partidos:
        for rol in ('local', 'visitante'):
            equipos[p[rol]['id']] = p[rol]['nombre']
    hits = []
    for tid, tname, i in lesiones():
        if tid in equipos and all(t in sin_tildes(i['athlete']['displayName']) for t in toks):
            hits.append((i, i['athlete'], tid, tname))
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        sys.exit('Varios jugadores coinciden: ' + ', '.join(h[1]['displayName'] for h in hits))
    # No figura en el reporte: buscarlo en los rosters (= sin restriccion oficial)
    for tid, tname in equipos.items():
        r = ap.espn(f'teams/{tid}/roster')
        for grupo in r['athletes']:
            for a in grupo['items']:
                if all(t in sin_tildes(a['displayName']) for t in toks):
                    return None, a, tid, tname
    sys.exit(f'No encontre a "{texto}" en los equipos de los partidos pendientes de la semana.')


def hc_de(team_id):
    c = (ap.espn(f'teams/{team_id}/roster').get('coach') or [{}])[0]
    return f'{c.get("firstName", "")} {c.get("lastName", "")}'.strip() or None


def contexto(texto, semana):
    partidos = ap.partidos_de_la_semana(semana)
    pend = [p for p in partidos if p['estado'] == 'STATUS_SCHEDULED']
    inj, atleta, tid, tname = buscar_jugador(texto, pend)
    p = partido_de_equipo(pend, tid)
    return partidos, inj, atleta, tid, tname, p


def etiqueta_dia(p):
    """'hoy'/'esta noche' no se puede saber: da el dia de la semana y la franja."""
    et = p['utc'].astimezone(ap.ET)
    franja = 'noche' if et.hour >= 20 else ('tarde' if et.hour >= 16 else 'mediodia')
    return f'{ap.DIAS[et.weekday()]} ({franja} en el Este)'


def modo_ficha(texto, semana):
    partidos, inj, atleta, tid, tname, p = contexto(texto, semana)
    rival = p['visitante'] if tid == p['local']['id'] else p['local']
    tipo = 'LOCAL' if tid == p['local']['id'] else 'VISITANTE'
    print(f'{atleta["displayName"]} ({pos_de(inj) if inj else (atleta.get("position") or {}).get("abbreviation", "?")}) '
          f'- {tname} ({tipo}) vs {rival["nombre"]}')
    print(f'Partido: Semana {p["semana"]} | {ap.titulo_corto(p)} | {cuando(p)} - {etiqueta_dia(p)} | '
          f'{p["estadio"]}, {ap.sede(p)[1]} | TV: {"/".join(p["redes"]) or "-"}')
    print(f'Titulo fijo: ¿Juega o no {atleta["displayName"]} HOY en {p["visitante"]["nombre"]} vs {p["local"]["nombre"]}, '
          f'por la Semana {p["semana"]} de la NFL?')
    print(f'HC de {tname}: {hc_de(tid)}  |  HC de {rival["nombre"]}: {hc_de(rival["id"])}')
    if inj:
        d = inj.get('details') or {}
        print(f'\nESTADO OFICIAL (ESPN): {inj["status"]} | lesion: {d.get("type")} ({d.get("location")}) '
              f'| actualizado {inj.get("date")} | regreso estimado: {d.get("returnDate") or "-"}')
        print(f'  Corto: {inj.get("shortComment")}')
        print(f'  Largo: {inj.get("longComment")}')
        print(f'  -> respuestas compatibles: {", ".join(sorted(VEREDICTO.get(inj["status"], {"?"})))}')
    else:
        print('\nESTADO OFICIAL (ESPN): no figura en el reporte de lesiones (sin restriccion oficial). '
              'Si la nota es por una duda previa, confirmar con el reporte del equipo / el HC.')
    for rol in ('local', 'visitante'):
        t = p[rol]
        res, pos = ap.ultimos(t['id'])
        print(f'\n{t["nombre"]} (record {t["record"]}; {pos})')
        for r in res:
            print(f'   {r}')
    otros = [(n, i) for t, n, i in lesiones() if t in (tid, rival['id']) and i['status'] in ESTADOS_OK
             and i['athlete']['displayName'] != atleta['displayName'] and pos_de(i) in ('QB', 'RB', 'WR', 'TE')]
    if otros:
        print('\nOtros skill players en el reporte de estos equipos:')
        for n, i in otros:
            print(f'   {n}: {i["athlete"]["displayName"]} ({pos_de(i)}) {i["status"]} - '
                  f'{(i.get("details") or {}).get("type")}')
    print('\nRECORDATORIO: ESPN trae lo oficial pero NO las declaraciones del HC ni el estado fresco del viernes/sabado: '
          'verificar en prensa (equipo, ESPN/NFL.com, Adam Schefter/Ian Rapoport) y cruzar fechas (las busquedas mezclan 2025).')


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
    cuerpo = txt[m.end():].strip()
    return meta, cuerpo


def modo_nota(path, publicar, actualizar):
    meta, cuerpo = leer_nota(path)
    for k in ('jugador', 'respuesta', 'extracto', 'metadesc'):
        if not meta.get(k):
            sys.exit(f'{path}: falta "{k}:" en el bloque de datos.')
    resp = sin_tildes(meta['respuesta'])
    if resp not in ('si', 'no', 'duda'):
        sys.exit('"respuesta:" debe ser si, no o duda.')
    semana = int(meta.get('semana') or ap.semana_actual())
    partidos = ap.partidos_de_la_semana(semana)
    # Se busca entre TODOS los partidos de la semana para poder avisar si ya se jugo
    inj, atleta, tid, tname, p = None, None, None, None, None
    try:
        _, inj, atleta, tid, tname, p = contexto(meta['jugador'], semana)
    except SystemExit:
        # quiza el partido ya empezo/termino: buscarlo igual para dar un aviso claro
        i2, a2, t2, n2 = buscar_jugador(meta['jugador'], partidos)
        sys.exit(f'AVISO: el partido de {a2["displayName"]} ya no esta pendiente (estado: '
                 f'{partido_de_equipo(partidos, t2)["estado"]}). No se arma la nota.')
    rival = p['visitante'] if tid == p['local']['id'] else p['local']
    jugador = atleta['displayName']
    titulo = meta.get('titulo') or (f'¿Juega o no {jugador} HOY en {p["visitante"]["nombre"]} vs '
                                    f'{p["local"]["nombre"]}, por la Semana {p["semana"]} de la NFL?')
    hc = meta.get('hc') if meta.get('hc') else hc_de(tid)
    tags = [jugador, p['visitante']['nombre'], p['local']['nombre'], 'NFL']
    if hc and sin_tildes(hc) not in ('ninguno', 'no', '-'):
        tags.append(hc)

    # Validaciones contra el estado oficial
    estado = inj['status'] if inj else 'Active'
    avisos = []
    if resp not in VEREDICTO.get(estado, {'si', 'no', 'duda'}):
        avisos.append(f'La nota dice "{resp}" pero ESPN lo tiene como {estado}. Si cambio el estado, verificar y '
                      'usar --ignorar-estado; si no, corregir la respuesta.')
    primer = cuerpo.split('\n\n', 1)[0]
    if '**' not in primer:
        avisos.append('El primer parrafo no tiene la respuesta en **negrita** (jugara HOY / no jugara HOY / ...).')
    if not re.search(r'\bHOY\b', primer):
        avisos.append('El primer parrafo no dice "HOY" (asi abren las notas publicadas).')
    if not meta.get('tweet') and not re.search(r'https?://(x|twitter)\.com/', cuerpo):
        avisos.append('No hay tweet: la nota sale sin el embed de X.')
    if not meta.get('destacada'):
        avisos.append('No hay "destacada:" (imagen).')
    if not re.search(r'^##\s', cuerpo, re.M):
        avisos.append('La nota no tiene ningun subtitulo (## ...).')

    cab = [f'titulo: {titulo}', 'categoria: Agenda', f'tags: {", ".join(tags)}',
           f'extracto: {meta["extracto"]}', f'metadesc: {meta["metadesc"]}',
           f'focuskw: {meta.get("focuskw") or "juega hoy " + jugador.lower()}']
    dest = meta.get('destacada', '')
    if dest and not re.match(r'(media:|https?://)', dest):
        dest = dest if os.path.isabs(dest) else os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(path)), dest))
    if dest:
        cab.append(f'destacada: {dest}')
    if meta.get('destacada_pie'):
        cab.append(f'destacada_pie: {meta["destacada_pie"]}')
    if meta.get('linkear'):
        cab.append(f'linkear: {meta["linkear"]}')
    bloques = cuerpo.split('\n\n')
    if meta.get('tweet'):
        # el embed va despues del tercer bloque de texto (como en 8081/8109), o al final del cuerpo corto
        pos = min(3, len(bloques))
        bloques.insert(pos, meta['tweet'])
    # Como en las notas de partido: el ultimo video del canal antes del primer subtitulo
    # (por defecto; 'video: URL' pisa la URL, 'video: ninguno' lo saca)
    video, video_desc = ap.video_canal(meta.get('video'))
    if video:
        idx = next((k for k, b in enumerate(bloques) if b.startswith('## ')), len(bloques))
        bloques.insert(idx, video)
    md = '---\n' + '\n'.join(cab) + '\n---\n\n' + '\n\n'.join(bloques) + '\n'

    slug = re.sub(r'[^a-z0-9]+', '-', os.path.splitext(os.path.basename(path))[0].lower()).strip('-')
    os.makedirs(os.path.join(AQUI, 'salida'), exist_ok=True)
    destino = os.path.join(AQUI, 'salida', f'juega-{slug}.md')
    open(destino, 'w', encoding='utf-8').write(md)

    print(f'Jugador:  {jugador} ({tname}) | estado ESPN: {estado} | respuesta de la nota: {resp}')
    print(f'Partido:  {ap.titulo_corto(p)} | Semana {p["semana"]} | {cuando(p)} | {p["estadio"]}')
    print(f'Titulo:   {titulo}')
    print(f'Tags:     {", ".join(tags)}')
    print(f'Video:    {video} ({video_desc})' if video else 'Video:    (ninguno)')
    for a in avisos:
        print(f'AVISO: {a}')
    print(f'Nota armada en {destino}\n')
    bloqueantes = [a for a in avisos if a.startswith('La nota dice')]
    if (publicar or actualizar) and bloqueantes and not ARGS.ignorar_estado:
        sys.exit('No publico: la respuesta de la nota contradice el estado oficial de ESPN (ver AVISO).')
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
    global ARGS
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument('nota', nargs='?', help='Archivo .md de la nota (ver ayuda)')
    a.add_argument('--candidatos', action='store_true', help='Jugadores del reporte de lesiones de la semana')
    a.add_argument('--ficha', metavar='JUGADOR', help='Datos duros de un jugador para redactar')
    a.add_argument('--semana', type=int, help='Semana de temporada regular (default: la actual)')
    a.add_argument('--posiciones', default='QB', help='Posiciones para --candidatos (default QB; ej. QB,RB,WR,TE)')
    a.add_argument('--todos', action='store_true', help='--candidatos con todas las posiciones')
    a.add_argument('--publicar', action='store_true', help='Crea el borrador en WordPress')
    a.add_argument('--actualizar', type=int, metavar='ID', help='Reescribe un borrador ya creado')
    a.add_argument('--ignorar-estado', action='store_true',
                   help='Publica aunque la respuesta de la nota no coincida con el estado de ESPN')
    ARGS = a.parse_args()
    semana = ARGS.semana or ap.semana_actual()
    if ARGS.candidatos:
        modo_candidatos(semana, [x.strip().upper() for x in ARGS.posiciones.split(',')], ARGS.todos)
    elif ARGS.ficha:
        modo_ficha(ARGS.ficha, semana)
    elif ARGS.nota:
        modo_nota(ARGS.nota, ARGS.publicar, ARGS.actualizar)
    else:
        a.print_help()


if __name__ == '__main__':
    main()
