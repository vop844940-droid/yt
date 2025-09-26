import argparse
import datetime as dt
import json
import os
import pickle
import sys
from typing import List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from tqdm import tqdm

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]
CLIENT_SECRETS_FILE = os.environ.get("YT_CLIENT_SECRETS", "client_secret.json")
TOKEN_FILE = os.environ.get("YT_TOKEN_FILE", "token_youtube_upload.pickle")


def _load_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            return pickle.load(f)
    return None


def _save_token(creds):
    with open(TOKEN_FILE, "wb") as f:
        pickle.dump(creds, f)


def get_service():
    creds = _load_token()
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
        except Exception:
            creds = None

    if not creds or not getattr(creds, "valid", False):
        if creds and getattr(creds, "expired", False) and getattr(creds, "refresh_token", None):
            creds.refresh(Request())
            _save_token(creds)
        else:
            if not os.path.exists(CLIENT_SECRETS_FILE):
                raise FileNotFoundError(
                    f"Missing {CLIENT_SECRETS_FILE}. Download your OAuth client JSON "
                    f"from Google Cloud Console (YouTube Data API v3 enabled)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            try:
                # Tries to open a browser. If not possible, falls back to console flow.
                creds = flow.run_local_server(port=0, prompt="consent")
            except Exception:
                creds = flow.run_console()
            _save_token(creds)

    return build("youtube", "v3", credentials=creds)


def _parse_tags(tags_str: Optional[str]) -> List[str]:
    if not tags_str:
        return []
    # Support CSV or JSON list
    try:
        data = json.loads(tags_str)
        if isinstance(data, list):
            return [str(x) for x in data]
    except json.JSONDecodeError:
        pass
    return [t.strip() for t in tags_str.split(",") if t.strip()]


def _parse_publish_at(publish_at: Optional[str]) -> Optional[str]:
    if not publish_at:
        return None
    # Accept: "2025-01-31 14:30", "2025-01-31T14:30:00Z", or full RFC3339
    s = publish_at.strip()
    try:
        if s.endswith("Z"):
            # Already UTC RFC3339-ish
            dt_obj = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt_obj.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        if "T" in s:
            dt_obj = dt.datetime.fromisoformat(s)
        else:
            # assume local time without tz
            dt_obj = dt.datetime.fromisoformat(s)
        # Treat naive dt as local time; convert to UTC
        if dt_obj.tzinfo is None:
            dt_obj = dt_obj.astimezone()  # local tz
        return dt_obj.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        raise ValueError(
            "publish_at format invalid. Use 'YYYY-MM-DD HH:MM' (local), "
            "'YYYY-MM-DDTHH:MM:SS' with timezone, or RFC3339 '...Z'."
        )


def upload_video(
    file_path: str,
    title: str,
    description: str = "",
    tags: Optional[List[str]] = None,
    category_id: str = "22",
    privacy_status: str = "unlisted",
    thumbnail_path: Optional[str] = None,
    playlist_id: Optional[str] = None,
    publish_at: Optional[str] = None,
    made_for_kids: Optional[bool] = None,
) -> str:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Video file not found: {file_path}")

    service = get_service()

    status = {"privacyStatus": privacy_status}
    if publish_at:
        status["publishAt"] = publish_at
        # YouTube requires private for scheduled publish
        if privacy_status != "private":
            status["privacyStatus"] = "private"

    if made_for_kids is not None:
        status["madeForKids"] = bool(made_for_kids)

    body = {
        "snippet": {
            "title": title,
            "description": description or "",
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": status,
    }

    media = MediaFileUpload(
        file_path, chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/*"
    )

    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    pbar = tqdm(total=100, desc="Uploading", unit="%")
    last_progress = 0
    try:
        while response is None:
            status_chunk, response = request.next_chunk()
            if status_chunk:
                progress = int(status_chunk.progress() * 100)
                if progress > last_progress:
                    pbar.update(progress - last_progress)
                    last_progress = progress
        if "id" not in response:
            raise RuntimeError(f"Unexpected upload response: {response}")
    finally:
        pbar.close()

    video_id = response["id"]

    if thumbnail_path and os.path.exists(thumbnail_path):
        service.thumbnails().set(videoId=video_id, media_body=thumbnail_path).execute()

    if playlist_id:
        service.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()

    return video_id


def load_metadata(path: str) -> dict:
    import yaml  # lazy import

    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8") as f:
        if path.lower().endswith(".json"):
            return json.load(f)
        return yaml.safe_load(f)


def main(argv=None):
    parser = argparse.ArgumentParser(description="YouTube upload bot (OAuth-based)")
    parser.add_argument("--file", required=False, help="Path to video file")
    parser.add_argument("--title", required=False, help="Video title")
    parser.add_argument("--description", default="", help="Video description")
    parser.add_argument("--tags", default="", help="CSV or JSON array of tags")
    parser.add_argument("--category-id", default="22", help="YouTube categoryId (default 22)")
    parser.add_argument("--privacy", default="unlisted", choices=["public", "unlisted", "private"])
    parser.add_argument("--thumbnail", help="Path to thumbnail image")
    parser.add_argument("--playlist-id", help="Playlist ID to add the video to")
    parser.add_argument("--publish-at", help="Schedule publish time (e.g., '2025-01-31 14:30' local)")
    parser.add_argument("--made-for-kids", action="store_true", help="Mark as made for kids")
    parser.add_argument("--metadata", help="YAML/JSON file with fields to override flags")
    parser.add_argument("--client-secrets", help="Path to OAuth client JSON; else env YT_CLIENT_SECRETS or client_secret.json")
    parser.add_argument("--token-file", help="Where to store OAuth token; else env YT_TOKEN_FILE or token_youtube_upload.pickle")

    args = parser.parse_args(argv)

    global CLIENT_SECRETS_FILE, TOKEN_FILE
    if args.client_secrets:
        CLIENT_SECRETS_FILE = args.client_secrets
    if args.token_file:
        TOKEN_FILE = args.token_file

    meta = {}
    if args.metadata:
        meta = load_metadata(args.metadata) or {}

    def pick(name, default=None):
        return meta.get(name, getattr(args, name, default) if hasattr(args, name) else default)

    file_path = pick("file")
    title = pick("title")
    description = pick("description", "")
    tags = _parse_tags(pick("tags", ""))
    category_id = str(pick("category_id", "22"))
    privacy_status = pick("privacy", "unlisted")
    thumbnail_path = pick("thumbnail")
    playlist_id = pick("playlist_id")
    publish_at_input = pick("publish_at")
    made_for_kids = bool(meta.get("made_for_kids", args.made_for_kids))

    if not file_path or not title:
        print("Missing required --file and --title (or provide them via --metadata).", file=sys.stderr)
        sys.exit(2)

    publish_at = _parse_publish_at(publish_at_input) if publish_at_input else None

    try:
        video_id = upload_video(
            file_path=file_path,
            title=title,
            description=description or "",
            tags=tags,
            category_id=category_id,
            privacy_status=privacy_status,
            thumbnail_path=thumbnail_path,
            playlist_id=playlist_id,
            publish_at=publish_at,
            made_for_kids=made_for_kids,
        )
    except HttpError as e:
        print(f"YouTube API error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Uploaded video ID: {video_id}")


if __name__ == "__main__":
    main()