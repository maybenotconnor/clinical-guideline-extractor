"""Page manifest for tracking pipeline state and enabling resume."""

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path


class PageStatus(str, Enum):
    PENDING = "pending"
    RENDERED = "rendered"
    EXTRACTED_A = "extracted_a"
    EXTRACTED_B = "extracted_b"
    EXTRACTED_BOTH = "extracted_both"
    DIFFED = "diffed"
    RESOLVED = "resolved"
    VALIDATED = "validated"
    REVIEWED = "reviewed"
    ASSEMBLED = "assembled"


@dataclass
class PageState:
    page_num: int
    status: PageStatus = PageStatus.PENDING
    claude_extracted: bool = False
    flash_extracted: bool = False
    flash_blocked: bool = False
    jaccard: float | None = None
    disagreement_count: int = 0
    drug_disagreements: int = 0
    resolution_method: str | None = None
    validation_findings: list[dict] = field(default_factory=list)
    review_tier: str | None = None
    review_decision: str | None = None


class Manifest:
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self._path = work_dir / "manifest.json"
        self.pages: dict[int, PageState] = {}
        self._load()

    def _load(self):
        if self._path.exists():
            data = json.loads(self._path.read_text())
            for page_data in data.get("pages", []):
                ps = PageState(
                    page_num=page_data["page_num"],
                    status=PageStatus(page_data.get("status", "pending")),
                    claude_extracted=page_data.get("claude_extracted", False),
                    flash_extracted=page_data.get("flash_extracted", False),
                    flash_blocked=page_data.get("flash_blocked", False),
                    jaccard=page_data.get("jaccard"),
                    disagreement_count=page_data.get("disagreement_count", 0),
                    drug_disagreements=page_data.get("drug_disagreements", 0),
                    resolution_method=page_data.get("resolution_method"),
                    validation_findings=page_data.get("validation_findings", []),
                    review_tier=page_data.get("review_tier"),
                    review_decision=page_data.get("review_decision"),
                )
                self.pages[ps.page_num] = ps

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"pages": [asdict(ps) for ps in sorted(self.pages.values(), key=lambda p: p.page_num)]}
        self._path.write_text(json.dumps(data, indent=2, default=str))

    def init_pages(self, total_pages: int):
        """Initialize manifest for all pages if not already present."""
        for i in range(1, total_pages + 1):
            if i not in self.pages:
                self.pages[i] = PageState(page_num=i)
        self.save()

    def get(self, page_num: int) -> PageState:
        return self.pages[page_num]

    def update(self, page_num: int, **kwargs):
        ps = self.pages[page_num]
        for k, v in kwargs.items():
            setattr(ps, k, v)
        self.save()

    def pages_at_status(self, status: PageStatus) -> list[int]:
        return sorted(p.page_num for p in self.pages.values() if p.status == status)

    def pages_needing(self, min_status: PageStatus) -> list[int]:
        """Return pages that haven't reached the given status yet."""
        status_order = list(PageStatus)
        min_idx = status_order.index(min_status)
        return sorted(
            p.page_num for p in self.pages.values()
            if status_order.index(p.status) < min_idx
        )
