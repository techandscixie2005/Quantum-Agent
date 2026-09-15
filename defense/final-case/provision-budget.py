"""Explicit one-time ledger provisioning, only after human recording authorization."""
import argparse
from pathlib import Path
from uuid import UUID
from quantum_agent.llm.recording_budget import RecordingBudget

parser = argparse.ArgumentParser()
parser.add_argument('path', type=Path)
parser.add_argument('run_id', type=UUID)
parser.add_argument('--requests', type=int, required=True)
parser.add_argument('--seconds', type=float, default=600)
parser.add_argument('--output-tokens', type=int, default=2048)
parser.add_argument('--request-bytes', type=int, default=65536)
args = parser.parse_args()
RecordingBudget.provision(args.path, str(args.run_id), requests=args.requests,
                          seconds=args.seconds, output_tokens=args.output_tokens,
                          request_bytes=args.request_bytes)
print('Ledger created; deadline starts now. No model request sent. Existing path cannot refill.')
