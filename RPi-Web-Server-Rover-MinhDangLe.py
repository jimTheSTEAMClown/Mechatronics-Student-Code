#!/usr/bin/env python3
"""
Rover Web Server - Raspberry Pi 4 + 2x L298N
Hosts a web control panel on the Pi's local network.
Access from any browser at http://<PI_IP>:5000

Install deps:  pip3 install flask --break-system-packages
Run:           python3 rover_server.py

Controller 1 — Threads (ENA/ENB jumpers ON):
  IN1  -> GPIO 27 / BOARD 13  — Left thread direction A
  IN2  -> GPIO 17 / BOARD 11  — Left thread direction B
  IN3  -> GPIO 6  / BOARD 31  — Right thread direction A
  IN4  -> GPIO 5  / BOARD 29  — Right thread direction B

Controller 2 — Arms & Legs (ENA/ENB jumpers ON):
  IN5  -> GPIO 24 / BOARD 18  — Front arm direction A
  IN6  -> GPIO 25 / BOARD 22  — Front arm direction B
  IN7  -> GPIO 16 / BOARD 36  — Back leg direction A
  IN8  -> GPIO 20 / BOARD 38  — Back leg direction B
"""

import os
os.environ["GPIOZERO_PIN_FACTORY"] = "lgpio"

from flask import Flask, request, jsonify, render_template_string
from gpiozero import DigitalOutputDevice
from time import sleep, time
import threading
import socket

# ── Pin Definitions (BCM) ─────────────────────────────────────────────────────

# Controller 1 — Threads
LEFT_IN1  = DigitalOutputDevice(27, initial_value=False)
LEFT_IN2  = DigitalOutputDevice(17, initial_value=False)
RIGHT_IN3 = DigitalOutputDevice(6,  initial_value=False)
RIGHT_IN4 = DigitalOutputDevice(5,  initial_value=False)

# Controller 2 — Arms & Legs
FRONT_IN1 = DigitalOutputDevice(24, initial_value=False)
FRONT_IN2 = DigitalOutputDevice(25, initial_value=False)
BACK_IN1  = DigitalOutputDevice(16, initial_value=False)
BACK_IN2  = DigitalOutputDevice(20, initial_value=False)

ALL_DEVICES = [LEFT_IN1, LEFT_IN2, RIGHT_IN3, RIGHT_IN4,
               FRONT_IN1, FRONT_IN2, BACK_IN1, BACK_IN2]

# ── Motor Control ─────────────────────────────────────────────────────────────

def left_thread(fwd):
    LEFT_IN1.value = fwd
    LEFT_IN2.value = not fwd

def right_thread(fwd):
    RIGHT_IN3.value = fwd
    RIGHT_IN4.value = not fwd

def front_arm(fwd):
    FRONT_IN1.value = fwd
    FRONT_IN2.value = not fwd

def back_leg(fwd):
    BACK_IN1.value = fwd
    BACK_IN2.value = not fwd

def stop_threads():
    LEFT_IN1.off();  LEFT_IN2.off()
    RIGHT_IN3.off(); RIGHT_IN4.off()

def stop_arms():
    FRONT_IN1.off(); FRONT_IN2.off()
    BACK_IN1.off();  BACK_IN2.off()

def stop_all():
    stop_threads()
    stop_arms()

def cleanup():
    stop_all()
    for d in ALL_DEVICES:
        d.close()

# ── Watchdog ──────────────────────────────────────────────────────────────────

COMMAND_TIMEOUT   = 0.3
last_command_time = time()
current_command   = 'stop'

def watchdog():
    global current_command
    while True:
        if (current_command != 'stop'
                and (time() - last_command_time) > COMMAND_TIMEOUT):
            stop_all()
            current_command = 'stop'
        sleep(0.05)

wt = threading.Thread(target=watchdog, daemon=True)
wt.start()

# ── Flask App ─────────────────────────────────────────────────────────────────

app = Flask(__name__)

THREAD_COMMANDS = {
    'forward':     (True,  True,  True,  True),   # L-fwd, R-fwd
    'backward':    (False, False, False, False),
    'left':        (False, True,  True,  False),   # L-bwd, R-fwd
    'right':       (True,  False, False, True),    # L-fwd, R-bwd
    'pivot_left':  (None,  True,  True,  None),    # only right thread
    'pivot_right': (True,  None,  None,  True),    # only left thread
}

@app.route('/command', methods=['POST'])
def command():
    global last_command_time, current_command

    data = request.get_json()
    cmd  = data.get('command', 'stop')
    last_command_time = time()
    current_command   = cmd

    if cmd == 'stop':
        stop_all()

    elif cmd in THREAD_COMMANDS:
        lf, rf, _, _ = THREAD_COMMANDS[cmd]
        stop_threads()
        if lf is not None: left_thread(lf)
        if rf is not None: right_thread(rf)

    # Arm commands
    elif cmd == 'arms_up':
        front_arm(True); back_leg(True)
    elif cmd == 'front_arm_down':
        front_arm(False)
    elif cmd == 'all_arms_down':
        front_arm(False); back_leg(False)
    elif cmd == 'arms_stop':
        stop_arms()
    else:
        return jsonify({'status': 'error', 'message': 'unknown command'}), 400

    return jsonify({'status': 'ok', 'command': cmd})

@app.route('/status')
def status():
    return jsonify({'command': current_command})

@app.route('/')
def index():
    return render_template_string(HTML)

# ── HTML UI ───────────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Rover Control</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #f5f4f0;
    --surface:   #ffffff;
    --border:    #e2e0d8;
    --text:      #1a1916;
    --muted:     #9e9b92;
    --active-bg: #1a1916;
    --active-fg: #f5f4f0;
    --radius:    10px;
  }

  body {
    font-family: 'DM Sans', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 24px;
    padding: 40px 20px;
  }

  header { text-align: center; }
  header h1 {
    font-family: monospace;
    font-weight: 400;
    font-size: 1.1rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }
  header p {
    font-size: 0.78rem;
    color: var(--muted);
    margin-top: 6px;
    font-family: monospace;
  }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 28px;
    width: 100%;
    max-width: 420px;
  }

  .section-label {
    font-family: monospace;
    font-size: 0.68rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 14px;
  }

  /* D-pad */
  .dpad {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    max-width: 220px;
    margin: 0 auto;
  }

  /* Arm pad */
  .armpad {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    max-width: 220px;
    margin: 0 auto;
  }

  .btn {
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    cursor: pointer;
    font-family: monospace;
    font-size: 0.75rem;
    color: var(--text);
    height: 64px;
    user-select: none;
    transition: background 0.1s, color 0.1s, transform 0.08s;
    -webkit-tap-highlight-color: transparent;
    touch-action: none;
  }

  .btn svg {
    width: 20px; height: 20px;
    stroke: currentColor; fill: none;
    stroke-width: 1.8;
    stroke-linecap: round; stroke-linejoin: round;
  }

  .btn:active, .btn.pressed {
    background: var(--active-bg);
    color: var(--active-fg);
    border-color: var(--active-bg);
    transform: scale(0.95);
  }

  .btn.stop-btn:active, .btn.stop-btn.pressed {
    background: #c0392b;
    border-color: #c0392b;
    color: white;
  }

  .btn.empty {
    background: transparent;
    border: none;
    pointer-events: none;
  }

  .divider {
    border: none;
    border-top: 1px solid var(--border);
    margin: 22px 0;
  }

  /* Status bar */
  .status-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 22px;
    padding-top: 18px;
    border-top: 1px solid var(--border);
  }

  .status-dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: var(--border);
    transition: background 0.2s;
    flex-shrink: 0;
  }
  .status-dot.active { background: #3d9970; }

  .status-text {
    font-family: monospace;
    font-size: 0.72rem;
    color: var(--muted);
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }

  .hint {
    font-family: monospace;
    font-size: 0.68rem;
    color: var(--muted);
    text-align: center;
  }

  kbd {
    display: inline-block;
    padding: 1px 5px;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.68rem;
    background: var(--surface);
  }
</style>
</head>
<body>

<header>
  <h1>Rover Control</h1>
  <p id="ip-display"></p>
</header>

<div class="card">

  <!-- THREADS -->
  <div class="section-label">Threads</div>
  <div class="dpad">
    <div class="btn empty"></div>
    <div class="btn" id="btn-forward"  data-cmd="forward">
      <svg viewBox="0 0 24 24"><polyline points="18 15 12 9 6 15"/></svg>
    </div>
    <div class="btn empty"></div>

    <div class="btn" id="btn-left"     data-cmd="left">
      <svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg>
    </div>
    <div class="btn stop-btn" id="btn-stop" data-cmd="stop">
      <svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>
    </div>
    <div class="btn" id="btn-right"    data-cmd="right">
      <svg viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"/></svg>
    </div>

    <div class="btn empty"></div>
    <div class="btn" id="btn-backward" data-cmd="backward">
      <svg viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
    </div>
    <div class="btn empty"></div>
  </div>

  <hr class="divider">

  <!-- ARMS -->
  <div class="section-label">Arms &amp; Legs</div>
  <div class="armpad">
    <div class="btn empty"></div>
    <div class="btn" id="btn-arms-up"   data-cmd="arms_up">
      <svg viewBox="0 0 24 24"><polyline points="18 15 12 9 6 15"/></svg>
    </div>
    <div class="btn empty"></div>

    <div class="btn" id="btn-all-down"  data-cmd="all_arms_down">
      <svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg>
    </div>
    <div class="btn" id="btn-front-down" data-cmd="front_arm_down">
      <svg viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
    </div>
    <div class="btn" id="btn-all-down2" data-cmd="all_arms_down">
      <svg viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"/></svg>
    </div>

    <div class="btn empty"></div>
    <div class="btn empty"></div>
    <div class="btn empty"></div>
  </div>

  <div style="margin-top:10px; font-family:monospace; font-size:0.68rem; color:var(--muted); text-align:center;">
    ↑ both arms up &nbsp;·&nbsp; ↓ front arm down &nbsp;·&nbsp; ←/→ all arms down
  </div>

  <!-- STATUS -->
  <div class="status-bar">
    <div class="status-dot" id="status-dot"></div>
    <span class="status-text" id="status-text">stopped</span>
  </div>

</div>

<div class="hint">
  keyboard: <kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd> drive &nbsp;·&nbsp;
  <kbd>↑</kbd><kbd>↓</kbd><kbd>←</kbd><kbd>→</kbd> arms &nbsp;·&nbsp;
  <kbd>space</kbd> stop
</div>

<script>
  document.getElementById('ip-display').textContent = window.location.host;

  // ── Send command ───────────────────────────────────────────────────────────
  async function sendCommand(cmd) {
    try {
      await fetch('/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: cmd }),
      });
    } catch(e) {}
  }

  // ── Repeat interval for held buttons ──────────────────────────────────────
  let activeInterval = null;
  let activeCmd      = null;

  function startCmd(cmd) {
    if (activeCmd === cmd) return;
    clearInterval(activeInterval);
    activeCmd = cmd;
    sendCommand(cmd);
    if (cmd !== 'stop') {
      activeInterval = setInterval(() => sendCommand(cmd), 100);
    }
    updateUI(cmd);
  }

  function releaseCmd(cmd) {
    if (cmd === 'stop') return;
    clearInterval(activeInterval);
    activeCmd = null;
    // Stop only the right group
    const armCmds = ['arms_up','front_arm_down','all_arms_down'];
    sendCommand(armCmds.includes(cmd) ? 'arms_stop' : 'stop');
    updateUI('stop');
  }

  // ── UI highlight ───────────────────────────────────────────────────────────
  const statusDot  = document.getElementById('status-dot');
  const statusText = document.getElementById('status-text');

  const LABELS = {
    forward:'forward', backward:'backward', left:'spin left', right:'spin right',
    pivot_left:'pivot left', pivot_right:'pivot right',
    arms_up:'arms up', front_arm_down:'front arm down',
    all_arms_down:'all arms down', stop:'stopped',
  };

  function updateUI(cmd) {
    document.querySelectorAll('.btn[data-cmd]').forEach(b => {
      b.classList.toggle('pressed', b.dataset.cmd === cmd && cmd !== 'stop');
    });
    const moving = cmd !== 'stop';
    statusDot.className    = 'status-dot' + (moving ? ' active' : '');
    statusText.textContent = LABELS[cmd] || cmd;
  }

  // ── Button events ──────────────────────────────────────────────────────────
  document.querySelectorAll('.btn[data-cmd]').forEach(btn => {
    const cmd = btn.dataset.cmd;
    const press   = e => { e.preventDefault(); startCmd(cmd); };
    const release = e => { e.preventDefault(); releaseCmd(cmd); };
    btn.addEventListener('mousedown',  press);
    btn.addEventListener('touchstart', press,   { passive: false });
    btn.addEventListener('mouseup',    release);
    btn.addEventListener('mouseleave', release);
    btn.addEventListener('touchend',   release, { passive: false });
  });

  // ── Keyboard ───────────────────────────────────────────────────────────────
  const KEY_MAP = {
    'w':'forward', 's':'backward', 'a':'left', 'd':'right',
    'arrowup':'arms_up', 'arrowdown':'front_arm_down',
    'arrowleft':'all_arms_down', 'arrowright':'all_arms_down',
    ' ':'stop',
  };

  const held = new Set();

  document.addEventListener('keydown', e => {
    const cmd = KEY_MAP[e.key.toLowerCase()];
    if (!cmd || held.has(e.key.toLowerCase())) return;
    e.preventDefault();
    held.add(e.key.toLowerCase());
    startCmd(cmd);
  });

  document.addEventListener('keyup', e => {
    const cmd = KEY_MAP[e.key.toLowerCase()];
    if (!cmd) return;
    held.delete(e.key.toLowerCase());
    releaseCmd(cmd);
  });
</script>
</body>
</html>"""

# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except:
        local_ip = '0.0.0.0'

    print("=" * 40)
    print("  ROVER WEB SERVER")
    print("=" * 40)
    print(f"  Open in browser:")
    print(f"  http://{local_ip}:5000")
    print("=" * 40)
    print("  Ctrl+C to stop\n")

    try:
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    finally:
        cleanup()
        print("\nServer stopped. GPIO released.")
