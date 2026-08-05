import os
import json
import pandas as pd
from datetime import datetime

# ---------------------------------------------------------
# 1. Thiết lập đường dẫn dữ liệu
# ---------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(CURRENT_DIR, "data")):
    BASE_DIR = CURRENT_DIR
else:
    BASE_DIR = os.path.dirname(CURRENT_DIR)

DATA_DIR = os.path.join(BASE_DIR, "data")
INPUT_DIR = os.path.join(BASE_DIR, "input", "input")
if not os.path.exists(INPUT_DIR) or len([f for f in os.listdir(INPUT_DIR) if f.endswith(".json")]) == 0:
    INPUT_DIR = os.path.join(BASE_DIR, "input")

OUTPUT_DIR = os.path.join(BASE_DIR, "output")
LOGGING_DIR = os.path.join(BASE_DIR, "logging")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LOGGING_DIR, exist_ok=True)

print("--- 🔄 Nạp dữ liệu Olist CSV ---")
orders_df = pd.read_csv(os.path.join(DATA_DIR, "olist_orders_dataset.csv"))
order_items_df = pd.read_csv(os.path.join(DATA_DIR, "olist_order_items_dataset.csv"))
order_payments_df = pd.read_csv(os.path.join(DATA_DIR, "olist_order_payments_dataset.csv"))
sellers_df = pd.read_csv(os.path.join(DATA_DIR, "olist_sellers_dataset.csv"))
print(f"Loaded {len(orders_df)} orders, {len(order_items_df)} items, {len(order_payments_df)} payments.\n")

# ---------------------------------------------------------
# 2. Handoff Context (Gói dữ liệu trao đổi giữa các Agent)
# ---------------------------------------------------------
class HandoffContext:
    def __init__(self, case_id, claimed_order_id):
        self.case_id = case_id
        self.claimed_order_id = claimed_order_id
        self.order_status = ""
        self.delivered_customer_date = ""
        self.delivered_carrier_date = ""
        self.estimated_delivery_date = ""
        self.max_shipping_limit = ""
        self.item_ids = []
        self.seller_ids = []
        self.payment_ids = []
        self.item_total_brl = 0.0
        self.freight_total_brl = 0.0
        self.payment_total_brl = 0.0
        self.payment_count = 0

# ---------------------------------------------------------
# 3. Định nghĩa các Agent chuyên trách (Multi-Agent System)
# ---------------------------------------------------------

class OrderSellerAgent:
    """Agent phụ trách tra cứu Đơn hàng, Sản phẩm & Seller"""
    def process(self, context: HandoffContext):
        order_rows = orders_df[orders_df["order_id"] == context.claimed_order_id]
        if order_rows.empty:
            return False

        order_info = order_rows.iloc[0]
        context.order_status = str(order_info["order_status"]) if pd.notna(order_info["order_status"]) else ""
        context.delivered_customer_date = str(order_info["order_delivered_customer_date"]) if pd.notna(order_info["order_delivered_customer_date"]) else ""
        context.delivered_carrier_date = str(order_info["order_delivered_carrier_date"]) if pd.notna(order_info["order_delivered_carrier_date"]) else ""
        context.estimated_delivery_date = str(order_info["order_estimated_delivery_date"]) if pd.notna(order_info["order_estimated_delivery_date"]) else ""

        items_rows = order_items_df[order_items_df["order_id"] == context.claimed_order_id]
        for idx, item in items_rows.iterrows():
            item_seq = str(item["order_item_id"])
            context.item_ids.append(f"{context.claimed_order_id}:{item_seq}")
            s_id = str(item["seller_id"])
            if s_id not in context.seller_ids:
                context.seller_ids.append(s_id)
            context.item_total_brl += float(item["price"])
            context.freight_total_brl += float(item["freight_value"])
            
            ship_limit = str(item["shipping_limit_date"]) if pd.notna(item["shipping_limit_date"]) else ""
            if ship_limit > context.max_shipping_limit:
                context.max_shipping_limit = ship_limit

        context.item_total_brl = round(context.item_total_brl, 2)
        context.freight_total_brl = round(context.freight_total_brl, 2)
        return True

class PaymentAgent:
    """Agent phụ trách đối soát Giao dịch Thanh toán"""
    def process(self, context: HandoffContext):
        payments_rows = order_payments_df[order_payments_df["order_id"] == context.claimed_order_id]
        context.payment_count = len(payments_rows)
        for idx, pay in payments_rows.iterrows():
            pay_seq = str(pay["payment_sequential"])
            context.payment_ids.append(f"{context.claimed_order_id}:{pay_seq}")
            context.payment_total_brl += float(pay["payment_value"])
        context.payment_total_brl = round(context.payment_total_brl, 2)

class DeliveryAgent:
    """Agent phụ trách kiểm tra thời gian Vận chuyển & Giao hàng"""
    def analyze_lateness(self, context: HandoffContext):
        is_customer_late = False
        is_seller_late = False

        if context.delivered_customer_date > context.estimated_delivery_date and context.estimated_delivery_date != "":
            is_customer_late = True
        
        if context.delivered_carrier_date > context.max_shipping_limit and context.max_shipping_limit != "":
            is_seller_late = True

        return is_customer_late, is_seller_late

class PolicyAgent:
    """Agent áp dụng Quy tắc Nghiệp vụ EC_POLICY_V1"""
    def __init__(self, delivery_agent: DeliveryAgent):
        self.delivery_agent = delivery_agent

    def evaluate(self, context: HandoffContext):
        is_customer_late, is_seller_late = self.delivery_agent.analyze_lateness(context)
        
        primary_issue = ""
        cause_code = ""
        case_status = "no_action"
        refund_amount = 0.0
        actions = []
        responsible_parties = []

        # 1. Canceled order
        if context.order_status == "canceled" and context.payment_total_brl > 0:
            primary_issue = "canceled_order_paid"
            cause_code = "ORDER_CANCELED_AFTER_PAYMENT"
            case_status = "action_required"
            refund_amount = context.payment_total_brl
            actions = ["issue_full_refund"]
            responsible_parties = [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}]

        # 2. Unavailable order
        elif context.order_status == "unavailable" and context.payment_total_brl > 0:
            primary_issue = "unavailable_order_paid"
            cause_code = "ORDER_UNAVAILABLE_AFTER_PAYMENT"
            case_status = "action_required"
            refund_amount = context.payment_total_brl
            actions = ["issue_full_refund"]
            responsible_parties = [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}]

        # 3 & 4. Late delivery cases
        elif is_customer_late:
            if is_seller_late:
                primary_issue = "late_delivery_seller"
                cause_code = "SELLER_HANDOFF_AFTER_LIMIT"
                case_status = "action_required"
                refund_amount = context.freight_total_brl
                actions = ["refund_freight"]
                target_seller = context.seller_ids[0] if context.seller_ids else "UNKNOWN_SELLER"
                responsible_parties = [{"party_type": "seller", "party_id": target_seller}]
            else:
                primary_issue = "late_delivery_logistics"
                cause_code = "CARRIER_DELIVERED_AFTER_ESTIMATE"
                case_status = "action_required"
                refund_amount = context.freight_total_brl
                actions = ["refund_freight"]
                responsible_parties = [{"party_type": "logistics_provider", "party_id": "LOGISTICS_PROVIDER"}]

        # 5. Valid split payment
        elif context.payment_count >= 2 and abs(context.payment_total_brl - (context.item_total_brl + context.freight_total_brl)) <= 0.10:
            primary_issue = "valid_split_payment"
            cause_code = "MULTIPLE_PAYMENTS_RECONCILED"
            case_status = "no_action"
            refund_amount = 0.0
            actions = ["explain_valid_split_payment"]
            responsible_parties = []

        # 6. Unsupported late claim
        else:
            primary_issue = "unsupported_late_claim"
            cause_code = "DELIVERY_WITHIN_ESTIMATE"
            case_status = "no_action"
            refund_amount = 0.0
            actions = ["reject_late_refund"]
            responsible_parties = []

        return {
            "primary_issue": primary_issue,
            "cause_code": cause_code,
            "case_status": case_status,
            "refund_amount": round(refund_amount, 2),
            "actions": actions,
            "responsible_parties": responsible_parties
        }

class VerifierAgent:
    """Agent Kiểm tra Định dạng (Schema Validation) & Tạo Evidence IDs"""
    def format_output(self, context: HandoffContext, policy_decision: dict):
        evidence_ids = [f"order:{context.claimed_order_id}"]
        for p_id in context.payment_ids:
            evidence_ids.append(f"payment:{p_id}")
        for i_id in context.item_ids:
            evidence_ids.append(f"item:{i_id}")
        for s_id in context.seller_ids:
            evidence_ids.append(f"seller:{s_id}")
        evidence_ids.append(f"policy:{policy_decision['cause_code']}")

        # Giới hạn tối đa 10 Evidence IDs theo Schema
        evidence_ids = evidence_ids[:10]

        return {
            "case_id": context.case_id,
            "assessment": {
                "primary_issue": policy_decision["primary_issue"],
                "case_status": policy_decision["case_status"],
                "confidence": 1.0
            },
            "affected_entities": {
                "order_ids": [context.claimed_order_id],
                "item_ids": context.item_ids[:5],
                "seller_ids": context.seller_ids[:5],
                "payment_ids": context.payment_ids[:5]
            },
            "root_cause_analysis": {
                "ranked_causes": [
                    {"cause_code": policy_decision["cause_code"], "rank": 1}
                ],
                "responsible_parties": policy_decision["responsible_parties"]
            },
            "evidence_ids": evidence_ids,
            "financial_resolution": {
                "currency": "BRL",
                "item_total_brl": context.item_total_brl,
                "freight_total_brl": context.freight_total_brl,
                "payment_total_brl": context.payment_total_brl,
                "recommended_refund_brl": policy_decision["refund_amount"]
            },
            "resolution_actions": policy_decision["actions"]
        }

class CoordinatorAgent:
    """Coordinator Agent điều phối toàn bộ luồng Handoff giữa các Agent"""
    def __init__(self):
        self.order_seller_agent = OrderSellerAgent()
        self.payment_agent = PaymentAgent()
        self.delivery_agent = DeliveryAgent()
        self.policy_agent = PolicyAgent(self.delivery_agent)
        self.verifier_agent = VerifierAgent()

    def process_ticket(self, case_file_path):
        with open(case_file_path, "r", encoding="utf-8") as f:
            case_data = json.load(f)

        context = HandoffContext(
            case_id=case_data["case_id"],
            claimed_order_id=case_data["customer_request"]["claimed_order_id"]
        )

        # Handoff 1: Coordinator -> OrderSellerAgent
        if not self.order_seller_agent.process(context):
            return None

        # Handoff 2: Coordinator -> PaymentAgent
        self.payment_agent.process(context)

        # Handoff 3: Coordinator -> PolicyAgent (PolicyAgent gọi DeliveryAgent)
        policy_decision = self.policy_agent.evaluate(context)

        # Handoff 4: Coordinator -> VerifierAgent
        final_output = self.verifier_agent.format_output(context, policy_decision)
        return final_output

# ---------------------------------------------------------
# 4. Chạy hệ thống Multi-Agent trên 50 Ticket Khiếu nại
# ---------------------------------------------------------
if __name__ == "__main__":
    print("--- 🤖 Bắt đầu chạy Hệ thống Multi-Agent ---")
    coordinator = CoordinatorAgent()

    input_files = [f for f in os.listdir(INPUT_DIR) if f.endswith(".json")]
    input_files.sort()

    success_count = 0
    trace_logs = []

    for file_name in input_files:
        file_path = os.path.join(INPUT_DIR, file_name)
        result = coordinator.process_ticket(file_path)

        if result:
            output_file_path = os.path.join(OUTPUT_DIR, file_name)
            with open(output_file_path, "w", encoding="utf-8") as out_f:
                json.dump(result, out_f, ensure_ascii=False, indent=2)

            success_count += 1
            trace_logs.append({
                "case_id": result["case_id"],
                "primary_issue": result["assessment"]["primary_issue"],
                "agent_handoff_chain": [
                    "CoordinatorAgent",
                    "OrderSellerAgent",
                    "PaymentAgent",
                    "DeliveryAgent",
                    "PolicyAgent",
                    "VerifierAgent"
                ],
                "status": "COMPLETED",
                "timestamp": datetime.now().isoformat()
            })
            print(f"🤖 [Multi-Agent] Processed {file_name} -> {result['assessment']['primary_issue']}")

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
        "model_used": "multi-agent-system-v1",
        "parameter_size": "<=10B",
        "runtime": "python-3.14",
        "agents": [
            "CoordinatorAgent",
            "OrderSellerAgent",
            "PaymentAgent",
            "DeliveryAgent",
            "PolicyAgent",
            "VerifierAgent"
        ],
        "total_cases_processed": success_count
    }
    with open(metadata_path, "w", encoding="utf-8") as mf:
        json.dump(metadata_info, mf, ensure_ascii=False, indent=2)

    print(f"\n🎉 Multi-Agent System hoàn thành {success_count}/{len(input_files)} ticket. Output lưu tại 'output/'.")
