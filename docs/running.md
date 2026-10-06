# Running the pipeline

## Locally

```sh
pip install -r pipeline/requirements.txt
python pipeline/test_pipeline.py                     # unit tests, no network
python pipeline/run.py --period 2026-09 --dry-run    # print the evidence; no LLM call, nothing written
ANTHROPIC_API_KEY=... python pipeline/run.py         # classify the last complete month
python3 -m http.server -d site 8000                  # preview the site at http://localhost:8000
```

The LLM provider, model and effort come from `pipeline/config.toml`. The environment variables `SIGNALS_LLM_PROVIDER`, `SIGNALS_LLM_MODEL` and `SIGNALS_LLM_EFFORT` override them. Only the `anthropic` provider is implemented. Another one is a new branch in `classify_signals.py`.

## In GitHub Actions

- **Update signals** (`.github/workflows/update_signals.yml`) runs on the 5th of each month for the month before. It can also be run by hand with a month range and the backfill flag. It opens a pull request with the new data. It never pushes to `main`.
- **Deploy site** (`.github/workflows/pages.yml`) publishes `site/` to GitHub Pages when `site/` or `data/` changes on `main`.

### One-time setup (a repository admin)

1. Add the secret `ANTHROPIC_API_KEY` under Settings → Secrets and variables → Actions.
2. Optional: set the repository variables `SIGNALS_LLM_PROVIDER`, `SIGNALS_LLM_MODEL` or `SIGNALS_LLM_EFFORT` to change the LLM without a code change.
3. Under Settings → Actions → General, allow GitHub Actions to create pull requests.
4. Under Settings → Pages, set the source to GitHub Actions.

### The first backfill

Run **Update signals** by hand with `from` = six months before launch, `to` = the last complete month, and `backfill` checked. A six-month run makes 30 LLM calls and takes about 10 to 30 minutes, mostly waiting on GDELT and arXiv rate limits.
