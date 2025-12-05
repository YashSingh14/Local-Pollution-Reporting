import email
import os
import io
import csv
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, abort, flash
from dotenv import load_dotenv

from services.supa import get_client, get_service_client, public_url_for, upsert_profile, mask_user_handle
from services.images import validate_and_prepare_image
from services.geo import reverse_geocode_osm

load_dotenv()

APP_BBOX_MIN_LAT = float(os.getenv("APP_BBOX_MIN_LAT", "-90"))
APP_BBOX_MIN_LON = float(os.getenv("APP_BBOX_MIN_LON", "-180"))
APP_BBOX_MAX_LAT = float(os.getenv("APP_BBOX_MAX_LAT", "90"))
APP_BBOX_MAX_LON = float(os.getenv("APP_BBOX_MAX_LON", "180"))

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))

BUCKET = "reports"

supabase = get_client()
service = get_service_client()


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        uid = session["user"]["id"]
        role = get_user_role(uid)
        if role not in ("admin", "moderator"):
            abort(403)
        return view(*args, **kwargs)
    return wrapper


def get_user_role(uid: str) -> str:
    resp = supabase.table("profiles").select("role").eq("id", uid).single().execute()
    if resp.data:
        return resp.data.get("role", "user")
    return "user"


@app.route("/")
def home():
    return render_template("index.html", user=session.get("user"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("login.html")

        try:
            if action == "signup":
                # Create account server-side so it's instantly confirmed (requires SERVICE_ROLE key)
                created = service.auth.admin.create_user({
                    "email": email,
                    "password": password,
                    "email_confirm": True
                })
                # supabase-py v2 may return either created.user or created.data["user"]
                user = getattr(created, "user", None)
                if user is None:
                    data = getattr(created, "data", None)
                    if isinstance(data, dict):
                        user = data.get("user")

                if not user or not getattr(user, "id", None):
                    flash("Sign up failed (no user returned).", "error")
                    return render_template("login.html")

                upsert_profile(service, user.id, display_name=email.split("@")[0])
                session["user"] = {"id": user.id, "email": email}
                return redirect(url_for("home"))

            elif action == "login":
                auth = service.auth.sign_in_with_password({"email": email, "password": password})
                user = getattr(auth, "user", None)
                if not user:
                    flash("Invalid credentials.", "error")
                    return render_template("login.html")

                upsert_profile(service, user.id, display_name=email.split("@")[0])
                session["user"] = {"id": user.id, "email": email}
                return redirect(url_for("home"))

            else:
                flash("Unknown action.", "error")
                return render_template("login.html")

        except Exception as e:
            # Always return a response on exception
            flash(f"Auth error: {e}", "error")
            return render_template("login.html")

    # GET request
    return render_template("login.html")




@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/new", methods=["GET", "POST"])
@login_required
def new_report():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "Other")
        severity = request.form.get("severity", "Low")
        lat = request.form.get("lat")
        lon = request.form.get("lon")
        address = request.form.get("address", "").strip()
        photo = request.files.get("photo")

        # Client validation replicated server-side
        if not photo or not title or not lat or not lon:
            flash("Photo, Title, Latitude and Longitude are required.", "error")
            return redirect(url_for("new_report"))

        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except ValueError:
            flash("Latitude/Longitude must be numeric.", "error")
            return redirect(url_for("new_report"))

        # BBox check
        if not (APP_BBOX_MIN_LAT <= lat_f <= APP_BBOX_MAX_LAT and APP_BBOX_MIN_LON <= lon_f <= APP_BBOX_MAX_LON):
            flash("Location is outside the allowed area.", "error")
            return redirect(url_for("new_report"))

        # Rate limit via SQL function
        r = service.rpc("can_submit_report", {"p_user_id": session["user"]["id"]}).execute()
        if not r.data:
            flash("Rate limit exceeded: at most 5 reports per hour.", "error")
            return redirect(url_for("new_report"))

        # Image pipeline (validate, EXIF orient, strip, resize, thumbnail)
        try:
            prep = validate_and_prepare_image(photo.stream, max_px=1920, thumb_px=480)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("new_report"))

        # Optional reverse geocode if no address provided
        if not address:
            address = reverse_geocode_osm(lat_f, lon_f)

        # Upload to Storage
        report_id = str(uuid.uuid4())
        user_id = session["user"]["id"]
        original_key = f"reports/{user_id}/{report_id}/original.jpg"
        thumb_key = f"reports/{user_id}/{report_id}/thumb.jpg"

        service.storage.from_(BUCKET).upload(original_key, prep["image_bytes"], {
            "content-type": "image/jpeg",
            "x-upsert": "true"
        })
        service.storage.from_(BUCKET).upload(thumb_key, prep["thumb_bytes"], {
            "content-type": "image/jpeg",
            "x-upsert": "true"
        })

        image_url = public_url_for(BUCKET, original_key)
        thumb_url = public_url_for(BUCKET, thumb_key)

        # Insert into reports
        insert = {
            "user_id": user_id,
            "title": title,
            "description": description,
            "category": category,
            "severity": severity,
            "lat": lat_f,
            "lon": lon_f,
            "address": address,
            "image_url": image_url,
            "thumb_url": thumb_url
        }
        service.table("reports").insert(insert).execute()

        flash("Report submitted successfully!", "success")
        return redirect(url_for("map_view"))

    return render_template("new_report.html", user=session.get("user"))


@app.route("/map")
def map_view():
    return render_template("map.html", user=session.get("user"))


@app.route("/api/reports")
def api_reports():
    # Filters
    q = supabase.table("reports").select("*")

    start = request.args.get("start")
    end = request.args.get("end")
    category = request.args.get("category")
    severity = request.args.get("severity")
    status = request.args.get("status")
    search = request.args.get("search")

    if start:
        q = q.gte("created_at", start)
    if end:
        q = q.lte("created_at", end)
    if category:
        q = q.eq("category", category)
    if severity:
        q = q.eq("severity", severity)
    if status:
        q = q.eq("status", status)
    if search:
        like = f"%{search}%"
        q = q.or_(f"title.ilike.{like},description.ilike.{like},address.ilike.{like}")

    res = q.order("created_at", desc=True).execute()

    data = []
    for r in res.data or []:
        data.append({
            "id": r["id"],
            "title": r["title"],
            "description": r.get("description"),
            "category": r["category"],
            "severity": r["severity"],
            "lat": r["lat"],
            "lon": r["lon"],
            "address": r.get("address"),
            "image_url": r["image_url"],
            "thumb_url": r["thumb_url"],
            "status": r["status"],
            "created_at": r["created_at"],
            "reporter": mask_user_handle(r.get("user_id"))
        })
    return jsonify(data)


@app.route("/api/report/<rid>/status", methods=["POST"]) 
@admin_required
def api_set_status(rid):
    new_status = request.json.get("status")
    uid = session["user"]["id"]
    res = service.rpc("set_report_status", {"p_report_id": rid, "p_new_status": new_status, "p_changed_by": uid}).execute()
    if res.error:
        return jsonify({"ok": False, "error": res.error.message}), 400
    return jsonify({"ok": True})


@app.route("/my")
@login_required
def my_reports():
    return render_template("my_reports.html", user=session.get("user"))


@app.route("/api/my_reports")
@login_required
def api_my_reports():
    uid = session["user"]["id"]
    res = supabase.table("reports").select("*").eq("user_id", uid).order("created_at", desc=True).execute()
    return jsonify(res.data or [])


@app.route("/api/report/<rid>", methods=["POST", "DELETE"]) 
@login_required
def api_update_or_delete_report(rid):
    uid = session["user"]["id"]
    if request.method == "DELETE":
        # Owner can delete iff status = 'Open'
        r = service.table("reports").select("status").eq("id", rid).eq("user_id", uid).single().execute()
        if not r.data or r.data["status"] != "Open":
            return jsonify({"ok": False, "error": "Cannot delete once under review or resolved."}), 400
        service.table("reports").delete().eq("id", rid).execute()
        return jsonify({"ok": True})

    # Edit title/description only if Open
    payload = request.json or {}
    r = service.table("reports").select("status").eq("id", rid).eq("user_id", uid).single().execute()
    if not r.data or r.data["status"] != "Open":
        return jsonify({"ok": False, "error": "Cannot edit once under review or resolved."}), 400

    updates = {k: v for k, v in {"title": payload.get("title"), "description": payload.get("description")}.items() if v is not None}
    if updates:
        service.table("reports").update(updates).eq("id", rid).execute()
    return jsonify({"ok": True})


@app.route("/admin")
@admin_required
def admin():
    return render_template("admin.html", user=session.get("user"))


@app.route("/admin/export.csv")
@admin_required
def export_csv():
    # Apply same filters as /api/reports
    q = supabase.table("reports").select("*")
    start = request.args.get("start")
    end = request.args.get("end")
    category = request.args.get("category")
    severity = request.args.get("severity")
    status = request.args.get("status")

    if start:
        q = q.gte("created_at", start)
    if end:
        q = q.lte("created_at", end)
    if category:
        q = q.eq("category", category)
    if severity:
        q = q.eq("severity", severity)
    if status:
        q = q.eq("status", status)

    rows = q.order("created_at", desc=True).execute().data or []

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "title", "category", "severity", "status", "lat", "lon", "address", "created_at", "image_url", "thumb_url"]) 
    for r in rows:
        writer.writerow([r.get("id"), r.get("title"), r.get("category"), r.get("severity"), r.get("status"), r.get("lat"), r.get("lon"), r.get("address"), r.get("created_at"), r.get("image_url"), r.get("thumb_url")])

    mem = io.BytesIO(output.getvalue().encode("utf-8"))
    mem.seek(0)
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name="reports_export.csv")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
