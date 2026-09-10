import logging
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.consent import ConsentRecord
from app.models.medication_event import MedicationEvent
from app.models.medication_schedule import MedicationSchedule
from app.models.prescribed_medication import PrescribedMedication
from app.models.prescription import Prescription
from app.models.adherence_report import AdherenceReport
from app.models.reminder import Reminder
from app.models.follow_up_task import FollowUpTask
from app.models.patient import Patient
from app.models.user import User

logger = logging.getLogger(__name__)

class PatientService:
    @staticmethod
    async def delete_patient_and_history(session: AsyncSession, patient_id: int):
        """
        Secure, deterministic erasure of a patient's entire clinical history.
        This manually cascades deletes from the bottom up to avoid relying on
        undocumented database-level cascade evaluation orders which could otherwise
        violate the HIST-1 RESTRICT constraint on schedule_id.

        This also handles the compliance requirement to retain consent records
        by detaching them rather than deleting them.
        Finally, it deletes the User identity row, effectively revoking all access.
        """
        # Get user ID before we delete the patient
        patient = await session.get(Patient, patient_id)
        if not patient:
            return
        user_id = patient.user_id

        # 1. Detach consent records for audit retention
        await session.execute(
            update(ConsentRecord)
            .where(ConsentRecord.patient_id == patient_id)
            .values(patient_id=None)
        )

        # 2. Delete medication_events (the bottom of the dependency tree)
        await session.execute(
            delete(MedicationEvent).where(MedicationEvent.patient_id == patient_id)
        )

        # 3. Delete medication_schedules (now safe because events are gone)
        await session.execute(
            delete(MedicationSchedule).where(MedicationSchedule.patient_id == patient_id)
        )

        # 4. Delete prescribed_medications
        await session.execute(
            delete(PrescribedMedication).where(PrescribedMedication.patient_id == patient_id)
        )

        # 5. Delete prescriptions
        await session.execute(
            delete(Prescription).where(Prescription.patient_id == patient_id)
        )

        # 6. Delete other patient-scoped models
        await session.execute(
            delete(AdherenceReport).where(AdherenceReport.patient_id == patient_id)
        )
        await session.execute(
            delete(Reminder).where(Reminder.patient_id == patient_id)
        )
        await session.execute(
            delete(FollowUpTask).where(FollowUpTask.patient_id == patient_id)
        )

        # 7. Delete Patient profile
        await session.delete(patient)
        
        # 8. Delete User identity (which implicitly revokes tokens as the user no longer exists)
        user = await session.get(User, user_id)
        if user:
            await session.delete(user)
        
        await session.commit()

patient_service = PatientService()
