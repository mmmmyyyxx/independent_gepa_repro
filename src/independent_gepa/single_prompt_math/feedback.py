"""Bounded task feedback only; no candidate content or legality filter."""
from ..protocol import ProtocolViolation


def worked_reference(solution):
    if not isinstance(solution,str) or not solution.strip():raise ProtocolViolation('DATASET_WORKED_REFERENCE_REQUIRED')
    return {'source':'dataset_worked_solution','split':'optimize','text':solution[:4096],
            'original_characters':len(solution),'truncated':len(solution)>4096}
