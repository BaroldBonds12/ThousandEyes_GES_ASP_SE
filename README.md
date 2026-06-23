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
2. Under **Build and deployment**, set **Source** to **GitHub Actions** (not branch deploy)
3. Push to `main` — `pages.yml` deploys `/docs` with cache-busted CSS/JS
4. Watch **Actions → Deploy GitHub Pages** for the green check (~1–3 min)

### How fast do changes go live?

| Layer | Typical delay | What we did |
|-------|----------------|-------------|
| GitHub Actions build | 1–3 minutes | `pages.yml` runs on every `docs/` push; cancel-in-progress avoids queue pile-up |
| CDN cache (HTML) | Up to **10 minutes** | GitHub Pages sets `Cache-Control: max-age=600` — not configurable on free Pages |
| Browser cache | Varies | Actions inject `?v=<commit>` on CSS/JS each deploy; JSON fetched with `no-cache` |

**Tips for faster feedback:**

- **Local preview** (instant): `cd docs && python3 -m http.server 8080`
- **Know when deploy finished:** Actions tab → Deploy GitHub Pages → green ✓
- **After deploy:** hard refresh once (`Cmd+Shift+R`) if HTML still looks stale
- **Footer** shows `deploy: abc1234` (commit short SHA) when Actions deploy is active

If Pages source is still **Deploy from branch**, switch to **GitHub Actions** so cache-busting and deploy status work.

## Local preview

Serve the `docs/` folder with any static server:

```bash
cd docs && python3 -m http.server 8080
# Open http://localhost:8080
```

## RSS feed updates

The `update-feed.yml` workflow runs daily and commits fresh articles to `docs/data/feed.json`. Trigger manually via **Actions → Update Tech Radar Feed → Run workflow**.
