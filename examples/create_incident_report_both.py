import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.documents import DocumentEngine
from app.documents.templates import (
    incident_report_template,
)


model = incident_report_template(
    title="Clare Example-Staff Wi-Fi Incident",
    summary=(
        "NPS authentication succeeded but staff clients "
        "could not obtain network connectivity."
    ),
    symptoms=[
        "NPS Event 6272 reported access granted.",
        "Client did not receive usable connectivity.",
    ],
    root_cause=(
        "The Example-Staff WLAN Access VLAN at the example campus "
        "was configured as VLAN 30 instead of VLAN 80."
    ),
    resolution=(
        "Changed the WLAN Access VLAN from 30 to 80."
    ),
    validation=[
        "Client obtained a valid IP address.",
        "Gateway ping succeeded.",
        "Internet connectivity was restored.",
    ],
    organisation="Example School",
    document_id="RAZA-INC-2026-0001",
)

engine = DocumentEngine()

result = engine.create_both(
    model,
    filename="Example_WiFi_Incident_Report",
)

print(result)
