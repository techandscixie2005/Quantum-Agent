"""Reusable, immutable teaching designs; never a substitute for published evidence.

Package versions are source controlled. Their content digest is part of the
learning record, so an edited rubric cannot silently change an earlier assessment.
"""

# ruff: noqa: RUF001

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CoursePackageSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package_id: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def known_version(self) -> CoursePackageSelection:
        if (self.package_id, self.version) not in _PACKAGES:
            raise ValueError("unknown course package version")
        return self


class CoursePackageRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package_id: str
    version: str
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    objective_ids: tuple[str, ...]
    rubric_ids: tuple[str, ...]


class LearningObjective(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    objective_id: str
    description: str
    observable_evidence: str


class RubricCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    criterion_id: str
    objective_id: str
    description: str
    meets: str
    partial: str
    needs_revision: str
    evaluator: str


class PackageTask(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    stage: str
    prompt: str
    objective_ids: tuple[str, ...]


class CoursePackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package_id: str
    version: str
    title: str
    audience: str
    prerequisites: tuple[str, ...]
    assumptions: tuple[str, ...]
    objectives: tuple[LearningObjective, ...]
    rubric: tuple[RubricCriterion, ...]
    tasks: tuple[PackageTask, ...]
    evidence_policy: str
    validation_status: str

    @model_validator(mode="after")
    def traceable_objectives_and_criteria(self) -> CoursePackage:
        objectives = {item.objective_id for item in self.objectives}
        if len(objectives) != len(self.objectives):
            raise ValueError("course objective identifiers must be unique")
        criteria = {item.criterion_id for item in self.rubric}
        if len(criteria) != len(self.rubric):
            raise ValueError("rubric identifiers must be unique")
        tasks = {item.task_id for item in self.tasks}
        if len(tasks) != len(self.tasks):
            raise ValueError("task identifiers must be unique")
        if any(item.objective_id not in objectives for item in self.rubric) or any(
            not set(item.objective_ids) <= objectives for item in self.tasks
        ):
            raise ValueError("rubrics and tasks must reference package objectives")
        return self

    def reference(self) -> CoursePackageRef:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return CoursePackageRef(
            package_id=self.package_id,
            version=self.version,
            content_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            objective_ids=tuple(item.objective_id for item in self.objectives),
            rubric_ids=tuple(item.criterion_id for item in self.rubric),
        )


FINITE_BARRIERS = CoursePackage(
    package_id="finite-barriers",
    version="1.0.0",
    title="有限方势垒：预测、解释与独立迁移",
    audience="本科量子力学；建议一课时后安排延迟独立测评",
    prerequisites=("定态薛定谔方程", "复指数与指数函数", "概率流与边界连续性"),
    assumptions=(
        "一维、静态、实有限方势垒；粒子质量恒定；左右自由区势能相同。",
        "本包的宽度单调性任务限于固定 0<E<V0、固定质量与势垒高度。",
        "T 是透射概率流与入射概率流之比；左右波数不同时不能直接使用振幅模平方。",
        "数值下溢到零不代表有限势垒的透射严格为零；须报告对数尺度或精度限制。",
    ),
    objectives=(
        LearningObjective(
            objective_id="FB-O1",
            description="解释禁阻区中的非零指数解。",
            observable_evidence="初答与重构中区分经典禁阻和波函数非零。",
        ),
        LearningObjective(
            objective_id="FB-O2",
            description="用边界条件与概率流建立 T 的物理含义。",
            observable_evidence="学生说明连续性决定振幅、概率流比定义透射率。",
        ),
        LearningObjective(
            objective_id="FB-O3",
            description="预测宽度对透射率的影响并检验数值可信性。",
            observable_evidence="记录带条件的趋势预测、T/R 与精度或验证限制。",
        ),
        LearningObjective(
            objective_id="FB-O4",
            description="在无辅助的新任务中解释并应用这些关系。",
            observable_evidence="保存 Solo 首答、修订次数和延迟独立作答；教师复核。",
        ),
    ),
    rubric=(
        RubricCriterion(
            criterion_id="FB-R1",
            objective_id="FB-O1",
            description="禁阻区解释",
            meets="指出 E<V0 下非零指数解，未将经典禁阻等同于零波函数。",
            partial="预测非零但缺少机制解释。",
            needs_revision="断言有限势垒内波函数必为零。",
            evaluator="模型候选分析；需教师基于学生原文复核",
        ),
        RubricCriterion(
            criterion_id="FB-R2",
            objective_id="FB-O2",
            description="连续性与概率流",
            meets="连接边界连续性、透射振幅与入射/透射概率流之比。",
            partial="提及连续性或概率流但未连接。",
            needs_revision="把局部概率密度直接当透射率。",
            evaluator="教师复核概念解释；确定性工具只能核验指定数学或数值主张",
        ),
        RubricCriterion(
            criterion_id="FB-R3",
            objective_id="FB-O3",
            description="趋势与数值检验",
            meets="给定固定亚势垒条件后说明宽度增加使 T 减小，并辨识近零精度问题。",
            partial="趋势正确但未说明固定条件或数值限制。",
            needs_revision="趋势错误、混淆共振条件或把数值零说成严格零。",
            evaluator="确定性参考计算加模型候选解释分析；教师复核",
        ),
        RubricCriterion(
            criterion_id="FB-R4",
            objective_id="FB-O4",
            description="独立迁移",
            meets="新任务首答在辅助锁定时提交，解释满足对应标准；延迟测评另行记录。",
            partial="多次无辅助重试后完成；保留首答及所有修订。",
            needs_revision="退出 Solo 获取帮助或缺少可评价作答；不等同于独立通过。",
            evaluator="后端记录锁定与首答；教师评价；无自动课堂成效结论",
        ),
    ),
    tasks=(
        PackageTask(
            task_id="FB-T1",
            stage="commitment",
            prompt="固定 0<E<V0，有限宽度势垒是否使 T 严格为零？先写预测和理由。",
            objective_ids=("FB-O1",),
        ),
        PackageTask(
            task_id="FB-T2",
            stage="reconstruction",
            prompt="用自己的话连接禁阻区指数解、边界连续性和概率流比；说明宽度趋势的条件。",
            objective_ids=("FB-O1", "FB-O2", "FB-O3"),
        ),
        PackageTask(
            task_id="FB-T3",
            stage="solo",
            prompt="在新的亚势垒参数下独立解释宽度变化的趋势；保留第一次未经帮助的作答。",
            objective_ids=("FB-O3", "FB-O4"),
        ),
        PackageTask(
            task_id="FB-T4",
            stage="delayed_independent",
            prompt="由教师在后续课堂提供等值新题并关闭辅助；收集独立作答与理由后按量规复核。",
            objective_ids=("FB-O2", "FB-O4"),
        ),
    ),
    evidence_policy="仅已发布课程证据可支持课程主张；本包是教学设计，不是经教师批准的知识证据。",
    validation_status="source-controlled teaching design; classroom effectiveness unevaluated",
)

# Keep the original object byte-for-byte canonicalizable: existing records pin
# its digest. A revised interpretation is an explicit new selection, never a
# silent replacement in an ongoing conversation.
FINITE_BARRIERS_1_1 = CoursePackage.model_validate({
    **FINITE_BARRIERS.model_dump(),
    "version": "1.1.0",
    "rubric": [
        criterion.model_dump() if criterion.criterion_id != "FB-R4" else {
            **criterion.model_dump(),
            "description": "独立提交条件与独立物理表现分开记录",
            "meets": (
                "新任务首答在应用辅助锁定时提交；教师依据学生原文确认解释满足对应标准。"
                "数值正确另列；延迟测评另行记录，不由单次通过推断长期掌握。"
            ),
            "partial": (
                "首次独立提交是有效行动记录；仅数值相符或反馈后修订完成，"
                "尚不足以确认独立解释达标。"
            ),
            "needs_revision": (
                "教师指出原文中的具体物理错误并给出理由；缺少解释或参考不可用时"
                "标记未评价，不自动作为错误或先修缺陷。"
            ),
            "evaluator": (
                "后端记录任务关联、首答和辅助锁定；工具仅核验指定数值；"
                "模型解释判断为候选；实际教师量规评价单独署名记录。"
            ),
        }
        for criterion in FINITE_BARRIERS.rubric
    ],
    "tasks": [
        task.model_dump() if task.task_id != "FB-T4" else {
            **task.model_dump(),
            "prompt": (
                "由真实教师预先选定未曝光的新题并关闭辅助，保留独立原答后按量规复核。"
                "可参考独立版本的 heldout teacher packet 1.0.0；须先审阅、私发和试测，"
                "其三个完整题型尚未证明难度等值。"
            ),
        }
        for task in FINITE_BARRIERS.tasks
    ],
    "evidence_policy": (
        FINITE_BARRIERS.evidence_policy
        + " 有效独立提交、数值核验、模型解释推断、教师量规判断与掌握结论必须区分。"
        "不足以评价时保留 not_assessed；历史 verified 不回填为掌握证据。"
        " 离线未审阅教师材料见 docs/teacher-packets/finite-barriers-heldout/1.0.0/；"
        "文件名 teacher-only 不是权限控制，不纳入运行时检索或提示。"
    ),
    "validation_status": (
        "source-controlled assessment clarification; teacher packet unreviewed; "
        "alternate-form equivalence unvalidated; classroom effectiveness unevaluated"
    ),
})

_PACKAGES = {
    (package.package_id, package.version): package
    for package in (FINITE_BARRIERS, FINITE_BARRIERS_1_1)
}


def course_package(selection: CoursePackageSelection) -> CoursePackage:
    return _PACKAGES[(selection.package_id, selection.version)]


def available_course_packages() -> tuple[CoursePackage, ...]:
    return tuple(_PACKAGES.values())
