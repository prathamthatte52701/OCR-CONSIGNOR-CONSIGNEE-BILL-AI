"""Shared field-correction logic used by both the user-facing and admin document routers -
same field validation, same true-overwrite behavior, same audit trail."""

import copy
import re
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.audit_log import log_action
from app.features.documents.file_purge import document_snapshot
from app.features.documents.review_warnings import review_warnings
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


def _has_review_warnings_after(doc: dict[str, Any], set_ops: dict[str, Any]) -> bool:
    """review_warnings() on the document as it will be once set_ops is applied."""
    after = copy.deepcopy(doc)
    for key, new_value in set_ops.items():
        match = _LINE_ITEM_FIELD_RE.match(key)
        if match:
            after["lineItems"][int(match.group(1))][match.group(2)] = new_value
        else:
            after[key] = new_value
    return bool(review_warnings(after))


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

    # Trim; an empty value is refused for every field except irnNo, where it clears the field.
    text = value.strip() if value is not None else ""
    if text:
        value = text
    elif field == "irnNo":
        value = None
    else:
        raise HTTPException(status_code=400, detail="Please enter a value before saving.")

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

    set_ops["hasReviewWarnings"] = _has_review_warnings_after(doc, set_ops)
    set_ops["edited"] = True
    set_ops["updatedAt"] = now
    # Conditional on the document still being finished: a reprocess can start between the
    # read above and this write. Nothing matched -> no write, no corrections row, no audit entry.
    result = await db.documents.update_one(
        {"_id": doc["_id"], "uploadStatus": {"$in": ["processed", "failed"]}}, {"$set": set_ops}
    )
    if result.matched_count == 0:
        raise HTTPException(
            status_code=409, detail="Cannot edit while the document is still processing."
        )
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
    context: dict[str, Any] = {"documentId": str(doc["_id"]), "field": field, "byAdmin": by_admin}
    if by_admin:
        context.update(document_snapshot(doc))
    await log_action(actor_user_id, "document_corrected", context)
