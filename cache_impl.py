from http_impl import HTTPResponse
from typing import List, Dict
import threading
from log_impl import logging_setup
logger = logging_setup(logger_name=__name__)


class LRUCache:
    """
        LRUCache implements caching of resources
    """
    def __init__(self, max_object_size: int, max_cache_size: int):
        self.max_object_size: int = max_object_size
        self.max_cache_size: int = max_cache_size
        self.lru_list: List[str] = []
        self.lru_hash: Dict[str, HTTPResponse] = {}
        self.lock: threading.Lock = threading.Lock()
        self.current_size: int = 0
        

    def try_to_cache(self, host:str, port:int, req_path:str, resp: HTTPResponse) -> bool:
        path = f"{host.lower()}:{port}:{req_path}"
        if len(resp.body) > self.max_object_size:
            logger.debug(f'Cache response fail, response size > max_object_size, {len(resp.body)} > {self.max_object_size}')
            return False
        
        with self.lock:
            if path in self.lru_hash:
                # Replace an existing cached response.
                old_resp = self.lru_hash[path]
                self.current_size -= len(old_resp.body)
                self.lru_list.remove(path)
                del self.lru_hash[path]
            
            # update response object
            self.lru_hash[path] = resp
            self.lru_list.append(path)
            self.current_size += len(resp.body)
        
            # pop item until current size < max size
            while self.current_size > self.max_cache_size:
                path_to_remove = self.lru_list[0]
                self.lru_list.pop(0)
                old_resp = self.lru_hash[path_to_remove]
                self.current_size -= len(old_resp.body)
                del self.lru_hash[path_to_remove]
                logger.debug(f'Remove response from LRU cache, key={path_to_remove}')
                
        logger.debug(f'Cache response success, key: {path}')
        return True


    def get_cache(self, host:str, port:int, req_path:str) -> HTTPResponse | None:
        path = f"{host.lower()}:{port}:{req_path}"
        with self.lock:
            if path not in self.lru_hash:
                return None
            # update LRU
            old_resp = self.lru_hash[path]
            self.lru_list.remove(path)
            self.lru_list.append(path)
            return old_resp
        return
