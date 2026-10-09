# Running the pipeline

## Locally

```sh
pip install -r pipeline/requirements.txt
python pipeline/test_pipeline.py                     # unit tests, no network
python pipeline/run.py --period 2026-09 --dry-run    # print the evidence; no LLM call, nothing written
ANTHROPIC_API_KEY=... python pipeline/run.py         # classify the last complete month
python pipeline/check_data.py                        # check data/signals.json against docs/data-format.md
python3 -m http.server -d site 8000                  # preview the site at http://localhost:8000
```

- **Config:** the LLM provider, model, effort and `max_tokens` come from `pipeline/config.toml`. `SIGNALS_LLM_PROVIDER`, `SIGNALS_LLM_MODEL` and `SIGNALS_LLM_EFFORT` override them. Only the `anthropic` provider is implemented.
- **Backfill:** any month before the last complete month is marked `backfill` automatically.
- **Month cap:** a run covers at most 12 months unless `--force` is passed.
- **Exit codes:**

  | Code | Meaning |
  | --- | --- |
  | 0 | Every signal was classified. |
  | 3 | Some signals failed to classify; the rest were written. |
  | 4 | Nothing was written, because no source returned data. |
  | Anything else | A crash. |

- **Run summary:** if `RUN_SUMMARY` names a file, a Markdown summary goes there. It lists failed signals, months with no reading, and sources that failed or were skipped.

## In GitHub Actions

**Update signals** (`.github/workflows/update_signals.yml`) runs on the 10th of each month for the month before. It can also be run by hand with a month range. Data is published with no human in the loop:

1. Classify, then check `data/signals.json` with `check_data.py`. A crash or a run with no data stops here, and nothing is published.
2. Open a data PR. Its description includes the run summary.
3. Post the required `data-check` commit status. A PR opened with `GITHUB_TOKEN` triggers no other workflows, so the job reports the check itself.
4. Turn on auto-merge (squash) and wait for the merge.
5. Start **Deploy site**. A merge made with `GITHUB_TOKEN` doesn't trigger `pages.yml` on its own.

If some signals failed, the job still publishes the rest, then ends red so someone notices.

**Deploy site** (`.github/workflows/pages.yml`) publishes `site/` to GitHub Pages when `site/` or `data/` changes on `main`, and when it is started by the update workflow.

Every action is pinned to a full commit SHA, and `anthropic` is pinned to an exact version. The update job holds the API key and a write token.

### One-time setup (a repository admin)

1. **Environment:** create an environment named `signals`, limited to the `main` branch, and add the secret `ANTHROPIC_API_KEY` to it. A repository-level secret could be read by a workflow on any branch.
2. **Branch protection on `main`:**
   - require a pull request;
   - require review from code owners (CODEOWNERS covers everything except `data/`), with no general approval count;
   - require the status check `data-check`.
3. **Settings → General:** allow auto-merge.
4. **Settings → Actions → General:** allow GitHub Actions to create pull requests. This setting also lets a workflow approve its own PR, which matters once `main` requires review. Approval of code changes should stay with a person; data PRs need none, because `data/` has no code owner.
5. **Settings → Pages:** set the source to GitHub Actions.
6. Optional: the repository variables `SIGNALS_LLM_PROVIDER`, `SIGNALS_LLM_MODEL` or `SIGNALS_LLM_EFFORT` change the LLM without a code change.

### The first backfill

Run **Update signals** by hand with `from` set to six months before launch and `to` left empty. That is 30 LLM calls, and it takes about 10 to 30 minutes, mostly waiting on GDELT and arXiv rate limits.
