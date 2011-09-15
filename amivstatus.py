
import amivid
import logging
from sqlalchemy import sql, schema, create_engine

logger = logging.getLogger("status.amiv")

nethz_cache = {}

def get_status(rfidnr):
    from kaffi import get_config
    config = get_config()
    aid = amivid.AmivID(
            config.get('amivid', 'apikey'),
            config.get('amivid', 'secret'),
            config.get('amivid', 'baseurl'))
    user = aid.getUser(int(rfidnr))
    if user:
        nethz_cache[rfidnr] = user['nethz']
        return int(user['apps']['kafi']) > 0
    return None

metadata = schema.MetaData()
dbengine = None
bierlog = None
insert = None

def get_connection():
    global dbengine, bierlog, insert

    if not dbengine:
        from kaffi import get_config
        config = get_config()

        db_uri = config.get('amivreport', 'db_uri')
        dbengine_ = create_engine(db_uri, pool_recycle=3600)

        bierlog_ = schema.Table('bierlog', metadata, autoload=True, autoload_with=dbengine_)
        insert_ = bierlog_.insert().values(
            username=sql.expression.bindparam('username'),
            org='amiv',
            account=None,
            time=sql.func.now(),
            slot=sql.expression.bindparam('slot'),
        )

        dbengine, bierlog, insert = dbengine_, bierlog_, insert_

    return dbengine

def report_dispensed(rfidnr, item):

    nethz = nethz_cache[rfidnr]
    slot = item + 10

    logger.info("dispensed %(item)s (%(slot)s) for %(rfidnr)s (%(nethz)s), AMIV" % locals())

    engine = get_connection()
    engine.execute(insert, username=nethz, slot=slot)
