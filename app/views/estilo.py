"""Hoja de estilos de la aplicación."""

HOJA_ESTILOS = """
QWidget { font-size: 10pt; }
QLabel#titulo { font-size: 16pt; font-weight: 600; }
QLabel#subtitulo { color: palette(window-text); font-size: 9pt; }
QLabel#mensajeError { color: #b3261e; }
QLabel#mensajeExito { color: #1e6b34; }
QLineEdit { padding: 6px; }
QPushButton { padding: 6px 14px; }
QPushButton:default { font-weight: 600; }
QListWidget#navegacion { border: none; min-width: 220px; }
QListWidget#navegacion::item { padding: 10px 12px; }
QFrame#cabecera { border-bottom: 1px solid palette(mid); }
QTableView { gridline-color: palette(midlight); }
QHeaderView::section { padding: 4px 8px; font-weight: 600; }
QDateEdit, QComboBox, QSpinBox, QDoubleSpinBox { padding: 4px; }
"""
