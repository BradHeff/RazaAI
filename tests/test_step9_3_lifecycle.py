from types import SimpleNamespace
from app.playbooks.lifecycle import PlaybookLifecycleEvaluator
P={"id":"wifi-nps-no-connectivity"}
def main():
 print("\n========================================\nRazaAI Step 9.3 Lifecycle Test\n========================================\n")
 e=PlaybookLifecycleEvaluator(); s=SimpleNamespace(lifecycle_context={"expected_vlan":80},validation_evidence={})
 assert e.evaluate_resolution(P,s,"done").action=="need_fix_evidence"; print("[PASS] vague done does not prove resolution")
 assert e.evaluate_resolution(P,s,"Changed Access VLAN to VLAN 30").action=="need_fix_evidence"; print("[PASS] wrong VLAN does not enter validation")
 assert e.evaluate_resolution(P,s,"Changed Access VLAN to VLAN 80").action=="begin_validation"; print("[PASS] correct VLAN enters validation")
 d=e.evaluate_validation(P,s,"Client got an IP address"); assert d.action=="need_validation_evidence"; print("[PASS] DHCP alone does not close incident")
 d=e.evaluate_validation(P,s,"Gateway ping works"); assert d.action=="need_validation_evidence"; print("[PASS] gateway evidence accumulates")
 d=e.evaluate_validation(P,s,"Internet connectivity is working"); assert d.action=="close"; print("[PASS] full validation closes incident")
 s2=SimpleNamespace(lifecycle_context={"expected_vlan":80},validation_evidence={})
 assert e.evaluate_validation(P,s2,"Client has APIPA 169.254.10.25").action=="validation_failed"; print("[PASS] failed validation does not close")
 print("\n========================================\nSTEP 9.3 RESOLUTION / VALIDATION PASSED\n========================================\n")
if __name__=="__main__": main()
