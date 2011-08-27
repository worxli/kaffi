
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
        self.running = True
        self.legi_receiver = legi_receiver
        self.enable = enable

    def run(self):
        self.serial.write(self.enable)
        while self.running:
            ans = self.serial.read(size=14)
            if ans:
                legi_logger.debug("got input %s", tohex(ans))
            if ans and len(ans) == 14 and ans[:2] == fromhex("0d80"):
                legi = tohex(ans[10:13])
                legi_logger.info("got legi %r" % legi)
                self.legi_receiver(legi)
            if ans:
                self.serial.write(self.enable)

    def stop(self):
        self.running = False

class LegiChecker(object):

    def __init__(self, trigger):
        self.trigger = trigger

    def receive_legi(self, leginr):
        # TODO: check
        self.trigger()

def run():

    def print_(arg):
        print arg

    logging.basicConfig(level=logging.DEBUG)

    from kaffi import get_config
    enable = fromhex(get_config().get('legi', 'enable'))

    s = serial.Serial('/dev/ttyS1', 38400, timeout=1)
    l = LegiListener(s, enable, print_)
    t = threading.Thread(target=l.run)
    t.daemon = True
    t.start()

    return l

