import logging
import requests
import urllib
import urllib2
import re
try:
    import json
except ImportError:
    import simplejson as json

logger = logging.getLogger("status.vis")

def get_json_from_response(response, data):

    headers = response.getheaders()
    headers = dict((h.lower(), v) for h, v in headers)

    if headers.get('content-encoding', '') == 'gzip':
        import zlib
        try:
            data = zlib.decompress(data, 16+zlib.MAX_WBITS)
        except zlib.error:
            pass

    content_type = headers['content-type']
    m = re.match(r'^\s*(text/[^;]+);\s*charset=([a-zA-Z0-9-]+)\s*$', content_type)
    if m:
        content_type, encoding = m.group(1).strip(), m.group(2)
    else:
        content_type, encoding = content_type.strip(), 'utf-8'
    if content_type not in ('application/json', 'text/json'):
        raise ValueError("got unrecognized content type %s" % headers['content-type'])

    return json.loads(data.decode(encoding))

def request_url(url, method, body=None, headers=None):
    if body is None:
        body = ''
    if headers is None:
        headers = {}

    if '//' not in url:
        url = 'https://'+url
    from urlparse import urlsplit
    o = urlsplit(url)

    if o.scheme == 'https':
        from kaffi import get_config
        config = get_config()
        key_file = config.get('visstatus', 'key_file')
        cert_file = config.get('visstatus', 'cert_file')
        ca_file = config.get('visstatus', 'ca_file') if config.has_option('visstatus', 'ca_file') else None

        import httplibssl
        c = httplibssl.HTTPSClientAuthConnection(o.hostname, int(o.port or 443), key_file, cert_file, ca_file)
        #import httplib
        #c = httplib.HTTPSConnection(o.hostname, int(o.port or 443), key_file, cert_file)
    else:
        import httplib
        c = httplib.HTTPConnection(o.hostname, int(o.port or 80))

    c.request(method, o.path + '?' + o.query, body, headers)
    response = c.getresponse()
    data = response.read()
    c.close()

    return response, data

def fetch_url(url, body=None, headers=None):

    return request_url(url, 'GET', body, headers)

def post_url(url, data=None, headers=None):

    return request_url(url, 'POST', data, headers)

def get_status(rfid):

    from kaffi import get_config
    config = get_config()
    status_url_fmt = config.get('visstatus', 'status_url')

    status_url = status_url_fmt % dict(rfid=rfid)
    logger.debug("looking up status at %s", status_url)
    response, data = fetch_url(status_url, headers=dict(Accept="application/json;q=1.0, text/json;q=0.9"))
    if response.status == 404:
        return False
    if response.status != 200:
        logger.warning("got status %d %s from VIS's status url", response.status, response.reason)
        return False

    status_result = get_json_from_response(response, data)

    return status_result['coffees'] > 0

def report_dispensed(rfidnr, item):
    from kaffi import get_config
    config = get_config()

    dispense_url_fmt = config.get('visstatus', 'dispense_url')
    dispense_url = dispense_url_fmt % dict(rfidnr=rfidnr, item=item)

    dispense_data_fmt = config.get('visstatus', 'dispense_data')
    dispense_data = dispense_data_fmt % dict(rfidnr=rfidnr, item=item)

    response, data = post_url(dispense_url, dispense_data)
    if response.status != 200:
        raise urllib2.HTTPError(dispense_url, response.status, response.reason, response.getheaders(), None)
