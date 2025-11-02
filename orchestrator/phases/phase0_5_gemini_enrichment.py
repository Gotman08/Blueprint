"""
Phase 0.5: Gemini Enrichment
Enrichit séquentiellement les cahiers des charges avec des bonnes pratiques,
approches modernes et contexte du monde réel via Gemini CLI.
"""

import os
import json
import time
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..db import Database
from ..utils.logger import Logger
from ..agents.gemini_researcher import GeminiResearcher
from ..utils.config_loader import load_config


class GeminiEnricher:
    """
    Enrichit les cahiers des charges avec Gemini CLI.
    Traitement séquentiel avec 3 types d'enrichissement par cahier.
    """

    def __init__(self, config: Dict, database: Database, logger: Logger):
        self.config = config
        self.db = database
        self.logger = logger
        self.phase_config = config.get('phase0_5', {})
        self.enabled = self.phase_config.get('enabled', False)

        # Configuration de l'enrichissement
        self.enrich_all = self.phase_config.get('enrich_all_cahiers', True)
        self.priority_domains = self.phase_config.get('priority_domains', [])
        self.delay_between = self.phase_config.get('delay_between_cahiers', 5)

        # Types d'enrichissement
        self.enrichment_types = self.phase_config.get('enrichment_types', {
            'good_practices': True,
            'modern_approaches': True,
            'real_world_context': True
        })

        # Configuration Gemini
        self.gemini_model = self.phase_config.get('gemini_model', 'gemini-2.5-pro')
        self.gemini_timeout = self.phase_config.get('gemini_timeout', 60)

        # Format
        self.section_title = self.phase_config.get('enrichment_section_title', '🌟 ENRICHISSEMENT GEMINI')
        self.add_timestamp = self.phase_config.get('add_timestamp', True)
        self.add_model_info = self.phase_config.get('add_model_info', True)

        # Gestion d'erreurs
        self.max_retries = self.phase_config.get('max_retries_per_cahier', 2)
        self.skip_on_failure = self.phase_config.get('skip_on_failure', True)

        # Chercheur Gemini
        self.researcher = GeminiResearcher(config, logger) if self.enabled else None

    async def run(self) -> Dict:
        """
        Exécute Phase 0.5 : enrichit séquentiellement tous les cahiers.
        """
        if not self.enabled:
            self.logger.info("Phase 0.5 désactivée (phase0_5.enabled: false)")
            return {'status': 'skipped', 'reason': 'disabled'}

        self.logger.info("=== PHASE 0.5: Enrichissement Gemini ===")

        # Charger tous les cahiers avec statut CAHIER_READY
        cahiers = await self.db.get_cahiers_to_enrich()

        if not cahiers:
            self.logger.warning("Aucun cahier à enrichir trouvé")
            return {'status': 'completed', 'enriched': 0}

        # Filtrer selon configuration
        if not self.enrich_all:
            cahiers = [c for c in cahiers if c['domain'] in self.priority_domains]
            self.logger.info(f"Filtrage des domaines prioritaires: {len(cahiers)} cahiers")

        results = {
            'status': 'completed',
            'total': len(cahiers),
            'enriched': 0,
            'failed': 0,
            'skipped': 0,
            'enrichments': []
        }

        # Traitement séquentiel
        for idx, cahier in enumerate(cahiers, 1):
            self.logger.info(f"Enrichissement {idx}/{len(cahiers)}: {cahier['file_path']}")

            try:
                enriched = await self._enrich_cahier(cahier)
                if enriched:
                    results['enriched'] += 1
                    results['enrichments'].append(enriched)
                else:
                    results['skipped'] += 1
            except Exception as e:
                self.logger.error(f"Erreur enrichissement {cahier['cahier_id']}: {e}")
                results['failed'] += 1

                if not self.skip_on_failure:
                    raise

            # Délai entre cahiers (rate limiting)
            if idx < len(cahiers):
                self.logger.debug(f"Attente {self.delay_between}s (rate limiting)")
                time.sleep(self.delay_between)

        # Rapport final
        self.logger.info("=== Phase 0.5 Terminée ===")
        self.logger.info(f"✅ Enrichis: {results['enriched']}/{results['total']}")
        if results['failed'] > 0:
            self.logger.warning(f"⚠️ Échecs: {results['failed']}")
        if results['skipped'] > 0:
            self.logger.info(f"⏭️ Ignorés: {results['skipped']}")

        return results

    async def _enrich_cahier(self, cahier: Dict) -> Optional[Dict]:
        """
        Enrichit un cahier avec les 3 types d'enrichissement.
        """
        cahier_path = Path(cahier['file_path'])

        if not cahier_path.exists():
            self.logger.warning(f"Fichier cahier introuvable: {cahier_path}")
            return None

        # Charger le contenu actuel
        original_content = cahier_path.read_text(encoding='utf-8')

        # Vérifier si déjà enrichi
        if self.section_title in original_content:
            self.logger.info(f"Cahier déjà enrichi, skip: {cahier_path.name}")
            return None

        # Extraire le domaine
        domain = cahier.get('domain', 'Unknown')

        # Collecter les enrichissements
        enrichments = {}
        start_time = time.time()

        # 1. Good Practices
        if self.enrichment_types.get('good_practices'):
            self.logger.debug(f"Recherche Good Practices pour {domain}")
            good_practices = await self._get_good_practices(domain)
            enrichments['good_practices'] = good_practices

        # 2. Modern Approaches
        if self.enrichment_types.get('modern_approaches'):
            self.logger.debug(f"Recherche Modern Approaches pour {domain}")
            modern_approaches = await self._get_modern_approaches(domain)
            enrichments['modern_approaches'] = modern_approaches

        # 3. Real-world Context
        if self.enrichment_types.get('real_world_context'):
            self.logger.debug(f"Recherche Real-world Context pour {domain}")
            real_world = await self._get_real_world_context(domain)
            enrichments['real_world_context'] = real_world

        duration = int(time.time() - start_time)

        # Construire la section enrichissement
        enrichment_section = self._build_enrichment_section(enrichments, domain, duration)

        # Injecter dans le cahier
        enriched_content = self._inject_enrichment(original_content, enrichment_section)

        # Sauvegarder
        cahier_path.write_text(enriched_content, encoding='utf-8')

        # Mettre à jour la base de données
        await self._save_enrichment_to_db(cahier, enrichments, duration)

        self.logger.info(f"✅ Cahier enrichi: {cahier_path.name} ({duration}s)")

        return {
            'cahier_id': cahier['cahier_id'],
            'domain': domain,
            'duration': duration,
            'enrichment_types': list(enrichments.keys())
        }

    async def _get_good_practices(self, domain: str) -> str:
        """
        Recherche les bonnes pratiques actuelles pour un domaine.
        """
        query = f"""
        What are the current best practices for implementing {domain} in 2025?
        Include:
        - Industry standards and compliance requirements
        - Security best practices
        - Common design patterns
        - Testing strategies
        - Performance optimization tips
        Please provide specific, actionable recommendations.
        """

        try:
            result = await self.researcher.research(query, context=f"Domain: {domain}")
            return result.get('summary', 'No good practices found')
        except Exception as e:
            self.logger.error(f"Erreur recherche good practices: {e}")
            return f"Error retrieving good practices: {str(e)}"

    async def _get_modern_approaches(self, domain: str) -> str:
        """
        Recherche les approches modernes et technologies récentes.
        """
        query = f"""
        What are the modern approaches and latest technologies for {domain} in 2025?
        Include:
        - New frameworks and libraries (released in last 2 years)
        - Modern architectural patterns
        - Cloud-native approaches
        - Microservices and serverless considerations
        - AI/ML integrations if relevant
        Focus on production-ready solutions, not experimental tech.
        """

        try:
            result = await self.researcher.research(query, context=f"Domain: {domain}")
            return result.get('summary', 'No modern approaches found')
        except Exception as e:
            self.logger.error(f"Erreur recherche modern approaches: {e}")
            return f"Error retrieving modern approaches: {str(e)}"

    async def _get_real_world_context(self, domain: str) -> str:
        """
        Recherche le contexte du monde réel et retours d'expérience.
        """
        query = f"""
        How do professional teams implement {domain} in production environments?
        Include:
        - Common pitfalls and how to avoid them
        - Real-world scalability considerations
        - Monitoring and observability strategies
        - Deployment and CI/CD practices
        - Recommended tech stacks (specific tools/services)
        - Cost optimization strategies
        Provide practical, battle-tested advice from production experience.
        """

        try:
            result = await self.researcher.research(query, context=f"Domain: {domain}")
            return result.get('summary', 'No real-world context found')
        except Exception as e:
            self.logger.error(f"Erreur recherche real-world context: {e}")
            return f"Error retrieving real-world context: {str(e)}"

    def _build_enrichment_section(self, enrichments: Dict, domain: str, duration: int) -> str:
        """
        Construit la section Markdown d'enrichissement.
        """
        lines = []

        # En-tête
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(f"## {self.section_title}")
        lines.append("")

        if self.add_timestamp:
            lines.append(f"**Date d'enrichissement**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        if self.add_model_info:
            lines.append(f"**Modèle**: {self.gemini_model}")
            lines.append(f"**Durée**: {duration} secondes")

        lines.append("")

        # Good Practices
        if 'good_practices' in enrichments:
            lines.append("### 📚 Good Practices (Bonnes Pratiques 2025)")
            lines.append("")
            lines.append(enrichments['good_practices'])
            lines.append("")

        # Modern Approaches
        if 'modern_approaches' in enrichments:
            lines.append("### 🚀 Modern Approaches (Approches Modernes)")
            lines.append("")
            lines.append(enrichments['modern_approaches'])
            lines.append("")

        # Real-world Context
        if 'real_world_context' in enrichments:
            lines.append("### 🌍 Real-world Context (Contexte Professionnel)")
            lines.append("")
            lines.append(enrichments['real_world_context'])
            lines.append("")

        # Footer
        lines.append("---")
        lines.append("")
        lines.append("*Enrichissement généré automatiquement par Phase 0.5 - Gemini CLI*")
        lines.append("")

        return "\n".join(lines)

    def _inject_enrichment(self, original_content: str, enrichment_section: str) -> str:
        """
        Injecte la section enrichissement dans le cahier.
        Stratégie: Ajouter avant la dernière section ou à la fin.
        """
        lines = original_content.split('\n')

        # Chercher où insérer (avant "## Ressources" ou à la fin)
        insert_index = len(lines)

        for i in range(len(lines) - 1, -1, -1):
            if lines[i].startswith('## 8. Ressources') or lines[i].startswith('## 9.'):
                insert_index = i
                break

        # Insérer l'enrichissement
        enriched_lines = lines[:insert_index] + enrichment_section.split('\n') + lines[insert_index:]

        return '\n'.join(enriched_lines)

    async def _save_enrichment_to_db(self, cahier: Dict, enrichments: Dict, duration: int):
        """
        Sauvegarde les enrichissements en base de données.
        """
        for enrichment_type, content in enrichments.items():
            enrichment_id = f"enrich_{cahier['cahier_id']}_{enrichment_type}"

            await self.db.create_gemini_enrichment(
                enrichment_id=enrichment_id,
                cahier_id=cahier['cahier_id'],
                enrichment_type=enrichment_type,
                content=content[:5000],  # Limiter la taille
                model=self.gemini_model,
                duration_seconds=duration // len(enrichments)  # Diviser le temps
            )

        # Mettre à jour le hash du cahier
        cahier_path = Path(cahier['file_path'])
        new_content = cahier_path.read_text(encoding='utf-8')
        new_hash = hashlib.md5(new_content.encode()).hexdigest()

        await self.db.update_cahier_hash(cahier['cahier_id'], new_hash)


async def run_phase_0_5(config: Dict, database: Database, logger: Logger) -> Dict:
    """
    Point d'entrée pour Phase 0.5.
    """
    enricher = GeminiEnricher(config, database, logger)
    return await enricher.run()