import curses.ascii


class EditField:

    """Single line edit field.

    Returns content on Enter, None on cancel (Escape).

    Does not touch attributes, does not care about win size.
    Does not touch area behind current cursor pos + width.
    Clears the touched are when done.

    """

    def __init__(self, win, width=0):
        """Assign the field to `win`, allowing at max `width` chars.

        Zero width allows to uses all space up to the end of window.

        """
        # Compute width
        _, w = win.getmaxyx()
        by, bx = win.getbegyx()
        y, x = win.getyx()
        self.width = width or w - x
        # Create new window for edit box
        self.win = curses.newwin(1, width, by + y, bx + x)
        self.win.keypad(1)
        # Edited text is split to left and right part
        self.left = ''  # Text on left side of the cursor
        self.right = ''  # Text on right side of the cursor

    def edit(self):
        """Run edit loop, return the content."""
        while True:
            wc = self.win.get_wch()
            res = self.process_input(wc)
            if res == 'enter':
                return self.left + self.right
            if res == 'escape':
                return None
            self.draw()

    def draw(self):
        """Draw current content, move cursor to current position."""
        left, right = self.left, self.right
        # If whole content cannot fit, clip it
        while len(left) + len(right) > self.width - 1:
            if len(left) > self.width // 2:
                left = left[1:]
            else:
                right = right[:-1]
        if left != self.left:
            left = '<' + left[1:]
        if right != self.right:
            right = right[:-1] + '>'
        # Draw the (possibly clipped) content
        self.win.move(0, 0)
        self.win.addnstr(left, self.width)
        _, curs_x = self.win.getyx()
        self.win.addnstr(right, self.width - curs_x)
        _, end_x = self.win.getyx()
        self.win.hline(' ', self.width - end_x)
        self.win.move(0, curs_x)
        self.win.refresh()

    def process_input(self, wc):
        """Process character obtained from get_wch().

        Returns None if not resolved, or string with resolution type:

        * 'enter' - input finished, text is valid
        * 'escape' - input canceled, text is invalid

        """
        if wc == chr(curses.ascii.ESC):
            return 'escape'
        elif wc == curses.KEY_LEFT:
            self.right = self.left[-1:] + self.right
            self.left = self.left[:-1]
        elif wc == curses.KEY_RIGHT:
            self.left = self.left + self.right[:1]
            self.right = self.right[1:]
        elif wc == curses.KEY_HOME:
            self.right = self.left + self.right
            self.left = ''
        elif wc == curses.KEY_END:
            self.left = self.left + self.right
            self.right = ''
        elif wc == curses.KEY_BACKSPACE or wc == chr(curses.ascii.BS):
            self.left = self.left[:-1]
        elif wc == curses.KEY_DC or wc == chr(curses.ascii.DEL):
            self.right = self.right[1:]
        elif wc == chr(curses.ascii.NL):
            return 'enter'
        elif isinstance(wc, str):
            self.left += wc


if __name__ == '__main__':
    # Demo
    def curses_main(stdscr):
        w = 20
        stdscr.move(9, 10)
        stdscr.hline('-', w)
        stdscr.move(11, 10)
        stdscr.hline('-', w)
        stdscr.move(10, 10)
        stdscr.refresh()
        field = EditField(stdscr, w)
        return field.edit()
    result = curses.wrapper(curses_main)
    print(result)
