import ordereddict
import logging
import urllib

import visstatus
import amivstatus

org_handlers = ordereddict.OrderedDict([
    ('VIS', visstatus.get_status),
    ('AMIV', amivstatus.get_status),
])

status_logger = logging.getLogger("status")

def check_legi(leginr):
    for org, get_status in org_handlers.iteritems():
        try:
            status = get_status(leginr)
        except Exception:
            status_logger.warning("caught exception in get_status for legi %s, org %s", leginr, org, exc_info=True)
        else:
            if status:
                return org
    return None

def report_dispense(rfidnr, org, item):
    import sqllogging
    sqllogging.log_msg("DISPENSE", "%s:%s:%s" % (org, rfidnr, item))

    #if 'dispensed' in org_urls[org]:
    #    data = json.dumps(dict(rfidnr=rfidnr, item=item))
    #    requests.post(org_urls[org]['dispensed'], data)

    print "dispensed", rfidnr, org, item
