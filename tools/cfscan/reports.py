"""The reports.

Each one is a view over a loaded MapSet, and each returns a Report carrying
both the headline figures and the per-map rows behind them. The rows are the
point: a percentage is an argument, a ranked list of map paths is a work queue.

Every report that has a known bias states it in ``caveats``. Those print with
the report and belong in any write-up that quotes the number.
"""

import math
import os
import re
import statistics
from collections import Counter, defaultdict

from .mapset import GATE_ARCHES, TEACHING_ARCHES, chebyshev

# The server's estimator gives up here; see calculate_difficulty() in
# common/map.cpp. Declared values above this are on a different scale entirely.
ESTIMATOR_CEILING = 25


class Report:
    def __init__(self, key, title, columns, rows, summary=None, caveats=None):
        self.key = key
        self.title = title
        self.columns = columns
        self.rows = rows
        self.summary = summary or []
        self.caveats = caveats or []


def _pct(part, whole):
    return 0.0 if not whole else 100.0 * part / whole


# ---------------------------------------------------------------------------
# 1. Difficulty headers
# ---------------------------------------------------------------------------

def difficulty_headers(mapset, arches, exp_table=None, **_):
    maps = list(mapset.maps.values())
    declared = [m for m in maps if m.difficulty is not None]
    ones = [m for m in declared if m.difficulty == 1]
    above = [m for m in declared if m.difficulty > ESTIMATOR_CEILING]

    rows = []
    for m in sorted(declared, key=lambda m: -m.difficulty):
        hostiles = len(m.hostiles(arches))
        estimate = estimate_difficulty(m, arches, exp_table) if exp_table else ""
        rows.append((m.path, m.kind(), m.difficulty, estimate, hostiles, m.area))

    summary = [
        f"maps parsed: {len(maps)}",
        f"declaring a difficulty: {len(declared)} ({_pct(len(declared), len(maps)):.0f}%)",
        f"declaring exactly 1: {len(ones)} ({_pct(len(ones), len(declared)):.0f}% of declared)",
        f"declaring above the estimator ceiling of {ESTIMATOR_CEILING}: "
        f"{len(above)} ({_pct(len(above), len(declared)):.0f}%)",
    ]
    if declared:
        values = [m.difficulty for m in declared]
        summary.append(
            f"median {statistics.median(values):.0f}, mean {statistics.mean(values):.1f}, "
            f"max {max(values)}"
        )
    monster_ones = [m for m in ones if m.hostiles(arches)]
    summary.append(
        f"declaring 1 with hostile monsters present: {len(monster_ones)}  <- work queue"
    )

    return Report(
        "difficulty-headers",
        "Declared difficulty against map contents",
        ("map", "kind", "declared", "estimated", "hostiles", "area"),
        rows,
        summary,
        [
            "A non-zero declared value suppresses the server's own estimate "
            "entirely (common/map.cpp).",
            "The field also drives treasure, shop stock, skill-ident exp and "
            "hiding, so segment by kind before calling anything an outlier.",
        ],
    )


def estimate_difficulty(mapfile, arches, exp_table):
    """Reimplementation of the server's calculate_difficulty().

    Generators are approximated by their own exp only; the server also adds a
    guess at what they will spawn, so this reads slightly low for maps built
    around them.
    """
    total = sum(
        arches.exp.get(obj.arch, 0)
        for obj in mapfile.objects
        if obj.arch in arches.monsters
    )
    if total <= 0:
        return 0
    per_square = math.pow(total, 1.75) / (mapfile.area + 1)
    for level in range(1, ESTIMATOR_CEILING):
        if level < len(exp_table) and per_square <= exp_table[level]:
            return level
    return ESTIMATOR_CEILING


# ---------------------------------------------------------------------------
# 2. Dungeon shape
# ---------------------------------------------------------------------------

def dungeon_shape(mapset, arches, min_maps=3, monster_ratio=0.6, **_):
    rows = []
    flat = graded = rising = dipping = 0

    for directory, members in sorted(mapset.dungeons(min_maps).items()):
        members = {m for m in members if mapset.maps[m].difficulty is not None}
        if len(members) < min_maps:
            continue
        with_monsters = sum(1 for m in members if mapset.maps[m].hostiles(arches))
        if with_monsters < monster_ratio * len(members):
            continue  # guild hall, shop row, or apartment block

        entrances = mapset.entrances_to(directory, members)
        dist = mapset.depth_map(members, entrances)

        by_depth = defaultdict(list)
        for m in members:
            by_depth[dist.get(m, 99)].append(mapset.maps[m].difficulty)
        sequence = [round(statistics.mean(by_depth[d])) for d in sorted(by_depth)]

        if len(set(sequence)) == 1:
            shape = "flat"
            flat += 1
        else:
            graded += 1
            if any(sequence[i + 1] < sequence[i] for i in range(len(sequence) - 1)):
                shape = "dips"
                dipping += 1
            else:
                shape = "rising"
                rising += 1

        rows.append((directory, len(members), shape,
                     " ".join(str(v) for v in sequence)))

    total = flat + graded
    summary = [
        f"monster-bearing multi-map dungeons: {total}",
        f"  flat at every depth: {flat} ({_pct(flat, total):.0f}%)  <- work queue",
        f"  graded: {graded} ({_pct(graded, total):.0f}%)",
        f"    strictly rising: {rising} ({_pct(rising, graded):.0f}% of graded)",
        f"    containing a dip: {dipping} ({_pct(dipping, graded):.0f}% of graded)",
    ]
    rows.sort(key=lambda r: (r[2] != "flat", -r[1]))

    return Report(
        "dungeon-shape",
        "Declared difficulty sequence by depth from the entrance",
        ("dungeon", "maps", "shape", "sequence"),
        rows,
        summary,
        [
            "Declared difficulty is author intent, not what a player felt.",
            "Directory is a proxy for dungeon boundary: it merges some and splits others.",
            "Depth is breadth-first from whichever map is entered from outside, "
            "which is wrong for a dungeon with two entrances at different depths.",
            "A dip late in the sequence usually reads as inconsistency rather "
            "than pacing - check the sequence, not just the shape column.",
        ],
    )


# ---------------------------------------------------------------------------
# 3. Entry distance
# ---------------------------------------------------------------------------

def entry_distance(mapset, arches, vestibule=3, **_):
    rows = []
    for path, mapfile in mapset.maps.items():
        if path.startswith("world"):
            continue
        hostiles = mapfile.hostiles(arches)
        if not hostiles:
            continue
        ex, ey = mapfile.entry
        nearest = min(chebyshev(ex, ey, o.x, o.y) for o in hostiles)
        density = 100.0 * len(hostiles) / max(mapfile.area, 1)
        rows.append((path, nearest, len(hostiles), mapfile.area, round(density, 1)))

    distances = sorted(r[1] for r in rows)
    total = len(rows)
    summary = [f"maps with hostile monsters (world tiles excluded): {total}"]
    if total:
        summary.append(f"median distance to the first hostile: {statistics.median(distances):.0f} tiles")
        for threshold in (1, 2, 3, 5, 8, 12):
            count = sum(1 for d in distances if d <= threshold)
            summary.append(
                f"  within {threshold:2} tiles: {count:5} ({_pct(count, total):.0f}%)"
            )
        areas = [r[3] for r in rows]
        densities = [r[4] for r in rows]
        # Both figures are over maps that HAVE hostiles, not over all maps.
        # Quoting them beside an all-maps figure is how the two populations
        # get conflated.
        summary.append(f"median area of these maps: {statistics.median(areas):.0f} tiles")
        summary.append(
            f"median hostile density on these maps: "
            f"{statistics.median(densities):.1f} per 100 tiles"
        )
        no_vestibule = sum(1 for d in distances if d < vestibule)
        summary.append(
            f"maps with no {vestibule}-tile vestibule: {no_vestibule} "
            f"({_pct(no_vestibule, total):.0f}%)  <- work queue"
        )

    rows.sort(key=lambda r: (r[1], -r[2]))
    return Report(
        "entry-distance",
        "Distance from the entry point to the nearest hostile",
        ("map", "tiles", "hostiles", "area", "per_100_tiles"),
        rows,
        summary,
        [
            "Chebyshev distance, blind to walls: a monster behind stone counts "
            "the same as one in the corridor. Treat the figures as a floor.",
            "Hostility is archetype default overridden by the map instance, "
            "which still misfiles a few caged or scripted NPCs.",
        ],
    )


# ---------------------------------------------------------------------------
# 4. Entrance signage
# ---------------------------------------------------------------------------

def entrance_signage(mapset, arches, radius=3, **_):
    rows = []
    signed = Counter()
    total = 0
    all_doors = 0

    for path, mapfile in mapset.maps.items():
        if not path.startswith("world"):
            continue
        teaching = [
            o for o in mapfile.objects
            if (o.arch in TEACHING_ARCHES or o.arch in arches.signs) and o.msg
        ]
        squares = []
        for obj, target in mapfile.exits:
            destination = mapset.maps.get(target)
            if destination is None or not destination.hostiles(arches):
                continue
            total += 1
            nearest = min(
                (chebyshev(obj.x, obj.y, t.x, t.y) for t in teaching), default=None
            )
            for threshold in (1, 2, 3, 5):
                if nearest is not None and nearest <= threshold:
                    signed[threshold] += 1
            squares.append((obj, target, nearest, len(destination.hostiles(arches))))

        for door in _cluster_doors(squares):
            all_doors += 1
            if door["nearest"] is None or door["nearest"] > radius:
                rows.append((
                    path, door["x"], door["y"], door["arch"], door["target"],
                    door["hostiles"], door["squares"],
                    "" if door["nearest"] is None else door["nearest"],
                ))

    summary = [
        f"overworld entrance squares whose destination holds monsters: {total}",
        f"  grouped into doors (adjacent squares sharing a destination): {all_doors}",
    ]
    for threshold in (1, 2, 3, 5):
        summary.append(
            f"  squares signed within {threshold} tiles: {signed[threshold]:4} "
            f"({_pct(signed[threshold], total):.0f}%)"
        )
    summary.append(
        f"doors with nothing within {radius} tiles: {len(rows)} of {all_doors} "
        f"({_pct(len(rows), all_doors):.0f}%)  <- work queue"
    )

    rows.sort(key=lambda r: -r[5])
    return Report(
        "entrance-signage",
        "Overworld entrances to monster-bearing maps, and whether anything warns you",
        ("world_map", "x", "y", "entrance_arch", "destination", "hostiles",
         "squares", "nearest_sign"),
        rows,
        summary,
        [
            "Counts only signs, mouths and runes carrying text; scenery is excluded.",
            "A sign near an entrance is not proof it says anything useful - "
            "'Dungeon Master's Lounge' counts here.",
            "Adjacent squares sharing a destination are one door: a five-tile "
            "building frontage is one signage job, not five. Two doors far "
            "apart on the same world tile stay separate even to the same map.",
        ],
    )


def _cluster_doors(squares):
    """Collapse adjacent entrance squares that share a destination into one door.

    A building on the world map is several tiles wide and every tile carries its
    own exit object pointing at the same interior. Counting those as separate
    entrances inflates the work queue - it is one sign to write, not five.
    Grouping is by destination first, then by adjacency, so two genuinely
    separate doors into the same dungeon are still two jobs.
    """
    by_target = defaultdict(list)
    for obj, target, nearest, hostiles in squares:
        by_target[target].append((obj, nearest, hostiles))

    doors = []
    for target, members in by_target.items():
        unassigned = list(members)
        while unassigned:
            obj, nearest, hostiles = unassigned.pop()
            cluster = [(obj, nearest)]
            changed = True
            while changed:
                changed = False
                for candidate in list(unassigned):
                    cand_obj, cand_nearest, _ = candidate
                    if any(chebyshev(cand_obj.x, cand_obj.y, m.x, m.y) <= 1
                           for m, _ in cluster):
                        cluster.append((cand_obj, cand_nearest))
                        unassigned.remove(candidate)
                        changed = True
            # Report the door at its top-left square, and treat it as signed if
            # any of its squares is: one sign covers the whole frontage.
            found = [n for _, n in cluster if n is not None]
            doors.append({
                "x": min(m.x for m, _ in cluster),
                "y": min(m.y for m, _ in cluster),
                "arch": cluster[0][0].arch,
                "target": target,
                "hostiles": hostiles,
                "squares": len(cluster),
                "nearest": min(found) if found else None,
            })
    return doors


# ---------------------------------------------------------------------------
# 5. Item gates
# ---------------------------------------------------------------------------

def item_gates(mapset, arches, radius=6, **_):
    """Gates the player has to satisfy with an item, and whether anything says so.

    ``detector`` is deliberately reported apart from the other two. It fires on
    anything occupying a square - spell effects, markers, machinery - so most
    detectors are wiring rather than a puzzle the player is meant to solve, and
    folding them into one headline makes the map set look far worse than it is.
    """
    rows = []
    gated_maps = 0
    by_arch = Counter()
    unexplained_by_arch = Counter()
    invisible_altars = 0
    invisible_maps = set()

    for path, mapfile in mapset.maps.items():
        gates = mapfile.gates()
        if not gates:
            continue
        gated_maps += 1
        teaching = mapfile.teaching_objects(arches)

        for obj, required in gates:
            by_arch[obj.arch] += 1
            if obj.arch == "altar_trigger" and obj.attrs.get("invisible") == "1":
                invisible_altars += 1
                invisible_maps.add(path)

            words = arches.words_for(required)
            named_by = None
            nearest = None
            for teacher in teaching:
                distance = chebyshev(obj.x, obj.y, teacher.x, teacher.y)
                if nearest is None or distance < nearest:
                    nearest = distance
                lowered = teacher.msg.lower()
                if any(word in lowered for word in words):
                    named_by = distance
                    break
            if named_by is None and mapfile.has_dialogue:
                for candidate in mapfile.objects:
                    if candidate.msg and "@match" in candidate.msg:
                        lowered = candidate.msg.lower()
                        if any(word in lowered for word in words):
                            named_by = chebyshev(obj.x, obj.y, candidate.x, candidate.y)
                            break

            explained = named_by is not None and named_by <= radius
            if not explained:
                unexplained_by_arch[obj.arch] += 1
                rows.append((
                    path, obj.arch, required, obj.x, obj.y,
                    "yes" if obj.attrs.get("invisible") == "1" else "",
                    len(teaching),
                    "" if nearest is None else nearest,
                    "elsewhere on map" if named_by is not None else "nowhere",
                ))

    player_facing = by_arch["altar_trigger"] + by_arch["check_inv"]
    player_unexplained = (unexplained_by_arch["altar_trigger"]
                          + unexplained_by_arch["check_inv"])
    # Per-gate counts are dominated by a handful of maps that stack dozens of
    # altars on one square, so the per-map figure is the one to act on.
    affected_maps = {r[0] for r in rows if r[1] != "detector"}
    summary = [
        f"maps with item-keyed gates: {gated_maps}",
        f"  of those, maps with at least one unexplained player-facing gate: "
        f"{len(affected_maps)} ({_pct(len(affected_maps), gated_maps):.0f}%)  <- work queue",
        f"player-facing gates (altar_trigger + check_inv): {player_facing}",
        f"  altar_trigger {by_arch['altar_trigger']}, check_inv {by_arch['check_inv']}",
        f"  with nothing within {radius} tiles naming what they want: "
        f"{player_unexplained} ({_pct(player_unexplained, player_facing):.0f}%)",
        f"detectors keyed on slaying: {by_arch['detector']} "
        f"(mostly machinery - counted separately, not in the figures above)",
        f"invisible trigger altars: {invisible_altars} across {len(invisible_maps)} maps",
    ]

    rows.sort(key=lambda r: (r[8] != "nowhere", r[0]))
    return Report(
        "item-gates",
        "Gates keyed on an item, and whether anything in the map names it",
        ("map", "gate", "requires", "x", "y", "invisible", "teaching_objects",
         "nearest_teacher", "requirement_named"),
        rows,
        summary,
        [
            "This is the check nobody had run: not 'is there a sign' but "
            "'does the text name the thing the gate wants'.",
            "Matching is on the archetype name, its underscore-free form, and "
            "its display name, so a sign saying 'roses' will miss 'rose_white'.",
            "Guild crafting furniture (Stove, Forge, Cauldron) is keyed the "
            "same way and is explained by joining the guild, not by a sign.",
        ],
    )


# ---------------------------------------------------------------------------
# 6. Teaching objects
# ---------------------------------------------------------------------------

def teaching_objects(mapset, arches, **_):
    rows = []
    silent_dangerous = 0
    with_knowledge = 0

    for path, mapfile in sorted(mapset.maps.items()):
        if path.startswith("world"):
            continue
        hostiles = len(mapfile.hostiles(arches))
        teachers = mapfile.teaching_objects(arches)
        counts = Counter(o.arch for o in teachers)
        markers = sum(1 for o in mapfile.objects if "knowledge_marker" in o.attrs)
        if markers:
            with_knowledge += 1
        if hostiles and not teachers and not mapfile.has_dialogue:
            silent_dangerous += 1
        if hostiles:
            rows.append((
                path, mapfile.difficulty if mapfile.difficulty is not None else "",
                hostiles, len(teachers),
                counts.get("magic_mouth", 0), counts.get("rune_mark", 0),
                counts.get("sign", 0), markers,
                "yes" if mapfile.has_dialogue else "",
            ))

    summary = [
        f"maps with hostile monsters: {len(rows)}",
        f"  carrying no teaching object and no dialogue: {silent_dangerous} "
        f"({_pct(silent_dangerous, len(rows)):.0f}%)  <- work queue",
        f"maps using knowledge_marker: {with_knowledge} "
        f"(python scripts can grant knowledge too and are not counted here)",
    ]

    rows.sort(key=lambda r: (r[3], -(r[2] or 0)))
    return Report(
        "teaching-objects",
        "Teaching objects per map, against how dangerous the map is",
        ("map", "difficulty", "hostiles", "teachers", "mouths", "runes",
         "signs", "knowledge_markers", "dialogue"),
        rows,
        summary,
        [
            "Counts only objects carrying text. A bookshelf is scenery and "
            "does not count, which an earlier version of this scan got wrong.",
            "Presence is not usefulness: atmosphere text counts here.",
        ],
    )


# ---------------------------------------------------------------------------
# 7. Random map entrances
# ---------------------------------------------------------------------------

_RM_KEYS = ("dungeon_level", "dungeon_depth", "difficulty", "difficulty_increase",
            "layoutstyle", "monsterstyle")


def random_maps(mapset, arches, **_):
    rows = []
    with_ramp = 0
    single_level = 0
    overworld = 0

    for path, mapfile in sorted(mapset.maps.items()):
        for obj in mapfile.objects:
            if obj.attrs.get("slaying") != "/!" or not obj.msg:
                continue
            params = {}
            for line in obj.msg.split("\n"):
                key, _, value = line.strip().partition(" ")
                if key in _RM_KEYS:
                    params[key] = value.strip()
            depth = params.get("dungeon_depth", "")
            if params.get("difficulty_increase"):
                with_ramp += 1
            if depth in ("", "1"):
                single_level += 1
            if path.startswith("world"):
                overworld += 1
            rows.append((
                path, obj.x, obj.y, obj.arch,
                params.get("dungeon_level", ""), depth,
                params.get("difficulty_increase", ""),
                params.get("layoutstyle", ""),
            ))

    total = len(rows)
    summary = [
        f"random-map entrances: {total} ({overworld} of them on the world tiles)",
        f"  setting difficulty_increase (the per-level ramp): {with_ramp} "
        f"({_pct(with_ramp, total):.0f}%)",
        f"  single-level, where no ramp is possible: {single_level} "
        f"({_pct(single_level, total):.0f}%)  <- work queue",
    ]

    return Report(
        "random-maps",
        "Random-map entrances and their generation parameters",
        ("map", "x", "y", "arch", "dungeon_level", "dungeon_depth",
         "difficulty_increase", "layout"),
        rows,
        summary,
        [
            "The generator derives difficulty from dungeon_level scaled by "
            "difficulty_increase (random_maps/random_map.cpp).",
            "Nothing here reads player level or party size; the scaling is "
            "authored, not adaptive.",
        ],
    )


# ---------------------------------------------------------------------------
# 8. Quests
# ---------------------------------------------------------------------------

def quests(mapset, arches, **_):
    rows = []
    totals = Counter()

    for dirpath, dirnames, filenames in os.walk(mapset.root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for filename in filenames:
            if not filename.endswith(".quests"):
                continue
            path = os.path.relpath(os.path.join(dirpath, filename), mapset.root)
            totals["files"] += 1
            current = None
            counts = defaultdict(Counter)
            with open(os.path.join(dirpath, filename), encoding="utf-8",
                      errors="ignore") as handle:
                for line in handle:
                    line = line.rstrip()
                    if line.startswith("quest "):
                        current = line[6:].strip()
                        counts[current]  # touch
                    elif current:
                        stripped = line.strip()
                        if stripped.startswith("step "):
                            counts[current]["steps"] += 1
                        elif stripped == "setwhen":
                            counts[current]["setwhen"] += 1
                        elif stripped.startswith("parent "):
                            counts[current]["parent"] += 1
                        elif stripped.startswith("restart "):
                            counts[current]["restart"] += 1
            for quest, c in counts.items():
                totals["quests"] += 1
                totals["steps"] += c["steps"]
                totals["setwhen"] += c["setwhen"]
                totals["parent"] += c["parent"]
                rows.append((path, quest, c["steps"], c["setwhen"], c["parent"]))

    chained = sum(1 for r in rows if r[3] or r[4])
    summary = [
        f"quest files: {totals['files']}",
        f"quests: {totals['quests']}, steps: {totals['steps']}",
        f"setwhen blocks: {totals['setwhen']}, parent declarations: {totals['parent']}",
        f"quests using either: {chained} ({_pct(chained, totals['quests']):.0f}%)",
    ]
    if rows:
        summary.append(
            f"median steps per quest: {statistics.median(r[2] for r in rows):.0f}"
        )

    rows.sort(key=lambda r: -r[2])
    return Report(
        "quests",
        "Quest definitions and how many use the chaining features",
        ("file", "quest", "steps", "setwhen", "parent"),
        rows,
        summary,
        [
            "setwhen is the cross-quest conditional that makes a chain a chain "
            "rather than a list of steps.",
            "Quest state is advanced from Python; dialogue-driven progression "
            "in CFDialog keeps separate state and is invisible here.",
        ],
    )


REPORTS = {
    "difficulty-headers": difficulty_headers,
    "dungeon-shape": dungeon_shape,
    "entry-distance": entry_distance,
    "entrance-signage": entrance_signage,
    "item-gates": item_gates,
    "teaching-objects": teaching_objects,
    "random-maps": random_maps,
    "quests": quests,
}
