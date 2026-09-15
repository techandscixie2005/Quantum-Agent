"""Read-only manifest/schema/hash check; does not approve or publish anything."""
import argparse
from pathlib import Path
from quantum_agent.knowledge.barrier_scope import load_reviews

parser = argparse.ArgumentParser()
parser.add_argument('manifest', type=Path)
parser.add_argument('sha256', help='independently reviewed and pinned SHA-256')
args = parser.parse_args()
reviews = load_reviews(args.manifest, args.sha256)
print(f'Valid production-format entries: {len(reviews)}; no approval/publication performed.')
for review in reviews:
    print(review.evidence_id, review.document_version_id, review.approved_widths_m)
print('Runtime still checks course/publication, grounded evidence, version and all source hashes.')
