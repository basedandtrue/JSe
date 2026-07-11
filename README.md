# Veille emploi — filière culturelle

Page auto-actualisée (toutes les 30 min, 6h–22h) des offres bibliothèque / patrimoine /
langues dans un rayon de 20 km autour de Montgeron, avec notification sur téléphone
dès qu'une nouvelle offre paraît.

- **Offres ciblées** — grades de la filière culturelle (cat. A, B et C) + intitulés du domaine
- **À survoler** — filet de sécurité : offres sans grade ni mot-clé reconnu
- **État des sources** — si un adaptateur tombe à zéro, c'est une panne à réparer
- **Couverture** — collectivités encore lues via le hub (donc avec du retard)

`direct` = lu sur le site de la collectivité, sans attendre la publication sur le hub.

---

## 1. Mise en ligne (une fois)

1. Dépôt GitHub **public** (obligatoire pour Pages gratuit).
2. Déposer `veille_v2.py` à la racine et `.github/workflows/veille.yml` en respectant
   le chemin (via *Add file → Create new file*, taper le chemin complet dans le nom).
3. **Settings → Actions → General → Workflow permissions** → cocher **Read and write**.
4. Onglet **Actions** → *veille-emploi* → **Run workflow** (test manuel).
5. **Settings → Pages** → *Deploy from a branch* → branche `main`, dossier `/docs` → Save.
6. La page est en ligne : `https://<pseudo>.github.io/<dépôt>/` → à mettre en favori.

## 2. Notification sur son téléphone (recommandé)

C'est ce qui rend l'outil réellement utile : sans notification, il faut penser à consulter
la page.

1. Elle installe l'appli **ntfy** (gratuite, App Store / Play Store). Aucun compte à créer.
2. Choisir un **nom de canal long et non devinable**, par ex. `veille-biblio-k9x3mq7p`.
   ⚠️ Toute personne connaissant ce nom peut lire les notifications : ne pas prendre
   `veille-emploi` ou son prénom.
3. Dans l'appli : **+** → coller ce nom → s'abonner.
4. Sur GitHub : **Settings → Secrets and variables → Actions → New repository secret**
   → nom `NTFY_TOPIC`, valeur = le même nom de canal.
5. Pour que le clic sur la notification ouvre le rapport : même écran, onglet **Variables**
   → `REPORT_URL` = l'URL de la page GitHub Pages.
6. *(Optionnel)* secret `NTFY_EMAIL` = une adresse mail → la notification y est envoyée aussi.

Elle recevra **une seule notification récapitulative** par exécution (jamais une par offre),
et uniquement pour les offres ciblées — jamais pour le tier « à survoler ».

## 3. Temps de trajet réels (optionnel)

Sans clé, la colonne *Trajet* affiche un lien qui ouvre l'itinéraire pré-rempli depuis
Montgeron. Fonctionnel, mais non triable.

Pour afficher la durée en clair (« 47 min ») :

1. Créer un compte gratuit sur **PRIM** (Île-de-France Mobilités) : https://prim.iledefrance-mobilites.fr
2. Dans son espace, générer une **clé d'API** (une longue chaîne de caractères).
3. GitHub → **Settings → Secrets → New repository secret** → nom `PRIM_TOKEN`, valeur = la clé.

Le calcul est mis en cache par commune (`transit_cache.json`) : chaque ville n'est
interrogée qu'une fois.

⚠️ Ce chemin n'a **pas pu être testé** faute de clé. S'il échoue, le script retombe
silencieusement sur le lien d'itinéraire — rien ne casse.

## 4. À savoir

- **Retards de planification** : GitHub décale souvent les tâches de 5–15 min. « Fraîche à
  la demi-heure près » est la garantie honnête.
- **Dépôt inactif 60 jours** → GitHub suspend le planning et envoie un mail ; un clic le relance.
- **≈ devant une date** = la source ne date pas ses offres, c'est la date de première détection.
- **Panne d'une source** : le script continue avec les autres, et la section *État des sources*
  affiche le coupable en rouge. Activer les mails d'échec GitHub :
  profil → Settings → Notifications → Actions → *Failed workflows only*.
- **3 sites (Ivry, Neuilly-Plaisance, CD Essonne)** n'exposent leurs offres qu'après exécution
  du JavaScript : le workflow lance Chromium pour les lire. Sans Playwright, le script
  les ignore et continue.
- **Réglages** en tête de `veille_v2.py` : `GRADES`, `KW_RE` (mots-clés métier),
  `EXCL_RE` (exclusions), `HUB_URL` (ville / rayon).
