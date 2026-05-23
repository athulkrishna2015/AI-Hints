from aqt import mw
from aqt.qt import *

class AdvancedTabMixin:
    def _create_advanced_tab(self):
        """Constructs the Tab 3: Advanced UI"""
        self.advanced_tab = QWidget()
        adv_layout = QVBoxLayout()

        # System Prompt (at top)
        adv_layout.addWidget(QLabel("System Prompt:"))
        self.system_prompt_edit = QTextEdit()
        self.system_prompt_edit.setToolTip("Customize the core AI persona instructions defining generation constraints, math syntaxes, and output layout.")
        adv_layout.addWidget(self.system_prompt_edit)

        # Migration Section
        mig_group = QGroupBox("Migration Tools")
        mig_layout = QVBoxLayout()
        mig_layout.addWidget(QLabel("AI-Hints now saves data exclusively to the <b>first field</b> of every card to ensure visibility on the front side."))
        
        self.migrate_btn = QPushButton("🚀 Move all AI data to the first field")
        self.migrate_btn.setToolTip("Searches all fields in your entire collection and moves any AI-Hints data blocks to the first field of the note.")
        self.migrate_btn.setStyleSheet("padding: 4px 10px;")
        self.migrate_btn.clicked.connect(self.on_migrate_data)
        
        mig_btn_layout = QHBoxLayout()
        mig_btn_layout.addStretch()
        mig_btn_layout.addWidget(self.migrate_btn)
        mig_layout.addLayout(mig_btn_layout)
        
        mig_group.setLayout(mig_layout)
        adv_layout.addWidget(mig_group)

        # Maintenance Section
        maint_group = QGroupBox("Maintenance Tools")
        maint_layout = QVBoxLayout()
        maint_layout.addWidget(QLabel("Scan for and clean up orphaned/empty hints that no longer correspond to any cards (e.g. if you removed a cloze deletion)."))
        
        self.clean_orphans_btn = QPushButton("🧹 Scan & Clean Orphaned Hints")
        self.clean_orphans_btn.setToolTip("Scans all cards to detect AI hints that do not correspond to any active cards and list them to remove that data.")
        self.clean_orphans_btn.setStyleSheet("padding: 4px 10px;")
        self.clean_orphans_btn.clicked.connect(self.on_scan_orphans)
        
        clean_btn_layout = QHBoxLayout()
        clean_btn_layout.addStretch()
        clean_btn_layout.addWidget(self.clean_orphans_btn)
        maint_layout.addLayout(clean_btn_layout)

        maint_layout.addWidget(QLabel("Convert all legacy unicode escape codes (like \\u0d38) into readable characters and pretty-print existing card JSON blocks."))
        
        self.format_unicode_btn = QPushButton("📝 Convert Unicode Escapes to Normal Text")
        self.format_unicode_btn.setToolTip("Scan your entire collection and convert legacy JSON blocks with hex escapes (e.g. \\uXXXX) into clean, pretty-printed readable text.")
        self.format_unicode_btn.setStyleSheet("padding: 4px 10px;")
        self.format_unicode_btn.clicked.connect(self.on_convert_unicode_escapes)
        
        unicode_btn_layout = QHBoxLayout()
        unicode_btn_layout.addStretch()
        unicode_btn_layout.addWidget(self.format_unicode_btn)
        maint_layout.addLayout(unicode_btn_layout)
        
        maint_group.setLayout(maint_layout)
        adv_layout.addWidget(maint_group)

        # Raw Editor Toggle
        self.raw_toggle = QPushButton("Show Raw JSON Editor")
        self.raw_toggle.setCheckable(True)
        self.raw_toggle.setToolTip("Directly inspect and write the raw serialization JSON for fine-grained control.")
        self.raw_toggle.setStyleSheet("padding: 4px 10px;")
        
        raw_btn_layout = QHBoxLayout()
        raw_btn_layout.addStretch()
        raw_btn_layout.addWidget(self.raw_toggle)
        adv_layout.addLayout(raw_btn_layout)
        
        self.raw_editor = QTextEdit()
        self.raw_editor.setVisible(False)
        self.raw_toggle.toggled.connect(self.raw_editor.setVisible)
        adv_layout.addWidget(self.raw_editor)
        
        adv_layout.addStretch()
        
        self.advanced_tab.setLayout(adv_layout)
        return self.advanced_tab
