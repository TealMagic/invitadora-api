"""Ejecutar migraciones: python -m scripts.migrate"""

from alembic.config import Config
from alembic import command


def main() -> None:
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    print("Migraciones aplicadas.")


if __name__ == "__main__":
    main()
