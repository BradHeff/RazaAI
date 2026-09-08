import re
from dataclasses import dataclass, field

@dataclass
class LifecycleDecision:
    action: str
    reason: str
    missing_evidence: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)

class PlaybookLifecycleEvaluator:
    def evaluate_resolution(self, playbook, session, user_input):
        text=user_input.strip().lower()
        if text in {"ok","okay","done","yes","fixed","changed","all good"}:
            return LifecycleDecision("need_fix_evidence","The response does not identify the corrective change.",["explicit corrective change"])
        if playbook.get("id")=="fortigate-admin-gui-refused":
            if "admin-server-cert" not in text or "fortinet_factory" not in text:
                return LifecycleDecision(
                    "need_fix_evidence",
                    "The corrective admin-server-cert change has not been stated.",
                    ["exact admin-server-cert corrective command"],
                )
            command = 'config system global\nset admin-server-cert "Fortinet_Factory"\nend'
            return LifecycleDecision(
                "begin_validation",
                "The Fortinet_Factory admin-server-cert corrective change was explicitly reported.",
                evidence={"resolution_command": command, "admin_server_cert": "Fortinet_Factory"},
            )
        if playbook.get("id")=="wifi-nps-no-connectivity":
            m=re.search(r"\bvlan\s*[:=#-]?\s*(\d{1,4})\b",text,re.I)
            if not m:
                return LifecycleDecision("need_fix_evidence","The corrected WLAN Access VLAN has not been stated.",["corrected access VLAN"])
            vlan=int(m.group(1))
            expected=getattr(session,"lifecycle_context",{}).get("expected_vlan")
            if expected is not None and vlan != expected:
                return LifecycleDecision("need_fix_evidence",f"VLAN {vlan} does not match required VLAN {expected}.",[f"Access VLAN changed to {expected}"],{"configured_vlan":vlan,"expected_vlan":expected})
            return LifecycleDecision("begin_validation",f"The corrective VLAN change to {vlan} was explicitly reported.",evidence={"configured_vlan":vlan})
        return LifecycleDecision("need_fix_evidence","No deterministic resolution evaluator exists for this playbook.",["explicit corrective change"])

    def evaluate_validation(self, playbook, session, user_input):
        text=user_input.strip().lower()
        if playbook.get("id")=="fortigate-admin-gui-refused":
            evidence=getattr(session,"validation_evidence",{})
            if re.search(r"\b(?:connection refused|still refused|still not loading|still does not load|still doesn't load|gui still fails)\b", text):
                evidence["gui_access"]=False
            elif re.search(r"\b(?:gui|web|https|login page|web interface).{0,40}\b(?:works|working|loads|loaded|accessible|back|restored)\b", text) or re.search(r"\b(?:now )?i have access\b", text):
                evidence["gui_access"]=True
            session.validation_evidence=evidence
            if evidence.get("gui_access") is False:
                return LifecycleDecision("validation_failed","HTTPS GUI access is still failing.",evidence=evidence.copy())
            if evidence.get("gui_access") is True:
                return LifecycleDecision("close","HTTPS GUI access was restored after the certificate correction.",evidence=evidence.copy())
            return LifecycleDecision("need_validation_evidence","GUI recovery must be confirmed before closure.",["successful HTTPS GUI access"],evidence.copy())
        if playbook.get("id")!="wifi-nps-no-connectivity":
            return LifecycleDecision("need_validation_evidence","No deterministic validation evaluator exists.",list(playbook.get("validation") or ["validation evidence"]))
        evidence=getattr(session,"validation_evidence",{})
        if re.search(r"\b169\.254\.\d{1,3}\.\d{1,3}\b|\bapipa\b|\bno (?:dhcp )?lease\b",text):
            evidence["dhcp"]=False
        elif re.search(r"\b(?:dhcp|lease)\b.*\b(?:works|working|received|valid|yes)\b",text) or re.search(r"\b(?:10|172|192)\.(?:\d{1,3}\.){2}\d{1,3}\b",text) or "got an ip" in text:
            evidence["dhcp"]=True
        if re.search(r"\bgateway\b.*\b(?:ping|reachable|works|working|success|yes)\b",text): evidence["gateway"]=True
        elif re.search(r"\bgateway\b.*\b(?:fail|failed|unreachable|no)\b",text): evidence["gateway"]=False
        if re.search(r"\b(?:internet|network|connectivity)\b.*\b(?:works|working|up|yes|connected)\b",text): evidence["connectivity"]=True
        elif re.search(r"\b(?:internet|network|connectivity)\b.*\b(?:fail|failed|down|no|not working)\b",text): evidence["connectivity"]=False
        session.validation_evidence=evidence
        failed=[k for k,v in evidence.items() if v is False]
        if failed: return LifecycleDecision("validation_failed",f"Validation failed for: {', '.join(failed)}.",evidence=evidence.copy())
        missing=[k for k in ["dhcp","gateway","connectivity"] if evidence.get(k) is not True]
        if missing: return LifecycleDecision("need_validation_evidence","All validation checks must pass before closure.",missing,evidence.copy())
        return LifecycleDecision("close","DHCP, gateway reachability, and connectivity all passed.",evidence=evidence.copy())
