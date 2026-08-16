"""Walk the map set once and build a model every report can read.

Crossfire map files are a header block followed by object blocks:

    arch map
    name Some Dungeon
    difficulty 12
    msg
    Created: ...
    endmsg
    end
    arch sign
    msg
    Beware
    endmsg
    x 4
    y 9
    end

Object blocks nest - a chest's contents are arch blocks inside the chest's
block, before its ``end``. Only top-level objects have meaningful x/y, so the
parser tracks depth and reports position for depth-1 objects only.
"""

import os
import re
from collections import defaultdict

# Directories that are not shipped content. Excluding them is what keeps the
# numbers honest; editor/ and templates/ in particular are full of stubs.
DEFAULT_SKIP = frozenset(
    {".git", ".claude", "editor", "test", "templates", "styles", "unlinked"}
)

# Files that live in the map tree but are not maps.
NON_MAP_SUFFIXES = frozenset(
    {".py", ".png", ".trs", ".arc", ".html", ".sh", ".md", ".pl", ".quests",
     ".reg", ".txt", ".xml", ".json", ".jpg", ".gif", ".bak"}
)

# Attributes worth keeping per object. Everything else is dropped so the whole
# map set fits comfortably in memory.
KEPT_ATTRS = frozenset(
    {"slaying", "name", "invisible", "connected", "food", "level", "x", "y",
     "friendly", "unaggressive", "knowledge_marker", "no_pick", "move_on"}
)

# Archetypes that teach the player something, by mechanism.
TEACHING_ARCHES = frozenset({"sign", "magic_mouth", "rune_mark", "signpost", "board"})

# Gate mechanisms keyed on a slaying string.
GATE_ARCHES = frozenset({"check_inv", "altar_trigger", "detector"})

_HEADER_INT_KEYS = ("width", "height", "enter_x", "enter_y", "difficulty", "darkness")
_SHOP_KEYS = ("shopitems", "shopgreed", "shopmin", "shopmax", "shoprace")


class MapObject:
    __slots__ = ("arch", "x", "y", "attrs", "msg")

    def __init__(self, arch, x, y, attrs, msg):
        self.arch = arch
        self.x = x
        self.y = y
        self.attrs = attrs
        self.msg = msg

    def is_peaceful_instance(self):
        return self.attrs.get("friendly") == "1" or self.attrs.get("unaggressive") == "1"

    def __repr__(self):
        return f"<{self.arch} at {self.x},{self.y}>"


class MapFile:
    """One parsed map."""

    __slots__ = ("path", "header", "objects", "exits", "has_dialogue", "maplore",
                 "_hostiles", "_teachers")

    def __init__(self, path):
        self.path = path
        self.header = {}
        self.objects = []
        self.exits = []  # (MapObject, resolved target path or None)
        self.has_dialogue = False
        self.maplore = None
        self._hostiles = None
        self._teachers = None

    # -- header conveniences ------------------------------------------------

    @property
    def name(self):
        return self.header.get("name", os.path.basename(self.path))

    @property
    def difficulty(self):
        return self.header.get("difficulty")

    @property
    def width(self):
        return self.header.get("width", 16)

    @property
    def height(self):
        return self.header.get("height", 16)

    @property
    def area(self):
        return self.width * self.height

    @property
    def entry(self):
        return (self.header.get("enter_x", 0), self.header.get("enter_y", 0))

    @property
    def region(self):
        return self.header.get("region", "")

    @property
    def directory(self):
        return os.path.dirname(self.path)

    # -- classification -----------------------------------------------------

    def is_shop(self):
        return any(key in self.header for key in _SHOP_KEYS)

    def is_outdoor(self):
        return self.header.get("outdoor") == "1"

    def is_unique(self):
        return self.header.get("unique") == "1"

    def kind(self):
        """Coarse map type, so the difficulty audit can segment before comparing.

        A shop at difficulty 110 with no monsters is not a mislabelled dungeon,
        it is a shop using the field to set stock quality.
        """
        if self.is_shop():
            return "shop"
        if self.is_unique():
            return "unique"
        if self.path.startswith("world/") or self.path.startswith("world."):
            return "world"
        if self.is_outdoor():
            return "outdoor"
        return "indoor"

    # -- object queries -----------------------------------------------------

    def monsters(self, arches):
        return [
            obj for obj in self.objects
            if obj.arch in arches.monsters and not obj.is_peaceful_instance()
        ]

    def hostiles(self, arches):
        # Cached: the signage report asks every destination map this question
        # once per entrance pointing at it.
        if self._hostiles is None:
            hostile = arches.hostile
            self._hostiles = [
                obj for obj in self.objects
                if obj.arch in hostile and not obj.is_peaceful_instance()
            ]
        return self._hostiles

    def monster_exp(self, arch_exp):
        return sum(arch_exp.get(obj.arch, 0) for obj in self.objects)

    def teaching_objects(self, arches):
        """Objects that can actually tell a player something.

        Deliberately excludes scenery: a ``bookshelf`` matches a naive search
        for books and carries no text at all, which is exactly how the first
        version of this scan flattered the map set.
        """
        if self._teachers is None:
            found = []
            for obj in self.objects:
                if not obj.msg:
                    continue
                if (obj.arch in TEACHING_ARCHES
                        or obj.arch in arches.signs
                        or obj.arch in arches.books):
                    found.append(obj)
            self._teachers = found
        return self._teachers

    def gates(self):
        """Item-keyed gates: (object, required slaying string)."""
        out = []
        for obj in self.objects:
            if obj.arch in GATE_ARCHES and "slaying" in obj.attrs:
                out.append((obj, obj.attrs["slaying"]))
        return out

    def __repr__(self):
        return f"<MapFile {self.path}>"


def _looks_like_map(path):
    if os.path.splitext(path)[1] in NON_MAP_SUFFIXES:
        return False
    return True


def parse_map(root, relpath):
    """Parse one map file. Returns None if the file is not a map."""
    full = os.path.join(root, relpath)
    try:
        with open(full, encoding="utf-8", errors="ignore") as handle:
            text = handle.read(24)
            if not text.startswith("arch map"):
                return None
            handle.seek(0)
            lines = handle.read().split("\n")
    except (OSError, UnicodeDecodeError):
        return None

    mapfile = MapFile(relpath)
    # Each frame is [arch, attrs, msg]. Keeping msg on the frame rather than in
    # a single shared buffer matters: an object's msg block is written before
    # its inventory, so a shared buffer would hand the parent's text to the
    # first nested child that closes.
    stack = []
    in_msg = False
    in_lore = False
    msg_lines = []
    lore_lines = []
    header_done = False

    for line in lines:
        if in_lore:
            if line == "endmaplore":
                in_lore = False
                mapfile.maplore = "\n".join(lore_lines)
            else:
                lore_lines.append(line)
            continue

        if in_msg:
            if line == "endmsg":
                in_msg = False
                if stack:
                    stack[-1][2] = "\n".join(msg_lines)
            else:
                msg_lines.append(line)
            continue

        if line == "msg":
            in_msg = True
            msg_lines = []
            continue
        if line == "maplore":
            in_lore = True
            lore_lines = []
            continue

        if line.startswith("arch "):
            stack.append([line[5:].strip(), {}, None])
            continue

        if line == "end":
            if not stack:
                continue
            arch, attrs, msg = stack.pop()
            if arch == "map" and not header_done:
                mapfile.header = _parse_header(attrs, msg)
                header_done = True
                continue
            # Only top-level objects have meaningful coordinates; anything
            # deeper is inventory.
            if not stack:
                obj = MapObject(
                    arch,
                    int(attrs.get("x", 0) or 0),
                    int(attrs.get("y", 0) or 0),
                    {k: v for k, v in attrs.items() if k in KEPT_ATTRS},
                    msg,
                )
                mapfile.objects.append(obj)
                if msg and "@match" in msg:
                    mapfile.has_dialogue = True
            continue

        if stack and " " in line:
            key, _, value = line.partition(" ")
            stack[-1][1].setdefault(key, value.strip())
        elif stack and line.strip():
            stack[-1][1].setdefault(line.strip(), "1")

    return mapfile


def _parse_header(attrs, msg):
    header = dict(attrs)
    for key in _HEADER_INT_KEYS:
        if key in header:
            raw = header[key]
            header[key] = int(raw) if raw.lstrip("-").isdigit() else 0
    if msg:
        header["msg"] = msg
    return header


def resolve_exit(from_path, slaying):
    """Resolve an exit's slaying string to a map-set-relative path.

    Absolute paths start with /; everything else is relative to the directory
    of the map holding the exit. Random-map exits (``/!``) resolve to nothing.
    """
    if not slaying or slaying.startswith("/!"):
        return None
    if slaying.startswith("/"):
        return os.path.normpath(slaying[1:])
    return os.path.normpath(os.path.join(os.path.dirname(from_path), slaying))


class MapSet:
    """Every map in the tree, plus the exit graph between them."""

    def __init__(self, root, skip=DEFAULT_SKIP, include_world=True):
        self.root = root
        self.skip = set(skip)
        self.include_world = include_world
        self.maps = {}
        self.edges = set()  # (from_path, to_path)
        self._adjacency = None

    def load(self, arches=None, progress=None):
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [
                d for d in dirnames if d not in self.skip and not d.startswith(".")
            ]
            for filename in filenames:
                full = os.path.join(dirpath, filename)
                rel = os.path.relpath(full, self.root)
                if not _looks_like_map(rel):
                    continue
                if not self.include_world and rel.startswith("world"):
                    continue
                mapfile = parse_map(self.root, rel)
                if mapfile is not None:
                    self.maps[rel] = mapfile
                    if progress and len(self.maps) % 500 == 0:
                        progress(len(self.maps))
        self._build_graph(arches)
        return self

    def _build_graph(self, arches=None):
        """Resolve exits to targets inside the map set.

        Most overworld entrances are not ``arch exit`` - they are houses, huts,
        caves, and pit holes, over a thousand archetypes of object type 66. If
        the archetype tree is available we use it; without it we fall back to a
        path-shaped-slaying heuristic, which is looser.
        """
        known = set(self.maps)
        exit_arches = arches.exits if arches else None
        for rel, mapfile in self.maps.items():
            for obj in mapfile.objects:
                slaying = obj.attrs.get("slaying")
                if not slaying:
                    continue
                if exit_arches is not None:
                    if obj.arch not in exit_arches:
                        continue
                elif "/" not in slaying and "." not in slaying:
                    continue
                target = resolve_exit(rel, slaying)
                if target and target in known:
                    mapfile.exits.append((obj, target))
                    self.edges.add((rel, target))

    @property
    def adjacency(self):
        if self._adjacency is None:
            adj = defaultdict(set)
            for a, b in self.edges:
                adj[a].add(b)
                adj[b].add(a)
            self._adjacency = adj
        return self._adjacency

    def dungeons(self, min_maps=3):
        """Group linked maps by directory.

        Using the directory as the dungeon boundary is a proxy - it merges some
        things and splits others - but it matches how the map set is laid out
        and needs no hand-maintained list.
        """
        by_dir = defaultdict(set)
        for a, b in self.edges:
            if os.path.dirname(a) == os.path.dirname(b) and os.path.dirname(a):
                by_dir[os.path.dirname(a)] |= {a, b}
        return {d: ms for d, ms in by_dir.items() if len(ms) >= min_maps}

    def entrances_to(self, directory, members):
        """Maps in the group that are reachable from outside it."""
        outside = {
            b for a, b in self.edges
            if b in members and os.path.dirname(a) != directory
        }
        return outside or {min(members)}

    def depth_map(self, members, entrances):
        """Breadth-first depth from the entrance maps.

        Wrong for any dungeon with two entrances at different depths, which is
        the third caveat on every shape figure this produces.
        """
        from collections import deque

        dist = {entry: 0 for entry in entrances}
        queue = deque(entrances)
        adj = self.adjacency
        while queue:
            current = queue.popleft()
            for neighbour in adj[current]:
                if neighbour in members and neighbour not in dist:
                    dist[neighbour] = dist[current] + 1
                    queue.append(neighbour)
        return dist


def chebyshev(ax, ay, bx, by):
    """Distance in king-moves, which is how Crossfire movement works.

    Knows nothing about walls: a monster three tiles away behind stone counts
    the same as one in the open corridor.
    """
    return max(abs(ax - bx), abs(ay - by))
