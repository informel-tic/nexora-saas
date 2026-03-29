# blueprints — Business Templates

## Purpose

YAML-based business profile templates for common deployment scenarios. Each blueprint defines recommended apps, subdomains, security baselines, and monitoring/PRA policies for a target vertical.

## Structure

Each blueprint is a directory containing a single `profile.yaml`:

```
blueprints/
  msp/profile.yaml          # Managed Services Provider
  pme/profile.yaml          # SMB Office
  agency/profile.yaml       # Web/Creative Agency
  ecommerce/profile.yaml    # E-commerce
  collective/profile.yaml   # Association/Collective
  si-interne/profile.yaml   # Internal IT Department
  studio/profile.yaml       # Studio/Creative
  training/profile.yaml     # Training Organization
```

## Profile YAML Schema

Each `profile.yaml` contains:

| Key | Description |
|-----|-------------|
| `slug` | Unique identifier |
| `name` | Human-readable name |
| `activity` | Target vertical description |
| `description` | Detailed description |
| `profiles` | List of sub-profiles (variants) |
| `recommended_apps` | YunoHost apps to install |
| `subdomains` | Subdomain structure to create |
| `security_baseline` | Security policy defaults |
| `monitoring_baseline` | Monitoring configuration |
| `pra_baseline` | PRA (disaster recovery) policy |
| `portal` (optional) | Branding/theming configuration |

## Conventions

- One directory per blueprint vertical.
- Profile YAML is the single source of truth for each blueprint.
- Blueprints are consumed by `src/nexora_node_sdk/blueprints.py`.
