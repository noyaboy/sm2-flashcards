#!/usr/bin/env python3
"""
TOEIC Vocabulary Learning Tool - GUI Version
PyQt6-based graphical interface for vocabulary learning with SM-2 algorithm.

Usage:
    python vocab_gui.py          # Normal mode
    python vocab_gui.py --test   # Test mode (1000x speed: 1 day = 86.4s)
"""

import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QLineEdit, QTextEdit, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QMessageBox,
    QSpacerItem, QSizePolicy, QGridLayout, QDialog, QListWidget,
    QListWidgetItem, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

# Import core logic from vocab_trainer.py
from vocab_trainer import (
    get_connection, lookup_word, lookup_all_meanings, translate_to_chinese,
    format_time_until, get_pending_words, get_all_words, get_stats,
    add_word_to_db, submit_rating, clear_all_words, delete_word_by_id,
    LEARNING_STEPS, TEST_MODE
)


class MeaningSelectionDialog(QDialog):
    """Dialog to select from multiple word meanings."""

    def __init__(self, word: str, meanings: list, parent=None):
        super().__init__(parent)
        self.word = word
        self.meanings = meanings
        self.selected_meaning = None
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle(f"Select Meaning for '{self.word}'")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)

        # Header
        header = QLabel(f"Found {len(self.meanings)} meanings for '{self.word}':")
        header.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(header)

        # Meanings list
        self.list_widget = QListWidget()
        self.list_widget.setFont(QFont("Arial", 11))
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.itemDoubleClicked.connect(self.accept)

        for i, meaning in enumerate(self.meanings, 1):
            pos = meaning['pos']
            definition = meaning['definition']
            example = meaning.get('example', '')

            # Format display text
            text = f"{i}. ({pos}) {definition}"
            if example:
                text += f"\n    Example: {example}"

            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, meaning)
            self.list_widget.addItem(item)

        self.list_widget.setCurrentRow(0)
        layout.addWidget(self.list_widget)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def accept(self):
        current_item = self.list_widget.currentItem()
        if current_item:
            self.selected_meaning = current_item.data(Qt.ItemDataRole.UserRole)
        super().accept()

    def get_selected_meaning(self):
        return self.selected_meaning


class ReviewTab(QWidget):
    """Flashcard-style review interface."""

    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.current_word = None
        self.meaning_revealed = False
        self.pending_words = []
        self.review_count = 0
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 20, 30, 20)

        # Header with pending count and start button
        header_layout = QHBoxLayout()
        self.pending_label = QLabel("Pending: 0 words")
        self.pending_label.setFont(QFont("Arial", 12))
        header_layout.addWidget(self.pending_label)
        header_layout.addStretch()
        self.start_btn = QPushButton("Start Review")
        self.start_btn.setFont(QFont("Arial", 11))
        self.start_btn.setMinimumWidth(120)
        self.start_btn.clicked.connect(self.start_review)
        header_layout.addWidget(self.start_btn)
        layout.addLayout(header_layout)

        # Flashcard frame
        self.card_frame = QFrame()
        self.card_frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.card_frame.setLineWidth(2)
        self.card_frame.setMinimumHeight(250)
        card_layout = QVBoxLayout(self.card_frame)
        card_layout.setSpacing(15)
        card_layout.setContentsMargins(30, 30, 30, 30)

        # Word display
        self.word_label = QLabel("")
        self.word_label.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        self.word_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.word_label)

        # Status label (learning step or SM-2 info)
        self.status_label = QLabel("")
        self.status_label.setFont(QFont("Arial", 11))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #666;")
        card_layout.addWidget(self.status_label)

        # Separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        card_layout.addWidget(separator)

        # Meaning display (hidden until revealed)
        self.pos_label = QLabel("")
        self.pos_label.setFont(QFont("Arial", 12, italic=True))
        self.pos_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pos_label.setStyleSheet("color: #888;")
        card_layout.addWidget(self.pos_label)

        self.meaning_label = QLabel("")
        self.meaning_label.setFont(QFont("Arial", 14))
        self.meaning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.meaning_label.setWordWrap(True)
        card_layout.addWidget(self.meaning_label)

        # Chinese translation display
        self.chinese_label = QLabel("")
        self.chinese_label.setFont(QFont("Arial", 16))
        self.chinese_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chinese_label.setWordWrap(True)
        self.chinese_label.setStyleSheet("color: #0066cc;")
        card_layout.addWidget(self.chinese_label)

        # Reveal button
        self.reveal_btn = QPushButton("Show Answer")
        self.reveal_btn.setFont(QFont("Arial", 12))
        self.reveal_btn.setMinimumHeight(40)
        self.reveal_btn.clicked.connect(self.reveal_meaning)
        self.reveal_btn.setVisible(False)
        card_layout.addWidget(self.reveal_btn)

        layout.addWidget(self.card_frame)

        # Rating buttons
        rating_layout = QHBoxLayout()
        rating_layout.setSpacing(20)

        self.forgot_btn = QPushButton("Forgot (1)")
        self.forgot_btn.setFont(QFont("Arial", 12))
        self.forgot_btn.setMinimumHeight(50)
        self.forgot_btn.setMinimumWidth(120)
        self.forgot_btn.setStyleSheet("background-color: #ffcccc;")
        self.forgot_btn.clicked.connect(lambda: self.submit_rating(1))
        rating_layout.addWidget(self.forgot_btn)

        self.hard_btn = QPushButton("Hard (2)")
        self.hard_btn.setFont(QFont("Arial", 12))
        self.hard_btn.setMinimumHeight(50)
        self.hard_btn.setMinimumWidth(120)
        self.hard_btn.setStyleSheet("background-color: #ffffcc;")
        self.hard_btn.clicked.connect(lambda: self.submit_rating(2))
        rating_layout.addWidget(self.hard_btn)

        self.easy_btn = QPushButton("Easy (3)")
        self.easy_btn.setFont(QFont("Arial", 12))
        self.easy_btn.setMinimumHeight(50)
        self.easy_btn.setMinimumWidth(120)
        self.easy_btn.setStyleSheet("background-color: #ccffcc;")
        self.easy_btn.clicked.connect(lambda: self.submit_rating(3))
        rating_layout.addWidget(self.easy_btn)

        layout.addLayout(rating_layout)

        # Feedback label
        self.feedback_label = QLabel("")
        self.feedback_label.setFont(QFont("Arial", 11))
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.feedback_label)

        layout.addStretch()

        # Initial state
        self.set_review_mode(False)

    def refresh(self):
        """Refresh pending count."""
        self.pending_words = get_pending_words(self.conn)
        count = len(self.pending_words)
        self.pending_label.setText(f"Pending: {count} word{'s' if count != 1 else ''}")

    def set_review_mode(self, reviewing):
        """Toggle between idle and review modes."""
        self.start_btn.setVisible(not reviewing)
        self.reveal_btn.setVisible(reviewing and not self.meaning_revealed)
        self.forgot_btn.setVisible(reviewing and self.meaning_revealed)
        self.hard_btn.setVisible(reviewing and self.meaning_revealed)
        self.easy_btn.setVisible(reviewing and self.meaning_revealed)

        if not reviewing:
            self.word_label.setText("Click 'Start Review' to begin")
            self.status_label.setText("")
            self.pos_label.setText("")
            self.meaning_label.setText("")
            self.chinese_label.setText("")
            self.feedback_label.setText("")

    def start_review(self):
        """Start or continue the review session."""
        self.refresh()
        if not self.pending_words:
            self.word_label.setText("No words pending!")
            self.feedback_label.setText("Add some words or wait for scheduled reviews.")
            return

        self.review_count = 0
        self.load_next_word()

    def load_next_word(self):
        """Load the next pending word."""
        self.pending_words = get_pending_words(self.conn)
        if not self.pending_words:
            self.set_review_mode(False)
            self.word_label.setText("Review Complete!")
            self.feedback_label.setText(f"Reviewed {self.review_count} word{'s' if self.review_count != 1 else ''}.")
            self.refresh()
            return

        self.current_word = self.pending_words[0]
        self.meaning_revealed = False
        self.set_review_mode(True)

        # Display word
        self.word_label.setText(self.current_word['word'])

        # Status info
        if self.current_word['learning_step'] > 0:
            step = self.current_word['learning_step']
            total = len(LEARNING_STEPS)
            self.status_label.setText(f"Learning step {step}/{total}")
        else:
            reps = self.current_word['repetitions']
            ef = self.current_word['easiness_factor']
            self.status_label.setText(f"SM-2 Review (reps: {reps}, EF: {ef:.2f})")

        # Hide meaning
        self.pos_label.setText("")
        self.meaning_label.setText("")
        self.chinese_label.setText("")
        self.feedback_label.setText(f"Remaining: {len(self.pending_words)} word{'s' if len(self.pending_words) != 1 else ''}")
        self.reveal_btn.setVisible(True)

    def reveal_meaning(self):
        """Show the word's meaning and Chinese translation."""
        if not self.current_word:
            return

        self.meaning_revealed = True
        self.reveal_btn.setVisible(False)

        pos = self.current_word.get('pos', '')
        if pos:
            self.pos_label.setText(f"({pos})")
        self.meaning_label.setText(self.current_word['meaning'])

        # Show Chinese translation
        chinese = self.current_word.get('chinese', '')
        if chinese:
            self.chinese_label.setText(chinese)

        # Show rating buttons
        self.forgot_btn.setVisible(True)
        self.hard_btn.setVisible(True)
        self.easy_btn.setVisible(True)

    def submit_rating(self, rating):
        """Submit a rating for the current word."""
        if not self.current_word:
            return

        result = submit_rating(self.conn, self.current_word['id'], rating)
        self.review_count += 1
        self.feedback_label.setText(result['feedback'])

        # Brief delay to show feedback, then load next word
        QTimer.singleShot(500, self.load_next_word)


class AddWordTab(QWidget):
    """Form for adding new words."""

    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 20, 30, 20)

        # Title
        title = QLabel("Add New Word")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # Form layout
        form_layout = QGridLayout()
        form_layout.setSpacing(10)

        # Word input
        word_label = QLabel("Word:")
        word_label.setFont(QFont("Arial", 11))
        form_layout.addWidget(word_label, 0, 0)

        self.word_input = QLineEdit()
        self.word_input.setFont(QFont("Arial", 12))
        self.word_input.setPlaceholderText("Enter a word...")
        self.word_input.returnPressed.connect(self.add_word)
        form_layout.addWidget(self.word_input, 0, 1)

        # Chinese translation input
        chinese_label = QLabel("Chinese (繁體):")
        chinese_label.setFont(QFont("Arial", 11))
        form_layout.addWidget(chinese_label, 1, 0, Qt.AlignmentFlag.AlignTop)

        self.chinese_input = QTextEdit()
        self.chinese_input.setFont(QFont("Arial", 12))
        self.chinese_input.setMinimumHeight(60)
        self.chinese_input.setPlaceholderText("繁體中文翻譯...")
        form_layout.addWidget(self.chinese_input, 1, 1)

        layout.addLayout(form_layout)

        # Add button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.add_btn = QPushButton("Add Word")
        self.add_btn.setFont(QFont("Arial", 12))
        self.add_btn.setMinimumWidth(150)
        self.add_btn.setMinimumHeight(40)
        self.add_btn.clicked.connect(self.add_word)
        btn_layout.addWidget(self.add_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Status message
        self.status_label = QLabel("")
        self.status_label.setFont(QFont("Arial", 11))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        layout.addStretch()

    def add_word(self):
        """Add the word to the database."""
        word = self.word_input.text().strip()
        chinese = self.chinese_input.toPlainText().strip()

        result = add_word_to_db(self.conn, word, '', '', chinese)

        if result['success']:
            self.status_label.setText(result['message'])
            self.status_label.setStyleSheet("color: green;")
            self.clear_form()
            # Notify parent to refresh other tabs
            if hasattr(self.parent(), 'refresh_all_tabs'):
                self.parent().refresh_all_tabs()
        else:
            self.status_label.setText(result['message'])
            self.status_label.setStyleSheet("color: red;")

    def clear_form(self):
        """Clear all form inputs."""
        self.word_input.clear()
        self.chinese_input.clear()
        self.word_input.setFocus()


class WordListTab(QWidget):
    """Table view of all words."""

    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header with search and count
        header_layout = QHBoxLayout()

        search_label = QLabel("Search:")
        search_label.setFont(QFont("Arial", 11))
        header_layout.addWidget(search_label)

        self.search_input = QLineEdit()
        self.search_input.setFont(QFont("Arial", 11))
        self.search_input.setPlaceholderText("Filter words...")
        self.search_input.textChanged.connect(self.filter_words)
        self.search_input.setMaximumWidth(200)
        header_layout.addWidget(self.search_input)

        header_layout.addStretch()

        self.count_label = QLabel("Total: 0")
        self.count_label.setFont(QFont("Arial", 11))
        header_layout.addWidget(self.count_label)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFont(QFont("Arial", 10))
        refresh_btn.clicked.connect(self.refresh)
        header_layout.addWidget(refresh_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setFont(QFont("Arial", 10))
        self.delete_btn.clicked.connect(self.delete_selected_word)
        header_layout.addWidget(self.delete_btn)

        self.clean_btn = QPushButton("Clean List")
        self.clean_btn.setFont(QFont("Arial", 10))
        self.clean_btn.setStyleSheet("background-color: #ffcccc;")
        self.clean_btn.clicked.connect(self.show_clean_confirm)
        header_layout.addWidget(self.clean_btn)

        layout.addLayout(header_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Word", "POS", "Status", "Next Review", "EF"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        self.all_words = []

    def refresh(self):
        """Reload words from database."""
        self.all_words = get_all_words(self.conn)
        self.display_words(self.all_words)

    def display_words(self, words):
        """Display list of words in table."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(words))

        for row, word in enumerate(words):
            # Word (store ID as user data)
            item = QTableWidgetItem(word['word'])
            item.setData(Qt.ItemDataRole.UserRole, word['id'])
            self.table.setItem(row, 0, item)

            # POS
            item = QTableWidgetItem(word.get('pos', ''))
            self.table.setItem(row, 1, item)

            # Status
            if word['learning_step'] > 0:
                status = f"Learning {word['learning_step']}/{len(LEARNING_STEPS)}"
            else:
                status = f"SM-2 (reps: {word['repetitions']})"
            item = QTableWidgetItem(status)
            self.table.setItem(row, 2, item)

            # Next Review
            next_review = format_time_until(word['next_review'])
            item = QTableWidgetItem(next_review)
            self.table.setItem(row, 3, item)

            # EF
            item = QTableWidgetItem(f"{word['easiness_factor']:.2f}")
            self.table.setItem(row, 4, item)

        self.table.setSortingEnabled(True)
        self.count_label.setText(f"Total: {len(words)}")

    def filter_words(self, search_text):
        """Filter displayed words by search text."""
        if not search_text:
            self.display_words(self.all_words)
        else:
            search_lower = search_text.lower()
            filtered = [w for w in self.all_words if search_lower in w['word'].lower() or search_lower in w.get('meaning', '').lower()]
            self.display_words(filtered)

    def delete_selected_word(self):
        """Delete the currently selected word."""
        selected_row = self.table.currentRow()
        if selected_row < 0:
            QMessageBox.information(self, "Delete", "Please select a word to delete.")
            return

        item = self.table.item(selected_row, 0)
        if not item:
            return

        word_id = item.data(Qt.ItemDataRole.UserRole)
        word_text = item.text()

        reply = QMessageBox.warning(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete '{word_text}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel
        )

        if reply == QMessageBox.StandardButton.Yes:
            result = delete_word_by_id(self.conn, word_id)
            if result['success']:
                self.refresh()
                # Notify parent to refresh other tabs
                if hasattr(self.parent(), 'refresh_all_tabs'):
                    self.parent().refresh_all_tabs()

    def show_clean_confirm(self):
        """Show confirmation dialog before cleaning the word list."""
        count = len(self.all_words)
        if count == 0:
            QMessageBox.information(self, "Clean List", "The word list is already empty.")
            return

        reply = QMessageBox.warning(
            self,
            "Confirm Clean",
            f"Are you sure you want to delete all {count} word{'s' if count != 1 else ''}?\n\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel
        )

        if reply == QMessageBox.StandardButton.Yes:
            result = clear_all_words(self.conn)
            QMessageBox.information(self, "Clean List", result['message'])
            self.refresh()
            # Notify parent to refresh other tabs
            if hasattr(self.parent(), 'refresh_all_tabs'):
                self.parent().refresh_all_tabs()


class StatsTab(QWidget):
    """Statistics dashboard."""

    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(40, 30, 40, 30)

        # Title
        title = QLabel("Statistics")
        title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(20)

        # Stats grid
        stats_frame = QFrame()
        stats_frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        stats_layout = QGridLayout(stats_frame)
        stats_layout.setSpacing(15)
        stats_layout.setContentsMargins(30, 20, 30, 20)

        self.stat_labels = {}
        stat_items = [
            ("Total Words:", "total"),
            ("In Learning:", "learning"),
            ("Graduated (SM-2):", "graduated"),
            ("Pending Now:", "pending"),
            ("Average EF:", "avg_ef"),
        ]

        for row, (label_text, key) in enumerate(stat_items):
            label = QLabel(label_text)
            label.setFont(QFont("Arial", 12))
            stats_layout.addWidget(label, row, 0)

            value_label = QLabel("0")
            value_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            stats_layout.addWidget(value_label, row, 1)
            self.stat_labels[key] = value_label

        layout.addWidget(stats_frame)

        # Test mode indicator
        if TEST_MODE:
            test_label = QLabel("Test Mode: ON (1000x speed)")
            test_label.setFont(QFont("Arial", 11))
            test_label.setStyleSheet("color: orange;")
            test_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(test_label)

        layout.addStretch()

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFont(QFont("Arial", 11))
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def refresh(self):
        """Reload statistics."""
        stats = get_stats(self.conn)
        self.stat_labels['total'].setText(str(stats['total']))
        self.stat_labels['learning'].setText(str(stats['learning']))
        self.stat_labels['graduated'].setText(str(stats['graduated']))
        self.stat_labels['pending'].setText(str(stats['pending']))
        self.stat_labels['avg_ef'].setText(f"{stats['avg_ef']:.2f}" if stats['avg_ef'] else "N/A")


class MainWindow(QMainWindow):
    """Main application window with tabbed interface."""

    def __init__(self):
        super().__init__()
        self.conn = get_connection()
        self.setup_ui()

    def setup_ui(self):
        title = "TOEIC Vocabulary Trainer"
        if TEST_MODE:
            title += " [TEST MODE]"
        self.setWindowTitle(title)
        self.setMinimumSize(600, 500)
        self.resize(700, 550)

        # Central widget with tabs
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)

        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("Arial", 11))
        self.tabs.currentChanged.connect(self.on_tab_changed)

        # Create tabs
        self.review_tab = ReviewTab(self.conn, self)
        self.add_tab = AddWordTab(self.conn, self)
        self.list_tab = WordListTab(self.conn, self)
        self.stats_tab = StatsTab(self.conn, self)

        self.tabs.addTab(self.review_tab, "Review")
        self.tabs.addTab(self.add_tab, "Add Word")
        self.tabs.addTab(self.list_tab, "Word List")
        self.tabs.addTab(self.stats_tab, "Statistics")

        layout.addWidget(self.tabs)

        # Initial refresh
        self.review_tab.refresh()

    def on_tab_changed(self, index):
        """Refresh tab content when switching tabs."""
        if index == 0:
            self.review_tab.refresh()
        elif index == 2:
            self.list_tab.refresh()
        elif index == 3:
            self.stats_tab.refresh()

    def refresh_all_tabs(self):
        """Refresh all tab data (called after adding word)."""
        self.review_tab.refresh()

    def closeEvent(self, event):
        """Clean up database connection on close."""
        if self.conn:
            self.conn.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
