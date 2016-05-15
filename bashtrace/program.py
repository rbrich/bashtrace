import curses
import logging
import sys
import os
import subprocess
import select
import time
import signal
import struct
import fcntl
import termios
from tempfile import NamedTemporaryFile
from functools import partial

from .scriptsource import ScriptSource
from .scriptoutput import ScriptOutput


def signal_name(signum):
    for name in dir(signal):
        if name.startswith('SIG') and '_' not in name:
            if getattr(signal, name) == abs(signum):
                return name
    return signum


class ProgramFinished(Exception):
    pass


class TerminalResized(Exception):
    pass


class BashTrace:

    """Bash trace program.

    Should be run through curses.wrapper (curses init/cleanup not handled).

    """

    def __init__(self):
        self._stdscr = None
        self._scripts = []  # ScriptInfo
        self._awaiting_response = False
        self._continue = True
        self._break = None
        self._sleep = 0
        self._input_mode = False
        self._finished = False
        self._src_win = None
        self._out_win = None
        self._info_win = None
        self._proc = None
        self._counter = 0
        self._stp_wr = None

    @property
    def debug_script(self) -> ScriptSource:
        """Bottom script is our debug script."""
        return self._scripts[0]

    @property
    def top_script(self) -> ScriptSource:
        """Top (current) script."""
        return self._scripts[-1]

    @property
    def sleep(self):
        return self._sleep

    @sleep.setter
    def sleep(self, value):
        self._sleep = value

    @property
    def awaiting_response(self):
        return self._awaiting_response

    @awaiting_response.setter
    def awaiting_response(self, value):
        self._awaiting_response = value

    def init_window(self, stdscr):
        self._stdscr = stdscr

        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLUE)
        curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_YELLOW)
        curses.init_pair(5, curses.COLOR_YELLOW, curses.COLOR_MAGENTA)

        for i in range(8):
            fg = curses.COLOR_BLACK + i
            curses.init_pair(8 + i, fg, curses.COLOR_BLACK)
            curses.init_pair(16 + i, fg, curses.COLOR_YELLOW)
        # The case of yellow on yellow - make it black
        curses.init_pair(16 + 3, curses.COLOR_BLACK, curses.COLOR_YELLOW)

        curses.curs_set(2)

        h, w = self._stdscr.getmaxyx()

        self._stdscr.bkgd(' ', curses.color_pair(2) | curses.A_BOLD)
        self._stdscr.noutrefresh()

        self._src_win = curses.newwin(h - 1, 89)
        self._src_win.bkgd(' ', curses.color_pair(1))
        self._src_win.noutrefresh()

        win = curses.newwin(0, 0, 0, 90)
        win.bkgd(' ', curses.color_pair(1))
        win.scrollok(1)
        win.leaveok(0)
        win.noutrefresh()
        self._out_win = ScriptOutput(win)

        self._info_win = curses.newwin(1, 89, h - 1, 0)
        self._info_win.bkgd(' ', curses.color_pair(2) | curses.A_BOLD)
        self._info_win.attrset(curses.color_pair(2) | curses.A_BOLD)
        self._info_win.noutrefresh()

        curses.doupdate()

        # Convert SIGWCH to exception
        def sigwch(signum, stackframe):
            screen_size = struct.pack("HHHH", 0, 0, 0, 0)
            screen_size = fcntl.ioctl(0, termios.TIOCGWINSZ, screen_size)
            rows, cols, xpixels, ypixels = struct.unpack('HHHH', screen_size)
            if curses.is_term_resized(rows, cols):
                curses.resizeterm(rows, cols)
                raise TerminalResized("Terminal size changed")
        signal.signal(signal.SIGWINCH, sigwch)

    def set_break(self, script_name, line):
        if not script_name and not line:
            self._continue = False
        else:
            self._break = (script_name, int(line))

    def resize_windows(self):
        h, w = self._stdscr.getmaxyx()
        self._src_win.resize(h - 1, 89)
        self._out_win.resize(h, w - 90)
        self._info_win.mvwin(h - 1, 0)

    def redraw_screen(self):
        self._stdscr.clear()
        self._stdscr.noutrefresh()
        self.refresh_sources()
        self.refresh_info_line()
        self._out_win.redraw()
        curses.doupdate()

    def update_screen(self):
        self.refresh_sources()
        self.refresh_info_line()
        if self._input_mode:
            # Activate the output window to move the cursor there
            self._out_win.noutrefresh()
        curses.doupdate()

    def refresh_info_line(self, info=None):
        if not info:
            info = "/-\\"[self._counter % 3] + " "
            self._counter += 1
            if self._finished:
                info += "[q] quit"
            elif self._input_mode:
                info += "INPUT MODE: [Esc] leave"
            else:
                info += "[q] terminate  [i] input"
                if self.awaiting_response:
                    info += "  [n] next  [c] continue  [s] skip" \
                            "  [r] return  [e] eval"
                else:
                    info += "  [p] pause"
        self._info_win.addstr(0, 0, info)
        self._info_win.clrtoeol()
        self._info_win.noutrefresh()

    def refresh_sources(self):
        win = self._src_win
        win.erase()
        win_h, win_w = win.getmaxyx()
        y = 0
        for script in self._scripts[1:]:
            if script == self._scripts[-1]:
                actual_height = script.draw(win, y, win_h - y, win_w)
            else:
                actual_height = script.draw(win, y, 2, win_w)
            y += actual_height
        win.noutrefresh()

    def prepare_debug(self, script_name, dbg_wr, stp_rd) -> NamedTemporaryFile:
        """Copy script to temp file, adjust, return temp file object."""
        logging.info("Using debug script: %s", script_name)
        tmpf = NamedTemporaryFile()
        with open(script_name, 'rb') as f:
            data = f.read()
        data = data.replace(b'__DBG_WR__', str(dbg_wr).encode())
        data = data.replace(b'__STP_RD__', str(stp_rd).encode())
        tmpf.file.write(data)
        tmpf.file.flush()
        return tmpf

    def run_script_noui(self, script, args, debug_script):
        """No UI version of :meth:`run_script`."""
        dbg_rd, dbg_wr = os.pipe()
        stp_rd, self._stp_wr = os.pipe()
        temp_debug_script = self.prepare_debug(debug_script, dbg_wr, stp_rd)
        argv = ['bash', '-c', 'source ' + temp_debug_script.name,
                script] + list(args)

        self._proc = subprocess.Popen(argv, pass_fds=(dbg_wr, stp_rd))

        poll = select.poll()
        process_func = {}
        poll.register(dbg_rd, select.POLLIN)
        process_func[dbg_rd] = partial(self.proc_debug, dbg_rd)

        def sigchld(signum, stackframe):
            raise ProgramFinished
        signal.signal(signal.SIGCHLD, sigchld)
        while True:
            try:
                events = poll.poll()
                for fd, event in events:
                    if event & select.POLLHUP:
                        poll.unregister(fd)
                        break
                    else:
                        process_func[fd]()
            except ProgramFinished:
                break
        status = self._proc.wait()
        logging.info('Finished (returned %d)' % status)
        return status

    def run_script(self, script, args, debug_script):
        """Run `script` with `args` in debug mode.

        The `debug_script` is used to set up bash debugging.

        Basically, this could just execute `debug_script` in bash, giving
        it `script` and `args` in arguments::

             bash <debug_script> <script> ...

        The actual setup is a little more complicated. We want to:

        - communicate with `debug_script` using pipes
        - hide the `debug_script` from `script` (it should see itself as $0)

        The solution::

             bash -c "source <tmp_debug_script>" <script> <arg1> ...

        The `debug_script` is preprocessed, the result is written to temporary
        file (`tmp_debug_script`).

        Bash sources `tmp_debug_script`, which gets `script` as $0
        and $0 is set correctly from the beginning.

        User script gets:

        - CWD - untouched
        - $0 - script name
        - ${BASH_SOURCE[0]} - debug script (temp name)
        - ${BASH_SOURCE[1]} - script name

        If the script uses $0 to get actual script directory,
        it will work the same as if the script was executed directly.
        Still, the script can detect it was sourced by the debugger.

        """
        dbg_rd, dbg_wr = os.pipe()
        stp_rd, self._stp_wr = os.pipe()
        temp_debug_script = self.prepare_debug(debug_script, dbg_wr, stp_rd)
        argv = ['bash', '-c', 'source ' + temp_debug_script.name,
                script] + list(args)

        PIPE = subprocess.PIPE
        self._proc = subprocess.Popen(argv,
                                      stdout=PIPE, stderr=PIPE, stdin=PIPE,
                                      pass_fds=(dbg_wr, stp_rd))

        poll = select.poll()
        process_func = {}
        poll.register(sys.stdin, select.POLLIN)
        process_func[sys.stdin.fileno()] = self.user_input
        poll.register(self._proc.stdout, select.POLLIN)
        process_func[self._proc.stdout.fileno()] = self.proc_output
        poll.register(self._proc.stderr, select.POLLIN)
        process_func[self._proc.stderr.fileno()] = self.proc_error
        poll.register(dbg_rd, select.POLLIN)
        process_func[dbg_rd] = partial(self.proc_debug, dbg_rd)

        resized = False
        while True:
            try:
                if resized:
                    self.user_input()
                    resized = False
                    continue
                events = poll.poll()
                for fd, event in events:
                    if event & select.POLLHUP:
                        poll.unregister(fd)
                    else:
                        process_func[fd]()
                if not self._finished and not self._proc.poll() is None:
                    self.proc_finish()
                self.update_screen()
            except TerminalResized:
                resized = True
            except ProgramFinished:
                break

        return self._proc.returncode

    def proc_output(self):
        data = os.read(self._proc.stdout.fileno(), 100)
        if data is not None:
            data = data.decode()
            self._out_win.add_output(data)

    def proc_error(self):
        data = os.read(self._proc.stderr.fileno(), 100)
        if data is not None:
            data = data.decode()
            self._out_win.add_error(data)

    def proc_debug(self, dbg_rd):
        data = os.read(dbg_rd, 1000)
        if data:
            data = data.decode().rstrip()
            trap, data = data.split(' ', 1)
            caller, command, depth, subshell = data.split('!!!')
            lineno, script = caller.split(' ', 1)

            logging.info("Trap %s %s:%s depth=%s subshell=%s command=%r",
                         trap, script, lineno, depth, subshell, command)

            depth = int(depth)
            lineno = int(lineno)
            subshell = int(subshell)
            command = command.strip()

            assert trap == "DBG"

            if not len(self._scripts) or depth > self.top_script.depth:
                # New script -> add to stack
                script_source = ScriptSource(script, depth, lineno,
                                             command, subshell)
                self._scripts.append(script_source)
            else:
                if depth < self.top_script.depth:
                    # Returned from top script, remove it from stack
                    self._scripts.pop()
                # Update top script values
                assert self.top_script.depth == depth
                self.top_script.lineno = lineno
                self.top_script.command = command
                self.top_script.subshell = subshell

            # Not interested in DEBUG trap from our debug.sh script
            if self.top_script == self.debug_script:
                self.send_debug('0')
            else:
                if self._input_mode:
                    self._input_mode = False
                self.awaiting_response = True
                self.auto_respond()

    def proc_finish(self):
        status = self._proc.wait()
        self._out_win.end_output()
        if status < 0:
            self._out_win.add_diag('Terminated (%s)' % signal_name(status))
        else:
            self._out_win.add_diag('Finished (returned %d)' % status)
        self._finished = True

    def user_input(self):
        c = self._stdscr.get_wch()
        if c == curses.KEY_RESIZE:
            self.resize_windows()
            self.redraw_screen()
            return
        if self._input_mode:
            if c == "\x1b":  # ESCAPE
                self._input_mode = False
                self._src_win.noutrefresh()
            else:
                if isinstance(c, str):
                    self._out_win.add_output(c)
                    c = c.encode()
                    self._proc.stdin.write(c)
                    self._proc.stdin.flush()
        elif c == "q":
            if self._finished:
                raise ProgramFinished()
            else:
                self._proc.terminate()
        elif c == "p":
            # Pause execution (break on next line)
            self._continue = False
        elif c == "i":
            self._input_mode = True
            self._out_win.add_output('')
        elif self.awaiting_response:
            if c == "n":
                # Step to next command
                self.send_debug('0')
            elif c == "c":
                # Continue with execution, do not stop anymore
                self._continue = True
                self.send_debug('0')
            elif c == "s":
                # Skip line
                self.send_debug('1')
            elif c == "r":
                # Return (from current script)
                self.send_debug('2')
            elif c == "e":
                # Eval
                self.refresh_info_line("Awaiting command...  "
                                       "[Enter] execute  "
                                       "(leave blank to cancel)")
                value = self._out_win.read_line("Eval: ")
                if value:
                    self.send_debug('EVAL ' + value, done=False)

    def send_debug(self, msg, done=True):
        os.write(self._stp_wr, msg.encode() + b'\n')
        self.awaiting_response = not done

    def auto_respond(self):
        if self._continue:
            time.sleep(self._sleep)
            if self._break:
                break_script, break_line = self._break
                if ((not break_script or self.top_script.name == break_script)
                and (not break_line or self.top_script.lineno >= break_line)):
                    self._break = None
                    self._continue = False
                    return
            self.send_debug('0')
