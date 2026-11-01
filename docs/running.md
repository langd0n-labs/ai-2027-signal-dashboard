# Running the pipeline

## Locally

```sh
pip install -r pipeline/requirements.txt
python pipeline/test_pipeline.py                     # unit tests, no network
python pipeline/run.py --period 2026-09 --dry-run    # print the evidence; no LLM call, nothing written
SIGNALS_LLM_API_KEY=... python pipeline/run.py       # classify the last complete month (Anthropic, per config.toml)
SIGNALS_LLM_PROVIDER=openai SIGNALS_LLM_MODEL=gpt-5 SIGNALS_LLM_API_KEY=... python pipeline/run.py   # any OpenAI-compatible API
SIGNALS_LLM_PROVIDER=ollama SIGNALS_LLM_MODEL=qwen2.5:7b python pipeline/run.py   # same, with a local model and no key
python pipeline/check_data.py                        # check data/signals.json against docs/data-format.md
python3 -m http.server -d site 8000                  # preview the site at http://localhost:8000
```

- **Config:** the LLM provider, model, effort and `max_tokens` come from `pipeline/config.toml`. `SIGNALS_LLM_PROVIDER`, `SIGNALS_LLM_MODEL`, `SIGNALS_LLM_EFFORT` and `SIGNALS_LLM_BASE_URL` override them. Three providers are implemented:

  | Provider | Covers | Key |
  | --- | --- | --- |
  | `anthropic` | Claude | `SIGNALS_LLM_API_KEY` (or `ANTHROPIC_API_KEY`) |
  | `openai` | Any OpenAI-compatible API, chosen by `SIGNALS_LLM_BASE_URL`: OpenAI (the default, `https://api.openai.com/v1`), Gemini (`https://generativelanguage.googleapis.com/v1beta/openai`), Groq (`https://api.groq.com/openai/v1`), OpenRouter (`https://openrouter.ai/api/v1`) and others. The model must support JSON-schema structured output. | `SIGNALS_LLM_API_KEY` |
  | `ollama` | A local model | none |

  The `ollama` provider needs [Ollama](https://ollama.com) running with the model pulled, and reads `OLLAMA_HOST` (default `localhost:11434`).
- **Backfill:** any month before the last complete month is marked `backfill` automatically.
- **Month cap:** a run covers at most 12 months unless `--force` is passed.
- **Exit codes:**

  | Code | Meaning |
  | --- | --- |
  | 0 | Every signal was classified. |
  | 3 | Incomplete: some signals failed to classify or had no source data. The rest were written. |
  | 4 | Nothing was written, because no source returned data. |
  | Anything else | A crash. |

- **Run summary:** if `RUN_SUMMARY` names a file, a Markdown summary goes there. It lists failed signals, months with no reading, and sources that failed or were skipped.

## In GitHub Actions

**Update signals** (`.github/workflows/update_signals.yml`) runs on the 10th of each month for the month before. It can also be run by hand with a month range. Data is published with no human in the loop:

1. Check the App settings before any classification calls.
2. Classify, then validate `data/signals.json` with `check_data.py`. A crash or no source data stops publication.
3. Create a repository-scoped App installation token, push the data branch, and open a PR against `main`.
4. Enable squash auto-merge. The normal **data-check** workflow validates the PR. The update job waits up to ten minutes for merge.
5. The App-authenticated merge triggers **Deploy site** through its push to `main`.

If some signals fail or have no source data, the job publishes the remaining results and includes a partial summary. It then ends red. If no files change, it opens no PR.

**data-check** (`.github/workflows/data-check.yml`) runs pipeline tests on every PR, including automated data PRs. It also runs `pipeline/check_data.py` when the PR changes `data/`. Invalid data blocks merge.

**Deploy site** (`.github/workflows/pages.yml`) publishes `site/` when `site/` or `data/` changes on `main`. It also supports manual dispatch.

Every action uses a full commit SHA. The `anthropic` dependency uses an exact version. The built-in `GITHUB_TOKEN` has only `contents: read`.

### One-time setup (a repository admin)

Follow the [GitHub App setup checklist](github-app-setup.md). It covers the App, the `signals` environment, branch protection, auto-merge, and Pages.

### Trust boundary

Restrict the `signals` environment to `main`. Keep the LLM key (`ANTHROPIC_API_KEY`, or `LLM_API_KEY` for another provider), `SIGNALS_APP_CLIENT_ID`, and `SIGNALS_APP_PRIVATE_KEY` there. The App private key is available only to the configuration preflight and token action. The classifier shell receives no App credential. The token is created after classification and local validation to avoid its one-hour expiry during long runs. Only the publication step receives the token. The token action revokes it after the job.

Protect the App credential and workflow code on `main` with code-owner review. The App has no bypass permission. Data PRs need the required `data-check` from GitHub Actions. The update workflow does not post a substitute success status. Repository writers remain trusted to propose data for publication. Code changes require code-owner review; `data/` has no code owner.

GitHub creates approval-required workflows for PRs opened, synchronized, or reopened with `GITHUB_TOKEN`. App installation tokens avoid that approval requirement. See [GitHub's token documentation](https://docs.github.com/en/actions/concepts/security/github_token).

### Switching the LLM provider

The workflow passes `secrets.LLM_API_KEY`, falling back to `secrets.ANTHROPIC_API_KEY`, so the default Anthropic setup needs no change. To switch, in the `signals` environment add the secret `LLM_API_KEY` for the new provider, and set the repository variables `SIGNALS_LLM_PROVIDER` (`anthropic` or `openai`), `SIGNALS_LLM_MODEL`, and for `openai` `SIGNALS_LLM_BASE_URL`. `SIGNALS_LLM_EFFORT` is optional.

### The first backfill

Run **Update signals** by hand with `from` set to six months before launch and `to` left empty. That is 30 LLM calls, and it takes about 10 to 30 minutes, mostly waiting on GDELT and arXiv rate limits.
