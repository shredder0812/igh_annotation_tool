APP_STYLESHEET = """
QWidget {
    font-family: Segoe UI;
    font-size: 11pt;
    background: #f4f6f8;
    color: #1f2933;
}

QGroupBox {
    border: 1px solid #ccd6dd;
    border-radius: 8px;
    margin-top: 8px;
    padding-top: 10px;
    background: #f8fafb;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #1b4965;
    font-weight: 600;
}

QPushButton {
    background: #1b4965;
    color: #ffffff;
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 28px;
}

QPushButton:hover {
    background: #245d80;
}

QPushButton:pressed {
    background: #163a51;
}

QPushButton:disabled {
    background: #9db0bd;
}

QLineEdit {
    border: 1px solid #b6c3cc;
    border-radius: 6px;
    padding: 5px;
    background: #ffffff;
}

QTabWidget::pane {
    border: 1px solid #d7e1e8;
    border-radius: 8px;
    background: #ffffff;
}

QTabBar::tab {
    background: #e8eef3;
    color: #274c63;
    border: 1px solid #d7e1e8;
    padding: 6px 12px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background: #ffffff;
    color: #11364b;
    font-weight: 600;
}

QSlider::groove:horizontal {
    border: 1px solid #c4d0d8;
    height: 6px;
    background: #e6edf2;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #1b4965;
    border: 1px solid #163a51;
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
}

QCheckBox {
    spacing: 6px;
}

QTableWidget {
    gridline-color: #e5edf2;
    selection-background-color: #d8ebff;
    selection-color: #0f3550;
    alternate-background-color: #f6f9fc;
    background: #ffffff;
    border: 1px solid #d5e2eb;
    border-radius: 6px;
}

QHeaderView::section {
    background: #eaf2f7;
    color: #1b4965;
    border: 1px solid #d5e2eb;
    padding: 4px;
    font-weight: 600;
}
"""
