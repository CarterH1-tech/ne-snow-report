#!/usr/bin/env python3
"""Download GHCN-Daily data for long-record New England stations.

Fetches station metadata, inventory and per-station .dly files from NOAA NCEI.
Output lands in ./data/ (gitignored).
"""
import io
import os
import re
import sys
import urllib.request
import concurrent.futures
import collections

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, 'data')
STATIONS_TXT = os.path.join(DATA, 'ghcnd-stations.txt')
INVENTORY_TXT = os.path.join(DATA, 'ghcnd-inventory.txt')
DLY_DIR = os.path.join(DATA, 'dly')
BASE = 'https://www.ncei.noaa.gov/pub/data/ghcn/daily'
NE = ['ME', 'VT', 'NH', 'MA', 'CT', 'RI']


def ensure_file(url, out_path, timeout=300):
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        return
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    for attempt in range(3):
        try:
            print(f'Downloading {url} ...')
            with urllib.request.urlopen(url, timeout=timeout) as r:
                data = r.read()
            with open(out_path, 'wb') as f:
                f.write(data)
            return
        except Exception as e:
            print(f'  attempt {attempt + 1} failed: {e}')
    raise RuntimeError(f'Could not download {url}')


def clean_name(raw):
    raw = re.sub(r'\s+', ' ', raw).strip()
    parts = raw.split(' ')
    while parts and re.match(r'^(HCN|GSN|USW|USC|US|72509|7\d{4,5})$', parts[-1]):
        parts.pop()
    return ' '.join(parts)


def parse_stations(path):
    stations = {}
    with io.open(path, encoding='utf-8-sig') as f:
        for line in f:
            parts = line.split(None, 5)
            if len(parts) >= 5:
                try:
                    stations[parts[0]] = dict(
                        name=clean_name(parts[5].strip()) if len(parts) > 5 else '',
                        name_raw=parts[5].strip() if len(parts) > 5 else '',
                        lat=float(parts[1]), lon=float(parts[2]),
                        elev=float(parts[3]), state=parts[4])
                except ValueError:
                    continue
    return stations


def find_snow_candidates(stations, inventory_path):
    inv = collections.defaultdict(list)
    with io.open(inventory_path, encoding='utf-8-sig') as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 6:
                try:
                    inv[parts[0]].append((parts[3], int(parts[4]), int(parts[5])))
                except ValueError:
                    continue
    candidates = []
    for sid, recs in inv.items():
        st = stations.get(sid)
        if not st:
            continue
        if st['state'] not in NE:
            continue
        snow = [(b, e) for (el, b, e) in recs if el == 'SNOW']
        if not snow:
            continue
        b = min(x[0] for x in snow)
        e = max(x[1] for x in snow)
        if b <= 1941 and e >= 2020:
            candidates.append((sid, st['name'], st['state'], b, e))
    candidates.sort(key=lambda x: (x[2], x[1]))
    return candidates


def fetch(sid):
    out = os.path.join(DLY_DIR, sid + '.dly')
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        return sid, 'cached'
    url = f'{BASE}/all/{sid}.dly'
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                data = r.read()
            with open(out, 'wb') as f:
                f.write(data)
            return sid, f'ok ({len(data)} bytes)'
        except Exception:
            if attempt == 2:
                return sid, 'FAILED'
    return sid, 'FAILED'


def main():
    os.makedirs(DATA, exist_ok=True)
    ensure_file(f'{BASE}/ghcnd-stations.txt', STATIONS_TXT)
    ensure_file(f'{BASE}/ghcnd-inventory.txt', INVENTORY_TXT)

    stations = parse_stations(STATIONS_TXT)
    candidates = find_snow_candidates(stations, INVENTORY_TXT)
    print(f'New England stations with SNOW covering 1941-2020: {len(candidates)}')

    os.makedirs(DLY_DIR, exist_ok=True)
    ids = [c[0] for c in candidates]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for sid, status in ex.map(fetch, ids):
            print(sid, status, flush=True)

    print('Done.')


if __name__ == '__main__':
    main()
