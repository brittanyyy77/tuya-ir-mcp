#!/usr/bin/env python3
"""Tuya IR MCP Server

A lightweight MCP server that lets AI control any IR device
through a Tuya IR blaster. Speaks MCP protocol over HTTP.

Usage:
    cp .env.example .env  # fill in your credentials
    pip3 install flask requests
    python3 server.py
"""

import hashlib
import hmac
import json
import os
import time

import requests as req
from flask import Flask, request, jsonify

# --- Config from environment ---

def load_env():
    """Load .env file if it exists."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_env()

ACCESS_ID = os.environ.get("TUYA_ACCESS_ID", "")
ACCESS_SECRET = os.environ.get("TUYA_ACCESS_SECRET", "")
IR_DEVICE_ID = os.environ.get("TUYA_IR_DEVICE_ID", "")
ENDPOINT = os.environ.get("TUYA_ENDPOINT", "https://openapi.tuyacn.com")
PORT = int(os.environ.get("PORT", "18088"))

if not all([ACCESS_ID, ACCESS_SECRET, IR_DEVICE_ID]):
    print("Error: TUYA_ACCESS_ID, TUYA_ACCESS_SECRET, and TUYA_IR_DEVICE_ID must be set.")
    print("Copy .env.example to .env and fill in your credentials.")
    exit(1)

# --- Tuya API client ---

app = Flask(__name__)

_token = {"v": None, "exp": 0}
_remote = {"id": None, "keys": {}}


def sign(payload, token_str=""):
    """Generate Tuya API signature."""
    t = str(int(time.time() * 1000))
    raw = ACCESS_ID + token_str + t + payload
    s = hmac.new(
        ACCESS_SECRET.encode(),
        raw.encode(),
        hashlib.sha256
    ).hexdigest().upper()
    return t, s


def get_token():
    """Get or refresh Tuya API access token."""
    if _token["v"] and time.time() < _token["exp"]:
        return _token["v"]

    path = "/v1.0/token?grant_type=1"
    body_hash = hashlib.sha256(b"").hexdigest()
    payload = "GET\n" + body_hash + "\n\n" + path
    t, s = sign(payload)

    headers = {
        "client_id": ACCESS_ID,
        "sign": s,
        "t": t,
        "sign_method": "HMAC-SHA256",
    }

    r = req.get(ENDPOINT + path, headers=headers).json()
    if r.get("success"):
        _token["v"] = r["result"]["access_token"]
        _token["exp"] = time.time() + r["result"]["expire_time"] - 60
        return _token["v"]
    raise Exception("Token error: " + json.dumps(r))


def api(method, path, body=None):
    """Make an authenticated Tuya API call."""
    tok = get_token()
    t = str(int(time.time() * 1000))
    bs = json.dumps(body) if body else ""
    body_hash = hashlib.sha256(bs.encode()).hexdigest()
    payload = method + "\n" + body_hash + "\n\n" + path
    raw = ACCESS_ID + tok + t + payload
    s = hmac.new(
        ACCESS_SECRET.encode(),
        raw.encode(),
        hashlib.sha256
    ).hexdigest().upper()

    headers = {
        "client_id": ACCESS_ID,
        "access_token": tok,
        "sign": s,
        "t": t,
        "sign_method": "HMAC-SHA256",
        "Content-Type": "application/json",
    }

    if method == "GET":
        return req.get(ENDPOINT + path, headers=headers).json()
    return req.post(ENDPOINT + path, headers=headers, json=body).json()


# --- IR remote helpers ---

def load_keys():
    """Load IR remote panel and its learned keys."""
    r = api("GET", f"/v2.0/infrareds/{IR_DEVICE_ID}/remotes")
    if r.get("success") and r.get("result"):
        _remote["id"] = r["result"][0]["remote_id"]

        kr = api("GET", f"/v2.0/infrareds/{IR_DEVICE_ID}/remotes/{_remote['id']}/keys")
        if kr.get("success") and kr.get("result"):
            key_list = kr["result"].get("key_list", [])
            for k in key_list:
                _remote["keys"][k["key_name"]] = {
                    "key": k["key"],
                    "key_id": k["key_id"],
                }

    return _remote["id"], _remote["keys"]


def send_key(name):
    """Send an IR command by key name."""
    if not _remote["id"]:
        load_keys()
    if name not in _remote["keys"]:
        return {
            "ok": False,
            "msg": f"No key: {name}, have: {list(_remote['keys'].keys())}",
        }
    ki = _remote["keys"][name]
    return api(
        "POST",
        f"/v2.0/infrareds/{IR_DEVICE_ID}/remotes/{_remote['id']}/raw/command",
        {"category_id": 13, "key": ki["key"], "key_id": ki["key_id"]},
    )


def find_key(target):
    """Find a key by partial name match."""
    for name in _remote["keys"]:
        if target in name:
            return name
    return None


# --- MCP protocol ---

TOOLS = [
    {"name": "pillow_status", "description": "Check connection and available keys", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "pillow_power", "description": "Power on/off the device", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "pillow_pat_toggle", "description": "Toggle patting on/off", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "pillow_speed_up", "description": "Increase patting speed", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "pillow_speed_down", "description": "Decrease patting speed", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "pillow_light", "description": "Toggle light on/off", "inputSchema": {"type": "object", "properties": {}}},
]

# Map tool names to IR key search terms.
# Change these to match the key names you used when learning IR codes.
# Use pillow_status to see all available key names.
KEY_MAP = {
    "pillow_pat_toggle": "\u5f00\u5173",       # 拍打开关
    "pillow_speed_up": "\u5feb",             # 加快
    "pillow_speed_down": "\u6162",            # 减慢
    "pillow_light": "\u706f",                # 灯光
    "pillow_power": "\u5f00\u5173\u673a",       # 开关机
}


def ok_msg(rid, text):
    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": text}]}}


def err_msg(rid, text):
    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": text}], "isError": True}}


def process(d):
    """Process a single MCP JSON-RPC request."""
    m = d.get("method", "")
    rid = d.get("id")
    p = d.get("params", {})

    if m == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "tuya-ir-mcp", "version": "1.0.0"},
            },
        }

    if m == "notifications/initialized":
        return None

    if m == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if m == "tools/call":
        n = p.get("name", "")
        try:
            if n == "pillow_status":
                ri, k = load_keys()
                return ok_msg(rid, f"remote:{ri}\nkeys:{list(k.keys())}")

            if n in KEY_MAP:
                if not _remote["id"]:
                    load_keys()
                key_name = find_key(KEY_MAP[n])
                if not key_name:
                    return err_msg(
                        rid,
                        f"Key not found for {n}, have: {list(_remote['keys'].keys())}",
                    )
                r = send_key(key_name)
                return ok_msg(
                    rid,
                    f"{key_name}: {'done' if r.get('success') else json.dumps(r)}",
                )

            return err_msg(rid, f"unknown:{n}")

        except Exception as e:
            return err_msg(rid, str(e))

    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"unknown:{m}"}}


@app.route("/mcp", methods=["POST"])
def mcp():
    d = request.get_json()
    if isinstance(d, list):
        return jsonify([r for x in d for r in (process(x),) if r])
    r = process(d)
    return jsonify(r) if r else ("", 204)


# --- Entry point ---

if __name__ == "__main__":
    try:
        ri, k = load_keys()
        print(f"Connected! Remote: {ri}")
        for name in k:
            print(f"  {name}")
    except Exception as e:
        print(f"Warning: {e}")

    app.run(host="0.0.0.0", port=PORT)
