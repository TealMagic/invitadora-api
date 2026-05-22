import subprocess
import sys

from worker.run_worker import main as worker_main


def main() -> None:
    subprocess.run([sys.executable, "-m", "scripts.migrate"], check=True)
    worker_main()


if __name__ == "__main__":
    main()
