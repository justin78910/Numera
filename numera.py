"""Numera — safe MATLAB-inspired scalar calculator for Windows."""
import ast
import json
import math
import operator
import re
import sys
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut, QIcon
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QScrollArea,
    QLineEdit, QListWidget, QMainWindow, QPushButton, QVBoxLayout, QWidget)

STORE = Path.home() / '.calclab_variables.json'
BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
          ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow}
UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
FUNCTIONS = {
    'sqrt': math.sqrt, 'log': math.log, 'log2': math.log2,
    'log10': math.log10, 'ln': math.log, 'exp': math.exp,
    'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
    'asin': math.asin, 'acos': math.acos, 'atan': math.atan,
    'sind': lambda x: math.sin(math.radians(x)),
    'cosd': lambda x: math.cos(math.radians(x)),
    'tand': lambda x: math.tan(math.radians(x)),
    'abs': abs, 'floor': math.floor, 'ceil': math.ceil,
    'round': round, 'factorial': math.factorial,
    'sinc': lambda x: 1.0 if x == 0 else math.sin(math.pi*x)/(math.pi*x),
    'sinh': math.sinh, 'cosh': math.cosh, 'tanh': math.tanh,
    'asind': lambda x: math.degrees(math.asin(x)),
    'acosd': lambda x: math.degrees(math.acos(x)),
    'atand': lambda x: math.degrees(math.atan(x)),
    'deg2rad': math.radians, 'rad2deg': math.degrees,
}
CONSTANTS = {'pi': math.pi, 'e': math.e, 'Inf': math.inf}
RESERVED = set(FUNCTIONS) | set(CONSTANTS) | {'ans'}
# Each entry is (function name, short description, example).
# Only include supported scalar functions; no button for the e constant.
FUNCTION_HELP = {
    'Logs & powers': [
        ('sqrt', 'Square root', 'sqrt(25) = 5'),
        ('exp', 'Exponential: e raised to x', 'exp(2) = 7.389...'),
        ('log2', 'Base-2 logarithm', 'log2(8) = 3'),
        ('log10', 'Base-10 logarithm', 'log10(100) = 2'),
        ('ln', 'Natural logarithm (base e)', 'ln(exp(1)) = 1'),
    ],
    'Trigonometry': [
        ('sin', 'Sine; argument in radians', 'sin(pi/2) = 1'),
        ('cos', 'Cosine; argument in radians', 'cos(0) = 1'),
        ('tan', 'Tangent; argument in radians', 'tan(pi/4) = 1'),
        ('sind', 'Sine; argument in degrees', 'sind(30) = 0.5'),
        ('cosd', 'Cosine; argument in degrees', 'cosd(60) = 0.5'),
        ('tand', 'Tangent; argument in degrees', 'tand(45) = 1'),
        ('asin', 'Inverse sine; returns radians', 'asin(1) = pi/2'),
        ('acos', 'Inverse cosine; returns radians', 'acos(1) = 0'),
        ('atan', 'Inverse tangent; returns radians', 'atan(1) = pi/4'),
        ('asind', 'Inverse sine; returns degrees', 'asind(0.5) = 30'),
        ('acosd', 'Inverse cosine; returns degrees', 'acosd(0.5) = 60'),
        ('atand', 'Inverse tangent; returns degrees', 'atand(1) = 45'),
        ('sinc', 'Normalized sinc: sin(pi*x)/(pi*x); sinc(0)=1', 'sinc(0) = 1'),
    ],
    'Other math': [
        ('abs', 'Absolute value', 'abs(-5) = 5'),
        ('floor', 'Round down to integer', 'floor(2.9) = 2'),
        ('ceil', 'Round up to integer', 'ceil(2.1) = 3'),
        ('round', 'Round to nearest integer', 'round(2.6) = 3'),
        ('factorial', 'Factorial of a nonnegative integer', 'factorial(5) = 120'),
        ('sinh', 'Hyperbolic sine', 'sinh(0) = 0'),
        ('cosh', 'Hyperbolic cosine', 'cosh(0) = 1'),
        ('tanh', 'Hyperbolic tangent', 'tanh(0) = 0'),
        ('deg2rad', 'Convert degrees to radians', 'deg2rad(180) = pi'),
        ('rad2deg', 'Convert radians to degrees', 'rad2deg(pi) = 180'),
    ],
}
ASSIGNMENT = re.compile(r'^\s*([A-Za-z][A-Za-z0-9_]*)\s*=\s*(?![=])(.+?)\s*;?\s*$')


def show(value):
    return f'{value:.12g}'


class Engine:
    def __init__(self):
        self.variables = {}
        self.ans = 0.0
        try:
            data = json.loads(STORE.read_text(encoding='utf-8'))
            self.variables = {k: float(v) for k, v in data.items()
                              if k.isidentifier() and k not in RESERVED
                              and isinstance(v, (int, float)) and math.isfinite(float(v))}
        except (OSError, ValueError, TypeError):
            pass

    def evaluate(self, expression, commit=False):
        expr = expression.strip().replace('×', '*').replace('÷', '/').replace('−', '-').replace('^', '**')
        if len(expr) > 300:
            raise ValueError('Expression too long')
        match = ASSIGNMENT.fullmatch(expr)
        target = None
        if match:
            target, expr = match.group(1), match.group(2).rstrip(';').strip()
            if target in RESERVED:
                raise ValueError(f'{target} is reserved')
        elif expr.endswith(';'):
            expr = expr[:-1]
        # 'log' is ambiguous on handheld calculators versus MATLAB. Refuse it
        # even inside nested expressions instead of silently using a base.
        if re.search(r'(?<![A-Za-z0-9_])log\s*\(', expr):
            raise ValueError('Ambiguous log(x): use ln(x) for natural log or log10(x) for base 10.')
        tree = ast.parse(expr, mode='eval')

        def visit(node, depth=0):
            if depth > 35:
                raise ValueError('Expression too complex')
            if isinstance(node, ast.Expression):
                return visit(node.body, depth + 1)
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                return node.value
            if isinstance(node, ast.Name):
                if node.id == 'ans':
                    return self.ans
                if node.id in self.variables:
                    return self.variables[node.id]
                if node.id in CONSTANTS:
                    return CONSTANTS[node.id]
                raise ValueError(f'Unknown variable: {node.id}')
            if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY:
                return UNARY[type(node.op)](visit(node.operand, depth+1))
            if isinstance(node, ast.BinOp) and type(node.op) in BINARY:
                a = visit(node.left, depth+1)
                b = visit(node.right, depth+1)
                if isinstance(node.op, ast.Pow) and abs(b) > 1000:
                    raise ValueError('Exponent too large')
                return BINARY[type(node.op)](a, b)
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in FUNCTIONS and not node.keywords and len(node.args) == 1):
                return FUNCTIONS[node.func.id](visit(node.args[0], depth+1))
            raise ValueError('Unsupported syntax')

        value = visit(tree)
        if isinstance(value, complex) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('Result is not a finite real number')
        value = float(value)
        if commit:
            self.ans = value
            if target:
                self.variables[target] = value
                try:
                    STORE.write_text(json.dumps(self.variables, indent=2), encoding='utf-8')
                except OSError:
                    pass
        return value, target


class Calculator(QMainWindow):
    def __init__(self):
        super().__init__()
        self.engine = Engine()
        self.history = []
        self.last_result = None
        self.setWindowTitle('Numera — keyboard-first calculator')
        icon_path = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'numera.ico'
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(980, 670)
        self.setMinimumSize(560, 430)
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)
        main = QWidget()
        layout = QVBoxLayout(main)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        outer.addWidget(main, 3)
        self.function_panel = self.make_function_panel()
        outer.addWidget(self.function_panel, 2)
        title = QLabel('Numera')
        title.setObjectName('heading')
        layout.addWidget(title)
        hint = QLabel('Type expressions, press Enter to calculate · Ctrl+Shift+C to copy · radians by default')
        hint.setObjectName('hint')
        layout.addWidget(hint)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText('Try: x = log2(5)   or   x * 10')
        self.entry.setObjectName('entry')
        self.entry.textChanged.connect(self.preview)
        self.entry.textChanged.connect(lambda _: self.copy_button.setText('Copy result') if hasattr(self, 'copy_button') else None)
        self.entry.returnPressed.connect(self.calculate)
        layout.addWidget(self.entry)
        self.result = QLabel('0')
        self.result.setAlignment(Qt.AlignRight)
        self.result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result.setObjectName('result')
        layout.addWidget(self.result)
        bar = QHBoxLayout()
        bar.addWidget(QLabel('Variables (saved between launches)'))
        bar.addStretch()
        functions_toggle = QPushButton('Hide functions')
        self.functions_toggle = functions_toggle
        functions_toggle.clicked.connect(self.toggle_functions)
        bar.addWidget(functions_toggle)
        copy = QPushButton('Copy result')
        copy.clicked.connect(self.copy_result)
        self.copy_button = copy
        bar.addWidget(copy)
        layout.addLayout(bar)
        self.variables_list = QListWidget()
        self.variables_list.setMaximumHeight(115)
        self.variables_list.itemDoubleClicked.connect(lambda item: self.entry.insert(item.text().split(' = ')[0]))
        layout.addWidget(self.variables_list)
        layout.addWidget(QLabel('History (double-click to reuse)'))
        self.history_list = QListWidget()
        self.history_list.itemDoubleClicked.connect(self.reuse)
        layout.addWidget(self.history_list, 1)
        QShortcut(QKeySequence('Escape'), self, activated=self.clear)
        QShortcut(QKeySequence('Ctrl+L'), self, activated=self.clear)
        QShortcut(QKeySequence('Ctrl+Shift+C'), self, activated=self.copy_result)
        self.setStyleSheet('''
        QMainWindow, QWidget {background:#111827;color:#f9fafb;font:14px 'Segoe UI';}
        QLabel#heading {font-size:28px;font-weight:700;color:#93c5fd;}
        QLabel#hint {font-size:12px;color:#94a3b8;}
        QLineEdit#entry {background:#1f2937;border:1px solid #475569;border-radius:10px;padding:12px;font-size:20px;}
        QLabel#result {font-size:30px;font-weight:650;padding:6px;}
        QPushButton {background:#374151;color:white;border:0;border-radius:8px;padding:7px;font-weight:600;}
        QPushButton:hover {background:#4b5563;}
        QPushButton#equals {background:#2563eb;}
        QPushButton#clear {background:#7f1d1d;}
        QListWidget {background:#1f2937;border:0;border-radius:8px;padding:4px;}
        QListWidget::item {padding:5px;}
        QListWidget::item:selected {background:#1d4ed8;}
        QScrollArea {background:#1f2937;border:0;border-radius:10px;}
        QLabel#section {font-weight:700;color:#93c5fd;padding-top:8px;}
        QLabel#functionHelp {font-size:12px;color:#aab9cc;}
        QPushButton#functionButton {text-align:left;background:#334155;padding:7px 9px;}
        QPushButton#functionButton:hover {background:#2563eb;}
        ''')
        self.refresh_variables()
        self.entry.setFocus()

    def make_function_panel(self):
        panel = QWidget()
        panel.setObjectName('functionsPanel')
        panel.setMinimumWidth(230)
        side = QVBoxLayout(panel)
        side.setContentsMargins(4, 4, 4, 4)
        title = QLabel('Functions')
        title.setObjectName('heading')
        side.addWidget(title)
        search = QLineEdit()
        search.setPlaceholderText('Search functions or descriptions…')
        self.function_search = search
        side.addWidget(search)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        contents = QWidget()
        content_layout = QVBoxLayout(contents)
        content_layout.setSpacing(7)
        self.function_rows = []
        self.function_headers = []
        for category, entries in FUNCTION_HELP.items():
            heading = QLabel(category)
            heading.setObjectName('section')
            content_layout.addWidget(heading)
            category_rows = []
            for name, description, example in entries:
                row = QWidget()
                row_layout = QVBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(1)
                button = QPushButton(name + '( )')
                button.setObjectName('functionButton')
                button.setToolTip(f'{description}\n{example}')
                button.clicked.connect(lambda checked=False, fn=name: self.insert_function(fn))
                help_label = QLabel(description + '  ·  ' + example)
                help_label.setObjectName('functionHelp')
                help_label.setWordWrap(True)
                row_layout.addWidget(button)
                row_layout.addWidget(help_label)
                content_layout.addWidget(row)
                self.function_rows.append((row, (name + ' ' + description + ' ' + example).lower()))
                category_rows.append(row)
            self.function_headers.append((heading, category_rows))
        content_layout.addStretch()
        scroll.setWidget(contents)
        side.addWidget(scroll, 1)
        footer = QLabel('Tip: click to insert at the cursor.\npi, Inf and ans can be typed directly.')
        footer.setWordWrap(True)
        footer.setObjectName('hint')
        side.addWidget(footer)
        search.textChanged.connect(self.filter_functions)
        return panel

    def filter_functions(self, value):
        needle = value.strip().lower()
        for widget, haystack in self.function_rows:
            widget.setVisible(needle in haystack)
        for heading, rows in self.function_headers:
            heading.setVisible(any(not r.isHidden() for r in rows))

    def toggle_functions(self):
        visible = not self.function_panel.isVisible()
        self.function_panel.setVisible(visible)
        self.functions_toggle.setText('Hide functions' if visible else 'Show functions')
        self.entry.setFocus()

    def insert_function(self, function):
        # QLineEdit.insert replaces selected text, keeping normal text-edit semantics.
        self.entry.insert(function + '()')
        self.entry.cursorBackward(False, 1)
        self.entry.setFocus()

    def refresh_variables(self):
        self.variables_list.clear()
        for name, value in sorted(self.engine.variables.items()):
            self.variables_list.addItem(f'{name} = {show(value)}')

    def preview(self):
        if not self.entry.text().strip():
            self.result.setText('0')
            self.last_result = None
            return
        try:
            self.last_result = show(self.engine.evaluate(self.entry.text())[0])
            self.result.setText(self.last_result)
        except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, TypeError) as exc:
            self.last_result = None
            if isinstance(exc, ValueError) and 'Ambiguous log(x)' in str(exc):
                self.result.setText('Use ln(x) or log10(x)')
            else:
                self.result.setText('…')

    def calculate(self):
        expr = self.entry.text().strip()
        if not expr:
            return
        try:
            value, target = self.engine.evaluate(expr, commit=True)
        except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, TypeError) as exc:
            self.last_result = None
            self.result.setText(f'Error: {exc}')
            return
        answer = show(value)
        self.history.insert(0, expr)
        self.history_list.insertItem(0, f'{expr}  →  {answer}')
        self.last_result = answer
        self.result.setText(answer)
        self.refresh_variables()

    def clear(self):
        self.entry.clear()
        self.entry.setFocus()

    def copy_result(self):
        # Copy the number the user actually sees, including a just-submitted answer.
        # Do not silently fail or copy an error/placeholder.
        if self.last_result is None:
            self.copy_button.setText('No result to copy')
            return
        clipboard = QApplication.clipboard()
        clipboard.setText(self.last_result, mode=clipboard.Mode.Clipboard)
        self.copy_button.setText('Copied!')

    def reuse(self, item):
        self.entry.setText(self.history[self.history_list.row(item)])
        self.entry.setFocus()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName('Numera')
    window = Calculator()
    window.show()
    sys.exit(app.exec())
