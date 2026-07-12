import logging
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from app.core.security import get_password_hash
from app.leave_models.leave_balance_model import LeaveBalance
from app.leave_models.leave_plan_request_model import LeavePlanDetail, LeavePlanRequest
from app.leave_models.leave_policy_model import Policy
from app.leave_models.leave_request_model import LeaveRequest
from app.leave_models.leave_type_model import LeaveType
from app.leave_models.public_holiday_model import PublicHoliday
from app.leave_models.team_model import Team
from app.models import User, UserCreate

logger = logging.getLogger(__name__)

DEMO_TEAM_NAME = "Demo Engineering Team"
DEMO_PASSWORD = "Demo@12345"

MANAGER_EMAIL = "manager.demo@example.com"
EMPLOYEE1_EMAIL = "employee1.demo@example.com"
EMPLOYEE2_EMAIL = "employee2.demo@example.com"


def _create_local_user(session: Session, *, email: str, full_name: str) -> User:
    """Like crud.create_user, but only adds to the session -- caller commits once."""
    user_create = UserCreate(email=email, password=DEMO_PASSWORD, full_name=full_name)
    db_obj = User.model_validate(
        user_create, update={"hashed_password": get_password_hash(user_create.password)}
    )
    session.add(db_obj)
    return db_obj


def _build_demo_users(session: Session) -> tuple[User, User, User]:
    manager = _create_local_user(session, email=MANAGER_EMAIL, full_name="Morgan Lee")
    employee1 = _create_local_user(
        session, email=EMPLOYEE1_EMAIL, full_name="Alex Chen"
    )
    employee2 = _create_local_user(
        session, email=EMPLOYEE2_EMAIL, full_name="Sam Rivera"
    )
    session.flush()
    return manager, employee1, employee2


def _build_demo_team(
    session: Session, admin: User, manager: User, employee1: User, employee2: User
) -> Team:
    team = Team(
        name=DEMO_TEAM_NAME,
        description="Seeded demo team for QA / feature testing.",
        team_owner_id=manager.id,
        owner_id=admin.id,
    )
    session.add(team)
    session.flush()

    manager.team_id = team.id
    employee1.team_id = team.id
    employee2.team_id = team.id
    session.add_all([manager, employee1, employee2])
    return team


def _build_leave_types(session: Session, admin: User) -> tuple[LeaveType, LeaveType]:
    annual = LeaveType(
        code="annual",
        name="Annual Leave",
        entitlement=18,
        description="Standard yearly paid leave entitlement.",
        is_allow_plan=True,
        is_active=True,
        owner_id=admin.id,
    )
    sick = LeaveType(
        code="sick",
        name="Sick Leave",
        entitlement=10,
        description="Paid sick leave (not eligible for AI leave planning).",
        is_allow_plan=False,
        is_active=True,
        owner_id=admin.id,
    )
    session.add_all([annual, sick])
    session.flush()
    return annual, sick


def _first_thursday(year: int, month: int) -> date:
    d = date(year, month, 1)
    return d + timedelta(days=(3 - d.weekday()) % 7)


def _build_public_holidays(
    session: Session, admin: User, year: int
) -> tuple[list[PublicHoliday], date]:
    bridge_holiday_date = _first_thursday(year, 6)  # first Thursday in June
    bridge_friday = bridge_holiday_date + timedelta(days=1)

    holidays = [
        PublicHoliday(date=f"{year}-01-01", name="New Year's Day", owner_id=admin.id),
        PublicHoliday(date=f"{year}-05-01", name="Labor Day", owner_id=admin.id),
        PublicHoliday(date=f"{year}-09-02", name="National Day", owner_id=admin.id),
        PublicHoliday(date=f"{year}-12-25", name="Christmas Day", owner_id=admin.id),
        PublicHoliday(
            date=bridge_holiday_date.isoformat(),
            name="Founders' Day (Bridge Demo Holiday)",
            owner_id=admin.id,
        ),
    ]
    session.add_all(holidays)
    return holidays, bridge_friday


def _build_default_policies(session: Session, admin: User) -> list[Policy]:
    policies = [
        Policy(
            code="weekday",
            name="Weekday Preference",
            operation="in",
            value="[0,4]",
            score=1,
            description="Prefer leave adjacent to the weekend (Monday or Friday).",
            is_active=True,
            owner_id=admin.id,
        ),
        Policy(
            code="bridge_holiday",
            name="Bridge Holiday Bonus",
            operation="==",
            value="True",
            score=2,
            description="Boost single working days sandwiched between holidays/weekends.",
            is_active=True,
            owner_id=admin.id,
        ),
        Policy(
            code="team_workload",
            name="High Team Workload Penalty",
            operation=">",
            value="50%",
            score=-2,
            description="Discourage days where over half the team is already on leave.",
            is_active=True,
            owner_id=admin.id,
        ),
    ]
    session.add_all(policies)
    return policies


def _build_leave_balances(
    session: Session,
    manager: User,
    employee1: User,
    employee2: User,
    annual: LeaveType,
    sick: LeaveType,
    year: str,
) -> None:
    balances = [
        LeaveBalance(
            year=year, balance=18, leave_type_id=annual.id, owner_id=manager.id
        ),
        LeaveBalance(year=year, balance=10, leave_type_id=sick.id, owner_id=manager.id),
        LeaveBalance(
            year=year,
            balance=18,
            taken_balance=8,
            leave_type_id=annual.id,
            owner_id=employee1.id,
        ),
        LeaveBalance(
            year=year, balance=10, leave_type_id=sick.id, owner_id=employee1.id
        ),
        LeaveBalance(
            year=year, balance=18, leave_type_id=annual.id, owner_id=employee2.id
        ),
        LeaveBalance(
            year=year, balance=10, leave_type_id=sick.id, owner_id=employee2.id
        ),
    ]
    session.add_all(balances)


def _build_leave_requests(
    session: Session, employee1: User, team: Team, annual: LeaveType, manager: User
) -> None:
    today = date.today()
    now = datetime.now()

    draft = LeaveRequest(
        start_date=today + timedelta(days=30),
        end_date=today + timedelta(days=34),
        description="Draft: family trip (not yet submitted).",
        leave_type_id=annual.id,
        owner_id=employee1.id,
        team_id=team.id,
        year=str(today.year),
        amount=5,
        status="draft",
        requested_at=now,
    )
    pending = LeaveRequest(
        start_date=today + timedelta(days=10),
        end_date=today + timedelta(days=12),
        description="Pending: awaiting manager approval.",
        leave_type_id=annual.id,
        owner_id=employee1.id,
        team_id=team.id,
        year=str(today.year),
        amount=3,
        status="pending",
        requested_at=now,
        submitted_at=now,
        approver_id=manager.id,
    )
    approved = LeaveRequest(
        start_date=today - timedelta(days=40),
        end_date=today - timedelta(days=36),
        description="Approved: already taken.",
        leave_type_id=annual.id,
        owner_id=employee1.id,
        team_id=team.id,
        year=str(today.year),
        amount=5,
        status="approved",
        requested_at=now,
        submitted_at=now,
        approver_id=manager.id,
        approval_at=now,
    )
    rejected = LeaveRequest(
        start_date=today + timedelta(days=20),
        end_date=today + timedelta(days=21),
        description="Rejected: conflicted with team workload.",
        leave_type_id=annual.id,
        owner_id=employee1.id,
        team_id=team.id,
        year=str(today.year),
        amount=2,
        status="rejected",
        requested_at=now,
        submitted_at=now,
        approver_id=manager.id,
        approval_at=now,
    )
    session.add_all([draft, pending, approved, rejected])


def _build_leave_plan_requests(
    session: Session,
    employee2: User,
    team: Team,
    annual: LeaveType,
    manager: User,
    bridge_friday: date,
) -> None:
    today = date.today()
    now = datetime.now()

    def details(plan: LeavePlanRequest, *dates: date) -> list[LeavePlanDetail]:
        return [LeavePlanDetail(leave_date=d, leave_plan_id=plan.id) for d in dates]

    draft = LeavePlanRequest(
        description="Draft: possible long weekend.",
        leave_type_id=annual.id,
        owner_id=employee2.id,
        team_id=team.id,
        year=str(today.year),
        amount=2,
        status="draft",
        requested_at=now,
    )
    draft_details = details(
        draft, today + timedelta(days=50), today + timedelta(days=51)
    )

    pending = LeavePlanRequest(
        description="Pending: awaiting manager approval.",
        leave_type_id=annual.id,
        owner_id=employee2.id,
        team_id=team.id,
        year=str(today.year),
        amount=3,
        status="pending",
        requested_at=now,
        submitted_at=now,
        approver_id=manager.id,
    )
    pending_details = details(
        pending,
        today + timedelta(days=5),
        today + timedelta(days=6),
        today + timedelta(days=40),
    )

    approved = LeavePlanRequest(
        description="Approved: includes a bridge-day pick.",
        leave_type_id=annual.id,
        owner_id=employee2.id,
        team_id=team.id,
        year=str(bridge_friday.year),
        amount=4,
        status="approved",
        requested_at=now,
        submitted_at=now,
        approver_id=manager.id,
        approval_at=now,
    )
    approved_details = details(
        approved,
        bridge_friday,
        today + timedelta(days=60),
        today + timedelta(days=61),
        today + timedelta(days=62),
    )

    rejected = LeavePlanRequest(
        description="Rejected: too much overlap with teammates.",
        leave_type_id=annual.id,
        owner_id=employee2.id,
        team_id=team.id,
        year=str(today.year),
        amount=2,
        status="rejected",
        requested_at=now,
        submitted_at=now,
        approver_id=manager.id,
        approval_at=now,
    )
    rejected_details = details(
        rejected, today + timedelta(days=25), today + timedelta(days=70)
    )

    session.add_all(
        [
            draft,
            pending,
            approved,
            rejected,
            *draft_details,
            *pending_details,
            *approved_details,
            *rejected_details,
        ]
    )


def _log_demo_credentials(
    admin_email: str, manager: User, employee1: User, employee2: User
) -> None:
    logger.info("=" * 60)
    logger.info("Demo data seeded -- QA login credentials:")
    logger.info("  Superuser : %s / (see FIRST_SUPERUSER_PASSWORD env)", admin_email)
    logger.info("  Manager   : %s / %s", manager.email, DEMO_PASSWORD)
    logger.info("  Employee1 : %s / %s", employee1.email, DEMO_PASSWORD)
    logger.info("  Employee2 : %s / %s", employee2.email, DEMO_PASSWORD)
    logger.info("=" * 60)


def seed_demo_data(session: Session, admin: User) -> None:
    """Populate the database with a full demo dataset for manual/API testing.

    Idempotent: skips entirely if the demo team already exists, since the
    prestart service re-runs this on every `docker compose up` against a
    volume that may already be seeded.
    """

    existing = session.exec(select(Team).where(Team.name == DEMO_TEAM_NAME)).first()
    if existing:
        logger.info(
            "Demo data already present (team '%s' found) -- skipping seed.",
            DEMO_TEAM_NAME,
        )
        return

    year = datetime.now().year

    manager, employee1, employee2 = _build_demo_users(session)
    team = _build_demo_team(session, admin, manager, employee1, employee2)
    annual, sick = _build_leave_types(session, admin)
    _, bridge_friday = _build_public_holidays(session, admin, year)
    _build_default_policies(session, admin)
    _build_leave_balances(
        session, manager, employee1, employee2, annual, sick, str(year)
    )
    session.flush()
    _build_leave_requests(session, employee1, team, annual, manager)
    _build_leave_plan_requests(session, employee2, team, annual, manager, bridge_friday)

    session.commit()

    _log_demo_credentials(admin.email, manager, employee1, employee2)
