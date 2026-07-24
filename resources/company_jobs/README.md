# Local company job catalog

`agency_agents.catalog.json` is a normalized, runtime-local catalog generated from the MIT-licensed
[`msitarzewski/agency-agents`](https://github.com/msitarzewski/agency-agents) repository at pinned
commit `86a6695d4cee1c9720e2be4fd8ae007f9b6d96ae`.

The catalog contains all 245 role files across the 17 source divisions. Every entry remains marked
`experimental` until an EmploAI review and representative readiness test promote that specific
template. Suggested role material never grants tools, credentials, authority, or employee readiness.

Regenerate deliberately:

```powershell
python scripts/import_agency_agents.py <pinned-source-checkout> resources/company_jobs/agency_agents.catalog.json
```

Runtime use never contacts GitHub. Source version and license attribution are retained in every
template and in `AGENCY_AGENTS_LICENSE.txt`.
