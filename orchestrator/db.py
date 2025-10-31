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
    SPEC_READY = "spec_ready"           # Spec created by analyst
    DISPATCHED = "dispatched"           # Worktree created, agents assigned
    CODE_DONE = "code_done"             # Coder finished
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
                role TEXT NOT NULL,  -- 'coder', 'verifier', 'tester'
                template_name TEXT NOT NULL,  -- Name from ~/.claude/agents/
                status TEXT NOT NULL DEFAULT 'created',
                result TEXT,  -- JSON output from agent
                error_message TEXT,
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

            -- Indexes for performance
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_agents_task ON agents(task_id);
            CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
            CREATE INDEX IF NOT EXISTS idx_validations_task ON validations(task_id);
        """)

        await self.conn.commit()

    async def close(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()

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
        template_name: str
    ) -> None:
        """Create a new agent record"""
        await self.conn.execute("""
            INSERT INTO agents (agent_id, task_id, role, template_name)
            VALUES (?, ?, ?, ?)
        """, (agent_id, task_id, role, template_name))

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
