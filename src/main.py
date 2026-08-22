from pathlib import Path

from src.core.application import Application
from src.health.publish_policy import apply_publish_policy
from src.postprocess.m3u_deduper import dedupe_outputs


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = Application(root).run()

    if result == 0:
        apply_publish_policy(root)
        dedupe_outputs(root)

    return result


if __name__ == "__main__":
    raise SystemExit(main())
