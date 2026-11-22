#!/usr/bin/env python3
"""Analyze New England snowfall (GHCN-Daily) and produce report figures.

Usage: python scripts/analyze.py
Reads data/dly/*.dly and writes images/*.png plus prints the summary table.
Requires: pandas, numpy, matplotlib, scipy
"""
import io
import os
import re
import json
import statistics
import datetime
import sys
from scipy import stats as sp_stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, 'data')
DLY_DIR = os.path.join(DATA, 'dly')
IMAGES = os.path.join(REPO, 'images')
STATIONS_TXT = os.path.join(DATA, 'ghcnd-stations.txt')

BASELINE = (1941, 2000)
RECENT = (2001, 2020)
NE = ['ME', 'VT', 'NH', 'MA', 'CT', 'RI']
SEASON_LABELS = list(range(BASELINE[0], RECENT[1] + 1))

STATION_META = None


def parse_station_meta(path):
    stations = {}
    with io.open(path, encoding='utf-8-sig') as f:
        for line in f:
            parts = line.split(None, 5)
            if len(parts) >= 5:
                try:
                    stations[parts[0]] = dict(
                        name=clean_name(parts[5].strip()) if len(parts) > 5 else '',
                        lat=float(parts[1]), lon=float(parts[2]),
                        elev=float(parts[3]), state=parts[4])
                except ValueError:
                    continue
    return stations


def clean_name(raw):
    raw = re.sub(r'\s+', ' ', raw).strip()
    parts = raw.split(' ')
    while parts and re.match(r'^(HCN|GSN|USW|USC|US|72509|7\d{4,5})$', parts[-1]):
        parts.pop()
    return ' '.join(parts)


def parse_dly(path, element='SNOW'):
    """Yield (year, month, day, value) for the given element (snowfall in mm)."""
    with open(path, 'r', errors='replace') as f:
        for line in f:
            if len(line) < 28:
                continue
            year = int(line[11:15])
            month = int(line[15:17])
            el = line[17:21].strip()
            if el != element:
                continue
            for day in range(1, 32):
                start = 21 + (day - 1) * 8
                valstr = line[start:start + 5].strip()
                if not valstr:
                    continue
                try:
                    val = int(valstr)
                except ValueError:
                    continue
                if val == -9999:
                    continue
                yield year, month, day, val


def load_station_seasons(sid):
    """Build per-season NH snowfall totals (Nov-Apr)."""
    path = os.path.join(DLY_DIR, sid + '.dly')
    seasons = {}
    for year, month, day, val in parse_dly(path):
        if month in (11, 12):
            syear = year + 1
        elif month in (1, 2, 3, 4):
            syear = year
        else:
            continue
        if syear not in seasons:
            seasons[syear] = {'days': 0, 'snow_mm': 0.0, 'snow_days': 0}
        seasons[syear]['days'] += 1
        seasons[syear]['snow_mm'] += val
        if val > 0:
            seasons[syear]['snow_days'] += 1
    return seasons


def season_bounds(syear):
    start = datetime.date(syear - 1, 11, 1)
    end = datetime.date(syear, 4, 30)
    return (end - start).days + 1


def main():
    meta = parse_station_meta(STATIONS_TXT)
    if meta is None:
        sys.exit('Missing station metadata: expected data/ghcnd-stations.txt - run scripts/download_data.py first')

    os.makedirs(IMAGES, exist_ok=True)

    # --- collect per-season records for each station ---
    station_rows = []
    for sid in sorted(f[:-4] for f in os.listdir(DLY_DIR) if f.endswith('.dly')):
        if sid not in meta:
            continue
        st = meta[sid]
        if st['state'] not in NE:
            continue
        seasons = load_station_seasons(sid)
        rows = []
        for syear in SEASON_LABELS:
            if syear not in seasons:
                continue
            s = seasons[syear]
            expected = season_bounds(syear)
            completeness = s['days'] / expected
            rows.append(dict(
                season=syear,
                snow_mm=s['snow_mm'],
                snow_days=s['snow_days'],
                expected=expected,
                data_days=s['days'],
                completeness=completeness,
                included=completeness >= 0.75,
            ))
        if not rows:
            continue
        station_rows.append(dict(sid=sid, name=st['name'], state=st['state'],
                                 lat=st['lat'], lon=st['lon'], elev=st['elev'], seasons=rows))

    print(f'Stations parsed: {len(station_rows)}')

    # --- aggregates ---
    station_agg = []
    for d in station_rows:
        base = [s for s in d['seasons'] if BASELINE[0] <= s['season'] <= BASELINE[1] and s['included']]
        rec = [s for s in d['seasons'] if RECENT[0] <= s['season'] <= RECENT[1] and s['included']]
        if len(base) < 10 or len(rec) < 10:
            continue
        bm = statistics.mean([s['snow_mm'] for s in base])
        rm = statistics.mean([s['snow_mm'] for s in rec])
        station_agg.append(dict(
            sid=d['sid'], name=d['name'], state=d['state'], elev=d['elev'],
            n_base=len(base), n_rec=len(rec),
            base_mean=bm, rec_mean=rm,
            diff=rm - bm, pct=(rm - bm) / bm * 100 if bm else None,
            base_days=statistics.mean([s['snow_days'] for s in base]),
            rec_days=statistics.mean([s['snow_days'] for s in rec]),
        ))

    use = station_agg
    base_means = [a['base_mean'] for a in use]
    rec_means = [a['rec_mean'] for a in use]
    regional_base = statistics.mean(base_means)
    regional_rec = statistics.mean(rec_means)
    diffs = [a['rec_mean'] - a['base_mean'] for a in use]
    n = len(use)
    se_diff = statistics.stdev(diffs) / np.sqrt(n)
    t, p_diff = sp_stats.ttest_1samp(diffs, 0.0)
    w, p_w = sp_stats.wilcoxon([a['rec_mean'] for a in use], [a['base_mean'] for a in use])

    print('\n================ KEY RESULTS (equal-weight stations, n=%d) ================' % n)
    print(f'Baseline 1941-2000 (n={len(base_means)}):  mean seasonal snowfall {regional_base:.1f} mm')
    print(f'Recent   2001-2020 (n={len(rec_means)}):  mean seasonal snowfall {regional_rec:.1f} mm')
    print(f'Change:  {regional_rec - regional_base:+.1f} mm ({(regional_rec - regional_base) / regional_base * 100:+.1f}%)')
    print(f'        median: {statistics.median(base_means):.1f} mm -> {statistics.median(rec_means):.1f} mm')
    print(f'Per-station mean diff: {statistics.mean(diffs):+.1f} mm, 95% CI [{statistics.mean(diffs) - 1.96*se_diff:+.1f}, {statistics.mean(diffs) + 1.96*se_diff:+.1f}] mm')
    print(f't-test: t={t:.2f}, p={p_diff:.3g}   Wilcoxon: W={w:.0f}, p={p_w:.3g}')

    base_days = statistics.mean([a['base_days'] for a in use])
    rec_days = statistics.mean([a['rec_days'] for a in use])
    print(f'\nSnow days/season: baseline {base_days:.2f} -> recent {rec_days:.2f} '
          f'({(rec_days - base_days) / base_days * 100:+.1f}%)')

    print('\nPer-state summary (stations with >=10 seasons both periods):')
    for state in ['MA', 'CT', 'ME', 'NH', 'RI', 'VT']:
        agg = [a for a in use if a['state'] == state]
        if not agg:
            continue
        bm = statistics.mean([a['base_mean'] for a in agg])
        rm = statistics.mean([a['rec_mean'] for a in agg])
        print(f'  {state}: n={len(agg):2d}  {bm:7.1f} -> {rm:7.1f} mm ({(rm-bm)/bm*100:+.1f}%)')

    # --- regional series + trend ---
    per_season = {}
    for d in station_rows:
        base = [s for s in d['seasons'] if BASELINE[0] <= s['season'] <= BASELINE[1] and s['included']]
        rec = [s for s in d['seasons'] if RECENT[0] <= s['season'] <= RECENT[1] and s['included']]
        if len(base) < 10 or len(rec) < 10:
            continue
        for s in d['seasons']:
            if s['included']:
                per_season.setdefault(s['season'], []).append(s['snow_mm'])
    years = sorted(per_season)
    reg_mean = [statistics.mean(per_season[y]) for y in years]
    reg_n = [len(per_season[y]) for y in years]

    base_reg = [m for y, m in zip(years, reg_mean) if y <= 2000]
    rec_reg = [m for y, m in zip(years, reg_mean) if y >= 2001]
    slope, intercept, r_value, p_value, se = sp_stats.linregress(years, reg_mean)
    print('\nRegional per-season series (equal-weight stations):')
    print(f'  baseline ({BASELINE[0]}-{BASELINE[1]}): {statistics.mean(base_reg):.1f} mm (n={len(base_reg)})')
    print(f'  recent   ({RECENT[0]}-{RECENT[1]}): {statistics.mean(rec_reg):.1f} mm (n={len(rec_reg)})')
    print(f'  change: {statistics.mean(rec_reg) - statistics.mean(base_reg):+.1f} mm ({(statistics.mean(rec_reg) - statistics.mean(base_reg)) / statistics.mean(base_reg) * 100:+.1f}%)')
    print(f'  linear trend 1941-2020: slope {slope:+.3f} mm/yr ({slope*10:+.1f} mm/decade), R2={r_value**2:.3f}, p={p_value:.3g}')

    decennia = [(1941, 1950), (1951, 1960), (1961, 1970), (1971, 1980), (1981, 1990), (1991, 2000), (2001, 2010), (2011, 2020)]
    print('\nDecade means:')
    decade_means = []
    for y0, y1 in decennia:
        vals = [reg_mean[i] for i, y in enumerate(years) if y0 <= y <= y1]
        if vals:
            decade_means.append((f'{y0}-{y1}', statistics.mean(vals)))
            print(f'  {y0}-{y1}: {statistics.mean(vals):7.1f} mm')

    # --- figures ---
    plt.rcParams.update({
        'font.size': 12, 'font.family': 'DejaVu Sans', 'axes.titlesize': 15,
        'axes.titleweight': 'bold', 'axes.labelsize': 12,
        'figure.facecolor': 'white', 'axes.facecolor': 'white',
        'axes.edgecolor': '#cccccc', 'axes.linewidth': 1,
        'axes.grid': True, 'grid.color': '#eeeeee', 'grid.linewidth': 0.8,
        'axes.spines.top': False, 'axes.spines.right': False,
    })

    # fig 1: time series
    base_m = statistics.mean(base_reg)
    rec_m = statistics.mean(rec_reg)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.axvspan(1939, 2001, color='#f4f7fb', alpha=0.9)
    ax.axvspan(2001, 2022, color='#fdf2ec', alpha=0.9)
    ax.plot(years, reg_mean, color='#1f4e79', linewidth=2, marker='o', markersize=3, markerfacecolor='#1f4e79', label='Regional mean seasonal snowfall')
    ax.axhline(base_m, color='#1f4e79', linestyle='--', linewidth=1.5, label=f'1941-2000 baseline ({base_m:.0f} mm)')
    ax.axhline(rec_m, color='#c05621', linestyle='--', linewidth=1.5, label=f'2001-2020 ({rec_m:.0f} mm)')
    ax.set_ylabel('Seasonal snowfall (mm)')
    ax.set_xlabel('Season (Nov-Apr)')
    ax.set_xlim(1940, 2022)
    ax.set_ylim(0, 3100)
    ax.set_title('New England seasonal snowfall (Nov-Apr), 1941-2020')
    ax.legend(loc='upper right', frameon=True, fontsize=10)
    ax.text(1945, 40, '1941-2000', ha='center', fontsize=12, color='#1f4e79', fontweight='bold')
    ax.text(2011, 40, '2001-2020', ha='center', fontsize=12, color='#c05621', fontweight='bold')
    plt.tight_layout()
    plt.savefig(os.path.join(IMAGES, 'fig1_timeseries.png'), dpi=200, bbox_inches='tight')
    plt.close()

    # fig 2: decade means
    xs = range(len(decade_means))
    vals = [d[1] for d in decade_means]
    colors = ['#1f4e79'] * 6 + ['#c05621'] * 2
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.bar(xs, vals, color=colors, alpha=0.9, edgecolor='white', linewidth=1.2)
    for i, v in enumerate(vals):
        ax.text(i, v + 40, f'{v:.0f}', ha='center', fontsize=11, fontweight='bold')
    ax.set_xticks(list(xs))
    ax.set_xticklabels([d[0] for d in decade_means], fontsize=10)
    ax.set_ylabel('Mean seasonal snowfall (mm)')
    ax.set_ylim(0, 2300)
    ax.set_title('Regional mean snowfall by decade')
    plt.tight_layout()
    plt.savefig(os.path.join(IMAGES, 'fig2_decades.png'), dpi=200, bbox_inches='tight')
    plt.close()

    # fig 3: per-station % change
    use.sort(key=lambda a: a['pct'])
    pcts = [a['pct'] for a in use]
    labels = [a['name'].split()[0] + ' ' + a['state'] for a in use]
    colors = ['#2b6a4c' if p > 0 else '#c05621' for p in pcts]
    fig, ax = plt.subplots(figsize=(13, 19))
    ax.barh(range(len(pcts)), pcts, color=colors, alpha=0.9, edgecolor='white')
    ax.set_yticks(range(len(pcts)))
    ax.set_yticklabels(labels, fontsize=10)
    ax.axvline(0, color='#333333', linewidth=1.2)
    ax.set_xlabel('Change in mean seasonal snowfall, 2001-2020 vs 1941-2000 (%)')
    ax.set_title('Per-station change in snowfall', pad=15)
    for i, p in enumerate(pcts):
        ax.text(p + (1.2 if p > 0 else -1.2), i, f'{p:+.0f}%', va='center', ha='left' if p > 0 else 'right', fontsize=9)
    plt.tight_layout()
    plt.savefig(os.path.join(IMAGES, 'fig3_per_station.png'), dpi=200, bbox_inches='tight')
    plt.close()

    # fig 4: per-state dumbbell
    states = {}
    for a in use:
        states.setdefault(a['state'], []).append(a)
    state_names = {'MA': 'Massachusetts', 'CT': 'Connecticut', 'NH': 'New Hampshire', 'RI': 'Rhode Island', 'ME': 'Maine', 'VT': 'Vermont'}
    state_order = ['MA', 'CT', 'ME', 'NH', 'RI', 'VT']
    base_stats = {s: statistics.mean([a['base_mean'] for a in v]) for s, v in states.items()}
    rec_stats = {s: statistics.mean([a['rec_mean'] for a in v]) for s, v in states.items()}
    fig, ax = plt.subplots(figsize=(12, 6.5))
    for i, s in enumerate(state_order):
        if s not in states:
            continue
        ax.plot([base_stats[s], rec_stats[s]], [i, i], color='#dddddd', linewidth=5, zorder=1)
        ax.scatter(base_stats[s], i, s=280, color='#1f4e79', zorder=3, label='1941-2000 baseline' if i == 0 else None)
        ax.scatter(rec_stats[s], i, s=280, color='#c05621', zorder=3, label='2001-2020 recent' if i == 0 else None)
        ax.annotate(f'{base_stats[s]:.0f}', (base_stats[s], i + 0.38), ha='center', fontsize=11, color='#1f4e79', fontweight='bold')
        ax.annotate(f'{rec_stats[s]:.0f}', (rec_stats[s], i - 0.38), ha='center', fontsize=11, color='#c05621', fontweight='bold')
    ax.set_yticks(range(len(state_order)))
    ax.set_yticklabels([f'{state_order[i]} - {state_names[state_order[i]]}' for i in range(len(state_order))], fontsize=11)
    ax.set_xlabel('Mean seasonal snowfall (mm)')
    ax.set_title('Mean seasonal snowfall by New England state')
    ax.set_xlim(0, 2600)
    ax.set_ylim(-0.7, len(state_order) - 0.3)
    ax.legend(loc='lower right', frameon=True, fontsize=10)
    plt.tight_layout()
    plt.savefig(os.path.join(IMAGES, 'fig4_states.png'), dpi=200, bbox_inches='tight')
    plt.close()

    print('Figures written to images/')


if __name__ == '__main__':
    main()
