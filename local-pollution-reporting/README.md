# Local Pollution Reporting Software (Flask + HTML + Supabase)

A production-ready web app where citizens can upload geotagged reports of pollution. Built with Flask templates (HTML/CSS/JS) and Supabase (Auth, Postgres, Storage).

## Features
- Email/password signup/login (server-side using service role; for production you may prefer supabase-js on the client with OTP/email confirm).
- Create report with photo validation (≤10MB; JPEG/PNG/WEBP), auto-orient, EXIF stripping, resize (1920px) and 480px thumbnail.
- Optional reverse geocoding via OpenStreetMap Nominatim.
- Leaflet map with marker clustering, popups with photo + metadata, filter controls, synchronized list.
- Admin status changes with audit trail and CSV export.
- "My Reports" page with edit/delete when status is Open.
- Rate limit (5/hour per user) enforced via SQL function.
- BBox validation via environment variables.

## Setup
1. Create a Supabase project.
2. Create a public storage bucket named `reports` (enable public read).
3. Open SQL Editor and run contents of `db/sql_setup.sql`.
4. Create a service role user as admin: in `profiles` table, set your user row `role` to `admin`.
5. Copy `.env.example` to `.env` and set values.
6. Install dependencies and run:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:8000

### Docker
```bash
docker build -t local-pollution-reporting .
docker run -p 8000:8000 --env-file .env local-pollution-reporting
```

## Security Notes
- SERVICE_ROLE_KEY is used only on the server (Flask). Do **not** expose it to the browser.
- We strip EXIF before upload to avoid leaking sensitive metadata; only lat/lon provided by the user is stored.
- RLS policies ensure proper access controls. Validate inputs server-side as implemented.

## Demo Seed
Insert a few rows into `reports` for demo quickly (adjust user_id and URLs):
```sql
insert into reports (user_id, title, description, category, severity, lat, lon, address, image_url, thumb_url)
values
  ('<some-user-uuid>','Plastic dump near river','Needs immediate cleanup','Plastic','High', 25.61, 85.14, 'Patna, Bihar', 'https://picsum.photos/seed/1/1000', 'https://picsum.photos/seed/1/400'),
  ('<some-user-uuid>','Open sewage','Smells bad','Sewage','Medium', 19.07, 72.88, 'Mumbai, MH', 'https://picsum.photos/seed/2/1000', 'https://picsum.photos/seed/2/400'),
  ('<some-user-uuid>','Noise from factory','Night time disturbance','Noise','Low', 28.61, 77.20, 'Delhi', 'https://picsum.photos/seed/3/1000', 'https://picsum.photos/seed/3/400');
```

## Tests
Run unit tests:
```bash
pytest -q
```
