#!/usr/bin/env python3

import argparse
import locale
import logging
import os

from bashtrace.program import BashTrace


def main():
    locale.setlocale(locale.LC_ALL, '')

    program_dir = os.path.dirname(os.path.realpath(__file__))
    debug_script = os.path.join(program_dir, 'debug.sh')

    parser = argparse.ArgumentParser()
    add_arg = parser.add_argument
    add_arg('script', help="Target script to be run")
    add_arg('args', nargs=argparse.REMAINDER,
            help="Any following arguments are given to command")
    add_arg('-s', '--sleep', metavar="SECS", default=0,
            help="Wait SECS before executing the line "
                 "(default is %(default)ss)")
    add_arg('-b', '--break', metavar="SCRIPT:LINE",
            help="Break in SCRIPT on LINE. "
                 "If SCRIPT is empty, target is assumed. "
                 "If LINE is empty, first valid line is assumed. "
                 "Use ':' to break immediately.")
    add_arg('--no-ui', action="store_true",
            help="Switch off curses interface, do not touch script output. "
                 "Useful if only the log is wanted.")
    add_arg('--wrapper', metavar="FILENAME", default=debug_script,
            help="Use FILENAME as debug wrapper instead of internal one")
    add_arg('--log', metavar="FILENAME", help="Log file for debug messages")
    args = parser.parse_args()

    if args.log:
        logging.basicConfig(filename=args.log, level=logging.DEBUG)

    bash_trace = BashTrace()
    bash_trace.sleep = float(args.sleep)
    if vars(args)['break']:
        script_name, line = vars(args)['break'].split(':')
        bash_trace.set_break(script_name, line)

    if args.no_ui:
        bash_trace.run_script_noui(args.script, args.args, args.wrapper)
        return

    def curses_main(stdscr):
        bash_trace.init_window(stdscr)
        bash_trace.run_script(args.script, args.args, args.wrapper)

    import curses
    curses.wrapper(curses_main)


if __name__ == '__main__':
    main()
