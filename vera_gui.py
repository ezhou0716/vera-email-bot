"""Vera Email Bot — PyQt6 GUI

A 4-page GUI that lets users enter a prompt, review leads, edit emails,
and send with full editorial control. Replaces the CLI y/n confirmation.
"""

import sys
import json
import time

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QAbstractTableModel, QModelIndex
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QTextEdit, QLineEdit, QTableView,
    QScrollArea, QProgressBar, QCheckBox, QMessageBox, QHeaderView,
    QFrame, QSizePolicy, QAbstractItemView,
)
from PyQt6.QtGui import QFont

from prompt_engine import parse_prompt, generate_email, configure_genai
from lead_finder import find_leads
from email_sender import authenticate_gmail, create_message, send_single_email

CONFIG_FILE = "config.json"


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
    if not config.get("gemini_api_key") or config["gemini_api_key"].startswith("YOUR_"):
        raise ValueError("Set a valid 'gemini_api_key' in config.json")
    if not config.get("hunter_api_key") or config["hunter_api_key"].startswith("YOUR_"):
        print("Warning: No valid 'hunter_api_key' in config.json — will use free web scraping instead.")
    return config


# ---------------------------------------------------------------------------
# QThread Workers
# ---------------------------------------------------------------------------

class PromptParseWorker(QThread):
    finished = pyqtSignal(dict, dict)  # search_criteria, email_intent
    error = pyqtSignal(str)

    def __init__(self, prompt, model_name):
        super().__init__()
        self.prompt = prompt
        self.model_name = model_name

    def run(self):
        try:
            criteria, intent = parse_prompt(self.prompt, self.model_name)
            self.finished.emit(criteria, intent)
        except Exception as e:
            self.error.emit(str(e))


class LeadSearchWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, criteria, hunter_key, google_key, google_cx,
                 hunter_limit, google_limit, max_leads,
                 scraping_timeout=10, scraping_max_pages=5):
        super().__init__()
        self.criteria = criteria
        self.hunter_key = hunter_key
        self.google_key = google_key
        self.google_cx = google_cx
        self.hunter_limit = hunter_limit
        self.google_limit = google_limit
        self.max_leads = max_leads
        self.scraping_timeout = scraping_timeout
        self.scraping_max_pages = scraping_max_pages

    def run(self):
        try:
            leads = find_leads(
                self.criteria,
                hunter_api_key=self.hunter_key,
                google_search_api_key=self.google_key,
                google_search_cx=self.google_cx,
                hunter_limit=self.hunter_limit,
                google_search_limit=self.google_limit,
                max_leads=self.max_leads,
                scraping_timeout=self.scraping_timeout,
                scraping_max_pages=self.scraping_max_pages,
            )
            self.finished.emit(leads)
        except Exception as e:
            self.error.emit(str(e))


class EmailGenerationWorker(QThread):
    progress = pyqtSignal(int, int, dict)  # index, total, email_data
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, leads, email_intent, model_name):
        super().__init__()
        self.leads = leads
        self.email_intent = email_intent
        self.model_name = model_name

    def run(self):
        try:
            emails = []
            total = len(self.leads)
            for i, lead in enumerate(self.leads):
                try:
                    email_data = generate_email(
                        lead, self.email_intent, self.model_name
                    )
                except Exception:
                    email_data = None
                emails.append(email_data)
                self.progress.emit(i, total, email_data or {})
            self.finished.emit(emails)
        except Exception as e:
            self.error.emit(str(e))


class GmailAuthWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def run(self):
        try:
            service = authenticate_gmail()
            self.finished.emit(service)
        except Exception as e:
            self.error.emit(str(e))


class EmailSendWorker(QThread):
    progress = pyqtSignal(int, str, bool)  # index, recipient, success
    finished = pyqtSignal(int, int)  # sent, failed
    error = pyqtSignal(str)

    def __init__(self, service, send_list, send_delay):
        super().__init__()
        self.service = service
        self.send_list = send_list  # list of (to, subject, body)
        self.send_delay = send_delay

    def run(self):
        try:
            sent = 0
            failed = 0
            for i, (to, subject, body) in enumerate(self.send_list):
                message = create_message({"to": to, "subject": subject, "body": body})
                success = send_single_email(self.service, message, to)
                if success:
                    sent += 1
                else:
                    failed += 1
                self.progress.emit(i, to, success)
                if i < len(self.send_list) - 1:
                    time.sleep(self.send_delay)
            self.finished.emit(sent, failed)
        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# Lead Table Model
# ---------------------------------------------------------------------------

class LeadTableModel(QAbstractTableModel):
    COLUMNS = ["Include", "Name", "Email", "Company", "Role"]

    def __init__(self, leads=None):
        super().__init__()
        self._leads = leads or []
        self._checked = [True] * len(self._leads)

    def set_leads(self, leads):
        self.beginResetModel()
        self._leads = leads
        self._checked = [True] * len(leads)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._leads)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        lead = self._leads[row]
        if col == 0:
            if role == Qt.ItemDataRole.CheckStateRole:
                return Qt.CheckState.Checked if self._checked[row] else Qt.CheckState.Unchecked
            return None
        keys = [None, "name", "email", "company", "role"]
        if role == Qt.ItemDataRole.DisplayRole:
            return lead.get(keys[col], "") or ""
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            self._checked[index.row()] = value == Qt.CheckState.Checked
            self.dataChanged.emit(index, index, [role])
            return True
        return False

    def flags(self, index):
        base = super().flags(index)
        if index.column() == 0:
            return base | Qt.ItemFlag.ItemIsUserCheckable
        return base

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.COLUMNS[section]
        return None

    def selected_leads(self):
        return [l for l, c in zip(self._leads, self._checked) if c]

    def set_all_checked(self, checked):
        self.beginResetModel()
        self._checked = [checked] * len(self._leads)
        self.endResetModel()

    def selected_count(self):
        return sum(self._checked)


# ---------------------------------------------------------------------------
# Email Preview Card
# ---------------------------------------------------------------------------

class EmailPreviewCard(QFrame):
    toggled = pyqtSignal()

    def __init__(self, lead, email_data, parent=None):
        super().__init__(parent)
        self.lead = lead
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setLineWidth(1)
        self.setStyleSheet("EmailPreviewCard { border: 1px solid #ccc; border-radius: 6px; padding: 8px; margin: 4px; }")

        layout = QVBoxLayout(self)

        # Header row: checkbox + recipient info
        header = QHBoxLayout()
        self.checkbox = QCheckBox("Include")
        self.checkbox.setChecked(True)
        self.checkbox.stateChanged.connect(lambda: self.toggled.emit())
        header.addWidget(self.checkbox)

        name = lead.get("name") or "(unknown)"
        info = QLabel(f"<b>{name}</b> — {lead['email']}  ({lead.get('company', '')})")
        info.setWordWrap(True)
        header.addWidget(info, 1)
        layout.addLayout(header)

        # Subject
        layout.addWidget(QLabel("Subject:"))
        self.subject_edit = QLineEdit()
        self.subject_edit.setText(email_data.get("subject", ""))
        layout.addWidget(self.subject_edit)

        # Body
        layout.addWidget(QLabel("Body:"))
        self.body_edit = QTextEdit()
        self.body_edit.setPlainText(email_data.get("body", ""))
        self.body_edit.setMinimumHeight(120)
        self.body_edit.setMaximumHeight(250)
        layout.addWidget(self.body_edit)

    def is_checked(self):
        return self.checkbox.isChecked()

    def get_email_data(self):
        return {
            "to": self.lead["email"],
            "subject": self.subject_edit.text(),
            "body": self.body_edit.toPlainText(),
        }


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class VeraMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vera Email Bot")
        self.setMinimumSize(800, 600)
        self.resize(950, 700)

        # State
        self._config = None
        self._search_criteria = None
        self._email_intent = None
        self._leads = []
        self._emails = []
        self._email_cards = []
        self._worker = None  # keep reference so GC doesn't kill the thread

        # Load config once
        try:
            self._config = load_config()
            configure_genai(self._config["gemini_api_key"])
        except Exception as e:
            QMessageBox.critical(self, "Config Error", str(e))
            sys.exit(1)

        settings = self._config.get("settings", {})
        self._gemini_key = self._config["gemini_api_key"]
        self._hunter_key = self._config.get("hunter_api_key", "")
        gk = self._config.get("google_search_api_key", "")
        self._google_key = gk if gk and not gk.startswith("YOUR_") else None
        gc = self._config.get("google_search_cx", "")
        self._google_cx = gc if gc and not gc.startswith("YOUR_") else None
        self._model_name = settings.get("gemini_model", "gemini-2.0-flash")
        self._max_leads = settings.get("max_leads", 10)
        self._send_delay = settings.get("gmail_send_delay_seconds", 2)
        self._hunter_limit = settings.get("hunter_results_limit", 10)
        self._google_limit = settings.get("google_search_results_limit", 5)
        self._scraping_timeout = settings.get("scraping_timeout_seconds", 10)
        self._scraping_max_pages = settings.get("scraping_max_pages_per_domain", 5)

        # Stacked widget
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._build_page0_prompt()
        self._build_page1_leads()
        self._build_page2_emails()
        self._build_page3_progress()

    # --- Page 0: Prompt Input ---
    def _build_page0_prompt(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("Vera Email Bot")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Enter your outreach prompt below, then click Start Search.")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        self._prompt_edit = QTextEdit()
        self._prompt_edit.setPlaceholderText(
            "Examples:\n"
            '  "Find CTOs at AI startups and pitch our analytics tool"\n'
            '  "Reach out to marketing managers at Shopify about our SEO product"\n'
            '  "Contact engineering leads at fintech companies about our API platform"'
        )
        self._prompt_edit.setMinimumHeight(120)
        self._prompt_edit.setMaximumHeight(200)
        layout.addWidget(self._prompt_edit)

        self._start_btn = QPushButton("Start Search")
        self._start_btn.setMinimumHeight(40)
        self._start_btn.clicked.connect(self._on_start_search)
        layout.addWidget(self._start_btn)

        self._prompt_status = QLabel("")
        self._prompt_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._prompt_status)

        layout.addStretch()
        self._stack.addWidget(page)

    # --- Page 1: Lead Review ---
    def _build_page1_leads(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        self._criteria_label = QLabel("")
        self._criteria_label.setWordWrap(True)
        layout.addWidget(self._criteria_label)

        self._lead_model = LeadTableModel()
        self._lead_table = QTableView()
        self._lead_table.setModel(self._lead_model)
        self._lead_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._lead_table.horizontalHeader().setStretchLastSection(True)
        self._lead_table.verticalHeader().setVisible(False)
        layout.addWidget(self._lead_table, 1)

        btn_row = QHBoxLayout()
        sel_all = QPushButton("Select All")
        sel_all.clicked.connect(lambda: self._lead_model.set_all_checked(True))
        desel_all = QPushButton("Deselect All")
        desel_all.clicked.connect(lambda: self._lead_model.set_all_checked(False))
        btn_row.addWidget(sel_all)
        btn_row.addWidget(desel_all)
        btn_row.addStretch()

        back_btn = QPushButton("Back")
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        btn_row.addWidget(back_btn)

        self._gen_btn = QPushButton("Generate Emails")
        self._gen_btn.setMinimumHeight(36)
        self._gen_btn.clicked.connect(self._on_generate_emails)
        btn_row.addWidget(self._gen_btn)
        layout.addLayout(btn_row)

        self._stack.addWidget(page)

    # --- Page 2: Email Preview & Edit ---
    def _build_page2_emails(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        self._email_gen_status = QLabel("")
        layout.addWidget(self._email_gen_status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._email_list_widget = QWidget()
        self._email_list_layout = QVBoxLayout(self._email_list_widget)
        self._email_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._email_list_widget)
        layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        back_btn = QPushButton("Back to Leads")
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(1))
        btn_row.addWidget(back_btn)
        btn_row.addStretch()

        self._send_btn = QPushButton("Send 0 Emails")
        self._send_btn.setMinimumHeight(36)
        self._send_btn.clicked.connect(self._on_send)
        btn_row.addWidget(self._send_btn)
        layout.addLayout(btn_row)

        self._stack.addWidget(page)

    # --- Page 3: Send Progress ---
    def _build_page3_progress(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)

        self._progress_bar = QProgressBar()
        self._progress_bar.setValue(0)
        layout.addWidget(self._progress_bar)

        self._send_log = QTextEdit()
        self._send_log.setReadOnly(True)
        layout.addWidget(self._send_log, 1)

        self._summary_label = QLabel("")
        self._summary_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._summary_label)

        self._new_btn = QPushButton("New Outreach")
        self._new_btn.setMinimumHeight(40)
        self._new_btn.clicked.connect(self._reset)
        self._new_btn.setVisible(False)
        layout.addWidget(self._new_btn)

        self._stack.addWidget(page)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_start_search(self):
        prompt = self._prompt_edit.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "Empty Prompt", "Please enter an outreach prompt.")
            return
        self._start_btn.setEnabled(False)
        self._prompt_status.setText("Parsing prompt with Gemini...")

        self._worker = PromptParseWorker(prompt, self._model_name)
        self._worker.finished.connect(self._on_prompt_parsed)
        self._worker.error.connect(self._on_prompt_error)
        self._worker.start()

    def _on_prompt_parsed(self, criteria, intent):
        self._search_criteria = criteria
        self._email_intent = intent
        self._prompt_status.setText("Searching for leads...")

        self._worker = LeadSearchWorker(
            criteria, self._hunter_key, self._google_key, self._google_cx,
            self._hunter_limit, self._google_limit, self._max_leads,
            self._scraping_timeout, self._scraping_max_pages,
        )
        self._worker.finished.connect(self._on_leads_found)
        self._worker.error.connect(self._on_prompt_error)
        self._worker.start()

    def _on_leads_found(self, leads):
        self._start_btn.setEnabled(True)
        self._prompt_status.setText("")
        if not leads:
            QMessageBox.information(
                self, "No Leads",
                "No leads found. Try a different prompt or check your API keys."
            )
            return

        self._leads = leads
        self._lead_model.set_leads(leads)

        # Resize columns nicely
        header = self._lead_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for col in range(1, self._lead_model.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)

        # Show criteria summary
        roles = ", ".join(self._search_criteria.get("roles", []))
        purpose = self._email_intent.get("purpose", "")
        self._criteria_label.setText(
            f"<b>Target roles:</b> {roles}<br>"
            f"<b>Email purpose:</b> {purpose}<br>"
            f"<b>Leads found:</b> {len(leads)}"
        )
        self._stack.setCurrentIndex(1)

    def _on_prompt_error(self, msg):
        self._start_btn.setEnabled(True)
        self._prompt_status.setText("")
        QMessageBox.critical(self, "Error", msg)

    # --- Email generation ---

    def _on_generate_emails(self):
        selected = self._lead_model.selected_leads()
        if not selected:
            QMessageBox.warning(self, "No Leads Selected", "Select at least one lead.")
            return

        self._leads = selected
        self._gen_btn.setEnabled(False)
        self._email_gen_status.setText("Generating emails...")
        self._email_cards.clear()

        # Clear previous cards
        while self._email_list_layout.count():
            item = self._email_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._stack.setCurrentIndex(2)
        self._send_btn.setEnabled(False)

        self._worker = EmailGenerationWorker(
            selected, self._email_intent, self._model_name
        )
        self._worker.progress.connect(self._on_email_gen_progress)
        self._worker.finished.connect(self._on_email_gen_done)
        self._worker.error.connect(self._on_email_gen_error)
        self._worker.start()

    def _on_email_gen_progress(self, index, total, email_data):
        lead = self._leads[index]
        self._email_gen_status.setText(f"Generating email {index + 1}/{total}...")
        if email_data:
            card = EmailPreviewCard(lead, email_data)
            card.toggled.connect(self._update_send_count)
            self._email_list_layout.addWidget(card)
            self._email_cards.append(card)

    def _on_email_gen_done(self, emails):
        self._emails = emails
        self._gen_btn.setEnabled(True)
        self._send_btn.setEnabled(True)
        n = sum(1 for c in self._email_cards if c.is_checked())
        self._email_gen_status.setText(f"Generated {len(self._email_cards)} email(s). Review and edit below.")
        self._send_btn.setText(f"Send {n} Email{'s' if n != 1 else ''}")

    def _on_email_gen_error(self, msg):
        self._gen_btn.setEnabled(True)
        self._email_gen_status.setText("")
        QMessageBox.critical(self, "Error", msg)

    def _update_send_count(self):
        n = sum(1 for c in self._email_cards if c.is_checked())
        self._send_btn.setText(f"Send {n} Email{'s' if n != 1 else ''}")

    # --- Sending ---

    def _on_send(self):
        checked = [c for c in self._email_cards if c.is_checked()]
        if not checked:
            QMessageBox.warning(self, "No Emails Selected", "Check at least one email to send.")
            return

        reply = QMessageBox.question(
            self, "Confirm Send",
            f"Send {len(checked)} email(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._send_btn.setEnabled(False)
        self._progress_bar.setMaximum(len(checked))
        self._progress_bar.setValue(0)
        self._send_log.clear()
        self._summary_label.setText("")
        self._new_btn.setVisible(False)
        self._stack.setCurrentIndex(3)

        # Build send list from card contents (user may have edited)
        send_list = []
        for card in checked:
            d = card.get_email_data()
            send_list.append((d["to"], d["subject"], d["body"]))

        self._send_list_count = len(send_list)

        # Authenticate first, then send
        self._send_data = send_list
        self._send_log.append("Authenticating with Gmail...")

        self._worker = GmailAuthWorker()
        self._worker.finished.connect(self._on_gmail_authed)
        self._worker.error.connect(self._on_send_error)
        self._worker.start()

    def _on_gmail_authed(self, service):
        self._send_log.append("Authenticated. Sending emails...\n")

        self._worker = EmailSendWorker(service, self._send_data, self._send_delay)
        self._worker.progress.connect(self._on_send_progress)
        self._worker.finished.connect(self._on_send_done)
        self._worker.error.connect(self._on_send_error)
        self._worker.start()

    def _on_send_progress(self, index, recipient, success):
        status = "Sent" if success else "FAILED"
        self._send_log.append(f"  [{index + 1}/{self._send_list_count}] {recipient} — {status}")
        self._progress_bar.setValue(index + 1)

    def _on_send_done(self, sent, failed):
        self._summary_label.setText(f"Done!  Sent: {sent}  |  Failed: {failed}")
        self._new_btn.setVisible(True)

    def _on_send_error(self, msg):
        self._send_log.append(f"\nError: {msg}")
        self._summary_label.setText("Sending stopped due to an error.")
        self._new_btn.setVisible(True)

    # --- Reset ---

    def _reset(self):
        self._prompt_edit.clear()
        self._prompt_status.setText("")
        self._leads.clear()
        self._emails.clear()
        self._email_cards.clear()
        self._search_criteria = None
        self._email_intent = None
        self._lead_model.set_leads([])
        self._progress_bar.setValue(0)
        self._send_log.clear()
        self._summary_label.setText("")
        self._new_btn.setVisible(False)

        # Clear email cards
        while self._email_list_layout.count():
            item = self._email_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._stack.setCurrentIndex(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    window = VeraMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
