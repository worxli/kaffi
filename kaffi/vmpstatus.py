# -*- coding: utf-8 -*-
from __future__ import absolute_import

import logging
try:
    # python3
    from urllib.request import urlopen
except ImportError:
    # python2
    from urllib import urlopen
try:
    import json
except ImportError:
    import simplejson as json

logger = logging.getLogger("status.vmp")

status_url = 'https://vmp.ethz.ch/coffee/vmp_coffee_check.php?rfidnr=%(rfidnr)s'
report_url = 'https://vmp.ethz.ch/coffee/vmp_coffee_billing.php?rfidnr=%(rfidnr)s&slot_id=%(item)s'

def get_status(rfid):
    url = status_url % dict(rfidnr=rfid)
    res = urlopen(url)
    if res.getcode() == 404:
        return None
    elif res.getcode() != 200:
        logger.warn("vmp status url returned status %s" % res.getcode())
        return None
    else:
        status = json.load(res)
        return status['status'] == 0

def report_dispensed(rfid, item):
    logger.info("dispensed %s for %s, VMP" % (item, rfid))

    url = report_url % dict(rfidnr=rfid, item=item)
    res = urlopen(url)
    if res.getcode() != 200:
        logger.warn("vmp report url returned status %s" % res.getcode())
