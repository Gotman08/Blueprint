# Generative Agent Pipeline

Une chaîne d'assemblage (pipeline) entièrement automatisée où des agents "Générateurs" **créent** des agents "Ouvriers" spécialisés pour paralléliser chaque étape du cycle de vie du développement.

## Vue d'Ensemble

Ce système transforme un besoin métier en code production via **5 phases automatisées** :

```
Besoin Métier → Domaines → Specs → Code → Validation → Intégration
    Phase 0      Phase 1   Phase 2  Phase 3   Phase 4      Phase 5
```

### Architecture Générative

Le cœur de ce système est son **architecture générative** : au lieu d'avoir des agents fixes, le pipeline **crée dynamiquement** des agents spécialisés pour chaque tâche.

```
Master Analyst (Phase 0)
    ↓
    Crée → Analyste(Authentification) + Analyste(Paiements) + Analyste(Database)
                                       ↓
                            Phase 1 : Chaque analyste crée des specs
                                       ↓
                            Phase 2 : Pour chaque spec, création de :
                                         - Codeur-TASK-101
                                         - Vérificateur-TASK-101
                                         - Testeur-TASK-101
```

## Les 6 Phases du Pipeline

### Phase 0 : L'Analyste Maître (Le Générateur)

**Rôle** : Méta-analyse du besoin métier

**Input** : Un besoin métier global (ex: "Construire un système de réservation")

**Action** :
- N'analyse PAS le besoin directement
- Analyse **comment le besoin doit être analysé**
- Identifie les domaines nécessaires

**Output** : Liste de domaines avec leurs templates d'agents

**Exemple** :
```json
[
  {
    "name": "Authentication",
    "template": "security-auditor",
    "priority": "high",
    "complexity": "moderate"
  },
  {
    "name": "Payments",
    "template": "senior-engineer",
    "priority": "critical",
    "complexity": "very-complex"
  }
]
```

### Phase 1 : Les Analystes Spécialisés (Génération de Specs)

**Rôle** : Création de spécifications techniques atomiques

**Input** : Domaines identifiés par Phase 0

**Action** :
- Chaque analyste spécialisé travaille **en parallèle**
- Crée des specs techniques détaillées (le "contrat")
- Sauvegarde dans `specs/TASK-XXX.json`

**Output** : Fichiers de spécification JSON validés par schéma

**Exemple de Spec** :
```json
{
  "task_id": "TASK-101",
  "domain": "Authentication",
  "title": "Implémenter JWT token generation",
  "requirements": [
    "Utiliser la librairie jsonwebtoken",
    "Token expiry: 24 heures",
    "Inclure user ID et roles"
  ],
  "acceptance_criteria": [
    "Test: utilisateur admin reçoit un token valide",
    "Test: route protégée échoue sans token"
  ],
  "files_scope": ["src/auth/jwt-service.js"],
  "priority": "high"
}
```

### Phase 2 : Le Dispatcher (Création d'Équipes)

**Rôle** : Orchestration et création d'environnements isolés

**Input** : Nouvelles specs dans `specs/`

**Action** (pour **chaque** spec) :
1. **Crée un worktree Git** : `git worktree add -b feature/TASK-XXX`
2. **Crée une équipe de 3 agents dédiés** :
   - `Codeur-TASK-XXX`
   - `Vérificateur-TASK-XXX`
   - `Testeur-TASK-XXX`
3. **Injecte le contexte** : Donne la spec à tous les agents

**Output** : Environnements isolés + équipes prêtes

### Phase 3 : Les Agents Codeurs (Production)

**Rôle** : Implémentation du code

**Input** : Spec `TASK-XXX.json` + worktree dédié

**Action** :
- Travaille **exclusivement** dans son worktree
- Code pour répondre **parfaitement** à la spec
- Commit et push sur `feature/TASK-XXX`

**Output** : Code implémenté + branche poussée

**Parallélisation** : Jusqu'à `max_parallel_coders` agents simultanés

### Phase 4 : La Validation (Contrôle Qualité)

**Rôle** : Double validation parallèle

#### A. Vérificateur (Validation Logique)

**Question** : "Le code respecte-t-il la spec ?"

**Vérifie** :
- Tous les requirements implémentés
- Tous les critères d'acceptation respectés
- Seulement les fichiers du `files_scope` modifiés

**Output** : `GO Logique` ou `NO-GO Logique`

#### B. Testeur (Validation Technique)

**Question** : "Le code fonctionne-t-il techniquement ?"

**Exécute** :
- Tests unitaires
- Tests d'intégration
- Linting
- Build (si applicable)

**Output** :
- `GO Technique` : Tous les tests passent
- `NO-GO Technique` : Crée automatiquement un GitHub Issue

**Parallélisation** : Vérificateur ET Testeur tournent **en parallèle**

### Phase 5 : Le Mergeur (Intégration)

**Rôle** : Intégration sécurisée dans main

**Input** : Tâches avec `GO Logique` **ET** `GO Technique`

**Action** (une tâche à la fois pour protéger main) :
1. **Validation Humaine** (optionnel mais recommandé)
2. `git checkout main && git pull`
3. `git merge feature/TASK-XXX`
4. **Résolution des conflits** (auto ou manuelle)
5. `git push`
6. **Nettoyage** : Suppression worktree + branche

**Sécurité** : Un seul merge à la fois, point de validation obligatoire

## Installation

### Prérequis

- Python 3.9+
- Git 2.20+
- WSL (pour accéder aux agents templates)
- Accès à `~/.claude/agents/` dans WSL

### Installation des Dépendances

```bash
# Depuis le répertoire du projet
pip install -r requirements.txt
```

### Initialisation

```bash
# Initialiser la base de données et vérifier Git
python orchestrator/main.py init
```

## Configuration

Toute la configuration se trouve dans `config/pipeline_config.yaml`.

### Configuration Clé

```yaml
# Chemins
agents:
  templates_path: "~/.claude/agents"  # Templates d'agents en WSL

git:
  base_branch: "main"
  worktrees_dir: ".worktrees"

# Validation humaine
phase5:
  require_human_validation: true  # IMPORTANT : Validation avant merge
  auto_merge: false

# Parallélisation
phase1:
  max_parallel_agents: 5  # Analystes en parallèle
phase3:
  max_parallel_coders: 3  # Codeurs en parallèle
phase4:
  parallel_execution: true  # Verifier + Tester en parallèle
```

## Utilisation

### Lancer le Pipeline Complet

```bash
python orchestrator/main.py start "Construire un système de réservation d'hôtel"
```

### Lancer une Phase Spécifique

```bash
# Phase 0 : Analyse maître
python orchestrator/main.py run-phase 0 --requirement "Système de paiement"

# Phase 2 : Dispatcher
python orchestrator/main.py run-phase 2

# Phase 5 : Merger
python orchestrator/main.py run-phase 5
```

### Afficher le Statut

```bash
python orchestrator/main.py status
```

### Réinitialiser

```bash
python orchestrator/main.py reset
```

## Structure du Projet

```
.
├── config/
│   ├── pipeline_config.yaml      # Configuration globale
│   └── spec_schema.json          # Schéma JSON des specs
├── specs/                         # Specs générées (TASK-XXX.json)
├── .worktrees/                    # Git worktrees isolés
├── orchestrator/
│   ├── main.py                    # Point d'entrée CLI
│   ├── db.py                      # Gestion SQLite
│   ├── agent_factory.py           # Création d'agents depuis templates
│   ├── phases/
│   │   ├── phase0_master.py       # Analyste Maître
│   │   ├── phase1_specialists.py  # Analystes Spécialisés
│   │   ├── phase2_dispatcher.py   # Dispatcher
│   │   ├── phase3_coder.py        # Agents Codeurs
│   │   ├── phase4_qa.py           # Vérificateurs + Testeurs
│   │   └── phase5_merger.py       # Agent Mergeur
│   └── utils/
│       ├── git_helper.py          # Gestion Git/worktrees
│       └── logger.py              # Logging centralisé
├── pipeline.db                    # Base de données SQLite
└── requirements.txt               # Dépendances Python
```

## Base de Données

Le pipeline utilise SQLite pour tracker l'état :

### Tables

- **tasks** : Toutes les tâches (specs → code → validation → merge)
- **agents** : Tous les agents créés (instance, rôle, statut)
- **validations** : Résultats des validations (logic + tech)

### États des Tâches

```
SPEC_READY → DISPATCHED → CODE_DONE → VALIDATION_PASSED → MERGED
                               ↓
                        VALIDATION_FAILED
```

## Format de Spécification

Chaque tâche est définie par un fichier JSON validé par `config/spec_schema.json` :

```json
{
  "task_id": "TASK-101",
  "created_by": "Agent(Analyste-Authentication)",
  "domain": "Authentication",
  "title": "Implémenter JWT token generation",
  "description": "Créer un service qui génère des JWT tokens...",
  "requirements": [
    "Utiliser la librairie jsonwebtoken",
    "Token expiry: 24 heures"
  ],
  "files_scope": [
    "src/auth/jwt-service.js",
    "tests/auth/jwt.test.js"
  ],
  "acceptance_criteria": [
    "Un test prouve qu'un token est généré",
    "Un test prouve que le token contient les bonnes données"
  ],
  "dependencies": [],
  "priority": "high",
  "estimated_complexity": "moderate",
  "tags": ["security", "authentication"]
}
```

## Agents Templates

Le système réutilise les **18 agents existants** dans `~/.claude/agents/` :

### Mapping Rôle → Template

```yaml
role_mapping:
  coder: "senior-engineer"
  verifier: "code-reviewer"
  tester: "test-engineer"
  analyst: "system-architect"
  security: "security-auditor"
```

### Injection de Contexte

Les agents ne sont pas invoqués directement. L'`AgentFactory` :
1. Lit le template depuis WSL
2. Injecte le contexte de la tâche (spec, worktree, branche)
3. Génère un prompt complet spécialisé

## Sécurité et Bonnes Pratiques

### Validation Humaine

**CRITIQUE** : Toujours activer la validation humaine avant merge :

```yaml
phase5:
  require_human_validation: true
```

### Isolation Git

Chaque tâche travaille dans un **worktree isolé** :
- Pas de conflit entre agents
- Branche dédiée par tâche
- Cleanup automatique après merge

### Gestion des Conflits

```yaml
phase5:
  auto_resolve_conflicts: false  # Recommandé
  conflict_strategy: "ours"      # Si auto activé
```

### Dépendances

Le dispatcher vérifie automatiquement les dépendances :

```json
{
  "task_id": "TASK-201",
  "dependencies": ["TASK-101", "TASK-150"]
}
```

TASK-201 ne sera dispatché que si TASK-101 ET TASK-150 sont MERGED.

## Monitoring et Logs

### Logs

Tous les logs sont dans `logs/pipeline.log` (configurable) :

```bash
tail -f logs/pipeline.log
```

### Statistiques

```bash
python orchestrator/main.py status
```

Affiche :
- Nombre de tâches par statut
- Nombre d'agents créés
- Taux de succès des validations
- etc.

## Développement et Extension

### Ajouter un Nouveau Template

1. Créer le template dans `~/.claude/agents/nouveau-agent.md`
2. Ajouter dans `config/pipeline_config.yaml` :

```yaml
agents:
  role_mapping:
    nouveau_role: "nouveau-agent"
```

### Ajouter une Phase

1. Créer `orchestrator/phases/phase6_custom.py`
2. Implémenter `async def run_phase6(...)`
3. Ajouter dans `main.py`

### Tests

```bash
# TODO: Implémenter les tests unitaires
pytest tests/
```

## Limitations Actuelles

### Simulation vs Production

**IMPORTANT** : Cette version simule les appels IA.

Dans chaque phase, les fonctions `_simulate_*()` doivent être remplacées par de vrais appels à des modèles AI (ex: Claude via API Anthropic).

### Exemple de Remplacement

```python
# Actuel (simulation)
async def analyze(self):
    tasks = self._simulate_analysis()

# Production
async def analyze(self):
    prompt = self._create_prompt()
    response = await anthropic_api.call(prompt)
    tasks = self._parse_response(response)
```

## Corrections de Sécurité (v1.1)

Le système a été renforcé avec des corrections de sécurité critiques pour le rendre production-ready.

### 🔒 Boucle de Correction Automatique (Retry Loop)

**Problème résolu** : Les tâches qui échouaient en validation restaient bloquées indéfiniment.

**Solution** : Implémentation d'une boucle de retry avec feedback injecté :

```
VALIDATION_FAILED → Retry Handler → Feedback injecté → CODE_DONE (retry)
                                            ↓
                                  Max 3 tentatives → FAILED (permanent)
```

**Fonctionnement** :
1. Phase 4 détecte un échec de validation
2. Le `retry_handler` récupère le feedback détaillé (logic + tech)
3. Le feedback est injecté dans le prompt du codeur (Phase 3)
4. Le codeur corrige les erreurs spécifiques
5. Limite de 3 tentatives pour éviter les boucles infinies

**Configuration** :
```yaml
error_handling:
  enable_retry_loop: true
  max_retries: 3
  inject_feedback: true
```

**Exemple de feedback injecté** :
```
=== RETRY ATTEMPT (2/3) ===
Previous issues: 2

Logic validation failed: 1 requirement not met
  - Missing error handling for null values

Technical validation failed: 1 test failed
  - Test 'auth_without_token' expected 401, got 500

Corrections applied:
  1. Added null checks
  2. Fixed error response status code
```

### 🛡️ Sécurisation de la Gestion des Conflits

**Problème résolu** : Le repo Git pouvait rester dans un état de merge incomplet.

**Solution** : `git merge --abort` automatique en cas de conflit :

```python
# AVANT (DANGEREUX)
try:
    git.merge(branch)
except ConflictError:
    return False  # ⚠️ Repo reste en état de merge

# APRÈS (SÉCURISÉ)
try:
    git.merge(branch)
except ConflictError:
    git.merge('--abort')  # ✅ Repo nettoyé
    create_conflict_report(...)
    return False
```

**Fonctionnement** :
1. Phase 5 tente le merge
2. En cas de conflit : `git merge --abort` immédiat
3. Statut de la tâche → `MERGE_CONFLICT`
4. Création d'un rapport de conflit détaillé dans `conflict_reports/`
5. Le repo `main` reste propre

**Rapport de conflit généré** :
```json
{
  "task_id": "TASK-101",
  "branch_name": "feature/TASK-101",
  "conflicting_files": ["src/auth.js", "tests/auth.test.js"],
  "resolution_instructions": [
    "1. git checkout feature/TASK-101",
    "2. git rebase main",
    "3. Resolve conflicts manually",
    "..."
  ]
}
```

### ❌ Suppression de l'Auto-Résolution de Conflits

**Risque identifié** : L'option `auto_resolve_conflicts` pouvait écraser du code important.

**Action** : Suppression complète de cette fonctionnalité :

- ❌ Supprimé : `auto_resolve_conflicts: false`
- ❌ Supprimé : `conflict_strategy: "ours"`
- ❌ Supprimé : Fonction `_auto_resolve_conflicts()`

**Nouveau comportement** : Tous les conflits requièrent **intervention manuelle**.

### 📊 Nouveaux Statuts de Tâches

Ajout d'un nouveau statut pour tracker les conflits :

```python
class TaskStatus(Enum):
    # ... statuts existants
    MERGE_CONFLICT = "merge_conflict"  # Nouveau
```

**Workflow mis à jour** :
```
VALIDATION_PASSED → Phase 5 → Merge
                        ↓
                   Conflit détecté
                        ↓
                git merge --abort
                        ↓
              MERGE_CONFLICT + Rapport
```

### 🔢 Tracking des Retries

Nouvelles colonnes ajoutées à la base de données :

```sql
ALTER TABLE tasks ADD COLUMN retry_count INTEGER DEFAULT 0;
ALTER TABLE tasks ADD COLUMN last_feedback TEXT;
```

**Nouvelles méthodes** :
- `db.increment_retry(task_id, feedback)`
- `db.get_retry_count(task_id)`
- `db.get_last_feedback(task_id)`

### 📁 Nouveau Composant

**`orchestrator/phases/retry_handler.py`** : Gère la boucle de correction

**Utilisation** :
```python
# Dans le pipeline principal (après Phase 4)
retry_count = await run_retry_handler(config, logger, db)
# Les tâches échouées sont remises en queue avec feedback
```

### ⚙️ Configuration Mise à Jour

**Avant** (risqué) :
```yaml
phase5:
  auto_resolve_conflicts: false
  conflict_strategy: "ours"
```

**Après** (sécurisé) :
```yaml
phase5:
  # Auto-resolution supprimée - conflicts = toujours manuel
  create_conflict_report: true

error_handling:
  enable_retry_loop: true
  max_retries: 3
  on_validation_failure:
    action: "retry"  # Avec feedback injection
```

### ✅ Garanties de Sécurité

| Garantie | Description |
|----------|-------------|
| **Repo Propre** | `git merge --abort` empêche états de merge incomplets |
| **Auto-correction** | Boucle de retry avec feedback détaillé |
| **Limite de Retries** | Max 3 tentatives → évite boucles infinies |
| **Traçabilité** | Rapports de conflits sauvegardés |
| **Intervention Humaine** | Conflits = toujours résolution manuelle |
| **Pas de Risque d'Écrasement** | Auto-résolution complètement supprimée |

### 📝 Migration depuis v1.0

Si vous utilisez une version antérieure :

1. **Sauvegarder** votre `pipeline.db` existante
2. **Supprimer** l'ancienne base : `rm pipeline.db`
3. **Réinitialiser** : `python orchestrator/main.py init`
4. Les nouvelles colonnes `retry_count` et `last_feedback` seront créées

**Note** : Les tâches en cours seront perdues. Terminez-les avant la migration.

## Roadmap

- [ ] Intégration API Anthropic pour vrais appels IA
- [ ] GitHub Actions pour CI/CD
- [ ] Interface Web de monitoring
- [ ] Support multi-repos
- [ ] Métriques de performance
- [ ] Système de rollback automatique
- [ ] Tests unitaires complets

## Troubleshooting

### Problème : "Not a git repository"

```bash
git init
```

### Problème : "Agent template not found in WSL"

Vérifier que WSL est démarré et que `~/.claude/agents/` existe :

```bash
wsl ls ~/.claude/agents/
```

### Problème : "Database locked"

Une autre instance du pipeline tourne. Arrêter et relancer.

## Contribuer

Ce projet est un système expérimental d'architecture générative d'agents.

Les contributions sont bienvenues pour :
- Améliorer les prompts des agents
- Ajouter de nouveaux templates
- Optimiser la parallélisation
- Améliorer la gestion des conflits

## Licence

Ce projet est fourni "tel quel" à des fins éducatives et de recherche.

## Auteur

Système d'Architecture Générative d'Agents - 2025

---

**Note** : Ce README décrit le système tel que conçu. L'implémentation actuelle utilise des simulations. Pour une utilisation en production, remplacer les fonctions de simulation par de vrais appels à des modèles d'IA.
