#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import absolute_import

import logging
import threading
import serial
import binascii
import time

from . import (
    translator,
    mdb,
    legi,
    status,
    sqllogging,
    ampelstatus,
)

config = None
config_dirs = ['/etc/kaffi', '/etc/vis/kaffi', '~/.config/kaffi', '~/.config/vis/kaffi']
def get_config():
    global config
    if not config:
        try:
            # python3
            import configparser
        except ImportError:
            # python2
            import ConfigParser as configparser
        import os, os.path
        _config = configparser.RawConfigParser()
        if _config.read([os.path.expanduser(p) for p in config_dirs]):
            config = _config
        else:
            raise ValueError("could not find config file")
    return config

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
            self.connection.flush()
        else:
            raise ValueError("trying to write to closed stream")


main_logger = logging.getLogger('main')

class Main(object):

    def __init__(self, mdb):
        self._current_legi = None
        self._legi_lock = threading.Condition()
        self.mdb = mdb
    
    def _wait_for_legi(self):
        with self._legi_lock:
            while not self._current_legi:
                self._legi_lock.wait()
            legi = self._current_legi
            self._current_legi = None
            return legi
    
    def _legi_receiver(self,legi):
        # runs on legi thread
        with self._legi_lock:
            self._current_legi = legi
            self._legi_lock.notify()


    def run(self):
        while True:
            try:
                main_logger.info("waiting for legi")
                leginr = self._wait_for_legi() # return current legi (may block)
                
                main_logger.info("checking ampel status")
                if not ampelstatus.get_status():
                    # deny dispense
                    sqllogging.log_msg('DENIED Ampel', leginr)
                    continue

                main_logger.info("checking legi %s", leginr)
                org = status.check_legi(leginr)
                main_logger.info("got org %s for legi %s", org, leginr)
                if not org:
                    # deny dispense
                    sqllogging.log_msg('DENIED', leginr)
                else:
                    main_logger.info("Waiting for dispense...")
                    dispensed, itemdata = self.mdb.allow_one_and_wait()
                    main_logger.info("Dispensed: %s, itemdata: %r", dispensed, itemdata)
                    if dispensed:
                        try:
                            item_number = int(tohex(itemdata), 16)
                            status.report_dispense(leginr, org, item_number)
                        except Exception:
                            system_logger.error("caught exception while reporting dispense for %r, itemdata %r",
                                                (leginr, org), itemdata, exc_info=True)
            except Exception:
                main_logger.error("caught exception in main thread", exc_info=True)


system_logger = logging.getLogger("system")

class System(object):

    def __init__(self, legi_enable=None):
        self.serial = self.trans = self.mdb = self.mdb_thread = self.main = None
        self.listener = self.legi_thread = None
        self.reset_timer = None
        self.response_timer = None
        self.legi_enable = legi_enable or fromhex(get_config().get('legi', 'enable'))
        self.legi_info = None
        self.dispense_permitted = None

        logging.basicConfig(filename='output.txt', level=logging.INFO)

    def start(self):
        if self.is_running():
            system_logger.warn("system already running")
            return
        system_logger.info("starting")

        if self.serial is None:
            self.serial = SerialStream("/dev/ttyS0", 115200, timeout=5)
            self.serial.connect()

        if self.mdb is None:
            self.mdb = mdb.MdbL1Stm()

        if self.trans is None:
            self.response_timer = translator.ResponseTimer(self.mdb.received_data)
            self.response_timer.enabled = True
            self.trans = translator.TranslatorStm(self.serial, self.response_timer, self.mdb.received_nack)

        if self.main is None:
            self.main = Main(self.mdb)

        if self.listener is None:
            self.listener = legi.LegiListener(serial.Serial('/dev/ttyS1', 38400, timeout=1),
                    self.legi_enable, self.main._legi_receiver)

        self.main_thread = threading.Thread(target=self.main.run)
        self.main_thread.deamon = True

        self.mdb_thread = threading.Thread(target=self.trans.run)
        self.mdb_thread.daemon = True

        self.legi_thread = threading.Thread(target=self.listener.run)
        self.legi_thread.daemon = True

        self.main_thread.start()
        self.mdb_thread.start()
        self.legi_thread.start()

    def stop(self):
        system_logger.info("stopping")
        if self.mdb:
            for i in range(20):
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
        # todo: shutdown main thread
        sqllogging.stop_retrying()

    def _get_dispense_state(self):
        if self.dispense_permitted is None:
            return None
        return (self.dispense_permitted, self.legi_info)

    def _handle_legi(self, leginr):
        system_logger.debug("checking ampel status")
        if not ampelstatus.get_status():
            # deny dispense
            self.dispense(False, None)
            sqllogging.log_msg('DENIED Ampel', leginr)
            return

        system_logger.debug("handling legi %s", leginr)

        org = status.check_legi(leginr)
        legi_info = leginr, org
        system_logger.debug("got org %s for legi %s", org, leginr)

        if not org:
            # deny dispense
            self.dispense(False, legi_info)
            sqllogging.log_msg('DENIED', leginr)

        else:
            # wait for two seconds for a possibly running session to complete
            for i in range(10):
                if self.dispense_permitted is None:
                    break
                time.sleep(0.2)

            self.dispense(True, legi_info)

    def _handle_dispense(self, legi_info, itemdata):
        """
        Callback to handle a successful dispense.
        """
        system_logger.info("handling dispense %s for %s", (tohex(itemdata) if itemdata else itemdata), legi_info)

        # reset dispense
        self.dispense(None)

        try:
            item_number = int(tohex(itemdata), 16)
            status.report_dispense(legi_info[0], legi_info[1], item_number)
        except Exception:
            system_logger.error("caught exception while reporting dispense for %r, itemdata %r",
                                legi_info, itemdata, exc_info=True)

    def _handle_denied(self, leginr):
        system_logger.info("handling deny for %s", leginr)
        # reset dispense
        self.dispense(None)

    def is_running(self):
        return (self.mdb_thread is not None and self.mdb_thread.isAlive() or
                self.legi_thread is not None and self.legi_thread.isAlive())

    def _dispense_timeout(self):
        try:
            if self.dispense_permitted is not None:
                system_logger.info("dispense timed out")
            self.dispense(None)
        except Exception:
            system_logger.error("uncaught exception while handling dispense timeout", exc_info=True)

    def dispense(self, allow=True, legi_info=None):
        # reset any running dispense timer
        if self.reset_timer:
            self.reset_timer.cancel()
            self.reset_timer = None

        # make sure system is actually running
        if allow is not None:
            if not self.is_running():
                self.start()

        # set dispense data
        self.legi_info = legi_info
        self.dispense_permitted = allow
        if allow:
            # start timer if necessary
            self.reset_timer = threading.Timer(8, self._dispense_timeout)
            self.reset_timer.start()
