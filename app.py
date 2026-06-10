import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/send", methods=["POST"])
def send_email():
    data = request.get_json()

    smtp_host = data.get("smtp_host", "").strip()
    smtp_port = int(data.get("smtp_port", 587))
    smtp_user = data.get("smtp_user", "").strip()
    smtp_pass = data.get("smtp_pass", "").strip()
    from_addr = data.get("from_addr", "").strip() or smtp_user
    to_addr = data.get("to_addr", "").strip()
    subject = data.get("subject", "").strip()
    body = data.get("body", "").strip()
    use_tls = data.get("use_tls", True)

    if not all([smtp_host, smtp_user, smtp_pass, to_addr, subject, body]):
        return jsonify({"success": False, "error": "All fields are required."}), 400

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        if use_tls:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.ehlo()
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)

        server.login(smtp_user, smtp_pass)
        server.sendmail(from_addr, to_addr, msg.as_string())
        server.quit()

        return jsonify({"success": True, "message": "Email sent successfully!"})
    except smtplib.SMTPAuthenticationError:
        return jsonify({"success": False, "error": "Authentication failed. Check your username/password."}), 400
    except smtplib.SMTPConnectError:
        return jsonify({"success": False, "error": f"Could not connect to {smtp_host}:{smtp_port}."}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
