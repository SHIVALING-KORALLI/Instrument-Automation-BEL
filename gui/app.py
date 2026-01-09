# gui/app.py
"""
Flask Web GUI for Instrument Automation with manual controls and daily-report logging.

Usage:
    python gui/app.py

Behavior:
 - Serves the GUI from gui/static/
 - Exposes control endpoints (PSU / GEN / SA)
 - /api/run triggers automation and appends a session sheet into the daily Excel (source="GUI-Auto")
 - The ReportGenerator used is the daily one (reports/report_YYYYMMDD.xlsx)
"""

from __future__ import annotations
import os
import datetime
import json
import threading
from collections import deque
from typing import Any, Dict
import struct
import base64
from flask import make_response

from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context

from drivers.base_driver import _USED_RESOURCES

import subprocess
import serial  

import socket, binascii

# Ensure project root is importable whether running from project root or gui/
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(BASE_DIR))

# Import core drivers & report generator
from core.controller import AutomationController
from drivers.n8739a_supply import N8739APowerSupply
from drivers.smb_generator import SMB100AGenerator
from drivers.pxa_analyzer import N9030BAnalyzer
from core.report_generator import ReportGenerator
from drivers.base_driver import discover as visa_discover

# Static folder (gui/static)
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR), template_folder=str(STATIC_DIR))

# Controller & offline placeholders
ctrl = AutomationController()
ctrl.attach("psu", N8739APowerSupply(auto_connect=False))
ctrl.attach("psu2", N8739APowerSupply(auto_connect=False))
ctrl.attach("gen", SMB100AGenerator(auto_connect=False))
ctrl.attach("sa", N9030BAnalyzer(auto_connect=False))

# SSE logging
LOG_MAX = 2000
_log_deque = deque(maxlen=LOG_MAX)
_log_cond = threading.Condition()

def log_event(obj: Dict[str, Any]) -> None:
    with _log_cond:
        obj["ts"] = datetime.datetime.now().isoformat()
        _log_deque.append(obj)
        _log_cond.notify_all()

def _iter_log_stream():
    """Generator for Server-Sent Events. Yields backlog once, then only new events."""
    last_sent = 0
    while True:
        with _log_cond:
            _log_cond.wait(timeout=1.0)
            # send all new items since last_sent
            while last_sent < len(_log_deque):
                item = list(_log_deque)[last_sent]
                yield f"data: {json.dumps(item)}\n\n"
                last_sent += 1

# Serve login
@app.route("/")
def login():
    return send_from_directory(app.static_folder, "index.html")  #change to login.html after testing

# SSE endpoint
@app.route("/api/logs")
def api_logs():
    return Response(stream_with_context(_iter_log_stream()), mimetype="text/event-stream")

# Discover
@app.route("/api/discover")
def api_discover():
    try:
        resources = visa_discover()
        log_event({"type": "discover", "resources": resources})
        return jsonify({"status": "ok", "resources": resources})
    except Exception as e:
        log_event({"type": "discover_error", "err": str(e)})
        return jsonify({"status": "error", "message": str(e)}), 500

# Attach (manual or auto)
@app.route("/api/attach", methods=["POST"])
def api_attach():
    data = request.json or {}
    name = data.get("name")
    resource = data.get("resource")
    if not name:
        return jsonify({"status": "error", "message": "Missing 'name'"}), 400
    inst = ctrl.get(name)
    if not inst:
        return jsonify({"status": "error", "message": f"No instrument named '{name}' attached"}), 404
    try:
        if resource in (None, "", "auto"):
            cls = inst.__class__
            log_event({"type": "attach", "name": name, "resource": "auto"})
            new_inst = cls()  # auto-detect via driver
            ctrl.attach(name, new_inst)
            idn = new_inst.idn()
            log_event({"type": "attach_ok", "name": name, "idn": idn})
            return jsonify({"status": "ok", "idn": idn})
        else:
            # manual attach by resource string
            if hasattr(inst, "close"):
                try:
                    inst.close()
                except Exception:
                    pass
            setattr(inst, "_resource", resource)
            if hasattr(inst, "_rm"):
                setattr(inst, "_rm", None)
            inst.open()
            idn = inst.idn()
            log_event({"type": "attach_ok", "name": name, "resource": resource, "idn": idn})
            return jsonify({"status": "ok", "idn": idn})
    except Exception as e:
        log_event({"type": "attach_error", "name": name, "err": str(e)})
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/status")
def api_status():
    status = {}
    try:
        psu = ctrl.get("psu")
        psu2 = ctrl.get("psu2")
        gen = ctrl.get("gen")
        sa = ctrl.get("sa")

        if psu:
            try:
                v = psu.measure_voltage() if hasattr(psu, "measure_voltage") else None
            except Exception as e:
                v = f"err:{e}"
            try:
                i = psu.measure_current() if hasattr(psu, "measure_current") else None
            except Exception as e:
                i = f"err:{e}"
            status["psu"] = {"voltage": v, "current": i}

        if psu2:
            try:
                v2 = psu2.measure_voltage() if hasattr(psu2, "measure_voltage") else None
            except Exception as e:
                v2 = f"err:{e}"
            try:
                i2 = psu2.measure_current() if hasattr(psu2, "measure_current") else None
            except Exception as e:
                i2 = f"err:{e}"
            status["psu2"] = {"voltage": v2, "current": i2}

        if gen:
            try:
                f = gen.get_frequency() if hasattr(gen, "get_frequency") else None
            except Exception as e:
                f = f"err:{e}"
            try:
                p = gen.get_power() if hasattr(gen, "get_power") else None
            except Exception as e:
                p = f"err:{e}"
            try:
                rf = gen.is_rf_on() if hasattr(gen, "is_rf_on") else None
            except Exception as e:
                rf = f"err:{e}"
            status["gen"] = {"frequency": f, "power": p, "rf": rf}

        if sa:
            try:
                cf = sa.get_center_frequency() if hasattr(sa, "get_center_frequency") else None
            except Exception as e:
                cf = f"err:{e}"
            try:
                sp = sa.get_span() if hasattr(sa, "get_span") else None
            except Exception as e:
                sp = f"err:{e}"
            # RBW
            try:
                rbw = sa.get_rbw() if hasattr(sa, "get_rbw") else None
            except Exception as e:
                rbw = None
            # REF LEVEL
            try:
                ref = sa.get_ref_level() if hasattr(sa, "get_ref_level") else None
            except Exception as e:
                ref = f"err:{e}"

            status["sa"] = {"center": cf, "span": sp, "rbw": rbw, "ref_level": ref}

        log_event({"type": "status_poll", "status": status})
        return jsonify({"status": "ok", "data": status})
    except Exception as e:
        log_event({"type": "status_error", "err": str(e)})
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/run", methods=["POST"])
def api_run():
    """
    Orchestrates automation for a single board/channel run.
    Expects JSON:
      {
        "board_no": 1,
        "channel_no": 1,
        "pulse_width": "00 01",
        "prt": "0A AB 00 00"
      }
    """
    data = request.json or {}

    # parse inputs (basic validation)
    try:
        board_no = int(data.get("board_no", 1))
        channel_no = int(data.get("channel_no", 1))
        pulse_width = (data.get("pulse_width") or "00 00").strip()
        prt = (data.get("prt") or "00 00 00 00").strip()
    except Exception as e:
        return jsonify({"status": "error", "message": f"Invalid inputs: {e}"}), 400

    # progress handler - emits SSE log events using log_event()
    def progress_handler(progress_data):
        # enrich with board/channel for GUI convenience
        progress_data = dict(progress_data)
        progress_data.setdefault("board_no", board_no)
        progress_data.setdefault("channel_no", channel_no)
        log_event({"type": "automation_progress", "data": progress_data})

    # register callback
    ctrl.set_progress_callback(progress_handler)

    try:
        log_event({"type": "automation_start", "message": f"Starting automation Board {board_no} Ch {channel_no}"})

        # Call controller with parameters
        results = ctrl.run_example_sequence(board_no=board_no,
                                            channel_no=channel_no,
                                            pulse_width=pulse_width,
                                            prt=prt)

        from core.report_generator import ReportGenerator
        rg = ReportGenerator()
        rg.add_dtrc_results(board_no=board_no, channel_no=channel_no, results=results)
        report_path = rg.save()

        log_event({"type": "automation_complete", "message": f"Completed Board {board_no} Ch {channel_no}", "report": report_path})

        return jsonify({"status": "ok", "rows": len(results), "report": report_path})
    except Exception as e:
        log_event({"type": "automation_error", "message": str(e)})
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        ctrl.set_progress_callback(None)

# PSU endpoints
@app.route("/api/psu/set", methods=["POST"])
def api_psu_set():
    data = request.json or {}
    name = data.get("name", "psu") 
    psu = ctrl.get(name)
    if not psu:
        return jsonify({"status": "error", "message": f"PSU '{name}' not attached"}), 404
    try:
        if "voltage" in data:
            psu.set_voltage(float(data["voltage"]))
        if "current" in data:
            psu.set_current(float(data["current"]))
        log_event({"type": "psu_set", "name": name, "voltage": data.get("voltage"), "current": data.get("current")})
        return jsonify({"status": "ok"})
    except Exception as e:
        log_event({"type": "psu_set_error", "name": name, "err": str(e)})
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/psu/output", methods=["POST"])
def api_psu_output():
    data = request.json or {}
    name = data.get("name", "psu")
    psu = ctrl.get(name)
    if not psu:
        return jsonify({"status": "error", "message": f"PSU '{name}' not attached"}), 404
    state = data.get("state")
    try:
        if state == "on":
            psu.output_on()
        else:
            psu.output_off()
        log_event({"type": "psu_output", "name": name, "state": state})
        return jsonify({"status": "ok"})
    except Exception as e:
        log_event({"type": "psu_output_error", "name": name, "err": str(e)})
        return jsonify({"status": "error", "message": str(e)}), 500

# Generator endpoints
@app.route("/api/gen/set", methods=["POST"])
def api_gen_set():
    gen = ctrl.get("gen")
    if not gen:
        return jsonify({"status": "error", "message": "Generator not attached"}), 404
    data = request.json or {}
    try:
        if "frequency" in data:
            gen.set_frequency(float(data["frequency"]))
        if "power" in data:
            gen.set_power(float(data["power"]))
        log_event({"type": "gen_set", "frequency": data.get("frequency"), "power": data.get("power")})
        if data.get("log"):
            rg = ReportGenerator()
            meta = {"timestamp": datetime.datetime.now().isoformat(), "initiated_by": "GUI-Manual", "action": "gen_set"}
            r = {"measured_frequency_hz": data.get("frequency"), "measured_power_dbm": data.get("power")}
            rg.add_results([r], source="GUI-Manual", title="Manual Generator Action", metadata=meta)
            rg.save()
        return jsonify({"status": "ok"})
    except Exception as e:
        log_event({"type": "gen_set_error", "err": str(e)})
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/gen/rf", methods=["POST"])
def api_gen_rf():
    gen = ctrl.get("gen")
    if not gen:
        return jsonify({"status": "error", "message": "Generator not attached"}), 404
    data = request.json or {}
    state = data.get("state")
    try:
        if state == "on":
            gen.rf_on()
        else:
            gen.rf_off()
        log_event({"type": "gen_rf", "state": state})
        if data.get("log"):
            rg = ReportGenerator()
            meta = {"timestamp": datetime.datetime.now().isoformat(), "initiated_by": "GUI-Manual", "action": f"gen_rf_{state}"}
            r = {"measured_frequency_hz": gen.get_frequency() if hasattr(gen, "get_frequency") else None,
                 "measured_power_dbm": gen.get_power() if hasattr(gen, "get_power") else None}
            rg.add_results([r], source="GUI-Manual", title=f"Manual Gen RF {state}", metadata=meta)
            rg.save()
        return jsonify({"status": "ok"})
    except Exception as e:
        log_event({"type": "gen_rf_error", "err": str(e)})
        return jsonify({"status": "error", "message": str(e)}), 500

# Analyzer endpoints
@app.route("/api/sa/set", methods=["POST"])
def api_sa_set():
    sa = ctrl.get("sa")
    if not sa:
        return jsonify({"status": "error", "message": "Analyzer not attached"}), 404
    data = request.json or {}
    try:
        if "center" in data:
            sa.set_center_frequency(float(data["center"]))
        if "span" in data:
            sa.set_span(float(data["span"]))
        if "rbw" in data:
            sa.set_rbw(float(data["rbw"]))
        log_event({"type": "sa_set", "center": data.get("center"), "span": data.get("span"), "rbw": data.get("rbw")})
        if data.get("log"):
            rg = ReportGenerator()
            meta = {"timestamp": datetime.datetime.now().isoformat(), "initiated_by": "GUI-Manual", "action": "sa_set"}
            r = {"measured_frequency_hz": data.get("center"), "measured_power_dbm": None}
            rg.add_results([r], source="GUI-Manual", title="Manual SA Setting", metadata=meta)
            rg.save()
        return jsonify({"status": "ok"})
    except Exception as e:
        log_event({"type": "sa_set_error", "err": str(e)})
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/sa/marker")
def api_sa_marker():
    sa = ctrl.get("sa")
    if not sa:
        return jsonify({"status": "error", "message": "Analyzer not attached"}), 404
    try:
        sa.peak_search()
        freq = sa.marker_frequency()
        power = sa.marker_power()
        log_event({"type": "sa_marker", "freq": freq, "power": power})
        return jsonify({"status": "ok", "freq_hz": freq, "power_dbm": power})
    except Exception as e:
        log_event({"type": "sa_marker_error", "err": str(e)})
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/sa/screenshot")
def api_sa_screenshot():
    sa = ctrl.get("sa")
    if not sa:
        return jsonify({"status": "error", "message": "Analyzer not attached"}), 404
    try:
        filename = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        reports_dir = os.path.join(os.path.dirname(__file__), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        path = os.path.join(reports_dir, filename)

        sa.save_screenshot(path)

        log_event({"type": "sa_screenshot", "file": path})
        return jsonify({"status": "ok", "file": f"reports/{filename}"})
    except Exception as e:
        log_event({"type": "sa_screenshot_error", "err": str(e)})
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/sa/trace_clear", methods=["POST"])
def api_sa_trace_clear():
    sa = ctrl.get("sa")
    if not sa:
        return jsonify({"status": "error", "message": "Analyzer not attached"}), 400
    try:
        sa.trace_clear()
        return jsonify({"status": "ok", "message": "Trace cleared"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/sa/trace_max", methods=["POST"])
def api_sa_trace_max():
    sa = ctrl.get("sa")
    if not sa:
        return jsonify({"status": "error", "message": "Analyzer not attached"}), 400
    try:
        sa.trace_max()
        return jsonify({"status": "ok", "message": "Trace mode set to Max Hold"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/sa/trace")
def api_sa_trace():
    sa = ctrl.get("sa")
    if not sa:
        return jsonify({"status": "error", "message": "Analyzer not attached"}), 404
    try:
        # request trace binary (driver returns raw payload bytes)
        payload = sa.get_trace_binary(trace=1, fmt="REAL,64")
        if not payload:
            return jsonify({"status": "error", "message": "Empty trace payload"}), 500

        nbytes = len(payload)
        if nbytes % 8 != 0:
            # not an even multiple of 8 -> maybe it's floats (4 bytes) or single-precision
            # attempt to parse as REAL,32
            try:
                payload32 = sa.get_trace_binary(trace=1, fmt="REAL,32")
                payload = payload32
                nbytes = len(payload)
            except Exception:
                pass

        count = nbytes // 8
        # try big-endian then little-endian
        def try_unpack(fmt_char):
            try:
                fmt = f">{count}d" if fmt_char == ">" else f"<{count}d"
                vals = struct.unpack(fmt, payload)
                # sanity checks: finite and not huge
                finite = all((not (abs(v) > 1e300 or v != v)) for v in vals)
                return vals if finite else None
            except Exception:
                return None

        vals = try_unpack(">") or try_unpack("<")
        if vals is None:
            # fallback: return binary base64 so client can decide
            b64 = base64.b64encode(payload).decode("ascii")
            return jsonify({"status": "ok", "format": "base64", "data": b64, "note": "Unable to auto-parse floats; returned base64 binary."})

        # return CSV and JSON array
        csv_lines = "\n".join(str(v) for v in vals)
        # return as file download (CSV) when requested with ?download=1
        if request.args.get("download") == "1":
            resp = make_response(csv_lines)
            resp.headers["Content-Type"] = "text/csv"
            resp.headers["Content-Disposition"] = "attachment; filename=trace.csv"
            return resp

        return jsonify({"status": "ok", "format": "list", "count": len(vals), "data": list(vals)})
    except Exception as e:
        log_event({"type": "sa_trace_error", "err": str(e)})
        return jsonify({"status": "error", "message": str(e)}), 500
    
@app.route("/api/sa/amp", methods=["POST"])
def api_sa_amp():
    sa = ctrl.get("sa")
    if not sa:
        return jsonify({"status": "error", "message": "Analyzer not attached"}), 404
    data = request.json or {}
    action = data.get("action")
    step = float(data.get("step", 10.0))  # default 1 dB
    try:
        if action == "up":
            new = sa.ref_level_up(step)
        elif action == "down":
            new = sa.ref_level_down(step)
        elif action == "set":
            new = float(data.get("level"))
            sa.set_ref_level(new)
        else:
            return jsonify({"status": "error", "message": "Invalid action"}), 400

        log_event({"type": "sa_amp", "action": action, "ref_level_dbm": new})
        return jsonify({"status": "ok", "ref_level_dbm": new})
    except Exception as e:
        log_event({"type": "sa_amp_error", "err": str(e)})
        return jsonify({"status": "error", "message": str(e)}), 500

# Paths
BASE_DIR = os.path.dirname(__file__)
SCRIPT_PATH = os.path.join(BASE_DIR, "scripts", "program_fpga.tcl")

# Absolute path to vivado.bat
VIVADO_CMD = r"C:\Xilinx\2025.1\Vivado\bin\vivado.bat"

# Lock + state
program_lock = threading.Lock()
current_process = None
fpga_status = "idle"   # "idle", "programming", "done", "error"

@app.route("/api/fpga/program", methods=["POST"])
def api_fpga_program():
    global current_process, fpga_status

    if not program_lock.acquire(blocking=False):
        return jsonify({
            "status": "error",
            "message": "FPGA programming already in progress"
        }), 409

    try:
        fpga_status = "programming"

        cmd = [VIVADO_CMD, "-mode", "batch", "-source", SCRIPT_PATH]

        current_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8'  # explicitly set encoding
        )
            
        def monitor_proc(proc):
            global fpga_status
            try:
                for line in proc.stdout:
                    print(line, end = " ")
                    if "FPGA programmed successfully" in line.lower():
                        fpga_status = "done"
                    stderr = proc.stderr.read()
                    proc.wait()
                    if proc.returncode != 0 and fpga_status != "done":
                        fpga_status  = "error"
                        print("FPGA programming failed")
                        print("stderr:", stderr)
                    elif fpga_status != "done":
                        fpga_status = "done"
                        print("Pragramming Successful")
            finally:
                program_lock.release()

        threading.Thread(target=monitor_proc, args=(current_process,), daemon=True).start()

        return jsonify({
            "status": "ok",
            "message": "FPGA programming started in background"
        })

    except Exception as e:
        program_lock.release()
        fpga_status = "error"
        return jsonify({"status": "error", "message": str(e)}), 500 

@app.route("/api/fpga/status", methods=["GET"])
def api_fpga_status():
    return jsonify({"status": fpga_status})
    

def _hexify(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)

@app.route("/api/udp/send", methods=["POST"])
def api_udp_send():
    """
    Send a 40-byte UDP packet (no receive).
    JSON body example:
      {
        "src_ip": "xxxxx", 
        "src_port": 6005,
        "dst_ip": "xxxxx",
        "dst_port": 5005,
        "payload": "01 02 03 ... (40 bytes hex)"
      }
    """
    data = request.json or {}
    src_ip = data.get("src_ip")
    src_port = int(data.get("src_port", 0))
    dst_ip = data.get("dst_ip")
    dst_port = int(data.get("dst_port", 0))
    payload_hex = (data.get("payload") or "")
    payload_hex = "".join(payload_hex.split())  # strip whitespace

    if not (src_ip and src_port and dst_ip and dst_port and payload_hex):
        return jsonify({"status": "error",
                        "message": "Need src_ip, src_port, dst_ip, dst_port, payload"}), 400

    try:
        payload = binascii.unhexlify(payload_hex)
    except Exception:
        return jsonify({"status": "error", "message": "Invalid hex payload"}), 400

    if len(payload) != 40:
        return jsonify({"status": "error", "message": "Payload must be exactly 40 bytes"}), 400

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # bind to fixed source ip/port
        sock.bind((src_ip, src_port))
        sock.settimeout(2.0)

        # send once
        sent_bytes = sock.sendto(payload, (dst_ip, dst_port))

        # try to read back (loopback)
        try:
            resp, addr = sock.recvfrom(65536)
            recv_hex = _hexify(resp)
        except socket.timeout:
            recv_hex = "NO RESPONSE"

        sock.close()

        return jsonify({"status": "ok",
                        "sent_bytes": sent_bytes,
                        "src": f"{src_ip}:{src_port}",
                        "dst": f"{dst_ip}:{dst_port}",
                        "payload": _hexify(payload),
                        "received": recv_hex})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Absolute path to your reports folder
REPORTS_DIR = r"C:\Users\pinky\Downloads\deci-hex\deci-hex\gpt\reports"

@app.route("/reports/latest")
def download_latest_report():
    """Find and send the latest report file."""
    try:
        files = [f for f in os.listdir(REPORTS_DIR) if f.endswith(".xlsx")]
        if not files:
            return jsonify({"status": "error", "message": "No reports found"}), 404

        latest = max(
            files,
            key=lambda f: os.path.getmtime(os.path.join(REPORTS_DIR, f))
        )
        return send_from_directory(REPORTS_DIR, latest, as_attachment=True)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Instruments list
@app.route("/api/instruments")
def api_instruments():
    try:
        idns = ctrl.list_instruments()
        return jsonify(idns)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
 
@app.route("/api/close_all", methods=["POST"])
def api_close_all():
    try:
        ctrl.close_all()
        # Also force VISA resource release
        try:
            import pyvisa
            pyvisa.ResourceManager().close()
        except Exception as e:
            print("⚠ VISA resource cleanup warning:", e)
        _USED_RESOURCES.clear()
        log_event({"type": "close_all"})
        return jsonify({"status": "ok"})
    except Exception as e:
        log_event({"type": "close_all_error", "err": str(e)})
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, threaded=True, debug=False)

