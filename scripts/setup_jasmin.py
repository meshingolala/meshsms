"""
Automated Jasmin SMPP Gateway Configuration Script via Telnet (jcli).

Configures:
1. Upstream SMPP Carrier Connector (Step A)
2. API Group and Internal User (Step B)
3. Default MT Outbound Route (Step C)
4. Persists configuration to disk (Step D)
"""

import os
import sys
import time
import socket
import logging
import argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("setup_jasmin")


class JasminTelnetClient:
    def __init__(self, host="127.0.0.1", port=8990, username="jcliadmin", password="jclipwd", timeout=10, max_retries=15):
        self.host = host
        self.port = int(port)
        self.username = username
        self.password = password
        self.timeout = timeout
        self.max_retries = max_retries
        self.sock = None

    def connect(self):
        candidates = [self.host]
        for fallback in ["sms_jasmin", "jasmin", "127.0.0.1", "localhost"]:
            if fallback not in candidates:
                candidates.append(fallback)

        connected = False
        last_error = None

        logger.info("Connecting to Jasmin CLI (candidates: %s on port %s)...", candidates, self.port)
        for target_host in candidates:
            try:
                self.sock = socket.create_connection((target_host, self.port), timeout=self.timeout)
                self.host = target_host
                connected = True
                logger.info("Connected to Jasmin CLI via host '%s'!", target_host)
                break
            except (socket.gaierror, ConnectionRefusedError, OSError) as exc:
                last_error = exc
                continue

        if not connected:
            # If all failed on first pass, retry with backoff
            for attempt in range(1, self.max_retries + 1):
                for target_host in candidates:
                    try:
                        self.sock = socket.create_connection((target_host, self.port), timeout=self.timeout)
                        self.host = target_host
                        connected = True
                        logger.info("Connected to Jasmin CLI via host '%s'!", target_host)
                        break
                    except (socket.gaierror, ConnectionRefusedError, OSError) as exc:
                        last_error = exc
                        continue
                if connected:
                    break
                logger.info("Jasmin Telnet not ready yet (attempt %d/%d). Retrying in 2s...", attempt, self.max_retries)
                time.sleep(2)

        if not connected:
            raise RuntimeError(f"Could not connect to Jasmin on any host {candidates}: {last_error}")

        # Read welcome banner / login prompt
        self._read_until(b"Username:")
        self.sock.sendall(f"{self.username}\r\n".encode())
        self._read_until(b"Password:")
        self.sock.sendall(f"{self.password}\r\n".encode())
        output = self._read_until(b"jcli :")
        if b"Authentication failed" in output:
            raise RuntimeError("Jasmin CLI authentication failed! Check credentials.")
        logger.info("Successfully authenticated to Jasmin jcli.")

    def _read_until(self, expected: bytes) -> bytes:
        buffer = b""
        start = time.time()
        self.sock.settimeout(2.0)
        while expected not in buffer:
            if time.time() - start > self.timeout:
                raise TimeoutError(f"Timeout waiting for {expected}. Received so far: {buffer.decode(errors='ignore')}")
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                buffer += chunk
            except socket.timeout:
                continue
        return buffer

    def send_cmd(self, command: str) -> str:
        logger.debug(">> %s", command)
        self.sock.sendall(f"{command}\r\n".encode())
        res = self._read_until(b"jcli :")
        decoded = res.decode(errors="ignore").strip()
        logger.debug("<< %s", decoded)
        return decoded

    def send_interactive_block(self, init_cmd: str, subcommands: list[str]) -> str:
        """Sends an interactive command that expects > prompts until 'ok' or prompt returns to jcli :."""
        logger.info("Executing interactive block: %s", init_cmd)
        self.sock.sendall(f"{init_cmd}\r\n".encode())
        out = self._read_until(b">")

        for sub in subcommands:
            logger.info("  > %s", sub)
            self.sock.sendall(f"{sub}\r\n".encode())
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
    host=None,
    port=None,
    username=None,
    password=None,
    carrier_host=None,
    carrier_port=None,
    carrier_user=None,
    carrier_pass=None,
    carrier_cid=None,
    api_user=None,
    api_pass=None,
):
    # Auto-detect host: if running inside container or env var is set, use 'jasmin'
    default_host = os.environ.get("JASMIN_TELNET_HOST")
    if not default_host:
        default_host = "jasmin" if os.path.exists("/.dockerenv") else "127.0.0.1"

    host = host or default_host
    port = int(port or os.environ.get("JASMIN_TELNET_PORT", 8990))
    username = username or os.environ.get("JASMIN_TELNET_USER", "jcliadmin")
    password = password or os.environ.get("JASMIN_TELNET_PASS", "jclipwd")

    carrier_host = carrier_host or os.environ.get("SMPP_CARRIER_HOST", "smppsim")
    carrier_port = int(carrier_port or os.environ.get("SMPP_CARRIER_PORT", 2775))
    carrier_user = carrier_user or os.environ.get("SMPP_CARRIER_USER", "smppclient1")
    carrier_pass = carrier_pass or os.environ.get("SMPP_CARRIER_PASS", "password")
    carrier_cid = carrier_cid or "carrier_mtn"

    api_user = api_user or os.environ.get("JASMIN_USER", "gateway_api_user")
    api_pass = api_pass or os.environ.get("JASMIN_PASS", "super_secret_pwd")

    client = JasminTelnetClient(host=host, port=port, username=username, password=password)
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
    parser = argparse.ArgumentParser(description="Configure Jasmin SMS Gateway via Telnet")
    parser.add_argument("--host", default=None, help="Jasmin Telnet host (default: jasmin in docker, else 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Jasmin Telnet port (default: 8990)")
    parser.add_argument("--username", default=None, help="Jasmin jcli username (default: jcliadmin)")
    parser.add_argument("--password", default=None, help="Jasmin jcli password (default: jclipwd)")
    parser.add_argument("--carrier-host", default=None, help="SMPP carrier host (default: smppsim)")
    parser.add_argument("--carrier-port", type=int, default=None, help="SMPP carrier port (default: 2775)")
    parser.add_argument("--carrier-user", default=None, help="SMPP carrier username")
    parser.add_argument("--carrier-pass", default=None, help="SMPP carrier password")
    parser.add_argument("--carrier-cid", default=None, help="SMPP connector ID (default: carrier_mtn)")
    args = parser.parse_args()

    configure_jasmin(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        carrier_host=args.carrier_host,
        carrier_port=args.carrier_port,
        carrier_user=args.carrier_user,
        carrier_pass=args.carrier_pass,
        carrier_cid=args.carrier_cid,
    )
