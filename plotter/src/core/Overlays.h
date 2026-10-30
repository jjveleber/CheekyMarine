#pragma once
#include "Geo.h"
#include "VesselState.h"
#include <QJsonObject>
#include <QList>

// Source and image ids shared with the chart controller (Task 10). Layers filter on the `kind` property.
namespace OverlayIds {
inline constexpr const char* kOwnSource = "cm-own";
inline constexpr const char* kTracksSource = "cm-tracks";
inline constexpr const char* kAisSource = "cm-ais";
inline constexpr const char* kBoatImage = "cm-boat";
inline constexpr const char* kAisImageA = "cm-ais-a";
inline constexpr const char* kAisImageB = "cm-ais-b";
inline constexpr const char* kAisImageHollow = "cm-ais-hollow";
}

// Conventions: GeoJSON coordinates are [lon, lat]; `rot` is degrees in [0, 360), true; every LineString
// starts at the vessel position. The 50 km heading line is a 2-point great-circle chord (adequate at
// chart zooms). Own ship features: kind "boat" (Point, rot), "heading", "cog" (LineStrings).
QJsonObject ownShipGeoJson(const VesselState& v);
// One LineString (kind "track") per track with at least 2 points.
QJsonObject tracksGeoJson(const QList<QList<LatLon>>& tracks);
// Per target with a position: kind "ais" Point (mmsi, cls, rot, hollow) and, with COG and SOG, kind
// "aisvec" LineString (6 min of travel). rot = heading, else COG, else 0 (AIS angles are true).
// `own` is currently unused (reserved for CPA styling).
QJsonObject aisGeoJson(const QList<AisTarget>& targets, const VesselState& own);
