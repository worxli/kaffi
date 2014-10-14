#-*- coding: utf-8 -*-
from __future__ import absolute_import
# from: http://code.activestate.com/recipes/577548-https-httplib-client-connection-with-certificate-v/

import socket
import ssl
try:
    # python3
    from http.client import HTTPSConnection
except ImportError:
    # python2
    from httplib import HTTPSConnection

class HTTPSClientAuthConnection(HTTPSConnection):
    """ Class to make a HTTPS connection, with support for full client-based SSL Authentication"""

    def __init__(self, host, port, key_file, cert_file, ca_file, timeout=None):
        HTTPSConnection.__init__(self, host, key_file=key_file, cert_file=cert_file)
        self.key_file = key_file
        self.cert_file = cert_file
        self.ca_file = ca_file
        self.timeout = timeout
        self.port = port

    def connect(self):
        """ Connect to a host on a given (SSL) port.
            If ca_file is pointing somewhere, use it to check Server Certificate.

            Redefined/copied and extended from httplib.py:1105 (Python 2.6.x).
            This is needed to pass cert_reqs=ssl.CERT_REQUIRED as parameter to ssl.wrap_socket(),
            which forces SSL to check server certificate against our client certificate.
        """
        sock = socket.create_connection((self.host, self.port), self.timeout)
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
        # If there's no CA File, don't force Server Certificate Check
        if self.ca_file:
            self.sock = ssl.wrap_socket(sock, self.key_file, self.cert_file, ca_certs=self.ca_file, cert_reqs=ssl.CERT_REQUIRED)
        else:
            self.sock = ssl.wrap_socket(sock, self.key_file, self.cert_file, cert_reqs=ssl.CERT_NONE)

if __name__ == '__main__':
    # Little test-case of our class
    import sys
    if len(sys.argv) != 6:
        print("""usage: python https_auth_handler.py host port key_file cert_file ca_file
                 e.g.: python httplibssl.py api.vis.ethz.ch 4433 /etc/vis/kaffi.key /etc/vis/kaffi.crt /etc/vis/visapi.crt""")
        sys.exit(1)
    else:
        host, port, key_file, cert_file, ca_file = sys.argv[1:]
    conn = HTTPSClientAuthConnection(host, port, key_file=key_file, cert_file=cert_file, ca_file=ca_file)
    conn.request('GET', '/coffee/status/046631@rfid.ethz.ch')
    response = conn.getresponse()
    print("%d, %s" % (response.status, response.reason))
    data = response.read()
    print(data)
    conn.close()
