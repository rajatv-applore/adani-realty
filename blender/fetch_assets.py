#!/usr/bin/env python3
"""
Download the CC0 assets used by villa_render.py from Poly Haven (https://polyhaven.com).
All Poly Haven assets are CC0 (public domain), free for commercial use.

    python3 blender/fetch_assets.py          (or: npm run assets)

Files land in blender/assets/{hdri,textures,models}/ (git-ignored). Existing files are
skipped, so re-running only fetches what is missing.
"""
import json
import os
import sys
import urllib.request

API = "https://api.polyhaven.com/files/"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

HDRIS = {  # id -> resolution
    "kloofendal_48d_partly_cloudy_puresky": "4k",   # day
    "qwantani_dusk_2_puresky": "2k",                # dusk
}

TEXTURES = {  # id -> resolution
    "beige_wall_002": "2k",          # final sand stucco
    "white_stucco": "2k",            # charcoal paint (tinted) + cement plaster
    "concrete_wall_008": "2k",       # raw RCC
    "red_brick_03": "1k",            # blockwork infill
    "oak_veneer_01": "1k",           # soffits, rails, gate, deck
    "fine_grained_wood": "1k",       # main door
    "concrete_pavers_02": "1k",      # driveway
    "concrete_tiles": "1k",          # footpath / terrace
    "asphalt_02": "2k",              # road
    "grass_ground": "2k",            # lawn base
    "brown_mud_dry": "1k",           # bare site soil
}
TEXTURE_MAPS = {"Diffuse": "diff", "Rough": "rough", "Displacement": "disp"}

MODELS = [
    "anthurium_botany_01", "calathea_orbifolia_01", "fern_02", "periwinkle_plant",
    "searsia_burchellii", "searsia_lucida",
    "potted_plant_01", "potted_plant_02",
    "jacaranda_tree", "planter_box_01", "outdoor_table_chair_set_01",
]
MODEL_RES = "1k"

HEADERS = {"User-Agent": "adani-villa-progress/1.0 (asset fetcher)"}


def _open(url, timeout):
    return urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=timeout)


def fetch_json(url):
    with _open(url, 60) as r:
        return json.load(r)


def download(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    with _open(url, 300) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    os.replace(tmp, dest)
    return True


def main():
    count = 0
    for hid, res in HDRIS.items():
        files = fetch_json(API + hid)
        count += download(files["hdri"][res]["hdr"]["url"], os.path.join(ROOT, "hdri", f"{hid}_{res}.hdr"))
        # tonemapped LDR panorama: the visible sky backdrop in the web app
        count += download(files["tonemapped"]["url"], os.path.join(ROOT, "hdri", f"{hid}_tonemapped.jpg"))

    for tid, res in TEXTURES.items():
        files = fetch_json(API + tid)
        for key, short in TEXTURE_MAPS.items():
            if key not in files:
                continue
            info = files[key][res]["jpg"]
            count += download(info["url"], os.path.join(ROOT, "textures", tid, f"{short}.jpg"))

    for mid in MODELS:
        gltf = fetch_json(API + mid)["gltf"][MODEL_RES]["gltf"]
        base = os.path.join(ROOT, "models", mid)
        count += download(gltf["url"], os.path.join(base, f"{mid}.gltf"))
        for rel, inc in gltf.get("include", {}).items():
            count += download(inc["url"], os.path.join(base, rel))

    print(f"assets ready in {ROOT} ({count} new files)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # network errors etc.
        print("asset download failed:", e, file=sys.stderr)
        sys.exit(1)
