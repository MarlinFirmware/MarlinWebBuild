# Marlin Firmware Builder

Build [Marlin](https://github.com/MarlinFirmware/Marlin) firmware for any of its
[example configurations](https://github.com/MarlinFirmware/Configurations/tree/bugfix-2.1.x/config/examples),
without installing a build environment.

Choose **`bugfix-2.1.x`** (always built from its latest commit) or the latest patch release of a
Marlin series from **2.0.7** on (2.0.7.5, 2.0.8.7, … 2.1.2.10), with the example configurations published
for that release. Older series and beta releases are not offered, since they don't build with PlatformIO 6.

**You need a free [GitHub account](https://github.com/signup) to request a build**, because
each request is a GitHub issue and the download link is posted as a reply to it.

**[Open the configuration picker](https://marlinfirmware.github.io/MarlinWebBuild/)**

1. Sign in to GitHub, then pick a Marlin version, find your printer and pick a build environment.
2. Click **Request build on GitHub** and submit the pre-filled issue.
3. A few minutes later the issue gets a reply with a download link.

Downloads are kept for about two weeks. `bugfix-2.1.x` has the latest fixes and is often more stable than the last release, but it changes daily and recent changes can introduce new bugs.
Releases don't get fixes once published.

## How it works

| Piece | What it does |
|---|---|
| `site/` | Static picker page, deployed to GitHub Pages |
| `.github/workflows/pages.yml` | Every 6 hours, indexes the example configs and their PlatformIO envs for every version, then redeploys the page |
| `.github/ISSUE_TEMPLATE/build.yml` | Issue form the picker pre-fills (`?config=…&env=…`) |
| `.github/workflows/build.yml` | On a `build-request` issue: validate, build with PlatformIO, upload a zip to the `builds` release, reply and close |
| `.github/workflows/prune.yml` | Daily: delete release assets older than 14 days, lock old requests |
| `.github/workflows/version-check.yml` | On demand: build one example per platform for every offered version, to see which still build |
| `tools/versions.py` | Lists the offered versions: `bugfix-2.1.x`, plus the newest tag of each Marlin series with an `lts-<series>` branch, from 2.0.7 on, and its Configurations ref |
| `tools/build_site.py` | Writes `site/versions.json` and one `site/index/<version>.json` per version |
| `tools/matrix.py` | Picks the builds for `version-check.yml` |
| `tools/marlin_index.py` | Maps example configs to envs, using the same `pins.h` lookup as Marlin's `mfenvs` |
| `tools/parse_request.py` | Parses and validates the issue form text |

A build for the same Marlin commit, configuration folder and env is reused rather than rebuilt.
Users are limited to `DAILY_LIMIT` requests per day (see `build.yml`); the repo owner is exempt.

## Setting up your own copy

1. Push this repo to GitHub as a **public** repository (Actions minutes are free for public repos).
2. **Settings → Pages → Build and deployment → Source:** GitHub Actions.
3. **Issues → Labels → New label:** `build-request`. The issue form applies it, and the build workflow only runs on issues with it.
4. **Actions → Pages → Run workflow** to publish the picker for the first time.
5. If you renamed the repo or it's under another account, update the picker URL in `README.md` and
   `.github/ISSUE_TEMPLATE/build.yml` / `config.yml`.

## Testing locally

```sh
python3 tools/build_site.py site --repo you/MarlinWebBuild   # all versions, about 20 seconds
python3 tools/build_site.py site --only bugfix-2.1.x 2.1.2.7  # or just a few
python3 -m http.server -d site
```
