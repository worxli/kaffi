# -*- coding: utf-8 -*-
from __future__ import absolute_import

import binascii
import logging

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


    def __init__(self, get_dispense_status, item_dispensed_handler, denied_dispense_handler):
        """
        Initialization.

        :param item_dispensed_handler: must be a callable. It is called with an
            item's data whenever that item is dispensed.
        """
        self.response_data = ""
        self.state = self.st_inactive
        self.config_data = self.maxmin_data = self.item_data = None
        self.get_dispense_status = get_dispense_status
        self.item_dispensed_handler = item_dispensed_handler
        self.denied_dispense_handler = denied_dispense_handler
        self.send_reset = True
        self.current_dispense = None
        self.cancel_countdown = 0

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
        mdb_logger.error("out-of-sequence command %s in state %s with current_dispense %r",
                         tohex(data), self.state.__name__, self.current_dispense)
        #return self.RES_CMD_OUT_OF_SEQ
        return self.RES_MALFUNCTION

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
        self.current_dispense = None
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
            dispense = None
            try:
                dispense = self.get_dispense_status()
            except Exception:
                mdb_logger.error("caught exception from get_dispense_status", exc_info=True)

            if dispense:
                # mark dispense request as current dispens and transition to
                # session state
                self.current_dispense = dispense
                self._set_state(self.st_session_idle)
                return self.RES_BEGIN_SESS + fromhex('FFFF')

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

    def _deny(self):
        """Report denied dispense and end session"""
        try:
            self.denied_dispense_handler(self.current_dispense[1])
        except Exception:
            mdb_logger.error("caught exception in denied_dispense_handler", exc_info=True)
        self._set_state(self.st_session_ending)

    def st_session_idle(self, data):
        """
        Active session due to dispense notification. If dispense status is
        True, a dispense request will result in an accept and a transition into
        the vend state. Otherwise, dispense requests are denied and the session
        is cancelled as soon as possible.
        """

        if not self.current_dispense:
            mdb_logger.warning("in state st_session_idle with empty current_dispense %s", self.current_dispense)

        if self.is_command(data, self.CMD_POLL):
            if not self.current_dispense:
                # No pending dispense request, cancel session
                self._set_state(self.st_session_ending)
                return self.RES_SESS_CANCEL_REQ

            elif not self.current_dispense[0]:
                # The current dispense request is a deny, so cancel the session
                self._deny()
                return self.RES_SESS_CANCEL_REQ

            # check for changes to dispense request status
            dispense = None
            try:
                dispense = self.get_dispense_status()
            except Exception:
                mdb_logger.error("caught exception from get_dispense_status", exc_info=True)

            if self.current_dispense != dispense:
                # The current dispense was cancelled or changed
                self.current_dispense = dispense

                # if new dispense status is to deny the dispense, do it now
                if not self.current_dispense:
                    self._set_state(self.st_session_ending)
                    return self.RES_SESS_CANCEL_REQ

                elif not self.current_dispense[0]:
                    self._deny()
                    return self.RES_SESS_CANCEL_REQ

            return

        elif self.is_command(data, self.CMD_VEND_REQUEST):
            self.item_data = data[len(self.CMD_VEND_REQUEST):]
            mdb_logger.info("vend request item data: %s", tohex(self.item_data))

            # determine if a coffee should be dispensed for the current request
            if not self.current_dispense:
                # no dispense notification
                mdb_logger.warning("got vend request without current_dispense data")
                self._set_state(self.st_session_ending)
                return self.RES_VEND_DENIED

            elif self.current_dispense[0]:
                # approve dispense
                self._set_state(self.st_vend)
                # disable further dispense requests before session is complete
                self.current_dispense = (False, self.current_dispense[1])
                return self.RES_VEND_APPROVED + fromhex('FFFF')

            else:
                self._deny()
                return self.RES_VEND_DENIED

        elif self.is_command(data, self.CMD_VEND_CANCEL):
            # this should not happend as we respond immediately to a
            # vend_request.
            mdb_logger.warning("got vend cancel command")
            self.current_dispense = None
            return self.RES_VEND_DENIED

        elif self.is_command(data, self.CMD_VEND_SESS_COMPLETE):
            # reset current_dispense and return to enabled state
            if self.current_dispense:
                mdb_logger.warning("got session_complete with nonempty current_dispense")
                self.current_dispense = None

            self._set_state(self.st_enabled)
            return self.RES_END_SESSION

        elif self.is_command(data, self.CMD_READER_CANCEL):
            # should not really happen in this state, handle anyway...
            mdb_logger.warning("got reader cancel command")
            self.current_dispense = None
            self._set_state(self.st_enabled)
            return self.RES_CANCELLED

        elif self.is_command(data, self.CMD_RESET):
            self._set_state(self.st_inactive)
            return self.RES_RESET

        else:
            return self._out_of_sequence(data)

    def enter_st_session_ending(self):
        self.current_dispense = None
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

        if self.is_command(data, self.CMD_POLL):
            pass

        elif self.is_command(data, self.CMD_VEND_FAILURE):
            mdb_logger.warning("got vend_failure")
            self._set_state(self.st_session_ending)
            return

        elif self.is_command(data, self.CMD_VEND_CANCEL):
            mdb_logger.warning("got vend_cancel")
            self._set_state(self.st_session_ending)
            return self.RES_VEND_DENIED

        elif self.is_command(data, self.CMD_VEND_SUCCESS):
            self.item_data = data[len(self.CMD_VEND_SUCCESS):]
            mdb_logger.info("vend succes item data: %s", tohex(self.item_data))

            try:
                self.item_dispensed_handler(self.current_dispense[1], self.item_data)
            except Exception:
                mdb_logger.error("caught exception while handling dispense %s with itemdata %s",
                        self.current_dispense[1], tohex(self.item_data), exc_info=True)
            self._set_state(self.st_session_ending)
            return

        elif self.is_command(data, self.CMD_RESET):
            mdb_logger.warning("got reset in st_vend with current_dispense %r", self.current_dispense)
            self._set_state(self.st_inactive)
            return self.RES_RESET

        else:
            return self._out_of_sequence(data)

