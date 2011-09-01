
from sqlalchemy import sql, schema, create_engine, exc
import logging

metadata = schema.MetaData()
log_dbengine = None
coffeelog_tbl = None
config = None

fail_logger = logging.getLogger("fail")
reconnect_timer = None

def init():
    global config

    from kaffi import get_config
    config = get_config()

    fail_logger.propagate = False
    fail_fp = open(config.get('log', 'faillog'), 'a', buffering=1)
    fail_handler = logging.StreamHandler(fail_fp)
    fail_formatter = logging.Formatter(fmt="%(asctime)s|%(levelname)s|%(name)s|%(message)s")
    fail_handler.setFormatter(fail_formatter)
    fail_logger.addHandler(fail_handler)

    try_connect()

def try_connect(retry_interval=300):
    global log_dbengine, coffeelog_tbl, reconnect_timer
    if reconnect_timer:
        reconnect_timer.cancel()

    db_uri = config.get('log', 'db_uri')
    db_tbl = config.get('log', 'db_tbl')
    try:
        log_dbengine = create_engine(db_uri, pool_recycle=3600)
        coffeelog_tbl = schema.Table(db_tbl, metadata, autoload=True, autoload_with=log_dbengine)
    except exc.OperationalError:
        fail_logger.error("Failed to connect to sql log", exc_info=True)
        logging.critical("Failed to connect to sql log")
        import threading
        reconnect_timer = threading.Timer(retry_interval, try_connect)
        reconnect_timer.start()

def stop_retrying():
    if reconnect_timer:
        reconnect_timer.cancel()

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

