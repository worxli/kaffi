#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import threading
import serial
import binascii
import time, sys, signal

import mdb
import legi
import status

tohex = binascii.hexlify
fromhex = binascii.unhexlify

serial_logger = logging.getLogger("serial")

class SerialStream(object):

    def __init__(self, *args, **kwargs):
        """
        Initialize this SerialStream. args and kwargs are passed to the Serial
        constructor when connect() is called.
        """
        self.connection = None
        self.connect_args = args, kwargs

    def connect(self):
        self.connection = serial.Serial(*self.connect_args[0], **self.connect_args[1])

    def disconnect(self):
        self.connection.close()
        self.connection = None

    def is_open(self):
        return bool(self.connection and self.connection.isOpen())

    def read_byte(self):
        """
        Read and return a single byte if the stream is open, else return None
        """
        while self.connection and self.connection.isOpen():
            byte = self.connection.read()
            if byte:
                serial_logger.info("read %02x", ord(byte))
                return byte

    def write_bytes(self, byte):
        """
        Write some data to the stream. Throws ValueError if the stream is
        disconnected.
        """
        serial_logger.info("writing %s", tohex(byte))
        if self.connection and self.connection.isOpen():
            self.connection.write(byte)
        else:
            raise ValueError("trying to write to closed stream")

config = None
def get_config():
    global config
    if not config:
        import ConfigParser
        import os, os.path
        _config = ConfigParser.RawConfigParser()
        if _config.read([os.path.expanduser(p) for p in ['/etc/kaffi', '/etc/vis/kaffi', '~/.config/kaffi', '~/.config/vis/kaffi']]):
            config = _config
        else:
            raise ValueError("could not find config file")
    return config

system_logger = logging.getLogger("system")

class System(object):

    def __init__(self, legi_enable=None):
        self.serial = self.trans = self.mdb = self.mdb_thread = None
        self.listener = self.legi_thread = None
        self.reset_timer = None
        self.legi_enable = legi_enable or fromhex(get_config().get('legi', 'enable'))
        self.legi_info = None

        logging.basicConfig(filename='output.txt', level=logging.INFO)
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("system").setLevel(logging.DEBUG)
        logging.getLogger("mdb").setLevel(logging.INFO)
        logging.getLogger("translator").setLevel(logging.WARNING)
        logging.getLogger("serial").setLevel(logging.WARNING)
        logging.getLogger("legi").setLevel(logging.INFO)

    def start(self):
        if self.is_running():
            system_logger.warn("system already running")
            return
        system_logger.info("starting")

        if self.serial is None:
            self.serial = SerialStream("/dev/ttyS0", 115200, timeout=5)
            self.serial.connect()

        if self.mdb is None:
            self.mdb = mdb.MdbStm(self._handle_dispense)

        if self.trans is None:
            self.trans = mdb.TranslatorStm(self.serial, self.mdb.received_data)

        if self.listener is None:
            self.listener = legi.LegiListener(serial.Serial('/dev/ttyS1', 38400, timeout=1),
                    self.legi_enable, self._handle_legi)

        self.mdb_thread = threading.Thread(target=self.trans.run)
        self.mdb_thread.daemon = True

        self.legi_thread = threading.Thread(target=self.listener.run)
        self.legi_thread.daemon = True

        self.mdb_thread.start()
        self.legi_thread.start()

    def stop(self):
        system_logger.info("stopping")
        if self.mdb:
            for i in xrange(20):
                self.mdb.dispense_permitted = None
                if self.mdb.state != self.mdb.STATE_SESSION_IDLE:
                    break
                time.sleep(0.1)
        if self.trans is not None:
            self.trans.stop()
        if self.listener is not None:
            self.listener.stop()
        if self.reset_timer:
            self.reset_timer.cancel()

    def _handle_legi(self, leginr):
        system_logger.debug("handling legi %s", leginr)
        org = status.check_legi(leginr)
        if not org:
            return

        for i in xrange(10):
            if self.mdb.dispense_permitted is None:
                break
            time.sleep(0.1)

        self.legi_info = leginr, org
        self.dispense()

    def _handle_dispense(self, itemdata):
        system_logger.debug("handling dispense %s", tohex(itemdata))
        if self.legi_info is None:
            system_logger.error("got dispense but legi_info is None")
        else:
            try:
                item_number = int(tohex(itemdata), 16)
                status.report_dispense(self.legi_info[0], self.legi_info[1], item_number)
            except Exception:
                system_logger.error("caught exception while reporting dispense for %r, itemdata %r",
                        self.legi_info, itemdata, exc_info=True)

    def is_running(self):
        return (self.mdb_thread is not None and self.mdb_thread.isAlive() or
                self.legi_thread is not None and self.legi_thread.isAlive())

    def dispense(self, allow=True):
        if self.reset_timer:
            self.reset_timer.cancel()
            self.reset_timer = None
        if allow is not None:
            if not self.is_running():
                self.start()
            if self.mdb.dispense_permitted is not None:
                self.mdb.dispense_permitted = None
                time.sleep(1)
        self.mdb.dispense_permitted = allow
        if allow:
            self.reset_timer = threading.Timer(8, lambda: self.dispense(None))
            self.reset_timer.start()

def main(args=None):
    if args is None:
        args = sys.argv

    logging.basicConfig(filename='/root/output.txt', level=logging.DEBUG)

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
            attr = raw_input(">> ")
        except EOFError:
            print
            break

        try:
            if attr == "help":
                print '\t'.join(a for a in dir(s) if not a.startswith('_'))
                continue

            if attr.startswith('_') or not hasattr(s, attr):
                print "No such attribute"
                continue
            value = getattr(s, attr)

            if not callable(value):
                print value
                continue

            res = value()
            if res is not None:
                print repr(res)
        except Exception:
            import traceback
            traceback.print_exc()
    s.stop()

if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
