#!/usr/bin/env bash

set -u

# ============================================================
# ATC Requirement Traceability Validator
#
# Usage:
#
#   ./scripts/validate-requirements.sh radar
#   ./scripts/validate-requirements.sh tower
#   ./scripts/validate-requirements.sh command
#
# A requirement must have:
#
#   1. Requirement document
#   2. Entry in docs/requirements-index.md
#   3. Source implementation referencing the requirement ID
#   4. Automated test referencing the requirement ID
# ============================================================


# ------------------------------------------------------------
# Validate argument
# ------------------------------------------------------------

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <subsystem>"
    echo ""
    echo "Supported subsystems:"
    echo "  radar"
    echo "  tower"
    echo "  command"
    exit 1
fi


SUBSYSTEM="$1"

case "$SUBSYSTEM" in
    radar|tower|command)
        ;;
    *)
        echo "ERROR: Unknown subsystem: $SUBSYSTEM"
        echo ""
        echo "Supported subsystems:"
        echo "  radar"
        echo "  tower"
        echo "  command"
        exit 1
        ;;
esac


REQUIREMENTS_DIR="./requirements/$SUBSYSTEM"
SRC_DIR="./src/$SUBSYSTEM"
TESTS_DIR="./tests/$SUBSYSTEM"
REQUIREMENTS_INDEX="./docs/requirements-index.md"

errors=0
requirements_checked=0


echo "=========================================="
echo "ATC Requirement Traceability Validation"
echo "=========================================="
echo "Subsystem: $SUBSYSTEM"
echo "=========================================="


# ------------------------------------------------------------
# Validate directories and index
# ------------------------------------------------------------

for directory in "$REQUIREMENTS_DIR" "$SRC_DIR" "$TESTS_DIR"; do

    if [[ ! -d "$directory" ]]; then
        echo ""
        echo "ERROR: Required directory does not exist:"
        echo "       $directory"

        errors=$((errors + 1))
    fi

done


if [[ ! -f "$REQUIREMENTS_INDEX" ]]; then
    echo ""
    echo "ERROR: Requirements index does not exist:"
    echo "       $REQUIREMENTS_INDEX"

    exit 1
fi


if [[ $errors -gt 0 ]]; then
    exit 1
fi


# ------------------------------------------------------------
# Validate every requirement
# ------------------------------------------------------------

while IFS= read -r -d '' requirement_file; do

    filename=$(basename "$requirement_file")

    # Extract requirement ID from filename
    req_id=$(echo "$filename" | grep -oE 'REQ-[A-Z]+-[0-9]+')

    if [[ -z "$req_id" ]]; then

        echo ""
        echo "ERROR: Invalid requirement filename:"
        echo "       $requirement_file"

        errors=$((errors + 1))
        continue

    fi


    requirements_checked=$((requirements_checked + 1))

    echo ""
    echo "Checking: $req_id"
    echo "------------------------------------------"


    # ========================================================
    # 1. Requirement document
    # ========================================================

    echo "  Requirement:"

    if [[ -f "$requirement_file" ]]; then

        echo "    PASS: $requirement_file"

    else

        echo "    FAIL: Requirement document does not exist"

        errors=$((errors + 1))

    fi


    # ========================================================
    # 2. Requirements index
    #
    # Expected format:
    #
    # | REQ-SAF-003 | Safety | Early separation warning |
    # ========================================================

    echo "  Index:"

    index_matches=$(grep -E \
        "^\|[[:space:]]*$req_id[[:space:]]*\|" \
        "$REQUIREMENTS_INDEX" 2>/dev/null || true)


    if [[ -n "$index_matches" ]]; then

        echo "    PASS: $req_id exists in requirements-index.md"
        echo "          $index_matches"

    else

        echo "    FAIL: $req_id is missing from requirements-index.md"

        errors=$((errors + 1))

    fi


    # ========================================================
    # 3. Source implementation
    # ========================================================

    echo "  Source:"

    source_matches=$(grep -ril \
        --include="*.ts" \
        --include="*.tsx" \
        --include="*.js" \
        --include="*.jsx" \
        --include="*.py" \
        --include="*.java" \
        --include="*.go" \
        --include="*.c" \
        --include="*.cpp" \
        --include="*.h" \
        --include="*.hpp" \
        "$req_id" \
        "$SRC_DIR" 2>/dev/null || true)


    if [[ -n "$source_matches" ]]; then

        echo "    PASS"

        while IFS= read -r file; do
            echo "          $file"
        done <<< "$source_matches"

    else

        echo "    FAIL: No source implementation references $req_id"

        errors=$((errors + 1))

    fi


    # ========================================================
    # 4. Automated tests
    # ========================================================

    echo "  Tests:"

    test_matches=$(grep -ril \
        --include="*.test.ts" \
        --include="*.test.tsx" \
        --include="*.spec.ts" \
        --include="*.spec.tsx" \
        --include="*.test.js" \
        --include="*.test.jsx" \
        --include="*.spec.js" \
        --include="*.spec.jsx" \
        --include="test_*.py" \
        --include="*_test.py" \
        --include="*Test.java" \
        --include="*_test.go" \
        --include="*_test.c" \
        --include="*_test.cpp" \
        "$req_id" \
        "$TESTS_DIR" 2>/dev/null || true)


    if [[ -n "$test_matches" ]]; then

        echo "    PASS"

        while IFS= read -r file; do
            echo "          $file"
        done <<< "$test_matches"

    else

        echo "    FAIL: No automated test references $req_id"

        errors=$((errors + 1))

    fi


done < <(
    find "$REQUIREMENTS_DIR" \
        -type f \
        -name "REQ-*.md" \
        -print0
)


# ------------------------------------------------------------
# Final result
# ------------------------------------------------------------

echo ""
echo "=========================================="
echo "ATC VALIDATION RESULT"
echo "=========================================="
echo "Subsystem:              $SUBSYSTEM"
echo "Requirements checked:   $requirements_checked"
echo "Validation errors:      $errors"
echo "=========================================="


if [[ $errors -eq 0 ]]; then

    echo "PASS"
    echo ""
    echo "Requirement traceability is complete:"
    echo ""
    echo "  Requirement"
    echo "       ↓"
    echo "  Requirements Index"
    echo "       ↓"
    echo "  Source"
    echo "       ↓"
    echo "  Automated Test"

    exit 0

else

    echo "FAIL"
    echo ""
    echo "Every requirement must have:"
    echo "  [x] Requirement document"
    echo "  [x] Requirements index entry"
    echo "  [x] Source implementation"
    echo "  [x] Automated test"
    echo ""
    echo "The pull request cannot be merged."

    exit 1

fi
