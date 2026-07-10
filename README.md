# Veille emploi — page auto-actualisée

Une page web qui se met à jour toute seule (toutes les ~20 min en journée) avec :
- **Tier 1** : offres ciblées (grade 031302 + métiers du livre/culture/langues), triées, dédupliquées, ⚡ = vues en direct sur le site de la mairie avant le hub
- **Tier 2** : offres non étiquetées des mairies suivies (filet de sécurité)
- **Couverture** : collectivités visibles uniquement via le hub → celles où un
  passage manuel sur leur site peut encore battre l'outil

## Mise en place (une fois, ~10 minutes)

1. Créer un compte GitHub (gratuit) si besoin, puis un **nouveau dépôt** :
   `New repository` → nom `veille-emploi` → **Public** (obligatoire pour
   GitHub Pages gratuit) → Create.

2. Y déposer les 2 fichiers de ce dossier en respectant les chemins :
   - `veille_deux_tiers.py` (à la racine)
   - `.github/workflows/veille.yml` (créer les dossiers via
     `Add file → Create new file`, taper le chemin complet dans le nom)

3. Onglet **Actions** du dépôt → activer les workflows si demandé →
   ouvrir `veille-emploi` → bouton **Run workflow** (test manuel).
   Attendre ~1 min : un dossier `docs/` doit apparaître dans le dépôt.

4. **Settings → Pages** → Source : `Deploy from a branch` →
   Branch : `main`, dossier `/docs` → Save.

5. La page est en ligne (l'URL s'affiche dans Settings → Pages) :
   `https://<votre-pseudo>.github.io/veille-emploi/`
   → à mettre en favori sur son téléphone. C'est tout.

## À savoir

- **Horaires** : le planning GitHub n'est pas exact à la minute (retards de
  5-15 min fréquents aux heures pleines). L'ordre de grandeur reste "fraîche
  au quart d'heure près", largement suffisant.
- **Dépôt inactif 60 jours** → GitHub suspend le planning et envoie un mail ;
  un clic sur "Re-enable" le relance. N'importe quel commit remet le compteur
  à zéro.
- **🆕** = nouveau depuis la dernière exécution du robot (pas depuis sa
  dernière visite à elle) — avec un passage toutes les 20 min, c'est
  quasiment équivalent.
- **Panne d'une source** : le script continue avec les autres et le note dans
  les logs Actions ; la page reste servie dans sa dernière version.
- **Mots-clés / villes** : tout se règle en tête de `veille_deux_tiers.py`
  (`KW_RE`, `PP_TOWNS`, `HUB_URL`). Modifier le fichier sur GitHub suffit,
  le prochain passage prend le changement.

## Notifications (optionnel, plus tard)

Le script sait déjà quelles offres sont nouvelles. Pour recevoir une
notification sur téléphone, brancher https://ntfy.sh (gratuit, sans compte)
dans la fonction `notify` — une ligne de `requests.post`.
