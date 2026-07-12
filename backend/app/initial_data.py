import logging

from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine, init_db
from app.models import User
from app.seed_data import seed_demo_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init() -> None:
    with Session(engine) as session:
        init_db(session)
        if settings.ENVIRONMENT == "local":
            admin = session.exec(
                select(User).where(User.email == settings.FIRST_SUPERUSER)
            ).first()
            assert admin is not None, "First superuser should exist after init_db()"
            seed_demo_data(session, admin)


def main() -> None:
    logger.info("Creating initial data")
    init()
    logger.info("Initial data created")


if __name__ == "__main__":
    main()
