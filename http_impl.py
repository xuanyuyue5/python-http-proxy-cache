import socket
from typing import Dict, Tuple
from err_response import ProxyErrException
PROXY_ID = 'python-http-proxy'

# Headers fields that will be use
_META_HEADER_FIELDS = ['connection', 'proxy-connection', 'transfer-encoding', 'content-length', 'via']
_BUF_SIZE = 4096

class HTTPRequest:
    def __init__(self):
        self.method: str = ''
        self.url: str = ''
        self.http_version: str = 'HTTP/1.1'
        self.headers: Dict[str, str] = {}
        self.body: bytes = b''
        
        # Extra info for logging
        self.first_line: str = ''
        self.date_time_formated: str = ''
        

    def send_to(self, socket: socket.socket):
        """
            Send this request
        """
        socket.sendall(self._to_bytes())
        return

    def _to_bytes(self) -> bytes:
        """
            Format according to HTTP protocol and convert to bytes
        """
        data = f'{self.method} {self.url} {self.http_version}\r\n'
        for k, v in self.headers.items():
            if k in _META_HEADER_FIELDS:
                data += f"{k.title()}: {v}\r\n"
            else:
                data += f"{k}: {v}\r\n"
        data += "\r\n"
        data = data.encode() + self.body
        return data


class HTTPResponse:
    def __init__(self):
        self.http_version: str = 'HTTP/1.1'
        self.status_code: int = -1
        self.status_phase: str = ''
        self.headers: Dict[str, str] = {}
        self.body: bytes = b''

    def send_to(self, socket: socket.socket):
        """
            Send this response
        """
        socket.sendall(self._to_bytes())
        return

    def _to_bytes(self) -> bytes:
        """
            Format according to HTTP protocol and convert to bytes
        """
        data = f'{self.http_version} {self.status_code} {self.status_phase}\r\n'
        for k, v in self.headers.items():
            if k in _META_HEADER_FIELDS:
                data += f"{k.title()}: {v}\r\n"
            else:
                data += f"{k}: {v}\r\n"
        data += "\r\n"
        data = data.encode() + self.body
        return data


class HTTPError(Exception):
    """
        HTTPError is used to indicate that an error occurred when reading data and parsing it into the HTTP protocol. 
        It is used to indicate that the HTTP protocol data read from a TCP data stream is not in the correct format.
    """
    def __init__(self, message: str):
        super().__init__(message)


class ConnectionCloseError(Exception):
    """
        Used to indicate that the connection is closed
    """
    def __init__(self, message: str):
        super().__init__(message)

# Helper function to read from socket until a specific delimiter is found
def _read_until_delimiter(sock: socket.socket, initial_buffer: bytes, delimiter: bytes) -> Tuple[bytes, bytes]:
    """
    Reads from the socket, accumulating data in a buffer, until the delimiter is found.
    Returns a tuple: (data_before_delimiter, remaining_buffer_after_delimiter).
    """
    buffer = initial_buffer
    data = b''
    while delimiter not in buffer:
        data = sock.recv(_BUF_SIZE)
        if not data: # Connection closed or no more data available
            break
        buffer += data

    buffer_split = buffer.split(delimiter, 1)
    if len(buffer_split) == 2:
        data, remaining_buffer = buffer_split[0], buffer_split[1]
        return data, remaining_buffer
    elif not data:
        # connection close
        raise ConnectionCloseError(message="Connection closed unexpectedly")
    else:
            
        # # Delimiter not found in the received data. This could mean an incomplete message
        # # or the connection closed prematurely.
        # data = buffer_split[0]
        # return data, b'' # Return all accumulated data, with no remaining buffer
        raise HTTPError("Incomplete HTTP message")


def _read_until_close(sock: socket.socket, initial_buffer: bytes) -> Tuple[bytes, bytes]:
    """
        Read data until the connection is closed, or until the target size of data is read
    """
    buffer = initial_buffer
    while True:
        data = sock.recv(_BUF_SIZE)
        if not data: # Connection closed or no more data available
            break
        buffer += data
    return buffer, b''


def _read_until_size(sock: socket.socket, initial_buffer: bytes, target_size: int) -> Tuple[bytes, bytes]:
    """
        Read data from socket until receive data of given target_size
        Return (data_of_target_size, remaining_data_buffer).
    """
    buffer = initial_buffer
    while len(buffer) < target_size:
        data = sock.recv(_BUF_SIZE)
        if not data: # Connection closed or no more data available
            break
        buffer += data
    if len(buffer) == target_size or target_size==-1:
        return buffer, b''
    elif len(buffer) > target_size:
        buffer, remaining_buf = buffer[:target_size], buffer[target_size:]
        return buffer, remaining_buf
    else:
        raise HTTPError("Incomplete HTTP message")


def parse_http_request(sock: socket.socket, buffer: bytes) -> Tuple[HTTPRequest, bytes]:
    req = HTTPRequest()

    # 1. Read first line
    start_line_bytes, remining_data = _read_until_delimiter(sock, buffer, b'\r\n')
    start_line = start_line_bytes.decode('latin-1')
    req.first_line = start_line
    start_line_parts = start_line.split(' ', 2) # e.g., "GET /path.txt HTTP/1.1"
    
    if len(start_line_parts) == 3:
        req.method = start_line_parts[0]
        req.url = start_line_parts[1]
        req.http_version = start_line_parts[2]
    else:
        # Malformed start line, return partially populated request
        raise HTTPError(f"Received invalid HTTP start line: {start_line}")

    remining_data = _parse_headers(sock, req.headers, remining_data)
    
    # Parse request body if it is a POST request
    if req.method == 'POST':
        req.body, remining_data = _parse_body(sock, remining_data, req.headers)
    return req, remining_data


def parse_http_response(sock: socket.socket, request_method:str) -> Tuple[HTTPResponse, bytes]:
    """
    Parses an HTTP response from the given socket.

    Args:
        sock: The socket to read data from.

    Returns:
        The HTTPResponse object.
    """
    resp = HTTPResponse()

    # 1. Read first line
    start_line_bytes, remining_data = _read_until_delimiter(sock, b'', b'\r\n')
    start_line = start_line_bytes.decode('latin-1')
    start_line_parts = start_line.split(' ', 2) # e.g., # e.g., "HTTP/1.1 200 OK"
    if len(start_line_parts) >= 2: # Minimum for a response: HTTP-Version Status-Code
        resp.http_version = start_line_parts[0]
        try:
            resp.status_code = int(start_line_parts[1])
        except ValueError:
            raise HTTPError(f"Received invalid HTTP start line: {start_line}")
        resp.status_phase = start_line_parts[2] if len(start_line_parts) == 3 else ''
    else:
        # Malformed start line
        raise HTTPError(f"Received invalid HTTP start line: {start_line}")

    remining_data = _parse_headers(sock, resp.headers, remining_data)
    final_remaining_buffer = remining_data
    
    # Parse response body for GET/POST response
    if not (request_method == 'HEAD' or resp.status_code in [204, 304]):
        resp.body, final_remaining_buffer = _parse_body(sock, remining_data, resp.headers, is_response=True)
    
    return resp, final_remaining_buffer


def rewrite_client_request_header(req: HTTPRequest):
        # set 'connection: close' since proxy <-> server connection is one-off
    req.headers['connection'] = 'close'
    # delete proxy-connection
    if 'proxy-connection' in req.headers:
        del req.headers['proxy-connection']
    # set via
    req.headers['via'] = f'1.1 {PROXY_ID}'
    # set content-length
    req.headers['content-length'] = str(len(req.body))
    return

def rewrite_response_header(resp: HTTPResponse):
        # set connection: Keep-Alive
    resp.headers['connection'] = 'keep-alive'
    # set via
    resp.headers['via'] = f'1.1 {PROXY_ID}'
    
    # set content-length
    resp.headers['content-length'] = str(len(resp.body))
    return
    

def _parse_headers(sock: socket.socket, headers: Dict[str, str], data_buf: bytes) -> bytes:
    header_data, remaining_data_buffer = _read_until_delimiter(sock, data_buf, b'\r\n\r\n')
    header_lines = header_data.decode('latin-1').split('\r\n')
    if not header_lines:
        raise HTTPError("Fail to decode header and start line.")
    
    # Parse Headers
    for line in header_lines[1:]:
        if not line: # Skip empty lines
            continue
        try:
            key, value = line.split(':', 1) # Split by the first colon only
            key = key.strip()
            if key.lower() in _META_HEADER_FIELDS:
                key = key.lower()
                value = value.lower()
            headers[key] = value
        except ValueError:
            # Malformed header line (e.g., no colon), skip it
            pass
    return remaining_data_buffer


def _parse_body(sock: socket.socket, data_buf: bytes, headers: Dict[str, str], is_response: bool = False) -> Tuple[bytes, bytes]:
    content_length = int(headers.get('content-length', 0))
    transfer_encoding = headers.get('transfer-encoding')
    
    body_data, final_remaining_buffer = b'', data_buf
    if transfer_encoding:
        body_data, final_remaining_buffer = _read_until_close(sock, data_buf)
        
    elif content_length:
        body_data, final_remaining_buffer = _read_until_size(sock, data_buf, content_length)
        
    elif is_response:
        # no transfer_encoding/content_length exist
        # If is a request, then the message body length is zero
        # If is a response, then the message body length is determined by the number
        # of byters received until the server closing the connection
        body_data, final_remaining_buffer = _read_until_close(sock, data_buf)
    
    return body_data, final_remaining_buffer



def tcp_streaming_transfer(recv_socket: socket.socket, dest_socket: socket.socket):
    """
        Copy data from recv_socket to dest_socket, until recv_socket close
    """
    while True:
        data = recv_socket.recv(_BUF_SIZE)
        if not data:
            break
        dest_socket.sendall(data)
    return

def send_err_response(sock: socket.socket, err: ProxyErrException):
    """
        Send 4xx/5xx error message
    """
    err_response = HTTPResponse()
    err_response.status_code = err.status_code
    err_response.status_phase = err.status_phase
    body = f"{err.err_message}\r\n".encode()
    err_response.headers['content-length'] = str(len(body))
    err_response.headers['Content-Type'] = 'test/plain'
    err_response.body = body
    err_response.send_to(sock)
    return


def send_ok_response(sock: socket.socket):
    # send 200 OK response
    ok_response = HTTPResponse()
    ok_response.status_code = 200
    ok_response.status_phase = 'OK'
    ok_response.send_to(sock)
    return




