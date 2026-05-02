from dataclasses import dataclass

from src.models.enums import Category, Priority
from src.schemas.classification import ClassificationResult


@dataclass(frozen=True)
class _PriorityScore:
    priority: Priority
    confidence: float
    reasoning: str
    keywords: list[str]


@dataclass(frozen=True)
class _CategoryScore:
    category: Category
    confidence: float
    reasoning: str
    keywords: list[str]


class PriorityClassifier:
    KEYWORDS: dict[Priority, list[str]] = {
        Priority.URGENT: [
            "can't access", "cannot access", "critical", "production down", "security"
        ],
        Priority.HIGH: ["important", "blocking", "asap"],
        Priority.LOW: ["minor", "cosmetic", "suggestion"],
    }
    PRECEDENCE = (Priority.URGENT, Priority.HIGH, Priority.LOW)

    def classify(self, text: str) -> _PriorityScore:
        normalized = text.lower()
        for priority in self.PRECEDENCE:
            matches = [kw for kw in self.KEYWORDS[priority] if kw in normalized]
            if matches:
                total = len(self.KEYWORDS[priority])
                return _PriorityScore(
                    priority=priority,
                    confidence=min(1.0, len(matches) / total),
                    reasoning=(
                        f"Matched {len(matches)}/{total} '{priority.value}' keyword(s): "
                        f"{', '.join(matches)}"
                    ),
                    keywords=matches,
                )
        return _PriorityScore(
            priority=Priority.MEDIUM,
            confidence=0.5,
            reasoning="No priority keywords matched; using default 'medium'",
            keywords=[],
        )


class CategoryClassifier:
    KEYWORDS: dict[Category, list[str]] = {
        Category.ACCOUNT_ACCESS: [
            "login", "log in", "logged out", "log out", "password", "passwd",
            "2fa", "two-factor", "two factor", "authentication",
            "account locked", "locked out", "can't access", "cannot access",
            "sign in", "sign-in", "reset password",
        ],
        Category.TECHNICAL_ISSUE: [
            "bug", "error", "crash", "crashed", "exception", "broken",
            "doesn't work", "not working", "fails", "failed",
            "stack trace", "500", "404", "timeout",
        ],
        Category.BILLING_QUESTION: [
            "payment", "invoice", "refund", "charge", "billing",
            "subscription", "credit card", "paid", "discount",
        ],
        Category.FEATURE_REQUEST: [
            "feature request", "enhancement", "suggest", "wish",
            "would like", "would be nice", "could you add", "please add",
            "add support for", "support for",
        ],
        Category.BUG_REPORT: [
            "reproduce", "steps to reproduce", "expected", "actual",
            "regression", "defect", "repro",
        ],
    }

    def classify(self, text: str) -> _CategoryScore:
        normalized = text.lower()
        scores: dict[Category, list[str]] = {}
        for category, kws in self.KEYWORDS.items():
            matches = [kw for kw in kws if kw in normalized]
            if matches:
                scores[category] = matches

        if not scores:
            return _CategoryScore(
                category=Category.OTHER,
                confidence=0.5,
                reasoning="No category keywords matched; using default 'other'",
                keywords=[],
            )

        best_category, best_matches = max(scores.items(), key=lambda kv: len(kv[1]))
        total = len(self.KEYWORDS[best_category])
        return _CategoryScore(
            category=best_category,
            confidence=min(1.0, len(best_matches) / total),
            reasoning=(
                f"Matched {len(best_matches)}/{total} '{best_category.value}' keyword(s): "
                f"{', '.join(best_matches)}"
            ),
            keywords=best_matches,
        )


class TicketClassifier:
    def __init__(
        self,
        priority_classifier: PriorityClassifier | None = None,
        category_classifier: CategoryClassifier | None = None,
    ) -> None:
        self.priority_classifier = priority_classifier or PriorityClassifier()
        self.category_classifier = category_classifier or CategoryClassifier()

    def classify(self, subject: str, description: str) -> ClassificationResult:
        text = f"{subject}\n{description}"
        priority_score = self.priority_classifier.classify(text)
        category_score = self.category_classifier.classify(text)

        confidence = (priority_score.confidence + category_score.confidence) / 2
        reasoning = (
            f"Priority: {priority_score.reasoning}. "
            f"Category: {category_score.reasoning}."
        )
        keywords = priority_score.keywords + category_score.keywords

        return ClassificationResult(
            category=category_score.category,
            priority=priority_score.priority,
            confidence=confidence,
            reasoning=reasoning,
            keywords_found=keywords,
        )
