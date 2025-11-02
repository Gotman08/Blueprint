# Cahiers des Charges

Ce dossier contient les cahiers des charges générés par les agents analystes durant la **Phase 0** du pipeline Blueprint.

## Structure

```
cahiers_charges/
├── index.json                    # Index global de tous les cahiers
├── {Domaine}/
│   ├── rapport_analyse.md        # Analyse globale du domaine
│   ├── TASK-XXX_cahier.md        # Cahier des charges pour une tâche spécifique
│   └── ...
└── README.md                     # Ce fichier
```

## Format des Cahiers des Charges

Chaque cahier des charges est un fichier Markdown contenant :

- **Contexte** : Analyse du code existant et du besoin
- **Objectifs** : Ce qui doit être accompli
- **Architecture Recommandée** : Patterns et approches suggérés
- **Fichiers à modifier** : Liste des fichiers concernés
- **Dépendances détectées** : Bibliothèques et composants existants
- **Recherches externes** : Best practices et documentation (via Gemini)
- **Critères d'acceptation** : Liste de vérification pour validation

## Utilisation

Ces cahiers sont automatiquement injectés comme contexte dans les prompts des agents spécialistes (Phase 2) pour guider leur implémentation.

## Nettoyage

Ce dossier est créé dynamiquement à chaque exécution du pipeline. Les anciens cahiers peuvent être archivés ou supprimés selon la configuration.
