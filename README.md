BashTrace
=========

BashTrace utilizes Bash's internal debugging support, allowing to trace script
execution. Output of the script is displayed next to its source code, with
currently running command marked in color.

Features:

- curses UI, see which line is currently being run
- slow down - optional delay before executing each line
- pause / continue at any time, step through the script
- evaluate arbitrary code at current position of script
- syntax highlighting (requires *pygments*)


How it works
------------

The program is based on "extdebug" option of Bash. Debugged script is sourced
by internal debug wrapper, which sets up DEBUG trap together with two pipes:

- debug pipe: debugging information is sent from DEBUG handler
              to bashtrace program
- step pipe: user commands are sent back to DEBUG handler


Alternatives
------------

- For basic debugging, you might use `bash -v` or `bash -x`
- [bashdb](http://bashdb.sourceforge.net/) is another bash debugger,
  which mimicks the interface of gdb
- [BashEclipse](https://sourceforge.net/projects/basheclipse/)
  is Bash debugger plugin for Eclipse
