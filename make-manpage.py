#!/usr/bin/env python3
"""Render sardinetracker(7) -- the triage runbook, as a man page.

Two inputs, one output. TROUBLESHOOTING.md carries the general triage and is
the same file the website publishes, so the procedures can't drift.
runbook-site.md is the private overlay holding this installation's real
addresses, and is folded in as the first section.

    python3 make-manpage.py            # write man/sardinetracker.7
    python3 make-manpage.py --install  # ...and copy it onto the manpath

Then: man sardinetracker

No pandoc. It would mean a Haskell toolchain for one document, and the
markdown here uses a small enough subset that rendering it directly is less
machinery than installing a converter.
"""

import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GENERAL = ROOT / "TROUBLESHOOTING.md"
SITE = ROOT / "runbook-site.md"
OUT = ROOT / "man" / "sardinetracker.7"
MANPATH = Path.home() / ".local/share/man/man7"

NAME = "sardinetracker"
SECTION = "7"

# Characters roff would rather receive as escapes.
UNICODE = {
    "\u2014": r"\(em", "\u2013": r"\(en", "\u2018": "`", "\u2019": "'",
    "\u201c": r"\(lq", "\u201d": r"\(rq", "\u2192": r"\(->", "\u2190": r"\(<-",
    "\u2265": r"\(>=", "\u2264": r"\(<=", "\u00b7": r"\(bu", "\u2026": "...",
}


def esc(text: str, *, literal: bool = False) -> str:
    """Escape for roff. `literal` also protects hyphens so flags copy cleanly."""
    text = text.replace("\\", r"\e")
    # Hyphens first: the unicode map emits roff escapes that themselves contain
    # hyphens (\(->, \(<-), and escaping those would corrupt them.
    if literal:
        text = text.replace("-", r"\-")
    for ch, repl in UNICODE.items():
        text = text.replace(ch, repl)
    return text


def inline(text: str) -> str:
    """Markdown inline spans -> roff. Code and bold both render bold, which is
    the man convention for anything you would type literally."""
    out = []
    pos = 0
    # Handle `code` first so its hyphens get protected before anything else.
    for m in re.finditer(r"`([^`]+)`", text):
        out.append(inline_no_code(text[pos:m.start()]))
        out.append(r"\fB" + esc(m.group(1), literal=True) + r"\fR")
        pos = m.end()
    out.append(inline_no_code(text[pos:]))
    return "".join(out)


def inline_no_code(text: str) -> str:
    text = esc(text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)          # links -> text
    text = re.sub(r"\*\*([^*]+)\*\*", r"\\fB\1\\fR", text)         # bold
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\\fI\1\\fR", text)  # italic
    return text


def protect(line: str) -> str:
    """A line starting with . or ' is a roff request; neuter it."""
    return r"\&" + line if line[:1] in (".", "'") else line


def render_table(rows):
    """Markdown table -> aligned plain text. Avoids depending on tbl(1)."""
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    cells = [c for c in cells if not all(re.fullmatch(r":?-{2,}:?", x) for x in c)]
    if not cells:
        return []
    widths = [max(len(re.sub(r"[`*]", "", r[i])) for r in cells)
              for i in range(len(cells[0]))]
    out = [".RS 4", ".nf"]
    for n, row in enumerate(cells):
        plain = [re.sub(r"[`*]", "", c) for c in row]
        line = "  ".join(p.ljust(w) for p, w in zip(plain, widths)).rstrip()
        out.append(protect(esc(line, literal=True)))
        if n == 0:
            out.append(protect(esc("  ".join("-" * w for w in widths), literal=True)))
    out += [".fi", ".RE", ".PP"]
    return out


def convert(md: str, *, top_level: int = 2) -> list[str]:
    """Markdown -> roff lines. Handles the subset these documents use."""
    # A leading "# Title" is the document's own title; the man page already has
    # a NAME section, so emitting it produces a redundant .SH.
    md = re.sub(r"\A#\s+.*?\n", "", md, count=1)

    lines = md.split("\n")
    out: list[str] = []
    i = 0
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            out.append(".RE")
            in_list = False

    while i < len(lines):
        line = lines[i]

        if line.strip().startswith("<!--"):                      # comment block
            while i < len(lines) and "-->" not in lines[i]:
                i += 1
            i += 1
            continue

        fence = re.match(r"^(\s*)```", line)                      # fenced code
        if fence:
            # Match at ANY indentation. A fence nested inside a numbered step is
            # still a code block, and treating it as prose turns the commands --
            # the whole point of a runbook -- into inline run-on text.
            pad = len(fence.group(1))
            i += 1
            block = []
            while i < len(lines) and not re.match(r"^\s*```", lines[i]):
                block.append(lines[i][pad:] if lines[i][:pad].isspace()
                             or not lines[i][:pad] else lines[i])
                i += 1
            i += 1
            if not in_list:
                out.append(".PP")
            out += [".RS 4", ".nf", r"\fB"]
            out += [protect(esc(b, literal=True)) or "" for b in block]
            out += [r"\fR", ".fi", ".RE"]
            if not in_list:
                out.append(".PP")
            continue

        if re.match(r"^\|.*\|\s*$", line):                        # table
            close_list()
            rows = []
            while i < len(lines) and re.match(r"^\|.*\|\s*$", lines[i]):
                rows.append(lines[i])
                i += 1
            out += render_table(rows)
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)                  # heading
        if m:
            close_list()
            depth = len(m.group(1))
            title = re.sub(r"[`*]", "", m.group(2))
            if depth <= top_level:
                out += [".SH " + esc(title.upper())]
            else:
                out += [".SS " + esc(title)]
            i += 1
            continue

        m = re.match(r"^(\s*)(\d+)\.\s+(.*)$", line)              # ordered item
        if m:
            if not in_list:
                out.append(".RS 4")
                in_list = True
            out += [f'.IP "{m.group(2)}." 4', protect(inline(m.group(3)))]
            i += 1
            continue

        m = re.match(r"^(\s*)[-*]\s+(.*)$", line)                 # bullet item
        if m:
            if not in_list:
                out.append(".RS 4")
                in_list = True
            out += [r".IP \(bu 3", protect(inline(m.group(2)))]
            i += 1
            continue

        if not line.strip():                                      # blank
            i += 1
            continue

        para = [line]                                             # paragraph
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
            r"^(#{1,6}\s|\s*```|\||\s*[-*]\s|\s*\d+\.\s)", lines[i]
        ):
            para.append(lines[i])
            i += 1
        if in_list:
            # Continue at the step's text indent. Without the tagless .IP, prose
            # following a code block falls back to the list indent and reads as
            # a new item rather than as part of the step above it.
            out += ['.IP "" 4', protect(inline(" ".join(x.strip() for x in para)))]
        else:
            out += [".PP", protect(inline(" ".join(x.strip() for x in para)))]

    close_list()
    return out


def apply_subs(md: str, subs: dict[str, str]) -> str:
    """Substitute placeholders, preserving column alignment in ASCII diagrams.

    Inside a box-drawing block a shorter replacement is padded back out to the
    placeholder's width; a longer one would push the borders out of true, so it
    is left alone there and only the prose gets it.
    """
    out, in_fence, diagram = [], False, False
    for line in md.split("\n"):
        if re.match(r"^\s*```", line):
            if not in_fence:
                diagram = False
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence and re.search(r"[+][-]{2,}|[-]{3,}>", line):
            diagram = True
        for placeholder, real in subs.items():
            if placeholder not in line:
                continue
            if in_fence and diagram:
                if len(real) <= len(placeholder):
                    line = line.replace(placeholder, real.ljust(len(placeholder)))
            else:
                line = line.replace(placeholder, real)
        out.append(line)
    return "\n".join(out)


def read_substitutions(site_md: str) -> dict[str, str]:
    """Placeholder -> real value, from the overlay's Substitutions table."""
    m = re.search(r"## Substitutions\n.*?\n((?:\|.*\n)+)", site_md, re.S)
    if not m:
        return {}
    subs = {}
    for row in m.group(1).strip().split("\n"):
        cells = [c.strip().strip("`") for c in row.strip().strip("|").split("|")]
        if len(cells) == 2 and not set(cells[0]) <= set(":- "):
            subs[cells[0]] = cells[1]
    subs.pop("Placeholder", None)
    return subs


def manpath_of(path: Path) -> str:
    """A file path as a bold roff literal, shortened to ~ where it applies."""
    try:
        shown = "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        shown = str(path)
    return r"\fB" + esc(shown, literal=True) + r"\fR"


def build() -> str:
    today = dt.date.today().isoformat()
    head = [
        f'.TH {NAME.upper()} {SECTION} "{today}" "{NAME}" '
        f'"Miscellaneous Information Manual"',
        ".nh",   # never hyphenate: REMOTE_ACCESS.md split across lines once
        ".ad l",  # ragged right reads better than justified for technical text
        ".SH NAME",
        rf"{NAME} \- topology and failure triage for a self\-hosted instance",
        ".SH DESCRIPTION",
        ".PP",
        "Three kinds of client reach one SQLite database through Cloudflare, each "
        "carrying a different credential, and a fourth path reaches the machine "
        "over Tailscale without touching Cloudflare at all. That split is why an "
        "Access fault and an SSH fault are never the same fault, and it is most "
        "of what this page exists to disentangle.",
        ".PP",
        "Sections are ordered by what you see first rather than by which component "
        "failed. Work down from the top of the section that matches the symptom; "
        "the cheap and likely checks come first.",
    ]

    site_md = SITE.read_text(encoding="utf-8") if SITE.exists() else ""
    general_md = GENERAL.read_text(encoding="utf-8")

    subs = read_substitutions(site_md)
    if subs:
        # A runbook on this machine should carry this machine's values.
        general_md = apply_subs(general_md, subs)
        # ...which makes a section explaining the placeholders pointless.
        general_md = re.sub(r"\n## Placeholders\n.*?(?=\n## )", "\n",
                            general_md, flags=re.S)
        site_md = re.sub(r"\n## Substitutions\n.*?(?=\n## |\Z)", "\n",
                         site_md, flags=re.S)

    body: list[str] = []
    if site_md:
        body += convert(site_md)
    body += convert(general_md)

    tail: list[str] = [
        ".SH FILES",
        ".TP",
        manpath_of(GENERAL),
        "The general triage, and the source this page renders from.",
    ]
    tail += ([".TP", manpath_of(SITE),
              "This installation's own addresses, folded in as the opening "
              "section. Local only; keep it out of version control."]
             if SITE.exists() else [])
    tail += [
        ".TP",
        manpath_of(Path(__file__).resolve()),
        "Regenerates this page. Run it after editing either source.",
        ".SH SEE ALSO",
        ".PP",
        r"\fBtailscale\fR(1), \fBcloudflared\fR(8), \fBsystemctl\fR(1), "
        r"\fBjournalctl\fR(1), \fBsqlite3\fR(1)",
        ".PP",
        "The same guide as a web page, for when this machine is not the one in "
        "your hand: "
        r"\fBhttps://sardinetracker.com/docs/troubleshooting\fR.",
        ".SH AUTHOR",
        ".PP",
        "Alaric Moore.",
    ]

    return "\n".join(head + body + tail) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Render sardinetracker(7).")
    ap.add_argument("--install", action="store_true",
                    help=f"also copy the page into {MANPATH}")
    args = ap.parse_args()

    if not GENERAL.exists():
        sys.exit(f"missing {GENERAL}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}  ({OUT.stat().st_size // 1024} KB)")

    if args.install:
        MANPATH.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OUT, MANPATH / OUT.name)
        print(f"installed {MANPATH / OUT.name}")
        if shutil.which("mandb"):
            subprocess.run(["mandb", "-q", str(MANPATH.parent)],
                           capture_output=True)
        print(f"try: man {NAME}")


if __name__ == "__main__":
    main()
