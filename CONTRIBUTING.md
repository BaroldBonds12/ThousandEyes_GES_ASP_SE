# Contributing to the SE Hub

Thank you for helping build the GES & ASP SE collaboration hub. This repo is **public** — follow the rules below before opening a PR.

## Guided workflow (Cursor)

SEs using Cursor can start a chat with:

> **Let's share with the group**

That loads the **share-with-group** skill (`.cursor/skills/share-with-group/SKILL.md`): category intake → description → hub preview mockup → iteration → publish gate → catalog PR → GitHub Discussion + Webex announcement.

You can also `@share-with-group` to force-load the skill.

## Public-safe content policy

**Do not include:**

- Internal hostnames or private deployment URLs
- API tokens, `.env` values, passwords, or customer credentials
- Customer names, account IDs, or identifiable deal data
- Screenshots containing PII or confidential information

**Do include:**

- Public GitHub repo links
- Sanitized demo HTML or anonymized architecture diagrams
- README descriptions of what a tool does and how to run it locally

## Adding a project

### Option A — Propose via issue

Use the [New Project template](https://github.com/BaroldBonds12/ThousandEyes_GES_ASP_SE/issues/new?template=new-project.yml). A maintainer will help you open a PR.

### Option B — Pull request

1. Edit [`docs/data/projects.json`](docs/data/projects.json) and add an entry:

```json
{
  "id": "my-tool-slug",
  "name": "My Tool Name",
  "category": "automation",
  "status": "active",
  "description": "One or two sentences describing what it does.",
  "repo": "BaroldBonds12/ThousandEyes_GES_ASP_SE/tree/main/projects/my-tool",
  "demo": null,
  "tags": ["tag1", "tag2"],
  "featured": false,
  "maintainers": ["@github-username"]
}
```

2. If the project lives in this repo, add it under `projects/my-tool/`
3. Open a PR with a clear description

### Categories

| Value | Use for |
|-------|---------|
| `workproduct` | RFP tools, report generators, deliverable helpers |
| `workflow` | CRM, tracking, team process tools |
| `discovery` | Architecture, assessment, scoping tools |
| `automation` | Scripts, integrations, CI helpers |
| `showcase` | Sanitized customer demos and showcase artifacts |

### Status values

- `active` — maintained and usable
- `beta` — working but evolving
- `archived` — no longer maintained (kept for reference)

## Adding an RSS feed

Edit [`feeds.config.json`](feeds.config.json) at the repo root:

```json
{
  "name": "Source Name",
  "url": "https://example.com/feed.xml",
  "topics": ["ai", "networking"]
}
```

Valid topics: `ai`, `networking`, `observability`, `monitoring`, `development`

After merge, the daily workflow picks up new feeds automatically. You can also trigger **Update Hub Feeds** manually from Actions.

## In-repo project guidelines

- Include a `README.md` with setup and usage
- Add `.env.example` (never commit `.env`)
- Keep dependencies pinned where practical
- No hardcoded credentials

## Code review

Maintainers check for:

1. No secrets or internal URLs in diff
2. Valid JSON in `projects.json`
3. Accurate category and description
4. README present for in-repo projects
