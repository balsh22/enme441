import RPi.GPIO as GPIO
from http.server import BaseHTTPRequestHandler, HTTPServer

GPIO.setmode(GPIO.BCM)

led_pins = [17, 27, 22]
for pin in led_pins:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)

pwms = [GPIO.PWM(pin, 1000) for pin in led_pins]
for pwm in pwms:
    pwm.start(0)

# Track brightness levels
led_brightness = [0, 0, 0]

# Original parser (unchanged)
def parsePOSTdata(data):
    data_dict = {}
    idx = data.find('\r\n\r\n') + 4
    data = data[idx:]
    data_pairs = data.split('&')
    for pair in data_pairs:
        key_val = pair.split('=')
        if len(key_val) == 2:
            data_dict[key_val[0]] = key_val[1]
    return data_dict


class LEDHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(self.html_page().encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode("utf-8")

        # Add fake header section for the old parser
        formatted_data = "FAKE / HTTP/1.1\r\nHeader: value\r\n\r\n" + post_data
        data = parsePOSTdata(formatted_data)

        # Extract LED and brightness
        led = int(data.get("led", "1")) - 1
        brightness = int(data.get("brightness", "0"))
        led_brightness[led] = brightness

        pwms[led].ChangeDutyCycle(brightness)

        # Respond with simple OK (AJAX expects no reload)
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"OK")

    def html_page(self):
        # This HTML + JS controls all LEDs without page reload
        html = f"""
        <html>
        <head>
          <meta charset="utf-8">
          <title>LED Control (Live)</title>
          <style>
            body {{
              font-family: Arial, sans-serif;
              margin: 30px;
            }}
            .slider-container {{
              margin-bottom: 20px;
            }}
            .label {{
              display: inline-block;
              width: 80px;
            }}
          </style>
        </head>
        <body>
          <h2>Raspberry Pi LED Brightness Control</h2>

          <div class="slider-container">
            <span class="label">LED 1:</span>
            <input type="range" id="led1" min="0" max="100" value="{led_brightness[0]}">
            <span id="val1">{led_brightness[0]}%</span>
          </div>

          <div class="slider-container">
            <span class="label">LED 2:</span>
            <input type="range" id="led2" min="0" max="100" value="{led_brightness[1]}">
            <span id="val2">{led_brightness[1]}%</span>
          </div>

          <div class="slider-container">
            <span class="label">LED 3:</span>
            <input type="range" id="led3" min="0" max="100" value="{led_brightness[2]}">
            <span id="val3">{led_brightness[2]}%</span>
          </div>

          <script>
            // Send POST to server when a slider changes
            function sendUpdate(led, brightness) {{
              fetch("/", {{
                method: "POST",
                headers: {{
                  "Content-Type": "application/x-www-form-urlencoded"
                }},
                body: "led=" + led + "&brightness=" + brightness
              }})
              .then(response => response.text())
              .then(data => console.log("Server response:", data))
              .catch(err => console.error("Error:", err));
            }}

            // Attach event listeners to sliders
            const sliders = [1, 2, 3];
            sliders.forEach(i => {{
              const slider = document.getElementById("led" + i);
              const valLabel = document.getElementById("val" + i);
              slider.addEventListener("input", () => {{
                const val = slider.value;
                valLabel.textContent = val + "%";
                sendUpdate(i, val);
              }});
            }});
          </script>
        </body>
        </html>
        """
        return html


try:
    print("Starting web server on http://0.0.0.0:8080 ...")
    with HTTPServer(('', 8080), LEDHandler) as server:
        server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    for pwm in pwms:
        pwm.stop()
    GPIO.cleanup()
    print("Server stopped, GPIO cleaned up.")
