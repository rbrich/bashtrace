import curses
import logging

try:
    from pygments import highlight
    from pygments.lexers import BashLexer
    from pygments.formatters import TerminalFormatter  # Terminal256Formatter
except ImportError:
    highlight = lambda x, *args: x
    BashLexer = lambda: None
    TerminalFormatter = lambda **kwargs: None

from .ansicurses import ColorWin


def _color_pair_highlight(fg, bg):
    return curses.color_pair(16 + fg if fg is not None else 4)


def _color_pair_normal(fg, bg):
    return curses.color_pair(8 + fg if fg is not None else 1)


class ScriptSource:

    """View for script's source code, with marker for the part currently
    being run.

    The source syntax is highlighted (if pygments module is available).

    """

    def __init__(self, name, depth, lineno, command, subshell):
        # The script data
        self.name = name
        self.depth = depth
        self.lineno = lineno
        self.command = command
        self._subshell = subshell
        self.raw_lines = None
        self.lines = None
        # View helpers
        self._cmd_col = 0
        self._cmd_first_line = 0
        self._cmd_last_line = 0
        self._cmd_first_col = 0
        self._cmd_last_col = 0
        self._drawn_h = 0
        # Read the script file
        self.load()

    def load(self):
        with open(self.name, 'r', encoding="utf-8") as f:
            data = f.read()
        data = data.expandtabs(4)
        self.raw_lines = data.splitlines()
        self.lines = highlight(data, BashLexer(),
                               TerminalFormatter(bg="dark")).splitlines()

    @property
    def subshell(self):
        return self._subshell

    @subshell.setter
    def subshell(self, value):
        self._subshell = value
        if value == 0:
            self._cmd_col = 0

    def _process_multiline_statement(self):
        """Handle line continuation (\ before NL)"""
        while self.raw_lines[self._cmd_last_line].endswith('\\'):
            if self._cmd_last_line + 1 < len(self.raw_lines):
                self._cmd_last_line += 1

    def update_command_span(self):
        """Compute part of source to be highlighted as the command to be run.

        Writes result to self._cmd_(first_line|last_line|first_col|last_col)

        Columns are optional, when both of them are 0, whole line is highlighted.

        In most common case of full line command:
            first_line == last_line
            first_col == last_col == 0

        Lines are indexed from zero.

        """
        self._cmd_first_line = self._cmd_last_line = self.lineno - 1
        self._cmd_first_col = self._cmd_last_col = 0
        # Multi-line statement (escaped line ends)
        self._process_multiline_statement()
        # Check that we are correct (this block is not mandatory)
        highlighted_lines = []
        for ln in range(self._cmd_first_line, self._cmd_last_line + 1):
            line = self.raw_lines[ln].rstrip('\\').strip()
            highlighted_lines.append(line)
        merged_highlighted_lines = ' '.join(highlighted_lines)

        if len(self.command) < len(merged_highlighted_lines):
            col = merged_highlighted_lines.index(self.command, self._cmd_col)
            self._cmd_col = col
            pad = 0
            for line in highlighted_lines:
                if col > len(line):
                    self._cmd_first_line += 1
                    col -= len(line) + 1
                else:
                    raw_line = self.raw_lines[self._cmd_first_line]
                    logging.debug("XX %r %r", raw_line, line)
                    pad = raw_line.index(line)
                    break
            self._cmd_first_col = pad + col
            self._cmd_last_col = self._cmd_first_col + len(self.command)
        else:
            assert self.subshell == 0
            # Multi-line command - the last line is reported, expand backwards
            self._cmd_first_line -= self.command.count('\n')

    def draw(self, win, y, max_h, max_w) -> int:
        """Draw part of script source into `win` at `y`.

        Currently executed command (self.command, self.lineno) is highlighted
        and the view is centered around that line.

        Occupied space is limit by `max_h`, `max_w`.

        Returns number of lines actually drawn.
        This will be less or equal to `max_h`.

        """
        # Header
        win.attrset(curses.color_pair(2) | curses.A_BOLD)
        win.hline(y, 0, ' ', max_w)
        win.addstr(y, 0, self.name)
        win.attrset(0)
        self._drawn_h = 1

        # If whole source cannot fit, show just close context
        if max_h - 1 < len(self.lines):
            start = max((self.lineno - 1) - (max_h - 1) // 2, 0)
        else:
            start = 0

        # Print the source
        colorwin = ColorWin(win)
        line_to_y = {}

        def on_wrap():
            colorwin.addstr("..  ")
            self._drawn_h += 1

        colorwin.on_wrap = on_wrap
        colorwin.color_pair = _color_pair_normal
        colorwin.attrset(0)
        for n, line in enumerate(self.lines[start:], 1 + start):
            if self._drawn_h >= max_h:
                break
            line_to_y[n] = y + self._drawn_h
            colorwin.move(y + self._drawn_h, 0)
            colorwin.addstr("%2s  " % n)
            colorwin.addcolorstr(line)
            self._drawn_h += 1

        # Highlight part to be run
        self.update_command_span()
        colorwin.attrset(curses.color_pair(4))
        colorwin.color_pair = _color_pair_highlight
        if self._cmd_first_col == self._cmd_last_col == 0:
            # Highlight command, possibly multiple lines,
            # which is about to be executed
            for ln in range(self._cmd_first_line, self._cmd_last_line + 1):
                if ln > start - 1:
                    colorwin.move(line_to_y[ln + 1], 0)
                    colorwin.addstr("%2s  " % (ln + 1))
                    colorwin.addcolorstr(self.lines[ln])
        else:
            # Special handling for subshells:
            # The line is drawn in normal color,
            # subshell part is then highlighted
            colorwin.move(line_to_y[self._cmd_first_line + 1],
                          4 + self._cmd_first_col)
            colorwin.addstr(self.command)

        # Move the to highlighted line
        colorwin.move(line_to_y[self.lineno], 0)

        return self._drawn_h
