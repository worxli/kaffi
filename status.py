import ordereddict
import requests
import logging
try:
    import json
except ImportError:
    import simplejson as json
import urllib

org_urls = ordereddict.OrderedDict([
    ('VIS', {
        'rfid': 'http://beer.vis.ethz.ch/rfid/%(rfid)s?format=json',
        'status': 'http://beer.vis.ethz.ch/status/%(nethz)s?format=json',
    }),
])

status_logger = logging.getLogger("status")

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
    for org, urls in org_urls.iteritems():

        rfid_url = urls['rfid'] % dict(rfid=rfidnr)
        status_logger.debug("lookup up rfid at %s", rfid_url)

        r = requests.get(rfid_url, headers=dict(Accept="application/json;q=1.0, text/json;q=0.9"))

        if r.status_code == requests.codes.not_found:
            continue
        if r.status_code != requests.codes.ok:
            status_logger.warning("got status %d from %s's rfid url", r.status_code, org)
            continue

        rfid_result = get_json_from_response(r)
        quoted_result = dict((k, urllib.quote(v)) for k, v in rfid_result.iteritems() if isinstance(v, basestring))
        status_url = urls['status'] % quoted_result
        status_logger.debug("lookup up status for %s at %s", rfidnr, status_url)

        r = requests.get(status_url, headers=dict(Accept="application/json;q=1.0, text/json;q=0.9"))
        r.raise_for_status()

        status_result = get_json_from_response(r)

        return org, rfid_result, status_result
    status_logger.warning("%s not found", rfidnr)

def check_legi(leginr):
    try:
        result = get_status(leginr)
    except Exception:
        status_logger.error("caught exception while checking legi %s", leginr, exc_info=True)
        return None
    if not result:
        return None
    org, rfid_result, status_result = result
    if status_result['beer'] > 0:
        return org
    return None

def report_dispense(rfidnr, org, item):
    import sqllogging
    sqllogging.log_msg("DISPENSE", "%s:%s:%s" % (org, rfidnr, item))

    if 'dispensed' in org_urls[org]:
        import urllib
        data = json.dumps(dict(rfidnr=rfidnr, item=item))
        requests.post(org_urls[org]['dispensed'], data)

    print "dispensed", rfidnr, org, item
