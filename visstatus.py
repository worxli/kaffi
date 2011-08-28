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

    print headers
    content_type = headers['content-type']
    m = re.match(r'^\s*(text/[^;]+);\s*charset=([a-zA-Z0-9-]+)\s*$', content_type)
    if m:
        content_type, encoding = m.group(1).strip(), m.group(2)
    else:
        content_type, encoding = content_type.strip(), 'utf-8'
    if content_type not in ('application/json', 'text/json'):
        raise ValueError("got unrecognized content type %s from %s's rfid url" % r.headers['content-type'], org)

    print repr(data)
    result = json.loads(data.decode(encoding))
    print repr(result)
    return result

def fetch_url(url, body=None, headers=None):

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

    c.request('GET', o.path + '?' + o.query, body, headers)
    response = c.getresponse()
    data = response.read()
    c.close()

    return response, data

def get_status(rfidnr):

    from kaffi import get_config
    config = get_config()
    rfid_url_fmt = config.get('visstatus', 'rfid_url')
    status_url_fmt = config.get('visstatus', 'status_url')

    rfid_url = rfid_url_fmt % dict(rfid=rfidnr)
    logger.debug("lookup up rfid at %s", rfid_url)

    response, data = fetch_url(rfid_url, headers=dict(Accept="application/json;q=1.0, text/json;q=0.9"))
    if response.status == 404:
        return False
    if response.status != 200:
        logger.warning("got status %d %s from VIS's rfid url", response.status, response.reason)
        return False

    rfid_result = get_json_from_response(response, data)
    quoted_result = dict((k, urllib.quote(v)) for k, v in rfid_result.iteritems() if isinstance(v, basestring))
    status_url = status_url_fmt % quoted_result
    logger.debug("lookup up status for %s at %s", rfidnr, status_url)

    response, data = fetch_url(status_url, headers=dict(Accept="application/json;q=1.0, text/json;q=0.9"))
    if response.status != 200:
        raise urllib2.HTTPError(status_url, response.status, response.reason, response.getheaders())

    status_result = get_json_from_response(response, data)

    return status_result['beer'] > 0
