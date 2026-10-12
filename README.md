# Open Tech CFPs

Calls for papers at tech conferences and meetups, collected from
[Sessionize](https://sessionize.com) and refreshed every 3 hours.

- **Browse:** <https://1kevgriff.github.io/OpenTechCFPs/>
- **Point an LLM at it:** <https://1kevgriff.github.io/OpenTechCFPs/llms.txt>

## Use the data

Everything is a static file. No key, no rate limit, CORS open.

| What | URL (under `https://1kevgriff.github.io/OpenTechCFPs/`) |
| --- | --- |
| Guide for LLMs, lists every endpoint | `llms.txt` |
| Open CFPs | `api/open.json`, `api/open.md` |
| CFPs that have not opened yet | `api/upcoming.json`, `api/upcoming.md` |
| Closed, event still ahead | `api/closed.json`, `api/closed.md` |
| Everything current | `api/active.json` |
| By tag | `api/by-tag/<tag>.json`, `.md` |
| By country (ISO alpha-2, lowercase) | `api/by-country/<cc>.json`, `.md` |
| Online events | `api/online.json`, `api/online.md` |
| Tag and country indexes | `api/tags.json`, `api/countries.json` |
| Past events by year | `api/archive/<year>.json` |
| Record schema | `schema.json` |

Paths are stable: new ones may appear, existing ones are not renamed.

`cfp_close_utc` is the exact deadline. `status` (`open`, `upcoming`, `closed`) is
computed when the files are built; each file carries `generated_at`, so recompute
from `cfp_close_utc` if you need it to the minute.

The raw records also live in this repo under `data/sessionize/`: `active.json` for
events still ahead, `archive/<year>.json` for the rest.

## Tags

Sessionize has no tags, so they come from keyword rules in [`tags.yml`](tags.yml).
Missing a technology, or seeing a wrong match? Edit that file and open a pull
request. Events that match nothing are kept and listed as `untagged`.

## Run it locally

Needs [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pytest
uv run opentechcfps update --limit 25   # fetch a few events into data/
uv run opentechcfps build-site          # write _site/
uv run python -m http.server -d _site
```

`update` fetches open and upcoming events plus anything new, at one request per
second. `update --all` refetches every event Sessionize has ever listed.
`retag` re-applies `tags.yml` to archived events.

## How it works

1. Read `sessionize.com/sitemap/events.xml` (every event, with a priority that
   marks the live ones).
2. Fetch each live or new event page and read its dates, location and perks.
3. Tag it, resolve the country, and merge it into `data/`.
4. Build the site and API files and deploy them to GitHub Pages.

Adding another source means implementing the small `Source` protocol in
`src/opentechcfps/sources/base.py`.

## License

Code is [MIT](LICENSE). The compiled data is [CC BY 4.0](LICENSE-DATA).
