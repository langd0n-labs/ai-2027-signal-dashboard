# Data sources

Task 1 of issue #3: the sources for each signal, and whether each one can return data for a past date. Every source below can, so every signal can be backfilled. All of them are free and need no API key. Checked on 2026-10-05.

| Source | Signals | Past dates | What the pipeline takes | Terms and notes |
| --- | --- | --- | --- | --- |
| [Federal Register API](https://www.federalregister.gov/developers/documentation/api/v1) | Policy | Yes, by publication date | Count of documents matching "artificial intelligence" this month and last month, top titles by relevance | U.S. government work, public domain. |
| [FRED](https://fred.stlouisfed.org/) (Federal Reserve Bank of St. Louis) | Labor market, Economy | Yes, full history | The last 13 observations on or before the end of the month for each series in `pipeline/config.toml` | Series are revised after release, so a backfilled month sees revised numbers. Cite FRED and the original source: BLS for every series except initial jobless claims (ICSA), which come from the Department of Labor. |
| [arXiv API](https://info.arxiv.org/help/api/index.html) | Technology | Yes, by submission date | Number of `cs.AI` submissions this month and last month | Ask for one request every 3 seconds. Acknowledgement: "Thank you to arXiv for use of its open access interoperability." `max_results=0` returns HTTP 500, so the pipeline asks for one result and reads the total. |
| [Epoch AI, Notable AI Models](https://epoch.ai/data/notable-ai-models) | Technology | Yes, by publication date | Models published this month and last month, with training compute | CC BY 4.0. Cite Epoch AI. |
| [GDELT DOC 2.0 API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) | Public opinion | Yes, tested back to March 2026 | Daily average tone and share of coverage for "artificial intelligence" in English-language news, averaged per month | Allows one request every 5 seconds and throttles bursts even at 20-second gaps. After one failure the pipeline skips GDELT for the rest of the run instead of stalling. |
| [Hacker News Algolia API](https://hn.algolia.com/api) | All five | Yes, by creation time | The most-discussed story headlines for each query in the config, with links | Headlines only. Per-month story totals are not comparable: the index holds 368,063 stories for March 2026 and 29,607 for April, so counts are not used as a measure of attention. |

## Sources considered and not used

- **Layoffs.fyi**: no public API, and its data sits in an Airtable view. Scraping it may break its terms.
- **Google Trends**: no official API.
- **Congress.gov API**: needs an API key. Worth adding for policy if a key is available.

## Answers to the open questions in issue #3

- **Period length**: monthly. Most FRED series are monthly or quarterly, so a weekly period would mostly repeat the same numbers.
- **A signal with no past data**: every signal has at least one source with past data. If every source fails for a month, the pipeline writes no entry and the site shows "no reading" for that month.
