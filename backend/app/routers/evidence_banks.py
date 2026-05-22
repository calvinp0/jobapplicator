from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import EvidenceBank
from ..schemas import EvidenceBankCreate, EvidenceBankRead

router = APIRouter(prefix="/evidence-banks", tags=["evidence-banks"])


@router.post("", response_model=EvidenceBankRead, status_code=status.HTTP_201_CREATED)
def create_evidence_bank(payload: EvidenceBankCreate, db: Session = Depends(get_db)) -> EvidenceBank:
    bank = EvidenceBank(**payload.model_dump())
    db.add(bank)
    db.commit()
    db.refresh(bank)
    return bank


@router.get("", response_model=list[EvidenceBankRead])
def list_evidence_banks(db: Session = Depends(get_db)) -> list[EvidenceBank]:
    return list(db.query(EvidenceBank).order_by(EvidenceBank.created_at.desc()).all())


@router.get("/{evidence_bank_id}", response_model=EvidenceBankRead)
def get_evidence_bank(evidence_bank_id: str, db: Session = Depends(get_db)) -> EvidenceBank:
    bank = db.get(EvidenceBank, evidence_bank_id)
    if bank is None:
        raise HTTPException(status_code=404, detail="evidence bank not found")
    return bank
