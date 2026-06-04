from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LearningResource:
    title: str
    source: str
    related_topics: list[str] = field(default_factory=list)
    chunk_id: str = ""


class ResourceAgent:
    def __init__(self, rag=None, allow_degraded: bool = True):
        self.rag = rag
        self.allow_degraded = allow_degraded

    def run(self, goal, knowledge_points: list | None = None) -> list[LearningResource]:
        if self.rag is None:
            return []
        try:
            query = " ".join([goal.subject, *[point.name for point in knowledge_points or []]])
            raw_results = self.rag.search(query)
        except Exception:
            if self.allow_degraded:
                return []
            raise
        resources: list[LearningResource] = []
        for item in raw_results:
            topics = item.get("related_topics") or [point.name for point in knowledge_points or []]
            resources.append(
                LearningResource(
                    title=item.get("title", ""),
                    source=item.get("source", ""),
                    related_topics=list(topics),
                    chunk_id=item.get("chunk_id", ""),
                )
            )
        return resources
