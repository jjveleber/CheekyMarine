#pragma once
#include "Geo.h"
#include "VesselState.h"
#include <QColor>
#include <QJsonObject>
#include <QList>
#include <optional>

// Source and image ids shared with the chart controller (Task 10). Layers filter on the `kind` property.
namespace OverlayIds {
inline constexpr const char* kOwnSource = "cm-own";
inline constexpr const char* kTracksSource = "cm-tracks";        // finished visible tracks
inline constexpr const char* kActiveTrackSource = "cm-track-active"; // the track being recorded
inline constexpr const char* kAisSource = "cm-ais";
inline constexpr const char* kBoatImage = "cm-boat";
inline constexpr const char* kAisImageA = "cm-ais-a";
inline constexpr const char* kAisImageB = "cm-ais-b";
inline constexpr const char* kAisImageHollow = "cm-ais-hollow";
}

// Spec 6.6. True heading in degrees [0, 360): the heading when hdgRef is "True", heading + variation
// when "Magnetic" with a variation; otherwise none (a magnetic heading without variation, or one with
// no reference, is not shown or used as true).
std::optional<double> trueHeadingDeg(const VesselState& v);
// COG in degrees [0, 360) when SOG is above 0.5 kn (0.2572 m/s); none slower, where COG is noise.
std::optional<double> cogDeg(const VesselState& v);

// Conventions: GeoJSON coordinates are [lon, lat]; `rot` is degrees in [0, 360), true; every LineString
// starts at the vessel position. The 50 km heading line is a 2-point great-circle chord (adequate at
// chart zooms). Own ship features: kind "boat" (Point, rot), "heading", "cog" (LineStrings). The boat's
// rot is trueHeadingDeg, else cogDeg, else 0, like the head-up camera; heading and cog lines only
// when those are known.
QJsonObject ownShipGeoJson(const VesselState& v);
// One LineString (kind "track") per track with at least 2 points.
QJsonObject tracksGeoJson(const QList<QList<LatLon>>& tracks);
// Per target with a position: kind "ais" Point (mmsi, cls, rot, hollow) and, with COG and SOG, kind
// "aisvec" LineString (6 min of travel). rot = heading, else COG, else 0 (AIS angles are true).
// `own` is currently unused (reserved for CPA styling).
QJsonObject aisGeoJson(const QList<AisTarget>& targets, const VesselState& own);

// Colours of the runtime overlays (icons and lines) for a palette ("day", "dusk", "night"; anything
// else gives day). Night uses reds and black only: no channel but red above 0x20, as in Theme.qml.
struct OverlayColours {
    QColor boatFill, boatOutline, aisFill, aisOutline, heading, cog, aisVector, track;
};
OverlayColours overlayColours(const QString& palette);
