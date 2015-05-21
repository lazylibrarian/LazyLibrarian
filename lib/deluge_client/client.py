import logging
import socket
import ssl
import struct
import zlib

from .rencode import dumps, loads

RPC_RESPONSE = 1
RPC_ERROR = 2
RPC_EVENT = 3

#MESSAGE_HEADER_SIZE = 5
READ_SIZE = 10

logger = logging.getLogger(__name__)

class ConnectionLostException(Exception):
    pass

class CallTimeoutException(Exception):
    pass

class DelugeRPCClient(object):
    timeout = 20
    
    def __init__(self, host, port, username, password):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        
        self.request_id = 1
        self.connected = False
        self._socket = ssl.wrap_socket(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        self._socket.settimeout(self.timeout)
    
    def connect(self):
        """
        Connects to the Deluge instance
        """
        logger.info('Connecting to %s:%s' % (self.host, self.port))
        self._socket.connect((self.host, self.port))
        logger.debug('Connected to Deluge, logging in')
        result = self.call('daemon.login', self.username, self.password)
        logger.debug('Logged in with value %r' % result)
        self.connected = True
    
    def call(self, method, *args, **kwargs):
        """
        Calls an RPC function
        """
        self.request_id += 1
        logger.debug('Calling reqid %s method %r with args:%r kwargs:%r' % (self.request_id, method, args, kwargs))
        
        req = ((self.request_id, method, args, kwargs), )
        req = zlib.compress(dumps(req))
        
        #self._socket.send('D' + struct.pack("!i", len(req))) # seems to be for the future !
        self._socket.send(req)
        
        data = b''
        while True:
            try:
                d = self._socket.recv(READ_SIZE)
            except ssl.SSLError:
                raise CallTimeoutException()
            
            data += d
            try:
                data = zlib.decompress(data)
            except zlib.error:
                if not d:
                    raise ConnectionLostException()
                continue
            break
        
        data = list(loads(data))
        msg_type = data.pop(0)
        request_id = data.pop(0)
        
        if msg_type == RPC_ERROR:
            exception_type, exception_msg, traceback = data
            raise Exception()
        elif msg_type == RPC_RESPONSE:
            retval = data[0]
            return retval