from dataclasses import dataclass
from pathlib import Path
import json

from .session import PlaybookSession


@dataclass
class PlaybookMatch:
    id: str
    name: str
    score: float
    playbook: dict


class PlaybookEngine:
    def __init__(self):
        self.root = Path(__file__).resolve().parents[2] / "playbooks"
        self.playbooks = self._load()

    def _load(self):
        items = []
        if not self.root.exists():
            return items
        for path in sorted(self.root.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            data["_path"] = str(path)
            items.append(data)
        return items

    def get(self, playbook_id: str):
        for pb in self.playbooks:
            if pb.get("id") == playbook_id:
                return pb
        return None

    def match(self, query: str, expert: str | None = None):
        text = query.lower()
        best = None

        for pb in self.playbooks:
            required_any = [str(item).lower() for item in pb.get("requires_any", []) if str(item).strip()]
            if required_any and not any(term in text for term in required_any):
                continue

            score = 0.0
            expert_bonus = 0.0

            if expert and pb.get("expert") == expert:
                expert_bonus = 1.0
                score += expert_bonus

            trigger_score = 0.0
            for trigger in pb.get("triggers", []):
                if trigger.lower() in text:
                    trigger_score += 2.0 if " " in trigger else 1.0

            score += trigger_score

            if trigger_score <= 0:
                continue

            candidate = PlaybookMatch(
                id=pb["id"],
                name=pb["name"],
                score=round(score, 2),
                playbook=pb,
            )

            if best is None or candidate.score > best.score:
                best = candidate

        return best

    def start_session(self, match: PlaybookMatch):
        return PlaybookSession(
            playbook_id=match.id,
            playbook_name=match.name,
        )

    def guidance(
        self,
        match: PlaybookMatch | None,
        session: PlaybookSession | None = None,
        continuation: bool = False,
    ):
        if not match or not session:
            return "No active formal diagnostic playbook."

        pb = match.playbook
        current = session.current_check(pb)

        if current is None:
            return (
                f"Playbook {pb['name']} has no remaining diagnostic checks. "
                "Move to resolution/validation only if the evidence supports it."
            )

        observations = "\n".join(
            f"- Step {o['step']}: {o['text']}"
            for o in session.observations[-5:]
        ) or "- none yet"

        if continuation:
            mode = """
This is a CONTINUATION of an active diagnostic session.
The user's latest message is evidence/results for the CURRENT STEP.
Evaluate that result before doing anything else.

You have exactly three allowed outcomes:
A) CAUSE ISOLATED:
   Explain briefly why the evidence isolates the cause, give the smallest
   corrective action, and give validation steps. Do not advance.
B) CURRENT CHECK PASSED / DID NOT ISOLATE:
   Say so briefly, then advance to the NEXT playbook check only.
C) RESULT UNCLEAR:
   Ask one precise clarification needed to complete the current check.

Do not restart the playbook. Do not repeat earlier checks. Do not dump later
checks. Never claim a check passed unless the user/tool evidence shows it.
""".strip()
        else:
            mode = """
This is the START of a diagnostic session.
Present ONLY the current check below. Ask the user for the exact result needed
to evaluate it. Do not show later checks, fallback branches, full resolution
trees, or validation steps yet.
""".strip()

        return f"""
STATEFUL DIAGNOSTIC PLAYBOOK
Playbook: {pb['name']}
Playbook ID: {pb['id']}
Status: {session.status}
Current step: {session.current_step + 1}

CURRENT CHECK:
{current}

Recorded observations:
{observations}

{mode}

The playbook controls order. Retrieved field notes and live evidence control the
conclusion. Never invent observations or completed checks.
""".strip()
