from aqt import mw
from aqt.qt import *

class AdvancedTabMixin:
    def _create_advanced_tab(self):
        """Constructs the Tab 3: Advanced UI"""
        self.advanced_tab = QWidget()
        adv_layout = QVBoxLayout()
        
        adv_layout.addWidget(QLabel("Target Fields (Where hints are saved, comma-separated):"))
        self.target_fields_edit = QLineEdit()
        self.target_fields_edit.setToolTip("Example: Extras, Back, Text")
        adv_layout.addWidget(self.target_fields_edit)
        
        adv_layout.addWidget(QLabel("System Prompt:"))
        self.system_prompt_edit = QTextEdit()
        self.system_prompt_edit.setToolTip("Customize the core AI persona instructions defining generation constraints, math syntaxes, and output layout.")
        adv_layout.addWidget(self.system_prompt_edit)
        
        adv_layout.addWidget(QLabel("Note Type Fields:"))
        
        if mw.col is not None:
            self.nt_selector_layout = QVBoxLayout()
            self.nt_cb = QComboBox()
            self.nt_cb.setToolTip("Switch active Note Type to edit allowed field scans.")
            self.nt_cb.currentIndexChanged.connect(self.on_nt_changed)
            self.nt_selector_layout.addWidget(self.nt_cb)
            
            self.fld_list = QListWidget()
            self.fld_list.setToolTip("Check off specifically which fields in this note type contain textual question context the AI should ingest.")
            self.fld_list.itemChanged.connect(self.on_fld_changed)
            self.nt_selector_layout.addWidget(self.fld_list)
            
            adv_layout.addLayout(self.nt_selector_layout)
            
            self.note_fields_edit = QTextEdit()
            self.note_fields_edit.setVisible(False)
        else:
            adv_layout.addWidget(QLabel("(Raw JSON editor since collection is closed)"))
            self.note_fields_edit = QTextEdit()
            self.note_fields_edit.setMaximumHeight(150)
            adv_layout.addWidget(self.note_fields_edit)
        
        # Raw Editor Toggle
        self.raw_toggle = QPushButton("Show Raw JSON Editor")
        self.raw_toggle.setCheckable(True)
        self.raw_toggle.setToolTip("Directly inspect and write the raw serialization JSON for fine-grained control.")
        adv_layout.addWidget(self.raw_toggle)
        
        self.raw_editor = QTextEdit()
        self.raw_editor.setVisible(False)
        self.raw_toggle.toggled.connect(self.raw_editor.setVisible)
        adv_layout.addWidget(self.raw_editor)
        
        self.advanced_tab.setLayout(adv_layout)
        return self.advanced_tab
