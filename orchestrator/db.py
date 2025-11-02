"""
Database management for the generative agent pipeline.

This module handles all SQLite operations for tracking tasks, agents, and validations.
"""

import aiosqlite
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import Enum


class TaskStatus(Enum):
    """Task lifecycle states"""
    CAHIER_READY = "cahier_ready"       # Cahier des charges created by analyst
    SPEC_READY = "spec_ready"           # Spec created by analyst (legacy)
    DISPATCHED = "dispatched"           # Worktree created
    SPECIALIST_WORKING = "specialist_working"  # Specialist agent is working
    CODE_DONE = "code_done"             # Code finished
    VALIDATION_PENDING = "validation_pending"  # Waiting for QA
    VALIDATION_FAILED = "validation_failed"    # QA rejected
    VALIDATION_PASSED = "validation_passed"    # Both logic + tech passed
    MERGE_CONFLICT = "merge_conflict"   # Merge conflict detected - manual resolution required
    MERGED = "merged"                   # Merged to main
    FAILED = "failed"                   # Unrecoverable error


class AgentStatus(Enum):
    """Agent lifecycle states"""
    CREATED = "created"
    WORKING = "working"
    COMPLETED = "completed"
    ERROR = "error"


class ValidationStatus(Enum):
    """Validation check states"""
    PENDING = "pending"
    GO = "go"
    NO_GO = "no_go"


class Database:
    """Async SQLite database manager"""

    def __init__(self, db_path: str = "pipeline.db"):
        self.db_path = Path(db_path)
        self.conn: Optional[aiosqlite.Connection] = None

    async def initialize(self):
        """Create database schema if not exists"""
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row

        await self.conn.executescript("""
            -- Tasks table: tracks each development task
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                spec_path TEXT NOT NULL,
                branch_name TEXT,
                worktree_path TEXT,
                priority TEXT DEFAULT 'medium',
                status TEXT NOT NULL DEFAULT 'spec_ready',
                dependencies TEXT,  -- JSON array of task_ids
                retry_count INTEGER DEFAULT 0,  -- Number of retry attempts
                last_feedback TEXT,  -- JSON feedback from failed validations
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );

            -- Agents table: tracks agent instances working on tasks
            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                role TEXT NOT NULL,  -- 'coder', 'verifier', 'tester', 'analyst', 'specialist'
                template_name TEXT NOT NULL,  -- Name from ~/.claude/agents/
                status TEXT NOT NULL DEFAULT 'created',
                result TEXT,  -- JSON output from agent
                error_message TEXT,
                allow_paths TEXT,  -- JSON array of allowed file/directory patterns
                exclude_paths TEXT,  -- JSON array of excluded file/directory patterns
                access_mode TEXT DEFAULT 'block',  -- 'block', 'log', 'ask'
                worktree_path TEXT,  -- Path to agent's worktree for validation context
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(task_id)
            );

            -- Validations table: tracks QA checks
            CREATE TABLE IF NOT EXISTS validations (
                validation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                validator_type TEXT NOT NULL,  -- 'logic' or 'tech'
                status TEXT NOT NULL DEFAULT 'pending',
                message TEXT,
                details TEXT,  -- JSON with detailed results
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(task_id)
            );

            -- Access violations table: tracks file access attempts and violations
            CREATE TABLE IF NOT EXISTS access_violations (
                violation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                agent_id TEXT,
                file_path TEXT NOT NULL,
                operation TEXT NOT NULL,  -- 'read', 'write', 'delete', etc.
                decision TEXT NOT NULL,  -- 'allowed', 'denied_excluded', 'denied_not_in_allow', etc.
                reason TEXT,
                human_approved INTEGER DEFAULT 0,  -- 0 = not approved, 1 = approved
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(task_id),
                FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
            );

            -- Agent templates table: tracks available templates from all sources
            CREATE TABLE IF NOT EXISTS agent_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                source TEXT NOT NULL,  -- 'local', 'github', 'custom'
                category TEXT,
                description TEXT,
                model TEXT DEFAULT 'opus',
                version TEXT,
                content TEXT,
                metadata TEXT,  -- JSON metadata (tools, tags, etc.)
                download_count INTEGER DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Template usage table: tracks which templates were used for which tasks
            CREATE TABLE IF NOT EXISTS template_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_name TEXT NOT NULL,
                task_id TEXT,
                agent_id TEXT,
                phase TEXT,  -- 'phase0', 'phase1', 'phase3', 'phase4'
                role TEXT,  -- 'coder', 'verifier', 'tester', 'analyst'
                success INTEGER DEFAULT 0,  -- 0 = failed, 1 = success
                duration_seconds INTEGER,  -- How long the agent worked
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(task_id),
                FOREIGN KEY (agent_id) REFERENCES agents(agent_id),
                FOREIGN KEY (template_name) REFERENCES agent_templates(name)
            );

            -- Cahiers des charges table: tracks specifications created by analyst agents
            CREATE TABLE IF NOT EXISTS cahiers_charges (
                cahier_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                task_id TEXT,
                analyst_agent_id TEXT,
                file_path TEXT NOT NULL,
                content_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(task_id),
                FOREIGN KEY (analyst_agent_id) REFERENCES agents(agent_id)
            );

            -- Gemini research table: tracks external research done for cahiers
            CREATE TABLE IF NOT EXISTS gemini_research (
                research_id INTEGER PRIMARY KEY AUTOINCREMENT,
                cahier_id TEXT,
                query TEXT NOT NULL,
                results TEXT,  -- JSON results from Gemini
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cahier_id) REFERENCES cahiers_charges(cahier_id)
            );

            -- Indexes for performance
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_agents_task ON agents(task_id);
            CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
            CREATE INDEX IF NOT EXISTS idx_validations_task ON validations(task_id);
            CREATE INDEX IF NOT EXISTS idx_violations_task ON access_violations(task_id);
            CREATE INDEX IF NOT EXISTS idx_violations_decision ON access_violations(decision);
            CREATE INDEX IF NOT EXISTS idx_templates_source ON agent_templates(source);
            CREATE INDEX IF NOT EXISTS idx_templates_category ON agent_templates(category);
            CREATE INDEX IF NOT EXISTS idx_template_usage_template ON template_usage(template_name);
            CREATE INDEX IF NOT EXISTS idx_template_usage_task ON template_usage(task_id);
            CREATE INDEX IF NOT EXISTS idx_template_usage_phase ON template_usage(phase);
            CREATE INDEX IF NOT EXISTS idx_cahiers_domain ON cahiers_charges(domain);
            CREATE INDEX IF NOT EXISTS idx_cahiers_task ON cahiers_charges(task_id);
            CREATE INDEX IF NOT EXISTS idx_gemini_research_cahier ON gemini_research(cahier_id);
        """)

        await self.conn.commit()

        # Run migrations for existing databases
        await self._migrate_agents_access_control()

    async def close(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()

    async def _migrate_agents_access_control(self) -> None:
        """
        Migration: Add access control columns to agents table for existing databases.

        This migration adds:
        - allow_paths: JSON array of allowed file patterns
        - exclude_paths: JSON array of excluded file patterns
        - access_mode: Enforcement mode ('block', 'log', 'ask')
        - worktree_path: Path to agent's worktree

        Safe to run multiple times (columns will only be added if missing).
        """
        try:
            # Try to add allow_paths column
            await self.conn.execute("""
                ALTER TABLE agents ADD COLUMN allow_paths TEXT
            """)
            await self.conn.commit()
        except aiosqlite.OperationalError:
            # Column already exists, skip
            pass

        try:
            # Try to add exclude_paths column
            await self.conn.execute("""
                ALTER TABLE agents ADD COLUMN exclude_paths TEXT
            """)
            await self.conn.commit()
        except aiosqlite.OperationalError:
            # Column already exists, skip
            pass

        try:
            # Try to add access_mode column
            await self.conn.execute("""
                ALTER TABLE agents ADD COLUMN access_mode TEXT DEFAULT 'block'
            """)
            await self.conn.commit()
        except aiosqlite.OperationalError:
            # Column already exists, skip
            pass

        try:
            # Try to add worktree_path column
            await self.conn.execute("""
                ALTER TABLE agents ADD COLUMN worktree_path TEXT
            """)
            await self.conn.commit()
        except aiosqlite.OperationalError:
            # Column already exists, skip
            pass

    # ========== TASK OPERATIONS ==========

    async def create_task(
        self,
        task_id: str,
        domain: str,
        title: str,
        description: str,
        spec_path: str,
        priority: str = "medium",
        dependencies: Optional[List[str]] = None
    ) -> None:
        """Create a new task record"""
        deps_json = json.dumps(dependencies) if dependencies else None

        await self.conn.execute("""
            INSERT INTO tasks (task_id, domain, title, description, spec_path, priority, dependencies)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (task_id, domain, title, description, spec_path, priority, deps_json))

        await self.conn.commit()

    async def update_task_status(self, task_id: str, status: TaskStatus) -> None:
        """Update task status"""
        await self.conn.execute("""
            UPDATE tasks
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
        """, (status.value, task_id))

        await self.conn.commit()

    async def set_task_branch(self, task_id: str, branch_name: str, worktree_path: str) -> None:
        """Set git branch and worktree for a task"""
        await self.conn.execute("""
            UPDATE tasks
            SET branch_name = ?, worktree_path = ?, updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
        """, (branch_name, worktree_path, task_id))

        await self.conn.commit()

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task by ID"""
        async with self.conn.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_tasks_by_status(self, status: TaskStatus) -> List[Dict[str, Any]]:
        """Get all tasks with a specific status"""
        async with self.conn.execute(
            "SELECT * FROM tasks WHERE status = ? ORDER BY created_at", (status.value,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def mark_task_completed(self, task_id: str) -> None:
        """Mark task as merged and completed"""
        await self.conn.execute("""
            UPDATE tasks
            SET status = ?, completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
        """, (TaskStatus.MERGED.value, task_id))

        await self.conn.commit()

    # ========== AGENT OPERATIONS ==========

    async def create_agent(
        self,
        agent_id: str,
        task_id: str,
        role: str,
        template_name: str,
        allow_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
        access_mode: str = "block",
        worktree_path: Optional[str] = None
    ) -> None:
        """
        Create a new agent record with access control configuration.

        Args:
            agent_id: Unique agent identifier
            task_id: Associated task ID
            role: Agent role ('analyst', 'specialist', 'verifier', 'tester')
            template_name: Name of the agent template
            allow_paths: Optional list of allowed file/directory patterns (glob format)
            exclude_paths: Optional list of excluded file/directory patterns (glob format)
            access_mode: Enforcement mode ('block', 'log', 'ask')
            worktree_path: Path to agent's worktree for validation context
        """
        # Convert lists to JSON for storage
        allow_json = json.dumps(allow_paths) if allow_paths else None
        exclude_json = json.dumps(exclude_paths) if exclude_paths else None

        await self.conn.execute("""
            INSERT INTO agents (
                agent_id, task_id, role, template_name,
                allow_paths, exclude_paths, access_mode, worktree_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            agent_id, task_id, role, template_name,
            allow_json, exclude_json, access_mode, worktree_path
        ))

        await self.conn.commit()

    async def update_agent_status(
        self,
        agent_id: str,
        status: AgentStatus,
        result: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Update agent status and result"""
        completed_at = datetime.now() if status in [AgentStatus.COMPLETED, AgentStatus.ERROR] else None

        await self.conn.execute("""
            UPDATE agents
            SET status = ?, result = ?, error_message = ?, completed_at = ?
            WHERE agent_id = ?
        """, (status.value, result, error_message, completed_at, agent_id))

        await self.conn.commit()

    async def get_agents_for_task(self, task_id: str) -> List[Dict[str, Any]]:
        """Get all agents assigned to a task"""
        async with self.conn.execute(
            "SELECT * FROM agents WHERE task_id = ? ORDER BY created_at", (task_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_agent_access_config(self, agent_id: str) -> Dict[str, Any]:
        """
        Get access control configuration for an agent.

        Args:
            agent_id: Agent ID to retrieve configuration for

        Returns:
            Dictionary with access control configuration:
            {
                'allow': [...],  # List of allowed patterns
                'exclude': [...],  # List of excluded patterns
                'mode': 'block',  # Enforcement mode
                'worktree_path': '/path/to/worktree'
            }

            Returns empty dict if agent not found.
        """
        async with self.conn.execute("""
            SELECT allow_paths, exclude_paths, access_mode, worktree_path
            FROM agents WHERE agent_id = ?
        """, (agent_id,)) as cursor:
            row = await cursor.fetchone()

        if not row:
            return {}

        # Parse JSON arrays
        allow_paths = json.loads(row[0]) if row[0] else []
        exclude_paths = json.loads(row[1]) if row[1] else []

        return {
            'allow': allow_paths,
            'exclude': exclude_paths,
            'mode': row[2] or 'block',
            'worktree_path': row[3]
        }

    # ========== VALIDATION OPERATIONS ==========

    async def create_validation(
        self,
        task_id: str,
        validator_type: str,
        status: ValidationStatus = ValidationStatus.PENDING
    ) -> int:
        """Create a validation record, returns validation_id"""
        cursor = await self.conn.execute("""
            INSERT INTO validations (task_id, validator_type, status)
            VALUES (?, ?, ?)
        """, (task_id, validator_type, status.value))

        await self.conn.commit()
        return cursor.lastrowid

    async def update_validation(
        self,
        validation_id: int,
        status: ValidationStatus,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update validation status and results"""
        details_json = json.dumps(details) if details else None

        await self.conn.execute("""
            UPDATE validations
            SET status = ?, message = ?, details = ?
            WHERE validation_id = ?
        """, (status.value, message, details_json, validation_id))

        await self.conn.commit()

    async def get_validations_for_task(self, task_id: str) -> List[Dict[str, Any]]:
        """Get all validations for a task"""
        async with self.conn.execute(
            "SELECT * FROM validations WHERE task_id = ? ORDER BY created_at", (task_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def check_task_ready_for_merge(self, task_id: str) -> bool:
        """Check if task has both logic and tech validation passed"""
        async with self.conn.execute("""
            SELECT validator_type, status
            FROM validations
            WHERE task_id = ?
            AND validator_type IN ('logic', 'tech')
            ORDER BY created_at DESC
        """, (task_id,)) as cursor:
            rows = await cursor.fetchall()

            if len(rows) < 2:
                return False

            validations = {row['validator_type']: row['status'] for row in rows}
            return (
                validations.get('logic') == ValidationStatus.GO.value and
                validations.get('tech') == ValidationStatus.GO.value
            )

    # ========== RETRY OPERATIONS ==========

    async def increment_retry(self, task_id: str, feedback: str) -> None:
        """
        Increment retry count and store feedback.

        Args:
            task_id: Task ID
            feedback: JSON feedback from failed validations
        """
        await self.conn.execute("""
            UPDATE tasks
            SET retry_count = retry_count + 1,
                last_feedback = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
        """, (feedback, task_id))

        await self.conn.commit()

    async def get_retry_count(self, task_id: str) -> int:
        """
        Get current retry count for a task.

        Args:
            task_id: Task ID

        Returns:
            Retry count (0 if no retries)
        """
        async with self.conn.execute(
            "SELECT retry_count FROM tasks WHERE task_id = ?", (task_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row['retry_count'] if row else 0

    async def get_last_feedback(self, task_id: str) -> Optional[str]:
        """
        Get last feedback for a task.

        Args:
            task_id: Task ID

        Returns:
            Last feedback JSON string or None
        """
        async with self.conn.execute(
            "SELECT last_feedback FROM tasks WHERE task_id = ?", (task_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row['last_feedback'] if row and row['last_feedback'] else None

    # ========== UTILITY OPERATIONS ==========

    async def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics"""
        stats = {}

        # Task stats by status
        async with self.conn.execute("""
            SELECT status, COUNT(*) as count
            FROM tasks
            GROUP BY status
        """) as cursor:
            stats['tasks_by_status'] = {row['status']: row['count'] for row in await cursor.fetchall()}

        # Agent stats
        async with self.conn.execute("""
            SELECT status, COUNT(*) as count
            FROM agents
            GROUP BY status
        """) as cursor:
            stats['agents_by_status'] = {row['status']: row['count'] for row in await cursor.fetchall()}

        # Total counts
        async with self.conn.execute("SELECT COUNT(*) as count FROM tasks") as cursor:
            stats['total_tasks'] = (await cursor.fetchone())['count']

        async with self.conn.execute("SELECT COUNT(*) as count FROM agents") as cursor:
            stats['total_agents'] = (await cursor.fetchone())['count']

        return stats

    async def get_active_tasks(self, exclude_task_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all active tasks (not completed, failed, or merged).

        Args:
            exclude_task_id: Optional task ID to exclude from results

        Returns:
            List of active task records
        """
        if exclude_task_id:
            async with self.conn.execute("""
                SELECT * FROM tasks
                WHERE status NOT IN ('merged', 'failed')
                AND task_id != ?
                ORDER BY created_at
            """, (exclude_task_id,)) as cursor:
                rows = await cursor.fetchall()
        else:
            async with self.conn.execute("""
                SELECT * FROM tasks
                WHERE status NOT IN ('merged', 'failed')
                ORDER BY created_at
            """) as cursor:
                rows = await cursor.fetchall()

        return [dict(row) for row in rows]

    async def get_task_spec(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Load and parse the task specification from JSON file.

        Args:
            task_id: Task ID

        Returns:
            Parsed spec dict or None if not found
        """
        task = await self.get_task(task_id)
        if not task or not task.get('spec_path'):
            return None

        try:
            spec_path = Path(task['spec_path'])
            if spec_path.exists():
                with open(spec_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            print(f"Error loading spec for {task_id}: {e}")

        return None

    # ========== ACCESS CONTROL OPERATIONS ==========

    async def log_access_violation(
        self,
        task_id: str,
        file_path: str,
        operation: str,
        decision: str,
        reason: Optional[str] = None,
        agent_id: Optional[str] = None,
        human_approved: bool = False
    ) -> int:
        """
        Log a file access attempt (both allowed and denied).

        Args:
            task_id: Task ID
            file_path: File path that was accessed/attempted
            operation: Type of operation (read, write, delete, etc.)
            decision: Access decision (allowed, denied_excluded, etc.)
            reason: Reason for the decision
            agent_id: Optional agent ID
            human_approved: Whether human approved this access

        Returns:
            Violation ID
        """
        cursor = await self.conn.execute("""
            INSERT INTO access_violations
            (task_id, agent_id, file_path, operation, decision, reason, human_approved)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (task_id, agent_id, file_path, operation, decision, reason, 1 if human_approved else 0))

        await self.conn.commit()
        return cursor.lastrowid

    async def get_access_violations_for_task(
        self,
        task_id: str,
        denied_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all access violations/attempts for a task.

        Args:
            task_id: Task ID
            denied_only: If True, only return denied access attempts

        Returns:
            List of violation records
        """
        if denied_only:
            async with self.conn.execute("""
                SELECT * FROM access_violations
                WHERE task_id = ? AND decision != 'allowed'
                ORDER BY created_at DESC
            """, (task_id,)) as cursor:
                rows = await cursor.fetchall()
        else:
            async with self.conn.execute("""
                SELECT * FROM access_violations
                WHERE task_id = ?
                ORDER BY created_at DESC
            """, (task_id,)) as cursor:
                rows = await cursor.fetchall()

        return [dict(row) for row in rows]

    async def approve_access_violation(self, violation_id: int) -> None:
        """
        Mark an access violation as human-approved.

        Args:
            violation_id: Violation ID to approve
        """
        await self.conn.execute("""
            UPDATE access_violations
            SET human_approved = 1
            WHERE violation_id = ?
        """, (violation_id,))

        await self.conn.commit()

    async def get_access_stats(self) -> Dict[str, Any]:
        """
        Get access control statistics.

        Returns:
            Dict with access statistics
        """
        stats = {}

        # Total violations
        async with self.conn.execute(
            "SELECT COUNT(*) as count FROM access_violations"
        ) as cursor:
            stats['total_attempts'] = (await cursor.fetchone())['count']

        # Violations by decision
        async with self.conn.execute("""
            SELECT decision, COUNT(*) as count
            FROM access_violations
            GROUP BY decision
        """) as cursor:
            stats['by_decision'] = {row['decision']: row['count'] for row in await cursor.fetchall()}

        # Denied violations that were human-approved
        async with self.conn.execute("""
            SELECT COUNT(*) as count
            FROM access_violations
            WHERE decision != 'allowed' AND human_approved = 1
        """) as cursor:
            stats['human_approved_denials'] = (await cursor.fetchone())['count']

        return stats

    # ========== TEMPLATE OPERATIONS ==========

    async def register_template(
        self,
        name: str,
        source: str,
        category: Optional[str] = None,
        description: Optional[str] = None,
        model: str = "opus",
        version: Optional[str] = None,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Register or update a template in the database.

        Args:
            name: Template name
            source: Source ('local', 'github', 'custom')
            category: Template category
            description: Template description
            model: Default model
            version: Template version
            content: Template content
            metadata: Additional metadata (tools, tags, etc.)

        Returns:
            Template ID
        """
        metadata_json = json.dumps(metadata) if metadata else None

        # Try to insert, if exists update
        cursor = await self.conn.execute("""
            INSERT INTO agent_templates
            (name, source, category, description, model, version, content, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                source = excluded.source,
                category = excluded.category,
                description = excluded.description,
                model = excluded.model,
                version = excluded.version,
                content = excluded.content,
                metadata = excluded.metadata,
                last_updated = CURRENT_TIMESTAMP
        """, (name, source, category, description, model, version, content, metadata_json))

        await self.conn.commit()
        return cursor.lastrowid

    async def get_template(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get a template by name.

        Args:
            name: Template name

        Returns:
            Template record or None
        """
        async with self.conn.execute(
            "SELECT * FROM agent_templates WHERE name = ?", (name,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                result = dict(row)
                # Parse metadata JSON
                if result.get('metadata'):
                    result['metadata'] = json.loads(result['metadata'])
                return result
            return None

    async def increment_template_downloads(self, name: str) -> None:
        """
        Increment download count for a template.

        Args:
            name: Template name
        """
        await self.conn.execute("""
            UPDATE agent_templates
            SET download_count = download_count + 1
            WHERE name = ?
        """, (name,))

        await self.conn.commit()

    async def get_templates_by_source(self, source: str) -> List[Dict[str, Any]]:
        """
        Get all templates from a specific source.

        Args:
            source: Source ('local', 'github', 'custom')

        Returns:
            List of template records
        """
        async with self.conn.execute(
            "SELECT * FROM agent_templates WHERE source = ? ORDER BY name", (source,)
        ) as cursor:
            rows = await cursor.fetchall()
            results = [dict(row) for row in rows]

            # Parse metadata JSON for each
            for result in results:
                if result.get('metadata'):
                    result['metadata'] = json.loads(result['metadata'])

            return results

    async def get_templates_by_category(self, category: str) -> List[Dict[str, Any]]:
        """
        Get all templates in a category.

        Args:
            category: Category name

        Returns:
            List of template records
        """
        async with self.conn.execute(
            "SELECT * FROM agent_templates WHERE category = ? ORDER BY name", (category,)
        ) as cursor:
            rows = await cursor.fetchall()
            results = [dict(row) for row in rows]

            # Parse metadata JSON for each
            for result in results:
                if result.get('metadata'):
                    result['metadata'] = json.loads(result['metadata'])

            return results

    async def log_template_usage(
        self,
        template_name: str,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        phase: Optional[str] = None,
        role: Optional[str] = None,
        success: bool = False,
        duration_seconds: Optional[int] = None
    ) -> int:
        """
        Log template usage for analytics.

        Args:
            template_name: Name of the template used
            task_id: Task ID
            agent_id: Agent ID
            phase: Phase where template was used
            role: Role of the agent
            success: Whether the agent succeeded
            duration_seconds: How long the agent worked

        Returns:
            Usage ID
        """
        cursor = await self.conn.execute("""
            INSERT INTO template_usage
            (template_name, task_id, agent_id, phase, role, success, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (template_name, task_id, agent_id, phase, role, 1 if success else 0, duration_seconds))

        await self.conn.commit()
        return cursor.lastrowid

    async def get_template_usage_stats(self, template_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get template usage statistics.

        Args:
            template_name: Optional template name to filter by

        Returns:
            Usage statistics
        """
        stats = {}

        if template_name:
            # Stats for specific template
            async with self.conn.execute("""
                SELECT COUNT(*) as count, AVG(duration_seconds) as avg_duration
                FROM template_usage
                WHERE template_name = ?
            """, (template_name,)) as cursor:
                row = await cursor.fetchone()
                stats['total_uses'] = row['count']
                stats['avg_duration'] = row['avg_duration']

            async with self.conn.execute("""
                SELECT COUNT(*) as count
                FROM template_usage
                WHERE template_name = ? AND success = 1
            """, (template_name,)) as cursor:
                stats['successful_uses'] = (await cursor.fetchone())['count']

            # Success rate
            if stats['total_uses'] > 0:
                stats['success_rate'] = stats['successful_uses'] / stats['total_uses']
            else:
                stats['success_rate'] = 0.0

        else:
            # Overall stats
            async with self.conn.execute("""
                SELECT template_name, COUNT(*) as uses,
                       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes
                FROM template_usage
                GROUP BY template_name
                ORDER BY uses DESC
            """) as cursor:
                rows = await cursor.fetchall()
                stats['by_template'] = {
                    row['template_name']: {
                        'uses': row['uses'],
                        'successes': row['successes'],
                        'success_rate': row['successes'] / row['uses'] if row['uses'] > 0 else 0.0
                    }
                    for row in rows
                }

            async with self.conn.execute("""
                SELECT phase, COUNT(*) as count
                FROM template_usage
                GROUP BY phase
            """) as cursor:
                stats['by_phase'] = {row['phase']: row['count'] for row in await cursor.fetchall()}

        return stats

    # ========== CAHIER DES CHARGES OPERATIONS ==========

    async def create_cahier(
        self,
        cahier_id: str,
        domain: str,
        file_path: str,
        task_id: Optional[str] = None,
        analyst_agent_id: Optional[str] = None,
        content_hash: Optional[str] = None
    ) -> None:
        """
        Create a new cahier des charges record.

        Args:
            cahier_id: Unique identifier for the cahier
            domain: Domain name (e.g., "Security", "API")
            file_path: Path to the markdown file
            task_id: Optional task ID this cahier is for
            analyst_agent_id: Optional agent ID that created this cahier
            content_hash: Optional hash of the content for change tracking
        """
        await self.conn.execute("""
            INSERT INTO cahiers_charges
            (cahier_id, domain, task_id, analyst_agent_id, file_path, content_hash)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (cahier_id, domain, task_id, analyst_agent_id, file_path, content_hash))

        await self.conn.commit()

    async def get_cahier(self, cahier_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a cahier des charges by ID.

        Args:
            cahier_id: Cahier ID

        Returns:
            Cahier record or None
        """
        async with self.conn.execute(
            "SELECT * FROM cahiers_charges WHERE cahier_id = ?", (cahier_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_cahiers_by_domain(self, domain: str) -> List[Dict[str, Any]]:
        """
        Get all cahiers for a specific domain.

        Args:
            domain: Domain name

        Returns:
            List of cahier records
        """
        async with self.conn.execute(
            "SELECT * FROM cahiers_charges WHERE domain = ? ORDER BY created_at",
            (domain,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_cahier_for_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the cahier des charges for a specific task.

        Args:
            task_id: Task ID

        Returns:
            Cahier record or None
        """
        async with self.conn.execute(
            "SELECT * FROM cahiers_charges WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
            (task_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_all_cahiers(self) -> List[Dict[str, Any]]:
        """
        Get all cahiers des charges.

        Returns:
            List of all cahier records
        """
        async with self.conn.execute(
            "SELECT * FROM cahiers_charges ORDER BY domain, created_at"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def load_cahier_content(self, cahier_id: str) -> Optional[str]:
        """
        Load the markdown content of a cahier des charges.

        Args:
            cahier_id: Cahier ID

        Returns:
            Markdown content or None
        """
        cahier = await self.get_cahier(cahier_id)
        if not cahier or not cahier.get('file_path'):
            return None

        try:
            file_path = Path(cahier['file_path'])
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
        except IOError as e:
            print(f"Error loading cahier {cahier_id}: {e}")

        return None

    # ========== GEMINI RESEARCH OPERATIONS ==========

    async def create_gemini_research(
        self,
        query: str,
        cahier_id: Optional[str] = None,
        results: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Create a Gemini research record.

        Args:
            query: Search query
            cahier_id: Optional cahier ID this research is for
            results: Optional results from Gemini

        Returns:
            Research ID
        """
        results_json = json.dumps(results) if results else None

        cursor = await self.conn.execute("""
            INSERT INTO gemini_research (cahier_id, query, results)
            VALUES (?, ?, ?)
        """, (cahier_id, query, results_json))

        await self.conn.commit()
        return cursor.lastrowid

    async def update_gemini_research(
        self,
        research_id: int,
        results: Dict[str, Any]
    ) -> None:
        """
        Update Gemini research results.

        Args:
            research_id: Research ID
            results: Results from Gemini
        """
        results_json = json.dumps(results)

        await self.conn.execute("""
            UPDATE gemini_research
            SET results = ?
            WHERE research_id = ?
        """, (results_json, research_id))

        await self.conn.commit()

    async def get_gemini_research(self, research_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a Gemini research record by ID.

        Args:
            research_id: Research ID

        Returns:
            Research record or None
        """
        async with self.conn.execute(
            "SELECT * FROM gemini_research WHERE research_id = ?", (research_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                result = dict(row)
                # Parse results JSON
                if result.get('results'):
                    result['results'] = json.loads(result['results'])
                return result
            return None

    async def get_research_for_cahier(self, cahier_id: str) -> List[Dict[str, Any]]:
        """
        Get all research records for a specific cahier.

        Args:
            cahier_id: Cahier ID

        Returns:
            List of research records
        """
        async with self.conn.execute(
            "SELECT * FROM gemini_research WHERE cahier_id = ? ORDER BY created_at",
            (cahier_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            results = [dict(row) for row in rows]

            # Parse results JSON for each
            for result in results:
                if result.get('results'):
                    result['results'] = json.loads(result['results'])

            return results
