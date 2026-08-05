import os
import json
import zipfile

# Paths in the Lead's repository
REPO_DIR = r"c:\AIThucChien\K3-Day9-DingDong"
LOGGING_DIR = os.path.join(REPO_DIR, "logging")
OUTPUT_DIR = os.path.join(REPO_DIR, "output")

def write_trace_case(case_id, trace_steps):
    """
    Append a single case's agent execution trace to logging/trace.jsonl.
    """
    os.makedirs(LOGGING_DIR, exist_ok=True)
    trace_file = os.path.join(LOGGING_DIR, "trace.jsonl")
    
    # We will write in append mode or rewrite depending on execution
    # For a fresh run, it's good to append or manage line by line
    row = {
        "case_id": case_id,
        "trace": trace_steps
    }
    with open(trace_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

def initialize_trace_file():
    """Clear existing trace.jsonl file before running the batch."""
    os.makedirs(LOGGING_DIR, exist_ok=True)
    trace_file = os.path.join(LOGGING_DIR, "trace.jsonl")
    with open(trace_file, "w", encoding="utf-8") as f:
        pass # Empty write to clear the file

def write_metadata(model_name="gemini-3.5-flash-lite", runtime_sec=0.0):
    """
    Generate the metadata.json file inside the logging folder.
    """
    os.makedirs(LOGGING_DIR, exist_ok=True)
    metadata_file = os.path.join(LOGGING_DIR, "metadata.json")
    
    metadata = {
        "cohort": "K3",
        "repo_starter": "K3-Day9-Multi-Agent-A2A",
        "policy_version": "EC_POLICY_V1",
        "model_name": model_name,
        "parameter_size": "under 10B (Mixture-of-Experts/Lite)",
        "framework": "google-generativeai SDK",
        "runtime_seconds": round(runtime_sec, 2)
    }
    
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"Metadata saved to {metadata_file}")

def package_submission(zip_filename="submission.zip"):
    zip_path = os.path.join(REPO_DIR, zip_filename)
    
    print(f"Packaging submission into {zip_path}...")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Only add output JSON files (folder structure: output/EC_001.json)
        if os.path.exists(OUTPUT_DIR):
            for root, _, files in os.walk(OUTPUT_DIR):
                for file in files:
                    if file.endswith(".json") and file.startswith("EC_"):
                        file_path = os.path.join(root, file)
                        # We want the folder structure: output/EC_001.json (using forward slash for Linux compatibility)
                        arcname = os.path.relpath(file_path, REPO_DIR).replace('\\', '/')
                        zipf.write(file_path, arcname)
                        
    print(f"Successfully created zip file: {zip_path}")
    return zip_path
