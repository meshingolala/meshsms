"""
Automated Jasmin SMPP Gateway Configuration Script via Telnet (jcli).

Configures:
1. Upstream SMPP Carrier Connector (Step A)
2. API Group and Internal User (Step B)
3. Default MT Outbound Route (Step C)
4. Persists configuration to disk (Step D)
"""

import sys
import time
import socket
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("setup_jasmin")


class JasminTelnetClient:
    def __init__(self, host="127.0.0.1", port=8990, username="jcliadmin", password="jclipwd", timeout=10):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.sock = None

    def connect(self):
        logger.info("Connecting to Jasmin CLI at %s:%s...", self.host, self.port)
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        # Read welcome banner / login prompt
        self._read_until(b"Username:")
        self.sock.sendall(f"{self.username}\n".encode())
        self._read_until(b"Password:")
        self.sock.sendall(f"{self.password}\n".encode())
        output = self._read_until(b"jcli :")
        if b"Authentication failed" in output:
            raise RuntimeError("Jasmin CLI authentication failed! Check credentials.")
        logger.info("Successfully authenticated to Jasmin jcli.")

    def _read_until(self, expected: bytes) -> bytes:
        buffer = b""
        start = time.time()
        while expected not in buffer:
            if time.time() - start > self.timeout:
                raise TimeoutError(f"Timeout waiting for {expected}. Received so far: {buffer.decode(errors='ignore')}")
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            buffer += chunk
        return buffer

    def send_cmd(self, command: str) -> str:
        logger.debug(">> %s", command)
        self.sock.sendall(f"{command}\n".encode())
        res = self._read_until(b"jcli :")
        decoded = res.decode(errors="ignore").strip()
        logger.debug("<< %s", decoded)
        return decoded

    def send_interactive_block(self, init_cmd: str, subcommands: list[str]) -> str:
        """Sends an interactive command that expects > prompts until 'ok' or prompt returns to jcli :."""
        logger.info("Executing interactive block: %s", init_cmd)
        self.sock.sendall(f"{init_cmd}\n".encode())
        out = self._read_until(b">")

        for sub in subcommands:
            logger.info("  > %s", sub)
            self.sock.sendall(f"{sub}\n".encode())
            if sub == "ok":
                out += self._read_until(b"jcli :")
            else:
                out += self._read_until(b">")
        return out.decode(errors="ignore")

    def close(self):
        if self.sock:
            try:
                self.sock.sendall(b"quit\n")
                self.sock.close()
            except Exception:
                pass


def configure_jasmin(
    host="127.0.0.1",
    port=8990,
    carrier_host="smppsim",
    carrier_port=2775,
    carrier_user="smppclient1",
    carrier_pass="password",
    carrier_cid="carrier_mtn",
    api_user="gateway_api_user",
    api_pass="super_secret_pwd",
):
    client = JasminTelnetClient(host=host, port=port)
    try:
        client.connect()

        # Step A: Add Upstream Carrier Connector
        logger.info("Step A: Creating SMPP connector '%s'...", carrier_cid)
        client.send_interactive_block(
            "smppccm -a",
            [
                f"cid {carrier_cid}",
                f"host {carrier_host}",
                f"port {carrier_port}",
                f"username {carrier_user}",
                f"password {carrier_pass}",
                "bind transceiver",
                "submit_throughput 50",
                "dlr_msgid 1",
                "src_ton 5",
                "src_npi 0",
                "dst_ton 1",
                "dst_npi 1",
                "ok",
            ],
        )

        # Start connector
        logger.info("Starting connector '%s'...", carrier_cid)
        client.send_cmd(f"smppccm -1 {carrier_cid}")

        # Step B: Create Group and Internal API User
        logger.info("Step B: Creating group 'api_group' and user '%s'...", api_user)
        client.send_interactive_block("group -a", ["gid api_group", "ok"])
        client.send_interactive_block(
            "user -a",
            [
                "uid internal_api",
                "gid api_group",
                f"username {api_user}",
                f"password {api_pass}",
                "ok",
            ],
        )

        # Step C: Configure Outbound MT Routing
        logger.info("Step C: Creating DefaultRoute to connector smppc(%s)...", carrier_cid)
        client.send_interactive_block(
            "mtrouter -a",
            [
                "type DefaultRoute",
                f"connector smppc({carrier_cid})",
                "rate 0.00",
                "ok",
            ],
        )

        # Step D: Persist
        logger.info("Step D: Persisting configuration...")
        res = client.send_cmd("persist")
        logger.info("Persist response: %s", res)
        logger.info("Jasmin SMS Gateway configured successfully!")

    except Exception as exc:
        logger.error("Failed to configure Jasmin: %s", exc)
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    configure_jasmin()
