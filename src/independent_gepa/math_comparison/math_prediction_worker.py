"""Pinned native payload parser; initialization defects are never model errors."""
import json
import sys
from .math_domain_worker import initialize, parse_payload


def main():
    initialize()  # Dependency/runtime failures retain a nonzero exit.
    expression = json.load(sys.stdin)["expression"]
    try:
        values, valid = parse_payload(expression)
        reason = None if valid else "PAYLOAD_UNSUPPORTED" if values else "PAYLOAD_PARSE_FAILURE"
    except Exception:
        # Only native parsing of this prediction is inside this boundary.
        reason = "PAYLOAD_PARSE_FAILURE"
    json.dump(dict(invalid_reason=reason), sys.stdout)


if __name__ == "__main__":
    main()
