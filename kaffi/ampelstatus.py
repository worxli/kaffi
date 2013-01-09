#-*- coding: utf-8 -*- 
import httplib

import logging

logger = logging.getLogger("status.ampel")

def get_status():
    from .system import get_config
    config = get_config()
    ampel_host = config.get('ampel', 'host')
    ampel_suffix = config.get('ampel', 'suffix')
    try:
        connection = httplib.HTTPSConnection(ampel_host, timeout=5.0)
        connection.request('GET', ampel_suffix)
        response = connection.getresponse()
        result = response.read()
        logger.info("ampel result: " + result)

        return result in [u'green', u'yellow']
    except Exception as e:
        logger.warn(e)
        return False
