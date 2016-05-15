import curses

try:
    from pygments import highlight
    from pygments.lexers import BashLexer
    from pygments.formatters import TerminalFormatter  # Terminal256Formatter
except ImportError:
    highlight = lambda x, *args: x
    BashLexer = lambda: None
    TerminalFormatter = lambda **kwargs: None

from .ansicurses import ColorWin


def _color_pair_command(fg, bg):
    return curses.color_pair(16 + fg if fg is not None else 4)


def _color_pair_normal(fg, bg):
    return curses.color_pair(8 + fg if fg is not None else 1)


class ScriptSource:

    """View for script's source code, with marker for the part currently
    being run.

    The source syntax is optionally highlighted depending on availability
    of pygments module.

    """

    def __init__(self, name, depth, lineno, command, subshell):
        # The script data
        self.name = name
        self.depth = depth
        self._lineno = lineno  # Starts at 1
        self.command = command
        self.subshell = subshell
        self.raw_lines = None
        self.lines = None
        # View helpers
        self._cmd_first_lineno = 0
        self._cmd_last_lineno = 0
        self._drawn_h = 0
        # Read the script file
        self.load()

    @property
    def lineno(self):
        return self._lineno

    @lineno.setter
    def lineno(self, value):
        if value != self._lineno:
            self._lineno = value
            self._cmd_first_lineno = 0
            self._cmd_last_lineno = 0

    def load(self):
        with open(self.name, 'r', encoding="utf-8") as f:
            data = f.read()
        data = data.expandtabs(4)
        self.raw_lines = data.splitlines()
        self.lines = highlight(data, BashLexer(),
                               TerminalFormatter(bg="dark")).splitlines()

    def update_command_span(self):
        """Compute part of source to be marked as the command being run.

        Writes result to self._cmd_(first_line|last_line|first_col|last_col)
        Columns are optional, when both of them are 0, whole line is marked.

        In most common case of full line command:
            first_line == last_line
            first_col == last_col == 0

        Lines are indexed from zero.

        """
        if self._cmd_first_lineno != 0:
            return

        self._cmd_first_lineno = self._cmd_last_lineno = self.lineno

        # Multi-line statement (escaped line ends - \ before NL)
        while self.raw_lines[self._cmd_last_lineno - 1].endswith('\\'):
            if self._cmd_last_lineno < len(self.raw_lines):
                self._cmd_last_lineno += 1

        # Multi-line command - the last line is reported, expand backwards
        self._cmd_first_lineno -= self.command.count('\n')

    def draw(self, win, y, max_h, max_w) -> int:
        """Draw part of script source into `win` at `y`.

        Currently executed command (self.command, self.lineno) is marked
        and the view is centered around that line.

        Occupied space is limited by `max_h`, `max_w`.

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

        # Mark lines currently being run
        self.update_command_span()
        colorwin.attrset(curses.color_pair(4))
        colorwin.color_pair = _color_pair_command
        for ln in range(self._cmd_first_lineno, self._cmd_last_lineno + 1):
            if ln > start:
                colorwin.move(line_to_y[ln], 0)
                colorwin.addstr("%2s  " % ln)
                colorwin.addcolorstr(self.lines[ln - 1])

        # Mark/show the command if different from marked lines
        marked_lines = '\n'.join(self.raw_lines[self._cmd_first_lineno - 1:
                                                self._cmd_last_lineno])
        if self.command.strip() != marked_lines.strip():
            # If there is one exact match of command in marked lines,
            # highlight it at the position
            if marked_lines.count(self.command) == 1:
                pos = marked_lines.index(self.command)
                prefix = marked_lines[:pos]
                cmd_lineno = self._cmd_first_lineno
                cmd_col = len(prefix)
                if '\n' in prefix:
                    cmd_lineno += prefix.count('\n')
                    cmd_col -= prefix.rindex('\n') + 1
                colorwin.move(line_to_y[cmd_lineno], 4 + cmd_col)
            # Otherwise, do not try to guess which part is actually running,
            # instead print the reported command above marked lines
            else:
                colorwin.move(line_to_y[self._cmd_first_lineno] - 1, 4)
            colorwin.attrset(curses.color_pair(5) | curses.A_BOLD)
            colorwin.addstr(self.command)

        # Move the line reported by Bash
        colorwin.move(line_to_y[self.lineno], 0)

        return self._drawn_h
