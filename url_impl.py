from http_impl import HTTPRequest
from typing import Tuple
from err_response import ProxyErrException


def parse_absolute_addr(request: HTTPRequest) -> Tuple[Tuple[str, int], str]:
    if not request.url.startswith('http://'):
        raise ProxyErrException.bad_request_exception('no host')

    url = request.url.removeprefix('http://')
    url_split = url.split('/', 1)  # remove url argument
    if len(url_split) == 2:
        [host_port_str, path] = url_split
        path = '/' + path
    else:
        host_port_str = url_split[0]
        path = '/'
    
    if host_port_str.count(':') != 0:
        [host, port] = host_port_str.split(':', 1)
    else:
        # using default port
        host, port = host_port_str, 80
    try:
        port = int(port)
    except:
        raise ProxyErrException.bad_request_exception("invalid port")

    return ((host, port), path)



def parse_authority_addr(request: HTTPRequest) -> Tuple[str, int]:
    if request.url.startswith('http://'):
        raise ProxyErrException.bad_request_exception('invalid url / invalid host / invalid port')
    
    if request.url.count(':') != 1:
        # must define port
        raise ProxyErrException.bad_request_exception("no host or invalid port")
    
    [host, port] = request.url.split(':', 1)
    try:
        port = int(port)
    except:
        raise ProxyErrException.bad_request_exception("invalid port")

    if port != 443:
        raise ProxyErrException.bad_request_exception("invalid port")
    return (host, port)