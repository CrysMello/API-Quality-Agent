from enum import Enum


class DependencyConfidence(str, Enum):
    CONFIRMED = "confirmed"
    SUGGESTED = "suggested"
