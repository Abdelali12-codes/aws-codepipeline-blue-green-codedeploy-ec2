import os
from flask import Flask, jsonify

app = Flask(__name__)

DRAINING_FLAG = "/var/www/my-app/draining"

@app.route("/")
def home():
    return jsonify({"version": "v1", "env": "blue"})


@app.route("/health")
def health():
    # When the draining flag exists, return 503 so the ALB stops sending
    # new requests to this instance before it is deregistered.
    # before_block_traffic.sh creates this file; after_block_traffic.sh removes it.
    if os.path.exists(DRAINING_FLAG):
        return jsonify({"status": "draining"}), 503
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
