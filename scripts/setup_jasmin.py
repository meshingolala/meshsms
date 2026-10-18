"""
Automated Jasmin SMPP Gateway Configuration Script via Telnet / Raw Socket.

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


class JasminClient:
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
        for fallback in ["127.0.0.1", "sms_jasmin", "jasmin", "localhost"]:
            if fallback not in candidates:
                candidates.append(fallback)

        connected = False
        last_error = None

        logger.info("Connecting to Jasmin CLI (candidates: %s on port %s)...", candidates, self.port)
        for target_host in candidates:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(self.timeout)
                self.sock.connect((target_host, self.port))
                self.host = target_host
                connected = True
                logger.info("Connected to Jasmin CLI via host '%s'!", target_host)
                break
            except (socket.gaierror, ConnectionRefusedError, OSError) as exc:
                last_error = exc
                continue

        if not connected:
            for attempt in range(1, self.max_retries + 1):
                for target_host in candidates:
                    try:
                        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        self.sock.settimeout(self.timeout)
                        self.sock.connect((target_host, self.port))
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

        # Login flow
        time.sleep(1.0)
        initial_banner = self._read_available()
        logger.info("Server banner: %s", initial_banner.strip())

        # Send Username
        logger.info("Authenticating user '%s'...", self.username)
        self.sock.sendall(f"{self.username}\n".encode())
        time.sleep(0.5)
        user_res = self._read_available()

        # Send Password
        self.sock.sendall(f"{self.password}\n".encode())
        time.sleep(1.0)
        login_res = self._read_available()

        if "Authentication failed" in login_res or "Invalid" in login_res:
            raise RuntimeError(f"Jasmin authentication failed: {login_res}")

        logger.info("Successfully authenticated to Jasmin jcli!")

    def _read_available(self) -> str:
        """Reads currently available bytes from the socket without blocking indefinitely."""
        self.sock.setblocking(False)
        buffer = b""
        time.sleep(0.3)
        while True:
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                buffer += chunk
            except BlockingIOError:
                break
            except Exception:
                break
        self.sock.setblocking(True)
        return buffer.decode("utf-8", errors="ignore")

    def send_cmd(self, command: str, delay: float = 0.5) -> str:
        logger.info(">> %s", command)
        self.sock.sendall(f"{command}\n".encode())
        time.sleep(delay)
        output = self._read_available().strip()
        if output:
            logger.info("<< %s", output)
        return output

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
    host = host or ("jasmin" if os.path.exists("/.dockerenv") else "127.0.0.1")
    port = int(port or 8990)
    username = username or "jcliadmin"
    password = password or "jclipwd"

    carrier_host = carrier_host or "smppsim"
    carrier_port = int(carrier_port or 2775)
    carrier_user = carrier_user or "smppclient1"
    carrier_pass = carrier_pass or "password"
    carrier_cid = carrier_cid or "carrier_mtn"

    api_user = api_user or "gatewayapiuser"
    api_pass = api_pass or "supersecretpwd"

    client = JasminClient(host=host, port=port, username=username, password=password)
    try:
        client.connect()

        # Step A: Add Upstream Carrier Connector
        logger.info("Step A: Creating SMPP connector '%s'...", carrier_cid)
        res_a = client.send_cmd("smppccm -a")
        if "already exists" in res_a or "Adding a new connector" not in res_a:
            client.send_cmd("ko")
        else:
            client.send_cmd(f"cid {carrier_cid}")
            client.send_cmd(f"host {carrier_host}")
            client.send_cmd(f"port {carrier_port}")
            client.send_cmd(f"username {carrier_user}")
            client.send_cmd(f"password {carrier_pass}")
            client.send_cmd("bind transceiver")
            client.send_cmd("submit_throughput 50")
            client.send_cmd("dlr_msgid 1")
            client.send_cmd("src_ton 5")
            client.send_cmd("src_npi 0")
            client.send_cmd("dst_ton 1")
            client.send_cmd("dst_npi 1")
            ok_res = client.send_cmd("ok")
            if "Error" in ok_res or "already" in ok_res:
                client.send_cmd("ko")

        # Start connector
        logger.info("Starting connector '%s'...", carrier_cid)
        client.send_cmd(f"smppccm -1 {carrier_cid}")

        # Step B: Create Group and Internal API User
        logger.info("Step B: Creating group 'api_group' and user '%s'...", api_user)
        res_g = client.send_cmd("group -a")
        if "Adding a new Group" in res_g:
            client.send_cmd("gid api_group")
            client.send_cmd("ok")
        else:
            client.send_cmd("ko")

        res_u = client.send_cmd("user -a")
        if "Adding a new User" in res_u:
            client.send_cmd("uid internal_api")
            client.send_cmd("gid api_group")
            client.send_cmd(f"username {api_user}")
            client.send_cmd(f"password {api_pass}")
            usr_ok = client.send_cmd("ok")
            if "Error" in usr_ok:
                client.send_cmd("ko")
        else:
            client.send_cmd("ko")

        # Step C: Configure Outbound MT Routing
        logger.info("Step C: Creating DefaultRoute to connector smppc(%s)...", carrier_cid)
        res_r = client.send_cmd("mtrouter -a")
        if "Adding a new" in res_r or "type" in res_r:
            client.send_cmd("type DefaultRoute")
            client.send_cmd(f"connector smppc({carrier_cid})")
            client.send_cmd("rate 0.00")
            client.send_cmd("ok")
        else:
            client.send_cmd("ko")

        # Step D: Persist
        logger.info("Step D: Persisting configuration...")
        client.send_cmd("persist", delay=1.0)
        logger.info("Jasmin SMS Gateway configured successfully!")

    except Exception as exc:
        logger.error("Failed to configure Jasmin: %s", exc)
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Configure Jasmin SMS Gateway via Telnet/Socket")
    parser.add_argument("--host", default=None, help="Jasmin Telnet host")
    parser.add_argument("--port", type=int, default=None, help="Jasmin Telnet port")
    parser.add_argument("--username", default=None, help="Jasmin jcli username")
    parser.add_argument("--password", default=None, help="Jasmin jcli password")
    parser.add_argument("--carrier-host", default=None, help="SMPP carrier host")
    parser.add_argument("--carrier-port", type=int, default=None, help="SMPP carrier port")
    parser.add_argument("--carrier-user", default=None, help="SMPP carrier username")
    parser.add_argument("--carrier-pass", default=None, help="SMPP carrier password")
    parser.add_argument("--carrier-cid", default=None, help="SMPP connector ID")
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
