# SM2 Flashcards

A vocabulary learning tool using the SuperMemo-2 (SM-2) spaced repetition algorithm with Anki-style learning steps.

## Features

- **SM-2 Algorithm**: Optimized review scheduling based on memory retention research
- **Anki-style Learning Steps**: New cards go through 1min → 10min → 1day before graduating
- **Multi-definition Support**: Auto-fetches top 5 definitions for polysemous words
- **Chinese Translation**: Automatic Traditional Chinese translation for definitions
- **PyQt6 GUI**: Clean tabbed interface with Review, Add Word, Word List, and Statistics tabs
- **Standalone Executable**: No Python installation required

## Installation

### From Source

```bash
pip install -r requirements.txt
python vocab_gui.py
```

### Test Mode

Run with 1000x speed for testing (1 day = 86.4 seconds):

```bash
python vocab_gui.py --test
```

## Usage

### Adding Words

1. Go to "Add Word" tab
2. Enter a word and click "Lookup"
3. Top 5 definitions are auto-selected with Chinese translations
4. Click "Add Word" to save

### Reviewing

1. Go to "Review" tab
2. Click "Start Review" when words are pending
3. Rate each word:
   - **Forgot (1)**: Reset to beginning
   - **Hard (2)**: Repeat current step
   - **Easy (3)**: Advance to next step

### Rating System

| Rating | Learning Phase | SM-2 Phase |
|--------|----------------|------------|
| Forgot | Reset to step 1 | Back to learning |
| Hard | Repeat current step | Slower interval growth |
| Easy | Advance step | Exponential interval growth |

## Building Standalone Executable

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "VocabTrainer" vocab_gui.py
```

Executable will be in `dist/VocabTrainer`.

## APIs Used

- [Free Dictionary API](https://dictionaryapi.dev/) - Word definitions
- [MyMemory Translation API](https://mymemory.translated.net/) - Chinese translations

## License

MIT
