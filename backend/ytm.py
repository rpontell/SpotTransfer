import re
import os
import unicodedata
import time
import tempfile
from collections import Counter
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from anyascii import anyascii
from pykakasi import kakasi
from ytmusicapi import YTMusic
import ytmusicapi
from spotify import get_all_tracks, get_playlist_details


MIN_MATCH_SCORE = float(os.getenv("YTMUSIC_MIN_MATCH_SCORE", "0.70"))
YTMUSIC_SEARCH_DELAY_SECONDS = float(os.getenv("YTMUSIC_SEARCH_DELAY_SECONDS", "0.75"))
YTMUSIC_TRANSIENT_ERROR_COOLDOWN_SECONDS = float(
    os.getenv("YTMUSIC_TRANSIENT_ERROR_COOLDOWN_SECONDS", "8")
)
YTMUSIC_IMMEDIATE_RETRY_PASSES = int(os.getenv("YTMUSIC_IMMEDIATE_RETRY_PASSES", "1"))
YTMUSIC_IMMEDIATE_RETRY_COOLDOWN_SECONDS = float(
    os.getenv("YTMUSIC_IMMEDIATE_RETRY_COOLDOWN_SECONDS", "12")
)
YTMUSIC_FINAL_RETRY_PASSES = int(os.getenv("YTMUSIC_FINAL_RETRY_PASSES", "2"))
YTMUSIC_FINAL_RETRY_COOLDOWN_SECONDS = float(
    os.getenv("YTMUSIC_FINAL_RETRY_COOLDOWN_SECONDS", "20")
)
YTMUSIC_LAST_CHANCE_RETRY_PASSES = int(
    os.getenv("YTMUSIC_LAST_CHANCE_RETRY_PASSES", "1")
)
YTMUSIC_LAST_CHANCE_RETRY_COOLDOWN_SECONDS = float(
    os.getenv("YTMUSIC_LAST_CHANCE_RETRY_COOLDOWN_SECONDS", "60")
)
YTMUSIC_PLAYLIST_ADD_CHUNK_SIZE = int(
    os.getenv("YTMUSIC_PLAYLIST_ADD_CHUNK_SIZE", "50")
)
YTMUSIC_PLAYLIST_ADD_RETRIES = int(
    os.getenv("YTMUSIC_PLAYLIST_ADD_RETRIES", "5")
)
YTMUSIC_PLAYLIST_ADD_RETRY_COOLDOWN_SECONDS = float(
    os.getenv("YTMUSIC_PLAYLIST_ADD_RETRY_COOLDOWN_SECONDS", "10")
)
YTMUSIC_SEARCH_RETRIES = int(os.getenv("YTMUSIC_SEARCH_RETRIES", "3"))
YTMUSIC_SEARCH_FILTERS = [
    search_filter.strip()
    for search_filter in os.getenv("YTMUSIC_SEARCH_FILTERS", "songs,videos").split(",")
    if search_filter.strip()
]
SKIPPED_YTMUSIC_HEADERS = {
    "accept-encoding",
    "connection",
    "content-encoding",
    "content-length",
    "host",
    "priority",
}
JAPANESE_TRANSLITERATOR = kakasi()
JAPANESE_CHARACTER_PATTERN = re.compile(
    "[\\u3040-\\u30ff\\u3400-\\u4dbf\\u4e00-\\u9fff]"
)


def parse_headers(headers_text):
    """
    Convert headers from plain text format to proper HTTP header format.
    Supports both formats:
    - Standard format: "header: value"
    - Plain format: "header\nvalue\nheader2\nvalue2"
    """
    if not headers_text or not headers_text.strip():
        raise Exception("YouTube Music auth headers cannot be empty")

    lines = [line.strip() for line in headers_text.strip().split("\n") if line.strip()]
    first_line = lines[0] if lines else ""
    colon_pos = first_line.find(": ")

    if colon_pos > 0 and colon_pos < 50:
        filtered_lines = []
        for line in lines:
            header_name = line.split(":", 1)[0].strip().lower()
            if header_name in SKIPPED_YTMUSIC_HEADERS:
                continue
            filtered_lines.append(line)
        return "\n".join(filtered_lines)

    cleaned_lines = []
    skip_mode = False

    for line in lines:
        if line == "Decoded:":
            skip_mode = True
            continue

        if skip_mode:
            if (
                line.startswith("message ")
                or line.startswith("//")
                or line.startswith("repeated ")
                or line == "}"
                or line.startswith("int32 ")
                or "{" in line
            ):
                continue
            skip_mode = False

        cleaned_lines.append(line)

    lines = cleaned_lines

    if len(lines) % 2 != 0:
        last_line = lines[-1] if lines else "none"
        raise Exception(
            "Invalid YouTube Music headers format. Each header name must have "
            f"a corresponding value. Got {len(lines)} lines. Last line: '{last_line}'"
        )

    formatted_headers = []
    for i in range(0, len(lines), 2):
        header_name = lines[i].strip()
        header_value = lines[i + 1].strip()
        if header_name.lower() in SKIPPED_YTMUSIC_HEADERS:
            continue
        formatted_headers.append(f"{header_name}: {header_value}")

    parsed_header_names = [
        line.split(":", 1)[0].strip().lower()
        for line in formatted_headers
        if ":" in line
    ]
    safe_header_names = [
        name
        for name in parsed_header_names
        if name not in {"authorization", "cookie"}
    ]
    print(f"YouTube Music headers parsed: {', '.join(safe_header_names)}")
    return "\n".join(formatted_headers)


def _is_youtube_auth_error(error):
    message = str(error).lower()
    return (
        "401" in message
        or "unauthorized" in message
        or "must be signed in" in message
        or "sign in" in message
    )


def _raise_youtube_error(action, error):
    if _is_youtube_auth_error(error):
        raise Exception(
            "YouTube Music authentication failed while "
            f"{action}. Regenerate fresh request headers from a signed-in "
            "music.youtube.com POST /browse request with status 200, then paste "
            "the new headers and retry."
        )
    raise Exception(f"YouTube Music failed while {action}: {error}")


def _normalize_text(value):
    value = unicodedata.normalize("NFKC", value or "")
    value = (value or "").lower()
    value = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", value)
    value = re.sub(
        r"\b(feat|ft|featuring|prod|remaster|remastered|radio edit)\b",
        " ",
        value,
    )
    value = "".join(
        char if char.isalnum() else " "
        for char in value
    )
    return " ".join(value.split())


@lru_cache(maxsize=2048)
def _romanize_japanese(value):
    if not value:
        return ""
    if not JAPANESE_CHARACTER_PATTERN.search(value):
        return value
    romanized = " ".join(
        item.get("hepburn", item.get("orig", ""))
        for item in JAPANESE_TRANSLITERATOR.convert(value)
    )
    return re.sub(r"\s+([^\w\s])", r"\1", romanized)


@lru_cache(maxsize=2048)
def _transliterate_unicode(value):
    return anyascii(value or "")


def _transliteration_variants(value):
    candidates = [value]
    if value and any(not char.isascii() for char in value):
        if JAPANESE_CHARACTER_PATTERN.search(value):
            candidates.append(_romanize_japanese(value))
        else:
            candidates.append(_transliterate_unicode(value))

    variants = []
    for candidate in candidates:
        candidate = " ".join((candidate or "").split())
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants


def _text_variants(value):
    variants = []
    for candidate in _transliteration_variants(value):
        normalized = _normalize_text(candidate)
        if normalized and normalized not in variants:
            variants.append(normalized)
    return variants


def _similarity(left, right):
    left_variants = _text_variants(left)
    right_variants = _text_variants(right)
    if not left_variants or not right_variants:
        return 0

    best_score = 0
    for left_variant in left_variants:
        for right_variant in right_variants:
            if left_variant == right_variant:
                return 1
            if left_variant in right_variant or right_variant in left_variant:
                best_score = max(best_score, 0.9)
            else:
                best_score = max(
                    best_score,
                    SequenceMatcher(None, left_variant, right_variant).ratio(),
                )
    return best_score


def _result_artists(result):
    artists = result.get("artists") or []
    if not artists and result.get("artist"):
        artists = [result.get("artist")]
    return [
        artist.get("name") if isinstance(artist, dict) else str(artist)
        for artist in artists
        if (isinstance(artist, dict) and artist.get("name")) or isinstance(artist, str)
    ]


def _score_result(track, result):
    title_score = _similarity(track["name"], result.get("title"))
    source_artists = track.get("artists") or []
    result_artists = _result_artists(result)

    artist_score = 0
    for source_artist in source_artists:
        for result_artist in result_artists:
            artist_score = max(artist_score, _similarity(source_artist, result_artist))

    album_score = 0
    if track.get("album") and result.get("album"):
        album = result["album"]
        album_name = album.get("name") if isinstance(album, dict) else str(album)
        album_score = _similarity(track["album"], album_name)

    return (title_score * 0.55) + (artist_score * 0.4) + (album_score * 0.05)


def _best_search_result(track, results):
    candidates = [
        result
        for result in results
        if result.get("videoId") and result.get("title")
    ]
    if not candidates:
        return None, 0

    scored = [(_score_result(track, result), result) for result in candidates]
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1], scored[0][0]


def _is_transient_youtube_error(error):
    message = str(error).lower()
    return (
        "expecting value" in message
        or "line 1 column 1" in message
        or "read timed out" in message
        or "read timeout" in message
        or "connection reset" in message
        or "connection aborted" in message
        or "429" in message
        or "too many requests" in message
        or "temporarily" in message
    )


def _is_ytmusic_parser_error(error):
    message = str(error).lower()
    return (
        "unable to find" in message
        or "using path" in message
        or "keyerror" in type(error).__name__.lower()
    )


def _is_retryable_youtube_error(error):
    return _is_transient_youtube_error(error) or _is_ytmusic_parser_error(error)


def _ytmusic_search(ytmusic, query, filter_name):
    last_error = None
    for attempt in range(YTMUSIC_SEARCH_RETRIES):
        try:
            return ytmusic.search(query, filter=filter_name)
        except Exception as error:
            last_error = error
            if _is_youtube_auth_error(error):
                raise
            if _is_ytmusic_parser_error(error):
                print(
                    f"Skipping YouTube Music parser error for "
                    f"{filter_name} query '{query}': {error}"
                )
                return []
            if not _is_transient_youtube_error(error) or attempt == YTMUSIC_SEARCH_RETRIES - 1:
                raise
            time.sleep(min(2**attempt, 8))
    raise last_error


def _dedupe_results(results):
    seen = set()
    deduped = []
    for result in results:
        video_id = result.get("videoId")
        key = video_id or f"{result.get('title')}|{_result_artists(result)}"
        if key in seen:
            continue
        deduped.append(result)
        seen.add(key)
    return deduped


def _search_queries(track):
    name = track["name"]
    artists = track.get("artists") or []
    primary_artist = artists[0] if artists else ""
    album = track.get("album")

    name_variants = _transliteration_variants(name)
    artist_variants = _transliteration_variants(primary_artist)

    queries = []
    for name_variant in name_variants:
        for artist_variant in artist_variants:
            queries.extend(
                [
                    f"{name_variant} {artist_variant}",
                    f'"{name_variant}" "{artist_variant}"',
                    f"{artist_variant} {name_variant}",
                ]
            )
        queries.append(name_variant)
    for artist_variant in artist_variants:
        queries.append(f"{name} {artist_variant} topic")
    if album:
        queries.append(f"{name} {primary_artist} {album}")

    seen = set()
    unique_queries = []
    for query in queries:
        normalized = " ".join(query.split())
        if normalized and normalized not in seen:
            unique_queries.append(normalized)
            seen.add(normalized)
    return unique_queries


def _track_label(track):
    artists = track.get("artists") or []
    primary_artist = artists[0] if artists else ""
    return f"{track['name']} {primary_artist}".strip()


def _find_video_id_for_track(ytmusic, track):
    best_result = None
    score = 0
    search_results = []
    for search_filter in YTMUSIC_SEARCH_FILTERS:
        for query in _search_queries(track):
            search_results.extend(_ytmusic_search(ytmusic, query, search_filter))
            best_result, score = _best_search_result(
                track,
                _dedupe_results(search_results),
            )
            if best_result and score >= MIN_MATCH_SCORE:
                return best_result["videoId"], score

    raise Exception(f"No confident YouTube Music match. Best score: {score:.2f}")


def _find_video_id_with_immediate_retries(ytmusic, track):
    search_string = _track_label(track)
    for attempt in range(YTMUSIC_IMMEDIATE_RETRY_PASSES + 1):
        try:
            return _find_video_id_for_track(ytmusic, track)
        except Exception as error:
            if _is_youtube_auth_error(error):
                raise
            if not _is_transient_youtube_error(error):
                raise
            if attempt >= YTMUSIC_IMMEDIATE_RETRY_PASSES:
                raise

            print(
                f"{search_string} hit a temporary YouTube Music response error; "
                f"retrying this track after cooldown "
                f"({attempt + 1}/{YTMUSIC_IMMEDIATE_RETRY_PASSES}): {error}"
            )
            time.sleep(YTMUSIC_IMMEDIATE_RETRY_COOLDOWN_SECONDS)


def get_video_ids(ytmusic, tracks):
    video_ids = []
    missed_tracks = {
        "count": 0,
        "tracks": [],
    }
    temporary_error_tracks = []
    for track in tracks:
        search_string = _track_label(track)
        try:
            video_id, _score = _find_video_id_with_immediate_retries(ytmusic, track)
            video_ids.append(video_id)
            time.sleep(YTMUSIC_SEARCH_DELAY_SECONDS)
        except Exception as error:
            if _is_youtube_auth_error(error):
                _raise_youtube_error("searching songs", error)
            if _is_transient_youtube_error(error):
                print(
                    f"{search_string} skipped after temporary YouTube Music "
                    f"non-JSON responses: {error}"
                )
                temporary_error_tracks.append(track)
                time.sleep(YTMUSIC_TRANSIENT_ERROR_COOLDOWN_SECONDS)
                continue
            print(f"{search_string} not found on YouTube Music: {error}")
            missed_tracks["count"] += 1
            missed_tracks["tracks"].append(search_string)

    for retry_pass in range(1, YTMUSIC_FINAL_RETRY_PASSES + 1):
        if not temporary_error_tracks:
            break

        print(
            f"Retrying {len(temporary_error_tracks)} temporary YouTube Music "
            f"search failures, pass {retry_pass}/{YTMUSIC_FINAL_RETRY_PASSES}"
        )
        time.sleep(YTMUSIC_FINAL_RETRY_COOLDOWN_SECONDS)

        remaining_temporary_tracks = []
        for track in temporary_error_tracks:
            search_string = _track_label(track)
            try:
                video_id, _score = _find_video_id_with_immediate_retries(
                    ytmusic,
                    track,
                )
                video_ids.append(video_id)
                print(f"Recovered temporary YouTube Music failure: {search_string}")
                time.sleep(YTMUSIC_SEARCH_DELAY_SECONDS)
            except Exception as error:
                if _is_youtube_auth_error(error):
                    _raise_youtube_error("searching songs", error)
                if _is_transient_youtube_error(error):
                    remaining_temporary_tracks.append(track)
                    print(
                        f"{search_string} still has temporary YouTube Music "
                        f"response errors on final retry pass {retry_pass}: {error}"
                    )
                    time.sleep(YTMUSIC_TRANSIENT_ERROR_COOLDOWN_SECONDS)
                    continue
                print(f"{search_string} not found on YouTube Music after retry: {error}")
                missed_tracks["count"] += 1
                missed_tracks["tracks"].append(search_string)

        temporary_error_tracks = remaining_temporary_tracks

    for retry_pass in range(1, YTMUSIC_LAST_CHANCE_RETRY_PASSES + 1):
        if not temporary_error_tracks:
            break

        print(
            f"Last-chance retry for {len(temporary_error_tracks)} temporary "
            f"YouTube Music response errors, pass "
            f"{retry_pass}/{YTMUSIC_LAST_CHANCE_RETRY_PASSES}"
        )
        time.sleep(YTMUSIC_LAST_CHANCE_RETRY_COOLDOWN_SECONDS)

        remaining_temporary_tracks = []
        for track in temporary_error_tracks:
            search_string = _track_label(track)
            try:
                video_id, _score = _find_video_id_with_immediate_retries(
                    ytmusic,
                    track,
                )
                video_ids.append(video_id)
                print(f"Recovered last-chance temporary failure: {search_string}")
                time.sleep(YTMUSIC_SEARCH_DELAY_SECONDS)
            except Exception as error:
                if _is_youtube_auth_error(error):
                    _raise_youtube_error("searching songs", error)
                if _is_transient_youtube_error(error):
                    remaining_temporary_tracks.append(track)
                    print(
                        f"{search_string} still has temporary YouTube Music "
                        f"response errors on last-chance retry pass "
                        f"{retry_pass}: {error}"
                    )
                    time.sleep(YTMUSIC_TRANSIENT_ERROR_COOLDOWN_SECONDS)
                    continue
                print(
                    f"{search_string} not found on YouTube Music after "
                    f"last-chance retry: {error}"
                )
                missed_tracks["count"] += 1
                missed_tracks["tracks"].append(search_string)

        temporary_error_tracks = remaining_temporary_tracks

    for track in temporary_error_tracks:
        search_string = _track_label(track)
        missed_tracks["count"] += 1
        missed_tracks["tracks"].append(
            f"{search_string} (temporary YouTube Music response error)"
        )

    print(f"Found {len(video_ids)} songs on YouTube Music")
    if len(video_ids) == 0:
        raise Exception("No songs found on YouTube Music")
    return video_ids, missed_tracks


def _playlist_video_ids(ytmusic, playlist_id):
    playlist = ytmusic.get_playlist(playlist_id, limit=None)
    return [
        track.get("videoId")
        for track in playlist.get("tracks") or []
        if track.get("videoId")
    ]


def _reconcile_playlist_prefix(ytmusic, playlist_id, expected_video_ids):
    try:
        actual_video_ids = _playlist_video_ids(ytmusic, playlist_id)
    except Exception as error:
        if _is_youtube_auth_error(error):
            raise
        if _is_retryable_youtube_error(error):
            print(
                "YouTube Music could not expose the newly created playlist "
                f"for reconciliation yet: {error}"
            )
            return None
        raise

    return _missing_expected_video_ids(expected_video_ids, actual_video_ids)


def _missing_expected_video_ids(expected_video_ids, actual_video_ids):
    actual_counts = Counter(actual_video_ids)
    missing = []
    for video_id in expected_video_ids:
        if actual_counts[video_id] > 0:
            actual_counts[video_id] -= 1
        else:
            missing.append(video_id)
    return missing


def _add_playlist_items_chunked(
    ytmusic,
    playlist_id,
    video_ids,
    progress_callback=None,
):
    total = len(video_ids)
    for start in range(0, total, YTMUSIC_PLAYLIST_ADD_CHUNK_SIZE):
        chunk = video_ids[start:start + YTMUSIC_PLAYLIST_ADD_CHUNK_SIZE]
        end = start + len(chunk)
        expected_prefix = video_ids[:end]
        pending_video_ids = chunk
        needs_reconciliation = False

        for attempt in range(YTMUSIC_PLAYLIST_ADD_RETRIES + 1):
            try:
                if needs_reconciliation:
                    missing_prefix = _reconcile_playlist_prefix(
                        ytmusic,
                        playlist_id,
                        expected_prefix,
                    )
                    if missing_prefix is None:
                        if attempt >= YTMUSIC_PLAYLIST_ADD_RETRIES:
                            raise Exception(
                                "YouTube Music did not return a readable "
                                "playlist after an ambiguous write response"
                            )
                        cooldown = YTMUSIC_PLAYLIST_ADD_RETRY_COOLDOWN_SECONDS * (
                            attempt + 1
                        )
                        time.sleep(cooldown)
                        continue

                    pending_video_ids = missing_prefix[-len(chunk):]
                    if not pending_video_ids:
                        print(
                            f"YouTube Music playlist items 1-{end}/{total} "
                            "were accepted despite the invalid response"
                        )
                        if progress_callback:
                            progress_callback(end, total, playlist_id)
                        break

                    print(
                        f"Reconciliation found {len(pending_video_ids)} "
                        f"unconfirmed items through {end}/{total}"
                    )
                    needs_reconciliation = False

                print(
                    f"Adding YouTube Music playlist items "
                    f"{end - len(pending_video_ids) + 1}-{end}/{total} "
                    f"(attempt {attempt + 1}/{YTMUSIC_PLAYLIST_ADD_RETRIES + 1})"
                )
                ytmusic.add_playlist_items(
                    playlist_id,
                    pending_video_ids,
                    duplicates=True,
                )

                if progress_callback:
                    progress_callback(end, total, playlist_id)
                time.sleep(YTMUSIC_SEARCH_DELAY_SECONDS)
                break
            except Exception as error:
                if _is_youtube_auth_error(error):
                    raise
                if (
                    not _is_retryable_youtube_error(error)
                    or attempt >= YTMUSIC_PLAYLIST_ADD_RETRIES
                ):
                    raise

                cooldown = YTMUSIC_PLAYLIST_ADD_RETRY_COOLDOWN_SECONDS * (
                    attempt + 1
                )
                print(
                    f"Temporary YouTube Music error while adding items "
                    f"through {end}/{total}; will reconcile after "
                    f"{cooldown:.0f}s: "
                    f"{error}"
                )
                needs_reconciliation = True
                time.sleep(cooldown)


def create_ytm_playlist(playlist_link, headers, progress_callback=None):
    auth_path = None
    try:
        formatted_headers = parse_headers(headers)
        auth_file = tempfile.NamedTemporaryFile(
            mode="w",
            suffix="-ytmusic-auth.json",
            delete=False,
        )
        auth_path = auth_file.name
        auth_file.close()
        ytmusicapi.setup(filepath=auth_path, headers_raw=formatted_headers)
        ytmusic = YTMusic(auth_path)
    except Exception as error:
        _raise_youtube_error("setting up auth headers", error)

    try:
        tracks = get_all_tracks(playlist_link, "IT")
        playlist_details = get_playlist_details(playlist_link)
        name = playlist_details["name"]

        try:
            playlist_id = ytmusic.create_playlist(name, "", "PRIVATE")
            print(f"Created empty YouTube Music playlist: {name}")
        except Exception as error:
            _raise_youtube_error("creating the empty playlist", error)

        video_ids, missed_tracks = get_video_ids(ytmusic, tracks)

        try:
            _add_playlist_items_chunked(
                ytmusic,
                playlist_id,
                video_ids,
                progress_callback=progress_callback,
            )
        except Exception as error:
            _raise_youtube_error("adding songs to the playlist", error)
    finally:
        if auth_path:
            try:
                Path(auth_path).unlink(missing_ok=True)
            except OSError:
                pass

    print(f"Created YouTube Music playlist: {name} with {len(video_ids)} songs")
    return {
        "missed_tracks": missed_tracks,
        "cover_url": playlist_details.get("cover_url"),
        "playlist_name": name,
    }
