# Access Control System - Documentation

## Vue d'ensemble

Le système de contrôle d'accès Blueprint permet de restreindre l'accès aux fichiers et dossiers pour chaque agent, évitant ainsi les conflits entre tâches concurrentes et renforçant la sécurité du pipeline.

## Principes fondamentaux

### 1. Double niveau de configuration

Les restrictions d'accès peuvent être définies à **deux niveaux** :

1. **Templates d'agents** (`~/.claude/agents/*.md`) : Restrictions permanentes pour un type d'agent
2. **Specs de tâches** (`specs/TASK-*.json`) : Restrictions spécifiques à une tâche

Les deux configurations sont **fusionnées** (union), avec les exclusions toujours prioritaires.

### 2. Règle de priorité

**EXCLUSION > INCLUSION** : Si un chemin est à la fois dans `allow` et `exclude`, il sera **toujours refusé**.

### 3. Détection automatique des conflits

Le système détecte automatiquement les chevauchements d'accès entre tâches actives et peut générer des exclusions automatiques.

---

## Configuration dans les Templates d'Agents

### Format YAML (frontmatter)

Les templates d'agents (`~/.claude/agents/*.md`) supportent désormais un champ `access_control` dans le frontmatter YAML :

```yaml
---
name: senior-engineer
description: Senior software engineer specialized in backend development
model: opus
color: blue

# Access control - restrictions permanentes pour ce type d'agent
access_control:
  allow:
    - "src/backend/"
    - "src/api/"
    - "tests/backend/"
  exclude:
    - "src/backend/admin/"
    - "src/config/secrets.js"
    - "**/.env"
---

# Agent instructions here...
```

### Exemples par rôle

#### Agent Coder (Backend)
```yaml
access_control:
  allow:
    - "src/backend/**/*.js"
    - "src/api/**/*.js"
    - "tests/backend/"
  exclude:
    - "src/backend/migrations/"  # Réservé à un agent spécialisé
    - "**/*.env"
```

#### Agent Security Auditor
```yaml
access_control:
  allow:
    - "src/auth/"
    - "src/middleware/security/"
    - "tests/security/"
  exclude:
    - "src/auth/oauth/providers.config.js"  # Config sensible
```

#### Agent Test Engineer
```yaml
access_control:
  allow:
    - "tests/**/*.test.js"
    - "tests/**/*.spec.js"
  exclude:
    - "tests/e2e/"  # Réservé pour autre agent
```

---

## Configuration dans les Specs de Tâches

### Format JSON

Ajouter le champ `access` dans vos specs de tâches (`specs/TASK-*.json`) :

```json
{
  "task_id": "TASK-101",
  "domain": "Authentication",
  "title": "Implémenter JWT authentication",
  "description": "...",
  "requirements": [...],
  "acceptance_criteria": [...],

  "files_scope": [
    "src/auth/",
    "src/middleware/auth.js",
    "tests/auth/"
  ],

  "access": {
    "allow": [
      "src/auth/",
      "src/config/jwt.js",
      "tests/auth/**/*.test.js"
    ],
    "exclude": [
      "src/auth/admin/",
      "src/auth/legacy/"
    ]
  }
}
```

### Différence entre `files_scope` et `access`

| Champ | But | Enforcement |
|-------|-----|-------------|
| `files_scope` | Guideline pour l'agent (suggestion) | Non enforced (prompt only) |
| `access.allow` | Restriction stricte (whitelist) | **Enforced** at runtime |
| `access.exclude` | Interdiction absolue (blacklist) | **Enforced** at runtime |

**Recommandation** : Utilisez les deux pour clarté maximale.

---

## Patterns de chemins supportés

Le système supporte les patterns **glob** pour une flexibilité maximale :

### Patterns simples

```yaml
allow:
  - "src/auth/"                    # Dossier et tout son contenu
  - "src/config/jwt.js"            # Fichier spécifique
```

### Patterns avec wildcards

```yaml
allow:
  - "src/api/*.js"                 # Tous les .js dans api/ (pas récursif)
  - "src/api/**/*.js"              # Tous les .js dans api/ (récursif)
  - "tests/**/*.test.js"           # Tous les fichiers de test
  - "src/**/utils.js"              # utils.js à n'importe quel niveau
```

### Exclusions sensibles (par défaut)

Le système exclut automatiquement certains chemins sensibles (configurables dans `pipeline_config.yaml`) :

```yaml
sensitive_paths:
  - "**/.env"
  - "**/.env.*"
  - "**/secrets.json"
  - "**/credentials.json"
  - "**/id_rsa"
  - "**/id_rsa.pub"
  - "**/.git/config"
```

---

## Modes d'enforcement

Configurez le comportement en cas de violation dans `config/pipeline_config.yaml` :

```yaml
security:
  access_control:
    enabled: true
    mode: "block"  # Options: "block", "log", "ask"
```

### Modes disponibles

| Mode | Comportement | Usage |
|------|--------------|-------|
| `block` | **Erreur** et arrêt immédiat | Production, sécurité maximale |
| `log` | **Warning** mais continue | Development, debugging |
| `ask` | Demande **validation humaine** | Review manuel requis |

### Configuration détaillée

```yaml
security:
  access_control:
    enabled: true
    mode: "block"

    # Logging
    log_all_attempts: true           # Logger même les accès autorisés
    log_file: "logs/access_violations.log"

    # Détection de conflits
    detect_conflicts: true            # Détecter chevauchements entre tâches
    auto_exclude_conflicts: true      # Générer auto-exclusions
    conflict_severity_threshold: "medium"

    # Validation humaine (si mode = "ask")
    ask_timeout: 300                  # 5 minutes
    ask_default_deny: true            # Timeout = deny par défaut

    # Phases où appliquer le contrôle
    enforce_in_phases:
      - "phase3"  # Coder agents
      - "phase4"  # QA agents
```

---

## Détection automatique des conflits

### Comment ça fonctionne

Quand une nouvelle tâche est créée, le système :

1. **Scanne** toutes les tâches actives (statut ≠ merged/failed)
2. **Compare** les `access.allow` lists
3. **Détecte** les chevauchements de chemins
4. **Génère** automatiquement des exclusions si `auto_exclude_conflicts: true`

### Exemple de conflit

```json
// TASK-101 (active)
"access": {
  "allow": ["src/auth/", "src/config/"]
}

// TASK-102 (nouvelle)
"access": {
  "allow": ["src/auth/jwt/", "src/api/"]  // Conflit détecté !
}
```

**Résultat** : Le système ajoute automatiquement `src/auth/` aux exclusions de TASK-102.

### Logs de conflits

Les conflits détectés sont loggés :

```
[WARNING] Conflict detected between TASK-102 and TASK-101:
  - Overlapping path: src/auth/ ↔ src/auth/jwt/
  - Severity: high
  - Action: Auto-excluded src/auth/ from TASK-102
```

---

## Exemples pratiques

### Cas 1 : Séparer Frontend et Backend

**Agent Backend (template)**
```yaml
access_control:
  allow:
    - "src/backend/"
    - "src/api/"
  exclude:
    - "src/frontend/"
```

**Agent Frontend (template)**
```yaml
access_control:
  allow:
    - "src/frontend/"
    - "src/components/"
  exclude:
    - "src/backend/"
    - "src/api/"
```

### Cas 2 : Tâches parallèles sans conflits

**TASK-101 : Authentication**
```json
"access": {
  "allow": ["src/auth/", "tests/auth/"],
  "exclude": ["src/payment/"]
}
```

**TASK-102 : Payment (simultané)**
```json
"access": {
  "allow": ["src/payment/", "tests/payment/"],
  "exclude": ["src/auth/"]
}
```

➡️ Aucun conflit, les deux peuvent s'exécuter en parallèle.

### Cas 3 : Exclusion d'un sous-dossier

**TASK-201 : General API work**
```json
"access": {
  "allow": ["src/api/"],
  "exclude": [
    "src/api/admin/",      // Réservé
    "src/api/internal/"    // Sensible
  ]
}
```

➡️ L'agent peut accéder à `src/api/*` SAUF `admin/` et `internal/`.

---

## Monitoring et Logs

### Base de données

Toutes les tentatives d'accès sont enregistrées dans la table `access_violations` :

```sql
SELECT
  task_id,
  file_path,
  operation,
  decision,
  reason,
  human_approved
FROM access_violations
WHERE decision != 'allowed'
ORDER BY created_at DESC;
```

### Statistiques

Obtenir des stats via la base de données :

```python
import asyncio
from orchestrator.db import Database

async def get_stats():
    db = Database()
    await db.initialize()

    stats = await db.get_access_stats()
    print(stats)
    # {
    #   'total_attempts': 145,
    #   'by_decision': {
    #     'allowed': 130,
    #     'denied_excluded': 12,
    #     'denied_not_in_allow': 3
    #   },
    #   'human_approved_denials': 2
    # }

asyncio.run(get_stats())
```

### Vérification dans Phase QA

Le **VerifierAgent** (Phase 4) vérifie automatiquement :

✅ Aucune violation d'accès n'a eu lieu
✅ Tous les fichiers modifiés sont dans `allow`
✅ Aucun fichier `exclude` n'a été touché

En cas de violation détectée, la tâche est **rejetée** (ValidationStatus.NO_GO).

---

## Validation humaine (mode ASK)

### Fonctionnement

Quand `mode: "ask"` :

1. Violation détectée ➡️ Exécution **suspendue**
2. Notification envoyée (console/log)
3. Attente de validation humaine (timeout configurable)
4. Si timeout atteint sans réponse :
   - `ask_default_deny: true` ➡️ **Refusé**
   - `ask_default_deny: false` ➡️ **Autorisé**

### Approuver une violation

Via l'API base de données :

```python
# Récupérer les violations en attente
violations = await db.get_access_violations_for_task(
    task_id="TASK-101",
    denied_only=True
)

# Approuver une violation spécifique
await db.approve_access_violation(violation_id=42)
```

---

## Migration depuis l'ancien système

Si vous aviez seulement `files_scope` avant :

### Avant (sans access control)
```json
{
  "task_id": "TASK-101",
  "files_scope": [
    "src/auth/",
    "tests/auth/"
  ]
}
```

### Après (avec access control)
```json
{
  "task_id": "TASK-101",
  "files_scope": [
    "src/auth/",
    "tests/auth/"
  ],
  "access": {
    "allow": [
      "src/auth/",
      "tests/auth/"
    ],
    "exclude": [
      "src/payment/",  // Autre agent
      "**/.env"
    ]
  }
}
```

**Note** : `files_scope` reste utile pour la documentation, mais `access` est ce qui est **réellement enforced**.

---

## Troubleshooting

### Problème : Violation non détectée

**Vérifiez** :
- ✅ `security.access_control.enabled: true` dans config
- ✅ Phase d'enforcement dans `enforce_in_phases`
- ✅ Mode n'est pas `log` (qui ne bloque pas)

### Problème : Trop restrictif

**Solutions** :
- Passer temporairement en mode `log` pour debugging
- Ajouter des patterns glob plus larges dans `allow`
- Vérifier les `default_restrictions` dans la config

### Problème : Conflits non détectés

**Vérifiez** :
- ✅ `detect_conflicts: true`
- ✅ Les deux tâches sont bien au statut `active`
- ✅ Patterns utilisent des chemins compatibles

---

## Best Practices

1. **Commencez large, affinez ensuite**
   - Démarrez avec `mode: "log"` pour observer
   - Analysez les logs de violations
   - Passez à `mode: "block"` une fois stable

2. **Utilisez des patterns cohérents**
   - Préférez `src/auth/**/*.js` plutôt que `src/auth/`
   - Soyez explicite : `tests/**/*.test.js`

3. **Documentez les exclusions**
   - Ajoutez des commentaires dans les specs JSON (si format le permet)
   - Maintenez ce fichier à jour avec vos conventions

4. **Templates = Conventions, Specs = Spécifique**
   - Templates : restrictions de rôle générales
   - Specs : restrictions de tâche précises

5. **Monitorez régulièrement**
   ```bash
   # Voir les violations récentes
   sqlite3 pipeline.db "SELECT * FROM access_violations WHERE decision != 'allowed' ORDER BY created_at DESC LIMIT 20;"
   ```

---

## API Reference

### AccessControlManager

```python
from orchestrator.utils.access_control import AccessControlManager, AccessMode

# Initialiser
manager = AccessControlManager(
    access_config={
        'allow': ['src/auth/', 'tests/auth/'],
        'exclude': ['src/auth/admin/']
    },
    worktree_path=Path('/path/to/worktree'),
    mode=AccessMode.BLOCK
)

# Valider un fichier
decision, reason = manager.validate_file_access(
    file_path='src/auth/jwt.js',
    operation='write'
)

# Détecter les conflits
conflicts = manager.detect_conflicts(db, current_task_id='TASK-101')
```

### Database Operations

```python
# Logger une violation
await db.log_access_violation(
    task_id='TASK-101',
    file_path='src/auth/admin/users.js',
    operation='write',
    decision='denied_excluded',
    reason='Path in exclusion list',
    agent_id='Agent-Coder-TASK-101'
)

# Récupérer les violations
violations = await db.get_access_violations_for_task('TASK-101', denied_only=True)

# Statistiques
stats = await db.get_access_stats()
```

---

## Changelog

### v1.1.0 (2025-11-02)
- ✨ Ajout du système de contrôle d'accès complet
- ✨ Support des patterns glob
- ✨ Détection automatique des conflits
- ✨ Trois modes d'enforcement (block/log/ask)
- ✨ Validation dans Phase QA
- ✨ Logging en base de données

---

## Support

Pour toute question ou problème :
1. Consultez les logs : `logs/access_violations.log`
2. Vérifiez la base de données : `pipeline.db` table `access_violations`
3. Testez en mode `log` pour diagnostiquer

---

**Documentation maintenue par : Blueprint Pipeline Team**
**Dernière mise à jour : 2 novembre 2025**
