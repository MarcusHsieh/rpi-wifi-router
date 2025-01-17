from flask import Flask, request, render_template, redirect, url_for
import subprocess
import os
import logging

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)

wifi_device = "wlan1"

if os.geteuid() != 0:
    raise PermissionError("This script must be run as root. Use sudo to execute it.")

@app.route('/')
def index():
    # get current connection details
    try:
        result = subprocess.check_output(["nmcli", "device", "show", wifi_device])
        lines = result.decode().strip().split("\n")
        active_ssid = next((line.split(":")[1].strip() for line in lines if "GENERAL.CONNECTION" in line), "None")
        active_ip = next((line.split(":")[1].strip() for line in lines if "IP4.ADDRESS" in line), "No IP")
    except Exception as e:
        app.logger.error(f"Error fetching current connection details: {e}")
        active_ssid, active_ip = "None", "No IP"

    # get available networks
    try:
        result = subprocess.check_output(["nmcli", "--colors", "no", "-m", "multiline", "--get-values", "SSID,SIGNAL", "dev", "wifi", "list", "ifname", wifi_device])
        raw_lines = result.decode().strip().split("\n")
        
        # parse each SSID and SIGNAL
        networks = []
        for i in range(0, len(raw_lines) - 1, 2):  # step through every two lines
            ssid = raw_lines[i].replace("SSID:", "").strip()  # rm "SSID:" prefix
            signal = raw_lines[i + 1].replace("SIGNAL:", "").strip()  # rm "SIGNAL:" prefix
            if ssid:  # exclude blank SSIDs
                networks.append((ssid, int(signal)))
        
        # sort by signal strength (descending)
        networks = sorted(networks, key=lambda x: x[1], reverse=True)
    except subprocess.CalledProcessError as e:
        app.logger.error(f"Error fetching WiFi networks: {e}")
        networks = []

    return render_template("index.html", networks=networks, active_ssid=active_ssid, active_ip=active_ip)




@app.route('/submit', methods=['POST'])
def submit():
    ssid = request.form.get('ssid')
    username = request.form.get('username')
    password = request.form.get('password')

    app.logger.info(f"Attempting to connect to SSID: {ssid} with username: {username} and password: {password}")

    if not ssid:
        return render_template("result.html", result="Error: SSID is required.")

    try:
        if username and password:
            # WPA2 Enterprise networks
            connection_command = [
                "nmcli", "--colors", "no", "connection", "add",
                "type", "wifi",
                "con-name", ssid,
                "ifname", wifi_device,
                "ssid", ssid,
                "802-11-wireless-security.key-mgmt", "wpa-eap",
                "802-1x.eap", "peap",
                "802-1x.identity", username,
                "802-1x.password", password,
                "802-1x.phase2-auth", "mschapv2"
            ]
        else:
            # regular WPA2 networks
            connection_command = ["nmcli", "--colors", "no", "device", "wifi", "connect", ssid, "ifname", wifi_device]
            if password:
                connection_command.extend(["password", password])

        result = subprocess.run(connection_command, capture_output=True)
        if result.returncode != 0:
            error_message = result.stderr.decode()
            raise Exception(error_message)
    except Exception as e:
        app.logger.error(f"Failed to connect: {e}")
        return render_template("result.html", result=f"Error: Unable to connect to {ssid}. {e}")

    return render_template("result.html", result=f"Successfully connected to {ssid}.")

@app.route('/disconnect', methods=['POST'])
def disconnect():
    try:
        result = subprocess.run(["nmcli", "device", "disconnect", wifi_device], capture_output=True)
        if result.returncode == 0:
            return render_template("result.html", result="Successfully disconnected.")
        error_message = result.stderr.decode()
        raise Exception(error_message)
    except Exception as e:
        app.logger.error(f"Failed to disconnect: {e}")
        return render_template("result.html", result=f"Error: {e}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=80)