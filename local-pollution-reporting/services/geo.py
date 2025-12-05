import requests

def reverse_geocode_osm(lat: float, lon: float) -> str:
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"format": "json", "lat": lat, "lon": lon, "zoom": 18, "addressdetails": 1},
            timeout=4,
            headers={"User-Agent": "LocalPollutionReporting/1.0"}
        )
        if resp.ok:
            return resp.json().get("display_name", "")
    except Exception:
        pass
    return ""
