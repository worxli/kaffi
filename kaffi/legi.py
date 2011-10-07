#-*- coding: utf-8 -*-
from __future__ import absolute_import

import serial
import binascii
import logging
import threading

legi_logger = logging.getLogger("legi")

tohex = binascii.hexlify
fromhex = binascii.unhexlify

class LegiListener(object):

    def __init__(self, serial, enable, legi_receiver):
        self.serial = serial
        self.running = None
        self.legi_receiver = legi_receiver
        self.enable = enable

    def _do_read(self):
        ans = self.serial.read(size=14)
        if ans:
            legi_logger.debug("got input %s", tohex(ans))
        if ans and len(ans) == 14 and ans[:2] == fromhex("0d80"):
            legi = tohex(ans[10:13])
            legi_logger.info("got legi %r" % legi)
            try:
                self.legi_receiver(legi)
            except Exception:
                legi_logger.error("caught exception while handling legi %s", legi, exc_info=True)
        if ans:
            self.serial.write(self.enable)

    def run(self):
        self.running = True
        try:
            self.serial.write(self.enable)
            while self.running:
                self._do_read()
        except Exception:
            legi_logger.critical("unhandled exception", exc_info=True)
            self.running = False
            raise

    def stop(self):
        self.running = False

def run():

    def print_(arg):
        print(arg)

    logging.basicConfig(level=logging.DEBUG)

    from .system import get_config
    enable = fromhex(get_config().get('legi', 'enable'))

    s = serial.Serial('/dev/ttyS1', 38400, timeout=1)
    l = LegiListener(s, enable, print_)
    t = threading.Thread(target=l.run)
    t.daemon = True
    t.start()

    return l

