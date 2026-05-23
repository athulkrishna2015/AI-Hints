from aqt import mw
from aqt.qt import *

class AdvancedTabMixin:
    def _create_advanced_tab(self):
        """Constructs the Tab 3: Advanced UI"""
        self.advanced_tab = QWidget()
        adv_layout = QVBoxLayout()
        
        # Migration Section
        mig_group = QGroupBox("Migration Tools")
        mig_layout = QVBoxLayout()
        mig_layout.addWidget(QLabel("AI-Hints now saves data exclusively to the <b>first field</b> of every card to ensure visibility on the front side."))
        
        self.migrate_btn = QPushButton("🚀 Move all AI data to the first field")
        self.migrate_btn.setToolTip("Searches all fields in your entire collection and moves any AI-Hints data blocks to the first field of the note.")
        self.migrate_btn.setStyleSheet("font-weight: bold; padding: 5px;")
        self.migrate_btn.clicked.connect(self.on_migrate_data)
        mig_layout.addWidget(self.migrate_btn)
        
        mig_group.setLayout(mig_layout)
        adv_layout.addWidget(mig_group)

        # Maintenance Section
        maint_group = QGroupBox("Maintenance Tools")
        maint_layout = QVBoxLayout()
        maint_layout.addWidget(QLabel("Scan for and clean up orphaned/empty hints that no longer correspond to any cards (e.g. if you removed a cloze deletion)."))
        
        self.clean_orphans_btn = QPushButton("🧹 Scan & Clean Orphaned Hints")
        self.clean_orphans_btn.setToolTip("Scans all cards to detect AI hints that do not correspond to any active cards and list them to remove that data.")
        self.clean_orphans_btn.setStyleSheet("font-weight: bold; padding: 5px;")
        self.clean_orphans_btn.clicked.connect(self.on_scan_orphans)
        maint_layout.addWidget(self.clean_orphans_btn)
        
        maint_group.setLayout(maint_layout)
        adv_layout.addWidget(maint_group)

        adv_layout.addWidget(QLabel("System Prompt:"))
        self.system_prompt_edit = QTextEdit()
        self.system_prompt_edit.setToolTip("Customize the core AI persona instructions defining generation constraints, math syntaxes, and output layout.")
        adv_layout.addWidget(self.system_prompt_edit)
        
        # Raw Editor Toggle
        self.raw_toggle = QPushButton("Show Raw JSON Editor")
        self.raw_toggle.setCheckable(True)
        self.raw_toggle.setToolTip("Directly inspect and write the raw serialization JSON for fine-grained control.")
        adv_layout.addWidget(self.raw_toggle)
        
        self.raw_editor = QTextEdit()
        self.raw_editor.setVisible(False)
        self.raw_toggle.toggled.connect(self.raw_editor.setVisible)
        adv_layout.addWidget(self.raw_editor)
        
        adv_layout.addStretch()
        
        self.advanced_tab.setLayout(adv_layout)
        return self.advanced_tab
