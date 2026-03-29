# Nexora Console — Guide opérateur

La Nexora Console est l'interface web d'exploitation de la plateforme Nexora.
Elle offre une vue unifiée sur l'ensemble des capacités métier exposées par le
control plane REST, en s'appuyant sur un design system cohérent et accessible.

## Première connexion

### Instance de test

| Paramètre | Valeur |
|-----------|--------|
| **URL console** | `https://srv2testrchon.nohost.me/nexora/console` |
| **Token opérateur** | `9s2mGHS+YDuds1tG3b1o6TqS1uwMfRjMf642M0F0q/E=` |
| **Tenant ID** | `nexora-operator` |
| **Tier** | `enterprise` |
| **Rôle** | `operator` |

### Comment se connecter

1. Ouvrir `https://srv2testrchon.nohost.me/nexora/console` dans un navigateur.
2. Un champ de saisie du token apparaît automatiquement.
3. Coller le token opérateur et valider.
4. La console charge le Dashboard avec la vue d'ensemble de la flotte.

> Le token est stocké en **sessionStorage** (effacé à la fermeture de l'onglet).
> Pour vérifier le token actif côté serveur :
> ```bash
> sudo cat /home/yunohost.app/nexora/api-token
> ```

### Vérification API depuis le terminal

```bash
TOKEN="9s2mGHS+YDuds1tG3b1o6TqS1uwMfRjMf642M0F0q/E="
BASE="https://srv2testrchon.nohost.me/nexora/console"

# Santé
curl -sk -H "Authorization: Bearer $TOKEN" $BASE/api/v1/health

# Flotte (nœuds)
curl -sk -H "Authorization: Bearer $TOKEN" $BASE/api/v1/fleet

# Tenants
curl -sk -H "Authorization: Bearer $TOKEN" $BASE/api/v1/tenants

# Contexte d'accès
curl -sk -H "Authorization: Bearer $TOKEN" $BASE/api/console/access-context
```

---



```
apps/console/
├── index.html      # Shell HTML minimal (nav + main vide)
├── styles.css      # Design system complet (tokens, composants, responsive)
├── app.js          # Contrôleur NexoraConsole + renderers par section
├── assets/         # Logo, favicon
└── README.md
```

### Principes

| Principe | Détail |
|----------|--------|
| **Modularité** | Chaque section est un renderer autonome (`loadDashboard`, `loadFleet`, …) |
| **Rendu dynamique** | Le `<main>` est vidé et re-rempli à chaque navigation — pas de sections statiques |
| **Primitives UI** | Fonctions réutilisables : `nxStatCard`, `nxGauge`, `nxAlert`, `nxTable`, `nxBadge`, `nxLoader`, `nxEmpty` |
| **Pas de framework** | Vanilla JS — aucune dépendance externe |
| **Session-only tokens** | Le jeton API est stocké en `sessionStorage`, jamais en `localStorage` |

## Sections disponibles

| Section | Route nav | Description |
|---------|-----------|-------------|
| Dashboard | `#dashboard` | Vue d'ensemble (apps, domaines, sauvegardes, santé, alertes) |
| Scores | `#scores` | Jauges de score (sécurité, PRA, santé, conformité) + priorités |
| Applications | `#apps` | Liste des apps installées |
| Services | `#services` | État des services système |
| Domaines | `#domains` | Domaines + certificats |
| Sécurité | `#security` | Posture sécurité, permissions publiques, registre des risques |
| PRA | `#pra` | Score PRA, sauvegardes, runbooks, actions (snapshot, readiness, export) |
| Fleet | `#fleet` | Nœuds de la flotte, statistiques, topologie, actions par nœud |
| Blueprints | `#blueprints` | Catalogue de blueprints applicatifs |
| Automation | `#automation` | Templates de jobs automatisés et checklists |
| Adoption | `#adoption` | Analyse de compatibilité, import d'état |
| Modes | `#modes` | Mode courant, changement, escalations, confirmations, historique, journal admin |

## Design system

### Tokens CSS

Les variables CSS sont définies dans `:root` et organisées en catégories :

- **Couleurs** : `--bg`, `--fg`, `--card`, `--accent`, `--green`/`--yellow`/`--red`/…
- **Sémantiques** : `--success-bg/bd/fg`, `--warning-bg/bd/fg`, `--danger-bg/bd/fg`, `--info-bg/bd/fg`
- **Espacement** : `--sp-xs` à `--sp-xl`
- **Typographie** : `--text-xs` à `--text-3xl`, `--font-sans`, `--font-mono`
- **Rayons** : `--radius`, `--radius-sm`, `--radius-xs`, `--radius-full`
- **Ombres** : `--shadow-sm/md/lg`
- **Z-index** : `--z-nav`, `--z-modal`, `--z-overlay`, `--z-toast`

### Composants CSS

| Composant | Classe | Usage |
|-----------|--------|-------|
| Card | `.nx-card` | Conteneur principal |
| Stat card | `.nx-stat-card` | Indicateur chiffré avec barre de couleur |
| Badge | `.nx-badge` + variante | Labels inline (success, warning, danger, info, neutral) |
| Table | `.nx-table` | Tableaux de données avec tri (aria-sort) |
| Alert | `.nx-alert` + variante | Messages contextuels |
| Modal | `.nx-modal` + `.nx-modal-overlay` | Dialogues modaux |
| Tabs | `.nx-tabs` + `.nx-tab` | Navigation par onglets |
| Button | `.nx-btn` + variante | Actions (outline, danger, sm, icon) |
| Input | `.nx-input` | Champs de saisie |
| Select | `.nx-select` | Listes déroulantes |
| Loader | `.nx-loader` | Indicateur de chargement |
| Empty | `.nx-empty` | État vide |
| Grid | `.nx-grid` + `.nx-grid-2/3/4` | Grilles responsive |
| Skip link | `.nx-skip-link` | Lien d'accessibilité |

### Primitives JS

| Fonction | Signature | Retour |
|----------|-----------|--------|
| `nxStatCard` | `(value, label, color?, subtitle?)` | HTML stat card |
| `nxGauge` | `(score, label, grade)` | HTML gauge SVG |
| `nxAlert` | `(text, level?)` | HTML alert |
| `nxTable` | `(headers, rows, opts?)` | HTML table |
| `nxLoader` | `(text?)` | HTML loader |
| `nxEmpty` | `(message)` | HTML empty state |
| `nxBadge` | `(text, variant?)` | HTML badge |
| `scoreColor` | `(score)` | CSS color string |

## Accessibilité

- **Skip link** : lien « Aller au contenu principal » visible au focus
- **Navigation** : `role="navigation"`, `aria-label`, `aria-current="page"`
- **Badges** : `role="status"`, `aria-label`
- **Main** : `role="main"`, `aria-live="polite"` pour annoncer les changements
- **Modal auth** : `role="dialog"`, `aria-modal="true"`, `aria-labelledby`
- **Focus visible** : outline de 2px `var(--accent)` sur tous les éléments interactifs
- **Clavier** : navigation complète au clavier (Tab, Enter, Espace)
- **Contraste** : thème sombre avec ratios WCAG AA respectés
- **Responsive** : grilles adaptatives, navigation scrollable sur mobile

## Sécurité de session

- Les tokens API sont stockés en `sessionStorage` (effacés à la fermeture de l'onglet)
- Migration automatique depuis `localStorage` vers `sessionStorage` au démarrage
- Affichage du prompt d'authentification sur réponse 401
- Les actions POST incluent les headers `X-Nexora-Action` et `X-Nexora-Token`
