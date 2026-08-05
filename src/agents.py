import os
import json
import sys
import time
import google.generativeai as genai

# Force UTF-8 stdout for Windows consoles to prevent encoding errors
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Load API Key from .env
api_key = None
env_path = r"c:\AIThucChien\K3-Day9-DingDong\.env"
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith("GEMINI_API_KEY="):
                api_key = line.split("=")[1].strip()

if api_key:
    genai.configure(api_key=api_key)

MODEL_NAME = "gemini-3.5-flash-lite"

def call_llm(prompt, system_instruction=None, json_mode=False):
    """Utility function to call the Gemini model with a prompt and auto-retry for rate limits."""
    max_retries = 5
    base_delay = 10
    
    # Simple delay to maintain safety margin (strictly under 15 RPM)
    time.sleep(4.5)
    
    for attempt in range(max_retries):
        try:
            model = genai.GenerativeModel(
                model_name=MODEL_NAME,
                system_instruction=system_instruction
            )
            
            generation_config = {}
            if json_mode:
                generation_config["response_mime_type"] = "application/json"
                
            response = model.generate_content(
                prompt,
                generation_config=generation_config
            )
            return response.text.strip()
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "Quota exceeded" in err_msg:
                delay = base_delay * (attempt + 1)
                print(f" Rate limit hit. Waiting {delay}s before retry (Attempt {attempt+1}/{max_retries})...")
                time.sleep(delay)
            else:
                print(f"Error calling LLM ({MODEL_NAME}): {e}")
                return ""
                
    print("Max retries exceeded for LLM call.")
    return ""

class BaseAgent:
    def __init__(self, name, role):
        self.name = name
        self.role = role
        self.trace_log = []

    def log(self, message):
        self.trace_log.append(message)

class OrderSellerAgent(BaseAgent):
    def __init__(self):
        super().__init__("Order & Seller Agent", "Phân tích đơn hàng và người bán")

    def run(self, order_ctx):
        self.log("Bắt đầu phân tích đơn hàng và người bán...")
        order = order_ctx.get('order', {})
        items = order_ctx.get('items', [])
        
        order_id = order.get('order_id', '')
        order_status = order.get('order_status', '')
        
        # Calculate seller delays safely
        seller_delays = []
        carrier_date = order.get('order_delivered_carrier_date', '')
        is_any_late = False
        
        for item in items:
            limit_date = item.get('shipping_limit_date', '')
            is_late = False
            if carrier_date and limit_date and isinstance(carrier_date, str) and isinstance(limit_date, str):
                is_late = carrier_date > limit_date
            if is_late:
                is_any_late = True
            seller_delays.append({
                "item_id": f"{order_id}:{item.get('order_item_id', 1)}",
                "seller_id": item.get('seller_id', ''),
                "shipping_limit_date": limit_date if isinstance(limit_date, str) else "",
                "order_delivered_carrier_date": carrier_date if isinstance(carrier_date, str) else "",
                "is_late": is_late
            })
            
        facts = {
            "order_id": order_id,
            "order_status": order_status,
            "seller_delays": seller_delays,
            "items_count": len(items)
        }
        
        # Generate report instantly via deterministic template (Optimized!)
        late_desc = "Người bán có bàn giao cho vận chuyển muộn hơn hạn quy định (shipping_limit_date)." if is_any_late else "Người bán đã bàn giao hàng đúng hạn cho đơn vị vận chuyển."
        report = (
            f"### BÁO CÁO PHÂN TÍCH ĐƠN HÀNG VÀ NGƯỜI BÁN\n"
            f"1. Trạng thái đơn hàng: {order_status}\n"
            f"2. Đánh giá giao hàng của Người bán: {late_desc}\n"
            f"3. Danh sách bằng chứng (Evidence IDs):\n"
            f"   - order:{order_id}\n"
        )
        for s in seller_delays:
            report += f"   - item:{order_id}:{s['item_id'].split(':')[-1]}\n"
            report += f"   - seller:{s['seller_id']}\n"
            
        self.log(f"Báo cáo phân tích: {report}")
        return {
            "agent_name": self.name,
            "facts": facts,
            "report": report
        }

class PaymentAgent(BaseAgent):
    def __init__(self):
        super().__init__("Payment Agent", "Phân tích giao dịch thanh toán")

    def run(self, order_ctx):
        self.log("Bắt đầu đối soát thanh toán...")
        order_id = order_ctx.get('order_id', '')
        payments = order_ctx.get('payments', [])
        items = order_ctx.get('items', [])
        
        # Calculate total payments
        total_payment = sum(p.get('payment_value', 0.0) for p in payments)
        
        # Calculate total items price and freight
        total_items_price = sum(item.get('price', 0.0) for item in items)
        total_freight = sum(item.get('freight_value', 0.0) for item in items)
        total_calculated = total_items_price + total_freight
        
        # Check split payment
        is_split = len(payments) >= 2
        payment_reconciled = abs(total_payment - total_calculated) <= 0.10
        
        facts = {
            "order_id": order_id,
            "payments_count": len(payments),
            "payment_total_brl": round(total_payment, 2),
            "item_total_brl": round(total_items_price, 2),
            "freight_total_brl": round(total_freight, 2),
            "total_calculated_brl": round(total_calculated, 2),
            "is_split_payment": is_split,
            "payment_reconciled": payment_reconciled,
            "payments_details": [{"seq": p.get('payment_sequential', 1), "value": p.get('payment_value', 0.0)} for p in payments]
        }
        
        # Generate report instantly via deterministic template (Optimized!)
        reconcile_desc = f"Khớp hoàn toàn (Tổng tính toán: {facts['total_calculated_brl']} BRL, Khách trả: {facts['payment_total_brl']} BRL)." if payment_reconciled else f"Có sự lệch tiền (Tính toán: {facts['total_calculated_brl']} BRL, Khách trả: {facts['payment_total_brl']} BRL)."
        split_desc = "Có (Khách hàng thanh toán chia nhiều đợt)." if is_split else "Không (Khách hàng trả hết trong 1 lần)."
        
        report = (
            f"### BÁO CÁO ĐỐI SOÁT THANH TOÁN\n"
            f"1. Khớp số tiền thanh toán: {reconcile_desc}\n"
            f"2. Thanh toán chia đợt: {split_desc}\n"
            f"3. Danh sách bằng chứng (Evidence IDs):\n"
        )
        for p in payments:
            report += f"   - payment:{order_id}:{p.get('payment_sequential', 1)}\n"
            
        self.log(f"Báo cáo đối soát: {report}")
        return {
            "agent_name": self.name,
            "facts": facts,
            "report": report
        }

class DeliveryAgent(BaseAgent):
    def __init__(self):
        super().__init__("Delivery Agent", "Phân tích tiến độ giao hàng")

    def run(self, order_ctx):
        self.log("Bắt đầu đối soát thời gian giao hàng...")
        order = order_ctx.get('order', {})
        order_id = order.get('order_id', '')
        
        delivered_date = order.get('order_delivered_customer_date', '')
        estimated_date = order.get('order_estimated_delivery_date', '')
        
        is_late = False
        if delivered_date and estimated_date and isinstance(delivered_date, str) and isinstance(estimated_date, str):
            is_late = delivered_date > estimated_date
            
        facts = {
            "order_id": order_id,
            "order_delivered_customer_date": delivered_date if isinstance(delivered_date, str) else "",
            "order_estimated_delivery_date": estimated_date if isinstance(estimated_date, str) else "",
            "is_delivery_late": is_late
        }
        
        # Generate report instantly via deterministic template (Optimized!)
        late_desc = f"Đơn hàng được giao TRỄ HẠN (Giao thực tế: {delivered_date}, Dự kiến: {estimated_date})." if is_late else f"Đơn hàng giao ĐÚNG HẠN hoặc TRƯỚC HẠN (Giao thực tế: {delivered_date}, Dự kiến: {estimated_date})."
        report = (
            f"### BÁO CÁO PHÂN TÍCH THỜI GIAN GIAO HÀNG\n"
            f"1. Trạng thái giao hàng thực tế: {late_desc}\n"
            f"2. Danh sách bằng chứng (Evidence IDs):\n"
            f"   - order:{order_id}\n"
        )
        
        self.log(f"Báo cáo giao hàng: {report}")
        return {
            "agent_name": self.name,
            "facts": facts,
            "report": report
        }

class PolicyAgent(BaseAgent):
    def __init__(self):
        super().__init__("Policy Agent", "Áp dụng chính sách giải quyết tranh chấp")

    def run(self, order_ctx, order_report, payment_report, delivery_report):
        self.log("Bắt đầu áp dụng chính sách EC_POLICY_V1...")
        
        # Extract facts from agents
        order_facts = order_report['facts']
        payment_facts = payment_report['facts']
        delivery_facts = delivery_report['facts']
        
        order_id = order_facts['order_id']
        order_status = order_facts['order_status']
        items_count = order_facts['items_count']
        
        is_split = payment_facts['is_split_payment']
        payment_reconciled = payment_facts['payment_reconciled']
        payment_total = payment_facts['payment_total_brl']
        freight_total = payment_facts['freight_total_brl']
        item_total = payment_facts['item_total_brl']
        
        is_delivery_late = delivery_facts['is_delivery_late']
        
        # Check if seller handoff is late
        is_seller_late = False
        seller_id = ""
        for s in order_facts['seller_delays']:
            if s['is_late']:
                is_seller_late = True
                seller_id = s['seller_id'] # Gán đúng seller bị trễ bàn giao
                
        # Apply Policy logic strictly
        primary_issue = ""
        case_status = "no_action"
        recommended_refund = 0.0
        responsible_party_type = ""
        responsible_party_id = ""
        root_cause_code = ""
        action = ""
        
        # Rule 1: canceled_order_paid
        if order_status == 'canceled' and payment_total > 0:
            primary_issue = "canceled_order_paid"
            case_status = "action_required"
            recommended_refund = payment_total
            responsible_party_type = "platform"
            responsible_party_id = "OLIST_PLATFORM"
            root_cause_code = "ORDER_CANCELED_AFTER_PAYMENT"
            action = "issue_full_refund"
            
        # Rule 2: unavailable_order_paid
        elif order_status == 'unavailable' and payment_total > 0:
            primary_issue = "unavailable_order_paid"
            case_status = "action_required"
            recommended_refund = payment_total
            responsible_party_type = "platform"
            responsible_party_id = "OLIST_PLATFORM"
            root_cause_code = "ORDER_UNAVAILABLE_AFTER_PAYMENT"
            action = "issue_full_refund"
            
        # Rule 3: late_delivery_seller
        elif is_delivery_late and is_seller_late:
            primary_issue = "late_delivery_seller"
            case_status = "action_required"
            recommended_refund = freight_total
            responsible_party_type = "seller"
            responsible_party_id = seller_id if seller_id else "unknown_seller"
            root_cause_code = "SELLER_HANDOFF_AFTER_LIMIT"
            action = "refund_freight"
            
        # Rule 4: late_delivery_logistics
        elif is_delivery_late and not is_seller_late:
            primary_issue = "late_delivery_logistics"
            case_status = "action_required"
            recommended_refund = freight_total
            responsible_party_type = "logistics_provider"
            responsible_party_id = "LOGISTICS_PROVIDER"
            root_cause_code = "CARRIER_DELIVERED_AFTER_ESTIMATE"
            action = "refund_freight"
            
        # Rule 5: valid_split_payment
        elif is_split and payment_reconciled:
            primary_issue = "valid_split_payment"
            case_status = "no_action"
            recommended_refund = 0.0
            responsible_party_type = ""
            responsible_party_id = ""
            root_cause_code = "MULTIPLE_PAYMENTS_RECONCILED"
            action = "explain_valid_split_payment"
            
        # Rule 6: unsupported_late_claim
        else:
            primary_issue = "unsupported_late_claim"
            case_status = "no_action"
            recommended_refund = 0.0
            responsible_party_type = ""
            responsible_party_id = ""
            root_cause_code = "DELIVERY_WITHIN_ESTIMATE"
            action = "reject_late_refund"

        # Build evidence list and affected entities based on primary issue (Optimized to prevent False Positives!)
        evidence_ids = []
        item_ids = []
        seller_ids = []
        payment_ids = [f"{order_id}:{p.get('payment_sequential', 1)}" for p in order_ctx.get('payments', [])][:5]
        
        evidence_ids.append(f"order:{order_id}")
        for p in order_ctx.get('payments', []):
            evidence_ids.append(f"payment:{order_id}:{p.get('payment_sequential', 1)}")

        if primary_issue == "late_delivery_seller":
            # For seller delays, only include late items and late sellers
            for s in order_facts.get('seller_delays', []):
                if s['is_late']:
                    item_id_str = s['item_id']
                    item_ids.append(item_id_str)
                    evidence_ids.append(f"item:{item_id_str}")
                    
                    if s['seller_id'] and s['seller_id'] not in seller_ids:
                        seller_ids.append(s['seller_id'])
                        evidence_ids.append(f"seller:{s['seller_id']}")
        
        # Add policy code
        evidence_ids.append(f"policy:{root_cause_code}")
        
        # Deduplicate and limit size strictly
        unique_evidences = []
        for ev in evidence_ids:
            if ev not in unique_evidences:
                unique_evidences.append(ev)
        evidence_ids = unique_evidences[:10]

        decision = {
            "case_id": "",
            "assessment": {
                "primary_issue": primary_issue,
                "case_status": case_status,
                "confidence": 0.95
            },
            "affected_entities": {
                "order_ids": [order_id],
                "item_ids": item_ids[:5],
                "seller_ids": seller_ids[:5],
                "payment_ids": payment_ids
            },
            "root_cause_analysis": {
                "ranked_causes": [
                    { "cause_code": root_cause_code, "rank": 1 }
                ],
                "responsible_parties": [
                    { "party_type": responsible_party_type, "party_id": responsible_party_id }
                ] if responsible_party_type else []
            },
            "evidence_ids": evidence_ids,
            "financial_resolution": {
                "currency": "BRL",
                "item_total_brl": round(item_total, 2),
                "freight_total_brl": round(freight_total, 2),
                "payment_total_brl": round(payment_total, 2),
                "recommended_refund_brl": round(recommended_refund, 2)
            },
            "resolution_actions": [action]
        }
        
        # Policy Agent calls LLM to explain the final decision (Optimized: Only 1 LLM call per case!)
        prompt = f"""
        Bạn là Policy Agent. Hãy phân tích các báo cáo từ các agent khác và kết luận sơ bộ dưới đây để viết một đoạn giải thích chi tiết, thuyết phục và ngắn gọn lý do áp dụng chính sách này.
        Dữ liệu kết luận: {json.dumps(decision, indent=2)}
        Báo cáo của các Agent nghiệp vụ khác:
        - Order Agent: {order_report['report']}
        - Payment Agent: {payment_report['report']}
        - Delivery Agent: {delivery_report['report']}
        
        Hãy viết đoạn giải thích này bằng tiếng Việt, ngắn gọn trong khoảng 2-3 câu, chỉ rõ lý do vì sao lỗi thuộc về bên đó và phương án xử lý (hoàn tiền ship, hoàn toàn bộ tiền hay từ chối).
        """
        
        explanation = call_llm(prompt, system_instruction="Bạn là chuyên gia tư vấn chính sách giải quyết khiếu nại khách hàng của Olist.")
        self.log(f"Giải thích chính sách: {explanation}")
        
        decision["explanation"] = explanation
        return decision

class VerifierAgent(BaseAgent):
    def __init__(self):
        super().__init__("Verifier Agent", "Kiểm tra định dạng và tính chính xác của dữ liệu")

    def run(self, decision, order_ctx):
        self.log("Bắt đầu kiểm chứng dữ liệu trước khi xuất file...")
        errors = []
        
        items_in_db = [f"{order_ctx['order_id']}:{item.get('order_item_id')}" for item in order_ctx.get('items', [])]
        payments_in_db = [f"{order_ctx['order_id']}:{p.get('payment_sequential')}" for p in order_ctx.get('payments', [])]
        sellers_in_db = [item.get('seller_id') for item in order_ctx.get('items', [])]
        
        verified_evidences = []
        for ev in decision.get("evidence_ids", []):
            parts = ev.split(":")
            if parts[0] == "order":
                if parts[1] != order_ctx["order_id"]:
                    errors.append(f"Sai mã order_id trong evidence: {ev}")
                else:
                    verified_evidences.append(ev)
            elif parts[0] == "item":
                matched = False
                for it_in_db in items_in_db:
                    db_parts = it_in_db.split(":")
                    if db_parts[0] == parts[1] and str(db_parts[1]) == str(parts[2]):
                        matched = True
                if not matched:
                    errors.append(f"Mã item không tồn tại trong DB: {ev}")
                else:
                    verified_evidences.append(ev)
            elif parts[0] == "payment":
                matched = False
                for py_in_db in payments_in_db:
                    db_parts = py_in_db.split(":")
                    if db_parts[0] == parts[1] and str(db_parts[1]) == str(parts[2]):
                        matched = True
                if not matched:
                    errors.append(f"Mã payment không tồn tại trong DB: {ev}")
                else:
                    verified_evidences.append(ev)
            elif parts[0] == "seller":
                if parts[1] not in sellers_in_db:
                    errors.append(f"Mã seller không tồn tại trong DB: {ev}")
                else:
                    verified_evidences.append(ev)
            else:
                verified_evidences.append(ev)
                
        decision["evidence_ids"] = verified_evidences
        
        fin = decision["financial_resolution"]
        fin["item_total_brl"] = float(fin["item_total_brl"])
        fin["freight_total_brl"] = float(fin["freight_total_brl"])
        fin["payment_total_brl"] = float(fin["payment_total_brl"])
        fin["recommended_refund_brl"] = float(fin["recommended_refund_brl"])
        
        decision["affected_entities"]["order_ids"] = decision["affected_entities"]["order_ids"][:5]
        decision["affected_entities"]["item_ids"] = decision["affected_entities"]["item_ids"][:5]
        decision["affected_entities"]["seller_ids"] = decision["affected_entities"]["seller_ids"][:5]
        decision["affected_entities"]["payment_ids"] = decision["affected_entities"]["payment_ids"][:5]
        
        decision["evidence_ids"] = decision["evidence_ids"][:10]
        decision["root_cause_analysis"]["ranked_causes"] = decision["root_cause_analysis"]["ranked_causes"][:3]
        decision["root_cause_analysis"]["responsible_parties"] = decision["root_cause_analysis"]["responsible_parties"][:3]
        decision["resolution_actions"] = decision["resolution_actions"][:5]
        
        explanation = decision.pop("explanation", "")
        self.log(f"Kiểm chứng hoàn tất. Số lỗi phát hiện: {len(errors)}")
        return decision, errors, explanation

class CoordinatorAgent:
    def __init__(self):
        self.name = "Coordinator Agent"
        self.role = "Điều phối luồng công việc Multi-Agent"
        
    def resolve_case(self, case_id, customer_request, order_ctx):
        trace = []
        
        # Step 1: Receipt
        trace.append({
            "step": "1. Receipt",
            "agent": self.name,
            "message": f"Coordinator nhận ticket {case_id} xử lý đơn hàng {customer_request['claimed_order_id']}."
        })
        
        # Step 2: Order Analysis
        order_agent = OrderSellerAgent()
        order_res = order_agent.run(order_ctx)
        trace.append({
            "step": "2. Order Analysis",
            "agent": order_agent.name,
            "message": order_res['report']
        })
        
        # Step 3: Payment Audit
        payment_agent = PaymentAgent()
        payment_res = payment_agent.run(order_ctx)
        trace.append({
            "step": "3. Payment Audit",
            "agent": payment_agent.name,
            "message": payment_res['report']
        })
        
        # Step 4: Delivery Audit
        delivery_agent = DeliveryAgent()
        delivery_res = delivery_agent.run(order_ctx)
        trace.append({
            "step": "4. Delivery Audit",
            "agent": delivery_agent.name,
            "message": delivery_res['report']
        })
        
        # Step 5: Policy Decision
        policy_agent = PolicyAgent()
        decision = policy_agent.run(order_ctx, order_res, payment_res, delivery_res)
        decision["case_id"] = case_id
        trace.append({
            "step": "5. Policy Decision",
            "agent": policy_agent.name,
            "message": decision["explanation"]
        })
        
        # Step 6: Verification
        verifier_agent = VerifierAgent()
        final_output, errors, explanation = verifier_agent.run(decision, order_ctx)
        trace.append({
            "step": "6. Verification",
            "agent": verifier_agent.name,
            "message": f"Verifier hoàn thành kiểm tra. Lỗi: {len(errors)}. Bản giải thích: {explanation}"
        })
        
        return final_output, trace
