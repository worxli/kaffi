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

logger = logging.getLogger("status.vis")

def get_url(rfid, route):
    from .system import get_config
    config = get_config()
    base = config.get('visstatus', 'baseUrl')
    apikey = config.get('visstatus', 'key')

    if base and apikey:
        return base + '/coffee/' + route + '/' + rfid + '?key=' apikey
    else:
        None

def get_status(rfid):

    status_url = get_url(rfid, 'status')
    logger.debug("looking up status at %s", status_url)
    response = urlopen(status_url)

    if response.getcode() != 200:
        logger.warning("got status %d from VIS's status url", response.getcode())
        return False

    return response > 0

def report_dispensed(rfidnr, item):
    logger.info("dispensed %s for %s, VIS", item, rfidnr)

    report_url = get_url(rfidnr, 'dispensed')
    logger.info("report at %s", report_url)

    response = urlopen(report_url)
    if response.getcode() != 200:
        logger.warn("vis report url returned status %s" % response.getcode())
