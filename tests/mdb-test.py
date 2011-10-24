# -*- coding: utf-8 -*-
from __future__ import absolute_import

import unittest
from mock import Mock
import binascii
import sys, os, os.path
tohex = binascii.hexlify
fromhex = binascii.unhexlify

class MdbL1StmEnabledTests(unittest.TestCase):

    def assertResponse(self, value, res):
        self.assertEqual(value[:len(res)+1], '\x00'+res)
    def assertCalled(self, call_mock, *args, **kwargs):
        self.assertEqual(call_mock.call_args, (args, kwargs))

    def setUp(self):
        from kaffi import mdb
        self.status, self.dispensed, self.denied, self.info_o = Mock(), Mock(), Mock(), '_obj'
        self.stm = mdb.MdbL1Stm(self.status, self.dispensed, self.denied)
        self.stm._set_state(self.stm.st_enabled)

    def tearDown(self):
        self.stm = None

    def test_dispense_polledclose(self):
        self.status.return_value = (True, self.info_o)

        res = self.stm.received_data(self.stm.CMD_POLL)
        self.assertResponse(res, self.stm.RES_BEGIN_SESS)
        res = self.stm.received_data(self.stm.CMD_VEND_REQUEST+fromhex('0001'))
        self.assertResponse(res, self.stm.RES_VEND_APPROVED+fromhex('FFFF'))
        res = self.stm.received_data(self.stm.CMD_VEND_SUCCESS+fromhex('0001'))
        self.assertCalled(self.dispensed, self.info_o, fromhex('0001'))
        res = self.stm.received_data(self.stm.CMD_POLL)
        self.assertResponse(res, self.stm.RES_SESS_CANCEL_REQ)
        res = self.stm.received_data(self.stm.CMD_VEND_SESS_COMPLETE)
        self.assertResponse(res, self.stm.RES_END_SESSION)

    def test_dispense_autoclose(self):
        self.status.return_value = (True, self.info_o)

        res = self.stm.received_data(self.stm.CMD_POLL)
        self.assertResponse(res, self.stm.RES_BEGIN_SESS)
        res = self.stm.received_data(self.stm.CMD_VEND_REQUEST+fromhex('0001'))
        self.assertResponse(res, self.stm.RES_VEND_APPROVED+fromhex('FFFF'))
        res = self.stm.received_data(self.stm.CMD_VEND_SUCCESS+fromhex('0001'))
        self.assertCalled(self.dispensed, self.info_o, fromhex('0001'))
        #self.dispensed.mockCheckCall(self, 0, "__call__", fromhex('0001'))
        res = self.stm.received_data(self.stm.CMD_VEND_SESS_COMPLETE)
        self.assertResponse(res, self.stm.RES_END_SESSION)
        self.assertEqual(self.stm.state, self.stm.st_enabled)

    def test_nodispense_polledclose(self):
        self.status.return_value = (False, self.info_o)

        res = self.stm.received_data(self.stm.CMD_POLL)
        self.assertResponse(res, self.stm.RES_BEGIN_SESS)
        res = self.stm.received_data(self.stm.CMD_VEND_REQUEST+fromhex('0001'))
        self.assertResponse(res, self.stm.RES_VEND_DENIED)
        res = self.stm.received_data(self.stm.CMD_POLL)
        self.assertResponse(res, self.stm.RES_SESS_CANCEL_REQ)
        res = self.stm.received_data(self.stm.CMD_VEND_SESS_COMPLETE)
        self.assertResponse(res, self.stm.RES_END_SESSION)
        self.assertCalled(self.denied, self.info_o)
        #self.denied.mockCheckCall(self, 0, "__call__", None)
        self.assertEqual(self.stm.state, self.stm.st_enabled)

    def test_nodispense_autoclose(self):
        self.status.return_value = (False, self.info_o)

        res = self.stm.received_data(self.stm.CMD_POLL)
        self.assertResponse(res, self.stm.RES_BEGIN_SESS)
        res = self.stm.received_data(self.stm.CMD_VEND_REQUEST+fromhex('0001'))
        self.assertResponse(res, self.stm.RES_VEND_DENIED)
        res = self.stm.received_data(self.stm.CMD_VEND_SESS_COMPLETE)
        self.assertResponse(res, self.stm.RES_END_SESSION)
        self.assertCalled(self.denied, self.info_o)
        self.assertEqual(self.stm.state, self.stm.st_enabled)

    def test_changedispense_autoclose(self):
        self.status.return_value = (False, self.info_o)
        res = self.stm.received_data(self.stm.CMD_POLL)
        self.assertResponse(res, self.stm.RES_BEGIN_SESS)
        res = self.stm.received_data(self.stm.CMD_VEND_REQUEST+fromhex('0001'))
        self.assertResponse(res, self.stm.RES_VEND_DENIED)
        self.status.return_value = (True, self.info_o)
        res = self.stm.received_data(self.stm.CMD_VEND_SESS_COMPLETE)
        self.assertResponse(res, self.stm.RES_END_SESSION)
        self.assertCalled(self.denied, self.info_o)
        #self.denied.mockCheckCall(self, 0, "__call__", None)
        self.assertEqual(self.stm.state, self.stm.st_enabled)

    def test_changedispense_polledclose(self):
        self.status.return_value = (False, self.info_o)
        res = self.stm.received_data(self.stm.CMD_POLL)
        self.assertResponse(res, self.stm.RES_BEGIN_SESS)
        res = self.stm.received_data(self.stm.CMD_VEND_REQUEST+fromhex('0001'))
        self.assertResponse(res, self.stm.RES_VEND_DENIED)
        self.status.return_value = (True, self.info_o)
        res = self.stm.received_data(self.stm.CMD_POLL)
        self.assertResponse(res, self.stm.RES_SESS_CANCEL_REQ)
        res = self.stm.received_data(self.stm.CMD_VEND_SESS_COMPLETE)
        self.assertResponse(res, self.stm.RES_END_SESSION)
        self.assertCalled(self.denied, self.info_o)
        #self.denied.mockCheckCall(self, 0, "__call__", None)
        self.assertEqual(self.stm.state, self.stm.st_enabled)

if __name__ == '__main__':
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    unittest.main()
