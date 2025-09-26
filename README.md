# YouTube Upload Bot

Acest repo conține un script gata de folosit pentru a urca videoclipuri pe YouTube folosind YouTube Data API v3 cu OAuth 2.0.

Important: YouTube/Google nu permit autentificarea cu user/parolă pentru upload via API. Îți trebuie un client OAuth (fișier JSON) și o autorizare unică în contul tău. După această autorizare, scriptul folosește tokenul de refresh și nu-ți mai cere login.

## Setup

1) Creează un proiect Google Cloud și activează YouTube Data API v3.
2) Configurează OAuth consent screen (External/Internal) și adaugă scope: `https://www.googleapis.com/auth/youtube.upload`.
3) Creează OAuth Client ID de tip „Desktop app”.
4) Descarcă fișierul `client_secret.json` și pune-l în rădăcina proiectului (sau folosește `--client-secrets path`).

Instalare dependențe:
- Python 3.9+
- pip install -r requirements.txt

```
pip install -r requirements.txt
```

## Utilizare

Comandă de bază (va deschide un browser la prima rulare pentru autorizare, sau îți va afișa un cod de introdus):

```
python upload_youtube.py \
  --file example.mp4 \
  --title "Titlul meu" \
  --description "Descriere" \
  --tags "tag1,tag2" \
  --privacy unlisted
```

După prima autorizare, se salvează tokenul în `token_youtube_upload.pickle` și nu mai e nevoie de login.

### Opțiuni

- `--file` Calea către fișierul video (obligatoriu).
- `--title` Titlul video (obligatoriu).
- `--description` Descrierea.
- `--tags` CSV sau JSON array, ex: `"tag1,tag2"` sau `"[\"tag1\",\"tag2\"]"`.
- `--category-id` Implicit `22` (People & Blogs).
- `--privacy` `public|unlisted|private` (implicit `unlisted`).
- `--thumbnail` Calea către imagine thumbnail.
- `--playlist-id` Adaugă video în playlistul dat după upload.
- `--publish-at` Programează publicarea. Acceptă formate gen `2025-01-31 14:30` (ora locală) sau RFC3339 (ex: `2025-01-31T12:30:00Z`). Pentru scheduled, YouTube necesită `privacy=private` (scriptul setează automat dacă e nevoie).
- `--made-for-kids` Marchează video „made for kids”.
- `--metadata` YAML/JSON cu aceleași chei ca argumentele. Valorile din fișier suprascriu/completează argumentele CLI.
- `--client-secrets` Calea către fișierul OAuth client (altfel folosește `client_secret.json` sau env `YT_CLIENT_SECRETS`).
- `--token-file` Calea fișierului token (altfel `token_youtube_upload.pickle` sau env `YT_TOKEN_FILE`).

Exemplu YAML (metadata.yaml):

```yaml
file: example.mp4
title: Titlu din YAML
description: Descriere din YAML
tags: ["exemplu", "upload", "yt"]
category_id: "22"
privacy: private
thumbnail: thumb.jpg
playlist_id: PLxxxxxxx
publish_at: "2025-01-31 14:30"
made_for_kids: false
```

Rulare cu metadata:
```
python upload_youtube.py --metadata metadata.yaml
```

## Notă despre „date de logare”

Google nu permite folosirea user/parolă pentru API. Ceea ce îți putem cere în mod sigur este fișierul `client_secret.json` (OAuth client) al proiectului tău. La prima rulare se va cere autorizarea contului tău YouTube (browser sau cod dispozitiv în consolă). După aceea, tokenul de refresh păstrează accesul și uploadurile pot fi complet automate.

Dacă vrei, îmi poți furniza fișierul `client_secret.json`, iar eu mă ocup de configurare și îți livrez un flux în care doar pui fișierele video și scriptul le urcă după regulile tale.