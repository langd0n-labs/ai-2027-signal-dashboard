# GitHub App setup

A `langd0n-labs` organization owner and repository admin must complete this checklist.

## Create and install the App

1. Open **langd0n-labs → Settings → Developer settings → GitHub Apps → New GitHub App**.
2. Use the name `langd0n-ai-signals-updater`. If GitHub reports a collision, add a unique suffix. Keep the name within 34 characters.
3. Set **Homepage URL** to `https://ai-signals.langd0n.com/`.
4. Leave user authorization and callback URLs unset. Disable **Webhook → Active**. This App needs no user authentication.
5. Set only these repository permissions:
   - **Contents: Read and write**.
   - **Pull requests: Read and write**.
   - **Metadata: Read-only**, which GitHub adds automatically.
6. Leave all other permissions unset.
7. Under **Where can this GitHub App be installed?**, select **Only on this account**. Create the App under `langd0n-labs`.
8. Install the App on `langd0n-labs`. Select **Only select repositories**, then select only `ai-2027-signal-dashboard`.
9. Copy the App's **Client ID**. Generate a private key and retain the downloaded PEM securely. Do not commit the key.

## Configure the repository

1. Open **Settings → Environments → signals**. Create `signals` if it does not exist.
2. Restrict deployment branches to the selected branch `main`. Do not allow other branches or tags.
3. Add the environment variable **SIGNALS_APP_CLIENT_ID** with the App's Client ID.
4. Add the environment secret **SIGNALS_APP_PRIVATE_KEY** with the full PEM, including its header, footer, and newlines.
5. Keep **ANTHROPIC_API_KEY** as an environment secret alongside the App settings. Do not use repository-level copies of these secrets.
6. Protect `main`: require a pull request, require code-owner review, and set the general approval count to zero. Keep the `data/` code-owner exception.
7. Require **data-check**, with **GitHub Actions** as the expected source. Keep the actual PR workflow enabled; do not post a substitute success status.
8. Keep the App off all bypass lists. Require code-owner review for workflow and code changes on `main`.
9. Under **Settings → General → Pull Requests**, enable auto-merge and squash merging.
10. Under **Settings → Actions → General → Workflow permissions**, select read-only permissions. The App does not need the setting that lets `GITHUB_TOKEN` create or approve PRs.
11. Under **Settings → Pages**, set **Source** to **Deploy from a branch**, branch `gh-pages`, folder `/ (root)`. Run **Deploy site** first so the branch has the site at its root. Keep the custom domain `ai-signals.langd0n.com` (`site/CNAME` publishes it to the branch) and **Enforce HTTPS**. Under **Settings → Environments → github-pages → Deployment branches and tags**, add `gh-pages`; GitHub's Pages build deploys from that branch, and the environment otherwise allows only `main`.

The update job checks that both App settings are present before classification. Authentication happens after classification and local validation. An incorrect Client ID, key, installation, or permission can therefore fail publication after LLM calls have completed. The token covers only this repository, with Contents and Pull requests write permissions. The action revokes the token after the job.

## Verify after merge and setup

1. In a test PR, introduce invalid data, such as an invalid status. Confirm `data-check` fails and blocks merge. Close the test PR without merging it.
2. Run **Update signals** on `main` for one month. Set both `from` and `to` to that month. Use a month that needs an update.
3. Check that the App-created PR targets `main` and the normal **data-check** workflow runs without approval.
4. Confirm the valid automated data PR passes `data-check` and auto-merges with squash.
5. Confirm the merge's push to `main` starts **Deploy site** and publishes the updated data.

AI-Attribution: AI-G
