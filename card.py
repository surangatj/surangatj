"""Rebuild dark_mode.svg / light_mode.svg — the neofetch-style profile card.

Layout follows Andrew6rant/Andrew6rant: a rounded panel, a chunky ASCII
portrait on the left at 16px, and a right column of dot-leader key/value
rows grouped under section rules.

Run this by hand whenever the card's text or portrait should change:

    pip install pillow requests && python card.py

It rebuilds both SVGs from scratch but carries the live stat values across
from the existing files, so a rebuild never resets numbers the daily job
has already computed. The GitHub Action only runs today.py, which edits
those values in place -- it never needs Pillow.
"""
import html
import io
import os
import re

import requests
from PIL import Image, ImageOps, ImageEnhance, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = HERE
AVATAR_URL = "https://github.com/surangatj.png?size=460"
AVATAR_CACHE = os.path.join(HERE, "cache", "avatar.png")

W, H = 985, 530
ART_X, INFO_X = 15, 390
Y0, DY = 32, 20
COLS, ROWS = 36, 24
WIDTH = 60                     # every info row is padded to this many columns

RAMP = "@%#*+=;:,.` "
WHITE_CUT = 0.86

# The wink. Row 6 of the portrait is the brow line, row 7 the eyes; the
# viewer's-left eye sits at columns 10-13. Closing just that eye -- brow left
# alone -- is what reads as a wink rather than a blink at this resolution.
EYE_ROW, EYE_COL = 7, 10
EYE_OPEN, EYE_SHUT = "=#%+", ".--."

THEMES = {
    "dark_mode.svg":  dict(bg="#161b22", fg="#c9d1d9", key="#ffa657", val="#a5d6ff",
                           cc="#616e7f", add="#3fb950", dele="#f85149",
                           ansi=["#484f58", "#ff7b72", "#3fb950", "#d29922",
                                 "#58a6ff", "#bc8cff", "#39c5cf", "#b1bac4"],
                           bright=["#6e7681", "#ffa198", "#56d364", "#e3b341",
                                   "#79c0ff", "#d2a8ff", "#56d4dd", "#f0f6fc"]),
    "light_mode.svg": dict(bg="#f6f8fa", fg="#24292f", key="#953800", val="#0a3069",
                           cc="#c2cfde", add="#1a7f37", dele="#cf222e",
                           ansi=["#24292f", "#cf222e", "#1a7f37", "#9a6700",
                                 "#0969da", "#8250df", "#1b7c83", "#6e7781"],
                           bright=["#57606a", "#a40e26", "#2da44e", "#bf8700",
                                   "#218bff", "#a475f9", "#3192aa", "#8c959f"]),
}


# ---------------------------------------------------------------- ascii art
def avatar():
    """The GitHub avatar, cached locally so repeat runs work offline."""
    if not os.path.exists(AVATAR_CACHE):
        r = requests.get(AVATAR_URL, timeout=30)
        r.raise_for_status()
        os.makedirs(os.path.dirname(AVATAR_CACHE), exist_ok=True)
        Image.open(io.BytesIO(r.content)).convert("RGB").save(AVATAR_CACHE)
        print("fetched", AVATAR_URL)
    return Image.open(AVATAR_CACHE)


def ascii_art(crop=(120, 30, 340, 300), contrast=1.2, edge=0.30):
    im = avatar().convert("RGB").crop(crop)
    px = im.load()
    w, h = im.size
    for y in range(h):                       # orange backdrop + white ring -> blank
        for x in range(w):
            r, g, b = px[x, y]
            if r > 150 and r - b > 60 and g < r - 40:
                px[x, y] = (255, 255, 255)

    g = ImageOps.autocontrast(im.convert("L"), cutoff=1)
    g = ImageEnhance.Contrast(g).enhance(contrast)
    e = ImageOps.autocontrast(
        g.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(3)), cutoff=2)

    small, esmall = g.resize((COLS, ROWS), Image.LANCZOS).load(), \
                    e.resize((COLS, ROWS), Image.LANCZOS).load()
    rows = []
    for y in range(ROWS):
        line = ""
        for x in range(COLS):
            base = small[x, y] / 255.0
            v = max(0.0, base - edge * (esmall[x, y] / 255.0))
            line += " " if (base >= WHITE_CUT and v >= WHITE_CUT) \
                    else RAMP[min(len(RAMP) - 1, int(v * len(RAMP)))]
        rows.append(line.rstrip())
    return rows


# ------------------------------------------------------------------- markup
def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def seg(text, cls=None, sid=None):
    a = (f' class="{cls}"' if cls else "") + (f' id="{sid}"' if sid else "")
    return f"<tspan{a}>{esc(text)}</tspan>" if a else esc(text)


def kv(key, value, vid=None):
    """'. Key: ....... value' padded to WIDTH columns."""
    n = WIDTH - 5 - len(key) - len(value)
    dots = " " + "." * max(1, n) + " "
    return (seg(". ", "cc") + seg(key, "key") + ":"
            + seg(dots, "cc", f"{vid}_dots" if vid else None)
            + seg(value, "value", vid))


def rule(label):
    n = WIDTH - len(label) - 3
    return esc(label) + "—" * max(1, n) + "-—-"


def color_blocks(palette):
    """The swatch row real neofetch prints: 8 terminal colours, 3 cells each."""
    return "  " + "".join(f'<tspan fill="{c}">███</tspan>' for c in palette)


def prompt():
    """A shell prompt with a blinking block cursor, as if neofetch just exited."""
    return seg("suranga@tj", "key") + ":~$ " + seg("█", "cursor")


def stats_repos(repos, contrib, stars):
    """'. Repos: ... N {Contributed: N} | Stars: ... N'"""
    fixed = 2 + 5 + 1 + 2 + 11 + 2 + len(contrib) + 4 + 5 + 1 + len(repos) + len(stars)
    slack = WIDTH - fixed - 4          # 4 = the spaces bracketing both dot leaders
    d1, d2 = max(1, slack // 2), max(1, slack - slack // 2)
    return (seg(". ", "cc") + seg("Repos", "key") + ":"
            + seg(" " + "." * d1 + " ", "cc", "repo_data_dots")
            + seg(repos, "value", "repo_data")
            + " {" + seg("Contributed", "key") + ": "
            + seg(contrib, "value", "contrib_data") + "} | "
            + seg("Stars", "key") + ":"
            + seg(" " + "." * d2 + " ", "cc", "star_data_dots")
            + seg(stars, "value", "star_data"))


def stats_commits(commits, followers):
    fixed = 2 + 7 + 1 + 3 + 9 + 1 + 2 + 2 + len(commits) + len(followers)
    slack = WIDTH - fixed
    d1, d2 = max(1, slack // 2), max(1, slack - slack // 2)
    return (seg(". ", "cc") + seg("Commits", "key") + ":"
            + seg(" " + "." * d1 + " ", "cc", "commit_data_dots")
            + seg(commits, "value", "commit_data") + " | "
            + seg("Followers", "key") + ":"
            + seg(" " + "." * d2 + " ", "cc", "follower_data_dots")
            + seg(followers, "value", "follower_data"))


def stats_loc(loc, add, dele):
    label = "Lines of Code on GitHub"
    fixed = 2 + len(label) + 1 + 2 + len(loc) + 3 + len(add) + 2 + 2 + len(dele) + 4
    dots = max(1, WIDTH - fixed)
    return (seg(". ", "cc") + seg(label, "key") + ":"
            + seg(" " + "." * dots + " ", "cc", "loc_data_dots")
            + seg(loc, "value", "loc_data") + " ( "
            + seg(add, "addColor", "loc_add") + seg("++", "addColor") + ", "
            + seg(dele, "delColor", "loc_del") + seg("--", "delColor") + " )")


# Seed values, used only when building a card from nothing; a rebuild over an
# existing card reuses whatever today.py last wrote (see live_values).
SEED = {
    "age_data": "32 years, 6 months, 8 days",
    "repo_data": "46", "contrib_data": "3", "star_data": "1",
    "commit_data": "2,561", "follower_data": "4",
    "loc_data": "93,599", "loc_add": "220,766", "loc_del": "127,167",
}


def live_values(path):
    """Stat values already in the card on disk, so rebuilding preserves them."""
    v = dict(SEED)
    if not os.path.exists(path):
        return v
    svg = open(path, encoding="utf-8").read()
    for key in SEED:
        m = re.search(r'id="%s"[^>]*>([^<]*)<' % re.escape(key), svg)
        if m:
            v[key] = html.unescape(m.group(1))
    return v


def info_rows(theme, v):
    return [
        rule("suranga@tj -"),
        kv("OS", "macOS, iOS"),
        kv("Uptime", v["age_data"], "age_data"),
        kv("Host", "Knowit"),
        kv("Kernel", "Data Engineer, AI Dev & Data Scientist"),
        kv("IDE", "VSCode, Databricks, PyCharm"),
        kv("Clouds", "Azure, AWS, Google Cloud, Huawei"),
        seg(". ", "cc"),
        kv("Languages.Programming", "Python, Spark, SQL, React"),
        kv("Languages.Real", "Sinhala, English, Swedish"),
        seg(". ", "cc"),
        kv("Hobbies.Software", "iOS App Dev, Lightroom"),
        kv("Hobbies.Hardware", "Bitcoin Mining"),
        rule("- Contact -"),
        kv("Email.Personal", "suranga4@gmail.com"),
        kv("LinkedIn", "in/surangan"),
        kv("GitHub", "surangatj"),
        rule("- GitHub Stats -"),
        stats_repos(v["repo_data"], v["contrib_data"], v["star_data"]),
        stats_commits(v["commit_data"], v["follower_data"]),
        stats_loc(v["loc_data"], v["loc_add"], v["loc_del"]),
        seg(". ", "cc"),
        color_blocks(theme["ansi"]),
        color_blocks(theme["bright"]),
        prompt(),
    ]


def shut_eye(rows):
    """rows[EYE_ROW] with the viewer's-left eye closed."""
    row = rows[EYE_ROW]
    found = row[EYE_COL:EYE_COL + len(EYE_OPEN)]
    if found != EYE_OPEN:
        raise SystemExit(
            f"portrait shifted: expected {EYE_OPEN!r} at row {EYE_ROW} col {EYE_COL}, "
            f"found {found!r}. Re-locate the eye before rebuilding.")
    return row[:EYE_COL] + EYE_SHUT + row[EYE_COL + len(EYE_SHUT):]


def render(theme, v):
    art = ascii_art()

    def art_text(indices, rows, cls):
        tspans = "\n".join(
            f'<tspan x="{ART_X}" y="{Y0 + i * DY}">{esc(rows[i])}</tspan>' for i in indices)
        return (f'<text x="{ART_X}" y="{Y0}" fill="{theme["fg"]}" class="{cls}">'
                f'\n{tspans}\n</text>')

    # The eye row lives in its own <text> so only that one line is duplicated
    # for the animation; everything else is drawn once.
    still = [i for i in range(len(art)) if i != EYE_ROW]
    winking = list(art)
    winking[EYE_ROW] = shut_eye(art)
    art_blocks = "\n".join([
        art_text(still, art, "ascii"),
        art_text([EYE_ROW], art, "ascii eye-open"),
        art_text([EYE_ROW], winking, "ascii eye-shut"),
    ])

    info_tspans = "\n".join(
        f'<tspan x="{INFO_X}" y="{Y0 + i * DY}">{row}</tspan>'
        for i, row in enumerate(info_rows(theme, v)))

    return f"""<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" font-family="ConsolasFallback,Consolas,monospace" width="{W}px" height="{H}px" viewBox="0 0 {W} {H}" font-size="16px">
<style>
@font-face {{
src: local('Consolas'), local('Consolas Bold');
font-family: 'ConsolasFallback';
font-display: swap;
-webkit-size-adjust: 109%;
size-adjust: 109%;
}}
.key {{fill: {theme['key']};}}
.value {{fill: {theme['val']};}}
.addColor {{fill: {theme['add']};}}
.delColor {{fill: {theme['dele']};}}
.cc {{fill: {theme['cc']};}}
text, tspan {{white-space: pre;}}
.eye-open {{animation: eye-open 6s infinite;}}
.eye-shut {{opacity: 0; animation: eye-shut 6s infinite;}}
.cursor {{fill: {theme['key']}; animation: blink 1.2s step-end infinite;}}
@keyframes eye-open {{0%, 89% {{opacity: 1;}} 90%, 94% {{opacity: 0;}} 95%, 100% {{opacity: 1;}}}}
@keyframes eye-shut {{0%, 89% {{opacity: 0;}} 90%, 94% {{opacity: 1;}} 95%, 100% {{opacity: 0;}}}}
@keyframes blink {{0%, 50% {{opacity: 1;}} 51%, 100% {{opacity: 0;}}}}
@media (prefers-reduced-motion: reduce) {{
.eye-open {{animation: none; opacity: 1;}}
.eye-shut {{animation: none; opacity: 0;}}
.cursor {{animation: none; opacity: 1;}}
}}
</style>
<rect width="{W}px" height="{H}px" fill="{theme['bg']}" rx="15"/>
{art_blocks}
<text x="{INFO_X}" y="{Y0}" fill="{theme['fg']}">
{info_tspans}
</text>
</svg>
"""


if __name__ == "__main__":
    for fname, theme in THEMES.items():
        path = os.path.join(OUT_DIR, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(render(theme, live_values(path)))
        print("wrote", path)
