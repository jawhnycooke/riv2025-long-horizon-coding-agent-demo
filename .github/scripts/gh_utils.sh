#!/bin/bash
# F020: Shared GitHub CLI utilities with retry logic
# Source this file in workflows: source .github/scripts/gh_utils.sh

# gh_with_retry: Execute gh commands with exponential backoff retry
# Usage: gh_with_retry <max_attempts> <base_delay_seconds> <gh_command...>
# Example: gh_with_retry 3 2 gh issue edit 123 --add-label "agent-building"
#
# Returns: exit code from last gh attempt
gh_with_retry() {
    local max_attempts="${1:-3}"
    local base_delay="${2:-2}"
    shift 2

    local attempt=1
    local exit_code=0

    while [ $attempt -le $max_attempts ]; do
        echo "::debug::Attempt $attempt/$max_attempts: $*"

        if "$@"; then
            return 0
        fi

        exit_code=$?

        if [ $attempt -lt $max_attempts ]; then
            # Exponential backoff: base_delay * 2^(attempt-1)
            local delay=$((base_delay * (1 << (attempt - 1))))
            # Add jitter: random 0-1 seconds
            delay=$((delay + RANDOM % 2))
            echo "::warning::gh command failed (attempt $attempt/$max_attempts), retrying in ${delay}s..."
            sleep $delay
        fi

        attempt=$((attempt + 1))
    done

    echo "::error::gh command failed after $max_attempts attempts: $*"
    return $exit_code
}

# escape_markdown: Escape special characters for GitHub markdown
# Usage: escaped=$(escape_markdown "string with <special> chars")
escape_markdown() {
    local input="$1"
    # Escape: \ ` * _ { } [ ] ( ) # + - . ! < > |
    echo "$input" | sed -e 's/\\/\\\\/g' \
                        -e 's/`/\\`/g' \
                        -e 's/\*/\\*/g' \
                        -e 's/_/\\_/g' \
                        -e 's/{/\\{/g' \
                        -e 's/}/\\}/g' \
                        -e 's/\[/\\[/g' \
                        -e 's/\]/\\]/g' \
                        -e 's/(/\\(/g' \
                        -e 's/)/\\)/g' \
                        -e 's/#/\\#/g' \
                        -e 's/+/\\+/g' \
                        -e 's/-/\\-/g' \
                        -e 's/\./\\./g' \
                        -e 's/!/\\!/g' \
                        -e 's/</\\</g' \
                        -e 's/>/\\>/g' \
                        -e 's/|/\\|/g'
}

# sanitize_for_shell: Sanitize input for safe shell usage
# Usage: sanitized=$(sanitize_for_shell "$user_input")
sanitize_for_shell() {
    local input="$1"
    # Remove or escape dangerous characters
    echo "$input" | sed -e "s/'/'\\\\''/g" \
                        -e 's/"/\\"/g' \
                        -e 's/`/\\`/g' \
                        -e 's/\$/\\$/g' \
                        -e 's/;/\\;/g' \
                        -e 's/|/\\|/g' \
                        -e 's/&/\\&/g'
}

# write_job_summary: Write formatted output to GitHub Actions job summary
# Usage: write_job_summary "## Header" "Content line 1" "Content line 2"
write_job_summary() {
    for line in "$@"; do
        echo "$line" >> "$GITHUB_STEP_SUMMARY"
    done
}

# write_job_summary_table: Write a markdown table to job summary
# Usage: write_job_summary_table "Header1|Header2" "Row1Col1|Row1Col2" "Row2Col1|Row2Col2"
write_job_summary_table() {
    local header="$1"
    shift

    # Write header
    echo "| ${header//|/ | } |" >> "$GITHUB_STEP_SUMMARY"

    # Write separator (count columns from header)
    local num_cols=$(echo "$header" | tr -cd '|' | wc -c)
    num_cols=$((num_cols + 1))
    local separator="|"
    for ((i=0; i<num_cols; i++)); do
        separator="$separator---|"
    done
    echo "$separator" >> "$GITHUB_STEP_SUMMARY"

    # Write rows
    for row in "$@"; do
        echo "| ${row//|/ | } |" >> "$GITHUB_STEP_SUMMARY"
    done
}

# log_and_summary: Log message and optionally add to job summary
# Usage: log_and_summary "info" "Message" [add_to_summary]
log_and_summary() {
    local level="$1"
    local message="$2"
    local add_to_summary="${3:-false}"

    case "$level" in
        debug)   echo "::debug::$message" ;;
        info)    echo "$message" ;;
        warning) echo "::warning::$message" ;;
        error)   echo "::error::$message" ;;
        *)       echo "$message" ;;
    esac

    if [ "$add_to_summary" = "true" ] && [ -n "$GITHUB_STEP_SUMMARY" ]; then
        echo "$message" >> "$GITHUB_STEP_SUMMARY"
    fi
}
