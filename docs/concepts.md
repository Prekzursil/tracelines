# Street View coverage in plain English (101)

A quick, no-jargon tour of the ideas this tool is built on.

## Blue lines vs blue dots

Open Street View and you'll see two kinds of blue on the map:

- **Blue lines** = **continuous car coverage.** A camera car drove down that road, filming the
  whole way. These are what tracelines extracts.
- **Blue dots** = **one-off panoramas** — usually a **photosphere** somebody uploaded from their
  phone at a single spot. tracelines **excludes these.**

> The whole point of tracelines is: **keep the lines, drop the dots.** We call it the *HARD RULE*.

## Who made the coverage: car vs trekker vs you

Official coverage comes from a few sources:

| Who | What | tracelines keeps it? |
|-----|------|----------------------|
| 🚗 **Car** (`launch`) | camera car on roads — the classic blue lines | ✅ yes |
| 🎒 **Trekker** (`scout`) | a backpack/tripod on paths cars can't reach | optional (`--precision` drops it) |
| 🏛️ **Indoor tripod** | inside shops, museums | ❌ no |
| 📱 **You** (`photos:*`) | a photosphere from a phone | ❌ **never** |

Honest caveat: Google's data sometimes labels a road-snapped trekker as `launch`, so "car vs
trekker" isn't perfectly separable. But **a phone photosphere is *never* mistaken for a car line** —
that part is airtight. ([the rigorous version →](methodology.md))

## Why "official-only" matters

If you're mapping *where you can actually get a street-level view of a road*, a random person's
single phone photo is noise. You want the roads a camera **drove end to end**. Filtering to
official car coverage gives you clean, continuous lines you can measure, compare, and trust.

## What you get out

A **GeoJSON** file — a standard geo-data format — where each road is a line with properties like
its **source** and **capture date**. Drop it into any GIS tool, or the built-in
[map GUI](gui.md). ([exact schema →](output-schema.md))

## Three sources, one map

- **Google** — the densest coverage, but its data has no clean redistribution license (generate it
  for yourself).
- **Mapillary** & **KartaView** — open (CC-BY-SA), community + org driven.

tracelines can pull all three and show where they agree and disagree.

Now go try it → **[Quickstart: your first extraction](quickstart.md)**
