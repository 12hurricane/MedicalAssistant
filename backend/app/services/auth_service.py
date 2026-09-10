from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from app.schemas.auth import AdminUserCreate, UserRegister, UserRole
# Adjust these imports according to the actual model structure
from app.models.user import User
from app.models.patient import Patient
from app.core.security import get_password_hash, verify_password

class AuthService:
    @staticmethod
    async def register_user(db: AsyncSession, user_data: UserRegister) -> User:
        """
        Public self-service registration. Creates a PATIENT, unconditionally.

        The role is a literal here, not a value read off the request. ``UserRegister``
        has no ``role`` field to read, and this is the second half of that guarantee:
        even if the schema regained one, this call site would ignore it. Anything that
        needs to create a CLINICIAN or an ADMIN goes through
        :meth:`create_privileged_user`, which requires an authenticated ADMIN.
        """
        return await AuthService._create_user(
            db,
            name=user_data.name,
            email=user_data.email,
            password=user_data.password,
            phone=user_data.phone,
            role=UserRole.PATIENT.value,
        )

    @staticmethod
    async def create_privileged_user(db: AsyncSession, user_data: AdminUserCreate) -> User:
        """
        Create a CLINICIAN or an ADMIN. Authorization is the caller's job.

        The set of roles reachable here is fixed by ``AdminUserCreate.role``, whose type
        is :class:`PrivilegedRole` — so a retired value like DOCTOR or CAREGIVER is a
        422 from request validation and never arrives at this method at all.

        This service does not check who is asking — the ADMIN requirement is enforced
        by ``require_role("ADMIN")`` on the route, which is where FastAPI can express
        it as a dependency and where the OpenAPI schema records it. Duplicating the
        check here would give two places to keep in agreement and no extra safety.
        """
        return await AuthService._create_user(
            db,
            name=user_data.name,
            email=user_data.email,
            password=user_data.password,
            phone=user_data.phone,
            role=user_data.role.value,
        )

    @staticmethod
    async def _create_user(
        db: AsyncSession,
        *,
        name: str,
        email: str,
        password: str,
        phone: str | None,
        role: str,
    ) -> User:
        """
        Create the user and, for patients, their patient profile in ONE transaction.

        Atomicity here is a domain invariant, not a tidiness preference. This used
        to commit twice — the user first, the profile second — so any interruption
        between the two commits (crash, dropped connection, worker restart, or the
        profile insert simply failing) left a PATIENT user row with no patients row.

        That account then looks functional and is not: login only reads ``users``,
        so the credentials work and a token is issued, but every patient-scoped
        endpoint resolves the profile with
        ``select(Patient).where(Patient.user_id == ...)`` and gets None. Filing a
        prescription returns "User is not a patient", listing returns [], and there
        is nothing for schedules, reminders or adherence to hang off. Nothing in the
        system detects or repairs it, and the user has no way to re-register because
        the email is taken.

        The profile is attached through the ``User.patient`` relationship rather than
        inserted with an explicit ``user_id``, so SQLAlchemy orders the two INSERTs
        and fills the foreign key inside a single flush. There is no longer a point
        in time at which one row exists without the other.

        Shared by both creation paths on purpose. A second hand-written INSERT for
        privileged users would be a second chance to reintroduce the orphaned-profile
        bug, and ``role`` is a keyword-only argument so neither caller can pass one
        positionally by accident.
        """
        result = await db.execute(select(User).filter(User.email == email))
        if result.scalars().first():
            raise HTTPException(status_code=400, detail="Email already registered")

        db_user = User(
            name=name,
            email=email,
            phone=phone,
            hashed_password=get_password_hash(password),
            role=role,
        )

        # PATIENT is the only role with a profile table today; CLINICIAN and ADMIN have
        # none, so there is deliberately nothing to create for them.
        if db_user.role == UserRole.PATIENT.value:
            db_user.patient = Patient()

        db.add(db_user)
        try:
            # The single commit. No refresh follows it: the session is configured
            # expire_on_commit=False, and id / created_at / is_active are all filled
            # by the flush inside this commit, so a re-SELECT would add a round trip
            # and tell us nothing new.
            await db.commit()
        except IntegrityError:
            # The check above is check-then-act: two concurrent registrations of the
            # same address both pass it, and the unique index on users.email then
            # rejects the loser. Without this the race surfaces as a 500 rather than
            # the same 400 a sequential duplicate gets.
            await db.rollback()
            raise HTTPException(status_code=400, detail="Email already registered")

        return db_user

    @staticmethod
    async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
        result = await db.execute(select(User).filter(User.email == email))
        user = result.scalars().first()
        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: int) -> User:
        result = await db.execute(select(User).filter(User.id == user_id))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
        result = await db.execute(select(User).filter(User.email == email))
        return result.scalars().first()

auth_service = AuthService()
