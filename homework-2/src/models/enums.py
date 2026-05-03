from enum import Enum


class Category(str, Enum):
    ACCOUNT_ACCESS = "account_access"
    TECHNICAL_ISSUE = "technical_issue"
    BILLING_QUESTION = "billing_question"
    FEATURE_REQUEST = "feature_request"
    BUG_REPORT = "bug_report"
    OTHER = "other"


class Priority(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Status(str, Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    WAITING_CUSTOMER = "waiting_customer"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Source(str, Enum):
    WEB_FORM = "web_form"
    EMAIL = "email"
    API = "api"
    CHAT = "chat"
    PHONE = "phone"


class DeviceType(str, Enum):
    DESKTOP = "desktop"
    MOBILE = "mobile"
    TABLET = "tablet"
