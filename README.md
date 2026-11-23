# Government Data Gap Detector

A public browser tool at **https://coolcode.ca/govdatagaps/** for following a small federal dataset watchlist. Inspect source metadata, sampled download responses and changes across immutable weekly captures. Export a filtered resource CSV or an individual evidence note for follow-up research and access-to-information requests.

<!-- coolcode:guide -->
Choose a dataset to inspect its declared update frequency, metadata dates and sampled download responses. Set an optional metadata-age threshold for your own review, then save an evidence note with source links and timestamps. The first capture is a baseline: a blocked request does not mean a missing file, and an old metadata date does not prove the underlying data is overdue.
<!-- /coolcode:guide -->

## What works

- Search by title, institution, subject or record ID; filter by observation or subject.
- Select any retained capture, compare metadata, resource URLs and check classifications with the previous observation, and review up to six observations in the timeline.
- Review declared source cadence separately from a user-selected 30-, 90-, 180- or 365-day **portal metadata age** threshold. The default is no threshold. No SLA or statutory deadline is inferred.
- Save the filtered resource observations as CSV or save a selected dataset's evidence note. CSV protects spreadsheet formula cells.
- Follow the official catalogue and read the exact raw CKAN response retained for each capture, identified by SHA-256.

## Coverage and dates

`config/watchlist.json` deliberately selects eight federal records: completed ATIP summaries, federal contract disclosures, Canadian sanctions, current and historical land border waits, air border waits, the CSE contracting overview and the Open Government API. This is a curated observatory, not a complete federal audit. Add a real CKAN dataset UUID and label/theme to that file to extend collection.

The first actual capture was taken on **2026-11-23 UTC**. It contains eight records and 84 resource entries, of which 16 URLs were checked. No historical changes are fabricated. The first capture returned 15 reachable responses and one inconclusive HTTP 503 response for the sanctions XML resource; this is an observed response, not evidence that the XML was deleted.

`captured_at` is the start of collection; each resource has its own `checked_at`. `metadata_modified` is the portal's metadata timestamp. `dataset_modified` is the separately supplied publisher date when present. Neither automatically identifies the contents' latest reporting period. Source-declared update frequency is shown verbatim or with a readable label.

## Collection and interpretation

The [official Open Government API guide](https://open.canada.ca/en/access-our-application-programming-interface-api) documents GET requests. The [API catalogue record](https://open.canada.ca/data/en/dataset/2d90548d-50ef-4802-91f8-c59c5cf68251) confirms that public read access requires no key. Collection uses `package_show?id=…` and validates both the HTTP response and CKAN envelope.

For each dataset, two resource URLs are selected deterministically: common downloadable formats first, then English language, then resource ID. A HEAD request follows redirects; a server rejecting HEAD with 405 or 501 receives a GET with `Range: bytes=0-0`. File bodies are not read or archived. This is not content, schema, freshness or malware validation. The other resources remain explicitly **Not checked**. No visitor URL triggers a server request.

| Observation | Meaning |
| --- | --- |
| Reachable | A 2xx/3xx response was received. It may still be an HTML error page. |
| HTTP 404 / 410 | Resource lookup failed at the captured time; investigate the source. |
| Blocked / rate limited | HTTP 401, 403 or 429; availability is not established. |
| Inconclusive | Other errors, timeouts, network failures or unsupported URLs. |
| Catalogue Not Found | A valid CKAN response explicitly returned `Not Found Error`. Generic HTTP 404 pages and network errors never create this state. |

A previously observed catalogue record returning explicit CKAN Not Found is a **lookup change**, not proof that records were destroyed. A resource missing from new metadata likewise does not prove file deletion. Only compared metadata fields, URL additions/removals and response classifications produce timeline changes; body content is not compared.

Source records carry their own licence. Follow the [Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada) where applicable. This independent tool is not an official Government of Canada assessment.

## Scheduled refresh

`.github/workflows/refresh.yml` collects every Monday at 07:17 UTC or manually. No secrets or registration are needed. The collector validates every metadata response before writing a capture; unsuccessful collection leaves prior files untouched. All dated normalized snapshots and raw source responses remain under `web/data/snapshots/`. The manifest points to the latest successful capture. The workflow validates data, runs tests and builds before committing, then dispatches the Pages workflow explicitly because commits using `GITHUB_TOKEN` do not trigger push workflows.

GitHub schedules can be delayed or disabled after inactivity. The app shows the actual capture date. Collection failure is visible in Actions; this app does not send success emails or operate a notification service. Resource failures are valid observations, so they do not by themselves fail the capture.

```sh
python3 scripts/collect.py              # network collection, bounded resource checks
python3 scripts/collect.py --validate   # offline validation
node --test tests/*.test.mjs
python3 -m unittest discover -s tests -v
python3 scripts/build.py                # offline static build
```

Pages deploys successful main builds. `dist/` is generated and untracked. `tests/browser_smoke.py` checks the browser flow at a project subpath in CI.

## Privacy and evidence limits

Searches, thresholds, selections and exports remain in the tab and are not stored. The app fetches its own static captures only; opening official links contacts those providers. CoolCode's shared counter measures aggregate tool opens without query/filter values. No API keys are embedded.

The CSV includes all resource entries in the filtered datasets, including explicit unchecked entries. The text note includes one dataset's current observations and immediately preceding comparison. Evidence notes are research aids, not assertions of legal noncompliance. For example, follow up on the historical border-wait record by asking for its intended publication schedule and any records explaining the observed metadata/resource dates.
