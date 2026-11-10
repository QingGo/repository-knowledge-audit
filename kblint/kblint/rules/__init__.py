"""Rules package: R1-R9."""

from . import (r1_version, r2_number, r3_conflict, r4_supersedes, r5_expiry,
               r6_source_of_truth, r7_untracked, r8_audit_queue, r9_references)

# Ordered registry. Each module exposes run(ctx) -> list[Finding].
RULES = [
    ("R1", r1_version.run),
    ("R2", r2_number.run),
    ("R3", r3_conflict.run),
    ("R4", r4_supersedes.run),
    ("R5", r5_expiry.run),
    ("R6", r6_source_of_truth.run),
    ("R7", r7_untracked.run),
    ("R8", r8_audit_queue.run),
    ("R9", r9_references.run),
]

__all__ = ["RULES"]
