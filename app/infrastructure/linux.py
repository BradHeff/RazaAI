from .ssh_client import ReadOnlySSHClient


LINUX_CHECKS = {
    "system": "uname -a && hostnamectl --static",
    "uptime": "uptime",
    "memory": "free -h",
    "disk": "df -hT",
    "addresses": "ip -brief address",
    "routes": "ip route show",
    "dns": "cat /etc/resolv.conf",
    "failed_services": (
        "systemctl --failed --no-pager "
        "--no-legend"
    ),
}


class LinuxReadOnlyAdapter:
    def __init__(self, target, password=None):
        self.target = target
        self.client = ReadOnlySSHClient(
            host=target["host"],
            port=target.get("port", 22),
            username=target["username"],
            password=password,
        )

    def run_check(self, check):
        if check not in LINUX_CHECKS:
            raise ValueError(
                f"Unsupported Linux read-only check: {check}"
            )

        return self.client.execute(
            LINUX_CHECKS[check]
        )

    @staticmethod
    def checks():
        return sorted(LINUX_CHECKS)
