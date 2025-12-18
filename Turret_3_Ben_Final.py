#!/usr/bin/env python3

import socket
import time
import json
import os
import math
import threading
import sys
import traceback
import urllib.request
from urllib.parse import unquote_plus
import multiprocessing
import RPi.GPIO as GPIO

from shifter import Shifter
from stepper_class_shiftregister_multiprocessing import Stepper

######## Global Variables #####

DATA_PIN  = 16            # GPIO Pins for Shift Register
LATCH_PIN = 20
CLOCK_PIN = 21

LASER_PIN = 17              # Laser stuff
LASER_ON_SECONDS = 3 

USE_LOCAL_JSON = False                  # Flag to change for when doing testing outside of class without JSON server set up
LOCAL_JSON_FILE = "positions.json"      # Local JSON file used for testing, downloaded from test server during class
JSON_URL = "http://192.168.1.254:8000/positions.json"

MY_TEAM = "3"   # turret id (string)

HOST = ""
PORT = 8080    # pi webserver port

ANGLE_TOLERANCE_DEG = 0.40    # For checking if the motors have reached the target angle before firing the laser

CALIB_FILE = "calibration.json"        # For storing the calibrated angles

EL_INVERT = -1      #flip elevation direction because motor was backwards
AZ_INVERT = -1      #flip azimuth direciton because motor was backwards

s = None
m_az = None
m_el = None

positions = {}              # target coordinates
my_turret = None
processed_targets = []   # dicts for all the specifics for each target from the positions file
raw_target_angles = {}   # raw angles for targets
calibration = {}         # offset angles applied during calibration

####### JSON and Poistion Grabbing Stuff #######

def load_positions():               # grab the positions either from the local JSON when testing at home or the server during class
    global positions
    try:
        if USE_LOCAL_JSON:
            if not os.path.exists(LOCAL_JSON_FILE):
                print(f"ERROR LOCAL JSON '{LOCAL_JSON_FILE}' NOT FOUND", file=sys.stderr)
                positions = {}
                return False
            with open(LOCAL_JSON_FILE, 'r') as f:
                positions = json.load(f)
        else:
            with urllib.request.urlopen(JSON_URL, timeout=6) as resp:
                positions = json.loads(resp.read().decode('utf-8'))
        return True
    except Exception as e:
        print("Error loading positions", e, file=sys.stderr)
        positions = {}
        return False

def polar_to_cartesian_cm(r_cm, theta_rad, z_cm=0.0):
    x = r_cm * math.cos(theta_rad)
    y = r_cm * math.sin(theta_rad)
    return x, y, z_cm

def normalize_deg(angle):
    return (angle % 360.0 + 360.0) % 360.0

def compute_az_el(tur_r, tur_theta, tgt_r, tgt_theta, tgt_z):       # Compute the azimuth and elevation angles needed for each target

    tx, ty, tz = polar_to_cartesian_cm(tur_r, tur_theta, 6.0)       # Turret Positions, z is measured from ground to laser height
    px, py, pz = polar_to_cartesian_cm(tgt_r, tgt_theta, tgt_z)     # Target Positions

    # Whole bunch of vector stuff for calculating angles

    vx = px - tx
    vy = py - ty
    vz = pz - tz

    # Vector from turret to center
    zx = -tx
    zy = -ty

    # Normalize vectors
    v_len = math.hypot(vx, vy)
    z_len = math.hypot(zx, zy)

    if v_len == 0 or z_len == 0:
        az_deg = 0.0
    else:
        vx /= v_len
        vy /= v_len
        zx /= z_len
        zy /= z_len

        dot = zx * vx + zy * vy
        cross = zx * vy - zy * vx 

        az_rad = math.atan2(cross, dot)
        az_deg = normalize_deg(math.degrees(az_rad))

    
    horiz = math.hypot(px - tx, py - ty)
    el_deg = math.degrees(math.atan2(vz, horiz))

    dist = math.sqrt((px - tx)**2 + (py - ty)**2 + vz*vz)

    return az_deg, el_deg, dist

def build_processed_targets():      # grab the targets from the json and get all the specific info about each of them

    global processed_targets, my_turret, raw_target_angles
    processed_targets = []
    raw_target_angles = {}

    turrets = positions.get("turrets", {})
    globes = positions.get("globes", [])

    my_turret = turrets.get(MY_TEAM)
    if my_turret is None:
        print(f"ERROR: MY_TEAM '{MY_TEAM}' not found in JSON", file=sys.stderr)
        return False

    for k, v in turrets.items():   
        if k == MY_TEAM:
            continue
        label = f"turret{k}"
        az_raw, el_raw, dist = compute_az_el(my_turret["r"], my_turret["theta"], v["r"], v["theta"], 0.0)
        raw_target_angles[label] = {"az": az_raw, "el": el_raw}
        c = calibration.get(label, {"az": 0.0, "el": 0.0})
        az_applied = normalize_deg(az_raw + c.get("az", 0.0))
        el_applied = el_raw + c.get("el", 0.0)
        processed_targets.append({
            "label": label,
            "kind": "turret",
            "id": k,
            "r": v["r"], "theta": v["theta"], "z": 0.0,
            "az_deg_raw": az_raw, "el_deg_raw": el_raw,
            "az_deg_applied": az_applied, "el_deg_applied": el_applied,
            "distance": dist
        })

    for i, g in enumerate(globes, start=1):
        label = f"globe{i}"
        az_raw, el_raw, dist = compute_az_el(my_turret["r"], my_turret["theta"], g["r"], g["theta"], g.get("z", 0.0))
        raw_target_angles[label] = {"az": az_raw, "el": el_raw}
        c = calibration.get(label, {"az": 0.0, "el": 0.0})
        az_applied = normalize_deg(az_raw + c.get("az", 0.0))
        el_applied = el_raw + c.get("el", 0.0)
        processed_targets.append({
            "label": label,
            "kind": "globe",
            "id": i-1,
            "r": g["r"], "theta": g["theta"], "z": g.get("z", 0.0),
            "az_deg_raw": az_raw, "el_deg_raw": el_raw,
            "az_deg_applied": az_applied, "el_deg_applied": el_applied,
            "distance": dist
        })

    processed_targets.sort(key=lambda t: t["az_deg_raw"])       # sort targets by raw azimuth ascending (0–360) for smooth targeting

    
    return True

def load_calibration():
    global calibration
    if not os.path.exists(CALIB_FILE):
        calibration = {}
        save_calibration()  # create empty file
        return
    try:
        with open(CALIB_FILE, 'r') as f:
            calibration = json.load(f)
    except Exception as e:
        print("Error loading calibration.json:", e, file=sys.stderr)
        calibration = {}

def save_calibration():
    try:
        with open(CALIB_FILE, 'w') as f:
            json.dump(calibration, f, indent=2)
    except Exception as e:
        print("Error saving calibration.json:", e, file=sys.stderr)


####### Laser and Motor Stuff #########

def setup_motors():
    global s, m_az, m_el
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    s = Shifter(data=DATA_PIN, latch=LATCH_PIN, clock=CLOCK_PIN)
    lock1 = multiprocessing.Lock()
    lock2 = multiprocessing.Lock()
    # instantiate az then el
    m_az = Stepper(s, lock1)
    m_el = Stepper(s, lock2)
    m_az.zero()
    m_el.zero()
    print("Motors initialized and zeroed.")

def setup_laser():
    GPIO.setup(LASER_PIN, GPIO.OUT)
    GPIO.output(LASER_PIN, GPIO.LOW)

def fire_laser():
    try:
        print("Laser ON")
        GPIO.output(LASER_PIN, GPIO.HIGH)
        time.sleep(LASER_ON_SECONDS)
    finally:
        GPIO.output(LASER_PIN, GPIO.LOW)
        print("Laser OFF")

def handle_laser_request():
    threading.Thread(target=fire_laser, daemon=True).start()


def wait_for_motors(az_target, el_target):      # Wait for motors to reach target before firing or doing other stuff
    while True:
        with m_az.angle.get_lock():
            az_now = m_az.angle.value
        with m_el.angle.get_lock():
            el_now = m_el.angle.value

        az_err = abs((az_target - az_now + 180.0) % 360.0 - 180.0)
        el_err = abs((el_target - el_now + 180.0) % 360.0 - 180.0)

        if az_err <= ANGLE_TOLERANCE_DEG and el_err <= ANGLE_TOLERANCE_DEG:
            return True

        time.sleep(0.03)


####### UI Button Actions #########


def manual_step(axis, delta):
    if axis == "az":
        m_az.rotate(AZ_INVERT * float(delta))
    elif axis == "el":
        m_el.rotate(EL_INVERT * float(delta))

def goto_home():
    m_az.goAngle(0.0)
    m_el.goAngle(0.0)
    wait_for_motors(0.0, 0.0)

def set_zero():
    m_az.zero()
    m_el.zero()

def goto_target(label):                                                         # Go to selected target from list
    tgt = next((t for t in processed_targets if t["label"] == label), None)
    if tgt is None:
        print("goto: target not found:", label)
        return False

    def worker():
        try:
            az_goal = float(tgt["az_deg_applied"])
            el_goal = float(tgt["el_deg_applied"])
            print(f"[GOTO] moving to {label}: AZ={az_goal:.2f}, EL={el_goal:.2f}")
            m_az.goAngle(az_goal)
            m_el.goAngle(EL_INVERT * el_goal)
            ok = wait_for_motors(az_goal, EL_INVERT * el_goal)
            print("[GOTO] done, reached:", ok)
        except Exception as e:
            print("Exception in goto worker:", e)
            traceback.print_exc()

    thr = threading.Thread(target=worker, daemon=True)
    thr.start()
    return True

def save_calibration_for_label(label):                  # save current motor positions to az and el angles for the currently selected target

    if label not in raw_target_angles:
        return False, "label not found in raw angles"
    raw = raw_target_angles[label]
    with m_az.angle.get_lock():
        cur_az = float(m_az.angle.value)
    with m_el.angle.get_lock():
        cur_el = EL_INVERT*float(m_el.angle.value)
    raw_az = float(raw["az"])

    def shortest_signed(a):
        x = ((a + 180.0) % 360.0) - 180.0
        return x

    az_diff = shortest_signed(cur_az - raw_az)    # find shortest angle between current and processed azimuth bc you have to deal with wrap around
    el_diff = cur_el - float(raw["el"])           
    calibration[label] = {"az": az_diff, "el": el_diff}
    save_calibration()
    build_processed_targets()                                   # make sure to reload the target list and reprocess after updating calibraitions
    return True, {"az_offset": az_diff, "el_offset": el_diff}

def final_run_sequence():                                      # do the final automated sequence on the target list

    def worker():
        targets = sorted(
            processed_targets,
            key=lambda t: t["az_deg_applied"]
        )

        for t in targets:
            label = t["label"]
            az = float(t["az_deg_applied"])
            el = float(t["el_deg_applied"])

            print(f"[FINAL RUN] Moving to {label}: AZ={az:.2f}, EL={el:.2f}")

            m_az.goAngle(az)
            m_el.goAngle(EL_INVERT * el)

            while True:                         # for some reason when the turret goes across az = 0 it stops waiting so this is needed???
                reached = wait_for_motors(
                    az,
                    EL_INVERT * el,
                )
                if reached:
                    break
                print(f"[FINAL RUN] Still moving to {label}... waiting")
                time.sleep(0.1)

            print(f"[FINAL RUN] Reached {label}, firing laser")
            fire_laser()

            time.sleep(0.5)

        print("[FINAL RUN] Run complete")

    threading.Thread(target=worker, daemon=True).start()


######## HTTP Helpers ########


def recv_request(conn):
    try:
        return conn.recv(8192).decode('utf-8', errors='ignore')
    except:
        return ''

def parse_request_line(req_text):
    first = req_text.split("\r\n", 1)[0]
    parts = first.split()
    return (parts[0], parts[1]) if len(parts) >= 2 else ("GET", "/")

def parse_post_body(req_text):
    i = req_text.find("\r\n\r\n")
    if i < 0:
        return {}
    body = req_text[i+4:]
    out = {}
    for pair in body.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k] = unquote_plus(v)
    return out

def send_html(conn, html, status=200):
    try:
        b = html.encode()
        header = f"HTTP/1.1 {status} OK\r\nContent-Type: text/html\r\nConnection: close\r\nContent-Length: {len(b)}\r\n\r\n"
        conn.sendall(header.encode() + b)
    except Exception as e:
        print("send_html error:", e)

def send_json(conn, obj_dict):
    try:
        b = json.dumps(obj_dict).encode()
        header = f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: {len(b)}\r\n\r\n"
        conn.sendall(header.encode() + b)
    except Exception as e:
        print("send_json error:", e)

def send_file(conn, filepath, content_type):
    try:
        with open(filepath, "rb") as f:
            data = f.read()
        header = (
            "HTTP/1.1 200 OK\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(data)}\r\n"
            "Connection: close\r\n\r\n"
        )
        conn.sendall(header.encode() + data)
    except FileNotFoundError:
        send_html(conn, "<h1>404 Not Found</h1>", status=404)


####### HTML and Javascript Stuff #####


def page_html():
    return """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Captain Kesslers Turret Command</title>

<style>
body {
  font-family: Arial, sans-serif;
  margin: 0;
  padding: 0;
  display: flex;
  justify-content: center;
  background: #000;
}

#page {
  width: 100%;
  max-width: 900px;
  text-align: center;
}

#header {
  position: relative;
  width: 100%;
}

#header img {
  width: 100%;
  max-height: 550px;   /* ← controls how tall the image is */
  object-fit: contain; /* keeps aspect ratio */
  display: block;
  margin: 0 auto;
}

#header h1 {
  position: absolute;
  bottom: 16px;
  left: 50%;
  transform: translateX(-50%);
  margin: 0;
  padding: 10px 18px;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  border-radius: 8px;
  font-size: 28px;
}

.sect {
  border: 1px solid #ddd;
  padding: 12px;
  margin: 12px auto;
  border-radius: 6px;
  background: rgba(255,255,255,0.95);
}

button {
  padding: 8px 12px;
  margin: 6px;
}

#angles {
  white-space: pre;
  background: #f7f7f7;
  padding: 8px;
  border-radius: 4px;
}

#targetsDebug {
  max-height: 220px;
  overflow: auto;
  background: #f4f4f4;
  padding: 8px;
}
</style>
</head>

<body>
<div id="page">

  <div id="header">
    <img src="/capt_kessler2.jpg" alt="Captain Kessler">
    <h1>Captain Kesslers Turret Command</h1>
  </div>


<div class="sect">
  <h3>Manual</h3>
  <div><strong>Azimuth</strong><br>
    <button onclick="step('az',-5)">◀ -5°</button>
    <button onclick="step('az',-1)">◀ -1°</button>
    <button onclick="step('az',-0.5)">◀ -0.5°</button>
    <button onclick="step('az',0.5)">0.5° ▶</button>
    <button onclick="step('az',1)">1° ▶</button>
    <button onclick="step('az',5)">5° ▶</button>
  </div>
  <div style="margin-top:8px"><strong>Elevation</strong><br>
    <button onclick="step('el',-5)">▼ -5°</button>
    <button onclick="step('el',-1)">▼ -1°</button>
    <button onclick="step('el',-0.5)">▼ -0.5°</button>
    <button onclick="step('el',0.5)">0.5° ▲</button>
    <button onclick="step('el',1)">1° ▲</button>
    <button onclick="step('el',5)">5° ▲</button>
  </div>
  <div style="margin-top:10px;"><button onclick="zero()">Zero Motors</button></div>
      <button onclick="api('/laser','POST')">Laser (3s)</button>
      <button onclick="api('/home','POST')">
  Go Home
</button>
</div>

<div class="sect">
  <h3>Targets & Calibration</h3>
  <select id="targetSelect" style="width:320px;padding:8px;font-size:14px"></select>
  <div style="margin-top:10px">
    <button onclick="gotoSelected()">Go to selected target</button>
    <button onclick="saveCalibration()">Save Calibration (use current motor angles)</button>
    <button onclick="reloadTargets()">Reload Targets</button>
    <button onclick="finalRun()" style="background:#c62828;color:white;">FINAL RUN</button>
    <span id="targetMsg" style="margin-left:8px"></span>
  </div>
  <div style="margin-top:10px"><strong>Processed Targets (raw & applied):</strong>
    <pre id="targetsDebug"></pre>
  </div>
</div>

<div class="sect">
  <h3>Current Angles</h3>
  <div id="angles">Loading...</div>
</div>

<script>
async function api(path, method='GET', body=null){
  const opts = { method, headers: {} };
  if(body){
    opts.headers['Content-Type'] = 'application/x-www-form-urlencoded';
    opts.body = new URLSearchParams(body).toString();
  }
  const r = await fetch(path, opts);
  return r;
}

function step(axis, delta){
  api('/step','POST',{axis:axis, delta:String(delta)})
    .then(r=>r.json())
    .then(j=>{ if(!j.ok) alert('Step failed: '+(j.error||'')); });
}

function zero(){
  api('/zero','POST').then(r=>r.json()).then(j=>{ if(j.ok) alert('Zeroed'); });
}

function gotoSelected(){
  const sel = document.getElementById('targetSelect');
  const label = sel.value;
  if(!label){ alert('Select a target'); return; }
  document.getElementById('targetMsg').textContent = 'Going to '+label+'...';
  api('/goto','POST',{target:label}).then(r=>r.json()).then(j=>{
    if(j.ok) document.getElementById('targetMsg').textContent = 'Started moving to '+label;
    else document.getElementById('targetMsg').textContent = 'Error: '+(j.error||'');
    setTimeout(()=>document.getElementById('targetMsg').textContent='',2500);
  });
}

function saveCalibration(){
  const sel = document.getElementById('targetSelect');
  const label = sel.value;
  if(!label){ alert('Select a target'); return; }
  document.getElementById('targetMsg').textContent = 'Saving calibration for '+label+'...';
  api('/save_calibration','POST',{target:label}).then(r=>r.json()).then(j=>{
    if(j.ok){
      document.getElementById('targetMsg').textContent = 'Saved: az_offset=' + j.result.az_offset.toFixed(3) + '°, el_offset=' + j.result.el_offset.toFixed(3) + '°';
      // refresh processed targets list
      setTimeout(()=>reloadTargets(), 300);
    } else {
      document.getElementById('targetMsg').textContent = 'Error: ' + (j.error||'');
    }
    setTimeout(()=>document.getElementById('targetMsg').textContent = '', 3500);
  });
}

function reloadTargets(){
  api('/reload','POST').then(r=>r.json()).then(j=>{
    if(j.ok){ populateTargets(j.targets); }
    else alert('Reload failed: '+(j.error||''));
  });
}

function populateTargets(list){
  const sel = document.getElementById('targetSelect');
  sel.innerHTML = '';
  const dbg = document.getElementById('targetsDebug');
  dbg.textContent = JSON.stringify(list, null, 2);
  for(const t of list){
    const opt = document.createElement('option');
    opt.value = t.label;
    opt.text = t.label + ' (' + t.kind + ') rawA=' + t.az_deg_raw.toFixed(2) + '°, rawE=' + t.el_deg_raw.toFixed(2) + '°';
    sel.appendChild(opt);
  }
}

function finalRun(){
  if(!confirm("Start final run? This will fire the laser at ALL targets.")) return;
  api('/final_run','POST')
    .then(r=>r.json())
    .then(j=>{
      if(j.ok) alert('Final run started');
      else alert('Error: '+(j.error||''));
    });
}


async function refreshAngles(){
  try{
    const r = await api('/angles');
    if(!r.ok) throw 'bad';
    const j = await r.json();
    document.getElementById('angles').textContent = 'Azimuth: ' + j.az.toFixed(2) + '°\\nElevation: ' + j.el.toFixed(2) + '°';
  }catch(e){
    document.getElementById('angles').textContent = 'Error fetching angles';
  }
}

async function initialLoad(){
  const r = await api('/targets');
  if(r.ok){
    const j = await r.json();
    populateTargets(j.targets);
  }
  setInterval(refreshAngles, 700);
  refreshAngles();
}
initialLoad();
</script>

</div>
</body>
</html>
"""

####### Endpoint Handlers #######

def handle_step(req_text):
    data = parse_post_body(req_text)
    axis = data.get("axis", "")
    delta = float(data.get("delta", "0"))
    try:
        manual_step(axis, delta)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def handle_zero(req_text):
    try:
        set_zero()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def handle_goto(req_text):
    data = parse_post_body(req_text)
    tgt = data.get("target", "")
    if not tgt:
        return {"ok": False, "error": "no target specified"}
    ok = goto_target(tgt)
    if ok:
        return {"ok": True}
    else:
        return {"ok": False, "error": "target not found"}

def handle_reload(req_text):
    ok = load_positions()
    if not ok:
        return {"ok": False, "error": "reload failed"}
    ok2 = build_processed_targets()
    if not ok2:
        return {"ok": False, "error": "processing failed"}
    return {"ok": True, "targets": processed_targets}

def handle_targets(req_text=None):
    return {"ok": True, "targets": processed_targets}

def handle_angles(req_text=None):
    try:
        with m_az.angle.get_lock():
            az = float(m_az.angle.value)
        with m_el.angle.get_lock():
            el = EL_INVERT*float(m_el.angle.value)
        return {"ok": True, "az": az, "el": el}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def handle_save_calibration(req_text):
    data = parse_post_body(req_text)
    tgt = data.get("target", "")
    if not tgt:
        return {"ok": False, "error": "no target specified"}
    ok, result = save_calibration_for_label(tgt)
    if not ok:
        return {"ok": False, "error": result}
    return {"ok": True, "result": result}

def handle_laser(req_text=None):
    handle_laser_request()
    return {"ok": True, "message": f"Laser firing for {LASER_ON_SECONDS}s"}

def handle_final_run(req_text=None):
    final_run_sequence()
    return {"ok": True, "message": "Final run started"}

def handle_home(req_text=None):
    threading.Thread(target=goto_home, daemon=True).start()
    return {"ok": True}


####### Server Stuff YIPPEEE ########

def run_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, PORT))
    sock.listen(5)
    print(f"Serving on http://<pi-ip>:{PORT} - open in browser from another device on same Wi-Fi")

    while True:
        conn, addr = sock.accept()
        try:
            req = recv_request(conn)
            if not req:
                conn.close(); continue
            method, path = parse_request_line(req)
            print("Request:", method, path, "from", addr)

            if method == "GET":
                if path == "/targets":
                    send_json(conn, handle_targets())
                elif path == "/angles":
                    send_json(conn, handle_angles())
                elif path == "/capt_kessler2.jpg":
                    send_file(conn, "capt_kessler2.jpg", "image/jpeg")
                elif path == "/turret_background.jpg":
                    send_file(conn, "turret_background.jpg", "image/jpeg")
                else:
                    send_html(conn, page_html())
            elif method == "POST":
                if path == "/step":
                    res = handle_step(req); send_json(conn, res)
                elif path == "/zero":
                    res = handle_zero(req); send_json(conn, res)
                elif path == "/goto":
                    res = handle_goto(req); send_json(conn, res)
                elif path == "/reload":
                    res = handle_reload(req); send_json(conn, res)
                elif path == "/save_calibration":
                    res = handle_save_calibration(req); send_json(conn, res)
                elif path == "/laser":
                    res = handle_laser(req); send_json(conn, res)
                elif path == "/final_run":
                    res = handle_final_run(req); send_json(conn, res)
                elif path == "/home":
                    res = handle_home(req); send_json(conn, res)
                else:
                    send_json(conn, {"ok": False, "error": "unknown POST"})
            else:
                send_html(conn, "<html><body>unsupported method</body></html>")
        except Exception as e:
            print("Exception handling request:", e)
            traceback.print_exc()
        finally:
            conn.close()

######### Main ###########

if __name__ == "__main__":
    try:
        load_calibration()
        setup_laser()
        setup_motors()
        pos_loaded = load_positions()
        if not pos_loaded:
            print("Warning: positions not loaded. Create positions.json or set JSON_URL.", file=sys.stderr)
            positions = {}
        pos_processed = build_processed_targets()
        if not pos_processed:
            print("Warning: processed_targets empty or failed. Check JSON / MY_TEAM.", file=sys.stderr)
        run_server()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        try:
            if s: s.shiftByte(0)
        except:
            pass
        GPIO.cleanup()
        print("GPIO cleaned up.")

