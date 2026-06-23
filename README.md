# ThousandEyes GES & ASP SE Hub

Collaboration home for the ThousandEyes Global Enterprise Services and Advanced Services Partner Solution Engineering team.

**Live site:** [https://baroldbonds12.github.io/ThousandEyes_GES_ASP_SE/](https://baroldbonds12.github.io/ThousandEyes_GES_ASP_SE/)

## What's here

- **Landing page** (`docs/`) — project catalog, tech radar feed, contribution links
- **Flagship projects** (`projects/`) — in-repo tools the team maintains
- **Project catalog** (`docs/data/projects.json`) — data-driven index of team work

## Categories

| Category | Focus |
|----------|-------|
| Workproduct Tools | Deliverables, RFP helpers, report generators |
| Workflow Enhancements | CRM, tracking, process automation |
| Discovery Tools | Architecture, assessment, scoping |
| Automation | Scripts, CI, integrations |
| Customer Showcase | Sanitized demos and showcase artifacts |

## Quick links

- [Contributing guide](CONTRIBUTING.md) — includes **"Let's share with the group"** Cursor workflow
- [Share with the group onboarding guide](docs/onboarding/share-with-group-guide.html) — visual walkthrough + sample outputs
- [Propose a project](https://github.com/BaroldBonds12/ThousandEyes_GES_ASP_SE/issues/new?template=new-project.yml)
- [View issues](https://github.com/BaroldBonds12/ThousandEyes_GES_ASP_SE/issues)

## GitHub Pages setup (one-time)

1. Go to **Settings → Pages**
2. Under **Build and deployment**, set **Source** to **GitHub Actions**
3. Push to `main` — the `pages.yml` workflow deploys `/docs` automatically
4. Confirm the site at the URL above

## Local preview

Serve the `docs/` folder with any static server:

```bash
cd docs && python3 -m http.server 8080
# Open http://localhost:8080
```

## RSS feed updates

The `update-feed.yml` workflow runs daily and commits fresh articles to `docs/data/feed.json`. Trigger manually via **Actions → Update Tech Radar Feed → Run workflow**.
