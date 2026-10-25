"""Smart Event Management and Participant Analytics System.
Flask website with SQLite CRUD, analytics, CSV/JSON export, validation and API endpoints.
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from functools import wraps
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import requests
from flask import Flask, Response, flash, jsonify, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "event_management.db"
CHART_PATH = BASE_DIR / "static" / "dashboard_chart.png"
LOG_PATH = BASE_DIR / "event_app.log"

logging.basicConfig(filename=LOG_PATH, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
app = Flask(__name__)
app.secret_key = "change-this-development-key"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            event_name TEXT NOT NULL,
            registration_date TEXT NOT NULL,
            participant_type TEXT NOT NULL DEFAULT 'Regular',
            fee_paid REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")


def validate_form(form):
    name = form.get("name", "").strip()
    email = form.get("email", "").strip()
    phone = form.get("phone", "").strip()
    event_name = form.get("event_name", "").strip()
    registration_date = form.get("registration_date", "").strip() or date.today().isoformat()
    participant_type = form.get("participant_type", "Regular").strip()
    fee_text = form.get("fee_paid", "0").strip()
    errors = []
    if len(name) < 2:
        errors.append("Name must contain at least 2 characters.")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        errors.append("Enter a valid email address.")
    if not re.fullmatch(r"[0-9+()\-\s]{7,18}", phone):
        errors.append("Enter a valid phone number (7–18 characters).")
    if not event_name:
        errors.append("Event name is required.")
    if participant_type not in {"Regular", "VIP"}:
        errors.append("Participant type must be Regular or VIP.")
    try:
        fee_paid = float(fee_text)
        if fee_paid < 0:
            errors.append("Fee cannot be negative.")
    except ValueError:
        fee_paid = 0
        errors.append("Fee must be a number.")
    try:
        date.fromisoformat(registration_date)
    except ValueError:
        errors.append("Choose a valid registration date.")
    return {
        "name": name, "email": email, "phone": phone, "event_name": event_name,
        "registration_date": registration_date, "participant_type": participant_type,
        "fee_paid": fee_paid,
    }, errors


# OOP: meaningful domain class, encapsulated fee, inheritance and polymorphism.
class Participant:
    def __init__(self, name, email, event_name, fee_paid):
        self.name = name
        self.email = email
        self.event_name = event_name
        self.__fee_paid = float(fee_paid)

    def get_fee_paid(self):
        return self.__fee_paid

    def participant_type(self):
        return "Regular"

    def __str__(self):
        return f"{self.name} — {self.event_name} — ₹{self.__fee_paid:.2f}"

    @classmethod
    def from_row(cls, row):
        return cls(row["name"], row["email"], row["event_name"], row["fee_paid"])

    @staticmethod
    def valid_fee(value):
        return float(value) >= 0

    def __add__(self, other):
        if not isinstance(other, Participant):
            return NotImplemented
        return self.get_fee_paid() + other.get_fee_paid()


class VIPParticipant(Participant):
    def participant_type(self):
        return "VIP"


def timed(func):
    """Decorator used to record how long an analytics function takes."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        logging.info("%s completed in %.4f seconds", func.__name__, time.perf_counter() - start)
        return result
    return wrapper


def get_participants(search=""):
    with get_db() as conn:
        if search:
            like = f"%{search}%"
            return conn.execute("""SELECT * FROM participants
                WHERE name LIKE ? OR email LIKE ? OR event_name LIKE ?
                ORDER BY id DESC""", (like, like, like)).fetchall()
        return conn.execute("SELECT * FROM participants ORDER BY id DESC").fetchall()


@timed
def make_chart(rows):
    """Pandas aggregates saved database records and Matplotlib builds a chart."""
    plt.figure(figsize=(8, 4.2))
    if rows:
        df = pd.DataFrame([dict(r) for r in rows])
        summary = df.groupby("event_name", as_index=True)["id"].count().sort_values(ascending=False)
        summary.plot(kind="bar")
        plt.ylabel("Participants")
        plt.xlabel("Event")
        plt.title("Participants registered for each event")
        plt.xticks(rotation=20, ha="right")
    else:
        plt.text(0.5, 0.5, "Add participants to see your analytics", ha="center", va="center")
        plt.axis("off")
    plt.tight_layout()
    plt.savefig(CHART_PATH, dpi=140)
    plt.close()


async def async_event_summary(event_names):
    """Small asyncio example used by the API endpoint for concurrent summaries."""
    async def summarize(name):
        await asyncio.sleep(0)
        return {"event": name, "length": len(name)}
    return await asyncio.gather(*(summarize(name) for name in event_names))


@app.route("/")
def dashboard():
    rows = get_participants()
    make_chart(rows)
    total_fees = sum(float(r["fee_paid"]) for r in rows)
    events = sorted({r["event_name"] for r in rows})
    paid_count = sum(float(r["fee_paid"]) > 0 for r in rows)
    return render_template("dashboard.html", total=len(rows), total_fees=total_fees,
                           events_count=len(events), paid_count=paid_count, chart=url_for('static', filename='dashboard_chart.png', v=int(time.time())))


@app.route("/participants")
def participants():
    search = request.args.get("q", "").strip()
    return render_template("participants.html", participants=get_participants(search), q=search)


@app.route("/participants/add", methods=["GET", "POST"])
def add_participant():
    if request.method == "POST":
        data, errors = validate_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("participant_form.html", page_title="Add Participant", data=data), 400
        with get_db() as conn:
            conn.execute("""INSERT INTO participants
                (name,email,phone,event_name,registration_date,participant_type,fee_paid)
                VALUES (?,?,?,?,?,?,?)""", tuple(data[k] for k in ("name", "email", "phone", "event_name", "registration_date", "participant_type", "fee_paid")))
        logging.info("Participant added: %s", data["name"])
        flash("Participant saved successfully.", "success")
        return redirect(url_for("participants"))
    return render_template("participant_form.html", page_title="Add Participant", data={"registration_date": date.today().isoformat(), "participant_type": "Regular", "fee_paid": 0})


@app.route("/participants/<int:participant_id>/edit", methods=["GET", "POST"])
def edit_participant(participant_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM participants WHERE id=?", (participant_id,)).fetchone()
    if row is None:
        flash("Participant not found.", "error")
        return redirect(url_for("participants"))
    if request.method == "POST":
        data, errors = validate_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("participant_form.html", page_title="Edit Participant", data=data), 400
        with get_db() as conn:
            conn.execute("""UPDATE participants SET name=?,email=?,phone=?,event_name=?,registration_date=?,participant_type=?,fee_paid=? WHERE id=?""",
                         tuple(data[k] for k in ("name", "email", "phone", "event_name", "registration_date", "participant_type", "fee_paid")) + (participant_id,))
        logging.info("Participant updated: id=%s", participant_id)
        flash("Participant updated successfully.", "success")
        return redirect(url_for("participants"))
    return render_template("participant_form.html", page_title="Edit Participant", data=dict(row))


@app.route("/participants/<int:participant_id>/delete", methods=["POST"])
def delete_participant(participant_id):
    with get_db() as conn:
        conn.execute("DELETE FROM participants WHERE id=?", (participant_id,))
    logging.info("Participant deleted: id=%s", participant_id)
    flash("Participant deleted.", "success")
    return redirect(url_for("participants"))


@app.route("/export/csv")
def export_csv():
    rows = get_participants()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "email", "phone", "event_name", "registration_date", "participant_type", "fee_paid"])
    for row in rows:
        writer.writerow([row[k] for k in ("id", "name", "email", "phone", "event_name", "registration_date", "participant_type", "fee_paid")])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=participants.csv"})


@app.route("/export/json")
def export_json():
    rows = [dict(r) for r in get_participants()]
    return Response(json.dumps(rows, indent=2), mimetype="application/json", headers={"Content-Disposition": "attachment; filename=participants.json"})


# REST API: GET and POST participant data; dashboard is also able to consume these endpoints.
@app.route("/api/participants", methods=["GET", "POST"])
def api_participants():
    if request.method == "GET":
        return jsonify([dict(r) for r in get_participants()])
    data, errors = validate_form(request.get_json(silent=True) or {})
    if errors:
        return jsonify({"errors": errors}), 400
    with get_db() as conn:
        cur = conn.execute("""INSERT INTO participants
            (name,email,phone,event_name,registration_date,participant_type,fee_paid)
            VALUES (?,?,?,?,?,?,?)""", tuple(data[k] for k in ("name", "email", "phone", "event_name", "registration_date", "participant_type", "fee_paid")))
        new_id = cur.lastrowid
    return jsonify({"message": "created", "id": new_id}), 201


@app.route("/api/event-summary")
def api_event_summary():
    rows = get_participants()
    names = sorted({r["event_name"] for r in rows})
    return jsonify(asyncio.run(async_event_summary(names)))


@app.route("/holidays")
def holidays():
    """Optional public REST API example; website still works if the API is unavailable."""
    year = date.today().year
    try:
        response = requests.get(f"https://date.nager.at/api/v3/PublicHolidays/{year}/IN", timeout=4)
        response.raise_for_status()
        holiday_data = response.json()
        return render_template("holidays.html", holidays=holiday_data, year=year, error=None)
    except (requests.RequestException, ValueError) as exc:
        logging.warning("Public holiday API unavailable: %s", exc)
        return render_template("holidays.html", holidays=[], year=year, error="The public holiday API is unavailable right now. The rest of the website still works.")


@app.errorhandler(500)
def internal_error(error):
    logging.exception("Unexpected application error: %s", error)
    return render_template("error.html"), 500


init_db()
if __name__ == "__main__":
    app.run(debug=True)
