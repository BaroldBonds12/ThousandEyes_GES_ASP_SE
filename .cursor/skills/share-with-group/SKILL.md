---
name: share-with-group
description: >-
  Guides GES/ASP SEs through sharing a project on the team hub repo: category
  intake, description, HTML catalog mockup review, iteration, publish gate,
  projects.json PR, GitHub Discussion post, and Webex announcement. Use when
  the user says "Let's share with the group", "share with the group", "publish
  to the hub", "add to the SE hub", or wants to contribute a tool or showcase
  to ThousandEyes_GES_ASP_SE.
---

# Share with the group (SE Hub)

Interactive workflow for contributing to **ThousandEyes_GES_ASP_SE** — the public GES & ASP SE collaboration hub. Mirrors the CRM **production-patch** rhythm: intake → mockup → iterate → publish gate → implement → announce.

**Repo:** https://github.com/BaroldBonds12/ThousandEyes_GES_ASP_SE  
**Live site:** https://baroldbonds12.github.io/ThousandEyes_GES_ASP_SE/

Do **not** edit `projects.json`, open PRs, or draft announcements until the user approves the mockup and passes the publish gate.

---

## Phase 0 — Start

When the user opens with **"Let's share with the group"** (or similar):

1. Acknowledge share mode briefly.
2. Do **not** edit the hub repo yet.
3. Proceed immediately to Phase 1.

---

## Phase 1 — Category

Ask the user which **hub category** best fits (use `AskQuestion` when available):

| ID | Label | Use for |
|----|-------|---------|
| `workproduct` | Workproduct | RFP tools, report generators, deliverable helpers |
| `workflow` | Workflow | Tracking, team process, CRM-style tools |
| `discovery` | Discovery | Architecture, assessment, scoping tools |
| `automation` | Automation | Scripts, integrations, CI helpers |
| `showcase` | Customer Showcase | Sanitized demos, HTML reports, anonymized artifacts |

Also ask (same turn or next):

- **Project name** (display name for the catalog)
- **In-repo or link-only?** — flagship tool under `projects/` vs external repo link only

Record selections before Phase 2.

---

## Phase 2 — Description intake

Collect a **public-safe** summary. Ask explicitly:

1. **What does it do?** (1–2 sentences)
2. **What problem does it solve for SEs?** (1–2 sentences)
3. **Tags** — 3–5 keywords (e.g. `rfp`, `architecture`, `thousandeyes-api`)
4. **Maintainer** — GitHub username (e.g. `@BaroldBonds12`)
5. **Status** — `active`, `beta`, or `archived`
6. **Featured?** — pin on hub overview (`true` / `false`; default `false` unless user asks)

Run the **public-safe checklist** (see [reference.md](reference.md)). If anything fails, ask the user to rephrase before mockups.

---

## Phase 3 — Scope lock

Summarize back:

- Category, name, status, featured
- Description (what + problem solved)
- In-repo path or external repo URL
- Tags and maintainer
- Explicit **out of scope** for this share (e.g. "no source upload, catalog entry only")

Ask: *"Anything else before I draft the hub preview?"*

Wait for confirmation or edits before Phase 4.

---

## Phase 4 — Hub mockup

Create a **standalone HTML preview** showing how the entry will look on the dashboard.

**Location:** `docs/share-previews/<slug>-preview.html`

**Design:** Match the live hub — dark dashboard, **project card** + **featured task row**. Link `../css/styles.css`.

**Banner note on preview:** *Share preview — not on the live hub yet.*

Also draft in chat (markdown):

- **`projects.json` entry** (exact JSON block)
- **GitHub Discussion post** (title + body) — see [reference.md](reference.md)

After writing the preview file:

1. Give the user the path and how to open it locally.
2. Paste the JSON entry and discussion draft in chat.
3. Ask: *"Please review the preview. What tweaks do you want?"*

**Do not implement catalog changes until mockup is approved** (unless user explicitly skips preview for a metadata-only tweak — confirm in writing).

---

## Phase 5 — Mockup iteration

Apply user tweaks to preview HTML and chat drafts only. Re-share paths after each round.

When the user signals approval (*"looks good"*, *"approved"*, *"ready to publish"* for the preview), proceed to Phase 6.

---

## Phase 6 — Publish gate (mandatory)

Before any repo edits or PR:

1. List final catalog entry (bullets).
2. Re-run public-safe checklist verbally.
3. Ask: **"Are you ready to publish this to the hub?"**
4. Then ask: **"Anything else before I update the repo and prep the announcement?"** (required — do not skip)

Only proceed on explicit **yes** to publish. If the user adds scope, return to Phase 4 or 5.

---

## Phase 7 — Implement

1. Add or update entry in `docs/data/projects.json` (valid JSON, unique `id` slug).
2. If **in-repo flagship:** add or update `projects/<slug>/` with README (and code if provided).
3. Keep diffs minimal — no unrelated hub changes.
4. Open or describe PR: title `Add hub entry: <Project Name>`, body with summary + public-safe confirmation.

Tell the user:

- Merge to `main` updates GitHub Pages within a few minutes (hard refresh if cached).
- Branch deploy source: **main** / **docs**.

---

## Phase 8 — Announce

After publish (or when PR is ready and user confirms merge):

1. **GitHub Discussion** — provide final title + body; link to hub catalog URL and repo path. Prompt user to post in repo Discussions (enable Discussions in repo Settings if missing). Suggested category: **Show and tell** or **Ideas** (see [reference.md](reference.md)).

2. **Webex** — provide copy-paste message for the **GES ASP SE Webex space**:

   ```
   📢 New on the SE Hub: [Project Name]

   [One-line what it does]

   🔗 Hub: https://baroldbonds12.github.io/ThousandEyes_GES_ASP_SE/
   🔗 Repo: [link]

   [Optional: ask for feedback / collaborators]
   ```

3. Ask the user to confirm when Discussion is posted and Webex message is sent.

---

## Rules of engagement

| Do | Don't |
|----|--------|
| Ask category + description first | Edit `projects.json` on trigger phrase |
| HTML hub preview before publish | Merge or push before mockup approval |
| Public-safe checklist every time | Include internal URLs, tokens, customer names |
| Publish gate + "anything else?" | Skip Discussion / Webex prompt after publish |
| One project per share flow | Batch unrelated tools without user consent |

---

## Optional: dedicated chat

Suggest a **new chat** with *"Let's share with the group"* for a clean intake. User can `@share-with-group` to force-load this skill.

## Deep reference

Templates, JSON schema, discussion format, Webex copy, preview conventions: [reference.md](reference.md)
