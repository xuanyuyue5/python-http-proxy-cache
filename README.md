# Python HTTP Proxy Cache

A small multithreaded HTTP proxy implemented with Python sockets. It supports ordinary HTTP forwarding, HTTPS tunneling through the `CONNECT` method, access logging, and an in-memory LRU cache for cacheable `GET` responses.

This repository is a cleaned portfolio version of the project. It intentionally excludes course report files, local logs, browser cache data, and any generated artifacts.

## Features

- TCP server that accepts multiple clients with one worker thread per connection
- HTTP request and response parsing from raw socket streams
- Header rewriting for proxy-to-origin forwarding
- `CONNECT host:443` tunneling for HTTPS traffic
- Size-bounded LRU cache for successful `GET` responses
- Access-log output with cache hit/miss status
- Basic 400, 502, and 504 error handling

## Repository Layout

```text
python-http-proxy-cache/
|-- proxy.py             # server entry point and per-client handler
|-- http_impl.py         # HTTP request/response parsing and serialization
|-- cache_impl.py        # thread-safe LRU response cache
|-- url_impl.py          # absolute-form and authority-form URL parsing
|-- err_response.py      # proxy error types
|-- log_impl.py          # access logging helpers
|-- tests/
|   `-- test_cache.py
|-- requirements.txt
`-- .gitignore
```

## Requirements

The proxy uses only the Python standard library at runtime. Python 3.10 or newer is recommended.

## Run

```bash
python proxy.py 8080 30 1048576 10485760
```

Arguments:

```text
python proxy.py <port> <timeout_seconds> <max_object_size_bytes> <max_cache_size_bytes>
```

Example values above start the proxy on port `8080`, use a 30-second socket timeout, cache individual objects up to 1 MB, and limit the total cache to 10 MB.

## Try It Locally

In another terminal, send a request through the proxy:

```bash
curl -x http://127.0.0.1:8080 http://example.com/
```

Run the same command twice; the second request should be served from cache if the response fits within the configured object and cache limits.

For HTTPS tunneling:

```bash
curl -x http://127.0.0.1:8080 https://example.com/
```

## Tests

```bash
python -m unittest discover -s tests
```

The included tests cover the LRU cache behavior. Network integration tests are intentionally left manual because they depend on local ports and external hosts.

## Limitations

This is an educational proxy, not a production VPN or privacy tool. It does not implement TLS interception, authentication, persistent upstream connections, HTTP/2, or full RFC-complete cache semantics.
