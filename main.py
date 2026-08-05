import os
import json
import pandas as pd
from datetime import datetime

# ---------------------------------------------------------
# 1. Đường dẫn thư mục
# ---------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(CURRENT_DIR, "data")):
    BASE_DIR = CURRENT_DIR
else:
    BASE_DIR = os.path.dirname(CURRENT_DIR)

DATA_DIR = os.path.join(BASE_DIR, "data")

# Tự động quét tìm folder chứa 50 file JSON khiếu nại
INPUT_DIR = os.path.join(BASE_DIR, "input", "input")
if not os.path.exists(INPUT_DIR) or len([f for f in os.listdir(INPUT_DIR) if f.endswith(".json")]) == 0:
    INPUT_DIR = os.path.join(BASE_DIR, "input")

OUTPUT_DIR = os.path.join(BASE_DIR, "output")
LOGGING_DIR = os.path.join(BASE_DIR, "logging")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LOGGING_DIR, exist_ok=True)

print("--- Đang load dữ liệu Olist CSV ---")
# 2. Đọc các bảng dữ liệu chính từ CSV
orders_df = pd.read_csv(os.path.join(DATA_DIR, "olist_orders_dataset.csv"))
order_items_df = pd.read_csv(os.path.join(DATA_DIR, "olist_order_items_dataset.csv"))
order_payments_df = pd.read_csv(os.path.join(DATA_DIR, "olist_order_payments_dataset.csv"))
sellers_df = pd.read_csv(os.path.join(DATA_DIR, "olist_sellers_dataset.csv"))

print(f"Loaded {len(orders_df)} orders, {len(order_items_df)} items, {len(order_payments_df)} payments.")

# ---------------------------------------------------------
# 3. Hàm xử lý 1 case khiếu nại theo EC_POLICY_V1
# ---------------------------------------------------------
def process_case(case_file_path):
    with open(case_file_path, "r", encoding="utf-8") as f:
        case_data = json.load(f)

    case_id = case_data["case_id"]
    claimed_order_id = case_data["customer_request"]["claimed_order_id"]

    # Tra cứu Order
    order_rows = orders_df[orders_df["order_id"] == claimed_order_id]
    if order_rows.empty:
        return None

    order_info = order_rows.iloc[0]
    order_status = str(order_info["order_status"]) if pd.notna(order_info["order_status"]) else ""
    delivered_customer_date = str(order_info["order_delivered_customer_date"]) if pd.notna(order_info["order_delivered_customer_date"]) else ""
    delivered_carrier_date = str(order_info["order_delivered_carrier_date"]) if pd.notna(order_info["order_delivered_carrier_date"]) else ""
    estimated_delivery_date = str(order_info["order_estimated_delivery_date"]) if pd.notna(order_info["order_estimated_delivery_date"]) else ""

    # Tra cứu Items
    items_rows = order_items_df[order_items_df["order_id"] == claimed_order_id]
    item_ids = []
    seller_ids = []
    item_total = 0.0
    freight_total = 0.0
    max_shipping_limit = ""

    for idx, item in items_rows.iterrows():
        item_seq = str(item["order_item_id"])
        item_ids.append(f"{claimed_order_id}:{item_seq}")
        s_id = str(item["seller_id"])
        if s_id not in seller_ids:
            seller_ids.append(s_id)
        
        item_total += float(item["price"])
        freight_total += float(item["freight_value"])
        
        ship_limit = str(item["shipping_limit_date"]) if pd.notna(item["shipping_limit_date"]) else ""
        if ship_limit > max_shipping_limit:
            max_shipping_limit = ship_limit

    # Tra cứu Payments
    payments_rows = order_payments_df[order_payments_df["order_id"] == claimed_order_id]
    payment_ids = []
    payment_total = 0.0

    for idx, pay in payments_rows.iterrows():
        pay_seq = str(pay["payment_sequential"])
        payment_ids.append(f"{claimed_order_id}:{pay_seq}")
        payment_total += float(pay["payment_value"])

    # Làm tròn 2 chữ số thập phân
    item_total = round(item_total, 2)
    freight_total = round(freight_total, 2)
    payment_total = round(payment_total, 2)

    # Đánh giá theo 6 quy tắc chính của EC_POLICY_V1
    primary_issue = ""
    cause_code = ""
    case_status = "no_action"
    refund_amount = 0.0
    actions = []
    responsible_parties = []

    # 1. Đơn bị hủy đã trả tiền
    if order_status == "canceled" and payment_total > 0:
        primary_issue = "canceled_order_paid"
        cause_code = "ORDER_CANCELED_AFTER_PAYMENT"
        case_status = "action_required"
        refund_amount = payment_total
        actions = ["issue_full_refund"]
        responsible_parties = [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}]

    # 2. Đơn hết hàng/không khả dụng đã trả tiền
    elif order_status == "unavailable" and payment_total > 0:
        primary_issue = "unavailable_order_paid"
        cause_code = "ORDER_UNAVAILABLE_AFTER_PAYMENT"
        case_status = "action_required"
        refund_amount = payment_total
        actions = ["issue_full_refund"]
        responsible_parties = [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}]

    # 3 & 4. Kiểm tra trễ hạn giao hàng
    elif delivered_customer_date > estimated_delivery_date and estimated_delivery_date != "":
        # Seller bàn giao trễ cho shipper
        if delivered_carrier_date > max_shipping_limit and max_shipping_limit != "":
            primary_issue = "late_delivery_seller"
            cause_code = "SELLER_HANDOFF_AFTER_LIMIT"
            case_status = "action_required"
            refund_amount = freight_total
            actions = ["refund_freight"]
            target_seller = seller_ids[0] if seller_ids else "UNKNOWN_SELLER"
            responsible_parties = [{"party_type": "seller", "party_id": target_seller}]
        else:
            # Lỗi do đơn vị vận chuyển giao trễ
            primary_issue = "late_delivery_logistics"
            cause_code = "CARRIER_DELIVERED_AFTER_ESTIMATE"
            case_status = "action_required"
            refund_amount = freight_total
            actions = ["refund_freight"]
            responsible_parties = [{"party_type": "logistics_provider", "party_id": "LOGISTICS_PROVIDER"}]

    # 5. Đơn thanh toán nhiều lần hợp lệ
    elif len(payments_rows) >= 2 and abs(payment_total - (item_total + freight_total)) <= 0.10:
        primary_issue = "valid_split_payment"
        cause_code = "MULTIPLE_PAYMENTS_RECONCILED"
        case_status = "no_action"
        refund_amount = 0.0
        actions = ["explain_valid_split_payment"]
        responsible_parties = []

    # 6. Không có căn cứ hoàn trễ (giao đúng/trước hạn)
    else:
        primary_issue = "unsupported_late_claim"
        cause_code = "DELIVERY_WITHIN_ESTIMATE"
        case_status = "no_action"
        refund_amount = 0.0
        actions = ["reject_late_refund"]
        responsible_parties = []

    # Xây dựng Evidence IDs
    evidence_ids = [f"order:{claimed_order_id}"]
    for p_id in payment_ids:
        evidence_ids.append(f"payment:{p_id}")
    for i_id in item_ids:
        evidence_ids.append(f"item:{i_id}")
    for s_id in seller_ids:
        evidence_ids.append(f"seller:{s_id}")
    evidence_ids.append(f"policy:{cause_code}")

    evidence_ids = evidence_ids[:10]

    output_data = {
        "case_id": case_id,
        "assessment": {
            "primary_issue": primary_issue,
            "case_status": case_status,
            "confidence": 1.0
        },
        "affected_entities": {
            "order_ids": [claimed_order_id],
            "item_ids": item_ids[:5],
            "seller_ids": seller_ids[:5],
            "payment_ids": payment_ids[:5]
        },
        "root_cause_analysis": {
            "ranked_causes": [
                {"cause_code": cause_code, "rank": 1}
            ],
            "responsible_parties": responsible_parties
        },
        "evidence_ids": evidence_ids,
        "financial_resolution": {
            "currency": "BRL",
            "item_total_brl": item_total,
            "freight_total_brl": freight_total,
            "payment_total_brl": payment_total,
            "recommended_refund_brl": round(refund_amount, 2)
        },
        "resolution_actions": actions
    }

    return output_data

# ---------------------------------------------------------
# 4. Chạy batch qua toàn bộ 50 ticket trong folder input
# ---------------------------------------------------------
print("\n--- Bắt đầu xử lý 50 Ticket Khiếu nại ---")

input_files = [f for f in os.listdir(INPUT_DIR) if f.endswith(".json")]
input_files.sort()

success_count = 0
trace_logs = []

for file_name in input_files:
    file_path = os.path.join(INPUT_DIR, file_name)
    result = process_case(file_path)
    
    if result:
        # Ghi file kết quả output
        output_file_path = os.path.join(OUTPUT_DIR, file_name)
        with open(output_file_path, "w", encoding="utf-8") as out_f:
            json.dump(result, out_f, ensure_ascii=False, indent=2)
        
        success_count += 1
        trace_logs.append({
            "case_id": result["case_id"],
            "primary_issue": result["assessment"]["primary_issue"],
            "status": "COMPLETED",
            "timestamp": datetime.now().isoformat()
        })
        print(f"✅ Processed {file_name} -> {result['assessment']['primary_issue']}")

# Ghi file trace.jsonl
trace_path = os.path.join(LOGGING_DIR, "trace.jsonl")
with open(trace_path, "w", encoding="utf-8") as tf:
    for entry in trace_logs:
        tf.write(json.dumps(entry, ensure_ascii=False) + "\n")

# Ghi file metadata.json
metadata_path = os.path.join(LOGGING_DIR, "metadata.json")
metadata_info = {
    "cohort": "K3",
    "repo_starter": "K3-Day9-Multi-Agent-A2A",
    "policy_version": "EC_POLICY_V1",
    "model_used": "rule-based-agent-v1",
    "parameter_size": "<=10B",
    "runtime": "python-3.14",
    "total_cases_processed": success_count
}
with open(metadata_path, "w", encoding="utf-8") as mf:
    json.dump(metadata_info, mf, ensure_ascii=False, indent=2)

print(f"\n🎉 Xử lý xong {success_count}/{len(input_files)} ticket. Đầu ra lưu tại thư mục 'output/'.")
