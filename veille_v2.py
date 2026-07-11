#!/usr/bin/env python3
"""
Veille emploi culturelle — Île-de-France (origine : Montgeron)

CHANGEMENTS v2
  1. GRADES : 8 grades de la filière culturelle (cat. A/B/C) au lieu d'un seul
     grade de cat. C  ->  98 offres au lieu de 27 sur le hub.
  2. SOURCES DIRECTES ajoutées : Val-de-Marne + Est-Ensemble (Gestmax variante
     "list-group"), Fontenay / Grand-Orly / Cachan (flux RSS natifs).
  3. TRAJET : temps de transport en commun depuis Montgeron, par commune.
     - Sans clé : lien pré-rempli (Google Maps transit) sur chaque ligne.
     - Avec clé PRIM (IDFM, gratuite) dans la variable d'env PRIM_TOKEN :
       durée porte-à-porte calculée et mise en cache (transit_cache.json).
  4. CATÉGORIE affichée quand la source la donne (A/B/C).

Deps: requests, beautifulsoup4
"""

import os, sys, re, json, unicodedata, hashlib, datetime as dt
from difflib import SequenceMatcher
from email.utils import format_datetime
from urllib.parse import quote_plus
from xml.sax.saxutils import escape
import requests
from bs4 import BeautifulSoup

# ----------------------------------------------------------------- CONFIG
ORIGIN_NAME = "Montgeron"
ORIGIN_LATLON = (48.6952, 2.4638)
SEARCH_VILLE, SEARCH_DIST = "91421", "20"

# Filière culturelle — grades accessibles avec une licence (bac+3).
GRADES = {
    "030401": "Bibliothécaire (A)",
    "030301": "Attaché de conservation (A)",
    "030904": "Assistant de conservation (B)",
    "030905": "Assistant cons. ppal 2e cl. (B)",
    "030906": "Assistant cons. ppal 1re cl. (B)",
    "031301": "Adjoint patrimoine ppal 1re cl. (C)",
    "031302": "Adjoint patrimoine ppal 2e cl. (C)",
    "031305": "Adjoint du patrimoine (C)",
}
HUB_URL = ("https://www.emploi-territorial.fr/emploi-mobilite/"
           f"?search-ville={SEARCH_VILLE}&search-distance={SEARCH_DIST}"
           + "".join(f"&search-grade%5B%5D={g}" for g in GRADES))

# slug Profil Public -> libelle propre (accents et traits d'union corrects :
# sert l'affichage ET le geocodage des trajets)
PP_TOWNS = {
    "ville-de-choisy-le-roi":   "Choisy-le-Roi",
    "ville-de-creteil":         "Créteil",
    "ville-de-maisons-alfort":  "Maisons-Alfort",
    "ville-de-villejuif":       "Villejuif",
    "ville-de-bourg-la-reine":  "Bourg-la-Reine",
    "ville-de-nogent":          "Nogent-sur-Marne",
    "neuilly-sur-marne":        "Neuilly-sur-Marne",
}
GESTMAX_TABLE = [("https://emploi.gpsea.fr", "GPSEA")]              # variante <table>
GESTMAX_LIST  = [("https://gestion-candidatures.valdemarne.fr", "Département du Val-de-Marne"),
                 ("https://recrutement.est-ensemble.fr", "Est Ensemble"),
                 ("https://vyvs-recrutement.gestmax.fr", "Val d'Yerres Val de Seine"),
                 ("https://travaillerpourparis.offres.paris.fr", "Ville de Paris")]
HDS_URL   = "https://recrutement.hauts-de-seine.fr/nos-offres-demploi/"
SCEAUX_API= "https://recrutement.sceaux.fr/wp-json/wp/v2/posts"
VINCENNES = "https://www.vincennes.fr/economie-et-emploi/emploi/offres-demploi"
CHAMPIGNY = "https://www.champignysurmarne.fr/vivre-champigny/insertion-et-emploi/la-ville-recrute"
CHARENTON = "https://www.charenton.fr/economie_emploi/emploi_mairie_recrute/"
MONTREUIL = "https://recrutement.montreuil.fr/fr/ville-de-montreuil/site-map"
WP_JOBS   = {  # WordPress exposant le type de contenu "job-offers"
    "Longjumeau": "https://www.longjumeau.fr",
    "Vallée Sud - Grand Paris": "https://www.valleesud.fr",
}
LEPERREUX = "https://leperreux94.nous-recrutons.fr/sitemap.xml"

# Gestmax variante "list-group" (deja gere) : on ajoute VYVS et Ville de Paris
# Gestmax variante "tr" (Antony) : lignes <tr> avec lien /<id>/<n>/<slug>
GESTMAX_TR = [("https://antony.gestmax.fr", "Antony")]
# WordPress avec custom post type dedie -> API REST
WP_CPT = [("Grand Paris Sud", "https://www.grandparissud.fr", "job-offers"),
          ("Chevilly-Larue", "https://www.ville-chevilly-larue.fr", "job_offer"),
          ("Coeur d'Essonne", "https://www.coeuressonne.fr", "offre-d-emploi")]
# WordPress ou les offres sont de simples articles
WP_POSTS = [("Châtillon", "https://recrutement.ville-chatillon.fr")]
MASSY = "https://www.ville-massy.fr/offres-demploi/"
NOISY = ("https://www.noisylegrand.fr/votre-mairie/services-municipaux/"
         "la-ville-recrute/consulter-les-offres")
PMUSEES  = "https://www.parismusees.paris.fr/fr/liste-des-offres"
ESPCI    = "https://www.espci.psl.eu/recrutement/offres-emploi/"
ARCUEIL  = "https://www.arcueil.fr/offres-demploi/"
FRESNES  = "https://www.fresnes94.fr/votre-mairie/la-mairie-recrute/"
ROSNY    = "https://www.rosnysousbois.fr/services-municipaux/nous-rejoindre/"
STMANDE  = "https://www.saintmande.fr/offres-demploi-1"
IVRY     = "https://www.ivry94.fr/595/ivry-recrute.htm"

# --- Sources JS pures : rendues par un navigateur headless (Playwright).
# Si Playwright n'est pas installe, ces sources sont simplement ignorees et
# leurs offres restent visibles via le hub : le script ne casse jamais.
IVRY_IFRAME = ("https://apply.wink-lab.com/iframe/jobs/"
               "587833e2-c273-4ea5-b34e-d4c8e80473a4")
NEUILLY_P   = "https://www.mairie-neuillyplaisance.com/emploi/la-ville-recrute"
ESSONNE_ATS = ("https://talents.elsatis.fr/router/servlet/Portal"
               "?c=145528129&p=113739240&g=113739518&idSupport=113711076")
HEADLESS_TIMEOUT = 60000
# Mettre HEADLESS_INSECURE=1 UNIQUEMENT derriere un proxy qui reecrit les certificats
# (environnement de test). Sur GitHub Actions, laisser vide : TLS verifie normalement.
HEADLESS_INSECURE = os.environ.get("HEADLESS_INSECURE") == "1"
# Titres a ignorer : liens de navigation / documents hors offres
NOTJOB = re.compile(r"bornes? de recharge|stationnement|application|newsletter|cookies|"
                    r"plan du site|contact|mentions|accessibilit|candidature spontan|"
                    r"^t[ée]l[ée]charger|^voir les d[ée]tails|^en savoir|^lire la suite|"
                    r"^postuler|^d[ée]poser", re.I)

RSS_FEEDS = {
    "Fontenay-sous-Bois": "https://www.fontenay.fr/vie-municipale/offres-demploi/offres-demploi-de-la-mairie-600/rss",
    "Grand-Orly Seine Bièvre": "https://www.grandorlyseinebievre.fr/recrutement/feed.xml",
    "Cachan": "https://ville-cachan.fr/offres-emploi/feed/",
}

KW_RE = re.compile(
    r"mediath|biblioth|patrimoine|archiv|documental|ludoth|conservat"
    r"|\blivres?\b|\blecture\b|\bculturel(?:le|les|s)?\b|\bculture\b"
    r"|\bmusees?\b|exposition|linguist|\blangues?\b|interpret|traduc"
    r"|international|jumelage|coreen|\bartistique\b|\bpublics?\b.*\bculture")
CULT_RE = re.compile(r"culturel", re.I)     # filière déclarée par la source
# Postes tagués filière culturelle par la source mais hors cible (musicien/danseur).
# Vider EXCL_RE pour tout revoir.
EXCL_RE = re.compile(
    r"\bpiano\b|\bviolon|\balto\b|\bsaxo|trompette|guitare|violoncelle|contrebasse"
    r"|clarinette|hautbois|\bflute\b|\bfl\u00fbte\b|percussion|\bharpe\b|\bchant\b"
    r"|formation musicale|\bdanse\b|\borchestre\b|\bch\u0153ur\b|\bchoeur\b"
    r"|professeur d[e\u2019\']\s*(?:musique|art)|enseignant d[e\u2019\']\s*(?:musique)"
    r"|cimeti[eè]re",           # "Conservateur de cimetiere" : homonyme, hors domaine
    re.I)

FUZZY = 0.86
STATE = "seen_two_tier.json"          # {guid: first_seen_iso}
TCACHE = "transit_cache.json"         # {commune: minutes|null}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "fr-FR,fr;q=0.9"}
PRIM = os.environ.get("PRIM_TOKEN", "").strip()

# --- Notifications ---------------------------------------------------------
# NTFY_TOPIC : nom de "canal" prive (ex. veille-biblio-k9x3mq). Elle installe l'appli
#   ntfy, s'abonne a ce meme nom, et recoit les nouvelles offres sur son telephone.
#   Gratuit, sans compte. Choisir un nom long et non devinable : qui connait le nom
#   peut lire le canal.
# NTFY_EMAIL : optionnel, ntfy envoie AUSSI la notification a cette adresse.
# REPORT_URL : lien ouvert quand elle tape sur la notification.
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_EMAIL = os.environ.get("NTFY_EMAIL", "").strip()
REPORT_URL = os.environ.get("REPORT_URL", "").strip()
# -----------------------------------------------------------------

def _n(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii","ignore").decode().lower()
    return re.sub(r"\s+", " ", s)

ALIASES = {   # memes employeurs sous deux noms
    "gpsea": "grandparissudestavenir",
    "cd94": "valdemarne",
    "departementduvaldemarne": "valdemarne",
}

def norm_town(s):
    t = re.sub(r"\(.*?\)", " ", _n(s))          # (T8), (CD94), (T12)...
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    for p in ("communaute d agglomeration ", "communaute dagglomeration ",
              "communaute de communes ", "etablissement public territorial ",
              "conseil departemental de l ", "conseil departemental de la ",
              "conseil departemental du ", "conseil departemental d ",
              "ville de ", "commune de ", "mairie de ",
              "departement du ", "departement de la ", "departement des ", "departement d "):
        if t.startswith(p): t = t[len(p):]
    t = re.sub(r"\s+agglomeration$", "", t)
    t = re.sub(r"\s+", "", t)
    return ALIASES.get(t, t)

def norm_title(s):
    t = re.sub(r"[^a-z0-9 ]", " ", _n(s))
    t = re.sub(r"\b([fh])\s*[/-]?\s*([hf])\b", "", t)
    t = re.sub(r"\b(copie|remplacement|cdd|cdi|un|une)\b", "", t)
    return re.sub(r"\s+", " ", t).strip()

STOP = {"hf","fh","h","f","cdd","cdi","un","une","de","du","des","la","le","les","en","et",
        "a","au","aux","pour","sur","poste","offre","temps","heures","heure","mois","ans","au",
        "recrute","recrutement","ou","dans","par","avec","son","sa","the"}

def toks(t):
    return {w for w in norm_title(t).split() if len(w) > 2 and w not in STOP}

def same_job(a_t, a_k, b_t, b_k):
    """Meme offre ? Il faut (1) un employeur/lieu commun ET (2) des titres concordants.
    Deux tests de titre : chaine entiere (strict) OU recouvrement de mots-cles
    (tolere 'Mediathecaire jeunesse (CDD 7 mois)' vs 'Mediathecaire secteur jeunesse')."""
    if not (a_k & b_k):
        return False
    if SequenceMatcher(None, norm_title(a_t), norm_title(b_t)).ratio() >= FUZZY:
        return True
    ta, tb = toks(a_t), toks(b_t)
    if not ta or not tb:
        return False
    inter = ta & tb
    return len(inter) >= 2 and len(inter) / min(len(ta), len(tb)) >= 0.6

def rec(**k):
    k.setdefault("category", None); k.setdefault("filiere", None)
    k.setdefault("published", None)
    k.setdefault("employer", k.get("town"))     # employeur (peut differer du lieu)
    return k

def keyset(r):
    return {x for x in (norm_town(r.get("town") or ""), norm_town(r.get("employer") or "")) if x}

# ----------------------------------------------------------------- ADAPTERS
def a_hub():
    s = requests.Session(); s.headers.update(UA)
    def parse(h):
        soup = BeautifulSoup(h, "html.parser"); out = []
        for a in soup.select("div.detail-offre-titre a[href^='/offre/']"):
            m = re.search(r"/offre/(o\d+)-", a["href"])
            if not m: continue
            oid = m.group(1); y = oid[4:10]
            try: pub = dt.datetime(2000+int(y[:2]), int(y[2:4]), int(y[4:6]), tzinfo=dt.timezone.utc)
            except ValueError: pub = None
            card = a.find_parent("div").find_parent("div")
            emp = card.select_one("a[href*='search-col']") if card else None
            cat = None
            if card:
                cb = card.select_one("span.badge-success, span.badge-warning, span.badge-info")
                cat = cb.get_text(strip=True) if cb else None
            out.append(rec(source="hub", direct=False, ongrade=True,
                title=a.get_text(strip=True),
                town=emp.get_text(strip=True) if emp else "?",
                url="https://www.emploi-territorial.fr"+a["href"],
                published=pub, category=cat))
        return out
    offers = parse(s.get(HUB_URL, timeout=30).text)
    seen = {o["url"] for o in offers}
    for page in range(2, 80):
        r = s.post("https://www.emploi-territorial.fr/recherche_emploi_mobilite/",
                   data=f"page={page}&ajax=1",
                   headers={"X-Requested-With":"XMLHttpRequest",
                            "Content-Type":"application/x-www-form-urlencoded"}, timeout=30)
        b = [o for o in parse(r.text) if o["url"] not in seen]
        if not b: break
        seen.update(o["url"] for o in b); offers += b
    return offers

def a_profilpublic():
    out = []
    for slug, town in PP_TOWNS.items():
        try:
            d = requests.get("https://app.profilpublic.fr/api/jobs",
                params={"filters[employer][slug][$eq]": slug, "pagination[pageSize]": 100,
                        "sort":"validatedAt:desc"}, headers=UA, timeout=30).json().get("data", [])
        except Exception as e:
            sys.stderr.write(f"[pp:{slug}] FAIL {e}\n"); continue
        for j in d:
            try: pub = dt.datetime.fromisoformat((j.get("validatedAt") or j["createdAt"]).replace("Z","+00:00"))
            except Exception: pub = None
            g = j.get("grades") or []
            out.append(rec(source="mairie", direct=True,
                ongrade=any(x in GRADES for x in g),
                title=j.get("title") or "", town=town,
                url=f"https://recrutement-pp.fr/{slug}/jobs/{j.get('slug','')}",
                published=pub, grades=g, untagged=not g))
    return out

def a_gestmax_table(base, emp):
    out = []
    def page(u):
        s = BeautifulSoup(requests.get(u, headers=UA, timeout=30).text, "html.parser")
        rows = s.select("tr[class*=vacancy-id-]"); recs = []
        for tr in rows:
            m = re.search(r"vacancy-id-(\d+)", " ".join(tr.get("class", [])))
            if not m: continue
            g = lambda h: (tr.select_one(f"td[headers*={h}]").get_text(strip=True)
                           if tr.select_one(f"td[headers*={h}]") else "")
            a = tr.find("a", href=True)
            recs.append(dict(title=g("vacancy_title"), town=g("vac_lieu") or g("customer_company"),
                             date=g("publication_start"), url=a["href"] if a else base))
        mp = [int(x.get_text()) for x in s.select("a[href*='/search/index/page/']")
              if x.get_text().strip().isdigit()]
        return recs, (max(mp) if mp else 1)
    r, mp = page(base + "/search")
    for p in range(2, mp+1): r += page(base + f"/search/index/page/{p}")[0]
    for x in r:
        try: pub = dt.datetime.strptime(x["date"], "%d/%m/%Y").replace(tzinfo=dt.timezone.utc)
        except Exception: pub = None
        t = x["town"]
        if not t or re.search(r"direction|service|p[o\u00f4]le|^dsc\b", t, re.I): t = emp
        out.append(rec(source="mairie", direct=True, ongrade=False, untagged=True,
                       title=x["title"], town=t, employer=emp, url=x["url"], published=pub))
    return out

def a_gestmax_list(base, default_town):
    """Variante Gestmax 'list-group' (Val-de-Marne, Est-Ensemble).
    Expose filière + catégorie ; pas de date -> on utilise la 1re détection."""
    s = requests.Session(); s.headers.update(UA)
    out, page = [], 1
    while page <= 40:
        h = s.get(f"{base}/search/index/frontsearchtab_id/1/page/{page}", timeout=30).text
        soup = BeautifulSoup(h, "html.parser")
        items = soup.select("a.list-group-item")
        real = [a for a in items if a.select_one("h3") and "apply/" not in a.get("href","")]
        if not real: break
        for a in real:
            h3 = a.select_one("h3"); loc = a.select_one(".listdiv-date")
            fil = a.select_one(".listdiv-vac_filiere .listdiv-value")
            cat = a.select_one(".listdiv-vac_categorie .listdiv-value")
            filt = fil.get_text(strip=True) if fil else ""
            catt = cat.get_text(strip=True) if cat else ""
            town = re.sub(r"^[\s\-]+", "", loc.get_text(strip=True)) if loc else ""
            out.append(rec(source="mairie", direct=True,
                ongrade=bool(CULT_RE.search(filt)),
                title=h3.get_text(strip=True),
                town=town.split(";")[0].strip().title() or default_town,
                employer=default_town,
                url=a["href"].split("?")[0], published=None,
                category=(re.search(r"\b([ABC])\b", catt).group(1) if re.search(r"\b([ABC])\b", catt) else None),
                filiere=filt.replace("Filière FPT de référence","").strip() or None,
                untagged=not filt))
        page += 1
    return out

def a_rss(town, url):
    out = []
    try: xml = requests.get(url, headers=UA, timeout=25).text
    except Exception as e:
        sys.stderr.write(f"[rss:{town}] FAIL {e}\n"); return out
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
        t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        l = re.search(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", it, re.S)
        d = re.search(r"<pubDate>(.*?)</pubDate>", it, re.S)
        if not t: continue
        pub = None
        if d:
            try:
                from email.utils import parsedate_to_datetime
                pub = parsedate_to_datetime(d.group(1).strip())
                if pub.tzinfo is None: pub = pub.replace(tzinfo=dt.timezone.utc)
            except Exception: pub = None
        out.append(rec(source="mairie", direct=True, ongrade=False, untagged=True,
            title=re.sub(r"<[^>]+>","",t.group(1)).strip(),
            town=town, url=(l.group(1).strip() if l else url), published=pub))
    return out

def a_hds():
    """Hauts-de-Seine (TYPO3) : liens /nos-offres-demploi/detail/<slug>."""
    so = BeautifulSoup(requests.get(HDS_URL, headers=UA, timeout=30).text, "html.parser")
    seen, out = set(), []
    for a in so.select("a[href*='/nos-offres-demploi/detail/']"):
        t = a.get_text(" ", strip=True)
        href = a["href"]
        if not t or len(t) < 6 or href in seen: continue
        seen.add(href)
        out.append(rec(source="mairie", direct=True, ongrade=False, untagged=True,
            title=t, town="Département des Hauts-de-Seine",
            employer="Département des Hauts-de-Seine",
            url=href if href.startswith("http") else "https://recrutement.hauts-de-seine.fr"+href))
    return out

def a_sceaux():
    """Sceaux : API REST WordPress."""
    d = requests.get(SCEAUX_API, params={"per_page": 100}, headers=UA, timeout=30).json()
    out = []
    for j in d:
        try: pub = dt.datetime.fromisoformat(j["date"]).replace(tzinfo=dt.timezone.utc)
        except Exception: pub = None
        t = re.sub(r"<[^>]+>", "", j.get("title", {}).get("rendered", "")).strip()
        t = t.replace("&#8217;", "'").replace("&amp;", "&").replace("&#8211;", "-")
        if not t: continue
        out.append(rec(source="mairie", direct=True, ongrade=False, untagged=True,
            title=t, town="Sceaux", employer="Sceaux", url=j.get("link", ""), published=pub))
    return out

def a_vincennes():
    """Vincennes : offres hebergees chez Flatchr, liens presents sur la page mairie."""
    so = BeautifulSoup(requests.get(VINCENNES, headers=UA, timeout=30).text, "html.parser")
    seen, out = set(), []
    for a in so.select("a[href*='flatchr.io']"):
        if "vacancy" not in a["href"]: continue
        t = a.get_text(" ", strip=True)
        if not t or len(t) < 6 or a["href"] in seen: continue
        seen.add(a["href"])
        out.append(rec(source="mairie", direct=True, ongrade=False, untagged=True,
            title=t, town="Vincennes", employer="Vincennes", url=a["href"]))
    return out

def a_champigny():
    so = BeautifulSoup(requests.get(CHAMPIGNY, headers=UA, timeout=30).text, "html.parser")
    seen, out = set(), []
    for a in so.find_all("a", href=True):
        if "la-ville-recrute/" not in a["href"]: continue
        href = a["href"]
        if href in seen: continue
        t = a.get_text(" ", strip=True)
        if not t or "tail" in t.lower():          # "Details de l'offre" -> titre ailleurs
            p = a.find_parent(["article", "li", "div"])
            hh = p.find(["h2", "h3", "h4"]) if p else None
            t = hh.get_text(" ", strip=True) if hh else ""
        if not t or len(t) < 8: continue
        seen.add(href)
        out.append(rec(source="mairie", direct=True, ongrade=False, untagged=True,
            title=t, town="Champigny-sur-Marne", employer="Champigny-sur-Marne",
            url=href if href.startswith("http") else "https://www.champignysurmarne.fr"+href))
    return out

def a_charenton():
    so = BeautifulSoup(requests.get(CHARENTON, headers=UA, timeout=30).text, "html.parser")
    seen, out = set(), []
    for a in so.select("a[href*='annonce_emploi']"):
        href = a["href"]
        if href in seen: continue
        blk = a.find_parent(class_=re.compile("job")) or a.find_parent(["li", "article", "div"])
        txt = blk.get_text(" ", strip=True) if blk else a.get_text(" ", strip=True)
        m = re.search(r"Cat[ée]gorie\s*([ABC])\b", txt)
        t = re.sub(r"^\d+\s*", "", txt.split("Statut")[0]).strip()
        if not t or len(t) < 8: continue
        seen.add(href)
        out.append(rec(source="mairie", direct=True, ongrade=False, untagged=True,
            title=t[:110], town="Charenton-le-Pont", employer="Charenton-le-Pont",
            category=(m.group(1) if m else None),
            url=href if href.startswith("http") else "https://www.charenton.fr"+href))
    return out

def a_montreuil():
    """Montreuil (WeRecruit/Angular) : les offres ne sont pas dans le HTML de la page,
    mais le PLAN DU SITE les liste en liens statiques -> pas besoin de navigateur headless."""
    so = BeautifulSoup(requests.get(MONTREUIL, headers=UA, timeout=30).text, "html.parser")
    seen, out = set(), []
    for a in so.find_all("a", href=True):
        if "/fr/offres/" not in a["href"]: continue
        t = a.get_text(" ", strip=True)
        if not t or len(t) < 8 or a["href"] in seen: continue
        seen.add(a["href"])
        out.append(rec(source="mairie", direct=True, ongrade=False, untagged=True,
            title=t, town="Montreuil", employer="Montreuil", url=a["href"]))
    return out

def a_wp_jobs(town, base):
    """WordPress exposant le custom post type 'job-offers' via l'API REST."""
    d = requests.get(f"{base}/wp-json/wp/v2/job-offers", params={"per_page": 100},
                     headers={**UA, "Accept": "application/json"}, timeout=30).json()
    out = []
    for j in d if isinstance(d, list) else []:
        t = re.sub(r"<[^>]+>", "", j.get("title", {}).get("rendered", "")).strip()
        t = (t.replace("&#8217;", "'").replace("&amp;", "&")
              .replace("&#8211;", "-").replace("&#039;", "'"))
        if not t: continue
        try: pub = dt.datetime.fromisoformat(j["date"]).replace(tzinfo=dt.timezone.utc)
        except Exception: pub = None
        out.append(rec(source="mairie", direct=True, ongrade=False, untagged=True,
            title=t, town=town, employer=town, url=j.get("link", base), published=pub))
    return out

def a_leperreux():
    """Le Perreux : offres absentes du HTML, mais listees dans le sitemap.
    On recupere le vrai titre sur chaque fiche (une quinzaine de pages)."""
    xml = requests.get(LEPERREUX, headers=UA, timeout=25).text
    urls = [u for u in re.findall(r"<loc>([^<]+)</loc>", xml) if "/poste/" in u]
    out = []
    for u in urls[:40]:
        try:
            so = BeautifulSoup(requests.get(u, headers=UA, timeout=20).text, "html.parser")
            hh = so.find("h1") or so.find("title")
            t = hh.get_text(" ", strip=True) if hh else ""
            t = re.split(r"\s[–|-]\s", t)[0].strip()
        except Exception:
            t = ""
        if not t:   # repli : reconstruire depuis le slug
            t = re.sub(r"^[a-z0-9]{8,12}-", "", u.rstrip("/").split("/")[-1]).replace("-", " ").capitalize()
        out.append(rec(source="mairie", direct=True, ongrade=False, untagged=True,
            title=t, town="Le Perreux-sur-Marne", employer="Le Perreux-sur-Marne", url=u))
    return out

def a_gestmax_tr(base, town):
    """Variante Gestmax en lignes <tr> (Antony) : lien /<id>/<n>/<slug>, categorie en cellule."""
    so = BeautifulSoup(requests.get(base + "/search/index", headers=UA, timeout=30).text, "html.parser")
    seen, out = set(), []
    for a in so.find_all("a", href=True):
        if not re.search(r"/\d{3,}/\d+/", a["href"]): continue
        t = a.get_text(" ", strip=True)
        if not t or len(t) < 10 or a["href"] in seen: continue
        if re.fullmatch(r"(Permanent|Cat[ée]gorie [ABC]|Temporaire|CDD|CDI)\.?", t, re.I): continue
        seen.add(a["href"])
        row = a.find_parent("tr")
        cat = None
        if row:
            m = re.search(r"Cat[ée]gorie\s*([ABC])\b", row.get_text(" ", strip=True))
            cat = m.group(1) if m else None
        out.append(rec(source="mairie", direct=True, ongrade=False, untagged=True,
            title=t, town=town, employer=town, url=a["href"], category=cat))
    return out

def a_wp_cpt(town, base, cpt):
    """WordPress exposant un custom post type d'offres via l'API REST."""
    d = requests.get(f"{base}/wp-json/wp/v2/{cpt}", params={"per_page": 100},
                     headers={**UA, "Accept": "application/json"}, timeout=30).json()
    out = []
    for j in d if isinstance(d, list) else []:
        t = re.sub(r"<[^>]+>", "", j.get("title", {}).get("rendered", "")).strip()
        t = (t.replace("&#8217;", "'").replace("&amp;", "&")
              .replace("&#8211;", "-").replace("&#039;", "'").replace("&#8230;", "..."))
        if not t: continue
        try: pub = dt.datetime.fromisoformat(j["date"]).replace(tzinfo=dt.timezone.utc)
        except Exception: pub = None
        out.append(rec(source="mairie", direct=True, ongrade=False, untagged=True,
            title=t, town=town, employer=town, url=j.get("link", base), published=pub))
    return out

def a_massy():
    so = BeautifulSoup(requests.get(MASSY, headers=UA, timeout=30).text, "html.parser")
    seen, out = set(), []
    for a in so.find_all("a", href=True):
        if "/offres-demploi/" not in a["href"]: continue
        t = a.get_text(" ", strip=True)
        if re.match(r"(lire la suite|partager|imprimer|t[ée]l[ée]charger)", t, re.I): continue
        t = re.sub(r'^[^«]*«\s*|\s*»[^»]*$', '', t).strip() or t
        if not t or len(t) < 14 or a["href"] in seen: continue
        seen.add(a["href"])
        m = re.search(r"Cat[ée]gorie\s*([ABC])\b", t)
        t = re.split(r"\s+[–-]\s+Cat[ée]gorie", t)[0].strip()
        out.append(rec(source="mairie", direct=True, ongrade=False, untagged=True,
            title=t[:110], town="Massy", employer="Massy", url=a["href"],
            category=(m.group(1) if m else None)))
    return out

def a_noisy():
    """Noisy-le-Grand (TYPO3/Stratis) : blocs article.job-block__item.
    Donne titre, service, categorie, filiere ET date -> la source la plus riche."""
    so = BeautifulSoup(requests.get(NOISY, headers=UA, timeout=30).text, "html.parser")
    seen, out = set(), []
    for art in so.select("article.job-block__item"):
        a = art.select_one("h2.job-block__title a, .job-block__title a")
        if not a or not a.get("href"): continue
        t = a.get_text(" ", strip=True)
        if not t or a["href"] in seen: continue
        seen.add(a["href"])
        txt = art.get_text(" ", strip=True)
        mc = re.search(r"Cat[ée]gorie\s*:?\s*([ABC])\b", txt)
        mf = re.search(r"Fili[èe]re\s*:?\s*([A-Za-zÀ-ÿ' -]{3,30})", txt)
        tm = art.select_one("time[datetime]")
        pub = None
        if tm:
            try:
                pub = dt.datetime.strptime(tm["datetime"][:10], "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
            except Exception:
                pub = None
        fil = mf.group(1).strip() if mf else None
        out.append(rec(source="mairie", direct=True,
            ongrade=bool(fil and CULT_RE.search(fil)),
            untagged=not fil,
            title=t, town="Noisy-le-Grand", employer="Noisy-le-Grand",
            url=a["href"] if a["href"].startswith("http") else "https://www.noisylegrand.fr" + a["href"],
            published=pub, category=(mc.group(1) if mc else None), filiere=fil))
    return out

def _push(out, title, url, town, cat=None, pub=None):
    t = re.sub(r"\s+", " ", (title or "")).strip()
    t = re.sub(r"\s*\(pdf\)\s*$", "", t, flags=re.I)
    if len(t) < 10 or NOTJOB.search(t): return
    out.append(rec(source="mairie", direct=True, ongrade=False, untagged=True,
                   title=t[:120], town=town, employer=town, url=url,
                   category=cat, published=pub))

def a_parismusees():
    """Paris Musees (Drupal) : .offers-list__card, 3 pages (?page=N, base 0)."""
    out, seen = [], set()
    for pg in range(0, 6):
        u = PMUSEES + (f"?page={pg}" if pg else "")
        so = BeautifulSoup(requests.get(u, headers=UA, timeout=30).text, "html.parser")
        cards = so.select(".offers-list__card")
        if not cards: break
        fresh = 0
        for c in cards:
            h2 = c.select_one("h2")
            a = c.find("a", href=True)
            if not h2: continue
            href = a["href"] if a else PMUSEES
            if href in seen: continue
            seen.add(href); fresh += 1
            tm = c.select_one("time[datetime]")
            pub = None
            if tm:
                try: pub = dt.datetime.fromisoformat(tm["datetime"].replace("Z", "+00:00"))
                except Exception: pub = None
            _push(out, h2.get_text(" ", strip=True),
                  href if href.startswith("http") else "https://www.parismusees.paris.fr" + href,
                  "Paris Musées", pub=None)   # la date affichee est la date LIMITE, pas la publication
        if not fresh: break
    return out

def a_espci():
    so = BeautifulSoup(requests.get(ESPCI, headers=UA, timeout=30).text, "html.parser")
    out, seen = [], set()
    for a in so.find_all("a", href=True):
        if "/recrutement/offres-emploi/" not in a["href"]: continue
        if a["href"].rstrip("/").endswith("offres-emploi"): continue
        if a["href"] in seen: continue
        seen.add(a["href"])
        _push(out, a.get_text(" ", strip=True), a["href"], "ESPCI")
    return out

def a_arcueil():
    """Arcueil : offres en accordeons (pas d'URL propre) -> on pointe la page."""
    so = BeautifulSoup(requests.get(ARCUEIL, headers=UA, timeout=30).text, "html.parser")
    out = []
    for a in so.select('a[href^="#collapse_block"]'):
        _push(out, a.get_text(" ", strip=True), ARCUEIL, "Arcueil")
    return out

def a_fresnes():
    """Fresnes : chaque offre est un PDF sous /app/uploads/, mais le site pose DEUX liens
    par offre (une vignette sans texte + le titre) -> on retient le meilleur libelle."""
    so = BeautifulSoup(requests.get(FRESNES, headers=UA, timeout=30).text, "html.parser")
    best = {}
    for a in so.find_all("a", href=True):
        if "/app/uploads/" not in a["href"]: continue
        t = a.get_text(" ", strip=True)
        if len(t) > len(best.get(a["href"], "")):
            best[a["href"]] = t
    out = []
    for href, t in best.items():
        _push(out, t, href, "Fresnes")
    return out

def a_rosny():
    so = BeautifulSoup(requests.get(ROSNY, headers=UA, timeout=30).text, "html.parser")
    out, seen = [], set()
    for a in so.find_all("a", href=True):
        if ".pdf" not in a["href"].lower() or "/uploads/" not in a["href"]: continue
        if a["href"] in seen: continue
        seen.add(a["href"])
        _push(out, a.get_text(" ", strip=True), a["href"], "Rosny-sous-Bois")
    return out

def a_saintmande():
    """Saint-Mande : accordeons. Le titre est dans a.accordion-title, le PDF dans le
    div.accordion-content qui suit."""
    so = BeautifulSoup(requests.get(STMANDE, headers=UA, timeout=30).text, "html.parser")
    out = []
    for head in so.select("a.accordion-title"):
        title = head.get_text(" ", strip=True)
        body = head.find_next_sibling(class_="accordion-content")
        link = body.find("a", href=True) if body else None
        url = link["href"] if link else STMANDE
        _push(out, title, url if url.startswith("http") else "https://www.saintmande.fr" + url,
              "Saint-Mandé")
    return out

def a_ivry():
    """Ivry : offres sous le titre 'Postes a pourvoir'."""
    so = BeautifulSoup(requests.get(IVRY, headers=UA, timeout=30).text, "html.parser")
    out, seen = [], set()
    anchor = None
    for hh in so.select("h2, h3, h4"):
        if "postes à pourvoir" in hh.get_text(strip=True).lower():
            anchor = hh; break
    scope = anchor.find_parent(["section", "div"]) if anchor else so
    for a in scope.find_all("a", href=True):
        h = a["href"]
        if h in seen or h.startswith("#"): continue
        t = a.get_text(" ", strip=True)
        if not re.search(r"h/?f|f/?h|\(h|responsable|charg|agent|assistant|technicien|"
                         r"directeur|animateur|[ée]ducateur|gestionnaire|adjoint|"
                         r"m[ée]diath|biblioth", t, re.I):
            continue
        seen.add(h)
        _push(out, t, h if h.startswith("http") else "https://www.ivry94.fr" + h, "Ivry-sur-Seine")
    return out

ROLE_RE = re.compile(
    r"h/?f|f/?h|\(h|responsable|charg[ée]|agent|assistant|technicien|directeur|directrice|"
    r"animateur|[ée]ducateur|gestionnaire|coordinateur|auxiliaire|adjoint|m[ée]diath|biblioth|"
    r"conservat|apprenti|chef de|jardinier|cuisinier|attach[ée]|professeur|surveillant|"
    r"r[ée]f[ée]rent|ing[ée]nieur|infirmier|psychologue|archiviste|juriste|comptable|"
    r"[ée]lectricien|m[ée]canicien|secr[ée]taire|m[ée]decin|chef d|instructeur", re.I)

def a_headless():
    """Trois sites n'exposent leurs offres qu'apres execution du JavaScript :
       - Ivry           : widget wink-lab en iframe (SPA Nuxt)
       - Neuilly-Plaisance : widget JS injecte
       - CD Essonne     : portail Elsatis, la liste s'affiche apres un clic
    On lit la page rendue, comme le ferait un visiteur. Aucune API privee n'est forcee.
    Optionnel : sans Playwright installe, la fonction renvoie [] sans faire echouer le run."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.stderr.write("[headless] Playwright absent -> 3 sources ignorees (repli sur le hub)\n")
        return []

    out = []
    UAS = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
    with sync_playwright() as pw:
        args = ["--no-sandbox"] + (["--ignore-certificate-errors"] if HEADLESS_INSECURE else [])
        br = pw.chromium.launch(args=args)
        ctx = br.new_context(user_agent=UAS, locale="fr-FR",
                             ignore_https_errors=HEADLESS_INSECURE)

        def texts_of(page, selector="a"):
            seen, res = set(), []
            for fr in page.frames:
                try:
                    for el in fr.query_selector_all(selector):
                        t = re.sub(r"\s+", " ", (el.inner_text() or "").strip())
                        if 12 < len(t) < 100 and ROLE_RE.search(t) and t not in seen:
                            seen.add(t)
                            res.append((t, el.get_attribute("href") or ""))
                except Exception:
                    continue
            return res

        # --- Ivry : on attaque directement l'iframe
        try:
            pg = ctx.new_page()
            pg.goto(IVRY_IFRAME, wait_until="networkidle", timeout=HEADLESS_TIMEOUT)
            pg.wait_for_timeout(4000)
            pg.mouse.wheel(0, 4000); pg.wait_for_timeout(2000)
            # wink-lab ne met pas les intitules dans des <a> -> selecteur elargi
            for t, href in texts_of(pg, "a, li, article, h2, h3, [class*=job], [class*=offer]"):
                _push(out, t, href or IVRY, "Ivry-sur-Seine")
            sys.stderr.write(f"[headless:ivry] {len([o for o in out if o['town']=='Ivry-sur-Seine'])}\n")
            pg.close()
        except Exception as e:
            sys.stderr.write(f"[headless:ivry] FAIL {str(e)[:60]}\n")

        # --- Neuilly-Plaisance
        try:
            pg = ctx.new_page()
            pg.goto(NEUILLY_P, wait_until="networkidle", timeout=HEADLESS_TIMEOUT)
            pg.wait_for_timeout(4000)
            n0 = len(out)
            for t, href in texts_of(pg):
                _push(out, t, href or NEUILLY_P, "Neuilly-Plaisance")
            sys.stderr.write(f"[headless:neuilly] {len(out)-n0}\n")
            pg.close()
        except Exception as e:
            sys.stderr.write(f"[headless:neuilly] FAIL {str(e)[:60]}\n")

        # --- CD Essonne : la liste apparait apres un clic, puis c'est un tableau
        try:
            pg = ctx.new_page()
            pg.goto(ESSONNE_ATS, wait_until="networkidle", timeout=HEADLESS_TIMEOUT)
            pg.wait_for_timeout(3000)
            el = pg.query_selector("a:has-text('LISTE DES OFFRES')")
            if el:
                el.click(); pg.wait_for_timeout(5000)
            n0 = len(out)
            for row in pg.query_selector_all("tr"):
                t = re.sub(r"\s+", " ", (row.inner_text() or "").strip())
                if not (12 < len(t) < 160) or not ROLE_RE.search(t): continue
                # "TITRE  TypeContrat  Domaine  Lieu" -> on coupe avant le type de contrat
                title = re.split(r"\s+(?:CDD|CDI|Emploi permanent|Stage|Apprentissage)\b",
                                 t, maxsplit=1)[0].strip()
                _push(out, title, ESSONNE_ATS, "Conseil départemental de l'Essonne")
            sys.stderr.write(f"[headless:essonne] {len(out)-n0}\n")
            pg.close()
        except Exception as e:
            sys.stderr.write(f"[headless:essonne] FAIL {str(e)[:60]}\n")

        br.close()
    return out

# ----------------------------------------------------------------- TRANSIT
def transit_link(town):
    return ("https://www.google.com/maps/dir/?api=1&travelmode=transit"
            f"&origin={quote_plus(ORIGIN_NAME+', France')}"
            f"&destination={quote_plus(town+', France')}")

def transit_minutes(towns):
    """Durée porte-à-porte via l'API PRIM (IDFM). Nécessite PRIM_TOKEN.
    Mise en cache : une commune n'est calculée qu'une fois."""
    try: cache = json.load(open(TCACHE))
    except Exception: cache = {}
    if not PRIM:
        return cache            # pas de clé -> on garde ce qu'on a (souvent vide)
    todo = [t for t in towns if t not in cache]
    for t in todo:
        try:
            g = requests.get("https://geo.api.gouv.fr/communes",
                params={"nom": t, "fields":"centre", "boost":"population", "limit":1}, timeout=15).json()
            if not g: cache[t] = None; continue
            lon, lat = g[0]["centre"]["coordinates"]
            when = (dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).strftime("%Y%m%dT090000")
            r = requests.get("https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia/journeys",
                params={"from": f"{ORIGIN_LATLON[1]};{ORIGIN_LATLON[0]}",
                        "to": f"{lon};{lat}", "datetime": when},
                headers={"apikey": PRIM}, timeout=25)
            js = r.json()
            secs = [j["duration"] for j in js.get("journeys", []) if j.get("duration")]
            cache[t] = round(min(secs)/60) if secs else None
        except Exception as e:
            sys.stderr.write(f"[transit:{t}] {str(e)[:50]}\n"); cache[t] = None
    json.dump(cache, open(TCACHE,"w"), ensure_ascii=False, indent=0)
    return cache

def notify(fresh):
    """Envoie UNE notification recapitulative (pas une par offre) vers le telephone.
    Silencieux si NTFY_TOPIC n'est pas configure : le script reste utilisable sans."""
    if not fresh or not NTFY_TOPIC:
        return
    n = len(fresh)
    titre = f"{n} nouvelle offre" + ("s" if n > 1 else "")
    lignes = [f"• {o['title']} — {o['town']}" for o in fresh[:5]]
    if n > 5:
        lignes.append(f"… et {n - 5} autre(s)")
    corps = "\n".join(lignes)
    headers = {"Title": titre.encode("utf-8"), "Tags": "books", "Priority": "default"}
    # Si une seule offre, le clic mene droit a l'offre ; sinon au rapport.
    cible = fresh[0]["url"] if n == 1 else REPORT_URL
    if cible:
        headers["Click"] = cible
    if NTFY_EMAIL:
        headers["Email"] = NTFY_EMAIL
    try:
        r = requests.post(f"https://ntfy.sh/{NTFY_TOPIC}",
                          data=corps.encode("utf-8"), headers=headers, timeout=15)
        sys.stderr.write(f"[notify] ntfy {r.status_code} — {n} offre(s)\n")
    except Exception as e:
        sys.stderr.write(f"[notify] echec {str(e)[:60]}\n")

# ----------------------------------------------------------------- MERGE
def merge(records):
    out = []
    for r in records:
        nt, ks = norm_title(r["title"]), keyset(r)
        hit = None
        for m in out:
            if same_job(r["title"], ks, m["title"], m["_keys"]):
                hit = m; break
        if hit:
            hit["sources"].add(r["source"]); hit["_keys"] |= ks
            if r.get("published") and (not hit["published"] or r["published"] < hit["published"]):
                hit["published"] = r["published"]
            if r["direct"] and not hit["_direct"]:
                hit.update(url=r["url"], title=r["title"], town=r["town"], _direct=True)
            hit["category"] = hit["category"] or r.get("category")
            hit["ongrade"] = hit["ongrade"] or r.get("ongrade")
        else:
            out.append(dict(_nt=nt, _keys=ks, _direct=r["direct"], sources={r["source"]},
                title=r["title"], town=r["town"], url=r["url"], published=r.get("published"),
                category=r.get("category"), ongrade=r.get("ongrade", False),
                untagged=r.get("untagged", False)))
    for o in out:
        anchor = sorted(o["_keys"])[0] if o["_keys"] else "?"
        o["guid"] = "job-" + hashlib.sha1((anchor + "|" + o["_nt"]).encode()).hexdigest()[:16]
    return out

# ----------------------------------------------------------------- MAIN
def monitored():
    """Employeurs lus en direct, avec leur mode de lecture. Sert la section finale
    'Communes et employeurs suivis' : elle doit refleter la config, pas une liste
    ecrite a la main qui se desynchroniserait."""
    api  = list(PP_TOWNS.values())
    api += [t for t, _, _ in WP_CPT] + [t for t, _ in WP_POSTS] + list(WP_JOBS)
    api += list(RSS_FEEDS)
    site = [t for _, t in GESTMAX_TABLE] + [t for _, t in GESTMAX_LIST] + [t for _, t in GESTMAX_TR]
    site += ["Département des Hauts-de-Seine", "Sceaux", "Vincennes", "Champigny-sur-Marne",
             "Charenton-le-Pont", "Montreuil", "Le Perreux-sur-Marne", "Massy",
             "Noisy-le-Grand", "Paris Musées", "ESPCI", "Arcueil", "Fresnes",
             "Rosny-sous-Bois", "Saint-Mandé"]
    js   = ["Ivry-sur-Seine", "Neuilly-Plaisance", "Conseil départemental de l'Essonne"]
    out = ([(n, "api") for n in api] + [(n, "site") for n in site] + [(n, "js") for n in js])
    seen, uniq = set(), []
    for n, m in sorted(out, key=lambda x: _n(x[0])):
        if norm_town(n) in seen: continue
        seen.add(norm_town(n)); uniq.append((n, m))
    return uniq

def main():
    R = []
    HEALTH = []   # (nom, nb_offres) pour l'etat des sources
    for name, fn in [("hub", a_hub)]:
        try: r = fn(); R += r; sys.stderr.write(f"[{name}] {len(r)}\n"); HEALTH.append((f"{name}", len(r)))
        except Exception as e: sys.stderr.write(f"[{name}] FAIL {e}\n")
    try: r = a_profilpublic(); R += r; sys.stderr.write(f"[profilpublic] {len(r)}\n"); HEALTH.append((f"profilpublic", len(r)))
    except Exception as e: sys.stderr.write(f"[profilpublic] FAIL {e}\n")
    for b, e_ in GESTMAX_TABLE:
        try: r = a_gestmax_table(b, e_); R += r; sys.stderr.write(f"[gestmax-table {e_}] {len(r)}\n"); HEALTH.append((f"gestmax-table {e_}", len(r)))
        except Exception as e: sys.stderr.write(f"[gestmax-table] FAIL {e}\n")
    for b, dt_ in GESTMAX_LIST:
        try: r = a_gestmax_list(b, dt_); R += r; sys.stderr.write(f"[gestmax-list {dt_}] {len(r)}\n"); HEALTH.append((f"gestmax-list {dt_}", len(r)))
        except Exception as e: sys.stderr.write(f"[gestmax-list] FAIL {e}\n")
    for nm, fn in [("hauts-de-seine", a_hds), ("sceaux", a_sceaux), ("vincennes", a_vincennes),
                   ("champigny", a_champigny), ("charenton", a_charenton),
                   ("montreuil", a_montreuil), ("le perreux", a_leperreux),
                   ("noisy-le-grand", a_noisy), ("paris musées", a_parismusees),
                   ("espci", a_espci), ("arcueil", a_arcueil), ("fresnes", a_fresnes),
                   ("rosny", a_rosny), ("saint-mandé", a_saintmande)]:
        try: r = fn(); R += r; sys.stderr.write(f"[{nm}] {len(r)}\n"); HEALTH.append((f"{nm}", len(r)))
        except Exception as e: sys.stderr.write(f"[{nm}] FAIL {e}\n")
    for tw, bs in WP_JOBS.items():
        try: r = a_wp_jobs(tw, bs); R += r; sys.stderr.write(f"[wp {tw}] {len(r)}\n"); HEALTH.append((f"wp {tw}", len(r)))
        except Exception as e: sys.stderr.write(f"[wp {tw}] FAIL {e}\n")
    for b, tw in GESTMAX_TR:
        try: r = a_gestmax_tr(b, tw); R += r; sys.stderr.write(f"[gestmax-tr {tw}] {len(r)}\n"); HEALTH.append((f"gestmax-tr {tw}", len(r)))
        except Exception as e: sys.stderr.write(f"[gestmax-tr {tw}] FAIL {e}\n")
    for tw, bs, cpt in WP_CPT:
        try: r = a_wp_cpt(tw, bs, cpt); R += r; sys.stderr.write(f"[wp-cpt {tw}] {len(r)}\n"); HEALTH.append((f"wp-cpt {tw}", len(r)))
        except Exception as e: sys.stderr.write(f"[wp-cpt {tw}] FAIL {e}\n")
    for tw, bs in WP_POSTS:
        try: r = a_wp_cpt(tw, bs, "posts"); R += r; sys.stderr.write(f"[wp-posts {tw}] {len(r)}\n"); HEALTH.append((f"wp-posts {tw}", len(r)))
        except Exception as e: sys.stderr.write(f"[wp-posts {tw}] FAIL {e}\n")
    try: r = a_massy(); R += r; sys.stderr.write(f"[massy] {len(r)}\n"); HEALTH.append((f"massy", len(r)))
    except Exception as e: sys.stderr.write(f"[massy] FAIL {e}\n")
    try: r = a_headless(); R += r; sys.stderr.write(f"[headless total] {len(r)}\n"); HEALTH.append((f"headless total", len(r)))
    except Exception as e: sys.stderr.write(f"[headless] FAIL {e}\n")
    for t, u in RSS_FEEDS.items():
        try: r = a_rss(t, u); R += r; sys.stderr.write(f"[rss {t}] {len(r)}\n"); HEALTH.append((f"rss {t}", len(r)))
        except Exception as e: sys.stderr.write(f"[rss {t}] FAIL {e}\n")

    # tiers : 1 = pertinent (grade OK, ou filière culturelle, ou mot-clé métier)
    t1r = [r for r in R if (r.get("ongrade") or KW_RE.search(_n(r["title"])))
           and not EXCL_RE.search(r["title"])]
    t2r = [r for r in R if r not in t1r and r.get("untagged")]
    t1, t2 = merge(t1r), merge(t2r)
    g1 = {o["guid"] for o in t1}
    t2 = [o for o in t2 if o["guid"] not in g1]

    # première détection (sert de date quand la source n'en donne pas)
    try: state = json.load(open(STATE))
    except Exception: state = {}
    if isinstance(state, list): state = {g: None for g in state}
    now = dt.datetime.now(dt.timezone.utc)
    new = set()
    for o in t1 + t2:
        if o["guid"] not in state:
            state[o["guid"]] = now.isoformat(); new.add(o["guid"])
        if not o["published"]:
            try: o["published"] = dt.datetime.fromisoformat(state[o["guid"]])
            except Exception: o["published"] = now
            o["approx_date"] = True
    json.dump(state, open(STATE,"w"), indent=0)
    t1.sort(key=lambda o: o["published"], reverse=True)
    t2.sort(key=lambda o: o["published"], reverse=True)

    notify([o for o in t1 if o["guid"] in new])   # Tier 1 uniquement : pas de bruit

    tc = transit_minutes({o["town"] for o in t1})
    ADAPTED = {norm_town(x) for x in (
        list(PP_TOWNS.values())
        + [e for _, e in GESTMAX_TABLE] + [e for _, e in GESTMAX_LIST]
        + list(RSS_FEEDS) + list(WP_JOBS)
        + ["Département des Hauts-de-Seine", "Sceaux", "Vincennes", "Champigny-sur-Marne",
           "Charenton-le-Pont", "Grand Paris Sud Est Avenir", "Montreuil",
           "Le Perreux-sur-Marne", "Massy", "Noisy-le-Grand", "Paris Musées", "ESPCI",
           "Arcueil", "Fresnes", "Rosny-sous-Bois", "Saint-Mandé", "Ivry-sur-Seine",
           "Ecole Supérieure de Physique et de Chimie Industrielles",
           "Conseil départemental de l'Essonne", "Neuilly-Plaisance"]
        + [t for _, t in GESTMAX_TR] + [t for t, _, _ in WP_CPT] + [t for t, _ in WP_POSTS])}
    def adapted(keys):
        for k in keys:
            for a in ADAPTED:
                if k == a: return True
                if len(a) >= 8 and len(k) >= 8 and (k.startswith(a) or a.startswith(k)):
                    return True
        return False

    cov = {}
    for o in t1 + t2:
        if not adapted(o["_keys"]):                # aucun adaptateur -> depend du hub
            k = sorted(o["_keys"])[0] if o["_keys"] else "?"
            c = cov.setdefault(k, dict(town=o["town"], n=0))
            c["n"] += 1
    sys.stderr.write(f"[tiers] T1={len(t1)} T2={len(t2)} new={len(new)} hub-only={len(cov)}\n")
    html_report(t1, t2, new, sorted(cov.values(), key=lambda c: -c["n"]), tc, HEALTH, monitored())
    rss_out(t1, "Veille culturelle — ciblé", "tier1.xml")
    rss_out(t2, "Veille culturelle — à vérifier", "tier2.xml")

def rss_out(offers, title, fn):
    items = "".join(f"""  <item>
    <title>{escape(o['title'])}</title><link>{escape(o['url'])}</link>
    <guid isPermaLink="false">{o['guid']}</guid>
    <pubDate>{format_datetime(o['published'])}</pubDate>
    <description>{escape(o['town'] + (' | cat. '+o['category'] if o.get('category') else ''))}</description>
  </item>\n""" for o in offers)
    open(fn, "w", encoding="utf-8").write(
f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>{escape(title)}</title>
<link>{escape(HUB_URL)}</link><description>{len(offers)} offres</description>
<lastBuildDate>{format_datetime(dt.datetime.now(dt.timezone.utc))}</lastBuildDate>
{items}</channel></rss>""")

def html_report(t1, t2, new, cov, tc, health=(), mons=()):
    now = dt.datetime.now()
    fresh = [o for o in t1 if o["guid"] in new]
    n_fast = sum(1 for o in t1 if "mairie" in o["sources"])

    def cat_chip(c):
        return (f'<span class="cat cat-{c}">{c}</span>' if c in ("A", "B", "C")
                else '<span class="cat cat-none">·</span>')

    def trajet(o):
        m = tc.get(o["town"])
        if isinstance(m, int):
            return f'<span class="mins">{m}<span class="u">min</span></span>'
        return (f'<a class="mins-link" target="_blank" rel="noopener" '
                f'href="{escape(transit_link(o["town"]))}">itinéraire</a>')

    def row(o, is_new):
        d = o["published"]
        day = f'{d.day:02d}.{d.month:02d}'
        approx = ' <span class="approx" title="La source ne date pas ses offres : date de première détection">≈</span>' if o.get("approx_date") else ''
        src = ('<span class="src src-fast" title="Lu directement sur le site de la collectivité">direct</span>'
               if "mairie" in o["sources"]
               else '<span class="src src-hub" title="Vu via emploi-territorial">hub</span>')
        return f"""<tr class="{'is-new' if is_new else ''}"
              data-new="{1 if is_new else 0}" data-fast="{1 if 'mairie' in o['sources'] else 0}"
              data-cat="{o.get('category') or '-'}"
              data-q="{escape((o['title'] + ' ' + o['town']).lower())}">
          <td class="c-date"><span class="day">{day}</span>{approx}</td>
          <td class="c-cat">{cat_chip(o.get('category'))}</td>
          <td class="c-title">
            <a href="{escape(o['url'])}" target="_blank" rel="noopener">{escape(o['title'])}</a>
            <span class="town">{escape(o['town'])}</span>
          </td>
          <td class="c-src">{src}</td>
          <td class="c-trajet">{trajet(o)}</td>
        </tr>"""

    stamp = ""
    if fresh:
        items = "".join(
            f"""<li><a href="{escape(o['url'])}" target="_blank" rel="noopener">{escape(o['title'])}</a>
                <span class="n-meta">{escape(o['town'])}{' · cat. ' + o['category'] if o.get('category') else ''}</span></li>"""
            for o in fresh[:12])
        more = f'<p class="n-more">et {len(fresh)-12} autre(s) — voir le tampon dans la liste</p>' if len(fresh) > 12 else ""
        stamp = f"""
    <section class="new-panel">
      <div class="stamp"><span>{len(fresh)}</span><em>{'nouvelle' if len(fresh)==1 else 'nouvelles'}</em></div>
      <div class="new-body">
        <h2>Depuis votre dernier passage</h2>
        <ul class="new-list">{items}</ul>
        {more}
      </div>
    </section>"""

    t2rows = "".join(
        f"""<tr><td class="c-date"><span class="day">{o['published'].day:02d}.{o['published'].month:02d}</span></td>
        <td class="c-cat">{cat_chip(o.get('category'))}</td>
        <td class="c-title"><a href="{escape(o['url'])}" target="_blank" rel="noopener">{escape(o['title'])}</a>
        <span class="town">{escape(o['town'])}</span></td></tr>""" for o in t2[:400])

    covrows = "".join(f"<li>{escape(c['town'])} <span>{c['n']}</span></li>" for c in cov) or "<li>Toutes les collectivités suivies sont lues en direct.</li>"
    MODE = {"api": "API", "site": "site", "js": "navigateur"}
    mon_rows = "".join(
        f'<li>{escape(nm)} <span>{MODE[m]}</span></li>' for nm, m in mons)
    health_rows = "".join(
        f'<li class="{"dead" if not n else ""}">{escape(nm)} <span>{n}</span></li>'
        for nm, n in health)

    open("report.html", "w", encoding="utf-8").write(f"""<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Veille · filière culturelle</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,300;0,500;0,600;1,300&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --ink:#1B2A33; --ink-2:#54666F; --ink-3:#8A9AA2;
    --paper:#FBFAF7; --card:#FFF; --rule:#E4E1D8;
    --stamp:#A0303C; --fast:#2C6A57; --hub:#8A9AA2;
    --catA:#2F4C7A; --catB:#6C4F86; --catC:#7A6234;
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--paper);color:var(--ink);
    font:400 15px/1.55 Inter,system-ui,sans-serif;
    -webkit-font-smoothing:antialiased}}
  .wrap{{max-width:1080px;margin:0 auto;padding:2.6rem 1.25rem 5rem}}

  header{{border-bottom:2px solid var(--ink);padding-bottom:1.1rem;margin-bottom:2rem}}
  h1{{font:300 2.6rem/1.05 Spectral,Georgia,serif;letter-spacing:-.015em;margin:0 0 .35rem}}
  h1 em{{font-style:italic;font-weight:300}}
  .sub{{font:400 .8rem/1.5 "IBM Plex Mono",monospace;color:var(--ink-2);
    text-transform:uppercase;letter-spacing:.09em}}
  .stats{{display:flex;gap:1.75rem;margin-top:1rem;flex-wrap:wrap}}
  .stat b{{font:500 1.35rem/1 Spectral,serif;display:block}}
  .stat span{{font:400 .68rem/1 "IBM Plex Mono",monospace;color:var(--ink-3);
    text-transform:uppercase;letter-spacing:.1em}}

  /* --- tampon : la signature de la page --- */
  .new-panel{{display:flex;gap:1.6rem;align-items:flex-start;background:var(--card);
    border:1px solid var(--rule);border-left:3px solid var(--stamp);
    padding:1.4rem 1.5rem;margin-bottom:2.4rem}}
  .stamp{{flex:0 0 92px;height:92px;border:2px solid var(--stamp);border-radius:50%;
    color:var(--stamp);display:flex;flex-direction:column;align-items:center;
    justify-content:center;transform:rotate(-8deg);opacity:.92}}
  .stamp span{{font:500 2rem/1 "IBM Plex Mono",monospace}}
  .stamp em{{font:400 .58rem/1 "IBM Plex Mono",monospace;font-style:normal;
    text-transform:uppercase;letter-spacing:.11em;margin-top:.25rem}}
  .new-body h2{{font:500 1.05rem/1.2 Spectral,serif;margin:.15rem 0 .7rem}}
  .new-list{{list-style:none;margin:0;padding:0}}
  .new-list li{{padding:.3rem 0;border-bottom:1px dotted var(--rule)}}
  .new-list li:last-child{{border:0}}
  .new-list a{{color:var(--ink);text-decoration:none;font-weight:500;border-bottom:1px solid var(--stamp)}}
  .new-list a:hover{{color:var(--stamp)}}
  .n-meta{{font:400 .72rem/1 "IBM Plex Mono",monospace;color:var(--ink-3);margin-left:.5rem}}
  .n-more{{font-size:.8rem;color:var(--ink-3);margin:.6rem 0 0}}

  .tools{{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin-bottom:.9rem}}
  #q{{flex:1 1 220px;min-width:180px;padding:.5rem .7rem;border:1px solid var(--rule);
    background:var(--card);font:400 .85rem Inter,sans-serif;color:var(--ink)}}
  #q:focus{{outline:2px solid var(--ink);outline-offset:-1px}}
  .chip{{padding:.4rem .75rem;border:1px solid var(--rule);background:var(--card);
    font:400 .72rem/1 "IBM Plex Mono",monospace;text-transform:uppercase;
    letter-spacing:.07em;color:var(--ink-2);cursor:pointer}}
  .chip[aria-pressed=true]{{background:var(--ink);color:#fff;border-color:var(--ink)}}
  .chip:focus-visible{{outline:2px solid var(--ink);outline-offset:2px}}

  h2.sec{{font:500 1.25rem/1.2 Spectral,serif;margin:2.6rem 0 .3rem;
    display:flex;align-items:baseline;gap:.6rem}}
  h2.sec .n{{font:400 .72rem "IBM Plex Mono",monospace;color:var(--ink-3)}}
  .lead{{color:var(--ink-2);font-size:.85rem;margin:0 0 1rem;max-width:62ch}}

  table{{width:100%;border-collapse:collapse}}
  thead th{{font:500 .64rem/1 "IBM Plex Mono",monospace;text-transform:uppercase;
    letter-spacing:.1em;color:var(--ink-3);text-align:left;padding:.5rem .6rem;
    border-bottom:1px solid var(--ink)}}
  tbody tr{{border-bottom:1px solid var(--rule)}}
  tbody tr:hover{{background:#fff}}
  td{{padding:.72rem .6rem;vertical-align:top}}
  .c-date{{width:64px;white-space:nowrap}}
  .day{{font:500 .8rem "IBM Plex Mono",monospace;color:var(--ink-2)}}
  .approx{{color:var(--ink-3);cursor:help}}
  .c-cat{{width:34px}}
  .cat{{display:inline-block;width:20px;height:20px;line-height:19px;text-align:center;
    font:500 .7rem "IBM Plex Mono",monospace;border:1px solid currentColor}}
  .cat-A{{color:var(--catA)}} .cat-B{{color:var(--catB)}} .cat-C{{color:var(--catC)}}
  .cat-none{{color:#CFCBC1;border-color:#E9E6DE}}
  .c-title a{{color:var(--ink);text-decoration:none;font-weight:500;
    border-bottom:1px solid transparent}}
  .c-title a:hover{{border-bottom-color:var(--ink)}}
  .town{{display:block;font:400 .74rem/1.4 "IBM Plex Mono",monospace;color:var(--ink-3);margin-top:.1rem}}
  .c-src{{width:74px}}
  .src{{font:400 .64rem/1 "IBM Plex Mono",monospace;text-transform:uppercase;letter-spacing:.07em}}
  .src-fast{{color:var(--fast)}} .src-hub{{color:var(--hub)}}
  .c-trajet{{width:88px;text-align:right}}
  .mins{{font:500 .85rem "IBM Plex Mono",monospace}}
  .mins .u{{font-size:.6rem;color:var(--ink-3);margin-left:2px}}
  .mins-link{{font:400 .68rem "IBM Plex Mono",monospace;color:var(--ink-3);
    text-decoration:none;border-bottom:1px dotted var(--ink-3)}}
  .mins-link:hover{{color:var(--ink)}}

  tr.is-new td{{background:#FDF7F7}}
  tr.is-new .c-date{{position:relative}}
  tr.is-new .c-date::before{{content:"";position:absolute;left:-12px;top:.95rem;
    width:5px;height:5px;border-radius:50%;background:var(--stamp)}}

  details{{margin-top:1rem;border-top:1px solid var(--rule);padding-top:1rem}}
  summary{{cursor:pointer;font:500 .8rem "IBM Plex Mono",monospace;
    text-transform:uppercase;letter-spacing:.08em;color:var(--ink-2)}}
  summary:hover{{color:var(--ink)}}
  .cov{{list-style:none;padding:0;margin:.8rem 0 0;columns:2;font-size:.85rem}}
  .cov li{{padding:.2rem 0;color:var(--ink-2)}}
  .cov span{{font:400 .72rem "IBM Plex Mono",monospace;color:var(--ink-3)}}
  .monitored{{columns:3;font-size:.85rem}}
  .monitored li{{break-inside:avoid;padding:.22rem 0;color:var(--ink)}}
  .monitored span{{font:400 .64rem "IBM Plex Mono",monospace;color:var(--ink-3);
    text-transform:uppercase;letter-spacing:.06em;margin-left:.3rem}}
  @media(max-width:820px){{.monitored{{columns:2}}}}
  @media(max-width:520px){{.monitored{{columns:1}}}}
  .health li.dead{{color:var(--stamp)}}
  .health li.dead span{{color:var(--stamp);font-weight:500}}
  footer{{margin-top:3.5rem;padding-top:1rem;border-top:1px solid var(--rule);
    font:400 .74rem/1.7 "IBM Plex Mono",monospace;color:var(--ink-3)}}
  .empty{{padding:1.4rem;color:var(--ink-3);font-size:.85rem;display:none}}
  @media(max-width:620px){{
    h1{{font-size:2rem}} .new-panel{{flex-direction:column;gap:1rem}}
    .c-trajet,.c-src{{display:none}} .cov{{columns:1}}
  }}
  @media(prefers-reduced-motion:no-preference){{
    .new-panel{{animation:rise .5s ease-out both}}
    @keyframes rise{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:none}}}}
  }}
</style></head><body>
<div class="wrap">
  <header>
    <h1>Veille <em>filière culturelle</em></h1>
    <p class="sub">Bibliothèques · patrimoine · langues — 20 km autour de {ORIGIN_NAME}</p>
    <div class="stats">
      <div class="stat"><b>{len(t1)}</b><span>offres ciblées</span></div>
      <div class="stat"><b>{len(fresh)}</b><span>nouvelles</span></div>
      <div class="stat"><b>{n_fast}</b><span>lues en direct</span></div>
      <div class="stat"><b>{now.strftime('%d.%m · %Hh%M')}</b><span>mise à jour</span></div>
    </div>
  </header>
  {stamp}
  <h2 class="sec">Offres ciblées <span class="n">{len(t1)}</span></h2>
  <p class="lead">Grades de la filière culturelle (catégories A, B et C) et intitulés du domaine
     livre, patrimoine et langues. <em>Direct</em> signale une offre lue sur le site de la
     collectivité, sans attendre la publication sur le hub.</p>
  <div class="tools">
    <input id="q" type="search" placeholder="Filtrer par intitulé ou commune…" aria-label="Filtrer">
    <button class="chip" data-f="new" aria-pressed="false">Nouvelles</button>
    <button class="chip" data-f="fast" aria-pressed="false">Direct</button>
    <button class="chip" data-f="A" aria-pressed="false">Cat. A</button>
    <button class="chip" data-f="B" aria-pressed="false">Cat. B</button>
    <button class="chip" data-f="C" aria-pressed="false">Cat. C</button>
  </div>
  <table id="t1">
    <thead><tr><th>Publiée</th><th>Cat.</th><th>Offre</th><th>Source</th><th>Trajet</th></tr></thead>
    <tbody>
      {"".join(row(o, o["guid"] in new) for o in t1)}
    </tbody>
  </table>
  <p class="empty" id="empty">Aucune offre ne correspond à ce filtre.</p>

  <h2 class="sec">À survoler <span class="n">{len(t2)}</span></h2>
  <p class="lead">Offres des sources directes sans grade, filière ni intitulé reconnu.
     Filet de sécurité : rien n'est écarté en silence.</p>
  <details>
    <summary>Déplier la liste</summary>
    <table><tbody>{t2rows}</tbody></table>
  </details>

  <h2 class="sec">État des sources <span class="n">{sum(1 for _, n in health if n)}/{len(health)} actives</span></h2>
  <p class="lead">Une source qui tombe à zéro sans raison signale une panne : le site a changé
     de structure. Rien ne casse — les autres sources continuent — mais l'adaptateur est à réparer.</p>
  <details>
    <summary>Déplier</summary>
    <ul class="cov health">{health_rows}</ul>
  </details>

  <h2 class="sec">Couverture</h2>
  <p class="lead">Collectivités encore lues via le hub uniquement — leurs offres peuvent
     arriver avec du retard.</p>
  <ul class="cov">{covrows}</ul>

  <h2 class="sec">Communes et employeurs suivis <span class="n">{len(mons)} en direct</span></h2>
  <p class="lead">Ces collectivités sont lues sur leur propre site, sans attendre le hub.
     <em>API</em> : flux ou interface de données · <em>site</em> : lecture de la page ·
     <em>navigateur</em> : la page n'existe qu'après exécution du JavaScript.<br>
     S'y ajoute <strong>emploi-territorial</strong>, qui couvre <em>toutes</em> les autres
     collectivités dans les 20 km autour de {ORIGIN_NAME} — mais avec un délai de publication.</p>
  <ul class="cov monitored">{mon_rows}</ul>

  <footer>
    ≈ date de première détection (la source ne date pas ses offres) ·
    {len(GRADES)} grades suivis · généré le {now.strftime('%d/%m/%Y à %H:%M')}
  </footer>
</div>
<script>
  const rows = [...document.querySelectorAll('#t1 tbody tr')];
  const chips = [...document.querySelectorAll('.chip')];
  const q = document.getElementById('q');
  const empty = document.getElementById('empty');
  const on = new Set();
  function apply() {{
    const term = q.value.trim().toLowerCase();
    let shown = 0;
    rows.forEach(r => {{
      let ok = !term || r.dataset.q.includes(term);
      if (ok && on.has('new')  && r.dataset.new  !== '1') ok = false;
      if (ok && on.has('fast') && r.dataset.fast !== '1') ok = false;
      const cats = [...on].filter(f => ['A','B','C'].includes(f));
      if (ok && cats.length && !cats.includes(r.dataset.cat)) ok = false;
      r.style.display = ok ? '' : 'none';
      if (ok) shown++;
    }});
    empty.style.display = shown ? 'none' : 'block';
  }}
  chips.forEach(c => c.addEventListener('click', () => {{
    const f = c.dataset.f;
    on.has(f) ? on.delete(f) : on.add(f);
    c.setAttribute('aria-pressed', on.has(f));
    apply();
  }}));
  q.addEventListener('input', apply);
</script>
</body></html>""")



if __name__ == "__main__":
    main()
