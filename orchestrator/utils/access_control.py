"""
Access Control Module for Blueprint Generative Agent Pipeline

This module provides granular file and directory access control for agents,
preventing conflicts between concurrent tasks and enforcing security policies.

Key Features:
- File/directory access validation with glob pattern support
- Automatic conflict detection between active tasks
- Path traversal prevention
- Exclusion priority over inclusion
- Comprehensive logging of access attempts
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from enum import Enum
import fnmatch


class AccessMode(Enum):
    """Access control enforcement modes."""
    BLOCK = "block"      # Raise error on violation
    LOG = "log"          # Log warning and continue
    ASK = "ask"          # Request human validation


class AccessDecision(Enum):
    """Access validation decision types."""
    ALLOWED = "allowed"
    DENIED_EXCLUDED = "denied_excluded"
    DENIED_NOT_IN_ALLOW = "denied_not_in_allow"
    DENIED_PATH_TRAVERSAL = "denied_path_traversal"
    DENIED_CONFLICT = "denied_conflict"


class AccessViolation(Exception):
    """Raised when file access is denied."""
    pass


class AccessControlManager:
    """
    Manages file access control for agent tasks.

    Validates file operations against allow/exclude rules with glob pattern support.
    Enforces exclusion priority: if a path matches both allow and exclude, it's denied.
    """

    def __init__(
        self,
        access_config: Optional[Dict[str, List[str]]] = None,
        worktree_path: Optional[Path] = None,
        mode: AccessMode = AccessMode.BLOCK
    ):
        """
        Initialize the access control manager.

        Args:
            access_config: Dict with 'allow' and 'exclude' keys containing path patterns
            worktree_path: Root path of the worktree (for path normalization)
            mode: Enforcement mode (BLOCK, LOG, or ASK)
        """
        self.access_config = access_config or {}
        self.allow_patterns = self.access_config.get('allow', [])
        self.exclude_patterns = self.access_config.get('exclude', [])
        self.worktree_path = Path(worktree_path) if worktree_path else Path.cwd()
        self.mode = mode

        # If no allow patterns specified, allow everything (unless excluded)
        self.allow_all = len(self.allow_patterns) == 0

    def validate_file_access(
        self,
        file_path: str | Path,
        operation: str = "write"
    ) -> Tuple[AccessDecision, str]:
        """
        Validate if access to a file/directory is permitted.

        Args:
            file_path: Path to validate
            operation: Type of operation (for logging)

        Returns:
            Tuple of (AccessDecision, reason_message)

        Raises:
            AccessViolation: If access is denied and mode is BLOCK
        """
        # Normalize and secure the path
        try:
            normalized_path = self._normalize_path(file_path)
        except ValueError as e:
            decision = AccessDecision.DENIED_PATH_TRAVERSAL
            reason = f"Path traversal detected: {e}"
            return self._handle_decision(decision, reason, file_path, operation)

        # Convert to relative path from worktree for pattern matching
        try:
            relative_path = normalized_path.relative_to(self.worktree_path)
        except ValueError:
            # Path is outside worktree
            decision = AccessDecision.DENIED_PATH_TRAVERSAL
            reason = f"Path outside worktree: {normalized_path}"
            return self._handle_decision(decision, reason, file_path, operation)

        # Check exclusions first (priority over allows)
        if self._is_excluded(relative_path):
            decision = AccessDecision.DENIED_EXCLUDED
            reason = f"Path matches exclusion pattern"
            return self._handle_decision(decision, reason, file_path, operation)

        # Check if allowed
        if self.allow_all or self._is_allowed(relative_path):
            return (AccessDecision.ALLOWED, "Access granted")

        # Not in allow list
        decision = AccessDecision.DENIED_NOT_IN_ALLOW
        reason = f"Path not in allow list"
        return self._handle_decision(decision, reason, file_path, operation)

    def _handle_decision(
        self,
        decision: AccessDecision,
        reason: str,
        file_path: str | Path,
        operation: str
    ) -> Tuple[AccessDecision, str]:
        """Handle an access decision based on the mode."""
        if decision != AccessDecision.ALLOWED:
            full_message = f"Access {decision.name} for {operation} on '{file_path}': {reason}"

            if self.mode == AccessMode.BLOCK:
                raise AccessViolation(full_message)
            elif self.mode == AccessMode.LOG:
                # In LOG mode, just return the decision (caller will log)
                pass
            elif self.mode == AccessMode.ASK:
                # In ASK mode, caller should request human validation
                pass

        return (decision, reason)

    def _normalize_path(self, file_path: str | Path) -> Path:
        """
        Normalize and validate a file path to prevent security issues.

        Args:
            file_path: Path to normalize

        Returns:
            Normalized absolute Path

        Raises:
            ValueError: If path contains dangerous patterns
        """
        path = Path(file_path)

        # Check for path traversal attempts
        parts = path.parts
        if '..' in parts:
            raise ValueError(f"Path traversal detected: {file_path}")

        # Resolve to absolute path
        if not path.is_absolute():
            path = self.worktree_path / path

        # Resolve symlinks and normalize
        try:
            path = path.resolve()
        except (OSError, RuntimeError) as e:
            raise ValueError(f"Cannot resolve path {file_path}: {e}")

        return path

    def _is_excluded(self, relative_path: Path) -> bool:
        """
        Check if a path matches any exclusion pattern.

        Args:
            relative_path: Path relative to worktree

        Returns:
            True if path should be excluded
        """
        path_str = str(relative_path).replace('\\', '/')

        for pattern in self.exclude_patterns:
            if self._matches_pattern(path_str, pattern):
                return True

        return False

    def _is_allowed(self, relative_path: Path) -> bool:
        """
        Check if a path matches any allow pattern.

        Args:
            relative_path: Path relative to worktree

        Returns:
            True if path is in allow list
        """
        path_str = str(relative_path).replace('\\', '/')

        for pattern in self.allow_patterns:
            if self._matches_pattern(path_str, pattern):
                return True

        return False

    def _matches_pattern(self, path: str, pattern: str) -> bool:
        """
        Check if a path matches a pattern (supports glob patterns).

        Args:
            path: Normalized path string (with forward slashes)
            pattern: Pattern to match against (may include *, **, ?)

        Returns:
            True if path matches pattern
        """
        # Normalize pattern to use forward slashes
        pattern = pattern.replace('\\', '/')

        # Remove trailing slash from pattern for consistency
        pattern = pattern.rstrip('/')
        path = path.rstrip('/')

        # If pattern is a directory (doesn't end with file extension), match directory and contents
        if '.' not in pattern.split('/')[-1]:
            # Directory pattern - match if path starts with it
            if path.startswith(pattern + '/') or path == pattern:
                return True

        # Use fnmatch for glob pattern matching
        if fnmatch.fnmatch(path, pattern):
            return True

        # Also check if path is inside a matched directory
        if fnmatch.fnmatch(path, pattern + '/*'):
            return True

        # Support for ** (recursive glob)
        if '**' in pattern:
            # Convert ** pattern to regex
            regex_pattern = pattern.replace('**', '.*').replace('*', '[^/]*').replace('?', '.')
            if re.match(f'^{regex_pattern}$', path):
                return True

        return False

    def detect_conflicts(
        self,
        db,
        current_task_id: str
    ) -> List[Dict[str, Any]]:
        """
        Detect access conflicts with other active tasks.

        Scans all active tasks (not completed/error) and checks for overlapping
        file access permissions.

        Args:
            db: Database instance
            current_task_id: ID of the current task

        Returns:
            List of conflict dictionaries with:
                - task_id: Conflicting task ID
                - conflicting_paths: List of overlapping paths
                - severity: 'high' or 'medium'
        """
        conflicts = []

        # Get all active tasks except current one
        active_tasks = db.get_active_tasks(exclude_task_id=current_task_id)

        for task in active_tasks:
            # Load task spec to get its access config
            spec = db.get_task_spec(task['task_id'])
            if not spec or 'access' not in spec:
                continue

            other_access = spec['access']
            other_allow = other_access.get('allow', [])

            # Check for overlaps
            overlaps = self._find_overlapping_patterns(
                self.allow_patterns,
                other_allow
            )

            if overlaps:
                conflicts.append({
                    'task_id': task['task_id'],
                    'conflicting_paths': overlaps,
                    'severity': 'high' if len(overlaps) > 3 else 'medium'
                })

        return conflicts

    def _find_overlapping_patterns(
        self,
        patterns_a: List[str],
        patterns_b: List[str]
    ) -> List[str]:
        """
        Find overlapping patterns between two lists.

        Args:
            patterns_a: First list of patterns
            patterns_b: Second list of patterns

        Returns:
            List of overlapping pattern strings
        """
        overlaps = []

        for pattern_a in patterns_a:
            for pattern_b in patterns_b:
                # Normalize patterns
                norm_a = pattern_a.replace('\\', '/').rstrip('/')
                norm_b = pattern_b.replace('\\', '/').rstrip('/')

                # Check for exact match
                if norm_a == norm_b:
                    overlaps.append(norm_a)
                    continue

                # Check for hierarchical overlap (one is parent of other)
                if norm_a.startswith(norm_b + '/') or norm_b.startswith(norm_a + '/'):
                    overlaps.append(f"{norm_a} ↔ {norm_b}")
                    continue

                # Check for glob pattern overlap (complex case - simplified)
                if '*' in norm_a or '*' in norm_b:
                    # If patterns share the same base directory, consider potential overlap
                    base_a = norm_a.split('*')[0].rstrip('/')
                    base_b = norm_b.split('*')[0].rstrip('/')
                    if base_a and base_b and (base_a.startswith(base_b) or base_b.startswith(base_a)):
                        overlaps.append(f"{norm_a} ↔ {norm_b}")

        return overlaps

    def generate_exclusions_from_conflicts(
        self,
        conflicts: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Generate exclusion patterns to avoid detected conflicts.

        Args:
            conflicts: List of conflicts from detect_conflicts()

        Returns:
            List of exclusion patterns to add
        """
        exclusions = []

        for conflict in conflicts:
            for path in conflict['conflicting_paths']:
                # Extract actual paths from overlap notation
                if '↔' in path:
                    parts = path.split('↔')
                    exclusions.extend([p.strip() for p in parts])
                else:
                    exclusions.append(path)

        return list(set(exclusions))  # Remove duplicates


def merge_access_configs(
    spec_access: Optional[Dict[str, List[str]]],
    template_access: Optional[Dict[str, List[str]]]
) -> Dict[str, List[str]]:
    """
    Merge access configurations from task spec and agent template.

    Template access serves as base restrictions (applies to all tasks using that template).
    Spec access provides task-specific overrides.

    Merging rules:
    - Allows are UNION of both (template_allow ∪ spec_allow)
    - Excludes are UNION of both (template_exclude ∪ spec_exclude)
    - If spec has no allow list, use template's
    - If spec has no exclude list, use template's

    Args:
        spec_access: Access config from task spec
        template_access: Access config from agent template

    Returns:
        Merged access configuration
    """
    merged = {
        'allow': [],
        'exclude': []
    }

    # Merge allow lists (union)
    if spec_access and 'allow' in spec_access:
        merged['allow'].extend(spec_access['allow'])
    if template_access and 'allow' in template_access:
        merged['allow'].extend(template_access['allow'])

    # Remove duplicates while preserving order
    merged['allow'] = list(dict.fromkeys(merged['allow']))

    # Merge exclude lists (union)
    if spec_access and 'exclude' in spec_access:
        merged['exclude'].extend(spec_access['exclude'])
    if template_access and 'exclude' in template_access:
        merged['exclude'].extend(template_access['exclude'])

    # Remove duplicates while preserving order
    merged['exclude'] = list(dict.fromkeys(merged['exclude']))

    return merged
