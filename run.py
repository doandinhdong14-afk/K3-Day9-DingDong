from typing import Dict, Any, List
import pandas as pd

class OrderSellerAgent:
    """Agent chịu trách nhiệm điều tra dữ liệu Đơn hàng, Sản phẩm (Items) và Seller

    từ bộ dữ liệu Olist.
    """

    def __init__(self, data_dir: str = "data"):
        """Load sẵn dữ liệu Olist từ thư mục data/."""
        self.orders_df = pd.read_csv(f"{data_dir}/olist_orders_dataset.csv")
        self.items_df = pd.read_csv(f"{data_dir}/olist_order_items_dataset.csv")

    def process_case(self, input_case: Dict[str, Any]) -> Dict[str, Any]:
        """Xử lý yêu cầu điều tra từ Coordinator Agent cho một case.

        :param input_case: Dict chứa thông tin đầu vào (ví dụ EC_001.json)
        :return: Dict kết quả điều tra Order/Seller để handoff sang Policy Agent
        """
        case_id = input_case.get("case_id")
        claimed_order_id = input_case["customer_request"]["claimed_order_id"]

        # 1. Truy xuất thông tin Order từ olist_orders_dataset.csv
        order_rows = self.orders_df[
            self.orders_df["order_id"] == claimed_order_id
        ]

        if order_rows.empty:
            # Trường hợp order_id không tồn tại trong database
            return {
                "case_id": case_id,
                "claimed_order_id": claimed_order_id,
                "order_exists": False,
                "order_status": None,
                "has_items": False,
                "financials": {"item_total_brl": 0.0, "freight_total_brl": 0.0},
                "entities": {"item_ids": [], "seller_ids": []},
                "timestamps": {},
                "evidences": [],
            }

        order_data = order_rows.iloc[0]
        order_status = str(order_data["order_status"])

        # Lấy các mốc thời gian (so sánh trực tiếp chuỗi timestamp theo quy định đề bài)
        deliv_carrier = (
            str(order_data["order_delivered_carrier_date"])
            if pd.notna(order_data["order_delivered_carrier_date"])
            else None
        )
        deliv_customer = (
            str(order_data["order_delivered_customer_date"])
            if pd.notna(order_data["order_delivered_customer_date"])
            else None
        )
        estimated_deliv = (
            str(order_data["order_estimated_delivery_date"])
            if pd.notna(order_data["order_estimated_delivery_date"])
            else None
        )

        # 2. Truy xuất Items & Sellers từ olist_order_items_dataset.csv
        items_rows = self.items_df[
            self.items_df["order_id"] == claimed_order_id
        ]

        item_ids: List[str] = []
        seller_ids: List[str] = []
        shipping_limit_dates: List[str] = []
        item_total_brl = 0.0
        freight_total_brl = 0.0

        if not items_rows.empty:
            for _, item in items_rows.iterrows():
                # Tạo format item_id: <order_id>:<order_item_id>
                item_seq = item["order_item_id"]
                item_ids.append(f"{claimed_order_id}:{item_seq}")

                # Lấy seller_id
                seller_id = str(item["seller_id"])
                if seller_id not in seller_ids:
                    seller_ids.append(seller_id)

                # Cộng dồn tài chính
                item_total_brl += float(item.get("price", 0.0))
                freight_total_brl += float(item.get("freight_value", 0.0))

                # Lấy shipping_limit_date
                if pd.notna(item.get("shipping_limit_date")):
                    shipping_limit_dates.append(
                        str(item["shipping_limit_date"])
                    )

        # Giới hạn số lượng ID theo quy chuẩn Schema (Tối đa 5 ID)
        item_ids_clean = item_ids[:5]
        seller_ids_clean = seller_ids[:5]

        # 3. Tạo danh sách Evidence IDs hợp lệ từ dữ liệu thực tế
        evidence_ids = [f"order:{claimed_order_id}"]
        for i_id in item_ids_clean:
            evidence_ids.append(f"item:{i_id}")
        for s_id in seller_ids_clean:
            evidence_ids.append(f"seller:{s_id}")

        # 4. Trả về kết quả Handoff Payload
        return {
            "case_id": case_id,
            "claimed_order_id": claimed_order_id,
            "order_exists": True,
            "order_status": order_status,
            "has_items": len(items_rows) > 0,
            "timestamps": {
                "order_delivered_carrier_date": deliv_carrier,
                "order_delivered_customer_date": deliv_customer,
                "order_estimated_delivery_date": estimated_deliv,
                "shipping_limit_dates": shipping_limit_dates,
            },
            "financials": {
                "item_total_brl": round(item_total_brl, 2),
                "freight_total_brl": round(freight_total_brl, 2),
            },
            "entities": {
                "item_ids": item_ids_clean,
                "seller_ids": seller_ids_clean,
            },
            "evidences": evidence_ids,
        }

class PaymentAgent:
    """Agent chịu trách nhiệm điều tra và đối soát dữ liệu Thanh toán từ olist_order_payments_dataset.csv."""

    def __init__(self, data_dir: str = "data"):
        """Load dữ liệu thanh toán Olist từ thư mục data/."""
        self.payments_df = pd.read_csv(
            f"{data_dir}/olist_order_payments_dataset.csv"
        )

    def process_case(self, input_case: Dict[str, Any]) -> Dict[str, Any]:
        """Xử lý yêu cầu điều tra thanh toán cho một case.

        :param input_case: Dict chứa thông tin đầu vào (ví dụ EC_001.json hoặc
        Handoff từ Coordinator)
        :return: Dict kết quả điều tra Payment để handoff cho Policy /
        Coordinator Agent
        """
        case_id = input_case.get("case_id")
        claimed_order_id = (
            input_case.get("claimed_order_id")
            or input_case["customer_request"]["claimed_order_id"]
        )

        # 1. Truy xuất các dòng thanh toán từ olist_order_payments_dataset.csv
        pay_rows = self.payments_df[
            self.payments_df["order_id"] == claimed_order_id
        ]

        payment_ids: List[str] = []
        payment_types: List[str] = []
        payment_total_brl = 0.0

        if not pay_rows.empty:
            for _, pay in pay_rows.iterrows():
                # Tạo format payment_id: <order_id>:<payment_sequential>
                seq = pay["payment_sequential"]
                p_id = f"{claimed_order_id}:{seq}"
                payment_ids.append(p_id)

                # Cộng dồn giá trị thanh toán thực tế (làm tròn 2 chữ số thập phân)
                payment_total_brl += float(pay.get("payment_value", 0.0))

                # Thu thập loại hình thanh toán
                p_type = str(pay.get("payment_type", "unknown"))
                if p_type not in payment_types:
                    payment_types.append(p_type)

        # Giới hạn số lượng ID theo quy chuẩn Schema (Tối đa 5 ID)
        payment_ids_clean = payment_ids[:5]

        # 2. Tạo Evidence IDs chuẩn hóa: payment:<order_id>:<payment_sequential>
        evidence_ids = [f"payment:{p_id}" for p_id in payment_ids_clean]

        # 3. Trả về kết quả Handoff Payload
        return {
            "case_id": case_id,
            "claimed_order_id": claimed_order_id,
            "has_payments": len(pay_rows) > 0,
            "payment_count": len(pay_rows),
            "payment_total_brl": round(payment_total_brl, 2),
            "payment_types": payment_types,
            "entities": {
                "payment_ids": payment_ids_clean,
            },
            "evidences": evidence_ids,
        }
from typing import Dict, Any, Optional


class DeliveryAgent:
    """Agent chuyên trách phân tích mốc thời gian vận chuyển và xác định bên chịu trách nhiệm giao trễ."""

    def process_delivery_analysis(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Phân tích mốc thời gian giao hàng nhận được từ Order/Seller Agent.

        :param order_data: Dict thông tin đơn hàng từ Order/Seller Agent.
        :return: Dict kết quả phân tích vận chuyển để handoff cho Policy Agent.
        """
        timestamps = order_data.get("timestamps", {})
        
        deliv_carrier = timestamps.get("order_delivered_carrier_date")
        deliv_customer = timestamps.get("order_delivered_customer_date")
        estimated_deliv = timestamps.get("order_estimated_delivery_date")
        shipping_limit_dates = timestamps.get("shipping_limit_dates", [])

        # 1. Kiểm tra đơn hàng có bị giao trễ cho khách hay không
        is_late_delivery = False
        if deliv_customer and estimated_deliv:
            # So sánh chuỗi ISO/CSV timestamp trực tiếp theo quy định đề bài
            if deliv_customer > estimated_deliv:
                is_late_delivery = True

        # 2. Nếu giao trễ, phân định trách nhiệm giữa Seller và Logistics Provider
        is_seller_at_fault = False
        violating_seller_id: Optional[str] = None

        if is_late_delivery:
            if deliv_carrier and shipping_limit_dates:
                # Kiểm tra nếu carrier nhận hàng sau bất kỳ shipping_limit_date nào của item
                for idx, limit_date in enumerate(shipping_limit_dates):
                    if deliv_carrier > limit_date:
                        is_seller_at_fault = True
                        # Lấy seller_id tương ứng nếu có
                        seller_ids = order_data.get("entities", {}).get("seller_ids", [])
                        if idx < len(seller_ids):
                            violating_seller_id = seller_ids[idx]
                        elif seller_ids:
                            violating_seller_id = seller_ids[0]
                        break

        # 3. Tổng hợp kết luận điều tra vận chuyển
        if is_late_delivery:
            if is_seller_at_fault:
                responsible_party_type = "seller"
                responsible_party_id = violating_seller_id or "SELLER"
                root_cause_code = "SELLER_HANDOFF_AFTER_LIMIT"
                suggested_issue = "late_delivery_seller"
            else:
                responsible_party_type = "logistics_provider"
                responsible_party_id = "LOGISTICS_PROVIDER"
                root_cause_code = "CARRIER_DELIVERED_AFTER_ESTIMATE"
                suggested_issue = "late_delivery_logistics"
        else:
            responsible_party_type = None
            responsible_party_id = None
            root_cause_code = "DELIVERY_WITHIN_ESTIMATE"
            suggested_issue = "unsupported_late_claim"

        return {
            "case_id": order_data.get("case_id"),
            "order_id": order_data.get("claimed_order_id"),
            "is_late_delivery": is_late_delivery,
            "is_seller_at_fault": is_seller_at_fault,
            "suggested_issue": suggested_issue,
            "root_cause_code": root_cause_code,
            "responsible_party": {
                "party_type": responsible_party_type,
                "party_id": responsible_party_id
            } if responsible_party_type else None,
            "policy_evidence": f"policy:{root_cause_code}"
        }
from typing import Dict, Any, List, Optional


class PolicyAgent:
    """Agent chịu trách nhiệm áp dụng bộ quy tắc nghiệp vụ EC_POLICY_V1

    và đưa ra phương án giải quyết tài chính + hành động cuối cùng.
    """

    def evaluate_policy(
        self,
        order_info: Dict[str, Any],
        payment_info: Dict[str, Any],
        delivery_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Đánh giá toàn bộ bằng chứng và trả về phương án giải quyết theo thứ tự ưu tiên.

        :param order_info: Output từ Order/Seller Agent
        :param payment_info: Output từ Payment Agent
        :param delivery_info: Output từ Delivery Agent
        :return: Dict chứa kết quả đánh giá policy
        """
        order_status = order_info.get("order_status")
        p_total = round(payment_info.get("payment_total_brl", 0.0), 2)
        p_count = payment_info.get("payment_count", 0)

        # Lấy giá trị tiền hàng & cước phí
        has_items = order_info.get("has_items", False)
        item_total = (
            round(order_info.get("financials", {}).get("item_total_brl", 0.0), 2)
            if has_items
            else 0.0
        )
        freight_total = (
            round(
                order_info.get("financials", {}).get("freight_total_brl", 0.0),
                2,
            )
            if has_items
            else 0.0
        )

        # -------------------------------------------------------------
        # PRIORITY 1: canceled_order_paid
        # -------------------------------------------------------------
        if order_status == "canceled" and p_total > 0:
            return self._build_resolution(
                primary_issue="canceled_order_paid",
                case_status="action_required",
                root_cause_code="ORDER_CANCELED_AFTER_PAYMENT",
                party_type="platform",
                party_id="OLIST_PLATFORM",
                recommended_refund=p_total,
                action="issue_full_refund",
                item_total=item_total,
                freight_total=freight_total,
                payment_total=p_total,
            )

        # -------------------------------------------------------------
        # PRIORITY 2: unavailable_order_paid
        # -------------------------------------------------------------
        if order_status == "unavailable" and p_total > 0:
            return self._build_resolution(
                primary_issue="unavailable_order_paid",
                case_status="action_required",
                root_cause_code="ORDER_UNAVAILABLE_AFTER_PAYMENT",
                party_type="platform",
                party_id="OLIST_PLATFORM",
                recommended_refund=p_total,
                action="issue_full_refund",
                item_total=item_total,
                freight_total=freight_total,
                payment_total=p_total,
            )

        # -------------------------------------------------------------
        # PRIORITY 3: late_delivery_seller
        # -------------------------------------------------------------
        if (
            delivery_info.get("is_late_delivery")
            and delivery_info.get("is_seller_at_fault")
        ):
            resp_party = delivery_info.get("responsible_party") or {}
            seller_id = resp_party.get("party_id") or (
                order_info.get("entities", {}).get("seller_ids", ["UNKNOWN"])[0]
            )

            return self._build_resolution(
                primary_issue="late_delivery_seller",
                case_status="action_required",
                root_cause_code="SELLER_HANDOFF_AFTER_LIMIT",
                party_type="seller",
                party_id=seller_id,
                recommended_refund=freight_total,
                action="refund_freight",
                item_total=item_total,
                freight_total=freight_total,
                payment_total=p_total,
            )

        # -------------------------------------------------------------
        # PRIORITY 4: late_delivery_logistics
        # -------------------------------------------------------------
        if delivery_info.get("is_late_delivery") and not delivery_info.get(
            "is_seller_at_fault"
        ):
            return self._build_resolution(
                primary_issue="late_delivery_logistics",
                case_status="action_required",
                root_cause_code="CARRIER_DELIVERED_AFTER_ESTIMATE",
                party_type="logistics_provider",
                party_id="LOGISTICS_PROVIDER",
                recommended_refund=freight_total,
                action="refund_freight",
                item_total=item_total,
                freight_total=freight_total,
                payment_total=p_total,
            )

        # -------------------------------------------------------------
        # PRIORITY 5: valid_split_payment
        # -------------------------------------------------------------
        expected_total = round(item_total + freight_total, 2)
        if p_count >= 2 and abs(p_total - expected_total) <= 0.10:
            return self._build_resolution(
                primary_issue="valid_split_payment",
                case_status="no_action",
                root_cause_code="MULTIPLE_PAYMENTS_RECONCILED",
                party_type=None,
                party_id=None,
                recommended_refund=0.0,
                action="explain_valid_split_payment",
                item_total=item_total,
                freight_total=freight_total,
                payment_total=p_total,
            )

        # -------------------------------------------------------------
        # PRIORITY 6: unsupported_late_claim (Default / Fallback)
        # -------------------------------------------------------------
        return self._build_resolution(
            primary_issue="unsupported_late_claim",
            case_status="no_action",
            root_cause_code="DELIVERY_WITHIN_ESTIMATE",
            party_type=None,
            party_id=None,
            recommended_refund=0.0,
            action="reject_late_refund",
            item_total=item_total,
            freight_total=freight_total,
            payment_total=p_total,
        )

    def _build_resolution(
        self,
        primary_issue: str,
        case_status: str,
        root_cause_code: str,
        party_type: Optional[str],
        party_id: Optional[str],
        recommended_refund: float,
        action: str,
        item_total: float,
        freight_total: float,
        payment_total: float,
    ) -> Dict[str, Any]:
        """Tạo gói cấu trúc kết quả phân tích quy định."""
        responsible_parties = []
        if party_type and party_id:
            responsible_parties.append(
                {"party_type": party_type, "party_id": party_id}
            )

        return {
            "assessment": {
                "primary_issue": primary_issue,
                "case_status": case_status,
                "confidence": 1.0,
            },
            "root_cause_analysis": {
                "ranked_causes": [
                    {"cause_code": root_cause_code, "rank": 1}
                ],
                "responsible_parties": responsible_parties,
            },
            "financial_resolution": {
                "currency": "BRL",
                "item_total_brl": item_total,
                "freight_total_brl": freight_total,
                "payment_total_brl": payment_total,
                "recommended_refund_brl": round(recommended_refund, 2),
            },
            "resolution_actions": [action],
            "policy_evidence": f"policy:{root_cause_code}",
        }
from typing import Dict, Any, List
from pydantic import BaseModel, Field


# ==========================================
# PYDANTIC OUTPUT SCHEMA
# ==========================================

class Assessment(BaseModel):
    primary_issue: str
    case_status: str  # "action_required" | "no_action"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

class AffectedEntities(BaseModel):
    order_ids: List[str] = Field(default_factory=list, max_length=5)
    item_ids: List[str] = Field(default_factory=list, max_length=5)
    seller_ids: List[str] = Field(default_factory=list, max_length=5)
    payment_ids: List[str] = Field(default_factory=list, max_length=5)

class RootCause(BaseModel):
    cause_code: str
    rank: int

class ResponsibleParty(BaseModel):
    party_type: str
    party_id: str

class RootCauseAnalysis(BaseModel):
    ranked_causes: List[RootCause] = Field(default_factory=list, max_length=3)
    responsible_parties: List[ResponsibleParty] = Field(default_factory=list, max_length=3)

class FinancialResolution(BaseModel):
    currency: str = "BRL"
    item_total_brl: float
    freight_total_brl: float
    payment_total_brl: float
    recommended_refund_brl: float

class CaseOutput(BaseModel):
    case_id: str
    assessment: Assessment
    affected_entities: AffectedEntities
    root_cause_analysis: RootCauseAnalysis
    evidence_ids: List[str] = Field(default_factory=list, max_length=10)
    financial_resolution: FinancialResolution
    resolution_actions: List[str] = Field(default_factory=list, max_length=5)


# ==========================================
# VERIFIER AGENT CLASS
# ==========================================

class VerifierAgent:
    """Agent đảm bảo chất lượng, kiểm định dữ liệu và format Output JSON chuẩn xác."""

    def verify_and_build(
        self,
        case_id: str,
        claimed_order_id: str,
        order_info: Dict[str, Any],
        payment_info: Dict[str, Any],
        policy_res: Dict[str, Any],
    ) -> CaseOutput:
        """Kiểm tra điều kiện, làm sạch dữ liệu và đóng gói Pydantic Schema.

        :param case_id: Mã case (ví dụ EC_001)
        :param claimed_order_id: Mã order
        :param order_info: Output từ Order/Seller Agent
        :param payment_info: Output từ Payment Agent
        :param policy_res: Output từ Policy Agent
        :return: CaseOutput đã được validate
        """
        has_items = order_info.get("has_items", False)

        # 1. Kiểm tra Affected Entities (Ép rỗng nếu không có items)
        order_ids = [claimed_order_id][:5]
        item_ids = order_info.get("entities", {}).get("item_ids", [])[:5] if has_items else []
        seller_ids = order_info.get("entities", {}).get("seller_ids", [])[:5] if has_items else []
        payment_ids = payment_info.get("entities", {}).get("payment_ids", [])[:5]

        # 2. Xử lý Financials
        item_total = round(order_info.get("financials", {}).get("item_total_brl", 0.0), 2) if has_items else 0.0
        freight_total = round(order_info.get("financials", {}).get("freight_total_brl", 0.0), 2) if has_items else 0.0
        payment_total = round(payment_info.get("payment_total_brl", 0.0), 2)
        
        fin_res = policy_res.get("financial_resolution", {})
        rec_refund = round(fin_res.get("recommended_refund_brl", 0.0), 2)

        # 3. Tổng hợp và Lọc trùng Evidence IDs (Max 10 IDs)
        raw_evidences = []
        raw_evidences.append(f"order:{claimed_order_id}")
        
        if has_items:
            for item_id in item_ids:
                raw_evidences.append(f"item:{item_id}")
            for seller_id in seller_ids:
                raw_evidences.append(f"seller:{seller_id}")

        for pay_id in payment_ids:
            raw_evidences.append(f"payment:{pay_id}")

        # Thêm policy evidence
        policy_ev = policy_res.get("policy_evidence")
        if policy_ev:
            raw_evidences.append(policy_ev)

        # Khử trùng lặp giữ nguyên thứ tự và giới hạn tối đa 10
        clean_evidences = list(dict.fromkeys(raw_evidences))[:10]

        # 4. Kiểm tra Root Causes & Responsible Parties
        rc_data = policy_res.get("root_cause_analysis", {})
        ranked_causes = [
            RootCause(cause_code=rc["cause_code"], rank=rc["rank"])
            for rc in rc_data.get("ranked_causes", [])
        ][:3]

        resp_parties = [
            ResponsibleParty(party_type=rp["party_type"], party_id=rp["party_id"])
            for rp in rc_data.get("responsible_parties", [])
        ][:3]

        # 5. Xây dựng Pydantic Object cuối cùng (Tự động Validate)
        output_data = CaseOutput(
            case_id=case_id,
            assessment=Assessment(
                primary_issue=policy_res["assessment"]["primary_issue"],
                case_status=policy_res["assessment"]["case_status"],
                confidence=float(policy_res["assessment"].get("confidence", 1.0)),
            ),
            affected_entities=AffectedEntities(
                order_ids=order_ids,
                item_ids=item_ids,
                seller_ids=seller_ids,
                payment_ids=payment_ids,
            ),
            root_cause_analysis=RootCauseAnalysis(
                ranked_causes=ranked_causes,
                responsible_parties=resp_parties,
            ),
            evidence_ids=clean_evidences,
            financial_resolution=FinancialResolution(
                currency="BRL",
                item_total_brl=item_total,
                freight_total_brl=freight_total,
                payment_total_brl=payment_total,
                recommended_refund_brl=rec_refund,
            ),
            resolution_actions=policy_res.get("resolution_actions", [])[:5],
        )

        return output_data
import json
import os
import zipfile
from typing import Dict, Any, List
import pandas as pd


class CoordinatorAgent:
    """Agent Điều phối hệ thống Multi-Agent Dispute Resolution.

    Chịu trách nhiệm khởi tạo pipeline, điều phối handoff dữ liệu giữa các
    specialist agents, ghi log trace.jsonl và đóng gói file zip kết quả.
    """

    def __init__(self, data_dir: str = "data", input_dir: str = "input", output_dir: str = "output"):
        self.data_dir = data_dir
        self.input_dir = input_dir
        self.output_dir = output_dir

        # 1. Khởi tạo Data Store tập trung
        print("🔄 [Coordinator] Đang nạp dữ liệu Olist từ thư mục data/...")
        self.data_store = {
            "orders": pd.read_csv(os.path.join(data_dir, "olist_orders_dataset.csv")),
            "order_items": pd.read_csv(os.path.join(data_dir, "olist_order_items_dataset.csv")),
            "order_payments": pd.read_csv(os.path.join(data_dir, "olist_order_payments_dataset.csv")),
            "sellers": pd.read_csv(os.path.join(data_dir, "olist_sellers_dataset.csv")),
        }

        # 2. Khởi tạo các Agent thành viên
        print("🤖 [Coordinator] Đang khởi tạo các Specialist Agents...")
        self.order_seller_agent = OrderSellerAgent(data_dir=self.data_dir)
        self.payment_agent = PaymentAgent(data_dir=self.data_dir)
        self.delivery_agent = DeliveryAgent()
        self.policy_agent = PolicyAgent()
        self.verifier_agent = VerifierAgent()

    def process_single_case(self, case_id: str, case_input: Dict[str, Any]) -> Dict[str, Any]:
        """Điều phối xử lý 1 case qua luồng Handoff Multi-Agent."""
        claimed_order_id = case_input["customer_request"]["claimed_order_id"]

        # Step 1: Order/Seller Agent kiểm tra order status, items, sellers, timestamps
        order_info = self.order_seller_agent.process_case(case_input)

        # Step 2: Payment Agent kiểm tra giao dịch thanh toán
        payment_info = self.payment_agent.process_case(case_input)

        # Step 3: Delivery Agent phân tích mốc thời gian giao nhận
        delivery_info = self.delivery_agent.process_delivery_analysis(order_info)

        # Step 4: Policy Agent đánh giá quy định EC_POLICY_V1 theo thứ tự ưu tiên
        policy_res = self.policy_agent.evaluate_policy(order_info, payment_info, delivery_info)

        # Step 5: Verifier Agent kiểm định Schema, chống False Positives và xuất Pydantic Object
        verified_output = self.verifier_agent.verify_and_build(
            case_id=case_id,
            claimed_order_id=claimed_order_id,
            order_info=order_info,
            payment_info=payment_info,
            policy_res=policy_res,
        )

        return verified_output.model_dump()

    def run_all_cases(self, total_cases: int = 50):
        """Chạy trọn vẹn 50 case từ EC_001 đến EC_050, ghi trace log và nén zip."""
        os.makedirs(self.output_dir, exist_ok=True)
        trace_logs: List[Dict[str, Any]] = []

        print(f"\n🚀 [Coordinator] Bắt đầu xử lý {total_cases} cases...")

        for i in range(1, total_cases + 1):
            case_id = f"EC_{i:03d}"
            input_file = os.path.join(self.input_dir, f"{case_id}.json")

            if not os.path.exists(input_file):
                print(f"⚠️  [Warning] Không tìm thấy file input: {input_file}")
                continue

            # Read Case Input
            with open(input_file, "r", encoding="utf-8") as f:
                case_input = json.load(f)

            claimed_order_id = case_input["customer_request"]["claimed_order_id"]

            try:
                # Điều phối xử lý
                case_result = self.process_single_case(case_id, case_input)

                # Write Case Output JSON
                output_file = os.path.join(self.output_dir, f"{case_id}.json")
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(case_result, f, ensure_ascii=False, indent=2)

                # Record Trace Log
                trace_logs.append({
                    "case_id": case_id,
                    "claimed_order_id": claimed_order_id,
                    "primary_issue": case_result["assessment"]["primary_issue"],
                    "case_status": case_result["assessment"]["case_status"],
                    "recommended_refund": case_result["financial_resolution"]["recommended_refund_brl"],
                    "execution_status": "SUCCESS"
                })

                print(f"  ✅ [{case_id}] Order: {claimed_order_id} -> Issue: {case_result['assessment']['primary_issue']}")

            except Exception as e:
                print(f"  ❌ [{case_id}] Lỗi xử lý: {str(e)}")
                trace_logs.append({
                    "case_id": case_id,
                    "claimed_order_id": claimed_order_id,
                    "execution_status": "FAILED",
                    "error": str(e)
                })

        # Ghi Trace Log duy nhất lượt chạy mới nhất ra trace.jsonl
        print("\n📝 [Coordinator] Đang xuất file trace.jsonl...")
        with open("trace.jsonl", "w", encoding="utf-8") as f:
            for log in trace_logs:
                f.write(json.dumps(log, ensure_ascii=False) + "\n")

        # Nén thư mục output thành output.zip
        self.package_output_zip()

    def package_output_zip(self):
        """Đóng gói chính xác 50 file JSON trong output/ thành file output.zip."""
        zip_path = "output.zip"
        print(f"📦 [Coordinator] Đang đóng gói thư mục '{self.output_dir}/' thành {zip_path}...")

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            files = sorted(os.listdir(self.output_dir))
            for file_name in files:
                if file_name.endswith(".json"):
                    file_path = os.path.join(self.output_dir, file_name)
                    # Chỉ đưa file JSON trực tiếp vào root của zip file
                    zipf.write(file_path, arcname=file_name)

        print(f"✨ [Coordinator] Hoàn tất! Zip file chứa {len(files)} file JSON.")


if __name__ == "__main__":
    coordinator = CoordinatorAgent()
    coordinator.run_all_cases(total_cases=50)
import json
import os
from typing import Dict, Any, List
# Sử dụng thư viện LLM tiêu chuẩn (OpenAI API / LiteLLM / Ollama)
from openai import OpenAI



class LLMCoordinatorAgent:
    """Coordinator Agent nâng cấp kết hợp LLM làm Supervisor điều phối luồng."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "openai_key"))

        # Khởi tạo các Specialist Agent đóng vai trò làm Tools
        self.order_seller_agent = OrderSellerAgent(data_dir=data_dir)
        self.payment_agent = PaymentAgent(data_dir=data_dir)
        self.delivery_agent = DeliveryAgent()
        self.policy_agent = PolicyAgent()
        self.verifier_agent = VerifierAgent()

    def _extract_intent_and_order_id(self, user_text: str) -> Dict[str, Any]:
        """Sử dụng LLM để trích xuất order_id và phân tích ý định từ văn bản tự do."""
        prompt = f"""
        Bạn là hệ thống phân tích phản hồi khách hàng sàn thương mại điện tử Olist.
        Hãy đọc đoạn tin nhắn khiếu nại sau và trích xuất thông tin dưới dạng JSON:
        
        Tin nhắn khách hàng: "{user_text}"
        
        Yêu cầu trả về đúng định dạng JSON:
        {{
            "claimed_order_id": "Mã order 32 ký tự Hex (nếu có, nếu không trả về null)",
            "customer_sentiment": "VERY_NEGATIVE | NEGATIVE | NEUTRAL",
            "perceived_issue": "Mô tả tóm tắt vấn đề bằng 1 câu"
        }}
        """
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        return json.loads(response.choices[0].message.content)

    def process_natural_case(self, case_id: str, raw_input: Dict[str, Any]) -> Dict[str, Any]:
        """Điều phối xử lý 1 case từ dữ liệu chưa cấu trúc bằng LLM + Specialist Agents."""
        user_message = raw_input.get("customer_request", {}).get("customer_message", "")
        fallback_order_id = raw_input.get("customer_request", {}).get("claimed_order_id")

        # -------------------------------------------------------------
        # STEP 1: LLM Phân tích bức xúc & Trích xuất Order ID
        # -------------------------------------------------------------
        print(f"\n🧠 [LLM Coordinator] Đang đọc hiểu tin nhắn case {case_id}...")
        extracted_info = self._extract_intent_and_order_id(user_message)
        
        claimed_order_id = extracted_info.get("claimed_order_id") or fallback_order_id
        
        print(f"  🔍 Trích xuất Order ID: {claimed_order_id}")
        print(f"  😠 Cảm xúc: {extracted_info.get('customer_sentiment')}")
        print(f"  📌 Vấn đề nhận diện: {extracted_info.get('perceived_issue')}")

        # Chuẩn hóa case input cho các agent bên dưới
        structured_case_input = {
            "case_id": case_id,
            "customer_request": {
                "claimed_order_id": claimed_order_id
            }
        }

        # -------------------------------------------------------------
        # STEP 2: Điều phối các Specialist Agents (Deterministic Execution)
        # -------------------------------------------------------------
        print("🤖 [LLM Coordinator] Kích hoạt các Specialist Agents tra cứu DB...")
        
        # 1. Order/Seller Agent
        order_info = self.order_seller_agent.process_case(structured_case_input)

        # 2. Payment Agent
        payment_info = self.payment_agent.process_case(structured_case_input)

        # 3. Delivery Agent
        delivery_info = self.delivery_agent.process_delivery_analysis(order_info)

        # -------------------------------------------------------------
        # STEP 3: Áp dụng Policy Rules & Verifier
        # -------------------------------------------------------------
        print("⚖️  [LLM Coordinator] Chuyển thông tin cho Policy Agent đánh giá...")
        policy_res = self.policy_agent.evaluate_policy(order_info, payment_info, delivery_info)

        # 4. Verifier Agent kiểm tra Schema & loại bỏ lỗi False Positive
        verified_output = self.verifier_agent.verify_and_build(
            case_id=case_id,
            claimed_order_id=claimed_order_id,
            order_info=order_info,
            payment_info=payment_info,
            policy_res=policy_res,
        )

        final_result = verified_output.model_dump()

        # -------------------------------------------------------------
        # STEP 4: LLM Soạn phản hồi cá nhân hóa cho Khách hàng
        # -------------------------------------------------------------
        final_result["customer_response_letter"] = self._generate_empathetic_reply(
            user_message=user_message,
            resolution=final_result
        )

        return final_result

    def _generate_empathetic_reply(self, user_message: str, resolution: Dict[str, Any]) -> str:
        """Sử dụng LLM viết thư phản hồi lịch sự dựa trên kết quả xử lý chính xác."""
        issue = resolution["assessment"]["primary_issue"]
        refund = resolution["financial_resolution"]["recommended_refund_brl"]
        
        prompt = f"""
        Soạn câu trả lời hỗ trợ khách hàng dựa trên kết quả xử lý khiếu nại:
        - Tin nhắn gốc của khách: "{user_message}"
        - Mã vấn đề xác định: {issue}
        - Số tiền hoàn trả: {refund} BRL
        
        Yêu cầu: Ngắn gọn, chuyên nghiệp, thể hiện sự xin lỗi nếu có lỗi từ sàn/người bán.
        """
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        return response.choices[0].message.content