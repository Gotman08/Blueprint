"""
Git Helper - Manages git worktrees, branches, and merges.

This module provides utilities for creating isolated worktrees for parallel
development, managing branches, and handling merges with conflict resolution.
"""

import asyncio
from pathlib import Path
from typing import Optional, List, Tuple
from git import Repo, GitCommandError
from git.exc import InvalidGitRepositoryError


class GitHelper:
    """Manages git operations for the pipeline"""

    def __init__(self, repo_path: str):
        """
        Initialize git helper.

        Args:
            repo_path: Path to the main git repository

        Raises:
            InvalidGitRepositoryError: If path is not a git repository
        """
        self.repo_path = Path(repo_path)
        try:
            self.repo = Repo(self.repo_path)
        except InvalidGitRepositoryError:
            raise InvalidGitRepositoryError(f"Not a git repository: {repo_path}")

        self.worktrees_dir = self.repo_path / ".worktrees"
        self.worktrees_dir.mkdir(exist_ok=True)

    def _run_git_command(self, *args) -> str:
        """
        Execute a git command and return output.

        Args:
            *args: Git command arguments

        Returns:
            Command output as string

        Raises:
            GitCommandError: If command fails
        """
        return self.repo.git.execute(args)

    async def create_worktree(self, task_id: str, base_branch: str = "main") -> Tuple[str, str]:
        """
        Create a new git worktree for isolated development.

        Args:
            task_id: Task identifier (e.g., 'TASK-101')
            base_branch: Branch to base the new branch on (default: 'main')

        Returns:
            Tuple of (branch_name, worktree_path)

        Raises:
            GitCommandError: If worktree creation fails
        """
        branch_name = f"feature/{task_id}"
        worktree_path = self.worktrees_dir / task_id

        # Ensure we're on the base branch and up to date
        self.repo.git.checkout(base_branch)

        # Create worktree with new branch
        try:
            self._run_git_command(
                "worktree", "add",
                "-b", branch_name,
                str(worktree_path),
                base_branch
            )
        except GitCommandError as e:
            # If branch already exists, use it
            if "already exists" in str(e):
                self._run_git_command(
                    "worktree", "add",
                    str(worktree_path),
                    branch_name
                )
            else:
                raise

        return branch_name, str(worktree_path)

    async def remove_worktree(self, task_id: str, force: bool = False) -> None:
        """
        Remove a worktree and optionally delete its branch.

        Args:
            task_id: Task identifier
            force: Force removal even with uncommitted changes

        Raises:
            GitCommandError: If removal fails
        """
        worktree_path = self.worktrees_dir / task_id

        if not worktree_path.exists():
            return  # Already removed

        # Remove worktree
        args = ["worktree", "remove", str(worktree_path)]
        if force:
            args.append("--force")

        try:
            self._run_git_command(*args)
        except GitCommandError as e:
            if not force:
                # Retry with force
                await self.remove_worktree(task_id, force=True)
            else:
                raise

    async def delete_branch(self, branch_name: str, force: bool = False) -> None:
        """
        Delete a git branch.

        Args:
            branch_name: Name of branch to delete
            force: Force deletion even if not merged

        Raises:
            GitCommandError: If deletion fails
        """
        flag = "-D" if force else "-d"

        try:
            self._run_git_command("branch", flag, branch_name)
        except GitCommandError as e:
            if "not found" not in str(e):
                raise

    async def commit_changes(
        self,
        worktree_path: str,
        message: str,
        author_name: Optional[str] = None,
        author_email: Optional[str] = None
    ) -> str:
        """
        Commit changes in a worktree.

        Args:
            worktree_path: Path to the worktree
            message: Commit message
            author_name: Optional author name
            author_email: Optional author email

        Returns:
            Commit SHA

        Raises:
            GitCommandError: If commit fails
        """
        worktree_repo = Repo(worktree_path)

        # Stage all changes
        worktree_repo.git.add(A=True)

        # Check if there are changes to commit
        if not worktree_repo.is_dirty() and not worktree_repo.untracked_files:
            raise ValueError("No changes to commit")

        # Prepare commit kwargs
        commit_kwargs = {}
        if author_name and author_email:
            commit_kwargs['author'] = f"{author_name} <{author_email}>"

        # Commit
        commit = worktree_repo.index.commit(message, **commit_kwargs)

        return commit.hexsha

    async def push_branch(self, branch_name: str, remote: str = "origin") -> None:
        """
        Push a branch to remote.

        Args:
            branch_name: Name of branch to push
            remote: Remote name (default: 'origin')

        Raises:
            GitCommandError: If push fails
        """
        try:
            self.repo.git.push(remote, branch_name, set_upstream=True)
        except GitCommandError as e:
            # If remote doesn't exist, skip (for local testing)
            if "does not appear to be a git repository" in str(e):
                pass  # No remote configured, skip
            else:
                raise

    async def merge_branch(
        self,
        branch_name: str,
        target_branch: str = "main",
        strategy: str = "recursive"
    ) -> Tuple[bool, Optional[str]]:
        """
        Merge a branch into target branch.

        Args:
            branch_name: Branch to merge
            target_branch: Target branch (default: 'main')
            strategy: Merge strategy (default: 'recursive')

        Returns:
            Tuple of (success, error_message)
            success: True if merge succeeded, False if conflicts
            error_message: None if success, conflict details if failed
        """
        # Checkout target branch
        self.repo.git.checkout(target_branch)

        # Pull latest changes
        try:
            self.repo.git.pull()
        except GitCommandError:
            pass  # No remote or no changes

        # Attempt merge
        try:
            self.repo.git.merge(branch_name, strategy=strategy)
            return True, None
        except GitCommandError as e:
            # Check if it's a conflict
            if "CONFLICT" in str(e) or "conflict" in str(e).lower():
                # CRITICAL: Abort the merge immediately to keep repo clean
                try:
                    self.repo.git.merge('--abort')
                except GitCommandError:
                    # Merge might already be aborted or in a state where abort fails
                    # This is non-critical, log but continue
                    pass

                # Get conflict details (after abort, conflicts may not be visible, so we get them from the error)
                conflicts = self.get_merge_conflicts()
                if not conflicts:
                    # If get_merge_conflicts returns empty (because we aborted), parse from error message
                    conflicts = ["Check git log for conflict details"]

                conflict_msg = f"Merge conflicts detected. Merge aborted to keep repository clean.\nConflicting files:\n" + "\n".join(f"  - {f}" for f in conflicts)
                return False, conflict_msg
            else:
                # Other error - also try to abort if in merge state
                try:
                    self.repo.git.merge('--abort')
                except GitCommandError:
                    pass
                return False, str(e)

    def get_merge_conflicts(self) -> List[str]:
        """
        Get list of files with merge conflicts.

        Returns:
            List of file paths with conflicts
        """
        try:
            # Files with conflicts have 'U' status
            status = self.repo.git.status(porcelain=True)
            conflicts = []

            for line in status.split('\n'):
                if line.startswith('UU') or line.startswith('AA'):
                    # Extract filename
                    filename = line[3:].strip()
                    conflicts.append(filename)

            return conflicts
        except GitCommandError:
            return []

    async def resolve_conflicts_auto(self, strategy: str = "ours") -> bool:
        """
        Attempt automatic conflict resolution.

        Args:
            strategy: Resolution strategy ('ours', 'theirs')

        Returns:
            True if all conflicts resolved, False otherwise
        """
        conflicts = self.get_merge_conflicts()

        if not conflicts:
            return True

        for file_path in conflicts:
            try:
                if strategy == "ours":
                    # Keep our version
                    self.repo.git.checkout("--ours", file_path)
                elif strategy == "theirs":
                    # Keep their version
                    self.repo.git.checkout("--theirs", file_path)
                else:
                    return False

                # Stage the resolved file
                self.repo.git.add(file_path)
            except GitCommandError:
                return False

        # Check if all resolved
        return len(self.get_merge_conflicts()) == 0

    async def complete_merge(self, message: Optional[str] = None) -> str:
        """
        Complete a merge after conflict resolution.

        Args:
            message: Optional merge commit message

        Returns:
            Commit SHA

        Raises:
            ValueError: If there are unresolved conflicts
        """
        if self.get_merge_conflicts():
            raise ValueError("Cannot complete merge: unresolved conflicts remain")

        # Commit the merge
        if message:
            commit = self.repo.index.commit(message)
        else:
            commit = self.repo.index.commit()  # Use default merge message

        return commit.hexsha

    def get_diff(self, branch_name: str, base_branch: str = "main") -> str:
        """
        Get diff between a branch and base branch.

        Args:
            branch_name: Branch to compare
            base_branch: Base branch (default: 'main')

        Returns:
            Diff output as string
        """
        return self.repo.git.diff(f"{base_branch}...{branch_name}")

    def get_changed_files(self, branch_name: str, base_branch: str = "main") -> List[str]:
        """
        Get list of files changed in a branch.

        Args:
            branch_name: Branch to check
            base_branch: Base branch (default: 'main')

        Returns:
            List of changed file paths
        """
        diff_output = self.repo.git.diff(
            f"{base_branch}...{branch_name}",
            name_only=True
        )

        return [f.strip() for f in diff_output.split('\n') if f.strip()]

    async def cleanup_merged_branch(self, task_id: str, branch_name: str) -> None:
        """
        Clean up after successful merge: remove worktree and branch.

        Args:
            task_id: Task identifier
            branch_name: Branch name to delete
        """
        # Remove worktree
        await self.remove_worktree(task_id, force=True)

        # Delete branch
        await self.delete_branch(branch_name, force=False)

    def is_branch_merged(self, branch_name: str, target_branch: str = "main") -> bool:
        """
        Check if a branch has been merged into target.

        Args:
            branch_name: Branch to check
            target_branch: Target branch (default: 'main')

        Returns:
            True if merged, False otherwise
        """
        try:
            # List branches merged into target
            merged = self.repo.git.branch(merged=target_branch)
            return branch_name in merged
        except GitCommandError:
            return False

    def get_current_branch(self) -> str:
        """Get name of current branch"""
        return self.repo.active_branch.name

    def get_commit_info(self, commit_sha: str) -> dict:
        """
        Get information about a commit.

        Args:
            commit_sha: Commit SHA

        Returns:
            Dictionary with commit info
        """
        commit = self.repo.commit(commit_sha)

        return {
            'sha': commit.hexsha,
            'author': str(commit.author),
            'email': commit.author.email,
            'message': commit.message,
            'date': commit.committed_datetime.isoformat(),
            'files_changed': len(commit.stats.files)
        }
