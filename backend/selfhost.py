import argparse
from pathlib import Path

from ytm import create_ytm_playlist


def main():
    parser = argparse.ArgumentParser(
        description="Clone a Spotify playlist to YouTube Music."
    )
    parser.add_argument("playlist_url", help="Spotify playlist URL")
    parser.add_argument(
        "headers_file",
        type=Path,
        help="Text file containing fresh YouTube Music request headers",
    )
    args = parser.parse_args()

    headers = args.headers_file.read_text(encoding="utf-8")
    result = create_ytm_playlist(args.playlist_url, headers)
    print(f"Playlist created: {result['playlist_name']}")
    print(f"Missed tracks: {result['missed_tracks']['count']}")


if __name__ == "__main__":
    main()
