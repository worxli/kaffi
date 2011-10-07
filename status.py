import ordereddict
import logging
import urllib

import visstatus
import amivstatus
import vmpstatus

org_handlers = ordereddict.OrderedDict([
    ('VIS', (visstatus.get_status, visstatus.report_dispensed)),
    ('AMIV', (amivstatus.get_status, amivstatus.report_dispensed)),
    ('VMP', (vmpstatus.get_status, vmpstatus.report_dispensed)),
])

status_logger = logging.getLogger("status")

def check_legi(leginr):
    for org, handlers in org_handlers.iteritems():
        try:
            status = handlers[0](leginr)
        except Exception:
            status_logger.warning("caught exception in get_status for legi %s, org %s", leginr, org, exc_info=True)
        else:
            if status:
                return org
    return None

def report_dispense(rfidnr, org, item):
    import sqllogging
    sqllogging.log_msg("DISPENSE", "%s:%s:%s" % (org, rfidnr, item))

    try:
        org_handlers[org][1](rfidnr, item)
    except Exception:
        status_logger.error("caught exception report_dispense for legi %s, org %s, item %s", rfidnr, org, item, exc_info=True)
