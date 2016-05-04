#!/usr/bin/env bash
# This file is preprocessed before run.
# Following placeholders are replace by appropriate FD number:
# __DBG_WR__    Debug pipe, write end.
# __STP_RD__    Step pipe, read end.
#

shopt -s extdebug
set -T

debug_trap()
{
    # Communicate script line to our "debug" pipe
    echo "DBG $(caller)!!!${BASH_COMMAND}!!!${#BASH_ARGC[*]}!!!${BASH_SUBSHELL}" >&__DBG_WR__
    # Wait for instruction from our "step" pipe
    while true
    do
        read -u __STP_RD__ -r DEBUG_CMD
        case "${DEBUG_CMD}" in
            EVAL*)
                eval ${DEBUG_CMD:4}
                ;;
            *)
                # Return the answer as is (should be numeric 0, 1 or 2)
                return ${DEBUG_CMD}
                ;;
        esac
    done
}

trap debug_trap DEBUG
source "$0"
