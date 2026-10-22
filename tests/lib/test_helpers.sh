#!/bin/sh
#
# test_helpers.sh: shared definitions for the tests in tests/.
#
# This file is sourced, not executed: scripts/tests-run.sh executes only
# tests/*.sh, so a helper under tests/lib/ never runs on its own. A test uses
# it with:
#
#     . "$(dirname -- "$0")/lib/test_helpers.sh"
#
# The standard tool-gated skip message is "SKIP: missing tool: <tool>", so a
# skip is visible in the run transcript without being a failure.

# skip_test MESSAGE: report a clean skip and exit 0.
skip_test() {
    echo "SKIP: $1"
    exit 0
}

# skip_unless_tool TOOL: skip cleanly when TOOL is not on PATH.
skip_unless_tool() {
    command -v "$1" >/dev/null 2>&1 || skip_test "missing tool: $1"
}

# fail_test TEST_NAME MESSAGE: report a failure and exit 1.
fail_test() {
    echo "$1: $2" >&2
    exit 1
}

# pass_test TEST_NAME: report success and exit 0.
pass_test() {
    echo "$1: ok"
    exit 0
}
