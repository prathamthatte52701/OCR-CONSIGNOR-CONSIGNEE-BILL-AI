"""Document model: one record per Part1+Part2 file pair. Field/confidence/autoCorrected
triplets mirror app.features.ocr.extraction's field classification."""

from datetime import datetime
from typing import Literal

from app.core.base_model import CamelModel, MongoBaseModel
from app.core.object_id import PyObjectId


class LineItem(CamelModel):
    """No independent lifecycle (no per-row correction/delete route), so this is a plain
    embedded value, not a MongoBaseModel with its own id/timestamps."""

    sr_no: str | None = None
    sr_no_confidence: int = 0
    sr_no_auto_corrected: bool = False
    description: str | None = None
    description_confidence: int = 0
    hsn_sac: str | None = None
    hsn_sac_confidence: int = 0
    hsn_sac_auto_corrected: bool = False
    basic: str | None = None
    basic_confidence: int = 0
    basic_auto_corrected: bool = False
    quantity: str | None = None
    quantity_confidence: int = 0
    quantity_auto_corrected: bool = False
    amount: str | None = None
    amount_confidence: int = 0
    amount_auto_corrected: bool = False


class Document(MongoBaseModel):
    user_id: PyObjectId
    is_deleted: bool = False
    deleted_at: datetime | None = None

    upload_status: Literal["uploaded", "processing", "processed", "failed"] = "uploaded"
    processing_error: str | None = None
    processed_at: datetime | None = None
    reprocessed_at: datetime | None = None
    edited: bool = False

    part1_gridfs_file_id: PyObjectId | None = None
    part1_original_filename: str | None = None
    part1_mime_type: str | None = None
    part1_size: int | None = None
    part1_file_purged: bool = False
    part1_file_purged_at: datetime | None = None

    part2_gridfs_file_id: PyObjectId | None = None
    part2_original_filename: str | None = None
    part2_mime_type: str | None = None
    part2_size: int | None = None
    part2_file_purged: bool = False
    part2_file_purged_at: datetime | None = None

    multi_page: bool = False
    has_low_confidence_fields: bool = False

    # Part 1: consignee block
    consignee_code: str | None = None
    consignee_code_confidence: int = 0
    consignee_code_auto_corrected: bool = False
    consignee: str | None = None
    consignee_confidence: int = 0
    consignee_auto_corrected: bool = False
    consignee_address: str | None = None
    consignee_address_confidence: int = 0
    consignee_pincode: str | None = None
    consignee_pincode_confidence: int = 0
    consignee_pincode_auto_corrected: bool = False
    consignee_state_code: str | None = None
    consignee_state_code_confidence: int = 0
    consignee_state_code_auto_corrected: bool = False
    consignee_state_name: str | None = None
    consignee_state_name_confidence: int = 0
    consignee_gstin: str | None = None
    consignee_gstin_confidence: int = 0
    consignee_gstin_auto_corrected: bool = False
    consignee_pan: str | None = None
    consignee_pan_confidence: int = 0
    consignee_pan_auto_corrected: bool = False
    invoice_no: str | None = None
    invoice_no_confidence: int = 0
    invoice_no_auto_corrected: bool = False
    fi_doc: str | None = None
    fi_doc_confidence: int = 0
    fi_doc_auto_corrected: bool = False
    challan_date: str | None = None
    challan_date_confidence: int = 0
    challan_date_auto_corrected: bool = False
    reason: str | None = None
    reason_confidence: int = 0

    # Part 1: consignor block
    consignor_name: str | None = None
    consignor_name_confidence: int = 0
    consignor_name_auto_corrected: bool = False
    consignor_address: str | None = None
    consignor_address_confidence: int = 0
    consignor_pincode: str | None = None
    consignor_pincode_confidence: int = 0
    consignor_pincode_auto_corrected: bool = False
    consignor_state_code: str | None = None
    consignor_state_code_confidence: int = 0
    consignor_state_code_auto_corrected: bool = False
    consignor_state_name: str | None = None
    consignor_state_name_confidence: int = 0
    consignor_po_no: str | None = None
    consignor_po_no_confidence: int = 0
    consignor_po_no_auto_corrected: bool = False
    consignor_gstin: str | None = None
    consignor_gstin_confidence: int = 0
    consignor_gstin_auto_corrected: bool = False
    consignor_pan: str | None = None
    consignor_pan_confidence: int = 0
    consignor_pan_auto_corrected: bool = False
    request_no: str | None = None
    request_no_confidence: int = 0
    request_no_auto_corrected: bool = False
    irn_no: str | None = None
    irn_no_confidence: int = 0
    irn_no_auto_corrected: bool = False

    # Part 2: line items + tax summary
    line_items: list[LineItem] = []
    total_basic_amount: str | None = None
    total_basic_amount_confidence: int = 0
    total_basic_amount_auto_corrected: bool = False
    cgst_rate: str | None = None
    cgst_rate_confidence: int = 0
    cgst_rate_auto_corrected: bool = False
    cgst_amount: str | None = None
    cgst_amount_confidence: int = 0
    cgst_amount_auto_corrected: bool = False
    sgst_rate: str | None = None
    sgst_rate_confidence: int = 0
    sgst_rate_auto_corrected: bool = False
    sgst_amount: str | None = None
    sgst_amount_confidence: int = 0
    sgst_amount_auto_corrected: bool = False
    igst_rate: str | None = None
    igst_rate_confidence: int = 0
    igst_rate_auto_corrected: bool = False
    igst_amount: str | None = None
    igst_amount_confidence: int = 0
    igst_amount_auto_corrected: bool = False
    total_amount: str | None = None
    total_amount_confidence: int = 0
    total_amount_auto_corrected: bool = False
