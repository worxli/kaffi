#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import absolute_import

import logging
import binascii
import time, sys, signal

tohex = binascii.hexlify
fromhex = binascii.unhexlify

def main(args=None):
    if args is None:
        args = sys.argv
    log_args = dict(format="%(asctime)s|%(levelname)s|%(name)s|%(message)s", level=logging.WARNING)
    try:
        i = args[::-1].index("--log")
        log_args['filename'] = args[len(args)-i]
    except ValueError:
        pass
    log_args['level'] = logging.ERROR

    logging.basicConfig(**log_args)
    logging.info("setting up logging")

    from . import sqllogging
    sqllogging.init()
    sqllogger = sqllogging.SqlLogHandler(logging.WARNING)
    logging.getLogger().addHandler(sqllogger)

    logging.getLogger("system").setLevel(logging.DEBUG)
    logging.getLogger("mdb").setLevel(logging.DEBUG)
    logging.getLogger("translator").setLevel(logging.DEBUG)
    logging.getLogger("serial").setLevel(logging.WARNING)
    logging.getLogger("legi").setLevel(logging.INFO)
    logging.getLogger("status").setLevel(logging.INFO)
    logging.getLogger("main").setLevel(logging.DEBUG)
    # Make this thing STFU!
    logging.getLogger("system").setLevel(logging.WARNING)
    logging.getLogger("mdb").setLevel(logging.WARNING)
    logging.getLogger("translator").setLevel(logging.WARNING)
    logging.getLogger("serial").setLevel(logging.WARNING)
    logging.getLogger("legi").setLevel(logging.WARNING)
    logging.getLogger("status").setLevel(logging.WARNING)
    logging.getLogger("main").setLevel(logging.INFO)

    from .system import System
    s = System()

    oldsig = None
    def stop_system(signum, frame):
        s.stop()
        time.sleep(1)
        if oldsig not in (signal.SIG_IGN, signal.SIG_DFL):
            oldsig(signum, frame)
        else:
            sys.exit(1)
    oldsig = signal.signal(signal.SIGTERM, stop_system)

    if "--daemon" in args:
        s.start()
        while True:
            time.sleep(10)
        return

    s.start()
    while True:
        try:
            try:
                # python2
                attr = raw_input(">> ")
            except NameError:
                # python3
                attr = input(">> ")
        except EOFError:
            print('')
            break

        try:
            if attr == "help":
                print('\t'.join(a for a in dir(s) if not a.startswith('_')))
                continue

            if attr.startswith('_') or not hasattr(s, attr):
                print("No such attribute")
                continue
            value = getattr(s, attr)

            if not callable(value):
                print(value)
                continue

            res = value()
            if res is not None:
                print(repr(res))
        except Exception:
            import traceback
            traceback.print_exc()
    s.stop()

if __name__ == "__main__":
    import os, os.path
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from kaffi import main as _main
    try:
        sys.exit(_main() or 0)
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(127)
