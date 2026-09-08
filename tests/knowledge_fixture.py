"""Create a synthetic knowledge corpus and isolated index for test runs."""

from pathlib import Path
import json
import os
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def prepare():
    temporary = tempfile.TemporaryDirectory(prefix='raza-tests-')
    root = Path(temporary.name)
    knowledge = root / 'knowledge'
    for category in ('networking', 'servers', 'microsoft'):
        (knowledge / category).mkdir(parents=True)
    for relative in (
        'networking/apipa-169-254-dhcp-failure-troubleshooting.md',
        'networking/fortigate-admin-gui-access-troubleshooting.md',
        'networking/fortigate-ipsec-tunnel-down-troubleshooting.md',
        'networking/fortigate-policy-not-matching-troubleshooting.md',
        'servers/nginx-502-bad-gateway-troubleshooting.md',
        'networking/razaai_step4_test.md', 'networking/razaai_step5_test.md',
    ):
        source = ROOT / 'knowledge' / relative
        shutil.copyfile(source, knowledge / relative)
        metadata = source.with_suffix('.md.meta.json')
        if metadata.exists():
            shutil.copyfile(metadata, (knowledge / relative).with_suffix('.md.meta.json'))
    fixtures = {
        'networking/school-networking-field-notes.md': '''# Fictional lab incident examples

## NPS accepts Wi-Fi authentication but the client cannot join
**Symptom:** NPS grants access on the Ruckus WLAN, but the school Wi-Fi client cannot join the network.
**Cause:** The WLAN access VLAN does not match the client network.
**Fix:** Correct the access VLAN and verify the DHCP lease and gateway reachability.

## Aruba AP-515 Wi-Fi throughput capped around 315 Mbps
**Symptom:** The test client's Wi-Fi throughput is limited.
**Cause:** The test radio uses a narrower channel than the fixture expects.
**Fix:** The fictional lab measurement improved with 80 MHz channel width.

## FortiGate traceroute shows all stars
**Symptom:** Intermediate routers do not return ICMP replies.
**Cause:** ICMP responses are filtered.
**Fix:** Check destination reachability separately before declaring a routing failure.

## DHCP scope exhausted
**Symptom:** Clients have no lease.
**Cause:** No free addresses remain in the scope.
**Fix:** Free an unused test lease and retry DHCP.

## Switch port disabled
**Symptom:** The lab endpoint has no link.
**Cause:** The port is administratively disabled.
**Fix:** An authorised operator enables the lab port and verifies link state.
''',
        'microsoft/example-directory.md': '''# Fictional directory incident

## Linewize LDAPS synchronization failure at the example campus
**Symptom:** Directory synchronization fails over LDAPS.
**Cause:** The configured domain controller is unavailable.
**Fix:** Restore connectivity to the domain controller and verify its LDAPS certificate.
''',
        'servers/example-filesystem.md': '''# Fictional filesystem incident

## Plex VM boots into initramfs and the LXD VM agent is not running
**Symptom:** The Plex VM cannot start because its ext4 root filesystem is corrupted.
**Cause:** Filesystem errors prevent the guest from mounting root.
**Fix:** In this fixture, an operator repairs the unmounted filesystem with fsck.ext4 and verifies a clean boot.
''',
    }
    for relative, content in fixtures.items():
        path = knowledge / relative
        path.write_text(content)
        path.with_suffix('.md.meta.json').write_text(json.dumps({'knowledge_type':'field_notes', 'category':Path(relative).parts[0]}))
    os.environ['RAZAAI_KNOWLEDGE_DIR'] = str(knowledge)
    os.environ['RAZAAI_KNOWLEDGE_DATA_DIR'] = str(root / 'data')
    os.environ['RAZAAI_STATE_DIR'] = str(root / 'state')
    return temporary


def indexed():
    """Prepare test data and build its index before starting test subprocesses."""
    import subprocess
    import sys

    fixture = prepare()
    try:
        result = subprocess.run([sys.executable, '-m', 'scripts.ingest_knowledge'],
                                cwd=ROOT, capture_output=True, text=True, timeout=900)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
    except BaseException:
        fixture.cleanup()
        raise
    return fixture
