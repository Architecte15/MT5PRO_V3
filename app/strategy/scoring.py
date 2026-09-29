from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreItem:
    name: str
    points: int
    present: bool
    reason: str


@dataclass(frozen=True)
class SignalScore:
    total: int
    maximum_possible: int
    items: tuple[ScoreItem, ...]

    @property
    def missing(self) -> tuple[ScoreItem, ...]:
        return tuple(x for x in self.items if not x.present)


def compute_score(**features: bool) -> SignalScore:
    items = tuple(ScoreItem(name=k, points=1, present=bool(v), reason="confirmed" if v else "not confirmed") for k, v in features.items())
    return SignalScore(sum(i.points for i in items if i.present), len(items), items)
