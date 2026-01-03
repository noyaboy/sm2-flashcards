#!/usr/bin/env python3
"""
TOEIC Vocabulary Learning Tool
Uses the SuperMemo-2 (SM-2) algorithm for spaced repetition scheduling.
Based on the Ebbinghaus Forgetting Curve principles.

Usage:
  python vocab_trainer.py          # Normal mode
  python vocab_trainer.py --test   # Test mode (1000x speed: 1 day = 86.4s)
"""

import sqlite3
import math
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================

# Test mode: enabled via --test flag
# In test mode, time runs 1000x faster (1 day = 86.4 seconds)
TEST_MODE = "--test" in sys.argv
TIME_SCALE = 1000 if TEST_MODE else 1  # 1000x faster in test mode

# Database file path - handle PyInstaller frozen executable
# When frozen, use the directory containing the executable
# When running as script, use the script's directory
if getattr(sys, 'frozen', False):
    # Running as PyInstaller executable
    APP_DIR = Path(sys.executable).parent
else:
    # Running as Python script
    APP_DIR = Path(__file__).parent

DB_PATH = APP_DIR / ("toeic_vocab_test.db" if TEST_MODE else "toeic_vocab.db")

# Learning steps in minutes (Anki-style)
# New cards go through these steps before graduating to SM-2 schedule
# Step 0 = graduated (in SM-2 schedule)
LEARNING_STEPS = [1, 10, 1440]  # 1 min, 10 min, 1 day (1440 min)


def init_database(conn: sqlite3.Connection) -> None:
    """
    Initialize the database with the vocab table if it doesn't exist.

    Schema:
    - id: Primary key
    - word: The vocabulary word
    - meaning: Definition/translation (English)
    - chinese: Traditional Chinese translation
    - learning_step: Current learning step (0 = graduated to SM-2, 1-3 = in learning)
    - repetitions (n): Number of successful reviews in a row
    - interval (I): Days until next review
    - easiness_factor (EF): SM-2 easiness factor (default 2.5, min 1.3)
    - next_review: Datetime when word should be reviewed next (ISO format)
    """
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vocab (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL UNIQUE,
            pos TEXT DEFAULT '',
            meaning TEXT NOT NULL,
            chinese TEXT DEFAULT '',
            learning_step INTEGER DEFAULT 1,
            repetitions INTEGER DEFAULT 0,
            interval INTEGER DEFAULT 1,
            easiness_factor REAL DEFAULT 2.5,
            next_review TEXT NOT NULL
        )
    """)
    # Migrations for existing databases
    cursor.execute("PRAGMA table_info(vocab)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'pos' not in columns:
        cursor.execute("ALTER TABLE vocab ADD COLUMN pos TEXT DEFAULT ''")
    if 'learning_step' not in columns:
        cursor.execute("ALTER TABLE vocab ADD COLUMN learning_step INTEGER DEFAULT 0")
    if 'chinese' not in columns:
        cursor.execute("ALTER TABLE vocab ADD COLUMN chinese TEXT DEFAULT ''")
    # Rename next_review_date to next_review if old column exists
    if 'next_review_date' in columns and 'next_review' not in columns:
        cursor.execute("ALTER TABLE vocab RENAME COLUMN next_review_date TO next_review")
    conn.commit()


def get_connection() -> sqlite3.Connection:
    """Get database connection, initializing if needed."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    init_database(conn)
    return conn


# =============================================================================
# Translation API (English -> Traditional Chinese)
# =============================================================================

def translate_to_chinese(text: str) -> str | None:
    """
    Translate English text to Traditional Chinese using MyMemory API.
    Free API, no key required. Returns translated text or None on error.
    """
    if not text.strip():
        return None

    # MyMemory API - free translation service
    # langpair: en|zh-TW for English to Traditional Chinese
    encoded_text = urllib.parse.quote(text)
    url = f"https://api.mymemory.translated.net/get?q={encoded_text}&langpair=en|zh-TW"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

            if data.get('responseStatus') == 200:
                translated = data.get('responseData', {}).get('translatedText', '')
                # Check for error messages in response
                if translated and 'MYMEMORY WARNING' not in translated:
                    return translated

        return None

    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        return None


# =============================================================================
# Dictionary API Lookup (Free Dictionary API - supports multiple meanings)
# =============================================================================

def lookup_all_meanings(word: str) -> list:
    """
    Look up a word using Free Dictionary API and return ALL meanings.
    Returns list of dicts with 'pos', 'definition', 'example'.
    """
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

            if not data or not isinstance(data, list):
                return []

            meanings = []
            seen_definitions = set()

            for entry in data:
                for meaning in entry.get('meanings', []):
                    pos = meaning.get('partOfSpeech', '')

                    for defn in meaning.get('definitions', []):
                        definition = defn.get('definition', '')

                        # Skip duplicates
                        if definition in seen_definitions:
                            continue
                        seen_definitions.add(definition)

                        example = defn.get('example', '')

                        meanings.append({
                            'pos': pos,
                            'definition': definition,
                            'example': example
                        })

            return meanings

    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        return []


def lookup_word(word: str) -> dict | None:
    """
    Look up a word using the Free Dictionary API and translate to Traditional Chinese.
    Returns dict with 'pos', 'definition', and 'chinese' or None if not found.

    API: https://dictionaryapi.dev/
    """
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}"

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))

            if not data or not isinstance(data, list):
                return None

            # Extract first meaning
            entry = data[0]
            meanings = entry.get('meanings', [])

            if not meanings:
                return None

            # Get the first part of speech and its first definition
            first_meaning = meanings[0]
            pos = first_meaning.get('partOfSpeech', '')

            definitions = first_meaning.get('definitions', [])
            definition = definitions[0].get('definition', '') if definitions else ''

            # Collect all parts of speech for display
            all_pos = [m.get('partOfSpeech', '') for m in meanings if m.get('partOfSpeech')]
            pos_display = '/'.join(all_pos) if all_pos else ''

            # Translate definition to Traditional Chinese
            chinese = translate_to_chinese(definition)

            return {
                'pos': pos_display,
                'definition': definition,
                'chinese': chinese or ''
            }

    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        return None


# Need to import urllib.parse for URL encoding
import urllib.parse


# =============================================================================
# SM-2 Algorithm Implementation
# =============================================================================
#
# The SuperMemo-2 algorithm calculates optimal review intervals based on:
# 1. How well the user remembers the item (quality rating q: 0-5)
# 2. The current easiness factor (EF) of the item
# 3. The number of successful repetitions
#
# Key Formulas:
# -------------
# Interval calculation:
#   I(1) = 1 day (first review after 1 day)
#   I(2) = 6 days (second review after 6 days)
#   I(n) = I(n-1) * EF for n > 2 (subsequent intervals grow exponentially)
#
# Easiness Factor adjustment:
#   EF' = EF + (0.1 - (5-q) * (0.08 + (5-q) * 0.02))
#
#   This formula adjusts EF based on response quality:
#   - q=5 (perfect): EF increases by 0.1
#   - q=4 (good): EF stays roughly the same
#   - q=3 (hard): EF decreases slightly
#   - q<3 (forgot): EF decreases more significantly
#
#   Minimum EF is capped at 1.3 to prevent intervals from shrinking too fast.
#
# Our simplified rating system:
#   (1) Forgot  -> q=0: Reset to beginning, penalize EF heavily
#   (2) Hard    -> q=3: Slow interval growth, slight EF decrease
#   (3) Easy    -> q=5: Exponential interval growth, EF increase
# =============================================================================


def calculate_sm2(repetitions: int, interval: int, ef: float, quality: int) -> tuple:
    """
    Apply SM-2 algorithm to calculate next review parameters.

    Args:
        repetitions: Current number of successful repetitions
        interval: Current interval in days
        ef: Current easiness factor
        quality: User's rating (0=forgot, 3=hard, 5=easy)

    Returns:
        Tuple of (new_repetitions, new_interval, new_ef)
    """
    # Calculate new easiness factor
    # Formula: EF' = EF + (0.1 - (5-q) * (0.08 + (5-q) * 0.02))
    new_ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))

    # EF must not go below 1.3
    new_ef = max(1.3, new_ef)

    if quality < 3:
        # User forgot: reset repetitions and interval
        new_repetitions = 0
        new_interval = 1
    else:
        # User remembered: increment repetitions and calculate new interval
        new_repetitions = repetitions + 1

        if new_repetitions == 1:
            # First successful review: interval = 1 day
            new_interval = 1
        elif new_repetitions == 2:
            # Second successful review: interval = 6 days
            new_interval = 6
        else:
            # Subsequent reviews: interval grows by EF factor
            # I(n) = I(n-1) * EF, rounded up
            new_interval = math.ceil(interval * new_ef)

    return new_repetitions, new_interval, new_ef


def get_next_review(minutes: int = 0, days: int = 0) -> str:
    """
    Calculate the next review datetime based on interval.
    In test mode, time is scaled by TIME_SCALE (1000x faster).
    """
    # Convert to total seconds, then scale
    total_seconds = (minutes * 60 + days * 86400) / TIME_SCALE
    next_time = datetime.now() + timedelta(seconds=total_seconds)
    return next_time.strftime("%Y-%m-%d %H:%M:%S")


def format_time_until(next_review: str) -> str:
    """Format the time remaining until next review in human-readable form."""
    try:
        # Try parsing with time
        next_dt = datetime.strptime(next_review, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        # Fallback for old date-only format
        next_dt = datetime.strptime(next_review, "%Y-%m-%d")

    diff = next_dt - datetime.now()
    total_seconds = diff.total_seconds()

    if total_seconds < 0:
        return "now"

    if TEST_MODE:
        # In test mode, show actual seconds remaining
        if total_seconds < 60:
            return f"{total_seconds:.1f}s"
        else:
            return f"{total_seconds/60:.1f}min"
    else:
        # Normal mode: show in minutes/hours/days
        total_minutes = int(total_seconds / 60)
        if total_minutes < 60:
            return f"{total_minutes}min"
        elif total_minutes < 1440:
            hours = total_minutes // 60
            return f"{hours}h"
        else:
            days = total_minutes // 1440
            return f"{days}d"


def is_due_for_review(next_review: str) -> bool:
    """Check if a word is due for review."""
    try:
        next_dt = datetime.strptime(next_review, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        next_dt = datetime.strptime(next_review, "%Y-%m-%d")
    return datetime.now() >= next_dt


# =============================================================================
# Data Access Functions (for GUI import)
# =============================================================================


def get_pending_words(conn: sqlite3.Connection) -> list:
    """Get all words due for review. Returns list of dicts."""
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        SELECT id, word, pos, meaning, chinese, learning_step, repetitions, interval, easiness_factor, next_review
        FROM vocab
        WHERE next_review <= ?
        ORDER BY next_review ASC
    """, (now,))

    return [dict(row) for row in cursor.fetchall()]


def get_all_words(conn: sqlite3.Connection) -> list:
    """Get all words in the database. Returns list of dicts."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, word, pos, meaning, chinese, learning_step, repetitions, interval, easiness_factor, next_review
        FROM vocab
        ORDER BY word ASC
    """)
    return [dict(row) for row in cursor.fetchall()]


def get_stats(conn: sqlite3.Connection) -> dict:
    """Get vocabulary statistics. Returns dict."""
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("SELECT COUNT(*) FROM vocab")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM vocab WHERE next_review <= ?", (now,))
    pending = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM vocab WHERE learning_step > 0")
    learning = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM vocab WHERE learning_step = 0")
    graduated = cursor.fetchone()[0]

    cursor.execute("SELECT AVG(easiness_factor) FROM vocab WHERE learning_step = 0")
    avg_ef = cursor.fetchone()[0]

    return {
        'total': total,
        'pending': pending,
        'learning': learning,
        'graduated': graduated,
        'avg_ef': avg_ef or 0.0
    }


def add_word_to_db(conn: sqlite3.Connection, word: str, pos: str, meaning: str, chinese: str = '') -> dict:
    """
    Add a word to the database.
    Returns dict with 'success' (bool), 'message' (str), 'word_id' (int or None).
    """
    if not word.strip():
        return {'success': False, 'message': 'Word cannot be empty.', 'word_id': None}
    if not meaning.strip():
        return {'success': False, 'message': 'Definition cannot be empty.', 'word_id': None}

    cursor = conn.cursor()
    try:
        first_step_minutes = LEARNING_STEPS[0]
        next_review = get_next_review(minutes=first_step_minutes)
        cursor.execute("""
            INSERT INTO vocab (word, pos, meaning, chinese, learning_step, next_review)
            VALUES (?, ?, ?, ?, 1, ?)
        """, (word.strip(), pos.strip(), meaning.strip(), chinese.strip(), next_review))
        conn.commit()
        return {
            'success': True,
            'message': f"Added '{word}' - first review in {first_step_minutes} min",
            'word_id': cursor.lastrowid
        }
    except sqlite3.IntegrityError:
        return {'success': False, 'message': f"Word '{word}' already exists.", 'word_id': None}


def submit_rating(conn: sqlite3.Connection, word_id: int, rating: int) -> dict:
    """
    Submit a rating for a word (1=forgot, 2=hard, 3=easy).
    Returns dict with 'success', 'feedback', 'graduated', 'next_review_str'.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT learning_step, repetitions, interval, easiness_factor
        FROM vocab WHERE id = ?
    """, (word_id,))
    row = cursor.fetchone()

    if not row:
        return {'success': False, 'feedback': 'Word not found.', 'graduated': False, 'next_review_str': ''}

    learning_step = row['learning_step']
    repetitions = row['repetitions']
    interval = row['interval']
    ef = row['easiness_factor']

    graduated = False

    if learning_step > 0:
        # Card is in learning phase
        if rating == 1:  # Forgot: reset to step 1
            new_step = 1
            next_minutes = LEARNING_STEPS[0]
            feedback = f"Reset to step 1 - review in {next_minutes}min"
        elif rating == 2:  # Hard: repeat current step
            new_step = learning_step
            next_minutes = LEARNING_STEPS[learning_step - 1]
            feedback = f"Repeat step {new_step} - review in {next_minutes}min"
        else:  # Easy: advance to next step or graduate
            if learning_step >= len(LEARNING_STEPS):
                # Graduate to SM-2 schedule
                cursor.execute("""
                    UPDATE vocab
                    SET learning_step = 0, repetitions = 1, interval = 1, next_review = ?
                    WHERE id = ?
                """, (get_next_review(days=1), word_id))
                conn.commit()
                graduated = True
                return {
                    'success': True,
                    'feedback': 'Graduated! Next review in 1 day',
                    'graduated': True,
                    'next_review_str': '1 day'
                }
            else:
                # Advance to next learning step
                new_step = learning_step + 1
                next_minutes = LEARNING_STEPS[new_step - 1]
                feedback = f"Step {new_step}/{len(LEARNING_STEPS)} - review in {next_minutes}min"

        next_review = get_next_review(minutes=next_minutes)
        cursor.execute("""
            UPDATE vocab
            SET learning_step = ?, next_review = ?
            WHERE id = ?
        """, (new_step, next_review, word_id))
    else:
        # Card is in SM-2 review phase
        quality_map = {1: 0, 2: 3, 3: 5}
        quality = quality_map[rating]

        new_reps, new_interval, new_ef = calculate_sm2(repetitions, interval, ef, quality)

        if quality < 3:
            # Forgot: back to learning phase
            next_minutes = LEARNING_STEPS[0]
            cursor.execute("""
                UPDATE vocab
                SET learning_step = 1, repetitions = 0, interval = 1, easiness_factor = ?, next_review = ?
                WHERE id = ?
            """, (new_ef, get_next_review(minutes=next_minutes), word_id))
            feedback = f"Back to learning - review in {next_minutes}min"
        else:
            next_review = get_next_review(days=new_interval)
            cursor.execute("""
                UPDATE vocab
                SET repetitions = ?, interval = ?, easiness_factor = ?, next_review = ?
                WHERE id = ?
            """, (new_reps, new_interval, new_ef, next_review, word_id))
            feedback = f"Next review in {new_interval} day(s)"

    conn.commit()
    return {
        'success': True,
        'feedback': feedback,
        'graduated': graduated,
        'next_review_str': feedback.split('review in ')[-1] if 'review in' in feedback else ''
    }


def clear_all_words(conn: sqlite3.Connection) -> dict:
    """
    Delete all words from the database.
    Returns dict with 'success' (bool), 'message' (str), 'count' (int).
    """
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM vocab")
    count = cursor.fetchone()[0]

    cursor.execute("DELETE FROM vocab")
    conn.commit()

    return {
        'success': True,
        'message': f"Deleted {count} word{'s' if count != 1 else ''}.",
        'count': count
    }


# =============================================================================
# CLI Commands
# =============================================================================


def cmd_add(conn: sqlite3.Connection) -> None:
    """Add a new word to the vocabulary database."""
    print("\n--- Add New Word ---")
    word = input("Word: ").strip()
    if not word:
        print("Word cannot be empty.")
        return

    # Auto-lookup definition and POS
    print("  Looking up definition...")
    lookup = lookup_word(word)

    if lookup:
        pos = lookup['pos']
        meaning = lookup['definition']
        print(f"  POS: {pos}")
        print(f"  Definition: {meaning}")

        # Allow user to confirm or edit
        confirm = input("  Accept? (Enter=yes, or type new definition): ").strip()
        if confirm:
            meaning = confirm

        pos_edit = input(f"  POS [{pos}] (Enter=keep, or type new): ").strip()
        if pos_edit:
            pos = pos_edit
    else:
        print("  (Word not found in dictionary)")
        pos = input("  POS (e.g., noun, verb, adj): ").strip()
        meaning = input("  Definition: ").strip()

    if not meaning:
        print("Definition cannot be empty.")
        return

    cursor = conn.cursor()
    try:
        # New words start in learning phase (step 1) with first review in 1 minute
        first_step_minutes = LEARNING_STEPS[0]
        next_review = get_next_review(minutes=first_step_minutes)
        cursor.execute("""
            INSERT INTO vocab (word, pos, meaning, learning_step, next_review)
            VALUES (?, ?, ?, 1, ?)
        """, (word, pos, meaning, next_review))
        conn.commit()
        print(f"Added: '{word}' ({pos}) - first review in {first_step_minutes} min")
    except sqlite3.IntegrityError:
        print(f"Word '{word}' already exists in the database.")


def cmd_pending(conn: sqlite3.Connection) -> None:
    """Show all words due for review."""
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        SELECT id, word, learning_step, repetitions, next_review
        FROM vocab
        WHERE next_review <= ?
        ORDER BY next_review ASC
    """, (now,))

    rows = cursor.fetchall()

    if not rows:
        print("\nNo words pending for review. Great job!")
        return

    print(f"\n--- Pending Reviews: {len(rows)} word(s) ---")
    for row in rows:
        step = row['learning_step']
        if step > 0:
            status = f"learning (step {step}/{len(LEARNING_STEPS)})"
        else:
            status = f"reviewing (reps: {row['repetitions']})"
        print(f"  - {row['word']} [{status}]")


def cmd_review(conn: sqlite3.Connection) -> None:
    """Start an interactive review session for pending words."""
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        SELECT id, word, pos, meaning, chinese, learning_step, repetitions, interval, easiness_factor
        FROM vocab
        WHERE next_review <= ?
        ORDER BY next_review ASC
    """, (now,))

    rows = cursor.fetchall()

    if not rows:
        print("\nNo words pending for review. Great job!")
        return

    print(f"\n--- Review Session: {len(rows)} word(s) ---")
    print("Rating: (1) Forgot  (2) Hard  (3) Easy  (q) Quit\n")

    reviewed = 0
    for row in rows:
        word_id = row['id']
        word = row['word']
        pos = row['pos']
        meaning = row['meaning']
        learning_step = row['learning_step']
        repetitions = row['repetitions']
        interval = row['interval']
        ef = row['easiness_factor']

        # Show learning status
        if learning_step > 0:
            phase = f"[Learning {learning_step}/{len(LEARNING_STEPS)}]"
        else:
            phase = f"[Review #{repetitions + 1}]"

        # Show the word
        print(f"{phase} Word: {word}")
        input("  [Press Enter to see meaning...]")
        pos_str = f"({pos}) " if pos else ""
        print(f"  {pos_str}{meaning}\n")

        # Get user rating
        while True:
            rating = input("  Your rating (1/2/3/q): ").strip().lower()
            if rating == 'q':
                print(f"\nSession ended. Reviewed {reviewed} word(s).")
                return
            if rating in ('1', '2', '3'):
                break
            print("  Invalid input. Please enter 1, 2, 3, or q.")

        # Process rating based on whether card is in learning phase or SM-2 phase
        if learning_step > 0:
            # Card is in learning phase
            if rating == '1':  # Forgot: reset to step 1
                new_step = 1
                next_minutes = LEARNING_STEPS[0]
                feedback = f"Reset to step 1 - review in {next_minutes}min"
            elif rating == '2':  # Hard: repeat current step
                new_step = learning_step
                next_minutes = LEARNING_STEPS[learning_step - 1]
                feedback = f"Repeat step {new_step} - review in {next_minutes}min"
            else:  # Easy: advance to next step or graduate
                if learning_step >= len(LEARNING_STEPS):
                    # Graduate to SM-2 schedule
                    new_step = 0
                    cursor.execute("""
                        UPDATE vocab
                        SET learning_step = 0, repetitions = 1, interval = 1, next_review = ?
                        WHERE id = ?
                    """, (get_next_review(days=1), word_id))
                    conn.commit()
                    reviewed += 1
                    print(f"  -> Graduated! Next review in 1 day\n")
                    continue
                else:
                    # Advance to next learning step
                    new_step = learning_step + 1
                    next_minutes = LEARNING_STEPS[new_step - 1]
                    feedback = f"Step {new_step}/{len(LEARNING_STEPS)} - review in {next_minutes}min"

            next_review = get_next_review(minutes=next_minutes)
            cursor.execute("""
                UPDATE vocab
                SET learning_step = ?, next_review = ?
                WHERE id = ?
            """, (new_step, next_review, word_id))
        else:
            # Card is in SM-2 review phase
            quality_map = {'1': 0, '2': 3, '3': 5}
            quality = quality_map[rating]

            new_reps, new_interval, new_ef = calculate_sm2(
                repetitions, interval, ef, quality
            )

            if quality < 3:
                # Forgot: back to learning phase
                new_step = 1
                next_minutes = LEARNING_STEPS[0]
                cursor.execute("""
                    UPDATE vocab
                    SET learning_step = 1, repetitions = 0, interval = 1, easiness_factor = ?, next_review = ?
                    WHERE id = ?
                """, (new_ef, get_next_review(minutes=next_minutes), word_id))
                feedback = f"Back to learning - review in {next_minutes}min"
            else:
                next_review = get_next_review(days=new_interval)
                cursor.execute("""
                    UPDATE vocab
                    SET repetitions = ?, interval = ?, easiness_factor = ?, next_review = ?
                    WHERE id = ?
                """, (new_reps, new_interval, new_ef, next_review, word_id))
                feedback = f"Next review in {new_interval} day(s)"

        conn.commit()
        reviewed += 1
        print(f"  -> {feedback}\n")

    print(f"Session complete! Reviewed {reviewed} word(s).")


def cmd_stats(conn: sqlite3.Connection) -> None:
    """Show vocabulary statistics."""
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("SELECT COUNT(*) FROM vocab")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM vocab WHERE next_review <= ?", (now,))
    pending = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM vocab WHERE learning_step > 0")
    learning = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM vocab WHERE learning_step = 0")
    graduated = cursor.fetchone()[0]

    cursor.execute("SELECT AVG(easiness_factor) FROM vocab WHERE learning_step = 0")
    avg_ef = cursor.fetchone()[0]

    print(f"\n--- Statistics ---")
    print(f"  Total words: {total}")
    print(f"  In learning: {learning}")
    print(f"  Graduated (SM-2): {graduated}")
    print(f"  Pending now: {pending}")
    if avg_ef:
        print(f"  Average EF (graduated): {avg_ef:.2f}")


def cmd_list(conn: sqlite3.Connection) -> None:
    """List all words in the database."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT word, pos, meaning, learning_step, repetitions, interval, easiness_factor, next_review
        FROM vocab
        ORDER BY word ASC
    """)

    rows = cursor.fetchall()

    if not rows:
        print("\nNo words in database. Use 'add' to add some!")
        return

    print(f"\n--- All Words ({len(rows)}) ---")
    for row in rows:
        pos_str = f" ({row['pos']})" if row['pos'] else ""
        print(f"  {row['word']}{pos_str}: {row['meaning']}")

        step = row['learning_step']
        time_until = format_time_until(row['next_review'])
        if step > 0:
            print(f"    [Learning step {step}/{len(LEARNING_STEPS)}] next: {time_until}")
        else:
            print(f"    [SM-2] reps: {row['repetitions']}, interval: {row['interval']}d, "
                  f"EF: {row['easiness_factor']:.2f}, next: {time_until}")


def cmd_wait(conn: sqlite3.Connection) -> None:
    """Wait for a specified number of seconds (test mode only)."""
    if not TEST_MODE:
        print("Wait command only available in test mode.")
        return

    try:
        seconds = input("Wait seconds (or Enter for 1s): ").strip()
        wait_time = float(seconds) if seconds else 1.0
    except ValueError:
        print("Invalid number.")
        return

    import time
    print(f"Waiting {wait_time}s...", end="", flush=True)
    time.sleep(wait_time)
    print(" done.")


def show_help() -> None:
    """Display available commands."""
    help_text = """
--- TOEIC Vocabulary Trainer ---
Commands:
  add     - Add a new word
  pending - Show words due for review
  review  - Start a review session
  list    - List all words
  stats   - Show statistics
  help    - Show this help message
  exit    - Quit the program
"""
    if TEST_MODE:
        help_text += "  wait    - Wait N seconds (test mode)\n"
    print(help_text)


def main() -> None:
    """Main entry point for the CLI application."""
    print("=" * 40)
    print("  TOEIC Vocabulary Trainer (SM-2)")
    print("=" * 40)
    if TEST_MODE:
        print("  *** TEST MODE (1000x speed) ***")
        print("  1 min = 0.06s, 10 min = 0.6s, 1 day = 86.4s")
        print("=" * 40)
    print("Type 'help' for available commands.\n")

    conn = get_connection()

    commands = {
        'add': cmd_add,
        'pending': cmd_pending,
        'review': cmd_review,
        'list': cmd_list,
        'stats': cmd_stats,
        'wait': cmd_wait,
        'help': lambda _: show_help(),
    }

    try:
        while True:
            try:
                user_input = input("> ").strip().lower()
            except EOFError:
                break

            if not user_input:
                continue

            if user_input in ('exit', 'quit', 'q'):
                print("Goodbye!")
                break

            if user_input in commands:
                commands[user_input](conn)
            else:
                print(f"Unknown command: '{user_input}'. Type 'help' for available commands.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
