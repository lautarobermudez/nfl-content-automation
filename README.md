# NFL content automation for a WordPress site

Scripts I use for [nohuddle.com.ar](https://nohuddle.com.ar), a Spanish-language NFL site. They build the repeatable parts of two kinds of service articles and upload them as **WordPress drafts** (nothing is published automatically):

- **Match agenda notes**: "A vs. B, Week N: time and how to watch the NFL on TV and streaming".
- **"Will X play today?" notes** for players listed on the injury report.

They also help choose topics by combining Search Console and GA4 signals.

> **Built with AI assistance** (Claude Code). I designed the workflow and the editorial rules and review every draft before it goes live. The prose of each note is written separately and then validated by these scripts.

## What is in here
| File | Purpose |
|---|---|
| `agenda_partido.py` | Pulls the schedule from ESPN's public endpoints, converts kick-off times to Argentina, Mexico and Spain, adds TV/streaming info (`agenda_tv.json`), builds title, tags, excerpt and Yoast data. |
| `juega_o_no.py` | Lists players with Questionable/Doubtful/Out status, builds the article skeleton and **checks the yes/no/doubt answer does not contradict the official status**. |
| `publicar_nota.py` | Markdown → WordPress block HTML (headings, captioned images, YouTube/X embeds, tag links, Yoast) and creates the draft through the WP REST API. Standard library only. |
| `buscar_media.py`, `foto_destacada.py` | Reuse images from the WP media library; crop/resize a featured image to 1820×715 with Pillow. |
| `ultimo_video.py` | Latest non-Shorts video from the channel's public RSS feed (no API key). |
| `fetch_signals.py` | Search Console + GA4 numbers for candidate topics. |

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env                    # WP_URL, WP_USER, WP_APP_PASSWORD
cp config.example.json config.json      # Search Console site and GA4 property
```
Use a WordPress **application password**, not your login password. `token.json`, `client_secret.json`, `.env` and `config.json` are git-ignored.

Dry-run is the default; add `--publicar` to create the draft:
```bash
python agenda_partido.py --lista --semana 5
python agenda_partido.py notas/agenda/semana-05-example.md            # simulate
python agenda_partido.py notas/agenda/semana-05-example.md --publicar # create draft
```

## Not included
The articles, photos and topic log are not published here. The Google OAuth helper scripts are omitted.

## Known limitations
- Spanish code and comments; tied to the site's editorial template.
- Depends on ESPN endpoints that are not an official API and may change.
- No tests yet.
