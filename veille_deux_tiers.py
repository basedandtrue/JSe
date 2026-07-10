#!/usr/bin/env python3
"""
Two-tier job watch for grade 031302 / books-culture-language domain.

FETCH 1 — FAST PATH (Profil Public API, mairie source-of-truth, ~zero lag):
  all offers from the in-radius PP towns, split by title keywords.
FETCH 2 — HUB (emploi-territorial, her exact ville+20km+grade filter,
  authoritative grade tags, but ingestion lag):
  everything it returns is on-grade by construction -> always Tier 1.

TIER 1  "expedient": keyword-matched fast-path offers + all hub offers,
        deduped, earliest date wins, direct URL preferred. Check daily.
TIER 2  "quarantine": fast-path offers with NO grade tag and NO keyword hit.
        Safety net so nothing untagged is silently dropped. Skim weekly.

Outputs: report.html (two tables), tier1.xml + tier2.xml (RSS), state file
for new-offer notifications.

Deps: requests, beautifulsoup4
"""

import sys, re, json, unicodedata, hashlib, datetime as dt
from difflib import SequenceMatcher
from email.utils import format_datetime
from xml.sax.saxutils import escape
import requests
from bs4 import BeautifulSoup

# ------------------------------------------------------------------ CONFIG
HUB_URL = ("https://www.emploi-territorial.fr/emploi-mobilite/"
           "?search-ville=91421&search-distance=20&search-grade=031302")
PP_TOWNS = ["ville-de-choisy-le-roi", "ville-de-creteil", "ville-de-maisons-alfort",
            "ville-de-villejuif", "ville-de-bourg-la-reine", "ville-de-nogent",
            "neuilly-sur-marne"]
KW_RE = re.compile(
    r"mediath|biblioth|patrimoine|archiv|documental|ludoth|conservat"
    r"|\blivres?\b|\blecture\b|\bculturel(?:le|les|s)?\b|\bculture\b"
    r"|\bmusees?\b|exposition|linguist|\blangues?\b|interpret|traduc"
    r"|international|jumelage|coreen")
FUZZY = 0.86
STATE = "seen_two_tier.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; job-rss/1.0)"}
# ------------------------------------------------------------------

def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii","ignore").decode().lower()
    return re.sub(r"\s+", " ", s)

def norm_town(s):
    t = re.sub(r"[^a-z0-9 ]"," ",_norm(s))
    for p in ("ville de ","commune de ","mairie de "):
        if t.startswith(p): t=t[len(p):]
    return t.replace(" ","")

def norm_title(s):
    t = re.sub(r"[^a-z0-9 ]"," ",_norm(s))
    t = re.sub(r"\b([fh])\s*[/-]?\s*([hf])\b","",t)
    t = re.sub(r"\b(copie|remplacement|cdd|cdi)\b","",t)
    return re.sub(r"\s+"," ",t).strip()

# ------------------------------------------------------------------ FETCH 1
def fetch_profilpublic():
    tier1, tier2 = [], []
    for slug in PP_TOWNS:
        try:
            d = requests.get("https://app.profilpublic.fr/api/jobs",
                params={"filters[employer][slug][$eq]": slug,
                        "pagination[pageSize]": 100, "sort": "validatedAt:desc"},
                headers=UA, timeout=30).json().get("data", [])
        except Exception as e:
            sys.stderr.write(f"[pp:{slug}] FAILED {e}\n"); continue
        town = slug.replace("ville-de-","").replace("-"," ").title()
        for j in d:
            date = j.get("validatedAt") or j.get("createdAt")
            try: pub = dt.datetime.fromisoformat(date.replace("Z","+00:00"))
            except Exception: pub = dt.datetime.now(dt.timezone.utc)
            rec = dict(source="mairie", direct=True,
                       title=j.get("title") or "", town=town,
                       url=f"https://recrutement-pp.fr/{slug}/jobs/{j.get('slug','')}",
                       published=pub,
                       grades=j.get("grades") or [], expires=j.get("expiresAt"))
            if KW_RE.search(_norm(rec["title"])):
                tier1.append(rec)
            elif not rec["grades"]:
                tier2.append(rec)        # untagged, off-keyword -> quarantine
            # tagged + off-keyword + off-grade -> dropped (hub covers on-grade)
        sys.stderr.write(f"[pp:{slug}] {len(d)} offres\n")
    return tier1, tier2

# ------------------------------------------------------------------ FETCH 2
def fetch_hub():
    s = requests.Session(); s.headers.update(UA)
    def parse(html):
        soup = BeautifulSoup(html, "html.parser"); out=[]
        for a in soup.select("div.detail-offre-titre a[href^='/offre/']"):
            m = re.search(r"/offre/(o\d+)-", a["href"])
            if not m: continue
            oid=m.group(1); y=oid[4:10]
            try: pub=dt.datetime(2000+int(y[:2]),int(y[2:4]),int(y[4:6]),tzinfo=dt.timezone.utc)
            except ValueError: pub=dt.datetime.now(dt.timezone.utc)
            card=a.find_parent("div").find_parent("div")
            emp=card.select_one("a[href*='search-col']") if card else None
            colid=None
            if emp:
                mc=re.search(r"search-col=(\d+)", emp.get("href",""))
                colid=mc.group(1) if mc else None
            out.append(dict(source="hub", direct=False,
                title=a.get_text(strip=True),
                town=emp.get_text(strip=True) if emp else "?",
                colid=colid,
                url="https://www.emploi-territorial.fr"+a["href"],
                published=pub, grades=["031302"], expires=None))
        return out
    offers = parse(s.get(HUB_URL, timeout=30).text)
    seen = {o["url"] for o in offers}
    for page in range(2, 60):
        r = s.post("https://www.emploi-territorial.fr/recherche_emploi_mobilite/",
                   data=f"page={page}&ajax=1",
                   headers={"X-Requested-With":"XMLHttpRequest",
                            "Content-Type":"application/x-www-form-urlencoded"},
                   timeout=30)
        batch=[o for o in parse(r.text) if o["url"] not in seen]
        if not batch: break
        seen.update(o["url"] for o in batch); offers+=batch
    sys.stderr.write(f"[hub] {len(offers)} offres (grade-filtered)\n")
    return offers

# ------------------------------------------------------------------ MERGE
def merge(records):
    buckets={}
    for r in records:
        tk=norm_town(r["town"]); nt=norm_title(r["title"]); hit=False
        for m in buckets.get(tk,[]):
            if SequenceMatcher(None,nt,m["_nt"]).ratio()>=FUZZY:
                m["sources"].add(r["source"])
                if r["published"]<m["published"]: m["published"]=r["published"]
                if r["direct"] and not m["_direct"]:
                    m.update(url=r["url"],title=r["title"],_direct=True)
                m["expires"]=m["expires"] or r["expires"]
                hit=True; break
        if not hit:
            buckets.setdefault(tk,[]).append(dict(
                _nt=nt,_direct=r["direct"],sources={r["source"]},
                title=r["title"],town=r["town"],url=r["url"],
                published=r["published"],expires=r["expires"]))
    out=[o for l in buckets.values() for o in l]
    for o in out:
        o["guid"]="job-"+hashlib.sha1((norm_town(o["town"])+"|"+o["_nt"]).encode()).hexdigest()[:16]
    out.sort(key=lambda o:o["published"],reverse=True)
    return out

# ------------------------------------------------------------------ OUTPUT
def rss(offers, title, fname):
    items="".join(f"""    <item>
      <title>{escape(o['title'])}</title>
      <link>{escape(o['url'])}</link>
      <guid isPermaLink="false">{o['guid']}</guid>
      <pubDate>{format_datetime(o['published'])}</pubDate>
      <description>{escape(o['town']+' | sources: '+','.join(sorted(o['sources'])))}</description>
    </item>\n""" for o in offers)
    open(fname,"w",encoding="utf-8").write(
f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>{escape(title)}</title>
  <link>{escape(HUB_URL)}</link>
  <description>{len(offers)} offres</description>
  <lastBuildDate>{format_datetime(dt.datetime.now(dt.timezone.utc))}</lastBuildDate>
{items}</channel></rss>""")

def html_report(t1, t2, new_guids, coverage):
    def rows(offers):
        r=""
        for o in offers:
            badge="🆕 " if o["guid"] in new_guids else ""
            fast="⚡" if "mairie" in o["sources"] else ""
            exp=f" · exp. {o['expires']}" if o.get("expires") else ""
            r+=(f"<tr><td>{o['published'].date()}</td>"
                f"<td>{escape(o['town'])}</td>"
                f"<td>{badge}<a href='{escape(o['url'])}'>{escape(o['title'])}</a></td>"
                f"<td>{fast}{','.join(sorted(o['sources']))}{exp}</td></tr>\n")
        return r
    open("report.html","w",encoding="utf-8").write(f"""<!doctype html><html lang="fr"><head>
<meta charset="utf-8"><title>Veille emploi — patrimoine / culture</title>
<style>
 body{{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#1c1c1c}}
 h2{{border-bottom:2px solid #0a59a9;padding-bottom:.3rem}}
 table{{border-collapse:collapse;width:100%;margin-bottom:2.5rem;font-size:.92rem}}
 th,td{{border:1px solid #ddd;padding:.45rem .6rem;text-align:left;vertical-align:top}}
 th{{background:#0a59a9;color:#fff}} tr:nth-child(even){{background:#f6f8fa}}
 a{{color:#0a59a9}} .meta{{color:#666;font-size:.85rem}}
</style></head><body>
<h1>Veille emploi — grade 031302 &amp; domaine livre/culture/langues</h1>
<p class="meta">Généré le {dt.datetime.now().strftime('%d/%m/%Y %H:%M')} ·
⚡ = source mairie directe (sans délai hub) · 🆕 = nouveau depuis la dernière exécution</p>

<h2>Tier 1 — Offres ciblées ({len(t1)})</h2>
<p class="meta">Correspondance grade (hub) ou mots-clés métier (mairies directes). À consulter en priorité.</p>
<table><tr><th>Publiée</th><th>Collectivité</th><th>Offre</th><th>Source</th></tr>
{rows(t1)}</table>

<h2>Tier 2 — Non étiquetées, à vérifier ({len(t2)})</h2>
<p class="meta">Offres des mairies directes sans grade ni mot-clé reconnu. Filet de sécurité : un survol hebdomadaire suffit.</p>
<table><tr><th>Publiée</th><th>Collectivité</th><th>Offre</th><th>Source</th></tr>
{rows(t2)}</table>

<h2>Couverture — collectivités suivies uniquement via le hub ({len(coverage)})</h2>
<p class="meta">Pour ces employeurs, l'outil ne voit les offres qu'au rythme du hub (délai d'ingestion possible).
Si l'un d'eux l'intéresse particulièrement, vérifier son site de temps en temps — ou me le signaler
pour tenter un adaptateur direct. NB : beaucoup de petites communes publient <em>directement</em> sur
le hub sans site propre ; dans ce cas il n'existe rien de plus rapide à consulter.</p>
<table><tr><th>Collectivité</th><th>Offres actives (filtre grade)</th><th>Dernière publication vue</th><th>Liens</th></tr>
{"".join(f"<tr><td>{escape(c['town'])}</td><td>{c['n']}</td><td>{c['latest'].date()}</td>"
         f"<td><a href='{escape(c['hub_url'])}'>offres hub</a> · "
         f"<a href='{escape(c['site_search'])}'>chercher le site officiel</a></td></tr>"
         for c in coverage)}</table>
</body></html>""")

def hub_only_coverage(hub):
    """Collectivités reached ONLY via hub -> her lag still applies there."""
    from urllib.parse import quote_plus
    fast = {norm_town(s.replace("ville-de","").replace("-"," ")) for s in PP_TOWNS}
    cov = {}
    for o in hub:
        tk = norm_town(o["town"])
        if tk in fast: continue
        c = cov.setdefault(tk, dict(town=o["town"], n=0, latest=o["published"],
                                    colid=o.get("colid")))
        c["n"] += 1
        if o["published"] > c["latest"]: c["latest"] = o["published"]
        c["colid"] = c["colid"] or o.get("colid")
    for c in cov.values():
        c["hub_url"] = (f"https://www.emploi-territorial.fr/emploi-mobilite/?search-col={c['colid']}"
                        if c.get("colid") else HUB_URL)
        c["site_search"] = ("https://duckduckgo.com/?q="
                            + quote_plus(f"{c['town']} offres emploi recrutement site officiel"))
    return sorted(cov.values(), key=lambda c: c["latest"], reverse=True)

def main():
    pp1, pp2 = fetch_profilpublic()
    hub = []
    try: hub = fetch_hub()
    except Exception as e: sys.stderr.write(f"[hub] FAILED {e}\n")
    coverage = hub_only_coverage(hub)
    t1 = merge(pp1 + hub)
    t2 = merge(pp2)
    t2guids={o["guid"] for o in t2}
    t1guids={o["guid"] for o in t1}
    t2=[o for o in t2 if o["guid"] not in t1guids]   # never show twice
    try: prev=set(json.load(open(STATE)))
    except Exception: prev=set()
    new={o["guid"] for o in t1+t2 if o["guid"] not in prev}
    sys.stderr.write(f"[tiers] T1={len(t1)} T2={len(t2)} | new={len(new)}\n")
    json.dump(sorted({o['guid'] for o in t1+t2}), open(STATE,"w"))
    rss(t1,"Veille patrimoine/culture — Tier 1 ciblé","tier1.xml")
    rss(t2,"Veille — Tier 2 non étiquetées","tier2.xml")
    html_report(t1,t2,new,coverage)
    sys.stderr.write("[out] report.html, tier1.xml, tier2.xml\n")

if __name__=="__main__":
    main()
