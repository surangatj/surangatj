"""
Updates dark_mode.svg / light_mode.svg with live GitHub stats:
uptime (age), repo count, contributed-repo count, commit count, stars,
followers, and total lines of code (additions/deletions) authored by me.

Inspired by Andrew6rant/Andrew6rant. Requires:
  ACCESS_TOKEN  - GitHub PAT with repo + read:user scopes
  USER_NAME     - GitHub login (defaults to surangatj)
"""
import datetime
import html
import json
import os
import re
import sys

import requests

USER_NAME = os.environ.get("USER_NAME", "surangatj")
HEADERS = {"Authorization": "token " + os.environ["ACCESS_TOKEN"]}
BIRTHDAY = datetime.date(1994, 1, 24)
GRAPHQL = "https://api.github.com/graphql"
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "loc_cache.json")
SVG_FILES = ["dark_mode.svg", "light_mode.svg"]


def gql(query, variables):
    r = requests.post(GRAPHQL, json={"query": query, "variables": variables}, headers=HEADERS)
    if r.status_code != 200:
        raise RuntimeError(f"GraphQL request failed ({r.status_code}): {r.text[:300]}")
    payload = r.json()
    if "errors" in payload:
        raise RuntimeError(f"GraphQL errors: {payload['errors']}")
    return payload["data"]


def uptime(today):
    """Age as 'X years, Y months, Z days'."""
    years = today.year - BIRTHDAY.year
    months = today.month - BIRTHDAY.month
    days = today.day - BIRTHDAY.day
    if days < 0:
        months -= 1
        prev_month_end = today.replace(day=1) - datetime.timedelta(days=1)
        days += prev_month_end.day
    if months < 0:
        months += 12
        years -= 1
    def plural(n, word):
        return f"{n} {word}" + ("" if n == 1 else "s")
    return f"{plural(years, 'year')}, {plural(months, 'month')}, {plural(days, 'day')}"


def user_info():
    q = """
    query($login: String!) {
      user(login: $login) {
        id
        followers { totalCount }
        repositoriesContributedTo(contributionTypes: [COMMIT], includeUserRepositories: false) { totalCount }
      }
    }"""
    u = gql(q, {"login": USER_NAME})["user"]
    return u["id"], u["followers"]["totalCount"], u["repositoriesContributedTo"]["totalCount"]


def repo_list():
    """All repos I own or collaborate on, with stars (own repos only) and default-branch commit totals."""
    q = """
    query($login: String!, $cursor: String) {
      user(login: $login) {
        repositories(first: 100, after: $cursor,
                     ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]) {
          totalCount
          pageInfo { hasNextPage endCursor }
          nodes {
            nameWithOwner
            isFork
            owner { login }
            stargazers { totalCount }
            defaultBranchRef { target { ... on Commit { history { totalCount } } } }
          }
        }
      }
    }"""
    repos, cursor = [], None
    own_count = 0
    stars = 0
    while True:
        data = gql(q, {"login": USER_NAME, "cursor": cursor})["user"]["repositories"]
        for n in data["nodes"]:
            if n["owner"]["login"].lower() == USER_NAME.lower():
                own_count += 1
                stars += n["stargazers"]["totalCount"]
            repos.append(n)
        if not data["pageInfo"]["hasNextPage"]:
            break
        cursor = data["pageInfo"]["endCursor"]
    return repos, own_count, stars


def repo_loc(name_with_owner, my_id):
    """Walk the default branch history and total my commits/additions/deletions."""
    owner, name = name_with_owner.split("/")
    q = """
    query($owner: String!, $name: String!, $id: ID!, $cursor: String) {
      repository(owner: $owner, name: $name) {
        defaultBranchRef {
          target {
            ... on Commit {
              history(first: 100, author: {id: $id}, after: $cursor) {
                totalCount
                pageInfo { hasNextPage endCursor }
                nodes { additions deletions }
              }
            }
          }
        }
      }
    }"""
    commits = additions = deletions = 0
    cursor = None
    while True:
        ref = gql(q, {"owner": owner, "name": name, "id": my_id, "cursor": cursor})["repository"]["defaultBranchRef"]
        if ref is None:
            return 0, 0, 0
        hist = ref["target"]["history"]
        commits = hist["totalCount"]
        for node in hist["nodes"]:
            additions += node["additions"]
            deletions += node["deletions"]
        if not hist["pageInfo"]["hasNextPage"]:
            break
        cursor = hist["pageInfo"]["endCursor"]
    return commits, additions, deletions


def gather(my_id, repos):
    """Sum my commits and LOC across repos, using the cache to skip unchanged repos."""
    try:
        with open(CACHE_FILE) as f:
            cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cache = {}
    my_commits = additions = deletions = 0
    for repo in repos:
        name = repo["nameWithOwner"]
        ref = repo["defaultBranchRef"]
        branch_total = ref["target"]["history"]["totalCount"] if ref else 0
        cached = cache.get(name)
        if cached and cached["branch_total"] == branch_total:
            entry = cached
        else:
            c, a, d = repo_loc(name, my_id)
            entry = {"branch_total": branch_total, "commits": c, "additions": a, "deletions": d}
            cache[name] = entry
            print(f"  scanned {name}: {c} commits, +{a} -{d}")
        my_commits += entry["commits"]
        additions += entry["additions"]
        deletions += entry["deletions"]
    # drop cache entries for repos that no longer exist
    live = {r["nameWithOwner"] for r in repos}
    cache = {k: v for k, v in cache.items() if k in live}
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2, sort_keys=True)
    return my_commits, additions, deletions


INFO_X = 390          # x of the right-hand text column
ROW_WIDTH = 60        # every info row is padded to this many characters

ROW_RE = re.compile(r'^<tspan x="' + str(INFO_X) + r'" y="\d+">.*</tspan>$')
DOTS_RE = re.compile(r'(<tspan class="cc" id="\w+_dots"> )(\.*)( </tspan>)')
TAG_RE = re.compile(r"</?tspan[^>]*>")


def replace_id(svg, element_id, new_text):
    pattern = re.compile(r'(<tspan[^>]*id="' + re.escape(element_id) + r'"[^>]*>)[^<]*(</tspan>)')
    if not pattern.search(svg):
        print(f"  WARNING: id '{element_id}' not found in SVG", file=sys.stderr)
    return pattern.sub(lambda m: m.group(1) + new_text + m.group(2), svg)


def visible_len(markup):
    return len(html.unescape(TAG_RE.sub("", markup)))


def rejustify(row):
    """Grow/shrink a row's dot leaders so it stays exactly ROW_WIDTH characters.

    Stat values change length over time (46 -> 100 repos); without this the
    right-hand edge of the card drifts out of alignment.
    """
    runs = list(DOTS_RE.finditer(row))
    delta = ROW_WIDTH - visible_len(row)
    if not runs or delta == 0:
        return row
    share = [delta // len(runs)] * len(runs)
    share[-1] += delta - sum(share)               # last run absorbs the remainder

    out, cursor = "", 0
    for run, d in zip(runs, share):
        out += row[cursor:run.start()]
        out += run.group(1) + "." * max(0, len(run.group(2)) + d) + run.group(3)
        cursor = run.end()
    out += row[cursor:]

    if visible_len(out) > ROW_WIDTH:      # dot leaders exhausted; values outgrew the row
        print(f"  WARNING: row exceeds {ROW_WIDTH} cols and may clip: "
              f"{TAG_RE.sub('', out)[:80]}", file=sys.stderr)
    return out


def update_svgs(values):
    for path in SVG_FILES:
        with open(path, encoding="utf-8") as f:
            svg = f.read()
        for element_id, text in values.items():
            svg = replace_id(svg, element_id, text)
        svg = "\n".join(rejustify(line) if ROW_RE.match(line) else line
                        for line in svg.split("\n"))
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"updated {path}")


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    today = datetime.date.today()
    my_id, followers, contributed = user_info()
    repos, own_count, stars = repo_list()
    commits, additions, deletions = gather(my_id, repos)
    fmt = "{:,}".format
    update_svgs({
        "age_data": uptime(today),
        "repo_data": fmt(own_count),
        "contrib_data": fmt(contributed),
        "commit_data": fmt(commits),
        "star_data": fmt(stars),
        "follower_data": fmt(followers),
        "loc_data": fmt(additions - deletions),
        "loc_add": fmt(additions),          # the '++' / '--' suffixes are static markup
        "loc_del": fmt(deletions),
    })


if __name__ == "__main__":
    main()
