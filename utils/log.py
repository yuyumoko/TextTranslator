import logging
import colorlog
from tenacity import RetryCallState, _utils

__all__ = ["logger", "retry_log"]

logger = logging.getLogger("all")
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(
    colorlog.ColoredFormatter(
        fmt="%(log_color)s%(levelname)-8s%(reset)s%(blue)s%(asctime)s - %(green)s %(message)s",
        datefmt="(%Y-%m-%d %H:%M:%S)",
        reset=True,
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
    )
)
logger.addHandler(console_handler)


def retry_log(retry_state: "RetryCallState"):
    if retry_state.attempt_number > 1:
        fn_name = _utils.get_callback_name(retry_state.fn)
        logger.debug(fn_name + " 重试次数: %s" % retry_state.attempt_number)
