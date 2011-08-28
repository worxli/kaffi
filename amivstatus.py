
import amivid
import logging

logger = logging.getLogger("status.amiv")

def get_status(rfidnr):
    from kaffi import get_config
    config = get_config()
    aid = amivid.AmivID(
            config.get('amivid', 'apikey'),
            config.get('amivid', 'secret'),
            config.get('amivid', 'baseurl'))
    user = aid.getUser(int(rfidnr))
    return user and user['apps']['beer'] > 0

