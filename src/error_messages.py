"""Improved error messages for security hooks (F011).

This module provides consistent, actionable error messages that explain:
1. What action was blocked
2. Why it was blocked
3. How to fix it (suggested alternatives)

All error messages are logged to the audit trail.
"""


class SecurityErrorMessages:
    """Factory for security hook error messages.

    All methods return a dict suitable for hook responses with
    consistent formatting and actionable suggestions.
    """

    @staticmethod
    def path_outside_project(
        attempted_path: str,
        project_root: str,
        tool_name: str = "operation",
    ) -> str:
        """Generate error message for path outside project root.

        Args:
            attempted_path: The path that was attempted
            project_root: The allowed project root directory
            tool_name: Name of the tool that triggered the check

        Returns:
            Formatted error message with fix suggestions
        """
        return (
            f"🚫 PATH BLOCKED: {tool_name} denied\n\n"
            f"Attempted path: {attempted_path}\n"
            f"Allowed root:   {project_root}\n\n"
            f"The path '{attempted_path}' is outside the allowed project directory.\n\n"
            f"💡 How to fix:\n"
            f"  • Use a relative path within the project (e.g., './src/file.py')\n"
            f"  • Ensure the path starts with or resolves to: {project_root}\n"
            f"  • For reading files, check if you have the correct project context"
        )

    @staticmethod
    def no_project_root() -> str:
        """Generate error message when no project root is set.

        Returns:
            Formatted error message
        """
        return (
            "🚫 PATH BLOCKED: No project root directory set\n\n"
            "The security system requires a project root to validate paths.\n\n"
            "💡 How to fix:\n"
            "  • Ensure the agent was started with a valid project configuration\n"
            "  • Check that PROJECT_ROOT or equivalent is set in the environment"
        )

    @staticmethod
    def no_file_path(tool_name: str) -> str:
        """Generate error message when no file path is provided.

        Args:
            tool_name: Name of the tool that requires a file path

        Returns:
            Formatted error message
        """
        return (
            f"🚫 PATH BLOCKED: No file path provided for {tool_name}\n\n"
            f"The {tool_name} tool requires a file path to operate on.\n\n"
            f"💡 How to fix:\n"
            f"  • Provide a valid file_path parameter\n"
            f"  • Use an absolute path or path relative to the project root"
        )

    @staticmethod
    def command_not_allowed(
        command: str, first_word: str, allowed_commands: list[str]
    ) -> str:
        """Generate error message for command not in allowed list.

        Args:
            command: The full command that was blocked
            first_word: The command name (first word)
            allowed_commands: List of allowed commands

        Returns:
            Formatted error message with alternatives
        """
        # Group similar allowed commands for better suggestions
        dev_commands = [
            c
            for c in allowed_commands
            if c in ["npm", "npx", "node", "python", "python3", "pip"]
        ]
        git_commands = [c for c in allowed_commands if c in ["git"]]
        file_commands = [
            c for c in allowed_commands if c in ["ls", "cat", "mkdir", "touch", "cp"]
        ]

        suggestion = ""
        if first_word.startswith("sudo"):
            suggestion = (
                "  • Running as root/sudo is not permitted for security reasons\n"
            )
        elif first_word in ["curl", "wget", "fetch"]:
            suggestion = "  • For network requests, use the WebFetch tool instead\n"
        elif first_word in ["vim", "nano", "emacs"]:
            suggestion = "  • For editing files, use the Edit or Write tools instead\n"

        return (
            f"🚫 COMMAND BLOCKED: '{first_word}' not allowed\n\n"
            f"Command: {command}\n\n"
            f"The command '{first_word}' is not in the allowed list.\n\n"
            f"💡 Allowed commands include:\n"
            f"  • Development: {', '.join(dev_commands) or 'none'}\n"
            f"  • Git: {', '.join(git_commands) or 'none'}\n"
            f"  • File ops: {', '.join(file_commands[:5]) or 'none'}...\n\n"
            f"💡 How to fix:\n"
            f"{suggestion}"
            f"  • Use an allowed command from the list above\n"
            f"  • Full list: {', '.join(sorted(allowed_commands)[:15])}..."
        )

    @staticmethod
    def rm_not_allowed(command: str) -> str:
        """Generate error message for blocked rm command.

        Args:
            command: The rm command that was blocked

        Returns:
            Formatted error message
        """
        return (
            f"🚫 COMMAND BLOCKED: rm command restricted\n\n"
            f"Command: {command}\n\n"
            f"The 'rm' command is restricted to prevent accidental file deletion.\n\n"
            f"💡 Allowed rm usage:\n"
            f"  • rm -rf node_modules (to clean npm cache)\n\n"
            f"💡 How to fix:\n"
            f"  • If you need to delete files, consider if it's truly necessary\n"
            f"  • For npm issues, use: rm -rf node_modules\n"
            f"  • For other deletions, ask the user to handle it manually"
        )

    @staticmethod
    def node_not_allowed(command: str) -> str:
        """Generate error message for blocked node command.

        Args:
            command: The node command that was blocked

        Returns:
            Formatted error message
        """
        return (
            f"🚫 COMMAND BLOCKED: node command restricted\n\n"
            f"Command: {command}\n\n"
            f"Direct node execution is restricted to specific patterns.\n\n"
            f"💡 Allowed node usage:\n"
            f"  • node server.js (run the server)\n"
            f"  • node server/index.js (run server from subdirectory)\n\n"
            f"💡 How to fix:\n"
            f"  • Use 'npm run <script>' to run scripts defined in package.json\n"
            f"  • Use 'npx <tool>' to run npm packages\n"
            f"  • For testing, use: npm test or npx playwright test"
        )

    @staticmethod
    def pkill_not_allowed(command: str, allowed_patterns: list[str]) -> str:
        """Generate error message for blocked pkill command.

        Args:
            command: The pkill command that was blocked
            allowed_patterns: List of allowed pkill patterns

        Returns:
            Formatted error message
        """
        return (
            f"🚫 COMMAND BLOCKED: pkill command restricted\n\n"
            f"Command: {command}\n\n"
            f"The pkill command is restricted to specific process patterns.\n\n"
            f"💡 Allowed pkill patterns:\n"
            f"  • {chr(10).join('  ' + p for p in allowed_patterns)}\n\n"
            f"💡 How to fix:\n"
            f"  • Use one of the allowed patterns above\n"
            f"  • To stop the development server, use: pkill -f 'npm run dev'\n"
            f"  • Or use Ctrl+C in the terminal running the process"
        )

    @staticmethod
    def git_init_blocked() -> str:
        """Generate error message for blocked git init.

        Returns:
            Formatted error message
        """
        return (
            "🚫 COMMAND BLOCKED: git init not allowed\n\n"
            "Creating a new git repository would break the existing project structure.\n\n"
            "💡 How to fix:\n"
            "  • The project already has a git repository initialized\n"
            "  • Use 'git add <files>' to stage changes\n"
            "  • Use 'git commit -m \"message\"' to commit\n"
            "  • The infrastructure handles git setup automatically"
        )

    @staticmethod
    def sed_feature_list_blocked(command: str) -> str:
        """Generate error message for blocked sed on feature_list.json.

        Args:
            command: The sed command that was blocked

        Returns:
            Formatted error message
        """
        return (
            f"🚫 COMMAND BLOCKED: sed cannot modify feature_list.json\n\n"
            f"Command: {command}\n\n"
            f"Bulk modification of feature results is not allowed.\n"
            f"Each feature must be verified individually before marking as passed.\n\n"
            f"💡 How to fix:\n"
            f"  1. Run playwright-test.cjs to capture screenshot + console:\n"
            f"     node playwright-test.cjs --url http://localhost:6174 \\\n"
            f"       --test-id <feature-id> --output-dir screenshots/issue-X --operation full\n\n"
            f"  2. Read the console log to verify NO_CONSOLE_ERRORS\n"
            f"  3. Read the screenshot to verify visually\n"
            f"  4. Use the Edit tool to update that specific feature's 'passes' field\n\n"
            f"💡 Why this is required:\n"
            f"  • Prevents falsely marking features as passing\n"
            f"  • Ensures each feature is actually verified\n"
            f"  • Creates audit trail with screenshot + console evidence"
        )

    @staticmethod
    def bash_feature_list_blocked(command: str) -> str:
        """Generate error message for blocked bash command on feature_list.json.

        Args:
            command: The bash command that was blocked

        Returns:
            Formatted error message
        """
        return (
            f"🚫 COMMAND BLOCKED: Cannot modify feature_list.json via bash\n\n"
            f"Command: {command}\n\n"
            f"Using bash commands (awk, jq, python, echo, etc.) to modify feature_list.json is blocked.\n\n"
            f"💡 How to fix:\n"
            f"  1. Verify the feature actually passes by running it\n"
            f"  2. Capture screenshot + console log with playwright-test.cjs\n"
            f"  3. Read console log - verify NO_CONSOLE_ERRORS\n"
            f"  4. Read screenshot - verify visual correctness\n"
            f"  5. Use the Edit tool to update the specific feature entry\n\n"
            f"💡 Example workflow:\n"
            f"  • Capture: node playwright-test.cjs --url http://localhost:6174 \\\n"
            f"      --test-id <id> --output-dir screenshots/issue-X --operation full\n"
            f"  • Read: screenshots/issue-X/<id>-console.txt (verify NO_CONSOLE_ERRORS)\n"
            f"  • Read: screenshots/issue-X/<id>-<timestamp>.png (verify visually)\n"
            f"  • Edit: feature_list.json (change specific feature's passes: true)"
        )

    @staticmethod
    def test_no_screenshot(
        test_id: str, issue_number: str, screenshot_pattern: str
    ) -> str:
        """Generate error message when no screenshot exists for test.

        Args:
            test_id: The test ID being marked as passing
            issue_number: Current issue number
            screenshot_pattern: The glob pattern that was searched

        Returns:
            Formatted error message
        """
        return (
            f"🚫 TEST BLOCKED: No screenshot found for '{test_id}'\n\n"
            f"Pattern searched: {screenshot_pattern}\n\n"
            f"You cannot mark a test as passing without screenshot evidence.\n\n"
            f"💡 How to fix:\n"
            f"  1. Run playwright-test.cjs to capture screenshot + console:\n"
            f"     node playwright-test.cjs --url http://localhost:6174 \\\n"
            f"       --test-id {test_id} \\\n"
            f"       --output-dir screenshots/issue-{issue_number} \\\n"
            f"       --operation full\n\n"
            f"  2. Read the console log to verify NO_CONSOLE_ERRORS\n"
            f"  3. Read the screenshot to verify visually\n"
            f"  4. Then mark the test as passing"
        )

    @staticmethod
    def test_screenshot_not_viewed(test_id: str, screenshot_path: str) -> str:
        """Generate error message when screenshot exists but wasn't viewed.

        Args:
            test_id: The test ID being marked as passing
            screenshot_path: Path to the screenshot that wasn't viewed

        Returns:
            Formatted error message
        """
        return (
            f"🚫 TEST BLOCKED: Screenshot not verified for '{test_id}'\n\n"
            f"Screenshot exists: {screenshot_path}\n\n"
            f"You must view the screenshot before marking the test as passing.\n\n"
            f"💡 How to fix:\n"
            f"  1. Use the Read tool to view the screenshot:\n"
            f"     Read file: {screenshot_path}\n\n"
            f"  2. Verify the screenshot shows the expected behavior\n"
            f"  3. Also verify the console log shows NO_CONSOLE_ERRORS\n"
            f"  4. Then mark the test as passing"
        )

    @staticmethod
    def test_no_console_log(
        test_id: str, issue_number: str, console_pattern: str
    ) -> str:
        """Generate error message when no console log file exists.

        Console log files are REQUIRED with playwright-test.cjs workflow.
        The script generates both screenshot AND console log.

        Args:
            test_id: The test ID being marked as passing
            issue_number: Current issue number
            console_pattern: The pattern that was searched

        Returns:
            Formatted error message (blocking)
        """
        return (
            f"🚫 TEST BLOCKED: No console log found for '{test_id}'\n\n"
            f"Pattern searched: {console_pattern}\n\n"
            f"Console log files are REQUIRED. playwright-test.cjs generates both\n"
            f"screenshot and console log files.\n\n"
            f"💡 How to fix:\n"
            f"  1. Run playwright-test.cjs with --operation full:\n"
            f"     node playwright-test.cjs --url http://localhost:6174 \\\n"
            f"       --test-id {test_id} \\\n"
            f"       --output-dir screenshots/issue-{issue_number} \\\n"
            f"       --operation full\n\n"
            f"  2. This generates BOTH files:\n"
            f"     • screenshots/issue-{issue_number}/{test_id}-<timestamp>.png\n"
            f"     • screenshots/issue-{issue_number}/{test_id}-console.txt\n\n"
            f"  3. Read the console log to check for errors\n"
            f"  4. Read the screenshot to verify visually\n"
            f"  5. Then mark the test as passing"
        )

    @staticmethod
    def test_console_not_viewed(test_id: str, console_path: str) -> str:
        """Generate error message when console log exists but wasn't viewed.

        Console log verification is REQUIRED with playwright-test.cjs workflow.
        The agent must read the console log to verify NO_CONSOLE_ERRORS.

        Args:
            test_id: The test ID being marked as passing
            console_path: Path to the console log that wasn't viewed

        Returns:
            Formatted error message (blocking)
        """
        return (
            f"🚫 TEST BLOCKED: Console log not verified for '{test_id}'\n\n"
            f"Console log exists: {console_path}\n\n"
            f"You MUST read the console log and verify NO_CONSOLE_ERRORS\n"
            f"before marking the test as passing.\n\n"
            f"💡 How to fix:\n"
            f"  1. Use the Read tool to view the console log:\n"
            f"     Read file: {console_path}\n\n"
            f"  2. Check that it shows: NO_CONSOLE_ERRORS\n"
            f"     (If it shows ERRORS: you must fix them first)\n\n"
            f"  3. Then mark the test as passing"
        )

    @staticmethod
    def test_no_id_found() -> str:
        """Generate error message when test ID cannot be determined.

        Returns:
            Formatted error message
        """
        return (
            "🚫 TEST BLOCKED: Cannot determine test ID\n\n"
            "The edit context doesn't include enough information to identify the test.\n\n"
            "💡 How to fix:\n"
            "  • Include the test's 'id' field in your edit context\n"
            "  • Or include the test's 'name' field\n"
            "  • Edit one test at a time with sufficient surrounding context\n\n"
            "💡 Example edit:\n"
            '  old_string: \'"id": "my-test", "passes": false\'\n'
            '  new_string: \'"id": "my-test", "passes": true\''
        )
