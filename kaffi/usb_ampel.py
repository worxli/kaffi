#-*- coding: utf-8 -*- 
import httplib
import subprocess
import time
import logging

logger = logging.getLogger("usb_ampel")

clewarecontrol = '/opt/vis/clewarecontrol'
light = {u'green':'2', u'yellow':'1', u'red':'0'}

def switch(status, old_status):
    try:
        if old_status is not None and status != old_status:
            subprocess.call([clewarecontrol, '-c', '1', '-as', light[old_status] ,'0' ])
        if status is not None:
            subprocess.call([clewarecontrol, '-c', '1', '-as', light[status] ,'1' ])
    except Exception as e:
        logger.warn(e)

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
        return result
    except Exception as e:
        logger.warn(e)
        return False

def ampel_controller():
    status = None
    while True:
        old_status = status
        status = get_status()
        switch(status, old_status)
        time.sleep(5)
        

