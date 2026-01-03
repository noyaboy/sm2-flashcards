Act as a Senior Python Developer. I need a CLI-based vocabulary learning tool for my TOEIC preparation.

### Project Goal
Build a local Python application that uses the **SuperMemo-2 (SM-2) algorithm** to schedule vocabulary reviews based on the Ebbinghaus Forgetting Curve.

### Tech Stack
- Language: Python 3.x (Standard libraries only, no pip install required if possible)
- Database: SQLite (local file: `toeic_vocab.db`)

### Core Features & Logic
1.  **Database Schema**:
    - Table `vocab`: id, word, meaning, repetitions (n), interval (I), easiness_factor (EF), next_review_date.
    - Default `EF` should be 2.5.

2.  **SM-2 Algorithm Implementation**:
    - The user rates a word as:
      - (1) **Forgot**: Quality = 0. Reset repetitions to 0, interval to 1 day. Penalize EF.
      - (2) **Hard/Medium**: Quality = 3. Interval grows slowly. EF lowers slightly.
      - (3) **Easy**: Quality = 5. Interval grows exponentially. EF increases.
    - **Formula**:
      - $I_1 = 1$, $I_2 = 6$
      - $I_n = I_{n-1} \times EF$ (rounded up)
      - $EF' = EF + (0.1 - (5-q) \times (0.08 + (5-q) \times 0.02))$
      - Minimum EF = 1.3

3.  **CLI Workflow**:
    - Command `add`: Prompt for Word and Meaning. Save to DB.
    - Command `pending`: Query words where `next_review_date <= NOW`.
    - Review Loop: Show word -> User presses Enter to see meaning -> User inputs rating (1/2/3) -> Update DB with new schedule.
    - Command `exit`: Quit.

### Output Requirements
- Provide a single, clean, runnable Python script file.
- Add comments explaining the SM-2 math logic.
- Ensure the database initializes automatically if it doesn't exist.
