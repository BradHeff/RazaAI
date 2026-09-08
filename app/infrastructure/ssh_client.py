import socket
import paramiko


class ReadOnlySSHClient:
    def __init__(
        self,
        host,
        username,
        password=None,
        port=22,
        timeout=10,
    ):
        self.host = host
        self.username = username
        self.password = password
        self.port = int(port or 22)
        self.timeout = timeout

    def execute(self, command):
        client = paramiko.SSHClient()

        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())

        try:
            client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=self.timeout,
                banner_timeout=self.timeout,
                auth_timeout=self.timeout,
                look_for_keys=True,
                allow_agent=True,
            )

            stdin, stdout, stderr = client.exec_command(
                command,
                timeout=self.timeout,
            )

            output = stdout.read().decode(
                "utf-8",
                errors="replace",
            )

            error = stderr.read().decode(
                "utf-8",
                errors="replace",
            )

            status = stdout.channel.recv_exit_status()

            return {
                "success": status == 0,
                "exit_code": status,
                "stdout": output.strip(),
                "stderr": error.strip(),
            }

        finally:
            client.close()
