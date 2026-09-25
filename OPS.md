# OPS.md

Read `README.md` first.

## Work in issues and pull requests

1. Open or pick an issue before you start a change.
2. Make the change on a branch. Name the branch after the issue, for example `12-landing-page`.
3. Open a pull request that references the issue.
4. A maintainer reviews the pull request before merge. Do not push directly to `main`.

## Keep the repository public-safe

This repository is public. Everything you commit is visible to anyone.

- Do not commit an email address other than a GitHub noreply address.
- Do not commit a local file path, a private note, or a raw private log.
- Do not commit a secret. Put API keys only in GitHub Actions secrets. Keep `.env` files out of Git.
- Cite every data source that the pipeline uses. Follow each source's terms of use.

## Mark AI involvement

State how AI contributed to each change. Use one level from https://langd0n.com/ai-attribution:

- `AI-A`: AI assisted with suggestions or research.
- `AI-E`: AI enhanced work that a person wrote.
- `AI-C`: a person and AI wrote the work together.
- `AI-G`: AI generated the work, directed and checked by a person.

Put the level in the commit message as `AI-Attribution: <level>`. Put it in the pull request description too.

## Keep choices configurable

- Do not hardcode an LLM provider or a model name in code. Read it from configuration.
- Change the format of `data/signals.json` only in a pull request that also updates the site.
