# Teacher reference explanations and numerical key

**TEACHER ONLY. UNREVIEWED DRAFT.** These are reference solutions for checking reasoning, not evidence that any student answered correctly or that a teacher approved the questions. Keep the original student response visible when assigning a criterion; never substitute a model summary for the response. Numbers alone cannot receive the explanation criteria. Numerical checkpoints use the supplied finite-precision constants.

## Common model and source conventions

The full width is `a`, the left interface is `x=0`, and the right interface is `x=a`. The particle mass is constant and the potential is real. Write the left/right exterior potentials as `UL,UR`; total energy is `E`. The propagating exterior wave numbers are `kL=√[2m(E−UL)]/ℏ` and `kR=√[2m(E−UR)]/ℏ`. Energies must be converted to joules in these SI expressions. The inside quantity is `q=√[2m(E−V0)]/ℏ`, possibly imaginary. There is no right-incident wave. Transmitted amplitude `t` below is referenced at `x=a`.

The governing stationary equation, matching conditions and probability current follow [MIT 8.04 Lectures XV and XVI](https://www.phys.nthu.edu.tw/~edyen/100-general-physics/notes/modern/Week11_Lec2.pdf), PDF pages 12–26. That source sometimes uses interfaces `−a,+a` and therefore full width `2a`; do not mix that notation with this packet's full width `a`. [OpenStax section 7.6](https://openstax.org/books/university-physics-volume-3/pages/7-6-the-quantum-tunneling-of-particles-through-potential-barriers) also describes attenuation and the opaque approximation. The threshold expressions below are derived here rather than asserted as supported by the runtime.

## Q1 and Q2 Below the barrier and boundary conditions

For `0<E<V0`, equal zero exterior potentials and `κ=√[2m(V0−E)]/ℏ>0`, use

```text
ψL(x) = exp(ikx) + r exp(−ikx)
ψB(x) = C exp(κx) + D exp(−κx), 0≤x≤a
ψR(x) = t exp[ik(x−a)]

1+r = C+D
ik(1−r) = κ(C−D)
C exp(κa)+D exp(−κa) = t
κ[C exp(κa)−D exp(−κa)] = ikt
```

Both exponentials are allowed on a finite interval: neither diverges at infinity within that interval. The condition `E<V0` changes the sign in the differential equation; it does not force its solution to vanish. Matching the two interfaces can produce a nonzero outgoing amplitude. It does not imply absorption, loss of total energy, or a classical trajectory inside the barrier.

With `j=(ℏ/m) Im(ψ*ψ′)`, `T=j_transmitted/j_incident=(kR/kL)|t|²` and `R=|r|²`. Only when exterior wave numbers and masses match does `T=|t|²` for incident amplitude 1. Constant mass gives continuity of both `ψ` and `ψ′`; a discontinuous effective mass requires a separately specified interface model and is outside this packet.

Eliminating the interior amplitudes for equal zero exteriors gives

```text
T = [1 + A sinh²(κa)]⁻¹, A = V0²/[4E(V0−E)] > 0.
dT/da = −A κ sinh(2κa) / [1+A sinh²(κa)]² < 0  (a>0).
```

Here the energy ratio in `A` may consistently use eV because its units cancel. At fixed `E,V0,m`, both `κ` and amplitude decay length `ℓ=1/κ` are fixed; `a` and `a/ℓ=κa` increase. Probability-density e-fold length for a single decaying exponential is `1/(2κ)` and is fixed too. The exact interior finite-barrier solution remains a superposition; do not claim that every local interior probability value simply equals a single decaying exponential.

| Form | Widths in nm | Narrow T | Wide T | Required conclusion |
|---|---:|---:|---:|---|
| A | 0.08 → 0.16 | 0.390335974567 | 0.072499631760 | T decreases; decay scale unchanged |
| B | 0.11 → 0.19 | 0.220921498882 | 0.036268881414 | Same conditional reasoning |
| C | 0.09 → 0.17 | 0.264567123630 | 0.044264668008 | Same conditional reasoning |

Q1 requires a direction and causal conditions, not these exact decimals. Q2 requires the actual continuity/current relationships, not two isolated keywords.

## Q3 Exactly at the barrier height

At `E=V0`, the inside stationary equation is `ψB″=0`, so `ψB=C+Dx`. It is neither an oscillatory wave nor the assertion `ψ=0`. Write `D` here with units of inverse length. Matching gives

```text
1+r = C,  ik(1−r)=D,
C+Da = t, D=ikt.
2 = t(2−ika),
T = 4/[4+k²a²] = [1 + m V0 a²/(2ℏ²)]⁻¹.
```

The same expression follows as `δ=V0−E→0+`: `sinh²(κa)≈κ²a²`, with `κ²=2mδ/ℏ²`, cancelling the apparent singularity. The limit from above uses `sin²(qa)≈q²a²` and agrees. Thus a finite, nonzero-width positive barrier at threshold generally has `0<T<1`. Exact zero and universal perfect transmission are both wrong conclusions for the stated cases.

| Form | E=V0 in eV | a in nm | Threshold T |
|---|---:|---:|---:|
| A | 4.4 | 0.12 | 0.706339404310 |
| B | 5.2 | 0.15 | 0.565700405497 |
| C | 3.8 | 0.18 | 0.553134727968 |

The classroom runtime rejects its near-threshold band for numerical support reasons. That refusal is not a physics verdict on the answer. Use this derivation and the separate high-precision reference check, not a false runtime PASS claim.

## Q4 Above the barrier

For equal zero exterior potentials, `E>V0>0` and `q=√[2m(E−V0)]/ℏ`, matching yields

```text
T = [1 + B sin²(qa)]⁻¹, B = V0²/[4E(E−V0)] > 0.
```

At `qa=nπ`, `T=1`; at `qa=(n+1/2)π`, `T=1/(1+B)<1`. These are coherent interface-interference results, not classical zero reflection for every above-barrier energy. Increasing width can raise or lower T. The strict width monotonicity derived in Q1 is limited to fixed sub-barrier `0<E<V0`; it is not valid across all energies, changing asymptotic potentials, absorbing barriers or arbitrary composite barriers.

| Form | a at qa=π/2 in nm | T at qa=π/2 | a at qa=π in nm | T at qa=π |
|---|---:|---:|---:|---:|
| A | 0.1461689096 | 0.895621301775 | 0.2923378191 | 1 |
| B | 0.1445356861 | 0.852880465378 | 0.2890713722 | 1 |
| C | 0.1496086486 | 0.913494809689 | 0.2992172972 | 1 |

Form A's `qa=3π/2` has `a≈0.4385067287 nm` and returns to `T≈0.895621301775`, explicitly showing nonmonotonicity. Do not round widths before calculating a resonance checkpoint; the reference uses the specified phase exactly.

## Q5 Unequal exterior potentials

Both exterior channels propagate in the supplied examples. The transmitted particle has different kinetic energy and speed from the incident particle, while its total energy remains E. With constant mass,

```text
j_in = (ℏ kL/m), j_trans = (ℏ kR/m)|t|²,
T = (kR/kL)|t|², R = |r|².
```

The supplied trial amplitudes are intentionally hypothetical. Correctly converting them is distinct from solving the entire matching problem:

| Form | kR/kL | Hypothetical \|t\|² | Trial-implied T | Full matching T, teacher reference only |
|---|---:|---:|---:|---:|
| A | 0.872278375989 | 0.16 | 0.139564540158 | 0.183862250927 |
| B | 0.824163383692 | 0.25 | 0.206040845923 | 0.149096568192 |
| C | 0.891555828242 | 0.36 | 0.320960098167 | 0.249294680015 |

The full matching values use the four interface equations and probability current; they do not reuse the trial amplitudes. If `E≤UR`, a propagating transmitted current on the right cannot be assumed. That different channel case is not one of the examples here. The classroom runtime's rectangular-barrier request assumes equal zero exteriors and must not be used to certify Q5.

For reproducibility, let `q²=2m(E−V0)/ℏ²` and retain consistent units. Eliminating the interior coefficients gives the interface-referenced transfer amplitude

```text
t = 2 kL / [(kL+kR)cos(qa) − i(q+kL kR/q)sin(qa)].
```

For imaginary `q=iκ`, this is continued with hyperbolic functions. At `q=0`, its denominator tends to `(kL+kR)−i kL kR a`. The script independently solves the interface-centered four-equation system and checks agreement with this expression, with each probability formed using the appropriate current ratio.

## Q6 Tiny positive values and underflow

The finite real barriers in these open-channel examples have positive T. A printed zero could arise from a formula error, a formatting/rounding policy, or floating-point underflow; the output alone does not distinguish them. The 2.4–2.7 nm cases are still representable and within the reference float64 opaque bound, so returning exactly zero is an error for those inputs. The 300 nm case is far beyond the classroom verifier's supported opaque range and should yield unsupported/inconclusive rather than a certified zero.

| Case | High-precision T | log10(T) approximately |
|---|---:|---:|
| A6 | 7.6162543283×10⁻⁴⁵ | −44.1182585621 |
| B6 | 1.3405816996×10⁻⁵⁰ | −49.8727067135 |
| C6 | 1.0656063617×10⁻⁴⁷ | −46.9724031954 |
| Shared opaque case | 3.8091779071×10⁻⁵⁰³¹ | −5030.4191687432 |

Useful checks include independent boundary matching, a high-precision/log-domain computation, relative transmission error for positive references, current conservation computed from independent amplitudes, and explicit support-range guards. Absolute agreement at `10⁻⁶` alone can accept zero or values many orders of magnitude wrong. Logarithmic error must also have a justified tolerance and handle nonpositive claimed values explicitly. A logarithm does not repair a wrong physical formula.

The opaque asymptotic approximation `T≈16E(V0−E)/V0² exp(−2κa)` requires `κa≫1`; it is not the exact expression at arbitrary width. Use its log only in its stated regime. A 100-digit reference result is a numerical cross-check under supplied assumptions, not a classroom result or an expansion of runtime support.

## Q7 Width and decay length

The correct distinction is `a` versus `ℓ=1/κ`. Only a changes when energy, height and mass are fixed. The larger dimensionless thickness `a/ℓ` increases attenuation across the interval. A phrase such as “longer decay length” conventionally says the exponential scale `ℓ` changed and is misleading here; it must not replace “longer attenuation distance.” If E approaches V0 while height and mass stay fixed, κ decreases and ℓ increases; that is a different parameter variation. At fixed width, a larger ℓ means weaker spatial attenuation, not the proposed width-caused stronger attenuation.

This distinction is supported by the decay-length definition in the [MIT lecture notes](https://www.phys.nthu.edu.tw/~edyen/100-general-physics/notes/modern/Week11_Lec2.pdf), PDF pages 12 and 22. Do not apply a blanket phrase ban: a student may correctly discuss changing decay length in an experiment that changes E or V0.

## Q8 Validation and what counts as evidence

Defining `R=1−T` makes `R+T=1` an identity. It can detect a later arithmetic/serialization problem but does not independently validate T, the choice of regime, units, approximation or student explanation. Solve the complex interface equations for both amplitudes or use another independently expressed physical calculation; compare positive tiny T relatively and report unsupported cases honestly.

Keep four judgments separate:

1. A valid independent submission records a task-correlated first answer while in-app assistance was locked. It may be wrong, incomplete or unknown; external help still needs actual classroom observation.
2. Numeric correctness checks a specified output against a scoped reference. An answer can give the right number while asserting a wrong mechanism.
3. Explanation/rubric assessment examines the student's actual argument, conditions and contradictions. A model-supported interpretation is a candidate judgment. A missing explanation is `not_assessed`, not proof of mastery and not automatically a specific misconception.
4. Demonstrated performance on reviewed criteria requires an actual attributed teacher judgment with reasons. A claim about retained mastery or instructional effectiveness additionally needs appropriate delayed and comparative evidence; neither follows from an app loop completing.

Reference-only checkpoints can support the teacher's review of calculations. They cannot fill in a missing student derivation or create a teacher approval. Preserve first attempts, later responses and all known assistance as different records.
