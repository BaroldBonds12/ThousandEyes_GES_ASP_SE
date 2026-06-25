---
name: html-deck
description: >-
  Guides SEs through building Cisco brand-approved ThousandEyes HTML presentation
  decks: intake (audience, topics, customer), optional customer research and Gong
  notes, ThousandEyes data/screenshots/sharelinks, then deck generation from the
  official template. Use when the user says "I want to make a deck", "make a
  deck", "build a presentation", "HTML deck", or wants a Cisco/ThousandEyes
  slide deck.
---

# HTML deck workflow (Cisco ThousandEyes)

Interactive workflow for **brand-approved HTML presentation decks**. Do **not** generate the deck until intake is complete and (when a customer is named) the user confirms customer context.

**Canonical template:** `.cursor/skills/html-deck/cisco-thousandeyes-deck-template.html`  
(Fallback: `~/Downloads/Cisco ThousandEyes - HTML Presentation Template(1).html`)

## Phase 0 — Start

When the user opens with **"I want to make a deck"** (or similar):

1. Acknowledge deck mode briefly.
2. Ask these **required** intake questions in one message (use `AskQuestion` if helpful):
   - **Audience** — who will see this? (e.g. CIO, NetOps, security, executive sponsor, internal SE training)
   - **Primary topics** — what should the deck cover? (bullets are fine)
   - **Customer name** — optional; skip for internal/generic decks
3. Ask for **optional assets** in the same message:
   - ThousandEyes **data** (test IDs, dashboard IDs, alert/event IDs, account context)
   - **Screenshots** (attach or paste paths)
   - **Share links** (ThousandEyes share URLs, demo links, docs)
   - Any other reference material (RFP bullets, prior deck, architecture diagram)

**Do not** read the template or write HTML until intake answers arrive (except customer research in Phase 1 if a name was given early).

## Phase 1 — Customer context (when customer name provided)

If the user supplies a **customer name**:

1. **Research** (web search + SE knowledge): produce a short summary with:
   - Company overview (industry, scale, geography if relevant)
   - Likely **business priorities** (digital transformation, hybrid work, cloud migration, security, cost, resilience, etc.)
   - **ThousandEyes assurance plays** that map to those priorities — use outcome-oriented plays, not niche features:
     - Workforce Digital Experience
     - Network / WAN / SD-WAN assurance
     - Internet & routing visibility
     - SaaS / application delivery
     - Cloud & data center paths
     - AgenticOps / AIOps integration
     - Endpoint / device experience (if relevant)
   - Suggested **deck angles** tied to audience + primary topics
2. **Present** the summary clearly (bullets, not walls of text).
3. Ask explicitly:
   - *"Want to change anything in this customer framing?"*
   - *"Do you have Gong transcripts, call notes, or CRM notes to paste in? I'll fold them into the deck narrative."*
4. **Wait** for user response. If they paste notes/transcripts, extract:
   - Stated pain points and initiatives
   - Named apps, sites, vendors, architectures
   - Objections, competitors mentioned, timeline/budget signals
   - Quotes worth a `.slide.statement` slide
5. Merge research + pasted notes into a **confirmed customer brief** before Phase 2.

If **no customer name**, skip to Phase 2 after Phase 0 answers.

## Phase 2 — Deck plan (confirm before build)

Summarize back:

| Item | Content |
|------|---------|
| Audience | … |
| Customer | … or "Generic / internal" |
| Narrative arc | Cover → statement? → workflow? → cards → use cases → docs → closing |
| Slides to include | Pick from template library only what's needed |
| Data/assets | What will be embedded vs. linked vs. diagrammed |
| Output path | `decks/<slug>-deck.html` (default) |

Propose a **slide outline** (titles only, 5–15 slides typical). Ask: *"Ready for me to build this deck, or changes first?"*

Wait for explicit go-ahead.

## Phase 3 — Build the deck

1. **Copy** the canonical template to the output path (do not mutate the template file in `.cursor/skills/html-deck/`).
2. **Read** the template's HTML comment block (lines 8–166) — treat as **hard rules**. Also follow [reference.md](reference.md).
3. **Compose slides** using only brand-compliant components. Suggested default flow (adapt to content):
   - `.slide.cover` — title, customer, audience-appropriate subtitle
   - `.slide.statement` — optional customer quote or big idea (only slide allowed to use gradient)
   - `.slide.agenda` — if multi-section
   - `.slide.seg` — section dividers when needed
   - Workflow / `.cgrid` cards / `.ucgrid` use-case coverage — map customer plays to `.uccard` + `.ucdot` status
   - `.bvband` — business value alignment from customer brief
   - `.te` SVG diagrams — relabel gallery diagrams; use `.te.rca` for fault localization stories
   - `.slide.gfxonly` — full-bleed diagrams or screenshots
   - `.doc` — documentation / share links
   - `.slide.closing`
4. **Replace every `[bracketed]` placeholder** — none may remain.
5. **ThousandEyes data integration:**
   - **Share links** → `.doc` rows or agenda bullets with `.t-link`
   - **MCP** (`user-global-demo`): when user provides IDs, fetch test results, path viz, dashboards, alerts, outages as needed to populate metrics, diagram labels, or talking-point slides
   - **Screenshots**: embed as base64 `<img>` inside framed containers when user supplies files; always set `alt` text
6. **Keep one self-contained `.html` file** — embedded logo stays; no external fonts/scripts/CDNs.
7. **Do not modify** presenter script, print CSS, or `:root` token definitions unless fixing a bug.

## Phase 4 — Review & iteration

After writing the file:

1. Share the **full path** and how to use it:
   - Open in browser
   - **P** or "Present" → fullscreen presenter mode
   - **Ctrl/Cmd+P** or "Save to PDF" → one 16:9 slide per page
2. Ask: *"Review the deck — what slides or copy should I change?"*
3. Iterate on the output file only until approved.

## Rules of engagement

| Do | Don't |
|----|--------|
| Complete intake before building | Start HTML on "make a deck" alone |
| Research + confirm customer context | Invent customer facts without labeling assumptions |
| Use template CSS variables & components only | Invent colors, solid fills, or Magenta/Orange misuse |
| Static-readable slides (PDF = WYSIWYG) | Rely on animation to reveal content |
| Map to assurance **plays** | List random TE features |
| Embed user-provided screenshots | Ignore pasted Gong notes when offered |

## Brand reminders (non-negotiable)

- Colors: **only** `:root` CSS variables — no hex literals in new markup
- Magenta `#FF007F` / Orange `#FF9000`: decorative only, &lt;5%, never text/CTA — **safest: don't use**
- Containers: unfilled outlines; gradients **only** on `.slide.statement`
- Status: never color alone — pair `.ucdot` shape + label
- Footer year is automatic; slides get © + "Cisco Confidential" via script

## Output location

Default: `decks/<customer-or-topic-slug>-deck.html` at workspace root.  
Create `decks/` if missing. Use a descriptive slug (e.g. `acme-corp-exec-brief-deck.html`).
