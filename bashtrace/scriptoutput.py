import curses
import logging

from .editfield import EditField


class ScriptOutput:

    """Console for script's I/O and diagnostic messages.

    Append only, using curses buffer, no need to redraw
    (unless the content is trashed by terminal resize).

    Text flow and scrolling is done by curses, our additions are:

    - Line numbers
    - Color coding according to output type (stderr, stdout, diagnostics)

    """

    class Line:

        __slots__ = ('mode', 'number', 'text')

        def __init__(self, mode, number, text=''):
            self.mode = mode
            self.number = number
            self.text = text

        def empty(self):
            return not len(self.text)

        def __repr__(self):
            return "Line(%r, %r, %r)" % (self.mode, self.number, self.text)

    def __init__(self, win):
        self._win = win
        self.resize = win.resize
        self.noutrefresh = win.noutrefresh
        # State
        self._current_mode = ' '
        self._lineno_by_mode = {}
        self._output_ended = False
        # History of lines in output, each item is Line
        self._history = []
        # For view
        self.MODE_TO_ATTR = {
            ' ': curses.color_pair(1),  # stdout
            'E': curses.color_pair(3),  # stderr
            '!': curses.color_pair(4),  # diag
        }
        self.add_output('')

    def add_output(self, message):
        self.addstr(message, ' ')

    def add_error(self, message):
        self.addstr(message, 'E')

    def add_diag(self, message):
        self.addstr(message, '!')

    def end_output(self):
        """Signal that there will be no more output."""
        self._output_ended = True

    def addstr(self, message, mode):
        for line in message.splitlines(keepends=True):
            self._add_line_number(mode)
            self._history[-1].text += line
            self._win.addstr(line, self.MODE_TO_ATTR[mode])

        if not self._output_ended:
            self._add_line_number(' ')
        self._win.noutrefresh()

    def read_line(self, prompt, mode='!'):
        """Read a line of input."""
        # Draw prompt
        self._add_line_number(mode)
        self._win.addstr(prompt, self.MODE_TO_ATTR[mode])
        self._win.noutrefresh()
        curses.doupdate()
        # Execute blocking edit
        field = EditField(self._win)
        value = field.edit()
        if value:
            # Imprint the value from edit box
            self._history[-1].text += value
            self._win.addstr(value, self.MODE_TO_ATTR[mode])
            if not self._output_ended:
                self._add_line_number(' ')
            self._win.noutrefresh()
        return value

    def _add_line_number(self, mode):
        """Add line number on new line in `mode`.

        If we are currently in another mode, start new line.

        """
        y, x = self._win.getyx()
        newline = (x == 0)
        if not newline and self._current_mode != mode:
            # Dirty line, mode changed
            if x == 6:
                # Just the line number on the line, replace it
                assert self._history[-1].empty()
                self._history.pop()
                self._win.move(y, 0)
                self._lineno_by_mode[self._current_mode] -= 1
            else:
                # Something already printed -> new line
                self._win.addstr("\n")
            newline = True
        self._current_mode = mode
        if newline:
            lineno = self._lineno_by_mode.get(mode, 0) + 1
            # Add new line
            self._history.append(self.Line(mode, lineno))
            attr = self.MODE_TO_ATTR[mode]
            self._win.addstr("%s%3s  " % (mode, lineno), attr)
            self._lineno_by_mode[mode] = lineno

    def redraw(self):
        """Draw the history into window. Only required after terminal resize."""
        self._win.erase()
        self._win.move(0, 0)
        h, w = self._win.getmaxyx()
        for line in self._history[-h:]:
            attr = self.MODE_TO_ATTR[line.mode]
            self._win.addstr("%s%3s  " % (line.mode, line.number), attr)
            self._win.addstr(line.text, attr)
        self._win.noutrefresh()
