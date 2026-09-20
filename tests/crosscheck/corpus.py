"""The scalars the crosscheck runs through the real parsers.

Two sources, on purpose. The handwritten list covers the cases the dialect
modules make claims about, so a wrong claim fails loudly. The generated list
covers the cases nobody thought of, which is where transcription errors
actually live: the first version of the go-yaml dialect got `1e999` wrong, and
no handwritten list was ever going to contain `1e999`.
"""

from __future__ import annotations

import itertools
from pathlib import Path

#: Cases the dialect docstrings make a claim about. If one of these changes,
#: a comment somewhere is now a lie.
NAMED = [
    # The one everybody has heard of.
    "no", "No", "NO", "yes", "Yes", "YES", "on", "On", "ON", "off", "Off", "OFF",
    "y", "Y", "n", "N",
    "true", "True", "TRUE", "false", "False", "FALSE",
    # Leading zero: 10, 10, 12.
    "012", "0777", "010", "08", "09", "00", "0",
    # Base prefixes, which not everyone has.
    "0o12", "0x1f", "0xFF", "0b101", "0o777", "0X1F", "0B11",
    # Underscores: 1000, 1000, "1_000".
    "1_000", "0_1_2", "1_0.5", "1__0",
    # Base 60, dropped in 1.2 and still in PyYAML.
    "12:30", "1:2:3", "90:00", "12:60",
    # Floats, and the exponent PyYAML's regex will not take without a dot.
    "1.0", "1.10", "1.", ".5", "1e3", "1E3", "1.5e3", ".5e1", "1e-3", "1.5E+3",
    "-0.0", "+1", "-1", "+.5",
    # Specials.
    ".inf", ".Inf", ".INF", "-.inf", "+.inf", ".nan", ".NaN", ".NAN", "inf", "nan",
    # Nulls and the tags only PyYAML gives a name to.
    "~", "null", "Null", "NULL", "none", "None", "<<", "=",
    # Dates, including one that does not exist and one spelled short.
    "2026-09-19", "2026-9-19", "2026-02-31", "2026-13-01", "2026-02-28",
    "2026-09-19T10:30:00Z", "2026-09-19T10:30:00", "2026-09-19 10:30:00",
    "2026-09-19T10:30:00+01:00", "2026-09-19t10:30:00.5Z",
    # Big enough to stop being exact, or to stop being a number at all.
    "9007199254740993", "99999999999999999999", "1e999", "-1e999",
    "9223372036854775807", "9223372036854775808", "18446744073709551616",
    # Ordinary strings that must stay ordinary.
    "Norway", "NO_PROXY", "latest", "v1.2.3", "8080", "hello world", "a:b",
]


def generated() -> list[str]:
    """Short strings built from the characters that drive the resolvers.

    Not random: an exhaustive sweep of the alphabet that the three
    implementations branch on, which is the set where they can differ.
    """
    alphabet = "0123456789.:+-_eExXoObBynYN~"
    out = {"".join(parts) for parts in itertools.product(alphabet, repeat=2)}
    out |= {"".join(parts) for parts in itertools.product("01289.:+-_exo", repeat=3)}
    # A leading zero and a separator are where the three part company, so go a
    # little deeper on exactly those.
    out |= {f"0{a}{b}{c}" for a in "0189bxo." for b in "0189_:" for c in "0189"}
    out |= {f"{a}{b}:{c}{d}" for a in "019" for b in "059" for c in "056" for d in "019"}
    return sorted(out)


def harvested() -> list[str]:
    """Plain scalars taken out of real YAML.

    Every distinct scalar that was not an ordinary string in 3,826 `.yml` and
    `.yaml` files from prometheus, grafana, home-assistant and ansible, plus a
    sample of ones that were. Generated input is good at the edges of a regex
    and bad at knowing what people write; this is the other half. It is where
    `0644` and `2025-05-03 13:10:00.000000000 Z` came from, neither of which
    anyone would have sat down and invented.
    """
    path = Path(__file__).parent / "harvested.txt"
    return [line for line in path.read_text().splitlines() if line]


def all_scalars() -> list[str]:
    seen = list(NAMED)
    known = set(seen)
    for text in generated() + harvested():
        if text not in known:
            seen.append(text)
            known.add(text)
    return seen
