import os
import subprocess
import sys


def main() -> None:
    subprocess.run([sys.executable, "-m", "scripts.migrate"], check=True)
    port = os.environ.get("PORT", "8000")
    os.execvp(
        "uvicorn",
        ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", port],
    )


if __name__ == "__main__":
    main()
