# -*- coding: utf-8 -*-
from __future__ import absolute_import

import unittest
from mock import Mock
import binascii
import sys, os, os.path
tohex = binascii.hexlify
fromhex = binascii.unhexlify

class MdbStmTests(unittest.TestCase):
    def assertResponse(self, value, res):
        self.assertEqual(value[:len(res)+1], '\x00'+res)
    def assertCalled(self, call_mock, *args, **kwargs):
        self.assertEqual(call_mock.call_args, (args, kwargs))

    def test_dispense_polledclose(self):
        from kaffi import mdb
        handler = Mock()
        stm = mdb.MdbStm(lambda: True, handler)
        stm._set_state(stm.STATE_ENABLED)
        res = stm.received_data(stm.CMD_POLL)
        self.assertResponse(res, stm.RES_BEGIN_SESS)
        res = stm.received_data(stm.CMD_VEND_REQUEST+fromhex('0001'))
        self.assertResponse(res, stm.RES_VEND_APPROVED+fromhex('FFFF'))
        res = stm.received_data(stm.CMD_VEND_SUCCESS+fromhex('0001'))
        self.assertCalled(handler, fromhex('0001'))
        res = stm.received_data(stm.CMD_POLL)
        self.assertResponse(res, stm.RES_SESS_CANCEL_REQ)
        res = stm.received_data(stm.CMD_VEND_SESS_COMPLETE)
        self.assertResponse(res, stm.RES_END_SESSION)
        self.assertCalled(handler, None)

    def test_dispense_autoclose(self):
        from kaffi import mdb
        handler = Mock()
        stm = mdb.MdbStm(lambda: True, handler)
        stm._set_state(stm.STATE_ENABLED)
        res = stm.received_data(stm.CMD_POLL)
        self.assertResponse(res, stm.RES_BEGIN_SESS)
        res = stm.received_data(stm.CMD_VEND_REQUEST+fromhex('0001'))
        self.assertResponse(res, stm.RES_VEND_APPROVED+fromhex('FFFF'))
        res = stm.received_data(stm.CMD_VEND_SUCCESS+fromhex('0001'))
        self.assertCalled(handler, fromhex('0001'))
        res = stm.received_data(stm.CMD_VEND_SESS_COMPLETE)
        self.assertResponse(res, stm.RES_END_SESSION)
        self.assertCalled(handler, None)
        self.assertEqual(stm.state, stm.STATE_ENABLED)

    def test_nodispense_polledclose(self):
        from kaffi import mdb
        handler = Mock()
        stm = mdb.MdbStm(lambda: False, handler)
        stm._set_state(stm.STATE_ENABLED)
        res = stm.received_data(stm.CMD_POLL)
        self.assertResponse(res, stm.RES_BEGIN_SESS)
        res = stm.received_data(stm.CMD_VEND_REQUEST+fromhex('0001'))
        self.assertResponse(res, stm.RES_VEND_DENIED)
        res = stm.received_data(stm.CMD_POLL)
        self.assertResponse(res, stm.RES_SESS_CANCEL_REQ)
        res = stm.received_data(stm.CMD_VEND_SESS_COMPLETE)
        self.assertResponse(res, stm.RES_END_SESSION)
        self.assertCalled(handler, None)
        self.assertEqual(stm.state, stm.STATE_ENABLED)

    def test_nodispense_autoclose(self):
        from kaffi import mdb
        handler = Mock()
        stm = mdb.MdbStm(lambda: False, handler)
        stm._set_state(stm.STATE_ENABLED)
        res = stm.received_data(stm.CMD_POLL)
        self.assertResponse(res, stm.RES_BEGIN_SESS)
        res = stm.received_data(stm.CMD_VEND_REQUEST+fromhex('0001'))
        self.assertResponse(res, stm.RES_VEND_DENIED)
        res = stm.received_data(stm.CMD_VEND_SESS_COMPLETE)
        self.assertResponse(res, stm.RES_END_SESSION)
        self.assertCalled(handler, None)
        self.assertEqual(stm.state, stm.STATE_ENABLED)

    def test_changedispense_autoclose(self):
        from kaffi import mdb
        dispense = False
        handler = Mock()
        stm = mdb.MdbStm(lambda: dispense, handler)
        stm._set_state(stm.STATE_ENABLED)
        res = stm.received_data(stm.CMD_POLL)
        self.assertResponse(res, stm.RES_BEGIN_SESS)
        res = stm.received_data(stm.CMD_VEND_REQUEST+fromhex('0001'))
        self.assertResponse(res, stm.RES_VEND_DENIED)
        dispense = True
        res = stm.received_data(stm.CMD_VEND_SESS_COMPLETE)
        self.assertResponse(res, stm.RES_END_SESSION)
        self.assertCalled(handler, None)
        self.assertEqual(stm.state, stm.STATE_ENABLED)

    def test_changedispense_polledclose(self):
        from kaffi import mdb
        dispense = False
        handler = Mock()
        stm = mdb.MdbStm(lambda: dispense, handler)
        stm._set_state(stm.STATE_ENABLED)
        res = stm.received_data(stm.CMD_POLL)
        self.assertResponse(res, stm.RES_BEGIN_SESS)
        res = stm.received_data(stm.CMD_VEND_REQUEST+fromhex('0001'))
        self.assertResponse(res, stm.RES_VEND_DENIED)
        dispense = True
        res = stm.received_data(stm.CMD_POLL)
        self.assertResponse(res, stm.RES_SESS_CANCEL_REQ)
        res = stm.received_data(stm.CMD_VEND_SESS_COMPLETE)
        self.assertResponse(res, stm.RES_END_SESSION)
        self.assertCalled(handler, None)
        self.assertEqual(stm.state, stm.STATE_ENABLED)

if __name__ == '__main__':
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    unittest.main()
