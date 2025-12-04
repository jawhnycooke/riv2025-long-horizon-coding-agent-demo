"""Tests for src/session_manager.py - Session management utilities."""

import os
from pathlib import Path

import pytest

from src.session_manager import parse_build_plan_version


class TestParseBuildPlanVersion:
    """Tests for parse_build_plan_version function."""

    def test_parse_version_with_quoted_string(self, tmp_path: Path) -> None:
        """Version in double quotes is parsed correctly."""
        build_plan = tmp_path / "BUILD_PLAN.md"
        build_plan.write_text('---\nversion: "1.2.3"\n---\n\n# Content here')

        version = parse_build_plan_version(build_plan)
        assert version == "1.2.3"

    def test_parse_version_with_single_quotes(self, tmp_path: Path) -> None:
        """Version in single quotes is parsed correctly."""
        build_plan = tmp_path / "BUILD_PLAN.md"
        build_plan.write_text("---\nversion: '2.0.0'\n---\n\n# Content here")

        version = parse_build_plan_version(build_plan)
        assert version == "2.0.0"

    def test_parse_version_unquoted(self, tmp_path: Path) -> None:
        """Version without quotes is parsed correctly."""
        build_plan = tmp_path / "BUILD_PLAN.md"
        build_plan.write_text("---\nversion: 3.1.4\n---\n\n# Content here")

        version = parse_build_plan_version(build_plan)
        assert version == "3.1.4"

    def test_parse_version_with_other_frontmatter(self, tmp_path: Path) -> None:
        """Version is parsed when other frontmatter fields are present."""
        build_plan = tmp_path / "BUILD_PLAN.md"
        build_plan.write_text(
            '---\ntitle: "My Project"\nversion: "1.0.0"\nauthor: "Test"\n---\n\n# Content'
        )

        version = parse_build_plan_version(build_plan)
        assert version == "1.0.0"

    def test_no_frontmatter_returns_none(self, tmp_path: Path) -> None:
        """File without YAML frontmatter returns None."""
        build_plan = tmp_path / "BUILD_PLAN.md"
        build_plan.write_text("# Build Plan\n\nNo frontmatter here.")

        version = parse_build_plan_version(build_plan)
        assert version is None

    def test_frontmatter_without_version_returns_none(self, tmp_path: Path) -> None:
        """Frontmatter without version field returns None."""
        build_plan = tmp_path / "BUILD_PLAN.md"
        build_plan.write_text('---\ntitle: "My Project"\nauthor: "Test"\n---\n\n# Content')

        version = parse_build_plan_version(build_plan)
        assert version is None

    def test_nonexistent_file_returns_none(self, tmp_path: Path) -> None:
        """Nonexistent file returns None."""
        build_plan = tmp_path / "nonexistent.md"

        version = parse_build_plan_version(build_plan)
        assert version is None

    def test_unclosed_frontmatter_returns_none(self, tmp_path: Path) -> None:
        """Frontmatter without closing --- returns None."""
        build_plan = tmp_path / "BUILD_PLAN.md"
        build_plan.write_text('---\nversion: "1.0.0"\n\n# No closing ---')

        version = parse_build_plan_version(build_plan)
        assert version is None

    def test_parse_semver_with_prerelease(self, tmp_path: Path) -> None:
        """Semver with prerelease tag is parsed correctly."""
        build_plan = tmp_path / "BUILD_PLAN.md"
        build_plan.write_text('---\nversion: "2.0.0-beta.1"\n---\n\n# Content')

        version = parse_build_plan_version(build_plan)
        assert version == "2.0.0-beta.1"

    def test_parse_version_with_build_metadata(self, tmp_path: Path) -> None:
        """Semver with build metadata is parsed correctly."""
        build_plan = tmp_path / "BUILD_PLAN.md"
        build_plan.write_text('---\nversion: "1.0.0+build.123"\n---\n\n# Content')

        version = parse_build_plan_version(build_plan)
        assert version == "1.0.0+build.123"

    def test_parse_canopy_build_plan(self, tmp_path: Path) -> None:
        """Real-world canopy BUILD_PLAN.md format is parsed correctly."""
        build_plan = tmp_path / "BUILD_PLAN.md"
        build_plan.write_text(
            '---\nversion: "1.0.0"\n---\n\n<project_specification>\n  <project_name>Canopy</project_name>\n</project_specification>'
        )

        version = parse_build_plan_version(build_plan)
        assert version == "1.0.0"

    def test_version_with_extra_whitespace(self, tmp_path: Path) -> None:
        """Version with extra whitespace is trimmed."""
        build_plan = tmp_path / "BUILD_PLAN.md"
        build_plan.write_text('---\nversion:   "1.0.0"  \n---\n\n# Content')

        version = parse_build_plan_version(build_plan)
        assert version == "1.0.0"

    def test_empty_frontmatter_returns_none(self, tmp_path: Path) -> None:
        """Empty frontmatter returns None."""
        build_plan = tmp_path / "BUILD_PLAN.md"
        build_plan.write_text("---\n---\n\n# Content")

        version = parse_build_plan_version(build_plan)
        assert version is None
