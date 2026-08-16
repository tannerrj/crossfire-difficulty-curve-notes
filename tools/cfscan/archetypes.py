"""Load the archetype tree.

Everything the map scans need to know about archetypes comes from here: which
names are monsters, which of those are peaceful, which are exits, and what a
given archetype is called in plain English.

The arch tree is a few thousand small .arc files; one walk builds every set.
"""

import os
import re

# Object types we care about. Full list lives in the server's include/define.h.
TYPE_BOOK = 8
TYPE_EXIT = 66
TYPE_SIGN = 98

_OBJECT_RE = re.compile(r"^Object\s+(\S+)")


class Archetypes:
    """Name sets and lookups built from a crossfire-arch checkout."""

    def __init__(self, root):
        self.root = root
        self.monsters = set()
        self.peaceful = set()  # friendly or unaggressive by default
        self.exits = set()
        self.signs = set()
        self.books = set()
        self.display_name = {}  # arch name -> human-readable name
        self.exp = {}  # arch name -> stats.exp, for the difficulty estimate
        self._load()

    def _load(self):
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for filename in filenames:
                if filename.endswith(".arc"):
                    self._read_arc(os.path.join(dirpath, filename))

    def _read_arc(self, path):
        name = None
        attrs = {}
        with open(path, encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.rstrip("\n")
                match = _OBJECT_RE.match(line)
                if match:
                    name, attrs = match.group(1), {}
                    continue
                if line.strip() == "end":
                    if name:
                        self._classify(name, attrs)
                    name, attrs = None, {}
                    continue
                if name and " " in line:
                    key, _, value = line.strip().partition(" ")
                    attrs.setdefault(key, value)

    def _classify(self, name, attrs):
        obj_type = attrs.get("type")
        obj_type = int(obj_type) if obj_type and obj_type.lstrip("-").isdigit() else None

        if attrs.get("monster") == "1":
            self.monsters.add(name)
            if attrs.get("friendly") == "1" or attrs.get("unaggressive") == "1":
                self.peaceful.add(name)
        if obj_type == TYPE_EXIT:
            self.exits.add(name)
        elif obj_type == TYPE_SIGN:
            self.signs.add(name)
        elif obj_type == TYPE_BOOK:
            self.books.add(name)

        if "name" in attrs:
            self.display_name[name] = attrs["name"]

        exp = attrs.get("exp")
        if exp and exp.lstrip("-").isdigit():
            self.exp[name] = int(exp)

    @property
    def hostile(self):
        """Monster archetypes that are not peaceful by default.

        A map instance can still override this either way, so callers must also
        check the instance's own friendly/unaggressive attributes.
        """
        return self.monsters - self.peaceful

    def words_for(self, arch_name):
        """Words a map author might use to refer to this archetype.

        Used to check whether a sign actually names the item a gate wants:
        an altar keyed on ``demon_head`` should be matched by a sign that says
        "demon head" as readily as one that says "demon_head".
        """
        words = {arch_name.lower()}
        words.add(arch_name.replace("_", " ").lower())
        display = self.display_name.get(arch_name)
        if display:
            words.add(display.lower())
        return {w for w in words if len(w) > 2}


def load_exp_table(server_root):
    """Parse lib/config/exp_table into a list indexed by level.

    Returns None if the table cannot be found, in which case the caller should
    skip the computed-difficulty comparison rather than guess at it.
    """
    path = os.path.join(server_root, "lib", "config", "exp_table")
    if not os.path.exists(path):
        return None

    values = []
    with open(path, encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("max_level"):
                continue
            for token in re.split(r"[,\s]+", line):
                if token.isdigit():
                    values.append(int(token))
    return values or None
