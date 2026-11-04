#!/usr/bin/env python3
"""Builds the profile's statistics card as an SVG, from the GitHub API.

Runs in Actions once a day (.github/workflows/stats.yml) with the workflow's token.
Replaces github-readme-stats, whose public server answers 503 more often than not.

    python3 stats_card.py --user inkoffTTV --out dist
    python3 stats_card.py --user inkoffTTV --out dist --mock sample.json   # no network
"""
import argparse, datetime, html, json, os, sys, urllib.request

API = "https://api.github.com"
COLORS = {  # github-linguist colors for the languages likely to show up
    "C++": "#f34b7d", "C": "#555555", "TypeScript": "#3178c6", "JavaScript": "#f1e05a", "Python": "#3572A5",
    "QML": "#44a51c", "CMake": "#DA3434", "Kotlin": "#A97BFF", "Java": "#b07219", "Shell": "#89e051",
    "PowerShell": "#012456", "CSS": "#563d7c", "HTML": "#e34c26", "Dockerfile": "#384d54", "GLSL": "#5686a5",
    "Inno Setup": "#264b99", "Go": "#00ADD8", "Rust": "#dea584", "Lua": "#000080", "Batchfile": "#C1F12E",
}
FALLBACK = ["#8b949e", "#6e7681", "#484f58"]


def request(url, token, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "profile-stats-card",
        **({"Authorization": f"Bearer {token}"} if token else {}),
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def collect(user, token):
    repos = [r for r in request(f"{API}/users/{user}/repos?per_page=100&type=owner&sort=pushed", token)
             if not r["fork"] and not r["archived"] and r["name"].lower() != user.lower()]
    langs = {}
    for r in repos:
        for name, size in request(r["languages_url"], token).items():
            langs[name] = langs.get(name, 0) + size
    data = {
        "stars": sum(r["stargazers_count"] for r in repos),
        "forks": sum(r["forks_count"] for r in repos),
        "repos": len(repos),
        "languages": langs,
    }
    try:  # contributions need GraphQL; without it the card keeps the REST numbers
        q = """query($u:String!){user(login:$u){followers{totalCount}
          contributionsCollection{totalCommitContributions totalPullRequestContributions
          contributionCalendar{totalContributions}}}}"""
        u = request(f"{API}/graphql", token, {"query": q, "variables": {"u": user}})["data"]["user"]
        c = u["contributionsCollection"]
        data.update(commits=c["totalCommitContributions"], prs=c["totalPullRequestContributions"],
                    contributions=c["contributionCalendar"]["totalContributions"], followers=u["followers"]["totalCount"])
    except Exception as e:  # noqa: BLE001 - a partial card beats no card
        print(f"graphql skipped: {e}", file=sys.stderr)
    return data


def esc(s):
    return html.escape(str(s), quote=True)


def card(d, updated):
    metrics = [(label, d[key]) for key, label in [
        ("contributions", "вкладов за год"), ("commits", "коммитов за год"), ("stars", "звёзд"),
        ("repos", "репозиториев"), ("prs", "pull request"), ("followers", "подписчиков"), ("forks", "форков"),
    ] if key in d][:4]
    total = sum(d["languages"].values()) or 1
    top = sorted(d["languages"].items(), key=lambda kv: -kv[1])
    shown = top[:6]
    rest = sum(v for _, v in top[6:])
    if rest:
        shown.append(("Другие", rest))

    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="210" viewBox="0 0 1000 210" role="img" aria-label="Статистика GitHub">',
           '<style>.n{font:700 34px "Segoe UI",Roboto,Arial,sans-serif;fill:#f0f6fc}.l{font:12px "Segoe UI",Roboto,Arial,sans-serif;fill:#8b949e}'
           '.h{font:600 11px ui-monospace,Consolas,monospace;fill:#2BC6A4;letter-spacing:3px}.k{font:12px "Segoe UI",Roboto,Arial,sans-serif;fill:#c9d1d9}'
           '.p{font:12px ui-monospace,Consolas,monospace;fill:#8b949e}.u{font:10px ui-monospace,Consolas,monospace;fill:#6e7681;letter-spacing:1px}'
           '.seg{transform-origin:left;animation:grow .9s cubic-bezier(.16,1,.3,1) both}.m{animation:fade .6s ease-out both}'
           '@keyframes grow{from{transform:scaleX(0)}}@keyframes fade{from{opacity:0;transform:translateY(6px)}}'
           '@media (prefers-reduced-motion:reduce){.seg,.m{animation:none}}</style>',
           '<rect x=".5" y=".5" width="999" height="209" rx="12" fill="#0d1117" stroke="#30363d"/>',
           '<text x="32" y="38" class="h">СТАТИСТИКА</text>']
    for i, (label, value) in enumerate(metrics):
        x, y = 32 + (i % 2) * 210, 92 + (i // 2) * 74
        out.append(f'<g class="m" style="animation-delay:{i * 0.08:.2f}s"><text x="{x}" y="{y}" class="n">{value:,}</text>'
                   f'<text x="{x}" y="{y + 20}" class="l">{esc(label)}</text></g>'.replace(",", " "))
    out.append('<line x1="470" y1="28" x2="470" y2="182" stroke="#21262d"/>')
    out.append('<text x="504" y="38" class="h">ЯЗЫКИ</text>')
    # stacked bar
    bx, bw, x, fb = 504, 464, 504.0, 0
    out.append(f'<clipPath id="bar"><rect x="{bx}" y="54" width="{bw}" height="10" rx="5"/></clipPath><g clip-path="url(#bar)">')
    for i, (name, size) in enumerate(shown):
        w = bw * size / total
        color = COLORS.get(name) or FALLBACK[fb % len(FALLBACK)]
        if name not in COLORS: fb += 1
        out.append(f'<rect class="seg" style="animation-delay:{0.15 + i * 0.06:.2f}s" x="{x:.1f}" y="54" width="{w + 0.6:.1f}" height="10" fill="{color}"/>')
        x += w
    out.append('</g>')
    # legend, two columns
    fb = 0
    for i, (name, size) in enumerate(shown):
        color = COLORS.get(name) or FALLBACK[fb % len(FALLBACK)]
        if name not in COLORS: fb += 1
        cx, cy = bx + (i % 2) * 236, 92 + (i // 2) * 26
        out.append(f'<g class="m" style="animation-delay:{0.3 + i * 0.05:.2f}s"><circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{color}"/>'
                   f'<text x="{cx + 18}" y="{cy}" class="k">{esc(name)}</text>'
                   f'<text x="{cx + 214}" y="{cy}" class="p" text-anchor="end">{100 * size / total:.1f}%</text></g>')
    out.append(f'<text x="968" y="196" class="u" text-anchor="end">обновлено {updated}</text>')
    out.append('</svg>')
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mock")
    a = ap.parse_args()
    data = json.load(open(a.mock, encoding="utf-8")) if a.mock else collect(a.user, os.environ.get("GITHUB_TOKEN", ""))
    os.makedirs(a.out, exist_ok=True)
    updated = datetime.datetime.now(datetime.timezone.utc).strftime("%d.%m.%Y")
    with open(os.path.join(a.out, "stats.svg"), "w", encoding="utf-8") as f:
        f.write(card(data, updated))
    print(json.dumps({k: v for k, v in data.items() if k != "languages"}, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    main()
