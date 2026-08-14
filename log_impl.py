import logging

def logging_setup(logger_name:str):
    """
        setup debug logger
    """
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    return logging.getLogger(logger_name)
    

def proxy_log(client_ip:str, client_port:int, cache_status:str, date_time: str, request_line:str, status_code:int, bytes_returned:int):
    """
        Print one access-log entry for a proxied request
    """
    log_str = f'{client_ip} {client_port} {cache_status} [{date_time}] "{request_line}" {status_code} {bytes_returned}'
    print(log_str)
    return
