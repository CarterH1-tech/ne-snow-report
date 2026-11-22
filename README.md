# Did New England get any less snowy?

A data-driven check of the uncle's complaint, using the **Global Historical Climatology Network — Daily (GHCN-Daily)**.

**Live report (GitHub Pages):** https://carterh1-tech.github.io/ne-snow-report/

## The short answer

**No.** Seasonal snowfall (Nov–Apr) in New England in 2001–2020 was, on average, *slightly higher* than in 1941–2000 — not lower. The change is roughly +2.7% (equal-weight over 57 long-record stations) and is not statistically significant (t = 1.50, p ≈ 0.14). Snow days per season rose ~3.8%.

## How it works

- **Data:** NOAA NCEI, GHCN-Daily (Version 3.35), per-station .dly files — 57 long-record New England stations with SNOW records spanning 1941–2020.
- **Analysis:** seasonal (Nov–Apr) snowfall aggregates per station, gated on ≥ 75% day completeness (~98% mean completeness on included seasons).
- **Figures:** all PNGs in `images/` are regenerated from raw data by `scripts/analyze.py`.

## Repo layout

| Path | What |
| --- | --- |
| `index.html` | The report (served by GitHub Pages) |
| `images/` | Figures used in the report |
| `scripts/download_data.py` | Downloads station metadata + .dly files into `data/` (gitignored) |
| `scripts/analyze.py` | Parses .dly files, computes statistics, regenerates figures |
| `data/` | **Ignored** — large raw datasets, recreated by the download script |

## Reproducing the analysis

Requires Python 3.12+ and `pandas`, `numpy`, `matplotlib`, `scipy`.

```bash
python scripts/download_data.py   # downloads ~60 station .dly files into data/
python scripts/analyze.py        # computes statistics + writes figures to images/
```

Then open `index.html` or visit the GitHub Pages URL above.

## Caveats

GHCN-Daily is not homogenized; baseline and recent values should be treated as approximate. Seasonal totals are noisy. New Hampshire's stations do show a modest decline (−5%); the southern coastal stations gained snow. See the report for details.

## License / data citation

GHCN-Daily: Menne, I. Durre, R. Vose et al. (2012). NOAA / NCEI. This repo is a personal analysis, not an official NOAA product.
