---
description: "Nettoyer le repo Nexora : archiver les fichiers temporaires racine, normaliser l'arborescence et vérifier la cohérence de la documentation."
agent: "agent"
tools: ["search", "codebase", "terminal"]
---

# Nettoyage et normalisation du repo Nexora

Tu es un ingénieur DevEx chargé de remettre le repo Nexora au propre avant release.
L'objectif est d'éliminer le bruit, normaliser l'arborescence et s'assurer que la documentation reflète fidèlement la structure réelle du projet.

## Contexte

Le repo accumule des scripts de debug/deploy ad hoc à la racine (`_*.py`), des caches potentiellement commités, et la documentation peut référencer des fichiers déplacés ou supprimés.

## Entrées de référence

- [Documentation Architecture](../../docs/DOCUMENTATION_ARCHITECTURE.md) — hiérarchie et typologie docs
- [Docs Inventory](../../docs/docs_inventory.yaml) — inventaire formel
- [.gitignore](../../.gitignore) — patterns d'exclusion actuels

## Étapes

### 1. Inventaire des fichiers temporaires à la racine

Liste tous les fichiers `_*.py` à la racine du repo. Pour chacun, détermine :
- **Utilitaire réutilisable** → proposer un déplacement vers `scripts/` avec renommage propre
- **Script de debug jetable** → proposer la suppression ou l'archivage dans `scripts/_archive/`
- **Doublon versionné** (ex: `_deploy.py`, `_deploy2.py`, `_deploy_v2.py`) → ne garder que la version finale

Produis un tableau :

```markdown
| Fichier | Verdict | Destination | Justification |
|---------|---------|-------------|---------------|
```

**Ne supprime rien** sans confirmation explicite de l'utilisateur.

### 2. Nettoyage des artefacts de build/cache

Vérifie si des dossiers ou fichiers qui devraient être ignorés sont présents dans le repo git :

```bash
git ls-files --cached __pycache__ .mypy_cache .ruff_cache .pytest_cache .venv dist build *.pyc
```

Si des fichiers trackés sont trouvés, propose les commandes `git rm --cached` appropriées.

Vérifie que `.gitignore` couvre au minimum :
- `__pycache__/`, `*.pyc`, `*.pyo`
- `.venv/`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`
- `dist/`, `build/`, `*.egg-info/`
- `var/`, `*.sqlite3`, `*.log`
- `.env`

Propose les ajouts manquants.

### 3. Normalisation de l'arborescence

Vérifie la conformité de la structure avec les conventions Nexora :

```
src/           — code source (modules domaine)
apps/          — applications (control_plane, console, node_agent…)
tests/         — tests automatisés
scripts/       — scripts utilitaires et CI
deploy/        — scripts de déploiement et templates
docs/          — documentation canonique
blueprints/    — templates métier
ynh-package/   — packaging YunoHost
```

Signale tout fichier ou dossier hors structure attendue (hors dotfiles standards).

### 4. Cohérence de la documentation

#### 4a. Inventaire vs réalité

```bash
# Liste les .md réels dans docs/
Get-ChildItem -Path docs -Filter *.md -Name | Sort-Object
```

Compare avec `docs/docs_inventory.yaml` :
- Fichiers présents dans `docs/` mais absents de l'inventaire → **ajouter**
- Fichiers déclarés dans l'inventaire mais absents du disque → **retirer ou signaler**

#### 4b. Liens internes cassés

Recherche dans tous les fichiers `docs/*.md` les liens Markdown `[...](...)` et vérifie que chaque cible existe. Signale les liens cassés.

#### 4c. Documents obsolètes

Identifie les documents qui n'ont pas été mis à jour depuis plus de 7 jours et qui référencent des chiffres ou statuts potentiellement périmés (nombre de tests, outils MCP, statuts WS).

### 5. Vérification des gates CI de documentation

Lance les tests de cohérence documentaire :

```bash
PYTHONPATH=src python -m pytest tests/test_docs_completeness.py tests/test_docs_inventory_contract.py tests/test_docs_obsolescence_contract.py -v --tb=short
```

Signale tout échec et propose la correction.

## Format de sortie

```markdown
## Résumé
<!-- 2-3 phrases : état d'hygiène, nombre de fichiers à traiter, risques -->

## Fichiers temporaires racine
| Fichier | Verdict | Destination | Justification |
|---------|---------|-------------|---------------|

## Artefacts trackés à nettoyer
<!-- Commandes git rm --cached si nécessaire -->

## Ajouts .gitignore proposés
<!-- Patterns manquants -->

## Écarts inventaire documentation
| Fichier | Problème | Action |
|---------|----------|--------|

## Liens cassés
| Document source | Lien | Cible manquante |
|-----------------|------|-----------------|

## Gates CI documentation
| Test | Résultat | Action si échec |
|------|----------|-----------------|

## Plan d'exécution
<!-- Liste ordonnée des commandes à exécuter, en attente de validation utilisateur -->
```

**Règle absolue** : ne supprime et ne déplace aucun fichier sans validation explicite. Propose, explique, attends le feu vert.
