# 📈 Crossfire Difficulty Curve Notes

### Applying davetech.co.uk's "Difficulty Curves" to Crossfire

![License](https://img.shields.io/badge/license-GPLv2-blue)
![Format](https://img.shields.io/badge/format-DokuWiki-green)
![Status](https://img.shields.io/badge/status-notes-lightgrey)

A working analysis of [Dave Roberts' "Difficulty Curves"](https://www.davetech.co.uk/difficultycurves) article measured against Crossfire. The source article is written for linear single-player platformers, so part of it maps onto Crossfire directly, part of it fights Crossfire's basic shape, and part of it points at work that is already half-built. These notes sort it into those three piles and say what to do about each.

---

## 📄 Contents

* **[difficulty-notes.txt](difficulty-notes.txt)** — the notes themselves, in DokuWiki markup.

Sections:

* **What applies** — the difficulty saw at the map-set level, the untaught mechanic surface, death penalties, hidden mechanics as puzzles, adrenaline pacing, monitoring.
* **The mechanic surface, expanded** — why "why did that not work?" is a teaching failure rather than a tuning failure, the teaching objects already in the engine, worked map examples, and conventions worth adding to `Info/mapguide`.
* **Who Crossfire is actually for, expanded** — layering information so depth stays opt-in, comparable games (NetHack, DCSS, Dwarf Fortress, Caves of Qud, EVE Online), where players currently have to go to read about Crossfire, and what it would take to move that reading in-game.
* **What does not apply cleanly** — dynamic difficulty adjustment, enforced sequence, formal QA.
* **What Crossfire should actually adopt** — a prioritised list, led by the `difficulty` header audit and death-location aggregation.

---

## 📝 Format

The notes are written in **DokuWiki markup**, not Markdown, so they can be pasted straight into the Crossfire wiki. GitHub will not render them — read the raw file, or paste it into a DokuWiki page.

Quick reference for the markup used here:

| Syntax | Meaning |
| --- | --- |
| `===== Heading =====` | Section heading (more `=` means higher level) |
| `**text**` | Bold |
| `//text//` | Italic |
| `''text''` | Inline code — used for map fields, archetypes, and file paths |
| `[[url\|label]]` | Link |
| `  - item` | Ordered list item |
| `<code>` … `</code>` | Code block — map file snippets |

---

## 🎯 Scope

These are notes, not a specification. They lean on three things that already exist:

* [Crossfire Map Report](https://github.com/tannerrj/crossfire-map-audit) — already does the map scanning half of the `difficulty` header audit.
* [Crossfire World Map Entrances](https://github.com/tannerrj/crossfire-world-map-entrances) — already enumerates entrances, which makes signage coverage measurable.
* Crossfire Death Tracker (not yet published) — the starting point for death-location aggregation.

Claims about engine behaviour are checked against the Crossfire server and arch trees rather than against the wiki, and cite the relevant file where it matters (for example `types/book/book.cpp` for the skill and level gate on readable books).

---

## 🤝 Contributing

 * Contributions are welcome.
 * Pull requests are welcome.
 * Creating a fork on this code base is also welcome.

Corrections to engine behaviour are especially welcome — cite the source file.

---

## 📄 License

GNU General Public License v2 — see [LICENSE](LICENSE).

---

## Questions

I can be reached via [tannerrj GitHub Profile](https://github.com/tannerrj)

----

## Crossfire Social Media Links

 * [BlueSky](https://bsky.app/profile/crossfireproject.bsky.social)
 * [Facebook](https://www.facebook.com/crossfireproject/)
 * [Mastodon](https://mastodon.social/@crossfiremrpg)
 * [X (Formerly Twitter)](https://twitter.com/crossfiremrpg/)
