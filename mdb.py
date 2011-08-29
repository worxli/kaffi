
import binascii
import logging

tohex = binascii.hexlify
fromhex = binascii.unhexlify

translator_logger = logging.getLogger("translator")

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
            translator_logger.info("received %s", tohex(self.received_data))
            data = self.handler(self.received_data)
            self.received_data = ""

            # prepare to send data
            translator_logger.info("sending %s", tohex(data))
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
            translator_logger.warn("mega komisch: %s nachem DLE" % tohex(c))

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
            translator_logger.info("es NAK")
        else:
            translator_logger.warn("mega komisch: %s im idle" % tohex(c))

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
            self.translator_logger.critical("uncaught exception", exc_info=True)
            self.running = False
            raise

    def stop(self):
        """
        Stop the state machine if it is running
        """
        self.running = False

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

    #
    # Misc codes
    #

    ACK = fromhex('00')


    def __init__(self, item_dispensed_handler):
        """
        Initialization.
        
        :param item_dispensed_handler: must be a callable. It is called with an
            item's data whenever that item is dispensed.
        """
        self.response_data = ""
        self.state = self.STATE_INACTIVE
        self.config_data = self.maxmin_data = self.item_data = None
        self.dispense_permitted = None
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
            self.dispense_permitted = None

        elif self.is_command(data, self.CMD_POLL):
            if self.state is self.STATE_INACTIVE:
                self.response_data = self.RES_RESET
                self._set_state(self.STATE_DISABLED)

            elif self.state is self.STATE_ENABLED and self.dispense_permitted is not None:
                self.response_data = self.RES_BEGIN_SESS + fromhex('FFFF')
                self._set_state(self.STATE_SESSION_IDLE)

            elif self.state is self.STATE_SESSION_IDLE and self.dispense_permitted is not True:
                self.response_data = self.RES_SESS_CANCEL_REQ

            #elif self.state is self.STATE_ENABLED and self.display_update:
            #    self.response_data = self.RES_DISPLAY_REQ + fromhex('64') + self.display_update[0]
            #    self.display_update = None

        elif self.is_command(data, self.CMD_SETUP_CONF_DATA):
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

            if self.dispense_permitted is True:
                mdb_logger.info("dispense allowed")
                self.response_data = self.RES_VEND_APPROVED + fromhex('FFFF') # electronic token
            elif self.dispense_permitted is False:
                mdb_logger.warn("dispensed denied")
                self.response_data = self.RES_VEND_DENIED
            else:
                mdb_logger.warn("got vend_request with dispense_permitted == %r", self.dispense_permitted)
                self.response_data = self.RES_VEND_DENIED

        elif self.is_command(data, self.CMD_VEND_CANCEL):
            mdb_logger.warn("dispense canceled")
            self.dispense_permitted = None
            self.response_data = self.RES_VEND_DENIED

        elif self.is_command(data, self.CMD_VEND_SUCCESS):
            self.item_data = data[len(self.CMD_VEND_SUCCESS):]
            mdb_logger.info("vend succes item data: %s", tohex(self.item_data))
            try:
                self.item_dispensed_handler(self.item_data)
            except Exception:
                mdb_logger.error("caught exception while handling dispense with itemdata %s",
                        tohex(self.item_data), exc_info=True)
            self.response_data = self.RES_END_SESSION

        elif self.is_command(data, self.CMD_VEND_FAILURE):
            mdb_logger.warn("dispense failed")

        elif self.is_command(data, self.CMD_VEND_SESS_COMPLETE):
            self.response_data = self.RES_END_SESSION
            self.dispense_permitted = None
            self._set_state(self.STATE_ENABLED)

        # not handled: CASH SALE

        elif self.is_command(data, self.CMD_READER_DISABLE):
            if self.state is not self.STATE_ENABLED:
                logging.warn("got disable while in state %s", self.state)
            self.dispense_permitted = None
            self._set_state(self.STATE_DISABLED)

        elif self.is_command(data, self.CMD_READER_ENABLE):
            if (self.state is not self.STATE_DISABLED):
                logging.warn("got enable while in state %s", self.state)
            self.dispense_permitted = None
            self._set_state(self.STATE_ENABLED)

        elif self.is_command(data, self.CMD_READER_CANCEL):
            self.dispense_permitted = None
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

