import os
import time
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

SPOTIFY_ACCOUNTS_BASE_URL = "https://accounts.spotify.com"
SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"
SPOTIFY_PLAYLIST_ITEMS_PARSER = "playlist-items-item-v3"


def _json_or_error(response, label):
    try:
        return response.json()
    except ValueError:
        preview = response.text[:300].strip() or "<empty response>"
        raise Exception(
            f"{label} returned non-JSON response "
            f"(status {response.status_code}): {preview}"
        )


def _spotify_request(method, url, headers, label, **kwargs):
    max_attempts = 4

    for attempt in range(max_attempts):
        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=30,
            **kwargs,
        )
        data = _json_or_error(response, label)

        if response.status_code == 429 and attempt < max_attempts - 1:
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                delay = int(retry_after)
            else:
                delay = min(2**attempt, 8)
            time.sleep(delay)
            continue

        if response.status_code >= 400:
            spotify_error = data.get("error") if isinstance(data, dict) else None
            message = (
                spotify_error.get("message")
                if isinstance(spotify_error, dict)
                else str(data)
            )
            if response.status_code == 401:
                raise Exception(
                    f"{label} returned 401 Unauthorized: {message}. "
                    "Check the Spotify OAuth refresh token or app credentials."
                )
            if response.status_code == 403:
                raise Exception(
                    f"{label} returned 403 Forbidden: {message}. Spotify's "
                    "OpenAPI schema says this playlist items endpoint requires "
                    "the current user to be the playlist owner or collaborator. "
                    "Use a user OAuth refresh token for an account that can edit "
                    "or collaborate on this playlist."
                )
            if response.status_code == 429:
                raise Exception(
                    f"{label} returned 429 Too Many Requests after retries: "
                    f"{message}"
                )
            raise Exception(
                f"{label} failed with status {response.status_code}: {message}"
            )

        return data

    raise Exception(f"{label} failed after too many retries")


def _spotify_get(url, headers, label):
    return _spotify_request("GET", url, headers, label)


def _post_spotify_token(data, label, client_id, client_secret):
    response = requests.post(
        f"{SPOTIFY_ACCOUNTS_BASE_URL}/api/token",
        auth=(client_id, client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=data,
        timeout=30,
    )
    data = _json_or_error(response, label)
    if response.status_code != 200:
        spotify_error = data.get("error_description") or data.get("error") or data
        if label == "Spotify refresh token endpoint" and "Invalid refresh token" in str(spotify_error):
            raise Exception(
                "Spotify refresh token is invalid. Generate a new refresh token "
                "with the same Spotify Developer app used by "
                "SPOTIPY_CLIENT_ID/SPOTIPY_CLIENT_SECRET. Do not use a BQ... "
                "access token from the Spotify test console."
            )
        raise Exception(
            f"{label} failed with status {response.status_code}: {spotify_error}"
        )
    return data


def get_spotify_access_token(client_id, client_secret):
    if not client_id or not client_secret:
        raise Exception("Missing SPOTIPY_CLIENT_ID or SPOTIPY_CLIENT_SECRET")

    refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
    if refresh_token:
        data = _post_spotify_token(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            "Spotify refresh token endpoint",
            client_id,
            client_secret,
        )
        return data["access_token"]

    data = _post_spotify_token(
        {
            "grant_type": "client_credentials",
        },
        "Spotify client credentials token endpoint",
        client_id,
        client_secret,
    )
    return data["access_token"]


def extract_playlist_id(playlist_url):
    playlist_url = (playlist_url or "").strip()
    if playlist_url.startswith("spotify:playlist:"):
        return playlist_url.split(":")[-1]

    parsed = urlparse(playlist_url)
    if parsed.path.startswith("/playlist/"):
        return parsed.path.split("/playlist/", 1)[1].split("/", 1)[0]

    if "/playlist/" not in playlist_url:
        raise Exception("Invalid Spotify playlist URL")
    return playlist_url.split("/playlist/")[1].split("?")[0].split("&")[0]


def get_all_tracks(link, market):
    playlist_id = extract_playlist_id(link)
    market = os.getenv("SPOTIFY_MARKET", market or "IT")
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    access_token = get_spotify_access_token(client_id, client_secret)

    url = (
        f"{SPOTIFY_API_BASE_URL}/playlists/{playlist_id}/items"
        "?fields=items(is_local,item(type,name,artists(name),album(name)),track(type,name,artists(name),album(name))),next"
        f"&market={market}&limit=50&additional_types=track"
    )
    headers = {"Authorization": f"Bearer {access_token}"}

    all_tracks = []
    skipped = {
        "missing_item": 0,
        "non_track": 0,
        "local": 0,
        "missing_metadata": 0,
    }
    while url:
        data = _spotify_get(url, headers, "Spotify playlist items endpoint")
        for item in data.get("items", []):
            track = item.get("item") or item.get("track")
            if not track:
                skipped["missing_item"] += 1
                continue
            if item.get("is_local"):
                skipped["local"] += 1
                continue
            if track.get("type") and track.get("type") != "track":
                skipped["non_track"] += 1
                continue

            name = track.get("name")
            artists = [
                artist.get("name")
                for artist in track.get("artists", [])
                if artist.get("name")
            ]
            album = track.get("album", {}).get("name")
            if not name or not artists:
                skipped["missing_metadata"] += 1
                continue

            all_tracks.append(
                {
                    "name": name,
                    "artists": artists,
                    "album": album,
                }
            )
        url = data.get("next")

    if not all_tracks:
        raise Exception(
            "No Spotify tracks with usable metadata found "
            f"(parser={SPOTIFY_PLAYLIST_ITEMS_PARSER}). "
            f"Skipped counts: missing_item={skipped['missing_item']}, "
            f"non_track={skipped['non_track']}, "
            f"local={skipped['local']}, "
            f"missing_metadata={skipped['missing_metadata']}."
        )
    return all_tracks


def get_playlist_details(link):
    playlist_id = extract_playlist_id(link)
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    access_token = get_spotify_access_token(client_id, client_secret)

    data = _spotify_get(
        f"{SPOTIFY_API_BASE_URL}/playlists/{playlist_id}",
        {"Authorization": f"Bearer {access_token}"},
        "Spotify playlist endpoint",
    )
    return {
        "name": data["name"],
    }


def get_playlist_name(link):
    return get_playlist_details(link)["name"]
