# Audio Detection Success Rate Plan

Note: this plan is a working implementation guide for the current audio
detection tuning effort. Archive or remove it once these phases are completed so
it does not become stale project documentation.

## Context

We are focusing on audio-fingerprint intro detection, not chapter-name detection.
Arabic content should be measured from the local Kodi TV library. English content
should not use the local library; when we get to it, it should use Fenlight plus
Real-Debrid-resolved streams.

Current local Arabic probe results from `test-container/audio_library_probe.py`:

- Arabic, 10 shows x 3 episodes, 90s intro scan, outro disabled: 3/10 hits.
- Arabic, 10 shows x 5 episodes, 90s intro scan, outro disabled: 3/10 hits.
- Lowering minimum common duration from 30s to 10s did not recover misses.
- Loosening Hamming distance from 16 to 24 did not recover misses.
- Extending scan to 180s did not recover misses, but one hit expanded from 87s
  to 163s, which is a false-positive/overlong-match risk.
- Every observed miss was `no_common_fingerprint_match`, not ffmpeg/probe
  failure.

## Quick Research Notes

The web does not appear to publish a reliable timing distribution for Arabic
series intro start times or durations. It does support these working
hypotheses:

- Arabic Ramadan opening credits/teters are a repeated episode element and can
  be a meaningful production component, not just a short title card.
- Arabic shows can include pre-opening scenes; Scoop Empire explicitly warns not
  to miss a pre-opening credits scene in one Ramadan show.
- Arabic broadcast versions can remove or alter teters under advertising
  pressure, so the same show may have inconsistent intro material depending on
  source or episode.
- American/English scripted TV commonly uses cold opens. A general reference
  describes modern American sitcom cold opens as usually 1-2 minutes and at most
  around 3-4 minutes before the title/theme.
- English opening-credit durations are highly mixed: modern title cards can be
  around 14-15 seconds, many streaming titles are around 60-90 seconds, and some
  older/prestige openings run longer.

Sources:

- Cold open overview and common American sitcom cold-open timing:
  https://en.wikipedia.org/wiki/Cold_open
- Current long English opening-credit examples around 60+ seconds, with older
  examples over 90 seconds:
  https://www.tvline.com/lists/best-worst-tv-opening-credits-sequences/
- English opening-credit trend examples: 1:20 sitcom openings, 15-second title
  cards, and decline of long network intros:
  https://theweek.com/articles/632836/brief-history-tv-shows-opening-credit-sequences
- Arabic teters as Ramadan-show production elements and ad-pressure variability:
  https://www.elwatannews.com/news/details/756175
- Arabic article on cancellation/removal of teters due to ad pressure:
  https://www.almasryalyoum.com/news/details/758531
- Arabic Ramadan opening songs and pre-opening scene example:
  https://scoopempire.com/highlighting-top-ramadan-show-opening-songs/

## Working Model

We need to explicitly support two show patterns:

1. Fixed-position intros
   - The intro starts at nearly the same timestamp in every episode.
   - Common in many traditional broadcast/library encodes.
   - Detection should favor stable time clusters and avoid overlong shared
     segments.

2. Variable cold-open intros
   - A variable-length dialogue/story scene appears before the intro.
   - The intro audio is still shared, but its start time shifts by episode.
   - Detection should match the repeated audio segment even when offsets differ,
     then store per-show skip timing only when the result can be applied safely.

Arabic-first assumption:

- Arabic shows likely include both patterns, but the local failures suggest the
  current misses are not explained by simple duration threshold, Hamming
  threshold, episode count, or scan window alone. We need better diagnostics
  before changing production behavior.

## Goals

1. Improve Arabic audio-detection success rate without increasing false
   positives.
2. Distinguish fixed-position intros from variable cold-open intros in reports.
3. Add enough diagnostics to explain every miss class.
4. Keep production defaults conservative until measured data supports a change.
5. Defer English/Fenlight/Real-Debrid implementation until the Arabic detector
   strategy is proven.

## Non-Goals For This Phase

- Do not tune against the local library for English content.
- Do not add Fenlight/Real-Debrid probing until Arabic metrics and detector
  behavior are stable.
- Do not lower thresholds blindly just to increase apparent hit rate.
- Do not accept overlong common segments as intros without additional evidence.

## Phase 1: Arabic Measurement Harness

Enhance `test-container/audio_library_probe.py` and/or a small companion script
so we can build repeatable Arabic datasets.

Planned changes:

- Add deterministic sampling modes:
  - `--sample-strategy alphabetical|random|from-file`
  - `--seed`
  - `--show-title` repeated option for targeted repros.
- Save compact result summaries for sweeps:
  - show title
  - episode ids/files
  - hit/miss
  - detected start/end/duration
  - optional manual ground-truth start/end for a reviewed subset
  - elapsed time
  - failure reason
  - scan parameters
  - detector candidate diagnostics once Phase 2 exists.
- Run baseline Arabic sweeps:
  - 30 shows x 3 episodes, 90s scan.
  - 30 shows x 5 episodes, 90s scan.
  - Targeted reruns for all misses with 180s and 300s scan.

Acceptance criteria:

- We can reproduce the same Arabic sample with one command.
- We have a saved JSON report for the baseline and each parameter sweep.
- The report separates true detector misses from source/probe failures.
- At least 5-10 shows in the 30-show sample have manual ground-truth labels so
  we can measure boundary accuracy, not just hit/miss rate.

## Phase 2: Detector Diagnostics

Before changing matching, expose why each show did or did not match.

Planned changes in `resources/lib/audio_intro.py`:

- Add an optional `diagnostics` dict argument to the fingerprint detection path.
  The harness can pass it in and production callers can omit it, avoiding normal
  runtime logging/noise.
- Collect top candidate pair matches instead of only `best` and `best_rejected`.
- Record rejection reasons:
  - below minimum duration
  - outside intro bounds
  - over max plausible intro duration
  - poor time clustering
  - insufficient episode consensus
  - no matching fingerprints at all.
- Include candidate metadata for diagnostics:
  - left/right start/end
  - raw start/end
  - duration/raw duration
  - average Hamming distance
  - RMS distribution and quiet/loud-window counts
  - start spread
  - episode pair ids.
- Keep diagnostics optional so normal addon runtime does not become noisy.

Acceptance criteria:

- For every Arabic miss in the 10-show and 30-show samples, the harness can say
  whether the detector saw no candidate, only too-short candidates, only
  out-of-bounds candidates, or unstable candidates.

## Phase 3: Fixed-Position Intro Strategy

Add a conservative path for intros that start at the same time across episodes.

Approach:

- Continue using pairwise matching, then cluster candidate start/end times across
  episode pairs.
- Treat a show as fixed-position only when candidate starts cluster within a
  tight timestamp tolerance across enough pairs.
- Allow short gaps/dropouts within each run.
- Require at least two matching episodes initially; prefer three or more when
  available.
- Score by:
  - run duration
  - timestamp consistency
  - number of participating episodes
  - average distance
  - plausible duration range.

Guardrails:

- Do not return segments longer than a configured plausible max unless manually
  enabled in the harness.
- Prefer the shortest stable run that satisfies the intro threshold over an
  overlong run that absorbs surrounding identical audio.

Acceptance criteria:

- Fixed-position synthetic cases pass.
- Arabic baseline hit rate improves or stays the same.
- False-positive spot checks do not increase.

## Phase 4: Variable Cold-Open Strategy

Improve shifted-offset matching for shows where dialogue length varies before
the intro.

Approach:

- Keep pairwise offset matching, but cluster candidates by repeated audio
  duration and relative shape rather than absolute start time.
- For each candidate cluster, decide whether it is safe to store a show-level
  skip:
  - If starts are clustered tightly, store normal show-level start/end.
  - If starts vary widely, do not store a single show-level timestamp unless we
    can compute an episode-specific time at playback.
- Consider storing a show-level fingerprint profile for later per-episode
  matching only if the data model and runtime cost are acceptable. This would be
  a larger architecture change because playback would need to extract and match
  audio from the current episode before applying a skip.

Guardrails:

- Avoid returning a show-level timestamp for variable-start intros when that
  timestamp would skip dialogue in some episodes.
- For Arabic first, variable-start intros should be "detected but not
  auto-applied"; expose them as context-menu suggestions or manual-confirmation
  candidates rather than silently auto-skipping.

Acceptance criteria:

- Variable-offset synthetic harness cases pass, including fractional offsets
  that currently miss.
- Arabic variable-start candidates are classified separately from fixed-start
  candidates.
- No production behavior change is made for variable-start shows until we have a
  safe storage/playback plan.

## Phase 5: Overlong Match Control

Address the 87s-to-163s expansion seen when scan time was increased.

Approach:

- Add configurable `fingerprint_max_intro_seconds` for intro candidates.
- Test candidate trimming:
  - choose earliest stable sub-run inside an overlong run
  - optionally split long runs at low-confidence/gap points
  - prefer the most repeated high-confidence subsegment.
- Add a harness flag to report overlong candidates instead of accepting them.

Initial hypothesis:

- Arabic full teters may be longer than many American intros, so a hard 60s cap
  is too aggressive. Start measurement with candidate buckets:
  - short: 15-45s
  - normal: 45-120s
  - long: 120-180s
  - suspicious: >180s or expands with scan length.

Acceptance criteria:

- Longer scan windows do not change a previously plausible 80-90s intro into an
  obviously overlong skip without explanation.
- Harness reports overlong candidates distinctly.

## Phase 6: Arabic Evaluation Loop

Run the Arabic sweeps after each detector change.

Metrics:

- Strict hit rate: detected intro looks plausible by automated constraints.
- Manual-checked hit rate: sampled hits confirmed by spot check.
- Miss breakdown by reason.
- False-positive count.
- Median and p95 runtime per show.

Initial target:

- Move Arabic strict hit rate from 30% toward 50%+ on the 30-show sample without
  adding observed false positives.

Stop condition:

- If diagnostics show most Arabic misses have no stable repeated intro audio,
  stop tuning thresholds and document that source/episode variability is the
  limiting factor.

## Phase 7: English/Fenlight/Real-Debrid Later

After Arabic is stable, build a separate English probe.

Constraints:

- Do not use the local Kodi TV library for English.
- Use Fenlight and Real-Debrid-resolved streams.

Plan outline:

- Identify the safest way to trigger or resolve Fenlight streams in Kodi without
  changing user settings.
- Capture resolved playback URLs or temporary `.strm`-equivalent inputs.
- Reuse the audio detector and reporting format from the Arabic harness.
- Build an English sample split by likely format:
  - sitcom with fixed short cold open
  - drama with variable cold open
  - streaming prestige title with long title sequence
  - title-card/minimal intro.

English-specific expectations:

- Cold opens commonly precede intros.
- Intro durations vary more aggressively, from very short title cards to
  60-90s+ sequences.
- Variable-start handling will matter more than for fixed-position Arabic
  teters.

## Verification Commands

Baseline unit tests:

```bash
python3 test_video_metadata.py -v
```

Synthetic audio matrix:

```bash
python3 test-container/audio_detection_harness.py --matrix
```

Arabic local-library probe example:

```bash
python3 test-container/audio_library_probe.py \
  --path-map 'smb://nas/share/=/Volumes/share/' \
  --language arabic \
  --shows-per-language 30 \
  --episodes-per-show 3 \
  --max-scan-seconds 90 \
  --ffmpeg-timeout-seconds 60 \
  --skip-outro \
  --output /tmp/skipintro_arabic_30x3.json
```

## Open Questions

- What is the acceptable false-positive rate for automatic audio detection?
- Should variable-start intros be saved as show-level config, episode-level
  config, or "detected but needs confirmation"?
- Do we want a temporary debug setting in Kodi, or keep all diagnostics in
  `test-container` tooling only?
- For Arabic long teters, what should the maximum plausible skip duration be
  before confirmation is required?
