
import os
import time
import requests

from random import SystemRandom
from datetime import datetime
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

API_URL = "https://api.spotify.com/v1"

PLAYLIST_NAME = "Pure Random"

# Previously created Pure Random playlist.
EXISTING_PLAYLIST_ID = "12HMSlZYG0u5LRkUfM0g4D"

MIN_TRACKS = 70
MAX_TRACKS = 100

SCOPES = (
    "user-library-read "
    "user-library-modify "
    "playlist-read-private "
    "playlist-modify-private "
    "playlist-modify-public"
)

rng = SystemRandom()

auth = SpotifyOAuth(
    client_id=os.environ["SPOTIPY_CLIENT_ID"],
    client_secret=os.environ["SPOTIPY_CLIENT_SECRET"],
    redirect_uri=os.environ["SPOTIPY_REDIRECT_URI"],
    scope=SCOPES,
    cache_path=".spotify_cache"
)


# ==========================================
# Spotify API request handler
# ==========================================

def spotify_request(method, endpoint, **kwargs):

    url = (
        endpoint if endpoint.startswith(API_URL + "/")
        else API_URL + endpoint
    )

    for attempt in range(5):

        token = auth.get_access_token(as_dict=False)

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

        if not response.ok:
            print(f"Spotify API error: {response.status_code}")
            print(response.text)

        response.raise_for_status()

        # Some Spotify endpoints return an empty body.
        if not response.content:
            return None

        return response.json()

    raise RuntimeError("Spotify rate limit exceeded")


# ==========================================
# Get current Spotify user
# ==========================================

def get_current_user():

    return spotify_request("GET", "/me")


# ==========================================
# Retrieve complete saved tracks library
# ==========================================

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


# ==========================================
# Generate uniform random selection
# ==========================================

def generate_random_selection(tracks):

    if len(tracks) < MAX_TRACKS:

        raise ValueError(
            f"At least {MAX_TRACKS} eligible tracks are required."
        )

    quantity = rng.randint(MIN_TRACKS, MAX_TRACKS)

    return rng.sample(tracks, quantity)


# ==========================================
# Find existing Pure Random playlist
# ==========================================

def find_existing_playlist(user_id):

    endpoint = "/me/playlists?limit=50"
    matches = {}

    while endpoint:

        page = spotify_request("GET", endpoint)

        for playlist in page["items"]:

            if not playlist:
                continue

            if (
                playlist["name"] == PLAYLIST_NAME
                and playlist["owner"]["id"] == user_id
            ):
                matches[playlist["id"]] = playlist

        endpoint = page.get("next")

    # Recover the original playlist if it is not
    # currently displayed in the user's library.

    if EXISTING_PLAYLIST_ID and EXISTING_PLAYLIST_ID not in matches:

        try:

            playlist = spotify_request(
                "GET",
                f"/playlists/{EXISTING_PLAYLIST_ID}"
            )

            if (
                playlist["name"] == PLAYLIST_NAME
                and playlist["owner"]["id"] == user_id
            ):
                matches[playlist["id"]] = playlist

        except requests.HTTPError as error:

            if error.response.status_code != 404:
                raise

    if len(matches) > 1:

        raise RuntimeError(
            "Multiple owned Pure Random playlists found. "
            "Please resolve duplicates before continuing."
        )

    if matches:

        playlist = next(iter(matches.values()))

        print(f"Existing playlist found: {playlist['id']}")

        return playlist

    return None


# ==========================================
# Generate playlist description
# ==========================================

def get_playlist_description(tracks):

    return (
        "Pure Random | Uniform random selection "
        "from saved tracks. "
        f"{len(tracks)} songs. "
        f"Updated: {datetime.now():%Y-%m-%d %H:%M}"
    )


# ==========================================
# Create playlist if it does not exist
# ==========================================

def create_playlist(tracks):

    print("Creating new Pure Random playlist...")

    return spotify_request(
        "POST",
        "/me/playlists",
        json={
            "name": PLAYLIST_NAME,
            "description": get_playlist_description(tracks),
            "public": False,
            "collaborative": False
        }
    )


# ==========================================
# Ensure playlist remains private
# ==========================================

def update_playlist_details(playlist_id, tracks):

    print("Updating playlist details and privacy...")

    spotify_request(
        "PUT",
        f"/playlists/{playlist_id}",
        json={
            "name": PLAYLIST_NAME,
            "description": get_playlist_description(tracks),
            "public": False,
            "collaborative": False
        }
    )


# ==========================================
# Replace ALL existing playlist tracks
# ==========================================

def replace_playlist_tracks(playlist_id, tracks):

    print("Replacing playlist tracks...")

    spotify_request(
        "PUT",
        f"/playlists/{playlist_id}/items",
        json={
            "uris": [
                track["uri"]
                for track in tracks
            ]
        }
    )

    print(f"Playlist now contains {len(tracks)} new tracks.")


# ==========================================
# Save playlist to user's Spotify library
# ==========================================


def is_playlist_in_library(playlist_id):

    endpoint = "/me/playlists?limit=50"

    while endpoint:

        page = spotify_request("GET", endpoint)

        for playlist in page["items"]:

            if playlist and playlist["id"] == playlist_id:
                return True

        endpoint = page.get("next")

    return False


def save_playlist_to_library(playlist_id):

    print("Checking if playlist is already in your library...")

    if is_playlist_in_library(playlist_id):

        print("Playlist is already in your library.")
        return True

    print("Saving playlist to your library...")

    try:

        spotify_request(
            "PUT",
            "/me/library",
            params={
                "uris": f"spotify:playlist:{playlist_id}"
            }
        )

    except requests.HTTPError as error:

        print(
            f"Warning: Spotify returned HTTP "
            f"{error.response.status_code} while saving."
        )

    # Verify the actual state, even if Spotify
    # returned an error during the save request.

    if is_playlist_in_library(playlist_id):

        print("Playlist successfully verified in your library.")
        return True

    print(
        "Warning: Playlist tracks were updated, "
        "but saving to your library could not be verified."
    )

    return False



# ==========================================
# Create or update Pure Random
# ==========================================

def create_or_update_playlist(tracks, user_id):

    playlist = find_existing_playlist(user_id)

    if playlist is None:

        playlist = create_playlist(tracks)
        action = "created"

    else:

        print("Reusing existing Pure Random playlist...")
        action = "updated"

    playlist_id = playlist["id"]

    update_playlist_details(playlist_id, tracks)

    replace_playlist_tracks(playlist_id, tracks)

    saved = save_playlist_to_library(playlist_id)

    return playlist, action, saved


# ==========================================
# Main program
# ==========================================

def main():

    print("=== Spotify Pure Random v1.1 ===")

    user = get_current_user()

    print(f"Spotify user: {user.get('display_name', user['id'])}")

    print("\nRetrieving your complete library...")

    library = get_saved_tracks()

    selection = generate_random_selection(library)

    print(f"Selected {len(selection)} random tracks.")

    playlist, action, saved = create_or_update_playlist(
        selection,
        user["id"]
    )

    print(f"\nPlaylist {action} successfully!")
    print(f"Name: {PLAYLIST_NAME}")
    print(f"Tracks: {len(selection)}")
    print("Visibility requested: Private")
    print(f"Saved to library: {'OK' if saved else 'NOT VERIFIED'}")
    print(f"Playlist ID: {playlist['id']}")
    print(f"https://open.spotify.com/playlist/{playlist['id']}")

    print("\nPlaylist content:\n")

    for index, track in enumerate(selection, 1):

        artists = ", ".join(
            artist["name"]
            for artist in track["artists"]
        )

        print(
            f"{index}. {track['name']} - {artists}"
        )


if __name__ == "__main__":
    main()
