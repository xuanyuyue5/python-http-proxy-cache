class ProxyErrException(Exception):
    """
        ProxyErrException defines the error message that needs to be returned when an error occurs in the proxy.
    """
    def __init__(self, status_code: int, status_phase: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.status_phase = status_phase
        self.err_message = message

    @classmethod
    def bad_request_exception(cls, msg:str) -> 'ProxyErrException':
        return ProxyErrException(400, 'Bad Request', msg)

    @classmethod
    def bad_gateway_exception(cls, msg:str) -> 'ProxyErrException':
        return ProxyErrException(502, 'Bad Gateway', msg)

    @classmethod
    def gateway_timeout_exception(cls, msg:str) -> 'ProxyErrException':
        return ProxyErrException(504, 'Gateway Timeout', msg)