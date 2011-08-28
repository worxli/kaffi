import logging
import requests
import urllib
try:
    import json
except ImportError:
    import simplejson as json

logger = logging.getLogger("status.vis")

rfid_url_fmt = 'http://beer.vis.ethz.ch/rfid/%(rfid)s?format=json'
status_url_fmt = 'http://beer.vis.ethz.ch/status/%(nethz)s?format=json'

def get_json_from_response(response):
    r = response
    if r.headers['content-type'] == 'application/json':
        encoding = 'utf-8'
    else:
        m = re.match('^text/json; charset=([a-zA-Z0-9-]+)$', r.headers['content-type'])
        if m:
            encoding = m.group(1)
        else:
            raise ValueError("got unrecognized content type %s from %s's rfid url" % r.headers['content-type'], org)
    return json.loads(r.content.decode(encoding))

def get_status(rfidnr):

    from kaffi import get_config
    config = get_config()
    rfid_url_fmt = config.get('visstatus', 'rfid_url')
    status_url_fmt = config.get('visstatus', 'status_url')

    rfid_url = rfid_url_fmt % dict(rfid=rfidnr)
    logger.debug("lookup up rfid at %s", rfid_url)

    r = requests.get(rfid_url, headers=dict(Accept="application/json;q=1.0, text/json;q=0.9"))

    if r.status_code == requests.codes.not_found:
        return False
    if r.status_code != requests.codes.ok:
        logger.warning("got status %d from %s's rfid url", r.status_code, org)
        return False

    rfid_result = get_json_from_response(r)
    quoted_result = dict((k, urllib.quote(v)) for k, v in rfid_result.iteritems() if isinstance(v, basestring))
    status_url = status_url_fmt % quoted_result
    logger.debug("lookup up status for %s at %s", rfidnr, status_url)

    r = requests.get(status_url, headers=dict(Accept="application/json;q=1.0, text/json;q=0.9"))
    r.raise_for_status()

    status_result = get_json_from_response(r)

    return status_result['beer'] > 0
