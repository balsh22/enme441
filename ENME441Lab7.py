import RPi.GPIO as GPIO
import socket

GPIO.setmode(GPIO.BCM)

# LED setup
led_pins = [17, 27, 22]
for pin in led_pins:
    GPIO.setup(pin, GPIO.OUT)

led_pwm = [GPIO.PWM(pin, 1000) for pin in led_pins]
for pwm in led_pwm:
    pwm.start(0)

# Track brightness
led_brightness = [0, 0, 0]

# Helper function to parse POST data (no urllib)
def parsePOSTdata(data):
    data_dict = {}
    idx = data.find('\r\n\r\n') + 4
    if idx < 4:
        return data_dict
    data = data[idx:]
    pairs = data.split('&')
    for pair in pairs:
        if '=' in pair:
            k, v = pair.split('=', 1)
            data_dict[k] = v
    return data_dict

# HTML page (as you specified)
def html_page():
    html = f"""
    <html>
    <form method="POST" action="/">
    <label>Brightness level:</label><br>
    <input type="range" name="brightness" min="0" max="100" value="0"><br>
    <br>
    Select LED:<br>
    <input type="radio" name="led" value="1" checked> LED 1 ({led_brightness[0]}%)<br>
    <input type="radio" name="led" value="2"> LED 2 ({led_brightness[1]}%)<br>
    <input type="radio" name="led" value="3"> LED 3 ({led_brightness[2]}%)<br>
    <br>
    <input type="submit" value="Change Brightness">
    </form>
    </html>
    """
    return html

# Web server
def run_server():
    host, port = '', 8080
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((host, port))
    s.listen(1)
    print(f"Server running on port {port}...")

    while True:
        conn, addr = s.accept()
        request = b""
        while True:
            chunk = conn.recv(1024)
            if not chunk:
                break
            request += chunk
        request = request.decode('utf-8', errors='ignore')
        print(f"Request from {addr}")

        if "POST" in request:
            data = parsePOSTdata(request)
            if "led" in data and "brightness" in data:
                try:
                    led = int(data["led"]) - 1
                    brightness = int(data["brightness"])
                    led_brightness[led] = brightness
                    led_pwm[led].ChangeDutyCycle(brightness)
                    print(f"LED {led + 1} set to {brightness}%")
                except Exception as e:
                    print("Error:", e)

        # Serve HTML
        body = html_page()
        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "\r\n"
            + body
        )
        conn.sendall(response.encode('utf-8'))
        conn.close()

# Main
if __name__ == "__main__":
    try:
        run_server()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        for pwm in led_pwm:
            pwm.stop()
        GPIO.cleanup()
