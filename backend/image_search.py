# backend/image_search.py
import requests
import os
import urllib.parse

def search_artist_image(artist_name):
    try:
        search_term = f"{artist_name} musician"
        url = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": search_term,
            "srlimit": 1,
            "srnamespace": 6
        }
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code != 200:
            print(f"[ImageSearch] HTTP {response.status_code} for {artist_name}")
            return None
        
        try:
            data = response.json()
        except ValueError:
            print(f"[ImageSearch] Non-JSON response for {artist_name}")
            return None

        if "query" in data and "search" in data["query"]:
            results = data["query"]["search"]
            if results:
                title = results[0]["title"]
                file_url = f"https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo&iiprop=url&titles={urllib.parse.quote(title)}"
                file_resp = requests.get(file_url, timeout=10)
                if file_resp.status_code != 200:
                    return None
                try:
                    file_data = file_resp.json()
                except ValueError:
                    return None
                pages = file_data["query"]["pages"]
                for page in pages.values():
                    if "imageinfo" in page:
                        return page["imageinfo"][0]["url"]
    except Exception as e:
        print(f"[ImageSearch] Exception for {artist_name}: {e}")
    return None

def download_image(image_url, save_path):
    try:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        response = requests.get(image_url, timeout=15)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(response.content)
            return True
    except Exception as e:
        print(f"[ImageSearch] Download failed: {e}")
    return False