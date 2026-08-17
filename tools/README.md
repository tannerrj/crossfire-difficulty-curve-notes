# difficulty-scan

Static scans over the Crossfire map set — the tooling behind the figures in
[difficulty-notes.txt](../difficulty-notes.txt).

The notes argue that most of the difficulty conversation is taste until
something counts it. This is the counting. Every report prints both the
headline figure and the per-map rows behind it, because a percentage is an
argument and a ranked list of map paths is a work queue.

## Requirements

Python 3.8+, standard library only. No install step.

It reads three checkouts, none of which it writes to:

| Checkout | Used for | Default | Override |
| --- | --- | --- | --- |
| crossfire-maps | the map set | `~/Documents/cf-devel/crossfire-crossfire-maps` | `--maps`, `$CF_MAPS` |
| crossfire-arch | which archetypes are monsters, exits, signs | `~/Documents/cf-devel/crossfire-crossfire-arch` | `--arch`, `$CF_ARCH` |
| crossfire-server | `lib/config/exp_table`, for the difficulty estimate | `~/Documents/cf-devel/crossfire-crossfire-server` | `--server`, `$CF_SERVER` |

The server checkout is optional; without it the estimated-difficulty column is
left blank.

## Usage

```bash
./difficulty-scan                      # every report, headline figures only
./difficulty-scan dungeon-shape        # one report, with rows and caveats
./difficulty-scan entry-distance --rows 40
./difficulty-scan all --csv out/       # full rows to out/<report>.csv
```

A full run is about 15 seconds over ~3,300 maps.

Useful flags: `--rows N` (0 for all), `--csv DIR`, `--quiet`, `--no-caveats`.

`out/` is the conventional place to write to and is gitignored — snapshots go
stale as soon as the map set changes, so they are working output rather than a
record. Keep a dated copy outside the repo if you want a baseline to diff
against.

## Reports

| Report | Answers |
| --- | --- |
| `difficulty-headers` | What each map declares, what the server would have estimated, and how far apart they are. |
| `dungeon-shape` | The declared difficulty sequence through each multi-level dungeon, classified flat / rising / dips. |
| `entry-distance` | How many tiles from the entry point to the first hostile — the vestibule question. |
| `entrance-signage` | Overworld entrances into monster-bearing maps, and whether anything nearby warns you. |
| `item-gates` | Gates keyed on an item, and whether any text in the map **names what they want**. |
| `teaching-objects` | Teaching objects per map against how dangerous the map is. |
| `random-maps` | Random-map entrances and whether they set the per-level difficulty ramp. |
| `quests` | Quest definitions, and how many use `setwhen` / `parent` chaining. |

## Reading the output

Two things are load-bearing and easy to skip past.

**The caveats print with the report.** Several figures are only honest with
the caveat attached — entry distance is blind to walls, dungeon shape uses the
directory as a proxy for dungeon boundary, declared difficulty is author intent
and not what a player felt. `--no-caveats` exists for when you are re-reading
familiar output; don't quote a number that you stripped the caveat off.

**Lines marked `<- work queue`** are the actionable count in each report. Pair
them with `--csv` to get the list.

## Design notes

One walk, many views. `cfscan/mapset.py` parses the tree once into a model
(headers, top-level objects with coordinates, resolved exit graph);
`cfscan/reports.py` is functions over that model. Adding a report means adding
a function, not another tree walk.

Three details account for most of the accuracy, and each one was a bug in the
throwaway scripts that produced the first draft of the notes:

- **Exits are archetype-driven.** Over a thousand archetypes have object type
  66. Most overworld entrances are not `arch exit` — they are houses, huts,
  caves, and pit holes. Matching on a hardcoded handful of names loses most of
  the exit graph.
- **Hostility is instance-aware.** A monster archetype can be made peaceful by
  the map that places it, and 82 archetypes are peaceful to begin with.
  Counting every `monster 1` as a threat turns every town into a dungeon.
- **Scenery is not teaching.** A `bookshelf` matches a naive search for books
  and carries no text. Only objects with an actual `msg` count.

The `item-gates` report goes one step further than any earlier scan: rather
than asking whether a map contains a sign, it asks whether any text in the map
**names the item the gate is keyed on**, matching the archetype name, its
underscore-free form, and its display name.

## What this does not do

Everything here is static — what an author declared and what objects a map
contains. None of it measures what a player experienced. That needs the
runtime telemetry described in the monitoring section of the notes:
`python/events/death/log_death.py` and the `mapenter` / `mapleave` pair.

Two tools already in the server tree overlap with this one and are worth
knowing about before extending it: `utils/mapper` generates content listings
with random treasure resolved, and `utils/maps-to-dot` emits per-region
GraphViz graphs of the same exit connections this builds.
