# Architecture Nexora

_Dernière mise à jour : 2026-03-29._

---

## 1. Vue d'ensemble

Nexora est une **plateforme d'orchestration professionnelle pour infrastructures YunoHost** organisée en 3 couches :

```
  Layer C — Nexora Control Plane Platform
  FastAPI REST API · Console opérateur · MCP AI Adapter
  Gouvernance · Fleet · Enrollment · Audit · Multi-tenant

  Layer B — Nexora Node Runtime & Core Shared
  Domain modules Python · Identity · Inventory · Lifecycle
  Actions locales · Compatibilité · Secret Store · Auth

  Layer A — YunoHost Runtime (non modifié)
  Applications · Domaines · Utilisateurs · Certificats TLS
  Services système · Nginx · SSO (YunoHost natif)
```

---

## 2. Frontières de Runtime (Boundaries)

### 2.1 YunoHost Runtime (Layer A)
YunoHost reste le substrat d'infrastructure et d'application :
- Gestion des apps, domaines, utilisateurs et certificats TLS.
- Firewall et services système de base.
- **Principe** : Nexora ne modifie pas le cœur de YunoHost.

### 2.2 Nexora Node (Layer B)
Exécuté sur ou près du nœud géré :
- Collecte d'inventaire local et exposition des capacités.
- Matériel d'attestation et métadonnées d'identité du nœud.
- Exécution locale d'actions approuvées (idempotence, dry-run).
- Surfaces de métriques et de santé locales.

### 2.3 Nexora Control Plane (Layer C)
Propriétaire des préoccupations au niveau de la flotte :
- Coordination de l'enrollment et politique de compatibilité.
- Orchestration du cycle de vie (lifecycle) et topologie de flotte.
- Gouvernance, audit global et agrégation multi-nœuds.
- Backend de la console et isolation multi-tenant.

### 2.4 Nexora MCP & Package
- **MCP** : Adaptation d'interface pour les outils IA uniquement (pas de logique métier parallèle).
- **Package YunoHost** : Gestion de l'installation, mise à jour, suppression et intégration système (nginx/systemd).

---

## 3. Composants officiels

| Composant | Chemin | Rôle |
|-----------|--------|------|
| nexora_saas | src/nexora_saas/ | Domain logic SaaS (orchestrator, subscription, provisioning) |
| nexora_node_sdk | src/nexora_node_sdk/ | SDK nœud partagé (state, identity, security, lifecycle) |
| yunohost_mcp | src/yunohost_mcp/ | Adaptateur MCP vers AI |
| control_plane | apps/control_plane/ | API centrale FastAPI (99 routes) |
| node_agent | apps/node_agent/ | Agent local passif — récepteur HMAC |
| console | apps/console/ | SPA opérateur JS (20 vues, vanilla JS) |
| public_site | apps/public_site/ | Page publique offres SaaS |
| deploy/ | deploy/ | Scripts bootstrap |
| ynh-package/ | ynh-package/ | Artefact distribution YunoHost |

---

## 4. Modules src/nexora_core/ (58 modules)

### Sécurité et identité
- auth/ — package TokenAuth, CSRF, SecurityHeaders, SecretStore, RateLimit, Scopes (refactoré en sous-modules)
- identity.py, identity_lifecycle.py — émission/rotation/révocation identités nœuds
- trust.py, trust_policy.py — politique de confiance inter-nœuds
- tls.py — support mTLS

### Orchestration et lifecycle
- orchestrator.py — orchestrateur central
- bootstrap.py — transitions bootstrap fresh/adopt/augment
- enrollment.py — enrollment nœuds avec attestation
- node_lifecycle.py — transitions lifecycle (drain, cordon, retire…)
- fleet.py — topologie et résumé de flotte
- modes.py — gestion des modes de déploiement

### Persistance et état
- persistence.py — abstraction backend avec JSON atomique + journal rotate
- state.py — loading/saving état flotte
- models.py — modèles Pydantic partagés
- sync.py, sync_engine.py — synchronisation état multi-nœuds
- storage.py — gestion stockage

### Actions et exécution
- node_actions.py — 9+ backends d'action réels sur nœud
- operator_actions.py, admin_actions.py — actions opérateur/admin
- privileged_actions.py — actions système privilégiées
- automation.py, hooks.py — automation et hooks lifecycle
- docker.py — compose apply, container management

### Gouvernance et observabilité
- governance.py — politiques, rapports, snapshots
- scoring.py — scoring de santé des nœuds
- sla.py — niveaux de service et alertes
- metrics.py — métriques opérationnelles
- security_audit.py — audits de posture
- adoption.py — adoption scoring / prechecks YunoHost

### Multi-tenant et SaaS
- multitenant.py — génération YAML config tenant (STUB — pas d'isolation RLS réelle, voir NEXT-25)
- quota.py — enforcement quotas storage/apps/nodes par tenant
- portal.py — portail abonné

---

## 5. API Control Plane (apps/control_plane/api.py)

Structure par domaine (fonctions `register_*_routes`) :

```
register_public_routes()          GET /api/public/offers
register_health_routes()          GET /api/health, /api/v1/health
register_inventory_routes()       GET /api/dashboard, /api/inventory/*, /api/identity
register_fleet_routes()           GET/POST /api/fleet/*, /api/fleet/nodes/*
register_catalog_routes()         GET /api/blueprints/*
register_governance_routes()      GET /api/governance/*, /api/scores/*, /api/security/*
register_modes_routes()           GET/POST /api/modes/*
register_operations_routes()      GET /api/storage/*, /api/docker/*, etc.
register_auth_routes()            POST /api/token/validate, /api/auth/login
register_subscription_routes()    GET/POST /api/plans, /api/organizations, /api/subscriptions
register_tenant_mgmt_routes()     GET/POST /api/tenants/*
register_provisioning_routes()    GET/POST /api/provisioning/*
register_console_routes()         montage static console + /api/console/access-context
```

**Middlewares actifs (ordre d'application)** :
1. TokenAuthMiddleware — authentification Bearer/X-Nexora-Token
2. CSRFProtectionMiddleware — validation Origin/Referer sur mutations
4. operator_only_surface_middleware — contrôle RBAC opérateur
5. SecurityHeadersMiddleware — injection headers sécurité

---

## 6. Node Agent (apps/node_agent/api.py)

Interface passive exposée localement (port 38121). Le node agent **ne prend aucune initiative** :
le SaaS control plane pousse toutes les fonctionnalités après enrollment.

**Modèle de sécurité** :
- Routes READ : accessibles avec token API local
- Routes MUTATION (overlay) : exigent une signature HMAC-SHA256 du SaaS (`X-Nexora-SaaS-Signature`)
- Rollback : ne requiert pas de signature SaaS (doit fonctionner pendant désinstallation)

**Persistance** : état sauvegardé dans `/var/lib/nexora/node-agent-state.json` (atomique, 0o600).
Restauration automatique au démarrage.

**Routes** :
- Read : `/health`, `/api/v1/status`, `/overlay/status`, `/overlay/services`, `/overlay/guard`, `/overlay/integrity`, `/overlay/tamper-log`, `/metrics`
- Enrollment : `POST /enroll`, `/attest`, `/revoke`, `/establish-secret`
- Overlay mutations (HMAC) : `POST /overlay/docker/*`, `/overlay/service/*`, `/overlay/nginx/*`, `/overlay/cron/*`, `/overlay/systemd/*`, `/overlay/heartbeat`

---

## 7. Architecture 3 domaines (surfaces)

Nexora expose 3 surfaces distinctes via des sous-domaines nginx, toutes proxiées vers le même backend FastAPI :

| Sous-domaine | Surface | Rôle | Auth |
|---|---|---|---|
| `saas.<domain>` | saas | Owner Console — administration complète | Passphrase |
| `www.<domain>` | public | Site public — offres et souscription | Aucune |
| `console.<domain>` | console | Console subscriber — gestion tenant | Token + tenant_id |

**Isolation** :
- nginx injecte `X-Nexora-Surface` dans chaque vhost
- `surface_isolation_middleware` (api.py) filtre les endpoints autorisés par surface
- Les sessions owner sont bloquées sur `console.*`, les tokens subscriber sont bloqués sur `saas.*`
- `www.*` n'expose que les endpoints publics (/subscribe, /api/public/*, /api/health)

**Déploiement** : `deploy/bootstrap-full-platform.sh` orchestre en 3 phases :
1. `bootstrap-node.sh` — services, venv, systemd
2. `deploy-subdomains.sh` — création sous-domaines YunoHost + nginx vhosts + SSL
3. Post-install — passphrase owner + état tenant

---

## 8. Console opérateur — Owner (apps/owner_console/)

SPA vanilla JS servie sur `saas.<domain>/owner-console/`. Authentification par passphrase propriétaire → session token en `sessionStorage`.

**Auth** : `X-Nexora-Session` + `X-Nexora-Actor-Role: owner`.

---

## 9. Console subscriber (apps/console/)

SPA vanilla JS (aucun framework) servie sur `console.<domain>/console/`.

**Fichiers** : `index.html`, `app.js` (contrôleur), `api.js` (auth + fetch), `views.js` (20 vues), `components.js` (primitives), `styles.css`.

**20 vues** : Dashboard, Scores, Apps, Services, Domaines, Sécurité, PRA, Fleet,
Blueprints, Automation, Adoption, Modes, Docker, Storage, Notifications, Hooks,
Governance, SLA-Tracking, Subscription, Provisioning.

**Auth** : token stocké en `sessionStorage`, envoyé via `Authorization: Bearer`.
Prompt automatique si pas de token. Rôle abonné masque les sections admin.

**Dashboard** : carte nœud hôte (identité, version YunoHost/Debian), session console (token, rôle, tenant), alertes, apps récentes, services.

**Sécurité** : 5 sous-panneaux temps réel (mises à jour, fail2ban, ports ouverts, audit permissions, connexions récentes).

**Subscription** : plans, organisations, souscriptions avec actions (suspendre, résilier, réactiver).

**Provisioning** : carte par nœud avec features, statut, boutons provision/déprovision, rafraîchissement.

---

## 10. MCP Adapter (src/yunohost_mcp/)

Adaptateur Model Context Protocol exposant les capacités Nexora vers des agents IA.
Consomme les mêmes services Python que l'API REST (parité garantie).

---

## 11. Flux d'enrollment (séquence)

```
Opérateur            Control Plane           Node Agent

     POST /enroll/request
     ← token enrollment

                  (envoie token au node)
                           POST /enroll/attest →
                           ← attestation OK

     POST /enroll/register
     ← node registered
```

---

## 12. Flux réseau

```
Internet / Opérateur
        ↓
   [Nginx / TLS]   YunoHost (Layer A)
        ↓
   Control Plane API :8000  (Layer C)
        ↓
         mTLS → Node Agent :8001 ... :800N  (Layer B)
        ↓
         local → YunoHost CLI / yunohost.api  (Layer A)
```

---

## 13. Persistance et Durabilité

Le control plane Nexora utilise un backend configurable via `NEXORA_PERSISTENCE_BACKEND`.

### 13.1 Garanties du backend JSON (Par défaut)
- **Atomicité** : Écritures via fichiers temporaires + `replace()`.
- **Journalisation** : `state.json.journal` écrit avant chaque commit pour reprise après crash.
- **Backups** : Rotation de 10 sauvegardes locales dans `var/backups/`.
- **Récupération** : Ordre automatique : Journal > Dernier Backup > Migration legacy.

### 13.2 Plan d'industrialisation SQL + RLS (Phase 9/10)
Migration vers PostgreSQL avec **Row Level Security** (Isolation stricte par `tenant_id`) :
1. **J0 (Shadow)** : Dual-write JSON + SQL avec rapport de cohérence.
2. **J1 (Read Switch)** : Lecture SQL activable via flag, fallback JSON autorisé.
3. **J2 (RLS Enforcement)** : Activation des politiques RLS sur toutes les tables.
4. **J3 (Full SQL)** : JSON conservé uniquement pour export/backup.

---

## 14. Conventions de Nommage

### 14.1 Capacités métier (CapIDs)
Format : `<domaine>.<verbe>` (ex: `fleet.enrollment`, `node.actions`). Lowercase snake-free.

### 14.2 Surfaces API et UI
- **REST** : `/api/` + ressources en `kebab-case` (ex: `GET /api/fleet/nodes`).
- **Node Agent** : Verbes explicites finaux (`/apply`, `/sync`, `/run`).
- **MCP** : Préfixe `ynh_` (ex: `ynh_fleet_lifecycle`).
- **Console** : Routes en `kebab-case`, Composants en `PascalCase`.
- **Payloads** : JSON en `snake_case`, booléens préfixés par `is_` ou explicites.

---

## 15. Règles architecturales

1. **Le core (nexora_core) possède les règles métier** — ni la console, ni le MCP, ni le bootstrap shell ne réimplémentent de logique métier.
2. **Le control plane est l'autorité d'orchestration** — il est la seule source de vérité pour l'état de la flotte.
3. **Le node agent exécute localement** — il est le seul à appeler directement les APIs YunoHost CLI.
4. **La persistance précède le scale** — l'état doit être durable avant toute montée en charge.
5. **La sécurité précède le go-to-market** — les dettes S1-S7 sont traquées et adressées en priorité.

---

## 16. Dettes architecturales connues

| ID | Description | Impact | Ticket |
|----|-------------|--------|--------|
| A1 | multitenant.py stub (68 LOC), pas d'isolation RLS | Critique SaaS | NEXT-25 |
| A2 | SQL désactivé par défaut | Production risk | NEXT-17 |
| A3 | ~~Endpoints hardcodés~~ — Résolu : 5 stubs sécurité remplacés par implémentations dérivées de l'état | ~~Fonctionnel~~ ✅ | NEXT-13 |
| A4 | Monolithe applicatif (control plane + console dans le même process) | Scale | futur |

---

## 17. ADRs de référence

Voir docs/adr/ pour les décisions architecturales enregistrées.
