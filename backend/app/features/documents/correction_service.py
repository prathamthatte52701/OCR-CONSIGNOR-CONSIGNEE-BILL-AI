"""Shared field-correction logic used by both the user-facing and admin document routers -
same field validation, same true-overwrite behavior, same audit trail."""

import re
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.audit_log import log_action
from app.features.ocr.extraction import (
    LINE_ITEM_FIELD_CLASSES,
    PART1_FIELD_CLASSES,
    PART2_SUMMARY_FIELD_CLASSES,
    FieldClass,
)

EDITABLE_TOP_LEVEL_FIELDS = (
    set(PART1_FIELD_CLASSES)
    | {"consigneePincode", "consignorPincode"}
    | set(PART2_SUMMARY_FIELD_CLASSES)
)
_FIELD_CLASS_LOOKUP: dict[str, FieldClass] = {**PART1_FIELD_CLASSES, **PART2_SUMMARY_FIELD_CLASSES}
_LINE_ITEM_FIELD_RE = re.compile(r"^lineItems\.(\d+)\.(\w+)$")


async def apply_field_correction(
    db: AsyncIOMotorDatabase,
    doc: dict[str, Any],
    field: str,
    value: str | None,
    *,
    actor_user_id: ObjectId,
    by_admin: bool,
) -> None:
    """Raises HTTPException(400) on an unknown field or out-of-range line item index."""
    if doc.get("uploadStatus") not in ("processed", "failed"):
        raise HTTPException(
            status_code=409, detail="Cannot edit while the document is still processing."
        )

    now = datetime.now(UTC)
    line_item_match = _LINE_ITEM_FIELD_RE.match(field)

    if line_item_match:
        index = int(line_item_match.group(1))
        subfield = line_item_match.group(2)
        if subfield not in LINE_ITEM_FIELD_CLASSES:
            raise HTTPException(status_code=400, detail=f"Unknown line item field: {subfield}")
        line_items = doc.get("lineItems", [])
        if index < 0 or index >= len(line_items):
            raise HTTPException(status_code=400, detail="Line item index out of range.")

        old_value = line_items[index].get(subfield)
        set_ops: dict[str, Any] = {
            f"lineItems.{index}.{subfield}": value,
            f"lineItems.{index}.{subfield}Confidence": 100,
        }
        if LINE_ITEM_FIELD_CLASSES[subfield] != FieldClass.FREE_TEXT_LIGHT:
            set_ops[f"lineItems.{index}.{subfield}AutoCorrected"] = False
    else:
        if field not in EDITABLE_TOP_LEVEL_FIELDS:
            raise HTTPException(status_code=400, detail=f"Field '{field}' is not editable.")
        old_value = doc.get(field)
        set_ops = {field: value, f"{field}Confidence": 100}
        field_class = _FIELD_CLASS_LOOKUP.get(field)
        if field.endswith("Pincode") or (field_class and field_class != FieldClass.FREE_TEXT_LIGHT):
            set_ops[f"{field}AutoCorrected"] = False

    set_ops["edited"] = True
    set_ops["updatedAt"] = now
    await db.documents.update_one({"_id": doc["_id"]}, {"$set": set_ops})
    await db.corrections.insert_one(
        {
            "documentId": doc["_id"],
            "userId": actor_user_id,
            "fieldKey": field,
            "oldValue": old_value,
            "newValue": value,
            "byAdmin": by_admin,
            "correctedAt": now,
        }
    )
    await log_action(
        actor_user_id,
        "document_corrected",
        {"documentId": str(doc["_id"]), "field": field, "byAdmin": by_admin},
    )
