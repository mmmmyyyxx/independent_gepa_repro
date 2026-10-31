"""Pre-import socket denial shared by the verifier and every spawned child."""
import os
from pathlib import Path
import socket


def deny(*args, **kwargs):
    # Record categories only, never hostnames, addresses, requests or secrets.
    target = os.environ.get("PAPER_OFFLINE_EVENTS")
    if target:
        with Path(target).open("a", encoding="utf-8") as stream:
            stream.write("network_attempt\n")
    raise RuntimeError("PAPER_OFFLINE_NETWORK_DENIED")


socket.socket.connect = deny
socket.socket.connect_ex = deny
socket.socket.sendto = deny
socket.create_connection = deny
socket.getaddrinfo = deny
