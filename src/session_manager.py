"""Session management utilities for Claude Code."""

import builtins
import os
import re
import shutil
from pathlib import Path
from typing import Any

from .config import (
    OPTIONAL_PROJECT_FILES,
    REQUIRED_PROJECT_FILES,
)
from .prompt_templates import PromptTemplater


def parse_build_plan_version(build_plan_path: Path) -> str | None:
    """Parse version from BUILD_PLAN.md YAML frontmatter.

    The BUILD_PLAN.md file may contain YAML frontmatter at the top:

    ---
    version: "1.0.0"
    ---

    Args:
        build_plan_path: Path to BUILD_PLAN.md file

    Returns:
        Version string if found, None otherwise
    """
    if not build_plan_path.exists():
        return None

    try:
        content = build_plan_path.read_text(encoding="utf-8")

        # Check for YAML frontmatter (starts with --- on first line)
        if not content.startswith("---"):
            return None

        # Find the closing ---
        lines = content.split("\n")
        end_index = None
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_index = i
                break

        if end_index is None:
            return None

        # Parse YAML frontmatter
        frontmatter = "\n".join(lines[1:end_index])

        # Simple regex-based parsing for version field
        # Handles: version: "1.0.0" or version: 1.0.0 or version: '1.0.0'
        version_match = re.search(
            r'^version:\s*["\']?([^"\'\n]+)["\']?\s*$',
            frontmatter,
            re.MULTILINE,
        )

        if version_match:
            return version_match.group(1).strip()

        return None

    except Exception as e:
        builtins.print(f"⚠️ Error parsing BUILD_PLAN.md version: {e}")
        return None


class SessionManager:
    """Manages Claude Code session utilities."""

    @staticmethod
    def get_project_prompts_dir(current_dir: str, project_name: str | None) -> str:
        """Get the prompts directory for a project.

        Args:
            current_dir: Current working directory
            project_name: Name of the project, None for default

        Returns:
            Path to the prompts directory

        Raises:
            FileNotFoundError: If project directory doesn't exist
            ValueError: If required project files are missing
        """
        if project_name:
            project_prompts_dir = Path(f"{current_dir}/prompts/{project_name}")
            if not project_prompts_dir.exists():
                raise FileNotFoundError(
                    f"Project prompts directory not found: {project_prompts_dir}"
                )

            # Validate required files exist
            for required_file in REQUIRED_PROJECT_FILES:
                if not (project_prompts_dir / required_file).exists():
                    raise ValueError(
                        f"Project '{project_name}' missing required file: {required_file}"
                    )

            # Check for optional files and warn if missing
            for optional_file in OPTIONAL_PROJECT_FILES:
                if not (project_prompts_dir / optional_file).exists():
                    builtins.print(f"⚠️  Optional file not found: {optional_file}")

            return str(project_prompts_dir)
        else:
            # Use default prompts directory
            return f"{current_dir}/prompts"

    @staticmethod
    def list_available_projects(current_dir: str) -> list[str]:
        """List all available projects.

        Args:
            current_dir: Current working directory

        Returns:
            List of project names
        """
        prompts_dir = Path(f"{current_dir}/prompts")
        if not prompts_dir.exists():
            return []

        projects = []
        for item in prompts_dir.iterdir():
            if item.is_dir():
                # Check if it has required files
                has_required = all(
                    (item / req_file).exists() for req_file in REQUIRED_PROJECT_FILES
                )
                if has_required:
                    projects.append(item.name)

        return projects

    @staticmethod
    def setup_session_prompts(
        generation_dir: Path,
        prompts_dir: str,
        template_vars: dict[str, Any],
        bootstrap_files: bool = False,
    ) -> None:
        """Copy and template prompts for a session.

        Args:
            generation_dir: Session directory
            prompts_dir: Source prompts directory
            template_vars: Template variables for substitution
            bootstrap_files: If True, copy reference implementation files
        """
        # Copy prompts directory into generation for reference and apply templating
        prompts_dest = generation_dir / "prompts"
        PromptTemplater.copy_with_templating(
            Path(prompts_dir), prompts_dest, template_vars
        )

        # Override with the generic system prompt from top-level prompts directory
        top_level_prompts_dir = Path(prompts_dir).parent
        generic_system_prompt_path = top_level_prompts_dir / "system_prompt.txt"
        dest_system_prompt_path = prompts_dest / "system_prompt.txt"

        if generic_system_prompt_path.exists():
            # Copy the generic system prompt (no templating needed since it has no variables)
            shutil.copy2(generic_system_prompt_path, dest_system_prompt_path)
            builtins.print(
                "📄 Using generic system prompt from top-level prompts directory"
            )
        else:
            builtins.print(
                "⚠️  Generic system prompt not found, using project-specific one"
            )

        builtins.print("📄 Copied prompts directory for reference with port templating")

        # Copy bootstrap files if requested
        if bootstrap_files:
            SessionManager._copy_bootstrap_files(generation_dir)

    @staticmethod
    def _copy_bootstrap_files(generation_dir: Path) -> None:
        """Copy reference implementation files into project for agent to study.

        Args:
            generation_dir: Session directory
        """
        # Determine repo root (where agent.py lives)
        repo_root = Path(__file__).parent.parent.resolve()

        # Create reference directory
        reference_dir = generation_dir / "reference"
        reference_dir.mkdir(exist_ok=True)

        builtins.print("\n🔧 Copying bootstrap/reference files:")

        # Copy agent.py
        src_file = repo_root / "agent.py"
        if src_file.exists():
            shutil.copy2(src_file, reference_dir / "agent.py")
            builtins.print("  ✓ agent.py")
        else:
            builtins.print(f"  ⚠️  agent.py not found at {src_file}")

        # Copy src/ directory
        src_dir = repo_root / "src"
        if src_dir.exists():
            dest_src = reference_dir / "src"
            if dest_src.exists():
                shutil.rmtree(dest_src)
            shutil.copytree(src_dir, dest_src)
            builtins.print("  ✓ src/ directory")
        else:
            builtins.print(f"  ⚠️  src/ directory not found at {src_dir}")

        # Copy prompt_template.txt
        prompt_template = repo_root / "prompt_template.txt"
        if prompt_template.exists():
            shutil.copy2(prompt_template, reference_dir / "prompt_template.txt")
            builtins.print("  ✓ prompt_template.txt")
        else:
            builtins.print("  ⚠️  prompt_template.txt not found")

        # Copy top-level prompts/system_prompt.txt
        system_prompt = repo_root / "prompts" / "system_prompt.txt"
        if system_prompt.exists():
            shutil.copy2(system_prompt, reference_dir / "system_prompt.txt")
            builtins.print("  ✓ prompts/system_prompt.txt")
        else:
            builtins.print("  ⚠️  system_prompt.txt not found")

        builtins.print(
            f"\n📦 Reference files copied to: {reference_dir.relative_to(generation_dir.parent.parent)}"
        )
        builtins.print(
            "   Agent can now study and use these files as reference implementation\n"
        )

    @staticmethod
    def initialize_git_repo(generation_dir: Path) -> None:
        """Initialize git repository for new session.

        Delegates to GitManager which handles:
        - Checking if already inside a git repo (GitHub mode)
        - Running git init or skipping appropriately
        - Configuring git user.name and user.email
        - Setting npm registry

        Args:
            generation_dir: Session directory
        """
        from .git_manager import GitManager

        os.chdir(generation_dir)

        git_manager = GitManager(work_dir=generation_dir, mode="local")
        git_manager.initialize_repo()
