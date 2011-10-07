# -*- coding: utf-8 -*-
from __future__ import absolute_import

import binascii
import logging

tohex = binascii.hexlify
fromhex = binascii.unhexlify

logger = logging.getLogger("translator")

class TranslatorStm(object):

    STX = '\x02' #Start transaction
    ETX = '\x03' #End transaction
    EOT = '\x04'
    DLE = '\x10' #Escape character
    ACK = '\x06'
    NAK = '\x15'

    def __init__(self, serial_stream, handler):
        """
        Initialize the Translator.

        :param serial_stream: object with read_byte() and write_bytes(bytes)
        :param handler: callable that takes newly received data and responds
            with data to be sent
        """
        super(TranslatorStm, self).__init__()
        self.serial_stream = serial_stream
        self.handler = handler
        self.state_fn = self._transaction_idle
        self.running = False
        self.received_data = ""

    def _transaction_running(self, c):
        """
        Internal state handler. Current state is inside a receive transaction
        but not after a DLE.
        """
        if c == self.DLE:
            self.state_fn = self._escape_received
        else:
            self.received_data += c

    def _escape_received(self, c):
        """
        Internal state handler. Current state is immediately after a DLE
        """
        if c == self.ETX:
            # receive complete, forward to handler
            logger.info("received %s", tohex(self.received_data))
            data = self.handler(self.received_data)
            self.received_data = ""

            # prepare to send data
            logger.info("sending %s", tohex(data))
            data = data.replace(self.DLE, self.DLE + self.DLE)

            # why send ack?
            self.serial_stream.write_bytes(self.ACK)

            # wrap data in transaction
            self.serial_stream.write_bytes(self.STX + data + self.DLE + self.ETX)

            # update state
            self.state_fn = self._transaction_idle

        elif c == self.DLE:
            # DLE escapes itself
            self.received_data += self.DLE
            self.state_fn = self._transaction_running

        else:
            logger.warn("mega komisch: %s nachem DLE" % tohex(c))

    def _transaction_idle(self, c):
        """
        Internal state handler. Current state is after an ETX, i.e. between
        receive transactions.
        """
        if c == self.STX:
            self.state_fn = self._transaction_running
        elif c == self.ACK:
            pass
        elif c == self.NAK:
            logger.info("es NAK")
        else:
            logger.warn("mega komisch: %s im idle" % tohex(c))

    def run(self):
        """
        Run this state machine. Does not terminate until stop() has been
        called.
        """
        self.running = True
        try:
            while self.running:
                c = self.serial_stream.read_byte()
                self.state_fn(c)
        except Exception:
            logger.critical("uncaught exception", exc_info=True)
            self.running = False
            raise

    def stop(self):
        """
        Stop the state machine if it is running
        """
        self.running = False

