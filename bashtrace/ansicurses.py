import re
import curses


class ColorWin:

    """Wraps curses window, writes colored string into it.

    The only supported method is `addstr`.

    You should override `color_pair` to actual return color pair number
    to see any colors.

    Only a subset of ANSI codes are interpreted. Non-graphic codes are ignored
    (those will just appear in the output in verbatim).
    An NotImplementedError is raised when unknown graphic code is encountered.
    (This is meant for controlled input, so unknown codes should be implemented
    if this situation occurs.)

    """

    def __init__(self, win, attr=0, catch_exception=True):
        self._win = win
        self._attr = attr
        self._fg = None
        self._bg = None
        self._catch_exception = catch_exception
        self.attrset = win.attrset
        self.move = win.move

    def color_pair(self, fg, bg):
        """Return curses color_pair for combination of `fg`, `bg` colors.

        Value of None means default color.

        This default implementation does nothing (no color output).

        """
        return 0

    def on_wrap(self):
        pass

    def _apply_color(self, code):
        """Interpret ANSI escape code (Graphic Rendition)."""
        if code == 0:
            # reset
            self._attr = 0
            self._fg = None
            self._bg = None
        elif code == 1:
            # bold
            self._attr |= curses.A_BOLD
        elif 30 <= code <= 37:
            # foreground color
            self._fg = code - 30
        elif code == 39:
            # default foreground
            self._fg = None
        elif 40 <= code <= 47:
            # background color
            self._bg = code - 40
        elif code == 49:
            # default background
            self._bg = None
        else:
            raise NotImplementedError('Unknown code: %s' % code)
        self._win.attrset(self._attr | self.color_pair(self._fg, self._bg))

    def addstr(self, s):
        """Like curses win.addstr, but call on_wrap() when line overflows.
        This allows to add marker on line beginnings."""
        h, w = self._win.getmaxyx()
        y, x = self._win.getyx()
        space = w - x
        if space < len(s):
            self._win.addstr(s[:space])
            self.on_wrap()
            self.addstr(s[space:])
        else:
            self._win.addstr(s)

    def addcolorstr(self, s):
        """Like curses win.addstr, but this one interprets ANSI colors."""
        re_esc = re.compile('\033\\[(([0-9]{1,2})(;[0-9]{1,2})*)m')
        while len(s):
            m = re_esc.search(s)
            if m:
                match_start, match_end = m.span()
                text = s[:match_start]
                s = s[match_end:]
                codes = m.group(1).split(';')
                self.addstr(text)
                for code in codes:
                    self._apply_color(int(code))
            else:
                # No match - print the rest of text
                self.addstr(s)
                s = ''


if __name__ == '__main__':
    # Demo (without curses)
    #
    # Apply the parser on pygments highlighted text.
    # The color codes are printed as markup in square brackets.
    #
    from pygments import highlight
    from pygments.lexers import BashLexer
    from pygments.formatters import TerminalFormatter

    class FakeWin:

        def __init__(self):
            self._attr = 0
            self.move = None

        def addstr(self, s):
            """Print the string with "visualised" attributes."""
            if not s:
                return
            attr = self._attr
            fg = attr % 256
            attr >>= 8
            bg = attr % 256
            attr >>= 8
            if fg == 255:
                fg = '-'
            if bg == 255:
                bg = '-'
            if attr == 0:
                attr = '-'
            print('[%s,%s,%s]%s' % (fg, bg, attr, s), end='')

        def attrset(self, attr):
            self._attr = attr

    def color_pair(fg, bg):
        """Encode color pair in 16 bits."""
        if fg is None:
            fg = 255
        if bg is None:
            bg = 255
        return fg + (bg << 8)

    with open("script.sh", 'r', encoding="utf-8") as f:
            data = f.read()
    data = highlight(data, BashLexer(), TerminalFormatter(bg="dark"))
    win = FakeWin()
    proxy = ColorWin(win)
    proxy.addstr = win.addstr
    proxy.color_pair = color_pair
    proxy.addcolorstr(data)
