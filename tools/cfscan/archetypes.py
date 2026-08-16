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

# Dropped before matching a requirement against a sign: they carry no
# identifying information and their presence or absence is just phrasing.
_STOPWORDS = frozenset({
    "the", "a", "an", "of", "from", "and", "to", "for", "with", "in", "on",
    "at", "is", "it", "s",
})


def _tokens(text):
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def _content_words(phrase):
    return [t for t in _tokens(phrase) if t not in _STOPWORDS and len(t) >= 3]


def _word_hit(token, words):
    """Match a requirement word against the words in a message.

    Allows plurals in both directions ("scholars of Kurte" naming a gate keyed
    on ``scholar of kurte``), and prefixes for words long enough that a prefix
    is unlikely to be a coincidence.
    """
    for word in words:
        if word == token or word == token + "s" or token == word + "s":
            return True
        if len(token) >= 5 and word.startswith(token):
            return True
    return False


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

    def phrases_for(self, arch_name):
        """Ways a map author might refer to this archetype.

        An altar keyed on ``demon_head`` should be matched by a sign saying
        "demon head" as readily as one saying "demon_head".
        """
        phrases = {arch_name, arch_name.replace("_", " ")}
        display = self.display_name.get(arch_name)
        if display:
            phrases.add(display)
        return {p for p in phrases if len(p) > 2}

    def names_requirement(self, arch_name, text):
        """Does ``text`` name the thing a gate keyed on ``arch_name`` wants?

        Every content word of the requirement has to appear somewhere in the
        text, in any order, allowing simple plurals. Matching the exact phrase
        is too strict to be useful: a mouth reading "drop the letter from the
        dwarf captives here" is plainly naming a gate keyed on "letter from
        dwarf captives", and an NPC offering "the head of an angry pixie" is
        naming one keyed on "Angry Pixie's head".

        Measured over the whole map set, loosening this way moved four maps out
        of a 317-map queue, three of them correctly. A small effect either way,
        and useful mainly as evidence that the strict result was not riddled
        with false positives.
        """
        words = set(_tokens(text))
        if not words:
            return False
        for phrase in self.phrases_for(arch_name):
            required = _content_words(phrase)
            if required and all(_word_hit(w, words) for w in required):
                return True
        return False


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
