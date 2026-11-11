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
inline constexpr const char* kBackgroundSource = "cm-background"; // one world polygon under the chart
inline constexpr const char* kBoatImage = "cm-boat";
inline constexpr const char* kAisImageA = "cm-ais-a";
inline constexpr const char* kAisImageB = "cm-ais-b";
inline constexpr const char* kAisImageHollow = "cm-ais-hollow";
inline constexpr const char* kCogTipImage = "cm-cog-tip";
inline constexpr const char* kBackgroundImage = "cm-background"; // the pattern over the no-data fill
}

// Spec 6.6. True heading in degrees [0, 360): the heading when hdgRef is "True", heading + variation
// when "Magnetic" with a variation; otherwise none (a magnetic heading without variation, or one with
// no reference, is not shown or used as true).
std::optional<double> trueHeadingDeg(const VesselState& v);
// COG in degrees [0, 360) when SOG is above 0.5 kn (0.2572 m/s); none slower, where COG is noise.
std::optional<double> cogDeg(const VesselState& v);

// Conventions: GeoJSON coordinates are [lon, lat]; `rot` is degrees in [0, 360), true; every LineString
// starts at the vessel position. The 50 km heading line is a 2-point great-circle chord (adequate at
// chart zooms). Own ship features: kind "boat" (Point, rot), "heading", "cog" (LineStrings) and "cogtip"
// (Point at the cog line's last coordinate, rot = COG degrees). The boat's rot is trueHeadingDeg, else
// cogDeg, else 0, like the head-up camera; heading and cog lines only when those are known and enabled.
// OwnShipOptions: heading and cog switch the lines (cog off also drops the tip); cogSecs is the cog
// line's length in seconds of travel at the current SOG.
struct OwnShipOptions {
    bool heading = true;
    bool cog = true;
    double cogSecs = 60.0;
};
QJsonObject ownShipGeoJson(const VesselState& v, const OwnShipOptions& opts = {});
// One LineString (kind "track") per track with at least 2 points.
QJsonObject tracksGeoJson(const QList<QList<LatLon>>& tracks);
// Per target with a position: kind "ais" Point (mmsi, cls, rot, hollow) and, with COG and SOG, kind
// "aisvec" LineString (6 min of travel). rot = heading, else COG, else 0 (AIS angles are true).
// `own` is currently unused (reserved for CPA styling).
QJsonObject aisGeoJson(const QList<AisTarget>& targets, const VesselState& own);

// Colours of the runtime overlays (icons and lines) for a palette ("day", "dusk", "night"; anything
// else gives day). Dusk is the day set toward black by 0.45, as in the charts pack. Night is amber on
// black: blue <= 0x20 and green <= 0.75 x red, except the starboard light (#20A040), as in Theme.qml.
// The hull* to stbdLight fields draw the own-boat icon; `track` is the night track colour and the
// fallback (day and dusk tracks come from trackColour).
struct OverlayColours {
    QColor hullFill, hullOutline, cabin, windshield, motor, motorOutline, portLight, stbdLight;
    QColor aisFill, aisOutline, heading, cog, aisVector, track;
};
OverlayColours overlayColours(const QString& palette);
// Each channel x (1 - t), rounded half to even like Python's round in chartpack's _toward_black.
QColor towardBlack(const QColor& c, double t);
// The track color for a palette: the owner's choice by day, dimmed toward black at dusk, a fixed
// dim amber at night.
QColor trackColour(const QColor& chosen, const QString& palette);
