             ┌─────────────────────────────────────────┐
             │          Intent Agent (LLM)             │
             │ (Phân tích ý định & Trích xuất OrderID) │
             └────────────────────┬────────────────────┘
                                  │
                                  ▼
                  ┌──────────────────────────────┐
                  │    Coordinator Agent         │
                  │ (Phân tích Yêu cầu & Luồng)  │
                  └──────────────┬───────────────┘
                                 │
           ┌─────────────────────┼─────────────────────┐
           ▼                     ▼                     ▼
┌────────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│Order/Seller Agent  │ │   Payment Agent   │ │  Delivery Agent   │
│ - Trạng thái order │ │ - Sum payments    │ │ - Hand off vs Est │
│ - Items & Sellers  │ │ - Match vs items  │ │ - Delivered vs Est│
└──────────┬─────────┘ └─────────┬─────────┘ └─────────┬─────────┘
           │                     │                     │
           └─────────────────────┼─────────────────────┘
                                 │ (Handoff data/evidences)
                                 ▼
                  ┌──────────────────────────────┐
                  │        Policy Agent          │
                  │ - Áp dụng EC_POLICY_V1       │
                  │ - Xác định Issue, Refund,    │
                  │   Action, Root Cause         │
                  └──────────────┬───────────────┘
                                 │
                                 ▼
                  ┌──────────────────────────────┐
                  │        Verifier Agent        │
                  │ - Kiểm tra Schema & Bounds   │
                  │ - Trừ False Positives        │
                  └──────────────┬───────────────┘
                                 │
                                 ▼
                         Output JSON File
