import unittest

from cache_impl import LRUCache
from http_impl import HTTPResponse


def make_response(size):
    response = HTTPResponse()
    response.status_code = 200
    response.status_phase = "OK"
    response.body = b"x" * size
    response.headers["content-length"] = str(size)
    return response


class LRUCacheTests(unittest.TestCase):
    def test_rejects_object_larger_than_limit(self):
        cache = LRUCache(max_object_size=5, max_cache_size=20)
        cached = cache.try_to_cache("example.com", 80, "/large", make_response(6))
        self.assertFalse(cached)
        self.assertIsNone(cache.get_cache("example.com", 80, "/large"))

    def test_eviction_uses_least_recently_used_entry(self):
        cache = LRUCache(max_object_size=10, max_cache_size=15)
        cache.try_to_cache("example.com", 80, "/a", make_response(5))
        cache.try_to_cache("example.com", 80, "/b", make_response(5))
        cache.get_cache("example.com", 80, "/a")
        cache.try_to_cache("example.com", 80, "/c", make_response(6))

        self.assertIsNotNone(cache.get_cache("example.com", 80, "/a"))
        self.assertIsNone(cache.get_cache("example.com", 80, "/b"))
        self.assertIsNotNone(cache.get_cache("example.com", 80, "/c"))


if __name__ == "__main__":
    unittest.main()
