from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from typing import Any, List, Optional
from app.schemas.medication import MedicationCreate, MedicationUpdate, MedicationResponse
from app.models.medication import Medication
from app.dependencies import get_db, get_current_user
from app.models.user import User

router = APIRouter()


async def _find_duplicate(
    db: AsyncSession,
    brand_name: str,
    standard_strength: Optional[str],
    dosage_form: Optional[str],
    exclude_id: Optional[int] = None,
) -> Optional[Medication]:
    """
    Look for an existing catalogue entry with the same natural key.

    Done in Python rather than relying solely on the UniqueConstraint because SQL
    treats NULLs as distinct: ('Metformin', NULL, NULL) could otherwise be inserted
    any number of times. `is_(None)` generates IS NULL, which does match.
    """
    stmt = select(Medication).filter(
        Medication.brand_name == brand_name,
        Medication.standard_strength.is_(None)
        if standard_strength is None
        else Medication.standard_strength == standard_strength,
        Medication.dosage_form.is_(None)
        if dosage_form is None
        else Medication.dosage_form == dosage_form,
    )
    if exclude_id is not None:
        stmt = stmt.filter(Medication.id != exclude_id)
    return (await db.execute(stmt)).scalars().first()


@router.get("", response_model=List[MedicationResponse])
async def list_medications(
    search: Optional[str] = Query(
        None,
        min_length=2,
        max_length=100,
        description="Case-insensitive partial match on brand or generic name.",
    ),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    List or search the medication catalogue.

    Search is what prescription verification uses to resolve the free-text
    medicine_name from OCR onto a catalogue entry (prescribed_medications.medication_id).
    """
    stmt = select(Medication)

    if search:
        # ilike renders as a lower()-based LIKE, so it is case-insensitive on both
        # SQLite and Postgres. Wildcards in user input are escaped so a query of
        # "%" does not match everything.
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        stmt = stmt.filter(
            or_(
                Medication.brand_name.ilike(pattern, escape="\\"),
                Medication.generic_name.ilike(pattern, escape="\\"),
            )
        )

    stmt = stmt.order_by(Medication.brand_name).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{id}", response_model=MedicationResponse)
async def get_medication(
    id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get medication by ID."""
    result = await db.execute(select(Medication).filter(Medication.id == id))
    medication = result.scalars().first()
    if not medication:
        raise HTTPException(status_code=404, detail="Medication not found")
    return medication


@router.post("", response_model=MedicationResponse, status_code=status.HTTP_201_CREATED)
async def create_medication(
    med_data: MedicationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Admin only - add to catalog."""
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Not enough privileges")

    existing = await _find_duplicate(
        db, med_data.brand_name, med_data.standard_strength, med_data.dosage_form
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Medication already in catalogue as id {existing.id}",
        )

    medication = Medication(**med_data.model_dump())
    db.add(medication)
    try:
        await db.commit()
    except IntegrityError:
        # Backstop for a concurrent insert that slipped past the check above.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Medication already in catalogue",
        )
    await db.refresh(medication)
    return medication


@router.put("/{id}", response_model=MedicationResponse)
async def update_medication(
    id: int,
    med_data: MedicationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Admin only - update catalog medication."""
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Not enough privileges")

    result = await db.execute(select(Medication).filter(Medication.id == id))
    medication = result.scalars().first()
    if not medication:
        raise HTTPException(status_code=404, detail="Medication not found")

    update_data = med_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(medication, key, value)

    # An edit can collide with another row just as an insert can.
    clash = await _find_duplicate(
        db,
        medication.brand_name,
        medication.standard_strength,
        medication.dosage_form,
        exclude_id=id,
    )
    if clash:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Those details collide with catalogue entry id {clash.id}",
        )

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Those details collide with an existing catalogue entry",
        )
    await db.refresh(medication)
    return medication
