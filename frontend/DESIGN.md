# Design Guidelines

> This is the design language for the lead-gen product. Every frontend component, page, and interaction should follow these principles. When in doubt, choose restraint over decoration.

## Philosophy

We build tools for people who make high-stakes decisions about solar infrastructure. The interface should feel like a trusted advisor — calm, precise, and quietly authoritative. Not a flashy SaaS dashboard. Not a consumer app.

**Our reference point is Harvey AI** — warm minimalism, editorial typography, generous space, and near-zero visual noise. We adapt their principles for a data-rich context where clarity is everything.

Three rules to internalize:

1. **Quiet confidence.** The interface never shouts. Information hierarchy does the work — not color, not size, not animation.
2. **Earn every pixel.** If a border, shadow, color, or element doesn't serve user clarity, remove it. Default to less.
3. **Dark, warm, editorial.** Our surfaces are warm charcoal, not cold gray. Our type mixes serif and sans for editorial contrast. The product should feel like reading a well-designed report, not using software.

---

## Color

### Surfaces (dark foundation)

| Token | Value | Use |
|-------|-------|-----|
| `surface-primary` | `#1C1A17` | Page background |
| `surface-raised` | `#252320` | Cards, panels, popovers |
| `surface-overlay` | `#2E2C28` | Modals, dropdowns, hover states |

Never use cool grays or blue-tinted backgrounds.

### Text

| Token | Value | Use |
|-------|-------|-----|
| `text-primary` | `#FFF8EB` | Headings, important content |
| `text-secondary` | `rgba(255, 248, 235, 0.6)` | Body text, descriptions |
| `text-tertiary` | `rgba(255, 248, 235, 0.38)` | Labels, captions, placeholders |

Our white is warm ivory.

### Borders

| Token | Value | Use |
|-------|-------|-----|
| `border-subtle` | `rgba(255, 248, 235, 0.08)` | Card edges, table rows, dividers |
| `border-default` | `rgba(255, 248, 235, 0.12)` | Inputs, interactive boundaries |
| `border-focus` | `rgba(232, 162, 48, 0.5)` | Focus rings (amber, not blue) |

### Accent

| Token | Value | Use |
|-------|-------|-----|
| `accent-amber` | `#E8A230` | Primary brand accent — links, focus, emphasis |
| `accent-amber-muted` | `rgba(232, 162, 48, 0.15)` | Accent backgrounds (badges, subtle highlights) |

Amber is our brand color. Use it sparingly. It should feel like a carefully placed highlight in a book — not a paint job.

### Status colors (functional only)

These exist purely for user clarity. Never use them decoratively.

| Token | Value | Use |
|-------|-------|-----|
| `status-green` | `#5CB77A` | Confirmed, active, success |
| `status-red` | `#D4614E` | Withdrawn, error, rejected |
| `status-amber` | `#E8A230` | Pending, in-progress, review needed |

Status colors appear as small dots, badge text, or subtle background tints — never as large blocks of color.

### What is NOT in our palette

- Blue (no blue buttons, no blue links, no blue focus rings)
- Purple, pink, teal, or any "SaaS rainbow"
- Bright saturated colors of any kind outside the three status colors

---

## Typography

### Font stack

| Role | Family | Weight | Use |
|------|--------|--------|-----|
| **Serif** | Lora | 400, 500, 600 | Page titles, card titles, section headings, editorial moments |
| **Sans** | Geist | 300–600 | Everything else — body text, labels, buttons, inputs, data |
| **Mono** | Geist Mono | 400 | Code, IDs, technical values |

### Hierarchy

| Level | Font | Size | Weight | Tracking | Use |
|-------|------|------|--------|----------|-----|
| **Display** | Lora | 36–48px | 400 | -0.015em | Page titles only |
| **Heading 1** | Lora | 24–28px | 400 | -0.01em | Section headers |
| **Heading 2** | Lora | 18–22px | 500 | -0.01em | Card titles, panel headers |
| **Overline** | Geist | 11px | 500 | 0.08em, uppercase | Category labels, metadata |
| **Body** | Geist | 14–15px | 400 | normal | Descriptions, paragraphs |
| **Small** | Geist | 12–13px | 400–500 | normal | Table cells, captions, badges |
| **Micro** | Geist | 11px | 500 | 0.02em | Timestamps, secondary metadata |

### How to use the serif

The serif creates editorial contrast. It is **not** the default — it's the exception that makes key moments feel considered.

Use Lora for:
- Page-level titles ("EPC Discovery", "Project Pipeline")
- Card headings (company names, project names)
- Empty states or onboarding headlines
- Pull quotes or key metrics when displayed prominently

Use Geist for everything else. When in doubt, use Geist.

Never use Lora for: buttons, labels, table headers, form inputs, navigation items, badges, or tooltips.

---

## Spacing & Layout

### Principles

- **Be generous.** More whitespace always. Cramped layouts erode trust.
- **Let content breathe.** Minimum 24px between card groups. 16px between elements inside a card.
- **Consistent rhythm.** Use a 4px base grid. Common increments: 4, 8, 12, 16, 24, 32, 48, 64, 80.


---

## Motion

Less is more. Motion should be functional, not decorative.


## Plain English

**What is this document?**
It's the rulebook for how our product looks and feels. Think of it like a dress code — not every outfit is specified, but the boundaries are clear: dark backgrounds, warm tones, clean type, lots of breathing room. When someone builds a new component, they should be able to read this and make it look like it belongs, without asking.

**Why does it matter?**
Right now the product feels like different people built different parts (because they did). This guide makes it feel like one coherent product — which builds trust with users. Harvey AI is our north star because they nailed the "serious tool that respects your intelligence" aesthetic.

**The key idea:**
Quiet confidence. We use darkness, space, and typography to create hierarchy — not color and decoration. Color is reserved for moments where the user genuinely needs a signal (is this confirmed or pending?). Everything else is warm neutrals.
