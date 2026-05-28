#!/usr/bin/env python3
"""
Rover Web Server - Raspberry Pi 4 + L298N H-Bridge
Low-latency WebSocket control panel.
Access from any browser at http://<PI_IP>:5000

Install deps:  pip3 install flask flask-sock
Run:           python3 rover_server.py
"""

import os
os.environ["GPIOZERO_PIN_FACTORY"] = "lgpio"

from flask import Flask, render_template_string
from flask_sock import Sock
from gpiozero import LED, PWMOutputDevice, DigitalOutputDevice
from time import sleep, time
import threading
import json

# ── Pin Definitions (BCM) ─────────────────────────────────────────────────────
STATUS_LED      = 25
MOTOR_LEFT_ENA  = 12
MOTOR_LEFT_IN1  = 27
MOTOR_LEFT_IN2  = 17
MOTOR_RIGHT_ENB = 19
MOTOR_RIGHT_IN3 = 6
MOTOR_RIGHT_IN4 = 5

DEFAULT_SPEED = 0.75

# ── Device Setup ──────────────────────────────────────────────────────────────
led       = LED(STATUS_LED)
left_ena  = PWMOutputDevice(MOTOR_LEFT_ENA,  initial_value=0)
left_in1  = DigitalOutputDevice(MOTOR_LEFT_IN1,  initial_value=False)
left_in2  = DigitalOutputDevice(MOTOR_LEFT_IN2,  initial_value=False)
right_enb = PWMOutputDevice(MOTOR_RIGHT_ENB, initial_value=0)
right_in3 = DigitalOutputDevice(MOTOR_RIGHT_IN3, initial_value=False)
right_in4 = DigitalOutputDevice(MOTOR_RIGHT_IN4, initial_value=False)

# ── Motor Control ─────────────────────────────────────────────────────────────

def set_motors(left: float, right: float) -> None:
    left_in1.value  = left > 0
    left_in2.value  = left < 0
    left_ena.value  = abs(left)
    right_in3.value = right > 0
    right_in4.value = right < 0
    right_enb.value = abs(right)

def stop() -> None:
    set_motors(0.0, 0.0)
    led.off()

def cleanup() -> None:
    stop()
    for device in (left_ena, left_in1, left_in2,
                   right_enb, right_in3, right_in4, led):
        device.close()

# ── Watchdog ──────────────────────────────────────────────────────────────────
# If no command received within timeout, stop motors.
# Protects against lost connections, daddy.
COMMAND_TIMEOUT = 0.3
last_command_time = time()
current_command   = 'stop'

def watchdog():
    global current_command
    while True:
        if current_command != 'stop' and (time() - last_command_time) > COMMAND_TIMEOUT:
            stop()
            current_command = 'stop'
        sleep(0.02)

threading.Thread(target=watchdog, daemon=True).start()

# ── Motor command map ─────────────────────────────────────────────────────────
COMMANDS = {
    'forward':     ( 1.0,  1.0),
    'backward':    (-1.0, -1.0),
    'left':        (-1.0,  1.0),
    'right':       ( 1.0, -1.0),
    'pivot_left':  ( 0.0,  1.0),
    'pivot_right': ( 1.0,  0.0),
    'stop':        ( 0.0,  0.0),
}

def apply_command(cmd: str, speed: float) -> None:
    global last_command_time, current_command
    if cmd not in COMMANDS:
        return
    left, right = COMMANDS[cmd]
    set_motors(left * speed, right * speed)
    if cmd != 'stop':
        led.on()
    else:
        led.off()
    last_command_time = time()
    current_command   = cmd

# ── Flask + WebSocket ─────────────────────────────────────────────────────────
app  = Flask(__name__)
sock = Sock(app)

@sock.route('/ws')
def websocket(ws):
    """
    Each browser tab opens one persistent WebSocket.
    Messages are tiny JSON: {"cmd": "forward", "speed": 0.75}
    No HTTP overhead per command — just raw frames, daddy.
    """
    try:
        while True:
            data = ws.receive()
            if data is None:
                break
            try:
                msg   = json.loads(data)
                cmd   = msg.get('cmd', 'stop')
                speed = float(msg.get('speed', DEFAULT_SPEED))
                apply_command(cmd, speed)
            except (ValueError, KeyError):
                pass
    except Exception:
        pass
    finally:
        # Client disconnected — stop motors immediately
        stop()

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
  @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=DM+Sans:wght@300;400;500&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #f5f4f0;
    --surface:   #ffffff;
    --border:    #e2e0d8;
    --text:      #1a1916;
    --muted:     #9e9b92;
    --accent:    #1a1916;
    --active-bg: #1a1916;
    --active-fg: #f5f4f0;
    --radius:    10px;
  }

  body {
    font-family: 'DM Sans', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 28px;
    padding: 40px 20px;
  }

  header { text-align: center; }

  header h1 {
    font-family: 'DM Mono', monospace;
    font-weight: 400;
    font-size: 1.1rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  header p {
    font-size: 0.75rem;
    color: var(--muted);
    margin-top: 6px;
    font-family: 'DM Mono', monospace;
  }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 28px;
    width: 100%;
    max-width: 380px;
  }

  .section-label {
    font-family: 'DM Mono', monospace;
    font-size: 0.68rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 14px;
  }

  .dpad {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    grid-template-rows: repeat(3, 1fr);
    gap: 8px;
    aspect-ratio: 1;
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
    user-select: none;
    transition: background 0.08s, color 0.08s, transform 0.06s;
    -webkit-tap-highlight-color: transparent;
    touch-action: none;
  }

  .btn svg {
    width: 18px; height: 18px;
    stroke: currentColor; fill: none;
    stroke-width: 1.8;
    stroke-linecap: round; stroke-linejoin: round;
    pointer-events: none;
  }

  .btn.pressed, .btn:active {
    background: var(--active-bg);
    color: var(--active-fg);
    border-color: var(--active-bg);
    transform: scale(0.95);
  }

  .btn.empty { background: transparent; border: none; pointer-events: none; }

  .speed-section { margin-top: 22px; }

  .speed-row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 10px;
  }

  input[type=range] {
    flex: 1; height: 4px;
    -webkit-appearance: none;
    background: var(--border);
    border-radius: 2px; outline: none;
  }

  input[type=range]::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 18px; height: 18px;
    border-radius: 50%;
    background: var(--accent);
    cursor: pointer;
    border: 3px solid var(--surface);
    box-shadow: 0 0 0 1px var(--border);
  }

  .speed-value {
    font-family: 'DM Mono', monospace;
    font-size: 0.8rem;
    min-width: 36px;
    text-align: right;
  }

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
  .status-dot.active  { background: #3d9970; }
  .status-dot.offline { background: #e74c3c; }

  .status-text {
    font-family: 'DM Mono', monospace;
    font-size: 0.72rem;
    color: var(--muted);
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }

  /* Ping display */
  .ping {
    margin-left: auto;
    font-family: 'DM Mono', monospace;
    font-size: 0.68rem;
    color: var(--muted);
  }

  .hint {
    font-family: 'DM Mono', monospace;
    font-size: 0.68rem;
    color: var(--muted);
    text-align: center;
    letter-spacing: 0.04em;
  }

  kbd {
    display: inline-block;
    padding: 1px 5px;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-family: 'DM Mono', monospace;
    font-size: 0.68rem;
    background: var(--surface);
    color: var(--text);
  }
</style>
</head>
<body>

<header>
  <h1>Rover Control</h1>
  <p id="ip-display"></p>
</header>

<div class="card">
  <div class="section-label">Direction</div>
  <div class="dpad">
    <div class="btn empty"></div>
    <div class="btn" data-cmd="forward">
      <svg viewBox="0 0 24 24"><polyline points="18 15 12 9 6 15"/></svg>
    </div>
    <div class="btn empty"></div>

    <div class="btn" data-cmd="left">
      <svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg>
    </div>
    <div class="btn" data-cmd="stop">
      <svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>
    </div>
    <div class="btn" data-cmd="right">
      <svg viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"/></svg>
    </div>

    <div class="btn empty"></div>
    <div class="btn" data-cmd="backward">
      <svg viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
    </div>
    <div class="btn empty"></div>
  </div>

  <div class="speed-section">
    <div class="section-label">Speed</div>
    <div class="speed-row">
      <input type="range" id="speed-slider" min="10" max="100" value="75" step="5">
      <span class="speed-value" id="speed-label">75%</span>
    </div>
  </div>

  <div class="status-bar">
    <div class="status-dot" id="status-dot"></div>
    <span class="status-text" id="status-text">connecting...</span>
    <span class="ping" id="ping-display"></span>
  </div>
</div>

<div class="hint">
  <kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd> to move &nbsp;·&nbsp; <kbd>space</kbd> to stop
</div>

<script>
  const LABELS = {
    forward: 'forward', backward: 'backward',
    left: 'spinning left', right: 'spinning right',
    stop: 'stopped',
  };

  let speed = 0.75;
  let currentCmd = 'stop';
  let ws = null;
  let keepaliveInterval = null;
  let pingStart = 0;

  // ── IP display ─────────────────────────────────────────────────────────────
  document.getElementById('ip-display').textContent = window.location.host;

  // ── WebSocket ──────────────────────────────────────────────────────────────
  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onopen = () => {
      setStatus('stopped', false);
      // Keepalive: send current command every 150ms so watchdog stays fed
      keepaliveInterval = setInterval(() => {
        if (currentCmd !== 'stop') send(currentCmd);
        // Ping
        pingStart = performance.now();
        wsSend({ cmd: 'ping' });
      }, 150);
    };

    ws.onmessage = (e) => {
      // Measure round-trip ping
      if (e.data === 'pong') {
        const ms = Math.round(performance.now() - pingStart);
        document.getElementById('ping-display').textContent = ms + 'ms';
      }
    };

    ws.onclose = () => {
      clearInterval(keepaliveInterval);
      setStatus('offline', true);
      document.getElementById('ping-display').textContent = '';
      // Auto-reconnect after 1s
      setTimeout(connect, 1000);
    };

    ws.onerror = () => ws.close();
  }

  function wsSend(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
    }
  }

  function send(cmd) {
    wsSend({ cmd, speed });
  }

  // ── Commands ───────────────────────────────────────────────────────────────
  function startCommand(cmd) {
    if (currentCmd === cmd) return;
    currentCmd = cmd;
    send(cmd);
    updateUI(cmd);
  }

  function stopCommand() {
    currentCmd = 'stop';
    send('stop');
    updateUI('stop');
  }

  // ── UI ─────────────────────────────────────────────────────────────────────
  const statusDot  = document.getElementById('status-dot');
  const statusText = document.getElementById('status-text');

  function setStatus(label, offline) {
    statusDot.className  = 'status-dot' + (offline ? ' offline' : (label !== 'stopped' ? ' active' : ''));
    statusText.textContent = offline ? 'offline — reconnecting' : (LABELS[label] || label);
  }

  function updateUI(cmd) {
    document.querySelectorAll('.btn[data-cmd]').forEach(b => {
      b.classList.toggle('pressed', b.dataset.cmd === cmd && cmd !== 'stop');
    });
    setStatus(cmd, false);
  }

  // ── Speed slider ───────────────────────────────────────────────────────────
  const slider = document.getElementById('speed-slider');
  document.getElementById('speed-label').textContent = slider.value + '%';
  slider.addEventListener('input', () => {
    speed = slider.value / 100;
    document.getElementById('speed-label').textContent = slider.value + '%';
  });

  // ── Button events ──────────────────────────────────────────────────────────
  document.querySelectorAll('.btn[data-cmd]').forEach(btn => {
    const cmd = btn.dataset.cmd;

    const press = (e) => {
      e.preventDefault();
      cmd === 'stop' ? stopCommand() : startCommand(cmd);
    };
    const release = (e) => {
      e.preventDefault();
      if (cmd !== 'stop') stopCommand();
    };

    btn.addEventListener('mousedown',  press);
    btn.addEventListener('touchstart', press,   { passive: false });
    btn.addEventListener('mouseup',    release);
    btn.addEventListener('mouseleave', release);
    btn.addEventListener('touchend',   release, { passive: false });
  });

  // ── Keyboard ───────────────────────────────────────────────────────────────
  const KEY_MAP = { w:'forward', s:'backward', a:'left', d:'right', ' ':'stop' };
  const heldKeys = new Set();

  document.addEventListener('keydown', (e) => {
    const cmd = KEY_MAP[e.key.toLowerCase()];
    if (!cmd || heldKeys.has(e.key.toLowerCase())) return;
    e.preventDefault();
    heldKeys.add(e.key.toLowerCase());
    cmd === 'stop' ? stopCommand() : startCommand(cmd);
  });

  document.addEventListener('keyup', (e) => {
    const cmd = KEY_MAP[e.key.toLowerCase()];
    if (!cmd) return;
    heldKeys.delete(e.key.toLowerCase());
    if (cmd !== 'stop') stopCommand();
  });

  // ── Start ──────────────────────────────────────────────────────────────────
  connect();
</script>
</body>
</html>"""

# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import socket
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = '0.0.0.0'

    print("=" * 40)
    print("  ROVER WEB SERVER (WebSocket)")
    print("=" * 40)
    print(f"  Open in browser:")
    print(f"  http://{local_ip}:5000")
    print("=" * 40)
    print("  Ctrl+C to stop\n")

    for _ in range(3):
        led.on();  sleep(0.2)
        led.off(); sleep(0.2)

    try:
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    finally:
        cleanup()
        print("\nServer stopped. GPIO released.")
