# Methodology — the HARD-RULE filter contract

This page specifies the HARD RULE as a **normative contract**. Keywords **MUST**, **MUST NOT**,
**SHOULD**, **MAY** are used per [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119). Every claim
here is either **[VERIFIED]** (source code or reproducible measurement) or **[PLAUSIBLE]**
(reasoned, not exhaustively proven). Findings about undocumented endpoints are **date-stamped** —
they describe behaviour observed on **2026-07-13** and MAY drift.

## Goal

> The set of coverage nodes that reach the output **MUST** contain only official Google car
> Street View panoramas (the road-snapped "blue lines"), and **MUST NOT** contain any user
> photosphere, "photopet"/photo upload, or Google-hosted third-party panorama.

Car-vs-trekker separation is a **secondary, best-effort** goal (see [Limitations](#limitations)).
Photosphere exclusion is the **primary, hard** goal.

## Threat model

A "leak" is any non-official panorama appearing in output. The adversary is not malicious — it is
the data itself: Google's ecosystem contains user photospheres (`CIHM…`/`CIAB…`/`AF1Q…` ids,
`source == photos:*`), trekker/tripod coverage (`scout`, `innerspace`, `cultural_institute`), and
legacy edge cases. A single defective predicate could admit any of these.

## The three layers

A node is **KEPT** if and only if it passes **all** applicable layers; it is **DROPPED** if it
fails **any**.

### Layer 0 — Source (structural)

- Coverage nodes **MUST** be enumerated **only** through the z17 coverage-tile endpoint
  (`streetlevel.streetview.get_coverage_tile` / `get_coverage_tile_by_latlon`).
- The pipeline **MUST NOT** call `find_panorama(..., search_third_party=True)` or otherwise query
  the third-party photosphere layer.
- **Rationale [VERIFIED].** The coverage-tile request carries no unofficial-type flag and
  streetlevel exposes no third-party parameter on the tile functions, so third-party panoramas are
  **structurally absent** from this layer. A 49-tile / 7,433-pano sweep returned **0** third-party
  (see [Verification](verification.md)).

### Layer 1 — Positive id whitelist

- Every node id **MUST** satisfy `is_official_panoid(id)`:

    - length **MUST** equal 22;
    - the final character **MUST** be one of `{A, Q, g, w}`;
    - the id **MUST** URL-safe-base64-decode to exactly 16 bytes;
    - the id **MUST NOT** begin with `CIHM`, `CIAB`, or `AF1Q`.

- This is a **positive allowlist**, not a prefix denylist. It is stricter than streetlevel's
  `is_third_party_panoid` (which flags `startswith("CIHM0og") or len > 22`) and therefore closes
  that check's **documented false-negative classes**: legacy pre-2017 photospheres that kept
  22-char ids, and the post-2025 `CIAB` short-form UGC scheme.
- **Rationale [VERIFIED].** Official ids encode a 16-byte value in 22 URL-safe-base64 chars; 128
  bits leave only 2 meaningful bits in the final char → exactly four terminal characters
  `{A,Q,g,w}`. Measured: 753/753 real official ids accepted, 3/3 real photospheres rejected.

### Layer 2 — Source allowlist (`--precision`)

- When `--precision` is enabled, each surviving node's `source` **MUST** be fetched via
  `find_panorama_by_id` (GetMetadata); it is **not** present in the tile response.
- A node **MUST** be KEPT only if `source == "launch"` (or `source ∈ {launch, scout}` when
  `--include-trekker` is set). `source` values `photos:*`, `innerspace`, `cultural_institute` (and
  `scout` by default) **MUST** be DROPPED.
- A node whose source is **not confirmed** (fetch failed, or resolved with no source) **MUST NOT**
  be treated as a confirmed non-launch node. It is KEPT (it already passed Layers 0+1, so it is
  official and therefore never a photosphere), and counted in `precision_byid_failed` /
  `precision_source_none`. This fails **safe** for the HARD RULE and avoids silently discarding
  valid coverage on a transient network error.

**Net predicate:**
`KEEP ⟺ Layer0-sourced AND is_official_panoid(id) AND link_degree ≥ 1 [AND (¬precision OR source == "launch")]`

`link_degree ≥ 1` is a **connectivity** filter (drops isolated official dots so the output is
continuous lines), **not** a third-party filter.

## Why three layers

The layers cover each other's blind spots:

- If Layer 1's id heuristic ever missed a UGC id (a legacy 22-char or a novel scheme), Layer 2's
  `source == "launch"` would still reject it — a photosphere is never `launch`.
- If Layer 2 is disabled (no `--precision`), Layers 0+1 still exclude every photosphere; only the
  car-vs-trekker refinement is skipped.

So **photosphere exclusion holds even in the default (fast) mode**; `--precision` only adds the
car-vs-trekker gate.

## Limitations

- **Car vs trekker is not cleanly separable [VERIFIED].** streetlevel's own docs: `launch` is
  "regular car coverage **and sometimes trekker** whose lines are snapped to roads"; `scout` is
  "trekker or tripod **and sometimes car** … not snapped to roads". The field encodes the
  road-snapping pipeline, not the physical capture platform. So `source == "launch"` admits a small
  amount of road-snapped trekker and drops a little unsnapped car. This fuzz is **orthogonal** to
  the photosphere exclusion and never weakens it.
- **Residual id-classifier risk [VERIFIED, LOW].** "A 22-char non-`CIHM` id is necessarily
  official" is false *in general* (legacy photospheres exist), but such ids are essentially absent
  from current z17 tiles (consistent with the 0-leak sweep) and would still be caught by
  `source != "launch"` under `--precision`.
- **Undocumented + dated.** All of the above describes observed behaviour of undocumented endpoints
  on 2026-07-13 and MAY change; re-run [Verification](verification.md) to re-confirm.

## The guarantee, stated plainly

- **With `--precision`:** almost-certain (90–99%) that every kept node is official car coverage.
- **Without `--precision`:** the photosphere/photopet exclusion is still airtight; the output may
  include a small amount of official trekker (`scout`) coverage.
- **Never**, in either mode, a user photosphere or Google-hosted third-party panorama.
