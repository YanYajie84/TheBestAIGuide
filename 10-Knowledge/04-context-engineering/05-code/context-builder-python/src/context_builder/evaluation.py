from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EvidenceMetrics:
    required_count: int
    selected_count: int
    true_positive_count: int
    recall: float | None
    precision: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def evidence_metrics(required_ids: set[str], selected_ids: set[str]) -> EvidenceMetrics:
    overlap = required_ids & selected_ids
    recall = len(overlap) / len(required_ids) if required_ids else None
    precision = len(overlap) / len(selected_ids) if selected_ids else None
    return EvidenceMetrics(
        len(required_ids), len(selected_ids), len(overlap), recall, precision
    )
