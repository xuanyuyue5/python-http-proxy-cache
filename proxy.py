"""Multithreaded HTTP proxy with CONNECT tunneling and LRU response caching."""
import sys
import socket
import threading
from typing import Tuple
from http_impl import HTTPRequest, HTTPResponse, parse_http_request, parse_http_response
from http_impl import HTTPError, ConnectionCloseError
from http_impl import rewrite_client_request_header, rewrite_response_header
from http_impl import send_err_response, send_ok_response
from http_impl import tcp_streaming_transfer

from cache_impl import LRUCache
from url_impl import parse_absolute_addr, parse_authority_addr
from err_response import ProxyErrException
import traceback
import datetime
from log_impl import logging_setup, proxy_log
logger = logging_setup(logger_name=__name__)

SOCKET_TIMEOUT: int = 10


class ProxyServer:
    def __init__(self, port: int, max_object_size: int, max_cache_size: int):
        self.port: int = port
        self.lru_cache: LRUCache = LRUCache(max_object_size, max_cache_size)
        self.server_socket: socket.socket = None # type: ignore

    def handle_client(self, client_socket: socket.socket, client_address, conn_id: int):
        # Create client handler to handle the connection
        try:
            handler = ClientHandler(client_socket, client_address, self.lru_cache, conn_id)
            handler.start()
        except Exception as e:
            logger.error(f"{e}")
            traceback.print_exc()
        finally:
            client_socket.close()

    def start(self):
        """Starts the proxy server and listens for incoming connection."""
        global SOCKET_TIMEOUT
        
        # Open server socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.server_socket.bind(('', self.port))
            self.server_socket.listen(100)
            logger.debug(f"Proxy server listening on port {self.port}...")
            
            # Connection index for debug
            conn_id = 0
            
            while True:
                client_socket, client_address = self.server_socket.accept()
                logger.debug(f"Proxy server accept a new client connection. id={conn_id}")
                # Start a new thread to handle each client connection
                client_socket.settimeout(SOCKET_TIMEOUT)
                client_handler = threading.Thread(
                    target=self.handle_client, args=(client_socket, client_address, conn_id))
                client_handler.start()
                conn_id += 1
                
        except OSError as err:
            if self.server_socket:
                self.server_socket.close()
            logger.error(f"Error starting server: {err}")
            # Exit if the port is already in use or other network issues
            exit(1)
        except KeyboardInterrupt:
            logger.debug("\nShutting down proxy server...")
        finally:
            if self.server_socket:
                self.server_socket.close()
            logger.debug("Proxy server shut down.")


class ClientHandler:
    """
        ClientHandler handle http request from a persistence TCP connection
    """
    def __init__(self, client_socket: socket.socket, client_address, lru_cache:LRUCache, connection_id: int):
        self.client_socket: socket.socket = client_socket
        self.client_address = client_address
        self.lru_cache = lru_cache
        self.connection_id: int = connection_id

    def start(self):
        # store data buffer
        remaining_buffer = b''
        try:
            client_request:HTTPRequest
            while True:
                # Read client request
                client_request, remaining_buffer = parse_http_request(self.client_socket, remaining_buffer)
                client_request.date_time_formated = datetime.datetime.now().strftime("%d/%b/%Y:%H:%M:%S %z")
                logger.debug("Read request from client success")
                
                if client_request.method != 'CONNECT':
                    # Parse origin server address
                    parsed_url = parse_absolute_addr(client_request)
                    [remote_addr, request_path] = parsed_url
                    
                    # Parse connection setting
                    connection_header = client_request.headers.get('connection')
                    if not connection_header:
                        connection_header = client_request.headers.get('proxy-connection')
                    
                    # Read send request to remote server, and get response from remote server
                    rewrite_client_request_header(client_request)
                    client_request.url = request_path
                    # set host
                    if 'Host' not in client_request.headers:
                        client_request.headers['Host'] = remote_addr[0]
                    
                    # Try to load from cache
                    # If not in cache, load from remote server and cache response
                    remote_response = None
                    
                    # bypass proxy if not a GET request
                    cache_status = '-'
                    if client_request.method == 'GET':
                        remote_response = self.lru_cache.get_cache(host=remote_addr[0], port=remote_addr[1], req_path=request_path)
                        cache_status = 'H' if remote_response else 'M'
                        
                    if remote_response:
                        logger.debug('Cache hit, sending cached response')
                        cache_hit = True
                    else:
                        cache_hit = False
                        logger.debug('Cache miss, loading response from remote server')
                        remote_response = self._get_remote_response(
                            client_request, remote_addr)

                    logger.debug(f'Remote response size: {len(remote_response.body)}')
                    
                    # Send server response to client
                    rewrite_response_header(remote_response)
                    remote_response.send_to(self.client_socket)
                    logger.debug("Send response to client success")
                    
                    if  (not cache_hit) and \
                        (client_request.method == 'GET') and \
                        (remote_response.status_code // 100) == 2 and \
                        self.lru_cache.try_to_cache(host=remote_addr[0], port=remote_addr[1], req_path=request_path, resp=remote_response):
                        logger.debug(f"Cache response from remote server, size={len(remote_response.body)}")
                        logger.debug(f"Current lru cache size: {self.lru_cache.current_size}")
                    
                    # print a log entry
                    proxy_log(client_ip=self.client_address[0], client_port=self.client_address[1], 
                              cache_status=cache_status, date_time=client_request.date_time_formated, 
                              request_line=client_request.first_line, 
                              status_code=remote_response.status_code, 
                              bytes_returned=len(remote_response.body)
                    )
                    
                    # close connection if Connection / Proxy-Connection : close
                    if connection_header and 'close' in connection_header:
                        break
                else:
                    # Connect
                    self._connect_command(client_request)
                    break
                    
        except ConnectionCloseError:
            # client close the connection
            traceback.print_exc()
            pass
        
        except ProxyErrException as e:
            
            send_err_response(self.client_socket, e)
            proxy_log(client_ip=self.client_address[0], client_port=self.client_address[1], 
                        cache_status='-', date_time=client_request.date_time_formated,  # type: ignore
                        request_line=client_request.first_line, # type: ignore
                        status_code=e.status_code, # type: ignore
                        bytes_returned=len(f"{e.err_message}\r\n".encode()) # type: ignore
            )
        except Exception as e:
            traceback.print_exc()
        finally:            
            self.client_socket.close()
            logger.debug(f"Client connection close. Connection id={self.connection_id}")
        return

    def _connect_command(self, client_request: HTTPRequest) -> None:
        global SOCKET_TIMEOUT
        addr = parse_authority_addr(client_request)
        
        # connect to server
        remote_server_socket = socket.create_connection(addr) # type: ignore
        remote_server_socket.settimeout(SOCKET_TIMEOUT)
        
        send_ok_response(self.client_socket)
        
        # print a log entry
        proxy_log(client_ip=self.client_address[0], client_port=self.client_address[1], 
                    cache_status='-', date_time=client_request.date_time_formated, 
                    request_line=client_request.first_line, 
                    status_code=200,bytes_returned=0)
        
        # a thread receive data from client and send to server
        send_thread = threading.Thread(target=tcp_streaming_transfer, args=(self.client_socket, remote_server_socket))
        
        # a thread receive data from server and send to client
        recv_thread = threading.Thread(target=tcp_streaming_transfer, args=(remote_server_socket, self.client_socket))
        send_thread.start()
        recv_thread.start()
        
        # wait 
        send_thread.join()
        recv_thread.join()
        
        remote_server_socket.close()
        return




    def _get_remote_response(self, request: HTTPRequest, addr: Tuple[str, int]) -> HTTPResponse:
        logger.debug(f"Connect to remote server: {addr}")
        resp = None
        try:
            remote_server_socket = socket.create_connection(addr)
            remote_server_socket.settimeout(SOCKET_TIMEOUT)
        
            request.send_to(remote_server_socket)
            logger.debug(f"Send request to remote server completely")
            
            resp, _ = parse_http_response(remote_server_socket, request_method=request.method)
            logger.debug(f"Read response from remote server completely")
            # print(resp.body)
            # Close server connection
            remote_server_socket.close()
            return resp
        
        except socket.timeout:
            raise ProxyErrException.gateway_timeout_exception("timed out")
        except socket.error as e:
            if "connection refused" in str(e).lower():
                raise ProxyErrException.bad_gateway_exception("connection refused")
            elif "unresolved" in str(e).lower() or "name or service not known" in str(e).lower(): # Common DNS resolution errors
                raise ProxyErrException.bad_gateway_exception("could not resolve")
            elif "closed unexpectedly" in str(e).lower() or "reset by peer" in str(e).lower(): # Common unexpected close errors
                raise ProxyErrException.bad_gateway_exception("closed unexpectedly")
            else:
                # Catch-all for other socket errors
                raise ProxyErrException.bad_gateway_exception(f"An unexpected error occurred: {e}")
        except Exception as e:
            raise ProxyErrException.bad_gateway_exception(f"An unexpected error occurred: {e}")

        return resp # type: ignore


def main():
    global SOCKET_TIMEOUT
    if len(sys.argv) != 5:
        print("Usage: python proxy.py <port> <timeout> <max_object_size> <max_cache_size>")
        print("Example: python proxy.py 8080 300 5242880 10485760")
        sys.exit(1)

    try:
        port = int(sys.argv[1])
        timeout = int(sys.argv[2])
        max_object_size = int(sys.argv[3])  # In bytes
        max_cache_size = int(sys.argv[4])   # In bytes
    except ValueError:
        print("Error: All arguments must be integers.")
        sys.exit(1)

    SOCKET_TIMEOUT = timeout
    server = ProxyServer(port, max_object_size, max_cache_size)
    server.start()


if __name__ == '__main__':
    main()

