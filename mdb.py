
import binascii
import logging

tohex = binascii.hexlify
fromhex = binascii.unhexlify

mdb_logger = logging.getLogger("mdb")

class MdbStm(object):
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
    # States
    #

    STATE_INACTIVE = "__inactive"
    STATE_DISABLED = "__disabled"
    STATE_ENABLED = "__enabled"
    STATE_SESSION_IDLE = "__session_idle"
    STATE_SESSION_DISPENSED = "__session_dispensed"
    STATE_SESSION_ENDING = "__session_ending"

    #
    # Misc codes
    #

    ACK = fromhex('00')


    def __init__(self, get_dispense_status, item_dispensed_handler):
        """
        Initialization.

        :param item_dispensed_handler: must be a callable. It is called with an
            item's data whenever that item is dispensed.
        """
        self.response_data = ""
        self.state = self.STATE_INACTIVE
        self.config_data = self.maxmin_data = self.item_data = None
        #self.dispense = self.DISPENSE_NONE
        self.get_dispense_status = get_dispense_status
        self.item_dispensed_handler = item_dispensed_handler
        #self.display_update = None

    def _set_state(self, state):
        """
        Internal method. Update internal state.
        """
        mdb_logger.info("transitioning from %s to %s", self.state, state)
        self.state = state

    def is_command(self, data, command):
        """
        Check whether a data string matches a given MDB command.
        """
        # First MDB command byte (main command) may be offset by 50 (subcommand remains the same)
        return data[0] in (command[0], chr(ord(command[0])+50)) and data[1:len(command[1:])+1] == command[1:]

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

        self._handle(data)
        data_to_send = self.response_data
        self.response_data = ""
        data_to_send = self.ACK + data_to_send

        if data_to_send != self.ACK:
            mdb_logger.info("sending message %s", tohex(data_to_send))

        return data_to_send

    def _handle(self, data):
        """
        Internal handler for pre-processed received data.
        """

        # These commands handler are listed approximately in the same order as
        # in the MDB specification.

        if self.is_command(data, self.CMD_RESET):
            self._set_state(self.STATE_INACTIVE)
            self.config_data = self.maxmin_data = self.item_data = None

        elif self.is_command(data, self.CMD_POLL):
            if self.state is self.STATE_INACTIVE:
                self.response_data = self.RES_RESET
                self._set_state(self.STATE_DISABLED)

            elif (self.state is self.STATE_ENABLED and self.get_dispense_status() is not None):
                # pending dispense request (may be true or false), begin session
                self.response_data = self.RES_BEGIN_SESS + fromhex('FFFF')
                self._set_state(self.STATE_SESSION_IDLE)

            elif (self.state is self.STATE_SESSION_IDLE and self.get_dispense_status() is not True):
                self.item_dispensed_handler(None)
                self.response_data = self.RES_SESS_CANCEL_REQ
                self._set_state(self.STATE_SESSION_ENDING)

            elif (self.state is self.STATE_SESSION_ENDING):
                self.item_dispensed_handler(None)
                self.response_data = self.RES_SESS_CANCEL_REQ
                self._set_state(self.STATE_SESSION_ENDING)

            #elif self.state is self.STATE_ENABLED and self.display_update:
            #    self.response_data = self.RES_DISPLAY_REQ + fromhex('64') + self.display_update[0]
            #    self.display_update = None

        elif self.is_command(data, self.CMD_SETUP_CONF_DATA):
            if self.state == self.STATE_ENABLED:
                # WORKAROUND: sometimes after a dispense the machine starts
                # flooding setup conf data cmds.
                mdb_logger.warning("got setup conf data in enabled state, sending malfunction")
                self.response_data = self.RES_MALFUNCTION
                return
            self.config_data = data[len(self.CMD_SETUP_CONF_DATA):]
            self.response_data = ''.join([
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

        elif self.is_command(data, self.CMD_VEND_REQUEST):
            self.item_data = data[len(self.CMD_VEND_REQUEST):]
            mdb_logger.info("vend request item data: %s", tohex(self.item_data))

            dispense = self.get_dispense_status()
            if self.state is not self.STATE_SESSION_IDLE:
                # this should not happen according to mdb protocol
                mdb_logger.warning("got vend request outside state session_idle")
                self.response_data = self.RES_VEND_DENIED
                self._set_state(self.STATE_SESSION_ENDING)
            elif dispense is True:
                mdb_logger.info("dispense allowed")
                self.response_data = self.RES_VEND_APPROVED + fromhex('FFFF') # electronic token
                self._set_state(self.STATE_SESSION_DISPENSED)
            elif dispense is False:
                mdb_logger.info("dispense denied")
                self.response_data = self.RES_VEND_DENIED
                self._set_state(self.STATE_SESSION_ENDING)
            else:
                mdb_logger.warn("got vend_request with dispense == %r", dispense)
                self.response_data = self.RES_VEND_DENIED
                self._set_state(self.STATE_SESSION_ENDING)

        elif self.is_command(data, self.CMD_VEND_CANCEL):
            mdb_logger.warn("dispense canceled")
            self._set_state(self.STATE_SESSION_ENDING)
            self.response_data = self.RES_VEND_DENIED

        elif self.is_command(data, self.CMD_VEND_SUCCESS):
            if self.state is not self.STATE_SESSION_DISPENSED:
                mdb_logger.warning("got CMD_VEND_SUCCESS in state %r" % self.state)
            self._set_state(self.STATE_SESSION_ENDING)
            self.item_data = data[len(self.CMD_VEND_SUCCESS):]
            mdb_logger.info("vend succes item data: %s", tohex(self.item_data))
            try:
                self.item_dispensed_handler(self.item_data)
            except Exception:
                mdb_logger.error("caught exception while handling dispense with itemdata %s",
                        tohex(self.item_data), exc_info=True)

        elif self.is_command(data, self.CMD_VEND_FAILURE):
            if self.state is not self.STATE_SESSION_DISPENSED:
                mdb_logger.warning("got CMD_VEND_FAILURE in state %r" % self.state)
            self._set_state(self.STATE_SESSION_ENDING)
            mdb_logger.warn("dispense failed")
            self.item_dispensed_handler(None)

        elif self.is_command(data, self.CMD_VEND_SESS_COMPLETE):
            if self.state is not self.STATE_SESSION_ENDING:
                mdb_logger.warning("got CMD_VEND_SESS_COMPLETE in state %r" % self.state)
            self.item_dispensed_handler(None)
            self.response_data = self.RES_END_SESSION
            self._set_state(self.STATE_ENABLED)

        # not handled: CASH SALE

        elif self.is_command(data, self.CMD_READER_DISABLE):
            if self.state is not self.STATE_ENABLED:
                logging.warn("got disable while in state %s", self.state)
            self._set_state(self.STATE_DISABLED)

        elif self.is_command(data, self.CMD_READER_ENABLE):
            if self.state is not self.STATE_DISABLED:
                logging.warn("got enable while in state %s", self.state)
            self._set_state(self.STATE_ENABLED)

        elif self.is_command(data, self.CMD_READER_CANCEL):
            self.response_data = self.RES_CANCELLED

        elif self.is_command(data, self.CMD_REVALUE_REQUEST):
            self.response_data = self.RES_REVALUE_DENIED

        elif self.is_command(data, self.CMD_EXP_REQUEST_ID):
            self.response_data = ''.join([
                self.RES_PERIPHERAL_ID,
                fromhex('414258'), # manufacturer code - ASCII
                fromhex('202020202020202020202020'), # serial number - ASCII
                fromhex('413320202020202020202020'), # model number - ASCII
                fromhex('1531'), # software version - packed BCD
            ])

        # not handled: various extension commands

        else:
            mdb_logger.warning("unrecognized command "+tohex(data))

