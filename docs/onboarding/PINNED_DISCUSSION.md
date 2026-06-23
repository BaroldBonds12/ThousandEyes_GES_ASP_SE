# Pinned Discussion — copy/paste into GitHub

**How to publish:** Repo → **Discussions** → **New discussion** → paste below → Category: **Announcements** or **General** → Post → **Pin discussion** (maintainers only).

**Visual guide:** https://baroldbonds12.github.io/ThousandEyes_GES_ASP_SE/onboarding/share-with-group-guide.html

---

## Title

```
📌 How to share a project with the group (Cursor & Claude guide)
```

---

## Body (paste from here)

# How to share a project with the GES & ASP SE Hub

This pinned post explains how to use the **Share with the group** agent workflow to publish tools, workflows, and showcase artifacts to our team hub — without exposing internal URLs or customer data.

**Live hub:** https://baroldbonds12.github.io/ThousandEyes_GES_ASP_SE/  
**Repo:** https://github.com/BaroldBonds12/ThousandEyes_GES_ASP_SE

**Visual walkthrough with sample outputs:**  
https://baroldbonds12.github.io/ThousandEyes_GES_ASP_SE/onboarding/share-with-group-guide.html

---

## What is "Share with the group"?

A guided workflow (mirroring our CRM patch process) that walks you through:

1. **Category** — Workproduct, Workflow, Discovery, Automation, or Customer Showcase  
2. **Description** — what it does and what problem it solves (public-safe)  
3. **Hub preview mockup** — HTML preview of your catalog card before anything goes live  
4. **Iteration** — feedback rounds until you approve  
5. **Publish gate** — explicit "ready to publish?" confirmation  
6. **Catalog PR** — entry added to `docs/data/projects.json`  
7. **Announce** — GitHub Discussion post + message for the **GES ASP Webex space**

### Trigger phrase

Open a **new chat** and say:

> **Let's share with the group**

In Cursor you can also type `@share-with-group` to load the skill directly.

---

## Connect the repo — Cursor

### 1. Clone the hub repo

```bash
git clone https://github.com/BaroldBonds12/ThousandEyes_GES_ASP_SE.git
cd ThousandEyes_GES_ASP_SE
```

### 2. Open in Cursor

- **File → Open Folder…** → select the cloned `ThousandEyes_GES_ASP_SE` folder  
- Or from terminal: `cursor .` (if Cursor CLI is installed)

### 3. Skills load automatically

| Path | Purpose |
|------|---------|
| `.cursor/skills/share-with-group/SKILL.md` | Main workflow |
| `.cursor/skills/share-with-group/reference.md` | Templates & checklists |
| `.cursor/rules/share-with-group.mdc` | Auto-hints on trigger phrase |

No extra Cursor settings required — skills in `.cursor/skills/` are discovered when the repo is your workspace root.

### 4. Start sharing

1. New Agent chat  
2. Say **"Let's share with the group"**  
3. Follow the prompts (category → description → preview → approve → publish)

**Tip:** Use a dedicated chat per project so context stays clean.

---

## Connect the repo — Claude

### Option A — Claude Code (recommended)

1. Clone the repo (same `git clone` as above)  
2. Open the folder in Claude Code  
3. Claude reads **`CLAUDE.md`** at the repo root, which points to the share workflow  
4. Say **"Let's share with the group"**

### Option B — Claude.ai Project

1. Create a **Project** in Claude.ai  
2. Add **Project knowledge**: `CLAUDE.md`, `.cursor/skills/share-with-group/SKILL.md`, `.cursor/skills/share-with-group/reference.md`, `CONTRIBUTING.md`  
3. Project instructions:

   ```
   When I say "Let's share with the group", follow the share-with-group skill:
   intake category and description, create hub preview mockup, iterate until approved,
   confirm publish gate, then update projects.json and draft Discussion + Webex announcement.
   Never include internal URLs, tokens, or customer data.
   ```

4. Start a chat with **"Let's share with the group"**

### Option C — Paste the skill manually

Open [SKILL.md](https://github.com/BaroldBonds12/ThousandEyes_GES_ASP_SE/blob/main/.cursor/skills/share-with-group/SKILL.md) and paste into any Claude chat with: *"Follow this workflow for the rest of this conversation."*

---

## Sample workflow outputs

Visual examples: https://baroldbonds12.github.io/ThousandEyes_GES_ASP_SE/onboarding/share-with-group-guide.html

**Sample screenshots** (after Pages deploy):

![Category intake](https://baroldbonds12.github.io/ThousandEyes_GES_ASP_SE/onboarding/sample-cursor-intake.png)

![Hub preview mockup](https://baroldbonds12.github.io/ThousandEyes_GES_ASP_SE/onboarding/sample-hub-preview.png)

| Phase | What you'll see |
|-------|-----------------|
| Intake | Category picker + project name + description questions |
| Scope lock | Bulleted summary before mockup |
| Hub preview | HTML file in `docs/share-previews/` showing your catalog card |
| Publish gate | "Ready to publish?" + public-safe checklist |
| Announce | Draft GitHub Discussion + Webex copy-paste block |

---

## Public-safe content (required)

- No internal hostnames or private URLs  
- No API tokens or credentials  
- No customer names or identifiable deal data  

[CONTRIBUTING.md](https://github.com/BaroldBonds12/ThousandEyes_GES_ASP_SE/blob/main/CONTRIBUTING.md)

---

## After you publish

1. Merge PR to `main` → hub updates in ~2–10 min  
2. Post a **Discussion** (Show and tell)  
3. Share to **GES ASP Webex space**

---

## Pin instructions (maintainers)

After posting: **⋯** → **Pin discussion**.
