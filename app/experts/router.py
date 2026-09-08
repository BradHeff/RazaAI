from dataclasses import dataclass
import re


@dataclass
class ExpertRoute:
    expert: str
    category: str | None
    confidence: float
    matched_terms: list[str]


class ExpertRouter:
    """Lightweight deterministic ICT expert router."""

    RULES = {
        "networking": {
            "category": "networking",
            "terms": {
                "wifi",
                "wi-fi",
                "wireless",
                "ssid",
                "radius",
                "nps",
                "802.1x",
                "vlan",
                "switch",
                "routing",
                "route",
                "gateway",
                "fortigate",
                "fortinet",
                "aruba",
                "ruckus",
                "dns",
                "dhcp",
                "bgp",
                "ospf",
                "tcp",
                "udp",
                "firewall",
                "vpn",
                "ipsec",
                "subnet",
                "packet",
                "latency",
                "ping",
                "traceroute",
            },
        },
        "microsoft": {
            "category": "microsoft",
            "terms": {
                "active directory",
                "ad ds",
                "domain controller",
                "gpo",
                "group policy",
                "entra",
                "azure ad",
                "intune",
                "m365",
                "microsoft 365",
                "powershell",
                "windows server",
                "exchange",
                "sharepoint",
                "onedrive",
                "teams",
                "autopilot",
                "nps",
                "ldap",
                "ldaps",
            },
        },
        "servers": {
            "category": "servers",
            "terms": {
                "server",
                "lxd",
                "lxc",
                "vm",
                "virtual machine",
                "hypervisor",
                "storage",
                "filesystem",
                "ext4",
                "fsck",
                "initramfs",
                "raid",
                "backup",
                "restore",
                "snapshot",
                "docker",
                "container",
                "ollama",
                "plex",
                "nginx",
                "mysql",
                "mongodb",
                # Web/application-server symptoms. Multi-word terms
                # weigh 2.0, so "bad gateway" outranks networking's generic
                # "gateway" instead of tying with it.
                "apache",
                "httpd",
                "caddy",
                "haproxy",
                "reverse proxy",
                "upstream",
                "gunicorn",
                "uwsgi",
                "php-fpm",
                "unix socket",
                "bad gateway",
                "gateway timeout",
                "502",
                "503",
                "504",
            },
        },
        "linux": {
            "category": "linux",
            "terms": {
                "linux",
                "fedora",
                "ubuntu",
                "debian",
                "systemd",
                "systemctl",
                "journalctl",
                "bash",
                "kernel",
                "selinux",
                "dnf",
                "apt",
                "xorg",
                "wayland",
                "nvidia",
                "desktop",
                "mount",
                "fstab",
            },
        },
        "cybersecurity": {
            "category": "cybersecurity",
            "terms": {
                "security",
                "vulnerability",
                "incident",
                "malware",
                "edr",
                "mfa",
                "phishing",
                "hardening",
                "cve",
                "exploit",
                "breach",
                "ransomware",
                "zero trust",
                "firewall policy",
                "authentication",
                "authorization",
                "certificate",
                "pki",
                "password",
                "passwords",
                "credential",
                "credentials",
                "secret",
                "secrets",
                "api key",
                "token",
                "private key",
                "ssh key",
            },
        },
        "programming": {
            "category": "programming",
            "terms": {
                "python",
                "javascript",
                "typescript",
                "react",
                "nextjs",
                "node",
                "sql",
                "api",
                "code",
                "programming",
                "git",
                "github",
                "html",
                "css",
                "json",
                "yaml",
            },
        },
        "cloud": {
            "category": "cloud",
            "terms": {
                "azure",
                "aws",
                "gcp",
                "cloud",
                "ec2",
                "s3",
                "lambda",
                "virtual network",
                "vnet",
                "iam",
            },
        },
    }

    def route(self, query: str) -> ExpertRoute:
        text = query.lower().strip()
        scores = {}
        matches = {}

        # HTTP status phrases are application-server symptoms; do not
        # let them count as the networking term "gateway".
        networking_text = text.replace("bad gateway", " ").replace("gateway timeout", " ")

        for expert, rule in self.RULES.items():
            score = 0.0
            matched = []

            haystack = networking_text if expert == "networking" else text
            for term in rule["terms"]:
                if term in haystack:

                    weight = (
                        2.0 if (" " in term or "." in term or term.isupper()) else 1.0
                    )
                    score += weight
                    matched.append(term)

            scores[expert] = score
            matches[expert] = matched

        best_expert = max(scores, key=scores.get)
        best_score = scores[best_expert]

        if best_score <= 0:
            return ExpertRoute(
                expert="general_ict",
                category=None,
                confidence=0.25,
                matched_terms=[],
            )

        total = sum(scores.values()) or best_score
        confidence = min(0.99, max(0.40, best_score / total))

        return ExpertRoute(
            expert=best_expert,
            category=self.RULES[best_expert]["category"],
            confidence=round(confidence, 2),
            matched_terms=sorted(matches[best_expert]),
        )

    def system_guidance(self, route: ExpertRoute) -> str:
        if route.expert == "general_ict":
            return (
                "You are handling this as a general ICT request. Use live tools "
                "or search_knowledge when evidence would improve the answer."
            )

        return (
            f"Expert route: {route.expert}. Preferred knowledge category: "
            f"{route.category}. For environment-specific or recurring ICT "
            f"issues, search the relevant local knowledge before relying only "
            f"on pretrained knowledge. When knowledge is retrieved, clearly "
            f"separate 'From our field notes/knowledge' from 'Additional "
            f"diagnosis or recommendation'. Do not imply that general reasoning "
            f"came from a retrieved source."
        )
