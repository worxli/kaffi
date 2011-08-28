
from sqlalchemy import sql, schema, create_engine
import logging

metadata = schema.MetaData()
log_dbengine = None
coffeelog_tbl = None
config = None

fail_logger = logging.getLogger("fail")

def init():
    global log_dbengine, coffeelog_tbl, config

    from kaffi import get_config
    config = get_config()

    fail_logger.propagate = False
    fail_fp = open(config.get('log', 'faillog'), 'a', buffering=1)
    fail_logger.addHandler(logging.StreamHandler(fail_fp))

    db_uri = config.get('log', 'db_uri')
    db_tbl = config.get('log', 'db_tbl')
    log_dbengine = create_engine(db_uri, pool_recycle=3600)

    coffeelog_tbl = schema.Table(db_tbl, metadata, autoload=True, autoload_with=log_dbengine)

def log_msg(msg_type, msg):
    try:
        ins = coffeelog_tbl.insert().values(type=msg_type, msg=msg)
        log_dbengine.execute(ins)
    except Exception as e:
        fail_logger.error("failed to log msg %r: %r", msg_type, msg)

class SqlLogHandler(logging.Handler):

    def __init__(self, level=logging.NOTSET):
        logging.Handler.__init__(self, level)

    def emit(self, record):
        try:
            msg = self.format(record)
            log_msg(record.levelname, msg)
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)

