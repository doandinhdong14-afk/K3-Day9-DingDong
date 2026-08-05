import os
import json
import sys
import time
import argparse

# Force UTF-8 stdout for Windows consoles
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add src folder to python path to resolve imports when running from repo root
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import init_db, get_order_context
from agents import CoordinatorAgent
from utils import write_trace_case, initialize_trace_file, write_metadata, package_submission

# Paths in the Lead's repository
REPO_DIR = r"c:\AIThucChien\K3-Day9-DingDong"
INPUT_DIR = os.path.join(REPO_DIR, "input")
OUTPUT_DIR = os.path.join(REPO_DIR, "output")

def process_single_case(case_id):
    """Process a single JSON ticket file by case_id."""
    input_file = os.path.join(INPUT_DIR, f"{case_id}.json")
    if not os.path.exists(input_file):
        print(f"Error: Input file for {case_id} not found at {input_file}")
        return False
        
    print(f"\n==================== PROCESSING CASE: {case_id} ====================")
    
    # Load input ticket
    with open(input_file, 'r', encoding='utf-8') as f:
        ticket = json.load(f)
        
    claimed_order_id = ticket.get("customer_request", {}).get("claimed_order_id", "")
    customer_request = ticket.get("customer_request", {})
    
    # Query database for this order_id
    order_ctx = get_order_context(claimed_order_id)
    
    if not order_ctx:
        # Construct a fallback minimal context if order is not in database
        print(f"Warning: claimed_order_id '{claimed_order_id}' not found in database!")
        order_ctx = {
            "order_id": claimed_order_id,
            "order": {"order_id": claimed_order_id, "order_status": "unknown"},
            "items": [],
            "payments": [],
            "sellers": [],
            "products": []
        }
        
    # Instantiate coordinator and run multi-agent resolution
    coordinator = CoordinatorAgent()
    final_output, trace_steps = coordinator.resolve_case(case_id, customer_request, order_ctx)
    
    # Save the output JSON file
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_file = os.path.join(OUTPUT_DIR, f"{case_id}.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_output, f, indent=2, ensure_ascii=False)
    print(f"Output saved successfully to {output_file}")
    
    # Write trace to trace.jsonl
    write_trace_case(case_id, trace_steps)
    print(f"Trace logged to trace.jsonl for {case_id}")
    return True

def main():
    parser = argparse.ArgumentParser(description="Multi-Agent E-commerce Dispute Resolution Pipeline")
    parser.add_argument("--single", type=str, help="Process a single case (e.g. EC_001)")
    args = parser.parse_args()
    
    # Initialize DB (loads Olist CSV files into memory)
    init_db()
    
    if args.single:
        success = process_single_case(args.single)
        if success:
            print(f"\nSingle case run completed successfully!")
        else:
            print(f"\nSingle case run failed.")
            sys.exit(1)
    else:
        # Run entire batch of 50 tickets
        print("\nStarting batch run for 50 tickets...")
        start_time = time.time()
        
        # Clear/initialize trace.jsonl
        initialize_trace_file()
        
        success_count = 0
        for i in range(1, 51):
            case_id = f"EC_{i:03d}"
            try:
                if process_single_case(case_id):
                    success_count += 1
                # Small sleep to respect rate limits if calling external APIs
                time.sleep(0.5)
            except Exception as e:
                print(f"Exception occurred while processing {case_id}: {e}")
                
        end_time = time.time()
        total_runtime = end_time - start_time
        print(f"\nBatch processing finished! Successfully processed {success_count}/50 cases.")
        print(f"Total execution time: {total_runtime:.2f} seconds.")
        
        # Write metadata.json
        write_metadata(model_name="gemini-3.5-flash-lite", runtime_sec=total_runtime)
        
        # Package submission into submission.zip
        package_submission("submission.zip")

if __name__ == "__main__":
    main()
