# Finite barriers heldout teacher packet 1.0.0

**UNREVIEWED TEACHING MATERIAL. No teacher approval, student participation, classroom results, validated alternate-form equivalence, or demonstrated learning gain is claimed.** This packet was created after the fixed examples used in the recorded October 19 model runs. Its new questions and contrasting cases were not used to tune those earlier prompts. It is a prospective heldout resource, not a retrospective accuracy estimate or proof that a provider has never seen similar problems.

Give students only one file from `student-forms/`. Keep `teacher-only/`, the reference script and reference outputs out of student handouts, runtime retrieval manifests and model prompts. These directory names are workflow labels, not access control: anyone with repository or review-archive access can read the keys. An actual teacher must check prior student exposure, withhold the keys, or select a fresh private equivalent form; preregister exposure-based exclusions before the trial. Do not call the assessment blinded solely because of a file label. Retire a form from heldout use after it has been exposed to the tutor or used to tune a prompt; record the exposure and issue a new packet version.

The forms cover the same eight conceptual domains with different parameters and wording. They are complete drafts for a teacher to review and pilot, not psychometrically equated tests. Suggested use is A for pretest, B for immediate independent assessment, C for delayed assessment 7–14 days later. Counterbalance the three forms across students if the teacher can administer and record that allocation consistently. Do not compare unmatched items or quietly change allowed aids between occasions.

## Files and distribution

| Audience | File | Purpose |
|---|---|---|
| Students | [Form A](student-forms/form-a-pretest.md) | Initial predictions, explanations and calculations |
| Students | [Form B](student-forms/form-b-immediate.md) | Immediate alternate task form |
| Students | [Form C](student-forms/form-c-delayed.md) | Delayed alternate task form |
| Teachers only | [Answer key and derivations](teacher-only/answer-key.md) | Complete reference reasoning, scope and numerical answers |
| Teachers only | [Rubric anchors](teacher-only/rubric-and-examples.md) | Observable criteria and contrasting responses |
| Teachers only | [Administration and review](teacher-only/administration.md) | Real teacher/student steps, coding and reporting |
| Teachers only | `reference-cases.json`, `reference-results.json` | Numerical inputs and independently checked outputs |
| Operators | `manifest.json` | Version, source links and SHA-256 digests |

The versioned runtime teaching design `finite-barriers@1.0.0` is preserved. `finite-barriers@1.1.0` clarifies the assessment interpretation; it is not automatically substituted into existing conversations. This heldout packet has its own version and digest manifest and does not become published course evidence through its presence in the repository.

## Reproducing the reference checks

From the repository root, using the installed backend environment:

```powershell
services/api/.venv/Scripts/python.exe scripts/verify-heldout-barriers.py
```

The script uses `mpmath` from the locked backend environment, 100 decimal digits, constant particle mass, real stationary potentials and two propagating exterior channels. It solves interface equations and separately evaluates a closed transfer amplitude, comparing relative transmission, boundary residuals and current conservation. Decimal strings preserve tiny positive values and their logarithms. The output records input/script digests and the numerical library version. The supplied physical constants have finite precision; 100-digit arithmetic is a stability check, not a 100-digit physical measurement.

The classroom runtime still rejects its near-threshold band, unequal asymptotes and opaque cases beyond its independently verified float64 range. A mathematically well-defined example outside that implementation scope should be marked unsupported, not converted to an incorrect student answer. The teacher key explains those cases independently.

The numerical cases also run as automated regression checks. One above-barrier resonance disclosed a reference bound that rejected `1+2 ULP` of roundoff; that bound was corrected. Agreement after that fix is regression verification, not an untouched heldout estimate of code accuracy. No packet content was sent to a live model or used to tune the earlier prompts. A future independent evaluation of code generalization must select additional unrevealed cases.

## Scientific sources

The packet uses original questions and derivations. Primary teaching sources supporting the governing equations are [MIT 8.04 lecture notes hosted by National Tsing Hua University](https://www.phys.nthu.edu.tw/~edyen/100-general-physics/notes/modern/Week11_Lec2.pdf), Lecture XV for probability current and unequal wave numbers, Lecture XVI for matching and finite barriers; and [OpenStax University Physics Volume 3 section 7.6](https://openstax.org/books/university-physics-volume-3/pages/7-6-the-quantum-tunneling-of-particles-through-potential-barriers) for barrier attenuation and the conditions for the opaque-barrier approximation. The threshold limit and the numerical checkpoints below are independently derived here. An actual physics teacher must review the packet, calculations, notation and fit to the taught syllabus before use.
