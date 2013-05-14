# -*- coding: utf-8 -*-
from __future__ import absolute_import

import binascii
import logging
import threading

tohex = binascii.hexlify
fromhex = binascii.unhexlify

mdb_logger = logging.getLogger("mdb")

class MdbL1Stm(object):
    """MDB state machine handler.

    :attribute dispense_permitted: Set to True to allow next vend request, False to
        deny it, None to reset session (and deny any requests)
    :attribute response_data: data to be sent after next receive. If set
        externally this will only have an effect if no other response is
        sent due to the receive (i.e. if you're debugging you can set this
        to send something if nothing else is happening).
    :attribute config_data: set by the setup config data handler, so
        contains last received config data.
    :attribute maxmin_data: set by the setup maxmin handler, so contains
        last received maxmin information.
    :attribute item_data: set by the item dispense approved/successful
        handlers, so contains last received dispensed item information.
    """

    #
    # Command codes
    #

    CMD_RESET = fromhex('10')

    CMD_SETUP_CONF_DATA = fromhex('1100')
    CMD_SETUP_MAXMIN_PRICE = fromhex('1101')

    CMD_POLL = fromhex('12')

    CMD_VEND_REQUEST = fromhex('1300')
    CMD_VEND_CANCEL = fromhex('1301')
    CMD_VEND_SUCCESS = fromhex('1302')
    CMD_VEND_FAILURE = fromhex('1303')
    CMD_VEND_SESS_COMPLETE = fromhex('1304')
    CMD_VEND_CASH_SALE = fromhex('1305')
    CMD_VEND_NEG_VEND_REQ = fromhex('1306')

    CMD_READER_DISABLE = fromhex('1400')
    CMD_READER_ENABLE = fromhex('1401')
    CMD_READER_CANCEL = fromhex('1402')
    CMD_READER_DATA_ENTRY_RESP = fromhex('1403')

    CMD_REVALUE_REQUEST = fromhex('1500')
    CMD_REVALUE_LIMIT_REQ = fromhex('1501')

    CMD_EXP_REQUEST_ID = fromhex('1700')
    CMD_EXP_READ_USER_FILE = fromhex('1701')
    CMD_EXP_WRITE_USER_FILE = fromhex('1702')
    CMD_EXP_WRITE_TIMEDATE = fromhex('1703')
    CMD_EXP_OPT_FEAT_ENABLED = fromhex('1704')

    #
    # Response codes
    #

    RES_RESET = fromhex('0000')
    RES_READER_CONF_DATA = fromhex('01')
    RES_DISPLAY_REQ = fromhex('02')
    RES_BEGIN_SESS = fromhex('03')
    RES_SESS_CANCEL_REQ = fromhex('04')
    RES_VEND_APPROVED = fromhex('05')
    RES_VEND_DENIED = fromhex('06')
    RES_END_SESSION = fromhex('07')
    RES_CANCELLED = fromhex('08')
    RES_PERIPHERAL_ID = fromhex('09')
    RES_MALFUNCTION = fromhex('0A')
    RES_CMD_OUT_OF_SEQ = fromhex('0B')
    RES_REVALUE_APPROVED = fromhex('0D')
    RES_REVALUE_DENIED = fromhex('0E')
    RES_REVALUE_LIMIT_AMOUNT = fromhex('0F')
    RES_USER_FILE_DATA = fromhex('10')
    RES_TIME_DATE_REQUEST = fromhex('11')
    RES_DATA_ENTRY_REQ = fromhex('12')
    RES_DATA_ENTRY_CANCEL = fromhex('13')
    RES_DIAGNOSTIC = fromhex('FF')

    #
    # Misc codes
    #

    ACK = fromhex('00')


    def __init__(self):
        """
        Initialization.
        """
        self.response_data = ""
        self.state = self.st_inactive
        self.config_data = self.maxmin_data = self.item_data = None
        self.send_reset = True
        self.cancel_countdown = 0

        # Whether we want to allow ONE dispense. Access guarded by _lock.
        # _lock must be held while in state st_vend (between approve and success/cancel).
        self.allow = False
        self._lock = threading.Condition()

    def allow_one_and_wait(self):
        with self._lock:
            assert not self.allow
            self.allow = True
            self._lock.wait(2) # Two second timeout.
            dispensed = not self.allow
            self.allow = False
            item_data = self.item_data if dispensed else None
            return dispensed, item_data

    def _set_state(self, state):
        """
        Internal method. Update internal state.
        """
        mdb_logger.info("transitioning from %s to %s", self.state.__name__, state.__name__)

        # run "entry" method if present
        name = state.__name__
        if hasattr(self, 'enter_'+name):
            getattr(self, 'enter_'+name)()

        self.state = state

    def is_command(self, data, command):
        """
        Check whether a data string matches a given MDB command.
        """
        # First MDB command byte (main command) may be offset by 50 (subcommand remains the same)
        return data[0] in (command[0], chr(ord(command[0])+50)) and data[1:len(command[1:])+1] == command[1:]

    def _out_of_sequence(self, data):
        mdb_logger.error("out-of-sequence command %s in state %s",
                         tohex(data), self.state.__name__)
        #return self.RES_CMD_OUT_OF_SEQ
        return self.RES_MALFUNCTION

    def received_nack(self):
        mdb_logger.error("Received nack. Resetting...")
        if self.state == self.st_vend:
            self._lock.release()
            mdb_logger.error("Deadlock: Disabled     (by decision)")

        self.response_data = ""
        self.state = self.st_inactive
        self.config_data = self.maxmin_data = self.item_data = None
        self.send_reset = True
        self.cancel_countdown = 0

    def received_data(self, data):
        """
        Handle received data, return data to send back.
        """
        if data.startswith(self.ACK):
            data = data[1:]
        else:
            mdb_logger.warning("data does not start with ACK")

        if data == self.CMD_POLL:
            mdb_logger.debug("got message %s", tohex(data))
        else:
            mdb_logger.info("got message %s", tohex(data))

        result = self.state(data)
        data_to_send = self.response_data or result or ""
        self.response_data = ""
        data_to_send = self.ACK + data_to_send

        if data_to_send != self.ACK:
            mdb_logger.info("sending message %s", tohex(data_to_send))
        else:
            mdb_logger.debug("sending message %s", tohex(data_to_send))
        return data_to_send

    def default_handler(self, data):
        if self.is_command(data, self.CMD_SETUP_CONF_DATA):
            return ''.join([
                self.RES_READER_CONF_DATA,
                fromhex('01'), # feature level
                fromhex('0001'), # US dollars... CHF -> 1756?
                fromhex('01'), # scale factor
                fromhex('02'), # decimal places
                fromhex('01'), # application maximum response time - seconds
                fromhex('00'), # misc options
            ])

        elif self.is_command(data, self.CMD_SETUP_MAXMIN_PRICE):
            self.maxmin_data = data[len(self.CMD_SETUP_MAXMIN_PRICE):]
            return

        elif self.is_command(data, self.CMD_EXP_REQUEST_ID):
            return ''.join([
                self.RES_PERIPHERAL_ID,
                fromhex('414258'), # manufacturer code - ASCII
                fromhex('202020202020202020202020'), # serial number - ASCII
                fromhex('413320202020202020202020'), # model number - ASCII
                fromhex('1531'), # software version - packed BCD
            ])

        else:
            return self._out_of_sequence(data)

    def _enter_st_inactive(self):
        self.send_reset = True

    def st_inactive(self, data):
        """
        Inactive state, expecting setup data or an enable command
        """
        if self.is_command(data, self.CMD_POLL):
            if self.send_reset:
                self.send_reset = False
                return self.RES_RESET

        elif self.is_command(data, self.CMD_READER_ENABLE):
            self._set_state(self.st_enabled)
            return

        elif self.is_command(data, self.CMD_RESET):
            # set_state here despite already being in inactive state so enter
            # method is executed.
            self._set_state(self.st_inactive)
            return

        else:
            return self.default_handler(data)

    def st_disabled(self, data):
        """
        Disabled state, a sort of "standby" mode. No functions available, only
        resetting and transitioning to enabled state.
        """
        if self.is_command(data, self.CMD_POLL):
            return

        elif self.is_command(data, self.CMD_RESET):
            self._set_state(self.st_inactive)
            return self.RES_RESET

        elif self.is_command(data, self.CMD_READER_ENABLE):
            self._set_state(self.st_enabled)
            return

        else:
            return self.default_handler(data)


    def st_enabled(self, data):
        """
        Enabled state. Reacts to dispense notifications by starting a MDB
        "session", can also transition to disabled and reset state.
        """

        if self.is_command(data, self.CMD_POLL):
            # check for dispense request
            with self._lock:
                if self.allow:
                    # mark dispense request as current dispens and transition to
                    # session state
                    self._set_state(self.st_session_idle)
                    return self.RES_BEGIN_SESS + fromhex('FFFF')
                else:
                    return

        elif self.is_command(data, self.CMD_READER_DISABLE):
            self._set_state(self.st_disabled)
            return

        elif self.is_command(data, self.CMD_READER_CANCEL):
            # must handle this command, but does not really affect us.
            return self.RES_CANCELLED

        elif self.is_command(data, self.CMD_RESET):
            self._set_state(self.st_inactive)
            return self.RES_RESET
        
        else:
            if self.is_command(data, self.CMD_SETUP_CONF_DATA):
                # WORKAROUND: sometimes after a dispense the machine starts
                # flooding setup conf data cmds.
                mdb_logger.warning("got setup conf data in enabled state, sending malfunction")
                return self.RES_MALFUNCTION
            return self.default_handler(data)

    def st_session_idle(self, data):
        """
        Active session due to dispense notification. If dispense status is
        True, a dispense request will result in an accept and a transition into
        the vend state. Otherwise, dispense requests are denied and the session
        is cancelled as soon as possible.
        """

        if self.is_command(data, self.CMD_POLL):
            with self._lock:
                if not self.allow:
                    # No pending dispense request, cancel session
                    self._set_state(self.st_session_ending)
                    return self.RES_SESS_CANCEL_REQ
                return

        elif self.is_command(data, self.CMD_VEND_REQUEST):
            item_data = data[len(self.CMD_VEND_REQUEST):]
            mdb_logger.info("vend request item data: %s", tohex(item_data))

            self._lock.acquire();
            # determine if a coffee should be dispensed for the current request
            if not self.allow:
                self._lock.release();
                # no dispense notification
                mdb_logger.info("Too slow.")
                self._set_state(self.st_session_ending)
                return self.RES_VEND_DENIED

            else:
                # approve dispense, keep lock. Lock will be cleared in st_vend
                self._set_state(self.st_vend)
                return self.RES_VEND_APPROVED + fromhex('FFFF')


        elif self.is_command(data, self.CMD_VEND_CANCEL):
            # this should not happend as we respond immediately to a
            # vend_request.
            mdb_logger.warning("got vend cancel command")
            return self.RES_VEND_DENIED

        elif self.is_command(data, self.CMD_VEND_SESS_COMPLETE):
            # reset current_dispense and return to enabled state
            self._set_state(self.st_enabled)
            return self.RES_END_SESSION

        elif self.is_command(data, self.CMD_READER_CANCEL):
            # should not really happen in this state, handle anyway...
            mdb_logger.warning("got reader cancel command")
            self._set_state(self.st_enabled)
            return self.RES_CANCELLED

        elif self.is_command(data, self.CMD_RESET):
            self._set_state(self.st_inactive)
            return self.RES_RESET

        else:
            return self._out_of_sequence(data)

    def enter_st_session_ending(self):
        self.cancel_countdown = 10

    def st_session_ending(self, data):
        """
        Trying to exit active session. Dispense is complete (success/fail
        reported) or no dispense was requested (empty or false dispense
        status).
        """

        if self.is_command(data, self.CMD_POLL):
            if self.cancel_countdown > 0:
                self.cancel_countdown -= 1
            else:
                # XXX: is it ok to cancel a session like this?
                return self.RES_SESS_CANCEL_REQ

        elif self.is_command(data, self.CMD_VEND_SESS_COMPLETE):
            self._set_state(self.st_enabled)
            return self.RES_END_SESSION

        elif self.is_command(data, self.CMD_VEND_REQUEST):
            return self.RES_VEND_DENIED

        elif self.is_command(data, self.CMD_VEND_CANCEL):
            mdb_logger.warning("got vend cancel command")
            return self.RES_VEND_DENIED

        elif self.is_command(data, self.CMD_READER_CANCEL):
            # should not really happen in this state, handle anyway...
            mdb_logger.warning("got reader cancel command")
            self._set_state(self.st_enabled)
            return self.RES_CANCELLED

        elif self.is_command(data, self.CMD_VEND_SUCCESS):
            mdb_logger.error("got vend_success in state session_ending")
            return

        elif self.is_command(data, self.CMD_RESET):
            self._set_state(self.st_inactive)
            return self.RES_RESET

        else:
            return self._out_of_sequence(data)

    def st_vend(self, data):
        """
        Inside dispense sequence. Expencts to be notified of the result of the
        dispense.
        """
        assert self.allow #lock is held

        if self.is_command(data, self.CMD_POLL):
            pass

        elif self.is_command(data, self.CMD_VEND_FAILURE):
            mdb_logger.warning("got vend_failure")
            self._set_state(self.st_session_ending)
            self._lock.release()
            return

        elif self.is_command(data, self.CMD_VEND_CANCEL):
            mdb_logger.warning("got vend_cancel")
            self._set_state(self.st_session_ending)
            self._lock.release()
            return self.RES_VEND_DENIED

        elif self.is_command(data, self.CMD_VEND_SUCCESS):
            self.item_data = data[len(self.CMD_VEND_SUCCESS):]
            mdb_logger.info("vend succes item data: %s", tohex(self.item_data))
            self.allow = False
            self.itemdata = self.item_data
            self._lock.notify()
            self._lock.release()
            self._set_state(self.st_session_ending)
            return

        elif self.is_command(data, self.CMD_RESET):
            mdb_logger.warning("got reset in st_vend")
            self._set_state(self.st_inactive)
            self._lock.release()
            return self.RES_RESET

        else:
            # Does not change state, sends malefunction, reset should come next.
            # self._lock.release()
            return self._out_of_sequence(data)

