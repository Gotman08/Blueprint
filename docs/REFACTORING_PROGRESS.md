# Refactoring Progress - Blueprint Pipeline

**Date**: 2025-11-02
**Statut**: En cours - Architecture Phase analystes/cahiers des charges

## Vue d'ensemble

Refonte majeure du pipeline Blueprint pour intégrer une phase d'analyse complète générant des "cahiers des charges" (specifications) avant l'implémentation.

### Nouvelle Architecture

```
Phase 0: Master + Analystes
    ↓ (génère cahiers + tâches)
Phase 1: Dispatcher
    ↓ (crée worktrees)
Phase 2: Spécialistes
    ↓ (implémente avec contexte des cahiers)
Phase 3: QA
    ↓ (validation)
Phase 4: Merger + Gestion conflits
```

## ✅ Complété

### 1. Infrastructure

- [x] Dossier `cahiers_charges/` créé avec structure
- [x] README et index.json dans cahiers_charges/
- [x] Dossier `orchestrator/agents/` créé

### 2. Base de Données

- [x] Nouveau statut `CAHIER_READY` ajouté à `TaskStatus`
- [x] Nouveau statut `SPECIALIST_WORKING` ajouté
- [x] Table `cahiers_charges` créée (cahier_id, domain, task_id, file_path, etc.)
- [x] Table `gemini_research` créée (research_id, cahier_id, query, results)
- [x] Index ajoutés pour performance
- [x] Méthodes CRUD complètes:
  - `create_cahier()`, `get_cahier()`, `get_cahiers_by_domain()`
  - `get_cahier_for_task()`, `load_cahier_content()`
  - `create_gemini_research()`, `get_research_for_cahier()`

### 3. Agent Gemini Researcher

**Fichier**: `orchestrator/agents/gemini_researcher.py`

- [x] Classe `GeminiResearcher` complète
- [x] Méthodes:
  - `research()` - Recherche générale
  - `research_best_practices()` - Best practices par domaine
  - `research_security_recommendations()` - Recommandations sécurité
  - `research_library_documentation()` - Documentation bibliothèques
  - `batch_research()` - Recherches en parallèle
- [x] Simulation pour développement
- [x] Structure prête pour intégration Gemini API réelle

### 4. Phase 0: Master + Analystes

**Fichier**: `orchestrator/phases/phase0_master_analysts.py`

#### Classe `Domain`
- Dataclass représentant un domaine identifié
- Attributs: name, description, analyst_template, priority, complexity, research_queries

#### Classe `AnalystAgent`
- [x] Analyse un domaine spécifique
- [x] Intégration Gemini optionnelle pour recherche externe
- [x] **Génère le cahier des charges principal en Markdown**
- [x] **Crée des tâches granulaires** (2-3 par domaine)
- [x] Enregistre tout dans la DB
- [x] Méthodes:
  - `analyze_and_create_cahier()` - Workflow complet
  - `_perform_research()` - Recherche Gemini
  - `_simulate_cahier_generation()` - Génère cahier + tâches
  - `_save_cahier()` - Sauvegarde fichier MD
  - `_create_tasks_from_cahier()` - Crée tâches en DB avec statut `CAHIER_READY`

#### Classe `MasterAnalyst`
- [x] Analyse la requête utilisateur
- [x] Identifie les domaines nécessaires
- [x] Crée les agents analystes (exécution parallèle)
- [x] Coordonne la génération des cahiers
- [x] Met à jour l'index global

#### Fonction `run_phase0()`
- [x] Point d'entrée de la phase
- [x] Retourne le nombre de cahiers générés

### 5. Fichiers Copiés

- [x] `orchestrator/phases/phase1_dispatcher.py` (copié depuis phase2)
  - Prêt pour adaptation

## 🔄 En Cours

### Phase 1: Dispatcher

**Objectif**: Lire les tâches avec statut `CAHIER_READY` et créer les worktrees

**Modifications nécessaires**:
- Lire `CAHIER_READY` au lieu de `SPEC_READY`
- NE PAS créer les agents (ça sera fait en Phase 2)
- Juste créer worktrees et mettre statut à `DISPATCHED`

## ⏳ À Faire

### Phase 2: Spécialistes (nouveau)

**Fichier à créer**: `orchestrator/phases/phase2_specialists.py`

**Fonctionnalités**:
- Lire tâches avec statut `DISPATCHED`
- Pour chaque tâche:
  1. Charger le cahier des charges depuis la DB
  2. Créer un agent spécialiste
  3. **Injecter le cahier comme contexte** dans le prompt
  4. Laisser le spécialiste travailler
  5. Mettre statut à `CODE_DONE`

### Phase 3: QA (renommage)

- Renommer `phase4_qa.py` → `phase3_qa.py`
- Adapter les imports/références
- Pas de changement fonctionnel majeur

### Phase 4: Merger (renommage + amélioration)

- Renommer `phase5_merger.py` → `phase4_merger.py`
- **Ajouter gestion interactive des conflits**:
  - Si conflit détecté → `git merge --abort`
  - Créer rapport de conflit
  - **Prompt utilisateur**: "Voulez-vous résoudre manuellement ?"
  - Attendre intervention humaine

### Agent Factory

**Fichier**: `orchestrator/agent_factory.py`

**Modifications**:
- Ajouter support injection de cahiers Markdown dans les prompts
- Nouvelle méthode: `inject_cahier_context(prompt, cahier_content)`
- Formater joliment le cahier dans le prompt

### Configuration

**Fichier**: `config/pipeline_config.yaml`

**Nouvelles sections**:

```yaml
phase0:
  enabled: true
  master_template: "system-architect"
  analyst_templates:
    security: "security-auditor"
    api: "senior-engineer"
    database: "database-expert"
  max_parallel_analysts: 5
  enable_gemini_research: true
  gemini_model: "gemini-pro"
  cahiers_charges_dir: "cahiers_charges"

# Phase 1 = Dispatcher (ancien Phase 2)
phase1:
  enabled: true
  worktrees_dir: ".worktrees"
  check_dependencies: true

# Phase 2 = Spécialistes (nouveau)
phase2:
  enabled: true
  max_parallel_specialists: 3
  inject_cahier_as_context: true

# Phase 3 = QA (ancien Phase 4)
phase3:
  # ... config validation

# Phase 4 = Merger (ancien Phase 5)
phase4:
  require_human_validation: true
  on_conflict: "prompt_user"  # Nouveau comportement
```

### Main.py

**Fichier**: `orchestrator/main.py`

**Modifications**:
- Mettre à jour orchestration des phases
- Adapter commandes CLI:
  - `run-phase 0` → Phase 0 (analystes)
  - `run-phase 1` → Phase 1 (dispatcher)
  - `run-phase 2` → Phase 2 (spécialistes)
  - etc.
- Ajuster imports

### Nettoyage

**Fichiers à supprimer**:
- `orchestrator/phases/phase0_master.py` (ancien)
- `orchestrator/phases/phase1_specialists.py` (ancien)
- `orchestrator/phases/phase2_dispatcher.py` (renommé en phase1)
- `orchestrator/phases/phase3_coder.py` (remplacé par phase2_specialists)

### Documentation

**Fichier**: `README.md`

**Sections à mettre à jour**:
- Vue d'ensemble (6 phases au lieu de 6)
- Description de Phase 0 (nouveaux cahiers)
- Description de toutes les phases (nouvelles numérotations)
- Diagrammes de flux
- Exemples de cahiers des charges
- Configuration

## Notes Techniques

### Format des Cahiers

**Structure Markdown**:
```markdown
# Cahier des Charges - {Domain}

**Domaine**: Security
**Priorité**: high
**Complexité**: complex

## 1. Contexte et Analyse
## 2. Objectifs
## 3. Spécifications Techniques
## 4. Fichiers et Structure
## 5. Dépendances
## 6. Critères d'Acceptation
## 7. Sécurité
## 8. Notes Techniques
```

### Stockage

```
cahiers_charges/
├── index.json
├── Security/
│   ├── rapport_analyse.md       # Cahier principal du domaine
│   ├── TASK-101_cahier.md       # Cahier spécifique à la tâche
│   └── TASK-102_cahier.md
└── API/
    ├── rapport_analyse.md
    └── TASK-201_cahier.md
```

### Flux de Données

1. **User** → "Améliorer la sécurité"
2. **Phase 0**:
   - Master identifie domaines: [Security, Authentication]
   - Crée 2 analystes
   - Chaque analyste:
     - Génère cahier principal
     - Crée 2-3 tâches granulaires
     - Enregistre tout en DB (statut `CAHIER_READY`)
3. **Phase 1**:
   - Lit tâches `CAHIER_READY`
   - Crée worktrees
   - Statut → `DISPATCHED`
4. **Phase 2**:
   - Pour chaque tâche `DISPATCHED`:
     - Charge le cahier
     - Crée spécialiste
     - Injecte cahier dans prompt
     - Spécialiste implémente
     - Statut → `CODE_DONE`
5. **Phase 3**: Validation
6. **Phase 4**: Merge (avec gestion conflits interactive)

## Décisions Architecturales

### Option A Choisie ✅

Phase 0 crée à la fois:
- **Cahiers des charges** (rapport d'analyse)
- **Tâches granulaires** (2-3 par domaine)

Avantages:
- Tout automatisé dès le début
- Tâches déjà liées aux cahiers
- Workflow fluide Phase 0 → Phase 1

### Recherche Gemini

- **Optionnelle** (configurable)
- Enrichit les cahiers avec best practices externes
- Mode simulation par défaut (pour développement)
- Prêt pour intégration API réelle

## Prochaines Étapes

1. ✏️ **Finaliser Phase 1** (dispatcher adapté)
2. ✏️ **Créer Phase 2** (spécialistes avec injection cahiers)
3. ✏️ **Renommer Phases 3 & 4**
4. ✏️ **Modifier agent_factory.py**
5. ✏️ **Mettre à jour config YAML**
6. ✏️ **Adapter main.py**
7. ✏️ **Nettoyer anciens fichiers**
8. ✏️ **Mettre à jour README**
9. ✅ **Tests end-to-end**

## Tokens Utilisés

~90,000 / 200,000 tokens

## Questions Ouvertes

- [ ] Faut-il permettre à l'utilisateur de valider les cahiers avant de continuer ?
- [ ] Gemini API key: où la stocker ? (variable d'environnement ? config ?)
- [ ] Faut-il créer une phase 0.5 optionnelle pour review humaine des cahiers ?
