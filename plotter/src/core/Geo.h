#pragma once

// Spherical geo math (R = 6371008.8 m). Latitudes, longitudes and bearings are in degrees.
struct LatLon {
    double lat, lon;
};

LatLon destination(LatLon from, double bearingDeg, double distM);
double distanceM(LatLon a, LatLon b);
// Initial bearing from -> to, in [0, 360).
double bearingDeg(LatLon from, LatLon to);
// Ground resolution of MapLibre's 512 px world at latitude `latDeg` (degrees) and `zoom`.
double metresPerPixel(double latDeg, double zoom);
