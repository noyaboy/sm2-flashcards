#!/bin/bash
# Comprehensive test script for vocabulary trainer
# Tests learning cycle, SM-2 progression, and edge cases

# Don't exit on error - we want to see all test results
# set -e

echo "=========================================="
echo "  VOCABULARY TRAINER - COMPREHENSIVE TESTS"
echo "=========================================="
echo ""

# Clean up any existing test database
rm -f toeic_vocab_test.db

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass_count=0
fail_count=0

check_result() {
    if echo "$1" | grep -q "$2"; then
        echo -e "${GREEN}PASS${NC}: $3"
        ((pass_count++))
    else
        echo -e "${RED}FAIL${NC}: $3"
        echo "  Expected to find: $2"
        echo "  Got: $1"
        ((fail_count++))
    fi
}

# =============================================================================
echo ""
echo "TEST 1: Add word and verify learning step 1"
echo "--------------------------------------------"
# =============================================================================

# Use a real word so dictionary lookup works, accept defaults with Enter
result=$(printf 'add\ndiligent\n\n\nlist\nexit\n' | python3 vocab_trainer.py --test 2>&1)
check_result "$result" "first review in 1 min" "Word added with 1 min first review"
check_result "$result" "Learning step 1/3" "Word is at learning step 1"

# =============================================================================
echo ""
echo "TEST 2: Learning step 1 -> step 2 (rating: Easy)"
echo "-------------------------------------------------"
# =============================================================================

# Wait for step 1 to be due (0.06s) and review with Easy
sleep 0.1
result=$(printf 'pending\nreview\n\n3\nlist\nexit\n' | python3 vocab_trainer.py --test 2>&1)
check_result "$result" "learning (step 1/3)" "Pending shows step 1"
check_result "$result" "Step 2/3" "Advanced to step 2"
check_result "$result" "Learning step 2/3" "List shows step 2"

# =============================================================================
echo ""
echo "TEST 3: Learning step 2 -> step 3 (rating: Easy)"
echo "-------------------------------------------------"
# =============================================================================

# Wait for step 2 to be due (0.6s)
sleep 0.7
result=$(printf 'pending\nreview\n\n3\nlist\nexit\n' | python3 vocab_trainer.py --test 2>&1)
check_result "$result" "learning (step 2/3)" "Pending shows step 2"
check_result "$result" "Step 3/3" "Advanced to step 3"
check_result "$result" "Learning step 3/3" "List shows step 3"

# =============================================================================
echo ""
echo "TEST 4: Learning step 3 -> Graduate (rating: Easy)"
echo "---------------------------------------------------"
# =============================================================================

# Wait for step 3 to be due (86.4s)
echo "Waiting 87 seconds for step 3 to become due..."
sleep 87
result=$(printf 'pending\nreview\n\n3\nstats\nlist\nexit\n' | python3 vocab_trainer.py --test 2>&1)
check_result "$result" "learning (step 3/3)" "Pending shows step 3"
check_result "$result" "Graduated" "Card graduated"
check_result "$result" "Graduated (SM-2): 1" "Stats shows 1 graduated"
check_result "$result" "\[SM-2\]" "List shows SM-2 status"

# =============================================================================
echo ""
echo "TEST 5: SM-2 Review (1 day interval) - rating: Easy"
echo "----------------------------------------------------"
# =============================================================================

# Wait for 1 day interval (86.4s)
echo "Waiting 87 seconds for SM-2 review..."
sleep 87
result=$(printf 'pending\nreview\n\n3\nlist\nexit\n' | python3 vocab_trainer.py --test 2>&1)
check_result "$result" "reviewing (reps: 1)" "Pending shows review with 1 rep"
check_result "$result" "Next review in 6 day" "Interval increased to 6 days"

# =============================================================================
echo ""
echo "TEST 6: Add second word and test Hard rating"
echo "---------------------------------------------"
# =============================================================================

# Add a new real word
result=$(printf 'add\nmeticulous\n\n\nlist\nexit\n' | python3 vocab_trainer.py --test 2>&1)
check_result "$result" "first review in 1 min" "Second word added"

# Wait and review with Hard (should repeat step 1)
sleep 0.1
result=$(printf 'review\n\n2\nlist\nexit\n' | python3 vocab_trainer.py --test 2>&1)
check_result "$result" "Repeat step 1" "Hard rating repeats step 1"
check_result "$result" "Learning step 1/3" "Still at step 1"

# =============================================================================
echo ""
echo "TEST 7: Test Forgot rating (reset to step 1)"
echo "---------------------------------------------"
# =============================================================================

# Review meticulous with Easy to advance to step 2
sleep 0.1
result=$(printf 'review\n\n3\nexit\n' | python3 vocab_trainer.py --test 2>&1)
check_result "$result" "Step 2/3" "Advanced to step 2"

# Wait for step 2 and then Forget
sleep 0.7
result=$(printf 'review\n\n1\nlist\nexit\n' | python3 vocab_trainer.py --test 2>&1)
check_result "$result" "Reset to step 1" "Forgot resets to step 1"
check_result "$result" "meticulous.*Learning step 1/3" "List shows reset to step 1"

# =============================================================================
echo ""
echo "TEST 8: Graduate second word and test SM-2 forget"
echo "--------------------------------------------------"
# =============================================================================

# Fast-track to graduation: 3 Easy ratings through learning steps
sleep 0.1
printf 'review\n\n3\nexit\n' | python3 vocab_trainer.py --test > /dev/null 2>&1  # step 1->2
sleep 0.7
printf 'review\n\n3\nexit\n' | python3 vocab_trainer.py --test > /dev/null 2>&1  # step 2->3
echo "Waiting 87 seconds to graduate second word..."
sleep 87
result=$(printf 'review\n\n3\nstats\nexit\n' | python3 vocab_trainer.py --test 2>&1)
check_result "$result" "Graduated" "Second word graduated"
check_result "$result" "Graduated (SM-2): 2" "Stats shows 2 graduated"

# Wait for SM-2 review and then Forget (should go back to learning)
echo "Waiting 87 seconds for SM-2 review..."
sleep 87
result=$(printf 'review\n\n1\nstats\nlist\nexit\n' | python3 vocab_trainer.py --test 2>&1)
check_result "$result" "Back to learning" "Forgot sends back to learning"
check_result "$result" "In learning: 1" "Stats shows 1 in learning"
check_result "$result" "Graduated (SM-2): 1" "Stats shows 1 graduated"

# =============================================================================
echo ""
echo "TEST 9: Verify EF changes based on ratings"
echo "-------------------------------------------"
# =============================================================================

# Add a real word for EF testing
printf 'add\nperseverance\n\n\nexit\n' | python3 vocab_trainer.py --test > /dev/null 2>&1

# Graduate it with all Easy ratings
sleep 0.1
printf 'review\n\n3\nexit\n' | python3 vocab_trainer.py --test > /dev/null 2>&1  # step 1->2
sleep 0.7
printf 'review\n\n3\nexit\n' | python3 vocab_trainer.py --test > /dev/null 2>&1  # step 2->3
sleep 87
printf 'review\n\n3\nexit\n' | python3 vocab_trainer.py --test > /dev/null 2>&1  # graduate
echo "Waiting for EF test SM-2 reviews..."
sleep 87

# Rate Hard on SM-2 review (should decrease EF)
result=$(printf 'list\nexit\n' | python3 vocab_trainer.py --test 2>&1)
check_result "$result" "perseverance.*EF: 2.50" "EF starts at 2.50"

result=$(printf 'review\n\n2\nlist\nexit\n' | python3 vocab_trainer.py --test 2>&1)
check_result "$result" "perseverance.*EF: 2.36" "EF decreased after Hard rating"

# =============================================================================
echo ""
echo "TEST 10: Test multiple pending words"
echo "------------------------------------"
# =============================================================================

# Add multiple real words
printf 'add\nambitious\n\n\nexit\n' | python3 vocab_trainer.py --test > /dev/null 2>&1
printf 'add\nresilient\n\n\nexit\n' | python3 vocab_trainer.py --test > /dev/null 2>&1
printf 'add\npragmatic\n\n\nexit\n' | python3 vocab_trainer.py --test > /dev/null 2>&1

sleep 0.1
result=$(printf 'pending\nexit\n' | python3 vocab_trainer.py --test 2>&1)
check_result "$result" "ambitious" "ambitious in pending"
check_result "$result" "resilient" "resilient in pending"
check_result "$result" "pragmatic" "pragmatic in pending"

# Review all with quit in middle
result=$(printf 'review\n\n3\n\n3\nq\nlist\nexit\n' | python3 vocab_trainer.py --test 2>&1)
check_result "$result" "Reviewed 2 word" "Reviewed 2 words before quit"

# =============================================================================
echo ""
echo "=========================================="
echo "  TEST SUMMARY"
echo "=========================================="
echo -e "  ${GREEN}PASSED: $pass_count${NC}"
echo -e "  ${RED}FAILED: $fail_count${NC}"
echo "=========================================="

if [ $fail_count -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
