import logging
import time

from listen_dragon.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s component=worker %(message)s",
)
logger = logging.getLogger(__name__)


def run() -> None:
    settings = get_settings()
    logger.info(
        "worker_started poll_seconds=%s concurrency=%s",
        settings.worker_poll_seconds,
        settings.worker_concurrency,
    )
    while True:
        # T08-T13 将在此处接入 SQLite 可恢复任务领取和媒体流水线。
        time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    run()
