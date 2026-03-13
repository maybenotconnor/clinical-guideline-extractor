"""Track API token usage and costs across the pipeline."""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


# Pricing per 1M tokens (as of March 2026)
PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "gemini-3-flash-preview": {"input": 0.10, "output": 0.40},
    "gemini-3.1-pro-preview": {"input": 1.25, "output": 5.00},
}


@dataclass
class APICall:
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    stage: str
    page: int | None = None
    timestamp: float = field(default_factory=time.time)


class CostTracker:
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.calls: list[APICall] = []
        self._log_path = work_dir / "cost-log.jsonl"
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_existing()

    def _load_existing(self):
        """Load prior calls from the JSONL log so costs accumulate across runs."""
        if not self._log_path.exists():
            return
        for line in self._log_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                self.calls.append(APICall(
                    model=data["model"],
                    input_tokens=data["input_tokens"],
                    output_tokens=data["output_tokens"],
                    cost=data["cost"],
                    stage=data["stage"],
                    page=data.get("page"),
                    timestamp=data.get("timestamp", 0),
                ))
            except (json.JSONDecodeError, KeyError):
                continue

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        stage: str,
        page: int | None = None,
    ) -> float:
        pricing = PRICING.get(model, {"input": 0, "output": 0})
        cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000

        call = APICall(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            stage=stage,
            page=page,
        )
        self.calls.append(call)

        with open(self._log_path, "a") as f:
            f.write(json.dumps({
                "model": call.model,
                "input_tokens": call.input_tokens,
                "output_tokens": call.output_tokens,
                "cost": round(call.cost, 6),
                "stage": call.stage,
                "page": call.page,
                "timestamp": call.timestamp,
            }) + "\n")

        return cost

    def total_cost(self) -> float:
        return sum(c.cost for c in self.calls)

    def summary(self) -> dict:
        by_model: dict[str, dict] = {}
        by_stage: dict[str, dict] = {}

        for call in self.calls:
            # By model
            if call.model not in by_model:
                by_model[call.model] = {"input_tokens": 0, "output_tokens": 0, "cost": 0.0, "calls": 0}
            by_model[call.model]["input_tokens"] += call.input_tokens
            by_model[call.model]["output_tokens"] += call.output_tokens
            by_model[call.model]["cost"] += call.cost
            by_model[call.model]["calls"] += 1

            # By stage
            if call.stage not in by_stage:
                by_stage[call.stage] = {"input_tokens": 0, "output_tokens": 0, "cost": 0.0, "calls": 0}
            by_stage[call.stage]["input_tokens"] += call.input_tokens
            by_stage[call.stage]["output_tokens"] += call.output_tokens
            by_stage[call.stage]["cost"] += call.cost
            by_stage[call.stage]["calls"] += 1

        return {
            "total_cost": round(self.total_cost(), 4),
            "total_calls": len(self.calls),
            "by_model": {k: {**v, "cost": round(v["cost"], 4)} for k, v in by_model.items()},
            "by_stage": {k: {**v, "cost": round(v["cost"], 4)} for k, v in by_stage.items()},
        }
