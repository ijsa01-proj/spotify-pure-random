
import os
import time
import requests

from random import SystemRandom
from datetime import datetime
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

API_URL = "https://api.spotify.com/v1"

SCOPES = (
    "user-library-read "
    "playlist-modify-private"
)

rng = SystemRandom()

auth = SpotifyOAuth(
    client_id=os.environ["SPOTIPY_CLIENT_ID"],
    client_secret=os.environ["SPOTIPY_CLIENT_SECRET"],
    redirect_uri=os.environ["SPOTIPY_REDIRECT_URI"],
    scope=SCOPES,
    cache_path=".spotify_cache"
)


def spotify_request(method, endpoint, **kwargs):
    url = (
        endpoint if endpoint.startswith(API_URL + "/")
        else API_URL + endpoint
    )

    for attempt in range(5):
        token = auth.get_access_token(
            as_dict=False
        )

        response = requests.request(
            method,
            url,
            headers={
                "Authorization": f"Bearer {token}"
            },
            timeout=30,
            **kwargs
        )

        if response.status_code == 429:
            wait = int(
                response.headers.get("Retry-After", 5)
            )
            print(f"Rate limit. Waiting {wait}s...")
            time.sleep(wait)
            continue

        response.raise_for_status()
        return response.json()

    raise RuntimeError("Spotify rate limit exceeded")


def get_saved_tracks():
    tracks = {}
    scanned = 0
    expected = None

    endpoint = "/me/tracks?limit=50"

    while endpoint:
        page = spotify_request("GET", endpoint)

        if expected is None:
            expected = page.get("total")

        for item in page["items"]:
            scanned += 1
            track = item.get("track")

            if not track:
                continue

            uri = track.get("uri")

            if (
                uri
                and uri.startswith("spotify:track:")
                and not track.get("is_local", False)
            ):
                tracks[uri] = track

        print(
            f"\rScanned: {scanned} / {expected}",
            end="",
            flush=True
        )

        endpoint = page.get("next")

    print()

    if expected is not None and scanned != expected:
        raise RuntimeError(
            "Library changed or retrieval was incomplete. "
            "Please run the program again."
        )

    print(f"Eligible unique tracks: {len(tracks)}")
    print(f"Excluded/duplicates: {scanned - len(tracks)}")

    return list(tracks.values())


def generate_random_selection(tracks):
    if len(tracks) < 100:
        raise ValueError(
            "At least 100 eligible tracks are required."
        )

    quantity = rng.randint(70, 100)

    return rng.sample(tracks, quantity)


def create_playlist(tracks):
    playlist = spotify_request(
        "POST",
        "/me/playlists",
        json={
            "name": "Pure Random",
            "description": (
                "Uniform random selection from saved tracks. "
                f"{len(tracks)} songs. "
                f"Generated: {datetime.now():%Y-%m-%d %H:%M}"
            ),
            "public": False
        }
    )

    playlist_id = playlist["id"]

    try:
        spotify_request(
            "POST",
            f"/playlists/{playlist_id}/items",
            json={
                "uris": [
                    track["uri"] for track in tracks
                ]
            }
        )
    except Exception:
        print(
            f"Playlist created but adding tracks failed: "
               f"{playlist_id}. Check Spotify before retrying."
        )
        raise

    return playlist


def main():
    print("=== Spotify Pure Random ===")
    print("Retrieving your complete library...")

    library = get_saved_tracks()
    selection = generate_random_selection(library)

    print(f"Selected {len(selection)} random tracks.")

    playlist = create_playlist(selection)

    print("\nPlaylist created successfully!")
    print(f"Name: {playlist['name']}")
    print(f"Tracks: {len(selection)}")
    print(f"https://open.spotify.com/playlist/{playlist['id']}")

    print("\nPlaylist content:\n")

    for index, track in enumerate(selection, 1):
        artists = ", ".join(
            a["name"] for a in track["artists"]
        )

        print(
            f"{index}. {track['name']} - {artists}"
        )


if __name__ == "__main__":
    main()

