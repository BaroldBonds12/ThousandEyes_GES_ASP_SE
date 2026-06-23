# Share with the group — reference

## Hub catalog schema

Each entry in `docs/data/projects.json`:

```json
{
  "id": "kebab-case-slug",
  "name": "Display Name",
  "category": "workproduct",
  "status": "active",
  "description": "What it does and what problem it solves — public-safe, 1–2 sentences.",
  "repo": "BaroldBonds12/ThousandEyes_GES_ASP_SE/tree/main/projects/my-tool",
  "demo": null,
  "tags": ["tag1", "tag2"],
  "featured": false,
  "maintainers": ["@github-username"]
}
```

| Field | Rules |
|-------|--------|
| `id` | Unique kebab-case slug |
| `category` | `workproduct`, `workflow`, `discovery`, `automation`, `showcase` |
| `status` | `active`, `beta`, `archived` |
| `repo` | GitHub path or full URL; no private hostnames |
| `demo` | Public demo URL or `null` |
| `featured` | `true` only for pinned overview items |

---

## Public-safe checklist

Before mockup and again at publish gate:

- [ ] No internal hostnames (e.g. private CRM URLs)
- [ ] No API tokens, `.env` values, or credentials
- [ ] No customer names, account IDs, or identifiable deal data
- [ ] No screenshots with PII
- [ ] Description accurate for a **public** audience
- [ ] Demo links (if any) are publicly reachable

---

## Preview file conventions

| Item | Value |
|------|--------|
| Path | `docs/share-previews/<slug>-preview.html` |
| Slug | kebab-case from project name |
| CSS | Link `../css/styles.css` or inline hub tokens |
| Content | Project card + optional featured row matching live hub |
| Banner | *Share preview — not on the live hub yet* |

Open locally:

```bash
cd docs/share-previews
python3 -m http.server 8080
# http://localhost:8080/<slug>-preview.html
```

---

## GitHub Discussion template

**Enable Discussions:** Repo → Settings → General → Features → Discussions.

Suggested **title:**

```
[Workproduct] Questionnaire Automator — local RFP helper
```

Pattern: `[Category] Project Name — short hook`

**Body template:**

```markdown
## Summary

[What it does — 2–3 sentences]

## Problem it solves

[Why SEs should care]

## Links

- **Hub catalog:** https://baroldbonds12.github.io/ThousandEyes_GES_ASP_SE/
- **Repo / path:** [link]
- **Demo:** [link or N/A]

## Try it

[1–3 bullet steps to get started]

## Feedback

Questions, ideas, or contributions welcome — reply here or open an issue.
```

Pick category: **Show and tell** (shipping something) or **General** (early idea).

**New discussion URL:**  
https://github.com/BaroldBonds12/ThousandEyes_GES_ASP_SE/discussions/new

---

## Webex announcement template

Post to the **GES ASP SE Webex space** (team space — user selects the correct space manually):

```
📢 New on the SE Hub: [Project Name]

[One sentence — what it does and what it solves]

🔗 Live hub: https://baroldbonds12.github.io/ThousandEyes_GES_ASP_SE/
🔗 GitHub: [repo or PR link]

[Optional: "Looking for feedback on …" or "Ping me if you want a walkthrough."]
```

---

## PR checklist

- [ ] `docs/data/projects.json` valid JSON
- [ ] Unique `id`
- [ ] Preview removed or kept in `docs/share-previews/` (optional artifact)
- [ ] README in `projects/<slug>/` if in-repo
- [ ] CONTRIBUTING public-safe rules satisfied

**PR title:** `Add hub entry: <Project Name>`

---

## Pages deploy reminder

After merge to `main`:

- Source: **Deploy from branch** → `main` / `/docs`
- Allow 2–10 minutes; hard refresh (`Cmd+Shift+R`) if cached

---

## Related hub files

| File | Purpose |
|------|---------|
| `CONTRIBUTING.md` | Team contribution policy |
| `.github/ISSUE_TEMPLATE/new-project.yml` | Issue-based intake (alternative) |
| `docs/data/projects.json` | Catalog source of truth |
| `projects/` | In-repo flagship tools |
