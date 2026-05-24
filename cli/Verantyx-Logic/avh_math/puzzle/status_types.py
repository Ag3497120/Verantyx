from enum import Enum

class ReasoningStatus(Enum):
    PROVED = "proved"
    DISPROVED = "disproved"
    TENTATIVE_ANSWER = "tentative_answer"
    TENTATIVE_PROVED = "tentative_proved"
    TENTATIVE_DISPROVED = "tentative_disproved"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    SILENT = "silent"

    @classmethod
    def from_str(cls, s: str):
        for member in cls:
            if member.value == s.lower():
                return member
        return cls.SILENT
