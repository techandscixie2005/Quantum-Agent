# 教学图谱候选审核包（2026-09-15）

这些内容由课程原文抽取，全部保持 `review_required`，尚未审批或发布。来源与页码可核对，语义正确性仍由教师审核。

审核入口：`http://127.0.0.1:3000/teacher/knowledge`。完整节点和关系见 [JSON](artifacts/2026-09-15-course-review.json)。

| 类型 | 候选数 |
|---|---:|
| approximation | 3 |
| assumption | 3 |
| concept | 53 |
| derivation | 7 |
| derivation_step | 11 |
| formula | 30 |
| hint | 2 |
| mathematical_object | 4 |
| misconception | 2 |
| physical_system | 3 |
| principle | 7 |
| quantum_state | 1 |
| symbol | 8 |
| validity_condition | 6 |

共 140 个节点支持记录、51 条关系支持记录。

## 审核时必须处理的质量问题

精确引文只证明文字出现在原文中，不能证明节点分类或关系正确。例如下列
`Non-degenerate states assumption` 只引用了“Dealing with degeneracy”，不能支持
“非简并”假设，应拒绝或重新补充正文证据；`State vector perturbation` 等目录式
短语也不足以构成推导步骤。`The resulting eigen-energies` 缺少实际等式，须补全
证据后再审。不要整批批准。对其余候选逐一核对公式、前置条件、关系方向及
课程版本，再通过教师工作台审核并发布派生图谱版本。

七章的关键词命中统计仅用于选取后续审核材料，不能视为章节教学内容已经完整。

## 重点教学对象

### assumption：Non-degenerate states assumption

- 候选 ID：`27602cf0-d4a4-5afd-939f-19551420a70d`
- 来源：Steven Weinberg - Lectures on Quantum Mechanics-Cambridge University Press (2012)-1，物理页 10
- 状态：review_required

> Dealing with degeneracy

### assumption：Basis vectors are normalized

- 候选 ID：`df88c8f0-f7c8-5870-8c8d-ac1ccf247a96`
- 来源：Yan_QPhys，物理页 11
- 状态：review_required

> (b) i · i = j · j = 1
> (normalized)

### assumption：Basis vectors are orthogonal

- 候选 ID：`bbff8ac5-f214-5818-b5d1-6c95ff5efc00`
- 来源：Yan_QPhys，物理页 11
- 状态：review_required

> (a) i · j = 0
> (orthogonal)

### derivation_step：State vector perturbation

- 候选 ID：`6d17d7c0-fc48-58cd-8492-74a482548356`
- 来源：Steven Weinberg - Lectures on Quantum Mechanics-Cambridge University Press (2012)-1，物理页 10
- 状态：review_required

> State vector perturbation

### derivation_step：Perturbation series δEa and δa

- 候选 ID：`564cb426-3230-5a05-810e-96dcf4441959`
- 来源：Steven Weinberg - Lectures on Quantum Mechanics-Cambridge University Press (2012)-1，物理页 169
- 状态：review_required

> δEa = δ1Ea + δ2Ea + · · ·,
> δa = δ1a + δ2a + · · ·,
> (5.1.3)
> with δN Ea and δNa proportional to ϵN.

### derivation_step：Harmonic oscillator systems go by the potential energy

- 候选 ID：`54ea008c-3e19-574e-a45f-211ed1eb74eb`
- 来源：Yan_QPhys，物理页 33
- 状态：review_required

> Harmonic oscillator systems go by the potential energy the form of
> V (x) = 1
> 2mω2x2

### derivation_step：The resulting eigen-energies

- 候选 ID：`0a77c964-fe68-5ef4-8f25-333be491832f`
- 来源：Yan_QPhys，物理页 33
- 状态：review_required

> The resulting eigen-energies are

### derivation_step：Determine unknowns in Eq. (4.1.25)

- 候选 ID：`dac38da6-f784-5430-a6c9-68eee943025a`
- 来源：Yan_QPhys，物理页 78
- 状态：review_required

> Exercise: (a) Determine the unknowns in Eq. (4.1.25).

### derivation_step：Verify Eqs. (4.1.27)–(4.1.29)

- 候选 ID：`cf06cc15-22b6-57e4-9efe-c7bf17e1c982`
- 来源：Yan_QPhys，物理页 78
- 状态：review_required

> (b) Verify Eqs. (4.1.27)–(4.1.29),
> by using cos(iα) = cosh α and sin(iα) = sinh α. See also Eqs. (4.1.19)–(4.1.23).

### derivation_step：Apply boundary condition to bound state

- 候选 ID：`971370c8-9d78-5cd1-8aaa-3e377fe98452`
- 来源：Yan_QPhys，物理页 81
- 状态：review_required

> Apply then Eq. (4.1.39), resulting in
> √mα
> ψ(x) =
> 2ℏ2
> (4.1.41)
> ℏ
> e−mα|x|/ℏ2
> with
> E = −mα2

### derivation_step：Boundary values of the bound state

- 候选 ID：`3474635b-cef0-5c60-873b-4b6a5d91f426`
- 来源：Yan_QPhys，物理页 81
- 状态：review_required

> with the boundary values satisfying
> ψ(0) = √κ and ψ′(0+) −ψ′(0−) = −2κ√κ
> (4.1.40′)

### derivation_step：Integral of Vψ for δ-potential

- 候选 ID：`84417141-0eb0-561c-a224-4ea4e6803f2d`
- 来源：Yan_QPhys，物理页 81
- 状态：review_required

> Z ϵ
> Z ϵ
> V (x)ψ(x)dx = −α
> δ(x)ψ(x)dx = −αψ(0)
> −ϵ
> −ϵ

### derivation_step：Integral of ψ'' yields ψ' difference

- 候选 ID：`81eff4fe-ac85-5e34-ad23-4496a71f201c`
- 来源：Yan_QPhys，物理页 81
- 状态：review_required

> Z ϵ
> −ϵ
> (4.1.38)
> ψ′′(x)dx = ψ′(ϵ) −ψ′(−ϵ)

### derivation_step：Limiting Schrödinger equation integral

- 候选 ID：`e6f7198c-c0ee-5765-a05c-98146c05fc0c`
- 来源：Yan_QPhys，物理页 81
- 状态：review_required

> Consider the Schr¨odinger equation the limiting expression,
> 
> Z ϵ
> Z ϵ
> dx = E lim
> ψ(x)dx = 0
> (4.1.37)
> 2mψ′′(x) + V (x)ψ(x)
> 
> −ℏ2
> ϵ→0
> lim
> ϵ→0
> −ϵ
> −ϵ

### misconception：RHF overestimates ionic contribution

- 候选 ID：`f1f1b480-0224-513f-ba3d-29aea5d12ef6`
- 来源：Yan_QPhys，物理页 252
- 状态：review_required

> the RHF overestimates the ionic contribution, resulting in the wrong dissociation
> limit, Eq. (10.4.33).

### misconception：UHF is spin contaminated

- 候选 ID：`e8323d5b-4072-58be-a294-fc0b76d24234`
- 来源：Yan_QPhys，物理页 252
- 状态：review_required

> the UHF is in general spin contami-
> nated, as by the last term of Eq. (10.4.21) or Eq. (10.4.35): |ψα
> 1 ¯ψβ
> 1 ⟩is no longer
> factorizable into spatial and spin components, with different particle–permutation
> parities.

### validity_condition：Estimate of corrections

- 候选 ID：`e04e049c-6a7c-5e87-9dc0-cd909261926e`
- 来源：Steven Weinberg - Lectures on Quantum Mechanics-Cambridge University Press (2012)-1，物理页 10
- 状态：review_required

> Estimate of corrections

### validity_condition：Validity conditions

- 候选 ID：`8cbd2c34-8fc7-5a1b-8bd9-fcb4a35a74ef`
- 来源：Steven Weinberg - Lectures on Quantum Mechanics-Cambridge University Press (2012)-1，物理页 10
- 状态：review_required

> Validity conditions

### validity_condition：orthonormal eigenvectors of A

- 候选 ID：`72d167e2-1dc5-5947-9b54-00e68dd37d17`
- 来源：Steven Weinberg - Lectures on Quantum Mechanics-Cambridge University Press (2012)-1，物理页 112
- 状态：review_required

> where nr are all the orthonormal eigenvectors of A with
> eigenvalue an.

### validity_condition：Hamiltonian considered as function of x_n and p_n

- 候选 ID：`06cc4ea3-d6b7-5c59-91af-c923d692a944`
- 来源：Steven Weinberg - Lectures on Quantum Mechanics-Cambridge University Press (2012)-1，物理页 320
- 状态：review_required

> in using the Hamiltonian to derive dynamical equations,
> we must consider it as in Eq. (9.3.4), as a function of the xn and pn, and not as a
> function of the xn and ˙xn

### validity_condition：α(x,t) is an arbitrary real function

- 候选 ID：`a0f9581f-2b4e-5e4f-a443-470624b7c836`
- 来源：Steven Weinberg - Lectures on Quantum Mechanics-Cambridge University Press (2012)-1，物理页 320
- 状态：review_required

> (where α(x, t) is an arbitrary real function)

### validity_condition：Dissociation regime: θ = π/4 and S = 0

- 候选 ID：`0e1b9066-beb5-506c-8623-eec3b4824d14`
- 来源：Yan_QPhys，物理页 252
- 状态：review_required

> vanishes in the dis-
> sociation regime, where θ = π/4 and S = 0.

## 课程覆盖的检索线索

以下只证明材料中存在相关术语，不代表该章节的教学结构、练习及科学验证已完整验收。

| 课程主线 | 命中原文片段 |
|---|---:|
| 原子模型与旧量子论 | 38 |
| 量子力学基础 | 355 |
| 表象理论与矩阵力学 | 99 |
| 原子结构 | 101 |
| 近似理论方法 | 104 |
| 双原子分子 | 16 |
| 分子光谱 | 13 |
